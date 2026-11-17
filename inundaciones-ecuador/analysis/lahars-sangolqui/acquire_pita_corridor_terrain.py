"""Acquire numeric public MDT samples in river corridors; no terrain substitution."""
from study_reference import ROOT,WORK
import concurrent.futures,hashlib,json,time,urllib.parse,urllib.request
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString,Point
from shapely.ops import unary_union
from shapely import contains_xy
import rasterio

OUT=ROOT/'sources/pita-corridor-terrain'
BASE='https://geoide.ruminahui.gob.ec/image/rest/services/mdt/mdt_gadmur_2024/MapServer'

def point_key(geometry):
    sr=geometry.get('spatialReference',{})
    assert sr.get('latestWkid',sr.get('wkid'))==32717
    xy=(geometry['x'],geometry['y']);key=tuple(int(round(v)) for v in xy)
    assert max(abs(a-b) for a,b in zip(xy,key))<1e-5,'Unexpected coordinate shift'
    return key

def fetch(job):
    i,points=job;path=OUT/f'batch-{i:05d}.json'
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    q={'f':'json','geometry':json.dumps({'points':points,'spatialReference':{'wkid':32717}}),
       'geometryType':'esriGeometryMultipoint','sr':'32717','layers':'all:0,1,2,3,4,5,6,7',
       'tolerance':'0','mapExtent':'780000,9946000,792000,9970000','imageDisplay':'4000,8000,96',
       'returnGeometry':'true','returnUnformattedValues':'true'}
    requested={tuple(p) for p in points}
    for attempt in range(4):
        try:
            req=urllib.request.Request(BASE+'/identify',data=urllib.parse.urlencode(q).encode(),headers={'User-Agent':'Public-terrain-research/1.0'})
            with urllib.request.urlopen(req,timeout=45) as response:raw=response.read()
            result=json.loads(raw);assert 'error' not in result,result.get('error')
            assert not result.get('exceededTransferLimit',False)
            found=[(r['layerId'],*point_key(r['geometry'])) for r in result['results']]
            assert len(found)==len(set(found))
            if not all((x,y) in requested for _,x,y in found):
                (OUT/f'rejected-{i:05d}.json').write_bytes(raw)
                raise ValueError('Returned coordinates differ from requested samples; preserved response '+str(i))
            path.write_bytes(raw);time.sleep(.5);return result
        except Exception:
            if attempt==3:raise
            time.sleep(2**attempt)

def main():
    OUT.mkdir(exist_ok=True)
    m=json.loads((ROOT.parent/'dist/data/lahar-study-times/timeline.json').read_text(encoding='utf-8'))
    tr=Transformer.from_crs(4326,32717,always_xy=True)
    lines=[LineString([tr.transform(*p) for p in s['coordinates']]) for s in m['segments'] if s['id'] in ('pita2','pita3','pita4','santaclara2','santaclara3','santaclara4','sanpedro4')]
    corridor=unary_union([line.buffer(450) for line in lines]).union(Point(786900,9949500).buffer(1400))
    x=np.arange(781215,792000,30);y=np.arange(9946815,9970000,30);xx,yy=np.meshgrid(x,y)
    inside=contains_xy(corridor,xx,yy)
    points=np.c_[xx[inside],yy[inside]].astype(int).tolist()
    jobs=[(i,points[j:j+100]) for i,j in enumerate(range(0,len(points),100))]
    requested={tuple(p) for p in points};samples={p:[] for p in requested}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for i,result in enumerate(pool.map(fetch,jobs)):
            for r in result['results']:
                p=point_key(r['geometry'])
                try:z=float(next(iter(r['attributes'].values())))
                except (ValueError,TypeError):continue
                if np.isfinite(z) and 1000<z<6500:samples[p].append((r['layerId'],z))
            if i%20==0:print('corridor terrain',i+1,'/',len(jobs),flush=True)
    rows=[];conflicts=[]
    with rasterio.open(WORK/'prepared/cop_conditioned_30m.tif') as dem:
        for p,values in sorted(samples.items()):
            if not values:continue
            values.sort();spread=max(v[1] for v in values)-min(v[1] for v in values)
            if spread>3:conflicts.append({'xy':p,'values':values});continue
            layer,z=values[0];cop=float(next(dem.sample([p]))[0])
            rows.append((*p,z,cop,layer,len(values),spread))
    arr=np.asarray(rows)
    np.savetxt(OUT/'samples.csv',arr,delimiter=',',header='easting,northing,municipal_m,model_m,layer,overlap_count,overlap_spread_m',comments='',fmt='%.6f')
    report={'source':BASE,'requested_points':len(points),'valid_unambiguous_points':len(rows),
        'no_numeric_coverage':sum(not v for v in samples.values()),'overlap_conflicts':conflicts,
        'query_grid_m':30,'corridor_buffer_m':450,'caldera_buffer_m':1400,
        'native_resolution_confirmed':False,'vertical_datum_confirmed':False,
        'coordinate_rounding_tolerance_m':1e-5,
        'applied_to_model':False,'samples_sha256':hashlib.sha256((OUT/'samples.csv').read_bytes()).hexdigest(),
        'comparison_median_m':float(np.median(arr[:,2]-arr[:,3])) if len(arr) else None,
        'warning':'Sampled service MDT, not original raster. Coverage, overlaps, vertical reference and artificial seams require checking before any new sensitivity simulation.'}
    (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Corridor acquisition complete',len(rows),'/',len(points),'unambiguous elevations',flush=True)

if __name__=='__main__':main()
