"""Apply only the user-approved MUN-038 intersection and spacing exception."""
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pyogrio
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'sig-bridge'))
sys.path.insert(0, str(ROOT/'tools'))
from bridge.store import Store, read_json, write_json, digest, require, clean, now
from bridge.engine import calculate, verify_derived
import recalculate_current_gaps as dependencies

RELEASE = 'MUN038_PRIMERA_CONSTITUYENTE_DARQUEA_20261017'
OUT = ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES'/RELEASE
TARGET = Point(762224.0768998107, 9814398.204348933)
ADDRESS = 'Primera Constituyente x Bernardo Darquea'
AUTH = 'Usuario solicita mover MUN-038 a Primera Constituyente x Bernardo Darquea y responde sii a la excepcion especifica: RIO-003-DOMO a245.72m. MUN-028 no autorizada, permanece fija.'

def read(path, layer):
    return pyogrio.read_dataframe(path, layer=layer).to_crs(32717)

def main():
    store = Store()
    require(store.web.name=='MUN021_ACCESO_LICAN_HURONES_20261017','Unexpected baseline')
    require(not OUT.exists(),'Never overwrite a release')
    before = read(store.base,'PROPUESTA_MUNICIPAL_50_FINAL')
    index = before.index[before.ID_PROPUESTA.eq('MUN-038')][0]
    old = before.geometry[index]
    roads = read(Path('D:/codex/entregas/RIOBAMBA_CONSOLIDADO_PRIORIDAD_REUNION_20261017/RIOBAMBA_CONSOLIDADO.gpkg'),'PNPRI_RED_VIAL_REFERENCIA')
    crossing = roads[roads.geometry.distance(TARGET)<.001]
    for name in ['Primera Constituyente','Bernardo Darquea']:
        require(crossing['name'].fillna('').str.contains(name,regex=False).any(),'Missing road '+name)
    hashes = {str(p):digest(p) for p in [store.base,ROOT/'sig-bridge-active.json',ROOT/'riobamba-kde-combinado-data.js',ROOT/'riobamba-hotspot-urbano-200m-data.js']}
    existing = read(store.base,'CAMARAS_EXISTENTES_103_FINAL')
    police = read(store.base,'PROPUESTA_POLICIA_30_FINAL')
    fixed = list(existing.geometry)+list(police.geometry)+list(before.drop(index=index).geometry)
    nearest = min(TARGET.distance(g) for g in fixed)
    require(abs(nearest-245.7152316464428)<.001,'Spacing differs from approved exception')
    manual = {}
    for key,spec in store.config['layers'].items():
        frame = read(store.base,spec['source'])
        if 'OBSERVACION_MANUAL' not in frame: frame['OBSERVACION_MANUAL']=''
        if key=='municipal':
            frame.loc[index,'geometry']=TARGET
            frame.loc[index,'OBSERVACION_MANUAL']=AUTH
        manual[key]=frame
    receipt = dict(revision=RELEASE,createdAt=now(),authorization=AUTH,applied=True,published=False,priorRelease=store.web.name,baseHashes=hashes,
                   spacingException=dict(id='MUN-038',existing='RIO-003-DOMO',distanceM=nearest,previousMinimumM=350,userApproved=True),
                   changes=[dict(layer='municipal',id='MUN-038',geometryChanged=True,fields=[],distanceM=old.distance(TARGET),note=AUTH)])
    def nodes(_store,_changes,municipal,_police,urban):
        for point,props in municipal:
            if props['ID_PROPUESTA']=='MUN-038':
                require(point.equals_exact(TARGET,.000001),'Wrong destination')
                props.update(DIRECCION=ADDRESS,INTERSECCION_O_NODO=ADDRESS,ESTADO_REVISION='NODO_DARQUEA_EXCEPCION_USUARIO',BRIDGE_NODO_VALIDADO=True,
                             FUENTE_CRUCE='Cruce compartido OSM Primera Constituyente x Bernardo Darquea; sin verificacion de poste.')
        return [dict(id='MUN-038',passed=True,cartographicNodeValidated=True,principalRoad=True,fieldVerified=False,minimumSpacingM=nearest,
                     spacingExceptionApproved=True,roads=crossing['name'].dropna().unique().tolist())],[]
    OUT.mkdir(parents=True)
    print('Recalculando MUN-038 y dependencias de escenarios B/C...',flush=True)
    validation=calculate(store,OUT,OUT,manual,receipt,node_validator=nodes)
    require(not validation['publishBlocks'],str(validation['publishBlocks']))
    package=OUT/'ESCENARIO_FINAL_183.gpkg'
    folder=OUT/'coverage-inputs';folder.mkdir()
    print('Actualizando indicadores100/150/200m...',flush=True)
    dependencies.main(final=package,out=folder,js_output=OUT/'riobamba-brechas-actualizadas-data.js',expected_replacements=30)
    gaps=read_json(folder/'RESULTADOS.json');prior_gaps=read_json(store.web/'coverage-inputs/RESULTADOS.json')
    prior_overlay={r['id']:r for r in prior_gaps['inventoryCameraOverlay']}
    for row in gaps['inventoryCameraOverlay']: row.update(prior_overlay[row['id']])
    for key in ['inventoryGeolocation','sourceInventory']: gaps['metadata'][key]=prior_gaps['metadata'][key]
    gaps['inventoryCoverage']['metadata'].update(prior_gaps['inventoryCoverage']['metadata'])
    gaps['metadata']['localRevision']=RELEASE
    payload=json.dumps(clean(gaps),ensure_ascii=False,allow_nan=False,separators=(',',':'))
    (folder/'RESULTADOS.json').write_text(payload,encoding='utf-8')
    (OUT/'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = '+payload+';\n',encoding='utf-8')
    results=read_json(OUT/'RESULTADOS.json')
    for key in ['anilloBStudy','boyacaStudy','publicRelease']: results.pop(key,None)
    results.update(status='MUN038_DARQUEA_CORREGIDA',sourcePackage=RELEASE,applied=True,published=False,authorization=AUTH,bridge=validation,
                   selectionMethod='Movimiento manual especifico; no reoptimiza ni cambia MUN-028.',approvedExceptions=[receipt['spacingException']],
                   warnings=['Solo cambia MUN-038.103 existentes,30 policiales yotras49municipales fijas.', 'Excepcion especifica aprobada:245.72m aRIO-003-DOMO, menor a350m.',
                             'Radio200m potencial, no certifica vision optica.19 existentes siguen provisionales.'])
    for path in OUT.iterdir():
        if path.is_file() and path.suffix in ['.md','.json'] and path.name not in ['RESULTADOS.json','VALIDACION.json','CORRIDOR_COVERAGE_200M.json']: path.unlink()
    write_json(OUT/'RESULTADOS.json',results);write_json(OUT/'VALIDACION.json',validation);write_json(OUT/'APROBACION_Y_FUENTES.json',receipt)
    corridor=read_json(OUT/'CORRIDOR_COVERAGE_200M.json');corridor['metadata']['sourcePackage']=RELEASE;write_json(OUT/'CORRIDOR_COVERAGE_200M.json',corridor)
    pyogrio.write_dataframe(read(package,'ESCENARIO_FINAL_183').to_crs(4326),OUT/'ESCENARIO_FINAL_183.geojson',driver='GeoJSON')
    verify_derived(store,package,results)
    actual=read(package,'PROPUESTA_MUNICIPAL_50_FINAL')
    changed=actual.geometry.to_wkb().to_numpy()!=before.geometry.to_wkb().to_numpy()
    require(set(actual.loc[changed,'ID_PROPUESTA'])=={'MUN-038'},'Unexpected municipal movement')
    for layer in ['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_POLICIA_30_FINAL']:
        require(read(store.base,layer).geometry.to_wkb().tolist()==read(package,layer).geometry.to_wkb().tolist(),'Protected geometry changed')
    prior=read_json(store.web/'RESULTADOS.json')
    for row in results['corridors']:
        match=[r for r in prior['corridors'] if r['ESCENARIO']==row['ESCENARIO'] and r['CORREDOR']==row['CORREDOR']]
        require(len(match)==1 and abs(row['PCT_CUBIERTO']-match[0]['PCT_CUBIERTO'])<1e-7,'Unexpected corridor coverage change')
    require(all(digest(Path(p))==v for p,v in hashes.items()),'Protected source changed')
    write_json(OUT/'VERIFICACION_INDEPENDIENTE.json',dict(passed=True,changedMunicipal=['MUN-038'],otherMunicipal49Fixed=True,existing103Fixed=True,police30Fixed=True,
               mun028PendingAndFixed=True,minimumSpacingM=nearest,spacingExceptionApproved=True,movementM=old.distance(TARGET),corridorCoverageUnchanged=True,giKdeUnchanged=True,published=False,baseHashes=hashes))
    (OUT/'MOVIMIENTOS_MUNICIPALES.csv').write_text('ID,DESPLAZAMIENTO_M,DESTINO\nMUN-038,'+str(old.distance(TARGET))+','+ADDRESS+'\n',encoding='utf-8')
    (OUT/'INFORME_FINAL.md').write_text('# MUN-038: Primera Constituyente x Bernardo Darquea\n\nMovimiento82.93m. Excepcion especifica aprobada por usuario:245.72m aRIO-003-DOMO. No cambia la regla para otros destinos.\n\nOtras49municipales,103existentes y30policiales intactas. MUN-028 pendiente: no se aplica su movimiento. MUN-021 conserva Hurones.\n\nMacaji100%,0m sin cubrir. Anillo75.17%municipal/82.73%conPolicia, Ciclovias61.45%municipal/62.18%conPolicia. Coberturas de corredores sin cambio. Indicadores100/150/200m recalculados. KDE/Gi* sin recalculo. Radio potencial, no vision optica certificada.\n',encoding='utf-8')
    with sqlite3.connect(package) as db:
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Invalid package')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)');db.execute('PRAGMA journal_mode=DELETE')
    print(json.dumps(dict(passed=True,release=RELEASE,movementM=old.distance(TARGET),nearestM=nearest)),flush=True)

