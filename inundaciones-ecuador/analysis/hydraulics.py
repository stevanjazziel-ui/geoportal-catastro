"""Exploratory local-inertial 2D shallow-water implementation, not a certified solver.
Original code based on the equations described by Bates, Horritt & Fewtrell (2010),
doi:10.1016/j.jhydrol.2010.03.027. No external source code copied.
Staggered face unit-discharge q [m²/s], conservative depth update [m].
Flux donor limiting preserves nonnegative water and mass. Froude cap=1 is a
numerical safeguard; reported, and does not make steep-flow predictions valid.
"""
import numpy as np
G=9.81

def simulate(dem,dx,rain_mm_h=50.,rain_hours=2.,duration_hours=4.,manning=.05,infiltration_mm_h=5.,
             boundary='open',initial_depth=None,snapshot_minutes=15.,max_dt=10.,external=None,domain_mask=None):
    z=np.asarray(dem,dtype=np.float64);ny,nx=z.shape
    if not np.isfinite(z).all():raise ValueError('Missing terrain cannot be simulated')
    if dx<=0 or manning<=0 or rain_mm_h<0 or infiltration_mm_h<0:raise ValueError('Invalid physical input')
    if boundary not in ('open','closed'):raise ValueError('Boundary must be open or closed')
    active=z>0 if domain_mask is None else np.asarray(domain_mask,dtype=bool)
    if active.shape!=z.shape or not active.any():raise ValueError('Invalid domain mask')
    if duration_hours<=0 or snapshot_minutes<=0 or max_dt<=0:raise ValueError('Invalid run duration/time step')
    h=np.zeros_like(z) if initial_depth is None else np.array(initial_depth,dtype=np.float64,copy=True)
    if h.shape!=z.shape or not np.isfinite(h).all() or np.min(h)<0:raise ValueError('Invalid initial depth')
    # Nonpositive terrain is an excluded boundary/sink, not an asserted coastline.
    h[~active]=0
    qx=np.zeros((ny,nx+1));qy=np.zeros((ny+1,nx));area=dx*dx
    initial=float(h.sum()*area);rainvol=lossvol=outvol=externalvol=0.;t=0.;end=duration_hours*3600
    frames=[h.copy()];times=[0.];hydro=[{'minutes':0,'volume_m3':initial,'wet_km2':float((h>=.05).sum()*area/1e6)}]
    next_snap=snapshot_minutes*60;max_depth=h.copy();max_speed=0.;limited_faces=total_faces=0;steps=0
    while t<end-1e-7:
        cfl=.5*dx/(np.sqrt(G*max(float(h.max()),.001))+max_speed+1e-9)
        dt=min(max_dt,cfl,end-t,next_snap-t)
        if external is not None:dt=min(dt,external.next_event(t)-t)
        if t<rain_hours*3600:dt=min(dt,rain_hours*3600-t)
        if dt<1e-6:raise RuntimeError('Time step collapsed; unstable run')
        rain=rain_mm_h/1000/3600 if t<rain_hours*3600 else 0.
        dh=active*rain*dt;h+=dh;rainvol+=float(dh.sum()*area)
        loss=np.minimum(h,active*infiltration_mm_h/1000/3600*dt);h-=loss;lossvol+=float(loss.sum()*area)
        if external is not None:externalvol+=external.apply(h,active,area,dt,t)
        eta=z+h
        # Interior x faces. Water surface gradient drives local-inertial momentum.
        hx=np.maximum(0,np.maximum(eta[:,:-1],eta[:,1:])-np.maximum(z[:,:-1],z[:,1:]))
        hy=np.maximum(0,np.maximum(eta[:-1,:],eta[1:,:])-np.maximum(z[:-1,:],z[1:,:]))
        qxi=(qx[:,1:-1]-G*hx*dt*(eta[:,1:]-eta[:,:-1])/dx)/(1+G*manning**2*dt*np.abs(qx[:,1:-1])/np.maximum(hx,1e-6)**(7/3))
        qyi=(qy[1:-1,:]-G*hy*dt*(eta[1:,:]-eta[:-1,:])/dx)/(1+G*manning**2*dt*np.abs(qy[1:-1,:])/np.maximum(hy,1e-6)**(7/3))
        capx=hx*np.sqrt(G*hx);capy=hy*np.sqrt(G*hy)
        limited_faces+=int((np.abs(qxi)>capx+1e-10).sum()+(np.abs(qyi)>capy+1e-10).sum());total_faces+=qxi.size+qyi.size
        qx[:,1:-1]=np.where(hx>1e-5,np.clip(qxi,-capx,capx),0)
        qy[1:-1,:]=np.where(hy>1e-5,np.clip(qyi,-capy,capy),0)
        # Non-land cannot feed water into the domain; it can receive and remove flow.
        qx[:,1:-1]=np.where((qx[:,1:-1]>0)&~active[:,:-1],0,qx[:,1:-1])
        qx[:,1:-1]=np.where((qx[:,1:-1]<0)&~active[:,1:],0,qx[:,1:-1])
        qy[1:-1,:]=np.where((qy[1:-1,:]>0)&~active[:-1,:],0,qy[1:-1,:])
        qy[1:-1,:]=np.where((qy[1:-1,:]<0)&~active[1:,:],0,qy[1:-1,:])
        if boundary=='open':
            # Critical free outflow at perimeter; zero external inflow, not measured stages.
            qx[:,0]=-h[:,0]*np.sqrt(G*h[:,0]);qx[:,-1]=h[:,-1]*np.sqrt(G*h[:,-1])
            qy[0,:]=-h[0,:]*np.sqrt(G*h[0,:]);qy[-1,:]=h[-1,:]*np.sqrt(G*h[-1,:])
        else:qx[:,0]=qx[:,-1]=0;qy[0,:]=qy[-1,:]=0
        if external is not None:external.boundary(qx,qy,z,h,dt,dx,t,active)
        outgoing=np.maximum(qx[:,1:],0)+np.maximum(-qx[:,:-1],0)+np.maximum(qy[1:,:],0)+np.maximum(-qy[:-1,:],0)
        factor=np.minimum(1,h*dx/np.maximum(outgoing*dt,1e-30))
        qx[:,1:-1]*=np.where(qx[:,1:-1]>=0,factor[:,:-1],factor[:,1:])
        qy[1:-1,:]*=np.where(qy[1:-1,:]>=0,factor[:-1,:],factor[1:,:])
        qx[:,0]*=np.where(qx[:,0]<0,factor[:,0],1);qx[:,-1]*=np.where(qx[:,-1]>0,factor[:,-1],1)
        qy[0,:]*=np.where(qy[0,:]<0,factor[0,:],1);qy[-1,:]*=np.where(qy[-1,:]>0,factor[-1,:],1)
        edge=qx[:,-1].sum()-qx[:,0].sum()+qy[-1,:].sum()-qy[0,:].sum()
        h-=dt/dx*(qx[:,1:]-qx[:,:-1]+qy[1:,:]-qy[:-1,:])
        if float(h.min()) < -1e-8:raise RuntimeError('Negative water depth')
        h=np.maximum(h,0);sink=float(h[~active].sum()*area);h[~active]=0
        outvol+=float(edge*dt*dx)+sink
        max_depth=np.maximum(max_depth,h)
        ux=np.abs((qx[:,1:]+qx[:,:-1])/2)/np.maximum(h,.01)
        uy=np.abs((qy[1:,:]+qy[:-1,:])/2)/np.maximum(h,.01)
        max_speed=float(np.max(np.where(h>.01,np.hypot(ux,uy),0)))
        if not np.isfinite(h).all() or max_speed>100:raise RuntimeError('Unstable result')
        t+=dt;steps+=1
        if t>=next_snap-1e-6 or t>=end-1e-6:
            frames.append(h.copy());times.append(round(t/60,3));hydro.append({'minutes':round(t/60,3),'volume_m3':round(float(h.sum()*area),3),'wet_km2':round(float((h>=.05).sum()*area/1e6),4)})
            next_snap+=snapshot_minutes*60
    final=float(h.sum()*area);residual=initial+rainvol+externalvol-lossvol-outvol-final
    stats={'initial_m3':initial,'rain_m3':rainvol,'external_net_m3':externalvol,'infiltration_m3':lossvol,'outflow_m3':outvol,'boundary_and_sink_net_outflow_m3':outvol,'final_storage_m3':final,
           'mass_residual_m3':residual,'mass_relative_error':abs(residual)/max(initial+rainvol,1),
           'max_depth_m':float(max_depth.max()),'max_footprint_km2':float((max_depth>=.05).sum()*area/1e6),
           'froude_limited_fraction':limited_faces/max(total_faces,1),'steps':steps,
           'numerical_checks_passed':bool(abs(residual)/max(initial+rainvol,1)<1e-8)}
    return {'frames':frames,'times_minutes':times,'hydrograph':hydro,'max_depth':max_depth,'stats':stats}
