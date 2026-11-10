"""Independent checks against source road geometries and approved camera points."""
import json,hashlib,subprocess
from pathlib import Path
import numpy as np
import geopandas as gpd
from shapely import STRtree
from shapely.geometry import shape,LineString,Point
from shapely.ops import transform,substring
from pyproj import Transformer
R=Path(__file__).resolve().parents[1];O=R/'data/seguridad-riobamba/COBERTURA_250M_20261110'
B=R/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/CAMARAS_AJUSTADAS_USUARIO_20261109'
P=Transformer.from_crs(4326,32717,always_xy=True).transform
def main():
 report=json.loads((O/'AUDITORIA_COBERTURAS_VIALES.json').read_text(encoding='utf-8'))
 before=json.loads((O/'LINEAS_AJUSTADAS_RIO023_RIO052_PN21.geojson').read_text(encoding='utf-8'))['features']
 after=json.loads((O/'COBERTURA_VIAL_AUDITADA.geojson').read_text(encoding='utf-8'))['features']
 raw=json.loads((R.parent/'entregas/ESTUDIO_MOVILIDAD_MACAJI_BELLAVISTA/insumos/riobamba_osm_walk_network_5categorias_todas_plataformas.json').read_text(encoding='utf-8'))
 roads=[transform(P,LineString([(v['lon'],v['lat']) for v in w['geometry']])) for w in raw['elements'] if w.get('type')=='way' and len(w.get('geometry',[]))>1]
 for path,layer in [(R.parent/'entregas/RIOBAMBA_CONSOLIDADO_PRIORIDAD_REUNION_20261017/RIOBAMBA_CONSOLIDADO.gpkg','PNPRI_RED_VIAL_REFERENCIA'),(R.parent/'entregas/COMPARACION_CAMARAS_COP/PROYECTO_QGIS_CAMARAS/CAMARAS_Y_CAMBIOS_POLICIA.gpkg','RED_VIAL_CONTEXTO')]:roads.extend(gpd.read_file(path,layer=layer).to_crs(32717).geometry)
 tree=STRtree(roads);points={};protected=[]
 for name,key in [('CAMARAS_EXISTENTES_103_FINAL','ID_CAMARA'),('PROPUESTA_MUNICIPAL_50_FINAL','ID_PROPUESTA'),('PROPUESTA_POLICIA_30_FINAL','ID_POLICIA')]:
  source=B/(name+'.geojson');data=json.loads(source.read_text(encoding='utf-8'));old=json.loads(subprocess.check_output(['git','show','HEAD:'+source.relative_to(R).as_posix()],cwd=R))
  assert data==old
  points.update({f['properties'][key]:transform(P,shape(f['geometry'])) for f in data['features']})
 assert len(points)==183
 by={cid:[] for cid in points}
 for f in after:by[f['properties']['ID_CAMARA']].append(f)
 checked=0;max_road_error=0.;max_origin_error=0.
 for row in report['cases']:
  cid=row['cameraId']
  if row['status']!='CORREGIDO':assert by[cid]==[f for f in before if f['properties']['ID_CAMARA']==cid]
  for f in by[cid]:
   line=transform(P,shape(f['geometry']));origin=Point(line.coords[0]);error=origin.distance(points[cid]);max_origin_error=max(max_origin_error,error);assert error<1e-6
   if f['properties'].get('EXCEPCION_USUARIO'):
    assert cid=='RIO-052-DOMO' and abs(line.length-331.35296449393707)<1e-6
    assert f in before;continue
   assert line.length<=250.00001
   if not f['properties'].get('AUDITORIA_CARTOGRAFICA'):continue
   checked+=1;coords=list(line.coords);onroad=line if f['properties']['SEPARACION_CAMARA_RED_M']<1e-6 else LineString(coords[1:]);samples=[onroad.interpolate(x) for x in np.arange(0,onroad.length+1,2)]
   if not samples:continue
   _,distances=tree.query_nearest(np.array(samples,dtype=object),all_matches=False,return_distance=True)
   max_road_error=max(max_road_error,float(distances.max()));assert distances.max()<.01
   assert len(f['geometry']['coordinates'])>=2
 assert len(by['RIO-027-DOMO'])==8
 assert {f['properties']['VIA_INICIAL'] for f in by['RIO-027-DOMO']} >= {'Eugenio Espejo','Avenida Alfonso Chavez','Avenida Edelberto Bonilla Oleas'}
 for name in ['ESCENARIO_FINAL_183.gpkg','RESULTADOS.json','COBERTURA_73_110_183.json']:
  path=B/name;previous=subprocess.check_output(['git','show','HEAD:'+path.relative_to(R).as_posix()],cwd=R)
  assert hashlib.sha256(previous).digest()==hashlib.sha256(path.read_bytes()).digest()
 proof={'passed':True,'camerasAudited':183,'correctedCameras':report['correctedCameras'],'sourceMatchedPaths':checked,'totalDisplayedPaths':len(after),'maxRoadDeviationAfterConnectorM':max_road_error,'maxCameraOriginErrorM':max_origin_error,'all183CameraPositionsUnchanged':True,'maximumOrdinaryPathM':250,'rio052ExtensionUnchanged':True,'approvedManualCorrectionsPreserved':True,'unsupportedCamerasUnchanged':report['unassociatedCameras'],'areaPopulationAndGapCalculationsUnchanged':True}
 (O/'VALIDACION_AUDITORIA_VIAL.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(proof,ensure_ascii=False))
if __name__=='__main__':main()
