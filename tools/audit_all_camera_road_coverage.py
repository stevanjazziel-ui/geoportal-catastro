"""Audit tangent rays against local roads and correct only detected cases.

No camera relocation, new population assumption or wider coverage buffers.
Graph connections require shared mapped vertices; no geometric crossing noding.
"""
import csv,json,math,heapq,hashlib
from collections import defaultdict
from pathlib import Path
import geopandas as gpd
import numpy as np
from shapely import STRtree,union_all
from shapely.geometry import Point,LineString,shape,mapping
from shapely.ops import transform,substring
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/seguridad-riobamba/COBERTURA_250M_20261110'
BASE=ROOT/json.loads((ROOT/'sig-bridge-active.json').read_text())['root']
OSM=ROOT.parent/'entregas/ESTUDIO_MOVILIDAD_MACAJI_BELLAVISTA/insumos/riobamba_osm_walk_network_5categorias_todas_plataformas.json'
CONSOLIDATED=ROOT.parent/'entregas/RIOBAMBA_CONSOLIDADO_PRIORIDAD_REUNION_20261017/RIOBAMBA_CONSOLIDADO.gpkg'
MUNICIPAL=ROOT.parent/'entregas/COMPARACION_CAMARAS_COP/PROYECTO_QGIS_CAMARAS/CAMARAS_Y_CAMBIOS_POLICIA.gpkg'
TO_M=Transformer.from_crs(4326,32717,always_xy=True).transform
TO_LL=Transformer.from_crs(32717,4326,always_xy=True).transform
def dump(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
def clean_name(value):return str(value) if value is not None and str(value).lower() not in ('nan','none') else ''

class Network:
 def __init__(self,roads,label):
  self.label=label;self.nodes={};self.xy=[];self.adj=defaultdict(list);self.edges=[];seen=set()
  def node(coord,level):
   key=(round(coord[0],3),round(coord[1],3),str(level))
   if key not in self.nodes:self.nodes[key]=len(self.xy);self.xy.append(tuple(coord[:2]))
   return self.nodes[key]
  for line,name,way,level in roads:
   for a,b in zip(line.coords,list(line.coords)[1:]):
    u,v=node(a,level),node(b,level);key=tuple(sorted((u,v)))
    if u==v or key in seen:continue
    seen.add(key);geom=LineString([self.xy[u],self.xy[v]])
    if geom.length<.01:continue
    i=len(self.edges);self.edges.append({'u':u,'v':v,'geometry':geom,'name':clean_name(name),'way':str(way)})
    self.adj[u].append(i);self.adj[v].append(i)
  self.tree=STRtree([e['geometry'] for e in self.edges])
 def nearest(self,p):
  i=int(self.tree.nearest(p));return i,self.edges[i]['geometry'].distance(p)
 def distances(self,points):
  pairs,d=self.tree.query_nearest(points,return_distance=True,all_matches=False)
  out=np.zeros(len(points));out[pairs[0]]=d;return out
 def routes(self,p):
  eid,dist=self.nearest(p)
  if dist>30:return []
  edge=self.edges[eid];anchor=edge['geometry'].interpolate(edge['geometry'].project(p));start=len(self.xy)
  self.xy.append((anchor.x,anchor.y));removed={u:list(self.adj[u]) for u in (edge['u'],edge['v'])}
  temp=[]
  for endpoint in (edge['u'],edge['v']):
   i=len(self.edges);geom=LineString([self.xy[start],self.xy[endpoint]])
   self.edges.append({**edge,'u':start,'v':endpoint,'geometry':geom});temp.append(i)
   self.adj[start].append(i);self.adj[endpoint]=[j for j in self.adj[endpoint] if j!=eid]+[i]
  try:
   distances={start:dist};parents={};queue=[(dist,start)];inside=set()
   while queue:
    value,u=heapq.heappop(queue)
    if value!=distances[u] or value>100:continue
    if Point(self.xy[u]).distance(p)>35:continue
    inside.add(u)
    for j in self.adj[u]:
     e=self.edges[j];v=e['v'] if e['u']==u else e['u'];candidate=value+e['geometry'].length
     if Point(self.xy[v]).distance(p)<=35 and candidate<distances.get(v,float('inf')):
      distances[v]=candidate;parents[v]=(u,j);heapq.heappush(queue,(candidate,v))
   exits=[]
   for u in sorted(inside):
    for j in self.adj[u]:
     e=self.edges[j];v=e['v'] if e['u']==u else e['u']
     if v not in inside:exits.append((u,v,j))
   routes=[]
   for u,v,j in exits:
    nodes=[u];used=set();cursor=u
    while cursor!=start:
     previous,k=parents[cursor];used.add(k);nodes.append(previous);cursor=previous
    coords=[(p.x,p.y),*[self.xy[n] for n in reversed(nodes)]]
    coords=[c for i,c in enumerate(coords) if i==0 or math.dist(c,coords[i-1])>1e-8]
    length=sum(math.dist(a,b) for a,b in zip(coords,coords[1:]));names=[];ways=[];reason='250 m alcanzados'
    current,other,k=u,v,j;visited_nodes=set(nodes)
    for _ in range(1000):
     e=self.edges[k];used.add(k);ways.append(e['way'])
     if e['name'] and e['name'] not in names:names.append(e['name'])
     segment=LineString([self.xy[current],self.xy[other]]);remaining=250-length
     if remaining<=1e-7:break
     if segment.length>=remaining:
      end=segment.interpolate(remaining);coords.append((end.x,end.y));length=250.;break
     if other in visited_nodes:reason='retorno a un nodo ya recorrido';break
     visited_nodes.add(other)
     if segment.length>1e-8:coords.append(self.xy[other]);length+=segment.length
     previous,current=current,other;candidates=[]
     incoming=np.array(self.xy[current])-np.array(self.xy[previous]);norm=np.linalg.norm(incoming)
     if norm<1e-8:reason='segmento nulo';break
     for nxt in self.adj[current]:
      if nxt in used:continue
      candidate=self.edges[nxt];target=candidate['v'] if candidate['u']==current else candidate['u']
      direction=np.array(self.xy[target])-np.array(self.xy[current]);dn=np.linalg.norm(direction)
      if dn<1e-8:continue
      angle=math.degrees(math.acos(float(np.clip(np.dot(incoming,direction)/(norm*dn),-1,1))))
      same=bool(e['name'] and candidate['name']==e['name'])
      if angle<=(60 if same else 30):candidates.append((0 if same else 1,angle,nxt,target))
     if not candidates:reason='fin de vía o giro incompatible';break
     _,_,k,other=min(candidates)
    if len(coords)<2:continue
    line=LineString(coords)
    if line.length<40:continue
    if any(line.hausdorff_distance(r['geometry'])<2 for r in routes):continue
    assert line.length<=250.000001 and Point(line.coords[0]).distance(p)<1e-7
    routes.append({'geometry':line,'names':names,'ways':list(dict.fromkeys(ways)),'connectorM':dist,'stopReason':reason})
   return routes
  finally:
   for u,items in removed.items():self.adj[u]=items
   del self.adj[start];self.xy.pop();del self.edges[-2:]

def main():
 raw=json.loads(OSM.read_text(encoding='utf-8'));roads=[];walking_roads=[]
 allowed={'primary','secondary','tertiary','trunk','residential','unclassified','living_street','primary_link','secondary_link','tertiary_link','trunk_link','road','service'}
 for w in raw['elements']:
  tags=w.get('tags',{})
  if w.get('type')!='way' or len(w.get('geometry',[]))<2 or tags.get('highway') in ('construction','proposed') or tags.get('access')=='private':continue
  geom=transform(TO_M,LineString([(v['lon'],v['lat']) for v in w['geometry']]))
  item=(geom,tags.get('name',''),w['id'],tags.get('layer','0'));walking_roads.append(item)
  if tags.get('highway') in allowed:roads.append(item)
 for r in gpd.read_file(CONSOLIDATED,layer='PNPRI_RED_VIAL_REFERENCIA').to_crs(32717).itertuples():
  if str(r.highway) in ('construction','proposed'):continue
  for line in (r.geometry.geoms if hasattr(r.geometry,'geoms') else [r.geometry]):
   item=(line,r.name,r.osm_id,'0');walking_roads.append(item)
   if str(r.highway) in allowed:roads.append(item)
 osm=Network(roads,'OSM local consolidado');walking=Network(walking_roads,'OSM local consolidado · red peatonal de respaldo');local=[]
 for r in gpd.read_file(MUNICIPAL,layer='RED_VIAL_CONTEXTO').to_crs(32717).itertuples():
  for line in (r.geometry.geoms if hasattr(r.geometry,'geoms') else [r.geometry]):local.append((line,r.NOMBRE,'MUN-'+str(r.OBJECTID_1),'0'))
 municipal=Network(local,'Cartografía vial municipal local')
 original=json.loads((OUT/'LINEAS_AJUSTADAS_RIO023_RIO052_PN21.geojson').read_text(encoding='utf-8'))
 by=defaultdict(list)
 for f in original['features']:by[f['properties']['ID_CAMARA']].append(f)
 cameras=[]
 for group,name,key in [('existing','CAMARAS_EXISTENTES_103_FINAL','ID_CAMARA'),('municipal','PROPUESTA_MUNICIPAL_50_FINAL','ID_PROPUESTA'),('police','PROPUESTA_POLICIA_30_FINAL','ID_POLICIA')]:
  for f in json.loads((BASE/(name+'.geojson')).read_text(encoding='utf-8'))['features']:cameras.append((group,f['properties'][key],f))
 result=[];audit=[];case_features=[]
 for group,cid,camera in cameras:
  p=transform(TO_M,shape(camera['geometry']));old=by[cid];original_lines=[transform(TO_M,shape(f['geometry'])) for f in old]
  if cid in {'RIO-002-DOMO','RIO-023-DOMO','PN-21'}:
   result.extend(old);audit.append({'cameraId':cid,'group':group,'status':'AJUSTE_MANUAL_CONSERVADO','oldPaths':len(old),'newPaths':len(old),'reasons':['Ajuste cartográfico ya validado'],'maxOriginalOffRoadM':0.,'offRoadLengthM':0.});continue
  network=osm if osm.nearest(p)[1]<=30 else municipal if municipal.nearest(p)[1]<=30 else walking
  routes=network.routes(p)
  if not routes:
   result.extend(old);audit.append({'cameraId':cid,'group':group,'status':'SIN_ASOCIACION_LOCAL','oldPaths':len(old),'newPaths':len(old),'reasons':['No hay vía asociable a 30 m; no se inventa trazado'],'maxOriginalOffRoadM':None,'offRoadLengthM':None});continue
  manual=[f for f in old if f['properties'].get('EXCEPCION_USUARIO')]
  standard=[f for f in old if not f['properties'].get('EXCEPCION_USUARIO')]
  samples=[]
  for f in standard:
   line=transform(TO_M,shape(f['geometry']));samples.extend(line.interpolate(v) for v in np.arange(35,line.length+1e-7,5))
  distances=network.distances(np.array(samples,dtype=object)) if samples else np.array([])
  off=float((distances>12).sum()*5);maxoff=float(distances.max()) if len(distances) else 0.
  previous=union_all(original_lines).buffer(12) if original_lines else Point(p).buffer(.01)
  missing=[r for r in routes if r['geometry'].length>=70 and r['geometry'].difference(previous).length>max(20,.2*r['geometry'].length)]
  reasons=[]
  if off>=20:reasons.append('Línea fuera de la vía durante al menos 20 m')
  if missing:reasons.append('Brazos o calzadas del cruce sin representar')
  if len(routes)>len(old):reasons.append('Conectores internos ocultaban salidas del cruce')
  if cid=='RIO-027-DOMO':reasons.append('Caso señalado por el usuario: redondel y ejes de las avenidas')
  changed=bool(reasons)
  if not changed:result.extend(old)
  else:
   new=[]
   for route in routes:
    # The explicitly authorized long Puruhá arm of RIO-052 takes precedence.
    if manual and any(route['geometry'].difference(transform(TO_M,shape(f['geometry'])).buffer(12)).length<.2*route['geometry'].length for f in manual):continue
    props={'ID_CAMARA':cid,'SOURCE_GROUP':group,'REQUIERE_CAMBIO':bool(camera['properties'].get('REQUIERE_CAMBIO',False)),
     'BRAZO':len(new)+1,'VIA_INICIAL':' / '.join(route['names']) or 'Eje vial sin nombre en la fuente',
     'METODO_ANCLA':'Ejes conectados del cruce; continuación alineada, sin ramificación posterior',
     'FUENTE_RED':network.label,'SEPARACION_CAMARA_RED_M':route['connectorM'],'VISIBILIDAD_VERIFICADA':False,
     'DESDE_M':0,'HASTA_M':route['geometry'].length,'LONGITUD_M':route['geometry'].length,
     'RECORRIDO':'EJE_VIAL_AUDITADO','EXCEPCION_USUARIO':False,'AUDITORIA_CARTOGRAFICA':True,
     'FIN_RECORRIDO':route['stopReason'],'OSM_WAYS':','.join(route['ways'])}
    new.append({'type':'Feature','properties':props,'geometry':mapping(transform(TO_LL,route['geometry']))})
   new.extend(manual);result.extend(new)
   case_features.append({'type':'Feature','properties':{'ID_CAMARA':cid,'MOTIVOS':' | '.join(reasons)},'geometry':camera['geometry']})
  newcount=sum(f['properties']['ID_CAMARA']==cid for f in result)
  audit.append({'cameraId':cid,'group':group,'status':'CORREGIDO' if changed else 'SIN_CAMBIO','oldPaths':len(old),'newPaths':newcount,'reasons':reasons,'maxOriginalOffRoadM':maxoff,'offRoadLengthM':off,'source':network.label})
  print(cid,audit[-1]['status'],len(old),'->',newcount,flush=True)
 assert len(cameras)==183 and len({cid for _,cid,_ in cameras})==183
 cases=[r for r in audit if r['status']=='CORREGIDO'];unknown=[r for r in audit if r['status']=='SIN_ASOCIACION_LOCAL']
 output={'type':'FeatureCollection','features':result};dump('COBERTURA_VIAL_AUDITADA.geojson',output)
 dump('CAMARAS_CON_TRAZADO_CORREGIDO.geojson',{'type':'FeatureCollection','features':case_features})
 package=OUT/'COBERTURA_VIAL_AUDITADA.gpkg'
 gpd.GeoDataFrame.from_features(result,crs=4326).to_crs(32717).to_file(package,layer='COBERTURA_VIAL_AUDITADA',driver='GPKG')
 gpd.GeoDataFrame.from_features(case_features,crs=4326).to_crs(32717).to_file(package,layer='CAMARAS_CORREGIDAS',driver='GPKG')
 report={'camerasAudited':183,'correctedCameras':len(cases),'manualPreviouslyCorrected':3,'unassociatedCameras':[r['cameraId'] for r in unknown],
  'pathsBefore':len(original['features']),'pathsAfter':len(result),'criteria':{'associationM':30,'junctionRadiusM':35,'roadToleranceM':12,'minimumOffRoadLengthM':20,'maximumPathM':250,'maximumSameStreetTurnDegrees':60,'maximumChangedStreetTurnDegrees':30},
  'method':'Geometrías locales, vértices compartidos y nivel vial. Se priorizan vías vehiculares públicas; la red peatonal pública solo sirve de respaldo si no hay vía vehicular/municipal a 30 m. Se omiten accesos privados OSM. Un solo camino de continuación por brazo; sin ramificarse en cruces posteriores. Conector inicial desde la cámara a la vía, de hasta 30 m. No se certifica visibilidad física.',
  'cameraPositionsUnchanged':True,'areaPopulationAndGapCalculationsUnchanged':True,'rio052ExtensionPreserved':True,'cases':audit,
  'sourceConsolidatedRoadsSha256':hashlib.sha256(CONSOLIDATED.read_bytes()).hexdigest(),'sourceOsmSha256':hashlib.sha256(OSM.read_bytes()).hexdigest(),'sourceMunicipalSha256':hashlib.sha256(MUNICIPAL.read_bytes()).hexdigest()}
 dump('AUDITORIA_COBERTURAS_VIALES.json',report)
 with (OUT/'CAMARAS_CORREGIDAS_AUDITORIA.csv').open('w',newline='',encoding='utf-8-sig') as stream:
  writer=csv.writer(stream);writer.writerow(['CAMARA','GRUPO','MOTIVOS','TRAZOS_ANTES','TRAZOS_AHORA','MAX_DESVIO_ANTES_M'])
  for r in cases:writer.writerow([r['cameraId'],r['group'],' | '.join(r['reasons']),r['oldPaths'],r['newPaths'],round(r['maxOriginalOffRoadM'],2)])
 summary=json.loads((OUT/'RESUMEN.json').read_text(encoding='utf-8'));summary.update(primaryArms=len(result),geometryMode='AUDITED_ROAD_AXIS_COVERAGE',auditedCameras=183,correctedCameras=len(cases),streetMethod=report['method'])
 dump('RESUMEN.json',summary)
 print(json.dumps({k:v for k,v in report.items() if k not in ('cases','method')},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
