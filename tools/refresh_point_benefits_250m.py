"""Reconcile per-camera overlap and downloadable benefit tables at 250m."""
import json,hashlib,zipfile
import geopandas as gpd
import numpy as np
import pyogrio
from shapely import union_all,covers
from refresh_coverage_250m import BASE,PACKAGE
frames=[gpd.read_file(PACKAGE,layer=n) for n in ['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL']]
events=gpd.read_file(PACKAGE,layer='INCIDENTES_CLASIFICADOS');ep=np.asarray(events.geometry,dtype=object)
axes=gpd.read_file(PACKAGE,layer='CORREDORES');exclusive=[];overlaps=[]
all_disks=[[p.buffer(250,quad_segs=64) for p in f.geometry] for f in frames]
for k,name in [(1,'PROPUESTA_MUNICIPAL_50_FINAL'),(2,'PROPUESTA_POLICIA_30_FINAL')]:
 f=frames[k]
 for pos,(idx,row) in enumerate(f.iterrows()):
  disk=all_disks[k][pos];others=union_all([v for j,items in enumerate(all_disks) if j<=k for i,v in enumerate(items) if j!=k or i!=pos]);ex=disk.difference(others);over=disk.intersection(others)
  for field,value in {'AREA_BUFFER_M2':disk.area,'AREA_EXCLUSIVA_M2':ex.area,'AREA_SOLAPADA_M2':over.area,'SOLAPE_PREVIO_PCT':100*over.area/disk.area,'RADIO_M':250,'POBLACION_ASOCIADA':row.POBLACION_ASOCIADA_250M,'N_TOTAL':row.DELINCUENCIA_250M+row.VIOLENCIA_250M+row.CONVIVENCIA_250M}.items():f.at[idx,field]=value
  new=covers(disk,ep)&~covers(others,ep)&events.AMBITO.ne('EXTERNO_CANTON').to_numpy()
  for category,field in [('DELINCUENCIA','EVENTOS_D_NUEVOS'),('VIOLENCIA','EVENTOS_V_NUEVOS')]:f.at[idx,field]=int((new&events.CATEGORIA.eq(category).to_numpy()).sum())
  f.at[idx,'EVENTOS_DV_NUEVOS']=f.at[idx,'EVENTOS_D_NUEVOS']+f.at[idx,'EVENTOS_V_NUEVOS']
  for key in axes.CORREDOR.unique():f.at[idx,'LONGITUD_EXCLUSIVA_'+key+'_M']=union_all(axes.loc[axes.CORREDOR==key].geometry).intersection(ex).length
  for field in ['ALCANCE_VISUAL','POBLACION_METODO','CORREDOR_METODO']:
   if field in f and isinstance(row[field],str):f.at[idx,field]=row[field].replace('200 m','250 m').replace('200m','250m')
  if k==2:
   exclusive.append({'ID_POLICIA':row.ID_POLICIA,'RADIO_M':250,'geometry':ex});overlaps.append({'ID_POLICIA':row.ID_POLICIA,'RADIO_M':250,'geometry':over})
 pyogrio.write_dataframe(f,PACKAGE,layer=name);pyogrio.write_dataframe(f.to_crs(4326),BASE/(name+'.geojson'),driver='GeoJSON')
for name,rows in [('AREAS_EXCLUSIVAS_POLICIA_FINAL',exclusive),('AREAS_SOLAPADAS_POLICIA_FINAL',overlaps)]:pyogrio.write_dataframe(gpd.GeoDataFrame(rows,crs=32717),PACKAGE,layer=name)
results=json.loads((BASE/'RESULTADOS.json').read_text(encoding='utf-8'));results['policeMetrics']=json.loads(frames[2].drop(columns='geometry').to_json(orient='records'))
(BASE/'RESULTADOS.json').write_text(json.dumps(results,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
frames[2].drop(columns='geometry').to_csv(BASE/'POLICIA_BENEFICIO_FINAL.csv',index=False)
for field,name in [('incidents','INCIDENTES_CUBIERTOS_FINAL'),('territorial','COBERTURA_TERRITORIAL_FINAL'),('population','POBLACION_CUBIERTA_FINAL'),('corridors','COBERTURA_CORREDORES_FINAL')]:
 import pandas as pd
 pd.DataFrame(results[field]).to_csv(BASE/(name+'.csv'),index=False)
coverage=json.loads((BASE/'COBERTURA_73_110_183.json').read_text(encoding='utf-8'));coverage['sourcePackageSha256']=hashlib.sha256(PACKAGE.read_bytes()).hexdigest()
(BASE/'COBERTURA_73_110_183.json').write_text(json.dumps(coverage,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
with zipfile.ZipFile(BASE/'ENTREGA_POLICIA_KDE.zip','w',zipfile.ZIP_DEFLATED) as archive:
 for path in sorted(BASE.rglob('*')):
  if path.is_file() and path.suffix!='.zip' and not path.name.endswith('~'):archive.write(path,path.relative_to(BASE).as_posix())
print('PASS: overlaps, police exclusivity and downloadable tables reconciled at 250m.')
