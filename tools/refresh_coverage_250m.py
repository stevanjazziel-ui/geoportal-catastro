"""User-authorized change of all current camera coverage from 200 to 250 m."""
import json, shutil, sys, zipfile, hashlib, math
from pathlib import Path
import geopandas as gpd
import pyogrio
from shapely import union_all
from shapely.geometry import mapping, LineString
from shapely.ops import transform
from pyproj import Transformer
from build_camera_population_comparison import population_comparison
from build_current_camera_coverage import build_coverage
import apply_police_kde_intersections as methods

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/json.loads((ROOT/'sig-bridge-active.json').read_text())['root']
PACKAGE=BASE/'ESCENARIO_FINAL_183.gpkg'
OUT=ROOT/'data/seguridad-riobamba/COBERTURA_250M_20261110'
OLD=ROOT/'data/seguridad-riobamba/COBERTURA_RECTA_20261110'
UNPROJECT=Transformer.from_crs(32717,4326,always_xy=True).transform
def read(name):
 return gpd.read_file(PACKAGE,layer=name).to_crs(32717)
def records(frame):
 return [(r.geometry,{k:None if isinstance(v,float) and not math.isfinite(v) else v for k,v in r.drop('geometry').to_dict().items()}) for _,r in frame.iterrows()]
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf-8')
def save(name,frame):
 pyogrio.write_dataframe(frame,PACKAGE,layer=name)
 pyogrio.write_dataframe(frame.to_crs(4326),BASE/(name+'.geojson'),driver='GeoJSON')
