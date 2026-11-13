"""Execute explicitly synthetic local scenarios, with separate output directories."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from local_flood_solver import simulate

ROOT=Path(__file__).resolve().parent


def run(grid_folder,name,rain_hours,rain_mm_h,duration_hours,network=None,infiltration_factor=1.):
    grid_folder=Path(grid_folder);meta=json.loads((grid_folder/'metadata.json').read_text(encoding='utf-8'))
    out=grid_folder/name
    if out.exists():raise FileExistsError('Preserve previous runs; select a new scenario name')
    with np.load(grid_folder/'grid.npz') as f:g={k:f[k] for k in f.files}
    kwargs={};infil=g['infiltration_mm_h']*infiltration_factor
    if network:
        with np.load(network/'surface-forcing.npz') as f:
            kwargs={'source_times':f['seconds'],'source_rates':f['rates_m3_s'],'source_cells':f['cells'],'rain_factor':(~f['captured_mask']).astype(float)}
            # Soil losses in captured areas are already represented in SWMM runoff.
            infil[f['captured_mask']]=0
    # Reserve the run name before computing, so concurrent invocations cannot
    # spend minutes calculating the same output and collide at final write.
    out.mkdir()
    started=time.time()
    def progress(frac,steps):print(name,round(frac*100,1),'%',steps,'steps',round(time.time()-started,1),'seconds',flush=True)
    result=simulate(g['dem'],g['mask'],meta['dx_m'],g['manning'],infil,[[0,rain_mm_h],[rain_hours*3600,0]],duration_hours,progress=progress,**kwargs)
    np.savez_compressed(out/'result.npz',frames=result['frames'],times_minutes=result['times_minutes'],max_depth=result['max_depth'])
    wet=(result['max_depth']>=.05)&g['mask'];interior=g['boundary_distance_m']>=meta['dx_m']*3
    report={'id':name,'city':'Riobamba','method':'local-inertial-spatial-fields-v2-exploratory','calibrated':False,'synthetic_event':True,
            'rain_mm_h':rain_mm_h,'rain_hours':rain_hours,'total_rain_mm':rain_mm_h*rain_hours,'duration_hours':duration_hours,'infiltration_multiplier':infiltration_factor,
            'network':str(network) if network else 'Not represented; conservative no-drainage comparison','metadata':meta,'stats':result['stats'],'hydrograph':result['hydrograph'],
            'context_comparison':{'wet_km2_5cm':float(wet.sum()*meta['dx_m']**2/1e6),'interior_wet_km2_5cm':float((wet&interior).sum()*meta['dx_m']**2/1e6),
                                  'wet_area_in_given_high_classes_km2':float((wet&(g['anegamiento']>=3)).sum()*meta['dx_m']**2/1e6),
                                  'interpretation':'Spatial overlap with a supplied classification, not validation with an observed flood.'},
            'limitations':['Synthetic uniform hyetograph; maxima do not establish a return period or observed event.','Annual-maxima source provenance still requires confirmation.','Boundary conditions, infiltration and roughness are assumptions. No calibrated flood prediction.','Daily Chibunga series do not provide the missing subhourly event inflow or river bathymetry.']}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report['stats'],indent=2),flush=True)
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dx',type=int,default=24);p.add_argument('--case',choices=['hour','day'],default='hour');a=p.parse_args()
    folder=ROOT/'riobamba-runs'/f'grid-{a.dx}m';m=json.loads((folder/'metadata.json').read_text())
    if a.case=='hour':run(folder,'rain-1h-no-drainage',1,m['rain_input']['max_1h_mm'],2)
    else:run(folder,'rain-24h-no-drainage',24,m['rain_input']['max_24h_mm']/24,26)
