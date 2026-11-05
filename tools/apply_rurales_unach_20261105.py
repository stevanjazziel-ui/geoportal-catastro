"""Apply the six rural COP requests and the three explicitly approved UNACH transfers."""
import json
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

import pyogrio
from shapely.geometry import Point
from shapely.ops import transform
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'sig-bridge'), str(ROOT / 'tools')]
from bridge.store import Store, clean, digest, now, read_json, require, write_json
from bridge.engine import calculate, verify_derived
import recalculate_current_gaps as gaps_adapter

RELEASE = 'RURALES_COP_UNACH_20261105'
BASELINE = 'MUN036_JACINTO_UNIDAD_NACIONAL_20261021'
OUT = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE
SOURCE = ROOT.parent / 'entregas/COMPARACION_CAMARAS_COP'
RURAL = {'MUN-003', 'MUN-008', 'MUN-013', 'MUN-017', 'MUN-019', 'MUN-020'}
UNACH = {'MUN-004', 'MUN-016', 'MUN-022'}
AUTHORIZATION = ('Usuario solicita aplicar los movimientos rurales de Operaciones, trasladar tres municipales '
    'a los puntos marcados junto a la UNACH y publicar. MUN-022 sustituye MUN-019 para conservar '
    'la solicitud de Colegio Milton Reyes. Se acepta perdida de cobertura en los origenes rurales.')
PROJECT = Transformer.from_crs(4326, 32717, always_xy=True).transform

def read(path, layer):
    return pyogrio.read_dataframe(path, layer=layer).to_crs(32717)

