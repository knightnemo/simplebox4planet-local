"""Real HTTP integration tests, including all actions and spreadsheet exports."""
import io
import json
import threading
import time
import urllib.error
import urllib.request
import openpyxl
import pytest
from http.server import ThreadingHTTPServer
from server import Handler

@pytest.fixture(scope='module')
def url():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown();server.server_close()

def request(url,path,payload=None):
    req=urllib.request.Request(url+path,data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as response:return response.read()

def run(url,payload):
    job=json.loads(request(url,'/api/run',payload))['id']
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        state=json.loads(request(url,'/api/jobs/'+job))
        if state['status']=='done':return job,state['result']
        if state['status']=='error':raise AssertionError(state['error'])
        time.sleep(.15)
    raise AssertionError('Job timeout')

@pytest.mark.parametrize('mode',['steady','dynamic','fate','compare','sensitivity'])
def test_actions_and_exports(url,mode):
    payload={'mode':mode,'years':10}
    if mode=='compare':payload['chemicals']=['default substance','Perfluorobutanoic acid (PFBA)']
    if mode=='sensitivity':payload['rows']=[{'Kow':1000},{'Kow':5000}]
    job,result=run(url,payload)
    assert result['mode']==mode
    if mode in ('compare','sensitivity'):
        assert len(result['batch'])==2
        assert all(not row['error'] for row in result['batch'])
        assert result['batch'][0]['total_kg']!=result['batch'][1]['total_kg']
    if mode=='dynamic':assert len(result['dynamic']['points'])==201
    if mode=='fate':assert len(result['fate']['matrix_days'])==33
    csv=request(url,f'/api/export/{job}?format=csv').decode('utf-8-sig')
    assert len(csv.splitlines())>2
    xlsx=request(url,f'/api/export/{job}?format=xlsx')
    wb=openpyxl.load_workbook(io.BytesIO(xlsx),data_only=True)
    assert wb['Results'].max_row>2 and 'Method' in wb.sheetnames
    assert json.loads(request(url,f'/api/export/{job}?format=json'))['mode']==mode
    if result.get('run_id'):
        native=request(url,'/api/workbook/'+result['run_id'])
        assert openpyxl.load_workbook(io.BytesIO(native),read_only=True)['input']['I5'].value=='default substance'

def test_batch_errors_remain_visible(url):
    _,r=run(url,{'mode':'sensitivity','rows':[{'Molweight':-1},{'Kow':5000}]})
    assert r['batch'][0]['error'] and r['batch'][1]['total_kg']>0

def test_local_only_and_input_validation(url):
    with pytest.raises(urllib.error.HTTPError) as err:
        request(url,'/api/run',{'values':{'toAir':-1}})
    assert err.value.code==400
    req=urllib.request.Request(url+'/api/catalog',headers={'Origin':'https://example.com'})
    with pytest.raises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
    assert err.value.code==403
    for path in ['/','/app.js','/style.css','/guide','/favicon.svg']:
        assert request(url,path)
