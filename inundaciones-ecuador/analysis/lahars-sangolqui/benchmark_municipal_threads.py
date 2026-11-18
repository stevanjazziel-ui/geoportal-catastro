"""Measure thread throughput with unchanged old terrain and physical state."""
from municipal_study import WORK,ORIGINAL,ROOT,ENGINE
from study_reference import sha
from run_kestrel import env
import os,time,json,subprocess
import numpy as np
from netCDF4 import Dataset

def main():
    target=WORK/'prepared/cop_baseline_30m.tif'
    if not target.exists():os.link(ORIGINAL/'prepared/cop_conditioned_30m.tif',target)
    original=(ORIGINAL/'inputs/reference-cop30.txt').read_text(encoding='utf-8')
    # Input block parsing treats a colon as a block delimiter: use relative paths.
    initial='../'+ORIGINAL.name+'/runs/reference-cop30/000600'
    records=[];final={}
    for threads in (4,8):
        folder=WORK/'runs'/f'performance-v3-{threads}';folder.mkdir(exist_ok=False)
        text=original.replace('T end = 9000',f'T start = 9000\nT end = 9030\nInitial condition = {initial}').replace('N out = 600','N out = 2').replace('directory = runs/reference-cop30','directory = runs/performance-v3-'+str(threads)).replace('raster file = cop_conditioned_30m.tif','raster file = cop_baseline_30m.tif')
        input_path=WORK/'inputs'/f'performance-{threads}.txt';input_path.write_text(text,encoding='utf-8')
        e=env();e.update(OMP_NUM_THREADS=str(threads),OMP_WAIT_POLICY='ACTIVE',OMP_SCHEDULE='static')
        start=time.perf_counter()
        with (folder/'process.log').open('w',encoding='utf-8') as log:
            result=subprocess.run([str(ENGINE),str(input_path)],cwd=WORK,env=e,stdout=log,stderr=subprocess.STDOUT)
        elapsed=time.perf_counter()-start
        assert result.returncode==0,(threads,result.returncode)
        assert 'FATAL ERROR' not in (folder/'process.log').read_text(encoding='utf-8').upper()
        budget=np.genfromtxt(folder/'Volume.txt',delimiter=',',names=True)
        assert budget['volume'][0]>34_000_000,'Initial condition was not loaded; throughput test is invalid'
        with Dataset(folder/'000002.nc') as d:
            assert abs(float(d.time)-9030)<1e-8
            assert float(d['flow_depth'][:].max())>1
            final[threads]={key:np.asarray(d[key][:].filled(0)) for key in ('flow_depth','x_velocity','y_velocity','elevation_change')}
        records.append({'threads':threads,'wall_seconds':elapsed})
        print('Thread throughput',records[-1],flush=True)
    differences={key:float(abs(final[4][key]-final[8][key]).max()) for key in final[4]}
    assert all(np.allclose(final[4][key],final[8][key],rtol=1e-8,atol=1e-8) for key in final[4]),differences
    report={'engine_sha256':sha(ENGINE),'benchmarks':records,'maximum_field_differences':differences,
            'chosen_threads':min(records,key=lambda r:r['wall_seconds'])['threads'],
            'scope':'Only threading throughput; same physical state and terrain; not predictive validation.'}
    (WORK/'prepared/thread-benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Selected threads',report['chosen_threads'],flush=True)

if __name__=='__main__':main()
