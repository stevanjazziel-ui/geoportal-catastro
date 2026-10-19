"""Finish metadata and independent checks for the MUN-035/040 local preview."""
import json
import sqlite3
import sys
from pathlib import Path

import pyogrio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sig-bridge'))
from bridge.store import Store, read_json, write_json, digest, require, clean

RELEASE = 'MUN035_040_GUAYAQUIL_ESMERALDAS_20261018'
OUT = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE

def read(path, layer):
    return pyogrio.read_dataframe(path, layer=layer).to_crs(32717)

def main():
    store = Store()
    require(store.web.name == 'MUN041_PRIMERA_CONSTITUYENTE_BRASIL_20261018', 'Unexpected baseline')
    package = OUT / 'ESCENARIO_FINAL_183.gpkg'
    base = read(store.base, 'PROPUESTA_MUNICIPAL_50_FINAL')
    after = read(package, 'PROPUESTA_MUNICIPAL_50_FINAL')
    changed = set(after.loc[after.geometry.to_wkb().to_numpy() != base.geometry.to_wkb().to_numpy(), 'ID_PROPUESTA'])
    require(changed == {'MUN-035', 'MUN-040'}, f'Unexpected municipal changes: {changed}')
    for layer in ['CAMARAS_EXISTENTES_103_FINAL', 'PROPUESTA_POLICIA_30_FINAL']:
        require(read(store.base, layer).geometry.to_wkb().tolist() == read(package, layer).geometry.to_wkb().tolist(), f'{layer} changed')
    previous_gaps = read_json(store.web / 'coverage-inputs/RESULTADOS.json')
    gaps = read_json(OUT / 'coverage-inputs/RESULTADOS.json')
    overlay = {row['id']: row for row in previous_gaps['inventoryCameraOverlay']}
    for row in gaps['inventoryCameraOverlay']:
        row.update(overlay[row['id']])
    for key in ['inventoryGeolocation', 'sourceInventory']:
        gaps['metadata'][key] = previous_gaps['metadata'][key]
    gaps['inventoryCoverage']['metadata'].update(previous_gaps['inventoryCoverage']['metadata'])
    gaps['metadata']['localRevision'] = RELEASE
    write_json(OUT / 'coverage-inputs/RESULTADOS.json', gaps)
    payload = json.dumps(clean(gaps), ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    (OUT / 'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = ' + payload + ';\n', encoding='utf-8')
    (OUT / 'coverage-inputs/riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = ' + payload + ';\n', encoding='utf-8')
    validation = read_json(OUT / 'VALIDACION.json')
    corridors = read_json(OUT / 'CORRIDOR_COVERAGE_200M.json')
    m = corridors['scenarios']['B']['corridors']['BOULEVARD_MACAJI_BELLAVISTA']
    require(abs(m['coveredPct'] - 97.74207666073576) < 1e-8 and m['uncoveredM'] > 215, 'Unexpected Macaji result')
    waiver = dict(criterion='Macaji municipal coverage minimum 100%', userApproved=True,
                  approvedOutcomePct=m['coveredPct'], uncoveredM=m['uncoveredM'],
                  note='Usuario selecciona mantener los dos cruces solicitados aceptando la reduccion de Macaji.')
    require(len(validation['publishBlocks']) == 1 and 'BOULEVARD_MACAJI_BELLAVISTA' in validation['publishBlocks'][0],
            'Unexpected validation blocker')
    validation['waivedBlocks'] = list(validation['publishBlocks'])
    validation['publishBlocks'] = []
    validation['approvedWaivers'] = [waiver]
    validation['status'] = 'READY_WITH_USER_APPROVED_EXCEPTION'
    write_json(OUT / 'VALIDACION.json', validation)
    exceptions = list(read_json(store.web / 'RESULTADOS.json').get('approvedExceptions', []))
    for camera in ['MUN-035', 'MUN-040']:
        audit = next(row for row in validation['nodeAudit'] if row['id'] == camera)
        exceptions.append(dict(id=camera, camera='existing camera', distanceM=audit['nearestCameraM'], explicitUserDestination=True))
    results = read_json(OUT / 'RESULTADOS.json')
    results.update(status='MUN035_040_PREVIEW_USER_APPROVED', sourcePackage=RELEASE, applied=True, published=False,
                   authorization='Usuario solicita MUN-035 Guayaquil x Gabriel Garcia Moreno y MUN-040 Esmeraldas x Eugenio Espejo; acepta mantener ambos destinos con reduccion de cobertura Macaji y separaciones menores a 400m.',
                   bridge=validation, approvedExceptions=exceptions, pendingUnapplied=[],
                   warnings=list(results.get('warnings', [])) + [
                       f'Excepcion aprobada por usuario: Macaji municipal y escenario completo queda en {m["coveredPct"]:.5f}% ({m["uncoveredM"]:.2f}m sin cubrir), bajo el minimo previo de 100%.',
                       'MUN-035 queda a 114.63m de RIO-036; MUN-040 a 301.91m de RIO-063. Ambas distancias quedan bajo 400m.',
                       'Usuario acepta conservar ambos destinos pese a las distancias menores a 400m. Separacion mutua entre MUN-035 y MUN-040: 527.66m. Esta version sigue sin publicar.'
                   ])
    results.pop('publicRelease', None)
    write_json(OUT / 'RESULTADOS.json', results)
    receipt = read_json(OUT / 'APROBACION_Y_FUENTES.json')
    receipt.update(published=False, authorization=results['authorization'])
    receipt['approvedWaivers'] = [waiver]
    receipt.pop('publicRelease', None)
    write_json(OUT / 'APROBACION_Y_FUENTES.json', receipt)
    corridors['metadata']['sourcePackage'] = RELEASE
    write_json(OUT / 'CORRIDOR_COVERAGE_200M.json', corridors)
    write_json(OUT / 'VERIFICACION_INDEPENDIENTE.json', dict(
        passed=True, status='READY_WITH_USER_APPROVED_EXCEPTION', release=RELEASE, published=False,
        changedMunicipal=sorted(changed), otherMunicipal48Fixed=True,
        existing103Fixed=True, police30Fixed=True, macajiMinimumPreserved=False,
        macajiMunicipalPct=m['coveredPct'], macajiUncoveredM=m['uncoveredM'],
        approvedWaiver=waiver, nodeAudit=validation['nodeAudit']))
    (OUT / 'INFORME_FINAL.md').write_text(
        '# Revision MUN-035 y MUN-040\n\n'
        '- MUN-035: Guayaquil x Gabriel Garcia Moreno; movimiento 470.58m; RIO-036 a 114.63m.\n'
        '- MUN-040: Esmeraldas x Eugenio Espejo; movimiento 245.96m; RIO-063 a 301.91m.\n'
        '- Separacion entre ambos nuevos destinos: 527.66m.\n\n'
        f'El usuario aprueba mantener ambos cruces aceptando que la cobertura de Macaji en escenario municipal baje de 100% a {m["coveredPct"]:.5f}% y deje {m["uncoveredM"]:.2f}m sin cubrir. Las separaciones menores a 400m tambien quedan documentadas como excepciones expresas. Esta version se entrega localmente y aun no esta publicada.\n\n'
        'Se recalcularon coberturas. Las otras 48 municipales, las 103 existentes y las 30 policiales permanecen fijas. KDE/Gi* no se recalcularon. Los radios son proximidad potencial, no visibilidad optica certificada.\n', encoding='utf-8')
    source_hashes = receipt['baseHashes']
    hashes_match = all(Path(path).exists() and digest(Path(path)) == expected
                       for path, expected in source_hashes.items() if Path(path).name != 'sig-bridge-active.json')
    require(hashes_match, 'Protected camera, KDE, or Gi source changed')
    require(read_json(ROOT / 'sig-bridge-active.json')['releaseId'] == store.web.name, 'Active release changed')
    with sqlite3.connect(package) as db:
        require(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Invalid GeoPackage')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute('PRAGMA journal_mode=DELETE')
    print(json.dumps(dict(passed=True, release=RELEASE, changed=sorted(changed), macajiPct=m['coveredPct'],
                          macajiGapM=m['uncoveredM'], validationBlocks=validation['publishBlocks'],
                          sourceHashesUnchanged=hashes_match), ensure_ascii=False))

if __name__ == '__main__':
    main()
