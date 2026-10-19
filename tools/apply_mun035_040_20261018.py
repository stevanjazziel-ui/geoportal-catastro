"""Prepare the requested MUN-035 and MUN-040 moves; do not publish."""
import json
import sqlite3
import sys
from pathlib import Path

import pyogrio
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'sig-bridge'), str(ROOT / 'tools')]
from bridge.store import Store, read_json, write_json, digest, require, now, clean
from bridge.engine import calculate, verify_derived
import recalculate_current_gaps as dependencies

RELEASE = 'MUN035_040_GUAYAQUIL_ESMERALDAS_20261018'
OUT = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE
ROADS_PATH = Path('D:/codex/entregas/RIOBAMBA_CONSOLIDADO_PRIORIDAD_REUNION_20261017/RIOBAMBA_CONSOLIDADO.gpkg')
TARGETS = {
    'MUN-035': (Point(761236.2368629125, 9815037.651615301), 'Guayaquil x Gabriel Garcia Moreno', ('Guayaquil', 'Gabriel García Moreno')),
    'MUN-040': (Point(761227.5339324673, 9814510.060645752), 'Esmeraldas x Eugenio Espejo', ('Esmeraldas', 'Eugenio Espejo')),
}

def read(path, layer):
    return pyogrio.read_dataframe(path, layer=layer).to_crs(32717)

