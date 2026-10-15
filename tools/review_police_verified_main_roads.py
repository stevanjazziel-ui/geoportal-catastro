"""Unapplied police review using named, shared road vertices on principal axes."""
import csv
import json
import math
import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely import STRtree, covers, force_2d, points
from shapely.geometry import Point
from shapely.ops import unary_union

from review_police_kde_intersections import (
    ROOT, grid_data, kde, parts, source_hash, export_geojson, covered_kde,
    gi_reference, incident_counts, hotspot_coverage, UNPROJECT,
)

PACKAGE = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/INVENTARIO_103_30_20261015/ESCENARIO_FINAL_183.gpkg'
ROADS = Path('D:/codex/osm_vias_riobamba/osm_vias_dentro_canton_riobamba_utm.shp')
OUT = ROOT / 'data/seguridad-riobamba/REVISION_POLICIA_EJES_COMPROBADOS_20261015'
PRINCIPAL = {'trunk', 'primary', 'secondary', 'tertiary'}
DRIVABLE = PRINCIPAL | {'residential', 'unclassified', 'living_street', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link'}
RADIUS = 200


def named(value):
    if value is None or str(value).strip().lower() in ('nan', 'none', '', 'sin nombre', 'calle sin nombre'):
        return ''
    return str(value).strip()


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKD', named(value)).encode('ascii', 'ignore').decode().lower().split())


def separated(value):
    return str(value).strip().lower() not in ('', 'nan', 'none', 'no', '0', 'false')


def candidates_from_shared_vertices(roads, urban):
    """No union/noding: a geometric crossing without a shared source vertex is not a junction."""
    nodes = defaultdict(lambda: {'arms': set(), 'ways': {}, 'gradeSeparated': False})
    for row in roads.itertuples():
        if row.highway not in DRIVABLE:
            continue
        for line in parts(force_2d(row.geometry)):
            coordinates = [tuple(c[:2]) for c in line.coords]
            for i, xy in enumerate(coordinates):
                node = nodes[xy]
                node['ways'][str(row.osm_id)] = {'id': str(row.osm_id), 'name': named(row.name), 'highway': row.highway}
                node['gradeSeparated'] |= separated(row.bridge) or separated(row.tunnel)
                for j in (i-1, i+1):
                    if 0 <= j < len(coordinates) and coordinates[j] != xy:
                        node['arms'].add(coordinates[j])
    result = []
    for xy, node in sorted(nodes.items()):
        ways = list(node['ways'].values())
        main = [w for w in ways if w['highway'] in PRINCIPAL and w['name']]
        names = {normalized(w['name']): w['name'] for w in ways if w['name']}
        if node['gradeSeparated'] or len(node['arms']) < 3 or len(names) < 2 or not main:
            continue
        point = Point(xy)
        if not urban.covers(point):
            continue
        result.append({'id': f'OSM-CRUCE-{len(result)+1:05d}', 'point': point, 'degree': len(node['arms']),
            'roads': sorted(names.values()), 'principal': sorted({w['name'] for w in main}),
            'highways': sorted({w['highway'] for w in main}), 'osmIds': sorted(node['ways']), 'ways': ways})
    return result


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    protected_paths = [PACKAGE, ROOT/'sig-bridge-active.json', ROOT/'riobamba-conflictividad-data.js',
        ROOT/'riobamba-hotspot-urbano-200m-data.js', ROOT/'visor-seguridad-riobamba-v2.html']
    protected_paths += [p for p in ROADS.parent.glob(ROADS.stem+'.*') if p.is_file()]
    hashes = {str(p): source_hash(p) for p in protected_paths}
    read = lambda name: gpd.read_file(PACKAGE, layer=name).to_crs(32717)
    existing, municipal, current = [read(n) for n in ('CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL')]
    assert [len(existing), len(municipal), len(current)] == [103,50,30]
    urban = read('PLATAFORMAS_TERRITORIALES').geometry.union_all()
    base = read('COBERTURA_B').geometry.union_all()
    roads = gpd.read_file(ROADS).to_crs(32717)
    candidates = candidates_from_shared_vertices(roads, urban)
    if len(candidates) < 30:
        raise ValueError(f'Solo {len(candidates)} cruces comprobables disponibles')
    drive = roads.loc[roads.highway.isin(DRIVABLE)].reset_index(drop=True)
    major = roads.loc[roads.highway.isin(PRINCIPAL)].reset_index(drop=True)
    drive_tree, major_tree = STRtree(drive.geometry), STRtree(major.geometry)
    audit = []
    for row in current.itertuples():
        local = drive.iloc[int(drive_tree.nearest(row.geometry))]
        main_road = major.iloc[int(major_tree.nearest(row.geometry))]
        audit.append({'ID_POLICIA':row.ID_POLICIA, 'X_ACTUAL':row.geometry.x,'Y_ACTUAL':row.geometry.y,
            'VIA_CERCANA_OSM':named(local['name']), 'TIPO_OSM':local.highway, 'OSM_ID':local.osm_id,
            'DIST_EJE_VIAL_M':row.geometry.distance(local.geometry),
            'EJE_PRINCIPAL_CERCANO':named(main_road['name']), 'JERARQUIA_EJE_PRINCIPAL':main_road.highway,
            'DIST_EJE_PRINCIPAL_M':row.geometry.distance(main_road.geometry)})
    write_csv(OUT/'AUDITORIA_30_PUBLICADAS.csv',audit)
    incidents = read('INCIDENTES_CLASIFICADOS')
    events = incidents.loc[incidents.AMBITO.eq('URBANO') & incidents.CATEGORIA.isin(['DELINCUENCIA','VIOLENCIA'])]
    grid = grid_data()
    densities = {}
    for category in ('DELINCUENCIA','VIOLENCIA'):
        density, mask, west, north, size = kde([(g.x,g.y) for g in events.loc[events.CATEGORIA.eq(category)].geometry],grid,RADIUS)
        densities[category] = density
    density = densities['DELINCUENCIA'] + densities['VIOLENCIA']
    width, height = grid['width'], grid['height']
    indices = np.flatnonzero(mask)
    ys,xs = np.divmod(indices,width)
    cell_points = points(west+(xs+.5)*size,north-(ys+.5)*size)
    covered = np.zeros(width*height,dtype=bool)
    covered[indices] = covers(base,cell_points)
    for candidate in candidates:
        p = candidate['point']
        x0,x1 = max(0,math.floor((p.x-RADIUS-west)/size)),min(width-1,math.floor((p.x+RADIUS-west)/size))
        y0,y1 = max(0,math.floor((north-p.y-RADIUS)/size)),min(height-1,math.floor((north-p.y+RADIUS)/size))
        gx,gy = np.meshgrid(np.arange(x0,x1+1),np.arange(y0,y1+1))
        flat = (gy*width+gx).ravel()
        distance2 = (west+(gx.ravel()+.5)*size-p.x)**2+(north-(gy.ravel()+.5)*size-p.y)**2
        candidate['cells'] = flat[(distance2<=RADIUS**2)&mask[flat]]
        candidate['disk'] = p.buffer(RADIUS,quad_segs=64)
    selected,trace = [],[]
    current_union = base
    for step in range(1,31):
        ranked=[]
        for candidate in candidates:
            if candidate.get('selected') or not candidate['disk'].intersects(current_union):
                continue
            fresh = candidate['cells'][~covered[candidate['cells']]]
            gain = float(density[fresh].sum()*size*size/1e6)
            ranked.append((gain,candidate['degree'],candidate['id'],candidate))
        if not ranked:
            raise ValueError(f'Solo {len(selected)} candidatos conectados')
        # KDE remains the main criterion. Degree and a stable source ID break exact ties.
        gain,_,_,chosen = max(ranked,key=lambda value:value[:3])
        overlap = chosen['disk'].intersection(current_union).area/chosen['disk'].area*100
        chosen.update({'selected':True,'order':step,'gain':gain,'overlap':overlap})
        selected.append(chosen)
        covered[chosen['cells']] = True
        current_union = unary_union([current_union,chosen['disk']])
        trace.append({'order':step,'candidate':chosen['id'],'gainKdeDV':gain,'overlapPct':overlap})
        print(f'{step}/30: {chosen["id"]}; KDE marginal {gain:.4f}',flush=True)
    distance_matrix = np.array([[a.distance(c['point']) for c in selected] for a in current.geometry])
    ii,jj = linear_sum_assignment(distance_matrix)
    assigned = dict(zip(ii,jj))
    stats = {}
    for cat in ('DELINCUENCIA','VIOLENCIA'):
        rows = list(read('GI_URBANO_'+cat).itertuples())
        stats[cat] = (STRtree([r.geometry for r in rows]),rows)
    moves,new_points,arrows = [],[],[]
    from shapely.geometry import LineString
    for i,row in enumerate(current.itertuples()):
        c = selected[assigned[i]]
        p = c['point']
        before,after = gi_reference(row.geometry,stats),gi_reference(p,stats)
        record = {'ID_POLICIA':row.ID_POLICIA,'ID_CANDIDATO':c['id'],
            'X_ANTES':row.geometry.x,'Y_ANTES':row.geometry.y,'X_DESPUES':p.x,'Y_DESPUES':p.y,
            'DESPLAZAMIENTO_M':row.geometry.distance(p),'CRUCE':' x '.join(c['roads']),
            'EJE_PRINCIPAL':' | '.join(c['principal']),'JERARQUIA_OSM':' | '.join(c['highways']),
            'OSM_IDS':' | '.join(c['osmIds']),'GRADO_NODO':c['degree'],'ORDEN_KDE':c['order'],
            'MASA_KDE_DV_MARGINAL':c['gain'],'SOLAPE_SELECCION_PCT':c['overlap'],
            **{k+'_ANTES':v for k,v in before.items()},**{k+'_DESPUES':v for k,v in after.items()},
            'ESTADO':'PROPUESTA_PARA_REVISION_NO_APLICADA','RADIO_M':200,'FUENTE_VIAL':ROADS.name,
            'METODO_CRUCE':'VERTICE_COMPARTIDO_OSM; 2 calles nombradas; >=3 brazos; eje principal',
            'CAMPO_VISUAL_CERTIFICADO':False}
        moves.append(record)
        new_points.append((p,record))
        arrows.append((LineString([row.geometry,p]),record))
    write_csv(OUT/'MOVIMIENTOS_POLICIA_30.csv',moves)
    export_geojson(OUT/'PROPUESTA_POLICIA_30_REVISION.geojson',new_points)
    export_geojson(OUT/'MOVIMIENTOS.geojson',arrows)
    export_geojson(OUT/'POLICIA_PUBLICADA_30.geojson',[(r.geometry,{'ID_POLICIA':r.ID_POLICIA}) for r in current.itertuples()])
    export_geojson(OUT/'EXISTENTES_103_FIJAS.geojson',[(r.geometry,{'ID_CAMARA':r.ID_CAMARA,'REQUIERE_CAMBIO':bool(r.REQUIERE_CAMBIO)}) for r in existing.itertuples()])
    export_geojson(OUT/'MUNICIPALES_50_FIJAS.geojson',[(r.geometry,{'ID_PROPUESTA':r.ID_PROPUESTA}) for r in municipal.itertuples()])
    export_geojson(OUT/'EJES_PRINCIPALES.geojson',[(force_2d(r.geometry),{'name':named(r.name),'highway':r.highway,'osm_id':str(r.osm_id)}) for r in major.itertuples()])
    export_geojson(OUT/'RED_VIAL_CONTEXTO.geojson',[(force_2d(r.geometry),{'name':named(r.name),'highway':r.highway}) for r in drive.itertuples() if r.geometry.intersects(urban)])
    export_geojson(OUT/'PLATAFORMAS.geojson',[(r.geometry,{'name':r.platform_name}) for r in read('PLATAFORMAS_TERRITORIALES').itertuples()])
    candidate_frame = gpd.GeoDataFrame([p for _,p in new_points],geometry=[g for g,_ in new_points],crs=32717)
    candidate_frame.to_file(OUT/'REVISION_POLICIA_30.gpkg',layer='PROPUESTA_POLICIA_30_REVISION',driver='GPKG',index=False)
    before_union = read('COBERTURA_C').geometry.union_all()
    event_rows = [(r.geometry,r.CATEGORIA) for r in events.itertuples()]
    compare = {'kdeBefore':covered_kde(before_union,cell_points,indices,mask,densities),
        'kdeAfter':covered_kde(current_union,cell_points,indices,mask,densities),
        'eventsBefore':incident_counts(before_union,event_rows),'eventsAfter':incident_counts(current_union,event_rows),
        'hotspotBefore':hotspot_coverage(before_union,stats),'hotspotAfter':hotspot_coverage(current_union,stats)}
    corridors=[]
    for r in read('CORREDORES').itertuples():
        corridors.append({'corridor':r.CORREDOR,'beforePct':100*r.geometry.intersection(before_union).length/r.geometry.length,
            'afterPct':100*r.geometry.intersection(current_union).length/r.geometry.length})
    assert all(source_hash(Path(p))==h for p,h in hashes.items())
    assert len({p.wkb for p,_ in new_points})==30
    for c in selected:
        assert c['degree']>=3 and len(c['roads'])>=2 and c['principal'] and urban.covers(c['point'])
    png = ROOT/'data/seguridad-riobamba/propuesta-policia-kde-intersecciones-20261014/KDE_URBANO_DELINCUENCIA_VIOLENCIA_200M.png'
    shutil.copy2(png,OUT/png.name)
    west,south = grid['metricBounds'][0]
    east,north = grid['metricBounds'][1]
    lo,la=UNPROJECT(west,south); hi,ha=UNPROJECT(east,north)
    report={'status':'PARA_REVISION_NO_APLICADA','count':30,'existingFixed':103,'municipalFixed':50,
        'candidateCount':len(candidates),'principalHighways':sorted(PRINCIPAL),
        'sourceHashes':hashes,'sourcesUnchanged':True,'published':False,'applied':False,'giRecalculated':False,
        'kdeMethodUnchanged':True,'selectionTrace':trace,'comparison':compare,'corridorsSecondaryOnly':corridors,
        'displacements':{'meanM':float(np.mean([m['DESPLAZAMIENTO_M'] for m in moves])),
            'maxM':float(max(m['DESPLAZAMIENTO_M'] for m in moves)),'totalM':sum(m['DESPLAZAMIENTO_M'] for m in moves)},
        'kdeImage':'KDE_URBANO_DELINCUENCIA_VIOLENCIA_200M.png','kdeBounds':[[la,lo],[ha,hi]],
        'limitations':['OSM es una referencia de contraste, no certificacion municipal ni de postes en campo.',
            'Jerarquia OSM documentada por tramo; no se equipara automaticamente a la clasificacion municipal.',
            'Los enlaces de buffers representan proximidad geometrica, no linea de vista verificada.',
            'Seleccion greedy KDE, sin garantia de optimo global. IDs asignados minimizando desplazamiento total despues de seleccionar ubicaciones.']}
    (OUT/'RESULTADOS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('sourceHashes','selectionTrace')},ensure_ascii=True),flush=True)


if __name__=='__main__':
    main()
