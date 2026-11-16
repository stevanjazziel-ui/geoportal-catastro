"""Lossless coding of already quantized water and cumulative-max display frames."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

ENCODING = 'water-time-zigzag-max-residual-u16-v1'


def encode(values, frames):
    values = np.asarray(values)
    if values.ndim != 2 or values.shape[0] != 2 * frames:
        raise ValueError('Invalid display shape')
    water = values[:frames].astype(np.int32)
    maxima = values[frames:].astype(np.int32)
    delta = np.diff(water, axis=0, prepend=np.zeros((1, water.shape[1]), np.int32))
    zigzag = (delta << 1) ^ (delta >> 31)
    residual = maxima - water
    if zigzag.max() > 65535 or residual.min() < 0 or residual.max() > 65535:
        raise ValueError('Display delta exceeds encoding bounds')
    return np.concatenate([zigzag, residual]).astype('<u2')


def decode(values, frames):
    values = np.asarray(values).astype(np.int32)
    delta = (values[:frames] >> 1) ^ -(values[:frames] & 1)
    water = np.cumsum(delta, axis=0, dtype=np.int32)
    result = np.concatenate([water, water + values[frames:]])
    if result.min() < 0 or result.max() > 65535:
        raise ValueError('Invalid decoded water depth')
    return result.astype('<u2')


def publish_encoded():
    root = Path(__file__).resolve().parent / 'dist/data/riobamba-local'
    manifest_path = root / 'manifest.json'
    m = json.loads(manifest_path.read_text(encoding='utf-8'))
    total = 0
    for c in m['cases']:
        source = (root / c['file']).read_bytes()
        if hashlib.sha256(source).hexdigest() != c['sha256']:
            raise ValueError('Source payload hash mismatch')
        if c.get('payload_encoding') == ENCODING:
            total += len(source)
            continue
        original = np.frombuffer(gzip.decompress(source), '<u2').reshape(2 * c['frame_count'], m['cell_count'])
        coded = encode(original, c['frame_count'])
        np.testing.assert_array_equal(decode(coded, c['frame_count']), original)
        blob = gzip.compress(coded.tobytes(), compresslevel=9, mtime=0)
        name = c['id'] + '.delta15.u16.gz'
        (root / name).write_bytes(blob)
        c.update(file=name, bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(),
                 payload_encoding=ENCODING, payload_delivery='pages',
                 download_url='https://stevanjazziel-ui.github.io/geoportal-catastro/inundaciones-ecuador/data/riobamba-local/' + name)
        total += len(blob)
        print(c['id'], len(blob), 'bytes; exact display roundtrip', flush=True)
    m.update(version='riobamba-constant-quarterhour-v2',
             binary_delivery='Pages; lossless time-delta and maximum-residual coding of the same centimetre display depths')
    manifest_path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')
    print('TOTAL ENCODED BYTES', total, flush=True)


if __name__ == '__main__':
    publish_encoded()
