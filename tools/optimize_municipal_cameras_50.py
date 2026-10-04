"""Separate, reproducible municipal planning review. Never updates the production viewer."""
import csv
import hashlib
import json
import math
import unicodedata
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pyogrio
from pyproj import Transformer
from scipy.optimize import linear_sum_assignment
from shapely import STRtree, force_2d
from shapely.geometry import Point, mapping
from shapely.ops import transform, unary_union

from build_current_camera_diagnosis import parts, pct, sha, ROOT, CLASSES, CORRIDORS

OUT = ROOT / 'data/seguridad-riobamba/optimizacion-municipal-50-20261003'
BASE = ROOT / 'data/seguridad-riobamba/diagnostico-actual-103-20261002'
GPKG = BASE / 'DIAGNOSTICO_ACTUAL_103_200M.gpkg'
ORIGINAL = Path('C:/Users/PC/Downloads/PROPUESTA_CAMARAS_RIOBAMBA_200M.csv')
PREVIOUS = ROOT / 'data/seguridad-riobamba/correccion-propuesta-corredores-20261002/PROPUESTA_CAMARAS_RIOBAMBA_CORREGIDA_200M.csv'
ROADS = Path('C:/Users/PC/Downloads/barrios y plataformas/vias/vias_canton_riobamba_utm.shp')
LIMITS = Path('C:/Users/PC/Downloads/barrios y plataformas/cartografia base/CARTOGRAFIA_BASE/LIMITES_URBANOS_RURALES/LIMITES_URBANO_RURAL_PUGS2025.shp')
ROAD_GDB = Path('D:/codex/riobamba_matrix_review_20260921/cartografia_base/RIOBAMBA_Cartografia Base.gdb')
AXIS_KEYS = ('ANILLO_VIAL', 'CICLOVIAS', 'BOULEVARD_MACAJI_BELLAVISTA')
RADIUS = 200
TIE_M = 1e-6
UNPROJECT = Transformer.from_crs(32717, 4326, always_xy=True).transform
EQUIPMENT_LAYERS = ('Iglesias', 'Salud_publica_MSP', 'Salud_privada_MSP', 'Unidades_Educativas', 'Centralidades')


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value)) if not unicodedata.combining(c)).upper().replace(' ', '_')


def read_layer(path, name=None):
    frame = pyogrio.read_dataframe(path, layer=name).to_crs(32717)
    frame.geometry = frame.geometry.map(lambda g: force_2d(g) if g is not None else None)
    return frame


def records(frame):
    def value(v):
        if isinstance(v, (float, np.floating)) and not math.isfinite(v):
            return None
        return v.item() if isinstance(v, np.generic) else v
    return [(row.geometry, {k: value(v) for k, v in row.drop(labels='geometry').to_dict().items()}) for _, row in frame.iterrows()]


def save_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf-8')


def save_csv(name, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def save_layer(name, rows, package):
    frame = gpd.GeoDataFrame([p for _, p in rows], geometry=[g for g, _ in rows], crs=32717)
    pyogrio.write_dataframe(frame, package, layer=name)
    save_json(name + '.geojson', {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': p, 'geometry': mapping(transform(UNPROJECT, g)) if g is not None else None}
        for g, p in rows]})
    return {'name': name, 'records': len(rows), 'crs': 'EPSG:32717', 'fields': list(frame.columns[:-1])}


def road_nodes(network):
    """Node exact source lines, counting segment ends; no snapping or interpolated locations."""
    degrees, points = Counter(), {}
    for line in parts(network, 1):
        for coordinate in (line.coords[0], line.coords[-1]):
            key = tuple(coordinate[:2])
            points[key] = Point(key)
            degrees[key] += 1
    return [(points[k], degree) for k, degree in degrees.items()]


def crossing_points(geom):
    # Coincident lines have endpoints, not necessarily street intersections.
    return parts(geom, 0)


def unique_candidates(rows, canton):
    result = {}
    for point, origin, degree in rows:
        if not canton.covers(point) or point.is_empty or not point.is_valid:
            continue
        key = (round(point.x, 5), round(point.y, 5))
        if key not in result:
            result[key] = {'point': point, 'origins': set(), 'degree': degree}
        result[key]['origins'].add(origin)
        result[key]['degree'] = max(result[key]['degree'], degree)
    return [result[k] for k in sorted(result)]


class Evidence:
    def __init__(self, events, hot, equipment, current):
        self.events, self.hot, self.equipment, self.current = events, hot, equipment, current
        self.event_tree = STRtree([g for g, _ in events])
        self.hot_tree = STRtree([g for g, _ in hot])
        self.equip_tree = STRtree([g for g, _ in equipment])

    def candidate(self, item):
        point = item['point']
        disk = point.buffer(RADIUS, quad_segs=64)
        events = [int(i) for i in self.event_tree.query(disk, predicate='intersects')
                  if self.events[int(i)][1]['AMBITO'] != 'EXTERNO_CANTON']
        hot = [int(i) for i in self.hot_tree.query(disk, predicate='intersects')
               if self.hot[int(i)][0].intersection(disk).area > .01]
        equipment = [int(i) for i in self.equip_tree.query(disk, predicate='intersects')]
        item.update(disk=disk, events=events, hot=hot, equipment=equipment,
                    existingOverlapPct=pct(disk.intersection(self.current).area, disk.area))
        return item

    def detail(self, item):
        counts = Counter(self.events[i][1]['CATEGORIA'] for i in item['events'])
        names = sorted(set(f"{self.hot[i][1]['AMBITO']}:{self.hot[i][1]['CATEGORIA']}:{self.hot[i][1]['NIVEL']}%" for i in item['hot']))
        equipment = Counter(self.equipment[i][1]['FUENTE_CAPA'] for i in item['equipment'])
        return {'HOTSPOT_RELACIONADO': '|'.join(names) or 'Sin interseccion positiva con Hot Spot',
                'INCIDENTES_ENTORNO': len(item['events']),
                **{'INC_' + k: counts.get(k, 0) for k in CLASSES},
                'EQUIPAMIENTOS_ENTORNO': '|'.join(f'{k}:{v}' for k, v in sorted(equipment.items())) or 'Sin registros en las capas consultadas',
                'COBERTURA_PREVIA': item['existingOverlapPct'],
                'ORIGEN_CANDIDATO': '|'.join(sorted(item['origins'])), 'GRADO_NODO': item['degree']}


