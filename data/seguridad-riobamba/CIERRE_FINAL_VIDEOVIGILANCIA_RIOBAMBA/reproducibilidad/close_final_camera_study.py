"""Final local study: lexicographic municipal corridors, then limited police review."""
import csv
import json
import shutil
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from scipy.optimize import Bounds, LinearConstraint, linear_sum_assignment, milp
from scipy.sparse import coo_matrix, csr_matrix, vstack
from shapely import STRtree
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from build_police_camera_proposal import (ROOT, CLASSES, Context, AREA_EPS, read_layer,
    records, parts, pct, sha, geojson, scenario_evaluation, UNPROJECT)
from consolidate_camera_project import coverage, census_blocks
from review_police_camera_efficiency import Evaluator, preferences, revision_rank

BASE = ROOT / 'data/seguridad-riobamba'
SOURCE = BASE / 'consolidacion-183-20261004'
PREVIOUS = SOURCE / 'CONSOLIDACION_CAMARAS_183.gpkg'
POLICE_SOURCE = BASE / 'propuesta-policia-30-20261003/PROPUESTA_POLICIA_30.gpkg'
MUNICIPAL_SOURCE = BASE / 'optimizacion-municipal-50-20261003/PROPUESTA_50_OPTIMIZADA.gpkg'
OUT = BASE / 'CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA'
PACKAGE = OUT / 'CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.gpkg'
KEYS = ('BOULEVARD_MACAJI_BELLAVISTA', 'ANILLO_VIAL', 'CICLOVIAS')
GROUPS = ('01_CAMARAS_EXISTENTES_103', '02_MUNICIPALES_50', '03_POLICIA_30',
    '04_COBERTURAS', '05_HOTSPOTS', '06_INCIDENTES', '07_CORREDORES',
    '08_CABECERAS_RURALES', '09_LAS_ABRAS_MAATE', '10_CUNDUANA', '11_UPC',
    '12_BRECHAS', '13_AUDITORIA', '14_DIAGNOSTICO_FINAL')


def jsave(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False,
        indent=2), encoding='utf-8')


def csvsave(name, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for row in rows for k in row))
    with (OUT / (name + '.csv')).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)
    pyogrio.write_dataframe(pd.DataFrame(rows, columns=fields), PACKAGE, layer=name)


def export(name, rows, group, source='Procesamiento final; consultar trazabilidad'):
    frame = gpd.GeoDataFrame([p for _, p in rows], geometry=[g for g, _ in rows], crs=32717)
    pyogrio.write_dataframe(frame, PACKAGE, layer=name)
    jsave(name + '.geojson', geojson(rows))
    return {'name': name, 'group': group, 'records': len(rows), 'crs': 'EPSG:32717',
        'source': source, 'fields': list(frame.columns[:-1])}


def corridor_atoms(axes, candidates, fixed):
    """Exact linear intervals, grouped by identical candidate support; no raster sampling."""
    disks = [g.buffer(200, quad_segs=64) for g, _ in candidates]
    tree = STRtree(disks)
    grouped = defaultdict(float)
    totals, baseline = {}, {}
    for key in KEYS:
        axis = axes[key]
        totals[key] = axis.length
        baseline[key] = axis.intersection(fixed).length
        for component in parts(axis.difference(fixed), 1):
            events = defaultdict(lambda: [[], []])
            events[0.0]; events[component.length]
            for index in tree.query(component, predicate='intersects'):
                for piece in parts(component.intersection(disks[int(index)]), 1):
                    start = component.project(Point(piece.coords[0]))
                    end = component.project(Point(piece.coords[-1]))
                    low, high = sorted((start, end))
                    if high - low > 1e-8:
                        events[low][0].append(int(index))
                        events[high][1].append(int(index))
            active = Counter()
            last = 0.0
            for distance in sorted(events):
                if distance > last and active:
                    support = tuple(sorted(i for i, count in active.items() if count > 0))
                    if support:
                        grouped[(key, support)] += distance - last
                for index in events[distance][1]:
                    active[index] -= 1
                for index in events[distance][0]:
                    active[index] += 1
                last = distance
        print(json.dumps({'atomized': key, 'totalM': totals[key], 'fixedM': baseline[key]}), flush=True)
    atoms = [(key, support, length) for (key, support), length in grouped.items()]
    return atoms, totals, baseline


