"""Independent GIS checks for the approved police road-node publication."""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.sparse.csgraph import dijkstra
from shapely import covers
from shapely.ops import unary_union

from publish_reviewed_police_roads import DESTINATION, BASE, targets, ROADS, normalized, refresh_archives
from add_police_history_continuity import road_graph, reconstruct
from review_police_kde_intersections import source_hash


def main():
    package = DESTINATION / 'ESCENARIO_FINAL_183.gpkg'
    read = lambda layer: gpd.read_file(package, layer=layer).to_crs(32717)
    old = lambda layer: gpd.read_file(BASE / 'ESCENARIO_FINAL_183.gpkg', layer=layer).to_crs(32717)
    existing, municipal, police = [read(n) for n in (
        'CAMARAS_EXISTENTES_103_FINAL', 'PROPUESTA_MUNICIPAL_50_FINAL', 'PROPUESTA_POLICIA_30_FINAL')]
    assert [len(existing), len(municipal), len(police)] == [103, 50, 30]
    assert existing.REQUIERE_CAMBIO.astype(bool).sum() == 30
    for name, frame, identifier in [('CAMARAS_EXISTENTES_103_FINAL', existing, 'ID_CAMARA'),
                                    ('PROPUESTA_MUNICIPAL_50_FINAL', municipal, 'ID_PROPUESTA')]:
        previous = old(name).set_index(identifier).loc[frame[identifier]]
        assert previous.geometry.to_wkb().tolist() == frame.geometry.to_wkb().tolist()
    expected = targets().set_index('ID_POLICIA').loc[police.ID_POLICIA]
    assert expected.geometry.to_wkb().tolist() == police.geometry.to_wkb().tolist()
    assert police.geometry.to_wkb().nunique() == 30
    assert len({g.wkb for g in list(police.geometry) + list(municipal.geometry)}) == 80
    for row in police.itertuples():
        assert abs(row.X-row.geometry.x) < 1e-8 and abs(row.Y-row.geometry.y) < 1e-8
        assert abs(row.X_DESPUES-row.geometry.x) < 1e-8 and abs(row.Y_DESPUES-row.geometry.y) < 1e-8
        assert row.DIRECCION == row.INTERSECCION_O_NODO
        assert row.COBERTURA_VISUAL_CERTIFICADA == 0
        assert row.DECISION_FINAL == 'ESTUDIO_Y_AJUSTES_APROBADOS'
        assert abs(row.SOLAPE_PCT-row.SOLAPE_PREVIO_PCT) < 1e-8
    stats = []
    for scope in ('URBANO', 'RURAL'):
        for category in ('DELINCUENCIA', 'VIOLENCIA', 'CONVIVENCIA'):
            name = 'GI_'+scope+'_'+category
            before, after = old(name), read(name)
            assert before.geometry.to_wkb().tolist() == after.geometry.to_wkb().tolist()
            fields = [c for c in before.columns if c != 'geometry' and not c.startswith(('COB_', 'ESTADO_'))]
            pd.testing.assert_frame_equal(before[fields], after[fields], check_dtype=False)
            stats.append({'layer': name, 'cells': len(after), 'geometryAndStatisticsUnchanged': True})
    validation = json.loads((DESTINATION / 'VALIDACION.json').read_text(encoding='utf-8'))
    assert not validation['publishBlocks'] and len(validation['nodeAudit']) == 30
    assert all(r['passed'] and r['nodeDistanceM'] == 0 for r in validation['nodeAudit'])
    assert [r['id'] for r in validation['nodeAudit'] if not r['principalRoad']] == ['POL-05']
    assert all(source_hash(Path(p)) == h for p, h in validation['sourceHashes'].items())
    results = json.loads((DESTINATION / 'RESULTADOS.json').read_text(encoding='utf-8'))
    gaps = json.loads((DESTINATION / 'coverage-inputs/RESULTADOS.json').read_text(encoding='utf-8'))
    assert gaps['metadata']['sourceHashes'][str(package)] == source_hash(package)
    assert sum(c['requiresChange'] for c in gaps['inventoryCameraOverlay']) == 30
    events = read('INCIDENTES_CLASIFICADOS')
    blocks = read('MANZANAS_COBERTURA')
    radius_checks = []
    for radius in (100,150,200):
        disks = [p.buffer(radius,quad_segs=64) for p in existing.geometry]
        masks = {'A': unary_union(disks)}
        masks['B'] = unary_union(disks+[p.buffer(radius,quad_segs=64) for p in municipal.geometry])
        masks['C'] = unary_union([masks['B'], *[p.buffer(radius,quad_segs=64) for p in police.geometry]])
        for code, mask in masks.items():
            scenario = gaps['scenarios'][str(radius)][code]
            assert scenario['cameraRecords'] == {'A':103,'B':153,'C':183}[code]
            for row in blocks.itertuples():
                pct = 100*row.geometry.intersection(mask).area/row.geometry.area
                assert abs(scenario['byMan'][row.ID_MANZANA]['coveragePct']-pct) < 1e-5
            if radius == 200:
                actual = read('COBERTURA_'+code).geometry.iloc[0]
                assert actual.symmetric_difference(mask).area < .01
                assert np.array_equal(covers(mask,events.geometry.values), events['CUB_'+code].astype(bool).values)
                if code in ('A','B'):
                    assert old('COBERTURA_'+code).geometry.iloc[0].equals(actual)
                for scope in ('URBANO','CANTONAL'):
                    for category in ('DELINCUENCIA','VIOLENCIA','CONVIVENCIA'):
                        scope_mask = events.AMBITO.eq('URBANO') if scope == 'URBANO' else events.AMBITO.ne('EXTERNO_CANTON')
                        selected = events.loc[scope_mask & events.CATEGORIA.eq(category)]
                        count = int(covers(mask,selected.geometry.values).sum())
                        reported = next(r for r in results['incidents'] if r['ESCENARIO']==code and r['AMBITO']==scope and r['CATEGORIA']==category)
                        assert reported['CUBIERTOS'] == count
                for row in read('CORREDORES').itertuples():
                    r = next(r for r in results['corridors'] if r['ESCENARIO']==code and r['CORREDOR']==row.CORREDOR)
                    assert abs(r['CUBIERTO_M'] - row.geometry.intersection(mask).length) < .001
        radius_checks.append({'radiusM':radius,'passed':True})
    roads = gpd.read_file(ROADS).to_crs(32717)
    proano = roads.loc[roads['name'].map(normalized).eq(normalized('Avenida Monseñor Leonidas Proaño'))]
    vertices, edges, graph = road_graph(proano, proano.geometry.union_all().buffer(201))
    coordinates = [None]*len(vertices)
    for xy, index in vertices.items(): coordinates[index] = xy
    by_id = police.set_index('ID_POLICIA')
    p17, p19 = by_id.loc['POL-17'].geometry, by_id.loc['POL-19'].geometry
    source, target = vertices[(p19.x,p19.y)], vertices[(p17.x,p17.y)]
    distances, predecessors = dijkstra(graph,directed=False,indices=source,return_predecessors=True)
    assert np.isfinite(distances[target])
    _, route = reconstruct(predecessors,source,target,coordinates)
    gap = route.difference(read('COBERTURA_C').geometry.iloc[0]).length
    assert abs(gap-12.947563808750283) < .001
    report = {'passed':True,'counts':{'existing':103,'replacement':30,'municipal':50,'police':30},
        'all30MatchApprovedTargets':True,'fixed153Unmoved':True,'scenariosAandBUnchanged':True,
        'censusCoverageCheckedAtAllRadii':True,'radii':radius_checks,'gi':stats,
        'POL17_POL19':{'sameAxisRouteM':route.length,'potentialUncoveredM':gap,'lineOfSightCertified':False},
        'packageSha256':source_hash(package),'localJunctionExplicitlyRequested':'POL-05 Roma/Viena',
        'originalSourcesUnmodified':True,'approvedException':validation['approvedException']}
    (DESTINATION / 'VERIFICACION_INDEPENDIENTE.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    refresh_archives()
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
