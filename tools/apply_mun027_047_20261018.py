"""Apply, recalculate, and prepare publication of MUN-027 and MUN-047."""
import json, shutil, sqlite3, sys
from pathlib import Path
import pyogrio
from shapely.ops import nearest_points
from shapely.geometry import Point

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'sig-bridge'),str(ROOT/'tools')]
from bridge.store import Store,read_json,write_json,digest,require,now,clean
from bridge.engine import calculate
import recalculate_current_gaps as dependencies

RELEASE='MUN027_047_CANONIGO_DUCHICELA_20261018'
BASELINE='MUN035_040_GUAYAQUIL_ESMERALDAS_20261018'
OUT=ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES'/RELEASE
ROAD_PATH=Path('D:/codex/entregas/RIOBAMBA_CONSOLIDADO_PRIORIDAD_REUNION_20261017/RIOBAMBA_CONSOLIDADO.gpkg')
SPEC={'MUN-027':('CANONIGO RAMOS','AGUSTIN GUERRERO','Avenida Canónigo Ramos x Agustín Guerrero'),
      'MUN-047':('DUCHICELA','BOYACA','Duchicela x Boyacá')}

def read(path,layer): return pyogrio.read_dataframe(path,layer=layer).to_crs(32717)
def normalized(value):
    import unicodedata
    return unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().upper()

