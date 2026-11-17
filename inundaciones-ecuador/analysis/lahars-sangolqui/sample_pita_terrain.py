"""Read public terrain cross-sections near the missing Pita propagation."""
import json,concurrent.futures
from study_reference import ROOT,WORK
import audit_municipal_terrain as api
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString
import rasterio

def main():
    output=ROOT/'sources/pita-terrain-diagnosis';output.mkdir(exist_ok=True)
    api.OUT=output
    timeline=json.loads((ROOT.parent/'dist/data/lahar-study-times/timeline.json').read_text(encoding='utf-8'))
    tr=Transformer.from_crs(4326,32717,always_xy=True)
    sections=[];points=set()
    for s in timeline['segments']:
        if s['id'] not in ('pita2','pita3'):continue
        line=LineString([tr.transform(*p) for p in s['coordinates']])
        start=line.length*.75 if s['id']=='pita2' else 0
        for distance in np.arange(start,line.length,150):
            center=np.array(line.interpolate(distance).coords[0]);before=np.array(line.interpolate(max(0,distance-10)).coords[0]);after=np.array(line.interpolate(min(line.length,distance+10)).coords[0])
            tangent=after-before;tangent/=np.linalg.norm(tangent);normal=np.array([-tangent[1],tangent[0]])
            pts=[tuple(np.rint(center+normal*offset).astype(int)) for offset in range(-210,211,30)]
            sections.append({'river_segment':s['id'],'distance_in_segment_m':float(distance),'points':pts});points.update(pts)
    points=sorted(points,key=lambda p:(p[1],p[0]));jobs=[(i,[list(map(int,p)) for p in points[j:j+100]]) for i,j in enumerate(range(0,len(points),100))]
    rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for i,result in enumerate(pool.map(api.fetch,jobs)):
            rows.extend(result['results']);print('terrain batch',i+1,'of',len(jobs),flush=True)
    samples={}
    with rasterio.open(WORK/'prepared/cop_conditioned_30m.tif') as dem:
        for row in rows:
            xy=(row['geometry']['x'],row['geometry']['y'])
            try:z=float(next(iter(row['attributes'].values())))
            except (ValueError,TypeError):continue
            if np.isfinite(z) and 1000<z<6500:samples[xy]=(z,float(next(dem.sample([xy]))[0]))
    records=[]
    for section in sections:
        matched=[(point,*samples[point]) for point in section['points'] if point in samples]
        records.append({'segment':section['river_segment'],'distance_m':section['distance_in_segment_m'],
            'valid_points':len(matched),'requested_points':len(section['points']),
            'samples':[{'easting':int(p[0]),'northing':int(p[1]),'municipal_m':z,'model_m':model} for p,z,model in matched]})
    report={'service':api.BASE,'layer':7,'requested_points':len(points),'valid_points':len(samples),
        'sections':records,'vertical_datum_confirmed':False,'modified_model_terrain':False,
        'warning':'Sampling spacing is not native resolution. Differences do not establish field accuracy or prove a single propagation cause.'}
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Valid municipal terrain points',len(samples),'/',len(points),flush=True)

if __name__=='__main__':main()
