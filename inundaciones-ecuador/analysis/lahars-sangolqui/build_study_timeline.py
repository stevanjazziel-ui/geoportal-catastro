"""Kinematic reconstruction of published reach times, separate from the solver.

Display lines do not represent inundation widths or instantaneous water surfaces.
The clock follows cumulative seconds in EPN2017 Tables4.3/4.4 exactly at reach
endpoints; intermediate progression is explicitly interpolated by line distance.
"""
import gzip, json, math, shutil
from pathlib import Path
from study_reference import ROOT, WORK, sha
import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
from shapely import line_merge
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import substring

OUT=ROOT.parent/'dist/data/lahar-study-times'
TO_UTM=Transformer.from_crs(4326,32717,always_xy=True)
TO_GEO=Transformer.from_crs(32717,4326,always_xy=True)

# Pixel coordinates digitized along the mapped flow corridor in Annex9.
# Georeference uses printed UTM grid intersections, not satellite-image matching.
SALTO1=[(522,1758),(524,1720),(525,1660),(525,1600),(527,1550),(527,1510),(534,1470),(551,1441),(568,1404),(578,1362),(574,1323),(563,1297),(545,1273),(531,1260),(519,1237),(517,1205),(520,1174),(511,1144),(501,1119),(496,1100),(485,1076),(480,1048),(480,1010),(485,976),(493,946),(506,921),(522,891),(538,869),(553,850),(563,829),(563,806),(557,785),(550,769),(542,754),(529,738),(520,719),(517,694),(515,667),(517,649),(531,637),(555,634),(570,619),(577,595),(585,579),(597,565),(609,551),(614,533),(608,514),(604,493),(591,486),(572,485),(568,467),(565,441),(565,419),(552,405),(546,389),(542,366),(540,338),(540,303),(540,276),(542,250),(547,224),(543,207),(539,192),(543,177),(557,166),(580,160),(598,150),(614,138),(624,129)]
SALTO2=[(494,1659),(509,1640),(516,1618),(521,1596),(536,1584),(547,1563),(555,1542),(573,1524),(595,1513),(615,1504),(638,1499),(663,1495),(682,1499),(688,1501)]
SC2=[(884,885),(881,873),(880,860),(884,848),(889,834),(892,818),(892,802),(889,785),(890,770),(892,748),(889,731),(890,716),(893,701),(901,687),(912,674),(921,661),(930,649),(943,641),(948,638),(953,624),(956,608),(963,589),(977,575),(987,555),(990,533),(989,515),(988,499),(995,479),(1000,459),(1012,438),(1023,418),(1033,396),(1034,374),(1037,354),(1042,331),(1038,315),(1026,299),(1011,291),(1000,281),(995,264),(994,248),(999,229),(1006,208),(1009,181)]


def read_ways():
    files=[ROOT/'sources/osm-study-rivers.json',ROOT/'sources/osm-connected-rivers/santa-clara-connected.json']
    ways={}
    for file in files:
        for item in json.loads(file.read_text(encoding='utf-8'))['elements']:ways[item['id']]=item
    return ways,files


def merged(ways,ids):
    lines=[LineString([TO_UTM.transform(p['lon'],p['lat']) for p in ways[i]['geometry']]) for i in ids]
    line=line_merge(MultiLineString(lines))
    assert line.geom_type=='LineString','Disconnected river geometry; refuse invented joins'
    if line.coords[0][1]>line.coords[-1][1]:line=LineString(list(line.coords)[::-1])
    return line


def at_northing(line,y,expected_x):
    cross=line.intersection(LineString([(770000,y),(810000,y)]))
    candidates=[cross] if cross.geom_type=='Point' else list(cross.geoms)
    candidates=[p for p in candidates if p.geom_type=='Point']
    assert candidates,'No river intersection at documented reach boundary'
    p=min(candidates,key=lambda p:abs(p.x-expected_x))
    return line.project(p)


def part(line,start,end):
    a,b=start,end;assert b>a
    return substring(line,a,b)


