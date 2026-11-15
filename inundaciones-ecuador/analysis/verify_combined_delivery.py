"""Validate scientific lineage, recalculated outputs and browser encoding."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from combined_riobamba import ROOT, GRID, OUT, SPEC, modes, hyetograph


def main():
    m = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
    expected = {name + ('-network' if mode == 'network' else '-zero-loss' if mode == 'zero-loss' else '')
                for name in SPEC for mode in modes(name)}
    assert {c['id'] for c in m['cases']} == expected
    cat = json.loads((OUT / m['combined_idf_catalog']).read_text(encoding='utf-8'))
    assert cat['source_pdf_sha256'] == hashlib.sha256((ROOT / 'riobamba-inputs/idf/INAMHI-intensidades-final-1.pdf').read_bytes()).hexdigest()
    for c in m['cases']:
        name = c['id'].removesuffix('-network').removesuffix('-zero-loss')
        h = hyetograph(name, cat={**cat, 'mean_intensities_mm_h': {int(k): v for k, v in cat['mean_intensities_mm_h'].items()}})
        assert c['hyetograph']['return_period_years'] is None
        assert abs(c['total_rain_mm'] - h['total_mm']) < 1e-8
        r = json.loads((OUT / c['report']).read_text(encoding='utf-8'))
        assert r['calibrated'] is False and r['synthetic_event'] is True
        assert abs(r['stats']['mass_relative_error']) < 1e-6
        assert abs(r['rain_partition']['rain_partition_residual_m3']) < .01
        if c.get('network_diagnostics'):
            assert abs(c['network_diagnostics']['routing_continuity_error_percent']) < 1
        blob = (OUT / c['file']).read_bytes()
        assert len(blob) == c['bytes']
        assert hashlib.sha256(blob).hexdigest() == c['sha256']
        encoded = np.frombuffer(gzip.decompress(blob), dtype='<u2').reshape(c['frame_count'] + 1, m['cell_count'])
        assert c['max_frame_index'] == c['frame_count']
        assert c['times_minutes'][-1] == c['duration_hours'] * 60
        with np.load(GRID / c['id'] / 'result.npz') as f:
            times = f['times_minutes']
            ix = [int(np.flatnonzero(times == t)[0]) for t in c['times_minutes']]
            original = np.concatenate([f['frames'][ix], f['max_depth'][None]]).reshape(encoded.shape)
            np.testing.assert_array_equal(encoded, np.floor(original * 100 + 1e-6).astype('<u2'))
            assert abs(float(f['max_depth'].max()) - c['stats']['max_depth_m']) < 1e-4
            area = float((f['max_depth'] >= .05).sum() * 24 ** 2 / 1e6)
            assert abs(area - c['stats']['max_footprint_km2']) < 1e-8
        print(c['id'], 'OK', flush=True)
    print('VERIFIED', len(expected), 'recalculated simulations; balances, lineage and browser encoding pass.')


if __name__ == '__main__':
    main()
