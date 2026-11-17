"""Audit missing Pita propagation without imposing flow or carving a channel."""
import json, hashlib, sys
from study_reference import ROOT, WORK
import numpy as np
from netCDF4 import Dataset
from pyproj import Transformer
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    timeline_path=ROOT.parent/'dist/data/lahar-study-times/timeline.json'
    timeline=json.loads(timeline_path.read_text(encoding='utf-8'))
    tr=Transformer.from_crs(4326,32717,always_xy=True)
    municipal=np.loadtxt(ROOT/'sources/municipal-terrain-audit/samples.csv',delimiter=',',skiprows=1)
    tree=cKDTree(municipal[:,:2]);records=[]
    fig,ax=plt.subplots(figsize=(8,11),layout='constrained')
    with Dataset(WORK/'prepared/display-maximums.nc') as d:
        x=np.asarray(d['x'][:]);y=np.asarray(d['y'][:]);h=d['max_depth'][:].filled(0)
        ax.imshow(np.ma.masked_where(h<.05,h),extent=[x[0]-15,x[-1]+15,y[0]-15,y[-1]+15],origin='lower',cmap='YlOrBr',vmin=0,vmax=15)
        for s in timeline['segments']:
            if s['river']!='Pita':continue
            xy=np.array([tr.transform(*p) for p in s['coordinates']])
            cc=np.rint((xy[:,0]-x[0])/30).astype(int);rr=np.rint((xy[:,1]-y[0])/30).astype(int)
            valid=(cc>=2)&(cc<len(x)-2)&(rr>=2)&(rr<len(y)-2)
            depth=np.zeros(len(xy))
            for i in np.flatnonzero(valid):depth[i]=h[rr[i]-2:rr[i]+3,cc[i]-2:cc[i]+3].max()
            wet=depth>=.05
            dist,ids=tree.query(xy)
            records.append({'id':s['id'],'sample_count':len(xy),'samples_with_flow_within75m':int(wet.sum()),
                'wet_sample_fraction':float(wet.mean()),'maximum_depth_in_corridor_m':float(depth.max()),
                'municipal_terrain_samples_within100m':int((dist<100).sum())})
            ax.plot(xy[:,0],xy[:,1],color='#00a6bf',lw=1.1,label='Cauce Pita · OpenStreetMap' if s['id']=='pita1' else None)
            middle=xy[len(xy)//2];ax.text(*middle,s['id'],fontsize=10,color='#004e68',bbox=dict(fc='white',alpha=.8,ec='none'))
    ax.set(xlim=(782000,791000),ylim=(9934000,9969000),xlabel='Este UTM17S (m)',ylabel='Norte UTM17S (m)',title='Auditoría del recorrido del Pita\nMarrón: máximo calculado ≥5cm; azul: cauce cartográfico')
    ax.ticklabel_format(style='plain',useOffset=False);ax.legend(loc='lower left');ax.grid(alpha=.2)
    fig.text(.5,.005,'La falta de flujo calculado no demuestra ausencia de peligro. Comparación cartográfica, sin calibración.',ha='center',fontsize=8)
    output=ROOT.parent/'dist/data/sangolqui-lahars'
    fig.savefig(output/'pita-propagation-audit.png',dpi=130,bbox_inches='tight');plt.close(fig)
    report={'status':'unresolved_pita_propagation_gap','scope':'Completed Copernicus30m adaptation only',
        'case_input_sha256':hashlib.sha256((WORK/'inputs/reference-cop30.txt').read_bytes()).hexdigest(),
        'route_source':timeline['geometry_audit']['osm_attribution'],
        'route_sha256':hashlib.sha256(timeline_path.read_bytes()).hexdigest(),
        'method':'At each existing route vertex, maximum H within a5x5 neighborhood of30m native cells (75m square half-width); H>=5cm. Sample fractions are vertex fractions, not length percentages.',
        'segments':records,'predictive_validation_passed':False,
        'conclusion':'Pita3 has no flow within the sampled corridor; downstream wetting near the San Pedro confluence does not establish continuity through Pita3.',
        'cause_status':'Under investigation. Global30m terrain and channel alignment are limitations, not a proven single cause.',
        'not_corrected_by_visual_interpolation':True}
    (output/'pita-propagation-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
