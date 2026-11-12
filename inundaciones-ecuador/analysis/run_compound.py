"""Run an explicit, documented compound scenario; never reuse rainfall-only outputs.

Usage: python run_compound.py terrain.npz scenario.json new-output-directory
NPZ: dem [m], domain_mask [bool], optional initial_depth [m].
JSON: dx_m, terrain_datum, terrain_source, geometry_evidence, parameters, forcing.
The forcing format is documented in COMPONENTES_COMPUESTOS.md.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from compound_forcing import CompoundForcing
from hydraulics import simulate


def run(terrain, scenario, output):
    cfg=json.loads(Path(scenario).read_text(encoding='utf-8'))
    for key in ('terrain_source','terrain_datum','geometry_evidence'):
        if not cfg.get(key):raise ValueError(f'Missing {key}: document provenance and geometry before running')
    params=cfg['parameters']
    allowed={'rain_mm_h','rain_hours','duration_hours','manning','infiltration_mm_h','boundary','snapshot_minutes','max_dt'}
    if set(params)-allowed:raise ValueError('Unknown hydraulic parameter')
    duration=params['duration_hours']*3600
    with np.load(terrain,allow_pickle=False) as arrays:
        dem=arrays['dem'];mask=arrays['domain_mask'];h0=arrays['initial_depth'] if 'initial_depth' in arrays else None
    if mask.dtype!=np.bool_:raise ValueError('Domain mask must contain Boolean values')
    forcing=CompoundForcing(cfg['forcing'],dem.shape,cfg['terrain_datum'],duration)
    if not(forcing.ports or forcing.stages):raise ValueError('No external forcing supplied')
    output=Path(output)
    if output.exists():raise FileExistsError('Use a new output directory to preserve previous results')
    result=simulate(dem,cfg['dx_m'],initial_depth=h0,external=forcing,domain_mask=mask,**params)
    output.mkdir(parents=True)
    np.savez_compressed(output/'result.npz',frames=np.asarray(result['frames']),times_minutes=result['times_minutes'],max_depth=result['max_depth'],dem=dem,domain_mask=mask)
    report={'status':'exploratory_not_field_validated','scenario':cfg,'stats':result['stats'],'exchanges_m3':forcing.volumes,'requested_exchanges_m3':forcing.requested_volumes,'hydrograph':result['hydrograph'],
            'sha256':{str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (terrain,scenario,Path(__file__),Path(__file__).with_name('hydraulics.py'),Path(__file__).with_name('compound_forcing.py'))},
            'limitations':['Prescribed sewer exchange; no pipe-network routing or two-way SWMM coupling.','Geometry evidence is declared metadata, not automatic certification.','Not automatically published or substituted for existing city scenarios.']}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('terrain');p.add_argument('scenario');p.add_argument('output')
    a=p.parse_args();r=run(a.terrain,a.scenario,a.output)
    print(json.dumps(r['stats'],indent=2))
