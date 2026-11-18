"""Pause our own live solver briefly; compare identical nonempty native states."""
from municipal_study import WORK,CASE,ENGINE
from study_reference import sha
from run_kestrel import env
from netCDF4 import Dataset
import psutil,json,subprocess,time,datetime
import numpy as np

def main():
    matching=[]
    for p in psutil.process_iter(['name','cmdline']):
        try:
            command=' '.join(p.info['cmdline'] or []).replace('\\','/')
            if (p.info['name'] or '').lower()=='kestrel.exe' and WORK.name+'/inputs/' in command:matching.append(p)
        except (psutil.AccessDenied,psutil.NoSuchProcess):continue
    assert len(matching)==1,'Require exactly one owned municipal solver'
    live=matching[0]
    checkpoint=sorted((WORK/'runs'/CASE).glob('[0-9]*.nc'))[-3]
    with Dataset(checkpoint) as d:seconds=float(d.time)
    assert seconds>900
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    group=WORK/'runs'/('thread-sweep-'+stamp);group.mkdir()
    (group/'supervision.json').write_text(json.dumps({'main_pid':live.pid,'checkpoint':checkpoint.name,'time_s':seconds,'temporary_suspend_for_comparison':True},indent=2),encoding='utf-8')
    original=(WORK/'inputs'/f'{CASE}.txt').read_text(encoding='utf-8')
    records=[];fields={}
    live.suspend()
    try:
        for threads in (4,8,16):
            folder=group/str(threads);folder.mkdir()
            relative=folder.relative_to(WORK).as_posix()
            initial=checkpoint.relative_to(WORK).with_suffix('').as_posix()
            text=original.replace('T end = 9000',f'T start = {seconds:.0f}\nT end = {seconds+30:.0f}\nInitial condition = {initial}').replace('N out = 600','N out = 2').replace('directory = runs/'+CASE,'directory = '+relative)
            inp=group/f'input-{threads}.txt';inp.write_text(text,encoding='utf-8')
            e=env();e.update(OMP_NUM_THREADS=str(threads),OMP_WAIT_POLICY='ACTIVE',OMP_SCHEDULE='static')
            start=time.perf_counter()
            with (folder/'process.log').open('w',encoding='utf-8') as log:
                result=subprocess.run([str(ENGINE),str(inp)],cwd=WORK,env=e,stdout=log,stderr=subprocess.STDOUT)
            elapsed=time.perf_counter()-start
            assert result.returncode==0,(threads,result.returncode)
            assert 'FATAL ERROR' not in (folder/'process.log').read_text(encoding='utf-8').upper()
            budget=np.genfromtxt(folder/'Volume.txt',delimiter=',',names=True)
            assert budget['volume'][0]>34_000_000 and np.allclose(budget['time'],[seconds,seconds+15,seconds+30])
            total=budget['volume']+budget['total_bed_volume'];assert abs(total-total[0]).max()/total[0]<1e-8
            with Dataset(folder/'000002.nc') as d:
                assert abs(float(d.time)-(seconds+30))<1e-8
                fields[threads]={k:np.asarray(d[k][:].filled(0)) for k in ('flow_depth','x_velocity','y_velocity','elevation_change','solids_fraction','Hnpsi')}
            records.append({'threads':threads,'wall_seconds':elapsed});print('Active-state throughput',records[-1],flush=True)
        differences={str(t):{k:float(abs(fields[t][k]-fields[8][k]).max()) for k in fields[8]} for t in (4,16)}
        for t in (4,16):
            assert all(np.allclose(fields[t][k],fields[8][k],rtol=1e-8,atol=1e-8) for k in fields[8]),differences[str(t)]
        best=min(records,key=lambda r:r['wall_seconds']);baseline=next(r['wall_seconds'] for r in records if r['threads']==8)
        chosen=best['threads'] if best['wall_seconds']<baseline*.9 else 8
        report={'engine_sha256':sha(ENGINE),'seed_native_sha256':sha(checkpoint),'seed_time_s':seconds,
                'benchmarks':records,'maximum_field_differences_against8':differences,'chosen_threads':chosen,
                'selection_rule':'Change from8 only with at least10percent measured gain and all6state fields matching within1e-8.',
                'main_temporarily_suspended':True,'predictive_validation':False}
        (WORK/'prepared/active-thread-benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('Active-state selected threads',chosen,flush=True)
    finally:
        if live.is_running():live.resume()

if __name__=='__main__':main()
