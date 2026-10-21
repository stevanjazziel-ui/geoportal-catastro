"""Build the camera scenario explicitly reviewed and approved for publication."""
import json
import shutil
import sqlite3
import sys
import zipfile
from collections import Counter
from pathlib import Path

import pyogrio
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'sig-bridge'), str(ROOT / 'tools')]
from bridge.store import Store, clean, digest, now, read_json, require, write_json
from bridge.engine import calculate, verify_derived
from build_police_camera_proposal import UNPROJECT
import recalculate_current_gaps as gaps_adapter

RELEASE = 'MACAJI_COMPENSACION_021_043_20261021'
OUT = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE
APPROVED = Path(r'D:\codex\entregas\MACAJI_COMPENSACION_MUN021_043_20261021')
SOURCE_PACKAGE = APPROVED / 'MACAJI_BELLAVISTA_ESPEJO_PRIMERA.gpkg'
EXPECTED_MOVED = {'MUN-021','MUN-029','MUN-030','MUN-033','MUN-035','MUN-037',
                  'MUN-038','MUN-040','MUN-041','MUN-042','MUN-043'}
AUTHORIZATION = 'Usuario confirma los movimientos de MUN-021/MUN-043 y solicita: publica para ver los resultados. MUN-028 y MUN-047 fijas.'


def read(path, layer):
    return pyogrio.read_dataframe(path, layer=layer).to_crs(32717)


