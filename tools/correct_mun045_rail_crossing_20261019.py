"""Correct MUN-045 to the shared La Prensa / 9 de Octubre node marked by the user."""
import json
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

import pyogrio
from shapely.geometry import Point
from shapely.ops import nearest_points

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'sig-bridge'), str(ROOT / 'tools')]
from bridge.store import Store, clean, digest, now, read_json, require, write_json
from bridge.engine import calculate
import recalculate_current_gaps as gaps_adapter

RELEASE = 'MUN045_CRUCE_PRENSA_9OCTUBRE_20261019'
BASELINE = 'MUN045_PRENSA_9OCTUBRE_20261019'
OUT = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE
ROAD_SOURCE = ROOT.parent / 'entregas/RIOBAMBA_CONSOLIDADO_PRIORIDAD_REUNION_20261017/RIOBAMBA_CONSOLIDADO.gpkg'
ADDRESS = 'La Prensa x Avenida 9 de Octubre (cruce junto al ferrocarril)'


def read(path, layer):
    return pyogrio.read_dataframe(path, layer=layer).to_crs(32717)


def main():
    store = Store(ROOT)
    require(store.web.name == BASELINE, 'La base activa cambio')
    require(not OUT.exists(), 'No sobrescribir una entrega anterior')
    roads = read(ROAD_SOURCE, 'PNPRI_RED_VIAL_REFERENCIA')
    prensa = roads[roads['name'].fillna('').eq('La Prensa')]
    octubre = roads[roads['name'].fillna('').eq('Avenida 9 de Octubre')]
    anchor = Point(759455.8147674632, 9815559.659321252)
    candidates = []
    for i, a in prensa.iterrows():
        for j, b in octubre.iterrows():
            u, v = nearest_points(a.geometry, b.geometry)
            if a.geometry.distance(b.geometry) < 1e-7 and u.distance(anchor) < .01:
                candidates.append((u, i, j))
    require(bool(candidates), 'No se encontro el nodo compartido senalado por el usuario')
    target, fid_a, fid_b = candidates[0]
    evidence = dict(source='PNPRI_RED_VIAL_REFERENCIA', roads=['La Prensa', 'Avenida 9 de Octubre'],
                    sourceRows=[int(fid_a), int(fid_b)], centerlineGapM=0.0,
                    metricCoordinates=[target.x, target.y], fieldVerified=False,
                    screenshot='codex-clipboard-d12412d3-e86e-495c-ade5-b0b09b0acc89.png')
    municipal = read(store.base, 'PROPUESTA_MUNICIPAL_50_FINAL')
    old_point = municipal.loc[municipal.ID_PROPUESTA.eq('MUN-045')].geometry.iloc[0]
    note = ('Correccion del destino de MUN-045 segun la captura del usuario: ' + ADDRESS +
            '. Nodo comun de ambas lineas OSM; se conserva la posicion publicada anterior en el historial. ' +
            'La anterior posicion sobre otro tramo de 9 de Octubre no correspondia al cruce solicitado.')
    protected = {str(store.base): digest(store.base), str(ROAD_SOURCE): digest(ROAD_SOURCE)}
    manual = {}
    for key, spec in store.config['layers'].items():
        frame = read(store.base, spec['source'])
        if 'OBSERVACION_MANUAL' not in frame:
            frame['OBSERVACION_MANUAL'] = ''
        if key == 'municipal':
            index = frame.index[frame.ID_PROPUESTA.eq('MUN-045')][0]
            frame.loc[index, 'geometry'] = target
            frame.loc[index, 'OBSERVACION_MANUAL'] = note
        manual[key] = frame
    receipt = dict(revision=RELEASE, createdAt=now(), priorRelease=BASELINE,
                   authorization='Correccion del lugar marcado por el usuario, dentro de la publicacion solicitada.',
                   baseHashes=protected, changes=[dict(layer='municipal', id='MUN-045', geometryChanged=True,
                   fields=[], distanceM=old_point.distance(target), note=note)], crossingEvidence=evidence)

    def node_validator(_store, _changes, points, _police, _urban):
        matches = []
        for point, props in points:
            if props.get('ID_PROPUESTA') != 'MUN-045':
                continue
            require(point.equals_exact(target, 1e-7), 'Geometria distinta del nodo de la captura')
            props.update(DIRECCION=ADDRESS, INTERSECCION_O_NODO=ADDRESS,
                         BRIDGE_NODO_VALIDADO=True, ESTADO_REVISION='CRUCE_CORREGIDO_SEGUN_CAPTURA_USUARIO',
                         FUENTE_CRUCE='Nodo compartido OSM La Prensa x Avenida 9 de Octubre; separacion 0 m. Validacion cartografica; no de poste.')
            matches.append(dict(id='MUN-045', passed=True, cartographicNodeValidated=True, **evidence))
        require(len(matches) == 1, 'MUN-045 debe existir exactamente una vez')
        return matches, []

    OUT.mkdir(parents=True)
    print('Recalculando escenarios B y C en el cruce correcto...', flush=True)
    validation = calculate(store, OUT, OUT, manual, receipt, node_validator=node_validator)
    package = OUT / 'ESCENARIO_FINAL_183.gpkg'
    folder = OUT / 'coverage-inputs'
    folder.mkdir()
    gaps_adapter.main(final=package, out=folder, js_output=OUT/'riobamba-brechas-actualizadas-data.js', expected_replacements=30)
    gaps = read_json(folder / 'RESULTADOS.json')
    previous_gaps = read_json(store.web / 'coverage-inputs/RESULTADOS.json')
    overlays = {row['id']: row for row in previous_gaps['inventoryCameraOverlay']}
    for row in gaps['inventoryCameraOverlay']:
        row.update(overlays[row['id']])
    for key in ['inventoryGeolocation', 'sourceInventory']:
        gaps['metadata'][key] = previous_gaps['metadata'][key]
    gaps['inventoryCoverage']['metadata'].update(previous_gaps['inventoryCoverage']['metadata'])
    gaps['metadata']['localRevision'] = RELEASE
    write_json(folder / 'RESULTADOS.json', gaps)
    javascript = 'window.RIOBAMBA_UPDATED_GAPS = ' + json.dumps(clean(gaps), ensure_ascii=False, allow_nan=False, separators=(',', ':')) + ';\n'
    (OUT / 'riobamba-brechas-actualizadas-data.js').write_text(javascript, encoding='utf-8')
    (folder / 'riobamba-brechas-actualizadas-data.js').write_text(javascript, encoding='utf-8')
    shutil.copytree(store.web / 'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA', OUT / 'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA')
    pyogrio.write_dataframe(read(package, 'ESCENARIO_FINAL_183').to_crs(4326), OUT / 'ESCENARIO_FINAL_183.geojson', driver='GeoJSON')
    after = read(package, 'PROPUESTA_MUNICIPAL_50_FINAL')
    before_by_id = municipal.set_index('ID_PROPUESTA')
    changed = [row.ID_PROPUESTA for _, row in after.iterrows()
               if row.geometry.wkb != before_by_id.loc[row.ID_PROPUESTA].geometry.wkb]
    require(changed == ['MUN-045'], 'Se movieron otras municipales')
    for layer in ['CAMARAS_EXISTENTES_103_FINAL', 'PROPUESTA_POLICIA_30_FINAL', 'UPC_INFRAESTRUCTURA']:
        require(read(store.base, layer).geometry.to_wkb().tolist() == read(package, layer).geometry.to_wkb().tolist(), 'Cambio inesperado: ' + layer)
    require(len(read(package, 'UPC_INFRAESTRUCTURA')) == 18, 'Deben conservarse las 18 UPC')
    require(all(digest(Path(path)) == value for path, value in protected.items()), 'Se modificaron fuentes')
    corridors = read_json(OUT / 'CORRIDOR_COVERAGE_200M.json')
    corridors['metadata']['sourcePackage'] = RELEASE
    write_json(OUT / 'CORRIDOR_COVERAGE_200M.json', corridors)
    macaji = corridors['scenarios']['B']['corridors']['BOULEVARD_MACAJI_BELLAVISTA']
    results = read_json(OUT / 'RESULTADOS.json')
    results.update(status='MUN045_CRUCE_REAL_CORREGIDO', sourcePackage=RELEASE,
                   applied=True, published=True, publicRelease=RELEASE, gapScenarioCValidated=True)
    write_json(OUT / 'RESULTADOS.json', results)
    receipt.update(applied=True, published=True, previousUtm=[old_point.x, old_point.y],
                   correctedUtm=[target.x, target.y], validation=validation,
                   macajiMunicipalPct=macaji['coveredPct'])
    write_json(OUT / 'APROBACION_Y_FUENTES.json', receipt)
    proof = dict(passed=True, changedMunicipal=changed, otherMunicipal49Fixed=True,
                 existing103Fixed=True, police30Fixed=True, upc18Fixed=True,
                 crossingEvidence=evidence, macajiMunicipalPct=macaji['coveredPct'])
    write_json(OUT / 'VERIFICACION_INDEPENDIENTE.json', proof)
    (OUT / 'INFORME_FINAL.md').write_text(
        '# Correccion MUN-045 al cruce indicado\n\n' + note + '\n\n' +
        f'Posicion anterior: {old_point.x:.4f}, {old_point.y:.4f}. Posicion corregida: {target.x:.4f}, {target.y:.4f} (EPSG:32717).\n\n' +
        f'Cobertura municipal Macaji-Bellavista: {macaji["coveredPct"]:.5f}%; sin cubrir: {macaji["uncoveredM"]:.2f} m.\n\n' +
        'Se recalculan las coberturas y brechas con las posiciones finales. Se conservan las 103 existentes, las otras 49 municipales, las 30 policiales y las 18 UPC. KDE/Gi* no recalculados.\n', encoding='utf-8')
    with sqlite3.connect(package) as db:
        require(db.execute('pragma integrity_check').fetchone()[0] == 'ok', 'GeoPackage invalido')
    with zipfile.ZipFile(OUT / 'ENTREGA_POLICIA_KDE.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.rglob('*')):
            if path.is_file() and path.suffix != '.zip':
                archive.write(path, path.relative_to(OUT).as_posix())
    print(json.dumps(proof), flush=True)


if __name__ == '__main__':
    main()
