"""Real regional terrain for display only; local hydraulic inputs stay unchanged."""
import gzip,hashlib,io,json,math
from pathlib import Path
import numpy as np
from PIL import Image
from build_data import download

ROOT=Path(__file__).resolve().parent

def main():
    zoom=10;n=256;bounds=[-79.05,-2.05,-78.25,-1.25]
    lon=np.linspace(bounds[0],bounds[2],n);lat=np.linspace(bounds[3],bounds[1],n)
    x=np.floor((lon+180)/360*(256*2**zoom)).astype(int)
    y=np.floor((1-np.arcsinh(np.tan(np.radians(lat)))/math.pi)/2*(256*2**zoom)).astype(int)
    dem=np.full((n,n),np.nan);sources=[]
    for ty in np.unique(y//256):
        for tx in np.unique(x//256):
            url=f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{tx}/{ty}.png'
            path=ROOT/'raw'/f'terrain-{zoom}-{tx}-{ty}.png';raw=download(url,path)
            a=np.asarray(Image.open(io.BytesIO(raw)).convert('RGB'),dtype=float)
            heights=a[:,:,0]*256+a[:,:,1]+a[:,:,2]/256-32768
            rr=np.flatnonzero(y//256==ty);cc=np.flatnonzero(x//256==tx)
            dem[np.ix_(rr,cc)]=heights[np.ix_(y[rr]%256,x[cc]%256)]
            sources.append({'url':url,'sha256':hashlib.sha256(raw).hexdigest()})
    if not np.isfinite(dem).all():raise ValueError('Incomplete context terrain')
    obj={'bbox':bounds,'n':n,'dem':np.round(dem,1).tolist(),'use':'Visualization outside the supplied local DTM only. Not hydraulic terrain or additional simulated area.','source':'Mapzen / Tilezen Terrarium','sources':sources,'attribution':'https://github.com/tilezen/joerd/blob/master/docs/attribution.md','approximate_spacing_m':350}
    dest=ROOT/'dist/data/riobamba-local/regional-context.json.gz'
    dest.write_bytes(gzip.compress(json.dumps(obj,separators=(',',':')).encode(),mtime=0))
    print(json.dumps({'tiles':len(sources),'bytes':dest.stat().st_size,'min_m':float(dem.min()),'max_m':float(dem.max())}))

if __name__=='__main__':main()
