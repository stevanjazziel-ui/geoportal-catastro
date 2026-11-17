"""Audited adaptation of Vasconez et al. 2025; never an exact reproduction.

Uses the published nine northern water hydrographs and physical parameters.
Source coordinates are digitized from Figure 1B; terrain is an independently
acquired Copernicus GLO-30 DSM, NOT the paper's 2015 photogrammetric DEM.
"""
from pathlib import Path
import argparse, hashlib, heapq, json, os, subprocess, sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / '.deps'))
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling
from pyproj import Transformer

WORK = ROOT / 'study2025-cop30-v2'
ENGINE = ROOT / 'tools/kestrel-o3/src/kestrel.exe'
BOUNDS = (769800., 9900000., 829800., 9996000.)
PEAKS = [2019, 577, 6058, 3750, 12981, 3462, 16154, 16154, 16154]
# Pixel centers read from original 1644 x 1237 Figure 1B. These are cartographic
# estimates, not original author GIS coordinates; never silently snap to a valley.
PIXELS = [(1023,553),(1056,541),(1087,535),(1121,530),(1154,532),
          (1184,546),(1207,572),(1218,603),(1227,635)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fill_depressions(z):
    """Eight-neighbour priority flood; minimum spill elevation, no artificial fall."""
    ny, nx = z.shape
    filled = z.copy(); seen = np.zeros(z.shape, bool); heap = []
    for r, c in [(0,c) for c in range(nx)]+[(ny-1,c) for c in range(nx)]+[(r,0) for r in range(1,ny-1)]+[(r,nx-1) for r in range(1,ny-1)]:
        seen[r,c] = True; heapq.heappush(heap,(float(z[r,c]),r*nx+c))
    while heap:
        level, i = heapq.heappop(heap); r,c = divmod(i,nx)
        for rr in range(max(0,r-1),min(ny,r+2)):
            for cc in range(max(0,c-1),min(nx,c+2)):
                if seen[rr,cc]: continue
                seen[rr,cc] = True
                value = max(float(z[rr,cc]),level); filled[rr,cc] = value
                heapq.heappush(heap,(value,rr*nx+cc))
    return filled


def setup():
    (WORK/'prepared').mkdir(parents=True,exist_ok=True)
    (WORK/'inputs').mkdir(exist_ok=True); (WORK/'runs/reference-cop30').mkdir(parents=True,exist_ok=True)
    west,south,east,north=BOUNDS; dx=30; halo=1200
    nx=round((east-west)/dx);ny=round((north-south)/dx)
    transform=from_origin(west-halo,north+halo,dx,dx)
    terrain=np.full((ny+2*halo//dx,nx+2*halo//dx),-32768,np.float32)
    source=ROOT/'sources/copernicus-glo30-S01W079.tif'
    with rasterio.open(source) as ds:
        reproject(rasterio.band(ds,1),terrain,src_transform=ds.transform,src_crs=ds.crs,
                  src_nodata=ds.nodata,dst_transform=transform,dst_crs=32717,
                  dst_nodata=-32768,resampling=Resampling.bilinear)
    assert np.isfinite(terrain).all() and (terrain>=0).all() and (terrain<6500).all(), 'Invalid terrain coverage or regional elevation range'
    raw=terrain.copy(); filled=fill_depressions(terrain)
    # Deep depressions may be real (including the crater). Do not raise an
    # entire canyon to force its connectivity or a desired arrival in the city.
    small=(filled-raw)<=2
    terrain=np.where(small,filled,raw).astype(np.float32)
    delta=terrain-raw
    for name,z in [('cop_raw_30m.tif',raw),('cop_conditioned_30m.tif',terrain)]:
        with rasterio.open(WORK/'prepared'/name,'w',driver='GTiff',height=z.shape[0],width=z.shape[1],
                           count=1,dtype='float32',crs=32717,transform=transform,nodata=-32768,
                           compress='deflate',predictor=3) as ds: ds.write(z,1)
    geo=Transformer.from_crs(32717,4326,always_xy=True)
    sources=[]
    for sid,(px,py),q in zip(range(12,21),PIXELS,PEAKS):
        x=780000+(px-720)*10000/674; y=9930000-(py-275)*10000/673
        lon,lat=geo.transform(x,y);r,c=rasterio.transform.rowcol(transform,x,y)
        assert 4400<terrain[r,c]<5900, ('Source outside upper flank',sid,terrain[r,c])
        sources.append({'id':sid,'pixel':[px,py],'easting':x,'northing':y,'lon':lon,'lat':lat,
                        'terrain_m':float(terrain[r,c]),'peak_water_m3_s':q,'water_volume_m3':q*450})
    points=np.array([[s['easting'],s['northing']] for s in sources])
    gaps=np.linalg.norm(np.diff(points,axis=0),axis=1)
    assert ((gaps>400)&(gaps<650)).all(),gaps
    lon,lat=geo.transform((west+east)/2,(south+north)/2)
    text=f'''# Literature-based ADAPTATION, not exact reproduction or locally validated prediction.
Domain:
Lat = {lat:.10f}
Lon = {lon:.10f}
nXtiles = 100
nYtiles = 160
nXpertile = 20
nYpertile = 20
Xtilesize = 600
Boundary conditions = halt
'''
    for s in sources:
        text+=f'''Source:
sourceLat = {s['lat']:.10f}
sourceLon = {s['lon']:.10f}
sourceRadius = 100
sourceTime = (0,150,900)
sourceFlux = (0,{s['peak_water_m3_s']},0)
sourceConc = (0,0,0)
'''
    text+='''Solver:
T end = 9000
cfl = 0.25
Output:
N out = 600
directory = runs/reference-cop30
format = nc
Topog:
Type = DEM
raster file = cop_conditioned_30m.tif
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
    input_path=WORK/'inputs/reference-cop30.txt';input_path.write_text(text,encoding='utf-8')
    manifest={'id':'reference-cop30','status':'prepared','calibrated':False,'exact_reproduction':False,
        'primary_study':'https://doi.org/10.3389/feart.2025.1611579',
        'source_method_study':'https://doi.org/10.3389/feart.2024.1426088',
        'comparison_only_study':'https://doi.org/10.1002/esp.5056',
        'source_coordinate_method':{'figure':'2025 Figure 1B','crs':'EPSG:32717 assumed from UTM map grid',
          'image_sha256':sha(ROOT/'sources/study2025-figure1.webp'),'image_size':[1644,1237],
          'control_pixels':{'780000E':720,'790000E':1394,'9930000N':275,'9920000N':948},
          'assumed_digitization_tolerance_m':80,'ground_accuracy_validated':False,
          'original_author_gis_coordinates':False,'snapping':False},
        'sources':sources,'source_neighbor_gaps_m':gaps.tolist(),
        'water_input_m3':sum(s['water_volume_m3'] for s in sources),
        'sum_rounded_peaks_m3_s':sum(PEAKS),'published_rounded_total_peak_m3_s':77308,
        'rounding_note':'Per-source integer peaks sum to 77309; paper total rounds to 77308. No artificial redistribution.',
        'initial_solid_fraction':0,'source_radius_m':100,'hydrograph_s':[0,150,900],
        'glacier_geometry_reference_years':[2020,2021,2022],
        'glacier_remeasured_in_2026':False,
        'time_origin':'Simultaneous water release at nine upper-flank sources; not eruption warning time',
        'domain_utm17s':list(BOUNDS),'dx_m':dx,'duration_s':9000,'native_output_step_s':15,
        'terrain_halo_m':halo,'tile_size_m':600,'cells_per_tile':[20,20],
        'terrain':{'source':'https://registry.opendata.aws/copernicus-dem/','coverage':'GLO-30 S01W079',
          'native_pixel_m_approx':30,'paper_dem':False,'source_sha256':sha(source),
          'conditioned_sha256':sha(WORK/'prepared/cop_conditioned_30m.tif'),
          'conditioning':'Priority flood only for depressions requiring at most 2 m. Deeper basins retained. This is an explicit sensitivity assumption, different from the paper.',
          'deep_depression_cells_retained':int((~small).sum()),
          'full_fill_max_raise_m_NOT_applied':float((filled-raw).max()),
          'raised_cells':int((delta>0.001).sum()),'raised_area_km2':float((delta>0.001).sum()*.0009),
          'max_raise_m':float(delta.max()),'fill_volume_m3':float(delta.astype(float).sum()*900)},
        'engine_commit':'e0965b438b763d94f0236ca31911bb43e6b82f49','engine_sha256':sha(ENGINE),
        'compiler_options':'O3, native CPU, LTO; no fast-math; independent conservation benchmark passed',
        'input_sha256':sha(input_path),
        'limitations':['Independent 30m global surface model, not the fine photogrammetric DEM in the study. Vegetation, buildings and narrow canyons are unresolved.',
          'Digitized source coordinates; require original GIS coordinates for exact reproduction.',
          'Buildings and bridges are not hydraulic obstacles.','No tuning to force published city arrivals.',
          'Published RAMMS volumes and arrival times are comparisons, not imposed outputs.']}
    (WORK/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Prepared nine-source water release:',manifest['water_input_m3'],'m3; terrain changes:',manifest['terrain'],flush=True)


def run():
    sys.path.insert(0,str(ROOT));from run_kestrel import env
    e=env();e.update(OMP_NUM_THREADS=str(min(4,max(1,int(os.environ.get('LAHAR_THREADS','4'))))),
                    OMP_WAIT_POLICY='ACTIVE',OMP_SCHEDULE='static')
    log=WORK/'runs/reference-cop30.log'
    with log.open('w',encoding='utf-8') as output:
        result=subprocess.run([str(ENGINE),str(WORK/'inputs/reference-cop30.txt')],cwd=WORK,env=e,
                              stdout=output,stderr=subprocess.STDOUT)
    execution={'returncode':result.returncode,'threads':e['OMP_NUM_THREADS'],
               'schedule':e['OMP_SCHEDULE'],'wait_policy':e['OMP_WAIT_POLICY'],
               'engine_sha256':sha(ENGINE),'input_sha256':sha(WORK/'inputs/reference-cop30.txt')}
    (WORK/'runs/engine-exit.json').write_text(json.dumps(execution,indent=2),encoding='utf-8')
    print('Kestrel exit:',result.returncode,flush=True)
    if result.returncode:raise SystemExit(result.returncode)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--setup',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--finish',action='store_true');a=p.parse_args()
    if a.setup:setup()
    if a.run:run()
    if a.finish:
        from analyze_study import main as analyze
        from pack_study import main as pack
        analyze();pack()