def features(rows):return {'type':'FeatureCollection','features':[{'type':'Feature','properties':p,'geometry':mapping(transform(UNPROJECT,g))} for g,p in rows]}
def main():
 backup=ROOT.parent/'entregas/RESPALDO_ANTES_COBERTURA_250M_20261110'
 if not backup.exists():shutil.copytree(BASE,backup)
 OUT.mkdir(exist_ok=True)
 frames=[read(n) for n in ['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL']]
 e,m,p=map(records,frames);points=[g for g,_ in e+m+p]
 assert [len(f) for f in frames]==[103,50,30]
 camera_hash=hashlib.sha256(''.join(g.wkb_hex for g in points).encode()).hexdigest()
 urban=union_all(read('PLATAFORMAS_TERRITORIALES').geometry);canton=union_all(read('LIMITE_CANTONAL').geometry)
 blocks=read('MANZANAS_COBERTURA');events=read('INCIDENTES_CLASIFICADOS')
 stats={(scope,cat):records(read('GI_'+scope+'_'+cat)) for scope in ['URBANO','RURAL'] for cat in methods.CLASSES}
 axes_frame=read('CORREDORES');axes={key:union_all(axes_frame.loc[axes_frame.CORREDOR==key].geometry) for key in methods.CORRIDORS}
 masks={code:union_all([g.buffer(250,quad_segs=64) for g,_ in rows]) for code,rows in [('A',e),('B',e+m),('C',e+m+p)]}
 result=json.loads((BASE/'RESULTADOS.json').read_text(encoding='utf-8'))
 for field in ['territorial','population','incidents','hotspots','corridors']:result[field]=[]
 analyzed=sum(v['POBLACION']*g.intersection(urban).area/g.area for g,v in records(blocks) if v.get('POBLACION') is not None)
 for code,mask in masks.items():
  print('Recalculating scenario',code,flush=True)
  save('COBERTURA_'+code,gpd.GeoDataFrame([{'ESCENARIO':code,'RADIO_M':250,'geometry':mask}],crs=32717))
  result['territorial'].append({'ESCENARIO':code,'AREA_TOTAL_URBANA_KM2':urban.area/1e6,'AREA_CUBIERTA_URBANA_KM2':mask.intersection(urban).area/1e6,'PCT_URBANO':100*mask.intersection(urban).area/urban.area,'AREA_TOTAL_CANTON_KM2':canton.area/1e6,'AREA_CUBIERTA_CANTON_KM2':mask.intersection(canton).area/1e6,'PCT_CANTON':100*mask.intersection(canton).area/canton.area,'BUFFER_DISUELTO_KM2':mask.area/1e6})
  rows,included=methods.incident_metrics(records(events),mask,urban,canton)
  result['incidents'] += [{**v,'ESCENARIO':code} for v in rows];events['CUB_'+code]=included
  updated,summaries=methods.update_statistics(stats,mask)
  result['hotspots'] += [{**v,'ESCENARIO':code} for v in summaries]
  for key,rows in updated.items():
   stats[key]=[(g,{**v,'COB_'+code+'_PCT':v['COB_C_PCT'],'ESTADO_'+code:v['ESTADO_C']}) for g,v in rows]
  covered=sum(v['POBLACION']*g.intersection(mask.intersection(urban)).area/g.area for g,v in records(blocks) if v.get('POBLACION') is not None)
  result['population'].append({'ESCENARIO':code,'POBLACION_ANALIZADA':analyzed,'POBLACION_CUBIERTA':covered,'POBLACION_NO_CUBIERTA':analyzed-covered,'PCT_CUBIERTO':100*covered/analyzed})
  blocks['COB_'+code+'_PCT']=[100*g.intersection(mask).area/g.area for g in blocks.geometry]
  blocks['POB_'+code+'_CUBIERTA']=blocks.POBLACION*blocks['COB_'+code+'_PCT']/100
  for key,axis in axes.items():
   result['corridors'].append({'ESCENARIO':code,'CORREDOR':key,'TOTAL_M':axis.length,'CUBIERTO_M':axis.intersection(mask).length,'NO_CUBIERTO_M':axis.difference(mask).length,'PCT_CUBIERTO':100*axis.intersection(mask).length/axis.length})
 pyogrio.write_dataframe(blocks,PACKAGE,layer='MANZANAS_COBERTURA');pyogrio.write_dataframe(events,PACKAGE,layer='INCIDENTES_CLASIFICADOS')
 for (scope,cat),rows in stats.items():pyogrio.write_dataframe(gpd.GeoDataFrame([dict(v,geometry=g) for g,v in rows],crs=32717),PACKAGE,layer='GI_'+scope+'_'+cat)
 for frame,name,key in zip(frames,['RADIOS_EXISTENTES_SIMBOLOGIA_250M','COBERTURA_MUNICIPAL_250M','COBERTURA_POLICIA_250M'],['ID_CAMARA','ID_PROPUESTA','ID_POLICIA']):
  disks=frame[[key,'geometry']].copy();disks['RADIO_M']=250
  if 'REQUIERE_CAMBIO' in frame:disks['REQUIERE_CAMBIO']=frame.REQUIERE_CAMBIO
  disks.geometry=disks.geometry.buffer(250,resolution=64);save(name,disks)
 result.update(radiusM=250,coverageRevision='COBERTURA_250M_20261110',populationComparison=population_comparison(e,m,p,records(blocks),urban,250),authorizationRadius='Usuario: pon todas las coberturas a 250m')
 dump(BASE/'RESULTADOS.json',result)
 methods.RADIUS=250
 corridor=methods.corridor_view(axes,masks,e,m,p);corridor['metadata']['sourcePackage']=BASE.name;dump(BASE/'CORRIDOR_COVERAGE_250M.json',corridor)
 print('Building 73/110/183 census coverage at 250m',flush=True)
 coverage=json.loads((BASE/'COBERTURA_73_110_183.json').read_text(encoding='utf-8'))
 new=build_coverage(e,m,p,records(blocks),records(read('PLATAFORMAS_TERRITORIALES')),BASE,canton=canton,radii=(250,))
 coverage['scenarios']['250']=new['scenarios']['250'];coverage['sourcePackageSha256']=hashlib.sha256(PACKAGE.read_bytes()).hexdigest();dump(BASE/'COBERTURA_73_110_183.json',coverage)
 # Extend each verified straight bearing to 250 m, without any further ray.
 rays=gpd.read_file(OLD/'LINEAS_PRINCIPALES_200M.geojson').to_crs(32717)
 def extend(line):
  a,b=list(line.coords);return LineString([a,(a[0]+1.25*(b[0]-a[0]),a[1]+1.25*(b[1]-a[1]))])
 rays.geometry=rays.geometry.map(extend);rays['HASTA_M']=250.;rays['LONGITUD_M']=250.
 rays.to_crs(4326).to_file(OUT/'LINEAS_PRINCIPALES_250M.geojson',driver='GeoJSON')
 axis=union_all(gpd.read_file(BASE/'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA/TRAMO_BOULEVARD_MACAJI_BELLAVISTA.geojson').to_crs(32717).geometry)
 gap=axis.difference(masks['C']);parts=list(gap.geoms) if hasattr(gap,'geoms') else [gap]
 gaps=[(g,{'ID':f'MACAJI-250M-{i:03d}','CORREDOR':'TRAMO_MACAJI_BELLAVISTA_APROBADO','LONGITUD_M':g.length,'RADIO_CALCULO_M':250}) for i,g in enumerate(parts,1) if not g.is_empty and g.length>1e-6]
 dump(OUT/'BRECHA_MACAJI_TRAMO_250M.geojson',features(gaps));shutil.copyfile(OLD/'CAMARAS_MACAJI_BELLAVISTA.geojson',OUT/'CAMARAS_MACAJI_BELLAVISTA.geojson')
 scenarios={code:{'totalMacajiM':axis.length,'coveredMacaji250M':axis.intersection(mask).length,'uncoveredMacaji250M':axis.difference(mask).length,'coveredPct':100*axis.intersection(mask).length/axis.length} for code,mask in masks.items()}
 summary=json.loads((OLD/'RESUMEN.json').read_text(encoding='utf-8'))
 for k in list(summary):
  if '200M' in k:del summary[k]
 summary.update(radiusForGapM=250,primaryRadiusM=250,visualExtensions=0,formerVisual50IncludedInCoverage=True,extra50IncludedInGapCalculation=True,method='Diferencia del eje aprobado y union disuelta de buffers de 250 m, EPSG:32717, 64 segmentos por cuadrante.',streetMethod='Rayos rectos desde cada camara hasta 250 m. Sin extension adicional.',scenarios=scenarios,**scenarios['C'])
 dump(OUT/'RESUMEN.json',summary)
 rays.to_file(OUT/'COBERTURA_250M.gpkg',layer='RAYOS_RECTOS_250M',driver='GPKG')
 if gaps:gpd.GeoDataFrame([dict(v,geometry=g) for g,v in gaps],crs=32717).to_file(OUT/'COBERTURA_250M.gpkg',layer='TRAMOS_SIN_COBERTURA_MACAJI',driver='GPKG')
 assert hashlib.sha256(''.join(g.wkb_hex for f in frames for g in f.geometry).encode()).hexdigest()==camera_hash
 proof={'passed':True,'cameraPositionsUnchanged':True,'cameras':183,'radiusM':250,'rayCount':len(rays),'gapLengthM':gap.length,'gapSegments':len(gaps),'population73':new['scenarios']['250']['groups']['current']['coveredPopulation'],'population183':new['scenarios']['250']['groups']['combined']['coveredPopulation']}
 dump(OUT/'VALIDACION.json',proof)
 (BASE/'INFORME_COBERTURA_250M.md').write_text('# Cobertura potencial de 250 m\n\nCambio de radio autorizado por el usuario. Se mantienen las 183 posiciones. Buffers disueltos EPSG:32717; 64 segmentos por cuadrante. Area y poblacion sin duplicar solapes. Rayos rectos hasta 250 m; los ultimos 50 m ahora forman parte del analisis. Gi* y KDE no recalculados; se actualiza su cobertura.\n\n'+json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(proof),flush=True)
if __name__=='__main__':main()
