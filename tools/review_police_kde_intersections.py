"""Build a separate, reproducible police-camera alternative using urban KDE and major-road intersections."""
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyogrio
from pyproj import Transformer
from shapely import STRtree, covers, points
from shapely.geometry import Point, mapping
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'data/seguridad-riobamba/REUBICACION_POL24_20261007_B/ESCENARIO_FINAL_183.gpkg'
CONFLICT = ROOT / 'riobamba-conflictividad-data.js'
ROAD_GDB = Path(r'D:/codex/riobamba_matrix_review_20260921/cartografia_base/RIOBAMBA_Cartografia Base.gdb')
OUT = ROOT / 'data/seguridad-riobamba/propuesta-policia-kde-intersecciones-20261014'
RADIUS = 200.0
SIZE = 20.0
MAJOR = {'Expresa', 'Arterial A', 'Arterial B', 'Arterial P', 'Colectora'}
UNPROJECT = Transformer.from_crs(32717, 4326, always_xy=True).transform


def layer(path, name):
    return pyogrio.read_dataframe(path, layer=name).to_crs(32717)


def parts(geom):
    if geom.geom_type == 'LineString':
        yield geom
    elif hasattr(geom, 'geoms'):
        for part in geom.geoms:
            yield from parts(part)


def grid_data():
    text = CONFLICT.read_text(encoding='utf-8')
    data = json.loads(text.split('=', 1)[1].strip().rstrip(';'))
    return data['urbanGrid']


def source_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def kde(points_xy, grid, bandwidth):
    width, height = grid['width'], grid['height']
    west, south = grid['metricBounds'][0]
    east, north = grid['metricBounds'][1]
    size = grid['cellSize']
    density = np.zeros(width * height, dtype=np.float64)
    grouped = Counter((float(x), float(y)) for x, y in points_xy)
    radius = math.ceil(bandwidth / size)
    norm = 1e6 / (2 * math.pi * bandwidth**2 * (1 - math.exp(-.5)))
    for (px, py), weight in grouped.items():
        cx, cy = math.floor((px-west)/size), math.floor((north-py)/size)
        xs = np.arange(max(0, cx-radius-1), min(width-1, cx+radius+1)+1)
        ys = np.arange(max(0, cy-radius-1), min(height-1, cy+radius+1)+1)
        dx = west + (xs + .5) * size - px
        dy = north - (ys + .5) * size - py
        d2 = dy[:, None]**2 + dx[None, :]**2
        valid = d2 <= bandwidth**2
        indices = ys[:, None] * width + xs[None, :]
        density[indices[valid]] += weight * norm * np.exp(-.5 * d2[valid] / bandwidth**2)
    mask = np.zeros(width*height, dtype=bool)
    mask[np.asarray(grid['mask'], dtype=np.int64)] = True
    density[~mask] = 0
    return density, mask, west, north, size


def node_candidates(roads, urban, baseline_points):
    major_frame = roads[roads['TIPOLOGIA_'].astype(str).str.strip().isin(MAJOR)]
    major = unary_union(list(major_frame.geometry))
    network = unary_union(list(roads.geometry))
    degree, node_points = Counter(), {}
    for line in parts(network):
        for coord in (line.coords[0], line.coords[-1]):
            key = tuple(coord[:2])
            node_points[key] = Point(key)
            degree[key] += 1
    existing_tree = STRtree(baseline_points)
    rows = []
    for key, deg in degree.items():
        point = node_points[key]
        if deg < 3 or major.distance(point) > .05 or not urban.covers(point):
            continue
        if any(baseline_points[int(i)].distance(point) < 1 for i in existing_tree.query(point.buffer(1))):
            continue
        rows.append({'point': point, 'degree': int(deg)})
    return rows, major_frame, network


