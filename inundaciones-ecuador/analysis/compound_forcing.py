"""Explicit external forcing for the exploratory solver. No fabricated local data.
Drain exchanges are prescribed signed SWMM-node exchange series, not a sewer solver.
This is a one-way exchange interface, not a dynamically coupled SWMM simulation.
"""
import numpy as np

class CompoundForcing:
    def __init__(self,config,shape,terrain_datum,end_seconds):
        self.shape=shape;self.ports=[];self.stages=[];self.volumes={};self.requested_volumes={}
        self.coverage=end_seconds
        ids=set()
        for item in config.get('surface_exchange',[]):
            kind=item['kind']
            if not item.get('id') or item['id'] in ids:raise ValueError('Exchange ids must be present and unique')
            ids.add(item['id'])
            if kind not in ('river_inflow','swmm_prescribed_exchange'):raise ValueError('Unknown exchange kind')
            cells=item['cells'];weights=np.asarray(item.get('weights',[1]*len(cells)),float)
            if not cells or len(weights)!=len(cells) or not np.isfinite(weights).all() or np.any(weights<=0):raise ValueError('Invalid port cells/weights')
            for y,x in cells:
                if not isinstance(y,int) or not isinstance(x,int):raise ValueError('Cell indices must be integers')
                if not(0<=y<shape[0] and 0<=x<shape[1]):raise ValueError('Exchange outside domain')
            if len(set(map(tuple,cells)))!=len(cells):raise ValueError('Repeated exchange cell')
            t,v=self._series(item,'m3_s')
            if kind=='river_inflow' and np.any(v<0):raise ValueError('River inflow cannot be negative')
            self.ports.append((item['id'],cells,weights/weights.sum(),t,v));self.volumes[item['id']]=0.;self.requested_volumes[item['id']]=0.
        for item in config.get('stage_boundaries',[]):
            if not terrain_datum or item.get('vertical_reference')!=terrain_datum:raise ValueError('Stage and terrain vertical references differ or are missing')
            if not item.get('datum_evidence'):raise ValueError('Datum linkage evidence is required')
            if item['side'] not in ('west','east','north','south'):raise ValueError('Unknown boundary side')
            t,v=self._series(item,'stage_m')
            self.stages.append((item['side'],t,v))
        if len({x[0] for x in self.stages})!=len(self.stages):raise ValueError('Conflicting stage boundaries')
    def _series(self,item,unit):
        if not item.get('source'):raise ValueError('Source is required')
        t=np.asarray(item['seconds'],float);v=np.asarray(item[unit],float)
        if t.ndim!=1 or len(t)<2 or t.shape!=v.shape or not np.isfinite(t).all() or not np.isfinite(v).all():raise ValueError('Invalid time series')
        if np.any(np.diff(t)<=0) or t[0]>0 or t[-1]<self.coverage:raise ValueError('Time series must cover the full run with strictly increasing timestamps')
        return t,v
    def apply(self,h,active,area,dt,t):
        net=0.
        for ident,cells,w,ts,vs in self.ports:
            volume=float(np.interp(t+dt/2,ts,vs))*dt
            self.requested_volumes[ident]+=volume
            for (y,x),weight in zip(cells,w):
                if not active[y,x]:raise ValueError('Exchange cannot target an excluded terrain cell')
                amount=volume*weight
                if amount<0:amount=max(amount,-h[y,x]*area)
                h[y,x]+=amount/area;net+=amount;self.volumes[ident]+=amount
        return net
    def next_event(self,t):
        events=[self.coverage]
        for _,_,_,ts,_ in self.ports:events.extend(ts[ts>t+1e-7])
        for _,ts,_ in self.stages:events.extend(ts[ts>t+1e-7])
        return min(events)
    def boundary(self,qx,qy,z,h,dt,dx,t,active):
        # Local-inertial ghost boundary with exterior bed equal to the edge bed.
        for side,ts,vs in self.stages:
            stage=float(np.interp(t+dt/2,ts,vs));eta=z+h
            if side=='west': bed=z[:,0];inside=eta[:,0];old=qx[:,0];sign=1
            elif side=='east':bed=z[:,-1];inside=eta[:,-1];old=qx[:,-1];sign=-1
            elif side=='north':bed=z[0,:];inside=eta[0,:];old=qy[0,:];sign=1
            else:bed=z[-1,:];inside=eta[-1,:];old=qy[-1,:];sign=-1
            depth=np.maximum(0,np.maximum(stage,inside)-bed)
            q=old+sign*9.81*depth*dt*(stage-inside)/dx
            cap=depth*np.sqrt(9.81*depth);q=np.clip(q,-cap,cap)
            # Excluded cells cannot accept tidal inflow.
            mask=active[:,0] if side=='west' else active[:,-1] if side=='east' else active[0,:] if side=='north' else active[-1,:]
            q=np.where(mask,q,0)
            if side=='west':qx[:,0]=q
            elif side=='east':qx[:,-1]=q
            elif side=='north':qy[0,:]=q
            else:qy[-1,:]=q
