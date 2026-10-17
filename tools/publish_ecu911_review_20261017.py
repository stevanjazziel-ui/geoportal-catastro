"""Publish the approved 103-camera revision without moving the other 80 proposals."""
import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sig-bridge'))
from bridge.engine import calculate, verify_derived
from bridge.store import Store, clean, digest, now, read_json, require, write_json
from import_final_existing_inventory import normalize
import recalculate_current_gaps as dependencies

RELEASE = 'ECU911_74_INTACTAS_29_REVISADAS_20261017'
OUT = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE
REVIEW = Path('D:/codex/entregas/REVISION_ECU911_29_20261017')
CANDIDATE = Path('D:/codex/entregas/RIO084_CANDIDATO_SALIDA_MACAS_20261017/RIO084_SALIDA_MACAS_CANDIDATO.gpkg')
AUTHORIZATION = 'Usuario: mueve y publica todo. RIO-084 en empalme Juan Felix Proano / Via Riobamba-Macas; revision previa de 103, con 74 documentadas inmodificables.'


def build():
    require(not OUT.exists(), 'No sobrescribir una entrega existente')
    store = Store()
    base = store.base
    old = gpd.read_file(base, layer='CAMARAS_EXISTENTES_103_FINAL')
    original = gpd.read_file(REVIEW / 'ORIGINALES/CAMARAS_103_PARA_CODEX.gpkg')
    incoming = gpd.read_file(REVIEW / 'ECU911_103_REVISION_NO_PUBLICADA.gpkg', layer='CAMARAS_103_CONSOLIDADAS_REVISION')
    for field in ('X_PROP', 'Y_PROP', 'DESPLAZ_M'):
        incoming[field] = pd.to_numeric(incoming[field], errors='raise')
    candidate = gpd.read_file(CANDIDATE, layer='CANDIDATO_NO_INCORPORADO').iloc[0]
    idx = incoming.index[incoming.BASE_ID.eq('RIO-084')][0]
    require(incoming.at[idx, 'ESTADO_XY'] == 'PROVISIONAL', 'No se puede mover una documentada')
    incoming.at[idx, 'geometry'] = candidate.geometry
    for field, value in {'DECISION':'CRUCE_APROBADO_POR_USUARIO', 'X_PROP':candidate.geometry.x,
                         'Y_PROP':candidate.geometry.y, 'DESPLAZ_M':candidate.DIST_ANT_M,
                         'CONF_REVISION':'MEDIA_CARTOGRAFICA_NO_CAMPO', 'FUENTE_PROP':'OSM',
                         'EVIDENCIA':'Empalme con vertice OSM compartido Juan Felix Proano / Via Riobamba-Macas. Ubicacion aprobada por usuario. No verifica poste fisico.'}.items():
        incoming.at[idx, field] = value
    locked = incoming.ESTADO_XY.eq('DOCUMENTADA')
    require(int(locked.sum()) == 74, 'Se requieren 74 protegidas')
    require(incoming.loc[locked].geometry.to_wkb().tolist() == original.loc[locked].geometry.to_wkb().tolist(), '74 geometrias alteradas')
    inventory, comparison = normalize(incoming, old, confirmed=True)
    original_by_id = original.set_index('ID')
    before_by_id = old.set_index('ID_CAMARA')
    unproject = Transformer.from_crs(32717, 4326, always_xy=True)
    for i, row in inventory.iterrows():
        protected = row.ESTADO_XY == 'DOCUMENTADA'
        pending = row.DECISION == 'PENDIENTE_CONSERVA_PROVISIONAL'
        geo_state = 'DOCUMENTADA_INMODIFICABLE' if protected else ('PENDIENTE_VALIDACION' if pending else 'CRUCE_CARTOGRAFICO_APROBADO')
        inventory.at[i, 'ESTADO_GEO'] = geo_state
        inventory.at[i, 'METODO_GEO'] = 'COORDENADA_DOCUMENTADA_ORIGINAL' if protected else ('PROVISIONAL_SIN_CONFIRMAR' if pending else 'INTERSECCION_VIAL_REVISADA_APROBADA')
        inventory.at[i, 'CONFIANZA_GEO'] = 'DOCUMENTADA_ORIGINAL' if protected else ('INSUFICIENTE' if pending else 'MEDIA_CARTOGRAFICA_NO_CAMPO')
        inventory.at[i, 'OBSERVACION_GEO'] = row.EVIDENCIA
        inventory.at[i, 'AVISO_GEO'] = row.EVIDENCIA
        inventory.at[i, 'DIRECCION'] = row.DIR_DEPURADA
        inventory.at[i, 'X_UTM'], inventory.at[i, 'Y_UTM'] = row.geometry.x, row.geometry.y
        inventory.at[i, 'DESPLAZ_RESPECTO_ZIP_M'] = row.geometry.distance(original_by_id.loc[row.ID].geometry)
        inventory.at[i, 'DESPLAZ_RESPECTO_PUBLICADO_M'] = row.geometry.distance(before_by_id.loc[row.ID].geometry)
        inventory.at[i, 'FUENTE_INVENTARIO'] = 'ECU911_RIOBAMBA_103_FINAL_CODEX_20261017.zip'
    pending_ids = inventory.loc[inventory.ESTADO_GEO.eq('PENDIENTE_VALIDACION'), 'ID_CAMARA'].tolist()
    require(len(pending_ids) == 19, 'Se requieren 19 pendientes conservadas')
    moved_from_zip = inventory.loc[inventory.DESPLAZ_RESPECTO_ZIP_M.gt(1e-8), 'ID_CAMARA'].tolist()
    require(set(moved_from_zip) == {'RIO-084-DOMO', 'RIO-085-DOMO', 'RIO-099-DOMO', 'RIO-100-FIJA'}, 'Cambios fuera de alcance')
    protected_paths = [base, REVIEW / 'ORIGINALES/CAMARAS_103_PARA_CODEX.gpkg',
                       REVIEW / 'ECU911_103_REVISION_NO_PUBLICADA.gpkg', CANDIDATE]
    protected_paths += [ROOT / n for n in ('riobamba-hotspot-urbano-200m-data.js', 'riobamba-conflictividad-data.js',
        'riobamba-seguridad-kde-validacion-data.js', 'riobamba-cantonal-data.js', 'visor-seguridad-riobamba-data.js')]
    hashes = {str(p):digest(p) for p in protected_paths}
    OUT.mkdir(parents=True)
    manual = {}
    for key, spec in store.config['layers'].items():
        frame = gpd.read_file(base, layer=spec['source'])
        if 'OBSERVACION_MANUAL' not in frame:
            frame['OBSERVACION_MANUAL'] = ''
        manual[key] = frame
    prior = read_json(store.web / 'VALIDACION.json')
    def fixed_nodes(_store, changes, municipal, police, urban):
        require(not changes, 'No se reubican propuestas')
        return prior.get('nodeAudit', []), []
    receipt = {'revision': RELEASE, 'changes': [], 'baseHashes': hashes, 'createdAt': now(),
               'authorization': AUTHORIZATION, 'priorRelease':store.web.name,
               'fixed74Source':str(REVIEW / 'ORIGINALES/CAMARAS_103_PARA_CODEX.gpkg')}
    print('Recalculando cobertura 200m de A/B/C con 103 ubicaciones, 19 provisionales explicitadas', flush=True)
    validation = calculate(store, OUT, OUT, manual, receipt, existing_override=inventory, node_validator=fixed_nodes)
    require(not validation['publishBlocks'], str(validation['publishBlocks']))
    package = OUT / 'ESCENARIO_FINAL_183.gpkg'
    print('Recalculando dependencias metricas de 100/150/200m', flush=True)
    folder = OUT / 'coverage-inputs'
    folder.mkdir()
    dependencies.main(final=package, out=folder, js_output=OUT/'riobamba-brechas-actualizadas-data.js', expected_replacements=30)
    gaps = read_json(folder/'RESULTADOS.json')
    by_id = inventory.set_index('ID_CAMARA')
    for camera in gaps['inventoryCameraOverlay']:
        row = by_id.loc[camera['id']]
        camera.update(sourcePackage='ECU911_RIOBAMBA_103_FINAL_CODEX_20261017.zip',
            sourceMember='CAMARAS_103_PARA_CODEX.gpkg', source='Inventario ECU911 revisado; 74 documentadas intactas',
            coordinateSource=row.FUENTE_INVENTARIO, confidence=row.CONFIANZA_GEO,
            method=row.METODO_GEO, geoObservation=row.OBSERVACION_GEO, geoStatus=row.ESTADO_GEO,
            requiresChange=bool(row.REQUIERE_CAMBIO), studyCamera=bool(row.REQUIERE_CAMBIO),
            provisional=row.ESTADO_GEO == 'PENDIENTE_VALIDACION', ambitoEstudio='MUNICIPAL')
    quality = {'documentedUnchanged':74, 'reviewedApprovedIntersections':10, 'pendingValidation':19,
               'pendingIds':pending_ids, 'coverageIncludesProvisionalPositions':True,
               'warning':'Cobertura potencial estimada con 103 posiciones, incluidas 19 provisionales pendientes. No certifica ubicacion fisica ni vision efectiva.'}
    gaps['metadata']['inventoryGeolocation'] = quality
    gaps['metadata']['sourceInventory'] = {'package':'ECU911_RIOBAMBA_103_FINAL_CODEX_20261017.zip',
        'sha256':digest(Path('C:/Users/PC/Downloads/ECU911_RIOBAMBA_103_FINAL_CODEX_20261017.zip')),
        'replacementField':'ACTUALIZ', 'confirmedReplacement':30, **quality}
    gaps['inventoryCoverage']['metadata'].update(geolocationQuality=quality, provisionalIds=pending_ids,
        coverageIncludesProvisionalPositions=True)
    text = json.dumps(clean(gaps), ensure_ascii=False, allow_nan=False, separators=(',',':'))
    (folder/'RESULTADOS.json').write_text(text, encoding='utf-8')
    (OUT/'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = '+text+';\n', encoding='utf-8')
    results = read_json(OUT/'RESULTADOS.json')
    results.update(status='ECU911_REVISION_APROBADA_74_INTACTAS_19_PENDIENTES', sourcePackage=RELEASE,
        authorization=AUTHORIZATION, inventoryGeolocation=quality,
        counts={'existing':103,'changeIncluded':30,'municipal':50,'police':30},
        warnings=[quality['warning'], 'Las 50 municipales y 30 policiales permanecen en sus coordenadas publicadas. KDE y Gi* sin recalculo.'])
    validation.update(status='PASS_WITH_EXPLICIT_PROVISIONAL_POSITIONS', authorization=AUTHORIZATION,
        inventoryGeolocation=quality, original74GeometriesUnchanged=True, proposals80Unmoved=True,
        movedComparedToIncomingZip=moved_from_zip, sourceHashes=hashes)
    results['bridge'] = validation
    write_json(OUT/'RESULTADOS.json', results)
    write_json(OUT/'VALIDACION.json', validation)
    write_json(OUT/'APROBACION_Y_FUENTES.json', receipt)
    comparison['DESPLAZ_RESPECTO_ZIP_M'] = inventory.DESPLAZ_RESPECTO_ZIP_M
    comparison['ESTADO_GEO'] = inventory.ESTADO_GEO
    comparison.to_csv(OUT/'COMPARACION_INVENTARIO.csv', index=False, encoding='utf-8-sig')
    inventory.drop(columns='geometry').to_csv(OUT/'REVISION_103_COORDENADAS.csv', index=False, encoding='utf-8-sig')
    shutil.copy2(REVIEW/'CONTROL_74_INMODIFICABLES.csv', OUT/'CONTROL_74_INMODIFICABLES.csv')
    corridor = read_json(OUT/'CORRIDOR_COVERAGE_200M.json')
    corridor['metadata'].update(sourcePackage=RELEASE, inventoryGeolocation=quality)
    write_json(OUT/'CORRIDOR_COVERAGE_200M.json', corridor)
    before_results = read_json(store.web/'RESULTADOS.json')
    write_json(OUT/'COMPARACION_COBERTURAS.json', {k:{'before':before_results[k],'after':results[k]}
               for k in ('territorial','population','incidents','hotspots','corridors')})
    # Never present copied receipts for the previous municipal revision as current validation.
    for name in ('VALIDACION_CORRECCIONES_400M.json','VALIDACION_ESTADOS.json','VALIDACION_INDEPENDIENTE.json','VERIFICACION_INDEPENDIENTE.json'):
        path = OUT/name
        if path.exists():
            path.rename(OUT/('HISTORICO_'+name))
    (OUT/'INFORME_FINAL.md').write_text('# Inventario ECU911 aprobado\n\n'
        '103 equipos: 74 documentados intactos; 10 cruces revisados/aprobados cartograficamente; 19 pendientes que conservan su posicion provisional. '
        '30 para cambio incluidos en las 103; 73 sin cambio requerido.\n\n'
        'Cuatro movimientos respecto al ZIP recibido: RIO-084, RIO-085, RIO-099 y RIO-100. Las 74 documentadas no se ajustan a vias ni cambian geometria. '
        'RIO-099/100 mantienen IDs separados en un mismo cruce, sin duplicar registros. RIO-084 en el nodo compartido de Juan Felix Proano y Via Riobamba-Macas, '
        'aprobado por usuario: no constituye verificacion fisica del poste.\n\n'
        +quality['warning']+'\n\n'
        '50 municipales y 30 policiales conservadas. Metodo de buffers, percentiles, interseccion estricta, Gi* y KDE no cambian. '
        'Se recalculan coberturas e indicadores dependientes 100/150/200m. Los nombres de campos originales de validacion se preservan como antecedentes; '
        'ESTADO_GEO, CONFIANZA_GEO y OBSERVACION_GEO describen el estado actual.\n', encoding='utf-8')
    print('Validando 74 protegidas, 19 pendientes, 80 propuestas fijas y Gi*', flush=True)
    verify_derived(store, package, results, existing_override=inventory)
    reread = gpd.read_file(package, layer='CAMARAS_EXISTENTES_103_FINAL').set_index('ID_CAMARA')
    for row in original.loc[original.ESTADO_XY.eq('DOCUMENTADA')].itertuples():
        require(reread.loc[row.ID].geometry.wkb == row.geometry.wkb, row.ID+' documentada alterada')
    for id in pending_ids:
        require(reread.loc[id].geometry.wkb == original_by_id.loc[id].geometry.wkb, id+' pendiente alterada')
    for name, id_field in [('PROPUESTA_MUNICIPAL_50_FINAL','ID_PROPUESTA'),('PROPUESTA_POLICIA_30_FINAL','ID_POLICIA')]:
        before = gpd.read_file(base, layer=name).set_index(id_field)
        after = gpd.read_file(package, layer=name).set_index(id_field).loc[before.index]
        require(before.geometry.to_wkb().tolist() == after.geometry.to_wkb().tolist(), 'Propuestas movidas')
    for radius in (100,150,200):
        expected = unary_union([p.buffer(radius,quad_segs=64) for p in inventory.geometry])
        from shapely.geometry import shape
        from shapely.ops import transform
        metric = Transformer.from_crs(4326,32717,always_xy=True).transform
        web = transform(metric, shape(gaps['inventoryCoverage']['scenarios'][str(radius)]['coverage']['geometry']))
        require(expected.symmetric_difference(web).area < .02, 'Radio incorrecto')
    require(all(digest(Path(p)) == value for p,value in hashes.items()), 'Cambio de fuente')
    proof = {'passed':True, 'original74WkbIdentical':True, 'all19PendingUnmoved':True,
        'uniqueIds':103, 'replacementCount':30, 'proposals80Unmoved':True,
        'giGeometryStatisticsUnchanged':True, 'kdeSourceHashesUnchanged':True,
        'radiiValidatedM':[100,150,200], 'sourcePackageSha256':digest(package),
        'rio084WkbMatchesApprovedNode':reread.loc['RIO-084-DOMO'].geometry.wkb == candidate.geometry.wkb}
    require(proof['rio084WkbMatchesApprovedNode'], 'RIO084 no coincide')
    write_json(OUT/'VERIFICACION_INDEPENDIENTE.json', proof)
    for folder,name in [(folder,'BRECHAS_ACTUALIZADAS.zip'),(OUT,'ENTREGA_POLICIA_KDE.zip')]:
        with zipfile.ZipFile(folder/name,'w',zipfile.ZIP_DEFLATED) as z:
            for path in sorted(folder.iterdir()):
                if path.is_file() and path.suffix != '.zip':
                    z.write(path,path.name)
    print(json.dumps({'release':RELEASE,'quality':quality,'corridorsB':[r for r in results['corridors'] if r['ESCENARIO']=='B']}, ensure_ascii=True), flush=True)


def activate():
    proof = read_json(OUT/'VERIFICACION_INDEPENDIENTE.json')
    require(proof['passed'] and proof['original74WkbIdentical'], 'No hay validacion')
    write_json(ROOT/'sig-bridge-active.json', {'schemaVersion':1,
        'root':'./data/seguridad-riobamba/SIG_BRIDGE_RELEASES/'+RELEASE+'/',
        'releaseId':RELEASE,'coverageData':'riobamba-brechas-actualizadas-data.js'})
    print('Registro local activado: '+RELEASE)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--activate-only', action='store_true')
    args = parser.parse_args()
    activate() if args.activate_only else build()
