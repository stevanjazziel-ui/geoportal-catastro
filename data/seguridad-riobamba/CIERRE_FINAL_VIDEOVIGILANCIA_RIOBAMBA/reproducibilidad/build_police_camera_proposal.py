"""Police proposal complements the frozen municipal50; no Gi* recalculation or production edits."""
import csv
import json
import math
import shutil
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pyogrio
from shapely import STRtree, force_2d
from shapely.geometry import Point, shape, mapping
from shapely.ops import transform, unary_union

from build_current_camera_diagnosis import ROOT, PROJECT, UNPROJECT, parts, pct, sha, CLASSES
from build_remaining_camera_coverage import read_js, load
from optimize_municipal_cameras_50 import read_layer, records, road_nodes, unique_candidates, ROAD_GDB, ROADS

OUT = ROOT / 'data/seguridad-riobamba/propuesta-policia-30-20261003'
MUNICIPAL = ROOT / 'data/seguridad-riobamba/optimizacion-municipal-50-20261003'
PACKAGE = MUNICIPAL / 'PROPUESTA_50_OPTIMIZADA.gpkg'
RADIO_M = 200
AREA_EPS = .01
FRACTION_EPS = 1e-8


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf-8')


def write_csv(name, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def geojson(rows):
    return {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'properties': p,
        'geometry': mapping(transform(UNPROJECT, g)) if g is not None else None} for g, p in rows]}


def export_layer(name, rows, package, visual=True):
    frame = gpd.GeoDataFrame([p for _, p in rows], geometry=[g for g, _ in rows], crs=32717)
    pyogrio.write_dataframe(frame, package, layer=name)
    if visual:
        write_json(name + '.geojson', geojson(rows))
    return {'name': name, 'records': len(rows), 'crs': 'EPSG:32717', 'fields': list(frame.columns[:-1])}


def coverage_class(fraction):
    if fraction <= FRACTION_EPS:
        return 'SIN COBERTURA'
    if fraction >= 1-FRACTION_EPS:
        return 'CUBIERTO'
    return 'PARCIALMENTE CUBIERTO'


def original_statistics():
    urban = read_js('riobamba-hotspot-urbano-200m-data.js')
    canton = read_js('riobamba-cantonal-data.js')
    correction = read_js('riobamba-conflictividad-data.js')
    rows = {}
    for scope in ('URBANO', 'RURAL'):
        grid = urban['grid'] if scope == 'URBANO' else canton['ruralGrid']
        for category in CLASSES:
            results = urban['byClass'][category]['results'] if scope == 'URBANO' else correction['gi'][scope][category]['results']
            assert len(grid['cells']) == len(results)
            rows[(scope, category)] = [(transform(PROJECT, shape(cell['geometry'])),
                {'CELL_ID': cell['cellId'], 'AMBITO': scope, 'CATEGORIA': category,
                 'PLATAFORMA': cell.get('platform'), 'PARROQUIA': cell.get('PARROQUIA'),
                 'DISTANCE_M': 200 if scope == 'URBANO' else grid['neighborDistance'],
                 'CELL_SIZE_M': grid['cellSize'], **result,
                 'NIVEL': int(result['GI_CLASS'].split()[1].strip('%')) if result['GI_CLASS'].startswith(('HOTSPOT', 'COLDSPOT')) else 0})
                for cell, result in zip(grid['cells'], results)]
    return rows


def dv_coincidences(statistics):
    rows = []
    for scope in ('URBANO', 'RURAL'):
        violence = {p['CELL_ID']: (g, p) for g, p in statistics[(scope, 'VIOLENCIA')] if p['GI_CLASS'].startswith('HOTSPOT')}
        for geom, p in statistics[(scope, 'DELINCUENCIA')]:
            if not p['GI_CLASS'].startswith('HOTSPOT') or p['CELL_ID'] not in violence:
                continue
            v_geom, v = violence[p['CELL_ID']]
            overlap = geom.intersection(v_geom)
            if overlap.area > AREA_EPS:
                rows.append((overlap, {'ID_DV': scope + '-' + p['CELL_ID'], 'CELL_ID': p['CELL_ID'], 'AMBITO': scope,
                    'NIVEL_DEL': p['NIVEL'], 'NIVEL_VIOL': v['NIVEL'],
                    'NIVEL_MIN_DV': min(p['NIVEL'], v['NIVEL']),
                    'GI_Z_DEL': p['GI_ZSCORE'], 'GI_P_DEL': p['GI_PVALUE'],
                    'GI_Z_VIOL': v['GI_ZSCORE'], 'GI_P_VIOL': v['GI_PVALUE'],
                    'METODO': 'Superposicion geometrica; no nueva prueba conjunta de significancia'}))
    return rows