def main():
    store = Store(ROOT)
    require(store.web.name == BASELINE, 'La base activa cambio')
    resume = '--resume' in sys.argv
    require(not OUT.exists() or resume, 'No sobrescribir una revision')
    cop = read_json(SOURCE / 'comparacion.json')
    targets = {}
    for row in cop['records']:
        if row['id'] in RURAL:
            require(row['inferred'] is not None, 'Falta destino rural')
            targets[row['id']] = dict(coordinates=row['inferred'], address=row['suggestion'],
                method=row['destinationMethod'], source=row['destinationSource'], role='RURAL_COP')
    for row in read_json(SOURCE / 'TRASLADO_TRES_UNACH/MOVIMIENTOS_UNACH.json')['targets']:
        require(row['id'] in UNACH, 'Donante UNACH incorrecto')
        targets[row['id']] = dict(coordinates=row['coordinates'], address=row['label'], method=row['method'],
            source='https://www.openstreetmap.org/way/' + row['osmWay'], role='UNACH')
    require(set(targets) == RURAL | UNACH, 'Se requieren exactamente nueve destinos')
    require(not RURAL.intersection(UNACH), 'Solicitudes incompatibles')
    projected = {key: transform(PROJECT, Point(value['coordinates'])) for key, value in targets.items()}
    before = read(store.base, 'PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    protected = {str(p): digest(p) for p in (store.base, ROOT / 'riobamba-kde-combinado-data.js')}
    manual, changes = {}, []
    for key, spec in store.config['layers'].items():
        frame = read(store.base, spec['source'])
        if 'OBSERVACION_MANUAL' not in frame:
            frame['OBSERVACION_MANUAL'] = ''
        if key == 'municipal':
            for camera, point in projected.items():
                index = frame.index[frame.ID_PROPUESTA.eq(camera)][0]
                frame.at[index, 'geometry'] = point
                note = 'Destino autorizado por el usuario: ' + targets[camera]['address']
                frame.at[index, 'OBSERVACION_MANUAL'] = note
                changes.append(dict(layer='municipal', id=camera, geometryChanged=True, fields=[],
                    distanceM=before.loc[camera].geometry.distance(point), note=note))
        manual[key] = frame
    receipt = dict(revision=RELEASE, createdAt=now(), priorRelease=BASELINE,
        authorization=AUTHORIZATION, baseHashes=protected, changes=changes, targets=targets)

    def validate(_store, _changes, municipal, _police, _urban):
        audit = []
        for point, props in municipal:
            camera = props['ID_PROPUESTA']
            if camera not in targets:
                continue
            t = targets[camera]
            require(point.wkb == projected[camera].wkb, 'Destino distinto al autorizado')
            props.update(DIRECCION=t['address'], INTERSECCION_O_NODO=t['address'],
                BRIDGE_NODO_VALIDADO=False, ESTADO_REVISION='DESTINO_AUTORIZADO_USUARIO',
                FUENTE_CRUCE=t['method'], COORDENADAS_USUARIO_ANTES_CONSERVADAS=False,
                DESTINO_REVISION=t['role'])
            if camera in UNACH:
                props.update(GRUPO='RED_ESTRUCTURAL', PARROQUIA='Riobamba', FUNCION='ENTORNO_UNACH')
            audit.append(dict(id=camera, passed=True, approvedCoordinates=True, fieldVerified=False,
                cartographicNodeValidated=False, roads=[t['address']], source=t['source'], method=t['method']))
        require(len(audit) == 9, 'Falta un movimiento')
        return audit, []

    if not resume:
        OUT.mkdir(parents=True)
        write_json(OUT / 'DESTINOS_Y_AUTORIZACION.json', receipt)
        print('Recalculando nueve movimientos, coberturas, poblacion y manzanas...', flush=True)
        validation = calculate(store, OUT, OUT, manual, receipt, node_validator=validate)
    else:
        validation = read_json(OUT / 'VALIDACION.json')
    require(validation['publishBlocks'] == read_json(store.web / 'VALIDACION.json')['publishBlocks'],
        'Los movimientos introducen restricciones nuevas')
    package = OUT / 'ESCENARIO_FINAL_183.gpkg'
    folder = OUT / 'coverage-inputs'
    folder.mkdir(exist_ok=True)
    if not (resume and (folder / 'RESULTADOS.json').exists()):
        print('Actualizando dependencias del visor...', flush=True)
        gaps_adapter.main(final=package, out=folder,
            js_output=OUT / 'riobamba-brechas-actualizadas-data.js', expected_replacements=30)
    gaps = read_json(folder / 'RESULTADOS.json')
    prior_gaps = read_json(store.web / 'coverage-inputs/RESULTADOS.json')
    overlay = {r['id']: r for r in prior_gaps['inventoryCameraOverlay']}
    for row in gaps['inventoryCameraOverlay']:
        row.update(overlay[row['id']])
    for key in ('inventoryGeolocation', 'sourceInventory'):
        gaps['metadata'][key] = prior_gaps['metadata'][key]
    gaps['inventoryCoverage']['metadata'].update(prior_gaps['inventoryCoverage']['metadata'])
    gaps['metadata']['localRevision'] = RELEASE
    write_json(folder / 'RESULTADOS.json', gaps)
    javascript = 'window.RIOBAMBA_UPDATED_GAPS = ' + json.dumps(clean(gaps), ensure_ascii=False, allow_nan=False, separators=(',', ':')) + ';\n'
    for path in (OUT, folder):
        (path / 'riobamba-brechas-actualizadas-data.js').write_text(javascript, encoding='utf-8')
    segment = store.web / 'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA'
    if not (OUT / segment.name).exists():
        shutil.copytree(segment, OUT / segment.name)
    pyogrio.write_dataframe(read(package, 'ESCENARIO_FINAL_183').to_crs(4326), OUT / 'ESCENARIO_FINAL_183.geojson', driver='GeoJSON')
    after = read(package, 'PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    changed = {key for key in before.index if before.loc[key].geometry.wkb != after.loc[key].geometry.wkb}
    require(changed == RURAL | UNACH and len(after) == 50, 'Cambio municipal inesperado')
    for camera, target in projected.items():
        require(after.loc[camera].geometry.wkb == target.wkb, 'Coordenada final incorrecta')
        require(after.loc[camera].DIRECCION == targets[camera]['address'], 'Direccion final incorrecta')
    for layer, count in [('CAMARAS_EXISTENTES_103_FINAL', 103), ('PROPUESTA_POLICIA_30_FINAL', 30), ('UPC_INFRAESTRUCTURA', 18)]:
        original, final = read(store.base, layer), read(package, layer)
        require(len(final) == count and original.geometry.to_wkb().tolist() == final.geometry.to_wkb().tolist(), 'Cambio protegido: ' + layer)
    require(all(digest(Path(p)) == value for p, value in protected.items()), 'Se alteraron fuentes')
    results = read_json(OUT / 'RESULTADOS.json')
    results.update(status='RURALES_COP_Y_UNACH_AUTORIZADOS', sourcePackage=RELEASE,
        publicRelease=RELEASE, applied=True, published=True, authorization=AUTHORIZATION,
        selectionMethod='Destinos rurales solicitados por Operaciones y tres puntos UNACH autorizados; sin optimizacion adicional.')
    write_json(OUT / 'RESULTADOS.json', results)
    corridors = read_json(OUT / 'CORRIDOR_COVERAGE_200M.json')
    corridors['metadata']['sourcePackage'] = RELEASE
    write_json(OUT / 'CORRIDOR_COVERAGE_200M.json', corridors)
    proof = dict(passed=True, changedMunicipal=sorted(changed), ruralCOP=sorted(RURAL), unach=sorted(UNACH),
        municipalCount=50, otherMunicipal41Fixed=True, existing103Fixed=True, police30Fixed=True,
        upc18Fixed=True, allTargetsExact=True, remainingPriorReviewItems=validation['publishBlocks'])
    write_json(OUT / 'VERIFICACION_INDEPENDIENTE.json', proof)
    write_json(OUT / 'APROBACION_Y_FUENTES.json', {**receipt, 'applied': True, 'publicationRequested': True})
    (OUT / 'INFORME_FINAL.md').write_text('# Movimientos rurales y UNACH\n\n' + AUTHORIZATION +
        '\n\nSe mantienen 50 municipales; nueve movimientos y 41 posiciones intactas. Las 103 existentes, 30 policiales y 18 UPC conservan sus coordenadas.\n\n' +
        '\n'.join('- ' + key + ': ' + value['address'] for key, value in targets.items()) +
        '\n\nDestinos cartograficos: no verifican poste ni visibilidad. Calpi: el establecimiento confirmado por el usuario figura como Primax en OSM y PYS en el Excel. Coberturas potenciales recalculadas a 200 m.\n', encoding='utf-8')
    verify_derived(store, package, results)
    with sqlite3.connect(package) as db:
        require(db.execute('pragma integrity_check').fetchone()[0] == 'ok', 'GeoPackage invalido')
    with zipfile.ZipFile(OUT / 'ENTREGA_POLICIA_KDE.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.rglob('*')):
            if path.is_file() and path.suffix != '.zip':
                archive.write(path, path.relative_to(OUT).as_posix())
    write_json(ROOT / 'sig-bridge-active.json', dict(schemaVersion=1,
        root='./' + OUT.relative_to(ROOT).as_posix() + '/', releaseId=RELEASE,
        coverageData='riobamba-brechas-actualizadas-data.js'))
    print(json.dumps(proof), flush=True)

if __name__ == '__main__':
    main()
