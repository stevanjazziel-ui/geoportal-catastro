"""Reproducible exploratory terrain screening. No rainfall forecast or hydraulic solver.
Uses actual Mapzen Terrain Tiles; missing downloads fail the city, never become zero.
Population is only a GeoNames selection aid, not current census exposure.
"""
import concurrent.futures as cf
import datetime, hashlib, heapq, io, json, math, pathlib, time, urllib.request, zipfile
import numpy as np
from PIL import Image

ROOT=pathlib.Path(__file__).parent
CACHE=ROOT/'raw'; OUT=ROOT/'dist'/'data'
CACHE.mkdir(exist_ok=True); OUT.mkdir(parents=True,exist_ok=True)
ZOOM=11; N=192; CORE=128
PROV={'01':'Galápagos','02':'Azuay','03':'Bolívar','04':'Cañar','05':'Carchi','06':'Chimborazo','07':'Cotopaxi','08':'El Oro','09':'Esmeraldas','10':'Guayas','11':'Imbabura','12':'Loja','13':'Los Ríos','14':'Manabí','15':'Morona Santiago','17':'Pastaza','18':'Pichincha','19':'Tungurahua','20':'Zamora Chinchipe','22':'Sucumbíos','23':'Napo','24':'Orellana','25':'Santa Elena','26':'Santo Domingo de los Tsáchilas'}
COSTA={'08','09','10','13','14','25','26'}; AMAZON={'15','17','20','22','23','24'}

def download(url,path):
    if path.exists(): return path.read_bytes()
    error=None
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'EcuadorTerrainScreening/1.0 (+public research)'})
            data=urllib.request.urlopen(req,timeout=45).read()
            tmp=path.with_suffix(path.suffix+'.part'); tmp.write_bytes(data); tmp.replace(path)
            return data
        except Exception as e: error=e; time.sleep(attempt+1)
    raise RuntimeError(f'Download failed: {url}: {error}')

def cities():
    b=download('https://download.geonames.org/export/dump/EC.zip',CACHE/'EC.zip')
    rows=[]
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        for line in z.read('EC.txt').decode('utf-8').splitlines():
            x=line.split('\t')
            if x[6]!='P' or x[7] not in ('PPL','PPLA','PPLC','PPLA2'):continue
            rows.append(dict(id=x[0],name=x[1],lat=float(x[4]),lon=float(x[5]),code=x[10],population=int(x[14] or 0),feature=x[7],geonames_date=x[18]))
    top=sorted([r for r in rows if r['code']!='01'],key=lambda r:r['population'],reverse=True)[:30]
    selected={r['id']:r for r in top}
    for r in rows:
        if r['feature'] in ('PPLA','PPLC'):selected[r['id']]=r
    for r in selected.values():
        r['province']=PROV.get(r['code'],r['code'])
        r['region']='Insular' if r['code']=='01' else 'Costa' if r['code'] in COSTA else 'Amazonía' if r['code'] in AMAZON else 'Sierra'
        r['selection']='Capital provincial / nacional' if r['feature'] in ('PPLA','PPLC') else 'Entre las 30 localidades continentales con mayor población en GeoNames'
    return sorted(selected.values(),key=lambda r:r['population'],reverse=True)

