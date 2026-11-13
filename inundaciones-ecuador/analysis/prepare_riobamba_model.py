"""Prepare local rain-on-grid fields from supplied sources, preserving NoData.
Land-cover parameters are declared estimates, not local measurements.
"""
import argparse
import hashlib
import json
from pathlib import Path
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import reproject,Resampling
from scipy.ndimage import distance_transform_edt

ROOT=Path(__file__).resolve().parent
SRC=ROOT/'riobamba-inputs'
PARAMETERS={
 1:dict(name='Urbano y equipamientos',n=.08,infiltration_mm_h=.5,impervious_fraction=.8),
 2:dict(name='Agricultura y pastos',n=.05,infiltration_mm_h=5.,impervious_fraction=.1),
 3:dict(name='Forestal',n=.12,infiltration_mm_h=8.,impervious_fraction=.05),
 4:dict(name='Herbaceo y arbustivo',n=.06,infiltration_mm_h=5.,impervious_fraction=.05),
 5:dict(name='Suelo descubierto',n=.03,infiltration_mm_h=3.,impervious_fraction=.1),
 6:dict(name='Agua y cauce cartografiado',n=.035,infiltration_mm_h=0.,impervious_fraction=1.),
 7:dict(name='Invernaderos e infraestructura agropecuaria',n=.05,infiltration_mm_h=1.,impervious_fraction=.7),
 8:dict(name='Cobertura no clasificada: supuesto',n=.06,infiltration_mm_h=3.,impervious_fraction=.2)}


def category(row):
    c=str(row.get('subcategor',''));cover=str(row.get('cobertura',''))
    if c=='AGUAS INTERIORES':return 6
    if c=='TIERRA FORESTAL':return 3
    if c=='TIERRA AGROPECUARIA':return 2
    if c=='TIERRAS ARBUSTIVAS Y HERBACEAS':return 4
    if c=='TIERRA SIN COBERTURA VEGETAL' or c=='EXTRACCION':return 5
    if c=='AGROPECUARIA' or 'INVERNADERO' in cover:return 7
    if c=='RECREACION':return 4
    if c in ('ASENTAMIENTOS HUMANOS','ASOCIADO A ASENTAMIENTOS HUMANOS','COMERCIO','ALMACENAMIENTO','FABRICACION/PROCESAMIENTO','TRANSPORTE AEREO','AREAS Y/O LIMITES RESTRINGIDOS'):return 1
    return 8