def optimize_structural(cameras, municipal, axes):
    fixed_rows = cameras + [r for r in municipal if r[1]['GRUPO'] != 'RED_ESTRUCTURAL']
    fixed = coverage(fixed_rows)
    fixed_xy = {(round(g.x, 5), round(g.y, 5)) for g, _ in fixed_rows}
    candidate_rows = records(read_layer(MUNICIPAL_SOURCE, 'CANDIDATOS_ESTRUCTURALES'))
    candidates = [r for r in candidate_rows if (round(r[0].x, 5), round(r[0].y, 5)) not in fixed_xy]
    existing_xy = {(round(g.x, 5), round(g.y, 5)) for g, _ in candidates}
    original = [r for r in municipal if r[1]['GRUPO'] == 'RED_ESTRUCTURAL']
    for row in original:
        if (round(row[0].x, 5), round(row[0].y, 5)) not in existing_xy:
            candidates.append(row)
    atoms, totals, base = corridor_atoms(axes, candidates, fixed)
    n, m = len(candidates), len(atoms)
    row, col, val = [], [], []
    for j, (_, support, _) in enumerate(atoms):
        row.append(j); col.append(n+j); val.append(1.0)
        for i in support:
            row.append(j); col.append(i); val.append(-1.0)
    matrix = coo_matrix((val, (row, col)), shape=(m, n+m)).tocsr()
    constraints = [LinearConstraint(matrix, -np.inf, 0),
        LinearConstraint(csr_matrix(([1.0]*n, ([0]*n, list(range(n)))), shape=(1, n+m)), 24, 24)]
    lengths = {key: np.array([0.0]*n + [length if kind == key else 0.0 for kind, _, length in atoms]) for key in KEYS}
    constraints.append(LinearConstraint(csr_matrix(lengths[KEYS[0]][None, :]), .98*totals[KEYS[0]]-base[KEYS[0]], np.inf))
    integrality = np.array([1]*n+[0]*m)
    logs, selected = [], None
    for phase, key in enumerate(KEYS[1:], 1):
        begin = time.monotonic()
        solution = milp(-lengths[key], integrality=integrality,
            bounds=Bounds(np.zeros(n+m), np.ones(n+m)), constraints=constraints,
            options={'time_limit': 240, 'mip_rel_gap': 0.000001})
        if solution.x is None:
            raise RuntimeError(f'No feasible municipal solution: {solution.message}')
        selected = np.flatnonzero(solution.x[:n] > .5).tolist()
        mask = unary_union([fixed] + [candidates[i][0].buffer(200, quad_segs=64) for i in selected])
        actual = {k: axes[k].intersection(mask).length for k in KEYS}
        logs.append({'phase': phase, 'objective': key, 'status': int(solution.status),
            'message': solution.message, 'seconds': time.monotonic()-begin,
            'mipGap': float(solution.mip_gap), 'nodes': int(solution.mip_node_count),
            'modelCoveredM': base[key]-float(solution.fun), 'actualCoveredM': actual,
            'percent': {k: pct(actual[k], totals[k]) for k in KEYS}, 'selected': [candidates[i][1]['ID_CANDIDATO'] for i in selected]})
        jsave('OPTIMIZACION_ESTRUCTURAL.json', {'candidates': n, 'atoms': m, 'method': 'MILP lexicografico de union lineal exacta', 'phases': logs})
        print(json.dumps(logs[-1]), flush=True)
        assert abs(actual[key]-(base[key]-solution.fun)) < .02, 'Interval union vs GEOS mismatch'
        assert actual[KEYS[0]]/totals[KEYS[0]] >= .98-1e-9
        # Numeric tolerance only: do not trade Anillo against Ciclovias.
        constraints.append(LinearConstraint(csr_matrix(lengths[key][None, :]), actual[key]-base[key]-.001, np.inf))
    chosen = [candidates[i] for i in selected]
    distance_matrix = np.array([[old.distance(new) for new, _ in chosen] for old, _ in original])
    old_index, new_index = linear_sum_assignment(distance_matrix)
    mapping = {int(i): int(j) for i, j in zip(old_index, new_index)}
    structural = []
    for i, (_, old) in enumerate(original):
        point, candidate = chosen[mapping[i]]
        lon, lat = UNPROJECT(point.x, point.y)
        structural.append((point, {**old, 'ID_CANDIDATO': candidate['ID_CANDIDATO'],
            'X': point.x, 'Y': point.y, 'LONGITUD': lon, 'LATITUD': lat,
            'ORIGEN_CANDIDATO': candidate['ORIGEN_CANDIDATO'], 'GRADO_NODO': candidate['GRADO_NODO'],
            'METODO_FINAL': 'Macaji>=98%; maximizar Anillo; despues Ciclovias; sin cuotas por corredor',
            'ESTADO': 'PROPUESTA_FINAL_PARA_REVISION_NO_INSTALADA'}))
    final = sorted([r for r in municipal if r[1]['GRUPO'] != 'RED_ESTRUCTURAL'] + structural,
        key=lambda r: r[1]['ID_PROPUESTA'])
    return final, candidates, logs


