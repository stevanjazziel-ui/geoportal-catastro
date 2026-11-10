"""Correct PN-21's junction arms using documented local road geometries."""
import json,hashlib
from pathlib import Path
import geopandas as gpd
from shapely import union_all
from shapely.geometry import Point,LineString,mapping,shape
from shapely.ops import transform,linemerge,substring
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/seguridad-riobamba/COBERTURA_250M_20261110'
BASE=ROOT/json.loads((ROOT/'sig-bridge-active.json').read_text())['root']
SOURCE=ROOT.parent/'entregas/ESTUDIO_MOVILIDAD_MACAJI_BELLAVISTA/insumos/riobamba_osm_walk_network_5categorias_todas_plataformas.json'
PROJECT=Transformer.from_crs(4326,32717,always_xy=True).transform
UNPROJECT=Transformer.from_crs(32717,4326,always_xy=True).transform
def dump(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def main():
 original=json.loads((OUT/'LINEAS_AJUSTADAS_RIO023_RIO052.geojson').read_text(encoding='utf-8'))
 old=[f for f in original['features'] if f['properties']['ID_CAMARA']=='PN-21'];assert len(old)==3
 point=next(f for f in json.loads((BASE/'PROPUESTA_POLICIA_30_FINAL.geojson').read_text(encoding='utf-8'))['features'] if f['properties']['ID_POLICIA']=='PN-21')
 origin=transform(PROJECT,shape(point['geometry']))
 raw=json.loads(SOURCE.read_text(encoding='utf-8'))
 ways={w['id']:w for w in raw['elements'] if w.get('type')=='way' and len(w.get('geometry',[]))>1}
 routes=[('Avenida Edelberto Bonilla Oleas','Norte · calzada oriental',[325474130]),
         ('Avenida Edelberto Bonilla Oleas','Norte · calzada occidental',[325474135]),
         ('Avenida 9 de Octubre','Sur · calzada occidental',[325474120]),
         ('Avenida 9 de Octubre','Sur · calzada oriental',[325474123]),
         ('Avenida Celso Augusto Rodriguez','Occidente · calzada norte',[552271037]),
         ('Avenida Celso Augusto Rodriguez','Occidente · calzada sur',[325474113]),
         ('Avenida Celso Augusto Rodriguez','Oriente · Celso Augusto Rodríguez',[559551366,1181242575,109974248]),
         ('Recife','Oriente · bifurcación Recife',[559551366,1181242575,112649782])]
 new=[];audit=[]
 for name,role,ids in routes:
  parts=[transform(PROJECT,LineString([(p['lon'],p['lat']) for p in ways[key]['geometry']])) for key in ids]
  axis=parts[0] if len(parts)==1 else linemerge(union_all(parts))
  assert axis.geom_type=='LineString','Disconnected route: '+role
  at=axis.project(origin);anchor=axis.interpolate(at);connector=origin.distance(anchor)
  assert connector<25
  direction=1 if at<axis.length/2 else -1;target=at+direction*(250-connector)
  assert 0<=target<=axis.length
  path=substring(axis,at,target);line=LineString([(origin.x,origin.y),*list(path.coords)])
  assert abs(line.length-250)<1e-6 and max(axis.distance(Point(c)) for c in list(line.coords)[1:])<1e-6
  props={**old[0]['properties'],'BRAZO':len(new)+1,'VIA_INICIAL':name,'CALZADA':role,'RECORRIDO':'EJE_VIAL',
         'LONGITUD_M':line.length,'HASTA_M':250,'SEPARACION_CAMARA_RED_M':connector,
         'METODO_ANCLA':'Brazo del cruce sobre cartografia vial local; sin prolongar tangentes fuera de calle',
         'EXCEPCION_EJE_VIAL_USUARIO':True,'OSM_WAYS':','.join(map(str,ids)),'VISIBILIDAD_VERIFICADA':False}
  new.append({'type':'Feature','properties':props,'geometry':mapping(transform(UNPROJECT,line))})
  audit.append({'arm':props['BRAZO'],'street':name,'route':role,'lengthM':line.length,'connectorM':connector,'vertices':len(line.coords),'osmWays':ids})
 output=[];inserted=False
 for f in original['features']:
  if f['properties']['ID_CAMARA']=='PN-21':
   if not inserted:output.extend(new);inserted=True
  else:output.append(f)
 assert len(output)==619
 others=lambda rows:[f for f in rows if f['properties']['ID_CAMARA']!='PN-21']
 assert others(output)==others(original['features'])
 dump('LINEAS_AJUSTADAS_RIO023_RIO052_PN21.geojson',{'type':'FeatureCollection','features':output})
 gpd.GeoDataFrame.from_features(output,crs=4326).to_crs(32717).to_file(OUT/'COBERTURA_AJUSTADA_RIO023_RIO052_PN21.gpkg',layer='COBERTURA_VIAL_AJUSTADA',driver='GPKG')
 summary=json.loads((OUT/'RESUMEN.json').read_text(encoding='utf-8'))
 summary['primaryArms']=619
 summary['roadAxisExceptions']=[v for v in summary.get('roadAxisExceptions',[]) if v['cameraId']!='PN-21']+[{'cameraId':'PN-21','junctionArms':8,'maxRouteM':250,'originUnchanged':True,'source':'OSM local','sourceSha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'visibilityVerified':False}]
 summary['streetMethod']='Cobertura de 250 m con rayos rectos y ajustes viales solicitados: RIO-023 sobre ambas calzadas de Unidad Nacional y Duchicela; PN-21 sobre los brazos de Edelberto Bonilla, 9 de Octubre, Celso Augusto Rodríguez y Recife. Se conserva la extension de RIO-052 hasta 331,4 m. Area y poblacion mantienen radios de 250 m.'
 dump('RESUMEN.json',summary)
 proof={'passed':True,'cameraId':'PN-21','cameraPositionUnchanged':True,'correctedRoadPaths':8,'maximumPathM':250,'other611PathsUnchanged':True,'rio023AndRio052Preserved':True,'areaPopulationAndGapsUnchanged':True,'paths':audit}
 dump('VALIDACION_PN21_EJES.json',proof);print(json.dumps(proof,ensure_ascii=False))
if __name__=='__main__':main()
