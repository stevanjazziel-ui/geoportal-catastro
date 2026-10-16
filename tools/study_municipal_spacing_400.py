"""Joint node selection with 400 m same-axis separation and explicit retained cameras."""
import heapq
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linear_sum_assignment, milp
from scipy.sparse import coo_matrix, csr_matrix
from shapely.ops import unary_union
from shapely import STRtree

import study_current_municipal_nodes as module
from adjust_macaji_100 import interval_constraints
from audit_municipal_street_reach import road_catalog
from review_police_kde_intersections import source_hash
from review_police_verified_main_roads import normalized

ROOT = module.ROOT
OUT = ROOT / 'data/seguridad-riobamba/ESTUDIO_MUNICIPALES_CORRECCIONES_FACTIBLES_REV2_20261016'
RETAINED = {'MUN-028', 'MUN-035', 'MUN-040', 'MUN-046', 'MUN-039'}
MINIMUM, TOL = 400., .001


def bounded_routes(street, start):
    """Shortest source-edge distances, including same-name branches; no street transfer."""
    distance = {start: 0.}
    queue = [(0., start)]
    while queue:
        value, xy = heapq.heappop(queue)
        if value != distance[xy]:
            continue
        for end in street['adj'][xy]:
            candidate = value + math.dist(xy, end)
            if candidate < MINIMUM - TOL and candidate < distance.get(end, float('inf')):
                distance[end] = candidate
                heapq.heappush(queue, (candidate, end))
    return distance


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')


def canonical(value):
    text = re.sub(r'[^a-z0-9 ]', ' ', normalized(value))
    return ' '.join(w for w in text.split() if w not in {'avenida', 'av', 'calle'})


def fixed_road_associations(study, fixed, catalog):
    """Linear reference using documented street names; inventory geometry stays untouched."""
    documents = {r.ID_CAMARA: r._asdict() for r in study.existing.itertuples()}
    streets = defaultdict(list)
    matched, records, segment_cache = set(), [], {}
    names = {name: canonical(street['name']) for name, street in catalog.items()}
    for key, point in fixed:
        xy = (point.x, point.y)
        exact = [name for name, street in catalog.items() if xy in street['adj']]
        if exact:
            for name in exact:
                streets[name].append((key, xy, xy, 0., 0.))
                records.append({'ID_CAMARA': key, 'VIA': catalog[name]['name'],
                                'METODO': 'VERTICE_ORIGINAL_EXACTO', 'DIST_PUNTO_EJE_M': 0.})
            matched.add(key)
            continue
        document = documents.get(key, {})
        texts = [' ' + canonical(document.get(field, '')) + ' '
                 for field in ('CALLE_1', 'CALLE_2', 'DIR_ORIG')]
        for name, phrase in names.items():
            # Single-letter unnamed streets cannot establish a documented road identity.
            if len(phrase) < 4 or not any(' ' + phrase + ' ' in text for text in texts):
                continue
            if name not in segment_cache:
                edges = list(catalog[name]['edges'].values())
                segment_cache[name] = edges, STRtree(edges)
            edges, tree = segment_cache[name]
            indices = tree.query_nearest(point, all_matches=True)
            accepted = False
            for index in indices:
                edge = edges[int(index)]
                offset = point.distance(edge)
                # A street beyond the existing 200 m potential reach cannot establish
                # a usable road association solely from an inconsistent address.
                if offset > 200:
                    records.append({'ID_CAMARA': key, 'VIA': catalog[name]['name'],
                                    'METODO': 'DIRECCION_FUERA_RADIO200_NO_ASOCIADA',
                                    'DIST_PUNTO_EJE_M': offset})
                    continue
                along = edge.project(point)
                a, b = tuple(edge.coords[0]), tuple(edge.coords[-1])
                streets[name].append((key, a, b, along, edge.length - along))
                records.append({'ID_CAMARA': key, 'VIA': catalog[name]['name'],
                                'METODO': 'REFERENCIA_LINEAL_POR_DIRECCION_DOCUMENTADA',
                                'DIST_PUNTO_EJE_M': offset,
                                'X_REFERENCIA': edge.interpolate(along).x, 'Y_REFERENCIA': edge.interpolate(along).y,
                                'GEOMETRIA_INVENTARIO_MODIFICADA': False})
                accepted = True
            if accepted:
                matched.add(key)
    return streets, matched, records