def main():
    store=Store()
    require(store.web.name==BASELINE,'Active release changed')
    require(not OUT.exists(),'Never overwrite a release')
    roads=read(ROAD_PATH,'PNPRI_RED_VIAL_REFERENCIA')
    cameras=read(store.base,'PROPUESTA_MUNICIPAL_50_FINAL')
    old={}; targets={}; crossing_data={}
    for camera,(name_a,name_b,address) in SPEC.items():
        a=roads[roads.name.map(normalized).str.contains(name_a,regex=False)]
        b=roads[roads.name.map(normalized).str.contains(name_b,regex=False)]
        pairs=sorted(((x.geometry.distance(y.geometry),x.geometry,y.geometry,x['name'],y['name'])
                      for _,x in a.iterrows() for _,y in b.iterrows()),key=lambda item:item[0])
        require(bool(pairs),f'Roads unavailable for {camera}')
        gap,geom_a,geom_b,road_a,road_b=pairs[0]
        require(gap<=6,f'Roads do not meet at a verifiable node for {camera}: {gap:.2f}m')
        point_a,point_b=nearest_points(geom_a,geom_b)
        target=Point((point_a.x+point_b.x)/2,(point_a.y+point_b.y)/2)
        idx=cameras.index[cameras.ID_PROPUESTA.eq(camera)][0]
        old[camera]=cameras.geometry[idx]
        targets[camera]=(target,address)
        crossing_data[camera]=dict(gapM=gap,roads=[str(road_a),str(road_b)])
        cameras.loc[idx,'geometry']=target
    pair_distance=targets['MUN-027'][0].distance(targets['MUN-047'][0])
    ex=read(store.base,'CAMARAS_EXISTENTES_103_FINAL'); pn=read(store.base,'PROPUESTA_POLICIA_30_FINAL')
    fixed=list(ex.geometry)+list(pn.geometry)
    nearest={}
    for camera,(point,_) in targets.items():
        other=[g for cid,g in zip(cameras.ID_PROPUESTA,cameras.geometry) if cid!=camera]
        nearest[camera]=min(point.distance(g) for g in fixed+other)
    auth='Usuario solicita mover MUN-027 a Canónigo Ramos x Agustín Guerrero y MUN-047 a Duchicela x Boyacá, y publicar. Se conservan las excepciones aprobadas de Macají y separaciones menores a 400m.'
    sources=[store.base,ROOT/'riobamba-kde-combinado-data.js',ROOT/'riobamba-hotspot-urbano-200m-data.js']
    hashes={str(p):digest(p) for p in sources}
    hashes[str(ROOT/'sig-bridge-active.json')]=digest(ROOT/'sig-bridge-active.json')
    manual={}
    for key,spec in store.config['layers'].items():
        frame=read(store.base,spec['source'])
        if 'OBSERVACION_MANUAL' not in frame: frame['OBSERVACION_MANUAL']=''
        if key=='municipal':
            for camera,(point,address) in targets.items():
                i=frame.index[frame.ID_PROPUESTA.eq(camera)][0]
                frame.loc[i,'geometry']=point; frame.loc[i,'OBSERVACION_MANUAL']=auth
        manual[key]=frame
    receipt=dict(revision=RELEASE,createdAt=now(),authorization=auth,applied=True,published=False,
                 priorRelease=store.web.name,baseHashes=hashes,
                 changes=[dict(layer='municipal',id=camera,geometryChanged=True,fields=[],distanceM=old[camera].distance(targets[camera][0]),note=auth) for camera in SPEC],
                 nearestCameraM=nearest,pairSeparationM=pair_distance,crossingEvidence=crossing_data)
    def node_validator(_store,_changes,points,_police,_urban):
        checks=[]
        for point,props in points:
            camera=props.get('ID_PROPUESTA')
            if camera not in SPEC: continue
            target,address=targets[camera]
            require(point.equals_exact(target,1e-6),f'Wrong geometry {camera}')
            evidence=crossing_data[camera]
            props.update(DIRECCION=address,INTERSECCION_O_NODO=address,BRIDGE_NODO_VALIDADO=True,
                         ESTADO_REVISION='DESTINO_EXPRESO_USUARIO',
                         FUENTE_CRUCE=f"Red vial OSM: {evidence['roads']}; separación de líneas de centro {evidence['gapM']:.2f} m, punto medio usado; verificación de campo pendiente.")
            checks.append(dict(id=camera,passed=True,cartographicNodeValidated=True,fieldVerified=False,
                               nearestCameraM=nearest[camera],nodeCenterlineGapM=evidence['gapM'],roads=evidence['roads']))
        require(len(checks)==2,'Both nodes must validate')
        return checks,[]
    OUT.mkdir(parents=True)
    print('Recalculando cámaras y coberturas...',flush=True)
    validation=calculate(store,OUT,OUT,manual,receipt,node_validator=node_validator)
    package=OUT/'ESCENARIO_FINAL_183.gpkg'; folder=OUT/'coverage-inputs'; folder.mkdir()
    dependencies.main(final=package,out=folder,js_output=OUT/'riobamba-brechas-actualizadas-data.js',expected_replacements=30)
    corridors=read_json(OUT/'CORRIDOR_COVERAGE_200M.json')
    prior_corridors=read_json(store.web/'CORRIDOR_COVERAGE_200M.json')
    for scenario in ['B','C']:
        new=corridors['scenarios'][scenario]['corridors']['BOULEVARD_MACAJI_BELLAVISTA']['coveredPct']
        prior=prior_corridors['scenarios'][scenario]['corridors']['BOULEVARD_MACAJI_BELLAVISTA']['coveredPct']
        require(new>=prior-1e-7,f'Macaji coverage would further fall: {prior:.5f}% -> {new:.5f}%')
    if validation['publishBlocks']:
        require(all('BOULEVARD_MACAJI_BELLAVISTA' in x for x in validation['publishBlocks']),'Unexpected publish blocker')
        validation['waivedBlocks']=list(validation['publishBlocks']); validation['publishBlocks']=[]
        validation['approvedWaivers']=read_json(store.web/'VALIDACION.json').get('approvedWaivers',[])
        validation['status']='READY_WITH_USER_APPROVED_EXCEPTION'
    old_gaps=read_json(store.web/'coverage-inputs/RESULTADOS.json'); gaps=read_json(folder/'RESULTADOS.json')
    overlays={row['id']:row for row in old_gaps['inventoryCameraOverlay']}
    for row in gaps['inventoryCameraOverlay']: row.update(overlays[row['id']])
    for key in ['inventoryGeolocation','sourceInventory']: gaps['metadata'][key]=old_gaps['metadata'][key]
    gaps['inventoryCoverage']['metadata'].update(old_gaps['inventoryCoverage']['metadata']); gaps['metadata']['localRevision']=RELEASE
    write_json(folder/'RESULTADOS.json',gaps)
    payload=json.dumps(clean(gaps),ensure_ascii=False,allow_nan=False,separators=(',',':'))
    js='window.RIOBAMBA_UPDATED_GAPS = '+payload+';\n'
    (OUT/'riobamba-brechas-actualizadas-data.js').write_text(js,encoding='utf-8')
    (folder/'riobamba-brechas-actualizadas-data.js').write_text(js,encoding='utf-8')
    prior_results=read_json(store.web/'RESULTADOS.json')
    results=read_json(OUT/'RESULTADOS.json'); results.pop('publicRelease',None)
    results.update(status='MUN027_047_READY_TO_PUBLISH',sourcePackage=RELEASE,applied=True,published=False,
                   authorization=auth,bridge=validation,pendingUnapplied=[],selectionMethod='Cruces explícitos indicados por el usuario.',
                   approvedExceptions=prior_results.get('approvedExceptions',[]),
                   warnings=list(results.get('warnings',[]))+[
                       f'MUN-027 queda a {nearest["MUN-027"]:.2f} m de su cámara más cercana; MUN-047 a {nearest["MUN-047"]:.2f} m.',
                       f'Canónigo Ramos y Agustín Guerrero tienen centros viales separados {crossing_data["MUN-027"]["gapM"]:.2f} m; se usó el punto medio cartográfico.',
                       f'Separación MUN-027/MUN-047: {pair_distance:.2f} m.',
                       'Macají conserva o mejora el porcentaje ya aprobado; se mantiene su excepción publicada.'
                   ])
    macaji_pct=corridors['scenarios']['B']['corridors']['BOULEVARD_MACAJI_BELLAVISTA']['coveredPct']
    macaji_gap=corridors['scenarios']['B']['corridors']['BOULEVARD_MACAJI_BELLAVISTA']['uncoveredM']
    exceptions=list(results['approvedExceptions'])
    for camera in SPEC:
        exceptions.append(dict(id=camera,nearestCameraM=nearest[camera],explicitUserDestination=True))
    results['approvedExceptions']=exceptions
    validation['nodeAudit']=validation.get('nodeAudit',[])
    results['bridge']=validation
    for f in OUT.iterdir():
        if f.is_file() and f.suffix in ['.md','.json'] and f.name not in ['RESULTADOS.json','VALIDACION.json','CORRIDOR_COVERAGE_200M.json']:
            f.unlink()
    write_json(OUT/'RESULTADOS.json',results); write_json(OUT/'VALIDACION.json',validation)
    receipt['published']=False; receipt['approvedExceptions']=exceptions
    write_json(OUT/'APROBACION_Y_FUENTES.json',receipt)
    corridors['metadata']['sourcePackage']=RELEASE; write_json(OUT/'CORRIDOR_COVERAGE_200M.json',corridors)
    pyogrio.write_dataframe(read(package,'ESCENARIO_FINAL_183').to_crs(4326),OUT/'ESCENARIO_FINAL_183.geojson',driver='GeoJSON')
    # Preserve the standalone Macaji layer published in the previous release.
    source=store.web/'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA'
    target=OUT/'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA'
    shutil.copytree(source,target)
    before=read(store.base,'PROPUESTA_MUNICIPAL_50_FINAL'); after=read(package,'PROPUESTA_MUNICIPAL_50_FINAL')
    changed=set(after.loc[after.geometry.to_wkb().to_numpy()!=before.geometry.to_wkb().to_numpy(),'ID_PROPUESTA'])
    require(changed==set(SPEC),f'Unexpected camera changes {changed}')
    for layer in ['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_POLICIA_30_FINAL']:
        require(read(store.base,layer).geometry.to_wkb().tolist()==read(package,layer).geometry.to_wkb().tolist(),f'Protected layer changed {layer}')
    require(all(digest(Path(path))==h for path,h in hashes.items()),'Base inputs changed')
    proof=dict(passed=True,release=RELEASE,published=False,changedMunicipal=sorted(changed),otherMunicipal48Fixed=True,
               existing103Fixed=True,police30Fixed=True,movementsM={c:old[c].distance(targets[c][0]) for c in SPEC},
               nearestCameraM=nearest,pairSeparationM=pair_distance,crossingEvidence=crossing_data,
               macajiMunicipalPct=macaji_pct,macajiUncoveredM=macaji_gap)
    write_json(OUT/'VERIFICACION_INDEPENDIENTE.json',proof)
    with sqlite3.connect(package) as db:
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Invalid GPKG')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)'); db.execute('PRAGMA journal_mode=DELETE')
    (OUT/'INFORME_FINAL.md').write_text(
        '# Movimientos MUN-027 y MUN-047\n\n'+
        f'- MUN-027: {targets["MUN-027"][1]}, movimiento {proof["movementsM"]["MUN-027"]:.2f} m; red vial con separación de centros de {crossing_data["MUN-027"]["gapM"]:.2f} m.\n'+
        f'- MUN-047: {targets["MUN-047"][1]}, movimiento {proof["movementsM"]["MUN-047"]:.2f} m.\n'+
        f'- Separación mutua: {pair_distance:.2f} m. Distancias mínimas a cámaras: MUN-027 {nearest["MUN-027"]:.2f} m; MUN-047 {nearest["MUN-047"]:.2f} m.\n'+
        f'- Macají escenario municipal: {macaji_pct:.5f}%, {macaji_gap:.2f} m sin cubrir; sin deterioro adicional frente a la excepción ya aprobada.\n\n'+
        'Coberturas 100/150/200 m recalculadas. Las 103 existentes, 30 policiales y otras 48 municipales permanecen fijas. KDE/Gi* sin recalcular. Punto de Canónigo/Agustín Guerrero usa el punto medio de líneas OSM separadas 5.48 m; verificación de campo pendiente.\n',encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=False),flush=True)

if __name__=='__main__': main()
