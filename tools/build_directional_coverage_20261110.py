"""Visual street arms 200+50m; uncovered Macaji retains dissolved 200m disks."""
import json,math,hashlib
from pathlib import Path
from collections import defaultdict
import geopandas as gpd
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
from shapely import STRtree,union_all
from shapely.geometry import Point,LineString,mapping
from shapely.ops import substring,transform
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
RELEASE='CAMARAS_AJUSTADAS_USUARIO_20261109'
BASE=ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES'/RELEASE
OUT=ROOT/'data/seguridad-riobamba/COBERTURA_DIRECCIONAL_20261110'
ROADS=ROOT.parent/'entregas/RIOBAMBA_CONSOLIDADO_PRIORIDAD_REUNION_20261017/RIOBAMBA_CONSOLIDADO.gpkg'
TO_LL=Transformer.from_crs(32717,4326,always_xy=True).transform
def dump(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
def features(rows):return {'type':'FeatureCollection','features':[{'type':'Feature','properties':{k:v for k,v in r.items() if k!='geometry'},'geometry':mapping(transform(TO_LL,r['geometry']))} for r in rows]}
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 source=gpd.read_file(ROADS,layer='PNPRI_RED_VIAL_REFERENCIA').to_crs(32717)
 rawpath=ROOT.parent/'entregas/ESTUDIO_MOVILIDAD_MACAJI_BELLAVISTA/insumos/riobamba_osm_walk_network_5categorias_todas_plataformas.json'
 raw=json.loads(rawpath.read_text(encoding='utf-8'));extra_roads=[]
 for way in raw['elements']:
  if way.get('type')=='way' and len(way.get('geometry',[]))>1:
   tags=way.get('tags',{});extra_roads.append({'osm_id':str(way['id']),'highway':tags.get('highway'),'name':tags.get('name',''),'geometry':LineString([(p['lon'],p['lat']) for p in way['geometry']])})
 source=pd.concat([source,gpd.GeoDataFrame(extra_roads,crs=4326).to_crs(32717)],ignore_index=True)
 nodes={};xy=[];adj=defaultdict(list);edges=[];seen=set()
 def node(c,prefix='OSM'):
  key=(prefix,round(c[0],2),round(c[1],2))
  if key not in nodes:nodes[key]=len(xy);xy.append(tuple(c[:2]))
  return nodes[key]
 for r in source.itertuples():
  if str(r.highway) in ('construction','proposed'):continue
  parts=r.geometry.geoms if r.geometry.geom_type=='MultiLineString' else [r.geometry]
  for part in parts:
   coords=list(part.coords)
   for a,b in zip(coords,coords[1:]):
    u,v=node(a),node(b);key=tuple(sorted((u,v)))
    if u==v or key in seen:continue
    seen.add(key);geom=LineString([xy[u],xy[v]])
    if geom.length<.01:continue
    eid=len(edges);edges.append({'u':u,'v':v,'geometry':geom,'way':str(r.osm_id),'name':str(r.name) if r.name else ''});adj[u].append(eid);adj[v].append(eid)
 tree=STRtree([e['geometry'] for e in edges]);junctions=[u for u in adj if len(adj[u])>=3];jt=cKDTree([xy[u] for u in junctions])
 primary=[];extra=[];audit=[];cameras=[];camera_meta={}
 def trace(start,first,eid):
  path=[start];distance=0.;visited={eid};current=first;prev=start
  if math.dist(start,xy[current])>.001:path.append(xy[current]);distance+=math.dist(start,xy[current])
  else:prev=xy[edges[eid]['v'] if edges[eid]['u']==current else edges[eid]['u']]
  while distance<250-1e-8:
   incoming=np.array(xy[current])-np.array(prev);norm=np.linalg.norm(incoming)
   candidates=[]
   for j in adj[current]:
    if j in visited:continue
    e=edges[j];other=e['v'] if e['u']==current else e['u'];vec=np.array(xy[other])-np.array(xy[current]);cos=float(np.dot(incoming,vec)/max(norm*np.linalg.norm(vec),1e-12))
    if cos<.5:continue
    previous=edges[eid];bonus=.10*(e['way']==previous['way'])+.06*bool(e['name'] and e['name']==previous['name'])
    candidates.append((cos+bonus,j,other))
   if not candidates:break
   _,j,other=max(candidates);prev=xy[current];current=other;path.append(xy[current]);distance+=edges[j]['geometry'].length;visited.add(j);eid=j
  if len(path)<2:return None
  line=LineString(path);return substring(line,0,min(250,line.length))
 for group,layer,idfield in [('existing','CAMARAS_EXISTENTES_103_FINAL','ID_CAMARA'),('municipal','PROPUESTA_MUNICIPAL_50_FINAL','ID_PROPUESTA'),('police','PROPUESTA_POLICIA_30_FINAL','ID_POLICIA')]:
  frame=gpd.read_file(BASE/'ESCENARIO_FINAL_183.gpkg',layer=layer).to_crs(32717)
  for r in frame.to_dict('records'):
   point=r['geometry'];cid=r[idfield];cameras.append((cid,point));camera_meta[cid]={'SOURCE_GROUP':group,'REQUIERE_CAMBIO':bool(r.get('REQUIERE_CAMBIO',False))};eid=int(tree.nearest(point));edge=edges[eid];near=edge['geometry'].interpolate(edge['geometry'].project(point));dist=point.distance(near);jd,jindex=jt.query([point.x,point.y]);anchors=[];method=''
   if dist>30:audit.append({'cameraId':cid,'associated':False,'distanceToStreetM':dist,'reason':'Fuera de tolerancia de asociacion de 30 m; sin inventar brazos'});continue
   if jd<=30:
    u=junctions[int(jindex)];anchor=xy[u];dist=float(jd);method='Vertice compartido de interseccion hasta 30 m'
    for j in adj[u]:e=edges[j];anchors.append((anchor,e['v'] if e['u']==u else e['u'],j))
   else:
    anchor=(near.x,near.y);method='Proyeccion sobre segmento mas cercano hasta 30 m'
    anchors=[(anchor,edge['u'],eid),(anchor,edge['v'],eid)]
   count=0
   for arm,(start,first,j) in enumerate(anchors,1):
    geom=trace(start,first,j)
    if geom is None or geom.length<=.01:continue
    props={'ID_CAMARA':cid,'SOURCE_GROUP':group,'REQUIERE_CAMBIO':bool(r.get('REQUIERE_CAMBIO',False)),'BRAZO':arm,'SEPARACION_CAMARA_RED_M':dist,'VIA_INICIAL':edges[j]['name'],'METODO_ANCLA':method,'FUENTE_RED':'OSM local','VISIBILIDAD_VERIFICADA':False}
    a=substring(geom,0,min(200,geom.length));primary.append({**props,'DESDE_M':0,'HASTA_M':a.length,'LONGITUD_M':a.length,'geometry':a});count+=1
    if geom.length>200.01:
     b=substring(geom,200,min(250,geom.length));extra.append({**props,'DESDE_M':200,'HASTA_M':200+b.length,'LONGITUD_M':b.length,'SOLO_VISUAL':True,'geometry':b})
   audit.append({'cameraId':cid,'associated':True,'arms':count,'distanceToAnchorM':dist,'method':method})
 official_path=ROOT.parent/'entregas/COMPARACION_CAMARAS_COP/PROYECTO_QGIS_CAMARAS/CAMARAS_Y_CAMBIOS_POLICIA.gpkg'
 official=gpd.read_file(official_path,layer='RED_VIAL_CONTEXTO').to_crs(32717);start_edge=len(edges);local_nodes=set()
 for r in official.itertuples():
  parts=r.geometry.geoms if r.geometry.geom_type=='MultiLineString' else [r.geometry]
  for part in parts:
   coords=list(part.coords)
   for a,b in zip(coords,coords[1:]):
    u,v=node(a,'MUNICIPAL'),node(b,'MUNICIPAL');key=tuple(sorted((u,v)))
    if u==v or key in seen:continue
    seen.add(key);geom=LineString([xy[u],xy[v]])
    if geom.length<.01:continue
    j=len(edges);edges.append({'u':u,'v':v,'geometry':geom,'way':'LOCAL-'+str(r.OBJECTID_1),'name':str(r.NOMBRE or '')});adj[u].append(j);adj[v].append(j);local_nodes.update([u,v])
 local_edges=list(range(start_edge,len(edges)));lt=STRtree([edges[j]['geometry'] for j in local_edges]);lj=[u for u in local_nodes if len(adj[u])>=3];ljt=cKDTree([xy[u] for u in lj]);points=dict(cameras)
 for auditrow in audit:
  if auditrow['associated']:continue
  cid=auditrow['cameraId'];point=points[cid];j=local_edges[int(lt.nearest(point))];edge=edges[j];near=edge['geometry'].interpolate(edge['geometry'].project(point));dist=point.distance(near)
  if dist>30:continue
  jd,ji=ljt.query([point.x,point.y]);method='Cartografia vial municipal local'
  if jd<=30:
   u=lj[int(ji)];dist=float(jd);anchors=[(xy[u],edges[k]['v'] if edges[k]['u']==u else edges[k]['u'],k) for k in adj[u]]
  else:anchors=[((near.x,near.y),edge['u'],j),((near.x,near.y),edge['v'],j)]
  count=0
  for arm,(start,first,j) in enumerate(anchors,1):
   geom=trace(start,first,j)
   if geom is None or geom.length<=.01:continue
   props={'ID_CAMARA':cid,**camera_meta[cid],'BRAZO':arm,'SEPARACION_CAMARA_RED_M':dist,'VIA_INICIAL':edges[j]['name'],'METODO_ANCLA':method,'FUENTE_RED':'Cartografia vial municipal local','VISIBILIDAD_VERIFICADA':False};a=substring(geom,0,min(200,geom.length));primary.append({**props,'DESDE_M':0,'HASTA_M':a.length,'LONGITUD_M':a.length,'geometry':a});count+=1
   if geom.length>200.01:
    b=substring(geom,200,min(250,geom.length));extra.append({**props,'DESDE_M':200,'HASTA_M':200+b.length,'LONGITUD_M':b.length,'SOLO_VISUAL':True,'geometry':b})
  auditrow.update(associated=True,arms=count,distanceToAnchorM=dist,method=method)
 assert len(cameras)==183
 assert all(r['geometry'].length<=200.000001 for r in primary) and all(r['geometry'].length<=50.000001 for r in extra)
 axis=union_all(gpd.read_file(BASE/'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA/TRAMO_BOULEVARD_MACAJI_BELLAVISTA.geojson').to_crs(32717).geometry)
 masks=union_all([p.buffer(200,quad_segs=64) for _,p in cameras]);gap=axis.difference(masks);covered=axis.intersection(masks)
 parts=list(gap.geoms) if hasattr(gap,'geoms') else [gap];gaps=[]
 for i,g in enumerate(parts,1):
  if g.is_empty or g.length<1e-6:continue
  cid,point=min(cameras,key=lambda r:r[1].distance(g));gaps.append({'ID':f'MACAJI-200M-{i:03d}','CORREDOR':'TRAMO_MACAJI_BELLAVISTA_APROBADO','LONGITUD_M':g.length,'CAMARA_MAS_CERCANA':cid,'DIST_CAMARA_M':point.distance(g),'RADIO_CALCULO_M':200,'EXTRA_50_INCLUIDO':False,'geometry':g})
 assert abs(covered.length+sum(g['LONGITUD_M'] for g in gaps)-axis.length)<1e-6
 scenarios={}
 for code,enabled in [('A',{'existing'}),('B',{'existing','municipal'}),('C',{'existing','municipal','police'})]:
  selected=[]
  for group,layer in [('existing','CAMARAS_EXISTENTES_103_FINAL'),('municipal','PROPUESTA_MUNICIPAL_50_FINAL'),('police','PROPUESTA_POLICIA_30_FINAL')]:
   if group in enabled:selected.extend(gpd.read_file(BASE/'ESCENARIO_FINAL_183.gpkg',layer=layer).geometry)
  disk=union_all([p.buffer(200,quad_segs=64) for p in selected]);length=axis.intersection(disk).length
  scenarios[code]={'totalMacajiM':axis.length,'coveredMacaji200M':length,'uncoveredMacaji200M':axis.difference(disk).length,'coveredPct':100*length/axis.length}
 for filename,rows in [('LINEAS_PRINCIPALES_200M.geojson',primary),('EXTENSION_VISUAL_50M.geojson',extra),('BRECHA_MACAJI_TRAMO_200M.geojson',gaps)]:dump(filename,features(rows))
 package=OUT/'COBERTURA_LINEAL_Y_BRECHAS.gpkg'
 for name,rows in [('LINEAS_200M',primary),('EXTENSION_VISUAL_50M',extra),('BRECHAS_MACAJI_200M',gaps)]:gpd.GeoDataFrame(rows,crs=32717).to_file(package,layer=name,driver='GPKG')
 summary={'sourceRelease':RELEASE,'cameras':183,'associatedCameras':sum(r['associated'] for r in audit),'unassociatedCameras':[r['cameraId'] for r in audit if not r['associated']],'primaryArms':len(primary),'visualExtensions':len(extra),'totalMacajiM':axis.length,'coveredMacaji200M':covered.length,'uncoveredMacaji200M':gap.length,'coveredPct':100*covered.length/axis.length,'extra50IncludedInGapCalculation':False,'metricCrs':'EPSG:32717','radiusForGapM':200,'maxStreetAssociationM':30,'continuationMaxTurnDegrees':60,'method':'Misma metodologia previa: diferencia del eje especifico aprobado y union disuelta de radios de 200 m, 64 segmentos por cuadrante. Los brazos viales y sus 50 m adicionales son representacion visual y no sustituyen ni amplian esos radios.','streetMethod':'Vertices compartidos OSM red consolidada; cada brazo continua por la direccion mas alineada, sin ramificarse en cruces posteriores; se detiene ante giro mayor a 60 grados, fin de via o 250 m. No visibilidad real.','sourceCameraGeometrySha256':hashlib.sha256(''.join(cid+p.wkb_hex for cid,p in sorted(cameras)).encode()).hexdigest(),'sourceRoadsSha256':hashlib.sha256(ROADS.read_bytes()).hexdigest()}
 summary['scenarios']=scenarios;summary['sourceAdditionalLocalOsmSha256']=hashlib.sha256(rawpath.read_bytes()).hexdigest()
 summary['localMunicipalFallbackCameras']=[r['cameraId'] for r in audit if r.get('method')=='Cartografia vial municipal local'];summary['sourceMunicipalRoadsSha256']=hashlib.sha256(official_path.read_bytes()).hexdigest()
 dump('RESUMEN.json',summary);dump('ASOCIACION_CAMARAS.json',audit);dump('VALIDACION.json',{'passed':True,'cameras':183,'primaryAtMost200M':True,'extensionAtMost50M':True,'gapMethodUnchanged':True,'extra50NotUsedForGap':True,'axisLengthReconciled':True})
 (OUT/'METODOLOGIA.md').write_text('# Cobertura visual por brazos de via\n\n'+summary['streetMethod']+'\n\n'+summary['method']+'\n\nLas ubicaciones de camaras no se mueven para asociarlas a una via. Las separaciones y las camaras sin asociacion se conservan en ASOCIACION_CAMARAS.json. Los cruces se forman solo con vertices compartidos; no se conectan cruces geometricos interiores automaticamente. Se complementa OSM con la cartografia vial municipal local cuando no hay una via OSM a 30 m. Las dos redes no se conectan artificialmente entre si. Seis camaras quedan sin brazos por falta de asociacion local; sus radios de 200 m siguen participando en el calculo anterior de brechas.\n',encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
