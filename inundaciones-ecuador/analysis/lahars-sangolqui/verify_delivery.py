"""Compare every delivered state with native Kestrel results through independent georeferencing."""
from pathlib import Path
import sys,gzip,json,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.deps'))
import numpy as np
import rasterio
from pyproj import Transformer
from netCDF4 import Dataset

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent/'dist/data/sangolqui-lahars'

def read(asset,dtype):
    b=(OUT/asset['file']).read_bytes()
    assert hashlib.sha256(b).hexdigest()==asset['sha256']
    assert len(b)==asset['bytes']
    return np.frombuffer(gzip.decompress(b),dtype).copy()

def main():
    m=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'));n=m['cell_count'];dx=m['dx_m']
    g=read(m['geometry'],'<f4').reshape(n,4,3)
    lo=g[:,:,0].astype(float).mean(axis=1);la=g[:,:,1].astype(float).mean(axis=1)
    tr=Transformer.from_crs(4326,32717,always_xy=True);xx,yy=tr.transform(lo,la)
    west,south,east,north=m['setup']['domain_utm17s']
    cc=np.rint((xx-west)/dx-.5).astype(int);rr=np.rint((yy-south)/dx-.5).astype(int)
    assert np.hypot(xx-(west+(cc+.5)*dx),yy-(south+(rr+.5)*dx)).max()<1.5
    with rasterio.open(ROOT/'prepared/pita_domain_30m.tif') as dem:
        base=np.array([v[0] for v in dem.sample(zip(xx,yy))])
    results=[]
    for c in m['cases']:
        encoded=read(c,'<i4').reshape(c['frame_count'],5,n)
        data=np.cumsum(encoded,axis=0,dtype=np.int64)
        assert len(m['times_s'])==c['frame_count']==51
        snapmax=np.zeros(n);speedmax=np.zeros(n)
        folder=ROOT/c['output']
        def field(ds,name,fill=0):
            out=np.full(n,fill,float)
            x0=round((float(ds['x'][0])-west)/dx-.5);y0=round((float(ds['y'][0])-south)/dx-.5)
            col=cc-x0;row=rr-y0
            valid=(col>=0)&(col<len(ds.dimensions['x']))&(row>=0)&(row<len(ds.dimensions['y']))
            a=ds[name][:].filled(fill);out[valid]=a[row[valid],col[valid]];return out
        for t in range(51):
            with Dataset(folder/f'{t:06d}.nc') as ds:
                assert abs(float(ds.time)-m['times_s'][t])<1e-8
                h=field(ds,'flow_depth');v=field(ds,'flow_speed');psi=field(ds,'solids_fraction')
                vertical=h/np.sqrt(1+field(ds,'x_slope')**2+field(ds,'y_slope')**2)
                z=field(ds,'base_elevation')+field(ds,'elevation_change')+vertical-base
                z[h<.05]=0
                for k,a in [(0,np.floor(np.maximum(h,0)*100)),(1,np.floor(np.maximum(v,0)*100)),(2,np.rint(z*100)),(3,np.rint(psi*10000)),(4,np.rint(vertical*100))]:
                    assert np.array_equal(data[t,k],a),(c['id'],t,k,float(abs(data[t,k]-a).max()))
                snapmax=np.maximum(snapmax,h);speedmax=np.maximum(speedmax,v)
        maxima=read(c['max_asset'],'<f4').reshape(3,n)
        with Dataset(folder/'Maximums.nc') as ds:
            h=np.maximum(field(ds,'max_depth'),snapmax);v=np.maximum(field(ds,'max_speed'),speedmax)
            assert np.array_equal(maxima[0],np.floor(h*100))
            assert np.array_equal(maxima[1],np.floor(v*100))
        report=json.loads((OUT/c['report']).read_text(encoding='utf-8'))
        assert report['completed_time_s']==9000 and report['mixture_balance_relative_error']<1e-3
        results.append({'case':c['id'],'frames':51,'all_fields_exact':True,'native_georeferencing_verified':True})
        print(c['id'],'51 states x 5 fields match native outputs exactly',flush=True)
    a=m['buildings'];b=json.loads(gzip.decompress((OUT/a['file']).read_bytes()))
    assert len(b['features'])==a['count']
    assert hashlib.sha256((OUT/a['file']).read_bytes()).hexdigest()==a['sha256']
    for f in b['features']:
        assert set(f['properties'])=={'floors','height_m','base_m','height_origin'}
        assert f['properties']['height_m']==3*f['properties']['floors']
    result={'calibrated':False,'cases':results,'building_features':len(b['features']),
        'scope':'Numerical transport and georeferencing checks, not predictive validation'}
    (ROOT/'prepared/delivery-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('VERIFIED',len(results),'completed scenarios and anonymous building attributes.')

if __name__=='__main__':main()
