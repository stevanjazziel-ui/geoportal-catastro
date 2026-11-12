"""Read-only source audit and GIS preparation for supplied Riobamba inputs.
No pipe inverts, roughness, terrain datum or missing diameter is invented.
"""
import collections
import argparse
from datetime import datetime,timedelta
import hashlib
import json
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET
import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio
from shapely.geometry import LineString,Point
from scipy.spatial import cKDTree

ROOT=Path(__file__).resolve().parent
SRC=ROOT/'riobamba-inputs'
OUT=SRC/'prepared'


def workbook_rows(path):
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as z:
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        strings=[''.join(x.itertext()) for x in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns)] if 'xl/sharedStrings.xml' in z.namelist() else []
        rows=[]
        for r in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('.//m:row',ns):
            cells={}
            for c in r:
                v=c.find('m:v',ns);v=v.text if v is not None else ''.join(c.itertext())
                cells[re.sub('[0-9]','',c.get('r'))]=strings[int(v)] if c.get('t')=='s' else v
            rows.append(cells)
        properties=wb.find('m:workbookPr',ns)
        epoch=datetime(1904,1,1) if properties is not None and properties.get('date1904') in ('1','true') else datetime(1899,12,30)
        return rows,epoch


def main(output=None):
    OUT=Path(output).resolve() if output else SRC/'prepared'
    if not OUT.is_relative_to(ROOT):raise ValueError('Keep audit outputs inside this project')
    OUT.mkdir(parents=True,exist_ok=True)
    data=json.loads((SRC/'portal-network-original.json').read_text(encoding='utf-8'))
    origin=np.asarray(data['o']);records=[];ends=collections.defaultdict(list)
    for i,r in enumerate(data['s']):
        p0=origin+np.asarray(r[:2]);p1=origin+np.asarray(r[2:4]);ends[r[7]].append(p0);ends[r[8]].append(p1)
        records.append({'id':i,'node_from':r[7],'node_to':r[8],'diameter_mm':float(r[4]) if r[4]>0 else None,
                        'system':('combinado','pluvial','colector')[r[5]],'upstream_segment_count':r[6],'direction_questioned':bool(r[9]),'diameter_source_code':r[11],
                        'collector':data['cn'][r[10]] if r[10]<len(data['cn']) else None,'endpoint_chord_m':float(np.linalg.norm(p1-p0)),
                        'geometry':LineString([p0,p1])})
    # Interpreted from the portal's explicit WGS84 / central meridian -81 / south UTM formula.
    pipes=gpd.GeoDataFrame(records,crs='EPSG:32717')
    gpkg=OUT/'riobamba-preparacion.gpkg'
    if gpkg.exists():raise FileExistsError('Preserve the previous audit: use a new prepared directory')
    pipes.to_file(gpkg,layer='red_portal',driver='GPKG')
    nodes=gpd.GeoDataFrame([{'id':k,'endpoint_spread_m':float(np.max(np.linalg.norm(np.asarray(v)-v[0],axis=1))),'invert_m':None,'cover_m':None,'geometry':Point(v[0])} for k,v in ends.items()],crs=pipes.crs)
    nodes.to_file(gpkg,layer='nodos_sin_cotas_asignadas',driver='GPKG')
    for tag,name in [('c','cotas_CAD_sin_clasificar'),('h','anotaciones_hidraulicas')]:
        a=gpd.GeoDataFrame([{'source_index':i,'text':str(t[3]),'angle_source':t[2],'geometry':Point(origin+np.asarray(t[:2]))} for i,t in enumerate(data['cad']['tx']) if t[-1]==tag],crs=pipes.crs)
        a.to_file(gpkg,layer=name,driver='GPKG')
    basins=gpd.read_file(SRC/'caudales/CuencasHidrologicas.shp');basins.to_file(gpkg,layer='cuencas_originales',driver='GPKG')
    culverts=gpd.read_file(SRC/'cartografia/Alcantarillado.shp');culverts.to_file(gpkg,layer='alcantarillas_cartografia',driver='GPKG')
    path=f'zip://{(SRC/"ANEGAMIENTO2.zip").resolve()}!ANEGAMIENTO2.shp'
    info=pyogrio.read_info(path);attributes=pyogrio.read_dataframe(path,columns=['TIPO','M2'],read_geometry=False)
    aneg={'features':int(info['features']),'crs':info['crs'],'bounds':list(info['total_bounds']),'classes':attributes.TIPO.value_counts(dropna=False).to_dict(),
          'interpretation':'Classified anegamiento layer. Event date, depth and method are not established by the inspected fields; not a measured flood footprint.'}
    with rasterio.open(SRC/'terreno/MDT.TIF') as r:
        z=r.read(1,masked=True)
        terrain={'file':'terreno/MDT.TIF','shape':list(r.shape),'crs':str(r.crs),'resolution_m':list(r.res),'bounds':list(r.bounds),'nodata':r.nodata,
                 'valid_percent':float(z.count()/z.size*100),'elevation_min':float(z.min()),'elevation_max':float(z.max()),
                 'vertical_datum':'Not specified in inspected TIFF or XML. SIRGAS 2000 / UTM 17S identifies horizontal reference only.',
                 'lineage':'Metadata creation/synchronization date is not a verified survey/acquisition date.'}
        projected_nodes=nodes.to_crs(r.crs)
        samples=list(r.sample([(p.x,p.y) for p in projected_nodes.geometry],masked=True))
        terrain_valid=np.asarray([not np.ma.is_masked(v[0]) and np.isfinite(v[0]) and float(v[0])!=r.nodata for v in samples])
        ground=[float(v[0]) if ok else None for v,ok in zip(samples,terrain_valid)]
    cotas=gpd.read_file(gpkg,layer='cotas_CAD_sin_clasificar')
    distances,index=cKDTree([(p.x,p.y) for p in cotas.geometry]).query([(p.x,p.y) for p in nodes.geometry],k=2)
    candidates=[]
    for i,row in nodes.iterrows():
        if distances[i,0]>5:continue
        c=cotas.iloc[index[i,0]]
        candidates.append({'node_id':row.id,'annotation_index':int(c.source_index),'annotation_text':c.text,'distance_m':float(distances[i,0]),
                           'second_annotation_distance_m':float(distances[i,1]),'terrain_z':ground[i],'elevation_role':'UNCLASSIFIED_DO_NOT_ASSIGN_AS_INVERT','endpoint_spread_m':row.endpoint_spread_m})
    pd.DataFrame(candidates).to_csv(OUT/'cotas_candidatas_revision.csv',index=False)
    rows,epoch=workbook_rows(SRC/'caudales/caudales_H789 Chibunga.xlsx')
    flow=pd.DataFrame([{'date':(epoch+timedelta(days=float(r['A']))).date().isoformat(),'value_raw':r.get('C'),'origin_raw':r.get('D')} for r in rows[1:] if r.get('A')])
    flow['value']=pd.to_numeric(flow.value_raw,errors='coerce');flow.to_csv(OUT/'chibunga_H0789_daily_preserved.csv',index=False)
    flow_report={'sheet':'Caudal_Chibunga','rows':len(flow),'start':flow.date.min(),'end':flow.date.max(),'missing_values':int(flow.value.isna().sum()),'negative_values':int((flow.value<0).sum()),
                 'origin_counts':flow.origin_raw.value_counts(dropna=False).to_dict(),'min':float(flow.value.min()),'max':float(flow.value.max()),'duplicate_dates':int(flow.date.duplicated().sum()),
                 'units':'Not explicit in inspected header; verify m3/s and origin-code definitions before using as boundary or calibration.',
                 'origin_handling':'H and PDM preserved separately. Do not assume all rows are gauge observations.'}
    rows,_=workbook_rows(SRC/'clima/PrecipitacionMax.xlsx');rain=pd.DataFrame([{'year':r.get('A'),'annual_max_24h_mm':r.get('B'),'annual_max_1h_mm':r.get('C')} for r in rows[1:] if r.get('A')])
    rain.to_csv(OUT/'precipitation_annual_maxima_preserved.csv',index=False)
    rain_report={'sheet':'Sheet1','rows':len(rain),'first_year':int(pd.to_numeric(rain.year).min()),'last_year':int(pd.to_numeric(rain.year).max()),
                 'kind':'Annual maxima of accumulated 24h and 1h precipitation; not a storm hyetograph.',
                 'limitations':'Station/grid source, observation versus reanalysis and annual completeness need verification. Do not infer subhourly intensities from these maxima alone.'}
    retro=pd.read_csv(SRC/'caudales/retr0620828722.csv',sep=';')
    retro_dates=pd.to_datetime(dict(year=retro.Anio,month=retro.Mes,day=retro.Dia))
    retro_report={'rows':len(retro),'start':str(retro_dates.min().date()),'end':str(retro_dates.max().date()),'duplicate_dates':int(retro_dates.duplicated().sum()),'provenance':'CSV lacks station identity/units in inspected header. Do not assume the same support or provenance as H0789.'}
    report={'city':'Riobamba','date':'2026-11-12','source_urls':['https://alva-piva-ayuda.vercel.app/alcantarillado/','https://drive.google.com/drive/folders/1f5qi1zbSJl6g9J0IG5x0AOOkJef4ZPcO','https://drive.google.com/drive/folders/1GCHBInV71GKNds_kdjOS1FIEFK30fXuT'],
            'network':{'segments':len(pipes),'nodes':len(nodes),'system_counts':pipes.system.value_counts().to_dict(),'missing_diameters':int(pipes.diameter_mm.isna().sum()),'questioned_directions':int(pipes.direction_questioned.sum()),
                       'nodes_with_endpoint_spread_over_0_2m':int((nodes.endpoint_spread_m>.2).sum()),'cota_annotations_unassigned':sum(t[-1]=='c' for t in data['cad']['tx']),
                       'hydraulic_annotations_unassigned':sum(t[-1]=='h' for t in data['cad']['tx']),'crs_interpretation':'EPSG:32717 inferred from the portal projection formula; compare against original CAD/geodetic metadata.',
                       'nodes_over_valid_local_terrain':int(terrain_valid.sum()),'nodes_outside_valid_local_terrain':int((~terrain_valid).sum()),'nodes_with_cota_candidate_within_5m':len(candidates),
                       'candidate_assignment':'Nearest CAD annotation within 5m; not assigned as invert or cover; review ambiguity and reference.',
                       'visualization_fallback':'Portal uses r[4] || 800 for rendering. Missing diameters remain NULL here; 800 mm is not adopted as a measured value.',
                       'missing':['verified invert and cover elevations','node types and outfalls','roughness and material definitions','inlet capacities and connections','verified operating direction and geometry','source dates and asset status']},
            'cartographic_culverts':{'features':len(culverts),'fields':list(culverts.drop(columns='geometry').columns),'meaning':'AQ065 cartographic crossing/evacuation structures; not the 6359-segment sewer network.'},
            'terrain':terrain,'anegamiento':aneg,'chibunga':flow_report,'precipitation':rain_report,'other_flow_csv':retro_report,
            'ready_for':'GIS integration, terrain visualization and engineering-data reconciliation','ready_for_calibrated_swmm':False,
            'sha256':{str(p.relative_to(SRC)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(SRC.rglob('*')) if p.is_file() and (p.parent==SRC or p.relative_to(SRC).parts[0] in ('caudales','clima','terreno','cartografia'))}}
    (OUT/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['network','terrain','chibunga','precipitation','other_flow_csv']},ensure_ascii=True,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output');a=p.parse_args();main(a.output)
