"""Execute a supplied SWMM INP and export network results in SI units.

python run_swmm.py network.inp NEW_DIRECTORY
This computes the network only. Surface feedback is not dynamically coupled.
"""
import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent
if (ROOT/'.deps').exists():sys.path.insert(0,str(ROOT/'.deps'))
from swmm.toolkit import solver
from swmm.toolkit.shared_enum import ObjectType,NodeResult,LinkResult,UnitProperty,TimeProperty

FLOW_TO_CMS={0:.028316846592,1:.0000630901964,2:.0438126363889,3:1.,4:.001,5:1/86.4}


def run(inp,outdir):
    inp=Path(inp).resolve();outdir=Path(outdir).resolve()
    if outdir.exists():raise FileExistsError('Use a new output directory')
    outdir.mkdir(parents=True)
    solver.swmm_open(str(inp),str(outdir/'network.rpt'),str(outdir/'network.out'))
    try:
        flow_unit=solver.simulation_get_unit(UnitProperty.FLOW_UNIT.value)
        system_unit=solver.simulation_get_unit(UnitProperty.SYSTEM_UNIT.value)
        qscale=FLOW_TO_CMS[flow_unit];zscale=.3048 if system_unit==0 else 1.
        nodes=[solver.project_get_id(ObjectType.NODE.value,i) for i in range(solver.project_get_count(ObjectType.NODE.value))]
        links=[solver.project_get_id(ObjectType.LINK.value,i) for i in range(solver.project_get_count(ObjectType.LINK.value))]
        start=datetime(*solver.simulation_get_datetime(TimeProperty.START_DATE.value))
        end=datetime(*solver.simulation_get_datetime(TimeProperty.END_DATE.value))
        duration=(end-start).total_seconds()
        solver.swmm_start(True)
        count=0;last=0.;flood_vol=0.
        with (outdir/'nodes.csv').open('w',newline='',encoding='utf-8') as nf,(outdir/'links.csv').open('w',newline='',encoding='utf-8') as lf:
            nw=csv.writer(nf);lw=csv.writer(lf)
            nw.writerow(['seconds','node','head_m','depth_m','flood_m3_s'])
            lw.writerow(['seconds','link','flow_m3_s','depth_m'])
            def snapshot(seconds,delta):
                nonlocal flood_vol
                for i,name in enumerate(nodes):
                    flood=max(0,solver.node_get_result(i,NodeResult.FLOOD.value)*qscale)
                    nw.writerow([seconds,name,solver.node_get_result(i,NodeResult.HEAD.value)*zscale,solver.node_get_result(i,NodeResult.DEPTH.value)*zscale,flood])
                    flood_vol+=flood*delta
                for i,name in enumerate(links):
                    lw.writerow([seconds,name,solver.link_get_result(i,LinkResult.FLOW.value)*qscale,solver.link_get_result(i,LinkResult.DEPTH.value)*zscale])
            snapshot(0,0)
            while True:
                days=solver.swmm_step()
                if days<=0:
                    # The engine advances its final routing step before returning zero.
                    if last<duration:snapshot(duration,duration-last);last=duration;count+=1
                    break
                seconds=round(days*86400,8)
                if seconds<=last:raise RuntimeError('Non-increasing SWMM clock')
                snapshot(seconds,seconds-last);last=seconds;count+=1
            solver.swmm_end()
            balance=solver.swmm_get_mass_balance();solver.swmm_report()
        report={'engine':'SWMM','engine_version':solver.swmm_get_version(),'input':str(inp),'input_sha256':hashlib.sha256(inp.read_bytes()).hexdigest(),
                'units':'SI: m, m3/s, seconds since model start','original_flow_unit_code':flow_unit,'model_start':start.isoformat(),'model_end':end.isoformat(),'nodes':nodes,'links':links,'steps':count,'duration_seconds':last,
                'routing_continuity_error_percent':balance[1],'runoff_continuity_error_percent':balance[0],
                'flood_volume_step_integral_m3':flood_vol,'continuity_within_1_percent':abs(balance[1])<1,
                'status':'network_only_not_a_calibrated_city_model',
                'limitations':['A 1% continuity check is a diagnostic, not field validation.','Flood CSV is an instantaneous-rate series; resampling must conserve its integrated volume.','No dynamic bidirectional coupling with the surface solver.','Review warnings, instability, geometry, datum and hydrological inputs in network.rpt.']}
        (outdir/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return report
    finally:solver.swmm_close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inp');p.add_argument('output');a=p.parse_args()
    print(json.dumps(run(a.inp,a.output),indent=2))