def prepare(dx):
    out=ROOT/'riobamba-runs'/f'grid-{dx:g}m';out.mkdir(parents=True,exist_ok=True)
    with rasterio.open(SRC/'terreno/MDT.TIF') as src:
        width=int(np.ceil((src.bounds.right-src.bounds.left)/dx));height=int(np.ceil((src.bounds.top-src.bounds.bottom)/dx));shape=(height,width)
        tr=from_origin(src.bounds.left,src.bounds.top,dx,dx);z=np.full(shape,np.nan,np.float32)
        reproject(rasterio.band(src,1),z,src_transform=src.transform,src_crs=src.crs,src_nodata=src.nodata,dst_transform=tr,dst_crs=src.crs,dst_nodata=np.nan,resampling=Resampling.average)
        fraction=np.zeros(shape,np.float32)
        reproject(src.read_masks(1).astype(np.float32)/255,fraction,src_transform=src.transform,src_crs=src.crs,dst_transform=tr,dst_crs=src.crs,resampling=Resampling.average)
        mask=np.isfinite(z)&(fraction>=.95);crs=src.crs
    z[~mask]=0 # Numerical storage only. Excluded cells never supply elevations or water.
    cover=gpd.read_file(SRC/'cobertura/cob_uso_riobamba_a.shp').to_crs(crs)
    classes=rasterize([(r.geometry,category(r)) for _,r in cover.iterrows()],out_shape=shape,transform=tr,fill=8,dtype='uint8')
    geomorph=gpd.read_file(f'zip://{(SRC/"ANEGAMIENTO2.zip").resolve()}!geomorfologia.shp').to_crs(crs)
    river=rasterize([(g,1) for g in geomorph[geomorph.geof=='CAUCE ACTUAL'].geometry],out_shape=shape,transform=tr,fill=0,dtype='uint8')
    classes[river==1]=6
    n=np.zeros(shape);infil=np.zeros(shape);impervious=np.zeros(shape)
    for code,p in PARAMETERS.items():
        cells=classes==code;n[cells]=p['n'];infil[cells]=p['infiltration_mm_h'];impervious[cells]=p['impervious_fraction']
    # Classified source raster is a contextual layer, not an observed event or calibration target.
    a=gpd.read_file(f'zip://{(SRC/"ANEGAMIENTO2.zip").resolve()}!ANEGAMIENTO2.shp')
    aneg=rasterize([(g,{'BAJO':1,'MEDIO':2,'ALTO':3,'MUY ALTO':4}[t]) for g,t in zip(a.geometry,a.TIPO)],out_shape=shape,transform=tr,fill=0,dtype='uint8')
    basins=gpd.read_file(SRC/'caudales/CuencasHidrologicas.shp').to_crs(crs)
    basin=rasterize([(r.geometry,i+1) for i,(_,r) in enumerate(basins.iterrows())],out_shape=shape,transform=tr,fill=0,dtype='uint8')
    edge_distance=distance_transform_edt(mask)*dx
    np.savez_compressed(out/'grid.npz',dem=z,mask=mask,manning=n,infiltration_mm_h=infil,impervious_fraction=impervious,landcover=classes,channel=river,anegamiento=aneg,basin=basin,boundary_distance_m=edge_distance)
    rain=pd.read_csv(SRC/'prepared/precipitation_annual_maxima_preserved.csv');rain=rain[rain.year<2026]
    metadata={'dx_m':dx,'shape':list(shape),'crs':str(crs),'transform':list(tr)[:6],'valid_km2':float(mask.sum()*dx*dx/1e6),
              'source_dem_resolution_m':3,'minimum_valid_fraction_per_cell':.95,'landcover_source_year':2018,'estimated_parameters_by_class':PARAMETERS,
              'landcover_km2':{p['name']:float(((classes==k)&mask).sum()*dx*dx/1e6) for k,p in PARAMETERS.items()},
              'rain_input':{'years':[int(rain.year.min()),int(rain.year.max())],'max_1h_mm':float(rain.annual_max_1h_mm.max()),'max_24h_mm':float(rain.annual_max_24h_mm.max()),'median_1h_mm':float(rain.annual_max_1h_mm.median()),'source_status':'supplied annual-maxima series; station/grid provenance not verified; 2026 excluded as incomplete year'},
              'basin_codes':basins.nam.tolist(),'vertical_reference':'local source elevation frame; geodetic vertical datum unspecified; no sea-level boundary',
              'boundary_assumption':'Critical free outflow along valid-domain edges and NoData boundaries; no external catchment inflow. Interpretation near boundary is uncertain.',
              'limitations':['Parameters are estimates by 2018 land cover, not soil tests or measured impervious fractions.','Native 3m DEM averaged to calculation grid; streets and inlet details below that grid are unresolved.','No bathymetric adjustment or invented river cross-section.','Anegamiento classification is only a contextual comparison; it is not calibration with an observed event.','Daily river series are retained for hydrological context; no subhourly flood hydrograph is manufactured from them.'],
              'references':['https://www.hec.usace.army.mil/confluence/rasdocs/rmum/6.1/land-classification-layers','https://www.epa.gov/water-research/storm-water-management-model-swmm'],
              'source_sha256':{str(p.relative_to(SRC)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SRC/'terreno/MDT.TIF',SRC/'cobertura/cob_uso_riobamba_a.shp',SRC/'cobertura/cob_uso_riobamba_a.dbf',SRC/'ANEGAMIENTO2.zip',SRC/'prepared/precipitation_annual_maxima_preserved.csv']}}
    (out/'metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'folder':str(out),'shape':shape,'valid_km2':metadata['valid_km2'],'rain':metadata['rain_input']},indent=2))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dx',type=float,default=24);a=p.parse_args();prepare(a.dx)
