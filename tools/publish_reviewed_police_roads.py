"""Build the explicitly approved 30-point road review; never optimize or push."""
import csv
import json
import shutil
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely import covers, points, force_2d
from shapely.geometry import Point

from review_police_verified_main_roads import (
    ROOT, OUT as REVIEW, ROADS, normalized, named, separated, PRINCIPAL,
)
from review_police_kde_intersections import grid_data, kde, covered_kde, parts
from review_pol05_roma_viena import shared_intersection
import recalculate_current_gaps as dependencies

sys.path.insert(0, str(ROOT / 'sig-bridge'))
from bridge.store import Store, digest, require, read_json, write_json, now, clean
from bridge.engine import calculate, verify_derived, save_layer

RELEASE_ID = 'POLICIA_30_EJES_AJUSTES_20261015'
DESTINATION = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE_ID
BASE = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/INVENTARIO_103_30_20261015'
AUTHORIZATION = 'Las 30 del estudio, con los ajustes'


def normalize_final():
    """Retire selection-era attributes and synchronize every final download."""
    import pandas as pd
    import pyogrio
    from shapely.ops import unary_union
    package = DESTINATION / 'ESCENARIO_FINAL_183.gpkg'
    results = read_json(DESTINATION / 'RESULTADOS.json')
    police = gpd.read_file(package, layer='PROPUESTA_POLICIA_30_FINAL')
    platforms = gpd.read_file(package, layer='PLATAFORMAS_TERRITORIALES')
    existing = gpd.read_file(package, layer='CAMARAS_EXISTENTES_103_FINAL')
    municipal = gpd.read_file(package, layer='PROPUESTA_MUNICIPAL_50_FINAL')
    events = gpd.read_file(package, layer='INCIDENTES_CLASIFICADOS')
    old = gpd.read_file(BASE / 'ESCENARIO_FINAL_183.gpkg', layer='PROPUESTA_POLICIA_30_FINAL').set_index('ID_POLICIA')
    base_mask = gpd.read_file(package, layer='COBERTURA_B').geometry.iloc[0]
    output_rows = []
    for row in police.itertuples():
        p, geom = row._asdict(), row.geometry
        p.pop('geometry'); p.pop('Index', None)
        before = old.loc[row.ID_POLICIA].geometry
        p.update({'X_ANTES': before.x, 'Y_ANTES': before.y, 'X_DESPUES': geom.x, 'Y_DESPUES': geom.y,
            'DESPLAZAMIENTO_M': before.distance(geom), 'DECISION': 'REUBICAR',
            'DECISION_FINAL': 'ESTUDIO_Y_AJUSTES_APROBADOS', 'FUENTE_VIAL': ROADS.name,
            'SOLAPE_PCT': p['SOLAPE_PREVIO_PCT'], 'DIST_EXISTENTE_M': p['DIST_EXISTENTE'],
            'DIST_MUNICIPAL_M': p['DIST_MUNICIPAL'],
            'PLATAFORMA': '|'.join(platforms.loc[platforms.geometry.covers(geom), 'platform_name'].astype(str)) or None,
            'CRITERIO': 'Estudio KDE D+V aprobado; Gi* referencia; ajustes de nodo solicitados',
            'JUSTIFICACION': 'Estudio de 30 aprobado por el usuario. Cruce: '+p['INTERSECCION_O_NODO']+'. '
                +str(p.get('OBSERVACION_MANUAL') or '')})
        for key in ('NIVEL_DEL_RESIDUAL', 'NIVEL_VIOL_RESIDUAL', 'NIVEL_DV_RESIDUAL',
                    'AREA_HOTSPOT_D_NUEVA_M2', 'AREA_HOTSPOT_V_NUEVA_M2', 'COINCIDENCIA_DV_RESIDUAL_M2',
                    'SOLAPE_DURANTE_SELECCION_PCT'):
            p[key] = None
        p['ESTADO_HOTSPOT_DV_PREVIO'] = 'METRICA_DE_SELECCION_HISTORICA_NO_REUTILIZADA'
        others = unary_union([base_mask, *[q.buffer(200, quad_segs=64) for q in
            police.loc[~police.ID_POLICIA.eq(row.ID_POLICIA)].geometry]])
        disk = geom.buffer(200, quad_segs=64)
        p['EVENTOS_C_NUEVOS'] = int((~covers(others, events.geometry.values) & covers(disk, events.geometry.values)
            & events.CATEGORIA.eq('CONVIVENCIA').values & events.AMBITO.ne('EXTERNO_CANTON').values).sum())
        output_rows.append((geom, clean(p)))
    save_layer(package, 'PROPUESTA_POLICIA_30_FINAL', output_rows, DESTINATION)
    results['policeMetrics'] = [p for _, p in output_rows]
    pd.DataFrame(results['policeMetrics']).to_csv(DESTINATION / 'POLICIA_BENEFICIO_FINAL.csv', index=False, encoding='utf-8-sig')
    pyogrio.write_dataframe(pd.DataFrame(results['policeMetrics']), package, layer='POLICIA_BENEFICIO_FINAL')
    records = lambda f: [(r.geometry, clean({k:v for k,v in r._asdict().items() if k not in ('Index','geometry')})) for r in f.itertuples()]
    save_layer(package, 'ESCENARIO_FINAL_183',
        [(g, {**p, 'ID_EQUIPO':p['ID_CAMARA'], 'GRUPO_ESCENARIO':'EXISTENTE'}) for g,p in records(existing)]
        + [(g, {**p, 'ID_EQUIPO':p['ID_PROPUESTA'], 'GRUPO_ESCENARIO':'MUNICIPAL_PROPUESTA'}) for g,p in records(municipal)]
        + [(g, {**p, 'ID_EQUIPO':p['ID_POLICIA'], 'GRUPO_ESCENARIO':'POLICIA_PROPUESTA'}) for g,p in output_rows])
    write_json(DESTINATION / 'RESULTADOS.json', results)
    folder = DESTINATION / 'coverage-inputs'
    gaps = read_json(folder / 'RESULTADOS.json')
    gaps['metadata']['sourceHashes'][str(package)] = digest(package)
    text = json.dumps(gaps, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    (folder / 'RESULTADOS.json').write_text(text, encoding='utf-8')
    (DESTINATION / 'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = '+text+';\n', encoding='utf-8')
    refresh_archives()


def refresh_archives():
    for folder, name in ((DESTINATION / 'coverage-inputs', 'BRECHAS_ACTUALIZADAS.zip'), (DESTINATION, 'ENTREGA_POLICIA_KDE.zip')):
        with zipfile.ZipFile(folder / name, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.iterdir()):
                if path.is_file() and path.suffix != '.zip': archive.write(path, path.name)


def targets():
    frame = gpd.read_file(REVIEW / 'REVISION_POLICIA_30.gpkg').to_crs(32717)
    approved = {'POL-05': REVIEW / 'POL05_ROMA_VIENA/RESULTADOS.json',
                'POL-17': REVIEW / 'POL17_NODO_PROANO_CANONIGO/RESULTADOS.json'}
    for camera, source in approved.items():
        report = read_json(source)
        props = report['camera'] if camera == 'POL-05' else report
        x, y = (props['X'], props['Y']) if camera == 'POL-05' else (props['x'], props['y'])
        frame.loc[frame.ID_POLICIA.eq(camera), 'geometry'] = Point(x, y)
    require(len(frame) == 30 and frame.ID_POLICIA.is_unique and frame.geometry.to_wkb().nunique() == 30,
            'Las 30 ubicaciones deben ser unicas')
    return frame


def road_validator(roads):
    nodes = {}
    for row in roads.itertuples():
        for line in parts(force_2d(row.geometry)):
            coordinates = [tuple(c[:2]) for c in line.coords]
            for i, xy in enumerate(coordinates):
                node = nodes.setdefault(xy, {'arms': set(), 'ways': {}, 'separated': False})
                node['ways'][str(row.osm_id)] = {'name': named(row.name), 'highway': row.highway}
                node['separated'] |= separated(row.bridge) or separated(row.tunnel)
                node['arms'].update(coordinates[j] for j in (i-1, i+1) if 0 <= j < len(coordinates))
    requested_05, _ = shared_intersection(roads)

    def validate(store, changes, municipal, police, urban):
        require({r['layer'] for r in changes} == {'police'}, 'Solo se autoriza mover Policia')
        audit, failures = [], []
        for point, props in police:
            camera = props['ID_POLICIA']
            node = nodes.get((point.x, point.y))
            require(node is not None, 'No es un vertice vial original: ' + camera)
            names = sorted({w['name'] for w in node['ways'].values() if w['name']})
            principal = any(w['highway'] in PRINCIPAL and w['name'] for w in node['ways'].values())
            explicit_05 = camera == 'POL-05' and point.equals(requested_05)
            passed = (len(node['arms']) >= 3 and len({normalized(n) for n in names}) >= 2
                      and not node['separated'] and urban.covers(point) and (principal or explicit_05))
            audit.append({'id': camera, 'nodeDistanceM': 0, 'degree': len(node['arms']),
                'principalRoad': principal, 'urban': bool(urban.covers(point)), 'roads': names,
                'source': ROADS.name, 'osmIds': sorted(node['ways']), 'passed': bool(passed),
                'explicitRequestedLocalJunction': explicit_05 and not principal})
            if not passed:
                failures.append('Cruce original no validado: ' + camera)
            historical = {k: props.get(k) for k in ('ID_CANDIDATO', 'ORDEN_KDE', 'ORDEN_KDE_SELECCION',
                'MASA_KDE_DV_NUEVA_SELECCION', 'SOLAPE_ANTES_KDE_PCT') if k in props}
            for field in historical:
                props[field] = None
            junction = ' x '.join(names)
            props.update({'DIRECCION': junction, 'INTERSECCION_O_NODO': junction,
                'GRADO_NODO': len(node['arms']), 'DISTANCIA_NODO_M': 0,
                'TIPO_VIA_PRINCIPAL': '|'.join(sorted({w['highway'] for w in node['ways'].values()})),
                'FUENTE_CRUCE': ROADS.name, 'OSM_IDS': '|'.join(sorted(node['ways'])),
                'METODO_GEO': 'VERTICE_COMPARTIDO_RED_VIAL_ORIGINAL',
                'JERARQUIA_OSM_PRINCIPAL': principal, 'CRUCE_LOCAL_SOLICITADO': explicit_05 and not principal,
                'BRIDGE_NODO_VALIDADO': bool(passed), 'RADIO_POTENCIAL_M': 200,
                'ESTADO': 'PROPUESTA_REVISADA_NO_INSTALADA',
                'CRITERIO_UBICACION': 'KDE D+V principal; Gi* referencia; ajustes de nodo solicitados por usuario',
                'ALCANCE_VISUAL': 'Solo en direccion de vias; orientacion, obstaculos y visibilidad pendientes de campo',
                'COBERTURA_VISUAL_CERTIFICADA': False,
                'SELECCION_PREVIA_HISTORICA': json.dumps(clean(historical), ensure_ascii=False),
                'OBSERVACION_MANUAL': ('Cruce Roma x Viena solicitado; OSM residencial, jerarquia municipal discrepante. '
                    if explicit_05 else 'Cruce de eje principal comprobado en red OSM local. ')
                    + 'Radios potenciales, no vision a traves de manzanas; no certifica continuidad visual.'})
        return audit, failures
    return validate


def evaluate_kde(package, before_mask, after_mask):
    grid = grid_data()
    events = gpd.read_file(package, layer='INCIDENTES_CLASIFICADOS')
    densities = {}
    for category in ('DELINCUENCIA', 'VIOLENCIA'):
        selected = events.loc[events.AMBITO.eq('URBANO') & events.CATEGORIA.eq(category)].geometry
        density, mask, west, north, size = kde([(p.x, p.y) for p in selected], grid, 200)
        densities[category] = density
    indices = np.flatnonzero(mask)
    ys, xs = np.divmod(indices, grid['width'])
    cells = points(west + (xs + .5)*size, north - (ys + .5)*size)
    return {'methodUnchanged': True, 'bandwidthM': 200, 'cellM': size,
            'before': covered_kde(before_mask, cells, indices, mask, densities),
            'after': covered_kde(after_mask, cells, indices, mask, densities),
            'note': 'Evaluacion sobre el mismo KDE; no cambia fuente, parametros ni superficie oficial.'}


def main():
    require(not DESTINATION.exists(), 'La version ya existe; no se sobrescribe')
    store = Store()
    require(store.base == BASE / 'ESCENARIO_FINAL_183.gpkg', 'La base activa cambio; revisar antes de calcular')
    approved = targets()
    sources = [store.base, REVIEW / 'REVISION_POLICIA_30.gpkg',
               REVIEW / 'POL05_ROMA_VIENA/RESULTADOS.json', REVIEW / 'POL17_NODO_PROANO_CANONIGO/RESULTADOS.json']
    sources += [ROOT / name for name in ('riobamba-hotspot-urbano-200m-data.js', 'riobamba-conflictividad-data.js',
        'riobamba-seguridad-kde-validacion-data.js', 'riobamba-incidentes-spatial-data.js', 'riobamba-cantonal-data.js')]
    sources += [p for p in ROADS.parent.glob(ROADS.stem + '.*') if p.is_file()]
    hashes = {str(p): digest(p) for p in sources}
    roads = gpd.read_file(ROADS).to_crs(32717)
    manual, changes = {}, []
    for key, spec in store.config['layers'].items():
        frame = gpd.read_file(store.base, layer=spec['source'])
        frame['OBSERVACION_MANUAL'] = ''
        if key == 'police':
            for index, row in frame.iterrows():
                target = approved.loc[approved.ID_POLICIA.eq(row.ID_POLICIA)].geometry.iloc[0]
                changes.append({'layer': 'police', 'id': row.ID_POLICIA, 'geometryChanged': not row.geometry.equals(target),
                    'fields': [], 'distanceM': row.geometry.distance(target),
                    'note': 'Estudio de 30 aprobado, con ajustes Roma/Viena y Proano/Canonigo Ramos'})
                frame.at[index, 'geometry'] = target
        manual[key] = frame
    receipt = {'revision': RELEASE_ID, 'changes': changes, 'baseHashes': hashes,
               'createdAt': now(), 'authorization': AUTHORIZATION}
    DESTINATION.mkdir(parents=True)
    print('Calculando escenarios con las 30 ubicaciones aprobadas', flush=True)
    validation = calculate(store, DESTINATION, DESTINATION, manual, receipt,
                           node_validator=road_validator(roads))
    package = DESTINATION / 'ESCENARIO_FINAL_183.gpkg'
    prior = read_json(BASE / 'RESULTADOS.json')
    results = read_json(DESTINATION / 'RESULTADOS.json')
    # The municipal scenario is unchanged, so its existing approved exception is inherited exactly.
    for code in ('A', 'B'):
        previous = gpd.read_file(store.base, layer='COBERTURA_'+code).geometry.iloc[0]
        current = gpd.read_file(package, layer='COBERTURA_'+code).geometry.iloc[0]
        require(previous.equals(current), 'No debe cambiar el escenario ' + code)
    inherited = read_json(BASE / 'VALIDACION.json')['approvedException']
    ring = next(r for r in results['corridors'] if r['ESCENARIO'] == 'B' and r['CORREDOR'] == 'ANILLO_VIAL')
    require(abs(ring['PCT_CUBIERTO'] - inherited['observedPct']) < 1e-8, 'La excepcion anterior no aplica a un resultado distinto')
    approved_blocks = [s for s in validation['publishBlocks'] if s.startswith('Restriccion municipal ANILLO_VIAL:')]
    validation['publishBlocks'] = [s for s in validation['publishBlocks'] if s not in approved_blocks]
    require(not validation['publishBlocks'], 'Bloqueos no autorizados: '+str(validation['publishBlocks']))
    validation.update({'status': 'PASS_WITH_APPROVED_EXCEPTION', 'approvedException': inherited,
        'authorization': AUTHORIZATION, 'confirmedReplacement': 30, 'sourceHashes': hashes,
        'sourceGeometryPreserved': True, 'radiiM': [100,150,200], 'originalsUnmodified': True,
        'approvedLocalJunction': 'POL-05 Roma x Viena; no se presenta como principal OSM'})
    print('Actualizando dependencias de 100/150/200 m y clips censales', flush=True)
    coverage_directory = DESTINATION / 'coverage-inputs'
    coverage_directory.mkdir()
    dependencies.main(final=package, out=coverage_directory,
        js_output=DESTINATION / 'riobamba-brechas-actualizadas-data.js', expected_replacements=30)
    gaps = read_json(coverage_directory / 'RESULTADOS.json')
    previous_gaps = read_json(BASE / 'coverage-inputs/RESULTADOS.json')
    gaps['metadata']['sourceInventory'] = previous_gaps['metadata']['sourceInventory']
    # Preserve the already validated identity/institution metadata of the fixed inventory.
    gaps['inventoryCameraOverlay'] = previous_gaps['inventoryCameraOverlay']
    text = json.dumps(gaps, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    (coverage_directory / 'RESULTADOS.json').write_text(text, encoding='utf-8')
    (DESTINATION / 'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = '+text+';\n', encoding='utf-8')
    before_mask = gpd.read_file(store.base, layer='COBERTURA_C').geometry.iloc[0]
    after_mask = gpd.read_file(package, layer='COBERTURA_C').geometry.iloc[0]
    results.update({'status': 'POLICIA_30_EJES_AJUSTES_APROBADOS', 'sourcePackage': RELEASE_ID,
        'counts': {'existing':103, 'changeIncluded':30, 'municipal':50, 'police':30},
        'bridge': validation, 'authorization': AUTHORIZATION, 'gapScenarioCValidated': True,
        'kdeEvaluation': evaluate_kde(package, before_mask, after_mask),
        'warnings': [
            '11 esquinas existentes estimadas no verificadas, conservadas sin mover.',
            'Las 30 policiales son propuestas, no instaladas; KDE principal y Gi* de referencia sin recalcular.',
            'POL-05 Roma/Viena es un cruce local solicitado; jerarquia OSM residencial, clasificacion municipal discrepante.',
            'Radio 200 m es cobertura potencial; camaras ven hacia las vias, no a traves de manzanas. No se certifica linea de vista.',
            'POL-17 en Proano/Canonigo Ramos deja 12.95 m sin cobertura potencial respecto a POL-19 en el estudio; no se oculta el hueco.',
            'Los desplazamientos extensos y la perdida de eventos se conservan en la comparacion aprobada.',
        ]})
    corridor = read_json(DESTINATION / 'CORRIDOR_COVERAGE_200M.json')
    corridor['metadata']['sourcePackage'] = RELEASE_ID
    write_json(DESTINATION / 'CORRIDOR_COVERAGE_200M.json', corridor)
    write_json(DESTINATION / 'VALIDACION.json', validation)
    write_json(DESTINATION / 'RESULTADOS.json', results)
    write_json(DESTINATION / 'APROBACION_Y_FUENTES.json', receipt)
    write_json(DESTINATION / 'COMPARACION_COBERTURAS.json', {
        key: {'before': prior[key], 'after': results[key]}
        for key in ('territorial', 'population', 'incidents', 'hotspots', 'corridors')})
    with (DESTINATION / 'TRAZABILIDAD_POLICIA_FINAL.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        rows = [{**move, 'CRUCE_FINAL': next(n['roads'] for n in validation['nodeAudit'] if n['id'] == move['ID_POLICIA']),
                 'AUTORIZACION': AUTHORIZATION, 'FUENTE_VIAL': ROADS.name} for move in results['policeChanges']]
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    for name in ('HISTORIAL_30_CAMARAS.csv', 'HISTORIAL_COORDENADAS.geojson'):
        if (REVIEW / name).exists(): shutil.copy2(REVIEW / name, DESTINATION / ('HISTORICO_PREVIO_'+name))
    (DESTINATION / 'INFORME_FINAL.md').write_text(
        '# Propuesta policial: ejes viales y ajustes aprobados\n\n'
        'Se aplican las 30 ubicaciones del estudio, con POL-05 en Roma/Viena y POL-17 en Proano/Canonigo Ramos. '
        'Autorizacion expresa: "'+AUTHORIZATION+'". No hay nueva optimizacion.\n\n'
        '103 existentes (30 para cambio incluidas) y 50 municipales con geometrias fijas. Se mantienen 30 policiales. '
        'EPSG:32717, radios potenciales 200 m, quad_segs=64, union disuelta. Se actualizan dependencias de 100/150/200 m.\n\n'
        'Cada emplazamiento policial es un vertice vial original compartido, sin inventar coordenadas. '
        'POL-05 es el cruce local solicitado Roma/Viena: OSM residencial y jerarquia municipal discrepante, no se certifica como avenida. '
        'Los demas nodos corresponden a un eje OSM trunk/primary/secondary/tertiary.\n\n'
        'KDE D/V es el criterio principal del estudio; Gi* solo referencia. No se recalculan ni cambian estadisticos, celdas o significancias. '
        'Solo se actualizan coberturas. La comparacion conserva perdidas de eventos y grandes desplazamientos.\n\n'
        'Los buffers NO son campos visuales. Las camaras solo ven hacia las vias; orientacion, altura y obstaculos requieren comprobacion en campo. '
        'No se presupone visibilidad a traves de edificios ni alrededor de esquinas. POL-17/POL-19 conserva un hueco potencial de 12.95 m.\n\n'
        'APROBACION_Y_FUENTES.json conserva coordenadas fuente y hashes; TRAZABILIDAD_POLICIA_FINAL.csv enlaza coordenadas publicadas y finales por ID. '
        'Los archivos HISTORICO_PREVIO_* son snapshots anteriores, no las coordenadas finales. '
        'La geometria final esta en PROPUESTA_POLICIA_30_FINAL y ESCENARIO_FINAL_183.gpkg.\n', encoding='utf-8')
    require(all(digest(Path(p)) == h for p, h in hashes.items()), 'Una fuente cambio durante el calculo')
    verify_derived(store, package, results)
    normalize_final()
    print(json.dumps(clean({'release': RELEASE_ID, 'validation': validation,
        'incidents': [r for r in results['incidents'] if r['ESCENARIO']=='C' and r['AMBITO']=='URBANO'],
        'corridors': [r for r in results['corridors'] if r['ESCENARIO']=='C']}), ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
