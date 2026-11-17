"""Reacquire the exact public sources used by the literature adaptation.

Use the GeoAI Python environment. No account, secret, or source code execution.
Published hashes intentionally reject a changed product pending a fresh review.
"""
from pathlib import Path
import hashlib, json, urllib.request

ROOT=Path(__file__).resolve().parent
SOURCES=[
 ('study2025-figure1.webp','https://www.frontiersin.org/files/Articles/1611579/xml-images/feart-13-1611579-g001.webp',
  'c3d69f055c1faedd719da738cae07b69ac02ba9b9ce9c58a3e193b25ce07d2b8'),
 ('copernicus-glo30-S01W079.tif',
  'https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_S01_00_W079_00_DEM/Copernicus_DSM_COG_10_S01_00_W079_00_DEM.tif',
  '09dca8c4e872a804cacdc87084f32510aec30b6ac18da9e4d1f9d358d1488d4b')]


def main():
    folder=ROOT/'sources';folder.mkdir(exist_ok=True);audit=[]
    for name,url,expected in SOURCES:
        path=folder/name
        if path.exists():data=path.read_bytes()
        else:
            with urllib.request.urlopen(url,timeout=60) as response:data=response.read()
        digest=hashlib.sha256(data).hexdigest()
        if digest!=expected:raise ValueError('Source changed; review required: '+name)
        if not path.exists():path.write_bytes(data)
        audit.append({'file':name,'url':url,'sha256':digest,'bytes':len(data)})
        print('Verified',name,len(data),'bytes',flush=True)
    (folder/'study-reacquisition-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')


if __name__=='__main__':main()
