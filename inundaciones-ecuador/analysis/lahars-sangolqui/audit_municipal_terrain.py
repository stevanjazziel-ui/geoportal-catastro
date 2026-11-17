"""Cache public municipal elevation samples; compare without modifying solver DEM.

Identify samples are rounded service values, not an original DEM download.
No undocumented vertical datum correction or terrain merging is performed.
"""
import concurrent.futures, hashlib, json, time, urllib.parse, urllib.request
from pathlib import Path
from study_reference import ROOT, WORK
import numpy as np
import rasterio

BASE='https://geoide.ruminahui.gob.ec/image/rest/services/mdt/mdt_gadmur_2024/MapServer'
OUT=ROOT/'sources/municipal-terrain-audit'


def fetch(job):
    i,points=job;path=OUT/f'batch-{i:04d}.json'
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    q={'f':'json','geometry':json.dumps({'points':points,'spatialReference':{'wkid':32717}},separators=(',',':')),
       'geometryType':'esriGeometryMultipoint','sr':'32717','layers':'all:7',
       'tolerance':'0','mapExtent':'779600,9943500,790400,9961100',
       'imageDisplay':'3600,5850,96','returnGeometry':'true','returnUnformattedValues':'true'}
    for attempt in range(4):
        try:
            req=urllib.request.Request(BASE+'/identify?'+urllib.parse.urlencode(q),headers={'User-Agent':'Public-terrain-research/1.0'})
            with urllib.request.urlopen(req,timeout=60) as r:raw=r.read()
            result=json.loads(raw)
            assert 'error' not in result,result.get('error')
            assert not result.get('exceededTransferLimit',False)
            requested={tuple(p) for p in points}
            found=[(f['geometry']['x'],f['geometry']['y']) for f in result['results']]
            assert len(found)==len(set(found)) and set(found)==requested,'Missing, duplicated or shifted sample'
            path.write_bytes(raw);time.sleep(.5)
            return result
        except Exception:
            if attempt==3:raise
            time.sleep(2**attempt)


def main():
    OUT.mkdir(exist_ok=True)
    # Regional 120m audit plus five 5m cross-sections near the critical corridor.
    points={(int(x),int(y)) for y in range(9943600,9961000,120) for x in range(779680,790360,120)}
    points.update((x,y) for y in (9949000,9949500,9950000,9950500,9951000) for x in range(785500,787501,5))
    points=sorted(points,key=lambda p:(p[1],p[0]));jobs=[(i,points[j:j+100]) for i,j in enumerate(range(0,len(points),100))]
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for i,result in enumerate(pool.map(fetch,jobs)):
            results.extend(result['results'])
            if i%20==0:print('Cached',i+1,'/',len(jobs),'batches',flush=True)
    rows=[]
    with rasterio.open(WORK/'prepared/cop_raw_30m.tif') as cop:
        for f in results:
            x,y=f['geometry']['x'],f['geometry']['y']
            value=next(iter(f['attributes'].values()))
            try:z=float(value)
            except (ValueError,TypeError):continue
            if not np.isfinite(z) or not 1000<z<6500:continue
            reference=float(next(cop.sample([(x,y)]))[0])
            rows.append((x,y,z,reference,z-reference))
    arr=np.asarray(rows)
    np.savetxt(OUT/'samples.csv',arr,delimiter=',',header='easting,northing,municipal_service_m,copernicus30m_m,difference_m',comments='',fmt='%.5f')
    delta=arr[:,4]
    report={'service':BASE,'layer':7,'crs':'EPSG:32717','requested_points':len(points),'valid_numeric_samples':len(rows),
            'sampling':'120m regional grid plus five 5m cross-sections; not an original raster or proof of native resolution',
            'difference_m':{'median':float(np.median(delta)),'p05':float(np.percentile(delta,5)),'p95':float(np.percentile(delta,95)),
                            'rmse':float(np.sqrt(np.mean(delta**2))),'max_absolute':float(abs(delta).max())},
            'vertical_datum_confirmed':False,'merged_into_simulation':False,
            'warning':'Spatially variable surface differences and undocumented vertical reference prohibit automatic substitution or assumed bias correction.',
            'samples_sha256':hashlib.sha256((OUT/'samples.csv').read_bytes()).hexdigest()}
    (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
