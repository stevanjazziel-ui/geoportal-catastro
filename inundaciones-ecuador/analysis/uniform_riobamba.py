"""Constant rain: causal 15min prefixes of nine independent 12h calculations.

A shorter selection ends at the chosen rain duration. No post-rain recession is
inferred. Prefix maxima are saved during calculation, never taken from 12h maxima.
"""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from approximate_riobamba_network import build, execute
from run_riobamba_cases import run

ROOT = Path(__file__).resolve().parent
GRID = ROOT / 'riobamba-runs/grid-24m'
OUT = ROOT / 'dist/data/riobamba-local'
RATES = {'7p8': 7.8, '15p6': 15.6, '75': 75.}
MODES = ['none', 'network', 'zero-loss']
RAW = 'https://raw.githubusercontent.com/stevanjazziel-ui/geoportal-catastro/main/inundaciones-ecuador/'
LIMITS = [
    'Fixed intensities chosen for sensitivity, not station quantiles for each selected duration or an ENSO forecast.',
    '7.8 mm/h originated as the 6h combined high-reference mean; 15.6 is twice that; 75 is twice the combined 1h high-reference mean.',
    'Those former variable-rain means are deliberately used as constant forcing here; this is a new hypothetical experiment.',
    'Rain is spatially uniform across the valid local domain; no locally verified areal reduction or radar field is used.',
    'Each duration is the causal prefix of the same continuous-rain calculation; no post-stop drainage is simulated.',
    'Cumulative maxima and water budgets are recorded at each 15min cutoff; future water is excluded.',
    'Terrain, soil losses, open boundaries, inferred sewer and one-way overflow remain uncalibrated.',
    'No upstream river flood hydrograph or bathymetry is included; these are rain and inferred-sewer experiments.',
    '75 mm/h for 12h is 900mm: a stress assumption, not a probable or physically established local event.',
]


def case_id(key, mode):
    return 'uniform-' + key + ('' if mode == 'none' else '-' + mode)


def network_for(key):
    rate = RATES[key]
    folder = GRID / ('network-uniform-' + key)
    if (folder / 'surface-forcing.npz').exists():
        return folder
    if folder.exists():
        raise RuntimeError('Inspect incomplete uniform network before resuming')
    build(rate, folder.name)
    with np.load(folder / 'network-data.npz') as f:
        q = f['runoff_q'].copy()
    head = (folder / 'network.inp').read_text().split('[TIMESERIES]')[0]
    head = head.replace('END_TIME 02:00:00', 'END_TIME 12:00:00')
    lines = [head, '[TIMESERIES]']
    for i, value in enumerate(q):
        if value > 0:
            lines += [f'R{i} 01/01/2020 00:00:00 {value:.12g}',
                      f'R{i} 01/01/2020 12:00:00 {value:.12g}']
    lines += ['[REPORT]', 'NODES NONE', 'LINKS NONE']
    (folder / 'network.inp').write_text('\n'.join(lines) + '\n')
    a = json.loads((folder / 'assumptions.json').read_text())
    a.update(model_end_seconds=43200, input_runoff_m3=float(q.sum() * 43200),
             rainfall_mm_h=rate, temporal_distribution='Constant through calculation end; no ramp or duration-dependent normalization')
    a['assumptions'] = [s for s in a['assumptions'] if 'One-minute rainfall-input ramp' not in s]
    a['assumptions'].append('Same constant input through 12h; shorter selections truncate at their cutoff and do not simulate after rain stops.')
    (folder / 'assumptions.json').write_text(json.dumps(a, indent=2))
    execute(folder)
    return folder


def calculate(key, mode):
    name = case_id(key, mode)
    folder = GRID / name
    if (folder / 'report.json').exists():
        return
    if folder.exists():
        raise RuntimeError('Inspect incomplete uniform surface before resuming')
    net = network_for(key) if mode == 'network' else None
    run(GRID, name, 12, RATES[key], 12, net,
        infiltration_factor=0. if mode == 'zero-loss' else 1.,
        snapshot_minutes=15, record_prefixes=True)
    r = json.loads((folder / 'report.json').read_text())
    r.update(uniform_rainfall=True, limitations=LIMITS,
             duration_semantics='Snapshot prefix until chosen rain end; no post-rain calculation',
             intensity_origin={'7p8': 'Mean of combined 6h high reference',
                               '15p6': 'Twice the combined 6h high-reference mean',
                               '75': 'Twice the combined 1h high-reference mean'}[key])
    if net:
        r['network_diagnostics'] = json.loads((net / 'summary.json').read_text())
    (folder / 'report.json').write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')


