"""Selected mesh and roughness comparisons; diagnostic, not field validation."""
import json,pathlib
import numpy as np
from hydraulics import simulate
ROOT=pathlib.Path(__file__).parent;D=ROOT/'dist/data';results=[]
cat=json.loads((D/'cities.json').read_text(encoding='utf-8'))['cities']
for c in cat:
    if c['name'] not in ('Quito','Babahoyo'):continue
    raw=json.loads((D/f"{c['id']}.json").read_text());z=np.array(raw['dem'],float);sp=raw['spacing_m']
    for factor,n in [(2,.05),(1,.05),(2,.03)]:
        zz=z.reshape(64,2,64,2).mean(axis=(1,3)) if factor==2 else z
        r=simulate(zz,sp*factor,rain_mm_h=50,rain_hours=2,duration_hours=4,manning=n,infiltration_mm_h=5)
        wet=r['max_depth'][r['max_depth']>=.05]
        result={'city':c['name'],'factor':factor,'dx_m':sp*factor,'manning':n,'rain_mm_h':50,'max_depth_m':r['stats']['max_depth_m'],
                'max_wet_km2':r['stats']['max_footprint_km2'],'p95_max_wet_depth_m':float(np.percentile(wet,95)) if len(wet) else None,'mass_relative_error':r['stats']['mass_relative_error']}
        results.append(result);print(json.dumps(result),flush=True)
(D/'sensitivity.json').write_text(json.dumps({'calibrated':False,'note':'Mesh and roughness changes alter results; this is diagnostic sensitivity, not measured accuracy or uncertainty bounds.','comparisons':results},ensure_ascii=False,indent=1),encoding='utf-8')