def rural_selection(centers, limits, nodes, canton, evidence, current):
    selected, audit, areas, candidates = [], [], [], []
    coverage = current
    for center, props in centers:
        parish = props['PARROQUIA']
        polygons = [g for g, p in limits if str(p['FIRST_clas']).lower() == 'urbano' and g.covers(center)]
        assert len(polygons) == 1, f'Cabecera PUGS no univoca: {parish}'
        area = polygons[0].intersection(canton)
        areas.append((area, {'PARROQUIA': parish, 'FUENTE': 'PUGS2025: poligono urbano que contiene la cabecera GIS; copia dentro del canton'}))
        rows = [(p, 'INTERSECCION_VIAL_CANTONAL', d) for p, d in nodes if d >= 3 and area.covers(p)]
        assert len(rows) >= 2, f'Faltan dos intersecciones reales en {parish}'
        pool = [evidence.candidate(c) for c in unique_candidates(rows, canton)]
        for i, c in enumerate(pool):
            c['candidateId'] = f'RUR-{normalized(parish)}-{i+1:04d}'
        used = set()
        for iteration in (1, 2):
            best = None
            for i, c in enumerate(pool):
                if i in used:
                    continue
                new = c['disk'].difference(coverage)
                new_events = [j for j in c['events'] if area.covers(evidence.events[j][0]) and new.covers(evidence.events[j][0])]
                count = Counter(evidence.events[j][1]['CATEGORIA'] for j in new_events)
                hot_area = sum(evidence.hot[j][0].intersection(new).intersection(area).area
                               for j in c['hot'] if evidence.hot[j][1]['AMBITO'] == 'RURAL'
                               and evidence.hot[j][1]['CATEGORIA'] in CLASSES[:2])
                new_equipment = sum(area.covers(evidence.equipment[j][0]) and new.covers(evidence.equipment[j][0]) for j in c['equipment'])
                # Guarantee the GIS center is covered, then evidence and nonredundant locality area.
                center_gain = int(not coverage.covers(center) and c['disk'].covers(center))
                ranking = (center_gain, count['DELINCUENCIA'] + count['VIOLENCIA'], count['CONVIVENCIA'],
                           new_equipment, hot_area, new.intersection(area).area,
                           -c['existingOverlapPct'], -center.distance(c['point']))
                if best is None or ranking > best[0]:
                    best = (ranking, i, c, new_events, new.intersection(area).area)
            rank, i, c, new_events, new_area = best
            used.add(i)
            c.update(group='CABECERA_RURAL', parish=parish, iteration=iteration,
                     principal='Centralidad vial y nueva evidencia territorial en cabecera PUGS',
                     marginalAreaM2=new_area, newEvents=len(new_events), ranking=list(rank))
            selected.append(c)
            coverage = coverage.union(c['disk'])
        assert coverage.covers(center), parish
        candidates.extend((c['point'], {'ID_CANDIDATO': c['candidateId'], 'PARROQUIA': parish,
            'SELECCIONADO': i in used, **evidence.detail(c)}) for i, c in enumerate(pool))
        pair = selected[-2:]
        audit.append({'PARROQUIA': parish, 'CANDIDATOS_VIALES': len(pool), 'CAMARAS_PROPUESTAS': 2,
                      'SEPARACION_PAR_M': pair[0]['point'].distance(pair[1]['point']),
                      'COBERTURA_ACTUAL_CENTRO': current.covers(center), 'COBERTURA_PROPUESTA_CENTRO': coverage.covers(center),
                      'COB_ACTUAL_ENTORNO_200_PCT': props['COB_ENTORNO_200_PCT'],
                      'COB_FUTURA_ENTORNO_200_PCT': pct(center.buffer(200, quad_segs=64).intersection(coverage).area, center.buffer(200, quad_segs=64).area),
                      'COB_ACTUAL_PUGS_PCT': pct(area.intersection(current).area, area.area),
                      'COB_FUTURA_PUGS_PCT': pct(area.intersection(coverage).area, area.area),
                      'HOTSPOT_RURAL': props['HOTSPOT_RURAL'], 'INCIDENTES_ENTORNO': props['INCIDENTES'],
                      'POBLACION_LOCAL': None})
    return selected, coverage, audit, areas, candidates


