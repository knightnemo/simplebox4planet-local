"""Public UI field mappings; workbook remains the authoritative model/data source."""
from pathlib import Path
import warnings
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'SimpleBox4Planet/SimpleBoxSubOriginal.xlsx'
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

PROPERTIES = [
 ('Molweight',15,'Molecular Weight','g/mol',6), ('Tm',39,'Tm','°C',7),
 ('pKa',22,'pKa','−',5), ('Pvap25',35,'Pvap25','Pa',8),
 ('Sol25',37,'Sol25','mg/L',9), ('Kaw',19,'Kaw','−',10),
 ('Kow',20,'Kow','−',11), ('Ksw',17,'Ksw','−',12),
 ('Kdeg_air',66,'kdeg(air)','s⁻¹',17), ('Kdeg_water',70,'kdeg(water)','s⁻¹',18),
 ('Kdeg_sed',74,'kdeg(sed)','s⁻¹',19), ('Kdeg_soil',75,'kdeg(soil)','s⁻¹',20)]
FIELDS = {}
def field(key,row,label,unit,group,scale='',default=None):
    FIELDS[key] = dict(id=key,row=row,label=label,unit=unit,group=group,scale=scale,default=default)
for key,row,label,unit,col in PROPERTIES:
    field(key,row,label,unit,'properties')
for suffix,start,scale in [('',80,'Regional'),('Cont',88,'Continental')]:
    for offset,(key,label) in enumerate([('toAir','Air'),('toLakeWater','Lake water'),('toFreshWater','Fresh water'),('toSea','Sea water'),('toNatSoil','Natural soil'),('toAgriSoil','Agricultural soil'),('toOtherSoil','Other soil')]):
        field(key+suffix,start+offset,label,'t/yr','emissions',scale)
for suffix,start,scale in [('Mod',96,'Moderate'),('Arc',100,'Arctic'),('Trop',104,'Tropical')]:
    for offset,(key,label) in enumerate([('toAir','Air'),('toWater','Water'),('toSoil','Soil')]):
        field(key+suffix,start+offset,label,'t/yr','emissions',scale)
LAND = [('AreaLand','Area land','km²',111,129),('AreaSea','Area sea','km²',112,130),
 ('FracLake','Fraction lake water','−',113,133),('FracFresh','Fraction fresh water','−',114,134),
 ('FracNatSoil','Fraction natural soil','−',115,135),('FracAgriSoil','Fraction agricultural soil','−',116,136),
 ('FracUrbanSoil','Fraction urban / industrial soil','−',117,137),('Temp','Temperature','°C',118,138),
 ('Wind','Wind speed','m/s',119,139),('Precip','Average precipitation','mm/yr',120,140),
 ('DepthLake','Depth lake water','m',121,141),('DepthFresh','Depth fresh water','m',122,142),
 ('FracDischarge','Fresh water discharge to other scale','−',123,143),('Runoff','Fraction run off','−',124,145),
 ('Infiltration','Fraction infiltration','−',125,144),('SoilErosion','Soil erosion','mm/yr',126,146)]
for key,label,unit,rr,cr in LAND:
    field('reg'+key,rr,label,unit,'landscape','Regional')
    field('cont'+key,cr,label,unit,'landscape','Continental')
for row,key,label,unit in [(149,'pHAerosol','pH aerosol','−'),(150,'pHFreshWater','pH fresh water','−'),
 (151,'pHSeaWater','pH sea water','−'),(152,'pHNaturalSoil','pH natural soil','−'),
 (153,'pHAgricSoil','pH agricultural soil','−'),(154,'pHOtherSoil','pH other soil','−'),
 (155,'GasDiffusion','Gas phase diffusion coefficient','m²/s'),(156,'WaterDiffusion','Water phase diffusion coefficient','m²/s'),
 (157,'MassFraction','Organic carbon fraction in aerosol','−'),(158,'StandardMassFraction','Organic carbon fraction in soil / sediment','−'),
 (159,'DryDensity','Dry density of aerosol solids','kg/m³'),(160,'MineralDensity','Mineral density of sediment and soil','kg/m³')]:
    field(key,row,label,unit,'landscape','All-scale')

def catalog():
    w = openpyxl.load_workbook(SOURCE, data_only=True)
    inp=w['input']; sub=w['substances']; scenarios=w['scenarios']
    for f in FIELDS.values():
        r=f['row']; v=inp.cell(r,12).value
        # Display in user-input units, not internal SI/mol units.
        if r==15: v*=1000
        elif r==39 or r in (118,138): v-=273
        elif r==37: v*=inp['L15'].value*1000
        elif f['group']=='emissions': v*=inp['L15'].value*31536000/1000
        elif r in (111,112,129,130): v/=1e6
        elif r in (120,140,126,146): v*=31536000*1000
        f['default']=v
    chemicals=[]
    for r in [8]+list(range(15,4008)):
        name=sub.cell(r,2).value
        if not name: continue
        props={key:sub.cell(r,col).value for key,_,_,_,col in PROPERTIES}
        props={k:v for k,v in props.items() if isinstance(v,(int,float))}
        chemicals.append(dict(name=name,cas=str(sub.cell(r,3).value or '').strip(),
                              chemClass=sub.cell(r,4).value or '',row=r,properties=props))
    presets=[]
    for c in range(10,29):
        name=scenarios.cell(3,c).value
        if not name: continue
        lookup={scenarios.cell(r,7).value:scenarios.cell(r,c).value for r in range(7,71)}
        values={key:lookup[inp.cell(f['row'],7).value] for key,f in FIELDS.items()
                if inp.cell(f['row'],7).value in lookup and isinstance(lookup[inp.cell(f['row'],7).value],(int,float))}
        presets.append(dict(name=name,values=values))
    w.close()
    return dict(fields=list(FIELDS.values()),chemicals=chemicals,scenarios=presets,
                defaults={k:f['default'] for k,f in FIELDS.items()},sourceCommit='297dfacb633afc8140760b754360b3ff5a7d83c6')

CATALOG = catalog()
CHEMICALS = {}
for chemical in CATALOG['chemicals']:
    # Excel exact-match VLOOKUP uses the first duplicate, not the last.
    CHEMICALS.setdefault(chemical['name'],chemical)
SCENARIOS = {s['name']:s for s in CATALOG['scenarios']}
