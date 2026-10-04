"""Read-only diagnosis of the existing inventory; proposed cameras never enter calculations."""
import csv
import hashlib
import json
import math
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import pyogrio
from pyproj import Transformer
from shapely import force_2d
from shapely.geometry import Point, shape, mapping
from shapely.ops import transform, unary_union

from build_remaining_camera_coverage import ROOT, PROTECTED, read_js, load

OUT = ROOT / 'data/seguridad-riobamba/diagnostico-actual-103-20261002'
GPKG = Path('D:/codex/exportaciones/INSUMOS_CAMARAS_PROPUESTAS_20261002_CON_ANILLO/INSUMOS_CAMARAS_PROPUESTAS.gpkg')
ABRAS = [Path('C:/Users/PC/Downloads/barrios y plataformas/quebrada_las_abras_referencial.shp'),
         Path('C:/Users/PC/Downloads/barrios y plataformas/rios/quebrada_las_abras_completa.shp'),
         Path('C:/Users/PC/Downloads/barrios y plataformas/rios/quebrada_las_abras_eje_principal_completado.shp')]
PROJECT = Transformer.from_crs(4326, 32717, always_xy=True).transform
UNPROJECT = Transformer.from_crs(32717, 4326, always_xy=True).transform
CLASSES = ('DELINCUENCIA', 'VIOLENCIA', 'CONVIVENCIA')
CORRIDORS = {'ANILLO_VIAL': 'Anillo vial', 'BOULEVARD_MACAJI_BELLAVISTA': 'Macaji-Bellavista',
             'CICLOVIAS': 'Ciclovias', 'QUEBRADA_LAS_ABRAS': 'Quebrada Las Abras'}
DIMENSIONS = {'Point': 0, 'LineString': 1, 'Polygon': 2}
AREA_EPSILON = .01


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pct(value, total):
    return 100 * value / total if total else None


def parts(geom, dimension=None):
    if geom.is_empty:
        return []
    if geom.geom_type in DIMENSIONS:
        return [geom] if dimension is None or DIMENSIONS[geom.geom_type] == dimension else []
    return [part for g in getattr(geom, 'geoms', []) for part in parts(g, dimension)]


def fc(rows):
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': props, 'geometry': mapping(transform(UNPROJECT, geom)) if geom is not None else None}
        for geom, props in rows]}


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf-8')


def split_conditions(items, mask, condition, dimension):
    result = []
    for geom, conditions in items:
        result.extend((g, conditions | {condition}) for g in parts(geom.intersection(mask), dimension))
        result.extend((g, conditions) for g in parts(geom.difference(mask), dimension))
    return result


