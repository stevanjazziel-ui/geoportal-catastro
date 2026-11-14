"""Stress experiments, NOT ENSO forecasts or maximum possible floods.
The +25/+50/+100% perturbations are chosen sensitivity assumptions.
All physics is rerun; no previous depth or footprint is multiplied.
"""
import gzip,hashlib,json
from pathlib import Path
import numpy as np
from run_riobamba_cases import run
from approximate_riobamba_network import build,execute

ROOT=Path(__file__).resolve().parent
GRID=ROOT/'riobamba-runs/grid-24m'
OUT=ROOT/'dist/data/riobamba-local'
ERFEN='https://alertasecuador.gob.ec/el_nino/wp-content/uploads/2026/11/erfen_20261105.pdf'
CASES=[
 ('stress-1h-plus25',45.2,1,1.25,1.,False),
 ('stress-1h-plus50',45.2,1,1.5,1.,False),
 ('stress-1h-plus100',45.2,1,2.,1.,False),
 ('stress-2h-plus50',24.2,2,1.5,1.,False),
 ('stress-1h-plus50-zero-loss',45.2,1,1.5,0.,False),
 ('stress-1h-plus100-network',45.2,1,2.,1.,True)]

def main():
    items=[]
    for name,base,hours,multiplier,lossfactor,drain in CASES:
        intensity=round(base*multiplier,3);network=None
        if drain:
            network=GRID/'network-stress-90p4'
            if not (network/'surface-forcing.npz').exists():
                if network.exists():raise RuntimeError('Incomplete network experiment requires inspection')
                execute(build(intensity,network.name))
        folder=GRID/name
        if not (folder/'report.json').exists():
            if folder.exists():raise RuntimeError('Incomplete surface experiment requires inspection')
            run(GRID,name,hours,intensity,hours+1,network,infiltration_factor=lossfactor)
        report=json.loads((folder/'report.json').read_text())
        stress={'station_reference':'M1036 · Riobamba–ESPOCH','base_idf_intensity_mm_h':base,'base_idf_return_years':100,'duration_minutes':hours*60,'intensity_multiplier':multiplier,'intensity_mm_h':intensity,'total_rain_mm':intensity*hours,'return_period_years':None,'enso_rainfall_factor_verified':False,'infiltration_multiplier':lossfactor,'source_url':'https://www.inamhi.gob.ec/Publicaciones/Hidrologia/estudui_de_intensidades_v1_2018_1','enso_context_url':ERFEN,'classification':'Hypothetical stress test; not an ENSO forecast or a maximum physically possible flood','boundary_conditions':'Same limited local domain, dry initial surface, no external river inflow','hyetograph':'Uniform block, one hour recession'}
        report['stress']=stress;report['metadata']['rain_input']=stress
        report['limitations']=['No local ENSO multiplier has been established; rainfall perturbations are scenario assumptions.','Base reference is the historical station T100 IDF; the modified rain has no assigned return period.','No new grid convergence or field calibration; do not use for parcel or street decisions.','Zero infiltration, when selected, is a hypothetical limiting loss assumption, not a measured soil-moisture state.','No upstream flood hydrograph, river bathymetry, or bidirectional sewer feedback.']
        if drain:
            report['network']='network-stress-90p4: inferred sewer geometry, same assumed outlets and capture'
            report['network_diagnostics']=json.loads((network/'summary.json').read_text())
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        (OUT/(name+'-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        item={'id':name,'label':f'Estrés +{round((multiplier-1)*100)} % · {hours} h · '+('red estimada' if drain else 'sin infiltración ni drenaje' if lossfactor==0 else 'sin drenaje'),'rain_mm_h':intensity,'rain_hours':hours,'duration_hours':hours+1,'stats':report['stats'],'stress':stress,'report':name+'-report.json','network_diagnostics':report.get('network_diagnostics')}
        if drain:
            for src,dest in [('network.inp','stress-network.inp.gz'),('network.rpt','stress-network.rpt.gz')]:
                (OUT/dest).write_bytes(gzip.compress((network/src).read_bytes(),mtime=0))
            item.update(network_input_file='stress-network.inp.gz',network_report_file='stress-network.rpt.gz')
        items.append(item)
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    prior=[c for c in manifest['cases'] if not c['id'].startswith('stress-')]
    # Largest prescribed rainfall is first and remains explicitly hypothetical.
    cases=sorted(items,key=lambda c:0 if c['id']=='stress-1h-plus100' else 1)+prior
    archive=ROOT/'simulation-json-archive/riobamba-before-stress';archive.mkdir(exist_ok=True,parents=True)
    retired=[]
    for item in cases:
        old=item.get('file');folder=GRID/item['id']
        with np.load(folder/'result.npz') as data:
            times=data['times_minutes'];keep=[i for i,t in enumerate(times) if abs(t/30-round(t/30))<1e-6 or i==len(times)-1]
            depths=np.concatenate([data['frames'][keep],data['max_depth'][None]])
            if not np.isfinite(depths).all() or np.min(depths)<0 or np.max(depths)>655.35:raise ValueError('Invalid display range')
            # Display only: centimetres, downward quantization, 30min frames.
            # Full numerical outputs and diagnostics remain untouched locally.
            a=np.floor(depths*100+1e-6).astype('<u2');b=gzip.compress(a.tobytes(),compresslevel=9,mtime=0)
            filename=item['id']+'.display-cm30.u16.gz';(OUT/filename).write_bytes(b)
            report=json.loads((folder/'report.json').read_text());wet=[0.]+[h['wet_km2'] for h in report['hydrograph']]
            item.update(file=filename,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),depth_scale_m=.01,display_snapshot_minutes=30,display_quantization='Downward centimetres; original numerical depths retained',frame_count=len(keep),times_minutes=times[keep].tolist(),max_frame_index=len(keep),wet_km2_by_frame=[wet[i] for i in keep])
        if old and old!=filename:
            p=OUT/old
            if p.exists():
                target=archive/old
                if target.exists() and target.read_bytes()!=p.read_bytes():raise ValueError('Archive mismatch')
                target.write_bytes(p.read_bytes());retired.append(old)
    context={'retrieved':'2026-11-14','source_url':ERFEN,'report_date':'2026-11-05','report_id':'ERFEN 012-2026','enso_status':'Active in consulted report','regional_outlook':'November: normal monthly precipitation in inter-Andean valley; western slopes above normal; eastern slopes below normal. This does not determine hourly extremes in Riobamba.','multipliers_are_assumed':True,'note':'+25%, +50%, +100% are chosen sensitivity levels, not forecast changes, statistical upper bounds or assigned return periods.'}
    context['downloaded_erfen_pdf_sha256']=hashlib.sha256((ROOT/'riobamba-inputs/enso/ERFEN-20261105.pdf').read_bytes()).hexdigest()
    (OUT/'stress-context.json').write_text(json.dumps(context,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest.update(cases=cases,version='riobamba-stress-20261114-v1',stress_context='stress-context.json',display_note='Animation every 30min; display depths in centimetres. Original metric values are not rounded before area computation.')
    warning='ESTRÉS HIPOTÉTICO: aumentos de lluvia elegidos (+25/+50/+100 %) respecto a la IDF T100. No son un pronóstico de El Niño ni máximos físicos; no tienen retorno asignado.'
    manifest['notes_es']=[warning]+[n for n in manifest['notes_es'] if n!=warning]
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    retirement=OUT/'retired-browser-packages.json';existing=json.loads(retirement.read_text()) if retirement.exists() else []
    retirement.write_text(json.dumps(sorted(set(existing+retired)),indent=2))
    for name in retired:(OUT/name).unlink()
    print('Completed stress experiments',len(items),'active bytes',sum(p.stat().st_size for p in OUT.iterdir()),flush=True)

if __name__=='__main__':main()