def linear_selection(pool, axes, keys, n, coverage, evidence, group):
    """Greedy exact marginal line benefit; no weights, sampling, quota, or distance enforcement."""
    used, selected, trace = set(), [], []
    for iteration in range(1, n + 1):
        remaining = {key: axes[key].difference(coverage) for key in keys}
        best, maximum = None, -1.
        for i, c in enumerate(pool):
            if i in used:
                continue
            gains = {key: remaining[key].intersection(c['disk']).length for key in keys}
            total = sum(gains.values())
            if total < maximum - TIE_M:
                continue
            new_events = sum(not coverage.covers(evidence.events[j][0]) for j in c['events'])
            new_hot_area = sum(evidence.hot[j][0].intersection(c['disk'].difference(coverage)).area for j in c['hot'])
            overlap = pct(c['disk'].intersection(coverage).area, c['disk'].area)
            near_distance = min([c['point'].distance(p['point']) for p in selected] or [math.inf])
            continuity = int(300 <= near_distance <= 350)
            # Only numerical ties activate secondary criteria; primary marginal length is never sacrificed.
            ranking = (tuple(gains[key] for key in keys), sum(v > TIE_M for v in gains.values()),
                       new_hot_area, new_events, continuity, -overlap, c['degree'])
            if best is None or total > maximum + TIE_M or (abs(total-maximum) <= TIE_M and ranking > best[0]):
                maximum = total
                best = (ranking, i, c, gains, overlap, new_events, new_hot_area, near_distance)
        assert best and maximum > TIE_M, f'Sin beneficio adicional en {group} iteracion {iteration}'
        rank, i, c, gains, overlap, new_events, new_hot, near_distance = best
        used.add(i)
        c.update(group=group, parish='', iteration=iteration, gains=gains, marginalM=maximum,
                 newEvents=new_events, overlapPct=overlap,
                 principal='Maximo beneficio marginal de longitud adicional sobre ' + ' + '.join(keys))
        before = {key: axes[key].intersection(coverage).length for key in keys}
        coverage = coverage.union(c['disk'])
        after = {key: axes[key].intersection(coverage).length for key in keys}
        assert all(abs(after[k]-before[k]-gains[k]) < .001 for k in keys), (before, after, gains)
        trace.append({'GRUPO': group, 'ITERACION': iteration, 'ID_CANDIDATO': c['candidateId'],
            'X': c['point'].x, 'Y': c['point'].y, 'BENEFICIO_MARGINAL_M': maximum,
            **{'NUEVO_' + k + '_M': gains[k] for k in keys},
            'CORREDORES_NUEVOS': sum(v > TIE_M for v in gains.values()),
            'INCIDENTES_ADICIONALES': new_events, 'HOTSPOT_AREA_ADICIONAL_M2': new_hot,
            'SOLAPE_UNION_PREVIA_PCT': overlap,
            'DIST_PROPUESTA_PREVIA_M': near_distance if math.isfinite(near_distance) else None})
        selected.append(c)
        print(f'{group} {iteration}/{n}: {maximum:.2f} m nuevos', flush=True)
    return selected, coverage, trace


def candidate_rows(pool, axes, current, evidence, selected):
    chosen = {c['candidateId'] for c in selected}
    remaining = {key: axis.difference(current) for key, axis in axes.items()}
    return [(c['point'], {'ID_CANDIDATO': c['candidateId'], 'SELECCIONADO': c['candidateId'] in chosen,
        'X': c['point'].x, 'Y': c['point'].y,
        **{'NUEVO_' + key + '_M': remaining[key].intersection(c['disk']).length for key in axes},
        'N_CORREDORES': sum(axes[key].intersection(c['disk']).length > TIE_M for key in axes),
        **evidence.detail(c)}) for c in pool]


def comparison(axes, masks):
    rows = []
    for key, axis in axes.items():
        values = {name: axis.intersection(mask).length for name, mask in masks.items()}
        rows.append({'CORREDOR': key, 'LONGITUD_TOTAL_M': axis.length,
            **{f'CUBIERTO_{k}_M': v for k, v in values.items()}, **{f'PCT_{k}': pct(v, axis.length) for k, v in values.items()},
            'INCREMENTO_M': values['OPTIMIZADA']-values['ACTUAL'],
            'INCREMENTO_PP': pct(values['OPTIMIZADA']-values['ACTUAL'], axis.length),
            'RESTANTE_M': axis.length-values['OPTIMIZADA'],
            'CAMBIO_VS_PREVIA_M': values['OPTIMIZADA']-values['PREVIA']})
    return rows


