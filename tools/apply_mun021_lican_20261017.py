"""Apply the requested MUN-021 move and rebuild dependent public data."""
import json
import shutil
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

RELEASE = 'MUN021_ACCESO_LICAN_HURONES_20261017'
OUT = ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES'/RELEASE
AUTH = 'Usuario identifica MUN-021 junto a RIO-028 y solicita: esta muy pegada a la28 mueve. Destino revisado: Maldonado x Hurones; solo cambia MUN-021.'
TARGET = Point(755931.7858282902, 9816991.554998081)

def read(path, layer):
    return pyogrio.read_dataframe(path, layer=layer).to_crs(32717)

def main():
    store = Store()
    require(store.web.name == 'ANILLO_B_350M_5_URBANAS_20261017', 'Unexpected public baseline')
    require(not OUT.exists(), 'Do not overwrite release history')
    before = read(store.base, 'PROPUESTA_MUNICIPAL_50_FINAL')
    index = before.index[before.ID_PROPUESTA.eq('MUN-021')][0]
    old = before.geometry[index]
    roads_path = Path('D:/codex/entregas/RIOBAMBA_CONSOLIDADO_PRIORIDAD_REUNION_20261017/RIOBAMBA_CONSOLIDADO.gpkg')
    roads = read(roads_path, 'PNPRI_RED_VIAL_REFERENCIA')
    crossing = roads[roads.geometry.distance(TARGET) < .001]
    require(crossing['name'].fillna('').str.contains('Hurones').any(), 'Hurones missing')
    require(crossing['name'].fillna('').str.contains('Maldonado').any(), 'Main road missing')
    hashes = {str(path): digest(path) for path in [store.base, ROOT/'sig-bridge-active.json', ROOT/'riobamba-kde-combinado-data.js', ROOT/'riobamba-hotspot-urbano-200m-data.js']}
    manual = {}
    for key, spec in store.config['layers'].items():
        frame = read(store.base, spec['source'])
        if 'OBSERVACION_MANUAL' not in frame:
            frame['OBSERVACION_MANUAL'] = ''
        if key == 'municipal':
            frame.loc[index, 'geometry'] = TARGET
            frame.loc[index, 'OBSERVACION_MANUAL'] = AUTH
        manual[key] = frame
    fixed = list(read(store.base, 'CAMARAS_EXISTENTES_103_FINAL').geometry)+list(read(store.base, 'PROPUESTA_POLICIA_30_FINAL').geometry)+list(before.drop(index=index).geometry)
    nearest = min(TARGET.distance(g) for g in fixed)
    require(nearest >= 400, 'New destination violates400m')
    receipt = dict(revision=RELEASE, createdAt=now(), authorization=AUTH, applied=True, published=False, priorRelease=store.web.name, baseHashes=hashes,
                   changes=[dict(layer='municipal', id='MUN-021', geometryChanged=True, fields=[], distanceM=old.distance(TARGET), note=AUTH)])
    def nodes(_store, _changes, municipal, _police, urban):
        for point, props in municipal:
            if props['ID_PROPUESTA'] != 'MUN-021':
                continue
            require(point.equals_exact(TARGET, .000001), 'Wrong target')
            props.update(DIRECCION='Panamericana Sur / Av. Pedro Vicente Maldonado x Hurones', INTERSECCION_O_NODO='Pedro Vicente Maldonado x Hurones',
                         ESTADO_REVISION='ACCESO_LICAN_CORREGIDO_USUARIO', BRIDGE_NODO_VALIDADO=True, FUENTE_CRUCE='Nodo compartido de red OSM: Maldonado x Hurones. Sin verificacion de poste.')
        return [dict(id='MUN-021', passed=True, cartographicNodeValidated=True, principalRoad=True, fieldVerified=False, minimumSpacingM=nearest,
                     roads=crossing['name'].dropna().unique().tolist())], []
    OUT.mkdir(parents=True)
    print('Recalculando coberturas, incidentes, poblacion y solapes...', flush=True)
    validation = calculate(store, OUT, OUT, manual, receipt, node_validator=nodes)
    require(not validation['publishBlocks'], str(validation['publishBlocks']))
    package = OUT/'ESCENARIO_FINAL_183.gpkg'
    folder = OUT/'coverage-inputs'
    folder.mkdir()
    print('Actualizando dependencias100/150/200m...', flush=True)
    dependencies.main(final=package, out=folder, js_output=OUT/'riobamba-brechas-actualizadas-data.js', expected_replacements=30)
    gaps = read_json(folder/'RESULTADOS.json')
    prior_gaps = read_json(store.web/'coverage-inputs/RESULTADOS.json')
    overlay = {r['id']:r for r in prior_gaps['inventoryCameraOverlay']}
    for row in gaps['inventoryCameraOverlay']:
        row.update(overlay[row['id']])
    for key in ['inventoryGeolocation','sourceInventory']:
        gaps['metadata'][key] = prior_gaps['metadata'][key]
    gaps['inventoryCoverage']['metadata'].update(prior_gaps['inventoryCoverage']['metadata'])
    gaps['metadata']['localRevision'] = RELEASE
    payload = json.dumps(clean(gaps), ensure_ascii=False, allow_nan=False, separators=(',',':'))
    (folder/'RESULTADOS.json').write_text(payload, encoding='utf-8')
    (OUT/'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = '+payload+';\n', encoding='utf-8')
    results = read_json(OUT/'RESULTADOS.json')
    for key in ['anilloBStudy','boyacaStudy','approvedExceptions']:
        results.pop(key, None)
    results.update(status='MUN021_LICAN_CORREGIDA', sourcePackage=RELEASE, applied=True, published=False, authorization=AUTH,
                   selectionMethod='Correccion puntual solicitada de acceso a Lican. Sin optimizacion de otras camaras.',
                   warnings=['Solo MUN-021 reubicada.103 existentes,30 policiales,otras49municipales intactas.', 'Nodo cartografico; radio200m de proximidad no certifica vision optica.', '19 existentes conservan coordenadas provisionales.'])
    results['bridge'] = validation
    # Do not inherit historical approvals or movement reports as current evidence.
    for path in OUT.iterdir():
        if path.is_file() and ((path.suffix in ['.md','.json'] and path.name not in ['RESULTADOS.json','VALIDACION.json','CORRIDOR_COVERAGE_200M.json']) or path.name in ['MOVIMIENTOS_B_5.csv','MOVIMIENTOS_MUNICIPALES_50.csv','MOVIMIENTOS.csv']):
            path.unlink()
    write_json(OUT/'RESULTADOS.json', results)
    write_json(OUT/'VALIDACION.json', validation)
    write_json(OUT/'APROBACION_Y_FUENTES.json', receipt)
    corridor = read_json(OUT/'CORRIDOR_COVERAGE_200M.json')
    corridor['metadata']['sourcePackage'] = RELEASE
    write_json(OUT/'CORRIDOR_COVERAGE_200M.json', corridor)
    combined = read(package, 'ESCENARIO_FINAL_183')
    pyogrio.write_dataframe(combined.to_crs(4326), OUT/'ESCENARIO_FINAL_183.geojson', driver='GeoJSON')
    verify_derived(store, package, results)
    actual = read(package, 'PROPUESTA_MUNICIPAL_50_FINAL')
    changed = actual.geometry.to_wkb().to_numpy() != before.geometry.to_wkb().to_numpy()
    require(set(actual.loc[changed,'ID_PROPUESTA']) == {'MUN-021'}, 'Unexpected municipal moves')
    for layer in ['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_POLICIA_30_FINAL']:
        require(read(store.base,layer).geometry.to_wkb().tolist()==read(package,layer).geometry.to_wkb().tolist(), 'Protected geometry changed')
    prior = read_json(store.web/'RESULTADOS.json')
    for current in results['corridors']:
        old_rows = [r for r in prior['corridors'] if r['ESCENARIO']==current['ESCENARIO'] and r['CORREDOR']==current['CORREDOR']]
        require(len(old_rows)==1 and abs(current['PCT_CUBIERTO']-old_rows[0]['PCT_CUBIERTO'])<1e-7, 'Unexpected corridor coverage change')
    require(all(digest(Path(p))==v for p,v in hashes.items()), 'Source changed')
    write_json(OUT/'VERIFICACION_INDEPENDIENTE.json', dict(passed=True, changedMunicipal=['MUN-021'], existing103Fixed=True, police30Fixed=True, otherMunicipal49Fixed=True,
               minimumSpacingM=nearest, movementM=old.distance(TARGET), corridorCoverageUnchanged=True, giKdeUnchanged=True, published=False, baseHashes=hashes))
    (OUT/'INFORME_FINAL.md').write_text('# Correccion puntual MUN-021\n\nAcceso a Lican: Pedro Vicente Maldonado x Hurones. Movimiento673.27m. Separacion de RIO-028:163.70m antes,510.46m despues. Otras49municipales,103existentes y30policiales intactas.\n\nCoberturas de corredores sin cambio: Macaji100%, Anillo75.17%municipal/82.73%conPolicia. Dependencias100/150/200m recalculadas. KDE/Gi* intactos. Radio potencial, no certifica visibilidad optica.\n', encoding='utf-8')
    with sqlite3.connect(package) as db:
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok', 'Invalid GPKG')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute('PRAGMA journal_mode=DELETE')
    with zipfile.ZipFile(OUT/'ENTREGA_POLICIA_KDE.zip','w',zipfile.ZIP_DEFLATED) as z:
        for path in OUT.iterdir():
            if path.is_file() and path.suffix!='.zip': z.write(path,path.name)
    print(json.dumps(dict(passed=True, release=RELEASE, distanceM=nearest, output=str(OUT))), flush=True)

if __name__=='__main__':
    main()
