"""Move only MUN-033 to the road intersection requested by the user."""
import json
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

import pyogrio
from shapely.ops import nearest_points

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'sig-bridge'), str(ROOT / 'tools')]
from bridge.store import Store, clean, digest, now, read_json, require, write_json
from bridge.engine import calculate, verify_derived
import recalculate_current_gaps as gaps_adapter

RELEASE = 'MUN033_JACINTO_UNIDAD_NACIONAL_20261021'
CAMERA = 'MUN-033'
OUT = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE
ROADS = ROOT.parent / 'entregas/RIOBAMBA_CONSOLIDADO_PRIORIDAD_REUNION_20261017/RIOBAMBA_CONSOLIDADO.gpkg'
ADDRESS = 'Jacinto Gonzales x Avenida Unidad Nacional'
BASELINE = 'MACAJI_COMPENSACION_021_043_20261021'
AUTHORIZATION = 'Usuario solicita mover MUN-033 a Jacinto Gonzales y Avenida Unidad Nacional.'
NODE_VALIDATED = True
SOURCE_NOTE = 'Nodo compartido de ambas vias en PNPRI_RED_VIAL_REFERENCIA; no verificacion de poste.'


def read(path, layer):
    return pyogrio.read_dataframe(path, layer=layer).to_crs(32717)


def locate(roads):
    a = roads[roads['name'].eq('Jacinto Gonzales')]
    b = roads[roads['name'].eq('Avenida Unidad Nacional')]
    nodes = {}
    evidence_rows = []
    for i, road_a in a.iterrows():
        for j, road_b in b.iterrows():
            if road_a.geometry.distance(road_b.geometry) < 1e-7:
                point, _ = nearest_points(road_a.geometry, road_b.geometry)
                nodes[point.wkb] = point
                evidence_rows.append([int(i), int(j)])
    require(len(nodes) == 1, 'El cruce debe tener un unico nodo comprobado')
    target = next(iter(nodes.values()))
    evidence = dict(roads=['Jacinto Gonzales', 'Avenida Unidad Nacional'],
        source='PNPRI_RED_VIAL_REFERENCIA', sourceRows=evidence_rows, centerlineGapM=0,
        metricCoordinates=[target.x, target.y], fieldVerified=False)
    return target, evidence