def digitized(points,page):
    if page==293:
        xy=[(784000+(x-519)*2000/313,9936000+(1590-y)*8000/1254) for x,y in points]
    else:
        xy=[(784000+(x-375)*2000/354,9946000+(1539-y)*6000/1059) for x,y in points]
    return LineString(xy)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    meta=json.loads((ROOT/'study_travel_times.json').read_text(encoding='utf-8'))
    meta['source_pdf_sha256']=sha(ROOT/'sources/epn-lahares-norte-CD8076.pdf')
    ways,files=read_ways()
    pita=merged(ways,[667198422,1304714506])
    scids=[27936229]+[e['id'] for e in json.loads(files[1].read_text(encoding='utf-8'))['elements']]
    sc=merged(ways,scids)
    sp=merged(ways,[33846464,1226046228,1226046227,561073754])
    p=[at_northing(pita,y,x) for x,y in [(788327.2,9934926),(785436.1,9945333),(788516.466,9953734),(788547.386,9959955)]]
    p.append(pita.length)
    c=[at_northing(sc,9953736,787611.091),at_northing(sc,9959955,787061.58),sc.length]
    j=sp.project(Point(sc.coords[-1]));s=[j,at_northing(sp,9969567,783636.806),at_northing(sp,9974331,785153.572)]
    assert Point(sc.coords[-1]).distance(sp)<1,'Unconnected Santa Clara–San Pedro confluence'
    rawsc=digitized(SC2,294);rawsalto1=digitized(SALTO1,293);rawsalto2=digitized(SALTO2,294)
    sc_end=sc.interpolate(c[0]);sc_join_error=Point(rawsc.coords[-1]).distance(sc_end)
    assert sc_join_error<200,'Digitized map and river boundary incompatible; investigate'
    # Explicit display-only endpoint ties; never change a hydraulic DEM.
    scpoints=list(rawsc.coords);scpoints[-1]=tuple(sc_end.coords[0])
    salto1=list(rawsalto1.coords);salto1[0]=(784016.3,9934926);salto1[-1]=(784670.8,9945321)
    salto2=list(rawsalto2.coords);salto2[0]=salto1[-1];salto2[-1]=(785766.2,9946216.3)
    lines={'pita1':part(pita,p[0],p[1]),'pita2':part(pita,p[1],p[2]),'pita3':part(pita,p[2],p[3]),'pita4':part(pita,p[3],p[4]),
           'santaclara2':LineString(scpoints),'santaclara3':part(sc,c[0],c[1]),'santaclara4':part(sc,c[1],c[2]),
           'sanpedro4':part(sp,s[0],s[1]),'sanpedro5':part(sp,s[1],s[2]),'salto1':LineString(salto1),'salto2':LineString(salto2)}
    for segment in meta['segments']:
        line=lines[segment['id']]
        # Retain original vertices and add stations at most40m apart for smooth display.
        station=np.unique(np.r_[np.arange(0,line.length,40),line.length,
                    np.r_[0,np.cumsum(np.linalg.norm(np.diff(np.asarray(line.coords),axis=0),axis=1))]])
        points=[line.interpolate(float(d)) for d in station]
        coords=[TO_GEO.transform(q.x,q.y) for q in points]
        segment['coordinates']=[[round(lon,7),round(lat,7)] for lon,lat in coords]
        segment['distance_fraction']=(station/line.length).round(9).tolist()
        segment['mapped_length_m']=round(line.length,2)
        segment['geometry_origin']='Digitized Annex9 map' if segment['id'] in ('salto1','salto2','santaclara2') else 'Connected OpenStreetMap river geometry; clipped at study reach boundaries'
        for case in ('scenario3','calibration1877'):
            assert segment[case][1]>segment[case][0]>=0
        assert len(segment['coordinates'])==len(segment['distance_fraction'])
        print(segment['id'],'length',segment['mapped_length_m'],'published',segment['length_in_study_km']*1000,flush=True)
    meta['geometry_audit']={'display_only':True,'crs_processing':'EPSG:32717','crs_delivery':'EPSG:4326',
        'osm_attribution':'© OpenStreetMap contributors, ODbL','osm_source_hashes':{str(f.relative_to(ROOT)):sha(f) for f in files},
        'digitized_map_pages_pdf':[293,294],'rendered_size_px':[1623,2100],
        'map293_controls':{'easting':[519,784000,832,786000],'northing':[1590,9936000,336,9944000]},
        'map294_controls':{'easting':[375,784000,729,786000],'northing':[1539,9946000,480,9952000]},
        'assumed_digitization_tolerance_m':50,'ground_accuracy_validated':False,
        'santa_clara_boundary_display_tie_m':sc_join_error,
        'warning':'River lines are visual route guides, not inundation boundaries. Map digitization and cartographic positions have unvalidated accuracy. Original river widths and hydraulic cross-sections are not reconstructed.'}
    meta['milestones']=[{'segment':sid,'at':edge,'label':label} for sid,edge,label in [
        ('pita1','end','Pita · final del primer tramo'),('salto1','end','El Salto · final del primer tramo'),
        ('santaclara2','start','La Caldera · inicio hacia Santa Clara'),('pita2','end','Pita · salida del tramo2'),
        ('santaclara2','end','Santa Clara · salida del tramo2'),('santaclara3','end','Santa Clara · entrada al tramo urbano'),
        ('pita3','end','Pita · entrada al tramo urbano'),('santaclara4','end','Santa Clara · unión con San Pedro'),
        ('pita4','end','Pita · unión con San Pedro'),('sanpedro4','end','San Pedro · salida del tramo4'),
        ('sanpedro5','end','Cununyacu · final del área estudiada')]]
    meta['published_arrival_points_are_not_evacuation_deadlines']=True
    meta['reconstruction_not_new_hydraulic_simulation']=True
    meta['instantaneous_depth_and_volume_computed']=False
    (OUT/'timeline.json').write_text(json.dumps(meta,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    # Browser terrain is context only; temporal interpolation does not use its slopes.
    bbox=(-78.51,-.61,-78.36,-.20);rows,cols=850,320
    heights=np.full((rows,cols),-32768,np.float32)
    with rasterio.open(WORK/'prepared/cop_raw_30m.tif') as dem:
        reproject(rasterio.band(dem,1),heights,src_transform=dem.transform,src_crs=dem.crs,
                  dst_transform=from_bounds(*bbox,cols,rows),dst_crs=4326,
                  src_nodata=dem.nodata,dst_nodata=-32768,resampling=Resampling.bilinear)
    assert np.isfinite(heights).all() and (heights>0).all()
    encoded=np.rint(heights*10).astype('<u2')
    (OUT/'terrain.u16.gz').write_bytes(gzip.compress(encoded.tobytes(),mtime=0))
    terrain={'file':'terrain.u16.gz','sha256':sha(OUT/'terrain.u16.gz'),'bbox':list(bbox),'rows':rows,'cols':cols,'scale_m':.1,'source':'Copernicus GLO30, browser context only'}
    (OUT/'terrain.json').write_text(json.dumps(terrain),encoding='utf-8')
    # Reuse the existing anonymized visual building dataset; building upgrades remain deferred.
    existing=json.loads((ROOT.parent/'dist/data/sangolqui-lahars/manifest.json').read_text(encoding='utf-8'))
    meta_buildings=existing['buildings']
    shutil.copy2(ROOT.parent/'dist/data/sangolqui-lahars'/meta_buildings['file'],OUT/meta_buildings['file'])
    (OUT/'buildings-reference.json').write_text(json.dumps(meta_buildings),encoding='utf-8')
    regional=existing['regional']
    shutil.copy2(ROOT.parent/'dist/data/sangolqui-lahars'/regional['file'],OUT/regional['file'])
    (OUT/'regional.json').write_text(json.dumps(regional),encoding='utf-8')
    print('Published reach-time data prepared, without fabricated hydraulic fields.',flush=True)


if __name__=='__main__':main()
