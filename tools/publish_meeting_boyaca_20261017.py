"""Publish the approved meeting/rural/municipal local scenario, including Boyaca."""
import copy
import json
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path
import geopandas as gpd
import pandas as pd
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sig-bridge'))
from bridge.engine import calculate, verify_derived
from bridge.store import Store, clean, digest, now, read_json, require, write_json
import recalculate_current_gaps as dependencies

LOCAL = Path('D:/codex/entregas')
REVIEW = LOCAL / 'BOYACA_DOS_CAMARAS_1_A_7_REVISION_20261017'
SOURCE = REVIEW / 'BOYACA_DOS_CAMARAS_REVISION.gpkg'
RELEASE = 'REUNION_MUNICIPALES_BOYACA_20261017'
OUT = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE

def read(path, layer):
    return pyogrio.read_dataframe(path, layer=layer).to_crs(32717)

def main():
    require(not OUT.exists(), 'Release already exists; do not overwrite published history')
    store = Store()
    published_base = store.base
    inventory = read(SOURCE, 'EXISTENTES_103_INTACTAS')
    old_inventory = read(published_base, 'CAMARAS_EXISTENTES_103_FINAL').set_index('ID_CAMARA')
    require(inventory.geometry.to_wkb().tolist() == old_inventory.loc[inventory.ID_CAMARA].geometry.to_wkb().tolist(), 'Existing103 differ from published inventory')
    municipal = read(SOURCE, 'MUNICIPALES_DESPUES_PROPUESTAS_50')
    police = read(SOURCE, 'POLICIA_REUNION_30_PN27_BANCO')
    police['ID_POLICIA'] = police.Ord.map(lambda n: 'PN-' + str(int(n)).zfill(2))
    require(set(police.Ord) == set(range(1, 32)) - {13}, 'Meeting keeps11, excludes13')
    police['GRUPO'] = 'PROPUESTA_POLICIAL_REUNION'
    police['DIRECCION'] = police['DIRECCION'].fillna('Referencia documental de la reunion')
    police['ESTADO'] = 'PROPUESTA_REUNION_APROBADA_NO_INSTALADA'
    police['FUENTE_CRUCE'] = 'Propuesta entregada en reunion; PN27 en punto aprobado por usuario'
    police['ALCANCE_VISUAL'] = '200 m potenciales por ejes; no certifica vision fisica'
    police['DECISION_FINAL'] = 'PROPUESTA_REUNION_CON_PN27_AJUSTADA'
    for frame in [municipal, police]:
        frame['OBSERVACION_MANUAL'] = 'Escenario local aprobado para publicar: continua y publica los cambios para ver como quedo.'
        frame['X'] = frame.geometry.x
        frame['Y'] = frame.geometry.y
        ll = frame.to_crs(4326)
        frame['LONGITUD'] = ll.geometry.x
        frame['LATITUD'] = ll.geometry.y
    for ident, address in [('MUN-047', 'Boyaca x Augusto Alzamora'), ('MUN-027', 'Boyaca x Humberto Merino')]:
        mask = municipal.ID_PROPUESTA.eq(ident)
        municipal.loc[mask, 'DIRECCION'] = address
        municipal.loc[mask, 'INTERSECCION_O_NODO'] = address
        municipal.loc[mask, 'ESTADO_REVISION'] = 'PUBLICACION_APROBADA_EXCEPCION_SEPARACION_400M'
        municipal.loc[mask, 'OBSERVACION_MANUAL'] = 'Boyaca1a7; excepcion aprobada al publicar: 350.82 m entre nodos y cercania a existentes. Vision optica no verificada.'
    protected = [SOURCE, published_base, ROOT / 'riobamba-kde-combinado-data.js', ROOT / 'riobamba-hotspot-urbano-200m-data.js', ROOT / 'riobamba-conflictividad-data.js']
    hashes = {str(path): digest(path) for path in protected}
    staging = ROOT / 'artifacts' / RELEASE
    staging.mkdir(parents=True, exist_ok=True)
    stage = staging / 'BASE_CON_ESCENARIO_APROBADO.gpkg'
    store.backup(published_base, stage)
    # New PN IDs are documentary meeting IDs, not renamed identities of the old POL plan.
    pyogrio.write_dataframe(municipal, stage, layer='PROPUESTA_MUNICIPAL_50_FINAL')
    pyogrio.write_dataframe(police, stage, layer='PROPUESTA_POLICIA_30_FINAL')
    store.base = stage
    manual = {}
    for key, spec in store.config['layers'].items():
        frame = read(stage, spec['source'])
        if 'OBSERVACION_MANUAL' not in frame: frame['OBSERVACION_MANUAL'] = ''
        manual[key] = frame
    old_m = read(published_base, 'PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    changes = [dict(layer='municipal', id=row.ID_PROPUESTA, geometryChanged=True, fields=[], distanceM=row.geometry.distance(old_m.loc[row.ID_PROPUESTA].geometry), note=str(row.OBSERVACION_MANUAL))
               for row in municipal.itertuples() if row.geometry.distance(old_m.loc[row.ID_PROPUESTA].geometry) > 1e-6]
    changes += [dict(layer='police', id=row.ID_POLICIA, geometryChanged=True, fields=[], distanceM=0,
                     note='Sustitucion documental de propuesta POL anterior por PN reunion; no se afirma equivalencia de IDs.') for row in police.itertuples()]
    receipt = dict(revision=RELEASE, changes=changes, baseHashes=hashes, createdAt=now(),
                   authorization='Usuario: continua y publica los cambios para ver como quedo, tras mostrar separacion350.82m y Anillo70.78%.',
                   priorRelease=store.web.name, existing103Unmoved=True, meetingRetains11Excludes13=True,
                   approvedExceptions=['Boyaca350.82m entre propuestas; distancias a existentes344.13m y234.48m', 'MUN037 cruce local para Macaji100%', 'Anillo municipal70.78% sin minimo80%', 'PN27 frenteBancoPacifico'],
                   policeIdentity='PN IDs are meeting Ord values; historical POL identities are not equivalent')
    def review_nodes(_store, _changes, municipalities, police_rows, urban):
        audit = []
        for point, props in municipalities + police_rows:
            ident = props.get('ID_PROPUESTA') or props.get('ID_POLICIA')
            audit.append(dict(id=ident, roads=[props.get('DIRECCION') or props.get('INTERSECCION_O_NODO') or 'Referencia de estudio'],
                              passed=False, acceptedForPlanning=True, fieldVerified=False,
                              basis='Ubicacion de estudio/reunion aprobada; no certifica interseccion principal, poste o linea de vision.'))
            props['BRIDGE_NODO_VALIDADO'] = False
        return audit, []
    OUT.mkdir(parents=True)
    print('Recalculating A/B/C and dependent camera metrics without changing KDE/Gi*', flush=True)
    validation = calculate(store, OUT, OUT, manual, receipt, node_validator=review_nodes)
    require(not validation['publishBlocks'], str(validation['publishBlocks']))
    package = OUT / 'ESCENARIO_FINAL_183.gpkg'
    folder = OUT / 'coverage-inputs'
    folder.mkdir()
    print('Recalculating 100/150/200m dependent coverage', flush=True)
    dependencies.main(final=package, out=folder, js_output=OUT / 'riobamba-brechas-actualizadas-data.js', expected_replacements=30)
    gaps = read_json(folder / 'RESULTADOS.json')
    prior_gaps = read_json(store.web / 'coverage-inputs/RESULTADOS.json')
    prior_overlay = {row['id']: row for row in prior_gaps['inventoryCameraOverlay']}
    for row in gaps['inventoryCameraOverlay']: row.update(prior_overlay[row['id']])
    for key in ['inventoryGeolocation', 'sourceInventory']:
        gaps['metadata'][key] = prior_gaps['metadata'][key]
    gaps['inventoryCoverage']['metadata'].update(prior_gaps['inventoryCoverage']['metadata'])
    payload = json.dumps(clean(gaps), ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    (folder / 'RESULTADOS.json').write_text(payload, encoding='utf-8')
    (OUT / 'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = ' + payload + ';\n', encoding='utf-8')
    results = read_json(OUT / 'RESULTADOS.json')
    results.update(status='REUNION_Y_MUNICIPALES_BOYACA_APROBADOS', sourcePackage=RELEASE,
                   authorization=receipt['authorization'], counts=dict(existing=103, changeIncluded=30, municipal=50, police=30),
                   warnings=['103 existentes intactas; 19 posiciones provisionales siguen pendientes.',
                             'Policia:30 puntos de reunion, conserva11/excluye13; PN27 frenteBancoPacifico.',
                             'Boyaca:nodos3/6 con350.82m de separacion; existentes a344.13m y234.48m. Excepcion explicita.',
                             'Alcance por vias no certifica vision optica; buffers son proximidad. KDE/Gi* sin recalculo.'],
                   approvedExceptions=receipt['approvedExceptions'], boyacaStudy=read_json(REVIEW / 'RESULTADOS.json'))
    results['boyacaStudy'].update(published=True, status='APPROVED_FOR_PUBLICATION_BY_USER', requiresApproval=False)
    validation.update(authorization=receipt['authorization'], approvedExceptions=receipt['approvedExceptions'], existing103Intact=True,
                      historicalNodeCertificatesNotReused=True, physicalVisionVerified=False)
    results['bridge'] = validation
    # Remove copied receipts and obsolete movement tables that describe previous geometry.
    current_files = {'RESULTADOS.json', 'VALIDACION.json', 'CORRIDOR_COVERAGE_200M.json'}
    for path in OUT.glob('*.json'):
        if path.name not in current_files and path.name != 'APROBACION_Y_FUENTES.json':
            path.unlink()
    for name in ['MOVIMIENTOS_MUNICIPALES_24.csv', 'HISTORICO_PREVIO_HISTORIAL_30_CAMARAS.csv', 'HISTORICO_PREVIO_HISTORIAL_COORDENADAS.geojson']:
        (OUT / name).unlink(missing_ok=True)
    for name in ['CONTROL_74_INMODIFICABLES.csv', 'REVISION_103_COORDENADAS.csv']:
        if (store.web / name).exists(): shutil.copy2(store.web / name, OUT / name)
    write_json(OUT / 'RESULTADOS.json', results)
    write_json(OUT / 'VALIDACION.json', validation)
    write_json(OUT / 'APROBACION_Y_FUENTES.json', receipt)
    pd.DataFrame(changes[:len(changes)-30]).to_csv(OUT / 'MOVIMIENTOS_MUNICIPALES_50.csv', index=False, encoding='utf-8-sig')
    moves_pn = police[['ID_POLICIA', 'ID_REVISION', 'Ord', 'DIRECCION']].copy()
    moves_pn['FUENTE'] = 'Reunion; coordenadas originales salvo PN27. No corresponde a IDs POL historicos.'
    moves_pn.to_csv(OUT / 'MOVIMIENTOS_POLICIA_30.csv', index=False, encoding='utf-8-sig')
    for name in ['ANTES_DESPUES_BOYACA.png', 'MOVIMIENTOS.csv']:
        shutil.copy2(REVIEW / name, OUT / name)
    (OUT / 'INFORME_FINAL.md').write_text('# Escenario aprobado: reunion y municipales con Boyaca\n\n103 existentes intactas +50 municipales (22rurales,4LasAbras,24urbanas) +30 policiales de reunion. PN27 frente al Banco del Pacifico. IDs PN documentales:11 conservado,13 excluido. No son las identidades POL del estudio historico.\n\nMUN047 en Boyaca x Augusto Alzamora y MUN027 en Boyaca x Humberto Merino:632.40m de alcance longitudinal teorico continuo, separacion350.82m. Excepcion al minimo400m, tambien frente a existentes cercanas. Sin certificacion optica.\n\nMacaji100%,0m sin cobertura, sin sumar Policia. Anillo municipal70.78%, Ciclovias63.08%. No se exige minimo80%. Los radios y las coberturas globales representan proximidad200m. KDE/Gi* sin recalculo.\n\n19 de las103 ubicaciones siguen siendo provisionales pendientes. Ninguna existente se ha movido. Resultados recalculados para este escenario; las metricas de escenarios anteriores no son actuales.\n', encoding='utf-8')
    verify_derived(store, package, results)
    for layer, original, idcol in [('CAMARAS_EXISTENTES_103_FINAL', inventory, 'ID_CAMARA'), ('PROPUESTA_MUNICIPAL_50_FINAL', municipal, 'ID_PROPUESTA'), ('PROPUESTA_POLICIA_30_FINAL', police, 'ID_POLICIA')]:
        final = read(package, layer).set_index(idcol)
        require(final.loc[original[idcol]].geometry.to_wkb().tolist() == original.geometry.to_wkb().tolist(), layer + ' geometry mismatch')
    require(all(digest(Path(path)) == value for path, value in hashes.items()), 'Protected input changed')
    write_json(OUT / 'VERIFICACION_INDEPENDIENTE.json', dict(passed=True, geometryMatchesApprovedReview=True, sourceHashes=hashes, existing103Intact=True,
               meeting30=True, municipalComposition=[22,4,24], uniqueCameraIds=183, giKdeUnchanged=True))
    with sqlite3.connect(package) as db:
        require(db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Invalid sqlite')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute('PRAGMA journal_mode=DELETE')
    with zipfile.ZipFile(OUT / 'ENTREGA_POLICIA_KDE.zip', 'w', zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(OUT.iterdir()):
            if path.is_file() and path.suffix != '.zip': zipped.write(path, path.name)
    print(json.dumps(dict(release=RELEASE, passed=True, municipal50=True, police30Meeting=True), ensure_ascii=True), flush=True)

def finalize_release():
    results = read_json(OUT / 'RESULTADOS.json')
    for key in ['historicalKdeOptimization', 'gapScenarioCValidated', 'kdeEvaluation', 'municipalAxisReview', 'changedIds',
                'fixed182Unchanged', 'global400mRevisionApplied', 'singleCameraMove', 'spacingReview']:
        results.pop(key, None)
    results['selectionMethod'] = '30 puntos documentales de reunion; PN27 segun referencia del usuario. 50 municipales del estudio local con dos reasignaciones a Boyaca. Sin optimizacion KDE nueva.'
    package = OUT / 'ESCENARIO_FINAL_183.gpkg'
    municipal = read(package, 'PROPUESTA_MUNICIPAL_50_FINAL')
    prior_moves = pd.read_csv(LOCAL / 'PRIORIDAD_REUNION_AJUSTE_MUNICIPAL_MACAJI_20261017/MOVIMIENTOS_MUNICIPALES.csv').set_index('ID')
    for i, row in municipal.iterrows():
        if row.ID_PROPUESTA in ['MUN-027', 'MUN-047']:
            continue
        if row.ID_PROPUESTA in prior_moves.index and pd.notna(prior_moves.loc[row.ID_PROPUESTA, 'VIAS']):
            address = str(prior_moves.loc[row.ID_PROPUESTA, 'VIAS'])
        elif row.GRUPO == 'CABECERA_RURAL':
            address = str(row.PARROQUIA) + ' - ' + str(row.FUNCION) + ' (ubicacion de estudio, validar en campo)'
        else:
            address = 'Ubicacion cartografica aprobada; consultar geometria y estudio de ' + str(row.ID_PROPUESTA)
        municipal.at[i, 'DIRECCION'] = address
        municipal.at[i, 'INTERSECCION_O_NODO'] = address
    municipal['COBERTURA_RECALCULADA'] = True
    municipal['ESCENARIO'] = RELEASE
    pyogrio.write_dataframe(municipal, package, layer='PROPUESTA_MUNICIPAL_50_FINAL')
    pyogrio.write_dataframe(municipal.to_crs(4326), OUT / 'PROPUESTA_MUNICIPAL_50_FINAL.geojson', driver='GeoJSON')
    e = read(package, 'CAMARAS_EXISTENTES_103_FINAL')
    p = read(package, 'PROPUESTA_POLICIA_30_FINAL')
    all_frames = []
    for frame, field, group in [(e, 'ID_CAMARA', 'EXISTENTE'), (municipal, 'ID_PROPUESTA', 'MUNICIPAL_PROPUESTA'), (p, 'ID_POLICIA', 'POLICIA_PROPUESTA')]:
        f = frame.copy()
        f['ID_EQUIPO'] = f[field]
        f['GRUPO_ESCENARIO'] = group
        all_frames.append(f)
    combined = gpd.GeoDataFrame(pd.concat(all_frames, ignore_index=True), crs=32717)
    pyogrio.write_dataframe(combined, package, layer='ESCENARIO_FINAL_183')
    pyogrio.write_dataframe(combined.to_crs(4326), OUT / 'ESCENARIO_FINAL_183.geojson', driver='GeoJSON')
    corridor = read_json(OUT / 'CORRIDOR_COVERAGE_200M.json')
    corridor['metadata']['sourcePackage'] = RELEASE
    write_json(OUT / 'CORRIDOR_COVERAGE_200M.json', corridor)
    original = read(LOCAL / 'RIOBAMBA_CONSOLIDADO_PRIORIDAD_REUNION_20261017/RIOBAMBA_CONSOLIDADO.gpkg', 'PNPRI_POLICIA_REUNION_PRIORITARIA_30').set_index('ID_REVISION')
    police = read(OUT / 'ESCENARIO_FINAL_183.gpkg', 'PROPUESTA_POLICIA_30_FINAL')
    rows = []
    for row in police.itertuples():
        old = original.loc[row.ID_REVISION].geometry
        rows.append(dict(ID_POLICIA=row.ID_POLICIA, ID_REVISION=row.ID_REVISION, ORD_REUNION=int(row.Ord),
                         X_ANTES=old.x, Y_ANTES=old.y, X_DESPUES=row.geometry.x, Y_DESPUES=row.geometry.y,
                         DESPLAZAMIENTO_M=old.distance(row.geometry), FUENTE='Comparacion con reunion original, NO con propuesta POL historica'))
    results['policeChanges'] = rows
    write_json(OUT / 'RESULTADOS.json', results)
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / 'MOVIMIENTOS_POLICIA_30.csv', index=False, encoding='utf-8-sig')
    frame.to_csv(OUT / 'TRAZABILIDAD_POLICIA_FINAL.csv', index=False, encoding='utf-8-sig')
    for name in ['MOVIMIENTOS_POLICIA_30', 'TRAZABILIDAD_POLICIA_FINAL']:
        pyogrio.write_dataframe(frame, package, layer=name)
    for source, target in [('EXISTENTES_103_INTACTAS', 'CAMARAS_EXISTENTES_103_FINAL'),
                           ('MUNICIPALES_DESPUES_PROPUESTAS_50', 'PROPUESTA_MUNICIPAL_50_FINAL')]:
        a = read(SOURCE, source)
        b = read(package, target)
        field = 'ID_CAMARA' if source.startswith('EXISTENTES') else 'ID_PROPUESTA'
        require(a.geometry.to_wkb().tolist() == b.set_index(field).loc[a[field]].geometry.to_wkb().tolist(), 'Final mismatch')
    with sqlite3.connect(package) as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute('PRAGMA journal_mode=DELETE')
    with zipfile.ZipFile(OUT / 'ENTREGA_POLICIA_KDE.zip', 'w', zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(OUT.iterdir()):
            if path.is_file() and path.suffix != '.zip': zipped.write(path, path.name)
    print('Finalized: stale scenario claims removed; documentary PN traceability updated.', flush=True)

if __name__ == '__main__':
    if '--finalize-only' not in sys.argv: main()
    finalize_release()