class Context:
    def __init__(self, events, hot, dv, baseline, existing, municipal, infrastructure, blocks, urban, axes):
        self.events, self.hot, self.dv = events, hot, dv
        self.baseline, self.existing, self.municipal = baseline, existing, municipal
        self.infrastructure, self.blocks, self.urban, self.axes = infrastructure, blocks, urban, axes
        self.event_tree = STRtree([g for g, _ in events])
        self.hot_tree = STRtree([g for g, _ in hot])
        self.dv_tree = STRtree([g for g, _ in dv])
        self.block_tree = STRtree([g for g, _ in blocks])

    def candidate(self, c):
        disk = c['point'].buffer(RADIO_M, quad_segs=64)
        c['disk'] = disk
        c['events'] = [int(i) for i in self.event_tree.query(disk, predicate='intersects')
                       if self.events[int(i)][1]['AMBITO'] != 'EXTERNO_CANTON']
        c['hot'] = [(int(i), self.hot[int(i)][0].intersection(disk)) for i in self.hot_tree.query(disk, predicate='intersects')
                    if self.hot[int(i)][0].intersection(disk).area > AREA_EPS]
        c['dv'] = [(int(i), self.dv[int(i)][0].intersection(disk)) for i in self.dv_tree.query(disk, predicate='intersects')
                   if self.dv[int(i)][0].intersection(disk).area > AREA_EPS]
        c['counts'] = Counter(self.events[i][1]['CATEGORIA'] for i in c['events'])
        c['scope'] = 'URBANO' if any(self.hot[i][1]['AMBITO'] == 'URBANO' and self.hot[i][1]['CATEGORIA'] in CLASSES[:2] for i, _ in c['hot']) else 'RURAL'
        c['overlapB'] = pct(disk.intersection(self.baseline).area, disk.area)
        c['distanceExisting'] = min(c['point'].distance(p) for p in self.existing)
        c['distanceMunicipal'] = min(c['point'].distance(p) for p in self.municipal)
        return c

    def new_counts(self, c, covered_events):
        return Counter(self.events[i][1]['CATEGORIA'] for i in c['events'] if i not in covered_events)

    def marginal(self, c, coverage, covered_events, uncovered_hot, uncovered_dv, hot_fraction):
        counts = self.new_counts(c, covered_events)
        if counts['DELINCUENCIA'] + counts['VIOLENCIA'] == 0:
            return None
        scope = c['scope']
        h = [(i, c['disk'].intersection(uncovered_hot[i]).area) for i, _ in c['hot']
             if self.hot[i][1]['AMBITO'] == scope and self.hot[i][1]['CATEGORIA'] in CLASSES[:2]]
        d = [(i, c['disk'].intersection(uncovered_dv[i]).area) for i, _ in c['dv'] if self.dv[i][1]['AMBITO'] == scope]
        d = [(i, a) for i, a in d if a > AREA_EPS]
        h = [(i, a) for i, a in h if a > AREA_EPS]
        if d:
            priority, category = 1, 'DELINCUENCIA + VIOLENCIA'
            level = max(self.dv[i][1]['NIVEL_MIN_DV'] for i, _ in d)
            area = sum(a for i, a in d if self.dv[i][1]['NIVEL_MIN_DV'] == level)
            zero = any(coverage_class(self.dv[i][0].intersection(coverage).area/self.dv[i][0].area) == 'SIN COBERTURA' for i, _ in d)
        else:
            crime = [(i, a) for i, a in h if self.hot[i][1]['CATEGORIA'] == 'DELINCUENCIA']
            violence = [(i, a) for i, a in h if self.hot[i][1]['CATEGORIA'] == 'VIOLENCIA']
            if not crime and not violence:
                return None
            relevant = crime if crime else violence
            priority, category = (2, 'DELINCUENCIA') if crime else (3, 'VIOLENCIA')
            level = max(self.hot[i][1]['NIVEL'] for i, _ in relevant)
            area = sum(a for i, a in relevant if self.hot[i][1]['NIVEL'] == level)
            zero = any(coverage_class(hot_fraction[i]) == 'SIN COBERTURA' for i, _ in relevant)
        overlap = pct(c['disk'].intersection(coverage).area, c['disk'].area)
        gain_d = sum(a for i, a in h if self.hot[i][1]['CATEGORIA'] == 'DELINCUENCIA')
        gain_v = sum(a for i, a in h if self.hot[i][1]['CATEGORIA'] == 'VIOLENCIA')
        # Explicit lexicographic rules, not an arbitrary weighted index or a corridor objective.
        ranking = (int(scope == 'URBANO'), -priority, int(zero), level,
                   counts['DELINCUENCIA']+counts['VIOLENCIA'], area, gain_d+gain_v,
                   -overlap, counts['CONVIVENCIA'], c['degree'])
        return {'ranking': ranking, 'priority': priority, 'category': category, 'level': level,
                'uncoveredCell': zero, 'counts': counts, 'newHotD': gain_d, 'newHotV': gain_v,
                'newDV': sum(a for _, a in d), 'overlap': overlap}

    def population(self, disk):
        total, found, missing = 0., 0, 0
        for i in self.block_tree.query(disk, predicate='intersects'):
            geom, p = self.blocks[int(i)]
            area = geom.intersection(disk).intersection(self.urban).area
            if area <= AREA_EPS:
                continue
            value = p['POBLACION']
            if value is None:
                missing += 1
            else:
                total += value * area / geom.area
                found += 1
        return (total if found else None), found, missing

    def description(self, c):
        hot_props = [self.hot[i][1] for i, _ in c['hot']]
        fields = {}
        for category, label in zip(CLASSES, ('DEL', 'VIOL', 'CONV')):
            selected = [p for p in hot_props if p['CATEGORIA'] == category and p['AMBITO'] == c['scope']]
            fields['HOTSPOT_' + label] = '|'.join(p['CELL_ID'] for p in sorted(selected, key=lambda p:p['CELL_ID'])) or None
            fields['NIVEL_' + label] = max([p['NIVEL'] for p in selected] or [0])
        upcs = [(g, p) for g, p in self.infrastructure if p['TIPO'] == 'UPC']
        nearest, near_props = min(upcs, key=lambda row:c['point'].distance(row[0]))
        infra, infra_props = min(self.infrastructure, key=lambda row:c['point'].distance(row[0]))
        pop, valid, missing = self.population(c['disk'])
        corridors = [key for key, axis in self.axes.items() if axis.intersection(c['disk']).length > 1e-6]
        return {**fields, 'AMBITO_HOTSPOT': c['scope'], 'COINCIDENCIA_DV': any(self.dv[i][1]['AMBITO'] == c['scope'] for i, _ in c['dv']),
                'DELINCUENCIA_200M': c['counts']['DELINCUENCIA'], 'VIOLENCIA_200M': c['counts']['VIOLENCIA'],
                'CONVIVENCIA_200M': c['counts']['CONVIVENCIA'], 'N_TOTAL': sum(c['counts'].values()),
                'COBERTURA_PREVIA': c['overlapB'], 'POBLACION_ASOCIADA': pop,
                'MANZANAS_POB_VALIDAS': valid, 'MANZANAS_POB_FALTANTES': missing,
                'POBLACION_METODO': 'Estimacion areal CPV2022 dentro del radio200m y18Plataformas; no poblacion rural completa',
                'UPC_CERCANA': near_props['ID_INFRA'], 'NOMBRE_UPC': near_props['NOMBRE'], 'DIST_UPC_M': c['point'].distance(nearest),
                'INFRA_CERCANA': infra_props['ID_INFRA'], 'DIST_INFRA_M': c['point'].distance(infra),
                'DIST_EXISTENTE': c['distanceExisting'], 'DIST_MUNICIPAL': c['distanceMunicipal'],
                'INTERSECCION_O_NODO': '|'.join(sorted(c['origins'])), 'GRADO_NODO': c['degree'],
                'CORREDOR_COINCIDENTE': '|'.join(corridors) or None,
                'CORREDOR_METODO': 'Eje intersecta buffer200m; no implica punto sobre eje ni criterio de seleccion'}