def finalize():
    proof=read_json(OUT/'VERIFICACION_INDEPENDIENTE.json')
    require(proof['passed'] and proof['changedMunicipal']==['MUN-038'],'No validated correction')
    for filename in ['RESULTADOS.json','VALIDACION.json','VERIFICACION_INDEPENDIENTE.json','APROBACION_Y_FUENTES.json']:
        data=read_json(OUT/filename);data.update(published=True,publicRelease=RELEASE)
        if filename=='RESULTADOS.json': data['bridge'].update(published=True)
        write_json(OUT/filename,data)
    with zipfile.ZipFile(OUT/'ENTREGA_POLICIA_KDE.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in OUT.iterdir():
            if path.is_file() and path.suffix!='.zip': archive.write(path,path.name)
    print('Entrega MUN-038 preparada para publicacion.',flush=True)

def verify_public():
    import time
    import urllib.request
    base='https://stevanjazziel-ui.github.io/geoportal-catastro/'
    relative='data/seguridad-riobamba/SIG_BRIDGE_RELEASES/'+RELEASE+'/'
    def get(path,method='GET'):
        request=urllib.request.Request(base+path+'?verify='+str(time.time_ns()),headers={'Cache-Control':'no-cache','User-Agent':'Codex-MUN038-verification'},method=method)
        with urllib.request.urlopen(request,timeout=30) as response:
            require(response.status==200,'HTTP error')
            return response.read() if method=='GET' else int(response.headers.get('Content-Length',0))
    for attempt in range(45):
        pointer=json.loads(get('sig-bridge-active.json'))
        if pointer['releaseId']==RELEASE: break
        print('Esperando Pages: '+str(attempt+1),flush=True)
        time.sleep(8)
    else: raise RuntimeError('Deployment not confirmed')
    proof=dict(passed=False,release=RELEASE,files={})
    for filename,count in [('CAMARAS_EXISTENTES_103_FINAL.geojson',103),('PROPUESTA_MUNICIPAL_50_FINAL.geojson',50),('PROPUESTA_POLICIA_30_FINAL.geojson',30)]:
        actual=json.loads(get(relative+filename));expected=read_json(OUT/filename)
        require(actual==expected and len(actual['features'])==count,'Public camera mismatch')
        proof['files'][filename]=dict(matchesLocal=True,count=count)
        if count==50:
            proof['mun038']=next(f for f in actual['features'] if f['properties']['ID_PROPUESTA']=='MUN-038')['geometry']
    for filename in ['ESCENARIO_FINAL_183.gpkg','ENTREGA_POLICIA_KDE.zip']:
        length=get(relative+filename,'HEAD')
        require(length==(OUT/filename).stat().st_size,'Public download mismatch')
        proof['files'][filename]=dict(httpStatus=200,bytes=length)
    results=json.loads(get(relative+'RESULTADOS.json'))
    require(results['sourcePackage']==RELEASE and results['published'],'Wrong results release')
    proof['passed']=True
    write_json(Path('D:/codex/entregas/PUBLICACION_MUN038_20261017.json'),proof)
    print(json.dumps(proof,indent=2),flush=True)

if __name__=='__main__':
    if '--verify-public' in sys.argv: verify_public()
    elif '--finalize' in sys.argv: finalize()
    else: main()