def archive_current(manifest):
    previous = OUT / 'previous-scenarios-20261114.json'
    history = json.loads(previous.read_text(encoding='utf-8'))
    cases = {c['id']: c for c in history['cases']}
    for c in manifest['cases']:
        if not c['id'].startswith('uniform-'):
            cases[c['id']] = c
    for c in cases.values():
        c['asset_urls'] = {k: v if v.startswith('https://') else RAW + 'data/riobamba-local/' + v
                           for k in ['file', 'report', 'network_input_file', 'network_report_file']
                           if isinstance(v := c.get(k), str)}
    history['cases'] = list(cases.values())
    history['archived_assets_delivery'] = 'Previous variable-rain experiments preserved in GitHub; asset_urls are direct downloads.'
    previous.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')


def pack():
    m = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
    archive_current(m)
    items = []
    archives = ROOT / 'model-archives'
    for key, rate in RATES.items():
        for mode in MODES:
            name = case_id(key, mode)
            folder = GRID / name
            r = json.loads((folder / 'report.json').read_text())
            r['limitations'] = LIMITS
            r['metadata']['rain_input'] = {'mode': 'constant selected intensity', 'mm_h': rate,
                                         'master_minutes': 720, 'selectable_minutes': list(range(15, 721, 15)),
                                         'return_period_years': None, 'forecast': False}
            stats = r['prefix_stats']
            if len(stats) != 49 or max(s['mass_relative_error'] for s in stats) > 1e-8:
                raise ValueError('Invalid prefix budgets')
            if mode == 'network':
                net = GRID / ('network-uniform-' + key)
                a = json.loads((net / 'assumptions.json').read_text())
                with np.load(net / 'surface-forcing.npz') as f:
                    for i, minutes in enumerate(range(0, 721, 15)):
                        stop = minutes * 60
                        dt = np.maximum(0., np.minimum(f['seconds'][1:], stop) - f['seconds'][:-1])
                        overflow = float(np.sum(f['rates_m3_s'][1:] * dt[:, None]))
                        if abs(overflow - stats[i]['prescribed_overflow_m3']) > .001:
                            raise ValueError('Prefix overflow mismatch')
                        captured_rain = rate * minutes / 60 / 1000 * a['captured_km2'] * 1e6
                        residual = rate * minutes / 60 / 1000 * m['valid_km2'] * 1e6 - stats[i]['direct_rain_m3'] - captured_rain
                        if abs(residual) > .01:
                            raise ValueError('Prefix rain counted twice or missing')
                if abs(r['network_diagnostics']['routing_continuity_error_percent']) >= 1:
                    raise ValueError('Sewer continuity failed')
            else:
                for i, s in enumerate(stats):
                    if abs(rate * i / 4 / 1000 * m['valid_km2'] * 1e6 - s['direct_rain_m3']) > .01:
                        raise ValueError('Prefix rain volume mismatch')
            with np.load(folder / 'result.npz') as f:
                times = f['times_minutes']
                np.testing.assert_allclose(times, np.arange(0, 721, 15), atol=1e-8)
                depths = np.concatenate([f['frames'], f['max_frames']])
                if depths.min() < 0 or not np.isfinite(depths).all() or depths.max() > 655.35:
                    raise ValueError('Invalid water depths')
                blob = gzip.compress(np.floor(depths * 100 + 1e-6).astype('<u2').tobytes(), mtime=0)
            filename = name + '.prefix15.u16.gz'
            (OUT / filename).write_bytes(blob)
            (folder / 'report.json').write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
            (OUT / (name + '-report.json')).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
            item = {'id': name, 'rain_mm_h': rate, 'rain_hours': 12, 'duration_hours': 12,
                    'uniform_rainfall': True, 'file': filename, 'download_url': RAW + 'data/riobamba-local/' + filename,
                    'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest(),
                    'frame_count': 49, 'cumulative_max_offset': 49, 'depth_scale_m': .01,
                    'times_minutes': list(range(0, 721, 15)), 'display_snapshot_minutes': 15,
                    'wet_km2_by_frame': [0.] + [v['wet_km2'] for v in r['hydrograph']],
                    'cumulative_stats_by_frame': stats, 'stats': r['stats'],
                    'report': name + '-report.json', 'infiltration_multiplier': r['infiltration_multiplier'],
                    'network_diagnostics': r.get('network_diagnostics')}
            if mode == 'network':
                for ext, field in [('inp', 'network_input_file'), ('rpt', 'network_report_file')]:
                    fn = name + '.' + ext + '.gz'
                    (archives / fn).write_bytes(gzip.compress((net / ('network.' + ext)).read_bytes(), mtime=0))
                    item[field] = RAW + 'model-archives/' + fn
            items.append(item)
    m.update(cases=items, version='riobamba-constant-quarterhour-v1',
             rainfall_mode='constant', selectable_minutes=list(range(15, 721, 15)),
             duration_semantics='Rain until cutoff; no after-rain recession shown',
             binary_delivery='GitHub raw; SHA256 and byte counts refer to original compressed bytes',
             display_note='Every 15min; separate all-step cumulative maximum at each cutoff, no future leakage.')
    m['metadata']['rain_input'] = {'mode': 'chosen constant intensities', 'mm_h': list(RATES.values()),
                                 'max_minutes': 720, 'step_minutes': 15, 'return_period_years': None}
    m['notes_es'] = [
        'Lluvia constante elegida: 7,8; 15,6 o 75 mm/h, durante 15 a 720 minutos en pasos de 15.',
        'Las cantidades son supuestos de prueba; no valores de estación válidos para todas las duraciones ni pronósticos de El Niño.',
        'Se muestra únicamente hasta el final de la lluvia elegida; no se simula qué sucede después de que pare.',
        'Los máximos y métricas usan solo el tiempo elegido. No incluyen resultados de horas posteriores.',
        '75 mm/h durante 12 horas suma 900 mm: prueba extrema, sin probabilidad o máximo físico demostrado.',
        'El suelo, el drenaje y las condiciones de salida siguen sin calibrar con inundaciones observadas.',
    ]
    geometry_file = OUT / m['network']
    geometry = json.loads(gzip.decompress(geometry_file.read_bytes()))
    geometry['assumptions'] = json.loads((GRID / 'network-uniform-7p8/assumptions.json').read_text())
    geometry['diagnostics'] = json.loads((GRID / 'network-uniform-7p8/summary.json').read_text())
    geometry['scenario'] = 'Shared inferred geometry; metadata reference uniform-7p8-network. Each selected case report specifies actual rain.'
    m['network_geometry_reference_case'] = 'uniform-7p8-network'
    spatial_note = 'Se supone que la misma lluvia cae en toda la zona simulada; no se usa un mapa de lluvia por sectores.'
    if spatial_note not in m['notes_es']:m['notes_es'].append(spatial_note)
    geometry_file.write_bytes(gzip.compress(json.dumps(geometry, separators=(',', ':')).encode(), mtime=0))
    (OUT / 'manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')
    from uniform_payload_codec import publish_encoded
    publish_encoded()
    print('PACKED', len(items), 'constant-rain masters; 48 durations each; 432 selections', flush=True)


