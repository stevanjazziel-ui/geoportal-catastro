"""Independent checks and section estimates from completed native 15-second states.

Section flux is reconstructed from cell-center outputs, not the solver's internal
Riemann face flux. Report it as an estimate; temporal subsampling is a sensitivity
check, not a bound on its spatial or predictive error.
"""
from pathlib import Path
import csv, hashlib, json, shutil, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.deps'))
import numpy as np
from netCDF4 import Dataset
from pyproj import Transformer
from study_reference import ROOT, WORK

FOLDER=WORK/'runs/reference-cop30'
CITY=(-78.49,-.375,-78.395,-.285)
NORTHING=9958500.


def section_flux(h, velocity, gamma, concentration, dx):
    q=h*velocity*gamma*dx
    positive=np.maximum(q,0)
    return {'north_m3_s':float(positive.sum()),'south_m3_s':float((-np.minimum(q,0)).sum()),
            'net_north_m3_s':float(q.sum()),'solids_north_m3_s':float((positive*concentration).sum()),
            'water_north_m3_s':float((positive*(1-concentration)).sum())}


def main():
    manifest=json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
    execution=json.loads((WORK/'runs/engine-exit.json').read_text(encoding='utf-8'))
    assert execution['returncode']==0,'Solver failed; no publication'
    assert execution['input_sha256']==manifest['input_sha256']
    assert execution['engine_sha256']==manifest['engine_sha256']
    restart_test=json.loads((ROOT/'runs/benchmark-native-restart-v2/report.json').read_text(encoding='utf-8'))
    assert restart_test['passed'] and restart_test['engine_sha256']==execution['engine_sha256']
    assert 'FATAL ERROR' not in (FOLDER.parent/(FOLDER.name+'.log')).read_text(encoding='utf-8',errors='replace').upper()
    budget=np.genfromtxt(FOLDER/'Volume.txt',delimiter=',',names=True)
    assert abs(float(budget['time'][-1])-9000)<1e-6,'Refuse incomplete run'
    assert len(budget)==601 and np.allclose(budget['time'],np.arange(601)*15,atol=1e-6)
    q=manifest['sum_rounded_peaks_m3_s'];t=budget['time'];vin=manifest['water_input_m3']
    expected=np.where(t<150,q*t*t/300,np.where(t<900,vin-q*(900-t)**2/1500,vin))
    error=float(abs(budget['volume']+budget['total_bed_volume']-expected).max()/vin)
    assert error<.001,'Conservation failure'
    projected=Transformer.from_crs(4326,32717,always_xy=True)
    geographic=Transformer.from_crs(32717,4326,always_xy=True)
    xlo=projected.transform(CITY[0],CITY[1])[0];xhi=projected.transform(CITY[2],CITY[1])[0]
    with Dataset(FOLDER/'Maximums.nc') as ds:
        mx=np.asarray(ds['x'][:]);my=np.asarray(ds['y'][:])
        mh=ds['max_depth'][:].filled(0);ms=ds['max_speed'][:].filled(0)
        mt_h=ds['t_max_depth'][:].filled(-1);mt_s=ds['t_max_speed'][:].filled(-1)
    original_mh=mh.copy();original_ms=ms.copy()
    hydro=[];first_city=None;first_section=None;maxh=0.;maxv=0.;hashes={}
    depth_location=None;speed_location=None
    reference=json.loads((ROOT/'study2017-sections.json').read_text(encoding='utf-8'))
    station_records=[]
    for section in reference['sections']:
        ends=np.array(section['endpoints'],float)
        n=int(np.ceil(np.linalg.norm(ends[1]-ends[0])/15))+1
        sample=ends[0]+np.linspace(0,1,n)[:,None]*(ends[1]-ends[0])
        station_records.append({'section':section,'sample_xy':sample,'first_wet_s':None,
                                'sampled_max_depth_m':0.,'sampled_max_speed_m_s':0.})
    grid_key=None;urban=None
    for i in range(601):
        path=FOLDER/f'{i:06d}.nc';assert path.exists()
        with Dataset(path) as d:
            sec=float(d.time);assert abs(sec-i*15)<1e-6
            assert str(d.crs_epsg).lower() in ('32717','epsg:32717')
            assert abs(float(d.deltaX)-30)<1e-8 and abs(float(d.deltaY)-30)<1e-8
            x=np.asarray(d['x'][:]);y=np.asarray(d['y'][:])
            assert (np.diff(x)>0).all() and (np.diff(y)>0).all()
            key=(len(x),len(y),float(x[0]),float(y[0]),float(x[-1]),float(y[-1]))
            if key!=grid_key:
                xx,yy=np.meshgrid(x,y)
                lon,lat=geographic.transform(xx,yy)
                urban=(lon>=CITY[0])&(lon<=CITY[2])&(lat>=CITY[1])&(lat<=CITY[3])
                grid_key=key
            h=d['flow_depth'][:].filled(0);v=d['flow_speed'][:].filled(0)
            psi=d['solids_fraction'][:].filled(0)
            assert np.isfinite(h).all() and h.min()>=-1e-8
            assert np.isfinite(v).all() and psi.min()>=-1e-7 and psi.max()<=.65001
            ix=int(round((float(x[0])-float(mx[0]))/30));iy=int(round((float(y[0])-float(my[0]))/30))
            assert ix>=0 and iy>=0 and ix+len(x)<=len(mx) and iy+len(y)<=len(my)
            region=np.s_[iy:iy+len(y),ix:ix+len(x)]
            old_h=mh[region];old_s=ms[region]
            mt_h[region]=np.where(h>old_h,sec,mt_h[region]);mt_s[region]=np.where(v>old_s,sec,mt_s[region])
            mh[region]=np.maximum(old_h,h);ms[region]=np.maximum(old_s,v)
            wet=urban&(h>=.05)
            if wet.any():
                if first_city is None:first_city=sec
                local_h=float(h[wet].max());local_v=float(v[wet].max())
                if local_h>maxh:
                    rh,ch=np.unravel_index(np.argmax(np.where(wet,h,-np.inf)),h.shape)
                    gamma=float(np.sqrt(1+float(d['x_slope'][rh,ch])**2+float(d['y_slope'][rh,ch])**2))
                    depth_location={'lon':float(lon[rh,ch]),'lat':float(lat[rh,ch]),'time_s':sec,
                                    'slope_normal_depth_m':local_h,'vertical_depth_m':local_h/gamma}
                    maxh=local_h
                if local_v>maxv:
                    rv,cv=np.unravel_index(np.argmax(np.where(wet,v,-np.inf)),v.shape)
                    speed_location={'lon':float(lon[rv,cv]),'lat':float(lat[rv,cv]),'time_s':sec,
                                    'depth_m_at_speed_max':float(h[rv,cv])}
                    maxv=local_v
            for station in station_records:
                sample=station['sample_xy']
                cols=np.rint((sample[:,0]-x[0])/30).astype(int)
                rows=np.rint((sample[:,1]-y[0])/30).astype(int)
                inside=(cols>=0)&(cols<len(x))&(rows>=0)&(rows<len(y))
                if not inside.any():continue
                cells=np.unique(np.c_[rows[inside],cols[inside]],axis=0)
                hh=h[cells[:,0],cells[:,1]];vv=v[cells[:,0],cells[:,1]]
                water=hh>=.05
                if water.any():
                    if station['first_wet_s'] is None:station['first_wet_s']=sec
                    station['sampled_max_depth_m']=max(station['sampled_max_depth_m'],float(hh[water].max()))
                    station['sampled_max_speed_m_s']=max(station['sampled_max_speed_m_s'],float(vv[water].max()))
            sel=(x>=xlo)&(x<=xhi)
            row=np.searchsorted(y,NORTHING)
            record={'time_s':sec,'north_m3_s':0.,'south_m3_s':0.,'net_north_m3_s':0.,
                    'solids_north_m3_s':0.,'water_north_m3_s':0.}
            if sel.any() and 0<row<len(y):
                rr=[row-1,row];f=(NORTHING-y[row-1])/(y[row]-y[row-1]);weights=np.array([1-f,f])[:,None]
                hh=h[rr][:,sel];ps=psi[rr][:,sel]
                vy=d['y_velocity'][rr,:].filled(0)[:,sel]
                bx=d['x_slope'][rr,:].filled(0)[:,sel];by=d['y_slope'][rr,:].filled(0)[:,sel]
                gam=np.sqrt(1+bx*bx+by*by)
                # Interpolate fluxes, rather than products of separately averaged fields.
                part=[section_flux(hh[k],vy[k],gam[k],ps[k],30) for k in range(2)]
                record.update({key:float(sum(part[k][key]*weights[k,0] for k in range(2))) for key in part[0]})
                if first_section is None and ((hh>=.05)&(vy>0)).any():first_section=sec
            hydro.append(record)
        hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        if i%120==0:print('Verified native state',i,'of 600',flush=True)
    a=np.array([[r[k] for k in hydro[0]] for r in hydro],float);times=a[:,0]
    volumes={key.replace('_m3_s','_m3'):float(np.trapezoid(a[:,j],times)) for j,key in enumerate(hydro[0]) if j}
    sensitivity={key.replace('_m3_s','_m3'):float(np.trapezoid(a[::2,j],times[::2])) for j,key in enumerate(hydro[0]) if j}
    (WORK/'prepared').mkdir(exist_ok=True)
    derived=WORK/'prepared/display-maximums.nc';shutil.copy2(FOLDER/'Maximums.nc',derived)
    with Dataset(derived,'r+') as ds:
        ds['max_depth'][:]=mh;ds['max_speed'][:]=ms
        ds['t_max_depth'][:]=mt_h;ds['t_max_speed'][:]=mt_s
        ds.setncattr('delivery_envelope','Union of original aggregate and all 601 exported states; original file retained unchanged')
    corrections={'depth_cells':int((mh>original_mh+1e-9).sum()),'max_depth_correction_m':float((mh-original_mh).max()),
                 'speed_cells':int((ms>original_ms+1e-9).sum()),'max_speed_correction_m_s':float((ms-original_ms).max())}
    manifest['status']='completed_numerically_checked'
    (WORK/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'scenario':manifest,'execution':execution,'completed_time_s':9000,'native_frames_checked':601,
            'independent_native_restart_test':restart_test,
            'volume_balance_relative_error':error,'netcdf_sha256':hashes,
            'original_maximums_sha256':hashlib.sha256((FOLDER/'Maximums.nc').read_bytes()).hexdigest(),
            'display_envelope_sha256':hashlib.sha256(derived.read_bytes()).hexdigest(),
            'display_envelope_all_601_states':True,'aggregate_corrections':corrections,
            'urban_comparison_bbox':list(CITY),'wet_threshold_m':.05,
            'first_urban_wetting_bracket_s':None if first_city is None else [max(0,first_city-15),first_city],
            'urban_max_depth_m':maxh,'urban_max_speed_m_s':maxv,
            'urban_depth_max_location':depth_location,'urban_speed_max_location':speed_location,
            'urban_extrema_definition':'Maxima among601 native15-second samples, with H>=5cm. Depth is slope-normal; vertical component also provided at the depth maximum. Locations can be inside deep canyons, not streets or uniform city depths.',
            'published_section_context':{
                'source':reference['source'],'coordinates_source':reference['coordinates_source'],
                'velocity_source':reference['velocity_source'],
                'limitations':reference['not_identical_physical_quantities'],
                'sampling':'Nearest30m cell centers along published cross-section lines sampled every15m; duplicates removed; native outputs every15seconds; H>=5cm threshold. No internal Riemann flux inferred at these lines.',
                'sections':[{**s['section'],'first_wetting_bracket_s':None if s['first_wet_s'] is None else [max(0,s['first_wet_s']-15),s['first_wet_s']],
                             'sampled_max_depth_m':s['sampled_max_depth_m'],'sampled_max_speed_m_s':s['sampled_max_speed_m_s']} for s in station_records],
                'predictive_validation_passed':False},
            'section':{'northing_utm17s':NORTHING,'easting_range':[xlo,xhi],
                'endpoints_lonlat':[geographic.transform(xlo,NORTHING),geographic.transform(xhi,NORTHING)],
                'description':'Comparison section south of Sangolqui-San Rafael rectangle, spanning both Pita and Santa Clara corridors; not an administrative boundary',
                'method':'Cell-center H * gamma * north velocity * dx, interpolated between adjacent rows; trapezoid integration every 15 s. Not internal numerical face flux.',
                'first_northward_wetting_bracket_s':None if first_section is None else [max(0,first_section-15),first_section],
                'integrated_m3':volumes,'subsampled_30s_integrated_m3':sensitivity,
                'limitations':['Positive transport can count recrossing material more than once; net transport is also reported.',
                    'Subsampling difference tests time sampling only; it does not bound spatial/model error.',
                    'This is not all material that reaches the city or its streets.']},
            'predictive_validation_passed':False,
            'comparison_note':'Published RAMMS arrival times 52 min Sangolqui and 60/71/84 min San Rafael refer to different scenarios and sources. They are not imposed on this run.'}
    (WORK/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (WORK/'section-hydrograph.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(hydro[0]));w.writeheader();w.writerows(hydro)
    print('Completed scientific delivery checks:',{'conservation':error,'first_city_s':first_city,'maximum_city_speed_m_s':maxv,'section_estimates_m3':volumes},flush=True)


if __name__=='__main__':main()
