"""Junction-first municipal selection: Macaji100, no ring floor, auditable road links."""
import json
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix, csr_matrix
from shapely import STRtree
from shapely.geometry import LineString
from shapely.ops import unary_union

import audit_municipal_street_reach as audit
import study_current_municipal_nodes as study_module
from study_current_municipal_nodes import Study, ROOT, PACKAGE, ROADS, MACAJI, KEYS
from review_police_verified_main_roads import normalized, PRINCIPAL
from review_police_kde_intersections import source_hash, export_geojson
from adjust_macaji_100 import interval_constraints

OUT=ROOT/'data/seguridad-riobamba/MUNICIPALES_EJES_SIN_MINIMO_ANILLO_20261016'


def main():
    assert not (OUT/'RESULTADOS.json').exists(),'No se sobrescribe un resultado final'
    OUT.mkdir(exist_ok=True)
    s=Study()
    paths=[PACKAGE,ROOT/'sig-bridge-active.json',ROOT/'visor-seguridad-riobamba-v2.html',
        ROOT/'riobamba-conflictividad-data.js',ROOT/'riobamba-hotspot-urbano-200m-data.js']
    paths += [p for p in ROADS.parent.glob(ROADS.stem+'.*') if p.is_file()]
    hashes={str(p):source_hash(p) for p in paths}
    roads=s.roads.loc[s.roads.highway.isin(PRINCIPAL)].reset_index(drop=True)
    tree=STRtree(roads.geometry)
    intended={r.ID_PROPUESTA:normalized(roads.iloc[int(tree.nearest(r.geometry))]['name']) for r in s.original.itertuples()}
    intended.update({k:normalized(v) for k,v in study_module.REQUIRED_AXES.items()})
    accepted_axes={key:{value} for key,value in intended.items()}
    previous=json.loads((study_module.OUT/'C_PRIORIDAD_EJES.json').read_text(encoding='utf-8'))
    for row in previous['movements']:
        if row['ID_PROPUESTA'] not in study_module.REQUIRED_AXES:
            accepted_axes[row['ID_PROPUESTA']].update(normalized(n.strip()) for n in row['EJE_PRINCIPAL'].split('|') if n.strip())
    principal_union=unary_union([s.fixed,*[c['point'].buffer(200,quad_segs=64) for c in s.principal]])
    missing=s.axes[MACAJI].difference(principal_union)
    # Only local nodes that can close the principal-only Macaji gap are exceptions.
    pool=[c for c in s.candidates if c['principal'] or c['point'].buffer(200,quad_segs=64).intersection(missing).length>.001]
    allowed=[]
    for i,row in enumerate(s.original.itertuples()):
        for j,c in enumerate(pool):
            main={normalized(n) for n in c['principal']}
            if accepted_axes[row.ID_PROPUESTA]&main or (row.ID_PROPUESTA=='MUN-037' and not main):
                allowed.append((i,j))
    used={j for _,j in allowed};pool=[c for j,c in enumerate(pool) if j in used]
    allowed=[(i,j) for i,row in enumerate(s.original.itertuples()) for j,c in enumerate(pool)
        if accepted_axes[row.ID_PROPUESTA]&{normalized(n) for n in c['principal']}
        or (row.ID_PROPUESTA=='MUN-037' and not c['principal'])]
    print('Cruces por eje:',len(pool),'asignaciones:',len(allowed),flush=True)
    catalog=audit.road_catalog(s.roads)
    def traces(point,names):
        xy=(point.x,point.y)
        return {normalized(name):unary_union([audit.trace_arm(catalog[normalized(name)],xy,b)[0]
            for b in catalog[normalized(name)]['adj'].get(xy,[])]) for name in names
            if normalized(name) in catalog and xy in catalog[normalized(name)]['adj']}
    reaches=[traces(c['point'],c['principal']) for c in pool]
    fixed_streets=defaultdict(list)
    for row in list(s.existing.itertuples())+list(s.frozen.itertuples()):
        xy=(row.geometry.x,row.geometry.y)
        for name,street in catalog.items():
            if xy in street['adj']:
                fixed_streets[name].append((xy,unary_union([audit.trace_arm(street,xy,b)[0] for b in street['adj'][xy]])))
    potential_edges=[];fixed_support=np.zeros(len(pool),dtype=bool)
    spatial=STRtree([c['point'] for c in pool])
    for j,c in enumerate(pool):
        xy=(c['point'].x,c['point'].y)
        for name,trace in reaches[j].items():
            distances,previous=audit.source_routes(catalog[name],xy)
            def linked(end,other_trace):
                if end not in distances or distances[end]>400.001: return False
                if end==xy: return True
                path=LineString(audit.reconstruct(xy,end,previous))
                return audit.uncovered_route(path,unary_union([trace,other_trace])).length<=.001
            if any(linked(end,t) for end,t in fixed_streets.get(name,[])): fixed_support[j]=True
            for k in spatial.query(c['point'].buffer(400.001)):
                k=int(k)
                if k<=j or name not in reaches[k]: continue
                q=pool[k]['point']
                if linked((q.x,q.y),reaches[k][name]): potential_edges.append((j,k))
    potential_edges=sorted(set(potential_edges))
    _,impossible,_,lengths=interval_constraints([(key,axis,s.fixed) for key,axis in s.axes.items()],[(c['point'],c) for c in pool])
    assert impossible.get(MACAJI,0)<=.001,'El catalogo por ejes no cierra Macaji; no se publica un resultado incompleto'
    n=len(pool);a=len(allowed);e=len(potential_edges)
    # selected nodes, ID assignments, link flags, pair supports.
    size=n+a+n+e;rr=[];cc=[];vv=[];lo=[];hi=[]
    def add(entries,lower,upper):
        row=len(lo)
        for col,value in entries:rr.append(row);cc.append(col);vv.append(value)
        lo.append(lower);hi.append(upper)
    for i in range(24):add([(n+k,1) for k,(camera,_) in enumerate(allowed) if camera==i],1,1)
    for j in range(n):add([(j,-1)]+[(n+k,1) for k,(_,candidate) in enumerate(allowed) if candidate==j],0,0)
    junctions=defaultdict(list)
    for j,c in enumerate(pool):junctions[tuple(sorted(normalized(v) for v in c['roads']))].append(j)
    for group in junctions.values():add([(j,1) for j in group],-np.inf,1)
    for (key,support),length in lengths.items():
        if key==MACAJI:add([(j,1) for j in support],1,np.inf)
    touching=defaultdict(list)
    for k,(j,q) in enumerate(potential_edges):
        y=n+a+n+k;add([(y,1),(j,-1)],-np.inf,0);add([(y,1),(q,-1)],-np.inf,0)
        touching[j].append(y);touching[q].append(y)
    for j in range(n):
        z=n+a+j;add([(z,1),(j,-1)],-np.inf,0)
        add([(z,1),(j,-int(fixed_support[j]))]+[(y,-1) for y in touching[j]],-np.inf,0)
    constraints=[LinearConstraint(coo_matrix((vv,(rr,cc)),shape=(len(lo),size)).tocsr(),lo,hi)]
    main_weight=np.r_[[int(bool(c['principal'])) for c in pool],np.zeros(a+n+e)]
    link_weight=np.r_[np.zeros(n+a),np.ones(n),np.zeros(e)]
    transport=np.r_[np.zeros(n),[s.original.iloc[i].geometry.distance(pool[j]['point']) for i,j in allowed],np.zeros(n+e)]
    logs=[];solution=None
    for name,cost in [('MAX_NODOS_PRINCIPALES',-main_weight),('MAX_CAMARAS_CON_ENLACE_MISMO_EJE',-link_weight),('MIN_DESPLAZAMIENTO',transport)]:
        trial=milp(cost,integrality=np.r_[np.ones(n+a+n),np.zeros(e)],bounds=Bounds(np.zeros(size),np.ones(size)),
            constraints=constraints,options={'time_limit':60,'mip_rel_gap':1e-6})
        log={'phase':name,'status':int(trial.status),'message':trial.message,'objective':float(trial.fun) if trial.x is not None else None,
            'gap':float(trial.mip_gap) if trial.x is not None else None}
        logs.append(log);print(json.dumps(log),flush=True)
        if trial.x is None:
            assert solution is not None,'No existe solucion comprobada en el catalogo por ejes'
            break
        solution=trial
        weight=main_weight if name=='MAX_NODOS_PRINCIPALES' else link_weight
        if name!='MIN_DESPLAZAMIENTO':
            value=int(round(weight@trial.x));constraints.append(LinearConstraint(csr_matrix(weight[None,:]),value,value))
    pair=[(i,pool[j]) for k,(i,j) in enumerate(allowed) if solution.x[n+k]>.5]
    assert len(pair)==24 and len({i for i,_ in pair})==24
    pair.sort()
    study_module.OUT=OUT
    scenario=s.describe('EJES_PRIORITARIOS',pair,{'logs':logs,'allPhasesOptimalInCatalog':all(l['status']==0 for l in logs)})
    frame=gpd.read_file(OUT/'ESTUDIO_24_NODOS.gpkg',layer='EJES_PRIORITARIOS').to_crs(32717)
    assert scenario['municipal'][MACAJI]['uncoveredM']<=.001
    audit.OUT=OUT
    fixed=[(r.ID_CAMARA,r.geometry,False) for r in s.existing.itertuples()]
    fixed += [(r.ID_PROPUESTA,r.geometry,False) for r in s.frozen.itertuples()]
    fixed += [(r.ID_POLICIA,r.geometry,False) for r in s.police.itertuples()]
    nodes={(c['point'].x,c['point'].y):c for c in s.candidates}
    road_audit=audit.audit_scenario('EJES_PRIORITARIOS',frame,fixed,catalog,nodes)
    report={'applied':False,'published':False,'crs':'EPSG:32717','fixedCameras':159,'sourceHashes':hashes,
        'rangeAlongSameStreetM':200,'ringMinimumPct':None,'macajiRequiredUncoveredM':0,
        'scenario':scenario,'scenarios':[road_audit], 'intendedAxes':intended,
        'acceptedAxes':{k:sorted(v) for k,v in accepted_axes.items()},'solver':logs,
        'localExceptions':[r for r in scenario['movements'] if not r['VIA_PRINCIPAL']],
        'selectionContinuityUsesPolice':False,'selectionLinkCount':int(round(link_weight@solution.x)),
        'limitations':['Anillo sin minimo; Macaji100 se mantiene por union real de buffers.',
            'Los enlaces siguen una misma via y alcance200m por extremo, sin giros a otras calles; las curvas no certifican visibilidad.',
            'La excepcion local se limita a MUN-037 y a cruces capaces de cerrar el hueco Macaji no cubrible desde nodos principales.',
            'No se supone continuidad completa; faltan orientaciones, obstaculos y campo. Las 103 existentes,26municipales y30policiales no se mueven.']}
    assert all(source_hash(Path(p))==h for p,h in hashes.items())
    (OUT/'RESULTADOS.json').write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    print(json.dumps({'municipal':scenario['municipal'],'principalCount':scenario['principalCount'],
        'linkCount':report['selectionLinkCount'],'localExceptions':report['localExceptions'],
        'totalDisplacementM':scenario['totalDisplacementM']},ensure_ascii=True,indent=2),flush=True)


if __name__=='__main__':main()
