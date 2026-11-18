"""Decode small Potree root-node samples for a ground-height consistency check.

No downloaded loader code is reused. The AoS attribute layout comes from public
metadata;22-byte hierarchy records and scaled int32 positions are checked against
the portal's served loader. Root samples are not random or complete ground cover.
"""
from study_reference import ROOT,sha
import json,struct,urllib.request
import numpy as np
import rasterio
from pyproj import Transformer

OUT=ROOT/'sources/ruminahui-lidar/ground-check'

def byte_range(url,start,length,path):
    if path.exists():
        b=path.read_bytes();assert len(b)==length;return b
    req=urllib.request.Request(url,headers={'Range':f'bytes={start}-{start+length-1}','Accept-Encoding':'identity'})
    with urllib.request.urlopen(req,timeout=45) as r:
        assert r.status==206,'Server ignored range; refuse a complete-cloud download'
        assert r.headers['Content-Range'].startswith(f'bytes {start}-{start+length-1}/')
        b=r.read(length+1);assert len(b)==length
    path.write_bytes(b);return b

def main():
    OUT.mkdir(exist_ok=True)
    reports=[]
    with rasterio.open(ROOT/'sources/ruminahui-geoservicios-dtm/mdt2023-native3m.tif') as dem:
        for cloud,file in [('sangolqui','sangolqui-metadata.json'),('san_rafael_2024','san_rafael_2024-metadata.json'),('rumipamba_2024','rumipamba_2024-metadata.json')]:
            metadata_path=OUT.parent/file;m=json.loads(metadata_path.read_text(encoding='utf-8'));assert m['encoding']=='DEFAULT'
            base='https://ide.ruminahui.gob.ec/lidar/pointclouds/'+cloud+'/'
            hierarchy_path=OUT/(cloud+'-hierarchy.bin')
            b=byte_range(base+'hierarchy.bin',0,m['hierarchy']['firstChunkSize'],hierarchy_path)
            kind,children,n,offset,length=struct.unpack_from('<BBIqq',b)
            assert kind in (0,1) and n>0 and 0<length<20_000_000
            path=OUT/(cloud+'-root.bin');raw=byte_range(base+'octree.bin',offset,length,path)
            stride=sum(a['size'] for a in m['attributes']);assert len(raw)==n*stride
            offsets={};position=0
            for attr in m['attributes']:offsets[attr['name']]=position;position+=attr['size']
            xyz=np.ndarray((n,3),dtype='<i4',buffer=raw,offset=offsets['position'],strides=(stride,4)).astype(float)
            xyz=xyz*np.asarray(m['scale'])+np.asarray(m['offset'])
            cls=np.ndarray((n,),dtype='u1',buffer=raw,offset=offsets['classification'],strides=(stride,))
            ground=xyz[cls==2]
            assert len(ground)>0 and np.isfinite(ground).all()
            valid=(ground[:,0]>=dem.bounds.left)&(ground[:,0]<dem.bounds.right)&(ground[:,1]>=dem.bounds.bottom)&(ground[:,1]<dem.bounds.top)
            ground=ground[valid];z=np.array([v[0] for v in dem.sample(ground[:,:2])]);assert (z!=dem.nodata).all()
            delta=ground[:,2]-z
            np.savetxt(OUT/(cloud+'-ground-vs-mdt.csv'),np.c_[ground,z,delta],delimiter=',',header='easting,northing,lidar_ground_z,mdt3m_z,lidar_minus_mdt_m',comments='',fmt='%.6f')
            report={'cloud':cloud,'source':base+'metadata.json','metadata_sha256':sha(metadata_path),
                    'hierarchy_sha256':sha(hierarchy_path),'root_node_sha256':sha(path),
                    'root_node_points':n,'paired_class2_points':len(ground),
                    'lidar_minus_mdt_m':{'median':float(np.median(delta)),'p05_p95':np.percentile(delta,[5,95]).tolist(),'rmse':float(np.sqrt(np.mean(delta**2)))},
                    'declared_cloud_projection':m['projection'],'coordinate_interpretation_for_check':'EPSG32717; consistent coordinate magnitudes/location but not declared in cloud metadata',
                    'absolute_vertical_datum_confirmed':False,'random_sample':False,'predictive_validation':False}
            reports.append(report);print(cloud,report['paired_class2_points'],report['lidar_minus_mdt_m'],flush=True)
    central_path=ROOT/'sources/municipal-centro-dem_5m.tif'
    extra=None
    if central_path.exists():
        sample=np.loadtxt(OUT/'sangolqui-ground-vs-mdt.csv',delimiter=',',skiprows=1)
        transform=Transformer.from_crs(32717,3857,always_xy=True)
        with rasterio.open(central_path) as central:
            x,y=transform.transform(sample[:,0],sample[:,1])
            z=np.array([v[0] for v in central.sample(zip(x,y))]);valid=(z!=central.nodata)&(z>1000)
            extra={'product':'Previously acquired partial central municipal DEM; source ImageServer metadata declares vertical CRS5773',
                'sha256':sha(central_path),'paired_samples':int(valid.sum()),
                'lidar_minus_central_m_p05_median_p95':np.percentile(sample[valid,2]-z[valid],[5,50,95]).tolist(),
                'wcs_mdt_minus_central_m_p05_median_p95':np.percentile(sample[valid,3]-z[valid],[5,50,95]).tolist(),
                'warning':'Different products, partial coverage and sparse root samples. Metadata alone does not resolve these differences; no datum correction or terrain substitution inferred.'}
    (OUT/'report.json').write_text(json.dumps({'comparisons':reports,'additional_product_check':extra,'method':'Nearest native3m MDT pixel at class2 ground points from root nodes; no outlier removal or datum shift. This compares products, not independent field truth.'},ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
