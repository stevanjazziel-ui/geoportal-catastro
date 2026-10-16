"""Audit source-road reach without applying municipal alternatives or certifying visibility."""
import heapq
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
from shapely.affinity import translate
from shapely import force_2d
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from review_police_verified_main_roads import (
    DRIVABLE, PRINCIPAL, candidates_from_shared_vertices, normalized, separated,
)
from review_police_kde_intersections import export_geojson, parts, source_hash
from study_current_municipal_nodes import OUT as STUDY, PACKAGE, ROADS, ROOT

OUT = STUDY / 'AUDITORIA_TRAMOS_VIALES'
RANGE_M, NUMERICAL_TOL_M = 200., .001
OVERLAY_EPSILON_M = .000001


def uncovered_route(route, traces):
    # Partial source segments can differ by floating-point ulps after interpolation.
    # Work near the origin so micrometre buffers remain stable at UTM northings.
    x,y=route.coords[0]
    local=translate(route,xoff=-x,yoff=-y)
    mask=translate(traces,xoff=-x,yoff=-y).buffer(OVERLAY_EPSILON_M)
    return translate(local.difference(mask),xoff=x,yoff=y)


def road_catalog(roads):
    catalog = {}
    for row in roads.itertuples():
        name = normalized(row.name)
        if not name or row.highway not in DRIVABLE or separated(row.bridge) or separated(row.tunnel):
            continue
        street = catalog.setdefault(name, {'name':str(row.name), 'adj':defaultdict(set), 'edges':{}})
        for line in parts(force_2d(row.geometry)):
            xy = [tuple(c[:2]) for c in line.coords]
            for a,b in zip(xy,xy[1:]):
                if a == b:
                    continue
                street['adj'][a].add(b); street['adj'][b].add(a)
                street['edges'][tuple(sorted((a,b)))] = LineString([a,b])
    return catalog


def trace_arm(street, start, first, straight=False, limit=RANGE_M):
    """Follow one named axis, stopping at branches; strict mode stops before bends."""
    a,b = start,first
    points = [a]
    travelled = 0.
    visited = {a}
    ray = (b[0]-a[0], b[1]-a[1])
    magnitude = math.hypot(*ray)
    while True:
        if b in visited:
            return LineString(points), 'CICLO'
        if straight:
            cross = abs(ray[0]*(b[1]-start[1])-ray[1]*(b[0]-start[0]))/magnitude
            forward = ray[0]*(b[0]-a[0])+ray[1]*(b[1]-a[1])
            if cross > NUMERICAL_TOL_M or forward <= 0:
                return LineString(points), 'CAMBIO_DIRECCION'
        edge = LineString([a,b])
        if travelled + edge.length >= limit:
            end = edge.interpolate(limit-travelled)
            points.append((end.x,end.y))
            return LineString(points), 'ALCANCE_200_M'
        points.append(b); travelled += edge.length; visited.add(b)
        neighbors = street['adj'][b] - {a}
        if len(neighbors) != 1:
            return LineString(points), 'FIN_EJE' if not neighbors else 'BIFURCACION_MISMO_NOMBRE'
        a,b = b,next(iter(neighbors))


def source_routes(street, start):
    """No shortcuts between carriageways or through other street names."""
    distance, previous = {start:0.}, {}
    queue = [(0.,start)]
    while queue:
        total,xy = heapq.heappop(queue)
        if total != distance[xy]:
            continue
        if xy != start and len(street['adj'][xy]) > 2:
            continue
        for nxt in street['adj'][xy]:
            value = total + math.dist(xy,nxt)
            if value < distance.get(nxt,float('inf')):
                distance[nxt],previous[nxt] = value,xy
                heapq.heappush(queue,(value,nxt))
    return distance,previous


def reconstruct(start, end, previous):
    chain = [end]
    while chain[-1] != start:
        chain.append(previous[chain[-1]])
    return list(reversed(chain))