def build_candidates(context, canton):
    urban_roads = read_layer(ROAD_GDB, 'Vialidad_urbana')
    canton_roads = read_layer(ROADS)
    urban_hot = unary_union([g for g, p in context.hot if p['AMBITO'] == 'URBANO' and p['CATEGORIA'] in CLASSES[:2]])
    rural_hot = unary_union([g for g, p in context.hot if p['AMBITO'] == 'RURAL' and p['CATEGORIA'] in CLASSES[:2]])
    rows = [(p, 'INTERSECCION_VIAL_URBANA', d) for p, d in road_nodes(unary_union(list(urban_roads.geometry)))
            if d >= 3 and urban_hot.distance(p) <= RADIO_M]
    rows += [(p, 'INTERSECCION_VIAL_CANTONAL', d) for p, d in road_nodes(unary_union(list(canton_roads.geometry)))
             if d >= 3 and rural_hot.distance(p) <= RADIO_M and not context.urban.covers(p)]
    candidates = []
    for raw in unique_candidates(rows, canton):
        c = context.candidate(raw)
        if not any(context.hot[i][1]['CATEGORIA'] in CLASSES[:2] for i, _ in c['hot']):
            continue
        if c['distanceExisting'] <= 1e-5 or c['distanceMunicipal'] <= 1e-5:
            continue
        # A rural candidate needs direct D/V observations as well as a rural significant cell.
        if c['scope'] == 'RURAL' and c['counts']['DELINCUENCIA']+c['counts']['VIOLENCIA'] == 0:
            continue
        c['id'] = f'CAND-POL-{len(candidates)+1:05d}'
        candidates.append(c)
    return candidates


def select30(context, candidates):
    coverage, selected, trace, used = context.baseline, [], [], set()
    covered_events = {i for i, (g, _) in enumerate(context.events) if coverage.covers(g)}
    for step in range(1, 31):
        hot_fraction = [g.intersection(coverage).area/g.area for g, _ in context.hot]
        uncovered_hot = [g.difference(coverage) for g, _ in context.hot]
        uncovered_dv = [g.difference(coverage) for g, _ in context.dv]
        best = None
        for i, c in enumerate(candidates):
            if i in used:
                continue
            evidence = context.marginal(c, coverage, covered_events, uncovered_hot, uncovered_dv, hot_fraction)
            if evidence is not None and (best is None or evidence['ranking'] > best[0]['ranking']):
                best = evidence, i, c
        assert best is not None, f'No hay30 candidatos con nueva evidencia D/V; detener en{step}'
        evidence, i, c = best
        distance_police = min([c['point'].distance(s['point']) for s in selected] or [math.inf])
        trace.append({'ID_POLICIA': f'POL-{step:02d}', 'ITERACION': step, 'ID_CANDIDATO': c['id'],
            'PRIORIDAD': evidence['priority'], 'CATEGORIA_PRINCIPAL': evidence['category'], 'AMBITO_HOTSPOT': c['scope'],
            'HOTSPOT_SIN_COBERTURA': evidence['uncoveredCell'], 'NIVEL_PRIORIDAD': evidence['level'],
            'NUEVOS_EVENTOS_DELINCUENCIA_CUBIERTOS': evidence['counts']['DELINCUENCIA'],
            'NUEVOS_EVENTOS_VIOLENCIA_CUBIERTOS': evidence['counts']['VIOLENCIA'],
            'NUEVOS_EVENTOS_CONVIVENCIA_CUBIERTOS': evidence['counts']['CONVIVENCIA'],
            'BENEFICIO_MARGINAL': evidence['counts']['DELINCUENCIA']+evidence['counts']['VIOLENCIA'],
            'HOTSPOT_DEL_NUEVO_M2': evidence['newHotD'], 'HOTSPOT_VIOL_NUEVO_M2': evidence['newHotV'],
            'COINCIDENCIA_DV_NUEVA_M2': evidence['newDV'], 'SOLAPE_UNION_PREVIA_PCT': evidence['overlap'],
            'DIST_POLICIA_AL_SELECCIONAR': distance_police if math.isfinite(distance_police) else None,
            'CLAVE_ORDEN': json.dumps(evidence['ranking'])})
        used.add(i)
        c['selection'] = trace[-1]
        selected.append(c)
        covered_events.update(c['events'])
        coverage = coverage.union(c['disk'])
        print(f"POL-{step:02d}: P{evidence['priority']} {c['scope']} {evidence['level']}%; nuevos D/V={trace[-1]['BENEFICIO_MARGINAL']}", flush=True)
    return selected, coverage, trace