def finalize_metadata():
    """Refresh provenance after long calculations; never alter numeric outputs."""
    m = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
    assert m['rainfall_mode'] == 'constant' and len(m['cases']) == 9
    for c in m['cases']:
        path = GRID / c['id'] / 'report.json'
        r = json.loads(path.read_text())
        assert r['rain_mm_h'] == c['rain_mm_h'] and r['uniform_rainfall']
        r['limitations'] = LIMITS
        r['metadata']['rain_input'] = {'mode': 'constant selected intensity', 'mm_h': c['rain_mm_h'],
                                     'master_minutes': 720, 'selectable_minutes': list(range(15, 721, 15)),
                                     'return_period_years': None, 'forecast': False}
        for target in [path, OUT / c['report']]:
            target.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
    geo_path = OUT / m['network']
    geo = json.loads(gzip.decompress(geo_path.read_bytes()))
    geo['assumptions'] = json.loads((GRID / 'network-uniform-7p8/assumptions.json').read_text())
    geo['diagnostics'] = json.loads((GRID / 'network-uniform-7p8/summary.json').read_text())
    geo['scenario'] = 'Shared inferred geometry; metadata reference uniform-7p8-network. Each selected case report specifies actual rain.'
    geo_path.write_bytes(gzip.compress(json.dumps(geo, separators=(',', ':')).encode(), mtime=0))
    m['network_geometry_reference_case'] = 'uniform-7p8-network'
    (OUT / 'manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Provenance finalized; numeric arrays and metrics unchanged.')


def launch(job):
    key, mode = job
    logs = ROOT / 'riobamba-runs/uniform-logs'
    logs.mkdir(exist_ok=True)
    path = logs / (case_id(key, mode) + '-' + str(time.time_ns()) + '.log')
    print('START', key, mode, path.name, flush=True)
    with path.open('w', encoding='utf-8') as log:
        result = subprocess.run([sys.executable, '-u', str(Path(__file__).resolve()), '--rate', key, '--mode', mode], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print('DONE' if result.returncode == 0 else 'FAILED', key, mode, flush=True)
    return result.returncode


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--rate', choices=list(RATES), default='7p8')
    p.add_argument('--mode', choices=MODES, default='none')
    p.add_argument('--pack', action='store_true')
    p.add_argument('--batch', action='store_true')
    p.add_argument('--metadata-only', action='store_true')
    a = p.parse_args()
    if a.metadata_only:
        finalize_metadata()
    elif a.pack:
        pack()
    elif a.batch:
        jobs = [('75', 'network'), ('75', 'none'), ('75', 'zero-loss'), ('15p6', 'network'),
                ('7p8', 'network'), ('15p6', 'none'), ('15p6', 'zero-loss'), ('7p8', 'none'), ('7p8', 'zero-loss')]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(launch, jobs))
        if any(results):
            raise SystemExit('Inspect failed constant-rain jobs; no publication')
        pack()
    else:
        calculate(a.rate, a.mode)
