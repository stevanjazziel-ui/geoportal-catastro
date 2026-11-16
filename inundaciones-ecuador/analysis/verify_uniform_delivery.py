"""Audit all 432 duration/intensity/drainage selections without future maxima."""
import gzip
import hashlib
import json
import numpy as np
from uniform_riobamba import ROOT, GRID, OUT, RATES, MODES, case_id
from uniform_payload_codec import ENCODING, decode


def main():
    m = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
    assert m['selectable_minutes'] == list(range(15, 721, 15))
    assert {c['id'] for c in m['cases']} == {case_id(k, mode) for k in RATES for mode in MODES}
    for c in m['cases']:
        blob = (OUT / c['file']).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == c['sha256'] and len(blob) == c['bytes']
        encoded = np.frombuffer(gzip.decompress(blob), '<u2').reshape(98, m['cell_count'])
        if c.get('payload_encoding') == ENCODING:
            encoded = decode(encoded, c['frame_count'])
        assert c['cumulative_max_offset'] == 49
        assert c['times_minutes'] == list(range(0, 721, 15))
        with np.load(GRID / c['id'] / 'result.npz') as f:
            frames, max_frames = f['frames'], f['max_frames']
            for index, minutes in enumerate(c['times_minutes']):
                raw = frames[index].reshape(-1)
                maxima = max_frames[index].reshape(-1)
                np.testing.assert_array_equal(encoded[index], np.floor(raw * 100 + 1e-6).astype('<u2'))
                np.testing.assert_array_equal(encoded[49 + index], np.floor(maxima * 100 + 1e-6).astype('<u2'))
                assert np.all(maxima >= raw)
                if index:
                    assert np.all(maxima >= max_frames[index - 1].reshape(-1))
                s = c['cumulative_stats_by_frame'][index]
                assert abs(float(maxima.max()) - s['max_depth_m']) < 1e-4
                # Original metrics use float64, stored display inputs use float32.
                # Bound only the representational ambiguity at exactly 5 cm.
                half_ulp = float(np.spacing(np.float32(.05))) / 2
                lower = (maxima.astype(float) - half_ulp >= .05).sum() * 24**2 / 1e6
                upper = (maxima.astype(float) + half_ulp >= .05).sum() * 24**2 / 1e6
                assert lower - 1e-8 <= s['max_footprint_km2'] <= upper + 1e-8
                assert s['mass_relative_error'] < 1e-8
        r = json.loads((OUT / c['report']).read_text(encoding='utf-8'))
        assert r['calibrated'] is False and r['uniform_rainfall'] is True
        assert r['metadata']['rain_input']['mm_h'] == c['rain_mm_h']
        assert r['metadata']['rain_input']['mode'] == 'constant selected intensity'
        if c['network_diagnostics']:
            assert abs(c['network_diagnostics']['routing_continuity_error_percent']) < 1
        print(c['id'], '49 exact prefixes OK', flush=True)
    print('VERIFIED: 432 selections; exact time cutoffs, no future maxima, valid budgets and encoding.')


if __name__ == '__main__':
    main()