def export_geojson(path, rows):
    features = []
    for geom, props in rows:
        features.append({'type': 'Feature', 'properties': props,
                         'geometry': mapping(transform(UNPROJECT, geom))})
    path.write_text(json.dumps({'type': 'FeatureCollection', 'features': features},
                               ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def covered_kde(geom, cell_points, cell_ids, mask, densities):
    visible = np.asarray(covers(geom, cell_points), dtype=bool)
    covered_ids = cell_ids[visible]
    return {cat: float(values[covered_ids].sum() * SIZE * SIZE / 1e6 / (values[mask].sum() * SIZE * SIZE / 1e6))
            if values[mask].sum() else 0.0 for cat, values in densities.items()}


def gi_reference(geom, gi_layers):
    result = {}
    disk = geom.buffer(RADIUS, quad_segs=32) if geom.geom_type == 'Point' else geom
    for cat, (tree, rows) in gi_layers.items():
        nearby = [rows[int(i)] for i in tree.query(disk, predicate='intersects')]
        levels = [int(row.NIVEL) for row in nearby if str(row.GI_CLASS).startswith('HOTSPOT')]
        result[f'GI_{cat}_MAX_200M'] = max(levels, default=0)
    return result


def incident_counts(geom, event_rows):
    return {cat: sum(geom.covers(point) for point, category in event_rows if category == cat)
            for cat in ('DELINCUENCIA', 'VIOLENCIA')}


def hotspot_coverage(geom, gi_layers):
    out = {}
    for cat, (_, rows) in gi_layers.items():
        significant = [row.geometry for row in rows if str(row.GI_CLASS).startswith('HOTSPOT')]
        total = sum(g.area for g in significant)
        covered_area = sum(g.intersection(geom).area for g in significant)
        out[cat] = covered_area / total if total else 0.0
    return out


def minimum_assignment(cost):
    n = len(cost)
    u, v, matching, way = [0.0]*(n+1), [0.0]*(n+1), [0]*(n+1), [0]*(n+1)
    for i in range(1, n+1):
        matching[0] = i
        j0 = 0
        minimum, used = [math.inf]*(n+1), [False]*(n+1)
        while True:
            used[j0] = True
            i0, delta, j1 = matching[j0], math.inf, 0
            for j in range(1, n+1):
                if not used[j]:
                    value = cost[i0-1][j-1] - u[i0] - v[j]
                    if value < minimum[j]:
                        minimum[j], way[j] = value, j0
                    if minimum[j] < delta:
                        delta, j1 = minimum[j], j
            for j in range(n+1):
                if used[j]:
                    u[matching[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if matching[j0] == 0:
                break
        while True:
            j1 = way[j0]
            matching[j0] = matching[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = [0]*n
    for j in range(1, n+1):
        assignment[matching[j]-1] = j-1
    return assignment


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    grid = grid_data()
    incidents = layer(PKG, 'INCIDENTES_CLASIFICADOS')
    urban_incidents = incidents[(incidents['AMBITO'] == 'URBANO') & incidents['CATEGORIA'].isin(['DELINCUENCIA', 'VIOLENCIA'])]
    points_by_cat = {cat: [(g.x, g.y) for g in urban_incidents.loc[urban_incidents['CATEGORIA'] == cat].geometry]
                     for cat in ('DELINCUENCIA', 'VIOLENCIA')}
    kde_by_cat = {cat: kde(xy, grid, RADIUS)[0] for cat, xy in points_by_cat.items()}
    density = kde_by_cat['DELINCUENCIA'] + kde_by_cat['VIOLENCIA']
    _, mask, west, north, size = kde(points_by_cat['DELINCUENCIA'][:0], grid, RADIUS)
    width, height = grid['width'], grid['height']
    indices = np.flatnonzero(mask)
    ys, xs = np.divmod(indices, width)
    cell_points = points(west + (xs+.5)*size, north - (ys+.5)*size)

    platforms = layer(PKG, 'PLATAFORMAS_TERRITORIALES')
    urban = unary_union(list(platforms.geometry))
    roads = gpd.read_file(ROAD_GDB, layer='Vialidad_urbana').to_crs(32717)
    existing = layer(PKG, 'CAMARAS_EXISTENTES_103_FINAL')
    municipal = layer(PKG, 'PROPUESTA_MUNICIPAL_50_FINAL')
    current_police = layer(PKG, 'PROPUESTA_POLICIA_30_FINAL')
    base_points = [*existing.geometry, *municipal.geometry]
    base = layer(PKG, 'COBERTURA_B').geometry.union_all()
    candidates, major_frame, network = node_candidates(roads, urban, base_points)
    assert len(current_police) == 30
    if len(candidates) < 30:
        raise RuntimeError(f'Solo hay {len(candidates)} intersecciones elegibles; se requieren 30.')

    covered = np.zeros(width * height, dtype=bool)
    covered[indices] = np.asarray(covers(base, cell_points), dtype=bool)
    selected, trace = [], []
    coverage_geom = base
    gi_layers = {}
    for cat, name in [('DELINCUENCIA', 'GI_URBANO_DELINCUENCIA'), ('VIOLENCIA', 'GI_URBANO_VIOLENCIA')]:
        frame = layer(PKG, name)
        rows = list(frame.itertuples())
        gi_layers[cat] = (STRtree([row.geometry for row in rows]), rows)
    event_rows = [(g, p.CATEGORIA) for g, p in zip(urban_incidents.geometry, urban_incidents.itertuples())]
    for step in range(1, 31):
        best = None
        for i, candidate in enumerate(candidates):
            if candidate.get('selected') or candidate['point'].distance(coverage_geom) > RADIUS:
                continue
            p = candidate['point']
            x0, x1 = max(0, math.floor((p.x-RADIUS-west)/size)), min(width-1, math.floor((p.x+RADIUS-west)/size))
            y0, y1 = max(0, math.floor((north-(p.y+RADIUS))/size)), min(height-1, math.floor((north-(p.y-RADIUS))/size))
            gx, gy = np.meshgrid(np.arange(x0,x1+1), np.arange(y0,y1+1))
            flat = (gy*width+gx).ravel()
            cx, cy = west+(gx.ravel()+.5)*size, north-(gy.ravel()+.5)*size
            inside = (cx-p.x)**2+(cy-p.y)**2 <= RADIUS**2
            cells = flat[inside & mask[flat]]
            new = cells[~covered[cells]]
            mass_scale = size * size / 1e6
            dvgain = float(density[new].sum() * mass_scale)
            overlap = p.buffer(RADIUS).intersection(coverage_geom).area/(math.pi*RADIUS**2)
            rank = (dvgain, candidate['degree'], -overlap)
            if best is None or rank > best[0]:
                best = (rank, i, candidate, cells, float(kde_by_cat['DELINCUENCIA'][new].sum()*mass_scale),
                        float(kde_by_cat['VIOLENCIA'][new].sum()*mass_scale), overlap)
        if best is None:
            raise RuntimeError(f'No hay más candidatos conectados tras seleccionar {step-1}/30.')
        _, i, candidate, cells, gain_d, gain_v, overlap = best
        candidate['selected'] = True
        candidate['cells'] = cells
        candidate['step'] = step
        selected.append(candidate)
        covered[cells] = True
        coverage_geom = unary_union([coverage_geom, candidate['point'].buffer(RADIUS, quad_segs=64)])
        trace.append({'ORDEN_KDE': step, 'MASA_KDE_DV_NUEVA': gain_d+gain_v,
                      'MASA_KDE_D_NUEVA': gain_d, 'MASA_KDE_V_NUEVA': gain_v,
                      'FRACCION_SOLAPE_PREVIO': overlap, 'GRADO_NODO': candidate['degree']})
        print(f'Policía {step:02d}/30: KDE D+V marginal={gain_d+gain_v:.4f}; solape previo={overlap:.1%}', flush=True)

    old = current_police.geometry.tolist()
    new_points = [c['point'] for c in selected]
    distances = np.asarray([[a.distance(b) for b in new_points] for a in old])
    assignment = minimum_assignment(distances)
    moves = []
    out_features = []
    for old_i, new_i in enumerate(assignment):
        old_props = current_police.iloc[old_i].drop(labels='geometry').to_dict()
        c = selected[new_i]
        p = c['point']
        nearby = major_frame.geometry.distance(p)
        major_type = sorted(set(major_frame.loc[nearby <= .05, 'TIPOLOGIA_'].dropna().astype(str)))
        major_names = sorted(set(major_frame.loc[nearby <= .05, 'NOMBRE'].dropna().astype(str))) if 'NOMBRE' in major_frame else []
        gi_old, gi_new = gi_reference(old[old_i], gi_layers), gi_reference(p, gi_layers)
        move = {'ID_POLICIA': old_props.get('ID_POLICIA') or old_props.get('ID_POL'),
                'ID_CANDIDATO_NUEVO': f'KDE-INT-{new_i+1:04d}',
                'X_ANTES': old[old_i].x, 'Y_ANTES': old[old_i].y, 'X_DESPUES': p.x, 'Y_DESPUES': p.y,
                'DESPLAZAMIENTO_M': old[old_i].distance(p), 'TIPO_VIA_PRINCIPAL': '|'.join(major_type),
                'NOMBRE_VIA_PRINCIPAL': '|'.join(major_names),
                'GRADO_INTERSECCION': c['degree'], 'MASA_KDE_DV_NUEVA': trace[new_i]['MASA_KDE_DV_NUEVA'],
                'SOLAPE_PREVIO_PCT': trace[new_i]['FRACCION_SOLAPE_PREVIO']*100,
                **{f'{k}_ANTES':v for k,v in gi_old.items()},
                **{f'{k}_DESPUES':v for k,v in gi_new.items()}}
        moves.append(move)
        out_features.append((p, {**move, 'ESTADO': 'ALTERNATIVA_NO_APROBADA',
            'CRITERIO': 'KDE urbano D+V; Gi* referencia; nodo de via principal',
            'RADIO_M': RADIUS, 'COBERTURA_VISUAL_CERTIFICADA': False}))
    with (OUT/'MOVIMIENTOS_POLICIA_30.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(moves[0]));w.writeheader();w.writerows(moves)
    export_geojson(OUT/'PROPUESTA_POLICIA_30_KDE_INTERSECCIONES.geojson',out_features)
    old_combined = unary_union([layer(PKG, 'COBERTURA_B').geometry.union_all(),
                                unary_union([p.buffer(RADIUS, quad_segs=64) for p in old])])
    new_combined = coverage_geom
    kde_before = covered_kde(old_combined, cell_points, indices, mask, kde_by_cat)
    kde_after = covered_kde(new_combined, cell_points, indices, mask, kde_by_cat)
    event_before, event_after = incident_counts(old_combined, event_rows), incident_counts(new_combined, event_rows)
    gi_before, gi_after = hotspot_coverage(old_combined, gi_layers), hotspot_coverage(new_combined, gi_layers)
    results = {'status':'ALTERNATIVA_PARA_REVISION', 'crs':'EPSG:32717', 'radius_m':RADIUS,
        'urban_incidents_D':len(points_by_cat['DELINCUENCIA']), 'urban_incidents_V':len(points_by_cat['VIOLENCIA']),
        'major_road_types':sorted(MAJOR), 'major_road_features':len(major_frame),
        'candidate_major_intersections':len(candidates), 'selected':len(selected),
        'base_existing':len(existing), 'base_municipal_fixed':len(municipal), 'police_proposals':len(selected),
        'kde_grid':{'width':width,'height':height,'cell_m':size,'masked_cells':int(mask.sum()),'bandwidth_m':RADIUS},
        'kde_density_max_events_km2':{cat:float(values.max()) for cat,values in kde_by_cat.items()},
        'selection_method':'Greedy lexicographic ranking by incremental integrated D+V urban KDE over 20m cells within 200m buffers; equal event weights; each selected buffer intersects existing+municipal+previous proposal coverage. No weighted index.',
        'reference_method':'Existing Gi* cells retained for post-selection interpretation; Gi* not recalculated or used as the primary rank.',
        'limitations':['Buffer overlap is geometric continuity, not camera field of view. No height, azimuth, lens, building or visibility model was available.',
                       'Greedy solution is an alternative, not proof of a global optimum.',
                       'Municipal 50 and existing 103 geometries were held fixed.'],
        'source_sha256':{str(p.relative_to(ROOT)):source_hash(p) for p in [PKG,CONFLICT]},
        'selection_trace':trace,
        'total_incremental_kde_dv':sum(x['MASA_KDE_DV_NUEVA'] for x in trace),
        'comparison_before_after':{'kde_share_D_before':kde_before['DELINCUENCIA'],'kde_share_D_after':kde_after['DELINCUENCIA'],
            'kde_share_V_before':kde_before['VIOLENCIA'],'kde_share_V_after':kde_after['VIOLENCIA'],
            'events_D_before':event_before['DELINCUENCIA'],'events_D_after':event_after['DELINCUENCIA'],
            'events_V_before':event_before['VIOLENCIA'],'events_V_after':event_after['VIOLENCIA'],
            'hotspot_D_area_share_before':gi_before['DELINCUENCIA'],'hotspot_D_area_share_after':gi_after['DELINCUENCIA'],
            'hotspot_V_area_share_before':gi_before['VIOLENCIA'],'hotspot_V_area_share_after':gi_after['VIOLENCIA']},
        'moves_summary':{'changed_over_1m':sum(m['DESPLAZAMIENTO_M']>1 for m in moves),
            'distance_mean_m':float(np.mean([m['DESPLAZAMIENTO_M'] for m in moves])),
            'distance_max_m':float(max(m['DESPLAZAMIENTO_M'] for m in moves)),
            'mean_existing_overlap_pct':float(np.mean([m['SOLAPE_PREVIO_PCT'] for m in moves])),
            'max_existing_overlap_pct':float(max(m['SOLAPE_PREVIO_PCT'] for m in moves))},
        'gi_reference_site_counts':{cat:{'before':sum(m[f'GI_{cat}_MAX_200M_ANTES']>=90 for m in moves),
            'after':sum(m[f'GI_{cat}_MAX_200M_DESPUES']>=90 for m in moves)} for cat in ('DELINCUENCIA','VIOLENCIA')},
        'mean_preexisting_overlap_pct':100*np.mean([x['FRACCION_SOLAPE_PREVIO'] for x in trace]),
        'max_preexisting_overlap_pct':100*max(x['FRACCION_SOLAPE_PREVIO'] for x in trace)}
    (OUT/'RESULTADOS.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'METODOLOGIA.md').write_text('# Alternativa policial por KDE e intersecciones\n\n'
        'Corrida separada: no sustituye la propuesta publicada. Se conservan las 103 cámaras inventariadas y las 50 propuestas municipales.\n\n'
        'La selección prioriza la integral de KDE urbano de Delincuencia + Violencia que aporta cada radio de 200 m fuera de la cobertura acumulada. La malla y el kernel replican los parámetros del visor: EPSG:32717, celda 20 m, kernel gaussiano truncado y normalizado, peso 1 por registro. Los candidatos deben ser nodos de grado ≥3 coincidentes con vías Expresa, Arterial A/B/P o Colectora, dentro de las 18 Plataformas. Cada buffer nuevo debe intersectar la cobertura base o una propuesta previamente elegida. Gi* queda como referencia; no se recalcula.\n\n'
        'La unión de buffers solo indica continuidad geométrica de proximidad. No equivale a línea de vista real: para certificarla se requieren altura y orientación de cámaras, edificios/obstáculos y óptica. Las coordenadas son propuestas para revisión de campo.\n\n'
        'Consultar RESULTADOS.json, MOVIMIENTOS_POLICIA_30.csv y PROPUESTA_POLICIA_30_KDE_INTERSECCIONES.geojson.\n',encoding='utf-8')
    print('RESULTADOS', json.dumps({k:v for k,v in results.items() if k not in ('selection_trace','source_sha256')},ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
