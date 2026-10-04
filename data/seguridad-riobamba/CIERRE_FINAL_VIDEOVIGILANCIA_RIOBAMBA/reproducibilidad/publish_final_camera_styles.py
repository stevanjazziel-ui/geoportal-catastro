"""Presentation-only group coverage; preserve final coordinates, Gi* and statistics."""
import json
from shapely.ops import unary_union
from close_final_camera_study import OUT, PACKAGE, GROUPS, ROOT, sha, read_layer, export, jsave


def main():
    data = json.loads((OUT / 'RESULTADOS.json').read_text(encoding='utf-8'))
    inputs = [('CAMARAS_EXISTENTES_103_FINAL', 103),
              ('PROPUESTA_MUNICIPAL_50_FINAL', 50), ('PROPUESTA_POLICIA_30_FINAL', 30)]
    frames = [read_layer(PACKAGE, name) for name, _ in inputs]
    for frame, (name, count) in zip(frames, inputs):
        assert len(frame) == count and frame.crs.to_epsg() == 32717, name
        assert frame.geometry.notna().all() and frame.geometry.is_valid.all(), name
    change = int(frames[0]['REQUIERE_CAMBIO'].sum())
    assert change == 31
    masks = [unary_union([g.buffer(200, quad_segs=64) for g in frame.geometry]) for frame in frames]
    original = unary_union(read_layer(PACKAGE, 'COBERTURA_C').geometry)
    difference = unary_union(masks).symmetric_difference(original).area
    assert difference < 1e-4, difference
    names = ['COBERTURA_MUNICIPAL_200M', 'COBERTURA_POLICIA_200M']
    added = [export(name, [(mask, {'RADIO_M': 200, 'N_CAMARAS': count,
        'METODO': 'BUFFER EPSG:32717; UNION DISUELTA'})], GROUPS[3],
        'Geometrias finales; presentacion por grupo sin cambiar union oficial')
        for name, mask, count in zip(names, masks[1:], [50, 30])]
    data['catalog'] = [r for r in data['catalog'] if r['name'] not in names] + added
    data['publicationStyle'] = {'existing': '#246db5', 'change': '#8b46b5',
        'municipal': '#18815b', 'police': '#e8bd16', 'changeSymbol': 'square', 'radiusM': 200}
    viewer = str(ROOT / 'visor-seguridad-riobamba-v2.html')
    data['publicationUiChanges'] = {viewer: {'before': data['sourceHashes'][viewer],
        'after': sha(ROOT / 'visor-seguridad-riobamba-v2.html'),
        'reason': 'Publicacion autorizada; conexion a entrega final y controles de visualizacion'}}
    jsave('RESULTADOS.json', data)
    jsave('VALIDACION_PUBLICACION.json', {'passed': True, 'inventoried': 103,
        'requiresChange': change, 'municipal': 50, 'police': 30, 'total': 183,
        'radiusM': 200, 'crsMetric': 'EPSG:32717', 'coverageDifferenceM2': difference,
        'coordinatesModified': False, 'statisticsModified': False, 'giModified': False})
    print(json.dumps({'passed': True, 'counts': [103, change, 50, 30], 'coverageDifferenceM2': difference}))


if __name__ == '__main__':
    main()
