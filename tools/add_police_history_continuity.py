"""Add coordinate lineage and potential road continuity to the unapplied review."""
import csv
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra, minimum_spanning_tree
from shapely import force_2d
from shapely.geometry import LineString
from shapely.ops import unary_union

from review_police_verified_main_roads import OUT, ROOT, PACKAGE, ROADS, DRIVABLE, normalized, separated
from review_police_kde_intersections import parts, source_hash, export_geojson

TOLERANCE_M = .001
BASE = ROOT / 'data/seguridad-riobamba'
HISTORY = [
    ('2026-10-03', 'Propuesta inicial', 'propuesta-policia-30-20261003/PROPUESTA_POLICIA_30.geojson'),
    ('2026-10-04', 'Revision con escenario 100 GEO', 'propuesta-policia-30-final-100geo-20261004/PROPUESTA_POLICIA_30_REVISION.geojson'),
    ('2026-10-05', 'Cierre tras revision de redundancia', 'CIERRE_POLICIA_30_FINAL_20261005/PROPUESTA_POLICIA_30_FINAL.geojson'),
    ('2026-10-05', 'Revision puntual POL-20', 'REUBICACION_POL20_20261005/PROPUESTA_POLICIA_30_FINAL.geojson'),
    ('2026-10-06', 'Revision puntual POL-12', 'REUBICACION_POL12_20261006/PROPUESTA_POLICIA_30_FINAL.geojson'),
    ('2026-10-06', 'Revision puntual POL-24', 'REUBICACION_POL24_20261006/PROPUESTA_POLICIA_30_FINAL.geojson'),
    ('2026-10-07', 'Escenario B municipal; Policia conservada', 'REUBICACION_POL24_20261007_B/PROPUESTA_POLICIA_30_FINAL.geojson'),
    ('2026-10-15', 'Policia KDE e intersecciones municipales', 'POLICIA_KDE_INTERSECCIONES_20261015/PROPUESTA_POLICIA_30_FINAL.geojson'),
    ('2026-10-15', 'Actual publicada con inventario 103/30', 'SIG_BRIDGE_RELEASES/INVENTARIO_103_30_20261015/PROPUESTA_POLICIA_30_FINAL.geojson'),
    ('2026-10-15', 'Alternativa ejes OSM; NO aplicada', 'REVISION_POLICIA_EJES_COMPROBADOS_20261015/PROPUESTA_POLICIA_30_REVISION.geojson'),
]


