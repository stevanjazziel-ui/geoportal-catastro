"""Spatial diagnostic of simulated wetting and historical proximal deposits.

These scenarios and physical quantities differ. This is not an accuracy score
or predictive validation of city arrival, velocity or transported volume.
"""
import json
from study_reference import ROOT, WORK, sha
import geopandas as gpd
import numpy as np
from netCDF4 import Dataset
from rasterio.features import rasterize
from rasterio.transform import from_origin
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


def render(output):
    completed=json.loads((WORK/'report.json').read_text(encoding='utf-8'))
    assert completed['completed_time_s']==9000
    folder=ROOT/'sources/1877-field-evidence'
    deposits=gpd.read_file(folder/'1877-Deposit-Polygones.shp').to_crs(32717)
    assert len(deposits)==14 and deposits.is_valid.all()
    points=gpd.read_file(folder/'1877-fieldwork points.shp').to_crs(32717)
    bounds=deposits.total_bounds+np.array([-1500,-1500,1500,1500])
    with Dataset(WORK/'prepared/display-maximums.nc') as d:
        x=np.asarray(d['x'][:]);y=np.asarray(d['y'][:])
        ix=np.flatnonzero((x>=bounds[0])&(x<=bounds[2]));iy=np.flatnonzero((y>=bounds[1])&(y<=bounds[3]))
        assert len(ix)>0 and len(iy)>0
        h=d['max_depth'][iy[0]:iy[-1]+1,ix[0]:ix[-1]+1].filled(0)[::-1]
    x=x[ix];y=y[iy];transform=from_origin(x[0]-15,y[-1]+15,30,30)
    mapped=rasterize([(g,1) for g in deposits.geometry],out_shape=h.shape,transform=transform,fill=0,dtype='uint8',all_touched=False).astype(bool)
    wet=h>=.05
    record={'source_doi':'10.5281/zenodo.5866730','license':'CC-BY-4.0',
            'attribution':'Andrade, Saltos, Nogales, Cruz, Lee and Barclay (2022)',
            'original_shapefile_sha256':sha(folder/'1877-Deposit-Polygones.shp'),
            'valid_deposit_polygons':14,'fieldwork_points':len(points),'comparison_crs':'EPSG:32717',
            'deposit_area_vector_m2':float(deposits.geometry.union_all().area),
            'deposit_area_on30m_cell_centers_m2':int(mapped.sum())*900,
            'mapped_deposit_area_with_simulated_wetting_on30m_grid_m2':int((mapped&wet).sum())*900,
            'wet_threshold_m':.05,'not_an_accuracy_score':True,'predictive_validation_passed':False,
            'limitations':['Historical deposited material differs from transient maximum flow thickness.',
                           'Different glacier/source scenario; proximal coverage does not validate city arrivals, velocities or volumes.',
                           'Cell-center rasterization at30m is approximate; no agreement threshold imposed.']}
    (output/'historical-deposits-comparison.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    fig,ax=plt.subplots(figsize=(9,10),layout='constrained')
    extent=(x[0]-15,x[-1]+15,y[0]-15,y[-1]+15)
    ax.imshow(np.ma.masked_where(~wet,wet.astype(float)),extent=extent,origin='upper',
              cmap=ListedColormap(['#bc7b42']),vmin=0,vmax=1,alpha=.65)
    deposits.boundary.plot(ax=ax,color='#216a90',linewidth=1.1,label='Límites de depósitos cartografiados de 1877')
    points.plot(ax=ax,color='#216a90',markersize=4,alpha=.5,label='Puntos de trabajo de campo')
    ax.set(xlabel='Este UTM zona 17 sur (m)',ylabel='Norte UTM zona 17 sur (m)',
           title='Comparación cerca del volcán\nMarrón: zonas mojadas ≥5 cm en la adaptación; azul: evidencia de 1877')
    ax.ticklabel_format(style='plain',useOffset=False);ax.tick_params(axis='x',rotation=30)
    ax.legend(loc='upper right',fontsize=8);ax.grid(alpha=.15)
    fig.text(.5,.005,'Depósitos: Andrade y colaboradores (2022), CC BY 4.0, doi:10.5281/zenodo.5866730.\nFlujo máximo y depósitos son magnitudes diferentes: este contraste no valida un pronóstico.',ha='center',fontsize=8)
    fig.savefig(output/'historical-deposits-comparison.png',dpi=130,bbox_inches='tight');plt.close(fig)
    print('Historical deposit comparison rendered; no predictive accuracy claim.',flush=True)


if __name__=='__main__':render(WORK)