def assign_original(selected, original, previous, axes, evidence):
    """Matching labels minimizes movement within each immutable allocation group; never changes new geometry."""
    rows, moves = [], []
    groups = [('CABECERA_RURAL', parish) for parish in dict.fromkeys(c['parish'] for c in selected if c['group'] == 'CABECERA_RURAL')]
    groups += [('LAS_ABRAS', ''), ('RED_ESTRUCTURAL', '')]
    index = {id(row): i for i, row in enumerate(original)}
    previous_by_row = {i: row for i, row in enumerate(previous)}
    assert len(original) == len(previous) == 50
    for group, parish in groups:
        source_type = {'LAS_ABRAS': 'QUEBRADA_LAS_ABRAS', 'RED_ESTRUCTURAL': 'CORREDOR_ESTRUCTURAL'}.get(group, group)
        old = [r for r in original if r['TIPO'] == source_type and (not parish or r['SECTOR'] == parish)]
        new = [c for c in selected if c['group'] == group and c['parish'] == parish]
        assert len(old) == len(new), (group, parish, len(old), len(new))
        old_points = [Point(float(r['X']), float(r['Y'])) for r in old]
        distances = np.array([[p.distance(c['point']) for c in new] for p in old_points])
        a, b = linear_sum_assignment(distances)
        for j, k in zip(a, b):
            source, c = old[j], new[k]
            source_row = index[id(source)]
            prev = previous_by_row[source_row]
            assert prev['ID_PROP'] == source['ID_PROP']
            point = c['point']
            longitude, latitude = UNPROJECT(point.x, point.y)
            corridor_names = [key for key, axis in axes.items() if axis.intersection(c['disk']).length > TIE_M]
            detail = evidence.detail(c)
            gains = c.get('gains', {})
            reason = (f"Interseccion vial dentro de la cabecera PUGS de {parish}; seleccion {c['iteration']}/2. "
                      f"{c['newEvents']} eventos adicionales dentro de la localidad y {c['marginalAreaM2']:.1f} m2 nuevos de su area."
                      if group == 'CABECERA_RURAL' else
                      f"Nodo/cruce real; seleccion iterativa {c['iteration']}. Beneficio marginal {c['marginalM']:.1f} m "
                      + '; '.join(f'{key}:{v:.1f} m' for key, v in gains.items()) + '.')
            reason += f" Entorno 200 m: {detail['INCIDENTES_ENTORNO']} incidentes; solape con escenario actual {detail['COBERTURA_PREVIA']:.2f}%. Pendiente inspeccion de campo."
            props = {'ID_PROPUESTA': f'MUN-{source_row+1:03d}', 'ID_ORIGINAL': source['ID_PROP'], 'FILA_ORIGINAL': source_row+1,
                'GRUPO': group, 'SUBTIPO': 'INTERSECCION_CABECERA' if parish else 'CRUCE_VIAL_EJE' if group == 'LAS_ABRAS' else 'NODO_MULTICORREDOR' if len(corridor_names) >= 2 else 'NODO_CORREDOR',
                'X': point.x, 'Y': point.y, 'LONGITUD': longitude, 'LATITUD': latitude,
                'CRITERIO_PRINCIPAL': c['principal'],
                'CRITERIOS_SECUNDARIOS': ('Centro de cabecera; nuevos D/V y Convivencia; equipamientos; Gi* D/V rural; nueva area PUGS; menor solape'
                                          if parish else 'Interseccion/acceso real; Gi* disponible; incidentes directos; solape marginal; continuidad en empate numerico'),
                'CORREDOR': '|'.join(corridor_names), 'PARROQUIA': parish or None, **detail,
                'JUSTIFICACION': reason, 'ESTADO_VALIDACION': 'PROPUESTA_REVISADA', 'ID_CANDIDATO': c['candidateId'],
                'ORDEN_SELECCION_GRUPO': c['iteration'], 'BENEFICIO_MARGINAL_M': c.get('marginalM'),
                **{'NUEVO_' + key + '_M': gains.get(key) for key in AXIS_KEYS + ('QUEBRADA_LAS_ABRAS',)}}
            rows.append((point, props))
            original_point = old_points[j]
            previous_point = Point(float(prev['X']), float(prev['Y']))
            moves.append({'ID_PROPUESTA': props['ID_PROPUESTA'], 'ID_ORIGINAL': source['ID_PROP'], 'GRUPO': group,
                'PARROQUIA': parish, 'X_ORIGINAL': original_point.x, 'Y_ORIGINAL': original_point.y,
                'X_PREVIA': previous_point.x, 'Y_PREVIA': previous_point.y,
                'X_NUEVA': point.x, 'Y_NUEVA': point.y, 'DISTANCIA_MOVIMIENTO_M': original_point.distance(point),
                'DISTANCIA_VS_PREVIA_M': previous_point.distance(point), 'MOTIVO': reason})
    return sorted(rows, key=lambda r: r[1]['ID_PROPUESTA']), sorted(moves, key=lambda r: r['ID_PROPUESTA'])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = [GPKG, ORIGINAL, PREVIOUS, ROOT / 'riobamba-conflictividad-data.js', ROOT / 'riobamba-cantonal-data.js',
             ROOT / 'riobamba-hotspot-urbano-200m-data.js', ROOT / 'visor-seguridad-riobamba-v2.html', ROOT / 'riobamba-camaras-propuesta.js']
    paths += [p for p in BASE.iterdir() if p.is_file()]
    paths += [p for source in (ROADS, LIMITS) for p in source.parent.glob(source.stem + '.*') if p.suffix.lower() not in ('.lock', '.lck')]
    paths += [p for p in ROAD_GDB.iterdir() if p.is_file() and p.suffix.lower() not in ('.lock', '.lck')]
    protected = {str(p): sha(p) for p in paths}
    baseline = json.loads((BASE / 'RESULTADOS.json').read_text(encoding='utf-8'))
    cameras = read_layer(GPKG, 'CAMARAS_EXISTENTES_103')
    current = read_layer(GPKG, 'COBERTURA_ACTUAL_DISUELTA_200M').geometry.iloc[0]
    canton = read_layer(GPKG, 'LIMITE_CANTONAL').geometry.iloc[0]
    platform_rows = records(read_layer(GPKG, 'PLATAFORMAS_TERRITORIALES'))
    axes = {}
    prefixes = {'ANILLO_VIAL': 'ANILLO', 'CICLOVIAS': 'CICLOVIAS', 'BOULEVARD_MACAJI_BELLAVISTA': 'MACAJI_BELLAVISTA', 'QUEBRADA_LAS_ABRAS': 'LAS_ABRAS'}
    for key, prefix in prefixes.items():
        axes[key] = unary_union([g for status in ('CUBIERTO', 'SIN_COBERTURA') for g in read_layer(GPKG, f'{prefix}_{status}_200M').geometry])
    events = records(read_layer(GPKG, 'INCIDENTES_COBERTURA_ACTUAL'))
    hot = [row for scope in ('URBANO', 'RURAL') for cat in CLASSES for row in records(read_layer(GPKG, f'HOTSPOT_{scope}_{cat}'))]
    centers = records(read_layer(GPKG, 'CABECERAS_RURALES_DIAGNOSTICO'))
    roads = read_layer(ROADS)
    urban_roads = read_layer(ROAD_GDB, 'Vialidad_urbana')
    equipment = [(g, {'FUENTE_CAPA': layer}) for layer in EQUIPMENT_LAYERS for g in read_layer(ROAD_GDB, layer).geometry if g is not None and not g.is_empty]
    evidence = Evidence(events, hot, equipment, current)
    nodes = road_nodes(unary_union(list(roads.geometry)))
    urban_network = unary_union(list(urban_roads.geometry))
    urban_nodes = road_nodes(urban_network)
    rural, coverage, rural_audit, rural_areas, rural_candidates = rural_selection(centers, records(read_layer(LIMITS)), nodes, canton, evidence, current)
    print('Cabeceras revisadas:22 propuestas en11 localidades', flush=True)

    abras_axis = axes['QUEBRADA_LAS_ABRAS']
    abras_rows = [(p, 'CRUCE_ABRAS_VIALIDAD_URBANA', 0) for p in crossing_points(abras_axis.intersection(urban_network))]
    abras_rows += [(p, 'CRUCE_ABRAS_EJE_CANTONAL', 0) for p in crossing_points(abras_axis.intersection(unary_union(list(roads.geometry))))]
    abras_pool = [evidence.candidate(c) for c in unique_candidates(abras_rows, canton)]
    for i, c in enumerate(abras_pool):
        c['candidateId'] = f'ABR-{i+1:04d}'
    abras, coverage, abras_trace = linear_selection(abras_pool, axes, ('QUEBRADA_LAS_ABRAS',), 4, coverage, evidence, 'LAS_ABRAS')

    structural_rows = [(p, 'NODO_VIAL_URBANO', d) for p, d in urban_nodes if d >= 3 and any(axis.distance(p) <= RADIUS for key, axis in axes.items() if key in AXIS_KEYS)]
    for key in AXIS_KEYS:
        structural_rows += [(p, 'CRUCE_' + key + '_RED_VIAL', 0) for p in crossing_points(axes[key].intersection(urban_network))]
        for other in AXIS_KEYS:
            if other != key:
                structural_rows += [(p, 'CRUCE_CORREDORES', 0) for p in crossing_points(axes[key].intersection(axes[other]))]
    existing_new = [c['point'] for c in rural + abras]
    structural_pool = [evidence.candidate(c) for c in unique_candidates(structural_rows, canton) if all(c['point'].distance(p) > 1e-5 for p in existing_new)]
    for i, c in enumerate(structural_pool):
        c['candidateId'] = f'EST-{i+1:04d}'
    print(f'Candidatos: {len(abras_pool)} Abras; {len(structural_pool)} red estructural', flush=True)
    structural, future, structural_trace = linear_selection(structural_pool, axes, AXIS_KEYS, 24, coverage, evidence, 'RED_ESTRUCTURAL')
    selected = rural + abras + structural
    assert len(selected) == 50
    assert len({(c['point'].x, c['point'].y) for c in selected}) == 50
    assert all(c['point'].is_valid and canton.covers(c['point']) and (c['point'].x, c['point'].y) != (0, 0) for c in selected)
    with ORIGINAL.open(encoding='utf-8-sig', newline='') as stream:
        original = list(csv.DictReader(stream))
    with PREVIOUS.open(encoding='utf-8-sig', newline='') as stream:
        previous = list(csv.DictReader(stream))
    proposal, moves = assign_original(selected, original, previous, axes, evidence)
    masks = {'ACTUAL': current, 'ORIGINAL': current.union(unary_union([Point(float(r['X']), float(r['Y'])).buffer(200, quad_segs=64) for r in original])),
             'PREVIA': current.union(unary_union([Point(float(r['X']), float(r['Y'])).buffer(200, quad_segs=64) for r in previous])), 'OPTIMIZADA': future}
    corridor_stats = comparison(axes, masks)
    differences = []
    for old in baseline['corridors']:
        value = next(r for r in corridor_stats if r['CORREDOR'] == old['key'])
        delta = value['CUBIERTO_ACTUAL_M']-old['coveredM']
        assert abs(delta) < .001 and abs(value['LONGITUD_TOTAL_M']-old['totalM']) < .001
        differences.append({'CORREDOR': old['key'], 'DIFERENCIA_LINEA_BASE_M': delta})

    incident_stats, incident_rows = [], []
    for point, p in events:
        incident_rows.append((point, {**p, 'CUBIERTO_OPTIMIZADA': future.covers(point)}))
    for scope in ('BASE_COMPLETA', 'CANTONAL', 'URBANO', 'RESTO_CANTON', 'EXTERNO_CANTON'):
        for cat in CLASSES:
            rows = [p for _, p in incident_rows if p['CATEGORIA'] == cat and (scope == 'BASE_COMPLETA' or (scope == 'CANTONAL' and p['AMBITO'] != 'EXTERNO_CANTON') or p['AMBITO'] == scope)]
            actual, after = sum(p['CUBIERTO_200'] for p in rows), sum(p['CUBIERTO_OPTIMIZADA'] for p in rows)
            assert actual == baseline['incidents'][scope][cat]['covered']
            incident_stats.append({'AMBITO': scope, 'CATEGORIA': cat, 'TOTAL_EVENTOS': len(rows),
                'CUBIERTOS_ANTES': actual, 'PCT_ANTES': pct(actual, len(rows)), 'CUBIERTOS_DESPUES': after,
                'PCT_DESPUES': pct(after, len(rows)), 'INCREMENTO': after-actual, 'SIN_COBERTURA_DESPUES': len(rows)-after})
    hotspot_stats, hot_rows = [], []
    for geom, p in hot:
        area = geom.intersection(future).area
        hot_rows.append((geom, {**p, 'AREA_CUB_FUT_M2': area, 'COB_FUTURA_PCT': pct(area, geom.area)}))
    for scope in ('URBANO', 'RURAL'):
        for cat in CLASSES:
            for level in (99, 95, 90):
                rows = [(g, p) for g, p in hot_rows if p['AMBITO'] == scope and p['CATEGORIA'] == cat and p['NIVEL'] == level]
                total_area = sum(g.area for g, _ in rows)
                before = sum(p['AREA_CUB_M2'] for _, p in rows)
                after = sum(p['AREA_CUB_FUT_M2'] for _, p in rows)
                hotspot_stats.append({'AMBITO': scope, 'CATEGORIA': cat, 'NIVEL': level, 'TOTAL_CELDAS': len(rows),
                    'CON_COB_ANTES': sum(p['COB_200'] > 1e-6 for _, p in rows),
                    'CON_COB_DESPUES': sum(p['COB_FUTURA_PCT'] > 1e-6 for _, p in rows),
                    'COMPLETAS_DESPUES': sum(p['COB_FUTURA_PCT'] >= 99.9999 for _, p in rows),
                    'AREA_TOTAL_M2': total_area, 'AREA_CUB_ANTES_M2': before, 'AREA_CUB_DESPUES_M2': after,
                    'PCT_AREA_ANTES': pct(before, total_area), 'PCT_AREA_DESPUES': pct(after, total_area)})
    segments = []
    for key, axis in axes.items():
        for status, geom in [('CUBIERTO', axis.intersection(future)), ('SIN_COBERTURA', axis.difference(future))]:
            segments.extend((g, {'ID_SEGMENTO': f'{key}-{status}-{i+1:04d}', 'CORREDOR': key, 'ESTADO': status,
                'LONGITUD_M': g.length, 'RADIO_M': 200}) for i, g in enumerate(parts(geom, 1)))
    for row in rural_audit:
        pair = [p for _, p in proposal if p['PARROQUIA'] == row['PARROQUIA']]
        row['ID_PROPUESTAS'] = '|'.join(p['ID_PROPUESTA'] for p in pair)
        center = next(g for g, p in centers if p['PARROQUIA'] == row['PARROQUIA'])
        area = next(g for g, p in rural_areas if p['PARROQUIA'] == row['PARROQUIA'])
        row['COB_FUTURA_ENTORNO_200_PCT'] = pct(center.buffer(200, quad_segs=64).intersection(future).area, center.buffer(200, quad_segs=64).area)
        row['COB_FUTURA_PUGS_PCT'] = pct(area.intersection(future).area, area.area)
    warnings = [
        '103 inventariadas: solo99 con ubicacion aproximada;4 sin geometria no intervienen. Futuro153 teoricas/149 localizadas.',
        'Propuesta revisada, no autorizacion de instalacion. Cruces geometricos no certifican postes, energia, permiso, visibilidad o seguridad vial; requiere campo.',
        'Seleccion voraz exacta por beneficio marginal; no garantiza el optimo global de24 puntos. Prioridades secundarias solo en empate numerico de1e-6m; sin pesos arbitrarios.',
        'Los tramos comunes a redes distintas se informan en cada red: la suma objetivo es suma de tres indicadores, no longitud fisica unica.',
        'Intersecciones geometricas pueden ser pasos a distinto nivel; verificarlas en campo. Dos cartografias viales no se fusionan para inventar cruces entre fuentes.',
        'Cubijies: el ambito PUGS se recorta en una copia al limite cantonal disponible; discrepancias de limites requieren revision institucional.',
        'Poblacion local de cabeceras: No disponible; equipamientos son referencias GIS, no se certifica vigencia. Convivencia es criterio complementario, no peligrosidad.',
        'Gi* urbano100m/200m y rural1000m/2000m originales sin recalcular. Significancia nominal sin FDR; cobertura parcial de celda no equivale a celda completamente cubierta.',
        'No se usan brechas por manzana ni asignacion al vecino mas cercano;8986 puntos siguen sin asignar oficialmente. Incidentes conservan XY y peso1.',
        'Original50 contiene dos IDs repetidos San Juan/San Luis; se conserva ID_ORIGINAL y se usa ID_PROPUESTA unico por fila fuente.',
        'Radio200m potencial, no visibilidad real. No se impone separacion400m ni300-350m; continuidad se mide sobre ejes y solape solo desempata.']
    for r in rural_audit:
        if r['SEPARACION_PAR_M'] < 100:
            warnings.append(f"{r['PARROQUIA']}: par separado{r['SEPARACION_PAR_M']:.1f}m; localidad compacta, revisar utilidad operativa de ambos accesos.")
        if r['SEPARACION_PAR_M'] > 400:
            warnings.append(f"{r['PARROQUIA']}: par separado{r['SEPARACION_PAR_M']:.1f}m; los discos no se tocan. Se priorizaron accesos/evidencia distintos dentro de la cabecera, no continuidad entre el par.")
    tradeoff = sum(r['CAMBIO_VS_PREVIA_M'] for r in corridor_stats if r['CORREDOR'] in AXIS_KEYS)
    warnings.append(f'Frente a la propuesta inmediata previa: suma de tres redes mejora{tradeoff:.1f}m; Anillo y Macaji reducen su cobertura para aumentar mas Ciclovias. No es una mejora simultanea de todos los corredores.')
    metadata = {'generatedAt': datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'),
        'crsMetric': 'EPSG:32717', 'crsDisplay': 'EPSG:4326', 'radiusM': RADIUS,
        'inventory': len(cameras), 'located': int(cameras.geometry.notna().sum()), 'proposals': 50, 'policeProposals': 0,
        'groups': dict(Counter(p['GRUPO'] for _, p in proposal)), 'originalUniqueIds': len(set(r['ID_PROP'] for r in original)),
        'movedVsOriginal': sum(r['DISTANCIA_MOVIMIENTO_M'] > .01 for r in moves),
        'movedVsPrevious': sum(r['DISTANCIA_VS_PREVIA_M'] > .01 for r in moves),
        'objective': 'Suma de metros marginales exactos Anillo+Ciclovias+Macaji en cada iteracion;24sin cuota',
        'ruralMethod': 'Dos nodos de grado>=3 por localidad PUGS; centro sin cobertura primero; luego nuevos D/V, nuevos Conv, nuevos equipamientos, nueva area Gi* D/V rural, nueva area localidad; desempate menos solape/menor distancia al centro. Sin pesos ni simetria.',
        'order': '22 cabeceras, luego4 Abras, luego24 estructurales; cada grupo considera la union de existentes y los puntos ya elegidos.',
        'candidateCounts': {'rural': len(rural_candidates), 'abras': len(abras_pool), 'structural': len(structural_pool)},
        'roadsCRSOriginal': str(pyogrio.read_info(ROADS)['crs']), 'roadsCRSTarget': 'EPSG:32717',
        'roadsSource': str(ROADS), 'urbanRoadsSource': str(ROAD_GDB) + ':Vialidad_urbana', 'pugsSource': str(LIMITS),
        'ruralDistanceM': baseline['metadata']['ruralDistanceM'], 'urbanDistanceM': 200, 'urbanCellM': 100,
        'tieToleranceM': TIE_M, 'bufferQuadSegments': 64, 'sourceHashes': protected,
        'baselineDifferences': differences, 'warnings': warnings,
        'viewerModified': False, 'commit': False, 'push': False}
    package = OUT / 'PROPUESTA_50_OPTIMIZADA.gpkg'
    layers = {'PROPUESTA_50_OPTIMIZADA': proposal,
        'PROPUESTA_50_ORIGINAL': [(Point(float(r['X']), float(r['Y'])), {**r, 'FILA_ORIGINAL': i+1}) for i, r in enumerate(original)],
        'PROPUESTA_50_PREVIA': [(Point(float(r['X']), float(r['Y'])), {**r, 'FILA_ORIGINAL': i+1}) for i, r in enumerate(previous)],
        'CAMARAS_EXISTENTES_103': records(cameras),
        'COBERTURA_ACTUAL_200M': [(current, {'RADIO_M': 200, 'CAMARAS_UBICADAS': 99})],
        'BUFFERS_PROPUESTAS_200M': [(g.buffer(200, quad_segs=64), {'ID_PROPUESTA': p['ID_PROPUESTA'], 'GRUPO': p['GRUPO'], 'RADIO_M': 200}) for g, p in proposal],
        'COBERTURA_OPTIMIZADA_200M': [(future, {'RADIO_M': 200, 'CAMARAS_UBICADAS': 149})],
        'CORREDORES_CUBIERTOS': [(g, p) for g, p in segments if p['ESTADO'] == 'CUBIERTO'],
        'SEGMENTOS_SIN_COBERTURA': [(g, p) for g, p in segments if p['ESTADO'] == 'SIN_COBERTURA'],
        'CABECERAS_RURALES': [(g, next(r for r in rural_audit if r['PARROQUIA'] == p['PARROQUIA'])) for g, p in centers],
        'AMBITOS_CABECERAS_PUGS': rural_areas, 'PLATAFORMAS': platform_rows,
        'LIMITE_CANTONAL': [(canton, {'FUENTE': 'Diagnostico actual103'})],
        'CANDIDATOS_RURALES': rural_candidates,
        'CANDIDATOS_LAS_ABRAS': candidate_rows(abras_pool, {'QUEBRADA_LAS_ABRAS': abras_axis}, current, evidence, abras),
        'CANDIDATOS_ESTRUCTURALES': candidate_rows(structural_pool, {k: axes[k] for k in AXIS_KEYS}, current, evidence, structural),
        'INCIDENTES_COMPARACION': incident_rows,
        'EQUIPAMIENTOS_REFERENCIA': equipment}
    for scope in ('URBANO', 'RURAL'):
        for cat in CLASSES:
            layers[f'HOTSPOT_{scope}_{cat}'] = [(g, p) for g, p in hot_rows if p['AMBITO'] == scope and p['CATEGORIA'] == cat]
    layer_info = [save_layer(name, rows, package) for name, rows in layers.items()]
    for name, rows in [('PROPUESTA_50_OPTIMIZADA', [p for _, p in proposal]), ('CAMARAS_MOVIDAS', moves),
                       ('CORREDORES_ANTES_DESPUES', corridor_stats), ('INCIDENTES_ANTES_DESPUES', incident_stats),
                       ('HOTSPOTS_ANTES_DESPUES', hotspot_stats), ('CABECERAS_DOS_CAMARAS', rural_audit),
                       ('TRAZA_SELECCION_ITERATIVA', abras_trace + structural_trace),
                       ('CANDIDATOS_ESTRUCTURALES', [p for _, p in layers['CANDIDATOS_ESTRUCTURALES']]),
                       ('SEGMENTOS_SIN_COBERTURA', [p for _, p in layers['SEGMENTOS_SIN_COBERTURA']])]:
        save_csv(name + '.csv', rows)
    assert all(sha(Path(p)) == digest for p, digest in protected.items()), 'Una fuente protegida fue alterada'
    metadata['protectedFilesUnchanged'] = True
    data = {'metadata': metadata, 'corridors': corridor_stats, 'incidents': incident_stats,
        'hotspots': hotspot_stats, 'cabeceras': rural_audit, 'movements': moves, 'proposals': [p for _, p in proposal],
        'selectionTrace': abras_trace + structural_trace, 'layers': layer_info}
    save_json('RESULTADOS.json', data)
    write_report(data)
    print(json.dumps({'metadata': {k: v for k, v in metadata.items() if k not in ('sourceHashes', 'warnings')}, 'corridors': corridor_stats}, indent=2), flush=True)