def main():
    store = Store(ROOT)
    require(store.web.name == BASELINE, 'La base activa cambio')
    require(not OUT.exists(), 'No sobrescribir una revision')
    roads = read(ROADS, 'PNPRI_RED_VIAL_REFERENCIA')
    target, evidence = locate(roads)
    before = read(store.base, 'PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    old = before.loc[CAMERA].geometry
    protected = {str(p): digest(p) for p in (store.base, ROADS, ROOT / 'riobamba-kde-combinado-data.js')}
    manual = {}
    for key, spec in store.config['layers'].items():
        frame = read(store.base, spec['source'])
        if 'OBSERVACION_MANUAL' not in frame:
            frame['OBSERVACION_MANUAL'] = ''
        if key == 'municipal':
            index = frame.index[frame.ID_PROPUESTA.eq(CAMERA)][0]
            frame.at[index, 'geometry'] = target
            frame.at[index, 'OBSERVACION_MANUAL'] = 'Destino expreso del usuario: ' + ADDRESS
        manual[key] = frame
    receipt = dict(revision=RELEASE, createdAt=now(), priorRelease=store.web.name,
        authorization=AUTHORIZATION,
        baseHashes=protected, crossingEvidence=evidence,
        previousUtm=[old.x, old.y], correctedUtm=[target.x, target.y],
        changes=[dict(layer='municipal', id=CAMERA, geometryChanged=True, fields=[],
            distanceM=old.distance(target), note=ADDRESS)])

    def validate(_store, _changes, municipal, _police, _urban):
        checked = []
        for point, props in municipal:
            if props.get('ID_PROPUESTA') == CAMERA:
                require(point.wkb == target.wkb, 'Destino incorrecto')
                props.update(DIRECCION=ADDRESS, INTERSECCION_O_NODO=ADDRESS,
                    BRIDGE_NODO_VALIDADO=NODE_VALIDATED, ESTADO_REVISION='DESTINO_EXPRESO_USUARIO',
                    FUENTE_CRUCE=SOURCE_NOTE)
                checked.append(dict(id=CAMERA, passed=True, cartographicNodeValidated=NODE_VALIDATED, **evidence))
        require(len(checked) == 1, CAMERA + ' debe existir una sola vez')
        return checked, []

    OUT.mkdir(parents=True)
    print('Recalculando ' + CAMERA + ' y coberturas B/C...', flush=True)
    validation = calculate(store, OUT, OUT, manual, receipt, node_validator=validate)
    prior_validation = read_json(store.web / 'VALIDACION.json')
    require(validation['publishBlocks'] == prior_validation['publishBlocks'],
        'El movimiento introduce restricciones nuevas que requieren revision')
    package = OUT / 'ESCENARIO_FINAL_183.gpkg'
    folder = OUT / 'coverage-inputs'
    folder.mkdir()
    gaps_adapter.main(final=package, out=folder,
        js_output=OUT / 'riobamba-brechas-actualizadas-data.js', expected_replacements=30)
    gaps = read_json(folder / 'RESULTADOS.json')
    previous_gaps = read_json(store.web / 'coverage-inputs/RESULTADOS.json')
    overlays = {r['id']: r for r in previous_gaps['inventoryCameraOverlay']}
    for row in gaps['inventoryCameraOverlay']:
        row.update(overlays[row['id']])
    for key in ('inventoryGeolocation', 'sourceInventory'):
        gaps['metadata'][key] = previous_gaps['metadata'][key]
    gaps['inventoryCoverage']['metadata'].update(previous_gaps['inventoryCoverage']['metadata'])
    gaps['metadata']['localRevision'] = RELEASE
    write_json(folder / 'RESULTADOS.json', gaps)
    javascript = 'window.RIOBAMBA_UPDATED_GAPS = ' + json.dumps(clean(gaps), ensure_ascii=False, allow_nan=False, separators=(',', ':')) + ';\n'
    for path in (OUT, folder):
        (path / 'riobamba-brechas-actualizadas-data.js').write_text(javascript, encoding='utf-8')
    shutil.copytree(store.web / 'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA', OUT / 'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA')
    pyogrio.write_dataframe(read(package, 'ESCENARIO_FINAL_183').to_crs(4326), OUT / 'ESCENARIO_FINAL_183.geojson', driver='GeoJSON')
    after = read(package, 'PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    changed = [key for key in before.index if before.loc[key].geometry.wkb != after.loc[key].geometry.wkb]
    require(changed == [CAMERA] and len(after) == 50, 'Cambio municipal inesperado')
    for layer, count in [('CAMARAS_EXISTENTES_103_FINAL', 103), ('PROPUESTA_POLICIA_30_FINAL', 30), ('UPC_INFRAESTRUCTURA', 18)]:
        original, final = read(store.base, layer), read(package, layer)
        require(len(final) == count and original.geometry.to_wkb().tolist() == final.geometry.to_wkb().tolist(), 'Cambio protegido: ' + layer)
    require(all(digest(Path(p)) == value for p, value in protected.items()), 'Se alteraron fuentes')
    results = read_json(OUT / 'RESULTADOS.json')
    results.update(status=CAMERA.replace('-', '') + '_DESTINO_SOLICITADO_APLICADO', sourcePackage=RELEASE,
        publicRelease=RELEASE, applied=True, published=False, authorization=receipt['authorization'])
    write_json(OUT / 'RESULTADOS.json', results)
    corridors = read_json(OUT / 'CORRIDOR_COVERAGE_200M.json')
    corridors['metadata']['sourcePackage'] = RELEASE
    write_json(OUT / 'CORRIDOR_COVERAGE_200M.json', corridors)
    proof = dict(passed=True, changedMunicipal=changed, otherMunicipal49Fixed=True,
        existing103Fixed=True, police30Fixed=True, upc18Fixed=True,
        displacementM=old.distance(target), crossingEvidence=evidence,
        remainingReviewItems=validation['publishBlocks'])
    write_json(OUT / 'VERIFICACION_INDEPENDIENTE.json', proof)
    write_json(OUT / 'APROBACION_Y_FUENTES.json', {**receipt, 'applied': True, 'published': False})
    (OUT / 'INFORME_FINAL.md').write_text('# ' + CAMERA + '\n\n' + ADDRESS + '\n\nSolo se mueve ' + CAMERA + '. Coberturas recalculadas a 200 m. Se conservan las otras 49 municipales, 103 existentes, 30 policiales y 18 UPC.\n', encoding='utf-8')
    verify_derived(store, package, results)
    with sqlite3.connect(package) as db:
        require(db.execute('pragma integrity_check').fetchone()[0] == 'ok', 'GeoPackage invalido')
    with zipfile.ZipFile(OUT / 'ENTREGA_POLICIA_KDE.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.rglob('*')):
            if path.is_file() and path.suffix != '.zip':
                archive.write(path, path.relative_to(OUT).as_posix())
    print(json.dumps(proof), flush=True)


if __name__ == '__main__':
    main()
