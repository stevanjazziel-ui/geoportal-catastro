"""Apply the approved single relocation; keep the published closure as history."""
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pyogrio
from shapely import STRtree, covers
from shapely.geometry import LineString
from shapely.ops import unary_union

import finalize_police_30 as output
from audit_police_redundancy import Audit, CANDIDATES
from build_police_camera_proposal import (
    ROOT, CLASSES, AREA_EPS, UNPROJECT, sha, pct, parts, records, read_layer,
    coverage_class, scenario_evaluation,
)

SOURCE = ROOT / 'data/seguridad-riobamba/CIERRE_POLICIA_30_FINAL_20261005'
OUT = ROOT / 'data/seguridad-riobamba/REUBICACION_POL20_20261005'
PACKAGE = SOURCE / 'ESCENARIO_FINAL_183.gpkg'
SLOT = 'POL-20'


def main(slot=SLOT, source=SOURCE, destination=OUT, comparison_dir=None,
         selection_label=None, expected_candidate='CAND-POL-01017'):
    SOURCE, OUT, SLOT = Path(source), Path(destination), slot
    PACKAGE = SOURCE / 'ESCENARIO_FINAL_183.gpkg'
    suffix = SLOT.replace('-', '')
    comparison_dir = comparison_dir or ROOT / 'data/seguridad-riobamba/comparacion-pol20-20261005'
    comparison = json.loads((Path(comparison_dir) / 'RESULTADOS.json').read_text(encoding='utf-8'))
    selection = (next(r for r in comparison['complementary'] if r['OPCION'] == selection_label)
                 if selection_label else comparison['nearestPreferable'][0])
    # Only the explicitly approved, previously audited road node is incorporated.
    candidate_id = selection['ID_CANDIDATO']
    assert candidate_id == expected_candidate and selection['MENOR_SOLAPE_SIN_REDUCIR_DV']
    distance_field = 'DIST_DESDE_' + suffix + '_M'
    protected = {str(p): sha(p) for p in SOURCE.iterdir() if p.is_file()}
    protected[str(CANDIDATES)] = sha(CANDIDATES)
    audit = Audit(package=PACKAGE)
    prior = json.loads((SOURCE / 'RESULTADOS.json').read_text(encoding='utf-8'))
    old_points = {p['ID_POLICIA']: g for g, p in audit.official}
    active = dict(audit.active)
    original = active[SLOT]
    active[SLOT] = audit.candidates[candidate_id]
    assert candidate_id not in audit.official_ids
    assert all(active[id]['point'].equals_exact(old_points[id], 0) for id in active if id != SLOT)
    for c in active.values():
        c['origins'] = set(c['props']['INTERSECCION_O_NODO'].split('|'))
    current_props = audit.original_props[SLOT]
    retained = selection['DV_ACTUALES_CONSERVADOS']
    lost_dv = current_props['DV_NUEVOS'] - retained
    gained_dv = selection['EVENTOS_DV_NUEVOS'] - retained
    print('REUBICACION', SLOT, candidate_id, selection[distance_field], flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PACKAGE, OUT / PACKAGE.name)
    for name in ('RADIOS_EXISTENTES_SIMBOLOGIA_200M.geojson', 'COBERTURA_MUNICIPAL_200M.geojson'):
        shutil.copy2(SOURCE / name, OUT / name)
    for p in SOURCE.iterdir():
        if p.name.startswith(('AUDITORIA_REVISION_POL', 'MOVIMIENTO_POL',
                              'EVENTOS_GANADOS_PERDIDOS_POL')) and p.suffix in ('.csv', '.geojson'):
            shutil.copy2(p, OUT / p.name)
    output.OUT = OUT
    output.FINAL_PACKAGE = OUT / PACKAGE.name
    catalog = {r['name']: r for r in prior['catalog']}

    def add(name, rows, visual=True):
        catalog[name] = output.export(name, rows, visual)

    def table(name, rows):
        if rows:
            output.table(name, rows)
        else:
            # Empty audit results retain their schema, never rows from the prior scenario.
            frame = pyogrio.read_dataframe(PACKAGE, layer=name).iloc[:0]
            frame.to_csv(OUT / (name + '.csv'), index=False, encoding='utf-8-sig')
            pyogrio.write_dataframe(frame, output.FINAL_PACKAGE, layer=name)

    police, metrics, exclusive_rows, overlap_rows = [], [], [], []
    for id, c in sorted(active.items()):
        other, _ = audit.reference(active, id)
        detail, exclusive, overlap = audit.detail(c, other)
        description = audit.context.description(c)
        previous = audit.original_props[id]
        lon, lat = UNPROJECT(c['point'].x, c['point'].y)
        reason = (f"{SLOT} desplazada al nodo vial aprobado {candidate_id}. "
                  f"Desplazamiento {selection[distance_field]:.2f} m; solape {current_props['SOLAPE_PCT']:.2f}% a {detail['SOLAPE_PREVIO_PCT']:.2f}%. "
                  f"Conserva {retained}/{current_props['DV_NUEVOS']} eventos D/V exclusivos anteriores; "
                  f"{lost_dv} dejan de estar cubiertos y {gained_dv} distintos ganan cobertura. "
                  "Ningun nucleo D/V99 antes atendido queda totalmente sin cobertura."
                  if id == SLOT else previous['JUSTIFICACION'].split(' Configuracion final del estudio;')[0])
        reason += (f" Revision puntual {SLOT}: aporte actual {detail['EVENTOS_D_NUEVOS']} D/{detail['EVENTOS_V_NUEVOS']} V "
                   f"y solape {detail['SOLAPE_PREVIO_PCT']:.2f}%. Propuesta no instalada, pendiente verificacion de campo.")
        props = {**previous, **description, **detail,
            'ID_POL': id, 'ID_POLICIA': id, 'X': c['point'].x, 'Y': c['point'].y,
            'LONGITUD': lon, 'LATITUD': lat,
            'DECISION_FINAL': 'REUBICAR' if id == SLOT else previous['DECISION_FINAL'],
            'DECISION': 'REUBICAR' if id == SLOT else previous['DECISION'],
            'DECISION_REVISION_' + suffix: 'REUBICAR' if id == SLOT else 'COORDENADAS_CONSERVADAS',
            'JUSTIFICACION': reason, 'SOLAPE_PCT': detail['SOLAPE_PREVIO_PCT'],
            'COBERTURA_PREVIA': detail['SOLAPE_PREVIO_PCT'],
            'D_NUEVOS': detail['EVENTOS_D_NUEVOS'], 'V_NUEVOS': detail['EVENTOS_V_NUEVOS'],
            'DV_NUEVOS': detail['EVENTOS_DV_NUEVOS'],
            'HOTSPOT_D': description['HOTSPOT_DEL'], 'HOTSPOT_V': description['HOTSPOT_VIOL'],
            'NIVEL_GI': f"Sitio D: {detail['GI_D_CLASE_SITIO'] or 'No disponible'}; V: {detail['GI_V_CLASE_SITIO'] or 'No disponible'}",
            'NIVEL_GI_ENTORNO_200M': max(description['NIVEL_DEL'], description['NIVEL_VIOL'])}
        police.append((c['point'], props))
        metrics.append(props)
        exclusive_rows.append((exclusive, {'ID_POLICIA': id, 'AREA_M2': exclusive.area}))
        overlap_rows.append((overlap, {'ID_POLICIA': id, 'AREA_M2': overlap.area}))
    by_id = {p['ID_POLICIA']: p for p in metrics}
    chosen = by_id[SLOT]
    assert (chosen['D_NUEVOS'], chosen['V_NUEVOS']) == (selection['EVENTOS_D_NUEVOS'], selection['EVENTOS_V_NUEVOS'])
    assert abs(chosen['SOLAPE_PCT'] - selection['SOLAPE_PREVIO_PCT']) < 1e-7
    police_mask = unary_union([c['disk'] for c in active.values()])
    final_mask = unary_union([audit.base, police_mask])
    old_mask = read_layer(PACKAGE, 'COBERTURA_C').geometry.iloc[0]
    nuclei, transitions = [], []
    for g, p in audit.context.hot:
        if p['CATEGORIA'] not in CLASSES[:2]:
            continue
        before, after = g.intersection(old_mask).area / g.area, g.intersection(final_mask).area / g.area
        row = {k: p[k] for k in ('CELL_ID', 'AMBITO', 'CATEGORIA', 'NIVEL')}
        row.update(COB_ANTERIOR_PCT=100*before, COB_FINAL_PCT=100*after,
                   ESTADO_ANTERIOR=coverage_class(before), ESTADO_FINAL=coverage_class(after))
        if p['NIVEL'] == 99:
            nuclei.append(row)
        if coverage_class(before) == 'CUBIERTO' and coverage_class(after) != 'CUBIERTO':
            transitions.append(row)
    assert not any(r['ESTADO_ANTERIOR'] != 'SIN COBERTURA' and r['ESTADO_FINAL'] == 'SIN COBERTURA' for r in nuclei)

    incidents, hotspot_stats, corridor_stats, updated, _, _ = scenario_evaluation(
        audit.context, audit.statistics, audit.context.dv, {'C': final_mask})
    canton = unary_union([g for g, _ in audit.canton])
    territorial = {'ESCENARIO': 'C', 'AREA_TOTAL_URBANA_KM2': audit.urban.area/1e6,
        'AREA_CUBIERTA_URBANA_KM2': final_mask.intersection(audit.urban).area/1e6,
        'PCT_URBANO': pct(final_mask.intersection(audit.urban).area, audit.urban.area),
        'AREA_TOTAL_CANTON_KM2': canton.area/1e6,
        'AREA_CUBIERTA_CANTON_KM2': final_mask.intersection(canton).area/1e6,
        'PCT_CANTON': pct(final_mask.intersection(canton).area, canton.area), 'BUFFER_DISUELTO_KM2': final_mask.area/1e6}
    for kind, rows in (('incidents', incidents), ('hotspots', hotspot_stats), ('corridors', corridor_stats),
                       ('territorial', [territorial]), ('population', [output.population_metrics(audit.blocks, audit.urban, final_mask)])):
        prior[kind] = [r for r in prior[kind] if r['ESCENARIO'] != 'C'] + rows
    all_equipment = [(g, {**p, 'ID_EQUIPO': p['ID_CAMARA'], 'GRUPO_ESCENARIO': 'EXISTENTE'}) for g, p in audit.existing]
    all_equipment += [(g, {**p, 'ID_EQUIPO': p['ID_PROPUESTA'], 'GRUPO_ESCENARIO': 'MUNICIPAL_PROPUESTA'}) for g, p in audit.municipal]
    all_equipment += [(g, {**p, 'ID_EQUIPO': p['ID_POLICIA'], 'GRUPO_ESCENARIO': 'POLICIA_PROPUESTA'}) for g, p in police]
    add('PROPUESTA_POLICIA_30_FINAL', police)
    add('ESCENARIO_FINAL_183', all_equipment)
    add('CONTROL_SOLAPES_POLICIA_FINAL', [(active[p['ID_POLICIA']]['disk'], p) for p in metrics])
    add('AREAS_EXCLUSIVAS_POLICIA_FINAL', exclusive_rows)
    add('AREAS_SOLAPADAS_POLICIA_FINAL', overlap_rows)
    add('SOLAPE_DISUELTO_POLICIA_FINAL', [(unary_union([g for g, _ in overlap_rows]), {'METODO': 'Union sin doble conteo'})])
    add('COBERTURA_POLICIA_200M', [(police_mask, {'RADIO_M': 200})])
    add('COBERTURA_C', [(final_mask, {'ESCENARIO': 'C', 'RADIO_M': 200, 'TOTAL_EQUIPOS': 183})])
    for cat in CLASSES:
        add('HOTSPOT_' + cat, [(g, p) for (_, category), rows in updated.items() if category == cat
                              for g, p in rows if p['GI_CLASS'].startswith('HOTSPOT')])
    # Geometry/statistics are frozen. Only dependent coverage attributes change.
    add('INCIDENTES_CLASIFICADOS', [(g, {**p, 'CUB_C': final_mask.covers(g)}) for g, p in audit.events], False)
    add('MANZANAS_COBERTURA', [(g, {**p,
        'COB_C_PCT': pct(g.intersection(audit.urban).intersection(final_mask).area, g.intersection(audit.urban).area)
            if g.intersection(audit.urban).area > AREA_EPS else None,
        'POB_C_CUBIERTA': p['POBLACION']*g.intersection(audit.urban).intersection(final_mask).area/g.area
            if p['POBLACION'] is not None else None}) for g, p in audit.blocks], False)
    for name in ('CAMARAS_EXISTENTES_103_FINAL', 'PROPUESTA_MUNICIPAL_50_FINAL', 'COBERTURA_A', 'COBERTURA_B',
                 'PLATAFORMAS_TERRITORIALES', 'LIMITE_CANTONAL', 'CORREDORES', 'UPC_INFRAESTRUCTURA'):
        add(name, records(read_layer(PACKAGE, name)))
    camera_tree = STRtree([g for g, _ in all_equipment])
    for key, label in [('BOULEVARD_MACAJI_BELLAVISTA', 'MACAJI'), ('ANILLO_VIAL', 'ANILLO'),
                       ('CICLOVIAS', 'CICLOVIAS'), ('QUEBRADA_LAS_ABRAS', 'LAS_ABRAS')]:
        residual = []
        for i, segment in enumerate(parts(audit.context.axes[key].difference(final_mask), 1), 1):
            g, p = all_equipment[int(camera_tree.nearest(segment))]
            residual.append((segment, {'ID': f'{label}-{i:04d}', 'CORREDOR': key, 'LONGITUD_M': segment.length,
                'CAMARA_MAS_CERCANA': p['ID_EQUIPO'], 'DIST_CAMARA_M': segment.distance(g),
                'METODO_DIST': 'Distancia minima del segmento al punto de camara'}))
        add('BRECHA_' + label + '_FINAL', residual)
    matrix, pairs = [], []
    for id, c in sorted(active.items()):
        matrix.append({'ID_POLICIA': id, **{key: c['point'].distance(v['point']) for key, v in sorted(active.items())}})
    for i, (a, c) in enumerate(sorted(active.items())):
        for b, d in sorted(active.items())[i+1:]:
            distance = c['point'].distance(d['point'])
            if distance >= 400:
                continue
            band = '<100 m' if distance < 100 else '100-200 m' if distance < 200 else '200-300 m' if distance < 300 else '300-400 m'
            mutual = c['disk'].intersection(d['disk']).area
            pairs.append({'ID_A': a, 'ID_B': b, 'DISTANCIA_M': distance, 'BANDA': band,
                'ALGUNA_REUBICADA': SLOT in (a, b), 'AREA_SOLAPE_MUTUO_M2': mutual,
                'SOLAPE_MUTUO_BUFFER_PCT': pct(mutual, c['disk'].area),
                'DV_A_EXCLUSIVOS': by_id[a]['DV_NUEVOS'], 'DV_B_EXCLUSIVOS': by_id[b]['DV_NUEVOS'],
                'JUSTIFICACION': 'Distancia descriptiva; no se impone una separacion minima. Aportes contra las otras29.'})
    old_selected = audit.original_props[SLOT]
    revision = {'ID_POLICIA': SLOT, 'CANDIDATO_ANTERIOR': original['id'], 'CANDIDATO_FINAL': candidate_id,
        'X_ANTERIOR': original['point'].x, 'Y_ANTERIOR': original['point'].y,
        'X_FINAL': active[SLOT]['point'].x, 'Y_FINAL': active[SLOT]['point'].y,
        'DESPLAZAMIENTO_M': original['point'].distance(active[SLOT]['point']),
        'PLATAFORMA_ANTERIOR': old_selected['PLATAFORMA'], 'PLATAFORMA_FINAL': chosen['PLATAFORMA'],
        'DV_ANTERIOR': old_selected['DV_NUEVOS'], 'DV_FINAL': chosen['DV_NUEVOS'],
        'SOLAPE_ANTERIOR': old_selected['SOLAPE_PCT'], 'SOLAPE_FINAL': chosen['SOLAPE_PCT'],
        'JUSTIFICACION': chosen['JUSTIFICACION']}
    prior_audits = pyogrio.read_dataframe(PACKAGE, layer='AUDITORIA_REUBICACIONES_POLICIA').to_dict('records')
    for row in prior_audits:
        p = by_id[row['ID_POLICIA']]
        row.update(DV_FINAL=p['DV_NUEVOS'], SOLAPE_FINAL=p['SOLAPE_PCT'])
        if row['ID_POLICIA'] == SLOT:
            row.update(DECISION='REUBICAR', CANDIDATO_FINAL=candidate_id, X_FINAL=p['X'], Y_FINAL=p['Y'],
                       DESPLAZAMIENTO_M=revision['DESPLAZAMIENTO_M'], JUSTIFICACION=chosen['JUSTIFICACION'])
    table('AUDITORIA_REUBICACIONES_POLICIA', prior_audits)
    table('AUDITORIA_REVISION_' + suffix, [revision])
    add('MOVIMIENTO_' + suffix, [(LineString([original['point'], active[SLOT]['point']]), revision)])
    table('POLICIA_BENEFICIO_FINAL', metrics)
    table('MATRIZ_DISTANCIAS_POLICIA_30', matrix)
    table('PARES_POLICIA_MENOS_400M', pairs)
    table('CONTROL_NUCLEOS_GI_99', nuclei)
    table('CELDAS_COMPLETAS_A_PARCIALES', transitions)
    table('INCIDENTES_CUBIERTOS_FINAL', incidents)
    table('HOTSPOTS_ATENDIDOS_FINAL', hotspot_stats)
    table('CORREDORES_CUBIERTOS_FINAL', corridor_stats)
    comparison_rows, delta_events = [], []
    old_covered, new_covered = covers(old_mask, audit.event_points), covers(final_mask, audit.event_points)
    for cat in CLASSES:
        valid = np.array([p['CATEGORIA'] == cat and p['AMBITO'] != 'EXTERNO_CANTON' for _, p in audit.events])
        before, after = int((old_covered & valid).sum()), int((new_covered & valid).sum())
        comparison_rows.append({'INDICADOR': cat + ' cubiertos', 'ANTERIOR': before, 'FINAL': after, 'DIFERENCIA': after-before})
        delta_events.append({'CATEGORIA': cat, 'PERDIDOS': int((old_covered & ~new_covered & valid).sum()),
                             'GANADOS': int((~old_covered & new_covered & valid).sum())})
    comparison_rows += [{'INDICADOR': f'Solape {SLOT} %', 'ANTERIOR': old_selected['SOLAPE_PCT'], 'FINAL': chosen['SOLAPE_PCT']},
        {'INDICADOR': f'Area exclusiva {SLOT} m2', 'ANTERIOR': old_selected['AREA_EXCLUSIVA_M2'], 'FINAL': chosen['AREA_EXCLUSIVA_M2']}]
    table('COMPARACION_ANTERIOR_FINAL', comparison_rows)
    table('EVENTOS_GANADOS_PERDIDOS_' + suffix, delta_events)
    status = 'REVISION_' + suffix + '_VALIDADA'
    acceptance = {'estado': status, 'reubicadas': sum(p['DECISION_FINAL'] == 'REUBICAR' for p in metrics),
        'mantenidas': sum(p['DECISION_FINAL'] != 'REUBICAR' for p in metrics), 'revision_reubicadas': 1,
        'revision_conservadas': 29, 'existentes': 103, 'municipales': 50, 'policiales': 30, 'total_equipos': 183,
        'para_cambio_incluidas': 31, 'crs': 'EPSG:32717', 'radio_m': 200,
        'solape_medio_antes': float(np.mean([p['SOLAPE_PCT'] for p in audit.original_props.values()])),
        'solape_medio_final': float(np.mean([p['SOLAPE_PCT'] for p in metrics])),
        'solape_max_antes': max(p['SOLAPE_PCT'] for p in audit.original_props.values()),
        'solape_max_final': max(p['SOLAPE_PCT'] for p in metrics), 'nucleos99_abandonados': [],
        'niveles_redundancia': dict(Counter(p['REDUNDANCIA'] for p in metrics)),
        'pares_por_banda': dict(Counter(r['BANDA'] for r in pairs)),
        'pares_menor200': [r for r in pairs if r['DISTANCIA_M'] < 200],
        'celdas_completas_a_parciales': dict(Counter(r['CATEGORIA'] for r in transitions)), 'gi_recalculado': False,
        'fuentes_protegidas_hash': protected, 'regeneracion_completa': False,
        'existentes_municipales_conservadas': True, 'coordenadas_29_conservadas': True,
        'brechas_manzanas_c_reutilizadas': False, 'revision': revision, 'eventos_ganados_perdidos': delta_events,
        'commit': False, 'push': False}
    prior.update(generatedAt=datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'),
        status=status, sourceHashes=protected, catalog=list(catalog.values()),
        policeMetrics=metrics, policeClosure=acceptance, policeComparison=comparison_rows,
        policeChanges=[r for r in prior_audits if r['DECISION'] == 'REUBICAR'],
        giRecalculated=False, commit=False, push=False, gapScenarioCValidated=False)
    prior['summary'] = [{'INDICADOR': cat + ' cubiertos cantonales', **{str(n): next(r['CUBIERTOS'] for r in prior['incidents']
        if r['ESCENARIO'] == s and r['AMBITO'] == 'CANTONAL' and r['CATEGORIA'] == cat) for s, n in zip('ABC', (103, 153, 183))}}
        for cat in CLASSES]
    prior['warnings'].append(f'Revision {SLOT}: conserva {retained} eventos D/V anteriores, pierde {lost_dv} y gana {gained_dv} distintos. No es una mejora en toda celda o categoria.')
    output.save_json('RESULTADOS.json', prior)
    output.save_json('VALIDACION.json', acceptance)
    lines = ['# Reubicacion puntual de ' + SLOT, '',
        'Una camara reubicada; otras29 coordenadas,103 existentes y50 municipales conservadas. Total183.',
        'Los campos commit/push=false describen la auditoria de calculo, anterior a la publicacion autorizada.',
        f"Candidato {candidate_id}; nodo vial en {chosen['PLATAFORMA']}; desplazamiento {revision['DESPLAZAMIENTO_M']:.2f} m.",
        f"Solape {revision['SOLAPE_ANTERIOR']:.2f}% a {revision['SOLAPE_FINAL']:.2f}%; D/V exclusivos {revision['DV_ANTERIOR']} a {revision['DV_FINAL']} ({chosen['D_NUEVOS']}D+{chosen['V_NUEVOS']}V).",
        'Nodo vial auditado y expresamente aprobado; sin umbral arbitrario de distancia o solape.',
        f'Conserva {retained} eventos D/V exclusivos anteriores; pierde {lost_dv} y gana {gained_dv} distintos. No confundir mantener conteos con conservar todos los eventos.',
        'Gi* urbano/rural, metodologias, celdas, ejes y geometria censal NO recalculados ni modificados.',
        f"Gi* en el punto D/V: {chosen['GI_D_CLASE_SITIO']}/{chosen['GI_V_CLASE_SITIO']}; "
        f"nivel maximo Hot Spot intersectado por el radio D/V: {chosen['NIVEL_DEL']}%/{chosen['NIVEL_VIOL']}%. "
        'El nivel del entorno no clasifica estadisticamente el nodo vial.',
        'Ningun nucleo D/V99 anteriormente atendido queda totalmente sin cobertura; puede variar su cobertura parcial.',
        'Radio200m enEPSG:32717; cobertura disuelta sin doble conteo. No se optimizo ningun corredor.',
        'Recalculados: coberturaC, incidentes, Hot Spots atendidos, superficie, estimacion de poblacion, corredores,',
        'beneficio de las30, matriz, tablas, GeoJSON, mapa yZIP. Brechas por manzanaC: No disponible, sin reutilizar cifras anteriores.',
        'La fuente publicada anterior se conserva integra como historico. Esta revision es la fuente activa del visor.',
        'Poblacion: estimacion areal urbanaCPV2022; poblacion rural completa No disponible.', '',
        '| Indicador | Antes | Despues |', '|---|---:|---:|']
    lines += [f"| {r['INDICADOR']} | {r['ANTERIOR']:.2f} | {r['FINAL']:.2f} |" for r in comparison_rows]
    (OUT / 'INFORME_FINAL.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    output.write_map(prior, police, audit.existing, audit.municipal, audit.context.hot, audit.platforms,
                     exclusive_rows, overlap_rows, old_mask)
    assert all(sha(Path(p)) == h for p, h in protected.items())
    output.package_zip()
    print('VALIDADO', json.dumps({'revision': revision, 'comparacion': comparison_rows,
        'cambio_eventos': delta_events, '29_fijas': True, 'gi_intacto': True}, ensure_ascii=False), flush=True)