def strategic_sectors(axes, hot, centers, coverage):
    """Exact overlay only: no arbitrary neighborhood, score, snapping or camera placement."""
    candidates = []
    for scope in ('URBANO', 'RURAL'):
        d = unary_union([g for g, p in hot if p['AMBITO'] == scope and p['CATEGORIA'] == 'DELINCUENCIA'])
        v = unary_union([g for g, p in hot if p['AMBITO'] == scope and p['CATEGORIA'] == 'VIOLENCIA'])
        for geom, conditions in ((d.difference(v), {'HOTSPOT_DELINCUENCIA'}),
                                 (v.difference(d), {'HOTSPOT_VIOLENCIA'}),
                                 (d.intersection(v), {'HOTSPOT_DELINCUENCIA', 'HOTSPOT_VIOLENCIA'})):
            candidates.extend((g, c, scope) for g, c in split_conditions([(geom, conditions)], coverage, 'COBERTURA_ACTUAL', 2))
    hot_masks = {category: unary_union([g for g, p in hot if p['CATEGORIA'] == category]) for category in CLASSES[:2]}
    for key, axis in axes.items():
        items = [(axis, {key})]
        for other, geom in axes.items():
            if other != key:
                items = split_conditions(items, geom, other, 1)
        for category, geom in hot_masks.items():
            items = split_conditions(items, geom, 'HOTSPOT_' + category, 1)
        candidates.extend((g, c, 'LINEAL') for g, c in split_conditions(items, coverage, 'COBERTURA_ACTUAL', 1))
    # Point crossings are retained separately from positive-length overlaps.
    keys = list(axes)
    crossings = [p for i, key in enumerate(keys) for other in keys[i+1:]
                 for p in parts(axes[key].intersection(axes[other]), 0)]
    for point, is_center in [(p, False) for p in crossings] + [(p, True) for p in centers]:
        conditions = {'CABECERA_RURAL'} if is_center else set()
        conditions |= {key for key, axis in axes.items() if axis.intersects(point)}
        conditions |= {'HOTSPOT_' + key for key, geom in hot_masks.items() if geom.covers(point)}
        if coverage.covers(point):
            conditions.add('COBERTURA_ACTUAL')
        candidates.append((point, conditions, 'PUNTUAL'))
    rows, unique = [], set()
    for geom, conditions, scope in candidates:
        if geom.is_empty or (geom.geom_type == 'Polygon' and geom.area <= AREA_EPSILON):
            continue
        uncovered = 'COBERTURA_ACTUAL' not in conditions
        conditions = conditions - {'COBERTURA_ACTUAL'}
        if uncovered:
            conditions.add('BAJA_COBERTURA_ACTUAL')
        if len(conditions) < 2:
            continue
        key = (geom.normalize().wkb, tuple(sorted(conditions)))
        if key in unique:
            continue
        unique.add(key)
        rows.append((geom, {'ID_SECTOR': f'EST-{len(rows)+1:04d}', 'AMBITO': scope,
            'TIPO_GEOM': geom.geom_type, 'N_CONDICIONES': len(conditions), 'CONDICIONES': '|'.join(sorted(conditions)),
            'SIN_COB_200': uncovered, 'COB_200': 0. if uncovered else 100.,
            'AREA_M2': geom.area, 'LONGITUD_M': geom.length if geom.geom_type == 'LineString' else None,
            'METODO': 'Coincidencia geometrica exacta; sin ponderacion ni radio de asociacion'}))
    return rows


