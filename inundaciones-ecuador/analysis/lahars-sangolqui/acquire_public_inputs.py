"""Read-only acquisition of public source metadata, terrain and anonymous buildings."""
from pathlib import Path
import concurrent.futures as cf
import hashlib,json,urllib.request,urllib.parse

ROOT=Path(__file__).resolve().parent
S=ROOT/'sources'
L='https://geoide.ruminahui.gob.ec/image/rest/services/LAHAR/lahar_cotopaxi_zona_norte/MapServer'
B='https://geoide.ruminahui.gob.ec/server/rest/services/BDD_CATASTRO/catastro/MapServer/1'

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Sangolqui-geospatial-research/1.0'})
    return urllib.request.urlopen(req,timeout=60).read()

def query(params):return json.loads(get(B+'/query?'+urllib.parse.urlencode(params)))

def main():
    S.mkdir(exist_ok=True);audit=[]
    assets={'municipal-lahar.json':L+'?f=pjson',
            'municipal-building-metadata.json':B+'?f=pjson',
            'S01W079.hgt.gz':'https://s3.amazonaws.com/elevation-tiles-prod/skadi/S01/S01W079.hgt.gz'}
    for name,url in assets.items():
        p=S/name
        if not p.exists():p.write_bytes(get(url))
        audit.append({'file':name,'url':url,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    path=S/'municipal-buildings.geojson'
    if not path.exists():
        ids=sorted(query({'f':'json','where':'1=1','returnIdsOnly':'true'})['objectIds'])
        def page(part):
            d=query({'f':'geojson','objectIds':','.join(map(str,part)),
                     'outFields':'objectid,n_pisos','returnGeometry':'true','outSR':4326})
            if d.get('error') or d.get('exceededTransferLimit'):raise ValueError('Building query failed or truncated')
            return d['features']
        rows=[]
        with cf.ThreadPoolExecutor(max_workers=2) as pool:
            for part in pool.map(page,[ids[i:i+1000] for i in range(0,len(ids),1000)]):rows.extend(part)
        if len(rows)!=len(ids):raise ValueError('Incomplete building download')
        path.write_text(json.dumps({'type':'FeatureCollection','features':rows},separators=(',',':')),encoding='utf-8')
    d=json.loads(path.read_text(encoding='utf-8'))
    assert all(set(f['properties'])<= {'objectid','n_pisos'} for f in d['features'])
    audit.append({'file':path.name,'url':B,'fields':['objectid','n_pisos'],
                  'count':len(d['features']),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (S/'public-source-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print('Public source inputs verified:',len(audit),'records; buildings:',len(d['features']))

if __name__=='__main__':main()
