"""Publish the approved MUN-035/040 scenario and the standalone Macaji layer."""
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pyogrio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sig-bridge'))
from bridge.store import Store, read_json, write_json, require, digest

RELEASE = 'MUN035_040_GUAYAQUIL_ESMERALDAS_20261018'
BASELINE = 'MUN041_PRIMERA_CONSTITUYENTE_BRASIL_20261018'
OUT = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE

def read(path, layer):
    return pyogrio.read_dataframe(path, layer=layer).to_crs(32717)

def main():
    store = Store()
    pointer_path = ROOT / 'sig-bridge-active.json'
    pointer = read_json(pointer_path)
    require(pointer['releaseId'] == BASELINE, 'Active public release changed')
    validation = read_json(OUT / 'VALIDACION.json')
    require(validation['status'] == 'READY_WITH_USER_APPROVED_EXCEPTION' and not validation['publishBlocks'],
            'Approved exception is not recorded')
    require(validation['approvedWaivers'][0]['userApproved'] is True, 'Macaji waiver is not approved')
    proof = read_json(OUT / 'VERIFICACION_INDEPENDIENTE.json')
    require(proof['passed'] and proof['changedMunicipal'] == ['MUN-035', 'MUN-040'], 'Move verification failed')
    require(proof['existing103Fixed'] and proof['police30Fixed'] and proof['otherMunicipal48Fixed'], 'Protected inventory changed')
    package = OUT / 'ESCENARIO_FINAL_183.gpkg'
    require(pyogrio.read_info(package, layer='ESCENARIO_FINAL_183')['features'] == 183, 'Scenario count mismatch')
    old_package = store.web / 'ESCENARIO_FINAL_183.gpkg'
    for layer in ['CAMARAS_EXISTENTES_103_FINAL', 'PROPUESTA_POLICIA_30_FINAL']:
        require(read(package, layer).geometry.to_wkb().tolist() == read(old_package, layer).geometry.to_wkb().tolist(), f'{layer} changed')
    before = read(old_package, 'PROPUESTA_MUNICIPAL_50_FINAL')
    after = read(package, 'PROPUESTA_MUNICIPAL_50_FINAL')
    changed = set(after.loc[after.geometry.to_wkb().to_numpy() != before.geometry.to_wkb().to_numpy(), 'ID_PROPUESTA'])
    require(changed == {'MUN-035', 'MUN-040'}, f'Unexpected municipal changes: {changed}')
    standalone_path = OUT / 'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA/TRAMO_BOULEVARD_MACAJI_BELLAVISTA.gpkg'
    standalone = read(standalone_path, 'BOULEVARD_MACAJI_BELLAVISTA')
    corridor = read(package, 'CORREDORES')
    source = corridor[corridor.CORREDOR.eq('BOULEVARD_MACAJI_BELLAVISTA')].geometry.iloc[0]
    require(len(standalone) == 1 and source.equals_exact(standalone.geometry.iloc[0], 0), 'Standalone Macaji layer differs from the corridor')
    results = read_json(OUT / 'RESULTADOS.json')
    require(results['published'] is False and results['bridge']['approvedWaivers'], 'Results do not record user waiver')
    if 'MUN-041' in proof.get('changedMunicipal', []):
        raise RuntimeError('Unexpected revision scope')
    receipt = read_json(OUT / 'APROBACION_Y_FUENTES.json')
    protected = {path: expected for path, expected in receipt['baseHashes'].items() if Path(path).name != 'sig-bridge-active.json'}
    require(all(Path(path).exists() and digest(Path(path)) == expected for path, expected in protected.items()), 'Protected source hash mismatch')
    for name in ['RESULTADOS.json', 'VALIDACION.json', 'VERIFICACION_INDEPENDIENTE.json', 'APROBACION_Y_FUENTES.json']:
        data = read_json(OUT / name)
        data.update(published=True, publicRelease=RELEASE)
        if name == 'RESULTADOS.json':
            data['bridge']['published'] = True
        write_json(OUT / name, data)
    pointer.update(root='./data/seguridad-riobamba/SIG_BRIDGE_RELEASES/' + RELEASE + '/', releaseId=RELEASE)
    write_json(pointer_path, pointer)
    archive_path = OUT / 'ENTREGA_POLICIA_KDE.zip'
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in OUT.rglob('*'):
            if path.is_file() and path != archive_path:
                archive.write(path, path.relative_to(OUT))
    with sqlite3.connect(package) as db:
        require(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Invalid scenario GeoPackage')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute('PRAGMA journal_mode=DELETE')
    print(json.dumps(dict(published=True, release=RELEASE, changedMunicipal=sorted(changed),
                          standaloneMacajiLayerFeatures=len(standalone), zipBytes=archive_path.stat().st_size), ensure_ascii=False))

if __name__ == '__main__':
    main()