def scenario_evaluation(context, statistics, dv, masks):
    incident_stats, hot_stats, corridor_stats = [], [], []
    for scenario, coverage in masks.items():
        for scope in ('BASE_COMPLETA','CANTONAL','URBANO','RESTO_CANTON','EXTERNO_CANTON'):
            for category in CLASSES:
                points = [g for g, p in context.events if p['CATEGORIA'] == category and (scope == 'BASE_COMPLETA' or
                    (scope == 'CANTONAL' and p['AMBITO'] != 'EXTERNO_CANTON') or p['AMBITO'] == scope)]
                covered = sum(coverage.covers(g) for g in points)
                incident_stats.append({'ESCENARIO': scenario, 'AMBITO': scope, 'CATEGORIA': category,
                    'TOTAL': len(points), 'CUBIERTOS': covered, 'NO_CUBIERTOS': len(points)-covered, 'PCT_CUBIERTO': pct(covered, len(points))})
        for (scope, category), rows in statistics.items():
            for level in (99,95,90):
                cells = [g for g, p in rows if p['GI_CLASS'] == f'HOTSPOT {level}%']
                fractions = [g.intersection(coverage).area/g.area for g in cells]
                states = Counter(coverage_class(f) for f in fractions)
                area = sum(g.area for g in cells)
                covered_area = sum(g.area*f for g,f in zip(cells,fractions))
                hot_stats.append({'ESCENARIO': scenario, 'AMBITO': scope, 'CATEGORIA': category, 'NIVEL': level,
                    'TOTAL': len(cells), 'CUBIERTO': states['CUBIERTO'], 'PARCIAL': states['PARCIALMENTE CUBIERTO'],
                    'SIN_COBERTURA': states['SIN COBERTURA'], 'CON_ALGUNA_COBERTURA': len(cells)-states['SIN COBERTURA'],
                    'AREA_TOTAL_M2': area, 'AREA_CUBIERTA_M2': covered_area, 'PCT_AREA_CUBIERTA': pct(covered_area, area)})
        for key, axis in context.axes.items():
            covered = axis.intersection(coverage).length
            corridor_stats.append({'ESCENARIO': scenario, 'CORREDOR': key, 'TOTAL_M': axis.length,
                'CUBIERTO_M': covered, 'NO_CUBIERTO_M': axis.length-covered, 'PCT_CUBIERTO': pct(covered, axis.length)})
    updated = {}
    for key, rows in statistics.items():
        updated[key] = []
        for geom, p in rows:
            props = dict(p)
            for scenario, coverage in masks.items():
                fraction = geom.intersection(coverage).area/geom.area
                props['COB_' + scenario + '_PCT'] = 100*fraction
                props['ESTADO_' + scenario] = coverage_class(fraction)
            updated[key].append((geom, props))
    dv_rows, dv_remaining = [], []
    for geom, p in dv:
        props = dict(p)
        for scenario, coverage in masks.items():
            fraction = geom.intersection(coverage).area/geom.area
            props['COB_' + scenario + '_PCT'] = 100*fraction
            props['ESTADO_' + scenario] = coverage_class(fraction)
        dv_rows.append((geom, props))
        dv_remaining.extend((g, props) for g in parts(geom.difference(masks['C']), 2) if g.area > AREA_EPS)
    return incident_stats, hot_stats, corridor_stats, updated, dv_rows, dv_remaining


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    municipal_data = json.loads((MUNICIPAL / 'RESULTADOS.json').read_text(encoding='utf-8'))
    protected = {str(p):sha(p) for p in MUNICIPAL.rglob('*') if p.is_file() and p.suffix.lower() not in ('.log','.lock','.lck')}
    protected.update(municipal_data['metadata']['sourceHashes'])
    for name in ('policia-06d01-data.js','riobamba-censo-data/riobamba_manzanas.geojson','riobamba-censo-data/riobamba_manzanas_stats.json'):
        protected[str(ROOT / name)] = sha(ROOT / name)
    assert all(sha(Path(path)) == digest for path,digest in protected.items()), 'Fuente congelada cambio antes de comenzar'
    cameras = records(read_layer(PACKAGE, 'CAMARAS_EXISTENTES_103'))
    municipal = records(read_layer(PACKAGE, 'PROPUESTA_50_OPTIMIZADA'))
    current = read_layer(PACKAGE, 'COBERTURA_ACTUAL_200M').geometry.iloc[0]
    baseline = read_layer(PACKAGE, 'COBERTURA_OPTIMIZADA_200M').geometry.iloc[0]
    canton = read_layer(PACKAGE, 'LIMITE_CANTONAL').geometry.iloc[0]
    platforms = records(read_layer(PACKAGE, 'PLATAFORMAS'))
    urban = unary_union([g for g,_ in platforms])
    events = records(read_layer(PACKAGE, 'INCIDENTES_COMPARACION'))
    lines = records(read_layer(PACKAGE, 'CORREDORES_CUBIERTOS')) + records(read_layer(PACKAGE, 'SEGMENTOS_SIN_COBERTURA'))
    axes = {key:unary_union([g for g,p in lines if p['CORREDOR']==key]) for key in dict.fromkeys(p['CORREDOR'] for _,p in lines)}
    stats = original_statistics()
    hot = [(g,p) for rows in stats.values() for g,p in rows if p['GI_CLASS'].startswith('HOTSPOT')]
    dv = dv_coincidences(stats)
    infrastructure = [(transform(PROJECT,shape(f['geometry'])), {'ID_INFRA':f['properties']['code'],
        'TIPO':f['properties']['type'], 'NOMBRE':f['properties']['name'], 'ESTADO':f['properties']['status']})
        for f in read_js('policia-06d01-data.js')['infrastructure']['features']]
    census = load('riobamba-censo-data/riobamba_manzanas_stats.json')['byMan']
    blocks = []
    for f in load('riobamba-censo-data/riobamba_manzanas.geojson')['features']:
        g = transform(PROJECT,shape(f['geometry']))
        value = census.get(f['properties']['man'],{}).get('population_total')
        valid = value is not None and math.isfinite(value) and value >= 0
        blocks.append((g, {'POBLACION':value if valid else None}))
    context = Context(events,hot,dv,baseline,[g for g,_ in cameras if g is not None],[g for g,_ in municipal],infrastructure,blocks,urban,axes)
    assert len(cameras)==103 and len(context.existing)==99 and len(municipal)==50
    assert baseline.symmetric_difference(unary_union([current]+[g.buffer(200,quad_segs=64) for g,_ in municipal])).area < 1e-5
    candidates = build_candidates(context,canton)
    print(f'Candidatos por ambito: {Counter(c["scope"] for c in candidates)}', flush=True)
    selected,future,trace = select30(context,candidates)
    chosen = {c['id'] for c in selected}
    proposal = []
    for c in selected:
        selection = c['selection']
        point = c['point']
        lon,lat = UNPROJECT(point.x,point.y)
        distance_police = min(point.distance(s['point']) for s in selected if s is not c)
        description = context.description(c)
        n_del,n_viol = selection['NUEVOS_EVENTOS_DELINCUENCIA_CUBIERTOS'],selection['NUEVOS_EVENTOS_VIOLENCIA_CUBIERTOS']
        reason = (f"{selection['ID_POLICIA']}: nodo vial real {c['id']}, ambito Gi* {c['scope']}; prioridad{selection['PRIORIDAD']} "
                  f"por {selection['CATEGORIA_PRINCIPAL']} nominal{selection['NIVEL_PRIORIDAD']}%. "
                  f"Interseca celdas {description['HOTSPOT_DEL'] or 'sin Hot Spot D'} / {description['HOTSPOT_VIOL'] or 'sin Hot Spot V'}. "
                  f"Nueva cobertura en esta iteracion: {n_del} Delincuencia y{n_viol} Violencia; "
                  f"{selection['HOTSPOT_DEL_NUEVO_M2']:.1f}m2 de Hot SpotD y{selection['HOTSPOT_VIOL_NUEVO_M2']:.1f}m2 de Hot SpotV. "
                  f"Solape previo acumulado{selection['SOLAPE_UNION_PREVIA_PCT']:.1f}%; UPC{description['UPC_CERCANA']} a{description['DIST_UPC_M']:.1f}m. "
                  "Pendiente validacion operativa de Policia; no se certifica visibilidad o respuesta.")
        proposal.append((point, {'ID_POLICIA':selection['ID_POLICIA'],'X':point.x,'Y':point.y,'LONGITUD':lon,'LATITUD':lat,
            'PRIORIDAD':selection['PRIORIDAD'],'CATEGORIA_PRINCIPAL':selection['CATEGORIA_PRINCIPAL'],
            'CRITERIOS_SECUNDARIOS':'Convivencia observada; geometria del nodo; poblacion estimada/UPC/corredores solo descriptivos',
            **description, 'DIST_POLICIA':distance_police, **{k:v for k,v in selection.items() if k!='CLAVE_ORDEN'},
            'BENEFICIO_UNIDAD':'Eventos nuevos Delincuencia+Violencia, peso1 por registro; no score ponderado',
            'JUSTIFICACION':reason,'ESTADO':'PROPUESTA_PARA_VALIDACION_POLICIA'}))
    assert len(proposal)==30 and len(set(p['ID_POLICIA'] for _,p in proposal))==30
    assert len({g.wkb for g,_ in proposal})==30 and all(canton.covers(g) and g.is_valid and (g.x,g.y)!=(0,0) for g,_ in proposal)
    masks={'A':current,'B':baseline,'C':future}
    inc_stats,hot_stats,corridor_stats,updated,dv_rows,dv_remaining = scenario_evaluation(context,stats,dv,masks)
    for old in municipal_data['corridors']:
        row=next(r for r in corridor_stats if r['ESCENARIO']=='B' and r['CORREDOR']==old['CORREDOR'])
        assert abs(row['CUBIERTO_M']-old['CUBIERTO_OPTIMIZADA_M']) < .001
    candidate_rows=[]
    initial_covered={i for i,(g,_) in enumerate(events) if baseline.covers(g)}
    for c in candidates:
        counts=context.new_counts(c,initial_covered)
        candidate_rows.append((c['point'], {'ID_CANDIDATO':c['id'],'X':c['point'].x,'Y':c['point'].y,
            'SELECCIONADO':c['id'] in chosen,**context.description(c),
            **{'NUEVOS_EVENTOS_'+k+'_CUBIERTOS':counts[k] for k in CLASSES},
            'BENEFICIO_MARGINAL_INICIAL':counts['DELINCUENCIA']+counts['VIOLENCIA']}))
    remaining=[]
    for scope in ('URBANO','RURAL'):
        for category in CLASSES:
            for geom,p in updated[(scope,category)]:
                if p['GI_CLASS'].startswith('HOTSPOT'):
                    remaining.extend((g,p) for g in parts(geom.difference(future),2) if g.area > AREA_EPS)
    system80=[(g,{'ID_NUEVA':p['ID_PROPUESTA'],'INSTITUCION_PROPUESTA':'MUNICIPAL','GRUPO':p['GRUPO'],'ESTADO':p['ESTADO_VALIDACION']}) for g,p in municipal]
    system80 += [(g,{'ID_NUEVA':p['ID_POLICIA'],'INSTITUCION_PROPUESTA':'POLICIA_NACIONAL','GRUPO':p['CATEGORIA_PRINCIPAL'],'ESTADO':p['ESTADO']}) for g,p in proposal]
    warnings = [
        '103inventariadas/99ubicadas aproximadas/4sin geometria. B=149ubicadas/153teoricas; C=179ubicadas/183teoricas. Nuevas=80, no80actuales.',
        'Las50municipales permanecen congeladas. Flores:par43m;Cubijies411m yLican757m no garantizan continuidad. Se reporta, no se corrige.',
        'Ubicaciones propuestas para validacion de Policia. Cruce cartografico no certifica poste, espacio publico, electricidad, permiso, cota/puente ni campo visual.',
        'Regla operativa lexicografica para este estudio, no metodologia universal ni optimizacion global. No ponderaciones ni cuotas por tematica.',
        'Ambito urbano prioritario; candidatos rurales con Gi*rural yobservacionesD/V quedan como complemento sin cuota. Diferentes escalas100/200m urbano y1000/2000m rural no se mezclan en un unico indice.',
        'Cada seleccionado debe aportar al menos1nuevo eventoD/V yarea positiva de HotSpotD/V. Convivencia sola no genera una ubicacion policial.',
        'Cobertura de HotSpot:completa>=1-1e-8,parcial>1e-8,sin<=1e-8 de fraccion; no se introduce umbral33/66 o supuesto de cobertura operativa suficiente.',
        'CoincidenciaD/V es superposicion de pruebas originales. Nivel minimoD/V es referencia descriptiva, no nueva significancia conjunta ni p-value combinado.',
        'Gi* nominal sin FDR, resultados urbanos yrurales no recalculados; no equivale a riesgo,peligrosidad ni incidencia futura.',
        'Radio200m UTM17S,64segmentos/cuadrante yunion disuelta. Distancia espacial aUPC no es tiempo de respuesta ni indicador automatico de calidad.',
        'Poblacion asociada es estimacion areal CPV2022 dentro del radio y18Plataformas, no residentes identificados ni poblacion rural completa. Sin dato se conserva null.',
        'Los incidentes mantienen sus coordenadas ypeso1. No se usa Emergencias como peso,nearest-manzana ni brechas provisionales.',
        'Corredores,poblacion yUPC no entran en la clave de seleccion. Su efecto se mide despues; no se mueven puntos para completar redes.',
        'En candidatos los NUEVOS_* son respecto aB; en propuesta ytraza se recalculan al momento de seleccion. Solape previo puede ser alto si hay nuevos eventos/celdas justificados.']
    redundancy=sorted([p for _,p in proposal],key=lambda p:p['SOLAPE_UNION_PREVIA_PCT'],reverse=True)
    metadata={'generatedAt':datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'),
        'crsMetric':'EPSG:32717','crsDisplay':'EPSG:4326','radiusM':200,'bufferQuadSegments':64,
        'inventory':103,'located':99,'municipalFrozen':50,'police':30,'newTotal':80,
        'candidatesByScope':dict(Counter(c['scope'] for c in candidates)),
        'selectedByScope':dict(Counter(c['scope'] for c in selected)),
        'selectedByCategory':dict(Counter(p['CATEGORIA_PRINCIPAL'] for _,p in proposal)),
        'selectedByPriority':dict(Counter(p['PRIORIDAD'] for _,p in proposal)),
        'priorityRule':'Urbano primero; luegoP1D+V,P2D,P3V;sin cobertura antes queparcial;nivel99>95>90;nuevosD+V;area prioritaria nueva;areaD+V;menor solape;Conv;nodo. Recalcular despues de cada seleccion. P4es evidencia complementaria,no categoria exclusiva que desplaceD/V.',
        'benefitMetric':'Numero de observacionesD/V nuevas;no score. Tambiense reportan metros cuadrados marginales deHotSpots.',
        'populationMethod':'Estimacion areal CPV2022 intersectada con18Plataformas; solo descriptiva',
        'municipalDirectory':str(MUNICIPAL),'sourceHashes':protected,'warnings':warnings,
        'municipalOriginalWarnings':municipal_data['metadata']['warnings'],
        'coverageFractionEpsilon':FRACTION_EPS,'areaEpsilonM2':AREA_EPS,
        'giUrbanDistanceM':200,'giUrbanCellSizeM':100,'giRuralDistanceM':2000,'giRuralCellSizeM':1000,
        'giRecalculated':False,'productionViewerEdited':False,'commit':False,'push':False}
    layers={'PROPUESTA_POLICIA_30':proposal,'PROPUESTA_50_CONGELADA':municipal,'SISTEMA_80_NUEVAS':system80,
        'CAMARAS_EXISTENTES_103':cameras,'BUFFERS_POLICIA_200M':[(c['disk'],{'ID_POLICIA':c['selection']['ID_POLICIA'],'RADIO_M':200}) for c in selected],
        'BUFFERS_MUNICIPALES_200M':[(g.buffer(200,quad_segs=64),{'ID_PROPUESTA':p['ID_PROPUESTA'],'RADIO_M':200}) for g,p in municipal],
        **{'COBERTURA_'+scenario:[(mask,{'ESCENARIO':scenario,'RADIO_M':200})] for scenario,mask in masks.items()},
        'HOTSPOT_COINCIDENCIA_DV':dv_rows,'COINCIDENCIA_DV_RESIDUAL':dv_remaining,'HOTSPOTS_RESIDUALES':remaining,
        'CANDIDATOS_POLICIA':candidate_rows,'UPC_INFRAESTRUCTURA':infrastructure,'PLATAFORMAS':platforms,
        'LIMITE_CANTONAL':[(canton,{'FUENTE':'Limite original del proyecto'})],
        'CORREDORES_REFERENCIA':[(g,p) for g,p in lines],
        'INCIDENTES_ESCENARIOS':[(g,{**p,**{'CUB_'+s:mask.covers(g) for s,mask in masks.items()}}) for g,p in events]}
    for (scope,category),rows in updated.items():
        layers['GI_'+scope+'_'+category]=rows
    package=OUT/'PROPUESTA_POLICIA_30.gpkg'
    layer_info=[export_layer(name,rows,package,not name.startswith('GI_')) for name,rows in layers.items()]
    for category in CLASSES:
        write_json('HOTSPOT_'+category+'.geojson',geojson([(g,p) for (scope,cat),rows in updated.items() if cat==category for g,p in rows if p['GI_CLASS'].startswith('HOTSPOT')]))
    for name,rows in [('PROPUESTA_POLICIA_30',[p for _,p in proposal]),('CANDIDATOS_POLICIA',[p for _,p in candidate_rows]),
                      ('TRAZA_SELECCION',trace),('COMPARACION_INCIDENTES',inc_stats),('COMPARACION_HOTSPOTS',hot_stats),
                      ('EFECTO_CORREDORES',corridor_stats),('REDUNDANCIAS',[{k:p[k] for k in ('ID_POLICIA','COBERTURA_PREVIA','SOLAPE_UNION_PREVIA_PCT','DIST_EXISTENTE','DIST_MUNICIPAL','DIST_POLICIA','BENEFICIO_MARGINAL','JUSTIFICACION')} for p in redundancy]),
                      ('RELACION_UPC_CORREDORES',[{k:p[k] for k in ('ID_POLICIA','UPC_CERCANA','NOMBRE_UPC','DIST_UPC_M','INFRA_CERCANA','DIST_INFRA_M','CORREDOR_COINCIDENTE')} for _,p in proposal])]:
        write_csv(name+'.csv',rows)
    assert all(sha(Path(path))==digest for path,digest in protected.items()),'Una fuente congelada cambio durante la corrida'
    metadata['protectedFilesUnchanged']=True
    data={'metadata':metadata,'proposals':[p for _,p in proposal],'incidents':inc_stats,'hotspots':hot_stats,
        'corridors':corridor_stats,'selectionTrace':trace,'redundancies':[{k:p[k] for k in ('ID_POLICIA','DIST_EXISTENTE','DIST_MUNICIPAL','DIST_POLICIA','COBERTURA_PREVIA','SOLAPE_UNION_PREVIA_PCT','BENEFICIO_MARGINAL')} for p in redundancy],
        'residualHotspotParts':len(remaining),'dvCells':dict(Counter(p['AMBITO'] for _,p in dv)),
        'layers':layer_info}
    write_json('RESULTADOS.json',data)
    write_report(data)
    print(json.dumps({'categories':metadata['selectedByCategory'],'scopes':metadata['selectedByScope'],
        'incidentsCantonal':[r for r in inc_stats if r['AMBITO']=='CANTONAL'],'corridors':corridor_stats},indent=2),flush=True)


