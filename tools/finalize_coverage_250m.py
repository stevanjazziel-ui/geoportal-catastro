"""Sync camera attributes, historical deficit adapter and current downloads."""
import json, math, shutil, zipfile, hashlib
import numpy as np
import geopandas as gpd
import pyogrio
from shapely import covers
from refresh_coverage_250m import ROOT,BASE,PACKAGE,OUT
import recalculate_current_gaps as gaps

def main():
 events=gpd.read_file(PACKAGE,layer='INCIDENTES_CLASIFICADOS');points=np.asarray(events.geometry,dtype=object)
 blocks=gpd.read_file(PACKAGE,layer='MANZANAS_COBERTURA');idx=blocks.sindex
 results=json.loads((BASE/'RESULTADOS.json').read_text(encoding='utf-8'))
 for layer in ['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL']:
  f=gpd.read_file(PACKAGE,layer=layer)
  for i,row in f.iterrows():
   disk=row.geometry.buffer(250,quad_segs=64);included=covers(disk,points)
   for category in ['DELINCUENCIA','VIOLENCIA','CONVIVENCIA']:f.at[i,category+'_250M']=int((included & events.CATEGORIA.eq(category).to_numpy() & events.AMBITO.ne('EXTERNO_CANTON').to_numpy()).sum())
   pop=0.
   for j in idx.query(disk,predicate='intersects'):
    block=blocks.iloc[j]
    if block.POBLACION is not None and math.isfinite(block.POBLACION):pop+=block.POBLACION*block.geometry.intersection(disk).area/block.geometry.area
   f.at[i,'POBLACION_ASOCIADA_250M']=pop
  pyogrio.write_dataframe(f,PACKAGE,layer=layer)
  pyogrio.write_dataframe(f.to_crs(4326),BASE/(layer+'.geojson'),driver='GeoJSON')
  if layer=='PROPUESTA_POLICIA_30_FINAL':results['policeMetrics']=json.loads(f.drop(columns='geometry').to_json(orient='records'))
 (BASE/'RESULTADOS.json').write_text(json.dumps(results,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf-8')
 # Update the separate 200m vicinity selection with the current point attributes.
 exec(compile((ROOT/'tools/build_macaji_camera_layer.py').read_text(encoding='utf-8'),str(ROOT/'tools/build_macaji_camera_layer.py'),'exec'),{'__file__':str(ROOT/'tools/build_macaji_camera_layer.py')})
 shutil.copyfile(ROOT/'data/seguridad-riobamba/COBERTURA_RECTA_20261110/CAMARAS_MACAJI_BELLAVISTA.geojson',OUT/'CAMARAS_MACAJI_BELLAVISTA.geojson')
 print('Refreshing census deficit adapter including 250m',flush=True)
 gaps.main(final=PACKAGE,out=BASE/'coverage-inputs',js_output=BASE/'riobamba-brechas-actualizadas-data.js',expected_replacements=30)
 coverage=json.loads((BASE/'COBERTURA_73_110_183.json').read_text(encoding='utf-8'));coverage['sourcePackageSha256']=hashlib.sha256(PACKAGE.read_bytes()).hexdigest()
 (BASE/'COBERTURA_73_110_183.json').write_text(json.dumps(coverage,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 with zipfile.ZipFile(BASE/'ENTREGA_POLICIA_KDE.zip','w',zipfile.ZIP_DEFLATED) as archive:
  for path in sorted(BASE.rglob('*')):
   if path.is_file() and path.suffix!='.zip' and not path.name.endswith('~'):archive.write(path,path.relative_to(BASE).as_posix())
 print('250m downloads and deficit dependencies refreshed.',flush=True)
if __name__=='__main__':main()
