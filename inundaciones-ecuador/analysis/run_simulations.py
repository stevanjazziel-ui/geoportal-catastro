"""Explicit hypothetical rain-on-grid scenarios for every covered locality.
No return period, real event date or forecast is assigned to scenario intensities.
Simulation on 2x2 block-mean terrain (~153m), separately from ~76m screening.
"""
import concurrent.futures as cf,gzip,json,pathlib,time
import numpy as np
from hydraulics import simulate
ROOT=pathlib.Path(__file__).parent;DATA=ROOT/'dist/data';OUT=DATA/'simulations';OUT.mkdir(exist_ok=True)
SCENARIOS=[{'id':'rain50','label':'50 mm/h · 2 horas','rain_mm_h':50.,'rain_hours':2.,'duration_hours':4.,'manning':.05,'infiltration_mm_h':5.},
 {'id':'rain100','label':'100 mm/h · 2 horas','rain_mm_h':100.,'rain_hours':2.,'duration_hours':4.,'manning':.05,'infiltration_mm_h':5.}]
def run(c):
    raw=json.loads((DATA/f"{c['id']}.json").read_text());z=np.array(raw['dem'],float)
    z=z.reshape(64,2,64,2).mean(axis=(1,3));dx=raw['spacing_m']*2
    res=[]
    for scenario in SCENARIOS:
        p=OUT/f"{c['id']}-{scenario['id']}.json"
        if p.exists() or p.with_suffix('.json.gz').exists():
            previous=json.loads(p.read_text() if p.exists() else gzip.decompress(p.with_suffix('.json.gz').read_bytes()));res.append(previous['summary']);continue
        start=time.time();r=simulate(z,dx,**{k:v for k,v in scenario.items() if k not in ('id','label')})
        if not r['stats']['numerical_checks_passed']:raise RuntimeError('Mass conservation check failed')
        summary={'city_id':c['id'],'city':c['name'],'scenario':scenario['id'],**r['stats']}
        obj={'city_id':c['id'],'city':c['name'],'solver':'local-inertial-v1-exploratory','calibrated':False,'forcing_is_hypothetical':True,
             'parameters':{**scenario,'dx_m':dx,'boundary':'free outflow, zero external inflow; nonpositive terrain excluded',
             'sewers':'not represented','tides':'not represented','upstream_catchment_inflow':'not represented','froude_cap':1},
             'n':64,'spacing_m':dx,'bbox':raw['bbox'],'dem':np.round(z,2).tolist(),
             'times_minutes':r['times_minutes'],'frames':[np.round(a,4).tolist() for a in r['frames']],
             'max_depth':np.round(r['max_depth'],4).tolist(),'hydrograph':r['hydrograph'],'summary':summary}
        p.write_text(json.dumps(obj,separators=(',',':'),allow_nan=False),encoding='utf-8')
        print(c['name'],scenario['id'],'max',round(r['stats']['max_depth_m'],2),'mass error',r['stats']['mass_relative_error'],'seconds',round(time.time()-start,1),flush=True)
        res.append(summary)
    return res
def main():
    cities=json.loads((DATA/'cities.json').read_text(encoding='utf-8'))['cities'];summaries=[]
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        for results in pool.map(run,[c for c in cities if c['status']=='ok']):summaries.extend(results)
    (OUT/'index.json').write_text(json.dumps({'scenarios':SCENARIOS,'summaries':summaries,'calibrated':False,'note':'Scenario forcings are hypothetical; numerical tests are not validation against real floods.'},ensure_ascii=False,indent=1),encoding='utf-8')
    print('DONE',len(summaries),'simulations',flush=True)
if __name__=='__main__':main()
