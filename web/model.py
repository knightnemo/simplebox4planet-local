"""Recalculate the published workbook locally, then solve its 33-box linear system.

Only input cells and the two documented disconnected lake-emission cells are
patched in a disposable copy. No cached input-dependent result is reused.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from xml.sax.saxutils import escape

import numpy as np
import openpyxl
from scipy.linalg import expm
from .catalog import CATALOG, CHEMICALS, FIELDS, ROOT, SCENARIOS, SOURCE

YEAR=31536000.0
CACHE=ROOT/'runtime/cache'
CACHE.mkdir(parents=True,exist_ok=True)
LOCK=threading.Lock()
ENGINE_VERSION='4.04-local-3'
SCALES={'R':'Regional','C':'Continental','M':'Moderate','A':'Arctic','T':'Tropical'}
BOXES={'a':'Air','w0':'Lake water','w1':'Fresh water','w2':'Sea / surface water','w3':'Deep ocean water',
       'sd1':'Freshwater sediment','sd2':'Marine sediment','sd':'Sediment','s1':'Natural soil','s2':'Agricultural soil','s3':'Other soil','s':'Soil'}

def soffice_path():
    options=[os.environ.get('SOFFICE'),shutil.which('soffice'),'/Applications/LibreOffice.app/Contents/MacOS/soffice',
      str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice')]
    for p in options:
        if p and Path(p).is_file(): return str(Path(p).resolve())
    raise RuntimeError('未找到 LibreOffice。请安装 LibreOffice 或设置 SOFFICE 环境变量。')

def validate(payload):
    if not isinstance(payload,dict): raise ValueError('请求必须是 JSON 对象。')
    substance=payload.get('substance','default substance')
    scenario=payload.get('scenario','default scenario')
    if substance not in CHEMICALS: raise ValueError('请选择物质库中的完整名称。')
    if scenario not in SCENARIOS: raise ValueError('未知环境情景。')
    values=payload.get('values',{})
    if not isinstance(values,dict): raise ValueError('values 必须是对象。')
    cleaned={}
    for k,v in values.items():
        if k not in FIELDS: raise ValueError('未知参数：'+str(k))
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
            raise ValueError(f'{FIELDS[k]["label"]} 必须是有限数值。')
        f=FIELDS[k]
        if k not in ('Tm','pKa','regTemp','contTemp') and v<0: raise ValueError(f'{k} 不能小于零。')
        if k in ('Tm','regTemp','contTemp') and v<=-273: raise ValueError('温度必须高于 −273 °C。')
        if k in ('Molweight','Sol25','Kaw','Kow','GasDiffusion','WaterDiffusion','DryDensity','MineralDensity') and v<=0:
            raise ValueError(f'{k} 必须大于零。')
        if any(x in k for x in ('AreaLand','AreaSea','DepthLake','DepthFresh')) and v<=0:
            raise ValueError(f'{k} 必须大于零。')
        if ('Frac' in k or k.endswith(('Runoff','Infiltration'))) and v>1: raise ValueError(f'{k} 必须在 0–1 之间。')
        if k.startswith('pH') and not 0<=v<=14: raise ValueError(f'{k} 必须在 0–14 之间。')
        cleaned[k]=v
    # Fractions describe the same land surface. Check combined defaults/overrides.
    eff={**CATALOG['defaults'],**SCENARIOS[scenario]['values'],**cleaned}
    for prefix in ('reg','cont'):
        total=sum(eff[prefix+k] for k in ('FracLake','FracFresh','FracNatSoil','FracAgriSoil','FracUrbanSoil'))
        # Published regional presets include rounding discrepancies up to 0.34%.
        if not math.isclose(total,1,abs_tol=.01): raise ValueError(f'{prefix} 的五项土地/水域面积比例之和须接近 1（允许 1% 的原始情景误差），当前为 {total:g}。')
    return dict(substance=substance,scenario=scenario,values=cleaned)

def patch_xml(data,changes):
    """Preserve all other XML bytes, extensions and array formulas."""
    text=data.decode('utf-8')
    for addr,value in changes.items():
        pattern=rf'<c\b(?=[^>]*\br="{re.escape(addr)}")[^>]*?(?:/>|>.*?</c>)'
        old=re.search(pattern,text,re.S)
        attrs=f'r="{addr}"'
        if old:
            style=re.search(r'\bs="([^"]+)"',old.group())
            if style: attrs+=f' s="{style.group(1)}"'
        if isinstance(value,str) and value.startswith('='):
            cell=f'<c {attrs}><f>{escape(value[1:])}</f><v></v></c>'
        elif isinstance(value,str):
            cell=f'<c {attrs} t="inlineStr"><is><t>{escape(value)}</t></is></c>'
        elif value is None: cell=f'<c {attrs}/>'
        else: cell=f'<c {attrs}><v>{value!r}</v></c>'
        if old: text=text[:old.start()]+cell+text[old.end():]
        else:
            row=re.search(rf'<row\b[^>]*\br="{re.search(r"\d+",addr).group()}"[^>]*>.*?</row>',text,re.S)
            if not row: raise RuntimeError('模型缺少输入行：'+addr)
            # Most I-column input cells exist in source. Insert in sorted column order if absent.
            from openpyxl.utils.cell import coordinate_from_string,column_index_from_string
            target=column_index_from_string(coordinate_from_string(addr)[0])
            pos=row.end()-6
            for c in re.finditer(r'<c\b[^>]*\br="([A-Z]+)\d+"',row.group()):
                if column_index_from_string(c.group(1))>target:
                    pos=row.start()+c.start(); break
            text=text[:pos]+cell+text[pos:]
    return text.encode('utf-8')

def prepare(path,config):
    changes={'I5':config['substance'],'I6':None,'I8':config['scenario'],'I10':'defaults only'}
    changes.update({'I'+str(FIELDS[k]['row']):v for k,v in config['values'].items()})
    with zipfile.ZipFile(SOURCE) as src,zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data=src.read(item.filename)
            if item.filename=='xl/worksheets/sheet2.xml': data=patch_xml(data,changes)
            # Upstream engine had these two emissions hardcoded to 0 despite visible inputs.
            if item.filename=='xl/worksheets/sheet11.xml': data=patch_xml(data,{'E5':'=E.w0R','N5':'=E.w0C'})
            if item.filename.startswith('xl/worksheets/') and item.filename.endswith('.xml'):
                # Imported formula caches otherwise retain the old text-selection branch in Calc.
                def clear_cache(match):
                    cell=match.group(0)
                    if b'<f' in cell:
                        cell=re.sub(rb'<v(?:\s[^>]*)?>.*?</v>',b'',cell,flags=re.S)
                    return cell
                data=re.sub(rb'<c\b[^>]*?(?:/>|>.*?</c>)',clear_cache,data,flags=re.S)
            if item.filename=='xl/workbook.xml':
                data=re.sub(rb'<calcPr\b[^>]*/>',b'<calcPr calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>',data)
            dst.writestr(item,data)

def numeric(v,location):
    if not isinstance(v,(float,int)) or not math.isfinite(v):
        raise ValueError(f'模型在 {location} 无法计算（{v}）。请检查物质数据或参数，不能将缺失结果视为零。')
    return float(v)

def extract(path,config):
    w=openpyxl.load_workbook(path,data_only=True)
    e=w['engine']; inp=w['input']
    labels=[e.cell(3,c).value for c in range(4,37)]
    K=np.array([[numeric(e.cell(r,c).value,f'engine!{e.cell(r,c).coordinate}') for c in range(4,37)] for r in range(9,42)])
    emissions=np.array([numeric(e.cell(5,c).value,f'engine!{e.cell(5,c).coordinate}') for c in range(4,37)])
    volumes=np.array([numeric(e.cell(4,c).value,f'engine!{e.cell(4,c).coordinate}') for c in range(4,37)])
    mw=numeric(inp['L15'].value,'input!L15')
    mass_mol=np.linalg.solve(-K,emissions)
    mass=mass_mol*mw
    if (volumes<=0).any() or (mass < -1e-6).any() or not np.isfinite(mass).all():
        raise ValueError('参数导致非物理体积、负质量或无法计算的模型。')
    residual=K@mass_mol+emissions
    rel=float(np.max(np.abs(residual))/max(float(np.max(np.abs(emissions))),1e-30))
    if rel>1e-7: raise ValueError('质量守恒残差过大，结果未通过检查。')
    rows=[]
    for i,label in enumerate(labels):
        f=e.cell(51,i+4).value
        rows.append(dict(id=label,scale=SCALES[label[-1]],compartment=BOXES[label[:-1]],
            mass_kg=float(max(0,mass[i])),concentration_kg_m3=float(max(0,mass[i])/volumes[i]),
            fugacity_pa=float(f) if isinstance(f,(int,float)) else None,
            emission_t_yr=float(emissions[i]*mw*YEAR/1000),volume_m3=float(volumes[i])))
    props={}
    for key,f in FIELDS.items():
        r=f['row']; v=inp.cell(r,12).value
        if not isinstance(v,(int,float)): continue
        if r==15: v*=1000
        elif r==39 or r in (118,138): v-=273
        elif r==37: v*=mw*1000
        elif f['group']=='emissions': v*=mw*YEAR/1000
        elif r in (111,112,129,130): v/=1e6
        elif r in (120,140,126,146): v*=YEAR*1000
        props[key]=v
    flux=[]
    for j in range(33):
        for i in range(33):
            if i!=j and K[i,j]>0:
                flux.append(dict(source=labels[j],target=labels[i],kg_yr=float(K[i,j]*mass[j]*YEAR)))
    total=float(mass.sum()); input_rate=float(emissions.sum()*mw)
    diagnostics=[]
    for name in ('input','output','engine','formulas'):
        errors=[c.coordinate for row in w[name] for c in row if c.data_type=='e']
        if errors: diagnostics.append(dict(sheet=name,count=len(errors),cells=errors[:8]))
    output=[]
    for row in w['output'].iter_rows():
        vals=[c.value for c in row]
        if any(v is not None for v in vals):
            while vals and vals[-1] is None: vals.pop()
            output.append(dict(row=row[0].row,values=vals))
    w.close()
    return dict(config=config,rows=rows,total_kg=total,emission_kg_s=input_rate,
                persistence_days=total/input_rate/86400 if input_rate>0 else None,
                balance_relative=rel,properties=props,chemClass=CHEMICALS[config['substance']]['chemClass'],
                fluxes=flux,diagnostics=diagnostics,output=output,
                matrix=K.tolist(),emissions_mol_s=emissions.tolist(),molecular_weight_kg_mol=mw,
                method='Published SimpleBox 4.04 workbook recalculated with local LibreOffice; 33-box linear solve.',
                engine_version=ENGINE_VERSION)

def calculate(payload):
    config=validate(payload)
    key=hashlib.sha256((ENGINE_VERSION+json.dumps(config,sort_keys=True)).encode()).hexdigest()[:24]
    resultfile=CACHE/(key+'.json'); xlsx=CACHE/(key+'.xlsx')
    with LOCK:
        if resultfile.exists() and xlsx.exists(): return json.loads(resultfile.read_text())
        with tempfile.TemporaryDirectory(prefix='simplebox-') as tmp:
            d=Path(tmp); source=d/'model.xlsx'; out=d/'out'; out.mkdir()
            prepare(source,config)
            run=subprocess.run([soffice_path(),'-env:UserInstallation='+ (d/'profile').as_uri(),'--headless',
                '--convert-to','xlsx','--outdir',str(out),str(source)],capture_output=True,text=True,timeout=120)
            target=out/'model.xlsx'
            if run.returncode or not target.exists():
                raise RuntimeError('本地计算引擎未生成结果：'+(run.stderr or run.stdout)[-1000:])
            result=extract(target,config); result['run_id']=key
            shutil.copyfile(target,xlsx)
            resultfile.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
            return result

def dynamic(result,years,initial=None):
    if not isinstance(years,(int,float)) or not math.isfinite(years) or not 0<years<=100000:
        raise ValueError('模拟时间必须大于 0 且不超过 100000 年。')
    K=np.array(result['matrix']); e=np.array(result['emissions_mol_s']); mw=result['molecular_weight_kg_mol']
    # Exact constant-source solution with augmented matrix; works even with slow rates.
    A=np.zeros((34,34)); A[:33,:33]=K; A[:33,33]=e
    state=np.zeros(34); state[-1]=1
    if initial is not None:
        a=np.asarray(initial,dtype=float)
        if a.shape!=(33,) or not np.isfinite(a).all() or (a<0).any(): raise ValueError('初始质量必须为 33 个非负有限数值（kg）。')
        state[:33]=a/mw
    step=expm(A*years*YEAR/200)
    points=[]
    for i in range(201):
        points.append(dict(year=years*i/200,mass_kg=(np.maximum(state[:33],0)*mw).tolist()))
        state=step@state
    if not np.isfinite(state).all(): raise ValueError('动态积分未产生有限结果。')
    return dict(points=points,labels=[r['id'] for r in result['rows']],
                method='dM/dt = K M + E; constant emissions, initial mass zero unless supplied; matrix exponential.')

def fate(result):
    K=np.array(result['matrix']); factors=np.linalg.solve(-K,np.eye(33))/86400
    return dict(labels=[r['id'] for r in result['rows']],matrix_days=factors.tolist(),
                total_days=factors.sum(axis=0).tolist(),method='FF = −K⁻¹ / 86400. Rows: receiving compartments; columns: emitting compartments; unit: day.')