def police_review(context, previous, baseline_context):
    raw = records(read_layer(POLICE_SOURCE, 'CANDIDATOS_POLICIA'))
    raw_by_id = {p['ID_CANDIDATO']: (g, p) for g, p in raw}
    original_by_id = {p['ID_POLICIA']: (g, p) for g, p in previous}
    candidate_cache = {}
    def candidate(id):
        if id not in candidate_cache:
            g, p = raw_by_id[id]
            candidate_cache[id] = context.candidate({'point': g, 'id': id,
                'degree': p['GRADO_NODO'], 'origins': set(str(p['INTERSECCION_O_NODO']).split('|')), 'props': dict(p)})
        return candidate_cache[id]
    active = {p['ID_POLICIA']: candidate(p['ID_CANDIDATO']) for _, p in previous}
    evaluator = Evaluator(context)
    old_evaluator = Evaluator(baseline_context)
    before, loss = {}, {}
    for slot, current in active.items():
        others = [c for id, c in active.items() if id != slot]
        old_evaluator.prepare(unary_union([baseline_context.baseline] + [c['disk'] for c in others]))
        before[slot] = old_evaluator.evaluate(current, [c['point'] for c in others])
        evaluator.prepare(unary_union([context.baseline] + [c['disk'] for c in others]))
        new = evaluator.evaluate(current, [c['point'] for c in others])
        loss[slot] = (new['EVENTOS_DV_NUEVOS'] < before[slot]['EVENTOS_DV_NUEVOS']
            and new['SOLAPE_PREVIO_PCT'] > before[slot]['SOLAPE_PREVIO_PCT']+1e-8)
    observed = ['POL-08', 'POL-20', 'POL-21', 'POL-22', 'POL-30']
    review_order = observed + sorted(slot for slot in active if loss[slot] and slot not in observed)
    changes, comparisons, decisions = [], [], []
    reserved = {c['id'] for c in active.values()}
    for slot in review_order:
        others = {id: c for id, c in active.items() if id != slot}
        other_points = [c['point'] for c in others.values()]
        evaluator.prepare(unary_union([context.baseline] + [c['disk'] for c in others.values()]))
        old = evaluator.evaluate(active[slot], other_points)
        options = []
        for id, (g, p) in raw_by_id.items():
            if id in reserved or p['AMBITO_HOTSPOT'] != active[slot]['scope']:
                continue
            c = candidate(id)
            if c['distanceExisting'] < 1e-6 or c['distanceMunicipal'] < 1e-6:
                continue
            result = evaluator.evaluate(c, other_points)
            if result['COINCIDENCIA_DV_RESIDUAL_M2'] <= AREA_EPS:
                continue
            result['PREFERIBLE'] = preferences(result, old)
            options.append(result)
        options.sort(key=lambda r: (r['PREFERIBLE'], revision_rank(r)), reverse=True)
        for rank, r in enumerate([old]+options[:5]):
            c = candidate(r['ID_CANDIDATO'])
            comparisons.append({**r, 'ID_POLICIA': slot, 'OPCION': 'ACTUAL' if rank == 0 else 'ALTERNATIVA',
                'ORDEN': rank, 'POBLACION_ASOCIADA': context.population(c['disk'])[0],
                'CORREDOR_COINCIDENTE': c['props'].get('CORREDOR_COINCIDENTE')})
        winner = options[0] if loss[slot] and options and options[0]['PREFERIBLE'] else old
        replace = winner is not old
        reason = (f"Perdida comprobada con nuevas municipales: {before[slot]['EVENTOS_DV_NUEVOS']} a {old['EVENTOS_DV_NUEVOS']} D/V. "
            f"Alternativa significativa D/V: {old['EVENTOS_DV_NUEVOS']} a {winner['EVENTOS_DV_NUEVOS']} exclusivos; "
            f"solape {old['SOLAPE_PREVIO_PCT']:.2f}% a {winner['SOLAPE_PREVIO_PCT']:.2f}%; sin disminuir D ni V individualmente." if replace else
            'Mantener: no se verifican conjuntamente perdida de utilidad por nueva cobertura municipal y alternativa dominante en eventos D/V y redundancia. Sin cortes de distancia, solape o numero de eventos.')
        if replace:
            point = active[slot]['point']; new = candidate(winner['ID_CANDIDATO'])
            changes.append({'ID_ANTERIOR': slot, 'ID_FINAL': slot,
                'CANDIDATO_ANTERIOR': old['ID_CANDIDATO'], 'CANDIDATO_FINAL': new['id'],
                'UBICACION_ANTERIOR': f'{point.x},{point.y}', 'UBICACION_FINAL': f"{new['point'].x},{new['point'].y}",
                'MOTIVO': reason, 'DV_NUEVOS_ANTES': old['EVENTOS_DV_NUEVOS'],
                'DV_NUEVOS_DESPUES': winner['EVENTOS_DV_NUEVOS'], 'SOLAPE_ANTES': old['SOLAPE_PREVIO_PCT'],
                'SOLAPE_DESPUES': winner['SOLAPE_PREVIO_PCT'], 'D_ANTES': old['EVENTOS_D_NUEVOS'],
                'D_DESPUES': winner['EVENTOS_D_NUEVOS'], 'V_ANTES': old['EVENTOS_V_NUEVOS'], 'V_DESPUES': winner['EVENTOS_V_NUEVOS']})
            active[slot] = new; reserved.add(new['id'])
        decisions.append({'ID': slot, 'DECISION': 'REEMPLAZAR' if replace else 'MANTENER',
            'PERDIDA_VERIFICADA': loss[slot], 'DV_BASELINE': before[slot]['EVENTOS_DV_NUEVOS'],
            'DV_ACTUAL': old['EVENTOS_DV_NUEVOS'], 'DV_PROPUESTO': winner['EVENTOS_DV_NUEVOS'], 'MOTIVO': reason})
        print(json.dumps(decisions[-1]), flush=True)
    final, metrics = [], []
    for slot, c in active.items():
        others = [v for id, v in active.items() if id != slot]
        evaluator.prepare(unary_union([context.baseline] + [v['disk'] for v in others]))
        m = evaluator.evaluate(c, [v['point'] for v in others])
        lon, lat = UNPROJECT(c['point'].x, c['point'].y)
        props = {**original_by_id[slot][1], **context.description(c), 'ID_CANDIDATO': c['id'],
            'X': c['point'].x, 'Y': c['point'].y, 'LONGITUD': lon, 'LATITUD': lat,
            'BENEFICIO_MARGINAL': m['EVENTOS_DV_NUEVOS'], 'SOLAPE_RESTO_FINAL_PCT': m['SOLAPE_PREVIO_PCT'],
            'DECISION_FINAL': 'REEMPLAZAR' if any(r['ID_FINAL'] == slot for r in changes) else 'MANTENER',
            'EVENTOS_D_EXCLUSIVOS_FINAL': m['EVENTOS_D_NUEVOS'], 'EVENTOS_V_EXCLUSIVOS_FINAL': m['EVENTOS_V_NUEVOS'],
            'ESTADO': 'PROPUESTA_FINAL_PARA_REVISION_NO_INSTALADA'}
        final.append((c['point'], props))
        metrics.append({**m, 'ID_POLICIA': slot, 'DV_ANTERIOR': before[slot]['EVENTOS_DV_NUEVOS'],
            'SOLAPE_ANTERIOR': before[slot]['SOLAPE_PREVIO_PCT'], 'DECISION': props['DECISION_FINAL']})
    return final, changes, comparisons, metrics, decisions


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    protected = {str(p): sha(p) for folder in (SOURCE, BASE/'hotspot-urbano-200m-20261002')
        for p in folder.rglob('*') if p.is_file() and p.suffix not in ('.lock', '.lck', '.log')}
    for p in (ROOT/'riobamba-cantonal-view.js', ROOT/'visor-seguridad-riobamba-v2.html', POLICE_SOURCE, MUNICIPAL_SOURCE):
        protected[str(p)] = sha(p)
    prior = json.loads((SOURCE/'RESULTADOS.json').read_text(encoding='utf-8'))
    cameras = records(read_layer(PREVIOUS, 'CAMARAS_EXISTENTES_103_CONSOLIDADA'))
    municipal_old = records(read_layer(PREVIOUS, 'PROPUESTA_50_CONSOLIDADA'))
    police_old = records(read_layer(PREVIOUS, 'PROPUESTA_POLICIA_30_FINAL'))
    platforms = records(read_layer(PREVIOUS, 'PLATAFORMAS_TERRITORIALES'))
    urban = unary_union([g for g, _ in platforms])
    canton = read_layer(PREVIOUS, 'LIMITE_CANTONAL').geometry.iloc[0]
    axes = {p['CORREDOR']: g for g, p in records(read_layer(PREVIOUS, 'CORREDORES_CONSOLIDADOS'))}
    checkpoint = OUT/'MUNICIPALES_CHECKPOINT.gpkg'
    if checkpoint.exists():
        municipal = records(read_layer(checkpoint, 'MUNICIPALES'))
        candidates = records(read_layer(checkpoint, 'CANDIDATOS'))
        logs = json.loads((OUT/'OPTIMIZACION_ESTRUCTURAL.json').read_text(encoding='utf-8'))['phases']
    else:
        municipal, candidates, logs = optimize_structural(cameras, municipal_old, axes)
        for name, rows in (('MUNICIPALES', municipal), ('CANDIDATOS', candidates)):
            pyogrio.write_dataframe(gpd.GeoDataFrame([p for _, p in rows], geometry=[g for g, _ in rows], crs=32717), checkpoint, layer=name)
    a = coverage(cameras); b = unary_union([a, coverage(municipal)])
    assert pct(axes[KEYS[0]].intersection(b).length, axes[KEYS[0]].length) >= 98-1e-7
    print('MUNICIPALES CLOSED: MACAJI>=98; starting police review', flush=True)
    stats = {(scope, cat): records(read_layer(POLICE_SOURCE, 'GI_'+scope+'_'+cat))
        for scope in ('URBANO', 'RURAL') for cat in CLASSES}
    hot = [(g, p) for rows in stats.values() for g, p in rows if p['GI_CLASS'].startswith('HOTSPOT')]
    dv = records(read_layer(POLICE_SOURCE, 'HOTSPOT_COINCIDENCIA_DV'))
    events = records(read_layer(PREVIOUS, 'INCIDENTES_ANALITICOS'))
    infrastructure = records(read_layer(PREVIOUS, 'UPC_INFRAESTRUCTURA'))
    blocks = census_blocks()
    context = Context(events, hot, dv, b, [g for g, _ in cameras], [g for g, _ in municipal], infrastructure, blocks, urban, axes)
    b_old = unary_union([a, coverage(municipal_old)])
    context_old = Context(events, hot, dv, b_old, [g for g, _ in cameras], [g for g, _ in municipal_old], infrastructure, blocks, urban, axes)
    police, police_changes, options, police_metrics, decisions = police_review(context, police_old, context_old)
    c = unary_union([b, coverage(police)])
    masks = {'A': a, 'B': b, 'C': c, 'B_ANTERIOR': b_old, 'C_ANTERIOR': unary_union([b_old, coverage(police_old)])}
    inc, hot_stats, corridors, updated, dv_rows, dv_remaining = scenario_evaluation(context, stats, dv, masks)
    territorial, population, block_results = [], [], []
    for g, p in blocks:
        part = g.intersection(urban)
        props = {**p, 'AREA_URBANA_M2': part.area}
        for name, mask in masks.items():
            area = part.intersection(mask).area
            props['COB_'+name+'_PCT'] = pct(area, part.area) if part.area > AREA_EPS else None
            props['POB_'+name+'_CUBIERTA'] = p['POBLACION']*area/g.area if p['POBLACION'] is not None else None
        block_results.append((g, props))
    valid = [(g, p) for g, p in block_results if p['POBLACION'] is not None and p['AREA_URBANA_M2'] > AREA_EPS]
    pop_total = sum(p['POBLACION']*p['AREA_URBANA_M2']/g.area for g, p in valid)
    for name, mask in masks.items():
        territorial.append({'ESCENARIO': name, 'AREA_TOTAL_URBANA_KM2': urban.area/1e6,
            'AREA_CUBIERTA_URBANA_KM2': mask.intersection(urban).area/1e6, 'PCT_URBANO': pct(mask.intersection(urban).area, urban.area),
            'AREA_TOTAL_CANTON_KM2': canton.area/1e6, 'AREA_CUBIERTA_CANTON_KM2': mask.intersection(canton).area/1e6,
            'PCT_CANTON': pct(mask.intersection(canton).area, canton.area), 'BUFFER_DISUELTO_KM2': mask.area/1e6})
        covered = sum(p['POB_'+name+'_CUBIERTA'] for _, p in valid)
        population.append({'ESCENARIO': name, 'POBLACION_ANALIZADA': pop_total, 'POBLACION_CUBIERTA': covered,
            'POBLACION_NO_CUBIERTA': pop_total-covered, 'PCT_CUBIERTO': pct(covered, pop_total),
            'MANZANAS_VALIDAS': len(valid), 'MANZANAS_SIN_POBLACION': sum(p['POBLACION'] is None and p['AREA_URBANA_M2']>AREA_EPS for _, p in block_results),
            'AMBITO': '18 Plataformas; estimacion areal CPV2022, poblacion rural No disponible'})
    if PACKAGE.exists():
        PACKAGE.unlink()
    catalog = []
    def add(name, rows, group, source='Procesamiento final; consultar trazabilidad'):
        catalog.append(export(name, rows, group, source))
    add('CAMARAS_EXISTENTES_103_FINAL', cameras, GROUPS[0], str(PREVIOUS))
    add('PROPUESTA_MUNICIPAL_50_FINAL', municipal, GROUPS[1])
    add('PROPUESTA_POLICIA_30_FINAL', police, GROUPS[2])
    audit = records(read_layer(PREVIOUS, 'AUDITORIA_CAMARAS_EXISTENTES'))
    audit_rows = []
    for g, p in audit:
        audit_rows.append((g, {**p, 'ID': p.get('ID_CAMARA', p.get('ID')), 'X': g.x, 'Y': g.y}))
    add('AUDITORIA_GEOREFERENCIACION_CAMARAS', audit_rows, GROUPS[12], str(PREVIOUS))
    add('CAMARAS_RECUPERADAS', audit_rows, GROUPS[12], str(PREVIOUS))
    add('MUNICIPALES_ANTERIOR', municipal_old, GROUPS[12], str(PREVIOUS))
    add('POLICIA_ANTERIOR', police_old, GROUPS[12], str(PREVIOUS))
    add('CANDIDATOS_ESTRUCTURALES', candidates, GROUPS[12], str(MUNICIPAL_SOURCE))
    for name in ('INVENTARIO_ORIGINAL_103', 'PLATAFORMAS_TERRITORIALES', 'LIMITE_CANTONAL'):
        add(name, records(read_layer(PREVIOUS, name)), GROUPS[0] if name.startswith('INVENTARIO') else GROUPS[13], str(PREVIOUS))
    for name, group in (('CABECERAS_RURALES', GROUPS[7]), ('AMBITOS_CABECERAS_PUGS', GROUPS[7]),
        ('UPC_INFRAESTRUCTURA', GROUPS[10]), ('CUNDUANA_PUNTOS_CRITICOS', GROUPS[9]), ('CUNDUANA_TRAMOS_LIMPIEZA', GROUPS[9]),
        ('LAS_ABRAS_ACTUAL', GROUPS[8]), ('EJE_QUEBRADA_LAS_ABRAS_MAATE', GROUPS[8]),
        ('LAS_ABRAS_MAATE_REFERENCIA_CANTON', GROUPS[8]), ('ABRAS_DIFERENCIAS', GROUPS[8]), ('ABRAS_DIFERENCIAS_COMPLETAS', GROUPS[8])):
        add(name, records(read_layer(PREVIOUS, name)), group, str(PREVIOUS))
    for name, geom in pyogrio.list_layers(PREVIOUS):
        if name.startswith('MAATE_INSUMO_'):
            add(name, records(read_layer(PREVIOUS, name)), GROUPS[8], str(PREVIOUS))
    for (scope, cat), rows in updated.items():
        add('GI_'+scope+'_'+cat, rows, GROUPS[4], 'Gi* congelado: '+str(POLICE_SOURCE))
    for cat in CLASSES:
        add('HOTSPOT_'+cat, [(g, p) for (scope, category), rows in updated.items() if category==cat for g, p in rows if p['GI_CLASS'].startswith('HOTSPOT')], GROUPS[4])
    add('INCIDENTES_CLASIFICADOS', [(g, {**{k:v for k,v in p.items() if not k.startswith('CUB_')},
        **{'CUB_'+name: mask.covers(g) for name, mask in masks.items()}}) for g,p in events], GROUPS[5], str(PREVIOUS))
    add('MANZANAS_COBERTURA', block_results, GROUPS[13])
    add('CORREDORES', [(g, {'CORREDOR': key, 'LONGITUD_M': g.length}) for key, g in axes.items()], GROUPS[6])
    all_cameras = cameras+municipal+police
    unique_sites = {}
    for g, p in all_cameras:
        unique_sites.setdefault(g.wkb, (g, []))[1].append(p.get('ID_CAMARA') or p.get('ID_PROPUESTA') or p.get('ID_POLICIA'))
    add('BUFFERS_SITIOS_200M', [(g.buffer(200, quad_segs=64), {'IDS': '|'.join(ids), 'N_CAMARAS': len(ids), 'RADIO_M': 200}) for g, ids in unique_sites.values()], GROUPS[3])
    for name, mask in masks.items():
        add('COBERTURA_'+name, [(mask, {'ESCENARIO': name, 'RADIO_M': 200, 'METODO': 'BUFFER UNION DISUELTA'})], GROUPS[3])
    camera_tree = STRtree([g for g, _ in all_cameras])
    residuals = []
    for key, label in zip(KEYS+('QUEBRADA_LAS_ABRAS',), ('MACAJI', 'ANILLO', 'CICLOVIAS', 'LAS_ABRAS')):
        axis = axes[key]; rows = []
        for i, segment in enumerate(parts(axis.difference(c), 1), 1):
            index = int(camera_tree.nearest(segment)); point, props = all_cameras[index]
            start, end = segment.coords[0], segment.coords[-1]
            fields = {'ID': f'{label}-{i:04}', 'LONGITUD_M': segment.length, 'INICIO_X': start[0], 'INICIO_Y': start[1],
                'FIN_X': end[0], 'FIN_Y': end[1], 'CAMARA_MAS_CERCANA': props.get('ID_CAMARA') or props.get('ID_PROPUESTA') or props.get('ID_POLICIA'),
                'DIST_CAMARA_M': segment.distance(point), 'METODO_DIST': 'Distancia minima entre segmento completo y punto de camara'}
            rows.append((segment, fields)); residuals.append({**fields, 'CORREDOR': key})
        if rows:
            add('BRECHA_'+label+'_FINAL', rows, GROUPS[11])
        else:
            frame=gpd.GeoDataFrame(columns=['ID','LONGITUD_M','INICIO_X','INICIO_Y','FIN_X','FIN_Y','CAMARA_MAS_CERCANA','DIST_CAMARA_M','geometry'],geometry='geometry',crs=32717)
            pyogrio.write_dataframe(frame, PACKAGE, layer='BRECHA_'+label+'_FINAL',geometry_type='LineString')
            jsave('BRECHA_'+label+'_FINAL.geojson', {'type':'FeatureCollection','features':[]})
            catalog.append({'name':'BRECHA_'+label+'_FINAL','group':GROUPS[11],'records':0,'crs':'EPSG:32717','source':'Cobertura total; no remanentes','fields':list(frame.columns[:-1])})
        add('CUBIERTO_'+label+'_FINAL', [(g, {'CORREDOR': key, 'ESTADO': 'CUBIERTO'}) for g in parts(axis.intersection(c),1)], GROUPS[6])
    municipal_changes = []
    old_by_id = {p['ID_PROPUESTA']: (g,p) for g,p in municipal_old}
    for g,p in municipal:
        old, old_p = old_by_id[p['ID_PROPUESTA']]
        disk = g.buffer(200,quad_segs=64)
        municipal_changes.append({'ID':p['ID_PROPUESTA'],'GRUPO':p['GRUPO'],'POSICION_ANTERIOR':f'{old.x},{old.y}',
            'POSICION_FINAL':f'{g.x},{g.y}','DISTANCIA_MOVIMIENTO_M':g.distance(old),'CAMBIO':not g.equals(old),
            'MOTIVO':p.get('METODO_FINAL') if p['GRUPO']=='RED_ESTRUCTURAL' else 'Mantener posicion aceptada; no se demuestra mejora que justifique moverla',
            **{'COBERTURA_ANTES_'+key+'_M':axes[key].intersection(old.buffer(200,quad_segs=64)).length for key in axes},
            **{'COBERTURA_DESPUES_'+key+'_M':axes[key].intersection(disk).length for key in axes}})
    abras_review=[]
    for g,p in municipal:
        if p['GRUPO']!='LAS_ABRAS': continue
        other=coverage(cameras+[r for r in municipal if r[1]['ID_PROPUESTA']!=p['ID_PROPUESTA']])
        disk=g.buffer(200,quad_segs=64)
        abras_review.append({'ID':p['ID_PROPUESTA'],'DECISION':'MANTENER','X':g.x,'Y':g.y,
            'EJE_MAATE_DIST_M':g.distance(axes['QUEBRADA_LAS_ABRAS']),
            'MAATE_CUBIERTO_M':axes['QUEBRADA_LAS_ABRAS'].intersection(disk).length,
            'MAATE_EXCLUSIVO_M':axes['QUEBRADA_LAS_ABRAS'].intersection(disk.difference(other)).length,
            'POBLACION_ASOCIADA':context.population(disk)[0],
            'CUNDUANA_PUNTOS_200M':sum(disk.covers(q) for q,_ in records(read_layer(PREVIOUS,'CUNDUANA_PUNTOS_CRITICOS'))),
            'MOTIVO':'Cruce vial exacto MAATE aceptado en la corrida anterior; cobertura exclusiva y sectores poblados. Cunduana distante: no se inventa coincidencia.'})
    changes_fields=['ID_ANTERIOR','ID_FINAL','CANDIDATO_ANTERIOR','CANDIDATO_FINAL','UBICACION_ANTERIOR','UBICACION_FINAL','MOTIVO','DV_NUEVOS_ANTES','DV_NUEVOS_DESPUES','SOLAPE_ANTES','SOLAPE_DESPUES','D_ANTES','D_DESPUES','V_ANTES','V_DESPUES']
    tables={'CAMBIOS_MUNICIPALES':municipal_changes,'POLICIA_COMPARACION_ALTERNATIVAS':options,
        'POLICIA_BENEFICIO_FINAL':police_metrics,'POLICIA_DECISIONES':decisions,'LAS_ABRAS_CONTROL':abras_review,
        'COBERTURA_TERRITORIAL':territorial,'COBERTURA_POBLACIONAL':population,'INCIDENTES_CUBIERTOS':inc,
        'HOTSPOTS_ATENDIDOS':hot_stats,'CORREDORES_CUBIERTOS':corridors,'SEGMENTOS_SIN_COBERTURA':residuals}
    csvsave('POLICIA_CAMBIOS_FINAL',police_changes,changes_fields)
    for name,rows in tables.items():csvsave(name,rows)
    summary=[]
    def summary_row(label,fn):summary.append({'INDICADOR':label,**{str(count):fn(s) for s,count in zip('ABC',(103,153,183))}})
    summary_row('Territorio urbano potencialmente cubierto (%)',lambda s:next(r['PCT_URBANO'] for r in territorial if r['ESCENARIO']==s))
    summary_row('Territorio cantonal potencialmente cubierto (%)',lambda s:next(r['PCT_CANTON'] for r in territorial if r['ESCENARIO']==s))
    summary_row('Poblacion urbana estimada cubierta (%)',lambda s:next(r['PCT_CUBIERTO'] for r in population if r['ESCENARIO']==s))
    for cat in CLASSES:
        summary_row(cat+' eventos cantonales cubiertos (%)',lambda s,cat=cat:next(r['PCT_CUBIERTO'] for r in inc if r['ESCENARIO']==s and r['AMBITO']=='CANTONAL' and r['CATEGORIA']==cat))
        for field in ('CUBIERTO','PARCIAL','SIN_COBERTURA'):
            summary_row(cat+' Hot Spots '+field,lambda s,cat=cat,field=field:sum(r[field] for r in hot_stats if r['ESCENARIO']==s and r['CATEGORIA']==cat))
    for key in axes:summary_row(key+' (%)',lambda s,key=key:next(r['PCT_CUBIERTO'] for r in corridors if r['ESCENARIO']==s and r['CORREDOR']==key))
    csvsave('INDICADORES_103_153_183',summary)
    for table in pyogrio.list_layers(PACKAGE):
        name, geom=table
        if geom is None:catalog.append({'name':name,'group':GROUPS[12] if name.startswith(('POLICIA','CAMBIOS','LAS_ABRAS')) else GROUPS[13],
            'records':len(pyogrio.read_dataframe(PACKAGE,layer=name)),'crs':'No aplica; tabla','source':'Calculos finales','fields':list(pyogrio.read_info(PACKAGE,layer=name)['fields'])})
    shutil.copytree(SOURCE/'insumos_originales',OUT/'insumos_originales',dirs_exist_ok=True)
    for filename in ('AUDITORIA_INSUMOS.json','ABRAS_COMPARACION.csv','ABRAS_SENSIBILIDAD.csv'):
        if (SOURCE/filename).exists():shutil.copy2(SOURCE/filename,OUT/filename)
    result={'generatedAt':datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'),
        'sourceHashes':protected,'radiusM':200,'crsMetric':'EPSG:32717','groups':list(GROUPS),
        'optimization':logs,'catalog':catalog,'territorial':territorial,'population':population,'incidents':inc,
        'hotspots':hot_stats,'corridors':corridors,'summary':summary,'policeChanges':police_changes,
        'policeMetrics':police_metrics,'municipalChanges':municipal_changes,'abrasReview':abras_review,
        'axisComparison':prior['axisComparison'],'axisSensitivity':prior['axisSensitivity'],
        'warnings':prior['warnings'],'giRecalculated':False,'commit':False,'push':False,'viewerModified':False}
    assert all(sha(Path(p))==digest for p,digest in protected.items())
    jsave('RESULTADOS.json',result)
    print(json.dumps({'summary':summary,'policeChanged':len(police_changes)}),flush=True)


if __name__=='__main__':main()
