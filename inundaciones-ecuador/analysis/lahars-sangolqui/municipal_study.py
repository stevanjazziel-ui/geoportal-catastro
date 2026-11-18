"""Independent municipal-MDT adaptation; retain the original run unchanged."""
from study_reference import ROOT,WORK as ORIGINAL,ENGINE,sha
from pathlib import Path
import json,os,subprocess,time
import numpy as np
import rasterio
from rasterio.warp import reproject,Resampling

WORK=ROOT/'study2025-municipal30-v1'
CASE='reference-mdt30'

def setup():
    assert not (WORK/'manifest.json').exists(),'Do not overwrite a prepared or running scenario'
    for folder in ('prepared','inputs','runs/'+CASE): (WORK/folder).mkdir(parents=True,exist_ok=True)
    source=ROOT/'sources/ruminahui-geoservicios-dtm/mdt2023-native3m.tif'
    audit=json.loads((source.parent/'native3m-audit.json').read_text(encoding='utf-8'))
    assert sha(source)==audit['sha256'] and audit['valid_pixels']==audit['total_pixels']
    with rasterio.open(ORIGINAL/'prepared/cop_conditioned_30m.tif') as base,rasterio.open(source) as municipal:
        old=base.read(1);local=np.full(old.shape,-32768,np.float32)
        reproject(rasterio.band(municipal,1),local,src_transform=municipal.transform,src_crs=municipal.crs,
                  src_nodata=municipal.nodata,dst_transform=base.transform,dst_crs=base.crs,
                  dst_nodata=-32768,resampling=Resampling.bilinear)
        rows,cols=np.indices(old.shape);x=base.transform.c+(cols+.5)*30;y=base.transform.f-(rows+.5)*30
        b=municipal.bounds
        distance=np.minimum.reduce([x-b.left,b.right-x,y-b.bottom,b.top-y])
        # The transition is explicitly a modelling assumption, not a datum correction.
        weight=np.clip(distance/500,0,1);weight[local==-32768]=0
        new=old.copy();mask=weight>0
        new[mask]=(old[mask]*(1-weight[mask])+local[mask]*weight[mask]).astype(np.float32)
        assert np.isfinite(new).all() and new.min()>=0 and new.max()<6500
        assert np.array_equal(new[~mask],old[~mask])
        profile=base.profile.copy();profile.update(compress='deflate',predictor=3)
        target=WORK/'prepared/municipal_hybrid_30m.tif'
        with rasterio.open(target,'w',**profile) as out:out.write(new,1)
        full=weight>=1;delta=new-old
        transition=(weight>0)&(weight<1)
        statistics={'full_municipal_cells':int(full.sum()),'transition_cells':int(transition.sum()),
                    'transition_width_m':500,'difference_median_m':float(np.median(delta[full])),
                    'difference_p05_p95_m':np.percentile(delta[full],[5,95]).tolist(),
                    'maximum_absolute_difference_m':float(abs(delta).max()),
                    'added_slope_from_blending_p95':float(np.percentile(abs(local[transition]-old[transition])/500,95))}
    manifest=json.loads((ORIGINAL/'manifest.json').read_text(encoding='utf-8'))
    manifest.update(id=CASE,status='prepared',parent_scenario='reference-cop30',
        terrain={'source':audit['request'],'source_sha256':audit['sha256'],'native_pixel_m':3,
                 'native_dtype':'int16; one-metre elevation quantization',
                 'model_file':target.name,'conditioned_sha256':sha(target),
                 'background_source_sha256':sha(ORIGINAL/'prepared/cop_conditioned_30m.tif'),
                 'model_resampling':'Bilinear from native3m to unchanged30m computational grid',
                 'transition':statistics,'vertical_datum_confirmed':False,
                 'vertical_offset_applied_m':0,'paper_dem':False,
                 'conditioning':'No channel excavation or additional depression filling. Municipal terrain replaces the global surface in its interior;500m weighted boundary transition is an explicit uncertain assumption.'})
    manifest['limitations']=[
        'Computational cells remain30m; narrow channels may still be unresolved despite native3m municipal input.',
        'Municipal vertical datum is not documented; zero offset and500m transition are explicit sensitivity assumptions, not surveyed alignment.',
        'No local predictive calibration; the layer year2023 is not a verified acquisition date.',
        'Source positions remain digitized and glacier geometry is not updated to2026.',
        'LiDAR metadata/classification reviewed; unverified cloud projection prevents silently replacing terrain with unregistered points.',
        'Buildings remain visual references, not hydraulic obstacles.']
    text=(ORIGINAL/'inputs/reference-cop30.txt').read_text(encoding='utf-8')
    text=text.replace('directory = runs/reference-cop30','directory = runs/'+CASE).replace('raster file = cop_conditioned_30m.tif','raster file = '+target.name)
    path=WORK/'inputs'/f'{CASE}.txt';path.write_text(text,encoding='utf-8')
    manifest['input_sha256']=sha(path)
    (WORK/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (WORK/'prepared/terrain-integration.json').write_text(json.dumps(statistics,indent=2),encoding='utf-8')
    print('Prepared independent municipal terrain scenario:',statistics,flush=True)

def run(threads=8):
    from run_kestrel import env
    m=json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
    source=WORK/'inputs'/f'{CASE}.txt'
    assert sha(source)==m['input_sha256'] and sha(ENGINE)==m['engine_sha256']
    assert sha(WORK/'prepared'/m['terrain']['model_file'])==m['terrain']['conditioned_sha256']
    assert not (WORK/'runs'/CASE/'000000.nc').exists(),'Refuse to overwrite native states'
    e=env();e.update(OMP_NUM_THREADS=str(threads),OMP_WAIT_POLICY='ACTIVE',OMP_SCHEDULE='static')
    started=time.time()
    with (WORK/'runs'/f'{CASE}.log').open('w',encoding='utf-8') as log:
        result=subprocess.run([str(ENGINE),str(source)],cwd=WORK,env=e,stdout=log,stderr=subprocess.STDOUT)
    execution={'returncode':result.returncode,'threads':threads,'wall_seconds':time.time()-started,
               'input_sha256':sha(source),'engine_sha256':sha(ENGINE)}
    (WORK/'runs/engine-exit.json').write_text(json.dumps(execution,indent=2),encoding='utf-8')
    print('Municipal scenario solver exit:',result.returncode,flush=True)
    assert result.returncode==0
    finish()

def finish():
    import analyze_study
    analyze_study.WORK=WORK;analyze_study.FOLDER=WORK/'runs'/CASE
    analyze_study.main()
    from audit_pita_gap import main as audit
    audit(work=WORK,output=WORK/'delivery')
    import pack_study
    pack_study.WORK=WORK
    pack_study.main(case_id=CASE,output=WORK/'delivery')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--setup',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--threads',type=int,default=8);a=p.parse_args()
    if a.setup:setup()
    if a.run:run(a.threads)
