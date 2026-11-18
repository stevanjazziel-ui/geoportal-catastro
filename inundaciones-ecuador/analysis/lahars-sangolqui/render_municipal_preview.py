"""Preliminary same-time spatial comparison; not a completed-run claim."""
from municipal_study import ROOT,WORK,ORIGINAL,CASE
from study_reference import sha
import json,numpy as np,rasterio
from netCDF4 import Dataset
from pyproj import Transformer
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,LightSource
from matplotlib.patches import Patch

def main():
    frame=240;seconds=frame*15
    w,s,e,n=784800,9948000,789900,9958500
    x=np.arange(w+15,e,30);y=np.arange(s+15,n,30);xx,yy=np.meshgrid(x,y)
    timeline=json.loads((ROOT.parent/'dist/data/lahar-study-times/timeline.json').read_text(encoding='utf-8'))
    tr=Transformer.from_crs(4326,32717,always_xy=True)
    fig,axes=plt.subplots(1,2,figsize=(10,10));provenance=[]
    for ax,(title,folder,case,dem_path) in zip(axes,[('Terreno global anterior',ORIGINAL,'reference-cop30',ORIGINAL/'prepared/cop_conditioned_30m.tif'),('MDT municipal incorporado',WORK,CASE,WORK/'prepared/municipal_hybrid_30m.tif')]):
        path=folder/'runs'/case/f'{frame:06d}.nc'
        with Dataset(path) as d:
            assert float(d.time)==seconds
            cx=np.rint((x-float(d['x'][0]))/30).astype(int);ry=np.rint((y-float(d['y'][0]))/30).astype(int)
            h=np.zeros(xx.shape);validx=(cx>=0)&(cx<len(d.dimensions['x']));validy=(ry>=0)&(ry<len(d.dimensions['y']))
            raw=d['flow_depth'][:].filled(0)
            h[np.ix_(validy,validx)]=raw[np.ix_(ry[validy],cx[validx])]
        with rasterio.open(dem_path) as dem:z=np.asarray([a[0] for a in dem.sample(zip(xx.ravel(),yy.ravel()))]).reshape(xx.shape)
        shade=LightSource(315,45).hillshade(z,vert_exag=1,dx=30,dy=-30)
        ax.imshow(shade*.45+.45,origin='lower',extent=[w,e,s,n],cmap='gray',vmin=0,vmax=1)
        ax.imshow(np.ma.masked_where(h<.05,h),origin='lower',extent=[w,e,s,n],cmap=ListedColormap(['#b36b32']),vmin=0,vmax=1,alpha=.9)
        for segment in timeline['segments']:
            if segment['river']!='Pita':continue
            px,py=tr.transform(*np.array(segment['coordinates']).T);ax.plot(px,py,color='#00dce6',lw=1)
        ax.set(title=title,xlim=(w,e),ylim=(s,n),xlabel='Este UTM17S (m)');ax.ticklabel_format(style='plain',useOffset=False);ax.tick_params(axis='x',rotation=30)
        provenance.append({'case':case,'native_file':str(path.relative_to(ROOT)),'sha256':sha(path),'time_s':seconds})
    axes[0].set_ylabel('Norte UTM17S (m)')
    fig.suptitle('Vista preliminar · minuto60 de150\nMarrón: flujo calculado ≥5cm · Celeste: cauce cartográfico del Pita',fontsize=14)
    fig.text(.5,.005,'Misma entrada de agua y parámetros físicos. La nueva corrida sigue en curso; comparación sin validación predictiva local.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.04,1,.94))
    fig.savefig(WORK/'prepared/preview-municipal-60min.png',dpi=130,bbox_inches='tight');plt.close(fig)
    (WORK/'prepared/preview-municipal-60min.json').write_text(json.dumps({'status':'preliminary','native_snapshots':provenance,'method':'Cell-center flow-depth threshold5cm; each scenario uses its own terrain for hillshade; no depths invented or shifted.'},indent=2),encoding='utf-8')
    print('Preliminary actual native60min comparison rendered.',flush=True)

if __name__=='__main__':main()
