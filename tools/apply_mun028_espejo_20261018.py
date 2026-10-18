"""Publish the requested MUN-028 move; leave the unlocated MUN-041 pending."""
import json
import sqlite3
import sys
import zipfile
from pathlib import Path
import pyogrio
from shapely.geometry import Point

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sig-bridge'));sys.path.insert(0,str(ROOT/'tools'))
from bridge.store import Store,read_json,write_json,digest,require,clean,now
from bridge.engine import calculate,verify_derived
import recalculate_current_gaps as dependencies

RELEASE='MUN028_9OCTUBRE_EUGENIO_ESPEJO_20261018'
OUT=ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES'/RELEASE
TARGET=Point(760844.1573069814,9814049.17301709)
ADDRESS='Avenida 9 de Octubre x Eugenio Espejo'
AUTH='Usuario indica publica todo tras informar que MUN-028 queda a337m dePN-17 y Anillo conPolicia82.25%. Publicar este destino; MUN-041 pendiente de identificar cruce, no se mueve.'

def read(path,layer):
    return pyogrio.read_dataframe(path,layer=layer).to_crs(32717)

def main():
    store=Store()
    require(store.web.name=='MUN038_PRIMERA_CONSTITUYENTE_DARQUEA_20261017','Unexpected baseline')
    require(not OUT.exists(),'Never overwrite a release')
    before=read(store.base,'PROPUESTA_MUNICIPAL_50_FINAL')
    index=before.index[before.ID_PROPUESTA.eq('MUN-028')][0];old=before.geometry[index]
    roads=read(Path('D:/codex/entregas/RIOBAMBA_CONSOLIDADO_PRIORIDAD_REUNION_20261017/RIOBAMBA_CONSOLIDADO.gpkg'),'PNPRI_RED_VIAL_REFERENCIA')
    crossing=roads[roads.geometry.distance(TARGET)<.001]
    for name in ['9 de Octubre','Eugenio Espejo']:
        require(crossing['name'].fillna('').str.contains(name,regex=False).any(),'Missing road '+name)
    source_paths=[store.base,ROOT/'sig-bridge-active.json',ROOT/'riobamba-kde-combinado-data.js',ROOT/'riobamba-hotspot-urbano-200m-data.js']
    hashes={str(p):digest(p) for p in source_paths}
    e=read(store.base,'CAMARAS_EXISTENTES_103_FINAL');p=read(store.base,'PROPUESTA_POLICIA_30_FINAL')
    nearest=min(TARGET.distance(g) for g in list(e.geometry)+list(p.geometry)+list(before.drop(index=index).geometry))
    require(abs(nearest-336.576631563523)<.001,'Wrong spacing exception')
    manual={}
    for key,spec in store.config['layers'].items():
        frame=read(store.base,spec['source'])
        if 'OBSERVACION_MANUAL' not in frame:frame['OBSERVACION_MANUAL']=''
        if key=='municipal':
            frame.loc[index,'geometry']=TARGET;frame.loc[index,'OBSERVACION_MANUAL']=AUTH
        manual[key]=frame
    exception=dict(id='MUN-028',camera='PN-17',distanceM=nearest,previousMinimumM=350,userApproved=True)
    receipt=dict(revision=RELEASE,createdAt=now(),authorization=AUTH,applied=True,published=False,priorRelease=store.web.name,baseHashes=hashes,
                 spacingException=exception,pendingUnapplied=['MUN-041: Barbados x Primera Constituyente no identificado'],
                 changes=[dict(layer='municipal',id='MUN-028',geometryChanged=True,fields=[],distanceM=old.distance(TARGET),note=AUTH)])
    def nodes(_store,_changes,municipal,_police,urban):
        for point,props in municipal:
            if props['ID_PROPUESTA']=='MUN-028':
                require(point.equals_exact(TARGET,.000001),'Wrong target')
                props.update(DIRECCION=ADDRESS,INTERSECCION_O_NODO=ADDRESS,ESTADO_REVISION='EUGENIO_ESPEJO_EXCEPCION_USUARIO',BRIDGE_NODO_VALIDADO=True,
                             FUENTE_CRUCE='Cruce compartido OSM 9 de Octubre x Eugenio Espejo; poste y vision sin verificar en campo.')
        return [dict(id='MUN-028',passed=True,cartographicNodeValidated=True,principalRoad=True,fieldVerified=False,minimumSpacingM=nearest,
                     spacingExceptionApproved=True,roads=crossing['name'].dropna().unique().tolist())],[]
    OUT.mkdir(parents=True)
    print('Recalculando MUN-028 y dependencias B/C...',flush=True)
    validation=calculate(store,OUT,OUT,manual,receipt,node_validator=nodes)
    require(not validation['publishBlocks'],str(validation['publishBlocks']))
    package=OUT/'ESCENARIO_FINAL_183.gpkg';folder=OUT/'coverage-inputs';folder.mkdir()
    print('Recalculando indicadores100/150/200m...',flush=True)
    dependencies.main(final=package,out=folder,js_output=OUT/'riobamba-brechas-actualizadas-data.js',expected_replacements=30)
    gaps=read_json(folder/'RESULTADOS.json');prior_gaps=read_json(store.web/'coverage-inputs/RESULTADOS.json')
    overlay={r['id']:r for r in prior_gaps['inventoryCameraOverlay']}
    for row in gaps['inventoryCameraOverlay']:row.update(overlay[row['id']])
    for key in ['inventoryGeolocation','sourceInventory']:gaps['metadata'][key]=prior_gaps['metadata'][key]
    gaps['inventoryCoverage']['metadata'].update(prior_gaps['inventoryCoverage']['metadata']);gaps['metadata']['localRevision']=RELEASE
    payload=json.dumps(clean(gaps),ensure_ascii=False,allow_nan=False,separators=(',',':'))
    (folder/'RESULTADOS.json').write_text(payload,encoding='utf-8')
    (OUT/'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = '+payload+';\n',encoding='utf-8')
    results=read_json(OUT/'RESULTADOS.json');results.pop('publicRelease',None)
    prior=read_json(store.web/'RESULTADOS.json')
    results.update(status='MUN028_ESPEJO_CORREGIDA',sourcePackage=RELEASE,applied=True,published=False,authorization=AUTH,bridge=validation,
                   selectionMethod='Cambio manual solicitado de MUN-028; mantiene movimientos publicados de MUN-021 yMUN-038.',
                   approvedExceptions=prior.get('approvedExceptions',[])+[exception],pendingUnapplied=receipt['pendingUnapplied'],
                   warnings=['Solo cambia MUN-028 respecto a la version anterior.103existentes,30policiales,otras49municipales intactas.',
                             'Excepcion puntual336.58m respecto aPN-17. MUN-038 conserva su excepcion aprobada.',
                             'Macaji100%; Anillo combinado82.25%. MUN-041 no se mueve sin identificar el cruce.',
                             'Radio200m potencial, no vision optica certificada.19existentes provisionales.'])
    for path in OUT.iterdir():
        if path.is_file() and path.suffix in ['.md','.json'] and path.name not in ['RESULTADOS.json','VALIDACION.json','CORRIDOR_COVERAGE_200M.json']:path.unlink()
    write_json(OUT/'RESULTADOS.json',results);write_json(OUT/'VALIDACION.json',validation);write_json(OUT/'APROBACION_Y_FUENTES.json',receipt)
    corridor=read_json(OUT/'CORRIDOR_COVERAGE_200M.json');corridor['metadata']['sourcePackage']=RELEASE;write_json(OUT/'CORRIDOR_COVERAGE_200M.json',corridor)
    pyogrio.write_dataframe(read(package,'ESCENARIO_FINAL_183').to_crs(4326),OUT/'ESCENARIO_FINAL_183.geojson',driver='GeoJSON')
    verify_derived(store,package,results)
    actual=read(package,'PROPUESTA_MUNICIPAL_50_FINAL')
    changed=actual.geometry.to_wkb().to_numpy()!=before.geometry.to_wkb().to_numpy()
    require(set(actual.loc[changed,'ID_PROPUESTA'])=={'MUN-028'},'Unexpected municipal move')
    for layer in ['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_POLICIA_30_FINAL']:
        require(read(store.base,layer).geometry.to_wkb().tolist()==read(package,layer).geometry.to_wkb().tolist(),'Protected geometry changed')
    rows={(r['ESCENARIO'],r['CORREDOR']):r for r in results['corridors']}
    require(rows['B','BOULEVARD_MACAJI_BELLAVISTA']['NO_CUBIERTO_M']<=.01,'Macaji uncovered')
    require(abs(rows['B','ANILLO_VIAL']['PCT_CUBIERTO']-75.17199990)<1e-6,'Unexpected municipal ring')
    require(abs(rows['C','ANILLO_VIAL']['PCT_CUBIERTO']-82.25221417)<1e-6,'Unexpected combined ring')
    require(all(digest(Path(path))==value for path,value in hashes.items()),'Protected source changed')
    write_json(OUT/'VERIFICACION_INDEPENDIENTE.json',dict(passed=True,changedMunicipal=['MUN-028'],otherMunicipal49Fixed=True,existing103Fixed=True,police30Fixed=True,
               mun021And038Preserved=True,mun041PendingAndFixed=True,minimumSpacingM=nearest,spacingExceptionApproved=True,movementM=old.distance(TARGET),giKdeUnchanged=True,published=False,baseHashes=hashes))
    (OUT/'MOVIMIENTOS_MUNICIPALES.csv').write_text('ID,DESPLAZAMIENTO_M,DESTINO\nMUN-028,'+str(old.distance(TARGET))+','+ADDRESS+'\n',encoding='utf-8')
    (OUT/'INFORME_FINAL.md').write_text('# MUN-028: 9 de Octubre x Eugenio Espejo\n\nMovimiento79.70m. Excepcion336.58m aPN-17 aprobada al pedir publicar todo tras informar la restriccion.\n\nSolo cambia MUN-028 respecto a la anterior. Conserva MUN-021 enMaldonado x Hurones yMUN-038 enPrimera Constituyente x Bernardo Darquea.103existentes y30policiales fijas. MUN-041 pendiente: cruceBarbados x Primera Constituyente no identificado. No se inventan coordenadas.\n\nMacaji100%,0m sin cubrir. Anillo75.1720%municipal/82.2522%conPolicia. Ciclovias61.4546%municipal/62.1821%conPolicia. Dependencias100/150/200m recalculadas; KDE/Gi* sin recalculo. Radio potencial, no visibilidad optica certificada.\n',encoding='utf-8')
    with sqlite3.connect(package) as db:
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Invalid GPKG')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)');db.execute('PRAGMA journal_mode=DELETE')
    print(json.dumps(dict(passed=True,release=RELEASE,movementM=old.distance(TARGET),nearestM=nearest)),flush=True)

