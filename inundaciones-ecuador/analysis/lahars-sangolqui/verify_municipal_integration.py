"""Check real source inputs, grid and source-zone invariance after MDT insertion."""
from municipal_study import WORK,ORIGINAL,CASE,ROOT
from study_reference import sha
import json,numpy as np,rasterio

def main():
    old=(ORIGINAL/'inputs/reference-cop30.txt').read_text(encoding='utf-8')
    new=(WORK/'inputs'/f'{CASE}.txt').read_text(encoding='utf-8')
    assert old.split('Solver:')[0]==new.split('Solver:')[0]
    assert old.split('Parameters:')[1]==new.split('Parameters:')[1]
    source=json.loads((ORIGINAL/'manifest.json').read_text(encoding='utf-8'))
    meta=json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
    assert meta['sources']==source['sources'] and meta['water_input_m3']==source['water_input_m3']
    with rasterio.open(ORIGINAL/'prepared/cop_conditioned_30m.tif') as a,rasterio.open(WORK/'prepared/municipal_hybrid_30m.tif') as b:
        assert a.crs==b.crs and a.transform==b.transform and a.shape==b.shape
        aa=a.read(1);bb=b.read(1)
        assert np.isfinite(bb).all() and (bb>0).all() and (bb<6500).all()
        # All glacier-source cells and their100m input disks remain unchanged.
        rows,cols=np.indices(a.shape);xx=a.transform.c+(cols+.5)*30;yy=a.transform.f-(rows+.5)*30
        for s in meta['sources']:
            disk=np.hypot(xx-s['easting'],yy-s['northing'])<=100
            assert disk.any() and np.array_equal(aa[disk],bb[disk])
        # Outside the municipal footprint the original input is bitwise preserved.
        native_audit=json.loads((ROOT/'sources/ruminahui-geoservicios-dtm/native3m-audit.json').read_text())
        w,s,e,n=native_audit['bounds'];outside=(xx<w)|(xx>e)|(yy<s)|(yy>n)
        assert np.array_equal(aa[outside],bb[outside])
    report={'passed':True,'same_nine_source_hydrographs':True,'same_physical_parameters':True,
            'same_grid_and_source_disks':True,'outside_coverage_unchanged':True,
            'physical_grid_m':30,'native_municipal_grid_m':3,
            'model_terrain_sha256':sha(WORK/'prepared/municipal_hybrid_30m.tif'),
            'municipal_source_sha256':native_audit['sha256'],'input_sha256':sha(WORK/'inputs'/f'{CASE}.txt'),
            'predictive_validation':False,'vertical_datum_confirmed':False}
    (WORK/'prepared/integration-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Municipal input integration checks passed; no predictive calibration implied.',flush=True)

if __name__=='__main__':main()
