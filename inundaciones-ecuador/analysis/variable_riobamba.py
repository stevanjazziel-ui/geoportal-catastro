"""Six-hour, 10min alternating-block design storms; 12h calculations.
INAMHI ESPOCH table72, historical IDF, not reconstructed METAR events.
"""
import argparse,json,gzip,hashlib
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from affine import Affine
from run_riobamba_cases import run
from approximate_riobamba_network import build,execute

ROOT=Path(__file__).resolve().parent
GRID=ROOT/'riobamba-runs/grid-24m'
OUT=ROOT/'dist/data/riobamba-local'
DURATIONS=np.array([10,15,20,30,60,120,360],float)
INTENSITIES={25:[103.4,85.3,74.5,60.8,34.,18.8,7.1],50:[119.6,98.7,86.2,70.1,39.2,21.3,8.1],100:[138.4,114.2,99.7,80.9,45.2,24.2,9.2]}

def hyetograph(ret):
    depths=np.array(INTENSITIES[ret])*DURATIONS/60
    time=np.arange(10,361,10)
    cumulative=np.exp(np.interp(np.log(time),np.log(DURATIONS),np.log(depths)))
    blocks=np.diff(np.r_[0,cumulative]);assert (blocks>=0).all()
    ranked=np.sort(blocks)[::-1];order=[18]
    for k in range(1,36):
        for ix in (18-k,18+k):
            if 0<=ix<36 and ix not in order:order.append(ix)
    arranged=np.zeros(36);arranged[order]=ranked
    comparisons=[]
    for dur in [10,20,30,60,120,360]:
        expected=float(np.exp(np.interp(np.log(dur),np.log(DURATIONS),np.log(depths))))
        actual=float(np.convolve(arranged,np.ones(dur//10),'valid').max())
        comparisons.append({'minutes':dur,'reference_depth_mm':expected,'hyetograph_max_depth_mm':actual,'relative_difference':(actual-expected)/expected})
    if max(abs(c['relative_difference']) for c in comparisons)>.02:raise ValueError('Nested storm inconsistent with reference by over 2%')
    return {'station':'M1036 · Riobamba–ESPOCH','return_period_years':ret,'duration_minutes':360,'interval_minutes':10,'seconds':list(range(0,21600,600))+[21600],'intensities_mm_h':(arranged*6).tolist()+[0.],'total_mm':float(arranged.sum()),'peak_mm_h':float(arranged.max()*6),'peak_start_minutes':180,'peak_end_minutes':190,'duration_checks':comparisons,'source_url':'https://www.inamhi.gob.ec/Publicaciones/Hidrologia/estudui_de_intensidades_v1_2018_1','source_table':72,'source_printed_page':100,'method':'Log-log depth interpolation, successive differences, descending alternating blocks around central peak.','method_reference':'https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/meteorology/precipitation/frequency-storm','areal_reduction_factor':1.,'limitations':['Historical point IDF applied uniformly over the local domain; no locally verified areal reduction.','Synthetic temporal pattern; not a reconstruction of the airport METAR sequence.','Nested design durations do not establish joint storm or flood exceedance probability.']}

def conservative_series(q,block_seconds=600,duration=43200):
    q=np.asarray(q,float);times=[0.];values=[q[0].copy()]
    for k in range(len(q)):
        times.extend([(k+1)*block_seconds-1.,(k+1)*block_seconds])
        values.extend([q[k].copy(),q[k+1].copy() if k+1<len(q) else np.zeros(q.shape[1])])
    times.append(float(duration));values.append(np.zeros(q.shape[1]));values=np.array(values)
    target=q.sum(axis=0)*block_seconds;actual=np.sum((values[:-1]+values[1:])*.5*np.diff(times)[:,None],axis=0)
    factors=np.divide(target,actual,out=np.ones_like(target),where=actual>0);values*=factors
    integral=np.sum((values[:-1]+values[1:])*.5*np.diff(times)[:,None],axis=0)
    if not np.allclose(integral,target,atol=1e-7,rtol=1e-10):raise ValueError('Input hydrograph volume mismatch')
    return np.array(times),values,float(np.max(abs(factors-1)))

def network_for(ret,h,folder_name=None,duration_hours=12):
    folder=GRID/(folder_name or f'network-variable-t{ret}')
    if (folder/'surface-forcing.npz').exists():return folder
    if folder.exists():raise RuntimeError('Inspect incomplete network before resuming')
    build(h['peak_mm_h'],folder.name)
    with np.load(folder/'network-data.npz') as f:nodes=f['nodes'].copy();captured=f['captured_mask'].copy()
    meta=json.loads((GRID/'metadata.json').read_text())
    with np.load(GRID/'grid.npz') as f:loss=f['infiltration_mm_h'].copy()
    rr,cc=np.nonzero(captured);xx,yy=Affine(*meta['transform'])*(cc+.5,rr+.5)
    nearest=cKDTree(nodes[:,:2]).query(np.c_[xx,yy])[1]
    q=np.array([np.bincount(nearest,weights=np.maximum(0,r-loss[rr,cc])/3600000*meta['dx_m']**2,minlength=len(nodes)) for r in h['intensities_mm_h'][:-1]])
    times,values,correction=conservative_series(q,duration=duration_hours*3600)
    inp=(folder/'network.inp').read_text();head=inp.split('[TIMESERIES]')[0].replace('END_TIME 02:00:00',f'END_TIME {int(duration_hours):02d}:00:00')
    lines=[head,'[TIMESERIES]']
    for i in range(len(nodes)):
        if not q[:,i].any():continue
        for t,v in zip(times,values[:,i]):
            sec=int(t);clock=f'{sec//3600:02d}:{sec%3600//60:02d}:{sec%60:02d}'
            lines.append(f'R{i} 01/01/2020 {clock} {v:.12g}')
    lines+=['[REPORT]','NODES NONE','LINKS NONE']
    (folder/'network.inp').write_text('\n'.join(lines)+'\n')
    assumptions=json.loads((folder/'assumptions.json').read_text());assumptions.update(rainfall_mm_h=None,rain_profile=h,model_end_seconds=duration_hours*3600,input_runoff_m3=float(q.sum()*600),max_input_normalization_fraction=correction)
    assumptions['assumptions']=[a for a in assumptions['assumptions'] if 'One-minute rainfall-input ramp' not in a]
    assumptions['assumptions'].append('Runoff from each 10min rain block; 1s linear transitions, nodewise volume normalization. The same block rain and losses are used on captured and uncaptured cells.')
    (folder/'assumptions.json').write_text(json.dumps(assumptions,indent=2));execute(folder)
    return folder

def calculate(ret):
    h=hyetograph(ret);(GRID/f'hyetograph-t{ret}.json').write_text(json.dumps(h,ensure_ascii=False,indent=2),encoding='utf-8')
    for drainage in [False,True]:
        network=network_for(ret,h) if drainage else None
        name=f'variable-6h-t{ret}'+('-network' if drainage else '')
        folder=GRID/name
        if not (folder/'report.json').exists():
            if folder.exists():raise RuntimeError('Inspect incomplete surface run')
            run(GRID,name,6,h['total_mm']/6,12,network,rain_profile=np.c_[h['seconds'],h['intensities_mm_h']],snapshot_minutes=30)
        r=json.loads((folder/'report.json').read_text());r['hyetograph']=h;r['metadata']['rain_input']=h;r['total_rain_mm']=h['total_mm'];r['rain_mm_h_is_mean']=True
        r['limitations']=h['limitations']+['Uncalibrated, 24m local mesh; no new convergence demonstration.','Assumed soil losses, hydraulic edges, inverts, outlets and capture remain.','One-way sewer overflow only; no surface feedback.']
        volume=np.array([i['volume_m3'] for i in r['hydrograph']]);last=r['hydrograph'][-1]
        r['recession']={'rain_end_hours':6,'simulation_end_hours':12,'recession_hours':6,'volume_at_6h_m3':next(i['volume_m3'] for i in r['hydrograph'] if i['minutes']==360),'final_volume_m3':float(last['volume_m3']),'final_fraction_of_peak_volume':float(volume[-1]/max(1,volume.max())),'interpretation':'12h finite window; residual ponding may persist. Not a demonstration of complete drainage.'}
        if network:r['network_diagnostics']=json.loads((network/'summary.json').read_text());r['network']='Inferred network with volume-normalized variable inputs, same 6h storm, 12h routing.'
        (folder/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print('RETURN COMPLETE',ret,flush=True)

def diagnostics():
    h=hyetograph(25)
    for folder,name,lossfactor in [(ROOT/'riobamba-runs/grid-48m','variable-6h-t25',1.),(GRID,'variable-6h-t25-zero-loss',0.)]:
        out=folder/name
        if not (out/'report.json').exists():
            if out.exists():raise RuntimeError('Inspect incomplete diagnostic')
            run(folder,name,6,h['total_mm']/6,12,infiltration_factor=lossfactor,rain_profile=np.c_[h['seconds'],h['intensities_mm_h']],snapshot_minutes=30)
        r=json.loads((out/'report.json').read_text());r.update(hyetograph=h,rain_mm_h_is_mean=True)
        r['metadata']['rain_input']=h;r['limitations']=h['limitations']+['Diagnostic sensitivity, not field validation. Zero infiltration, when used, is hypothetical.']
        v=np.array([i['volume_m3'] for i in r['hydrograph']])
        r['recession']={'rain_end_hours':6,'simulation_end_hours':12,'recession_hours':6,'volume_at_6h_m3':next(i['volume_m3'] for i in r['hydrograph'] if i['minutes']==360),'final_volume_m3':float(v[-1]),'final_fraction_of_peak_volume':float(v[-1]/max(1,v.max())),'interpretation':'Finite window, not complete drainage.'}
        (out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    print('DIAGNOSTICS COMPLETE',flush=True)

def pack():
    m=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'));items=[]
    archive=ROOT/'model-archives';archive.mkdir(exist_ok=True)
    for ret in [25,50,100]:
        for mode in ['none','network']+(['zero-loss'] if ret==25 else []):
            drainage=mode=='network';zero=mode=='zero-loss'
            name=f'variable-6h-t{ret}'+('-network' if drainage else '-zero-loss' if zero else '');folder=GRID/name;r=json.loads((folder/'report.json').read_text());h=r['hyetograph'];r['rain_mm_h_is_mean']=True
            r['recession']['peak_volume_sampling_minutes']=30
            domain_rain=h['total_mm']/1000*m['valid_km2']*1e6
            partition={'uniform_domain_rain_m3':domain_rain,'direct_rain_2d_m3':r['stats']['direct_rain_m3']}
            if drainage:
                net=GRID/f'network-variable-t{ret}';a=json.loads((net/'assumptions.json').read_text())
                capture_rain=h['total_mm']/1000*a['captured_km2']*1e6
                partition.update(captured_excess_input_swmm_m3=a['input_runoff_m3'],captured_rain_losses_m3=capture_rain-a['input_runoff_m3'])
                partition['rain_partition_residual_m3']=domain_rain-partition['direct_rain_2d_m3']-capture_rain
                with np.load(net/'surface-forcing.npz') as f:
                    if abs(float(f['seconds'][-1])-43200)>1e-5:raise ValueError('Truncated network forcing')
                    exported=float(np.sum(f['rates_m3_s'][1:]*np.diff(f['seconds'])[:,None]))
                if abs(exported-r['stats']['prescribed_overflow_m3'])>1e-4:raise ValueError('Overflow transfer volume mismatch')
                partition['overflow_transferred_m3']=exported
            else:partition['rain_partition_residual_m3']=domain_rain-partition['direct_rain_2d_m3']
            if abs(partition['rain_partition_residual_m3'])>.01:raise ValueError('Rain counted twice or missing')
            r['rain_partition']=partition
            (OUT/(name+'-report.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
            with np.load(folder/'result.npz') as f:
                ix=[i for i,t in enumerate(f['times_minutes']) if t%60==0];a=np.concatenate([f['frames'][ix],f['max_depth'][None]])
                if a.max()>655.35:raise ValueError('Display range exceeded')
                b=gzip.compress(np.floor(a*100+1e-6).astype('<u2').tobytes(),compresslevel=9,mtime=0);filename=name+'.display-cm60.u16.gz';(OUT/filename).write_bytes(b)
                wet=[0.]+[i['wet_km2'] for i in r['hydrograph']]
                item={'id':name,'label':f'Variable 6 h · ESPOCH T{ret} · '+('red estimada' if drainage else 'infiltración nula' if zero else 'sin drenaje'),'file':filename,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'depth_scale_m':.01,'display_snapshot_minutes':60,'frame_count':len(ix),'max_frame_index':len(ix),'times_minutes':f['times_minutes'][ix].tolist(),'wet_km2_by_frame':[wet[i] for i in ix],'stats':r['stats'],'rain_mm_h':h['total_mm']/6,'rain_mm_h_is_mean':True,'total_rain_mm':h['total_mm'],'rain_hours':6,'duration_hours':12,'hyetograph':h,'recession':r['recession'],'infiltration_multiplier':r['infiltration_multiplier'],'network_diagnostics':r.get('network_diagnostics'),'report':name+'-report.json'}
            if drainage:
                for kind in ['inp','rpt']:
                    fn=f'variable-t{ret}-network.{kind}.gz'
                    destination=archive/fn
                    destination.write_bytes(gzip.compress((GRID/f'network-variable-t{ret}'/f'network.{kind}').read_bytes(),mtime=0))
                    item['network_input_file' if kind=='inp' else 'network_report_file']='https://raw.githubusercontent.com/stevanjazziel-ui/geoportal-catastro/main/inundaciones-ecuador/model-archives/'+fn
            items.append(item)
    m['cases']=items+[c for c in m['cases'] if not c['id'].startswith('variable-6h-')];m['version']='riobamba-variable6h-20261114-v1'
    note='Lluvias variables de diseño de 6h: bloques alternos de 10min, pico central; simulación 12h con 6h de recesión. No reconstruyen los METAR ni un evento observado.'
    m['notes_es']=[note]+[n.replace('Hietograma uniforme supuesto; el retorno de la inundación no está determinado.','Hietogramas de diseño identificados como uniformes o variables; el retorno de la inundación no está determinado.') for n in m['notes_es'] if n!=note]
    coarse=json.loads((ROOT/'riobamba-runs/grid-48m/variable-6h-t25/report.json').read_text())
    fine=items[0]
    sensitivity={'scenario':'Variable 6h ESPOCH T25, no sewer','area_24m_km2':fine['stats']['max_footprint_km2'],'area_48m_km2':coarse['stats']['max_footprint_km2'],'area_change_percent':100*(coarse['stats']['max_footprint_km2']/fine['stats']['max_footprint_km2']-1),'max_depth_24m_m':fine['stats']['max_depth_m'],'max_depth_48m_m':coarse['stats']['max_depth_m'],'valid_24m_km2':m['valid_km2'],'valid_48m_km2':coarse['metadata']['valid_km2'],'interpretation':'Two-grid sensitivity of this event only; valid masks also differ. No demonstrated spatial convergence or field validation.'}
    m['variable_sensitivity']=sensitivity
    (OUT/'variable-grid-sensitivity.json').write_text(json.dumps(sensitivity,indent=2))
    source=ROOT/'riobamba-inputs/rain-duration'
    for fn in ['duration-evidence.json','observations_selected_local.csv']:
        (OUT/fn).write_bytes((source/fn).read_bytes())
    m['duration_evidence']='duration-evidence.json'
    (OUT/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8');print('PACKED',len(items),'cases; total bytes',sum(p.stat().st_size for p in OUT.iterdir()))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--return-years',type=int,choices=[25,50,100]);p.add_argument('--pack',action='store_true');p.add_argument('--diagnostics',action='store_true');a=p.parse_args()
    if a.pack:pack()
    elif a.diagnostics:diagnostics()
    else:calculate(a.return_years or 25)