def main():
    assert not OUT.exists(), 'No se sobrescribe un estudio existente'
    active = json.loads((ROOT / 'sig-bridge-active.json').read_text())
    module.PACKAGE = ROOT / active['root'] / 'ESCENARIO_FINAL_183.gpkg'
    study = module.Study()
    OUT.mkdir()
    protected = {str(p): source_hash(p) for p in (module.PACKAGE, ROOT / 'sig-bridge-active.json')}
    original = study.original
    editable = original.loc[~original.ID_PROPUESTA.isin(RETAINED)].reset_index(drop=True)
    retained = original.loc[original.ID_PROPUESTA.isin(RETAINED)]
    assert len(editable) == 19 and len(retained) == 5
    fixed = [(r.ID_CAMARA, r.geometry) for r in study.existing.itertuples()]
    fixed += [(r.ID_PROPUESTA, r.geometry) for r in study.frozen.itertuples()]
    fixed += [(r.ID_POLICIA, r.geometry) for r in study.police.itertuples()]
    fixed += [(r.ID_PROPUESTA, r.geometry) for r in retained.itertuples()]
    catalog = road_catalog(study.roads)
    fixed_streets, matched, association_records = fixed_road_associations(study, fixed, catalog)
    unresolved = [(key, point) for key, point in fixed if key not in matched]
    pool, rejected = [], []
    for candidate in study.candidates:
        if not candidate['principal'] and candidate['point'].distance(study.axes[module.MACAJI]) >= 200:
            continue
        point = candidate['point']
        xy = (point.x, point.y)
        conflicts = []
        for name in {normalized(v) for v in candidate['roads']}:
            street = catalog.get(name)
            if not street or not fixed_streets[name]:
                continue
            distances = bounded_routes(street, xy)
            for key, a, b, leg_a, leg_b in fixed_streets[name]:
                distance = min(distances.get(a, float('inf')) + leg_a,
                               distances.get(b, float('inf')) + leg_b)
                if distance < MINIMUM - TOL:
                    conflicts.append((key, distance, street['name']))
        pending = [key for key, p in unresolved if point.distance(p) < MINIMUM - TOL]
        if conflicts or pending:
            rejected.append({'candidate': candidate['id'], 'conflicts': conflicts, 'unresolvedNearbyFixed': pending})
        else:
            pool.append(candidate)
    strict_mask = unary_union([study.fixed, *[p.buffer(200, quad_segs=64) for p in retained.geometry],
                               *[c['point'].buffer(200, quad_segs=64) for c in pool]])
    strict_missing = study.axes[module.MACAJI].difference(strict_mask).length
    known_points = {(c['point'].x, c['point'].y): c for c in study.candidates}
    eligible_points = {(c['point'].x, c['point'].y) for c in pool}
    # Existing noncompliant positions may remain only under their original IDs.
    # They are not presented as new valid placements or as solved spacing cases.
    for row in editable.itertuples():
        xy = (row.geometry.x, row.geometry.y)
        if xy not in eligible_points:
            legacy = dict(known_points[xy])
            legacy['legacyCameraId'] = row.ID_PROPUESTA
            pool.append(legacy)
    n = len(pool)
    by_street = defaultdict(lambda: defaultdict(list))
    for j, candidate in enumerate(pool):
        point = candidate['point']
        for name in {normalized(v) for v in candidate['roads']}:
            if name in catalog:
                by_street[name][(point.x, point.y)].append(j)
    pairs = set()
    for name, placed in by_street.items():
        for start, indices in placed.items():
            distances = bounded_routes(catalog[name], start)
            for end in distances.keys() & placed.keys():
                pairs.update(tuple(sorted((a, b))) for a in indices for b in placed[end]
                             if a != b and not (pool[a].get('legacyCameraId') and pool[b].get('legacyCameraId')))
    fixed_b = unary_union([study.fixed, *[p.buffer(200, quad_segs=64) for p in retained.geometry]])
    supports, impossible, disks, lengths = interval_constraints(
        [(key, axis, fixed_b) for key, axis in study.axes.items()], [(c['point'], c) for c in pool])
    report = {'applied': False, 'published': False, 'baseRelease': active['releaseId'],
              'sourceHashes': protected, 'crs': 'EPSG:32717', 'minimumSameAxisM': MINIMUM,
              'retained': sorted(RETAINED), 'editableCount': 19, 'fixedCount': 164,
              'candidateCount': n, 'candidatePairConflicts': len(pairs),
              'strict400mMacajiUncoverableInCatalogM': strict_missing,
              'legacyPositionsRetainOriginalIdOnly': True,
              'fixedCamerasWithoutExactRoadMembership': [key for key, _ in unresolved],
              'fixedRoadAssociations': association_records,
              'uncoverableEvenUsingAllCandidatesM': impossible,
              'conservativeUnresolvedRule': 'No candidato a menos de400m rectos de una fija sin asociacion vial exacta. No se inventa asociacion.',
              'limitations': ['Las camaras retenidas pueden conservar separaciones menores a400m entre si: son excepciones explicitas.',
                              'Se usa la misma via nominal y sus aristas originales; no se conectan calzadas ni nombres distintos.',
                              'Los buffers son potenciales. No se certifica vision entre manzanas, al girar o frente a obstaculos.',
                              'Las excepciones locales nuevas son alternativas para conservar Macaji100 y no se aplican silenciosamente.']}
    save('AVANCE.json', report)
    if impossible.get(module.MACAJI, 0) > TOL:
        report['status'] = 'SIN_FACTIBILIDAD_EN_CATALOGO_RESTRINGIDO'
        save('RESULTADOS.json', report)
        print(json.dumps(report), flush=True)
        return
    intervals = [(key, support, length) for (key, support), length in lengths.items()]
    size = n + len(intervals)
    rr, cc, vv, lower, upper = [], [], [], [], []

    def add(entries, lo, hi):
        row = len(lower)
        for col, value in entries:
            rr.append(row); cc.append(col); vv.append(value)
        lower.append(lo); upper.append(hi)

    add([(j, 1) for j in range(n)], len(editable), len(editable))
    for a, b in sorted(pairs):
        add([(a, 1), (b, 1)], -np.inf, 1)
    junctions = defaultdict(list)
    for j, candidate in enumerate(pool):
        junctions[tuple(sorted(normalized(v) for v in candidate['roads']))].append(j)
    for indices in junctions.values():
        if len(indices) > 1:
            add([(j, 1) for j in indices], -np.inf, 1)
    for k, (key, support, length) in enumerate(intervals):
        if key == module.MACAJI:
            add([(j, 1) for j in support], 1, np.inf)
        else:
            add([(n + k, 1)] + [(j, -1) for j in support], -np.inf, 0)
    # Only MUN-043 and MUN-049 retain a required named axis among the editable IDs.
    required_counts = defaultdict(int)
    for key in editable.ID_PROPUESTA:
        if key in module.REQUIRED_AXES:
            required_counts[normalized(module.REQUIRED_AXES[key])] += 1
    for name, count in required_counts.items():
        add([(j, 1) for j, c in enumerate(pool) if name in {normalized(v) for v in c['principal']}
             and (not c.get('legacyCameraId') or normalized(module.REQUIRED_AXES.get(c['legacyCameraId'], '')) == name)], count, np.inf)
    matrix = coo_matrix((vv, (rr, cc)), shape=(len(lower), size)).tocsr()
    constraints = [LinearConstraint(matrix, lower, upper)]
    principal = np.r_[[int(bool(c['principal'])) for c in pool], np.zeros(len(intervals))]
    weights = {key: np.r_[np.zeros(n), [length if kind == key else 0 for kind, _, length in intervals]]
               for key in (module.RING, module.CYCLE)}
    corrected = np.r_[[int(not c.get('legacyCameraId')) for c in pool], np.zeros(len(intervals))]
    objectives = [('MAX_POSICIONES_COMPATIBLES_400M', corrected), ('MAX_CRUCES_PRINCIPALES', principal), ('MAX_ANILLO', weights[module.RING]),
                  ('MAX_CICLOVIAS', weights[module.CYCLE])]
    solution, logs = None, []
    for phase, weight in objectives:
        trial = milp(-weight, integrality=np.r_[np.ones(n), np.zeros(len(intervals))],
                     bounds=Bounds(np.zeros(size), np.ones(size)), constraints=constraints,
                     options={'time_limit': 25, 'mip_rel_gap': 1e-6})
        log = {'phase': phase, 'status': int(trial.status), 'message': trial.message,
               'objective': float(-trial.fun) if trial.x is not None else None,
               'mipGap': float(trial.mip_gap) if trial.x is not None else None}
        logs.append(log)
        report['solver'] = logs
        save('AVANCE.json', report)
        print(json.dumps(log), flush=True)
        if trial.x is None:
            break
        solution = trial
        best = float(weight @ trial.x)
        if phase in ('MAX_CRUCES_PRINCIPALES', 'MAX_POSICIONES_COMPATIBLES_400M'):
            constraints.append(LinearConstraint(csr_matrix(weight[None, :]), round(best), round(best)))
        else:
            constraints.append(LinearConstraint(csr_matrix(weight[None, :]), best - TOL, np.inf))
    if solution is None:
        report['status'] = 'SIN_SOLUCION_CONJUNTA_COMPROBADA'
        save('RESULTADOS.json', report)
        return
    chosen_indices = list(np.flatnonzero(solution.x[:n] > .5))
    assert len(chosen_indices) == len(editable)
    assert not any(a in chosen_indices and b in chosen_indices for a, b in pairs)
    chosen = [pool[j] for j in chosen_indices]
    cost = np.array([[row.geometry.distance(c['point']) if study.allowed(row.ID_PROPUESTA, c)
                     and (not c.get('legacyCameraId') or c['legacyCameraId'] == row.ID_PROPUESTA) else np.inf
                     for c in chosen] for row in editable.itertuples()])
    aa, bb = linear_sum_assignment(cost)
    assert np.isfinite(cost[aa, bb]).all()
    target = original.copy()
    movements = []
    for a, b in zip(aa, bb):
        row, candidate = editable.iloc[int(a)], chosen[int(b)]
        target.loc[target.ID_PROPUESTA.eq(row.ID_PROPUESTA), 'geometry'] = candidate['point']
        movements.append({'ID_PROPUESTA': row.ID_PROPUESTA, 'ID_CANDIDATO': candidate['id'],
                          'CRUCE': ' x '.join(candidate['roads']), 'VIA_PRINCIPAL': bool(candidate['principal']),
                          'EJE_PRINCIPAL': ' | '.join(candidate['principal']), 'OSM_IDS': '|'.join(candidate['osmIds']),
                          'GRADO_NODO': candidate['degree'], 'DESPLAZAMIENTO_M': row.geometry.distance(candidate['point']),
                          'PENDIENTE_SEPARACION_400M': bool(candidate.get('legacyCameraId')),
                          'X_ANTES': row.geometry.x, 'Y_ANTES': row.geometry.y,
                          'X_PROPUESTO': candidate['point'].x, 'Y_PROPUESTO': candidate['point'].y})
    mask = unary_union([study.fixed, *[p.buffer(200, quad_segs=64) for p in target.geometry]])
    coverage = study.coverage(mask)
    assert coverage[module.MACAJI]['uncoveredM'] <= TOL
    assert all(source_hash(Path(path)) == digest for path, digest in protected.items())
    target.to_file(OUT / 'ESTUDIO_24_NODOS.gpkg', layer='EJES_PRIORITARIOS', driver='GPKG', index=False)
    gpd.GeoDataFrame(movements, geometry=[chosen[int(b)]['point'] for b in bb], crs=32717).to_file(
        OUT / 'ALTERNATIVAS.geojson', driver='GeoJSON')
    import pandas as pd
    pd.DataFrame(movements).to_csv(OUT / 'MOVIMIENTOS.csv', index=False, encoding='utf-8-sig')
    report.update(status='CORRECCIONES_PARCIALES_FACTIBLES_NO_APLICADAS', sourcesUnchanged=True,
                  municipal=coverage, movements=movements,
                  movedCount=sum(r['DESPLAZAMIENTO_M'] > TOL for r in movements),
                  localExceptions=[r for r in movements if not r['VIA_PRINCIPAL']],
                  unresolvedRetainedSpacing=[r['ID_PROPUESTA'] for r in movements if r['PENDIENTE_SEPARACION_400M']],
                  relocatedCamerasNoKnownSameAxisConflict=True,
                  globalMinimumCertified=False)
    save('RESULTADOS.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'municipal', 'movedCount', 'localExceptions')}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
