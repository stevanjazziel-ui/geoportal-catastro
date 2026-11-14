"""Explicitly inferred sewer scenario. Original portal measurements stay unmodified.
Instant capture of local excess rainfall within 75m is a scenario assumption.
Not an engineering reconstruction or a calibrated, bidirectional urban model.
"""
import json
import sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from pyproj import Transformer
from affine import Affine

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
from swmm.toolkit import solver
from swmm.toolkit.shared_enum import ObjectType


def build(rain_mm_h=None,scenario_name='network-inferred-1h-v2'):
    folder=ROOT/'riobamba-runs/grid-24m';out=folder/scenario_name
    out.mkdir(exist_ok=False)
    meta=json.loads((folder/'metadata.json').read_text())
    with np.load(folder/'grid.npz') as f:g={k:f[k] for k in f.files}
    d=json.loads((ROOT/'riobamba-inputs/portal-network-original.json').read_text(encoding='utf-8'))
    tr=Affine(*meta['transform']);inverse=~tr
    project=Transformer.from_crs(32717,31977,always_xy=True)
    nodes=[];lookup={};edges=[];missing=short=excluded=0
    def node(x,y):
        xx,yy=project.transform(x+d['o'][0],y+d['o'][1]);col,row=inverse*(xx,yy);r,c=int(np.floor(row)),int(np.floor(col))
        if not(0<=r<g['mask'].shape[0] and 0<=c<g['mask'].shape[1] and g['mask'][r,c]):return None
        key=(round(xx,1),round(yy,1))
        if key not in lookup:lookup[key]=len(nodes);nodes.append((xx,yy,r,c,float(g['dem'][r,c])))
        return lookup[key]
    medians={k:float(np.median([r[4]/1000 for r in d['s'] if r[5]==k and r[4]>0])) for k in (0,1,2)}
    for r in d['s']:
        a=node(r[0],r[1]);b=node(r[2],r[3])
        if a is None or b is None:excluded+=1;continue
        length=float(np.hypot(nodes[a][0]-nodes[b][0],nodes[a][1]-nodes[b][1]))
        if a==b or length<2:short+=1;continue
        diameter=r[4]/1000 if r[4]>0 else medians[r[5]];missing+=int(r[4]<=0)
        edges.append((a,b,length,diameter,int(r[9])))
    # Remove isolated nodes created while checking excluded/short edges.
    used=sorted(set(a for e in edges for a in e[:2]));remap={old:i for i,old in enumerate(used)}
    nodes=np.asarray([nodes[i] for i in used]);edges=[(remap[a],remap[b],l,diam,q) for a,b,l,diam,q in edges]
    ends=np.array([[a,b] for a,b,*_ in edges]);nn=len(nodes)
    adj=coo_matrix((np.ones(len(ends)*2),(np.r_[ends[:,0],ends[:,1]],np.r_[ends[:,1],ends[:,0]])),shape=(nn,nn))
    nc,labels=connected_components(adj)
    outlets=set(int(ix[np.argmin(nodes[ix,4])]) for k in range(nc) if len(ix:=np.flatnonzero(labels==k)))
    maxdiam=np.zeros(nn)
    for a,b,l,diam,q in edges:maxdiam[a]=max(maxdiam[a],diam);maxdiam[b]=max(maxdiam[b],diam)
    ground=nodes[:,4];invert=ground-1.-maxdiam
    rr,cc=np.nonzero(g['mask']);xx,yy=tr*(cc+.5,rr+.5)
    distance,nearest=cKDTree(nodes[:,:2]).query(np.c_[xx,yy])
    captured=np.zeros_like(g['mask']);use=(distance<=75)&(g['channel'][rr,cc]==0)
    captured[rr[use],cc[use]]=True
    rain=meta['rain_input']['max_1h_mm'] if rain_mm_h is None else float(rain_mm_h)
    if not np.isfinite(rain) or rain<=0:raise ValueError('Invalid rainfall intensity')
    # Capture excess rain once; captured cells receive neither direct 2D rainfall
    # nor 2D infiltration. Losses are accounted for before injecting the network.
    runoff=np.maximum(0,rain-g['infiltration_mm_h'][rr[use],cc[use]])/3600000*meta['dx_m']**2
    q=np.bincount(nearest[use],weights=runoff,minlength=nn)
    lines=['[TITLE]','Riobamba inferred geometry - exploratory assumed drainage','[OPTIONS]','FLOW_UNITS CMS','FLOW_ROUTING DYNWAVE','START_DATE 01/01/2020','START_TIME 00:00:00','END_DATE 01/01/2020','END_TIME 02:00:00','REPORT_STEP 00:05:00','ROUTING_STEP 00:00:05','VARIABLE_STEP 0.75','ALLOW_PONDING NO','[JUNCTIONS]']
    lines += [f'N{i} {invert[i]:.4f} {ground[i]-invert[i]:.4f} 0 0 0' for i in range(nn)]
    lines+=['[OUTFALLS]']+[f'O{i} {invert[i]-.1:.4f} FREE NO' for i in sorted(outlets)]
    # A direct outfall-outfall pipe is not allowed by SWMM; retain its source
    # in the map/audit, omit it from the approximate computational network.
    hydraulic_edges=edges
    lines+=['[CONDUITS]']+[f'C{i} N{a} N{b} {l:.3f} 0.013 0 0 0 0' for i,(a,b,l,di,qf) in enumerate(hydraulic_edges)]
    lines += [f'X{i} N{i} O{i} 10 0.013 0 0 0 0' for i in sorted(outlets)]
    lines+=['[XSECTIONS]']+[f'C{i} CIRCULAR {di:.4f} 0 0 0 1' for i,(_,_,_,di,_) in enumerate(hydraulic_edges)]
    lines += [f'X{i} CIRCULAR {maxdiam[i]:.4f} 0 0 0 1' for i in sorted(outlets)]
    lines+=['[INFLOWS]']+[f'N{i} FLOW R{i} FLOW 1 1 0' for i in range(nn) if q[i]>0]
    lines+=['[TIMESERIES]']
    # One-minute ramp at the rain transition is accounted for explicitly in
    # volume and represents a declared routing approximation (not a storm record).
    for i in range(nn):
        if q[i]>0:lines += [f'R{i} 01/01/2020 00:00 {q[i]:.9f}',f'R{i} 01/01/2020 00:59 {q[i]:.9f}',f'R{i} 01/01/2020 01:00 0',f'R{i} 01/01/2020 02:00 0']
    lines+=['[REPORT]','NODES NONE','LINKS NONE']
    (out/'network.inp').write_text('\n'.join(lines)+'\n')
    np.savez_compressed(out/'network-data.npz',nodes=nodes,edges=np.asarray(edges),captured_mask=captured,runoff_q=q)
    report={'status':'inferred_geometry_scenario_not_verified_engineering','nodes':nn,'links':len(hydraulic_edges),'source_links':len(d['s']),'excluded_outside_valid_terrain':excluded,'excluded_under_2m':short,'missing_diameters_inferred':missing,'diameter_medians_m':medians,'assumed_free_outlets':len(outlets),'captured_km2':float(captured.sum()*meta['dx_m']**2/1e6),'capture_radius_m':75,'assumptions':['Inverts = grid ground minus 1m cover minus largest incident pipe diameter.','Circular pipes; n=0.013 assumed; no measured invert levels.','Lowest terrain node per component is a free outfall; actual outlets unknown.','Missing diameters estimated by source system median; original missing values preserved.','Nearest-node instant capture within 75m; inlet locations/capacities unknown.','Hydraulic directions can reverse; portal doubtful directions are retained in audit.','One-way overflow to surface, no recapture or surface-to-sewer backwater.','One-minute rainfall-input ramp ends at 60 minutes.'], 'rainfall_mm_h':rain,'model_end_seconds':7200}
    (out/'assumptions.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)
    return out


def execute(out):
    data=np.load(out/'network-data.npz');nodes=data['nodes'];duration=7200
    solver.swmm_open(str(out/'network.inp'),str(out/'network.rpt'),str(out/'network.out'))
    try:
        engine_ids=[i for i in range(solver.project_get_count(ObjectType.NODE.value)) if solver.project_get_id(ObjectType.NODE.value,i).startswith('N')]
        ids=[int(solver.project_get_id(ObjectType.NODE.value,i)[1:]) for i in engine_ids]
        solver.swmm_start(False);last=np.zeros(len(ids));times=[0.];rates=[last.copy()]
        while True:
            days=solver.swmm_stride(60);seconds=days*86400 if days>0 else duration
            vol=np.array([solver.node_get_stats(i).volFlooded for i in engine_ids])
            dt=seconds-times[-1]
            if dt>1e-6:times.append(seconds);rates.append(np.maximum(vol-last,0)/dt)
            last=vol
            if len(times)%16==0:print('SWMM',round(seconds/60),'min',flush=True)
            if days<=0:break
        solver.swmm_end();balance=solver.swmm_get_mass_balance();solver.swmm_report()
        rates=np.asarray(rates);cells=nodes[ids,2:4].astype(int)
        integrated=float(np.sum(rates[1:]*np.diff(times)[:,None]))
        if abs(integrated-vol.sum())>1e-5:raise RuntimeError('Overflow volume export failed')
        summary={'routing_continuity_error_percent':balance[1],'runoff_continuity_error_percent':balance[0],'flood_volume_m3':integrated,'export_matches_cumulative_stats':True,'accepted_continuity':abs(balance[1])<1,'calibrated':False}
        (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
        if not summary['accepted_continuity']:raise RuntimeError('Network continuity exceeds 1%; do not use as accepted forcing')
        np.savez_compressed(out/'surface-forcing.npz',seconds=times,rates_m3_s=rates,cells=cells,captured_mask=data['captured_mask'])
    finally:solver.swmm_close()


if __name__=='__main__':execute(build())
