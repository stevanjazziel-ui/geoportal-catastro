"""Independently verify lineage and every route segment against source road vertices."""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
from scipy.spatial import cKDTree
from shapely import force_2d
from shapely.ops import unary_union

from review_police_verified_main_roads import OUT, ROADS, PACKAGE, DRIVABLE, separated
from review_police_kde_intersections import parts, source_hash


def main():
    data=json.loads((OUT/'TRAZABILIDAD.json').read_text(encoding='utf-8'))
    assert len(data['byCamera'])==30 and data['historyRows']==300
    assert all(len(row['history'])==10 for row in data['byCamera'].values())
    assert all(source_hash(Path(p))==h for p,h in data['sourceHashes'].items())
    roads=gpd.read_file(ROADS).to_crs(32717)
    vertices,segments=set(),set()
    for road in roads.itertuples():
        if road.highway not in DRIVABLE or separated(road.bridge) or separated(road.tunnel):
            continue
        for line in parts(force_2d(road.geometry)):
            coords=[tuple(c[:2]) for c in line.coords]
            vertices.update(coords)
            segments.update(tuple(sorted((a,b))) for a,b in zip(coords,coords[1:]) if a!=b)
    coordinates=sorted(vertices)
    tree=cKDTree(np.asarray(coordinates))
    frames=[gpd.read_file(PACKAGE,layer=name) for name in ('CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL')]
    frames.append(gpd.read_file(OUT/'REVISION_POLICIA_30.gpkg',layer='PROPUESTA_POLICIA_30_REVISION'))
    mask=unary_union([point.buffer(200,quad_segs=64) for frame in frames for point in frame.geometry])
    endpoints=frames[-1].set_index('ID_POLICIA').geometry
    routes=gpd.read_file(OUT/'ENLACES_POTENCIALES_POR_CALLES.geojson').to_crs(32717)
    checks=[]
    for route in routes.itertuples():
        coords=np.asarray(route.geometry.coords)[:,:2]
        distance,index=tree.query(coords)
        # Micrometre tolerance only accommodates the WGS84 export round trip, not road association.
        assert float(distance.max())<1e-6
        original=[coordinates[int(i)] for i in index]
        assert all(tuple(sorted((a,b))) in segments for a,b in zip(original,original[1:]))
        assert route.geometry.boundary.geoms[0].distance(endpoints.loc[route.CAMARA_A])<1e-6
        assert route.geometry.boundary.geoms[-1].distance(endpoints.loc[route.CAMARA_B])<1e-6
        gap=route.geometry.difference(mask).length
        assert gap<.001
        assert abs(route.geometry.length-route.LONGITUD_POR_CALLES_M)<.001
        checks.append({'id':route.ID_ENLACE,'segmentsOnOriginalRoads':True,
            'maxVertexRoundTripErrorM':float(distance.max()),'uncoveredRouteM':gap})
    assert len(routes)==data['potentialLinks']==30-len(data['potentialPoliceChains'])
    assert sum(bool(v['linkedPoliceNeighbors']) for v in data['byCamera'].values())==30-len(data['isolatedFromOtherPoliceInThisControl'])
    assert data['published'] is False and data['applied'] is False
    validation={'passed':True,'historyRecords':300,'versionsPerId':10,
        'sourceHashesUnchanged':True,'routeSegmentsVerifiedAgainstOriginalVertices':True,
        'checks':checks,'published':False,'applied':False}
    (OUT/'VALIDACION_TRAZABILIDAD.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
    print(json.dumps({'passed':True,'historyRecords':300,'verifiedRoutes':len(checks),'sourcesUnchanged':True,'published':False}))


if __name__=='__main__':
    main()
