"""Refresh coverage dependencies with final cameras; preserve GIS inputs and Gi*."""
import csv
import hashlib
import json
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import geopandas as gpd
import pyogrio
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform, unary_union

from build_camera_proposal import classify, problem_level
from build_remaining_camera_coverage import ROOT, load, read_js

BASE = ROOT / 'data/seguridad-riobamba'
FINAL = BASE / 'CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA/CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.gpkg'
PREVIOUS = BASE / 'propuesta-camaras-20261002/EVALUACION_PROPUESTA_CAMARAS.gpkg'
OUT = BASE / 'brechas-actualizadas-20261004'
FIXED_INPUT = OUT / 'INSUMOS_FIJOS_BRECHAS.json'
PROJECT = Transformer.from_crs(4326, 32717, always_xy=True).transform
UNPROJECT = Transformer.from_crs(32717, 4326, always_xy=True).transform
LEVELS = ('ALTA', 'MEDIA', 'BAJA', 'SIN EVIDENCIA')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def feature(geometry, properties):
    return {'type': 'Feature', 'properties': properties,
            'geometry': mapping(transform(UNPROJECT, geometry))}


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def main():
    protected = [FINAL, FIXED_INPUT if FIXED_INPUT.exists() else PREVIOUS] + [ROOT / name for name in
        ('visor-seguridad-riobamba-data.js', 'riobamba-camaras-inventario-data.js',
         'riobamba-camaras-data.js', 'riobamba-hotspot-urbano-200m-data.js',
         'riobamba-cantonal-data.js', 'riobamba-conflictividad-data.js',
         'riobamba-censo-data/riobamba_manzanas.geojson')]
    hashes = {str(path): sha(path) for path in protected}
    existing = pyogrio.read_dataframe(FINAL, layer='CAMARAS_EXISTENTES_103_FINAL')
    municipal = pyogrio.read_dataframe(FINAL, layer='PROPUESTA_MUNICIPAL_50_FINAL')
    police = pyogrio.read_dataframe(FINAL, layer='PROPUESTA_POLICIA_30_FINAL')
    assert [len(existing), len(municipal), len(police)] == [103, 50, 30]
    assert all(f.crs.to_epsg() == 32717 and f.geometry.is_valid.all()
               and f.geometry.notna().all() for f in (existing, municipal, police))
    replacements = existing.loc[existing.REQUIERE_CAMBIO == 1]
    assert len(replacements) == 31 and existing.geometry.to_wkb().nunique() == 100
    frames = {'REEMPLAZO_31': list(replacements.geometry), 'A': list(existing.geometry),
              'B': list(existing.geometry) + list(municipal.geometry),
              'C': list(existing.geometry) + list(municipal.geometry) + list(police.geometry)}
    original = load('riobamba-censo-data/riobamba_manzanas.geojson')['features']
    original_geoms = {f['properties']['man']: transform(PROJECT, shape(f['geometry'])) for f in original}
    if FIXED_INPUT.exists():
        fixed = json.loads(FIXED_INPUT.read_text(encoding='utf-8'))
        blocks = gpd.GeoDataFrame(fixed['rows'], geometry=[original_geoms[r['ID_MANZANA']] for r in fixed['rows']], crs=32717)
        method = fixed['method']
    else:
        blocks = pyogrio.read_dataframe(PREVIOUS, layer='MANZANAS_BRECHAS_COMPARADAS')
        method = load('data/seguridad-riobamba/propuesta-camaras-20261002/RESULTADOS.json')['metadata']['gapMethod']
    assert len(blocks) == len(original) and blocks.crs.to_epsg() == 32717
    assert all(g.equals(original_geoms[code]) for code, g in zip(blocks.ID_MANZANA, blocks.geometry))
    urban_gi = read_js('riobamba-hotspot-urbano-200m-data.js')
    indicators = {r['ID_MANZANA']: r for r in urban_gi['blockIndicators']}
    for row in blocks.itertuples():
        for name in ('HOTSPOT_DEL', 'HOTSPOT_VIOL', 'HOTSPOT_CONV'):
            assert clean(getattr(row, name)) == indicators[row.ID_MANZANA][name], (row.ID_MANZANA, name)
    platforms = {f['properties']['platform_name']: transform(PROJECT, shape(f['geometry']))
                 for f in load('riobamba-censo-data/riobamba_plataformas.geojson')['features']}
    urban = unary_union(list(platforms.values()))
    territory = read_js('riobamba-cantonal-data.js')
    canton = transform(PROJECT, shape(territory['canton']['geometry']))
    rural = canton.difference(urban)
    parishes = {f['properties']['name']: transform(PROJECT, shape(f['geometry'])).difference(urban)
                for f in territory['parishes']['features']}
    dictionary = read_js('riobamba-conflictividad-data.js')['dictionary']
    events = [(e['id'], Point(PROJECT(e['lng'], e['lat'])), dictionary[e['subtype']])
              for e in read_js('visor-seguridad-riobamba-data.js')['events']
              if e.get('mappable') and dictionary[e['subtype']] in
              ('DELINCUENCIA', 'VIOLENCIA', 'CONVIVENCIA') and urban.covers(Point(PROJECT(e['lng'], e['lat'])))]
    exposure = unary_union([p.buffer(250) for _, p, _ in events])
    block_tree = STRtree(list(blocks.geometry))
    urban_index = blocks.index[blocks.URBANA_OPERATIVA.astype(bool)]
    event_fields = ['N_DELINCUENCIA', 'N_VIOLENCIA', 'N_CONVIVENCIA']
    previous_urban_assignments = int(blocks.loc[urban_index, event_fields].sum().sum())
    blocks.loc[urban_index, event_fields] = 0
    strictly_assigned = 0
    for _, point, category in events:
        hits = block_tree.query(point, predicate='intersects')
        if len(hits):
            chosen = min(hits, key=lambda i: blocks.iloc[int(i)].ID_MANZANA)
            assert bool(blocks.iloc[int(chosen)].URBANA_OPERATIVA)
            blocks.loc[blocks.index[int(chosen)], 'N_' + category] += 1
            strictly_assigned += 1
    for index in urban_index:
        row = blocks.loc[index]
        rate = (row.N_DELINCUENCIA + row.N_VIOLENCIA) / row.POBLACION * 1000 if np.isfinite(row.POBLACION) and row.POBLACION > 0 else None
        problem, rule = problem_level(row.GI_DV_NIVEL, rate, method['incidenceP66'], row.HOTSPOT_CONV, row.N_CONVIVENCIA)
        blocks.loc[index, ['TASA_DV_1000', 'PROBLEMATICA', 'PROBLEMATICA_REGLA']] = [rate, problem, rule]
    assert int(blocks.loc[urban_index, event_fields].sum().sum()) == strictly_assigned
    cells = urban_gi['grid']['cells']
    cell_geoms = [transform(PROJECT, shape(c['geometry'])) for c in cells]
    cell_tree = STRtree(cell_geoms)
    cell_pop = np.zeros(len(cells))
    cell_parts = []
    block_parts = []
    population = read_js('riobamba-conflictividad-data.js')['derivedMethodology']['cameraScenarios']['150']['byPlatformName']
    for row in blocks.itertuples():
        geom = row.geometry
        part = geom.intersection(urban)
        local = [(name, geom.intersection(platform)) for name, platform in platforms.items() if geom.intersects(platform)]
        block_parts.append([(name, g) for name, g in local if g.area > .01])
        if not np.isfinite(row.POBLACION) or row.POBLACION <= 0:
            continue
        for i in cell_tree.query(part, predicate='intersects'):
            piece = part.intersection(cell_geoms[i])
            if piece.area > .01:
                factor = row.POBLACION / geom.area
                cell_pop[i] += piece.area * factor
                cell_parts.append((int(i), piece, factor))
    OUT.mkdir(exist_ok=True)
    scenarios, inventory_scenarios, replacement_scenarios = {}, {}, {}
    clips = {'inventory': {}, 'municipal': {}}
    output_fields = ['ID_MANZANA', 'POBLACION', 'PLATAFORMA', 'URBANA_OPERATIVA',
        'POBLACION_NIVEL', 'PROBLEMATICA', 'PROBLEMATICA_REGLA', 'TASA_DV_1000',
        'HOTSPOT_DEL', 'HOTSPOT_VIOL', 'HOTSPOT_CONV', 'GI_DV_NIVEL',
        'N_DELINCUENCIA', 'N_VIOLENCIA', 'N_CONVIVENCIA', 'ESTADO_METODOLOGIA']
    export = blocks[output_fields + ['geometry']].copy()
    if not FIXED_INPUT.exists():
        FIXED_INPUT.write_text(json.dumps(clean({'method': method, 'rows': export.drop(columns='geometry').to_dict(orient='records'),
            'sourceSha256': sha(PREVIOUS), 'assignment': 'INTERSECCION ESTRICTA'}), ensure_ascii=False, allow_nan=False), encoding='utf-8')
    comparisons, masks = [], {}
    for radius in (100, 150, 200):
        scenarios[str(radius)] = {}
        for key, points in frames.items():
            mask = unary_union([p.buffer(radius, quad_segs=64) for p in {p.wkb: p for p in points}.values()])
            masks[(key, radius)] = mask
            assert mask.is_valid
            rows = {name: {'platformName': name, 'platform': name.replace('PLATAFORMA ', ''),
                'population': population[name]['population'], 'coveredPopulation': 0., 'partialPopulation': 0.,
                'areaKm2': g.area / 1e6, 'coveredAreaKm2': g.intersection(mask).area / 1e6,
                'cameras': sum(g.covers(p) for p in points), 'coveredManzanas': 0,
                'partialManzanas': 0, 'uncoveredManzanas': 0, 'exposedUncoveredPopulation250': 0.}
                for name, g in platforms.items()}
            fractions, classification, gap_counts = {}, {}, Counter()
            clip_features = []
            for index, row in enumerate(blocks.itertuples()):
                covered = row.geometry.intersection(mask)
                fraction = min(1., max(0., covered.area / row.geometry.area))
                code = row.ID_MANZANA
                fractions[code] = fraction
                p_level = row.POBLACION_NIVEL if row.POBLACION_NIVEL else None
                problem = row.PROBLEMATICA if row.PROBLEMATICA else None
                level, rule = classify(fraction * 100 if row.URBANA_OPERATIVA else None,
                    p_level, problem, method['coverageLow'], method['coverageHigh'])
                classification[code] = {'coveragePct': fraction * 100, 'level': level, 'rule': rule,
                    'population': clean(row.POBLACION), 'populationLevel': p_level,
                    'problem': problem, 'hotspotDel': clean(row.HOTSPOT_DEL),
                    'hotspotViol': clean(row.HOTSPOT_VIOL), 'hotspotConv': clean(row.HOTSPOT_CONV),
                    'platformName': row.PLATAFORMA, 'urban': bool(row.URBANA_OPERATIVA)}
                if row.URBANA_OPERATIVA:
                    gap_counts[level] += 1
                if key in ('A', 'B', 'C'):
                    export.loc[index, f'COB_{key}_{radius}'] = fraction * 100
                    export.loc[index, f'BRECHA_{key}_{radius}'] = level
                    export.loc[index, f'REGLA_{key}_{radius}'] = rule
                if key in ('A', 'REEMPLAZO_31') and covered.area > .01:
                    clip_features.append(feature(covered, {'man': code, 'block_area_m2': row.geometry.area, 'covered_area_m2': covered.area}))
                for name, part in block_parts[index]:
                    local_area = part.intersection(mask).area
                    target = rows[name]
                    if local_area >= part.area * .999999:
                        target['coveredManzanas'] += 1
                    elif local_area > .01:
                        target['partialManzanas'] += 1
                    else:
                        target['uncoveredManzanas'] += 1
                    if np.isfinite(row.POBLACION):
                        factor = row.POBLACION / row.geometry.area
                        target['coveredPopulation'] += local_area * factor
                        if 0 < local_area < part.area * .999999:
                            target['partialPopulation'] += part.area * factor
                        target['exposedUncoveredPopulation250'] += part.intersection(exposure).difference(mask).area * factor
            for row in rows.values():
                row['coveredPopulation'] = min(row['population'], round(row['coveredPopulation']))
                row['uncoveredPopulation'] = row['population'] - row['coveredPopulation']
                row['coveredPct'] = row['coveredPopulation'] / row['population'] * 100 if row['population'] else None
                row['uncoveredPct'] = 100 - row['coveredPct'] if row['coveredPct'] is not None else None
                row['coveredAreaPct'] = row['coveredAreaKm2'] / row['areaKm2'] * 100
            result = {'byMan': classification, 'byPlatformName': rows,
                'gapCounts': {level: gap_counts[level] for level in LEVELS}, 'cameraRecords': len(points)}
            scenarios[str(radius)][key] = result
            comparisons.append({'radius': radius, 'scenario': key, 'cameras': len(points), **result['gapCounts']})
            if key in ('A', 'REEMPLAZO_31'):
                uncovered = np.zeros(len(cells))
                for i, part, factor in cell_parts:
                    uncovered[i] += part.difference(mask).area * factor
                def territorial(g):
                    return {'areaKm2': g.area / 1e6, 'coveredAreaKm2': g.intersection(mask).area / 1e6,
                        'cameras': sum(g.covers(p) for p in points), 'population': None, 'coveredPopulation': None}
                coverage = {'byPlatformName': rows, 'byMan': fractions,
                    'byCell': {c['cellId']: {'coveredPct': g.intersection(mask).area / g.area * 100,
                        'population': float(cell_pop[i]), 'uncoveredPopulation': float(uncovered[i])}
                        for i, (c, g) in enumerate(zip(cells, cell_geoms))},
                    'totalAreaKm2': urban.area / 1e6, 'totalCoveredAreaKm2': urban.intersection(mask).area / 1e6,
                    'totalManzanas': int(blocks.URBANA_OPERATIVA.sum()),
                    'coveredManzanas': sum(r['urban'] and r['coveragePct'] > 1e-6 for r in classification.values()),
                    'incidentIdsCovered': [code for code, point, _ in events if mask.covers(point)],
                    'coverage': feature(mask, {'radius_m': radius, 'cameras_total': len(points), 'crs_calculation': 'EPSG:32717'}),
                    'uncovered': feature(urban.difference(mask), {'radius_m': radius}),
                    'fullDissolvedAreaKm2': mask.area / 1e6, 'cantonal': territorial(canton), 'rural': territorial(rural),
                    'byParish': {name: territorial(g) for name, g in parishes.items()}}
                (inventory_scenarios if key == 'A' else replacement_scenarios)[str(radius)] = coverage
                clips['inventory' if key == 'A' else 'municipal'][str(radius)] = {'type': 'FeatureCollection', 'features': clip_features}
            print(json.dumps(comparisons[-1]), flush=True)
    for radius in (100, 150, 200):
        for first, second in (('A', 'B'), ('B', 'C')):
            assert masks[(first, radius)].difference(masks[(second, radius)]).area < .001
        for code in scenarios[str(radius)]['A']['byMan']:
            levels = [scenarios[str(radius)][key]['byMan'][code]['level'] for key in ('A', 'B', 'C')]
            rank = {'SIN EVIDENCIA': -1, 'BAJA': 0, 'MEDIA': 1, 'ALTA': 2}
            assert rank[levels[0]] >= rank[levels[1]] >= rank[levels[2]], (code, levels)
        export[f'COB_{radius}'] = export[f'COB_A_{radius}']
        export[f'BRECHA_{radius}'] = export[f'BRECHA_A_{radius}']
    inventory = read_js('riobamba-camaras-inventario-data.js')
    final_by_id = existing.set_index('ID_CAMARA')
    camera_overlay = []
    for camera in inventory['cameras']:
        row = final_by_id.loc[camera['id']]
        lng, lat = UNPROJECT(row.geometry.x, row.geometry.y)
        camera_overlay.append({**camera, 'lng': lng, 'lat': lat, 'mappable': True,
            'method': row.METODO_GEO, 'confidence': row.CONFIANZA_GEO, 'geoObservation': row.OBSERVACION_GEO,
            'coordinateSource': 'CAMARAS_EXISTENTES_103_FINAL; originales conservados'})
    metadata = {'generatedAt': datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'),
        'crs': 'EPSG:32717', 'inventoried': 103, 'located': 103, 'uniqueSites': 100,
        'municipalProposals': 50, 'policeProposals': 30, 'radii': [100, 150, 200],
        'method': method, 'sourceHashes': hashes, 'urbanHotspotCellM': 100, 'urbanHotspotDistanceM': 200,
        'blockIncidentScopeAudit': {'previousUrbanBlockCount': previous_urban_assignments, 'urbanStrictlyAssigned': strictly_assigned,
            'rule': 'Solo eventos dentro del ambito urbano operativo. Empates de interseccion: menor ID_MANZANA; sin proximidad. Los atributos rurales no se modifican.'},
        'eventAssignment': f'INTERSECCION ESTRICTA; {strictly_assigned} asignados, {len(events) - strictly_assigned} sin asignar de {len(events)} urbanos. Sin nearest-neighbor.',
        'limitations': 'Brechas provisionales por reglas operativas; incidentes en calles sin asociacion aprobada. No peligrosidad, AHP ni indice universal.'}
    result = {'metadata': metadata, 'scenarios': scenarios, 'replacementScenarios': replacement_scenarios,
        'inventoryCoverage': {'metadata': {'generatedAt': metadata['generatedAt'], 'totalRecords': 103,
            'locatedRecords': 103, 'pendingRecords': [], 'locatedIds': list(existing.ID_CAMARA),
            'cameraIds': list(existing.ID_CAMARA), 'crs': 'EPSG:32717', 'uniqueSites': 100}, 'scenarios': inventory_scenarios},
        'inventoryCameraOverlay': camera_overlay, 'censusClips': clips}
    result = clean(result)
    package = OUT / 'BRECHAS_ACTUALIZADAS.gpkg'
    pyogrio.write_dataframe(export, package, layer='BRECHAS_POR_MANZANA')
    export.drop(columns='geometry').to_csv(OUT / 'BRECHAS_POR_MANZANA.csv', index=False, encoding='utf-8-sig')
    with (OUT / 'COMPARACION_ESCENARIOS.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, list(comparisons[0])); writer.writeheader(); writer.writerows(comparisons)
    (OUT / 'RESULTADOS.json').write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf-8')
    (ROOT / 'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = ' + json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + ';\n', encoding='utf-8')
    assert all(sha(Path(path)) == value for path, value in hashes.items())
    validation = {'passed': True, 'sourceGeometriesUnchanged': True, 'giUnchanged': True,
        'strictIntersectionPreserved': True, 'populationAndProblematicLevelsFrozen': True,
        'counts': comparisons, 'populationP33': method['populationP33'], 'populationP66': method['populationP66'],
        'incidenceP33': method['incidenceP33'], 'incidenceP66': method['incidenceP66']}
    (OUT / 'VALIDACION.json').write_text(json.dumps(validation, indent=2, ensure_ascii=False), encoding='utf-8')
    documentation = '\n'.join(['# Brechas de cobertura y prioridad territorial', '',
        'Recalculo con camaras del cierre final, sin reoptimizar 50 municipales ni 30 policiales.',
        'Escenarios A=103, B=153, C=183; REEMPLAZO_31 conserva el objeto de estudio original.',
        '103 equipos existentes en 100 emplazamientos; los equipos coincidentes se conservan y la union evita doble conteo.',
        'EPSG:32717; radios 100/150/200 m, buffer quad_segs=64 y union disuelta antes de intersectar.',
        'COB = porcentaje de area completa de la manzana: baja <33%, parcial 33-66%, buena >66%.',
        f'P33 poblacion={method["populationP33"]}; P66={method["populationP66"]}; incidencia P33={method["incidenceP33"]}; P66={method["incidenceP66"]}. Valores y problematicas congelados entre escenarios/radios.',
        'Problematica ALTA: Hot Spot D/V95% o99%; MEDIA: D/V90% o tasa D/V superior a P66 sin Hot Spot>=95%. Convivencia>=95% con eventos observados en la manzana puede aportar MEDIA, nunca ALTA por si sola. BAJA: otras situaciones con datos validos.',
        'Brecha ALTA: cobertura baja + poblacion media/alta + problematica alta.',
        'Brecha MEDIA: cobertura baja + poblacion media/alta + problematica media, o cobertura parcial + poblacion media/alta + problematica alta.',
        'Brecha BAJA: otras situaciones evaluadas. SIN EVIDENCIA: falta poblacion, cobertura o problematica. Sin score, AHP ni ponderaciones.',
        'Gi* urbano conservado: celdas100m/distancia200m; Gi* rural intacto. No se mezclan categorias.',
        metadata['eventAssignment'] + ' Los no asignados NO se usan para clasificar manzanas; si conservan su uso original en Gi* y cobertura puntual.',
        'Brechas provisionales: P66 de incidencia0 refleja atribucion incompleta, no ausencia de problematica.',
        'Esta clasificacion constituye una herramienta operativa de priorizacion territorial para el presente estudio. No representa por si sola una medida de peligrosidad, riesgo delictivo ni una metodologia universal de brecha de videovigilancia.',
        'BRECHAS_ACTUALIZADAS.gpkg, capa BRECHAS_POR_MANZANA, y CSV: geometrias originales y campos COB_A/B/C_100/150/200, BRECHA_A/B/C_100/150/200, REGLA y alias COB_100/150/200,BRECHA_100/150/200 del escenario A.',
        'INSUMOS_FIJOS_BRECHAS.json: atributos y percentiles congelados para reproducir con geometrias censales originales. Ejecutar tools/recalculate_current_gaps.py con GeoPandas, Pyogrio, Shapely2 y PyProj.',
        'RESULTADOS.json: fuentes SHA256, coberturas, estadisticas, reglas, clips visuales y datos del visor. VALIDACION.json y COMPARACION_ESCENARIOS.csv: controles y conteos.', ''])
    (OUT / 'METODOLOGIA_BRECHAS.md').write_text(documentation, encoding='utf-8')
    with zipfile.ZipFile(BASE / 'BRECHAS_ACTUALIZADAS_20261004.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in OUT.iterdir():
            if path.is_file(): archive.write(path, OUT.name + '/' + path.name)
    print(json.dumps({'passed': True, 'counts': comparisons, 'sourceHashesUnchanged': True}), flush=True)


if __name__ == '__main__':
    main()