def route_diagnostics(line):
    points = list(line.coords)
    chord = LineString([points[0],points[-1]])
    deviations = [Point(p).distance(chord) for p in points]
    angles = []
    for a,b,c in zip(points,points[1:],points[2:]):
        u,v = (b[0]-a[0],b[1]-a[1]),(c[0]-b[0],c[1]-b[1])
        cosine = max(-1.,min(1.,sum(x*y for x,y in zip(u,v))/(math.hypot(*u)*math.hypot(*v))))
        angles.append(math.degrees(math.acos(cosine)))
    return {'DESVIACION_CUERDA_M':max(deviations),'GIRO_MAX_GRADOS':max(angles,default=0.),
            'RECTILINEO_CARTOGRAFICO':max(deviations)<=NUMERICAL_TOL_M}


def save(name, value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')


def csv_file(name, rows):
    import csv
    if rows:
        with (OUT/name).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def audit_scenario(name, frame, fixed, catalog, junctions):
    cameras = fixed + [(r.ID_PROPUESTA,r.geometry,True) for r in frame.itertuples()]
    street_cameras = defaultdict(list)
    reach, straight, arms, camera_rows = [],[],[],[]
    by_camera = defaultdict(list)
    for key,point,target in cameras:
        xy = (point.x,point.y)
        names = [n for n,s in catalog.items() if xy in s['adj']]
        for n in names:
            street_cameras[n].append((key,xy,target))
            for neighbor in sorted(catalog[n]['adj'][xy]):
                road,reason = trace_arm(catalog[n],xy,neighbor)
                axial,axial_reason = trace_arm(catalog[n],xy,neighbor,straight=True)
                props = {'ID_CAMARA':key,'VIA':catalog[n]['name'],'OBJETIVO_24':target,
                    'ALCANCE_POR_EJE_M':road.length,'TRAMO_RECTILINEO_M':axial.length,
                    'FIN_RECORRIDO':reason,'FIN_RECTILINEO':axial_reason,
                    'VISIBILIDAD_CERTIFICADA':False,**route_diagnostics(road)}
                reach.append((road,props));straight.append((axial,props))
                by_camera[key].append(props)
                if target:
                    arms.append(props)
        if target:
            node = junctions.get(xy)
            rows = by_camera[key]
            camera_rows.append({'ID_PROPUESTA':key,'NODO_COMPROBADO':bool(node),
                'VIA_PRINCIPAL':bool(node and node['principal']),
                'CRUCE':' x '.join(node['roads']) if node else '',
                'EJES_PRINCIPALES':' | '.join(node['principal']) if node else '',
                'BRAZOS_VIALES':len(rows),'TRAMOS_MISMO_EJE_M':sum(r['ALCANCE_POR_EJE_M'] for r in rows),
                'TRAMOS_RECTILINEOS_M':sum(r['TRAMO_RECTILINEO_M'] for r in rows),
                'BRAZOS_CON_CURVA':sum(r['FIN_RECTILINEO']=='CAMBIO_DIRECCION' for r in rows),
                'APROBADA_UBICACION':False,'VISIBILIDAD_CERTIFICADA':False})
    masks,axial_masks = {},{}
    for street in street_cameras:
        masks[street] = unary_union([g for g,p in reach if normalized(p['VIA'])==street])
        axial_masks[street] = unary_union([g for g,p in straight if normalized(p['VIA'])==street])
    links,gaps,link_rows,seen = [],[],[],set()
    for street,placed in sorted(street_cameras.items()):
        coord_cameras = defaultdict(set)
        for key,xy,target in placed:
            coord_cameras[xy].add(key)
        for key,xy,target in placed:
            if not target:
                continue
            distances,previous = source_routes(catalog[street],xy)
            for other,end,_ in placed:
                pair = (street,*sorted((key,other)))
                if end==xy or pair in seen or end not in distances:
                    continue
                chain = reconstruct(xy,end,previous)
                if any(coord_cameras[p] for p in chain[1:-1]):
                    continue
                seen.add(pair)
                route = LineString(chain)
                missing = uncovered_route(route,masks[street])
                axial_missing = uncovered_route(route,axial_masks[street])
                row = {'CAMARA_A':key,'CAMARA_B':other,'VIA':catalog[street]['name'],
                    'DISTANCIA_POR_EJE_M':route.length,
                    'HUECO_DOS_EXTREMOS_M':max(0.,route.length-2*RANGE_M),
                    'HUECO_TODAS_CAMARAS_M':missing.length,
                    'HUECO_RECTILINEO_M':axial_missing.length,
                    'CONTINUIDAD_POTENCIAL_MISMO_EJE':missing.length<=NUMERICAL_TOL_M,
                    'CONTINUIDAD_AXIAL_CONSERVADORA':axial_missing.length<=NUMERICAL_TOL_M,
                    'VISIBILIDAD_CERTIFICADA':False,**route_diagnostics(route)}
                links.append((route,row));link_rows.append(row)
                for gap in parts(missing):
                    if gap.length>NUMERICAL_TOL_M:
                        gaps.append((gap,row))
    connected = {r[c] for r in link_rows if r['CONTINUIDAD_POTENCIAL_MISMO_EJE'] for c in ('CAMARA_A','CAMARA_B')}
    straight_connected = {r[c] for r in link_rows if r['CONTINUIDAD_AXIAL_CONSERVADORA'] for c in ('CAMARA_A','CAMARA_B')}
    for row in camera_rows:
        row['ENLACE_POTENCIAL_MISMO_EJE'] = row['ID_PROPUESTA'] in connected
        row['ENLACE_AXIAL_CONSERVADOR'] = row['ID_PROPUESTA'] in straight_connected
    csv_file(name+'_CAMARAS.csv',camera_rows);csv_file(name+'_BRAZOS.csv',arms);csv_file(name+'_ENLACES.csv',link_rows)
    for suffix,data in [('TRAMOS',reach),('RECTILINEOS',straight),('ENLACES',links),('HUECOS',gaps)]:
        export_geojson(OUT/(name+'_'+suffix+'.geojson'),data)
        if data:
            gpd.GeoDataFrame([p for _,p in data],geometry=[g for g,_ in data],crs=32717).to_file(
                OUT/'AUDITORIA_VIAL.gpkg',layer=name+'_'+suffix,driver='GPKG',index=False)
    export_geojson(OUT/(name+'_CAMARAS.geojson'),[(r.geometry,next(p for p in camera_rows if p['ID_PROPUESTA']==r.ID_PROPUESTA)) for r in frame.itertuples()])
    return {'name':name,'nodes':sum(r['NODO_COMPROBADO'] for r in camera_rows),
        'principal':sum(r['VIA_PRINCIPAL'] for r in camera_rows),'cameraCount':len(camera_rows),
        'camerasWithPotentialSameAxisLink':sum(r['ENLACE_POTENCIAL_MISMO_EJE'] for r in camera_rows),
        'camerasWithConservativeAxialLink':sum(r['ENLACE_AXIAL_CONSERVADOR'] for r in camera_rows),
        'links':len(link_rows),'potentialContinuousLinks':sum(r['CONTINUIDAD_POTENCIAL_MISMO_EJE'] for r in link_rows),
        'conservativeAxialLinks':sum(r['CONTINUIDAD_AXIAL_CONSERVADORA'] for r in link_rows),
        'fixedExactSourceNodes':len({key for placed in street_cameras.values() for key,_,target in placed if not target}),
        'cameras':camera_rows,'connections':link_rows}


def main():
    OUT.mkdir(exist_ok=True)
    protected=[PACKAGE,STUDY/'ESTUDIO_24_NODOS.gpkg',STUDY/'RESULTADOS.json',ROOT/'sig-bridge-active.json',
        ROOT/'riobamba-conflictividad-data.js',ROOT/'riobamba-hotspot-urbano-200m-data.js',ROOT/'visor-seguridad-riobamba-v2.html']
    protected += [p for p in ROADS.parent.glob(ROADS.stem+'.*') if p.is_file()]
    hashes={str(p):source_hash(p) for p in protected}
    read=lambda name:gpd.read_file(PACKAGE,layer=name).to_crs(32717)
    original=read('PROPUESTA_MUNICIPAL_50_FINAL')
    fixed=[(r.ID_CAMARA,r.geometry,False) for r in read('CAMARAS_EXISTENTES_103_FINAL').itertuples()]
    fixed += [(r.ID_PROPUESTA,r.geometry,False) for r in original.loc[~original.GRUPO.eq('RED_ESTRUCTURAL')].itertuples()]
    fixed += [(r.ID_POLICIA,r.geometry,False) for r in read('PROPUESTA_POLICIA_30_FINAL').itertuples()]
    assert len(fixed)==159
    roads=gpd.read_file(ROADS).to_crs(32717)
    catalog=road_catalog(roads)
    junctions={(c['point'].x,c['point'].y):c for c in candidates_from_shared_vertices(
        roads,read('PLATAFORMAS_TERRITORIALES').geometry.union_all(),require_principal=False)}
    scenarios=[audit_scenario('PUBLICADA',original.loc[original.GRUPO.eq('RED_ESTRUCTURAL')],fixed,catalog,junctions)]
    for name in ('A_CRUCES_PROXIMOS','C_PRIORIDAD_EJES','D_PRIORIDAD_CICLOVIAS'):
        frame=gpd.read_file(STUDY/'ESTUDIO_24_NODOS.gpkg',layer=name).to_crs(32717)
        scenarios.append(audit_scenario(name,frame,fixed,catalog,junctions))
        print(json.dumps({k:v for k,v in scenarios[-1].items() if k not in ('cameras','connections')}),flush=True)
    report={'applied':False,'published':False,'crs':'EPSG:32717','rangeAlongSameStreetM':RANGE_M,
        'numericalToleranceM':NUMERICAL_TOL_M,'overlayEpsilonM':OVERLAY_EPSILON_M,'fixedCameras':159,'sourceHashes':hashes,
        'scenarios':scenarios,'limitations':[
            '200 m se mide por cada brazo de la misma via; nunca se gira a una calle de otro nombre.',
            'Las trazas amarillas por la misma via pueden curvarse: son alcance vial potencial, no vision.',
            'Las trazas verdes rectilineas se detienen antes del primer cambio de direccion fuera de 0,001 m de colinealidad numerica. Es un limite conservador cartografico, no un umbral de visibilidad fisica.',
            'Se detiene el recorrido en bifurcaciones ambiguas del mismo nombre. No se crean cruces geometricos ni se conectan calzadas separadas.',
            'Solo se incluyen apoyos fijos que coinciden exactamente con vertices originales de la red. Los demas no se desplazan ni se asocian por proximidad y no se declaran sin vision: quedan sin evaluar.',
            'Se enumeran pares adyacentes de camaras sobre la misma via; no garantiza continuidad completa de todos los corredores.',
            'Los porcentajes previos de Macaji/Anillo/Ciclovias son de buffers circulares. No equivalen a estos tramos ni a cobertura visual.',
            'Faltan orientacion, altura, lente, obstaculos y comprobacion en campo. No se certifica vision real ni conectividad optica.',
            'No se reoptimiza ni se aplica ninguna alternativa. C tiene un cruce local: MUN-037; no cumple 24/24 en principal.'
        ]}
    assert all(source_hash(Path(p))==h for p,h in hashes.items())
    report['sourcesUnchanged']=True
    save('RESULTADOS.json',report)
    export_geojson(OUT/'FIJAS.geojson',[(p,{'ID_CAMARA':key}) for key,p,_ in fixed])
    shutil.copyfile(STUDY/'CORREDORES.geojson',OUT/'CORREDORES.geojson')
    shutil.copyfile(Path(__file__).with_name('municipal_street_reach_review.html'),OUT/'index.html')
    lines=['# Auditoria de nodos, ejes y continuidad vial','',
        'Estado: no aplicado / no publicado. 159 equipos fijos sin cambios. EPSG:32717.',
        '', '| Alternativa | Nodos | Principales | Camaras con enlace potencial por misma via | Con enlace axial conservador |',
        '|---|---:|---:|---:|---:|']
    lines += [f"| {s['name']} | {s['nodes']}/24 | {s['principal']}/24 | {s['camerasWithPotentialSameAxisLink']}/24 | {s['camerasWithConservativeAxialLink']}/24 |" for s in scenarios]
    lines += ['',*['- '+s for s in report['limitations']]]
    (OUT/'INFORME.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
