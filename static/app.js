'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>v==null?'—':v===0?'0':Math.abs(v)>=1e6||Math.abs(v)<.001?Number(v).toExponential(4):Number(v).toLocaleString('en-US',{maximumSignificantDigits:7});
const palette=['#237b65','#539dcc','#bd954b','#8c7aaf','#8cb56f','#bc7763','#4aa6a8','#a6a870','#758b99'];
let catalog,fields,properties,chemicals,busy=false,currentJob=null,currentResult=null,compareNames=[],sensitivityRows=[];
let selectedSubstance='default substance',selectedScenario='default scenario';
function status(message,error=false,loading=false){const s=$('#status');s.hidden=false;s.className=error?'error':loading?'busy':'';s.textContent=message;}
function setBusy(value){busy=value;$$('button,input,select').forEach(el=>el.disabled=value);}
function dirty(){if(currentResult){$('#result-subtitle').textContent='输入已变更。以下结果对应上次计算，请重新执行模拟。';}}
async function api(path,data){const response=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const body=await response.json();if(!response.ok)throw Error(body.error||`HTTP ${response.status}`);return body;}
function input(f){return `<input id="${f.id}" data-field="${f.id}" aria-label="${esc(f.scale+' '+f.label)}" type="number" step="any" value="${f.default}" required>`;}
function field(f){return `<div class="field"><label for="${f.id}">${esc(f.label)} <span>${esc(f.unit)}</span></label>${input(f)}</div>`;}
function tableFor(group,scales){const fs=fields.filter(f=>f.group===group&&scales.includes(f.scale));const names=[...new Set(fs.map(f=>f.label))];return `<table><thead><tr><th>${group==='emissions'?'Emission · t/yr':'Parameter'}</th>${scales.map(s=>`<th>${s}</th>`).join('')}</tr></thead><tbody>${names.map(name=>`<tr><td>${esc(name)}${group==='landscape'?` <small>${esc(fs.find(f=>f.label===name).unit)}</small>`:''}</td>${scales.map(s=>{const f=fs.find(x=>x.label===name&&x.scale===s);return `<td>${f?input(f):'—'}</td>`}).join('')}</tr>`).join('')}</tbody></table>`;}
function values(){const result={};for(const f of fields){const el=$('#'+f.id);if(el.value.trim()===''||!Number.isFinite(el.valueAsNumber))throw Error(`${f.label} 不能为空，且必须为数值。`);result[f.id]=el.valueAsNumber;}return result;}
function config(){const name=$('#substance').value.trim();if(!chemicals.has(name))throw Error('请选择物质库中的完整名称。');if(name!==selectedSubstance)throw Error('请先完成物质选择，等待属性加载后再运行。');return {substance:name,scenario:$('#scenario').value,values:values()};}
function applyValues(vals){for(const [key,value] of Object.entries(vals)){const el=$('#'+key);if(el)el.value=value;}}
function substanceMeta(name){const c=chemicals.get(name);$('#cas').textContent=c?.cas||'—';$('#chem-class').textContent=c?.chemClass||'未分类（沿用原模型）';}
async function resolveSubstance(name){
 if(busy||!chemicals.has(name))return;
 setBusy(true);status('正在从本地模型解析物质属性…',false,true);
 try{const current=values();const v=Object.fromEntries(Object.entries(current).filter(([k])=>!properties.some(f=>f.id===k)));const result=await api('/api/resolve',{substance:name,scenario:$('#scenario').value,values:v});applyValues(Object.fromEntries(properties.map(f=>[f.id,result.properties[f.id]])));selectedSubstance=name;substanceMeta(name);status(`已加载 ${name}。缺失的物质数据沿用原工作簿的默认/估算规则。`);dirty();}
 catch(e){$('#substance').value=selectedSubstance;status(e.message,true);}
 finally{setBusy(false);}
}
function reset(){applyValues(catalog.defaults);selectedSubstance='default substance';selectedScenario='default scenario';$('#substance').value=selectedSubstance;$('#scenario').value=selectedScenario;$('#years').value=10;substanceMeta(selectedSubstance);$('#results').hidden=true;currentResult=null;currentJob=null;$('#status').hidden=true;}
async function run(mode,extra={}){
 if(busy)return;let payload;
 try{payload={...config(),mode,...extra};if(mode==='dynamic'){payload.years=Number($('#years').value);if(!(payload.years>0))throw Error('动态模拟时间必须大于 0。');}}
 catch(e){status(e.message,true);$('#status').scrollIntoView({block:'center'});return;}
 $$('dialog[open]').forEach(d=>d.close());setBusy(true);status('正在启动本地计算…',false,true);$('#status').scrollIntoView({block:'center'});
 try{
  const start=await api('/api/run',payload);let job;
  do{await new Promise(resolve=>setTimeout(resolve,600));job=await api('/api/jobs/'+start.id);status(job.progress||'计算中…',false,true);}while(job.status==='running');
  if(job.status==='error')throw Error(job.error);
  currentResult=job.result;currentJob=start.id;renderResult();status('计算完成。结果已保存在本机，可下载 CSV、Excel 或 JSON。');$('#results').scrollIntoView({block:'start'});
 }catch(e){status(e.message,true);}finally{setBusy(false);}
}
function downloads(){for(const f of ['csv','xlsx','json'])$('#download-'+f).href=`/api/export/${currentJob}?format=${f}`;const wb=$('#download-workbook');wb.hidden=!currentResult.run_id;if(currentResult.run_id)wb.href='/api/workbook/'+currentResult.run_id;}
function stats(r){return `<div class="stats"><div class="stat"><span>${r.mode==='dynamic'?'稳态参考总质量 / Steady-state mass':'所有尺度总质量 / Total mass'}</span><strong>${fmt(r.total_kg)}<small>kg</small></strong></div><div class="stat"><span>整体持久性 / Overall persistence</span><strong>${fmt(r.persistence_days)}<small>days</small></strong></div><div class="stat"><span>稳态质量平衡相对残差</span><strong>${fmt(r.balance_relative)}</strong></div></div>`;}
function selectScales(){return `<label>尺度 <select id="result-scale">${['Regional','Continental','Moderate','Arctic','Tropical','All'].map(x=>`<option>${x}</option>`).join('')}</select></label>`;}
function outputTable(rows){return `<div class="table-wrap"><table><thead><tr><th>Compartment</th><th>Scale</th><th>Mass (kg)</th><th>Concentration (kg/m³)</th><th>Fugacity (Pa)</th><th>Emission (t/yr)</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.compartment)} <small>${r.id}</small></td><td>${r.scale}</td><td>${fmt(r.mass_kg)}</td><td>${fmt(r.concentration_kg_m3)}</td><td>${fmt(r.fugacity_pa)}</td><td>${fmt(r.emission_t_yr)}</td></tr>`).join('')}</tbody></table></div>`;}
function barChart(labels,nums,unit='kg'){
 const max=Math.max(...nums,1e-30),n=labels.length,height=Math.max(180,n*26+45);
 return `<div class="chart"><svg role="img" aria-label="质量分布柱状图" viewBox="0 0 900 ${height}" style="height:${height}px">${labels.map((l,i)=>{const y=15+i*26;return `<text x="175" y="${y+12}" text-anchor="end" fill="#647970" font-size="11">${esc(l.length>27?l.slice(0,25)+'…':l)}</text><rect x="190" y="${y}" width="${nums[i]/max*540}" height="17" rx="3" fill="${palette[i%palette.length]}"/><text x="${200+nums[i]/max*540}" y="${y+12}" fill="#375c4b" font-size="10">${fmt(nums[i])} ${unit}</text>`}).join('')}</svg></div>`;
}
function lineChart(points,series,xLabel,yLabel){
 const max=Math.max(...series.flatMap(s=>s.values),1e-30),end=points.at(-1)||1;
 let lines='';for(let i=0;i<=4;i++){const y=235-i*50;lines+=`<line x1="85" x2="875" y1="${y}" y2="${y}" stroke="#e1e8de"/><text x="75" y="${y+4}" text-anchor="end" font-size="10" fill="#718371">${fmt(max*i/4)}</text>`;}
 lines+=series.map((s,i)=>`<path d="${s.values.map((v,j)=>`${j?'L':'M'}${85+points[j]/end*790},${235-v/max*200}`).join(' ')}" fill="none" stroke="${palette[i%palette.length]}" stroke-width="2"/>`).join('');
 for(let i=0;i<=4;i++)lines+=`<text x="${85+790*i/4}" y="254" text-anchor="middle" font-size="10" fill="#718371">${fmt(end*i/4)}</text>`;
 return `<div class="chart"><svg viewBox="0 0 900 280" role="img" aria-label="${esc(yLabel)}时间曲线">${lines}<text x="475" y="276" text-anchor="middle" font-size="10" fill="#718371">${esc(xLabel)}</text><text x="85" y="17" font-size="10" fill="#718371">${esc(yLabel)}</text></svg><div class="legend">${series.map((s,i)=>`<span><i style="background:${palette[i%palette.length]}"></i>${esc(s.name)}</span>`).join('')}</div></div>`;
}
function resultWarnings(r){return `<details><summary>计算方法、模型诊断与已知限制</summary><p>${esc(r.method||'每个情景使用独立的本地模型重算。')}</p><p>本地实现修复原始工作簿中未连接的区域/洲际湖水排放。动态模拟与归趋因子由相同的 33×33 传输矩阵求解。尚未验证与官方服务器逐项一致。</p>${r.diagnostics?.length?`<p>原模型保留的诊断错误：${r.diagnostics.map(d=>`${esc(d.sheet)} ${d.count} 处（${d.cells.join(', ')}）`).join('；')}。这些辅助单元格未用于本次质量求解；核心矩阵与质量平衡已检查。</p>`:''}<p>数据库不完整的物质可能使用上游默认参数，数值结果不代表该物质参数已独立验证。详情见<a href="/guide#differences" target="_blank">方法说明</a>。</p></details>`;}
function renderResult(){
 const r=currentResult;$('#results').hidden=false;downloads();const names={steady:'Steady-State Simulation · 稳态结果',dynamic:'Dynamic Simulation · 动态结果',fate:'Fate Factors · 归趋因子',compare:'Chemical Comparison · 物质对比',sensitivity:'Sensitivity Exploration · 敏感性分析'};
 $('#result-title').textContent=names[r.mode];$('#result-subtitle').textContent=`${r.config.substance} · ${r.config.scenario}`;
 if(r.mode==='compare'||r.mode==='sensitivity'){renderBatch();return;}
 let body=stats(r);
 if(r.mode==='fate'){
  body+=`<p class="result-note">FF = −K⁻¹ / 86400，单位为 day（kg ÷ kg/day）。选择排放箱体，查看单位排放在各接收箱体产生的稳态质量响应。</p><div class="result-controls"><label>排放箱体 <select id="fate-source">${r.rows.map((x,i)=>`<option value="${i}">${x.id} · ${x.scale} · ${esc(x.compartment)}</option>`).join('')}</select></label></div><div id="fate-view"></div><details><summary>完整 33 × 33 归趋因子矩阵（day）</summary><div class="table-wrap"><table class="heat-table"><thead><tr><th>接收 ↓ / 排放 →</th>${r.fate.labels.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${r.fate.matrix_days.map((row,i)=>`<tr><th>${r.fate.labels[i]}</th>${row.map(v=>`<td style="background:rgba(36,125,104,${Math.min(.5,Math.log10(1+Math.max(0,v))/12)})">${fmt(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
 }else{
  body+=`<div class="result-controls">${selectScales()}${r.mode==='dynamic'?'<label>纵轴 <select id="dynamic-metric"><option value="mass">Mass (kg)</option><option value="concentration">Concentration (kg/m³)</option></select></label>':''}</div><div id="chart-view"></div><div id="table-view"></div>`;
  if(r.mode==='steady')body+=`<details><summary>介质间质量通量 / Inter-compartment flows</summary><div class="table-wrap"><table><thead><tr><th>From</th><th>To</th><th>kg/yr</th></tr></thead><tbody>${r.fluxes.slice().sort((a,b)=>b.kg_yr-a.kg_yr).map(f=>`<tr><td>${f.source}</td><td>${f.target}</td><td>${fmt(f.kg_yr)}</td></tr>`).join('')}</tbody></table></div></details>`;
 }
 $('#result-body').innerHTML=body+resultWarnings(r);
 if(r.mode==='fate'){$('#fate-source').onchange=renderFate;renderFate();}else{$('#result-scale').onchange=renderScale;if($('#dynamic-metric'))$('#dynamic-metric').onchange=renderScale;renderScale();}
}
function renderScale(){const r=currentResult,scale=$('#result-scale').value,rows=r.rows.filter(x=>scale==='All'||x.scale===scale);
 if(r.mode==='steady'){$('#chart-view').innerHTML=barChart(rows.map(x=>x.id+' '+x.compartment),rows.map(x=>x.mass_kg));$('#table-view').innerHTML=outputTable(rows);}
 else{const d=r.dynamic,concentration=$('#dynamic-metric').value==='concentration';const filtered=rows.map(row=>({row,index:d.labels.indexOf(row.id)}));
 const series=filtered.map(({row,index})=>({name:row.id,values:d.points.map(p=>p.mass_kg[index]/(concentration?row.volume_m3:1))}));
 $('#chart-view').innerHTML=lineChart(d.points.map(p=>p.year),series,'Time (yr)',concentration?'Concentration (kg/m³)':'Mass (kg)');
 $('#table-view').innerHTML=`<p>模拟终点 ${fmt(d.points.at(-1).year)} 年的质量与浓度（逸度为稳态参考）</p>`+outputTable(filtered.map(({row,index})=>({...row,mass_kg:d.points.at(-1).mass_kg[index],concentration_kg_m3:d.points.at(-1).mass_kg[index]/row.volume_m3})));}
}
function renderFate(){const r=currentResult,j=Number($('#fate-source').value);$('#fate-view').innerHTML=barChart(r.rows.map(x=>x.id),r.fate.matrix_days.map(row=>row[j]),'day')+`<p>该排放箱体的总停留时间：<strong>${fmt(r.fate.total_days[j])} days</strong></p>`;}
function renderBatch(){const r=currentResult,ok=r.batch.filter(x=>!x.error),failed=r.batch.length-ok.length;
 let html=`<p>${r.batch.length} 个情景 · ${ok.length} 个成功${failed?` · <strong class="batch-error">${failed} 个失败，具体原因见表格</strong>`:''}</p>`;
 if(ok.length)html+=barChart(ok.map(x=>r.mode==='compare'?x.substance:'Scenario '+x.index),ok.map(x=>x.total_kg));
 html+=`<div class="table-wrap"><table><thead><tr><th>Row</th><th>Substance</th><th>Total (kg)</th><th>Persistence (days)</th><th>状态 / 下载</th></tr></thead><tbody>${r.batch.map(x=>`<tr><td>${x.index}</td><td>${esc(x.substance)}</td><td>${fmt(x.total_kg)}</td><td>${fmt(x.persistence_days)}</td><td>${x.error?`<span class="batch-error">${esc(x.error)}</span>`:`<a href="/api/workbook/${x.run_id}">完整模型 ↓</a>`}</td></tr>`).join('')}</tbody></table></div>`;
 html+=`<details><summary>各情景的箱体质量对比（kg）</summary><div class="table-wrap"><table><thead><tr><th>Compartment</th>${ok.map(x=>`<th>${r.mode==='compare'?esc(x.substance):'Scenario '+x.index}</th>`).join('')}</tr></thead><tbody>${(ok[0]?.rows||[]).map((row,i)=>`<tr><th>${row.id}</th>${ok.map(x=>`<td>${fmt(x.rows[i].mass_kg)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
 $('#result-body').innerHTML=html+resultWarnings(r);
}
function compareList(){$('#compare-list').innerHTML=compareNames.length?compareNames.map((name,i)=>`<div class="tag"><span>${esc(name)}</span><button data-remove="${i}" aria-label="移除 ${esc(name)}">移除</button></div>`).join(''):'<p class="empty">添加要比较的物质</p>';$$('[data-remove]').forEach(b=>b.onclick=()=>{compareNames.splice(Number(b.dataset.remove),1);compareList();});}
function sensitivityTable(){$('#sensitivity-table').innerHTML=`<table><thead><tr><th><input type="checkbox" id="all-rows" aria-label="选择所有情景"></th><th>Row</th>${properties.map(f=>`<th>${f.label}<br>${f.unit}</th>`).join('')}</tr></thead><tbody>${sensitivityRows.map((row,i)=>`<tr><td><input type="checkbox" data-select-row="${i}" aria-label="选择情景 ${i+1}"></td><td>${i+1}</td>${properties.map(f=>`<td><input type="number" step="any" aria-label="Scenario ${i+1} ${f.label}" data-row="${i}" data-key="${f.id}" value="${row[f.id]??''}"></td>`).join('')}</tr>`).join('')}</tbody></table>`;$$('[data-row]').forEach(el=>el.oninput=()=>sensitivityRows[Number(el.dataset.row)][el.dataset.key]=el.value===''?null:Number(el.value));$('#all-rows').onchange=e=>$$('[data-select-row]').forEach(el=>el.checked=e.target.checked);}
function propertyValues(){const all=values();return Object.fromEntries(properties.map(f=>[f.id,all[f.id]]));}
function csvText(rows){return rows.map(row=>row.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n');}
function download(name,text,type='application/json'){const u=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
function parseCSV(text){const rows=[];let row=[],value='',quoted=false;text=text.replace(/^\uFEFF/,'');for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){value+='"';i++;}else quoted=!quoted;}else if(c===','&&!quoted){row.push(value);value='';}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(value);if(row.some(x=>x.trim()))rows.push(row);row=[];value='';}else value+=c;}if(quoted)throw Error('CSV 引号未闭合。');row.push(value);if(row.some(x=>x.trim()))rows.push(row);return rows;}
function guard(fn){return async(...args)=>{try{await fn(...args);}catch(e){status(e.message,true);if($('dialog[open]'))alert(e.message);}};}
async function init(){
 catalog=await api('/api/catalog');fields=catalog.fields;properties=fields.filter(f=>f.group==='properties');chemicals=new Map();for(const c of catalog.chemicals)if(!chemicals.has(c.name))chemicals.set(c.name,c);
 $('#chemical-count').textContent=(catalog.chemicals.length-1).toLocaleString();$('#chemical-list').innerHTML=catalog.chemicals.map(c=>`<option value="${esc(c.name)}">${esc(c.cas)}</option>`).join('');
 $('#properties').innerHTML=properties.map(field).join('');$('#regional-emissions').innerHTML=tableFor('emissions',['Regional','Continental']);$('#global-emissions').innerHTML=tableFor('emissions',['Moderate','Arctic','Tropical']);$('#landscape-table').innerHTML=tableFor('landscape',['Regional','Continental']);$('#shared-landscape').innerHTML=fields.filter(f=>f.group==='landscape'&&f.scale==='All-scale').map(field).join('');
 $('#scenario').innerHTML=catalog.scenarios.map(s=>`<option>${esc(s.name)}</option>`).join('');$('#sweep-param').innerHTML=properties.map(f=>`<option value="${f.id}">${esc(f.label)}</option>`).join('');$('#sweep-param').value='Kow';
 $('#model-form').onsubmit=e=>e.preventDefault();$('#model-form').oninput=dirty;
 $('#substance').onchange=()=>resolveSubstance($('#substance').value.trim());
 $('#substance').onblur=()=>{const name=$('#substance').value.trim();if(name!==selectedSubstance)resolveSubstance(name);};
 $('#reset-properties').onclick=guard(()=>{const name=$('#substance').value.trim();if(!chemicals.has(name))throw Error('请选择物质库中的完整名称。');return resolveSubstance(name);});
 $('#scenario').onchange=()=>{selectedScenario=$('#scenario').value;applyValues(catalog.scenarios.find(s=>s.name===selectedScenario).values);dirty();};
 $('#steady').onclick=()=>run('steady');$('#dynamic').onclick=()=>run('dynamic');$('#fate').onclick=()=>run('fate');$('#clear').onclick=reset;
 $('#zero-emissions').onclick=()=>{for(const f of fields.filter(x=>x.group==='emissions'))$('#'+f.id).value=0;dirty();};
 $('#compare').onclick=()=>{if(!compareNames.length)compareNames=[selectedSubstance,selectedSubstance==='default substance'?'Perfluorobutanoic acid (PFBA)':'default substance'];compareList();$('#compare-dialog').showModal();};
 $('#add-chemical').onclick=guard(()=>{const n=$('#compare-choice').value.trim();if(!chemicals.has(n))throw Error('请选择物质库中的完整名称。');if(!compareNames.includes(n))compareNames.push(n);$('#compare-choice').value='';compareList();});
 $('#run-compare').onclick=()=>run('compare',{chemicals:compareNames});
 $('#sensitivity').onclick=guard(()=>{if(!sensitivityRows.length)sensitivityRows=[propertyValues()];sensitivityTable();$('#sensitivity-dialog').showModal();});
 $$('dialog .close').forEach(b=>b.onclick=()=>b.closest('dialog').close());
 $('#add-row').onclick=guard(()=>{if(sensitivityRows.length>=50)throw Error('最多支持 50 行。');sensitivityRows.push(propertyValues());sensitivityTable();});
 $('#remove-rows').onclick=()=>{const selected=new Set($$('[data-select-row]:checked').map(el=>Number(el.dataset.selectRow)));sensitivityRows=sensitivityRows.filter((_,i)=>!selected.has(i));sensitivityTable();};
 $('#clear-rows').onclick=()=>{sensitivityRows=[];sensitivityTable();};
 $('#run-sensitivity').onclick=guard(()=>{if(!sensitivityRows.length)throw Error('请至少添加一行。');for(const [i,row] of sensitivityRows.entries())for(const f of properties)if(row[f.id]==null||!Number.isFinite(row[f.id]))throw Error(`第 ${i+1} 行 ${f.label} 缺失或无效。`);run('sensitivity',{rows:sensitivityRows});});
 $('#generate-sweep').onclick=guard(()=>{const key=$('#sweep-param').value,min=Number($('#sweep-min').value),max=Number($('#sweep-max').value),n=Number($('#sweep-count').value);if(!Number.isInteger(n)||n<2||n>20||!Number.isFinite(min)||!Number.isFinite(max)||max<min)throw Error('请填写有效扫描范围，行数须为 2–20。');const base=propertyValues();sensitivityRows=Array.from({length:n},(_,i)=>({...base,[key]:min+(max-min)*i/(n-1)}));sensitivityTable();});
 $('#template-csv').onclick=guard(()=>download('simplebox-sensitivity-template.csv','\ufeff'+csvText([properties.map(f=>f.id),properties.map(f=>propertyValues()[f.id])]),'text/csv;charset=utf-8'));
 $('#upload-csv').onclick=()=>$('#sensitivity-file').click();
 $('#sensitivity-file').onchange=guard(async e=>{const file=e.target.files[0];if(!file)return;if(file.size>1000000)throw Error('CSV 文件不得超过 1 MB。');const data=parseCSV(await file.text());const header=data.shift()?.map(x=>x.trim());if(!header||properties.some(f=>!header.includes(f.id)))throw Error('CSV 列名不完整，请使用 Download CSV Template 模板。');if(!data.length||data.length>50)throw Error('CSV 应包含 1–50 行数据。');const parsed=data.map((row,i)=>Object.fromEntries(properties.map(f=>{const text=row[header.indexOf(f.id)]?.trim();if(!text||!Number.isFinite(Number(text)))throw Error(`CSV 第 ${i+2} 行 ${f.id} 不是有效数值。`);return [f.id,Number(text)];})));sensitivityRows=parsed;sensitivityTable();e.target.value='';});
 $('#save-config').onclick=guard(()=>download('simplebox-scenario.json',JSON.stringify({...config(),years:Number($('#years').value),version:1},null,2)));
 $('#load-config').onclick=()=>$('#config-file').click();$('#config-file').onchange=guard(async e=>{const file=e.target.files[0];if(!file)return;if(file.size>1000000)throw Error('情景文件过大。');const p=JSON.parse(await file.text());if(!chemicals.has(p.substance)||!catalog.scenarios.some(s=>s.name===p.scenario))throw Error('情景中的物质或环境场景不存在。');setBusy(true);status('验证并加载情景…',false,true);try{const r=await api('/api/resolve',p);reset();applyValues(r.properties);selectedSubstance=p.substance;selectedScenario=p.scenario;$('#substance').value=p.substance;$('#scenario').value=p.scenario;substanceMeta(p.substance);if(p.years>0&&p.years<=100000)$('#years').value=p.years;status('本地情景已载入。');}finally{setBusy(false);e.target.value='';}});
 reset();
}
init().catch(e=>status('初始化失败：'+e.message,true));
