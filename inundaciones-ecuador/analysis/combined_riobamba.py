"""Equal-weight station references and explicitly hypothetical preparedness storms.

Never average existing flood depths. All new rainfall inputs are routed again.
The average of station quantiles is not an areal quantile or an ENSO forecast.
"""
import argparse
import gzip
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from pypdf import PdfReader
from run_riobamba_cases import run
from variable_riobamba import network_for

ROOT = Path(__file__).resolve().parent
GRID = ROOT / 'riobamba-runs/grid-24m'
OUT = ROOT / 'dist/data/riobamba-local'
SOURCE = 'https://www.inamhi.gob.ec/Publicaciones/Hidrologia/estudui_de_intensidades_v1_2018_1'
ERFEN = 'https://www.inocar.mil.ec/boletin/ERFEN/erfen_20261105.pdf'
RETURNS = [2, 5, 10, 25, 50, 100]
SPEC = {
    'combined-6h-low': (25, 360, 1., 1),
    'combined-6h-medium': (50, 360, 1., 1),
    'combined-6h-high': (100, 360, 1., 1),
    'prepared-1h-double': (100, 60, 2., 1),
    'prepared-6h-double': (100, 360, 2., 1),
    'prepared-12h-repeat': (100, 360, 1., 2),
}
LIMITS = [
    'Equal-weight mean of historical point-station IDF values; not an observed storm.',
    'Averaging station quantiles does not establish an areal return period or joint exceedance probability.',
    'Uniform spatial rain with areal factor 1; no locally verified areal correction.',
    'Uncalibrated soil losses, roughness, boundaries and inferred sewer geometry remain.',
    'Zero infiltration is a limiting assumption, not measured saturation or an antecedent soil simulation.',
    'No upstream river flood hydrograph, bathymetry or bidirectional sewer feedback.',
    'ENSO context does not prescribe an hourly rainfall multiplier for Riobamba.',
]


def catalog():
    pdf = ROOT / 'riobamba-inputs/idf/INAMHI-intensidades-final-1.pdf'
    reader = PdfReader(pdf)
    stations = {}
    for code, name, page, table in [('M1036', 'Riobamba–ESPOCH', 100, 72),
                                     ('M0057', 'Riobamba Aeropuerto', 55, 27)]:
        text = reader.pages[page].extract_text()
        rows = {}
        for line in text.splitlines():
            values = line.split()
            if len(values) == 7 and values[0] in ['10', '15', '20', '30', '60', '120', '360']:
                try:
                    rows[int(values[0])] = [float(v) for v in values[1:]]
                except ValueError:
                    pass
        if set(rows) != {10, 15, 20, 30, 60, 120, 360}:
            raise ValueError(f'Incomplete source table {code}')
        stations[code] = {'name': name, 'source_table_code': 'M01036' if code == 'M1036' else code,
                          'printed_page': page, 'pdf_page': page + 1,
                          'table': table, 'weight': .5, 'intensities_mm_h': rows}
    averages = {d: ((np.array(stations['M1036']['intensities_mm_h'][d]) +
                    np.array(stations['M0057']['intensities_mm_h'][d])) / 2).tolist()
                for d in [10, 15, 20, 30, 60, 120, 360]}
    return {'source_url': SOURCE, 'study_year': 2015, 'source_retrieved': '2026-11-14',
            'combined_on': '2026-11-15',
            'source_pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
            'return_years_of_source_tables': RETURNS, 'stations': stations,
            'mean_intensities_mm_h': averages, 'method': '(ESPOCH + Aeropuerto) / 2 for matching duration and source return level',
            'assigned_combined_return_period_years': None, 'limitations': LIMITS}