def csv_file(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def road_graph(roads, coverage):
    """Keep source vertices; never create junctions at unconnected geometric crossings."""
    vertices, edges = {}, {}
    for row in roads.itertuples():
        if row.highway not in DRIVABLE or separated(row.bridge) or separated(row.tunnel):
            continue
        for line in parts(force_2d(row.geometry)):
            coords=[tuple(c[:2]) for c in line.coords]
            for a,b in zip(coords,coords[1:]):
                if a==b:
                    continue
                ia,ib=vertices.setdefault(a,len(vertices)),vertices.setdefault(b,len(vertices))
                key=tuple(sorted((ia,ib)))
                name=str(row.name) if normalized(row.name) else '(sin nombre)'
                if key in edges:
                    edges[key]['names'].add(name)
                    continue
                geometry=LineString([a,b])
                uncovered=geometry.difference(coverage).length
                edges[key]={'geometry':geometry,'length':geometry.length,'names':{name},
                    'covered':uncovered<=TOLERANCE_M,'uncovered':uncovered}
    rr,cc,ww=[],[],[]
    for (a,b),edge in edges.items():
        if edge['covered']:
            rr.extend((a,b));cc.extend((b,a));ww.extend((edge['length'],edge['length']))
    return vertices,edges,csr_matrix((ww,(rr,cc)),shape=(len(vertices),len(vertices)))


def reconstruct(predecessors, source, target, coordinates):
    path=[int(target)]
    while path[-1]!=source:
        previous=int(predecessors[path[-1]])
        if previous<0 or len(path)>len(coordinates):
            raise ValueError('Ruta no reconstruible en la fuente vial')
        path.append(previous)
    path.reverse()
    return path,LineString([coordinates[i] for i in path])


def main():
    proposal_path=OUT/'REVISION_POLICIA_30.gpkg'
    proposals=gpd.read_file(proposal_path,layer='PROPUESTA_POLICIA_30_REVISION').to_crs(32717)
    expected_ids=set(proposals.ID_POLICIA)
    assert len(expected_ids)==30
    hashes={str(p):source_hash(p) for p in [PACKAGE,proposal_path,ROOT/'sig-bridge-active.json']}
    previous,history_rows,history_points={},[],[]
    by_camera={key:[] for key in sorted(expected_ids)}
    for order,(date,label,relative) in enumerate(HISTORY,1):
        path=BASE/relative
        if not path.is_file():
            raise FileNotFoundError('No se inventa un hito ausente: '+str(path))
        hashes[str(path)]=source_hash(path)
        frame=gpd.read_file(path).to_crs(32717)
        if not frame.ID_POLICIA.is_unique or set(frame.ID_POLICIA)!=expected_ids:
            raise ValueError('IDs historicos inconsistentes: '+relative)
        for row in frame.itertuples():
            point=force_2d(row.geometry)
            old=previous.get(row.ID_POLICIA)
            attributes=row._asdict()
            documented_reason=' | '.join(f'{name}: {attributes[name]}' for name in
                ('JUSTIFICACION','JUSTIFICACION_FINAL','MOTIVO','CRITERIO')
                if attributes.get(name) is not None and str(attributes[name]).strip().lower() not in ('nan','none',''))
            entry={'ID_POLICIA':row.ID_POLICIA,'ORDEN':order,'FECHA_VERSION':date,'HITO':label,
                'FUENTE':relative,'SHA256_FUENTE':hashes[str(path)],'X':point.x,'Y':point.y,
                'DESPLAZAMIENTO_DESDE_HITO_ANTERIOR_M':old.distance(point) if old is not None else None,
                'ID_CANDIDATO_DOCUMENTADO':attributes.get('ID_CANDIDATO',attributes.get('ID_CANDIDATO_NUEVO')),
                'DECISION_DOCUMENTADA':attributes.get('DECISION',attributes.get('DECISION_FINAL')),
                'MOTIVO_DOCUMENTADO':documented_reason or None,
                'ESTADO':'NO_APLICADA' if order==len(HISTORY) else 'ACTUAL_PUBLICADA' if order==len(HISTORY)-1 else 'SNAPSHOT_HISTORICO',
                'FECHA_NOTA':'Fecha de la version, no fecha certificada de instalacion o aprobacion'}
            history_rows.append(entry);history_points.append((point,entry));by_camera[row.ID_POLICIA].append(entry)
            previous[row.ID_POLICIA]=point
    csv_file(OUT/'HISTORIAL_30_CAMARAS.csv',history_rows)
    export_geojson(OUT/'HISTORIAL_COORDENADAS.geojson',history_points)
    read=lambda name:gpd.read_file(PACKAGE,layer=name).to_crs(32717)
    fixed=[]
    for layer,identifier in [('CAMARAS_EXISTENTES_103_FINAL','ID_CAMARA'),('PROPUESTA_MUNICIPAL_50_FINAL','ID_PROPUESTA')]:
        fixed += [(row.geometry,getattr(row,identifier)) for row in read(layer).itertuples()]
    cameras=fixed+[(row.geometry,row.ID_POLICIA) for row in proposals.itertuples()]
    disks={key:g.buffer(200,quad_segs=64) for g,key in cameras}
    coverage=unary_union(list(disks.values()))
    roads=gpd.read_file(ROADS).to_crs(32717)
    for path in ROADS.parent.glob(ROADS.stem+'.*'):
        if path.is_file(): hashes[str(path)]=source_hash(path)
    print('Construyendo continuidad potencial sobre segmentos originales de calles',flush=True)
    vertices,edges,graph=road_graph(roads,coverage)
    coords=[None]*len(vertices)
    for xy,i in vertices.items(): coords[i]=xy
    node_ids=[]
    for point in proposals.geometry:
        xy=(point.x,point.y)
        assert xy in vertices, 'No se asocia por proximidad un extremo policial'
        node_ids.append(vertices[xy])
    _,components=connected_components(graph,directed=False)
    distances,predecessors=dijkstra(graph,directed=False,indices=node_ids,return_predecessors=True)
    pair_distances=distances[:,node_ids]
    a,b=np.where(np.isfinite(pair_distances)&(pair_distances>0))
    pair_graph=csr_matrix((pair_distances[a,b],(a,b)),shape=(30,30))
    spanning=minimum_spanning_tree(pair_graph).tocoo()
    groups={}
    for row,node in zip(proposals.itertuples(),node_ids):
        groups.setdefault(int(components[node]),[]).append(row.ID_POLICIA)
    ordered_groups=sorted(groups.values(),key=lambda ids:(-len(ids),ids))
    group_ids={camera:f'CADENA-{i:02d}' for i,ids in enumerate(ordered_groups,1) for camera in ids}
    links,link_geometries=[],[]
    neighbors={row.ID_POLICIA:[] for row in proposals.itertuples()}
    for i,j in zip(spanning.row,spanning.col):
        ca,cb=proposals.iloc[int(i)],proposals.iloc[int(j)]
        path,geometry=reconstruct(predecessors[int(i)],node_ids[int(i)],node_ids[int(j)],coords)
        names=sorted({name for u,v in zip(path,path[1:]) for name in edges[tuple(sorted((u,v)))]['names']})
        both=unary_union([disks[ca.ID_POLICIA],disks[cb.ID_POLICIA]])
        gap_pair=geometry.difference(both).length
        gap_all=geometry.difference(coverage).length
        assert gap_all<=TOLERANCE_M
        supporting=[key for key,disk in disks.items() if key not in (ca.ID_POLICIA,cb.ID_POLICIA) and geometry.intersection(disk).length>TOLERANCE_M]
        record={'ID_ENLACE':f'ENLACE-{len(links)+1:03d}','CAMARA_A':ca.ID_POLICIA,'CAMARA_B':cb.ID_POLICIA,
            'CADENA':group_ids[ca.ID_POLICIA],'DISTANCIA_RECTA_M':ca.geometry.distance(cb.geometry),
            'LONGITUD_POR_CALLES_M':geometry.length,'EJES':' | '.join(names),
            'CAMBIOS_DE_EJE':len({normalized(n) for n in names})>1,
            'LONGITUD_SIN_COBERTURA_183_M':gap_all,'LONGITUD_NO_CUBIERTA_SOLO_POR_EL_PAR_M':gap_pair,
            'REQUIERE_APOYO_OTRAS_CAMARAS':gap_pair>TOLERANCE_M,
            'EQUIPOS_CUYOS_RADIOS_INTERSECTAN_LA_RUTA':' | '.join(supporting),
            'ESTADO':'CONTINUIDAD_GEOMETRICA_POTENCIAL_EN_RED','LINEA_DE_VISTA_VERIFICADA':False,
            'FUENTE_VIAL':ROADS.name,'RADIO_M':200}
        links.append(record);link_geometries.append((geometry,record))
        neighbors[ca.ID_POLICIA].append(cb.ID_POLICIA);neighbors[cb.ID_POLICIA].append(ca.ID_POLICIA)
    csv_file(OUT/'ENLACES_POTENCIALES_POR_CALLES.csv',links)
    export_geojson(OUT/'ENLACES_POTENCIALES_POR_CALLES.geojson',link_geometries)
    isolated=[ids[0] for ids in ordered_groups if len(ids)==1]
    details={key:{'history':by_camera[key],'chain':group_ids[key],'linkedPoliceNeighbors':sorted(neighbors[key]),
        'linkIds':[r['ID_ENLACE'] for r in links if key in (r['CAMARA_A'],r['CAMARA_B'])],
        'note':'Sin otra policial enlazada en este control; no implica ausencia de cobertura' if key in isolated else 'Cadena potencial por calles; no certifica visibilidad'} for key in by_camera}
    result={'status':'ESTUDIO_NO_APLICADO','applied':False,'published':False,'crs':'EPSG:32717',
        'historyVersions':len(HISTORY),'historyRows':len(history_rows),'policeCount':30,'fixedCameraCount':153,
        'potentialPoliceChains':ordered_groups,'isolatedFromOtherPoliceInThisControl':isolated,
        'potentialLinks':len(links),'linksNeedingOtherCameraCoverage':sum(r['REQUIERE_APOYO_OTRAS_CAMARAS'] for r in links),
        'numericalToleranceM':TOLERANCE_M,'byCamera':details,'links':links,'sourceHashes':hashes,
        'method':'Red no dirigida de vertices originales OSM compartidos; aristas completas cubiertas por union de radios de 183 equipos; rutas minimas y arbol de expansion minima entre policiales alcanzables. Sin asignar extremos por proximidad ni crear cruces geometricos.',
        'limitations':['Continuidad de cobertura geometrica potencial; no significa seguimiento visual garantizado.',
            'La union puede requerir apoyo de otras camaras cuyos radios intersectan la ruta; no se certifica su instalacion, operatividad o alineacion con la calle.',
            'Giros, edificios, altura y orientacion no modelados. Enlaces con cambios de eje requieren revision operativa.',
            'No hay limite artificial 400m de enlace ni prioridad de optimizacion de corredores. No se mueven puntos.',
            'Un componente sin otra policial no acredita aislamiento respecto a todas las existentes o municipales; sus anclajes viales no se inventan.',
            'Snapshots historicos conservan fechas de version y procedencia, no fechas de aprobacion inventadas.']}
    assert all(source_hash(Path(p))==h for p,h in hashes.items())
    result['sourcesUnchanged']=True
    (OUT/'TRAZABILIDAD.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('byCamera','links','sourceHashes')},ensure_ascii=True),flush=True)


if __name__=='__main__':
    main()
