"""Resume an interrupted, checkpointed study without changing physical inputs."""
import datetime, json, os, re, shutil, subprocess
from pathlib import Path
from study_reference import ROOT, WORK, ENGINE, sha
from netCDF4 import Dataset
from run_kestrel import env


def main():
    folder=WORK/'runs/reference-cop30'
    original=WORK/'inputs/reference-cop30.txt'
    manifest=json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
    assert sha(original)==manifest['input_sha256']
    assert sha(ENGINE)==manifest['engine_sha256']
    info=(folder/'RunInfo.txt').read_text(encoding='utf-8')
    last=int(re.search(r'Last output file\s*=\s*(\d+)',info).group(1))
    checkpoint=folder/f'{last:06d}.nc'
    with Dataset(checkpoint) as ds:
        seconds=float(ds.time)
        assert abs(seconds-last*15)<1e-6
        for key in ('flow_depth','x_velocity','y_velocity','elevation_change'):
            assert key in ds.variables
    assert seconds<9000
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    audit=WORK/'runs'/f'recovery-{stamp}';audit.mkdir()
    for name in ('RunInfo.txt','Volume.txt','Maximums.nc'):
        shutil.copy2(folder/name,audit/name)
    resume=WORK/'inputs'/f'reference-resume-{stamp}.txt'
    text=original.read_text(encoding='utf-8')
    assert 'Restart =' not in text
    resume.write_text(text.replace('Solver:\n','Solver:\nRestart = on\n'),encoding='utf-8')
    record={'checkpoint':checkpoint.name,'checkpoint_sha256':sha(checkpoint),
            'checkpoint_time_s':seconds,'restart_input_sha256':sha(resume),
            'original_input_sha256':sha(original),'engine_sha256':sha(ENGINE),
            'reason':'Process absent after interrupted desktop session; no fatal error in previous log',
            'physical_inputs_changed':False,'utc':stamp}
    (audit/'recovery.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    e=env();e.update(OMP_NUM_THREADS='4',OMP_WAIT_POLICY='ACTIVE',OMP_SCHEDULE='static')
    log=WORK/'runs/reference-cop30.log'
    assert 'FATAL ERROR' not in log.read_text(encoding='utf-8',errors='replace').upper()
    print('Resuming checkpoint',checkpoint.name,'time',seconds,flush=True)
    with log.open('a',encoding='utf-8') as out:
        out.write('\n# Audited native checkpoint recovery '+stamp+'\n');out.flush()
        result=subprocess.run([str(ENGINE),str(resume)],cwd=WORK,env=e,stdout=out,stderr=subprocess.STDOUT)
    execution={'returncode':result.returncode,'threads':'4','schedule':'static','wait_policy':'ACTIVE',
               'input_sha256':sha(original),'engine_sha256':sha(ENGINE),'recovery':record}
    (WORK/'runs/engine-exit.json').write_text(json.dumps(execution,indent=2),encoding='utf-8')
    print('Kestrel exit:',result.returncode,flush=True)
    if result.returncode:raise SystemExit(result.returncode)
    from analyze_study import main as analyze
    from pack_study import main as pack
    analyze();pack()


if __name__=='__main__':main()
