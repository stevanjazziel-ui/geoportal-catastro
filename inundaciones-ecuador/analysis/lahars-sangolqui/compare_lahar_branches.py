"""Audit Pita and Santa Clara against the same native Kestrel clock."""

import json

from study_reference import ROOT, sha
from netCDF4 import Dataset
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString


RUN = ROOT / 'study2025-municipal30-v1'
TIMELINE = ROOT.parent / 'dist/data/lahar-study-times/timeline.json'
OUT = RUN / 'prepared/branch-audit.json'
DX = 30.0
DEPTH = .05
NEIGHBORHOOD = np.arange(-2, 3)


def sample_segments(timeline, project):
    for segment in timeline['segments']:
        if not (segment['id'] in ('pita2', 'pita3', 'pita4') or segment['river'] == 'Santa Clara'):
            continue
        lon, lat = np.array(segment['coordinates']).T
        line = LineString(np.column_stack(project.transform(lon, lat)))
        distance = np.linspace(0, line.length, int(np.ceil(line.length / DX)) + 1)
        xy = np.array([line.interpolate(d).coords[0] for d in distance])
        yield segment, distance, xy


def neighborhood(depth, rows, cols):
    result = np.zeros(len(rows))
    valid = (rows >= 2) & (rows < depth.shape[0] - 2) & (cols >= 2) & (cols < depth.shape[1] - 2)
    grid_rows = rows[valid, None, None] + NEIGHBORHOOD[None, :, None]
    grid_cols = cols[valid, None, None] + NEIGHBORHOOD[None, None, :]
    result[valid] = depth[grid_rows, grid_cols].max(axis=(1, 2))
    return result


def summarize(segment, distance, coordinates, arrival, peak):
    wet = arrival >= 0
    boundaries = np.r_[0, (distance[:-1] + distance[1:]) / 2, distance[-1]]
    split = np.flatnonzero(np.diff(wet)) + 1
    runs = [(a, b, bool(wet[a])) for a, b in zip(np.r_[0, split], np.r_[split, len(wet)])]
    gaps = [
        {'start_km': round(boundaries[a] / 1000, 3), 'end_km': round(boundaries[b] / 1000, 3),
         'length_km': round((boundaries[b] - boundaries[a]) / 1000, 3),
         'start': coordinates[a].tolist(), 'end': coordinates[b - 1].tolist()}
        for a, b, reached in runs if not reached and boundaries[b] - boundaries[a] >= 100
    ]
    return {'id': segment['id'], 'river': segment['river'], 'length_km': round(distance[-1] / 1000, 3),
            'coverage_fraction': round(float(np.diff(boundaries)[wet].sum() / distance[-1]), 4),
            'peak_thickness_m': round(float(peak.max()), 3), 'dry_runs_of_100m_or_more': gaps,
            'samples': [[round(d, 2), round(lo, 6), round(la, 6), int(t)]
                        for d, (lo, la), t in zip(distance, coordinates, arrival)]}


def main():
    clock = json.loads((RUN / 'report.json').read_text(encoding='utf-8'))
    assert clock['native_frames_checked'] == 601
    timeline = json.loads(TIMELINE.read_text(encoding='utf-8'))
    project = Transformer.from_crs(4326, 32717, always_xy=True)
    geographic = Transformer.from_crs(32717, 4326, always_xy=True)
    routes = list(sample_segments(timeline, project))
    xy = np.concatenate([route[2] for route in routes])
    x, y = xy.T
    arrival = np.full(len(x), -1, dtype=int)
    peak = np.zeros(len(x))
    folder = RUN / 'runs/reference-mdt30'
    for index in range(601):
        path = folder / f'{index:06d}.nc'
        with Dataset(path) as ds:
            seconds = int(round(float(ds.time)))
            assert seconds == index * 15
            x0, y0 = float(ds['x'][0]), float(ds['y'][0])
            cols = np.rint((x - x0) / DX).astype(int)
            rows = np.rint((y - y0) / DX).astype(int)
            nx, ny = len(ds['x']), len(ds['y'])
            sample_inside = (cols >= 2) & (cols < nx - 2) & (rows >= 2) & (rows < ny - 2)
            if not sample_inside.any():
                continue
            left, right = cols[sample_inside].min() - 2, cols[sample_inside].max() + 3
            bottom, top = rows[sample_inside].min() - 2, rows[sample_inside].max() + 3
            field = ds['flow_depth'][bottom:top, left:right].filled(0)
            thickness = neighborhood(field, rows - bottom, cols - left)
            wet = thickness >= DEPTH
            arrival[(arrival < 0) & wet] = seconds
            peak = np.maximum(peak, thickness)
        if index % 120 == 0:
            print(f'Native frame {index}/600', flush=True)
    geo = np.array(geographic.transform(x, y)).T
    summaries = []
    i = 0
    for segment, distance, _ in routes:
        j = i + len(distance)
        summaries.append(summarize(segment, distance, geo[i:j], arrival[i:j], peak[i:j]))
        i = j
    report = {'case': 'reference-mdt30', 'last_time_s': 9000, 'native_cadence_s': 15,
              'threshold_m': DEPTH, 'grid_m': DX, 'window_cells': 5,
              'scenario_input_sha256': clock['scenario']['input_sha256'],
              'timeline_sha256': sha(TIMELINE), 'segments': summaries,
              'sample_columns': ['distance_from_segment_start_m', 'lon', 'lat', 'first_saved_wetting_s'],
              'sample_clock_origin': 'Inicio de los nueve aportes en el flanco norte del Cotopaxi',
              'interpretation': 'Presencia de flujo simulado en el corredor del cauce. Cerca de una confluencia, una celda mojada puede proceder de otra rama. Los tiempos de esta corrida no constituyen validación predictiva.',
              'sections': clock['published_section_context']['sections']}
    OUT.write_text(json.dumps(report, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    for record in summaries:
        print(json.dumps({k: v for k, v in record.items() if k != 'samples'}, ensure_ascii=True), flush=True)
    print(OUT, flush=True)


if __name__ == '__main__':
    main()