def write_report(data):
    def table(fields,rows):
        def clean(v):
            if v is None:return 'No disponible'
            if isinstance(v,float):return f'{v:.3f}'
            return str(v).replace('|','/').replace('\n',' ')
        return '\n'.join(['| '+' | '.join(fields)+' |','| '+' | '.join(['---']*len(fields))+' |']+
            ['| '+' | '.join(clean(r.get(k)) for k in fields)+' |' for r in rows])
    m=data['metadata']
    lines=['# Propuesta de 30 camaras para Policia Nacional','',
        '**Sin commit/push. Visor definitivo intacto. Propuesta50municipal congelada. Revision tecnica/operativa pendiente.**',
        '## Sistema completo','A=103 inventariadas,99 ubicadas; B=A+50municipales(149 ubicadas/153teoricas); C=B+30Policia(179 ubicadas/183teoricas).50+30=80nuevas. Cuatro existentes sin geometria conservadas.',
        'Municipales:22cabeceras+4LasAbras+24estructurales. No se mueve,elimina,agrega ni reoptimiza ninguna.',
        '## Metodologia de seleccion',m['priorityRule'],m['benefitMetric'],
        'Candidatos en nodos de grado>=3 de redes viales originales, dentro del canton, a distancia potencial<=200m de HotSpotsD/V. No se crean centroides ni puntos a intervalos regulares. Fuentes urbanas y cantonales se nodifican por separado, sin inventar cruces entre dos cartografias.',
        'Cada candidato urbano puede estar dentro o justo fuera de las18Plataformas;AMBITO_HOTSPOT identifica la escala estadistica que justifica el radio. Un rural requiere ademas observacionesD/V reales. Urbano es objetivo principal; rural es complemento si no queda evidencia urbana elegible. No se fijan cuotas tematicas/geograficas.',
        'Elegibilidad en cada iteracion:al menos1nuevo eventoD/V yarea adicional>0.01m2 de HotSpotD/V. El umbral de area es tolerancia numerica, no un umbral operativo de peligrosidad/cobertura suficiente. Se excluye coincidencia exacta con actuales/municipales.',
        'En cada paso se recalculan eventos fuera de union acumulada yareas residualesD/V. Los valoresBENEFICIO_MARGINAL son eventos, no metros,porcentajes ni score0-100. El area por categoria puede superponerse; no sumar como superficie fisica unica.',
        'P1coincidenciaD/V tiene prioridad;P2D;P3V. Dentro de la prioridad:sin cobertura,despuesparcial;99>95>90;mas eventosD/V nuevos;masarea prioritaria;areaD+V;menos solape;Conv;grado nodo. P4alta concentracion se trata como evidencia complementaria ya presente en esas categorias,no cuota ni una categoriaConv exclusiva.',
        '## Distribucion resultante',str(m['selectedByCategory']),str(m['selectedByScope']),str(m['candidatesByScope']),
        '## Incidentes: A/B/C',table(list(data['incidents'][0]),data['incidents']),
        'BASE_COMPLETA conserva11150D/V/C incluidos8externos;CANTONAL11142;URBANO9915. Puntos originales,peso1,sin asignacion a manzanas.',
        '## Hot Spots: tres escenarios y niveles99/95/90',table(list(data['hotspots'][0]),data['hotspots']),
        'CUBIERTO=fraccion>=1-1e-8;PARCIAL=>1e-8y<1-1e-8;SIN<=1e-8. Alguna interseccion no equivale a celda completa. Gi* completo incluye estadosno significativo/ColdSpot originales disponibles en6capasGI. No se recalcula urbano ni rural.',
        '## Coincidencia D/V',str(data['dvCells']),
        'HOTSPOT_COINCIDENCIA_DV cruza geometricamente las celdas significativas; se conservan z-score,p-value y niveles separadosD/V. El menor nivel es solo descripcion del par,no prueba estadistica conjunta.',
        'COINCIDENCIA_DV_RESIDUAL yHOTSPOTS_RESIDUALES muestran las partes de celda que permanecen fuera de coberturaC, incluidas celdas parcialmente cubiertas.',
        '## Corredores: efecto incidental',table(list(data['corridors'][0]),data['corridors']),
        'Los corredores no entran en ninguna clave de seleccion ni condicion de beneficio. Se miden al finalizar, sin mover puntos. LasAbras solamente eje dentro del canton.',
        '## Tabla completa y justificaciones',table(['ID_POLICIA','X','Y','PRIORIDAD','CATEGORIA_PRINCIPAL','AMBITO_HOTSPOT','NIVEL_DEL','NIVEL_VIOL','NIVEL_CONV','DELINCUENCIA_200M','VIOLENCIA_200M','CONVIVENCIA_200M','BENEFICIO_MARGINAL','COBERTURA_PREVIA','POBLACION_ASOCIADA','UPC_CERCANA','DIST_UPC_M','CORREDOR_COINCIDENTE','JUSTIFICACION'],data['proposals']),
        'CSV/GPKG conserva los campos adicionales:IDs de celdas,coincidenciaD/V,distancias aexistente/municipal/policial,solape acumulado,poblacionfaltante,origennodo,contadoriterativo yestadoPROPUESTA_PARA_VALIDACION_POLICIA.',
        '## Redundancias',table(list(data['redundancies'][0]),data['redundancies']),
        'COBERTURA_PREVIA es%del disco ya cubierto porB;SOLAPE_UNION_PREVIA_PCT incluye laspoliciales seleccionadas antes. Distancias finales aotraPolicia ydistancia al seleccionar son campos diferentes. Solape alto no se interpreta automaticamente como duplicacion si hay beneficio real.',
        '## Advertencias',*['- '+w for w in m['warnings']],
        '## Capas y campos',table(['name','records','crs','fields'],[{**r,'fields':', '.join(r['fields'])} for r in data['layers']]),
        'GeoPackageEPSG:32717;GeoJSONvisualEPSG:4326. RESULTADOS.json conservaSHA256 de todas lasfuentes yde todo el paquete municipal,incluidozip. MetadatosnoNULLnoinventados. CANDIDATOS_POLICIA informa beneficio respectoB;traza ypropuesta beneficio al momento de seleccion.',
        '**Detenido para revision; no se publica ni se integra en el visor definitivo.**']
    (OUT/'INFORME_POLICIA_30.md').write_text('\n\n'.join(lines),encoding='utf-8')
    (OUT/'README.md').write_text('# Revision Policia30\n\nindex.html:mapa principal y80nuevas. coincidencias.html:mapaD/V yremanentes. PROPUESTA_POLICIA_30.gpkg contiene todas las capas metricas,incluidoGi*completo urbano/rural sin recalcular.\n\nINFORME_POLICIA_30.md:metodo,comparacionesA/B/C,30justificaciones,UPC,corredores,redundancias ylimitaciones. CSV:tablas completas;RESULTADOS.json:metadatos yhashes.\n\n50municipales congeladas. No commit/push. Revision operativa pendiente.\n',encoding='utf-8')


if __name__=='__main__':
    main()
