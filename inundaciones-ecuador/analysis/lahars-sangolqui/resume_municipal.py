"""Audited official checkpoint continuation after an interrupted desktop process."""
from municipal_study import WORK,CASE,ENGINE,finish
from study_reference import sha
from run_kestrel import env
from netCDF4 import Dataset
import datetime,json,re,shutil,subprocess,time
import numpy as np

def main(threads=8,reason='Native process and driver absent after supervisory session disconnected; no fatal solver error in log.'):
    folder=WORK/'runs'/CASE
    original=WORK/'inputs'/f'{CASE}.txt'
    manifest=json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
    assert sha(original)==manifest['input_sha256'] and sha(ENGINE)==manifest['engine_sha256']
    assert sha(WORK/'prepared'/manifest['terrain']['model_file'])==manifest['terrain']['conditioned_sha256']
    info=(folder/'RunInfo.txt').read_text(encoding='utf-8')
    last=int(re.findall(r'Last output file\s*=\s*(\d+)',info)[-1])
    checkpoint=folder/f'{last:06d}.nc'
    with Dataset(checkpoint) as d:
        seconds=float(d.time);assert seconds==last*15 and seconds<9000
        assert np.isfinite(d['flow_depth'][:].filled(0)).all()
    with Dataset(folder/'Maximums.nc') as d:
        assert abs(float(d.time)-seconds)<1e-6,'Maximums checkpoint time mismatch'
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    audit=WORK/'runs'/('recovery-'+stamp);audit.mkdir()
    for name in ('RunInfo.txt','Maximums.nc','Volume.txt'):shutil.copy2(folder/name,audit/name)
    if (WORK/'runs/engine-exit.json').exists():shutil.copy2(WORK/'runs/engine-exit.json',audit/'previous-engine-exit.json')
    record={'checkpoint':checkpoint.name,'time_s':seconds,'checkpoint_sha256':sha(checkpoint),
        'engine_sha256':sha(ENGINE),'original_input_sha256':sha(original),
        'reason':reason,'threads':threads,
        'physical_inputs_changed':False,'utc':stamp}
    text=original.read_text(encoding='utf-8');assert 'Restart =' not in text
    resume=WORK/'inputs'/('resume-'+stamp+'.txt');resume.write_text(text.replace('Solver:\n','Solver:\nRestart = on\n'),encoding='utf-8')
    record['restart_input_sha256']=sha(resume)
    (audit/'recovery.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    history_path=WORK/'execution-history.json'
    history=json.loads(history_path.read_text(encoding='utf-8')) if history_path.exists() else {'recoveries':[]}
    history['recoveries'].append(record);history_path.write_text(json.dumps(history,indent=2),encoding='utf-8')
    log=WORK/'runs'/f'{CASE}.log'
    assert 'FATAL ERROR' not in log.read_text(encoding='utf-8',errors='replace').upper()
    e=env();e.update(OMP_NUM_THREADS=str(threads),OMP_WAIT_POLICY='ACTIVE',OMP_SCHEDULE='static')
    print('Resuming unchanged native municipal state at',seconds/60,'minutes.',flush=True)
    start=time.time()
    with log.open('a',encoding='utf-8') as out:
        out.write('\n# Audited official checkpoint recovery '+stamp+'\n');out.flush()
        result=subprocess.run([str(ENGINE),str(resume)],cwd=WORK,env=e,stdout=out,stderr=subprocess.STDOUT)
    execution={'returncode':result.returncode,'threads':threads,'resume_wall_seconds':time.time()-start,
        'input_sha256':sha(original),'engine_sha256':sha(ENGINE),'recovery':record}
    (WORK/'runs/engine-exit.json').write_text(json.dumps(execution,indent=2),encoding='utf-8')
    print('Municipal resumed solver exit',result.returncode,flush=True)
    assert result.returncode==0
    finish()

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--threads',type=int,choices=[4,8,16],default=8)
    p.add_argument('--reason',default='Native process and driver absent after supervisory session disconnected; no fatal solver error in log.')
    args=p.parse_args();main(args.threads,args.reason)
