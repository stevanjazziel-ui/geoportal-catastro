"""Prepare measured terrain and cited source hydrographs, without claiming a lahar run."""
from pathlib import Path
import gzip
import hashlib
import json
import math
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.deps'))
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling

ROOT = Path(__file__).resolve().parent
PAPER = 'https://doi.org/10.3389/feart.2025.1611579'


def main():
    out = ROOT / 'prepared'
    out.mkdir(exist_ok=True)
    source = ROOT / 'sources/S01W079.hgt.gz'
    raw = gzip.decompress(source.read_bytes())
    n = math.isqrt(len(raw) // 2)
    if n * n * 2 != len(raw) or n != 3601:
        raise ValueError('Expected a complete one-arcsecond HGT grid')
    z = np.frombuffer(raw, '>i2').reshape(n, n).astype(np.float32)
    # HGT uses elevation posts, including both degree boundaries.
    spacing = 1 / (n - 1)
    src_transform = from_origin(-79 - spacing / 2, spacing / 2, spacing, spacing)
    service = json.loads((ROOT / 'sources/municipal-lahar.json').read_text())
    extent = service['fullExtent']
    assert extent['spatialReference']['wkid'] == 32717
    dx = 30
    west = math.floor(extent['xmin'] / dx) * dx
    north = math.ceil(extent['ymax'] / dx) * dx
    cols = math.ceil((extent['xmax'] - west) / dx)
    rows = math.ceil((north - extent['ymin']) / dx)
    transform = from_origin(west, north, dx, dx)
    dem = np.full((rows, cols), -32768, np.float32)
    reproject(z, dem, src_transform=src_transform, src_crs='EPSG:4326',
              dst_transform=transform, dst_crs='EPSG:32717', src_nodata=-32768,
              dst_nodata=-32768, resampling=Resampling.bilinear)
    valid = (dem != -32768) & np.isfinite(dem)
    if not valid.all():
        raise ValueError(f'Terrain coverage incomplete: {valid.mean():.3%}')
    dest = out / 'cotopaxi_norte_30m_contexto.tif'
    with rasterio.open(dest, 'w', driver='GTiff', height=rows, width=cols,
                       count=1, dtype='float32', crs='EPSG:32717', transform=transform,
                       nodata=-32768, compress='deflate', predictor=3) as ds:
        ds.write(dem, 1)
        ds.update_tags(purpose='Preliminary context; not validated lahar terrain',
                       source='Mapzen elevation tiles, Skadi HGT S01W079',
                       vertical_reference='Verify source vertical datum before engineering use')
    # Table 1: these are WATER source fluxes, not final sediment-laden volumes.
    peaks = [2019, 577, 6058, 3750, 12981, 3462, 16154, 16154, 16154]
    lines = ['source_id,time_s,water_discharge_m3_s']
    for sid, q in zip(range(12, 21), peaks):
        lines.extend(f'{sid},{t},{flow}' for t, flow in [(0, 0), (150, q), (900, 0)])
    (out / 'reference_water_hydrographs.csv').write_text('\n'.join(lines)+'\n')
    files = [{'file':str(p.relative_to(ROOT)), 'bytes':p.stat().st_size,
              'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted((ROOT / 'sources').iterdir()) if p.is_file()]
    report = {
        'status':'inputs_prepared_simulation_not_run', 'simulation_executed':False,
        'terrain':{'file':dest.name, 'shape':[rows, cols], 'crs':'EPSG:32717',
                   'grid_m':dx, 'source_spacing_arcseconds':1, 'valid_fraction':float(valid.mean()),
                   'elevation_min_m':float(dem.min()), 'elevation_max_m':float(dem.max()),
                   'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
                   'limitations':['30 m grid cannot resolve all narrow ravines',
                                  'Not the 3 m IGM terrain used in the cited study',
                                  'Resampling does not improve source resolution',
                                  'Vertical datum and source epochs require verification']},
        'reference_hydrographs':{'file':'reference_water_hydrographs.csv', 'source':PAPER,
                  'source_ids':list(range(12,21)), 'peak_time_s':150, 'release_end_s':900,
                  'summed_peak_m3_s':sum(peaks), 'water_volume_m3':sum(peaks)*900/2,
                  'limitations':['Source coordinates not yet verified',
                     'Paper totals contain rounding; calculated from printed source peaks',
                     'Water input volume is not final lahar volume',
                     'Does not define the municipal published scenario']},
        'municipal_reference':{'url':'https://geoide.ruminahui.gob.ec/image/rest/services/LAHAR/lahar_cotopaxi_zona_norte/MapServer',
                    'layers':{'0':'maximum depth','1':'maximum speed','2':'arrival time'},
                    'units_verified':False, 'scenario_verified':False,
                    'original_numeric_rasters_downloaded':False},
        'required_before_model_run':['Verify source coordinates and input solid concentrations',
                    'Obtain suitable terrain and inspect La Caldera and narrow channels',
                    'Install and validate Kestrel or equivalent sediment-flow solver',
                    'Verify units and scenario of municipal comparison outputs'],
        'source_files':files
    }
    (out / 'input-audit.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['status','terrain','reference_hydrographs']}, indent=2))


if __name__ == '__main__':
    main()