def hotspot_stats(rows):
    total = len(rows)
    with_coverage = sum(p['COB_200'] > 1e-6 for _, p in rows)
    complete = sum(p['COB_200'] >= 99.9999 for _, p in rows)
    return {'total': total, 'withCoverage': with_coverage, 'uncovered': total-with_coverage,
            'partiallyCovered': with_coverage-complete, 'fullyCovered': complete,
            'pctCellsWithCoverage': pct(with_coverage, total),
            'areaM2': sum(g.area for g, _ in rows),
            'coveredAreaM2': sum(p['AREA_CUB_M2'] for _, p in rows),
            'pctAreaCovered': pct(sum(p['AREA_CUB_M2'] for _, p in rows), sum(g.area for g, _ in rows))}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    protected_paths = [ROOT / p for p in PROTECTED] + [ROOT / 'riobamba-hotspot-urbano-200m-data.js',
        ROOT / 'riobamba-censo-data/riobamba_plataformas.geojson', ROOT / 'riobamba-censo-data/riobamba_manzanas.geojson',
        ROOT / 'riobamba-censo-data/riobamba_manzanas_stats.json', GPKG,
        Path('C:/Users/PC/Downloads/PROPUESTA_CAMARAS_RIOBAMBA_200M.csv')]
    protected_paths += list((ROOT / 'data/seguridad-riobamba/correccion-propuesta-corredores-20261002').glob('*'))
    protected_paths += list((ROOT / 'data/seguridad-riobamba/propuesta-camaras-20261002').glob('*'))
    protected_paths += [p for axis in ABRAS for p in axis.parent.glob(axis.stem + '.*') if p.suffix.lower() not in ('.lock', '.lck')]
    protected = {str(p): sha(p) for p in protected_paths if p.is_file()}
    inventory = read_js('riobamba-camaras-inventario-data.js')['cameras']
    camera_rows, points, camera_errors = [], [], []
    for camera in inventory:
        lon, lat = camera.get('lng'), camera.get('lat')
        valid = lon is not None and lat is not None and math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90 and (lon, lat) != (0, 0)
        point = Point(PROJECT(lon, lat)) if valid else None
        if point is not None:
            points.append(point)
        else:
            camera_errors.append(camera['id'])
        camera_rows.append((point, {'ID_CAMARA': camera['id'], 'TIPO': camera['type'],
            'ESTADO': camera.get('status', 'No disponible'), 'REQUIERE_CAMBIO': camera.get('requiresChange'),
            'INSTITUCION': camera.get('institution'), 'DIRECCION': camera.get('address'),
            'LONGITUD': lon, 'LATITUD': lat, 'X': point.x if point is not None else None,
            'Y': point.y if point is not None else None, 'GEOMETRIA_VALIDA': valid,
            'PRECISION': camera.get('locationStatus', 'Ubicacion aproximada; pendiente campo')}))
    assert len(inventory) == 103 and len(points) == 99 and len(camera_errors) == 4
    coverage = unary_union([p.buffer(200, quad_segs=64) for p in points])
    assert coverage.is_valid
    territory = read_js('riobamba-cantonal-data.js')
    correction = read_js('riobamba-conflictividad-data.js')
    urban_gi = read_js('riobamba-hotspot-urbano-200m-data.js')
    assert urban_gi['metadata']['HOTSPOT_URBANO_DISTANCE_M'] == 200 and urban_gi['grid']['cellSize'] == 100
    canton = transform(PROJECT, shape(territory['canton']['geometry']))
    platform_rows = [(transform(PROJECT, shape(f['geometry'])), f['properties']) for f in load('riobamba-censo-data/riobamba_plataformas.geojson')['features']]
    urban = unary_union([g for g, _ in platform_rows])
    axes = {key: unary_union(pyogrio.read_dataframe(GPKG, layer=key).to_crs(32717).geometry) for key in list(CORRIDORS)[:3]}
    original_abras = unary_union([g for axis in ABRAS for g in pyogrio.read_dataframe(axis).to_crs(32717).geometry])
    axes['QUEBRADA_LAS_ABRAS'] = original_abras.intersection(canton)
    layers = {'CAMARAS_EXISTENTES_103': camera_rows,
              'COBERTURA_ACTUAL_DISUELTA_200M': [(coverage, {'RADIO_M': 200, 'CAMARAS_USADAS': 99})],
              'PLATAFORMAS_TERRITORIALES': platform_rows,
              'LIMITE_CANTONAL': [(canton, {'FUENTE': 'Limite cantonal existente del proyecto'})]}
    corridor_stats, segment_rows = [], []
    for key, axis in axes.items():
        covered, uncovered = axis.intersection(coverage), axis.difference(coverage)
        assert abs(covered.length + uncovered.length - axis.length) < .001
        corridor_stats.append({'key': key, 'name': CORRIDORS[key], 'totalM': axis.length, 'coveredM': covered.length,
            'uncoveredM': uncovered.length, 'pctCovered': pct(covered.length, axis.length)})
        prefix = {'ANILLO_VIAL': 'ANILLO', 'BOULEVARD_MACAJI_BELLAVISTA': 'MACAJI_BELLAVISTA',
                  'CICLOVIAS': 'CICLOVIAS', 'QUEBRADA_LAS_ABRAS': 'LAS_ABRAS'}[key]
        for status, geom in [('CUBIERTO', covered), ('SIN_COBERTURA', uncovered)]:
            rows = [(g, {'ELEMENTO': key, 'NOMBRE': CORRIDORS[key], 'ESTADO': status, 'RADIO_M': 200, 'LONGITUD_M': g.length}) for g in parts(geom, 1)]
            layers[f'{prefix}_{status}_200M'] = rows
            segment_rows.extend(rows)
    population, population_covered, missing_population = 0., 0., 0
    population_data = load('riobamba-censo-data/riobamba_manzanas_stats.json')['byMan']
    for f in load('riobamba-censo-data/riobamba_manzanas.geojson')['features']:
        geom = transform(PROJECT, shape(f['geometry']))
        urban_part = geom.intersection(urban)
        if urban_part.area <= AREA_EPSILON:
            continue
        value = population_data.get(f['properties']['man'], {}).get('population_total')
        if value is None or not math.isfinite(value) or value < 0:
            missing_population += 1
            continue
        population += value * urban_part.area / geom.area
        population_covered += value * urban_part.intersection(coverage).area / geom.area
    events = []
    for event in read_js('visor-seguridad-riobamba-data.js')['events']:
        category = correction['dictionary'].get(event['subtype'])
        if category not in CLASSES:
            continue
        point = Point(PROJECT(event['lng'], event['lat']))
        scope = 'URBANO' if urban.covers(point) else 'RESTO_CANTON' if canton.covers(point) else 'EXTERNO_CANTON'
        events.append((point, {'ID': event['id'], 'CATEGORIA': category, 'SUBTIPO': event['subtype'],
            'AMBITO': scope, 'CUBIERTO_200': coverage.covers(point)}))
    incident_stats = {}
    for scope in ('BASE_COMPLETA', 'CANTONAL', 'URBANO', 'RESTO_CANTON', 'EXTERNO_CANTON'):
        incident_stats[scope] = {}
        for category in CLASSES:
            selected = [p for _, p in events if p['CATEGORIA'] == category and (scope == 'BASE_COMPLETA' or
                (scope == 'CANTONAL' and p['AMBITO'] != 'EXTERNO_CANTON') or p['AMBITO'] == scope)]
            covered = sum(p['CUBIERTO_200'] for p in selected)
            incident_stats[scope][category] = {'total': len(selected), 'covered': covered, 'uncovered': len(selected)-covered, 'pctCovered': pct(covered, len(selected))}
    layers['INCIDENTES_COBERTURA_ACTUAL'] = events
    hot_rows, hotspot_summary = [], {}
    for scope in ('URBANO', 'RURAL'):
        grid = urban_gi['grid'] if scope == 'URBANO' else territory['ruralGrid']
        for category in CLASSES:
            source = urban_gi['byClass'][category] if scope == 'URBANO' else correction['gi'][scope][category]
            rows = []
            for cell, result in zip(grid['cells'], source['results']):
                if not result['GI_CLASS'].startswith('HOTSPOT'):
                    continue
                geom = transform(PROJECT, shape(cell['geometry']))
                level = int(result['GI_CLASS'].split()[1].strip('%'))
                covered_area = geom.intersection(coverage).area
                rows.append((geom, {'CELL_ID': cell['cellId'], 'AMBITO': scope, 'CATEGORIA': category, 'NIVEL': level,
                    **result, 'AREA_CUB_M2': covered_area, 'COB_200': pct(covered_area, geom.area),
                    'DISTANCE_M': 200 if scope == 'URBANO' else grid['neighborDistance']}))
            layers[f'HOTSPOT_{scope}_{category}'] = rows
            hot_rows.extend(rows)
            hotspot_summary[f'{scope}_{category}'] = {'all': hotspot_stats(rows),
                'levels': {str(level): hotspot_stats([(g, p) for g, p in rows if p['NIVEL'] == level]) for level in (99, 95, 90)}}
    centers = pyogrio.read_dataframe(GPKG, layer='CABECERAS_PARROQUIALES_RURALES').to_crs(32717)
    center_rows, center_summary = [], []
    for _, row in centers.iterrows():
        point, parish = force_2d(row.geometry), str(row['PARROQUIA'])
        neighborhood = point.buffer(200, quad_segs=64)
        camera_ids = [p['ID_CAMARA'] for g, p in camera_rows if g is not None and point.distance(g) <= 200]
        incident_counts = {category: sum(neighborhood.covers(g) and p['CATEGORIA'] == category for g, p in events) for category in CLASSES}
        center_hot = {category: max([p['NIVEL'] for g, p in hot_rows if p['AMBITO'] == 'RURAL' and p['CATEGORIA'] == category and g.covers(point)] or [0]) for category in CLASSES}
        nearby_hot = {category: max([p['NIVEL'] for g, p in hot_rows if p['AMBITO'] == 'RURAL' and p['CATEGORIA'] == category and g.intersection(neighborhood).area > AREA_EPSILON] or [0]) for category in CLASSES}
        props = {'PARROQUIA': parish, 'CAMARAS_ACTUALES_200M': len(camera_ids), 'TIENE_COBERTURA': coverage.covers(point),
            'ID_CAMARAS': '|'.join(camera_ids), 'INCIDENTES': sum(incident_counts.values()),
            **{'INC_' + k: v for k, v in incident_counts.items()},
            'HOTSPOT_RURAL': '|'.join(f'{k}:{v}%' for k, v in center_hot.items() if v) or 'Sin Hot Spot en punto de cabecera',
            **{'GI_CENTRO_' + k: v for k, v in center_hot.items()}, **{'GI_ENTORNO_' + k: v for k, v in nearby_hot.items()},
            'COB_ENTORNO_200_PCT': pct(neighborhood.intersection(coverage).area, neighborhood.area),
            'DIST_CAMARA_MIN_M': min(point.distance(g) for g in points),
            'OBSERVACION': 'Referencia puntual GIS, no toda la parroquia. Incidentes en entorno200m; Gi* rural original. Poblacion local no disponible.'}
        center_rows.append((point, props))
        center_summary.append(props)
    layers['CABECERAS_RURALES_DIAGNOSTICO'] = center_rows
    strategies = strategic_sectors(axes, hot_rows, [g for g, _ in center_rows], coverage)
    layers['SECTORES_ESTRATEGICOS'] = strategies
    metadata = {'generatedAt': datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'),
        'crsMetric': 'EPSG:32717', 'crsDisplay': 'EPSG:4326', 'radiusM': 200,
        'scenario': 'ACTUAL_103_EXCLUSIVO', 'camerasInventoried': len(inventory), 'camerasLocated': len(points),
        'camerasWithoutGeometry': len(camera_errors), 'pendingCameraIds': camera_errors,
        'proposedCamerasUsed': 0, 'newPoliceCameras': 0, 'originalsModified': False,
        'urbanScope': 'Union de18 Plataformas reales: ambito urbano operativo, no limite urbano legal.',
        'populationMethod': 'Estimacion areal CPV2022 en manzanas con dato; no confundir con total urbano oficial de tasas.',
        'missingPopulationBlocks': missing_population, 'sourceHashes': protected,
        'ruralResultsSHA256': sha(ROOT / 'riobamba-conflictividad-data.js'), 'ruralDistanceM': territory['ruralGrid']['neighborDistance'],
        'hotspotCoverage': 'Con cobertura = fraccion de area cubierta >1e-8, tolerancia numerica consistente con evaluacion existente; no significa celda completa. Se informa por separado el porcentaje de area efectivamente cubierto.',
        'strategicMethod': 'Intersecciones exactas de corredores/hotspots D-V/cabeceras; subdivididas por cobertura actual. Dos o mas condiciones, sin score, pesos ni radio de asociacion. BAJA_COBERTURA_ACTUAL significa fuera de union200m, no indice de brecha.',
        'strategicCaveat': 'Coincidencia cartografica descriptiva. No clasifica peligrosidad, factibilidad ni ubicaciones nuevas. No cuenta CONVIVENCIA como criterio de priorizacion.',
        'gapStatus': 'ANALISIS EN VALIDACION: no utilizado en diagnostico ni decisiones.',
        'abrasScope': 'Union de tres ejes originales recortada solo en copia derivada dentro del canton.',
        'cameraPrecision': 'Ubicaciones aproximadas del inventario; geometria valida no certifica posicion de campo u operatividad.',
        'period': urban_gi['metadata']['period'], 'bufferMethod': 'Discos200m en UTM17S,64 segmentos por cuadrante; union disuelta antes de todo cruce.'}
    summary = {'metadata': metadata, 'general': {'urbanAreaKm2': urban.area/1e6,
        'coveredUrbanAreaKm2': urban.intersection(coverage).area/1e6, 'uncoveredUrbanAreaKm2': urban.difference(coverage).area/1e6,
        'pctTerritoryCovered': pct(urban.intersection(coverage).area, urban.area), 'populationAnalyzed': population,
        'populationCovered': population_covered, 'populationUncovered': population-population_covered,
        'pctPopulationCovered': pct(population_covered, population), 'fullDissolvedAreaKm2': coverage.area/1e6},
        'corridors': corridor_stats, 'incidents': incident_stats, 'hotspots': hotspot_summary, 'cabeceras': center_summary,
        'strategicCounts': dict(Counter(p['TIPO_GEOM'] for _, p in strategies)),
        'needs': {'ruralCentersWithoutCoverage': [p['PARROQUIA'] for p in center_summary if not p['TIENE_COBERTURA']],
                  'hotspotUncovered': {key: v['all']['uncovered'] for key, v in hotspot_summary.items()}}}
    for layer, rows in layers.items():
        frame = gpd.GeoDataFrame([props for _, props in rows], geometry=[g for g, _ in rows], crs=32717)
        pyogrio.write_dataframe(frame, OUT / 'DIAGNOSTICO_ACTUAL_103_200M.gpkg', layer=layer, geometry_type='Unknown' if layer == 'SECTORES_ESTRATEGICOS' else None)
    for name, rows in [('CAMARAS_ACTUALES', camera_rows), ('COBERTURA_ACTUAL', layers['COBERTURA_ACTUAL_DISUELTA_200M']),
                       ('CORREDORES_SEGMENTOS', segment_rows), ('HOTSPOTS_ACTUALES', hot_rows),
                       ('CABECERAS_ACTUALES', center_rows), ('SECTORES_ESTRATEGICOS', strategies), ('PLATAFORMAS', platform_rows),
                       ('LIMITE_CANTONAL', layers['LIMITE_CANTONAL'])]:
        write_json(name + '.geojson', fc(rows))
    for name, rows in [('CORREDORES', corridor_stats), ('CABECERAS', center_summary),
                       ('HOTSPOTS', [{'AMBITO_CATEGORIA': key, 'NIVEL': level, **v} for key, stat in hotspot_summary.items() for level, v in [('TODOS', stat['all']), *stat['levels'].items()]]),
                       ('INCIDENTES', [{'AMBITO': scope, 'CATEGORIA': key, **v} for scope, stats in incident_stats.items() for key, v in stats.items()])]:
        with (OUT / (name + '.csv')).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    assert all(sha(Path(path)) == digest for path, digest in protected.items()), 'Una fuente protegida cambio durante la corrida'
    metadata['protectedFilesUnchanged'] = True
    summary['layers'] = [{'name': layer, 'records': len(rows), 'crs': 'EPSG:32717',
        'fields': list(rows[0][1]) if rows else []} for layer, rows in layers.items()]
    write_json('RESULTADOS.json', summary)
    write_report(summary)
    with zipfile.ZipFile(OUT / 'DIAGNOSTICO_ACTUAL_103_200M.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in OUT.iterdir():
            if path.suffix in ('.gpkg', '.csv', '.md', '.json'):
                archive.write(path, path.name)
    print(json.dumps({'general': summary['general'], 'corridors': corridor_stats, 'needs': summary['needs'], 'strategicCounts': summary['strategicCounts']}, indent=2))


def write_report(data):
    def table(headers, rows):
        return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] +
            ['| ' + ' | '.join(str(v) for v in row) + ' |' for row in rows])
    def n(value, digits=2):
        return 'No disponible' if value is None else f'{value:,.{digits}f}'
    m, general = data['metadata'], data['general']
    lines = ['# Diagnostico del escenario actual:103 camaras, radio200m',
        '**SIN COMMIT/PUSH. No se modificaron las50 propuestas ni se generaron30 camaras para Policia.**',
        '[Mapa de diagnostico](http://127.0.0.1:8767/data/seguridad-riobamba/diagnostico-actual-103-20261002/index.html)',
        '## Estado actual', f'Inventariadas103; geometria valida99; sin geometria4: {", ".join(m["pendingCameraIds"])}.',
        m['cameraPrecision'], m['urbanScope'], m['populationMethod'],
        table(['Indicador', 'Valor'], [['Area urbana km2', n(general['urbanAreaKm2'])],
            ['Area urbana potencialmente cubierta km2', n(general['coveredUrbanAreaKm2'])],
            ['Territorio cubierto %', n(general['pctTerritoryCovered'])], ['Poblacion analizada estimada', n(general['populationAnalyzed'],0)],
            ['Poblacion cubierta estimada', n(general['populationCovered'],0)], ['Poblacion cubierta %', n(general['pctPopulationCovered'])]]),
        '## Diagnostico por corredor',
        table(['Elemento', 'Total km', 'Cubierto km', 'Sin cobertura km', '% cubierto'],
            [[v['name'], n(v['totalM']/1000,3), n(v['coveredM']/1000,3), n(v['uncoveredM']/1000,3), n(v['pctCovered'])] for v in data['corridors']]),
        m['abrasScope'], 'Longitudes en la union lineal original de cada red: solapes de ejes no se cuentan doble. Ciclovias incluye los ejes existentes/proyectados de la fuente, no certifica obra construida.',
        '## Cabeceras parroquiales rurales',
        table(['Parroquia', 'Camaras <=200m', 'Centro cubierto', 'Incidentes <=200m D/V/C', 'Gi* rural en centro', 'Dist. camara mas cercana m'],
            [[v['PARROQUIA'], v['CAMARAS_ACTUALES_200M'], v['TIENE_COBERTURA'], v['INCIDENTES'], v['HOTSPOT_RURAL'], n(v['DIST_CAMARA_MIN_M'])] for v in data['cabeceras']]),
        'Cobertura se refiere al punto de cabecera GIS, no a la parroquia completa. Incidentes contados individualmente en un entorno200m. CSV informa categorias y Gi* rural tanto en el centro como en el entorno; sin recalcularlo. Poblacion local no disponible.',
        f'Cabeceras sin cobertura del punto: {len(data["needs"]["ruralCentersWithoutCoverage"])}: {", ".join(data["needs"]["ruralCentersWithoutCoverage"])}.',
        '## Hot Spots existentes: relacion con cobertura', m['hotspotCoverage'],
        table(['Ambito/categoria', 'Nivel', 'Total', 'Con cobertura', 'Parcial', 'Completa', 'Sin cobertura', '%celdas con alguna cobertura', '%area cubierta'],
            [[key, level, v['total'], v['withCoverage'], v['partiallyCovered'], v['fullyCovered'], v['uncovered'], n(v['pctCellsWithCoverage']), n(v['pctAreaCovered'])]
             for key, stats in data['hotspots'].items() for level, v in [('TODOS', stats['all']), *stats['levels'].items()]]),
        'Urbano: malla100m, distanciaGi*200m. Rural: datos originales, distancia2000m; no se recalcula ni se reemplaza ningun archivo rural. Significancia nominal bilateral sin FDR; no implica peligrosidad. No sumar celdas de distintas categorias como sectores unicos: pueden superponerse.',
        '## Incidentes: interseccion directa punto-buffer',
        table(['Ambito', 'Categoria', 'Total', 'Cubiertos', 'Fuera', '%cubierto'],
            [[scope, key, v['total'], v['covered'], v['uncovered'], n(v['pctCovered'])] for scope, stats in data['incidents'].items() for key, v in stats.items()]),
        'BASE_COMPLETA conserva todos los D/V/C georreferenciados; CANTONAL excluye EXTERNO_CANTON explicitamente. URBANO usa las18 Plataformas. Peso1 por registro, no Emergencias. No se utiliza asociacion a manzanas ni centroides.',
        '## Sectores estrategicos descriptivos', m['strategicMethod'], m['strategicCaveat'],
        f'Geometrias resultantes por tipo: {data["strategicCounts"]}. No equivale a un numero de barrios ni a nuevas camaras.',
        'La coincidencia exigida es exacta. Corredores cercanos que no se cruzan no se declaran coincidentes. Cabeceras sin cobertura generan referencias puntuales, no areas de influencia inventadas. Poligonos hot D/V y lineas se subdividen por la union de cobertura; no se modifican fuentes.',
        '## Brechas', m['gapStatus'],
        'Se mantiene oficialmente la interseccion estricta929/9915 y8986 sin asignar. No interviene en este diagnostico ni en los sectores estrategicos.',
        '## Capas utilizadas',
        '-Inventario103: riobamba-camaras-inventario-data.js;99 ubicaciones aproximadas y4 pendientes.',
        '-Plataformas, manzanas y poblacion: riobamba-censo-data, fuentes originales CPV2022/GAD.',
        '-Redes y cabeceras: GeoPackage de insumos existente; Las Abras: tres ejes GIS originales, solo recorte derivado dentro del canton.',
        '-Incidentes: visor-seguridad-riobamba-data.js + diccionario de riobamba-conflictividad-data.js.',
        '-Gi* urbano: riobamba-hotspot-urbano-200m-data.js. Rural: riobamba-cantonal-data.js + resultados rurales originales de riobamba-conflictividad-data.js.',
        '## Capas generadas / campos',
        table(['Capa', 'Registros', 'CRS', 'Campos'], [[v['name'], v['records'], v['crs'], ', '.join(v['fields'])] for v in data['layers']]),
        '## Auditoria y limitaciones',
        'RESULTADOS.json conserva hashes de todas las fuentes y de los archivos existentes de la propuesta. Todos permanecen intactos. Camaras propuestas utilizadas=0. Nuevas camarasPolicia=0.',
        m['bufferMethod'], 'Radio es distancia desde el centro; no diametro. Cobertura geometrica potencial, no campo visual, altura, obstaculos, conectividad, operatividad ni tiempo de respuesta.',
        f'Manzanas urbanas sin poblacion valida: {m["missingPopulationBlocks"]}; ausencia de informacion no se convierte en cero. Poblacion cubierta es estimada bajo distribucion uniforme intramanzana.',
        'Solo se crearon tools/build_current_camera_diagnosis.py, su prueba y el directorio del diagnostico. Los modulos existentes y posiciones originales no se modifican.',
        '**Detenido para revision antes de distribuir80 camaras nuevas.**']
    (OUT / 'INFORME_DIAGNOSTICO.md').write_text('\n\n'.join(lines), encoding='utf-8')
    (OUT / 'README.md').write_text('# Diagnostico actual103\n\nSolo99 puntos validos, radio200m disuelto. Propuestas utilizadas0. EPSG:32717 en GeoPackage; GeoJSON visual EPSG:4326.\n\nINFORME_DIAGNOSTICO.md documenta fuentes, campos, conteos, metodologia, limitaciones y archivos. RESULTADOS.json conserva hashes y validacion.\n\nBrechas: ANALISIS EN VALIDACION, fuera de este diagnostico. Rural no recalculado. No commit/push.\n', encoding='utf-8')


if __name__ == '__main__':
    main()
