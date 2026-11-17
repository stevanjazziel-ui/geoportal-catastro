"""Independent checkpoint continuation check, using the official erosion test.

Uses the same O3 executable as the study. Truncation is at a normal output time;
the source is still active, and erosion, slopes and mixed drag are exercised.
This numerical test does not validate real-world lahar predictions.
"""
import json, subprocess
from study_reference import ROOT, ENGINE, sha
from run_kestrel import env
from netCDF4 import Dataset
import numpy as np


def main():
    folder=ROOT/'runs/benchmark-native-restart-v2'
    folder.mkdir(exist_ok=False)
    # Native directory creation invokes a shell command incompatible with these
    # Windows paths. Precreate both output directories, as in the real study.
    (folder/'full').mkdir();(folder/'continued').mkdir()
    original=(ROOT/'tools/kestrel/tests/Input_netcdf_restart1.txt').read_text(encoding='utf-8')
    full=original.replace('directory = netcdf_restart1/','directory = full/')
    partial=full.replace('T end = 10','T end = 5').replace('N out = 4','N out = 2').replace('directory = full/','directory = continued/')
    resume=full.replace('directory = full/','directory = continued/').replace('Restart = off','Restart = on')
    e=env();e.update(OMP_NUM_THREADS='1',OMP_WAIT_POLICY='PASSIVE',OMP_SCHEDULE='static')
    for name,text in [('full',full),('partial',partial),('resume',resume)]:
        path=folder/(name+'.txt');path.write_text(text,encoding='utf-8')
        with (folder/(name+'.log')).open('w',encoding='utf-8') as log:
            result=subprocess.run([str(ENGINE),str(path)],cwd=folder,env=e,stdout=log,stderr=subprocess.STDOUT)
        assert result.returncode==0,(name,result.returncode)
        assert 'FATAL ERROR' not in (folder/(name+'.log')).read_text(encoding='utf-8').upper()
        print('Completed checkpoint test stage',name,flush=True)
    checks={}
    for name in ('000004.nc','Maximums.nc'):
        with Dataset(folder/'full'/name) as a,Dataset(folder/'continued'/name) as b:
            assert set(a.variables)==set(b.variables)
            errors={};exact=True
            for key in a.variables:
                av=np.ma.asarray(a[key][:]);bv=np.ma.asarray(b[key][:])
                assert av.shape==bv.shape and np.array_equal(np.ma.getmaskarray(av),np.ma.getmaskarray(bv)),key
                exact = exact and av.filled(0).tobytes()==bv.filled(0).tobytes()
                aa=av.filled(0).astype(float);bb=bv.filled(0).astype(float)
                difference=float(np.max(abs(aa-bb)))
                normalized=difference/max(1.,float(abs(aa).max()))
                assert normalized<1e-10,(name,key,difference,normalized)
                if difference:errors[key]={'absolute':difference,'relative_to_global_scale':normalized};exact=False
            checks[name]={'bitwise_identical_numeric_fields':exact,'nonzero_differences':errors,'variables_checked':len(a.variables)}
    for case in ('full','continued'):
        budget=np.genfromtxt(folder/case/'Volume.txt',delimiter=',',names=True)
        assert len(budget)==5 and np.allclose(budget['time'],[0,2.5,5,7.5,10])
        assert abs(budget['volume'][-1]+budget['total_bed_volume'][-1]-40)<1e-7
    report={'engine_sha256':sha(ENGINE),'official_test_source':'jakelangham/kestrel/tests/Input_netcdf_restart1.txt',
            'scope':'Synthetic inclined eroding bed with ongoing source; continuation at5s to10s, same2.5s output spacing',
            'passed':True,'comparisons':checks,'predictive_validation':False}
    (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
