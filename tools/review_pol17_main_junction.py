"""Study the user-confirmed POL-17 junction without changing either scenario."""
import json
from pathlib import Path

import geopandas as gpd
from html import escape
import numpy as np
from scipy.sparse.csgraph import dijkstra
from shapely.ops import unary_union

from add_police_history_continuity import road_graph, reconstruct
from review_police_verified_main_roads import (
    OUT, PACKAGE, ROADS, ROOT, candidates_from_shared_vertices, normalized,
)
from review_police_kde_intersections import export_geojson, incident_counts, parts, source_hash


def main():
    destination = OUT / 'POL17_NODO_PROANO_CANONIGO'
    destination.mkdir(exist_ok=True)
    review_path = OUT / 'REVISION_POLICIA_30.gpkg'
    protected = [PACKAGE, review_path, ROOT / 'sig-bridge-active.json']
    protected += list(ROADS.parent.glob(ROADS.stem + '.*'))
    hashes = {str(p): source_hash(p) for p in protected if p.is_file()}
    read = lambda layer: gpd.read_file(PACKAGE, layer=layer).to_crs(32717)
    proposals = gpd.read_file(review_path).to_crs(32717)
    fixed = gpd.GeoDataFrame(geometry=list(read('CAMARAS_EXISTENTES_103_FINAL').geometry)
                            + list(read('PROPUESTA_MUNICIPAL_50_FINAL').geometry), crs=32717)
    published = read('PROPUESTA_POLICIA_30_FINAL')
    roads = gpd.read_file(ROADS).to_crs(32717)
    urban = read('PLATAFORMAS_TERRITORIALES').geometry.union_all()
    candidates = candidates_from_shared_vertices(roads, urban)
    by_id = {c['id']: c for c in candidates}
    # This original vertex keeps the same Proano carriageway as POL-19.
    candidate = by_id['OSM-CRUCE-00054']
    point = candidate['point']
    assert len(candidate['principal']) == 2 and candidate['degree'] >= 3
    old = proposals.loc[proposals.ID_POLICIA.eq('POL-17')].geometry.iloc[0]
    other = proposals.loc[proposals.ID_POLICIA.eq('POL-19')].geometry.iloc[0]
    public_old = published.loc[published.ID_POLICIA.eq('POL-17')].geometry.iloc[0]
    axis = roads.loc[roads['name'].map(normalized).eq(
        normalized('Avenida Monseñor Leonidas Proaño'))]
    vertices, edges, graph = road_graph(axis, axis.geometry.union_all().buffer(201))
    coordinates = [None] * len(vertices)
    for xy, index in vertices.items():
        coordinates[index] = xy
    source = vertices[(other.x, other.y)]
    distances, predecessors = dijkstra(graph, directed=False, indices=source, return_predecessors=True)
    common_points = list(fixed.geometry) + list(proposals.loc[~proposals.ID_POLICIA.eq('POL-17')].geometry)
    common = unary_union([p.buffer(200, quad_segs=64) for p in common_points])
    incidents = read('INCIDENTES_CLASIFICADOS')
    events = [(r.geometry, r.CATEGORIA) for r in incidents.loc[
        incidents.AMBITO.eq('URBANO') & incidents.CATEGORIA.isin(['DELINCUENCIA', 'VIOLENCIA'])].itertuples()]
    comparisons, routes, gaps = {}, {}, {}
    for key, camera in [('alternativa_anterior', old), ('nodo_confirmado', point)]:
        target = vertices[(camera.x, camera.y)]
        assert np.isfinite(distances[target])
        _, route = reconstruct(predecessors, source, target, coordinates)
        pair = unary_union([camera.buffer(200, quad_segs=64), other.buffer(200, quad_segs=64)])
        system = unary_union([common, camera.buffer(200, quad_segs=64)])
        gap = route.difference(pair)
        comparisons[key] = {
            'distancia_recta_pol19_m': camera.distance(other),
            'longitud_mismo_eje_proano_m': route.length,
            'hueco_solo_pol17_pol19_m': gap.length,
            'hueco_union_183_m': route.difference(system).length,
            'eventos_urbanos_cubiertos_sistema': incident_counts(system, events),
        }
        routes[key], gaps[key] = route, gap
    result = {
        'status': 'AJUSTE_PUNTUAL_PARA_REVISION_NO_APLICADO', 'applied': False, 'published': False,
        'id': 'POL-17', 'cruce': 'Avenida Monseñor Leonidas Proaño x Avenida Canónigo Ramos',
        'crs_calculo': 'EPSG:32717', 'radio_m': 200,
        'candidate': candidate['id'], 'osm_ids': candidate['osmIds'], 'brazos': candidate['degree'],
        'x': point.x, 'y': point.y, 'x_previo_estudio': old.x, 'y_previo_estudio': old.y,
        'desplazamiento_desde_estudio_m': old.distance(point),
        'desplazamiento_desde_publicado_m': public_old.distance(point),
        'comparison': comparisons,
        'otras_camaras_movidas': 0, 'coordenadas_fuente_originales': True,
        'linea_de_vista_verificada': False,
        'limitations': [
            'Mismo eje vial no equivale a visibilidad real: verificar postes, altura, orientacion y obstaculos en campo.',
            'La separacion cercana a 400 m es una referencia geometrica, no una regla automatica de seleccion.',
            'El apoyo de otros radios no prueba una cadena visual ni alineacion de sus emplazamientos.',
            'Este ajuste no aplica ni aprueba los restantes movimientos del estudio general.',
        ], 'sourceHashes': hashes,
    }
    assert all(source_hash(Path(p)) == h for p, h in hashes.items())
    result['sourcesUnchanged'] = True
    (destination / 'RESULTADOS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    export_geojson(destination / 'POL17_AJUSTE.geojson', [(point, {k: result[k] for k in
        ('id', 'cruce', 'candidate', 'x', 'y', 'radio_m', 'status')})])
    export_geojson(destination / 'CONTROL_CONTINUIDAD.geojson', [
        (routes[key], {'escenario': key, **comparisons[key]}) for key in routes])
    extent = (old.x - 530, point.x + 300, old.y - 310, point.y + 300)
    nearby = roads.cx[extent[0]:extent[1], extent[2]:extent[3]]
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">',
           '<rect width="1600" height="900" fill="#ffffff"/>',
           '<style>text{font-family:Arial,sans-serif;fill:#183c4a}</style>',
           '<text x="30" y="42" font-size="25" font-weight="bold">POL-17 | Cruce de las dos avenidas</text>',
           '<text x="30" y="73" font-size="17">AJUSTE PARA REVISION · NO APLICADO · NO PUBLICADO</text>']
    scale = 740 / (extent[1] - extent[0])
    for index, (key, camera, title) in enumerate(zip(comparisons, (old, point),
            ('Estudio anterior: Proano x Galapagos', 'Ajuste: Proano x Canonigo Ramos'))):
        left = 30 + index * 800
        def xy(x, y):
            return left + (x - extent[0]) * scale, 140 + (extent[3] - y) * scale
        def line(geometry, color, width):
            for segment in parts(geometry):
                points = ' '.join(f'{x:.2f},{y:.2f}' for x, y in (xy(*c[:2]) for c in segment.coords))
                svg.append(f'<polyline points="{points}" stroke="{color}" stroke-width="{width}" fill="none"/>')
        svg.append(f'<text x="{left}" y="117" font-size="20" font-weight="bold">{escape(title)}</text>')
        svg.append(f'<defs><clipPath id="panel{index}"><rect x="{left}" y="140" width="740" height="540"/></clipPath></defs>')
        svg.append(f'<g clip-path="url(#panel{index})"><rect x="{left}" y="140" width="740" height="540" fill="#f6f8f9"/>')
        for row in nearby.itertuples():
            major = row.highway in ['trunk', 'primary', 'secondary', 'tertiary']
            line(row.geometry, '#627b85' if major else '#c9d2d7', 2 if major else 1)
        for p in fixed.geometry:
            if extent[0] < p.x < extent[1] and extent[2] < p.y < extent[3]:
                x, y = xy(p.x, p.y)
                svg.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#246db5"/>')
        for p, label in [(other, 'POL-19'), (camera, 'POL-17')]:
            x, y = xy(p.x, p.y)
            svg.append(f'<circle cx="{x}" cy="{y}" r="{200 * scale}" fill="#e8bd16" fill-opacity=".16" stroke="#b8940d"/>')
        line(routes[key], '#087f8c', 4)
        if gaps[key].length > .001:
            line(gaps[key], '#bd0026', 7)
        for p, label in [(other, 'POL-19'), (camera, 'POL-17')]:
            x, y = xy(p.x, p.y)
            svg.append(f'<circle cx="{x}" cy="{y}" r="8" fill="#e8bd16" stroke="#153e50" stroke-width="2"/>')
            svg.append(f'<text x="{x}" y="{y - 17}" text-anchor="middle" font-size="17" font-weight="bold">{label}</text>')
        svg.append('</g>')
        stats = comparisons[key]
        for n, text in enumerate([
            f"Tramo por Proano: {stats['longitud_mismo_eje_proano_m']:.2f} m",
            f"Hueco del par: {stats['hueco_solo_pol17_pol19_m']:.2f} m",
            f"Hueco con 183 radios: {stats['hueco_union_183_m']:.2f} m",
        ]):
            svg.append(f'<text x="{left}" y="{718 + 28*n}" font-size="19">{escape(text)}</text>')
    svg += ['<text x="30" y="830" font-size="17">Amarillo: radios 200 m | Azul verdoso: mismo eje vial | Rojo: hueco entre el par</text>',
            '<text x="30" y="867" font-size="16">Cobertura potencial, no visibilidad certificada. Fuente: vertices originales de red OSM local. CRS: EPSG:32717.</text>', '</svg>']
    (destination / 'POL17_COMPARACION.svg').write_text('\n'.join(svg), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'sourceHashes'}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