def main():
    resume = '--resume' in sys.argv
    require(not OUT.exists() or resume, 'La entrega ya existe; no sobrescribir el historial')
    store = Store(ROOT)
    if resume and store.web.name == RELEASE:
        store.web = ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/MUN045_CRUCE_PRENSA_9OCTUBRE_20261019'
        store.base = store.web/'ESCENARIO_FINAL_183.gpkg'
    require(store.web.name == 'MUN045_CRUCE_PRENSA_9OCTUBRE_20261019', 'La base publicada cambio')
    approved = read(SOURCE_PACKAGE, 'MUNICIPALES_50_CONTINUIDAD').set_index('ID_PROPUESTA')
    municipal_before = read(store.base, 'PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    require(len(approved) == 50 and approved.index.is_unique, 'Se requieren 50 municipales unicas')
    require(set(approved.index) == set(municipal_before.index), 'Se alteraron los IDs')
    changed = {key for key in approved.index if approved.loc[key].geometry.wkb != municipal_before.loc[key].geometry.wkb}
    require(changed == EXPECTED_MOVED, 'Los movimientos no coinciden con el escenario aprobado')
    for key in ('MUN-028','MUN-047'):
        require(approved.loc[key].geometry.wkb == municipal_before.loc[key].geometry.wkb, 'Camara protegida movida: '+key)
    require(approved.loc['MUN-021'].geometry.wkb == municipal_before.loc['MUN-040'].geometry.wkb, 'Destino MUN-021 incorrecto')
    require(approved.loc['MUN-043'].geometry.wkb == municipal_before.loc['MUN-041'].geometry.wkb, 'Destino MUN-043 incorrecto')
    protected = {str(path):digest(path) for path in (store.base,SOURCE_PACKAGE,ROOT/'riobamba-kde-combinado-data.js')}
    manual, changes = {}, []
    for key,spec in store.config['layers'].items():
        frame = read(store.base,spec['source'])
        if 'OBSERVACION_MANUAL' not in frame:
            frame['OBSERVACION_MANUAL'] = ''
        if key == 'municipal':
            for index,row in frame.iterrows():
                camera = row.ID_PROPUESTA
                if camera not in changed:
                    continue
                point = approved.loc[camera].geometry
                frame.at[index,'geometry'] = point
                note = 'Posicion revisada en propuesta Macaji-Bellavista; '+AUTHORIZATION
                frame.at[index,'OBSERVACION_MANUAL'] = note
                changes.append(dict(layer='municipal',id=camera,geometryChanged=True,fields=[],
                    distanceM=row.geometry.distance(point),note=note))
        manual[key] = frame
    receipt = dict(revision=RELEASE,createdAt=now(),priorRelease=store.web.name,
        authorization=AUTHORIZATION,baseHashes=protected,approvedPackageSha256=digest(SOURCE_PACKAGE),
        changes=changes,protectedMunicipal=['MUN-028','MUN-047'],
        ruralException={'id':'MUN-021','priorParish':'Lican','priorFunction':'ENTRADA','newGroup':'RED_ESTRUCTURAL'})

    def approved_positions(_store,_changes,points,_police,_urban):
        rows = []
        for point,props in points:
            key = props['ID_PROPUESTA']
            if key not in changed:
                continue
            expected = approved.loc[key]
            require(point.wkb == expected.geometry.wkb, 'Posicion distinta a la aprobada: '+key)
            direction = (str(expected.DIRECCION) if key in ('MUN-021','MUN-043')
                         else 'Eje Macaji-Bellavista; ubicacion propuesta revisada')
            if key == 'MUN-041':
                direction = 'Eugenio Espejo x Primera Constituyente'
            props.update(DIRECCION=direction,INTERSECCION_O_NODO=direction,
                BRIDGE_NODO_VALIDADO=key in ('MUN-021','MUN-043','MUN-041'),
                ESTADO_REVISION='POSICION_CONFIRMADA_USUARIO_20261021',
                FUENTE_CRUCE='Paquete QGIS revisado y confirmado. Posicion de proyecto; no verificacion de poste.',
                DECISION_FINAL='PUBLICAR_ESCENARIO_CONFIRMADO_USUARIO')
            if key == 'MUN-021':
                props.update(GRUPO='RED_ESTRUCTURAL',PARROQUIA=None,FUNCION='RESPALDO_CRUCE_REUBICADO',
                    OBSERVACION_MANUAL='Traslado autorizado desde entrada de Lican para sustituir MUN-040 en Esmeraldas x Eugenio Espejo.')
            rows.append(dict(id=key,passed=True,approvedCoordinates=True,
                cartographicNodeValidated=props['BRIDGE_NODO_VALIDADO'],fieldVerified=False,roads=[direction]))
        require(len(rows) == 11, 'Falta un movimiento aprobado')
        return rows, []

    if not resume:
        OUT.mkdir(parents=True)
        print('Recalculando coberturas y resultados de los escenarios B/C...',flush=True)
        validation = calculate(store,OUT,OUT,manual,receipt,node_validator=approved_positions)
    else:
        validation = read_json(OUT/'VALIDACION.json')
    segment = store.web/'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA'
    require(segment.is_dir(), 'Falta el tramo independiente de Macaji-Bellavista')
    if not (OUT/segment.name).exists():
        shutil.copytree(segment, OUT/segment.name)
    package = OUT / 'ESCENARIO_FINAL_183.gpkg'
    actual = read(package,'PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    require(set(actual.index) == set(approved.index), 'Inventario municipal distinto')
    require(all(actual.loc[key].geometry.wkb == approved.loc[key].geometry.wkb for key in actual.index), 'Hay ubicaciones distintas a la propuesta')
    require(Counter(actual.GRUPO) == {'CABECERA_RURAL':21,'LAS_ABRAS':4,'RED_ESTRUCTURAL':25}, 'La excepcion de Lican no coincide')
    for name,count in [('CAMARAS_EXISTENTES_103_FINAL',103),('PROPUESTA_POLICIA_30_FINAL',30),('UPC_INFRAESTRUCTURA',18)]:
        old,new = read(store.base,name),read(package,name)
        require(len(new)==count and old.geometry.to_wkb().tolist()==new.geometry.to_wkb().tolist(),'Cambio inesperado: '+name)
    print('Actualizando brechas y dependencias del visor...',flush=True)
    folder = OUT/'coverage-inputs'
    if not (resume and (folder/'RESULTADOS.json').exists()):
        folder.mkdir(exist_ok=resume)
        gaps_adapter.main(final=package,out=folder,js_output=OUT/'riobamba-brechas-actualizadas-data.js',expected_replacements=30)
    gaps = read_json(folder/'RESULTADOS.json')
    prior_path = store.web/'coverage-inputs/RESULTADOS.json'
    if prior_path.exists():
        prior_gaps = read_json(prior_path)
    else:
        script = (store.web/'riobamba-brechas-actualizadas-data.js').read_text(encoding='utf-8')
        prior_gaps, _ = json.JSONDecoder().raw_decode(script.partition('=')[2].lstrip())
    overlay = {row['id']:row for row in prior_gaps['inventoryCameraOverlay']}
    for row in gaps['inventoryCameraOverlay']:
        row.update(overlay[row['id']])
    for key in ('inventoryGeolocation','sourceInventory'):
        gaps['metadata'][key] = prior_gaps['metadata'][key]
    gaps['inventoryCoverage']['metadata'].update(prior_gaps['inventoryCoverage']['metadata'])
    gaps['metadata']['localRevision'] = RELEASE
    write_json(folder/'RESULTADOS.json',gaps)
    javascript = 'window.RIOBAMBA_UPDATED_GAPS = '+json.dumps(clean(gaps),ensure_ascii=False,allow_nan=False,separators=(',',':'))+';\n'
    (OUT/'riobamba-brechas-actualizadas-data.js').write_text(javascript,encoding='utf-8')
    (folder/'riobamba-brechas-actualizadas-data.js').write_text(javascript,encoding='utf-8')
    pyogrio.write_dataframe(read(package,'ESCENARIO_FINAL_183').to_crs(4326),OUT/'ESCENARIO_FINAL_183.geojson',driver='GeoJSON')
    audit_dir = OUT/'AUDITORIA_DIRECCIONAL'
    audit_dir.mkdir(exist_ok=resume)
    for name in ('AUDITORIA_IMPACTO.json','IMPACTO_POR_CAMARA.csv','IMPACTO_ANTES_DESPUES.png','IMPACTO_REUBICACIONES.gpkg'):
        shutil.copy2(APPROVED/'AUDITORIA'/name,audit_dir/name)
    for src,name in [('COMPARAR_COMPENSACION.html','index.html'),('COMPENSACION_MUN021_043.png','PROPUESTA.png'),
                     ('COMPENSACION.json','COMPENSACION.json')]:
        shutil.copy2(APPROVED/src,OUT/name)
    shutil.copy2(APPROVED/'REVISAR_COMPENSACION_021_043.qgs',OUT/'REVISAR_PROPUESTA.qgs')
    # The review project is packaged with the exact database basename it references.
    shutil.copy2(SOURCE_PACKAGE,OUT/SOURCE_PACKAGE.name)
    summary = read_json(OUT/'RESULTADOS.json')
    warnings = ['Coberturas potenciales de proximidad a 200 m; no certifican vision optica.',
        'Se conservan las 103 existentes, las 30 policiales y las 18 UPC; MUN-028 y MUN-047 permanecen fijas.',
        'MUN-021 trasladada desde la entrada de Lican por instruccion expresa. MUN-043 trasladada desde Milton Reyes.',
        'La auditoria direccional registra perdidas en los origenes; consultar AUDITORIA_DIRECCIONAL.',
        'La cobertura longitudinal teorica del tramo no equivale a visibilidad comprobada ni a la cobertura del conjunto de bulevares.']
    summary.update(status='ESCENARIO_CONFIRMADO_USUARIO_PARA_PUBLICACION',sourcePackage=RELEASE,
        applied=True,published=True,publicRelease=RELEASE,authorization=AUTHORIZATION,selectionMethod='Coordenadas exactas del escenario revisado; sin optimizacion adicional.',
        warnings=warnings,approvedExceptions=receipt['ruralException'])
    for key in ('anilloBStudy','boyacaStudy'):
        summary.pop(key,None)
    write_json(OUT/'RESULTADOS.json',summary)
    corridor = read_json(OUT/'CORRIDOR_COVERAGE_200M.json')
    corridor['metadata']['sourcePackage']=RELEASE
    write_json(OUT/'CORRIDOR_COVERAGE_200M.json',corridor)
    for name in ('APROBACION_ANTERIOR_MUN027_047.json','VERIFICACION_INDEPENDIENTE.json','MOVIMIENTOS_MUNICIPALES.csv'):
        (OUT/name).unlink(missing_ok=True)
    proof=dict(passed=True,changedMunicipal=sorted(changed),municipalCount=50,existing103Fixed=True,
        police30Fixed=True,upc18Fixed=True,fixedMunicipal=['MUN-028','MUN-047'],
        groupComposition=dict(Counter(actual.GRUPO)),approvedPositionsExact=True,
        evaluationStatus=validation['status'],remainingReviewItems=validation['publishBlocks'])
    write_json(OUT/'VERIFICACION_INDEPENDIENTE.json',proof)
    write_json(OUT/'APROBACION_Y_FUENTES.json',{**receipt,'applied':True,'publicationRequested':True,'verification':proof})
    (OUT/'INFORME_FINAL.md').write_text('# Macaji-Bellavista: escenario confirmado\n\n'+AUTHORIZATION+'\n\n'+
        '\n'.join('- '+warning for warning in warnings)+'\n\nMovimientos: '+', '.join(sorted(changed))+'.\n',encoding='utf-8')
    verify_derived(store,package,summary)
    require(all(digest(Path(path))==value for path,value in protected.items()),'Se modificaron fuentes')
    with sqlite3.connect(package) as db:
        require(db.execute('pragma integrity_check').fetchone()[0]=='ok','GeoPackage invalido')
    with zipfile.ZipFile(OUT/'ENTREGA_POLICIA_KDE.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.rglob('*')):
            if path.is_file() and path.suffix not in ('.zip',):
                archive.write(path,path.relative_to(OUT).as_posix())
    write_json(ROOT/'sig-bridge-active.json',{'schemaVersion':1,'root':'./'+OUT.relative_to(ROOT).as_posix()+'/',
        'releaseId':RELEASE,'coverageData':'riobamba-brechas-actualizadas-data.js'})
    print(json.dumps(proof,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