def refresh_view(slot=SLOT, destination=OUT):
    """Refresh the map/template without repeating spatial calculations."""
    OUT = Path(destination)
    output.OUT = OUT
    output.FINAL_PACKAGE = OUT / PACKAGE.name
    result = json.loads((OUT / 'RESULTADOS.json').read_text(encoding='utf-8'))
    result['status'] = result['policeClosure']['estado'] = 'REVISION_' + slot.replace('-', '') + '_VALIDADA'
    pairs = pyogrio.read_dataframe(output.FINAL_PACKAGE, layer='PARES_POLICIA_MENOS_400M').to_dict('records')
    transitions = pyogrio.read_dataframe(output.FINAL_PACKAGE, layer='CELDAS_COMPLETAS_A_PARCIALES').to_dict('records')
    result['policeClosure'].update(pares_menor200=[r for r in pairs if r['DISTANCIA_M'] < 200],
        celdas_completas_a_parciales=dict(Counter(r['CATEGORIA'] for r in transitions)))
    output.save_json('RESULTADOS.json', result)
    output.save_json('VALIDACION.json', result['policeClosure'])
    report = (OUT / 'INFORME_FINAL.md').read_text(encoding='utf-8')
    report = report.replace('Total183. Sin commit/push.', 'Total183.\nLos campos commit/push=false describen la auditoria de calculo, anterior a la publicacion autorizada.')
    report = report.replace('Esta revision esta aplicada solo al visor local.', 'Esta revision es la fuente activa del visor.')
    (OUT / 'INFORME_FINAL.md').write_text(report, encoding='utf-8')
    def layer(name):
        return records(read_layer(output.FINAL_PACKAGE, name))
    hot = [row for cat in CLASSES for row in layer('HOTSPOT_' + cat)]
    output.write_map(result, layer('PROPUESTA_POLICIA_30_FINAL'), layer('CAMARAS_EXISTENTES_103_FINAL'),
        layer('PROPUESTA_MUNICIPAL_50_FINAL'), hot, layer('PLATAFORMAS_TERRITORIALES'),
        layer('AREAS_EXCLUSIVAS_POLICIA_FINAL'), layer('AREAS_SOLAPADAS_POLICIA_FINAL'), None)
    output.package_zip()
    print('MAPA_ACTUALIZADO_SIN_RECALCULO')


if __name__ == '__main__':
    refresh_view() if '--refresh-view' in sys.argv else main()
