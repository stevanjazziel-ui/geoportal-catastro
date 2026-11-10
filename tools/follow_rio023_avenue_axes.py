"""User-requested road-axis representation for RIO-023, both carriageways."""
import json,math,hashlib
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
def dump(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')

def main():
 source=json.loads((OUT/'LINEAS_CON_EXTENSION_RIO052.geojson').read_text(encoding='utf-8'))
 old=[f for f in source['features'] if f['properties']['ID_CAMARA']=='RIO-023-DOMO'];assert len(old)==4
 camera=next(f for f in json.loads((BASE/'CAMARAS_EXISTENTES_103_FINAL.geojson').read_text(encoding='utf-8'))['features'] if f['properties']['ID_CAMARA']=='RIO-023-DOMO')
 origin=transform(PROJECT,shape(camera['geometry']))
 raw=json.loads(SOURCE.read_text(encoding='utf-8'))
 networks={}
 for name in ['Avenida Unidad Nacional','Duchicela']:
  roads=[transform(PROJECT,LineString([(p['lon'],p['lat']) for p in way['geometry']])) for way in raw['elements'] if way.get('type')=='way' and way.get('tags',{}).get('name')==name and len(way.get('geometry',[]))>1]
  merged=linemerge(union_all(roads))
  networks[name]=[line for line in (list(merged.geoms) if hasattr(merged,'geoms') else [merged]) if line.distance(origin)<30 and line.length>500]
 lanes=networks['Avenida Unidad Nacional'];assert len(lanes)==2
 lanes.sort(key=lambda line:line.interpolate(line.project(origin)).y,reverse=True)
 duchi=networks['Duchicela'];assert len(duchi)==1
 new=[];audit=[]
 for name,role,axis in [('Avenida Unidad Nacional','Calzada norte',lanes[0]),('Avenida Unidad Nacional','Calzada sur',lanes[1]),('Duchicela','Cruce Duchicela',duchi[0])]:
  measure=axis.project(origin);anchor=axis.interpolate(measure);connector=origin.distance(anchor);budget=250-connector
  assert 0<=connector<30 and budget>220
  for direction in [-1,1]:
   target=measure+direction*budget;assert 0<=target<=axis.length
   path=substring(axis,measure,target);coords=[(origin.x,origin.y),*list(path.coords)]
   line=LineString(coords);assert abs(line.length-250)<1e-6
   assert Point(line.coords[0]).distance(origin)<1e-8
   assert max(axis.distance(Point(c)) for c in list(line.coords)[1:])<1e-6
   props={**old[0]['properties'],'BRAZO':len(new)+1,'VIA_INICIAL':name,'CALZADA':role,'RECORRIDO':'EJE_VIAL','LONGITUD_M':line.length,'HASTA_M':250,'SEPARACION_CAMARA_RED_M':connector,'METODO_ANCLA':'Conector corto desde camara a eje local y recorrido sobre la misma calzada; limite total 250 m','VISIBILIDAD_VERIFICADA':False,'EXCEPCION_EJE_VIAL_USUARIO':True}
   new.append({'type':'Feature','properties':props,'geometry':mapping(transform(UNPROJECT,line))})
   audit.append({'arm':props['BRAZO'],'street':name,'carriageway':role,'lengthM':line.length,'connectorM':connector,'vertices':len(coords)})
 features=[];inserted=False
 for feature in source['features']:
  if feature['properties']['ID_CAMARA']=='RIO-023-DOMO':
   if not inserted:features.extend(new);inserted=True
  else:features.append(feature)
 assert len(features)==614
 others=lambda values:[f for f in values if f['properties']['ID_CAMARA']!='RIO-023-DOMO']
 assert others(features)==others(source['features'])
 dump('LINEAS_AJUSTADAS_RIO023_RIO052.geojson',{'type':'FeatureCollection','features':features})
 gpd.GeoDataFrame.from_features(features,crs=4326).to_crs(32717).to_file(OUT/'COBERTURA_EJES_RIO023_RIO052.gpkg',layer='COBERTURA_VIAL_AJUSTADA',driver='GPKG')
 summary=json.loads((OUT/'RESUMEN.json').read_text(encoding='utf-8'))
 summary.update(primaryArms=614,geometryMode='STRAIGHT_WITH_ROAD_AXIS_EXCEPTIONS',roadAxisExceptions=[{'cameraId':'RIO-023-DOMO','avenueCarriageways':2,'avenueArms':4,'crossStreetArms':2,'maxRouteM':250,'originUnchanged':True,'source':'OSM local','sourceSha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'visibilityVerified':False}],streetMethod='Rayos rectos de 250 m, con dos ajustes solicitados: RIO-052 por Puruhá hasta 331,4 m; RIO-023 sigue ambos ejes de Unidad Nacional y Duchicela, con recorridos totales de 250 m desde la camara. Area y poblacion conservan buffers de 250 m.')
 dump('RESUMEN.json',summary)
 proof={'passed':True,'cameraId':'RIO-023-DOMO','cameraPositionUnchanged':True,'bothAvenueCarriageways':True,'avenueArms':4,'crossStreetArms':2,'maximumRouteM':250,'other608PathsUnchanged':True,'rio052ExtensionPreserved':True,'areaPopulationAndGapCalculationsUnchanged':True,'paths':audit}
 dump('VALIDACION_EJES_RIO023.json',proof);print(json.dumps(proof,ensure_ascii=False))
if __name__=='__main__':main()
