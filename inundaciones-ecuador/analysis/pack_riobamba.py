"""Publish compact local inputs/results, with measured/estimated provenance."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import geopandas as gpd
from affine import Affine
from pyproj import Transformer
from rasterio.warp import reproject,Resampling
from rasterio.transform import from_bounds

ROOT=Path(__file__).resolve().parent
FOLDER=ROOT/'riobamba-runs/grid-24m'
OUT=ROOT/'dist/data/riobamba-local'


def write_binary(name,array):
    data=np.ascontiguousarray(array).tobytes()
    dest=OUT/name
    dest.write_bytes(gzip.compress(data,compresslevel=9,mtime=0))
    return {'file':name,'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}


def main():
    OUT.mkdir(exist_ok=True)
    meta=json.loads((FOLDER/'metadata.json').read_text())
    with np.load(FOLDER/'grid.npz') as f:g={k:f[k] for k in f.files}
    rows,cols=g['mask'].shape;tr=Affine(*meta['transform']);rr,cc=np.indices((rows,cols))
    xx,yy=tr*(cc+.5,rr+.5);project=Transformer.from_crs(meta['crs'],4326,always_xy=True)
    lon,lat=project.transform(xx,yy)
    # Flat concatenated layers; indices in manifest are layer * cell_count.
    layers=np.asarray([lon,lat,g['dem'],g['mask'],g['landcover'],g['anegamiento'],g['channel']],dtype='<f4')
    bundle=write_binary('grid.f32.gz',layers)
    bounds=[float(lon.min()),float(lat.min()),float(lon.max()),float(lat.max())]
    geo=np.full((512,512),-9999,dtype='<f4');source=g['dem'].copy();source[~g['mask']]=-9999
    reproject(source,geo,src_transform=tr,src_crs=meta['crs'],src_nodata=-9999,dst_transform=from_bounds(*bounds,512,512),dst_crs='EPSG:4326',dst_nodata=-9999,resampling=Resampling.bilinear)
    terrain=write_binary('terrain.f32.gz',geo)
    cases=[]
    labels={'rain-1h-no-drainage':'Lluvia 1 h · sin drenaje','rain-1h-inferred-drainage':'Lluvia 1 h · red estimada','rain-24h-no-drainage':'Lluvia 24 h · sin drenaje'}
    for name,label in labels.items():
        folder=FOLDER/name;report=json.loads((folder/'report.json').read_text())
        with np.load(folder/'result.npz') as f:
            # Millimetre display quantization only; original computations Float64.
            depth=np.concatenate([f['frames'],f['max_depth'][None]],axis=0)
            if depth.max()>65.535:raise ValueError('Depth exceeds display encoding')
            packed=np.round(depth*1000).astype('<u2')
            item=write_binary(name+'.u16.gz',packed)
            item.update(id=name,label=label,frame_count=len(f['frames']),times_minutes=f['times_minutes'].tolist(),max_frame_index=len(f['frames']),stats=report['stats'],rain_mm_h=report['rain_mm_h'],rain_hours=report['rain_hours'],duration_hours=report['duration_hours'],context_comparison=report['context_comparison'])
        # Publish complete report excluding machine-specific local path.
        report['network']='Inferred SWMM network, assumptions.json' if 'inferred' in name else report['network']
        (OUT/(name+'-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        item['report']=name+'-report.json';cases.append(item)
    nd=np.load(FOLDER/'network-inferred-1h-v2/network-data.npz');nodes=nd['nodes'];edges=nd['edges']
    project_network=Transformer.from_crs(meta['crs'],4326,always_xy=True)
    nlon,nlat=project_network.transform(nodes[:,0],nodes[:,1])
    network={'nodes':[[round(float(a),7),round(float(b),7),round(float(c),2)] for a,b,c in zip(nlon,nlat,nodes[:,4])],
             'edges':[[int(a),int(b),float(d),int(flag)] for a,b,_,d,flag in edges],
             'assumptions':json.loads((FOLDER/'network-inferred-1h-v2/assumptions.json').read_text()),
             'diagnostics':json.loads((FOLDER/'network-inferred-1h-v2/summary.json').read_text())}
    (OUT/'network.json.gz').write_bytes(gzip.compress(json.dumps(network,separators=(',',':')).encode(),mtime=0))
    audit=json.loads((ROOT/'riobamba-inputs/prepared/audit.json').read_text(encoding='utf-8'))
    context={}
    gpkg=ROOT/'riobamba-inputs/prepared/riobamba-preparacion.gpkg'
    for name in ['cuencas_originales','alcantarillas_cartografia','cotas_CAD_sin_clasificar','anotaciones_hidraulicas']:
        layer=gpd.read_file(gpkg,layer=name)
        if name=='cuencas_originales':layer.geometry=layer.geometry.simplify(15,preserve_topology=True)
        layer=layer.to_crs(4326)
        context[name]=json.loads(layer.to_json(drop_id=True))
    (OUT/'context.json.gz').write_bytes(gzip.compress(json.dumps(context,separators=(',',':')).encode(),mtime=0))
    for file in ['chibunga_H0789_daily_preserved.csv','precipitation_annual_maxima_preserved.csv']:
        (OUT/(file+'.gz')).write_bytes(gzip.compress((ROOT/'riobamba-inputs/prepared'/file).read_bytes(),mtime=0))
    (OUT/'river-series-supplied.csv.gz').write_bytes(gzip.compress((ROOT/'riobamba-inputs/caudales/retr0620828722.csv').read_bytes(),mtime=0))
    for file in ['network.inp','network.rpt','assumptions.json','summary.json']:
        (OUT/(file+'.gz')).write_bytes(gzip.compress((FOLDER/'network-inferred-1h-v2'/file).read_bytes(),mtime=0))
    coarse=json.loads((ROOT/'riobamba-runs/grid-48m/rain-1h-no-drainage/report.json').read_text())
    fine=cases[0]['stats'];cs=coarse['stats']
    sensitivity={'comparison':'Same 1h synthetic rain, same parameter rules, 24m vs 48m; valid masks differ at boundaries.',
                 'area_5cm_24m_km2':fine['max_footprint_km2'],'area_5cm_48m_km2':cs['max_footprint_km2'],
                 'area_relative_change_percent':100*(cs['max_footprint_km2']/fine['max_footprint_km2']-1),
                 'interpretation':'Material grid sensitivity. Spatial extent has not converged; not suitable for parcel or street decisions.'}
    manifest={'version':'riobamba-local-20261112-v1','calibrated':False,'rows':rows,'cols':cols,'cell_count':rows*cols,'dx_m':24,'valid_km2':meta['valid_km2'],
              'bounds':bounds,'grid':bundle,'grid_layers':['longitude','latitude','dem_m','valid_mask','landcover','anegamiento_class','channel'],
              'terrain':dict(terrain,size=512,nodata=-9999),'cases':cases,'metadata':meta,'source_audit':audit,'network':'network.json.gz','sensitivity':sensitivity,
              'notes_es':['Aproximación exploratoria: no calibrada con eventos observados.','Relieve original de 3 m, cálculo a 24 m. Celdas sin terreno válido excluidas.','Lluvias uniformes sintéticas tomadas de máximos anuales suministrados (1950–2025); no representan un período de retorno.','Rugosidad e infiltración estimadas por cobertura 2018; faltan mediciones locales.','Red SWMM con cotas, salidas, captación y diámetros faltantes estimados. Acoplamiento de reboses hacia superficie en un sentido.','Caudales diarios del Chibunga, cuencas y anotaciones CAD revisados; faltan batimetría e hidrogramas de crecida para incorporarlos como frontera hidráulica.','ANEGAMIENTO2 se utiliza como clasificación de contexto; no como una inundación observada.','Sensibilidad a la malla significativa: la extensión inundada aún no converge.','Datum vertical del MDT no documentado; las alturas 3D son relativas al marco local suministrado.']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'published_bytes':sum(p.stat().st_size for p in OUT.iterdir()),'sensitivity':sensitivity,'cases':[{k:i[k] for k in ('id','bytes','stats')} for i in cases]},indent=2))


if __name__=='__main__':main()
