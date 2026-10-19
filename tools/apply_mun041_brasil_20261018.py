"""Prepare the explicitly requested MUN-041 move without publishing it."""
import json
import sqlite3
import sys
from pathlib import Path
import pyogrio
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sig-bridge'))
sys.path.insert(0, str(ROOT / 'tools'))
from bridge.store import Store, read_json, write_json, digest, require, now, clean
from bridge.engine import calculate, verify_derived
import recalculate_current_gaps as dependencies

RELEASE = 'MUN041_PRIMERA_CONSTITUYENTE_BRASIL_20261018'
OUT = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE
TARGET = Point(760732.7715657315, 9815699.697173316)
ADDRESS = 'Primera Constituyente x Brasil'

def read(path, layer):
    return pyogrio.read_dataframe(path, layer=layer).to_crs(32717)

def main():
    store = Store()
    require(store.web.name == 'MUN028_9OCTUBRE_EUGENIO_ESPEJO_20261018', 'Unexpected baseline')
    require(not OUT.exists(), 'Never overwrite a release')
    before = read(store.base, 'PROPUESTA_MUNICIPAL_50_FINAL')
    idx = before.index[before.ID_PROPUESTA.eq('MUN-041')][0]
    old = before.geometry[idx]
    roads = read(Path('D:/codex/entregas/RIOBAMBA_CONSOLIDADO_PRIORIDAD_REUNION_20261017/RIOBAMBA_CONSOLIDADO.gpkg'), 'PNPRI_RED_VIAL_REFERENCIA')
    crossing = roads[roads.distance(TARGET) < .001]
    require({'Primera Constituyente', 'Brasil'}.issubset(set(crossing['name'])), 'Crossing not verified')
    existing = read(store.base, 'CAMARAS_EXISTENTES_103_FINAL')
    police = read(store.base, 'PROPUESTA_POLICIA_30_FINAL')
    nearest = min(TARGET.distance(p) for p in list(existing.geometry) + list(police.geometry) + list(before.drop(index=idx).geometry))
    source_paths = [store.base, ROOT / 'sig-bridge-active.json', ROOT / 'riobamba-kde-combinado-data.js', ROOT / 'riobamba-hotspot-urbano-200m-data.js']
    hashes = {str(p): digest(p) for p in source_paths}
    auth = 'Usuario solicita mover MUN-041 a Primera Constituyente y Brasil y luego ordena publicar. Separacion a RIO-038-DOMO de 186.50 m, inferior al criterio general; se publica como excepcion registrada.'
    manual = {}
    for key, spec in store.config['layers'].items():
        frame = read(store.base, spec['source'])
        if 'OBSERVACION_MANUAL' not in frame:
            frame['OBSERVACION_MANUAL'] = ''
        if key == 'municipal':
            frame.loc[idx, 'geometry'] = TARGET
            frame.loc[idx, 'OBSERVACION_MANUAL'] = auth
        manual[key] = frame
    receipt = dict(revision=RELEASE, createdAt=now(), authorization=auth, applied=True, published=False,
                   priorRelease=store.web.name, baseHashes=hashes,
                   changes=[dict(layer='municipal', id='MUN-041', geometryChanged=True, fields=[], distanceM=old.distance(TARGET), note=auth)])
    def nodes(_store, _changes, municipal, _police, urban):
        for point, props in municipal:
            if props['ID_PROPUESTA'] == 'MUN-041':
                require(point.equals_exact(TARGET, .000001), 'Wrong target')
                props.update(DIRECCION=ADDRESS, INTERSECCION_O_NODO=ADDRESS, BRIDGE_NODO_VALIDADO=True,
                             ESTADO_REVISION='DESTINO_EXPRESO_USUARIO_BRASIL',
                             FUENTE_CRUCE='Cruce compartido OSM Primera Constituyente x Brasil; visibilidad y poste sin verificar en campo.')
        return [dict(id='MUN-041', passed=True, cartographicNodeValidated=True, fieldVerified=False,
                     minimumSpacingM=nearest, spacingExceptionExplicitDestination=True,
                     roads=crossing['name'].dropna().unique().tolist())], []
    OUT.mkdir(parents=True)
    print('Recalculando escenario y coberturas...', flush=True)
    validation = calculate(store, OUT, OUT, manual, receipt, node_validator=nodes)
    require(not validation['publishBlocks'], str(validation['publishBlocks']))
    package = OUT / 'ESCENARIO_FINAL_183.gpkg'
    folder = OUT / 'coverage-inputs'
    folder.mkdir()
    dependencies.main(final=package, out=folder, js_output=OUT / 'riobamba-brechas-actualizadas-data.js', expected_replacements=30)
    gaps = read_json(folder / 'RESULTADOS.json')
    prior_gaps = read_json(store.web / 'coverage-inputs/RESULTADOS.json')
    overlay = {r['id']: r for r in prior_gaps['inventoryCameraOverlay']}
    for row in gaps['inventoryCameraOverlay']:
        row.update(overlay[row['id']])
    for key in ['inventoryGeolocation', 'sourceInventory']:
        gaps['metadata'][key] = prior_gaps['metadata'][key]
    gaps['inventoryCoverage']['metadata'].update(prior_gaps['inventoryCoverage']['metadata'])
    gaps['metadata']['localRevision'] = RELEASE
    write_json(folder / 'RESULTADOS.json', gaps)
    payload = json.dumps(clean(gaps), ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    (OUT / 'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = ' + payload + ';\n', encoding='utf-8')
    results = read_json(OUT / 'RESULTADOS.json')
    prior = read_json(store.web / 'RESULTADOS.json')
    results.pop('publicRelease', None)
    results.update(status='MUN041_BRASIL_PREVISUALIZACION', sourcePackage=RELEASE, applied=True, published=False,
                   authorization=auth, bridge=validation, pendingUnapplied=[],
                   selectionMethod='Destino manual explicito MUN-041. Otras 182 camaras intactas.',
                   approvedExceptions=prior.get('approvedExceptions', []) + [dict(id='MUN-041', camera='RIO-038-DOMO', distanceM=nearest, explicitUserDestination=True)],
                   warnings=['Separacion 186.50m de RIO-038-DOMO; no cumple criterio general de 400m.',
                             'Radio potencial 200m, no vision optica certificada. Sin publicacion ni cambio del visor activo.'])
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
    actual = read(package, 'PROPUESTA_MUNICIPAL_50_FINAL')
    changed = actual.geometry.to_wkb().to_numpy() != before.geometry.to_wkb().to_numpy()
    require(set(actual.loc[changed, 'ID_PROPUESTA']) == {'MUN-041'}, 'Unexpected municipal move')
    for layer in ['CAMARAS_EXISTENTES_103_FINAL', 'PROPUESTA_POLICIA_30_FINAL']:
        require(read(store.base, layer).geometry.to_wkb().tolist() == read(package, layer).geometry.to_wkb().tolist(), 'Protected geometry changed')
    require(all(digest(Path(p)) == h for p, h in hashes.items()), 'Protected source changed')
    proof = dict(passed=True, release=RELEASE, published=False, changedMunicipal=['MUN-041'],
                 otherMunicipal49Fixed=True, existing103Fixed=True, police30Fixed=True,
                 movementM=old.distance(TARGET), nearestM=nearest, targetUTM32717=[TARGET.x, TARGET.y], baseHashes=hashes)
    write_json(OUT / 'VERIFICACION_INDEPENDIENTE.json', proof)
    (OUT / 'MOVIMIENTOS_MUNICIPALES.csv').write_text('ID,DESPLAZAMIENTO_M,DESTINO\nMUN-041,' + str(old.distance(TARGET)) + ',' + ADDRESS + '\n', encoding='utf-8')
    (OUT / 'INFORME_FINAL.md').write_text('# MUN-041: Primera Constituyente x Brasil\n\nPrevisualizacion local; no publicada. Solo cambia MUN-041. Movimiento 96.02 m. RIO-038-DOMO a 186.50 m: excepcion por destino expreso del usuario. Las otras 182 camaras se conservan. Coberturas recalculadas, KDE y Gi* intactos. Radio potencial, no visibilidad certificada.\n', encoding='utf-8')
    with sqlite3.connect(package) as db:
        require(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Invalid GPKG')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute('PRAGMA journal_mode=DELETE')
    print(json.dumps(proof), flush=True)

if __name__ == '__main__':
    if '--publish' in sys.argv:
        out = OUT
        proof = read_json(out / 'VERIFICACION_INDEPENDIENTE.json')
        require(proof['passed'] and proof['release'] == RELEASE and not proof['published'], 'No valid unpublished result')
        pointer = read_json(ROOT / 'sig-bridge-active.json')
        require(pointer['releaseId'] == 'MUN028_9OCTUBRE_EUGENIO_ESPEJO_20261018', 'Active release changed')
        for name in ['RESULTADOS.json', 'VALIDACION.json', 'VERIFICACION_INDEPENDIENTE.json', 'APROBACION_Y_FUENTES.json']:
            data = read_json(out / name)
            data.update(published=True, publicRelease=RELEASE)
            if name == 'RESULTADOS.json':
                data['bridge']['published'] = True
            write_json(out / name, data)
        pointer.update(root='./data/seguridad-riobamba/SIG_BRIDGE_RELEASES/' + RELEASE + '/', releaseId=RELEASE)
        write_json(ROOT / 'sig-bridge-active.json', pointer)
        proof['published'] = True
        write_json(out / 'VERIFICACION_INDEPENDIENTE.json', proof)
        import zipfile
        archive_path = out / 'ENTREGA_POLICIA_KDE.zip'
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in out.rglob('*'):
                if path.is_file() and path != archive_path:
                    archive.write(path, path.relative_to(out))
        print(json.dumps(dict(release=RELEASE, published=True, files=sum(1 for p in out.rglob('*') if p.is_file())), ensure_ascii=False))
    else:
        main()
