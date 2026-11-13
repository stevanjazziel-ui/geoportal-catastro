"""Exploratory local-inertial rain-on-grid solver with spatial fields and explicit masks.
Independent local-run implementation; existing national outputs are not overwritten.
Open mask boundaries are critical free outfalls, not measured river boundaries.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/'.deps'))
import numpy as np
from numba import njit


@njit(cache=True)
def step(z,mask,h,qx,qy,n,loss,rf,rate,dx,dt,opened):
    ny,nx=z.shape;rain=0.;infil=0.;limited=0;faces=0
    for y in range(ny):
        for x in range(nx):
            if mask[y,x]:
                add=rate*rf[y,x]*dt;rain+=add;h[y,x]+=add
                take=min(h[y,x],loss[y,x]*dt);h[y,x]-=take;infil+=take
    for y in range(ny):
        for x in range(nx+1):
            a=x>0 and mask[y,x-1];b=x<nx and mask[y,x]
            if a and b:
                hl=h[y,x-1];hr=h[y,x];zl=z[y,x-1];zr=z[y,x]
                depth=max(0.,max(zl+hl,zr+hr)-max(zl,zr));old=qx[y,x]
                if depth<1e-7:q=0.
                else:
                    nf=.5*(n[y,x-1]+n[y,x]);den=1.
                    if abs(old)>1e-15:den+=9.81*nf*nf*dt*abs(old)/depth**(7./3.)
                    q=(old-9.81*depth*dt*((zr+hr)-(zl+hl))/dx)/den
                    cap=depth*np.sqrt(9.81*depth)
                    if abs(q)>cap:limited+=1;q=max(-cap,min(cap,q))
                faces+=1
            elif opened and a:q=h[y,x-1]*np.sqrt(9.81*h[y,x-1])
            elif opened and b:q=-h[y,x]*np.sqrt(9.81*h[y,x])
            else:q=0.
            qx[y,x]=q
    for y in range(ny+1):
        for x in range(nx):
            a=y>0 and mask[y-1,x];b=y<ny and mask[y,x]
            if a and b:
                hl=h[y-1,x];hr=h[y,x];zl=z[y-1,x];zr=z[y,x]
                depth=max(0.,max(zl+hl,zr+hr)-max(zl,zr));old=qy[y,x]
                if depth<1e-7:q=0.
                else:
                    nf=.5*(n[y-1,x]+n[y,x]);den=1.
                    if abs(old)>1e-15:den+=9.81*nf*nf*dt*abs(old)/depth**(7./3.)
                    q=(old-9.81*depth*dt*((zr+hr)-(zl+hl))/dx)/den
                    cap=depth*np.sqrt(9.81*depth)
                    if abs(q)>cap:limited+=1;q=max(-cap,min(cap,q))
                faces+=1
            elif opened and a:q=h[y-1,x]*np.sqrt(9.81*h[y-1,x])
            elif opened and b:q=-h[y,x]*np.sqrt(9.81*h[y,x])
            else:q=0.
            qy[y,x]=q
    factor=np.ones_like(h)
    for y in range(ny):
        for x in range(nx):
            if mask[y,x]:
                out=max(qx[y,x+1],0.)+max(-qx[y,x],0.)+max(qy[y+1,x],0.)+max(-qy[y,x],0.)
                if out>0:factor[y,x]=min(1.,h[y,x]*dx/(out*dt))
    boundary=0.
    for y in range(ny):
        for x in range(nx+1):
            q=qx[y,x]
            if q>0 and x>0:qx[y,x]*=factor[y,x-1]
            elif q<0 and x<nx:qx[y,x]*=factor[y,x]
            a=x>0 and mask[y,x-1];b=x<nx and mask[y,x]
            if a!=b:boundary+=abs(qx[y,x])
    for y in range(ny+1):
        for x in range(nx):
            q=qy[y,x]
            if q>0 and y>0:qy[y,x]*=factor[y-1,x]
            elif q<0 and y<ny:qy[y,x]*=factor[y,x]
            a=y>0 and mask[y-1,x];b=y<ny and mask[y,x]
            if a!=b:boundary+=abs(qy[y,x])
    vmax=0.;hmax=0.;volume=0.
    for y in range(ny):
        for x in range(nx):
            if mask[y,x]:
                h[y,x]-=dt/dx*(qx[y,x+1]-qx[y,x]+qy[y+1,x]-qy[y,x])
                if h[y,x]<-1e-8:raise ValueError('Negative depth')
                h[y,x]=max(0.,h[y,x]);volume+=h[y,x];hmax=max(hmax,h[y,x])
                if h[y,x]>.01:
                    ux=(qx[y,x]+qx[y,x+1])*.5/h[y,x];uy=(qy[y,x]+qy[y+1,x])*.5/h[y,x]
                    vmax=max(vmax,np.sqrt(ux*ux+uy*uy))
    return rain*dx*dx,infil*dx*dx,boundary*dt*dx,vmax,hmax,volume*dx*dx,limited,faces


def simulate(z,mask,dx,manning,infiltration_mm_h,rain_profile,duration_hours,initial=None,rain_factor=None,
             source_times=None,source_rates=None,source_cells=None,snapshot_minutes=15,max_dt=8,boundary='open',progress=None):
    z=np.asarray(z,np.float64);mask=np.asarray(mask,bool);n=np.broadcast_to(manning,z.shape).astype(float).copy()
    loss=np.broadcast_to(infiltration_mm_h,z.shape).astype(float).copy()/3600000
    rf=np.ones(z.shape) if rain_factor is None else np.asarray(rain_factor,float)
    for a in (z,n,loss,rf):
        if a.shape!=z.shape or not np.isfinite(a).all():raise ValueError('Invalid grid fields')
    if mask.shape!=z.shape or not mask.any() or np.any(n<=0) or np.any(loss<0) or np.any(rf<0):raise ValueError('Invalid physical fields/domain')
    if dx<=0 or duration_hours<=0 or max_dt<=0 or snapshot_minutes<=0 or boundary not in ('open','closed'):raise ValueError('Invalid simulation settings')
    profile=np.asarray(rain_profile,float)
    if profile.ndim!=2 or profile.shape[1]!=2 or profile[0,0]!=0 or np.any(np.diff(profile[:,0])<=0) or np.any(profile[:,1]<0) or not np.isfinite(profile).all():raise ValueError('Invalid rain profile')
    h=np.zeros_like(z) if initial is None else np.asarray(initial,float).copy()
    if h.shape!=z.shape or not np.isfinite(h).all() or np.any(h<0) or np.any(h[~mask]!=0):raise ValueError('Invalid initial state')
    qx=np.zeros((z.shape[0],z.shape[1]+1));qy=np.zeros((z.shape[0]+1,z.shape[1]));end=duration_hours*3600
    if source_times is not None:
        source_times=np.asarray(source_times,float);source_rates=np.asarray(source_rates,float);source_cells=np.asarray(source_cells,int)
        if source_rates.shape!=(len(source_times),len(source_cells)) or source_times[0]!=0 or source_times[-1]<end or np.any(np.diff(source_times)<=0) or np.any(source_rates<0) or not np.isfinite(source_rates).all():raise ValueError('Invalid prescribed overflow')
        if np.any(source_cells<0) or np.any(source_cells[:,0]>=z.shape[0]) or np.any(source_cells[:,1]>=z.shape[1]) or not mask[source_cells[:,0],source_cells[:,1]].all():raise ValueError('Invalid overflow cells')
    initial_volume=float(h.sum()*dx*dx);rain=lossvol=outflow=external=0.;vmax=0.;hmax=float(h.max());t=0.;next_snap=snapshot_minutes*60;lim=faces=steps=0
    frames=[h.astype(np.float32).copy()];times=[0.];max_depth=h.copy();hydro=[]
    while t<end-1e-7:
        dt=min(max_dt,.45*dx/(np.sqrt(9.81*max(hmax,.001))+vmax+1e-9),end-t,next_snap-t)
        future=profile[:,0][profile[:,0]>t+1e-7]
        if len(future):dt=min(dt,future[0]-t)
        if source_times is not None:
            k=int(np.searchsorted(source_times,t+1e-7,side='right'));dt=min(dt,source_times[min(k,len(source_times)-1)]-t)
        if dt<1e-7:raise RuntimeError('Collapsed time step')
        rate=profile[max(0,np.searchsorted(profile[:,0],t+dt*.5,side='right')-1),1]/3600000
        if source_times is not None:
            k=min(np.searchsorted(source_times,t+dt*.5,side='left'),len(source_times)-1)
            amounts=source_rates[k]*dt;np.add.at(h,(source_cells[:,0],source_cells[:,1]),amounts/(dx*dx));external+=float(amounts.sum())
        rv,iv,ov,vmax,hmax,volume,lf,nf=step(z,mask,h,qx,qy,n,loss,rf,rate,dx,dt,boundary=='open')
        rain+=rv;lossvol+=iv;outflow+=ov;lim+=lf;faces+=nf;max_depth=np.maximum(max_depth,h);t+=dt;steps+=1
        if not np.isfinite(volume) or vmax>100:raise RuntimeError('Unstable run')
        if t>=next_snap-1e-7 or t>=end-1e-7:
            frames.append(h.astype(np.float32).copy());times.append(t/60);hydro.append({'minutes':t/60,'volume_m3':volume,'wet_km2':float((h>=.05).sum()*dx*dx/1e6)})
            next_snap+=snapshot_minutes*60
            if progress:progress(t/end,steps)
    final=float(h.sum()*dx*dx);residual=initial_volume+rain+external-lossvol-outflow-final
    stats={'initial_m3':initial_volume,'direct_rain_m3':rain,'prescribed_overflow_m3':external,'infiltration_m3':lossvol,'boundary_outflow_m3':outflow,'final_m3':final,
           'mass_residual_m3':residual,'mass_relative_error':abs(residual)/max(1,initial_volume+rain+external),'max_depth_m':float(max_depth.max()),
           'max_footprint_km2':float((max_depth>=.05).sum()*dx*dx/1e6),'froude_limited_fraction':lim/max(1,faces),'steps':steps}
    if stats['mass_relative_error']>1e-8:raise RuntimeError('Mass balance failed')
    return {'frames':np.asarray(frames),'times_minutes':times,'max_depth':max_depth,'hydrograph':hydro,'stats':stats}
