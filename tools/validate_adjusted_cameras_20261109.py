"""Independent source/coordinate/radius checks for the user-adjusted release."""
import json,sys
from pathlib import Path
import geopandas as gpd
from shapely.geometry import shape
from shapely.ops import unary_union,transform
from pyproj import Transformer
from apply_adjusted_cameras_20261109 import ROOT,OUT,INPUT,SPECS
project=Transformer.from_crs(4326,32717,always_xy=True).transform
def main():
 p=OUT/'ESCENARIO_FINAL_183.gpkg';summary={};allpoints=[]
 for key,layer,idfield,file,sourceid,count in SPECS:
  source=gpd.read_file(INPUT/file).set_index(sourceid);final=gpd.read_file(p,layer=layer).set_index(idfield)
  assert len(final)==count and set(final.index)==set(source.index)
  assert max(final.loc[k].geometry.distance(r.geometry) for k,r in source.iterrows())<1e-8
  assert max(r.geometry.distance(transform(project,shape({'type':'Point','coordinates':[r.LONGITUD,r.LATITUD]}))) for _,r in final.iterrows())<1e-6
  visual=json.loads((OUT/(layer+'.geojson')).read_text(encoding='utf-8'))
  assert len(visual['features'])==count
  for f in visual['features']:
   assert transform(project,shape(f['geometry'])).distance(final.loc[f['properties'][idfield]].geometry)<1e-6
  radlayer={'existing':'RADIOS_EXISTENTES_SIMBOLOGIA_200M','municipal':'RADIOS_MUNICIPALES_200M','police':'RADIOS_POLICIA_200M'}[key]
  disks=gpd.read_file(p,layer=radlayer).set_index(idfield)
  assert len(disks)==count
  assert max(disks.loc[k].geometry.centroid.distance(r.geometry) for k,r in final.iterrows())<1e-6
  assert max(abs(disks.loc[k].geometry.area-r.geometry.buffer(200,quad_segs=64).area) for k,r in final.iterrows())<.001
  summary[key]={'count':count,'coordinatesMatchSource':True,'tableCoordinatesMatchGeometry':True,'webPointsMatchGeometry':True,'radiiMatch200m':True};allpoints.extend(final.geometry)
 assert len(allpoints)==183
 actual=gpd.read_file(p,layer='COBERTURA_C').geometry.iloc[0];expected=unary_union([q.buffer(200,quad_segs=64) for q in allpoints])
 assert actual.symmetric_difference(expected).area<.01
 summary['combined183CoverageExact']=True
 (OUT/'VALIDACION_IMPORTACION_Y_RADIOS.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
