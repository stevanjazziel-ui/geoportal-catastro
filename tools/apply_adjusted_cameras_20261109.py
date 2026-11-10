"""Import user-approved adjusted shapefile geometries and refresh all coverage."""
import json,sys,shutil,zipfile,sqlite3
from pathlib import Path
import geopandas as gpd
import pyogrio
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'sig-bridge'),str(ROOT/'tools')]
from bridge.store import Store,read_json,write_json,digest,clean,require,now
from bridge.engine import calculate,verify_derived
import recalculate_current_gaps as gaps_adapter
RELEASE='CAMARAS_AJUSTADAS_USUARIO_20261109'
OUT=ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES'/RELEASE
INPUT=ROOT.parent/'entregas/CAMARAS_AJUSTADAS_20261109/insumos/camaras_ajustadas'
ARCHIVE=Path('C:/Users/PC/Downloads/camaras/camaras_ajustadas.rar')
UNPROJECT=Transformer.from_crs(32717,4326,always_xy=True)
SPECS=[('existing','CAMARAS_EXISTENTES_103_FINAL','ID_CAMARA','existentes_73_sin_cambio_y_30_cambio_ajustado.shp','ID_CAMARA',103),('municipal','PROPUESTA_MUNICIPAL_50_FINAL','ID_PROPUESTA','Municipales_50_ajustadas.shp','ID_PROPUES',50),('police','PROPUESTA_POLICIA_30_FINAL','ID_POLICIA','policia_30_ajustada.shp','ID_POLICIA',30)]
def read(p,l):return pyogrio.read_dataframe(p,layer=l).to_crs(32717)
def sync(frame):
 for ix,row in frame.iterrows():
  x,y=row.geometry.x,row.geometry.y;lon,lat=UNPROJECT.transform(x,y)
  for k,v in {'X':x,'Y':y,'X_UTM':x,'Y_UTM':y,'LONGITUD':lon,'LATITUD':lat,'ESTE_UTM_17S':x,'NORTE_UTM_17S':y}.items():
   if k in frame.columns:frame.at[ix,k]=v
 return frame
