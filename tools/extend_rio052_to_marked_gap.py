"""Authorized one-arm extension to the far end of the screenshot's red gap.

Circular area/population masks stay at 250m. Only approved-axis linear
coverage includes the specifically authorized gap; no corridor width is inferred.
"""
import json,hashlib
from pathlib import Path
import geopandas as gpd
from shapely import union_all
from shapely.geometry import Point,LineString,mapping
from shapely.ops import transform
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/seguridad-riobamba/COBERTURA_250M_20261110'
BASE=ROOT/json.loads((ROOT/'sig-bridge-active.json').read_text())['root']
TO_LL=Transformer.from_crs(32717,4326,always_xy=True).transform
def dump(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')

def main():
 rays=gpd.read_file(OUT/'LINEAS_PRINCIPALES_250M.geojson').to_crs(32717)
 original_rays=rays.copy()
 gaps=gpd.read_file(OUT/'BRECHA_MACAJI_TRAMO_250M.geojson').to_crs(32717)
 camera=gpd.read_file(BASE/'CAMARAS_EXISTENTES_103_FINAL.geojson').to_crs(32717)
 point=camera.loc[camera.ID_CAMARA.eq('RIO-052-DOMO')].geometry.iloc[0]
 assert len(gaps)==1 and abs(gaps.geometry.iloc[0].length-81.38382543661346)<1e-6
 gap=gaps.geometry.iloc[0];end=max([Point(gap.coords[0]),Point(gap.coords[-1])],key=point.distance)
 key=rays.ID_CAMARA.eq('RIO-052-DOMO') & rays.BRAZO.eq(4)
 assert key.sum()==1 and rays.loc[key,'VIA_INICIAL'].iloc[0]=='Puruhá'
 original=rays.loc[key].geometry.iloc[0]
 assert Point(original.coords[0]).distance(point)<1e-6
 line=LineString([point,end]);assert 330<line.length<333
 # The marked gap is on this straight sightline (within map-position tolerance).
 assert max(line.distance(Point(c)) for c in gap.coords)<2
 rays.loc[key,'geometry']=line
 rays.loc[key,'HASTA_M']=line.length;rays.loc[key,'LONGITUD_M']=line.length
 rays['EXCEPCION_USUARIO']=False;rays.loc[key,'EXCEPCION_USUARIO']=True
 rays.to_crs(4326).to_file(OUT/'LINEAS_CON_EXTENSION_RIO052.geojson',driver='GeoJSON')
 summary=json.loads((OUT/'RESUMEN.json').read_text(encoding='utf-8'))
 axis=union_all(gpd.read_file(BASE/'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA/TRAMO_BOULEVARD_MACAJI_BELLAVISTA.geojson').to_crs(32717).geometry)
 groups=[gpd.read_file(BASE/(n+'.geojson')).to_crs(32717) for n in ['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL']]
 for code,frames in [('A',groups[:1]),('B',groups[:2]),('C',groups)]:
  mask=union_all([p.buffer(250,quad_segs=64) for f in frames for p in f.geometry])
  radial_gap=axis.difference(mask);remaining=radial_gap.difference(gap.buffer(.001))
  row=summary['scenarios'][code]
  row.update(coveredMacajiWithExceptionsM=axis.length-remaining.length,uncoveredMacajiWithExceptionsM=remaining.length,coveredWithExceptionsPct=100*(axis.length-remaining.length)/axis.length)
  if code=='C':assert remaining.length<1e-6
 summary['directionalExceptions']=[{'cameraId':'RIO-052-DOMO','arm':4,'street':'Puruhá','lengthM':line.length,'previousLengthM':250,'addedLengthM':line.length-250,'markedGapLengthM':gap.length,'targetWgs84':list(transform(TO_LL,end).coords)[0],'authorization':'Usuario solicita extender RIO-052-DOMO hasta el extremo del tramo rojo de su captura.','visibilityVerified':False}]
 summary['streetMethod']='Rayos rectos de 250 m desde cada camara, salvo el brazo de Puruhá de RIO-052-DOMO, extendido a 331,4 m por solicitud del usuario. Sin ampliar radios circulares ni poblacion.'
 summary['linearOverlayToleranceM']=.001
 summary['linearCoverageMethod']='Union de cobertura radial de 250m sobre el eje aprobado y tramo rojo autorizado para el brazo de RIO-052-DOMO. Area y poblacion conservan exclusivamente los buffers de 250m; no se supone un ancho de visibilidad.'
 summary.update({k:v for k,v in summary['scenarios']['C'].items() if 'Exceptions' in k})
 dump('RESUMEN.json',summary)
 dump('BRECHA_MACAJI_CON_EXTENSION_RIO052.geojson',{'type':'FeatureCollection','features':[]})
 package=OUT/'COBERTURA_CON_EXTENSION_RIO052.gpkg'
 rays.to_file(package,layer='RAYOS_CON_EXTENSION_RIO052',driver='GPKG')
 gpd.GeoDataFrame([{'ID_CAMARA':'RIO-052-DOMO','LONGITUD_M':line.length,'geometry':line}],crs=32717).to_file(package,layer='EXTENSION_AUTORIZADA_RIO052',driver='GPKG')
 gpd.GeoDataFrame([{'ID_CAMARA':'RIO-052-DOMO','LONGITUD_M':gap.length,'geometry':gap}],crs=32717).to_file(package,layer='TRAMO_ROJO_INCORPORADO',driver='GPKG')
 proof={'passed':True,'cameraId':'RIO-052-DOMO','arm':4,'lengthM':line.length,'endpointMatchesMarkedGap':True,'straightFromUnmovedCamera':True,'other611RaysUnchanged':True,'areaAndPopulationRadiusM':250,'uncoveredApprovedAxisWithExceptionM':summary['uncoveredMacajiWithExceptionsM'],'uncoveredWithRadial250OnlyM':summary['uncoveredMacaji250M']}
 for index,row in rays.loc[~key].iterrows():
  assert row.geometry.wkb==original_rays.loc[index].geometry.wkb
 dump('VALIDACION_EXTENSION_RIO052.json',proof);print(json.dumps(proof))
if __name__=='__main__':main()
