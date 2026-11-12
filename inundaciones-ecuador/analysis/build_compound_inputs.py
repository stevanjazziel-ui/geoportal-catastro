"""Publish auditable source subsets; do not manufacture hydraulic readiness."""
import hashlib
import json
from pathlib import Path
import sys
import shutil
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.deps'))
import pandas as pd


def main():
    raw=ROOT/'raw/compound-acquisition';out=ROOT/'dist/data/compound';out.mkdir(parents=True,exist_ok=True)
    tide=pd.read_csv(raw/'inocar-predictions-resource2026.csv',sep=';',skiprows=1)
    tide=tide[tide.FECHA.notna()].dropna(axis=1,how='all')
    dt=pd.to_datetime(tide.FECHA)
    if dt.duplicated().any() or not (dt.diff().dropna()==pd.Timedelta(hours=1)).all():raise ValueError('Incomplete/duplicate tidal timeline')
    if not np.isfinite(tide.iloc[:,1:].to_numpy(float)).all():raise ValueError('Missing tide predictions')
    tides={'source':'INOCAR / Datos Abiertos Ecuador','license':'CC BY','kind':'predicted_not_observed','reference':'MLWS',
           'timezone':'not_explicit_in_downloaded_dictionary; verify before joining with UTC inputs',
           'original_units':'cm; confirmed by official data dictionary DD-INOCAR-CDA-003-2021-V01','units':'m','conversion':'original / 100',
           'dates':tide.FECHA.tolist(),'stations':{c:(tide[c]/100).round(2).tolist() for c in tide.columns if c!='FECHA'},
           'source_url':'https://www.datosabiertos.gob.ec/dataset/altura-horaria-predicha-de-mareas'}
    (out/'tides2026.json').write_text(json.dumps(tides,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    df=pd.read_parquet(raw/'geoglows-metadata.parquet')
    df=df[df.lon.between(-81.5,-75)&df.lat.between(-5.2,1.8)].copy()
    cities=json.loads((ROOT/'dist/data/cities.json').read_text(encoding='utf-8'))['cities']
    flows=[]
    for file in sorted(raw.glob('forecast-*.json')):
        d=json.loads(file.read_text());q=np.asarray(d['flow_median'],float);ts=pd.to_datetime(d['datetime'],utc=True)
        if len(q)!=len(ts) or not np.isfinite(q).all() or np.any(q<0) or ts.duplicated().any() or not ts.is_monotonic_increasing:raise ValueError('Invalid discharge series')
        if d['metadata']['units']['short']!='cms':raise ValueError('Unknown discharge units')
        d['source_url']=f"https://geoglows.ecmwf.int/api/v2/forecast/{d['metadata']['river_id']}?format=json"
        d['association_status']='nearest_outlet_candidate_not_verified_hydraulic_inlet'
        flows.append(d)
    available={x['metadata']['river_id'] for x in flows}
    rows=[]
    for c in cities:
        distance=6371*2*np.arcsin(np.sqrt(np.sin(np.deg2rad(df.lat-c['lat'])/2)**2+np.cos(np.deg2rad(c['lat']))*np.cos(np.deg2rad(df.lat))*np.sin(np.deg2rad(df.lon-c['lon'])/2)**2))
        ix=distance.nsmallest(3).index
        candidates=[{'river_id':int(df.loc[i,'LINKNO']),'vpu':int(df.loc[i,'VPUCode']),'lon':float(df.loc[i,'lon']),'lat':float(df.loc[i,'lat']),'distance_km':round(float(distance[i]),3),'flow_downloaded':int(df.loc[i,'LINKNO']) in available} for i in ix if distance[i]<=30]
        rows.append({'id':c['id'],'name':c['name'],'river_candidates':candidates,'river_assignment_verified':False,'compound_model_ready':False,
                     'pending':['verified_inlet_assignment','channel_sections_and_structures','terrain_vertical_reference','local_network_geometry_and_capacities','validation_observations'],
                     'coastal_requirement':'If tidal boundary applies: bathymetry, MLWS-to-terrain leveling, time-zone verification and initial water state.'})
    swmm=json.loads((ROOT/'swmm-verification/verified-export/summary.json').read_text())
    swmm['input']='EPA-Example2.inp';swmm['source_url']='https://github.com/USEPA/swmm-nrtestsuite/blob/dev/public/examples/Example2.inp'
    shutil.copyfile(ROOT/'swmm-verification/verified-export/network.rpt',out/'swmm-epa-network.rpt')
    doc={'date':'2026-11-12','cities':rows,'flows':flows,'swmm_verification':swmm,
         'counts':{'cities':len(rows),'regional_outlets_bbox':len(df),'tidal_stations':len(tides['stations']),'tidal_hourly_records_per_station':len(tide),'downloaded_candidate_hydrographs':len(flows)},
         'limitations':['No new calibrated city flood model. Existing 76 rain runs unchanged.','River selection uses nearest outlet distance only. It does not identify the main river or upstream boundary.','Do not treat GEOGLOWS forecasts as observed discharge or transfer one port tide to all coastal cities.'],
         'provenance':json.loads((raw/'acquisition-manifest.json').read_text()),
         'licenses':{'INOCAR':'CC BY, official CKAN catalog','GEOGLOWS':'https://geoglows.ecmwf.int/license','EPA_example':'US Government public example; numerical verification only'},
         'additional_inputs_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [raw/'inocar-dictionary.ods',raw/'EPA-Example2.inp',*sorted(raw.glob('forecast-*.json'))]}}
    (out/'inputs.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(doc['counts'],indent=2))


if __name__=='__main__':main()
