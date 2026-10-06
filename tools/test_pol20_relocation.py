"""Independent checks for the single POL-20 relocation and its GIS derivatives."""
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from shapely import covers
from shapely.ops import unary_union

from build_police_camera_proposal import CLASSES, read_layer, sha, coverage_class
from relocate_pol20 import PACKAGE, OUT, SLOT


def main(source_package=PACKAGE, destination=OUT, slot=SLOT,
         candidate='CAND-POL-01017', platform='PLATAFORMA G',
         exclusive_dv=12, overlap=22.613446324336934):
    PACKAGE, OUT, SLOT = Path(source_package), Path(destination), slot
    result = json.loads((OUT / 'RESULTADOS.json').read_text(encoding='utf-8'))
    previous_result = json.loads((PACKAGE.parent / 'RESULTADOS.json').read_text(encoding='utf-8'))
    final = OUT / PACKAGE.name
    before = read_layer(PACKAGE, 'PROPUESTA_POLICIA_30_FINAL').set_index('ID_POLICIA')
    after = read_layer(final, 'PROPUESTA_POLICIA_30_FINAL').set_index('ID_POLICIA')
    assert len(after) == 30 and set(after.index) == set(before.index)
    assert len({g.wkb for g in after.geometry}) == 30
    changed = [id for id in before.index if not before.loc[id].geometry.equals_exact(after.loc[id].geometry, 0)]
    assert changed == [SLOT]
    assert after.loc[SLOT].ID_CANDIDATO == candidate
    assert after.loc[SLOT].PLATAFORMA == platform
    assert after.loc[SLOT].DV_NUEVOS == exclusive_dv
    assert abs(after.loc[SLOT].SOLAPE_PCT - overlap) < 1e-6
    frozen = ['CAMARAS_EXISTENTES_103_FINAL', 'PROPUESTA_MUNICIPAL_50_FINAL', 'COBERTURA_A', 'COBERTURA_B',
              'PLATAFORMAS_TERRITORIALES', 'CORREDORES', 'RED_VIAL_CONTEXTO', 'LIMITE_CANTONAL']
    frozen += ['GI_' + scope + '_' + cat for scope in ('URBANO', 'RURAL') for cat in CLASSES]
    for name in frozen:
        a, b = read_layer(PACKAGE, name), read_layer(final, name)
        assert a.crs.to_epsg() == b.crs.to_epsg() == 32717
        assert list(a.geometry.to_wkb()) == list(b.geometry.to_wkb()), name
        pd.testing.assert_frame_equal(a.drop(columns='geometry'), b.drop(columns='geometry'))
    equipment = read_layer(final, 'ESCENARIO_FINAL_183')
    assert len(equipment) == len(set(equipment.ID_EQUIPO)) == 183
    baseline = read_layer(final, 'COBERTURA_B').geometry.iloc[0]
    mask = read_layer(final, 'COBERTURA_C').geometry.iloc[0]
    assert mask.symmetric_difference(unary_union([baseline] + [g.buffer(200, quad_segs=64) for g in after.geometry])).area < .001
    points = read_layer(final, 'INCIDENTES_CLASIFICADOS')
    for name in ('INCIDENTES_CLASIFICADOS', 'MANZANAS_COBERTURA'):
        assert list(read_layer(PACKAGE, name).geometry.to_wkb()) == list(read_layer(final, name).geometry.to_wkb())
    for kind in ('incidents', 'hotspots', 'population', 'territorial', 'corridors'):
        assert [r for r in result[kind] if r['ESCENARIO'] != 'C'] == [r for r in previous_result[kind] if r['ESCENARIO'] != 'C']
    inside = covers(mask, np.array(list(points.geometry), dtype=object))
    assert np.array_equal(inside, points.CUB_C.to_numpy())
    for cat in CLASSES:
        count = int((inside & (points.CATEGORIA == cat) & (points.AMBITO != 'EXTERNO_CANTON')).sum())
        row = next(r for r in result['incidents'] if r['ESCENARIO'] == 'C' and r['AMBITO'] == 'CANTONAL' and r['CATEGORIA'] == cat)
        assert row['CUBIERTOS'] == count
    for id, p in after.iterrows():
        disk = p.geometry.buffer(200, quad_segs=64)
        reference = unary_union([baseline] + [g.buffer(200, quad_segs=64) for g in after.drop(index=id).geometry])
        assert abs(disk.intersection(reference).area / disk.area * 100 - p.SOLAPE_PCT) < 1e-6
        exclusive = covers(disk, np.array(list(points.geometry), dtype=object)) & ~covers(reference, np.array(list(points.geometry), dtype=object))
        assert int((exclusive & points.CATEGORIA.isin(CLASSES[:2])).sum()) == p.DV_NUEVOS
    old_mask = read_layer(PACKAGE, 'COBERTURA_C').geometry.iloc[0]
    for cat in CLASSES[:2]:
        hot = read_layer(final, 'HOTSPOT_' + cat)
        for _, p in hot[hot.NIVEL == 99].iterrows():
            if coverage_class(p.geometry.intersection(old_mask).area / p.geometry.area) != 'SIN COBERTURA':
                assert coverage_class(p.geometry.intersection(mask).area / p.geometry.area) != 'SIN COBERTURA'
    for file, digest in result['sourceHashes'].items():
        assert sha(Path(file)) == digest
    assert result['gapScenarioCValidated'] is False
    with zipfile.ZipFile(OUT / 'CIERRE_POLICIA_30_FINAL.zip') as archive:
        assert archive.testzip() is None
        assert PACKAGE.name in archive.namelist()
    print('PASS: solo ' + SLOT + ' reubicada,29fijas,103/50/Gi intactos,183equipos,200m,solapes/eventos recalculados,99 no abandonados,ZIP valido.')


if __name__ == '__main__':
    main()