def world_px(lon,lat):
    total=256*2**ZOOM
    return (lon+180)/360*total,(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*total

def from_px(x,y):
    total=256*2**ZOOM
    return x/total*360-180,math.degrees(math.atan(math.sinh(math.pi*(1-2*y/total))))

def read_dem(c):
    cx,cy=world_px(c['lon'],c['lat']); left=int(round(cx-N/2)); top=int(round(cy-N/2))
    dem=np.full((N,N),np.nan,np.float32); urls=[]
    for ty in range(top//256,(top+N-1)//256+1):
        for tx in range(left//256,(left+N-1)//256+1):
            url=f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{ZOOM}/{tx}/{ty}.png'
            raw=download(url,CACHE/f'terrain-{ZOOM}-{tx}-{ty}.png'); urls.append(url)
            rgb=np.asarray(Image.open(io.BytesIO(raw)).convert('RGB'),dtype=np.float32)
            a=rgb[:,:,0]*256+rgb[:,:,1]+rgb[:,:,2]/256-32768
            x0=max(left,tx*256); y0=max(top,ty*256); x1=min(left+N,(tx+1)*256); y1=min(top+N,(ty+1)*256)
            dem[y0-top:y1-top,x0-left:x1-left]=a[y0-ty*256:y1-ty*256,x0-tx*256:x1-tx*256]
    if not np.isfinite(dem).all():raise ValueError('Incomplete terrain coverage')
    spacing=math.cos(math.radians(c['lat']))*2*math.pi*6378137/(256*2**ZOOM)
    return dem,spacing,left,top,urls

NEIGH=[(-1,-1,math.sqrt(2)),(-1,0,1),(-1,1,math.sqrt(2)),(0,-1,1),(0,1,1),(1,-1,math.sqrt(2)),(1,0,1),(1,1,math.sqrt(2))]

def drainage_hand(dem,spacing,threshold_km2=1):
    """Priority-flood conditioning; acyclic D8 routing, upslope area and HAND to derived channels.
    Boundary outlets retained; basins with no qualifying channel remain unknown (NaN).
    """
    h,w=dem.shape; filled=dem.copy(); seen=np.zeros((h,w),bool); heap=[]; order=[]; parent=np.full(h*w,-1,np.int32)
    for y in range(h):
        for x in range(w):
            if y in (0,h-1) or x in (0,w-1):
                i=y*w+x;seen[y,x]=True;heapq.heappush(heap,(float(dem[y,x]),i))
    while heap:
        elev,i=heapq.heappop(heap); order.append(i); y,x=divmod(i,w)
        for dy,dx,_ in NEIGH:
            yy,xx=y+dy,x+dx
            if 0<=yy<h and 0<=xx<w and not seen[yy,xx]:
                seen[yy,xx]=True;j=yy*w+xx;parent[j]=i
                z=max(float(dem[yy,xx]),elev);filled[yy,xx]=z;heapq.heappush(heap,(z,j))
    rank=np.empty(h*w,np.int32);rank[order]=np.arange(h*w)
    flat=filled.ravel()
    for i in order:
        if parent[i]<0:continue
        y,x=divmod(i,w);best=-1.;chosen=parent[i]
        for dy,dx,dist in NEIGH:
            yy,xx=y+dy,x+dx
            if 0<=yy<h and 0<=xx<w:
                j=yy*w+xx
                if rank[j]<rank[i]:
                    drop=(float(flat[i])-float(flat[j]))/dist
                    if drop>best:best=drop;chosen=j
        parent[i]=chosen
    accum=np.ones(h*w,np.float64)*spacing**2
    for i in reversed(order):
        if parent[i]>=0:accum[parent[i]]+=accum[i]
    channel=accum>=threshold_km2*1e6
    ref=np.full(h*w,np.nan,np.float64)
    for i in order:
        if channel[i]:ref[i]=dem.ravel()[i]
        elif parent[i]>=0:ref[i]=ref[parent[i]]
    hand=np.maximum(0,dem.ravel()-ref).reshape(h,w)
    return hand,channel.reshape(h,w),accum.reshape(h,w),filled

def json_array(a):
    return [[None if not np.isfinite(v) else round(float(v),2) for v in row] for row in a]

def analyze(c):
    dem,sp,left,top,urls=read_dem(c)
    hand,channel,acc,filled=drainage_hand(dem,sp)
    gy,gx=np.gradient(dem,sp);slope=np.degrees(np.arctan(np.hypot(gx,gy)))
    # Support is a 128-cell square around a named point, NOT an urban or canton polygon.
    b=(N-CORE)//2;s=np.s_[b:b+CORE,b:b+CORE]
    z=dem[s];hh=hand[s];sl=slope[s];ch=channel[s];aa=acc[s]/1e6
    land=z>0;known=land & np.isfinite(hh)
    index=.75*np.exp(-hh/5)+.25*np.exp(-sl/5)
    high=known & (hh<=5)&(sl<=5);moderate=known & ~high & (hh<=15)&(sl<=12)
    classes=np.where(~land,0,np.where(~known,4,np.where(high,3,np.where(moderate,2,1)))).astype('uint8')
    denom=int(land.sum()); valid=int(known.sum())
    hp=100*int(high.sum())/denom if denom else None
    # This is a relative screening priority based only on share of window with favorable terrain.
    priority='Sin datos' if not denom or valid/denom<.6 else 'Alta' if hp>=30 else 'Media' if hp>=10 else 'Localizada'
    west,north=from_px(left+b,top+b);east,south=from_px(left+b+CORE,top+b+CORE)
    stats={**c,'status':'ok','priority':priority,'high_pct':round(hp,1) if hp is not None else None,
           'moderate_pct':round(100*int(moderate.sum())/denom,1) if denom else None,
           'coverage_pct':round(valid/denom*100,1) if denom else 0,'window_km2':round(CORE*CORE*sp**2/1e6,2),
           'land_km2':round(denom*sp**2/1e6,2),'high_km2':round(int(high.sum())*sp**2/1e6,2),
           'resolution_m':round(sp,1),'elevation_median':round(float(np.median(z[land])),1) if denom else None,
           'slope_median':round(float(np.median(sl[land])),1) if denom else None,
           'bbox':[west,south,east,north], 'terrain_urls':urls,
           'unknown_pct':round(100*(denom-valid)/denom,1) if denom else 100}
    payload={'id':c['id'],'n':CORE,'bbox':stats['bbox'],'spacing_m':round(sp,3),'dem':json_array(z),
             'hand':json_array(hh),'slope':json_array(sl),'class':classes.tolist(),'channel':ch.astype('uint8').tolist()}
    (OUT/f"{c['id']}.json").write_text(json.dumps(payload,separators=(',',':'),allow_nan=False),encoding='utf-8')
    # Locally generated transparent raster, no invented flood polygon.
    palette=np.array([[0,0,0,0],[78,145,126,45],[237,178,67,155],[223,93,72,185],[139,148,158,70]],np.uint8)
    Image.fromarray(palette[classes]).save(OUT/f"{c['id']}.png")
    print(c['name'],priority,hp,flush=True)
    return stats

def main():
    chosen=cities(); print('Selected',len(chosen),flush=True)
    results=[]
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(analyze,c):c for c in chosen}
        for f in cf.as_completed(jobs):
            c=jobs[f]
            try:results.append(f.result())
            except Exception as e:
                print('FAILED',c['name'],str(e),flush=True)
                results.append({**c,'status':'error','priority':'Sin datos','error':str(e)})
    results.sort(key=lambda c:c['population'],reverse=True)
    meta={'created':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method_version':'terrain-screening-v1',
          'selection':'30 localidades continentales con mayor población GeoNames más capitales provinciales/nacional (PPLA/PPLC). No es un ranking censal INEC.',
          'cities':results,'sources':[
          {'name':'GeoNames · Ecuador','url':'https://download.geonames.org/export/dump/','license':'CC BY 4.0; población de referencia, fechas por registro'},
          {'name':'Mapzen / Tilezen Terrain Tiles · AWS','url':'https://registry.opendata.aws/terrain-tiles/','license':'Atribuciones por fuente: https://github.com/tilezen/joerd/blob/master/docs/attribution.md'},
          {'name':'SNGR · informes oficiales de lluvias','url':'https://www.gestionderiesgos.gob.ec/sitrep-afectaciones-por-lluvias-2025-2026/','use':'Referencia externa; no se usó como etiqueta ni validación del modelo'}]}
    (OUT/'cities.json').write_text(json.dumps(meta,ensure_ascii=False,indent=1,allow_nan=False),encoding='utf-8')
    (ROOT/'analysis-summary.json').write_text(json.dumps({'cities':len(results),'success':sum(c['status']=='ok' for c in results),'failed':[c['name'] for c in results if c['status']!='ok']},indent=2),encoding='utf-8')
    manifest=[{'file':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in CACHE.glob('*') if p.is_file()]
    (ROOT/'source-manifest.json').write_text(json.dumps(manifest,indent=1),encoding='utf-8')
    print('DONE',len(results),flush=True)

if __name__=='__main__':main()
