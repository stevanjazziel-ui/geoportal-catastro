"""Reproducible exploratory Pita boundary scenarios using the official Kestrel solver."""
from pathlib import Path
import os, sys, json, hashlib, subprocess, argparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.deps'))
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling
import gzip
from pyproj import Transformer

ROOT=Path(__file__).resolve().parent
ENGINE=ROOT/'tools/kestrel/src/kestrel.exe'
ENVROOT=ROOT/'tools/msys64/ucrt64'
VOLUMES={'menor':10_000_000,'grande':30_000_000,'mayor':60_000_000}

def env():
    e=os.environ.copy()
    e.update(PATH=str(ENVROOT/'bin')+os.pathsep+e.get('PATH',''),
        GDAL_DATA=str(ENVROOT/'share/gdal'),PROJ_DATA=str(ENVROOT/'share/proj'),
        OMP_NUM_THREADS=str(min(4,max(1,int(os.environ.get('LAHAR_THREADS','2'))))),OMP_WAIT_POLICY='passive',OMP_SCHEDULE='dynamic')
    return e

def setup():
    inputs=ROOT/'inputs'; inputs.mkdir(exist_ok=True)
    # Published river sampling point 4 (Chorro contribution to Pita), 2019 table 1.
    lon=-(78+25/60+57.86/3600); lat=-(29/60+9.73/3600)
    to_utm=Transformer.from_crs(4326,32717,always_xy=True)
    to_geo=Transformer.from_crs(32717,4326,always_xy=True)
    x,y=to_utm.transform(lon,lat)
    with rasterio.open(ROOT/'prepared/cotopaxi_norte_30m_contexto.tif') as ds:
        r,c=ds.index(x,y); z=ds.read(1)
        candidates=[]
        for rr in range(r-4,r+5):
            for cc in range(c-4,c+5):
                xx,yy=ds.xy(rr,cc); distance=np.hypot(xx-x,yy-y)
                if distance<=120:candidates.append((float(z[rr,cc]),distance,xx,yy))
        altitude,distance,sx,sy=min(candidates)
    slon,slat=to_geo.transform(sx,sy)
    # Rectangle inside the downloaded terrain, including Sangolqui and lower Pita.
    west,south,width,height=775500.,9943500.,24600.,55500.
    # Extend northward beyond the municipal reference to keep the flow away from
    # the edge during the requested 150 minutes. No artificial outlet is imposed.
    hgt=np.frombuffer(gzip.decompress((ROOT/'sources/S01W079.hgt.gz').read_bytes()),'>i2').reshape(3601,3601).astype(np.float32)
    model_dem=np.full((1850,820),-32768,np.float32)
    dst=from_origin(west,south+height,30,30)
    reproject(hgt,model_dem,src_transform=from_origin(-79-1/7200,1/7200,1/3600,1/3600),
              src_crs=4326,dst_transform=dst,dst_crs=32717,src_nodata=-32768,dst_nodata=-32768,
              resampling=Resampling.bilinear)
    assert np.isfinite(model_dem).all() and (model_dem!=-32768).all()
    with rasterio.open(ROOT/'prepared/pita_domain_30m.tif','w',driver='GTiff',height=1850,width=820,
        count=1,dtype='float32',crs=32717,transform=dst,nodata=-32768,compress='deflate',predictor=3) as ds:ds.write(model_dem,1)
    clon,clat=to_geo.transform(west+width/2,south+height/2)
    info={'calibrated':False,'scenario_type':'hypothetical upstream mixed-flow boundary',
       'not_a_reproduction_of_1877':True,'source_reference':{
       'url':'https://portal.amelica.org/ameli/journal/157/157776005/html/',
       'table':'Table 1 point 4; geographic river location only, not a lahar hydrograph',
       'original_lon':lon,'original_lat':lat,'model_lon':slon,'model_lat':slat,
       'snap_m':float(distance),'snap_rule':'minimum DEM elevation within 120 m',
       'elevation_m':altitude},'domain_utm17s':[west,south,west+width,south+height],
       'assumptions':{'solid_fraction':0.4,'source_radius_m':100,'peak_s':150,'release_end_s':900,
       'volume_is_total_mixture':True,'duration_s':9000,'building_obstacles':False,
       'roughness_calibrated_locally':False},'engine_sha256':hashlib.sha256(ENGINE.read_bytes()).hexdigest(),
       'engine_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'tools/kestrel',text=True).strip(),
       'cases':[]}
    for dx in (60,30):
      for name,volume in VOLUMES.items():
        case=f'{name}-{dx}m';out=ROOT/'runs'/case
        q=2*volume/900
        text=f'''# Exploratory mixture inflow at upper Pita. Not a forecast or calibrated eruption scenario.
Domain:
Lat = {clat:.10f}
Lon = {clon:.10f}
nXtiles = 82
nYtiles = 185
nXpertile = {300//dx}
nYpertile = {300//dx}
Xtilesize = 300
Boundary conditions = halt
Source:
sourceLat = {slat:.10f}
sourceLon = {slon:.10f}
sourceRadius = 100
sourceTime = (0,150,900)
sourceFlux = (0,{q:.12f},0)
sourceConc = (0.4,0.4,0.4)
Solver:
T end = 9000
cfl = 0.25
Output:
N out = 50
directory = runs/{case}
format = nc
Topog:
Type = DEM
raster file = pita_domain_30m.tif
dem directory = prepared
embed raster = off
Parameters:
Drag = variable
Chezy co = 0.01
Pouliquen min = 0.1
Pouliquen max = 0.35
Pouliquen beta = 0.136
voellmy switch value = 0.4
voellmy switch rate = 3.0
Erosion = mixed
Erosion rate = 1e-4
Granular erosion rate = 0.1
Erosion depth = 10
Erosion critical height = 0.01
Bed porosity = 0.35
maxPack = 0.65
Deposition = Spearman Manning
rhow = 1000
rhos = 2000
Solid diameter = 0.0015
Eddy Viscosity = 1e-2
'''
        (inputs/(case+'.txt')).write_text(text,encoding='utf-8')
        info['cases'].append({'id':case,'dx_m':dx,'mixture_input_m3':volume,'peak_m3_s':q,
                             'input':f'inputs/{case}.txt','output':f'runs/{case}'})
    (inputs/'scenario-manifest.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    benchmark='''Domain:
Lat = 0
Lon = 0
nXtiles = 4
nYtiles = 4
nXpertile = 20
nYpertile = 20
Xtilesize = 100
Boundary conditions = halt
Source:
sourceX = 0
sourceY = 0
sourceRadius = 10
sourceTime = (0,10,20)
sourceFlux = (0,100,0)
sourceConc = (0.4,0.4,0.4)
Topog:
Type = Function
Topog function = flat
Solver:
T end = 60
Output:
N out = 6
directory = runs/benchmark
format = nc
Parameters:
Drag = variable
Erosion = off
Deposition = off
'''
    (inputs/'benchmark.txt').write_text(benchmark)
    print('Prepared six hypothetical scenarios and an independent flat-domain mixture conservation benchmark.')

def run(case):
    path=ROOT/'inputs'/f'{case}.txt'
    if not path.is_file():raise ValueError('Unknown prepared case')
    log=ROOT/'runs'/f'{case}.log';log.parent.mkdir(exist_ok=True)
    (ROOT/'runs'/case).mkdir(exist_ok=True)
    with log.open('w') as f:
        result=subprocess.run([str(ENGINE),str(path)],cwd=ROOT,env=env(),stdout=f,stderr=subprocess.STDOUT)
    print('Engine exit',result.returncode,'log',log,flush=True)
    if result.returncode:raise SystemExit(result.returncode)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--setup',action='store_true');p.add_argument('--run');a=p.parse_args()
    if a.setup:setup()
    if a.run:run(a.run)
