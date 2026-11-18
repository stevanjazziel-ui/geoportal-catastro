"""Show which canyon elevations the new model actually uses."""
from municipal_study import ROOT,WORK,ORIGINAL
import json,numpy as np,rasterio
from shapely.geometry import LineString
from shapely.ops import unary_union
from pyproj import Transformer
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    timeline=json.loads((ROOT.parent/'dist/data/lahar-study-times/timeline.json').read_text(encoding='utf-8'))
    tr=Transformer.from_crs(4326,32717,always_xy=True)
    river=unary_union([LineString([tr.transform(*p) for p in s['coordinates']]) for s in timeline['segments'] if s['river']=='Pita'])
    fig,axes=plt.subplots(3,1,figsize=(10,9))
    with rasterio.open(ORIGINAL/'prepared/cop_conditioned_30m.tif') as old,rasterio.open(ROOT/'sources/ruminahui-geoservicios-dtm/mdt2023-native3m.tif') as native,rasterio.open(WORK/'prepared/municipal_hybrid_30m.tif') as new:
        for ax,(name,y,approx) in zip(axes,[('La Caldera',9949500,786900),('Pita · antes del tramo sin flujo anterior',9952500,788200),('Pita · tramo intermedio',9955500,788600)]):
            hit=river.intersection(LineString([(780000,y),(792000,y)]));points=[hit] if hit.geom_type=='Point' else [p for p in hit.geoms if p.geom_type=='Point']
            center=min(points,key=lambda p:abs(p.x-approx)).x
            x=center+np.arange(-450,451,3);xy=list(zip(x,np.full(len(x),y)))
            for ds,label,color in [(old,'Terreno global anterior ·30m','#8a8d8a'),(native,'MDT municipal original ·3m','#246e87'),(new,'Terreno incorporado al cálculo ·30m','#b16b32')]:
                z=np.array([p[0] for p in ds.sample(xy)]);assert (z!=ds.nodata).all()
                ax.plot(x-center,z,label=label,color=color,lw=1.7)
            ax.axvline(0,color='#164b52',ls=':',lw=1,label='Cauce cartográfico' if name=='La Caldera' else None)
            ax.set(title=name,ylabel='Cota del producto (m)',xlabel='Distancia transversal al cauce cartográfico (m)');ax.grid(alpha=.2)
    axes[0].legend(fontsize=9)
    fig.suptitle('Relieve municipal y terreno usado por el modelo',fontsize=16)
    fig.text(.5,.001,'Comparación de productos; referencia vertical municipal sin confirmar. La malla física permanece en30m.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.035,1,.96))
    fig.savefig(WORK/'prepared/municipal-integration-profiles.png',dpi=130,bbox_inches='tight');plt.close(fig)
    print('Actual terrain integration profiles rendered.',flush=True)

if __name__=='__main__':main()
