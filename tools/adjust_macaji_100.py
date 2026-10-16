"""Constrained Macaji completion using source road nodes, without publishing changes."""
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from scipy.optimize import Bounds, LinearConstraint, linear_sum_assignment, milp
from scipy.sparse import coo_matrix, csr_matrix
from shapely import STRtree
from shapely.geometry import Point
from shapely.ops import unary_union

from build_police_camera_proposal import ROOT, read_layer, records, parts, sha, geojson, UNPROJECT

SOURCE = ROOT / 'data/seguridad-riobamba/REUBICACION_POL24_20261006'
PACKAGE = SOURCE / 'ESCENARIO_FINAL_183.gpkg'
CANDIDATES = ROOT / 'data/seguridad-riobamba/optimizacion-municipal-50-20261003/PROPUESTA_50_OPTIMIZADA.gpkg'
OUT = ROOT / 'data/seguridad-riobamba/AJUSTE_MACAJI_100_20261006'
MACAJI = 'BOULEVARD_MACAJI_BELLAVISTA'
EPS_M = 1e-6


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')


def mask(rows):
    return unary_union([g.buffer(200, quad_segs=64) for g, _ in rows])


def interval_constraints(targets, candidates):
    """Require every positive-length interval; preserve covered locations, not just totals."""
    disks = [g.buffer(200, quad_segs=64) for g, _ in candidates]
    tree = STRtree(disks)
    supports, impossible, lengths = set(), defaultdict(float), defaultdict(float)
    for label, target, fixed_mask in targets:
        for component in parts(target.difference(fixed_mask), 1):
            events = defaultdict(lambda: [[], []])
            events[0.0]; events[component.length]
            for index in tree.query(component, predicate='intersects'):
                for piece in parts(component.intersection(disks[int(index)]), 1):
                    low, high = sorted(component.project(Point(c)) for c in (piece.coords[0], piece.coords[-1]))
                    if high - low > EPS_M:
                        events[low][0].append(int(index))
                        events[high][1].append(int(index))
            active, last = Counter(), 0.0
            for distance in sorted(events):
                if distance - last > EPS_M:
                    support = tuple(sorted(i for i, count in active.items() if count > 0))
                    if support:
                        supports.add(support)
                        lengths[label, support] += distance - last
                    else:
                        impossible[label] += distance - last
                for i in events[distance][1]:
                    active[i] -= 1
                for i in events[distance][0]:
                    active[i] += 1
                last = distance
        print('INTERVALOS', label, len(supports), dict(impossible), flush=True)
    return sorted(supports), dict(impossible), disks, lengths


