"""Prepare the requested Roma/Viena alternative without modifying active cameras."""
import json
from pathlib import Path
import shutil

import geopandas as gpd
import numpy as np
from scipy.sparse.csgraph import dijkstra
from shapely import force_2d
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from add_police_history_continuity import road_graph
from review_police_verified_main_roads import OUT, PACKAGE, ROADS, ROOT, normalized
from review_police_kde_intersections import export_geojson, incident_counts, parts, source_hash


def shared_intersection(roads):
    streets = [roads.loc[roads['name'].map(normalized).eq(name)] for name in ('roma', 'viena')]
    vertices = [{tuple(c[:2]) for geometry in street.geometry for line in parts(force_2d(geometry))
                 for c in line.coords} for street in streets]
    shared = vertices[0] & vertices[1]
    if len(shared) != 1:
        raise ValueError(f'Cruce Roma/Viena no univoco: {len(shared)} vertices compartidos')
    point = Point(next(iter(shared)))
    assert streets[0].geometry.union_all().intersection(streets[1].geometry.union_all()).equals(point)
    return point, streets


def potential_street_segments(street, point):
    vertices, edges, graph = road_graph(street, street.geometry.union_all().buffer(201))
    source = vertices[(point.x, point.y)]
    distances = dijkstra(graph, directed=False, indices=source)
    result = []
    for (a, b), edge in edges.items():
        da, db = distances[a], distances[b]
        if min(da, db) >= 200:
            continue
        geometry = edge['geometry']
        if max(da, db) <= 200:
            result.append(geometry)
        else:
            coordinates = list(geometry.coords)
            if db < da:
                coordinates.reverse()
            oriented = LineString(coordinates)
            stop = oriented.interpolate(200 - min(da, db))
            result.append(LineString([coordinates[0], (stop.x, stop.y)]))
    return result