def main():
 store=Store(ROOT);resume='--resume' in sys.argv;require(not OUT.exists() or resume,'No sobrescribir una entrega');manual={};targets={};changes=[];counts={}
 receipt={'revision':RELEASE,'createdAt':now(),'priorRelease':store.web.name,'authorization':'Usuario entrega camaras_ajustadas.rar como camaras ya ajustadas y solicita rehacer radios, ubicar y publicar. Se conservan las geometrias entregadas sin optimizacion ni ajuste automatico a vias.','baseHashes':{str(store.base):digest(store.base)},'sourceArchiveSha256':digest(ARCHIVE),'sourceFiles':{p.name:digest(p) for p in INPUT.iterdir() if p.is_file()},'changes':changes}
 for key,layer,idfield,file,sourceid,count in SPECS:
  original=read(store.base,layer);incoming=gpd.read_file(INPUT/file).to_crs(32717)
  require(len(incoming)==count and incoming[sourceid].is_unique and set(incoming[sourceid])==set(original[idfield]),'Conteo/IDs incorrectos: '+key)
  require(incoming.geometry.notna().all() and (~incoming.geometry.is_empty).all() and incoming.geometry.is_valid.all() and incoming.geom_type.eq('Point').all(),'Geometrias incorrectas')
  incoming=incoming.set_index(sourceid);targets[key]=incoming;counts[key]=0
  if key=='existing':require(all(bool(incoming.loc[r[idfield],'REQUIERE_C'])==bool(r.REQUIERE_CAMBIO) for _,r in original.iterrows()),'Clasificacion 73/30 alterada')
  for ix,row in original.iterrows():
   point=incoming.loc[row[idfield]].geometry;dist=row.geometry.distance(point);original.at[ix,'geometry']=point
   if dist>.001:
    counts[key]+=1;changes.append(dict(layer=key,id=row[idfield],geometryChanged=True,fields=[],distanceM=dist,note='Geometria aprobada por usuario en '+file+'; direccion nominal previa pendiente de cotejo.'))
    if key=='existing':
     original.at[ix,'METODO_GEO']='AJUSTE_USUARIO_SHAPEFILE_20261109';original.at[ix,'OBSERVACION_GEO']='Posicion geometrica entregada por el usuario; no verificacion GPS ni de campo visual.'
  original=sync(original)
  if key=='existing':inventory=original
  else:
   if 'OBSERVACION_MANUAL' not in original:original['OBSERVACION_MANUAL']=''
   for change in changes:
    if change['layer']==key:original.loc[original[idfield].eq(change['id']),'OBSERVACION_MANUAL']=change['note']
   manual[key]=original
 for key,spec in store.config['layers'].items():
  if key not in manual:manual[key]=read(store.base,spec['source'])
 OUT.mkdir(parents=True,exist_ok=resume);write_json(OUT/'IMPORTACION_AJUSTES_USUARIO.json',receipt)
 def approved_geometry(_store,_changes,municipal,police,_urban):
  for group,rows,idfield in [('municipal',municipal,'ID_PROPUESTA'),('police',police,'ID_POLICIA')]:
   for point,props in rows:
    require(point.wkb==targets[group].loc[props[idfield]].geometry.wkb,'Destino incorrecto')
    if any(c['layer']==group and c['id']==props[idfield] for c in changes):
     props.update(BRIDGE_NODO_VALIDADO=False,ESTADO_REVISION='GEOMETRIA_AJUSTADA_APROBADA_USUARIO',FUENTE_CRUCE='Shapefile ajustado por usuario; sin ajuste automatico a calles',COBERTURA_VISUAL_CERTIFICADA=False)
  return [],[]
 print('RECALCULANDO',counts,flush=True)
 validation=read_json(OUT/'VALIDACION.json') if resume else calculate(store,OUT,OUT,manual,receipt,existing_override=inventory,node_validator=approved_geometry)
 # Approved exact geometries take precedence over earlier optimization targets.
 exceptions=[m for m in validation['publishBlocks'] if m.startswith('Restriccion municipal ')] or validation.get('approvedGeometryException',{}).get('warnings',[])
 require(all(m in exceptions for m in validation['publishBlocks']),'Inconsistencia estructural: '+str(validation['publishBlocks']))
 if exceptions:
  validation['approvedGeometryException']={'warnings':exceptions,'authorization':receipt['authorization'],'reason':'Publicar las posiciones definitivas entregadas sin moverlas para alcanzar un objetivo historico de cobertura.'}
 validation['publishBlocks']=[];validation['status']='PASS_USER_APPROVED_GEOMETRIES'
 write_json(OUT/'VALIDACION.json',validation)
 package=OUT/'ESCENARIO_FINAL_183.gpkg'
 for key,layer,idfield,file,sourceid,count in SPECS:
  final=read(package,layer).set_index(idfield)
  require(all(final.loc[k].geometry.wkb==r.geometry.wkb for k,r in targets[key].iterrows()),'Geometria importada difiere: '+key)
  for radiuslayer in [('RADIOS_MUNICIPALES_200M' if key=='municipal' else 'RADIOS_POLICIA_200M' if key=='police' else 'RADIOS_EXISTENTES_SIMBOLOGIA_200M')]:
   disks=final.reset_index()[[idfield,'geometry']].copy();disks['RADIO_M']=200
   if key=='existing':disks['REQUIERE_CAMBIO']=final.REQUIERE_CAMBIO.values
   disks.geometry=disks.geometry.buffer(200,resolution=64);pyogrio.write_dataframe(disks,package,layer=radiuslayer)
  if key=='existing':
   continue
  pyogrio.write_dataframe(final.reset_index().to_crs(4326),OUT/(layer+'.geojson'),driver='GeoJSON')
 pyogrio.write_dataframe(read(package,'RADIOS_EXISTENTES_SIMBOLOGIA_200M').to_crs(4326),OUT/'RADIOS_EXISTENTES_SIMBOLOGIA_200M.geojson',driver='GeoJSON')
 folder=OUT/'coverage-inputs';folder.mkdir(exist_ok=resume)
 gaps_adapter.main(final=package,out=folder,js_output=OUT/'riobamba-brechas-actualizadas-data.js',expected_replacements=30)
 gaps=read_json(folder/'RESULTADOS.json');gaps['metadata']['localRevision']=RELEASE
 gaps['metadata']['sourceInventory']={'source':'camaras_ajustadas.rar','sha256':digest(ARCHIVE),'authorization':receipt['authorization']}
 for row in gaps['inventoryCameraOverlay']:
  row['coordinateSource']='Geometria ajustada por usuario en camaras_ajustadas.rar';row['sourcePackage']=RELEASE
 write_json(folder/'RESULTADOS.json',gaps)
 js='window.RIOBAMBA_UPDATED_GAPS = '+json.dumps(clean(gaps),ensure_ascii=False,allow_nan=False,separators=(',',':'))+';\n'
 for path in [OUT,folder]:(path/'riobamba-brechas-actualizadas-data.js').write_text(js,encoding='utf-8')
 shutil.copytree(store.web/'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA',OUT/'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA')
 pyogrio.write_dataframe(read(package,'ESCENARIO_FINAL_183').to_crs(4326),OUT/'ESCENARIO_FINAL_183.geojson',driver='GeoJSON')
 results=read_json(OUT/'RESULTADOS.json');results.update(status='AJUSTES_USUARIO_APLICADOS',sourcePackage=RELEASE,publicRelease=RELEASE,applied=True,published=False,bridge=validation,adjustedCameraCounts=counts,authorization=receipt['authorization'])
 write_json(OUT/'RESULTADOS.json',results);verify_derived(store,package,results,inventory)
 with sqlite3.connect(package) as db:require(db.execute('pragma integrity_check').fetchone()[0]=='ok','GPKG invalido')
 proof={'passed':True,'counts':{'existing':103,'unchangedClass':73,'replacementClass':30,'municipal':50,'police':30},'moved':counts,'all183GeometriesEqualApprovedSource':True,'radiusM':200,'buffersRecomputed':True,'coordinateAttributesUpdated':True,'approvedGeometryExceptions':exceptions,'sourceArchiveSha256':digest(ARCHIVE)}
 write_json(OUT/'VERIFICACION_INDEPENDIENTE.json',proof)
 write_json(OUT/'APROBACION_Y_FUENTES.json',{**receipt,'applied':True,'publicationRequested':True,'published':False})
 (OUT/'INFORME_FINAL.md').write_text('# Camaras ajustadas por usuario\n\n103 existentes, 50 municipales y 30 policiales. Se importan exactamente las geometrias recibidas, se actualizan coordenadas y se recalculan radios metricos de 200 m, coberturas, poblacion y brechas. No se optimizan posiciones. Los nombres viales previos requieren cotejo donde se movieron puntos. Los radios no certifican visibilidad.\n\nMovimientos: '+str(counts)+'\n\n'+('\n'.join(exceptions)),encoding='utf-8')
 with zipfile.ZipFile(OUT/'ENTREGA_POLICIA_KDE.zip','w',zipfile.ZIP_DEFLATED) as archive:
  for path in sorted(OUT.rglob('*')):
   if path.is_file() and path.suffix!='.zip':archive.write(path,path.relative_to(OUT).as_posix())
 print('VERIFICADO',json.dumps(proof),flush=True)
if __name__=='__main__':main()
