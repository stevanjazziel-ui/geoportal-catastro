"""Independently verify current metric 250m geometry and unchanged positions."""
import json,math
import geopandas as gpd
from shapely import union_all
from shapely.geometry import Point
from refresh_coverage_250m import ROOT,BASE,PACKAGE,OUT

backup=ROOT.parent/'entregas/RESPALDO_ANTES_COBERTURA_250M_20261110/ESCENARIO_FINAL_183.gpkg'
points=[]
for layer in ['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL']:
 old=gpd.read_file(backup,layer=layer);new=gpd.read_file(PACKAGE,layer=layer)
 assert list(old.geometry.to_wkb())==list(new.geometry.to_wkb())
 points.extend(new.geometry)
mask=union_all([p.buffer(250,quad_segs=64) for p in points])
published=gpd.read_file(PACKAGE,layer='COBERTURA_C').geometry.iloc[0]
assert published.symmetric_difference(mask).area<1e-5
for layer,n in [('RADIOS_EXISTENTES_SIMBOLOGIA_250M',103),('COBERTURA_MUNICIPAL_250M',50),('COBERTURA_POLICIA_250M',30)]:
 frame=gpd.read_file(PACKAGE,layer=layer);assert len(frame)==n and frame.RADIO_M.eq(250).all()
 assert all(abs(g.area-math.pi*250**2)<25 for g in frame.geometry)
rays=gpd.read_file(OUT/'LINEAS_PRINCIPALES_250M.geojson').to_crs(32717)
assert len(rays)==612
for line in rays.geometry:assert len(line.coords)==2 and abs(line.length-250)<1e-6
assert len(rays[rays.ID_CAMARA=='RIO-002-DOMO'])==4
axis=union_all(gpd.read_file(BASE/'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA/TRAMO_BOULEVARD_MACAJI_BELLAVISTA.geojson').to_crs(32717).geometry)
gaps=gpd.read_file(OUT/'BRECHA_MACAJI_TRAMO_250M.geojson').to_crs(32717)
expected=axis.difference(mask);assert expected.hausdorff_distance(union_all(gaps.geometry))<1e-6
coverage=json.loads((BASE/'COBERTURA_73_110_183.json').read_text(encoding='utf-8'))['scenarios']['250']
canton=union_all(gpd.read_file(PACKAGE,layer='LIMITE_CANTONAL').geometry)
assert abs(coverage['groups']['combined']['coveredCantonAreaKm2']-mask.intersection(canton).area/1e6)<1e-8
results=json.loads((BASE/'RESULTADOS.json').read_text(encoding='utf-8'));assert results['radiusM']==250
assert abs(results['populationComparison']['scenarios'][-1]['coveredPopulation']-coverage['groups']['combined']['coveredPopulation'])<1e-8
proof={'passed':True,'radiusM':250,'unchangedCameraPositions':183,'straightRays250M':612,'macajiGapM':expected.length,'gapSegments':len(gaps),'areaWithinCantonKm2':mask.intersection(canton).area/1e6,'population73':coverage['groups']['current']['coveredPopulation'],'population183':coverage['groups']['combined']['coveredPopulation']}
(OUT/'VERIFICACION_INDEPENDIENTE.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof))