def main(protect_b=True, candidate_package=CANDIDATES):
    OUT.mkdir(parents=True, exist_ok=True)
    protected = {str(p): sha(p) for p in (PACKAGE, SOURCE / 'RESULTADOS.json', candidate_package)}
    existing = records(read_layer(PACKAGE, 'CAMARAS_EXISTENTES_103_FINAL'))
    municipal = records(read_layer(PACKAGE, 'PROPUESTA_MUNICIPAL_50_FINAL'))
    police = records(read_layer(PACKAGE, 'PROPUESTA_POLICIA_30_FINAL'))
    original = [r for r in municipal if r[1]['GRUPO'] == 'RED_ESTRUCTURAL']
    frozen = [r for r in municipal if r[1]['GRUPO'] != 'RED_ESTRUCTURAL']
    fixed_b, fixed_c = mask(existing + frozen), mask(existing + frozen + police)
    axes_rows = records(read_layer(PACKAGE, 'CORREDORES'))
    axes = {key: unary_union([g for g, p in axes_rows if p['CORREDOR'] == key])
            for key in dict.fromkeys(p['CORREDOR'] for _, p in axes_rows)}
    before_b = read_layer(PACKAGE, 'COBERTURA_B').geometry.iloc[0]
    before_c = read_layer(PACKAGE, 'COBERTURA_C').geometry.iloc[0]
    fixed_points = {g.wkb for g, _ in existing + frozen + police}
    candidates = [r for r in records(read_layer(candidate_package, 'CANDIDATOS_ESTRUCTURALES')) if r[0].wkb not in fixed_points]
    for row in original:
        if not any(row[0].equals_exact(g, 1e-6) for g, _ in candidates):
            candidates.append((row[0], {**row[1], 'ID_CANDIDATO': 'ACTUAL_' + row[1]['ID_PROPUESTA']}))
    current_indices = {next(i for i, (g, _) in enumerate(candidates) if g.equals_exact(point, 1e-6))
                       for point, _ in original}
    targets = [('MACAJI_COMPLETO_C', axes[MACAJI], fixed_c)]
    for key, axis in axes.items():
        if key != MACAJI:
            if protect_b:
                targets.append((key + '_B', axis.intersection(before_b), fixed_b))
            targets.append((key + '_C', axis.intersection(before_c), fixed_c))
    supports, impossible, disks, lengths = interval_constraints(targets, candidates)
    result = {'generatedAt': datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'),
              'sourceHashes': protected, 'existing': 103, 'municipal': 50, 'police': 30, 'radius_m': 200,
              'crs': 'EPSG:32717', 'candidates': len(candidates), 'constraints': len(supports),
              'method': 'Cobertura de intervalos lineales GIS; minimo numero de municipales estructurales movidas. '
                        'Nodos viales de fuente, sin coordenadas inventadas.',
              'protectedScenarios': ['B', 'C'] if protect_b else ['C'],
              'originalsModified': False, 'uncoverableM': impossible}
    if impossible:
        result['status'] = 'NO_FACTIBLE_EN_CANDIDATOS'
        save('AJUSTE.json', result)
        print(json.dumps(result), flush=True)
        return
    n = len(candidates)
    rows, cols = [], []
    for j, support in enumerate(supports):
        rows.extend([j] * len(support)); cols.extend(support)
    matrix = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(supports), n)).tocsr()
    assert all(set(support).intersection(current_indices) for (label, support) in lengths
               if label != 'MACAJI_COMPLETO_C'), 'La configuracion actual debe satisfacer todas las protecciones'
    constraints = [LinearConstraint(matrix, 1, np.inf),
                   LinearConstraint(csr_matrix(np.ones((1, n))), len(original), len(original))]
    objective = np.array([0.0 if i in current_indices else 1.0 for i in range(n)])
    solution = milp(objective, integrality=np.ones(n), bounds=Bounds(np.zeros(n), np.ones(n)),
                    constraints=constraints, options={'time_limit': 90, 'mip_rel_gap': 0})
    result.update(solverStatus=int(solution.status), solverMessage=solution.message)
    if solution.x is None:
        result['status'] = 'SIN_SOLUCION_VERIFICADA'
        minimum = milp(np.ones(n), integrality=np.ones(n), bounds=Bounds(np.zeros(n), np.ones(n)),
                       constraints=[constraints[0]], options={'time_limit': 90, 'mip_rel_gap': 0})
        result['minimumCountSolverStatus'] = int(minimum.status)
        if minimum.x is not None:
            selected_more = np.flatnonzero(minimum.x > .5).tolist()
            trial = unary_union([fixed_c] + [disks[i] for i in selected_more])
            assert axes[MACAJI].difference(trial).length < .001
            for label, target, fixed in targets:
                check = unary_union([fixed] + [disks[i] for i in selected_more])
                assert target.difference(check).length < .001, label
            result.update(minimumStructuralFor100=len(selected_more),
                          minimumMunicipalFor100=len(frozen) + len(selected_more),
                          minimumCountProven=minimum.status == 0,
                          minimumSolutionCandidates=[candidates[i][1]['ID_CANDIDATO'] for i in selected_more])
            save('MINIMO_PARA_100_DIAGNOSTICO.geojson', geojson([candidates[i] for i in selected_more]))
        lower_bounds = np.zeros(n)
        lower_bounds[list(current_indices)] = 1.
        additions = milp(objective, integrality=np.ones(n), bounds=Bounds(lower_bounds, np.ones(n)),
                         constraints=[constraints[0]], options={'time_limit': 60, 'mip_rel_gap': 0})
        result['additionsOnlySolverStatus'] = int(additions.status)
        if additions.x is not None:
            extra = [int(i) for i in np.flatnonzero(additions.x > .5) if i not in current_indices]
            extra_mask = unary_union([before_c] + [disks[i] for i in extra])
            assert axes[MACAJI].difference(extra_mask).length < .001
            result.update(additionsWithoutMovingCurrent=len(extra), additionsOnlyProven=additions.status == 0,
                          additionCandidates=[candidates[i][1]['ID_CANDIDATO'] for i in extra])
            save('ADICIONALES_SIN_MOVIMIENTOS_DIAGNOSTICO.geojson', geojson([candidates[i] for i in extra]))
        protected_supports = sorted({support for label, support in lengths if label != 'MACAJI_COMPLETO_C'})
        macaji_lengths = {support: length for (label, support), length in lengths.items() if label == 'MACAJI_COMPLETO_C'}
        macaji_supports = sorted(macaji_lengths)
        m = len(macaji_supports)
        rr, cc, vv = [], [], []
        for j, support in enumerate(macaji_supports):
            rr.append(j); cc.append(n + j); vv.append(1.)
            for i in support:
                rr.append(j); cc.append(i); vv.append(-1.)
        for j, support in enumerate(protected_supports, m):
            for i in support:
                rr.append(j); cc.append(i); vv.append(1.)
        coverage_matrix = coo_matrix((vv, (rr, cc)), shape=(m + len(protected_supports), n + m)).tocsr()
        lower = np.array([-np.inf] * m + [1.] * len(protected_supports))
        upper = np.array([0.] * m + [np.inf] * len(protected_supports))
        count_row = np.array([1.] * n + [0.] * m)
        weights = np.array([0.] * n + [macaji_lengths[support] for support in macaji_supports])
        maximum = milp(-weights, integrality=np.array([1] * n + [0] * m),
                       bounds=Bounds(np.zeros(n + m), np.ones(n + m)),
                       constraints=[LinearConstraint(coverage_matrix, lower, upper),
                                    LinearConstraint(csr_matrix(count_row[None, :]), len(original), len(original))],
                       options={'time_limit': 90, 'mip_rel_gap': 1e-7})
        result['maximum50SolverStatus'] = int(maximum.status)
        if maximum.x is not None:
            chosen = np.flatnonzero(maximum.x[:n] > .5).tolist()
            trial = unary_union([fixed_c] + [disks[i] for i in chosen])
            actual = axes[MACAJI].intersection(trial).length
            model = axes[MACAJI].intersection(fixed_c).length - maximum.fun
            assert abs(actual - model) < .001
            for label, target, fixed in targets[1:]:
                check = unary_union([fixed] + [disks[i] for i in chosen])
                assert target.difference(check).length < .001, label
            result.update(maximum50CoveredM=actual, maximum50Pct=actual / axes[MACAJI].length * 100,
                          maximum50UncoveredM=axes[MACAJI].difference(trial).length,
                          maximum50Proven=maximum.status == 0,
                          maximum50ChangedStructural=len(set(chosen) - current_indices),
                          diagnosticOnly=True)
            trial_rows = [candidates[i] for i in chosen]
            save('MAXIMO_50_DIAGNOSTICO.geojson', geojson(trial_rows))
        assert all(sha(Path(p)) == digest for p, digest in protected.items())
        save('AJUSTE.json', result)
        print(json.dumps(result), flush=True)
        return
    selected = np.flatnonzero(solution.x > .5).tolist()
    new_indices = [i for i in selected if i not in current_indices]
    removed = [(g, p) for g, p in original if not any(g.equals_exact(candidates[i][0], 1e-6) for i in selected)]
    # With the minimum change count fixed, prefer short movements to the replaced original nodes.
    if new_indices:
        count = len(new_indices)
        constraints.append(LinearConstraint(csr_matrix(objective[None, :]), count, count))
        distance_objective = np.array([0. if i in current_indices else min(g.distance(candidates[i][0]) for g, _ in original)
                                       for i in range(n)])
        refinement = milp(distance_objective, integrality=np.ones(n), bounds=Bounds(np.zeros(n), np.ones(n)),
                          constraints=constraints, options={'time_limit': 60, 'mip_rel_gap': 1e-6})
        result['tieBreakSolverStatus'] = int(refinement.status)
        if refinement.x is not None:
            selected = np.flatnonzero(refinement.x > .5).tolist()
            new_indices = [i for i in selected if i not in current_indices]
            removed = [(g, p) for g, p in original if not any(g.equals_exact(candidates[i][0], 1e-6) for i in selected)]
    new = [candidates[i] for i in new_indices]
    final = [r for r in municipal if r[1]['ID_PROPUESTA'] not in {p['ID_PROPUESTA'] for _, p in removed}]
    movements = []
    if removed:
        a, b = linear_sum_assignment(np.array([[g.distance(h) for h, _ in new] for g, _ in removed]))
        for i, j in zip(a, b):
            old, props = removed[int(i)]
            point, candidate = new[int(j)]
            lon, lat = UNPROJECT(point.x, point.y)
            final.append((point, {**props, 'ID_CANDIDATO': candidate['ID_CANDIDATO'],
                         'X': point.x, 'Y': point.y, 'LONGITUD': lon, 'LATITUD': lat,
                         'ORIGEN_CANDIDATO': candidate['ORIGEN_CANDIDATO'], 'GRADO_NODO': candidate['GRADO_NODO'],
                         'METODO_FINAL': 'Completar Macaji al100%, preservando tramos cubiertos de otros corredores B/C; minimo numero de movimientos',
                         'ESTADO': 'PROPUESTA_FINAL_ESTUDIO_NO_INSTALADA'}))
            movements.append({'ID': props['ID_PROPUESTA'], 'CANDIDATO_NUEVO': candidate['ID_CANDIDATO'],
                              'X_ANTES': old.x, 'Y_ANTES': old.y, 'X_DESPUES': point.x, 'Y_DESPUES': point.y,
                              'DESPLAZAMIENTO_M': old.distance(point), 'ORIGEN': candidate['ORIGEN_CANDIDATO']})
    final.sort(key=lambda r: r[1]['ID_PROPUESTA'])
    after_b, after_c = mask(existing + final), mask(existing + final + police)
    result['corridors'] = []
    for scenario, before, after in (('B', before_b, after_b), ('C', before_c, after_c)):
        for key, axis in axes.items():
            lost = axis.intersection(before).difference(after).length
            result['corridors'].append({'ESCENARIO': scenario, 'CORREDOR': key,
                                       'TOTAL_M': axis.length, 'ANTES_M': axis.intersection(before).length,
                                       'DESPUES_M': axis.intersection(after).length,
                                       'PERDIDOS_M': lost, 'NO_CUBIERTO_M': axis.difference(after).length})
            if key != MACAJI and (scenario == 'C' or protect_b):
                assert lost < .001, (scenario, key, lost)
    assert axes[MACAJI].difference(after_c).length < .001
    assert len(final) == len({p['ID_PROPUESTA'] for _, p in final}) == 50
    assert len({g.wkb for g, _ in final}) == 50
    assert all(sha(Path(p)) == digest for p, digest in protected.items())
    result.update(status='AJUSTE_FACTIBLE_VALIDADO', movedMunicipal=len(movements),
                  minimumMovesProven=solution.status == 0, movements=movements)
    save('AJUSTE.json', result)
    frame = gpd.GeoDataFrame([p for _, p in final], geometry=[g for g, _ in final], crs=32717)
    pyogrio.write_dataframe(frame, OUT / 'AJUSTE_MACAJI.gpkg', layer='MUNICIPALES_50_AJUSTADAS')
    save('MUNICIPALES_50_AJUSTADAS.geojson', geojson(final))
    pd.DataFrame(movements).to_csv(OUT / 'MOVIMIENTOS_MUNICIPALES.csv', index=False, encoding='utf-8-sig')
    print(json.dumps({k: v for k, v in result.items() if k != 'sourceHashes'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