def main():
    store = Store()
    require(store.web.name == 'MUN041_PRIMERA_CONSTITUYENTE_BRASIL_20261018', 'Unexpected baseline')
    require(not OUT.exists(), 'Never overwrite a release')
    municipal = read(store.base, 'PROPUESTA_MUNICIPAL_50_FINAL')
    roads = read(ROADS_PATH, 'PNPRI_RED_VIAL_REFERENCIA')
    existing = read(store.base, 'CAMARAS_EXISTENTES_103_FINAL')
    police = read(store.base, 'PROPUESTA_POLICIA_30_FINAL')
    old = {}
    intersections = {}
    for camera, (point, address, street_names) in TARGETS.items():
        idx = municipal.index[municipal.ID_PROPUESTA.eq(camera)][0]
        old[camera] = municipal.geometry[idx]
        crossings = roads[roads.distance(point) < .001]
        found = set(crossings['name'].dropna())
        require(set(street_names).issubset(found), f'Unverified crossing for {camera}: {found}')
        intersections[camera] = crossings
        municipal.loc[idx, 'geometry'] = point
    idx_by_id = {row.ID_PROPUESTA: i for i, row in municipal.iterrows()}
    nearest = {}
    others = list(existing.geometry) + list(police.geometry)
    for camera, (point, _, _) in TARGETS.items():
        other_municipal = [g for cid, g in zip(municipal.ID_PROPUESTA, municipal.geometry) if cid != camera]
        nearest[camera] = min(point.distance(g) for g in others + other_municipal)
    separation = TARGETS['MUN-035'][0].distance(TARGETS['MUN-040'][0])
    source_paths = [store.base, ROOT / 'sig-bridge-active.json', ROOT / 'riobamba-kde-combinado-data.js', ROOT / 'riobamba-hotspot-urbano-200m-data.js']
    hashes = {str(path): digest(path) for path in source_paths}
    auth = 'Usuario solicita mover MUN-035 a Guayaquil x Gabriel Garcia Moreno y MUN-040 a Esmeraldas x Eugenio Espejo. Nodos cartograficos verificados. Proximidades menores a 400m de camaras existentes registradas como excepciones de destino expreso.'
    manual = {}
    for key, spec in store.config['layers'].items():
        frame = read(store.base, spec['source'])
        if 'OBSERVACION_MANUAL' not in frame:
            frame['OBSERVACION_MANUAL'] = ''
        if key == 'municipal':
            for camera, (point, address, _) in TARGETS.items():
                i = frame.index[frame.ID_PROPUESTA.eq(camera)][0]
                frame.loc[i, 'geometry'] = point
                frame.loc[i, 'OBSERVACION_MANUAL'] = auth
        manual[key] = frame
    receipt = dict(revision=RELEASE, createdAt=now(), authorization=auth, applied=True, published=False,
                   priorRelease=store.web.name, baseHashes=hashes,
                   changes=[dict(layer='municipal', id=camera, geometryChanged=True, fields=[], distanceM=old[camera].distance(spec[0]), note=auth)
                            for camera, spec in TARGETS.items()],
                   exceptions=[dict(id=camera, nearestCameraM=nearest[camera], below400m=True) for camera in TARGETS],
                   pairSeparationM=separation)
    def validate_nodes(_store, _changes, points, _police, _urban):
        validations = []
        for point, props in points:
            camera = props.get('ID_PROPUESTA')
            if camera not in TARGETS:
                continue
            target, address, streets = TARGETS[camera]
            require(point.equals_exact(target, .000001), f'Wrong target for {camera}')
            crossing = intersections[camera]
            props.update(DIRECCION=address, INTERSECCION_O_NODO=address, BRIDGE_NODO_VALIDADO=True,
                         ESTADO_REVISION='DESTINO_EXPRESO_USUARIO',
                         FUENTE_CRUCE=f'Cruce compartido en red OSM: {streets[0]} x {streets[1]}; poste y visibilidad no verificados en campo.')
            validations.append(dict(id=camera, passed=True, cartographicNodeValidated=True, fieldVerified=False,
                                    nearestCameraM=nearest[camera], exceptionDestinationExplicit=True,
                                    roads=crossing['name'].dropna().unique().tolist()))
        require(len(validations) == 2, 'Both requested destinations must validate')
        return validations, []
    OUT.mkdir(parents=True)
    print('Recalculando el escenario y coberturas...', flush=True)
    validation = calculate(store, OUT, OUT, manual, receipt, node_validator=validate_nodes)
    require(not validation['publishBlocks'], str(validation['publishBlocks']))
    package = OUT / 'ESCENARIO_FINAL_183.gpkg'
    folder = OUT / 'coverage-inputs'
    folder.mkdir()
    dependencies.main(final=package, out=folder, js_output=OUT / 'riobamba-brechas-actualizadas-data.js', expected_replacements=30)
    gaps = read_json(folder / 'RESULTADOS.json')
    previous_gaps = read_json(store.web / 'coverage-inputs/RESULTADOS.json')
    inventory_overlay = {row['id']: row for row in previous_gaps['inventoryCameraOverlay']}
    for row in gaps['inventoryCameraOverlay']:
        row.update(inventory_overlay[row['id']])
    for key in ['inventoryGeolocation', 'sourceInventory']:
        gaps['metadata'][key] = previous_gaps['metadata'][key]
    gaps['inventoryCoverage']['metadata'].update(previous_gaps['inventoryCoverage']['metadata'])
    gaps['metadata']['localRevision'] = RELEASE
    write_json(folder / 'RESULTADOS.json', gaps)
    payload = json.dumps(clean(gaps), ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    (OUT / 'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = ' + payload + ';\n', encoding='utf-8')
    results = read_json(OUT / 'RESULTADOS.json')
    previous_results = read_json(store.web / 'RESULTADOS.json')
    results.pop('publicRelease', None)
    exceptions = list(previous_results.get('approvedExceptions', []))
    exceptions.extend(dict(id=camera, camera='nearest existing', distanceM=nearest[camera], explicitUserDestination=True) for camera in TARGETS)
    results.update(status='MUN035_040_MOVES_PREVIEW', sourcePackage=RELEASE, applied=True, published=False,
                   authorization=auth, bridge=validation, pendingUnapplied=[], approvedExceptions=exceptions,
                   selectionMethod='Dos destinos explicitos solicitados por el usuario; coberturas recalculadas.',
                   warnings=[f'{camera}: camara existente mas cercana a {nearest[camera]:.2f} m, inferior a 400 m.' for camera in TARGETS]
                            + [f'Separacion entre los destinos MUN-035 y MUN-040: {separation:.2f} m.',
                               'Radio de 200m representa proximidad potencial, no visibilidad optica certificada. Aun sin publicar.'])
    for path in OUT.iterdir():
        if path.is_file() and path.suffix in ['.md', '.json'] and path.name not in ['RESULTADOS.json', 'VALIDACION.json', 'CORRIDOR_COVERAGE_200M.json']:
            path.unlink()
    write_json(OUT / 'RESULTADOS.json', results)
    write_json(OUT / 'VALIDACION.json', validation)
    write_json(OUT / 'APROBACION_Y_FUENTES.json', receipt)
    corridor = read_json(OUT / 'CORRIDOR_COVERAGE_200M.json')
    corridor['metadata']['sourcePackage'] = RELEASE
    write_json(OUT / 'CORRIDOR_COVERAGE_200M.json', corridor)
    pyogrio.write_dataframe(read(package, 'ESCENARIO_FINAL_183').to_crs(4326), OUT / 'ESCENARIO_FINAL_183.geojson', driver='GeoJSON')
    verify_derived(store, package, results)
    final_municipal = read(package, 'PROPUESTA_MUNICIPAL_50_FINAL')
    changed = set(final_municipal.loc[final_municipal.geometry.to_wkb().to_numpy() != read(store.base, 'PROPUESTA_MUNICIPAL_50_FINAL').geometry.to_wkb().to_numpy(), 'ID_PROPUESTA'])
    require(changed == set(TARGETS), f'Unexpected municipal moves {changed}')
    for layer in ['CAMARAS_EXISTENTES_103_FINAL', 'PROPUESTA_POLICIA_30_FINAL']:
        require(read(store.base, layer).geometry.to_wkb().tolist() == read(package, layer).geometry.to_wkb().tolist(), f'Protected geometries changed: {layer}')
    require(all(digest(Path(path)) == value for path, value in hashes.items()), 'Protected source changed')
    proof = dict(passed=True, release=RELEASE, published=False, changedMunicipal=sorted(TARGETS),
                 otherMunicipal48Fixed=True, existing103Fixed=True, police30Fixed=True,
                 movementsM={camera: old[camera].distance(spec[0]) for camera, spec in TARGETS.items()},
                 nearestM=nearest, pairSeparationM=separation, baseHashes=hashes)
    write_json(OUT / 'VERIFICACION_INDEPENDIENTE.json', proof)
    with sqlite3.connect(package) as db:
        require(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Invalid GPKG')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute('PRAGMA journal_mode=DELETE')
    report = ['# Movimientos municipales MUN-035 y MUN-040', '', 'Previsualizacion local; aun no publicada.', '']
    for camera, (point, address, _) in TARGETS.items():
        report.append(f'- {camera}: {address}; movimiento {old[camera].distance(point):.2f} m; camara existente mas cercana {nearest[camera]:.2f} m.')
    report += ['', f'Distancia entre ambos destinos: {separation:.2f} m.', '', 'Se recalcularon coberturas y dependencias. Las otras 48 municipales, 103 existentes y 30 policiales conservaron sus geometrias. KDE y Gi* no se recalcularon. Radio potencial de proximidad, no campo visual certificado.']
    (OUT / 'INFORME_FINAL.md').write_text('\n'.join(report) + '\n', encoding='utf-8')
    print(json.dumps(proof), flush=True)

if __name__ == '__main__':
    main()
