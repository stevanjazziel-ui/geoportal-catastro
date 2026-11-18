"""Export completed Kestrel outputs; no interpolation of a municipal hazard map."""
from pathlib import Path
import sys,json,gzip,hashlib,shutil,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.deps'))
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject,Resampling,transform_bounds
from pyproj import Transformer
from netCDF4 import Dataset
from shapely.geometry import shape,mapping

ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent/'dist/data/sangolqui-lahars'

def blob(path,values):
    data=gzip.compress(values.tobytes(),compresslevel=9,mtime=0);path.write_bytes(data)
    return {'file':path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

def values(ds,name,fill=0):return np.asarray(ds[name][:].filled(fill),np.float64)

def positions(ds,west,south,dx):
    x=np.rint((ds['x'][:]-west)/dx-.5).astype(int)
    y=np.rint((ds['y'][:]-south)/dx-.5).astype(int)
    assert np.max(np.abs((ds['x'][:]-west)/dx-.5-x))<1e-4
    assert np.max(np.abs((ds['y'][:]-south)/dx-.5-y))<1e-4
    return y[:,None],x[None,:]

def benchmark():
    a=np.genfromtxt(ROOT/'runs/benchmark/Volume.txt',delimiter=',',names=True)
    expected=np.where(a['time']<=10,5*a['time']**2,
                  np.where(a['time']<20,1000-5*(20-a['time'])**2,1000))
    volume=float(np.max(abs(a['volume']-expected))/1000)
    solid=float(np.max(abs(a['total_solids_mass']-expected*.4*2000))/800000)
    mass=float(np.max(abs(a['total_mass']-expected*1400))/1400000)
    assert volume<1e-10 and solid<1e-10 and mass<1e-6
    return {'volume_relative_error':volume,'solid_mass_relative_error':solid,
            'bulk_mass_relative_error':mass,'scope':'Synthetic flat closed-domain mixture release, no erosion/deposition'}

def main(cases=None):
    OUT.mkdir(parents=True,exist_ok=True)
    setup=json.loads((ROOT/'inputs/scenario-manifest.json').read_text(encoding='utf-8'))
    selected=[c for c in setup['cases'] if c['id'] in cases] if cases else [c for c in setup['cases'] if c['dx_m']==30]
    assert selected and len({c['dx_m'] for c in selected})==1
    dx=selected[0]['dx_m'];west,south,east,north=setup['domain_utm17s'];nx=round((east-west)/dx);ny=round((north-south)/dx)
    mask=np.zeros((ny,nx),bool)
    for c in selected:
        folder=ROOT/c['output'];v=np.genfromtxt(folder/'Volume.txt',delimiter=',',names=True)
        assert abs(v['time'][-1]-9000)<.01,'Refuse incomplete model '+c['id']
        assert all((folder/f'{i:06d}.nc').is_file() for i in range(51))
        with Dataset(folder/'Maximums.nc') as ds:
            iy,ix=positions(ds,west,south,dx);mask[iy,ix]|=values(ds,'max_depth')>=.05
        # Include every exported state as well as the solver's aggregate file.
        # Operator ordering can leave final-state extrema slightly above that file.
        for i in range(51):
            with Dataset(folder/f'{i:06d}.nc') as ds:
                iy,ix=positions(ds,west,south,dx);mask[iy,ix]|=values(ds,'flow_depth')>=.05
    rr,cc=np.where(mask);n=len(rr);lookup=np.full((ny,nx),-1,np.int32);lookup[rr,cc]=np.arange(n)
    tx=Transformer.from_crs(32717,4326,always_xy=True)
    xs=west+(cc+.5)*dx;ys=south+(rr+.5)*dx
    lon,lat=tx.transform(xs,ys)
    urban=(lon>=-78.49)&(lon<=-78.395)&(lat>=-.375)&(lat<=-.285)
    # Four georeferenced corners per active display cell, sampled from the same DEM.
    with rasterio.open(ROOT/'prepared/pita_domain_30m.tif') as dem:
        geometry=np.empty((n,4,3),np.float32)
        for j,(ox,oy) in enumerate([(-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5)]):
            xx=xs+ox*dx;yy=ys+oy*dx;lo,la=tx.transform(xx,yy)
            zz=np.array([p[0] for p in dem.sample(zip(xx,yy))])
            geometry[:,j,0]=lo;geometry[:,j,1]=la;geometry[:,j,2]=zz
        center_z=np.array([p[0] for p in dem.sample(zip(xs,ys))],np.float32)
        bounds=transform_bounds(dem.crs,4326,*dem.bounds)
        terrain_rows,terrain_cols=setup.get('display_grid',[1850,820])
        terrain=np.full((terrain_rows,terrain_cols),-9999,np.float32)
        tr=from_bounds(*bounds,terrain_cols,terrain_rows)
        reproject(rasterio.band(dem,1),terrain,src_transform=dem.transform,src_crs=dem.crs,
                  dst_transform=tr,dst_crs=4326,dst_nodata=-9999,resampling=Resampling.bilinear)
    if (terrain==-9999).any():
        # Rectangular geographic envelope includes tiny slivers outside projected rectangle.
        from scipy.ndimage import distance_transform_edt
        bad=terrain==-9999;inds=distance_transform_edt(bad,return_distances=False,return_indices=True)
        terrain[bad]=terrain[tuple(inds[:,bad])]
    assert terrain.min()>=0 and terrain.max()<6553.5
    terrain_meta=blob(OUT/'terrain.u16.gz',np.floor(terrain*10).astype('<u2'))
    terrain_meta.update(rows=terrain_rows,cols=terrain_cols,bbox=list(bounds),scale=.1,purpose='Display grid only; physics uses projected DEM')
    regional=np.frombuffer(gzip.decompress((ROOT/'sources/S01W079.hgt.gz').read_bytes()),'>i2').reshape(3601,3601)[::12,::12]
    assert (regional!=-32768).all()
    regional_meta=blob(OUT/'regional.i16.gz',regional.astype('<i2'))
    regional_meta.update(rows=301,cols=301,bbox=[-79,-1,-78,0],scale=1,posts=True,purpose='Coarse surrounding display only')
    meta={'version':'sangolqui-kestrel-v1','calibrated':False,'simulator':'Kestrel v1.2.1',
          'setup':setup,'cell_count':n,'dx_m':dx,'geometry':blob(OUT/'cells.f32.gz',geometry.astype('<f4')),
          'terrain':terrain_meta,'regional':regional_meta,'cases':[],'times_s':list(range(0,9001,180)),
          'urban_metrics_bbox':[-78.49,-.375,-78.395,-.285],
          'benchmark':benchmark(),'encoding':'i32-time-difference-5-fields-v1',
          'fields':['depth_cm','speed_cm_s','surface_offset_from_dem_cm','solids_permyriad','vertical_depth_cm'],
          'notice':'Pruebas hipotéticas de mezcla entrando al río Pita; sin calibración local ni obstáculos de edificios.'}
    def sparse(ds,name,fill=0):
        out=np.full(n,fill,np.float64);iy,ix=positions(ds,west,south,dx)
        ids=lookup[iy,ix];valid=ids>=0;out[ids[valid]]=values(ds,name,fill)[valid];return out
    def stats(h,s):
        wet=h>=.05;u=wet&urban
        return {'wet_km2':float(wet.sum()*dx*dx/1e6),'urban_wet_km2':float(u.sum()*dx*dx/1e6),
             'urban_depth_max_m':float(h[u].max()) if u.any() else 0.,
             'urban_speed_max_m_s':float(s[u].max()) if u.any() else 0.,
             'domain_depth_max_m':float(h.max()),'domain_speed_max_m_s':float(s[wet].max()) if wet.any() else 0.}
    for c in selected:
        folder=ROOT/c['output'];data=np.zeros((51,5,n),np.int32);rows=[]
        snapshot_h=np.zeros(n);snapshot_s=np.zeros(n)
        for i in range(51):
            with Dataset(folder/f'{i:06d}.nc') as ds:
                assert abs(float(ds.time)-i*180)<1e-6
                assert abs(float(ds.central_northing)-(north+south)/2)<.001
                h=sparse(ds,'flow_depth');s=sparse(ds,'flow_speed')
                snapshot_h=np.maximum(snapshot_h,h);snapshot_s=np.maximum(snapshot_s,s)
                assert np.isfinite(h).all() and np.isfinite(s).all() and h.min()>=-1e-8
                base=sparse(ds,'base_elevation');change=sparse(ds,'elevation_change')
                gam=np.sqrt(1+sparse(ds,'x_slope')**2+sparse(ds,'y_slope')**2)
                z=base+change+h/gam-center_z
                z[h<.05]=0
                data[i,0]=np.floor(np.maximum(h,0)*100).astype(np.int32)
                data[i,1]=np.floor(np.maximum(s,0)*100).astype(np.int32)
                data[i,2]=np.rint(z*100).astype(np.int32)
                psi=sparse(ds,'solids_fraction')
                assert psi.min()>=-1e-7 and psi.max()<=.65001
                data[i,3]=np.rint(psi*10000).astype(np.int32)
                data[i,4]=np.rint(h/gam*100).astype(np.int32)
                rows.append(stats(h,s))
        delta=np.diff(data,axis=0,prepend=np.zeros_like(data[:1])).astype('<i4')
        assert np.array_equal(np.cumsum(delta,axis=0),data)
        asset=blob(OUT/(c['id']+'.i32.gz'),delta)
        with Dataset(folder/'Maximums.nc') as ds:
            maxh=sparse(ds,'max_depth');maxs=sparse(ds,'max_speed');arrival=sparse(ds,'inundation_time',fill=-1)
            correction={'depth_cells':int((snapshot_h>maxh+1e-9).sum()),
                        'depth_largest_difference_m':float(np.maximum(snapshot_h-maxh,0).max()),
                        'speed_cells':int((snapshot_s>maxs+1e-9).sum()),
                        'speed_largest_difference_m_s':float(np.maximum(snapshot_s-maxs,0).max())}
            maxh=np.maximum(maxh,snapshot_h);maxs=np.maximum(maxs,snapshot_s)
            arrival[maxh<.05]=-1
            maxima=np.stack([np.floor(maxh*100),np.floor(maxs*100),arrival]).astype('<f4')
            assert np.all(data[:,0].max(axis=0)<=np.floor(maxh*100)+1)
        volume=np.genfromtxt(folder/'Volume.txt',delimiter=',',names=True)
        t=volume['time'];q=c['peak_m3_s']
        expected=np.where(t<150,q*t*t/300,np.where(t<900,c['mixture_input_m3']-q*(900-t)**2/1500,c['mixture_input_m3']))
        residual=volume['volume']+volume['total_bed_volume']-expected
        budget=float(abs(residual).max()/c['mixture_input_m3'])
        assert budget<1e-3,'Mixture budget failed '+c['id']
        report={**c,'completed_time_s':9000,'calibrated':False,'mixture_balance_relative_error':budget,
                'envelope_includes_aggregate_and_all_exported_states':True,
                'aggregate_snapshot_differences':correction,
                'metrics_by_frame':rows,'maximums':stats(maxh,maxs),
                'input_sha256':hashlib.sha256((ROOT/c['input']).read_bytes()).hexdigest(),
                'netcdf_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob('*.nc'))}}
        name=c['id']+'-report.json';(OUT/name).write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')
        shutil.copy2(ROOT/c['input'],OUT/(c['id']+'-input.txt'))
        meta['cases'].append({**c,**asset,'frame_count':51,'metrics_by_frame':rows,'maximums':stats(maxh,maxs),
                  'max_asset':blob(OUT/(c['id']+'-maximums.f32.gz'),maxima),
                  'report':name,'mixture_balance_relative_error':budget})
        print(c['id'],n,'display cells',asset['bytes'],'bytes', 'volume error',budget,flush=True)
    # Public building geometry and floors only. No cadastral key or owner attributes.
    original=json.loads((ROOT/'sources/municipal-buildings.geojson').read_text(encoding='utf-8'))
    buildings=[];missing=0
    to_utm=Transformer.from_crs(4326,32717,always_xy=True)
    with rasterio.open(ROOT/'prepared/pita_domain_30m.tif') as dem:
      for f in original['features']:
        g=shape(f['geometry'])
        if g.is_empty or not g.is_valid:continue
        simple=g.simplify(.000005,preserve_topology=True);centroid=simple.representative_point()
        x,y=to_utm.transform(centroid.x,centroid.y)
        if not (west<x<east and south<y<north):continue
        floors=f['properties'].get('n_pisos')
        try:floors=float(floors)
        except (TypeError,ValueError):floors=0
        if not np.isfinite(floors) or floors<=0: floors=1;missing+=1;origin='sin pisos: un piso supuesto'
        else:origin='pisos municipales; altura estimada'
        base=float(next(dem.sample([(x,y)]))[0])
        buildings.append({'type':'Feature','geometry':mapping(simple),'properties':{
            'floors':floors,'height_m':floors*3,'base_m':base,'height_origin':origin}})
    b=gzip.compress(json.dumps({'type':'FeatureCollection','features':buildings},separators=(',',':')).encode(),9,mtime=0)
    (OUT/'buildings.geojson.gz').write_bytes(b)
    meta['buildings']={'file':'buildings.geojson.gz','count':len(buildings),'unknown_floors':missing,
            'source_feature_count':len(original['features']),
            'omitted_features':len(original['features'])-len(buildings),'sha256':hashlib.sha256(b).hexdigest(),
            'bytes':len(b),'height_rule':'3 m por piso; alturas estimadas, no levantadas',
            'source':'https://geoide.ruminahui.gob.ec/server/rest/services/BDD_CATASTRO/catastro/MapServer/1',
            'hydraulic_obstacles':False}
    meta['setup']={k:v for k,v in setup.items() if k!='cases'}
    (OUT/'manifest.json').write_text(json.dumps(meta,ensure_ascii=False),encoding='utf-8')
    print('PACKED',len(meta['cases']),'cases;',len(buildings),'buildings;',sum(p.stat().st_size for p in OUT.iterdir()),'bytes')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cases',nargs='+');a=p.parse_args();main(a.cases)
