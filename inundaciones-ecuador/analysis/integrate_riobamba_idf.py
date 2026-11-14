"""Reproducible IDF scenarios from INAMHI tables 27 and 72 (2015 study).
Uniform design storms, not observed rain or a flood return-period assignment.
"""
import gzip,hashlib,json
from pathlib import Path
import numpy as np
from run_riobamba_cases import run
from approximate_riobamba_network import build,execute

ROOT=Path(__file__).resolve().parent
GRID=ROOT/'riobamba-runs/grid-24m'
OUT=ROOT/'dist/data/riobamba-local'
SOURCE='https://www.inamhi.gob.ec/Publicaciones/Hidrologia/estudui_de_intensidades_v1_2018_1'
STATIONS={
 'M1036':{'name':'Riobamba–ESPOCH','table':72,'printed_page':100,'intensities_mm_h':{60:[20.2,24.4,28.1,34.,39.2,45.2],120:[11.8,13.9,15.8,18.8,21.3,24.2]}},
 'M0057':{'name':'Riobamba Aeropuerto','table':27,'printed_page':55,'intensities_mm_h':{60:[14.2,16.9,19.3,22.9,26.1,29.8],120:[9.2,10.6,11.9,13.7,15.2,17.]}}}
RETURNS=[2,5,10,25,50,100]
CASES=[('M1036',60,t,False) for t in [25,10,50,100]]+[('M0057',60,25,False),('M1036',120,25,False),('M1036',60,25,True)]

def main():
    source_pdf=ROOT/'riobamba-inputs/idf/INAMHI-intensidades-final-1.pdf'
    catalog={'source_url':SOURCE,'title':'INAMHI · Determinación de ecuaciones para el cálculo de intensidades máximas de precipitación','study_year':2015,'retrieved':'2026-11-14','units':'mm/h','return_years':RETURNS,'stations':STATIONS,'downloaded_official_pdf_sha256':hashlib.sha256(source_pdf.read_bytes()).hexdigest(),'limitations':['Historical station IDF fits, not recent event measurements or a verified newest revision.','Station point intensity applied uniformly across the local domain without areal reduction.','Uniform hyetograph is an assumption; storm temporal distribution remains unverified.','Rainfall return period does not establish the return period of simulated inundation.']}
    (OUT/'inamhi-idf.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    items=[]
    for station,minutes,ret,drain in CASES:
        intensity=STATIONS[station]['intensities_mm_h'][minutes][RETURNS.index(ret)]
        name=f'idf-{station.lower()}-{minutes}min-t{ret}'+('-network' if drain else '')
        folder=GRID/name;network=None
        if drain:
            network=GRID/'network-idf-espoch-t25'
            if not (network/'surface-forcing.npz').exists():
                if network.exists():raise RuntimeError('Incomplete network run; inspect before resuming')
                execute(build(intensity,network.name))
        if not (folder/'report.json').exists():
            if folder.exists():raise RuntimeError('Incomplete simulation run; inspect before resuming')
            run(GRID,name,minutes/60,intensity,minutes/60+1,network)
        report=json.loads((folder/'report.json').read_text())
        forcing={'station':station,'station_name':STATIONS[station]['name'],'duration_minutes':minutes,'return_period_years':ret,'intensity_mm_h':intensity,'total_mm':intensity*minutes/60,'source_url':SOURCE,'source_table':STATIONS[station]['table'],'source_printed_page':STATIONS[station]['printed_page'],'temporal_distribution':'Uniform block design storm, not observed rainfall'}
        report['idf']=forcing;report['metadata']['rain_input']=forcing;report['limitations']=catalog['limitations']+['Uncalibrated terrain, infiltration, boundary and network assumptions remain.']
        if drain:report['network']='network-idf-espoch-t25: inferred geometry, 82 assumed outlets, one-way overflow';report['network_diagnostics']=json.loads((network/'summary.json').read_text())
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        (OUT/(name+'-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        with np.load(folder/'result.npz') as data:
            depth=np.concatenate([data['frames'],data['max_depth'][None]])
            if not np.isfinite(depth).all() or depth.max()>65.535:raise ValueError('Display encoding range exceeded')
            raw=np.round(depth*1000).astype('<u2').tobytes();b=gzip.compress(raw,compresslevel=9,mtime=0)
            (OUT/(name+'.u16.gz')).write_bytes(b)
            item={'id':name,'label':f"{STATIONS[station]['name']} · T{ret} · {minutes} min · "+('red estimada' if drain else 'sin drenaje'),'file':name+'.u16.gz','bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'frame_count':len(data['frames']),'max_frame_index':len(data['frames']),'times_minutes':data['times_minutes'].tolist(),'wet_km2_by_frame':[0.]+[h['wet_km2'] for h in report['hydrograph']],'stats':report['stats'],'rain_mm_h':intensity,'rain_hours':minutes/60,'duration_hours':minutes/60+1,'report':name+'-report.json','idf':forcing,'network_diagnostics':report.get('network_diagnostics')}
        if drain:
            for src,dest in [('network.inp','idf-network.inp.gz'),('network.rpt','idf-network.rpt.gz')]:
                (OUT/dest).write_bytes(gzip.compress((network/src).read_bytes(),mtime=0))
            item['network_input_file']='idf-network.inp.gz';item['network_report_file']='idf-network.rpt.gz'
        items.append(item);print('PACKED',name,len(b),flush=True)
    netfile=OUT/'network.json.gz'
    mapped=json.loads(gzip.decompress(netfile.read_bytes()))
    current_net=GRID/'network-idf-espoch-t25'
    mapped['assumptions']=json.loads((current_net/'assumptions.json').read_text())
    mapped['diagnostics']=json.loads((current_net/'summary.json').read_text())
    mapped['scenario']='ESPOCH T25, 1h, 34 mm/h; geometry shared by local comparisons'
    netfile.write_bytes(gzip.compress(json.dumps(mapped,separators=(',',':')).encode(),mtime=0))
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    reference=[c for c in manifest['cases'] if c['id'] in ['rain-1h-no-drainage','rain-1h-inferred-drainage']]
    for c in reference:c['label']='Referencia 7,10 mm/h · '+('red estimada' if 'inferred' in c['id'] else 'sin drenaje')+' · origen pendiente'
    manifest['cases']=items+reference;manifest['idf_catalog']='inamhi-idf.json';manifest['version']='riobamba-idf-20261114-v1'
    manifest['notes_es'][2]='Escenarios IDF históricos de INAMHI: duración, estación y retorno de la lluvia identificados. Hietograma uniforme supuesto; el retorno de la inundación no está determinado.'
    manifest['sensitivity']['comparison_es']='La comparación de mallas corresponde exclusivamente al caso de referencia de 7,10 mm/h; no demuestra convergencia de los nuevos escenarios IDF.'
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    # Pages is near its 1GB limit. Archive the earlier 24h browser package locally;
    # preserve its original result/report and previous Git revision.
    archive=ROOT/'simulation-json-archive/riobamba-pre-idf';archive.mkdir(parents=True,exist_ok=True)
    for name in ['rain-24h-no-drainage.u16.gz','rain-24h-no-drainage-report.json']:
        path=OUT/name
        if path.exists():
            target=archive/name
            if target.exists() and target.read_bytes()!=path.read_bytes():raise ValueError('Archive mismatch')
            target.write_bytes(path.read_bytes());path.unlink()
    if sum(p.stat().st_size for p in OUT.iterdir())>9_000_000:raise RuntimeError('Review Pages size before publishing')
    print('IDF scenarios ready',len(items),flush=True)

if __name__=='__main__':main()
