#!/usr/bin/env python3
"""Loopback-only local SimpleBox application. No cloud service calls."""
from concurrent.futures import ThreadPoolExecutor
import csv
import io
import json
import mimetypes
from pathlib import Path
import re
import threading
import traceback
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
import uuid

import openpyxl
from web.catalog import CATALOG,FIELDS,ROOT
from web.model import CACHE,calculate,dynamic,fate,soffice_path,validate

JOBS={}; JOB_LOCK=threading.Lock(); POOL=ThreadPoolExecutor(max_workers=2)
def public(result):
    return {k:v for k,v in result.items() if k not in ('matrix','emissions_mol_s','output')}

def work(job_id,payload):
    job=JOBS[job_id]
    try:
        mode=payload.get('mode','steady')
        config=validate(payload)
        if mode in ('steady','dynamic','fate'):
            job.update(progress='正在本机重算 SimpleBox 4.04…')
            r=calculate(config); answer=public(r)
            if mode=='dynamic':
                job.update(progress='正在求解 33 个环境箱体的时间序列…')
                answer['dynamic']=dynamic(r,payload.get('years',10),payload.get('initial_mass_kg'))
            if mode=='fate': answer['fate']=fate(r)
        elif mode in ('compare','sensitivity'):
            entries=payload.get('chemicals' if mode=='compare' else 'rows',[])
            if not isinstance(entries,list) or not 1<=len(entries)<=50:
                raise ValueError('请提供 1–50 个物质或敏感性情景。')
            rows=[]
            for i,entry in enumerate(entries):
                job.update(progress=f'正在计算 {i+1}/{len(entries)}…',completed=i,total=len(entries))
                base=dict(config); vals=dict(config['values'])
                if mode=='compare':
                    base['substance']=entry
                    # Each chemical must resolve its own properties, not inherit the selected chemical.
                    vals={k:v for k,v in vals.items() if FIELDS[k]['group']!='properties'}
                else:
                    if not isinstance(entry,dict): raise ValueError('情景行必须是参数对象。')
                    vals.update(entry)
                base['values']=vals
                try:
                    r=calculate(base)
                    rows.append(dict(index=i+1,substance=base['substance'],values=entry if mode=='sensitivity' else {},
                                     total_kg=r['total_kg'],persistence_days=r['persistence_days'],
                                     rows=r['rows'],run_id=r['run_id'],error=None))
                except (ValueError,RuntimeError) as exc:
                    rows.append(dict(index=i+1,substance=base['substance'],values=entry,error=str(exc)))
            answer=dict(batch=rows,config=config)
        else: raise ValueError('未知计算模式。')
        answer['mode']=mode
        job.update(status='done',progress='计算完成',result=answer)
    except Exception as exc:
        traceback.print_exc()
        job.update(status='error',error=str(exc))

def flat_export(result):
    if result['mode'] in ('compare','sensitivity'):
        keys=list(FIELDS)
        headers=['Index','Substance','Total (kg)','Persistence (days)','Error']+keys
        rows=[[x['index'],x['substance'],x.get('total_kg'),x.get('persistence_days'),x.get('error')]+[x.get('values',{}).get(k) if isinstance(x.get('values'),dict) else None for k in keys] for x in result['batch']]
    elif result['mode']=='dynamic':
        headers=['Time (yr)']+[s+' mass (kg)' for s in result['dynamic']['labels']]
        rows=[[p['year']]+p['mass_kg'] for p in result['dynamic']['points']]
    elif result['mode']=='fate':
        f=result['fate']; headers=['Receiving / emitting (days)']+f['labels']
        rows=[[label]+row for label,row in zip(f['labels'],f['matrix_days'])]
        rows.append(['Total residence time (days)']+f['total_days'])
    else:
        headers=['Compartment','Scale','Name','Mass (kg)','Concentration (kg/m³)','Fugacity (Pa)','Emission (t/yr)','Volume (m³)']
        rows=[[r[k] for k in ('id','scale','compartment','mass_kg','concentration_kg_m3','fugacity_pa','emission_t_yr','volume_m3')] for r in result['rows']]
    return headers,rows