def main():
    destination = OUT / 'POL05_ROMA_VIENA'
    destination.mkdir(exist_ok=True)
    review_path = OUT / 'REVISION_POLICIA_30.gpkg'
    protected = [PACKAGE, review_path, ROOT / 'sig-bridge-active.json']
    protected += [p for p in ROADS.parent.glob(ROADS.stem + '.*') if p.is_file()]
    hashes = {str(p): source_hash(p) for p in protected}
    roads = gpd.read_file(ROADS).to_crs(32717)
    point, streets = shared_intersection(roads)
    read = lambda layer: gpd.read_file(PACKAGE, layer=layer).to_crs(32717)
    published = read('PROPUESTA_POLICIA_30_FINAL')
    study = gpd.read_file(review_path).to_crs(32717)
    fixed = list(read('CAMARAS_EXISTENTES_103_FINAL').geometry) + list(read('PROPUESTA_MUNICIPAL_50_FINAL').geometry)
    assert len(fixed) == 153 and len(published) == len(study) == 30
    published_old = published.loc[published.ID_POLICIA.eq('POL-05')].geometry.iloc[0]
    study_old = study.loc[study.ID_POLICIA.eq('POL-05')].geometry.iloc[0]
    assert read('PLATAFORMAS_TERRITORIALES').geometry.union_all().covers(point)
    arms, osm_ids = set(), set()
    for row in roads.itertuples():
        for line in parts(force_2d(row.geometry)):
            coordinates = [tuple(c[:2]) for c in line.coords]
            for i, xy in enumerate(coordinates):
                if xy != (point.x, point.y):
                    continue
                assert str(row.bridge).lower() in ('', 'nan', 'none', 'no', '0', 'false')
                assert str(row.tunnel).lower() in ('', 'nan', 'none', 'no', '0', 'false')
                osm_ids.add(str(row.osm_id))
                arms.update(coordinates[j] for j in (i-1, i+1) if 0 <= j < len(coordinates))
    assert len(arms) >= 3
    incidents = read('INCIDENTES_CLASIFICADOS')
    events = [(r.geometry, r.CATEGORIA) for r in incidents.loc[
        incidents.AMBITO.eq('URBANO') & incidents.CATEGORIA.isin(['DELINCUENCIA', 'VIOLENCIA'])].itertuples()]
    comparison = {}
    for name, frame in [('publicado', published), ('estudio_general', study)]:
        old = frame.loc[frame.ID_POLICIA.eq('POL-05')].geometry.iloc[0]
        common = unary_union([p.buffer(200, quad_segs=64) for p in fixed + list(
            frame.loc[~frame.ID_POLICIA.eq('POL-05')].geometry)])
        previous = unary_union([common, old.buffer(200, quad_segs=64)])
        proposed = unary_union([common, point.buffer(200, quad_segs=64)])
        comparison[name] = {
            'desplazamiento_m': old.distance(point),
            'eventos_en_buffers_antes': incident_counts(previous, events),
            'eventos_en_buffers_despues': incident_counts(proposed, events),
            'solape_con_otras_182_pct': 100 * point.buffer(200, quad_segs=64).intersection(common).area / point.buffer(200, quad_segs=64).area,
        }
    props = {
        'ID_POLICIA': 'POL-05', 'CRUCE': 'Roma x Viena', 'X': point.x, 'Y': point.y,
        'ESTADO': 'AJUSTE_SOLICITADO_PARA_REVISION_NO_APLICADO',
        'RADIO_POTENCIAL_M': 200, 'GRADO_NODO': len(arms), 'OSM_IDS': ' | '.join(sorted(osm_ids)),
        'JERARQUIA_OSM_ROMA': ' | '.join(sorted(set(streets[0].highway))),
        'JERARQUIA_OSM_VIENA': ' | '.join(sorted(set(streets[1].highway))),
        'VISIBILIDAD_CERTIFICADA': False,
    }
    export_geojson(destination / 'POL05_AJUSTE.geojson', [(point, props)])
    gpd.GeoDataFrame([props], geometry=[point], crs=32717).to_file(
        destination / 'POL05_AJUSTE.gpkg', layer='POL05_ROMA_VIENA', driver='GPKG', index=False)
    export_geojson(destination / 'POSICIONES_ANTERIORES.geojson', [
        (published_old, {'ESTADO': 'PUBLICADA'}), (study_old, {'ESTADO': 'ESTUDIO_ANTERIOR'})])
    segments = [(segment, {'VIA': name, 'ALCANCE_POR_RED_M': 200,
                'ESTADO': 'TRAMO_VIAL_POTENCIAL_NO_VISIBILIDAD_CERTIFICADA'})
                for street, name in zip(streets, ('Roma', 'Viena'))
                for segment in potential_street_segments(street, point)]
    assert segments and all(g.distance(point) <= 200.001 for g, _ in segments)
    export_geojson(destination / 'TRAMOS_POTENCIALES_ROMA_VIENA.geojson', segments)
    assert all(source_hash(Path(p)) == h for p, h in hashes.items())
    report = {'status': props['ESTADO'], 'applied': False, 'published': False,
        'crs_calculo': 'EPSG:32717', 'camera': props, 'comparison': comparison,
        'otherCamerasMoved': 0, 'sourcesUnchanged': True, 'sourceHashes': hashes,
        'limitations': [
            'Los conteos comparan buffers potenciales circulares, no visibilidad real por calles.',
            'Los tramos de Roma/Viena se muestran hasta 200 m por su propia red, sin girar hacia calles distintas. No certifican linea de vista.',
            'OSM clasifica ambas vias como residenciales. La capa municipal rotula tramos cercanos de Viena como Arterial B y Local; no se homologa automaticamente la jerarquia.',
            'Solo se estudia POL-05; no se aplican el estudio general ni los ajustes de otros IDs.',
        ]}
    (destination / 'RESULTADOS.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copyfile(Path(__file__).with_name('pol05_roma_viena_review.html'), destination / 'index.html')
    print(json.dumps({k: v for k, v in report.items() if k != 'sourceHashes'}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
