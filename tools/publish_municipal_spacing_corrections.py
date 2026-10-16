"""Publish only verified improvements, explicitly retaining unresolved legacy exceptions."""
import json
import zipfile

import geopandas as gpd
import pandas as pd

import audit_municipal_street_reach as audit
import build_final_municipal_axis_release as builder
import finalize_axis_publication as finalize
import study_current_municipal_nodes as study_module
import validate_final_municipal_axis_release as independent
from review_police_verified_main_roads import candidates_from_shared_vertices
from study_municipal_spacing_400 import OUT as STUDY, RETAINED, bounded_routes, fixed_road_associations, MINIMUM, TOL

ROOT = builder.ROOT
RELEASE_ID = 'MUNICIPALES_CORRECCIONES_400M_REV2_20261016'
OUT = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE_ID
AUTHORIZATION = ('Arreglar los casos señalados y publicar. Conservar MUN-028,035,040,046; '
                 'MUN-039 en 9 de Octubre x Santa Marta. Mantener Macaji100. '
                 'Las incompatibilidades se documentan, no se declara cumplimiento global inexistente.')


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')


def refresh_public_movements():
    """Present movements against the last public release, including the Santa Marta step."""
    baseline = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/MUNICIPALES_NODOS_PRIORITARIOS_20261016/ESCENARIO_FINAL_183.gpkg'
    before = gpd.read_file(baseline, layer='PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    after = gpd.read_file(OUT / 'ESCENARIO_FINAL_183.gpkg', layer='PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    rows = pd.read_csv(OUT / 'MOVIMIENTOS_MUNICIPALES_24.csv')
    for i, row in rows.iterrows():
        old, new = before.loc[row.ID_PROPUESTA].geometry, after.loc[row.ID_PROPUESTA].geometry
        for field, value in [('X_ANTES', old.x), ('Y_ANTES', old.y), ('X_PROPUESTO', new.x),
                             ('Y_PROPUESTO', new.y), ('DESPLAZAMIENTO_M', old.distance(new))]:
            rows.at[i, field] = value
    rows.to_csv(OUT / 'MOVIMIENTOS_MUNICIPALES_24.csv', index=False, encoding='utf-8-sig')
    assert int((rows.DESPLAZAMIENTO_M > .001).sum()) == 17
    historical = OUT / 'VALIDACION_TRASLADO_MUN039.json'
    if historical.exists():
        historical.rename(OUT / 'HISTORICO_VALIDACION_TRASLADO_MUN039.json')
    states = after.loc[after.GRUPO.eq('RED_ESTRUCTURAL'), 'ESTADO_VALIDACION'].value_counts().to_dict()
    save(OUT / 'VALIDACION_ESTADOS.json', {'release': RELEASE_ID, 'municipalValidationStates': states,
         'sourcePackageSha256': builder.digest(OUT / 'ESCENARIO_FINAL_183.gpkg'),
         'global400mCompliance': False, 'pendingSpacing': ['MUN-029', 'MUN-041']})
    with zipfile.ZipFile(OUT / 'ENTREGA_POLICIA_KDE.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.iterdir()):
            if path.is_file() and path.suffix != '.zip':
                archive.write(path, path.name)


def main():
    assert not OUT.exists()
    active = json.loads((ROOT / 'sig-bridge-active.json').read_text())
    base = ROOT / active['root'] / 'ESCENARIO_FINAL_183.gpkg'
    read = lambda layer: gpd.read_file(base, layer=layer).to_crs(32717)
    report = json.loads((STUDY / 'RESULTADOS.json').read_text(encoding='utf-8'))
    assert report['status'] == 'CORRECCIONES_PARCIALES_FACTIBLES_NO_APLICADAS'
    assert report['baseRelease'] == active['releaseId']
    target = gpd.read_file(STUDY / 'ESTUDIO_24_NODOS.gpkg', layer='EJES_PRIORITARIOS')
    old = read('PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    roads = gpd.read_file(builder.ROADS).to_crs(32717)
    nodes = candidates_from_shared_vertices(roads, read('PLATAFORMAS_TERRITORIALES').geometry.union_all(), require_principal=False)
    by_point = {(c['point'].x, c['point'].y): c for c in nodes}
    movements = {r['ID_PROPUESTA']: r for r in report['movements']}
    for row in target.itertuples():
        if row.ID_PROPUESTA not in movements:
            assert row.ID_PROPUESTA in RETAINED
            node = by_point[(row.geometry.x, row.geometry.y)]
            movements[row.ID_PROPUESTA] = {'ID_PROPUESTA': row.ID_PROPUESTA,
                'ID_CANDIDATO': old.loc[row.ID_PROPUESTA, 'ID_CANDIDATO'],
                'CRUCE': ' x '.join(node['roads']), 'VIA_PRINCIPAL': bool(node['principal']),
                'DESPLAZAMIENTO_M': 0., 'PENDIENTE_SEPARACION_400M': False,
                'X_ANTES': row.geometry.x, 'Y_ANTES': row.geometry.y,
                'X_PROPUESTO': row.geometry.x, 'Y_PROPUESTO': row.geometry.y}
    local = {key: r['CRUCE'] for key, r in movements.items() if not r['VIA_PRINCIPAL']}
    plan = dict(report)
    plan.update(scenario={'movements': list(movements.values())},
                localExceptions=[r for r in movements.values() if not r['VIA_PRINCIPAL']])
    fixed = [(r.ID_CAMARA, r.geometry, False) for r in read('CAMARAS_EXISTENTES_103_FINAL').itertuples()]
    fixed += [(r.ID_PROPUESTA, r.geometry, False) for r in read('PROPUESTA_MUNICIPAL_50_FINAL').loc[lambda f: ~f.GRUPO.eq('RED_ESTRUCTURAL')].itertuples()]
    fixed += [(r.ID_POLICIA, r.geometry, False) for r in read('PROPUESTA_POLICIA_30_FINAL').itertuples()]
    audit.OUT = STUDY
    road_audit = audit.audit_scenario('EJES_PRIORITARIOS', target, fixed, audit.road_catalog(roads), by_point)
    plan['selectionLinkCount'] = road_audit['camerasWithPotentialSameAxisLink']
    save(STUDY / 'PLAN_PUBLICACION.json', plan)
    # The established builder reads RESULTADOS.json; preserve the original optimizer receipt separately.
    save(STUDY / 'RESULTADO_OPTIMIZADOR.json', report)
    save(STUDY / 'RESULTADOS.json', plan)
    builder.REVIEW, builder.OUT, builder.RELEASE_ID, builder.AUTHORIZATION = STUDY, OUT, RELEASE_ID, AUTHORIZATION
    builder.main(approved_local=local)
    package = OUT / 'ESCENARIO_FINAL_183.gpkg'
    municipal = gpd.read_file(package, layer='PROPUESTA_MUNICIPAL_50_FINAL')
    changed = [r.ID_PROPUESTA for r in municipal.itertuples() if not r.geometry.equals(old.loc[r.ID_PROPUESTA].geometry)]
    assert len(changed) == report['movedCount']
    assert not set(changed) & RETAINED
    pending = report['unresolvedRetainedSpacing']
    for i, row in municipal.loc[municipal.GRUPO.eq('RED_ESTRUCTURAL')].iterrows():
        key = row.ID_PROPUESTA
        if key in pending:
            municipal.at[i, 'ESTADO_VALIDACION'] = 'PENDIENTE_SEPARACION_400M'
            note = 'Ubicacion anterior conservada: incompatible con separacion400m y Macaji100 en el catalogo revisado. NO se declara resuelta.'
        elif key in RETAINED:
            municipal.at[i, 'ESTADO_VALIDACION'] = 'UBICACION_CONSERVADA_POR_USUARIO'
            note = 'Ubicacion expresamente conservada por el usuario. No implica cumplimiento global de separacion400m.'
        else:
            municipal.at[i, 'ESTADO_VALIDACION'] = 'CRUCE_400M_REFERENCIA_VIAL'
            note = 'Separacion minima400m evaluada sobre las vias documentadas; no certifica vision real.'
        if key in local:
            note += ' Cruce local documentado para conservar Macaji100: ' + local[key] + '.'
        municipal.at[i, 'OBSERVACION_MANUAL'] = note
        municipal.at[i, 'JUSTIFICACION'] = 'Ubicacion en ' + row.INTERSECCION_O_NODO + '. ' + note
    records = lambda f: [(r.geometry, builder.clean({k: v for k, v in r._asdict().items() if k not in ('Index', 'geometry')})) for r in f.itertuples()]
    builder.save_layer(package, 'PROPUESTA_MUNICIPAL_50_FINAL', records(municipal), OUT)
    existing = gpd.read_file(package, layer='CAMARAS_EXISTENTES_103_FINAL')
    police = gpd.read_file(package, layer='PROPUESTA_POLICIA_30_FINAL')
    builder.save_layer(package, 'ESCENARIO_FINAL_183',
        [(g, {**p, 'ID_EQUIPO': p['ID_CAMARA'], 'GRUPO_ESCENARIO': 'EXISTENTE'}) for g, p in records(existing)] +
        [(g, {**p, 'ID_EQUIPO': p['ID_PROPUESTA'], 'GRUPO_ESCENARIO': 'MUNICIPAL_PROPUESTA'}) for g, p in records(municipal)] +
        [(g, {**p, 'ID_EQUIPO': p['ID_POLICIA'], 'GRUPO_ESCENARIO': 'POLICIA_PROPUESTA'}) for g, p in records(police)], OUT)
    gaps = json.loads((OUT / 'coverage-inputs/RESULTADOS.json').read_text(encoding='utf-8'))
    gaps['metadata']['sourceHashes'][str(package)] = builder.digest(package)
    text = json.dumps(gaps, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    (OUT / 'coverage-inputs/RESULTADOS.json').write_text(text, encoding='utf-8')
    (OUT / 'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = '+text+';\n', encoding='utf-8')
    study_module.PACKAGE = base
    context = study_module.Study()
    catalog = audit.road_catalog(roads)
    checked = []
    for row in municipal.loc[municipal.ID_PROPUESTA.isin(changed)].itertuples():
        others = [(r.ID_CAMARA, r.geometry) for r in existing.itertuples()]
        others += [(r.ID_POLICIA, r.geometry) for r in police.itertuples()]
        others += [(r.ID_PROPUESTA, r.geometry) for r in municipal.itertuples() if r.ID_PROPUESTA != row.ID_PROPUESTA]
        associations, matched, association_rows = fixed_road_associations(context, others, catalog)
        node = by_point[(row.geometry.x, row.geometry.y)]
        from review_police_verified_main_roads import normalized
        violations = []
        for name in {normalized(n) for n in node['roads']}:
            distances = bounded_routes(catalog[name], (row.geometry.x, row.geometry.y))
            for key, a, b, da, db in associations[name]:
                distance = min(distances.get(a, float('inf')) + da, distances.get(b, float('inf')) + db)
                if distance < MINIMUM - TOL:
                    violations.append((key, distance, name))
        assert not violations, (row.ID_PROPUESTA, violations)
        assert not [key for key, p in others if key not in matched and row.geometry.distance(p) < MINIMUM - TOL]
        checked.append(row.ID_PROPUESTA)
    independent.OUT, independent.REVIEW, independent.PREVIOUS = OUT, STUDY, base
    independent.main(expected_local=local)
    published_before = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/MUNICIPALES_NODOS_PRIORITARIOS_20261016/ESCENARIO_FINAL_183.gpkg'
    public_municipal = gpd.read_file(published_before, layer='PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    changed_public = [r.ID_PROPUESTA for r in municipal.itertuples() if not r.geometry.equals(public_municipal.loc[r.ID_PROPUESTA].geometry)]
    proof = {'passed': True, 'changedVsPriorPublic': changed_public, 'changedVsMUN039Release': changed,
             'relocatedSameAxis400mChecked': checked, 'explicitlyRetained': sorted(RETAINED),
             'pendingSpacing': pending, 'localJunctionExceptions': local,
             'global400mCompliance': False, 'giAndKdeUnchanged': True,
             'strict400mMacajiUncoverableInReviewedCatalogM': report['strict400mMacajiUncoverableInCatalogM'],
             'fixedOtherCameras': 183 - len(changed_public),
             'authorization': AUTHORIZATION, 'crs': 'EPSG:32717'}
    save(OUT / 'VALIDACION_CORRECCIONES_400M.json', proof)
    validation = json.loads((OUT / 'VALIDACION.json').read_text())
    validation.update(approvedException={'authorization': AUTHORIZATION, 'localJunctions': local,
                     'retainedByUser': sorted(RETAINED), 'unresolvedSpacing': pending}, spacingReview=proof)
    save(OUT / 'VALIDACION.json', validation)
    results = json.loads((OUT / 'RESULTADOS.json').read_text())
    results.update(status='CORRECCIONES_VERIFICADAS_CON_EXCEPCIONES_PENDIENTES', bridge=validation, spacingReview=proof)
    save(OUT / 'RESULTADOS.json', results)
    pd.DataFrame(list(movements.values())).to_csv(OUT / 'MOVIMIENTOS_MUNICIPALES_24.csv', index=False, encoding='utf-8-sig')
    (OUT / 'INFORME_FINAL.md').write_text(
        '# Correcciones de proximidad municipales\n\n'
        'Se trasladan '+str(len(changed_public))+' municipales respecto a la ultima publicacion, incluida MUN-039 en Santa Marta. '
        'Las103existentes,26municipalesrurales/LasAbras y30policiales conservan geometria.\n\n'
        'MUN-028,035,040,046 quedan expresamente fijas. MUN-039 queda en9deOctubre xSantaMarta.\n\n'
        'Macaji100; Anillo '+str(round(report['municipal'][study_module.RING]['pct'],2))+'%; Ciclovias '+str(round(report['municipal'][study_module.CYCLE]['pct'],2))+'%. Cobertura potencial por union real de radios200m, no vision certificada.\n\n'
        'NO hay cumplimiento global de400m: las fijas solicitadas conservan proximidades y '+', '.join(pending)+' permanecen pendientes '
        'para no perder Macaji100. El catalogo estricto deja '+str(round(report['strict400mMacajiUncoverableInCatalogM'],2))+'m sin cubrir incluso usando todos los candidatos admisibles.\n\n'
        'Cruces locales necesarios: '+str(local)+'. Referencias viales de existentes documentadas sin mover inventario.\n', encoding='utf-8')
    finalize.OUT, finalize.PREVIOUS, finalize.AUTHORIZATION = OUT, published_before, AUTHORIZATION
    finalize.main()
    refresh_public_movements()
    print(json.dumps(proof, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