def hyetograph(name, cat=None):
    cat = cat or catalog()
    ret, minutes, multiplier, repetitions = SPEC[name]
    durations = np.array([d for d in [10, 15, 20, 30, 60, 120, 360] if d <= minutes])
    ix = RETURNS.index(ret)
    intensities = np.array([cat['mean_intensities_mm_h'][int(d)][ix] for d in durations])
    depths = intensities * durations / 60
    time = np.arange(10, minutes + 1, 10)
    cumulative = np.exp(np.interp(np.log(time), np.log(durations), np.log(depths)))
    increments = np.diff(np.r_[0, cumulative])
    if np.min(increments) < -1e-10:
        raise ValueError('Non-monotone depth-duration source')
    order = [len(time) // 2]
    for k in range(1, len(time)):
        for i in [len(time) // 2 - k, len(time) // 2 + k]:
            if 0 <= i < len(time):
                order.append(i)
    blocks = np.zeros(len(time))
    blocks[order] = np.sort(increments)[::-1]
    checks = []
    for d in durations:
        if d % 10:
            continue
        expected = float(depths[np.flatnonzero(durations == d)[0]])
        actual = float(np.convolve(blocks, np.ones(d // 10), 'valid').max())
        checks.append({'minutes': int(d), 'reference_depth_mm': expected,
                       'arranged_depth_mm': actual, 'relative_difference': actual / expected - 1})
    if max(abs(c['relative_difference']) for c in checks) > .02:
        raise ValueError('Nested storm differs from reference by over 2%')
    blocks = np.tile(blocks * multiplier, repetitions)
    stress = multiplier != 1 or repetitions != 1
    return {'station': 'Promedio 50/50 ESPOCH y Aeropuerto', 'source_url': SOURCE,
            'source_return_period_years': ret, 'return_period_years': None,
            'station_weights': {'M1036': .5, 'M0057': .5},
            'duration_minutes': minutes * repetitions, 'interval_minutes': 10,
            'seconds': list(range(0, minutes * repetitions * 60, 600)) + [minutes * repetitions * 60],
            'intensities_mm_h': (blocks * 6).tolist() + [0.],
            'total_mm': float(blocks.sum()), 'peak_mm_h': float(blocks.max() * 6),
            'peak_start_minutes': int(np.argmax(blocks) * 10),
            'peak_end_minutes': int((np.argmax(blocks) + 1) * 10),
            'duration_checks': checks, 'rainfall_multiplier': multiplier,
            'repetitions': repetitions, 'preparedness_test': stress,
            'scenario_basis': 'Chosen sensitivity assumption; no verified ENSO multiplier' if stress else 'Equal-weight station reference',
            'method': 'Log-log depth interpolation and alternating 10min blocks; repeat or multiply only when explicitly declared',
            'areal_reduction_factor': 1., 'limitations': LIMITS}


def modes(name):
    # Extra comparisons focus on the severe preparedness scenarios and the
    # highest combined reference. Lower references remain baseline rain only.
    return ['none'] if name in ['combined-6h-low', 'combined-6h-medium'] else ['none', 'network', 'zero-loss']


def calculate(name, mode, dx=24):
    if mode not in modes(name):
        print('Reference-only scenario; no additional drainage case requested:', name, mode, flush=True)
        return
    h = hyetograph(name)
    rain_hours = h['duration_minutes'] / 60
    # An extra six hours after long events, one hour after the short storm.
    end = rain_hours + (6 if rain_hours >= 6 else 1)
    grid = ROOT / f'riobamba-runs/grid-{dx}m'
    case = name + ('-network' if mode == 'network' else '-zero-loss' if mode == 'zero-loss' else '')
    folder = grid / case
    if dx != 24 and mode != 'none':
        raise ValueError('Network diagnostic is only implemented on 24m mesh')
    network = network_for(None, h, 'network-' + name, end) if mode == 'network' else None
    if not (folder / 'report.json').exists():
        if folder.exists():
            raise RuntimeError('Inspect incomplete surface run before resuming: ' + str(folder))
        run(grid, case, rain_hours, h['total_mm'] / rain_hours, end, network,
            infiltration_factor=0. if mode == 'zero-loss' else 1.,
            rain_profile=np.c_[h['seconds'], h['intensities_mm_h']], snapshot_minutes=10 if rain_hours <= 1 else 30)
    report = json.loads((folder / 'report.json').read_text())
    report.update(hyetograph=h, rain_mm_h_is_mean=True, total_rain_mm=h['total_mm'], limitations=LIMITS)
    report['metadata']['rain_input'] = h
    volume = np.array([v['volume_m3'] for v in report['hydrograph']])
    report['recession'] = {'rain_end_hours': rain_hours, 'simulation_end_hours': end,
                           'recession_hours': end - rain_hours,
                           'final_fraction_of_peak_volume': float(volume[-1] / max(1, volume.max())),
                           'peak_volume_sampling_minutes': 10 if rain_hours <= 1 else 30,
                           'interpretation': 'Finite calculation window; residual water is not proof of complete drainage.'}
    if network:
        report['network_diagnostics'] = json.loads((network / 'summary.json').read_text())
    if abs(report['stats']['mass_relative_error']) > 1e-6:
        raise ValueError('Surface mass balance failed')
    (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def guarded_calculate(name, mode, dx):
    """Coordinate exact-case ownership across isolated command environments.

    PIDs are informational: a sibling command may not expose its process table.
    Never infer process death from a PID lookup in a different command sandbox.
    """
    case = name + ('-network' if mode == 'network' else '-zero-loss' if mode == 'zero-loss' else '')
    lock = ROOT / f'riobamba-runs/grid-{dx}m/.{case}.run.lock.json'
    owner = {'pid': os.getpid(), 'claimed_utc_epoch': time.time()}
    started = time.monotonic()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, 'w') as f:
                json.dump(owner, f)
            break
        except FileExistsError:
            try:
                json.loads(lock.read_text())
            except FileNotFoundError:
                continue  # Owner finished between exclusive-open and inspection.
            except json.JSONDecodeError as error:
                if time.monotonic() - started < 5:
                    time.sleep(.1)  # Owner is writing its newly claimed lock.
                    continue
                raise RuntimeError('Unreadable run lock; inspect before resuming: ' + str(lock)) from error
            if time.monotonic() - started > 3600:
                raise TimeoutError('Calculation owner did not finish within an hour')
            print('Waiting for existing calculation:', case, flush=True)
            time.sleep(5)
    try:
        calculate(name, mode, dx)
    finally:
        lock.unlink()


def pack():
    cat = catalog()
    manifest = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
    previous = OUT / 'previous-scenarios-20261114.json'
    if not previous.exists():
        previous.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    history = json.loads(previous.read_text(encoding='utf-8'))
    base_url = 'https://raw.githubusercontent.com/stevanjazziel-ui/geoportal-catastro/main/inundaciones-ecuador/data/riobamba-local/'
    history['archived_assets_delivery'] = 'Historical case assets remain in GitHub; use each case asset_urls. Active Pages site serves the new simulations.'
    for case in history['cases']:
        case['asset_urls'] = {key: value if value.startswith('https://') else base_url + value
                              for key in ['file', 'report', 'network_input_file', 'network_report_file']
                              if isinstance(value := case.get(key), str)}
    previous.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
    items = []
    archives = ROOT / 'model-archives'
    archives.mkdir(exist_ok=True)
    for name in SPEC:
        for mode in modes(name):
            case = name + ('-network' if mode == 'network' else '-zero-loss' if mode == 'zero-loss' else '')
            folder = GRID / case
            r = json.loads((folder / 'report.json').read_text())
            h = r['hyetograph']
            net = GRID / ('network-' + name) if mode == 'network' else None
            domain_rain = h['total_mm'] / 1000 * manifest['valid_km2'] * 1e6
            partition = {'uniform_domain_rain_m3': domain_rain, 'direct_rain_2d_m3': r['stats']['direct_rain_m3']}
            captured_rain = 0.
            if net:
                a = json.loads((net / 'assumptions.json').read_text())
                captured_rain = h['total_mm'] / 1000 * a['captured_km2'] * 1e6
                partition.update(captured_excess_input_swmm_m3=a['input_runoff_m3'], captured_rain_losses_m3=captured_rain - a['input_runoff_m3'])
                with np.load(net / 'surface-forcing.npz') as f:
                    if abs(f['seconds'][-1] - r['duration_hours'] * 3600) > 1e-5:
                        raise ValueError('Truncated sewer output')
                    overflow = float(np.sum(f['rates_m3_s'][1:] * np.diff(f['seconds'])[:, None]))
                if abs(overflow - r['stats']['prescribed_overflow_m3']) > .001:
                    raise ValueError('Overflow volume transfer failed')
                if abs(r['network_diagnostics']['routing_continuity_error_percent']) > 1:
                    raise ValueError('Sewer continuity exceeds 1%')
                partition['overflow_transferred_m3'] = overflow
            partition['rain_partition_residual_m3'] = domain_rain - partition['direct_rain_2d_m3'] - captured_rain
            if abs(partition['rain_partition_residual_m3']) > .01:
                raise ValueError('Rain partition failed')
            r['rain_partition'] = partition
            (OUT / (case + '-report.json')).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding='utf-8')
            with np.load(folder / 'result.npz') as f:
                display_minutes = 10 if r['rain_hours'] <= 1 else 60
                keep = [i for i, t in enumerate(f['times_minutes']) if t % display_minutes == 0 or i == len(f['times_minutes']) - 1]
                depths = np.concatenate([f['frames'][keep], f['max_depth'][None]])
                if not np.isfinite(depths).all() or depths.min() < 0 or depths.max() > 655.35:
                    raise ValueError('Invalid depth range')
                blob = gzip.compress(np.floor(depths * 100 + 1e-6).astype('<u2').tobytes(), mtime=0)
                filename = case + f'.display-cm{display_minutes}.u16.gz'
                (OUT / filename).write_bytes(blob)
                wet = [0.] + [v['wet_km2'] for v in r['hydrograph']]
                item = {'id': case, 'label': name + ' · ' + mode, 'file': filename,
                        'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest(),
                        'depth_scale_m': .01, 'display_snapshot_minutes': display_minutes,
                        'frame_count': len(keep), 'max_frame_index': len(keep),
                        'times_minutes': f['times_minutes'][keep].tolist(),
                        'wet_km2_by_frame': [wet[i] for i in keep], 'stats': r['stats'],
                        'rain_mm_h': r['rain_mm_h'], 'rain_mm_h_is_mean': True,
                        'total_rain_mm': h['total_mm'], 'rain_hours': r['rain_hours'],
                        'duration_hours': r['duration_hours'], 'hyetograph': h,
                        'recession': r['recession'], 'infiltration_multiplier': r['infiltration_multiplier'],
                        'network_diagnostics': r.get('network_diagnostics'), 'report': case + '-report.json'}
                if net:
                    for ext, key in [('inp', 'network_input_file'), ('rpt', 'network_report_file')]:
                        fn = case + '.' + ext + '.gz'
                        (archives / fn).write_bytes(gzip.compress((net / ('network.' + ext)).read_bytes(), mtime=0))
                        item[key] = 'https://raw.githubusercontent.com/stevanjazziel-ui/geoportal-catastro/main/inundaciones-ecuador/model-archives/' + fn
                items.append(item)
    coarse = json.loads((ROOT / 'riobamba-runs/grid-48m/combined-6h-high/report.json').read_text())
    fine = next(c for c in items if c['id'] == 'combined-6h-high')
    sensitivity = {'scenario': 'Combined high reference, 6h, no sewer',
                   'area_24m_km2': fine['stats']['max_footprint_km2'], 'area_48m_km2': coarse['stats']['max_footprint_km2'],
                   'area_change_percent': 100 * (coarse['stats']['max_footprint_km2'] / fine['stats']['max_footprint_km2'] - 1),
                   'max_depth_24m_m': fine['stats']['max_depth_m'], 'max_depth_48m_m': coarse['stats']['max_depth_m'],
                   'interpretation': 'Sensitivity for this reference only; not convergence or field validation.'}
    context = {'source_url': ERFEN, 'report_date': '2026-11-05', 'checked': '2026-11-15',
               'report_id': 'ERFEN 012-2026', 'status_in_report': 'ACTIVO',
               'regional_outlook': 'November: normal monthly precipitation in inter-Andean valley; not a forecast of hourly Riobamba extremes.',
               'local_enso_rainfall_multiplier_established': False,
               'assumptions': 'Doubling intensity and repeating storms are chosen sensitivity tests, not forecasts or physical maxima.',
               'pdf_sha256': hashlib.sha256((ROOT / 'riobamba-inputs/enso/ERFEN-20261105.pdf').read_bytes()).hexdigest()}
    for fn, data in [('combined-station-idf.json', cat), ('preparedness-context.json', context), ('combined-grid-sensitivity.json', sensitivity)]:
        (OUT / fn).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    geometry_file = OUT / manifest['network']
    geometry = json.loads(gzip.decompress(geometry_file.read_bytes()))
    geometry['assumptions'] = json.loads((GRID / 'network-combined-6h-high/assumptions.json').read_text())
    geometry['diagnostics'] = json.loads((GRID / 'network-combined-6h-high/summary.json').read_text())
    geometry['scenario'] = 'Shared inferred geometry; these metadata describe combined-6h-high-network. Each case report specifies its actual rainfall and routing.'
    geometry_file.write_bytes(gzip.compress(json.dumps(geometry, separators=(',', ':')).encode(), mtime=0))
    manifest.update(cases=items, version='riobamba-combined-preparedness-20261115-v1',
                    combined_idf_catalog='combined-station-idf.json', idf_catalog='combined-station-idf.json',
                    stress_context='preparedness-context.json', enso_context=context,
                    variable_sensitivity=sensitivity, previous_scenarios=previous.name,
                    sensitivity=sensitivity, network_geometry_reference_case='combined-6h-high-network',
                    display_note='Short storm: 10min frames. Longer storms: 60min frames. Downward centimetre encoding; metrics use original results.')
    manifest['metadata']['rain_input'] = {
        'catalog': 'combined-station-idf.json', 'profiles': 'cases[].hyetograph',
        'method': 'Equal-weight ESPOCH and Aeropuerto reference; explicitly chosen preparedness changes.',
        'annual_maxima_reference_is_not_active_input': True,
    }
    manifest['notes_es'] = [
        'Referencia combinada: promedio 50/50 de ESPOCH y Aeropuerto para la misma duración y nivel de las tablas históricas.',
        'El promedio no representa una tormenta observada ni tiene una probabilidad anual asignada.',
        'Las pruebas de preparación aumentan la lluvia o repiten dos tormentas. No son pronósticos de El Niño ni máximos demostrados.',
        'Se supone que llueve en toda la zona; falta comprobar cómo varía la lluvia entre sectores.',
        'El drenaje, la absorción del suelo y otras características todavía son estimaciones.',
        'Suelo sin absorción es una condición de prueba; no una medición de la humedad actual.',
        'No se incluye una crecida externa del río ni la devolución de agua superficial al alcantarillado.',
        'Falta comparar los resultados con inundaciones observadas. No usar como alerta ni para decidir sobre una vivienda concreta.',
    ]
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PACKED', len(items), 'newly calculated cases', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--case', choices=list(SPEC))
    p.add_argument('--mode', choices=['none', 'network', 'zero-loss'], default='none')
    p.add_argument('--dx', type=int, default=24)
    p.add_argument('--pack', action='store_true')
    p.add_argument('--catalog', action='store_true')
    a = p.parse_args()
    if a.pack:
        pack()
    elif a.catalog:
        data = catalog()
        (OUT / 'combined-station-idf.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        for name in SPEC:
            h = hyetograph(name, data)
            print(name, h['total_mm'], 'mm;', h['duration_minutes'], 'min;', h['peak_mm_h'], 'mm/h peak')
    else:
        guarded_calculate(a.case or 'combined-6h-high', a.mode, a.dx)
