"""Stop only our solver after validating a complete official checkpoint.

The supervising parent records the controlled exit; resume_municipal then uses
the unchanged saved physical state with the independently benchmarked threads.
"""
from municipal_study import WORK,CASE
from study_reference import sha
from netCDF4 import Dataset
import datetime,json,re,time,psutil
import numpy as np

def main():
    benchmark=json.loads((WORK/'prepared/active-thread-benchmark.json').read_text(encoding='utf-8'))
    assert benchmark['chosen_threads']==16
    assert all(v<=1e-8 for v in benchmark['maximum_field_differences_against8']['16'].values())
    processes=[]
    for p in psutil.process_iter(['name','cmdline']):
        try:
            command=' '.join(p.info['cmdline'] or []).replace('\\','/')
            if (p.info['name'] or '').lower()=='kestrel.exe' and WORK.name+'/inputs/' in command:processes.append(p)
        except (psutil.NoSuchProcess,psutil.AccessDenied):continue
    assert len(processes)==1
    process=processes[0];folder=WORK/'runs'/CASE
    stopped=False
    for attempt in range(10):
        process.suspend()
        try:
            info=(folder/'RunInfo.txt').read_text(encoding='utf-8')
            last=int(re.findall(r'Last output file\s*=\s*(\d+)',info)[-1]);state=folder/f'{last:06d}.nc'
            with Dataset(state) as d:
                seconds=float(d.time);assert seconds==last*15
                for key in ('flow_depth','x_velocity','y_velocity','elevation_change','solids_fraction'):
                    assert np.isfinite(d[key][:].filled(0)).all()
            with Dataset(folder/'Maximums.nc') as d:
                assert float(d.time)==seconds
                for key in ('max_depth','max_speed','max_erosion','max_deposit','max_solids_frac'):
                    assert np.isfinite(d[key][:].filled(0)).all()
            budget=np.genfromtxt(folder/'Volume.txt',delimiter=',',names=True)
            assert len(budget)==last+1 and float(budget['time'][-1])==seconds
            record={'reason':'Controlled restart to benchmarked16threads; physical state unchanged.',
                    'time_s':seconds,'state_sha256':sha(state),'maxima_sha256':sha(folder/'Maximums.nc'),
                    'old_pid':process.pid,'old_threads':8,'new_threads':16,
                    'benchmark_sha256':sha(WORK/'prepared/active-thread-benchmark.json')}
            stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            (WORK/'prepared'/('thread-handoff-'+stamp+'.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
            process.terminate();process.wait(timeout=15);stopped=True
            print('Controlled stop at verified checkpoint',seconds/60,'min; ready for16threads.',flush=True)
            return
        except Exception:
            if attempt==9:raise
        finally:
            if not stopped and process.is_running():process.resume()
        time.sleep(1)
    raise RuntimeError('No consistent checkpoint; retained existing process')

if __name__=='__main__':main()