def finalize():
    proof=read_json(OUT/'VERIFICACION_INDEPENDIENTE.json');require(proof['passed'] and proof['changedMunicipal']==['MUN-028'],'No validated correction')
    for filename in ['RESULTADOS.json','VALIDACION.json','VERIFICACION_INDEPENDIENTE.json','APROBACION_Y_FUENTES.json']:
        data=read_json(OUT/filename);data.update(published=True,publicRelease=RELEASE)
        if filename=='RESULTADOS.json':data['bridge'].update(published=True)
        write_json(OUT/filename,data)
    with zipfile.ZipFile(OUT/'ENTREGA_POLICIA_KDE.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in OUT.iterdir():
            if path.is_file() and path.suffix!='.zip':archive.write(path,path.name)
    print('MUN-028 preparada para publicacion.',flush=True)

def verify_public():
    import time
    import urllib.request
    base='https://stevanjazziel-ui.github.io/geoportal-catastro/';relative='data/seguridad-riobamba/SIG_BRIDGE_RELEASES/'+RELEASE+'/'
    def get(path,method='GET'):
        request=urllib.request.Request(base+path+'?verify='+str(time.time_ns()),headers={'Cache-Control':'no-cache','User-Agent':'Codex-MUN028-verification'},method=method)
        with urllib.request.urlopen(request,timeout=30) as response:
            require(response.status==200,'HTTP error')
            return response.read() if method=='GET' else int(response.headers.get('Content-Length',0))
    for attempt in range(45):
        if json.loads(get('sig-bridge-active.json'))['releaseId']==RELEASE:break
        print('Esperando Pages: '+str(attempt+1),flush=True);time.sleep(8)
    else:raise RuntimeError('Deployment not confirmed')
    proof=dict(passed=False,release=RELEASE,files={})
    for filename,count in [('CAMARAS_EXISTENTES_103_FINAL.geojson',103),('PROPUESTA_MUNICIPAL_50_FINAL.geojson',50),('PROPUESTA_POLICIA_30_FINAL.geojson',30)]:
        actual=json.loads(get(relative+filename));require(actual==read_json(OUT/filename) and len(actual['features'])==count,'Public camera mismatch')
        proof['files'][filename]=dict(matchesLocal=True,count=count)
        if count==50:proof['mun028']=next(f for f in actual['features'] if f['properties']['ID_PROPUESTA']=='MUN-028')['geometry']
    for filename in ['ESCENARIO_FINAL_183.gpkg','ENTREGA_POLICIA_KDE.zip']:
        length=get(relative+filename,'HEAD');require(length==(OUT/filename).stat().st_size,'Public download mismatch');proof['files'][filename]=dict(httpStatus=200,bytes=length)
    results=json.loads(get(relative+'RESULTADOS.json'));require(results['sourcePackage']==RELEASE and results['published'],'Wrong release')
    proof['passed']=True;write_json(Path('D:/codex/entregas/PUBLICACION_MUN028_20261018.json'),proof);print(json.dumps(proof,indent=2),flush=True)

if __name__=='__main__':
    if '--verify-public' in sys.argv:verify_public()
    elif '--finalize' in sys.argv:finalize()
    else:main()