class Handler(BaseHTTPRequestHandler):
    def send(self,status,data,kind='application/json; charset=utf-8',filename=None):
        if isinstance(data,(dict,list)): data=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        if isinstance(data,str): data=data.encode()
        self.send_response(status); self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers(); self.wfile.write(data)
    def local_request(self):
        allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in allowed: return False
        origin=self.headers.get('Origin')
        return not origin or origin in {'http://'+v for v in allowed}
    def do_GET(self):
        if not self.local_request():return self.send(403,{'error':'Local requests only'})
        u=urlparse(self.path); path=u.path
        if path=='/api/health':return self.send(200,dict(status='ok',app='simplebox-local',frontend='studio',engine=soffice_path()))
        if path=='/api/catalog':return self.send(200,CATALOG)
        if path.startswith('/api/jobs/'):
            id=path.rsplit('/',1)[-1]; job=JOBS.get(id)
            if not job:return self.send(404,{'error':'Unknown job'})
            return self.send(200,job)
        if path.startswith('/api/export/'):
            id=path.rsplit('/',1)[-1]; job=JOBS.get(id)
            if not job or job['status']!='done':return self.send(404,{'error':'结果不可用，请重新计算。'})
            result=job['result']; fmt=parse_qs(u.query).get('format',['csv'])[0]
            if fmt=='json':return self.send(200,result,filename='simplebox-results.json')
            headers,rows=flat_export(result)
            if fmt=='xlsx':
                wb=openpyxl.Workbook(); ws=wb.active; ws.title='Results'; ws.append(headers)
                for row in rows:
                    ws.append([("'"+v) if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in row])
                ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
                for cell in ws[1]:cell.font=openpyxl.styles.Font(bold=True,color='FFFFFF'); cell.fill=openpyxl.styles.PatternFill('solid',fgColor='187B72')
                for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=23
                meta=wb.create_sheet('Method'); meta.append(['Source','SimpleBox 4.04 local workbook implementation'])
                meta.append(['Mode',result['mode']]); meta.append(['Config',json.dumps(result['config'],ensure_ascii=False)])
                meta.append(['Limit','Independent local implementation; not certified identical to hosted service.'])
                b=io.BytesIO();wb.save(b)
                return self.send(200,b.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','simplebox-results.xlsx')
            stream=io.StringIO(); writer=csv.writer(stream);writer.writerow(headers)
            for row in rows:writer.writerow([("'"+v) if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in row])
            return self.send(200,'\ufeff'+stream.getvalue(),'text/csv; charset=utf-8','simplebox-results.csv')
        if path.startswith('/api/workbook/'):
            id=path.rsplit('/',1)[-1]
            if not re.fullmatch('[a-f0-9]{24}',id):return self.send(404,{'error':'Unknown run'})
            p=CACHE/(id+'.xlsx')
            if not p.exists():return self.send(404,{'error':'Unknown run'})
            return self.send(200,p.read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','SimpleBox-calculated.xlsx')
        files={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/studio.css':'studio.css','/studio.js':'studio.js','/guide':'guide.html','/favicon.ico':'favicon.svg','/favicon.svg':'favicon.svg'}
        if path not in files:return self.send(404,{'error':'Not found'})
        p=ROOT/'static'/files[path]
        return self.send(200,p.read_bytes(),mimetypes.guess_type(p)[0] or 'application/octet-stream')
    def do_POST(self):
        if not self.local_request():return self.send(403,{'error':'Local requests only'})
        try:
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('仅接受 application/json。')
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=1000000:raise ValueError('请求大小无效。')
            p=json.loads(self.rfile.read(n))
            if self.path=='/api/resolve':
                return self.send(200,public(calculate(p)))
            if self.path!='/api/run':return self.send(404,{'error':'Not found'})
            validate(p)
            with JOB_LOCK:
                if sum(j['status']=='running' for j in JOBS.values())>=4:return self.send(429,{'error':'已有计算在排队，请稍后重试。'})
                id=uuid.uuid4().hex
                JOBS[id]={'id':id,'status':'running','progress':'等待本地计算引擎…'}
                if len(JOBS)>200:
                    old=next((k for k,v in JOBS.items() if v['status']!='running'),None)
                    if old:JOBS.pop(old)
            POOL.submit(work,id,p)
            self.send(202,{'id':id})
        except (ValueError,TypeError) as exc:self.send(400,{'error':str(exc)})
        except Exception as exc:traceback.print_exc();self.send(500,{'error':str(exc)})

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8766);args=parser.parse_args()
    soffice_path()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'SimpleBox local: http://127.0.0.1:{args.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();POOL.shutdown(wait=False,cancel_futures=True)