def write_report(data):
    def table(fields, rows):
        def clean(v):
            if v is None:
                return 'No disponible'
            if isinstance(v, float):
                return f'{v:.3f}'
            return str(v).replace('|', '/').replace('\n', ' ')
        return '\n'.join(['| ' + ' | '.join(fields) + ' |', '| ' + ' | '.join(['---']*len(fields)) + ' |'] +
                         ['| ' + ' | '.join(clean(r.get(k)) for k in fields) + ' |' for r in rows])
    m = data['metadata']
    lines = ['# Revision de50 camaras municipales', '**PROPUESTA_REVISADA. Sin commit, push ni cambio del visor definitivo. No se generan30 camaras de Policia.**',
        '## Control', f"103 inventariadas/99geometrias aproximadas/4sin geometria.50propuestas: {m['groups']}. Todos los puntos nuevos dentro del canton;50IDs y50XY unicos;sin0,0/geometrias invalidas.",
        f"Movidas frente a original: {m['movedVsOriginal']};frente a version inmediata previa: {m['movedVsPrevious']}. Original y previa conservadas completas con filas/IDs fuente.",
        '## Metodologia y prioridades', m['objective'], m['ruralMethod'], m['order'],
        'Discos200m,64segmentos/cuadrante enEPSG:32717; disolucion antes de cruces. Candidatos estructurales: nodos viales de grado>=3 a<=200m de ejes, cruces exactos eje-via y entre corredores, dentro del canton. Las Abras: cruces viales exactos sobre eje intr cantonal. Sin intervalos artificiales ni centroides.',
        'La prioridad Anillo>Ciclovias>Macaji desempata beneficios marginales numericamente iguales(1e-6m); despues numero de corredores, area nueva de Hot Spots, incidentes nuevos, continuidad300-350m, menor solape y grado vial. No hay cuotas ni penalizacion ponderada; cobertura redundante no aporta metros adicionales. No se sacrifica longitud para perseguir hotspots.',
        f"Candidatos={m['candidateCounts']}. Equipamientos consultados: {', '.join(EQUIPMENT_LAYERS)} de cartografia base GAD. No se infiere poblacion local a partir del numero de puntos.",
        f"CRS vial cantonal original={m['roadsCRSOriginal']}, transformado aEPSG:32717; vialidad urbana y PUGS con CRS propio transformado. No se sobrescribe ni reasigna CRS de fuentes. Gi* urbano100/200m;rural distancia{m['ruralDistanceM']}m original sin recalcular.",
        '## Cobertura de corredores', table(list(data['corridors'][0]), data['corridors']),
        'ACTUAL es el diagnostico103/99; ORIGINAL esCSV externo original; PREVIA escorreccion previa autorizada; OPTIMIZADA esrevision actual. Incremento en metros y puntos porcentuales. Las redes se evalúan por union lineal de cada fuente, no por conteo de camaras proximas.',
        'Diferencias respecto al diagnostico, solo precision de overlay:<0.001m. VerRESULTADOS.json/baselineDifferences.',
        '## Incidentes directos', table(list(data['incidents'][0]), data['incidents']),
        'BASE_COMPLETA conserva11150registrosD/V/C, incluidos8externos al canton. CANTONAL11142;URBANO9915 en18Plataformas. Peso1, sin mover incidentes ni asignarlos a manzanas. Tipologias institucionales/revision excluidas.',
        '## Hot Spots:99/95/90separados', table(list(data['hotspots'][0]), data['hotspots']),
        'Con cobertura significa interseccion positiva>1e-8de la fraccion de area, no cobertura completa. Se muestran tambien celdas completas y area efectivamente cubierta; no sumar categorias superpuestas como sectores diferentes.',
        '## Dos camaras por cabecera', table(list(data['cabeceras'][0]), data['cabeceras']),
        'Cobertura de centro, entorno200m y poligono urbanoPUGS son medidas diferentes; ninguna significa cubrir toda la parroquia. Las cifras de entorno usan el mismo punto/radio del diagnostico.',
        '## Justificacion de las50', table(['ID_PROPUESTA','GRUPO','PARROQUIA','X','Y','CORREDOR','HOTSPOT_RELACIONADO','INCIDENTES_ENTORNO','COBERTURA_PREVIA','JUSTIFICACION'], data['proposals']),
        '## Movimientos', table(['ID_PROPUESTA','ID_ORIGINAL','GRUPO','PARROQUIA','X_ORIGINAL','Y_ORIGINAL','X_PREVIA','Y_PREVIA','X_NUEVA','Y_NUEVA','DISTANCIA_MOVIMIENTO_M','DISTANCIA_VS_PREVIA_M','MOTIVO'], data['movements']),
        '## Vacio restante', 'SEGMENTOS_SIN_COBERTURA.geojson/gpkg/CSV conserva todos los tramos residuales. No se fuerza100% ni se cubren con30puntos de Policia.',
        '## Advertencias', *['- ' + w for w in m['warnings']],
        '## Fuentes y capas', table(['name','records','crs','fields'], [{**v,'fields': ', '.join(v['fields'])} for v in data['layers']]),
        'RESULTADOS.json contiene rutas, hashesSHA256 de fuentes y metadatos. Todos los archivos protegidos quedaron intactos. CSV utiliza UTF-8BOM, GeoPackageEPSG:32717, GeoJSONEPSG:4326. Los campos NUEVO_* de candidatos comparan con ACTUAL; la traza y las50usan el beneficio recalculado al momento de seleccion.',
        '**Detenido para revision tecnica.**']
    (OUT / 'INFORME_OPTIMIZACION.md').write_text('\n\n'.join(lines), encoding='utf-8')
    (OUT / 'README.md').write_text('# Propuesta municipal50:revision20261003\n\nAbrir index.html mediante servidorHTTP para revisar mapa interactivo. GeoPackage:24capas EPSG:32717; GeoJSON solo visualEPSG:4326.\n\nINFORME_OPTIMIZACION.md incluye metodologia, resultados,50justificaciones, movimientos ylimitaciones. CSV de candidatos y traza permiten auditar cada seleccion. RESULTADOS.json incluye hashes/campos/conteos.\n\nNo se modifica visor definitivo. Sin commit/push. No se generan30dePolicia. Los originales se mantienen.\n', encoding='utf-8')


if __name__ == '__main__':
    main()
