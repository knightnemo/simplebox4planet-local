import json
import numpy as np
import openpyxl
import pytest
from web.catalog import CATALOG,CHEMICALS,FIELDS,SOURCE
from web.model import calculate,dynamic,fate,validate,CACHE,YEAR,prepare

@pytest.fixture(scope='module')
def baseline():return calculate({})

def test_full_baseline_matches_excel_33_compartments(baseline):
    w=openpyxl.load_workbook(SOURCE,data_only=True)
    expected=np.array([w['engine'].cell(45,c).value*w['input']['L15'].value for c in range(4,37)])
    np.testing.assert_allclose([r['mass_kg'] for r in baseline['rows']],expected,rtol=1e-10)
    assert baseline['balance_relative']<1e-10
    assert len(CATALOG['chemicals'])==3994

def test_web_display_units_and_full_inputs(baseline):
    r=calculate({'values':CATALOG['defaults']})
    np.testing.assert_allclose([x['mass_kg'] for x in r['rows']],[x['mass_kg'] for x in baseline['rows']],rtol=1e-10)

def test_emission_change_matches_excel():
    r=calculate({'values':{'toAir':20000}})
    assert r['rows'][0]['mass_kg']==pytest.approx(137885.540048298,rel=1e-10)

def test_pfas_matches_excel():
    r=calculate({'substance':'Perfluorobutanoic acid (PFBA)'})
    assert r['rows'][0]['mass_kg']==pytest.approx(69443.4776163945,rel=1e-10)
    assert r['properties']['pKa']==-.21

def test_lake_emission_connected_and_export_consistent():
    values={k:0 for k,f in FIELDS.items() if f['group']=='emissions'}
    values['toLakeWater']=100
    r=calculate({'values':values})
    assert r['rows'][1]['emission_t_yr']==pytest.approx(100)
    assert r['rows'][1]['mass_kg']>0
    assert r['balance_relative']<1e-9
    w=openpyxl.load_workbook(CACHE/(r['run_id']+'.xlsx'),data_only=True)
    assert w['output']['C15'].value==pytest.approx(r['rows'][1]['mass_kg'],rel=1e-10)

def test_zero_emissions():
    r=calculate({'values':{k:0 for k,f in FIELDS.items() if f['group']=='emissions'}})
    assert r['total_kg']==0 and r['persistence_days'] is None
    assert np.max(dynamic(r,10)['points'][-1]['mass_kg'])==0

def test_dynamic_initial_condition_and_long_time_limit(baseline):
    d=dynamic(baseline,10000)
    assert all(v==0 for v in d['points'][0]['mass_kg'])
    np.testing.assert_allclose(d['points'][-1]['mass_kg'],[r['mass_kg'] for r in baseline['rows']],rtol=1e-6)
    short=dynamic(baseline,.000001)
    e=np.array(baseline['emissions_mol_s'])*baseline['molecular_weight_kg_mol']
    np.testing.assert_allclose(np.array(short['points'][1]['mass_kg'])/.000001*200/YEAR,e,atol=1e-5)

def test_fate_reconstructs_steady_state(baseline):
    f=fate(baseline)
    e=np.array(baseline['emissions_mol_s'])*baseline['molecular_weight_kg_mol']*86400
    np.testing.assert_allclose(np.array(f['matrix_days'])@e,[r['mass_kg'] for r in baseline['rows']],rtol=1e-10)

def test_all_preset_validation():
    for s in CATALOG['scenarios']:validate({'scenario':s['name'],'values':s['values']})

def test_duplicate_names_use_excel_first_match():
    seen={}
    for row in CATALOG['chemicals']:seen.setdefault(row['name'],row)
    assert len(seen)<len(CATALOG['chemicals'])
    assert CHEMICALS==seen

@pytest.mark.parametrize('values',[{'toAir':-1},{'Molweight':0},{'Kaw':float('nan')},{'toAir':True},{'regFracFresh':2},{'pHAerosol':15},{'not_a_field':1}])
def test_invalid_inputs(values):
    with pytest.raises(ValueError):validate({'values':values})

def test_reject_formula_injection():
    with pytest.raises(ValueError):validate({'values':{'Kow':'=WEBSERVICE("https://example.com")'}})

def test_input_patch_preserves_adjacent_formulas(tmp_path):
    path=tmp_path/'patched.xlsx'
    prepare(path,validate({'substance':'Perfluorobutanoic acid (PFBA)'}))
    before=openpyxl.load_workbook(SOURCE);after=openpyxl.load_workbook(path)
    allowed={('input',c) for c in ('I5','I6','I8','I10')}|{('engine','E5'),('engine','N5')}
    for s in before:
        for row in s:
            for cell in row:
                if (s.title,cell.coordinate) in allowed:continue
                a=cell.value;b=after[s.title][cell.coordinate].value
                if hasattr(a,'text'):assert a.text==b.text and a.ref==b.ref
                else:assert a==b,(s.title,cell.coordinate,a,b)
