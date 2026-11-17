"""Read small, connected public OSM waterway extracts; stop on ambiguous branches."""
import json, time, unicodedata, urllib.request
from pathlib import Path
from pyproj import Transformer
from study_reference import ROOT

FOLDER=ROOT/'sources/osm-connected-rivers'
TO_UTM=Transformer.from_crs(4326,32717,always_xy=True)


def get(endpoint):
    FOLDER.mkdir(exist_ok=True)
    path=FOLDER/(endpoint.replace('/','-')+'.json')
    if not path.exists():
        req=urllib.request.Request('https://api.openstreetmap.org/api/0.6/'+endpoint+'.json',headers={'User-Agent':'Cotopaxi-study-viewer/1.0'})
        with urllib.request.urlopen(req,timeout=30) as response:b=response.read()
        data=json.loads(b);assert 'elements' in data
        path.write_bytes(b);time.sleep(.6)
    return json.loads(path.read_text(encoding='utf-8'))


def normal(text):return ''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn')


def trace(node,river,minimum_northing):
    seen=set();ways=[]
    for step in range(30):
        incoming=[e for e in get(f'node/{node}/ways')['elements'] if e['type']=='way' and e.get('tags',{}).get('waterway') in ('river','stream') and e['nodes'][-1]==node and e['id'] not in seen]
        preferred=[e for e in incoming if river in normal(e.get('tags',{}).get('name',''))]
        if preferred:incoming=preferred
        if len(incoming)!=1:
            print('Stopped on absent/ambiguous incoming waterways',node,[(e['id'],e.get('tags')) for e in incoming],flush=True);break
        way=incoming[0];data=get(f'way/{way["id"]}/full')
        nodes={e['id']:e for e in data['elements'] if e['type']=='node'}
        coords=[[nodes[n]['lon'],nodes[n]['lat']] for n in way['nodes']]
        upstream=coords[0];northing=TO_UTM.transform(*upstream)[1]
        ways.append({'id':way['id'],'nodes':way['nodes'],'tags':way.get('tags',{}),'geometry':[{'lon':p[0],'lat':p[1]} for p in coords]})
        print('Connected',river,way['id'],'nodes',len(coords),'upstream northing',round(northing,1),flush=True)
        seen.add(way['id']);node=way['nodes'][0]
        if northing<=minimum_northing:break
    return ways


def main():
    ways=trace(306620538,'santa clara',9949000)
    (FOLDER/'santa-clara-connected.json').write_text(json.dumps({'elements':ways},ensure_ascii=False),encoding='utf-8')
    ways=trace(6246873162,'salto',9934000)
    (FOLDER/'salto-connected.json').write_text(json.dumps({'elements':ways},ensure_ascii=False),encoding='utf-8')


if __name__=='__main__':main()
