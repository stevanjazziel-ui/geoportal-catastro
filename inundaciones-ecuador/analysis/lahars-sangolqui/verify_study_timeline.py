"""Audit delivered study clocks, geometry and compressed assets independently."""
import gzip, hashlib, json
from pathlib import Path
from study_reference import ROOT
import numpy as np
from pyproj import Geod


def main():
    folder=ROOT.parent/'dist/data/lahar-study-times'
    a=json.loads((folder/'timeline.json').read_text(encoding='utf-8'))
    # Cumulative seconds independently transcribed from visually checked PDF140/141.
    reference={
      'pita1':((0,960),(0,1060)), 'salto1':((0,1350),(0,1550)),
      'pita2':((960,1900),(1060,2030)), 'salto2':((960,1210),(1060,1310)),
      'santaclara2':((1440,1775),(1576,2055)), 'pita3':((1900,3050),(2030,3190)),
      'santaclara3':((1775,2155),(2055,2705)), 'pita4':((3050,5010),(3190,4785)),
      'santaclara4':((2155,2945),(2705,4010)), 'sanpedro4':((2945,3775),(4010,4955)),
      'sanpedro5':((3775,4645),(4955,5985))}
    assert set(reference)=={s['id'] for s in a['segments']}
    geod=Geod(ellps='WGS84');length_differences={}
    for s in a['segments']:
        assert tuple(s['calibration1877'])==reference[s['id']][0]
        assert tuple(s['scenario3'])==reference[s['id']][1]
        coords=np.array(s['coordinates']);f=np.array(s['distance_fraction'])
        assert coords.shape==(len(f),2) and len(f)>2
        assert np.isfinite(coords).all() and np.isfinite(f).all()
        assert (coords[:,0]>-78.6).all() and (coords[:,0]<-78.3).all()
        assert (coords[:,1]>-.65).all() and (coords[:,1]<-.20).all()
        assert abs(f[0])<1e-8 and abs(f[-1]-1)<1e-8 and (np.diff(f)>=0).all()
        _,_,dist=geod.inv(coords[:-1,0],coords[:-1,1],coords[1:,0],coords[1:,1])
        assert dist.max()<41,'Unexpected gap between display stations'
        length_differences[s['id']]=(s['mapped_length_m']/(s['length_in_study_km']*1000)-1)*100
    # Preserve the documented early lower-Salto input instead of forcing one clock.
    assert reference['salto2'][1][0]<reference['salto1'][1][1]
    assert a['reconstruction_not_new_hydraulic_simulation'] is True
    assert a['instantaneous_depth_and_volume_computed'] is False
    for name,dtype in [('terrain.json','<u2'),('regional.json','<i2')]:
        m=json.loads((folder/name).read_text(encoding='utf-8'));raw=(folder/m['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==m['sha256']
        values=np.frombuffer(gzip.decompress(raw),dtype=dtype)
        assert values.size==m['rows']*m['cols']
        if name=='terrain.json':assert values.min()>0
    m=json.loads((folder/'buildings-reference.json').read_text(encoding='utf-8'))
    raw=(folder/m['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==m['sha256']
    buildings=json.loads(gzip.decompress(raw));assert len(buildings['features'])==20463
    assert all(set(f['properties'])<= {'floors','height_m','base_m','height_origin'} for f in buildings['features'])
    report={'study_segments_checked':11,'published_endpoint_times_checked':44,
            'scenario_max_s':5985,'calibration_max_s':5010,'asset_hashes_passed':True,
            'geometry_length_difference_percent':length_differences,
            'geometry_length_difference_is_not_predictive_accuracy':True,
            'original_study_gis_geometry_acquired':False,'predictive_validation':False,
            'warning':'Different mapped lengths are retained and reported. No flow velocity or new hydraulic quantities are derived from the animation.'}
    (folder/'delivery-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
