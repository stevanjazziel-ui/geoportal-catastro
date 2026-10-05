"""Independent regression checks for the approved final police configuration."""
import json
import zipfile
from itertools import combinations
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import covers
from shapely.ops import unary_union

from finalize_police_30 import OUT, ROOT, PACKAGE, FINAL_PACKAGE, RELOCATED, sha


def read(package, layer):
    frame = gpd.read_file(package, layer=layer)
    assert frame.crs.to_epsg() == 32717, layer
    return frame


def unchanged(layer):
    old, final = read(PACKAGE, layer), read(FINAL_PACKAGE, layer)
    assert list(old.columns) == list(final.columns), layer
    pd.testing.assert_frame_equal(old.drop(columns='geometry'), final.drop(columns='geometry'), check_dtype=False)
    assert all(a.equals_exact(b, 0) for a, b in zip(old.geometry, final.geometry)), layer


def main():
    result = json.loads((OUT / 'RESULTADOS.json').read_text(encoding='utf-8'))
    validation = json.loads((OUT / 'VALIDACION.json').read_text(encoding='utf-8'))
    assert validation['estado'] == 'FINAL'
    assert all(sha(Path(p)) == h for p, h in validation['fuentes_protegidas_hash'].items())
    for layer in ('CAMARAS_EXISTENTES_103_FINAL', 'PROPUESTA_MUNICIPAL_50_FINAL',
                  'PLATAFORMAS_TERRITORIALES', 'LIMITE_CANTONAL', 'CORREDORES',
                  'RED_VIAL_CONTEXTO', 'UPC_INFRAESTRUCTURA', 'COBERTURA_A', 'COBERTURA_B'):
        unchanged(layer)
    for scope in ('URBANO', 'RURAL'):
        for category in ('DELINCUENCIA', 'VIOLENCIA', 'CONVIVENCIA'):
            unchanged('GI_' + scope + '_' + category)
    existing = read(FINAL_PACKAGE, 'CAMARAS_EXISTENTES_103_FINAL')
    municipal = read(FINAL_PACKAGE, 'PROPUESTA_MUNICIPAL_50_FINAL')
    police = read(FINAL_PACKAGE, 'PROPUESTA_POLICIA_30_FINAL').set_index('ID_POLICIA')
    former = read(PACKAGE, 'PROPUESTA_POLICIA_30_FINAL').set_index('ID_POLICIA')
    combined = read(FINAL_PACKAGE, 'ESCENARIO_FINAL_183')
    assert (len(existing), len(municipal), len(police), len(combined)) == (103, 50, 30, 183)
    assert existing.REQUIERE_CAMBIO.sum() == 31
    assert combined.ID_EQUIPO.nunique() == 183
    assert set(police[police.DECISION_FINAL == 'REUBICAR'].index) == RELOCATED
    assert sum(police.loc[id].geometry.equals_exact(former.loc[id].geometry, 0) for id in police.index) == 22
    assert police.geometry.to_wkb().nunique() == 30
    baseline = read(FINAL_PACKAGE, 'COBERTURA_B').geometry.iloc[0]
    disks = {id: row.geometry.buffer(200, quad_segs=64) for id, row in police.iterrows()}
    union = unary_union([baseline, *disks.values()])
    final_mask = read(FINAL_PACKAGE, 'COBERTURA_C').geometry.iloc[0]
    assert union.symmetric_difference(final_mask).area < .01
    events = read(PACKAGE, 'INCIDENTES_CLASIFICADOS')
    points = events.geometry.to_numpy()
    canton = unary_union(read(PACKAGE, 'LIMITE_CANTONAL').geometry)
    in_canton = covers(canton, points)
    expected = {'DELINCUENCIA': 1783, 'VIOLENCIA': 989, 'CONVIVENCIA': 4999}
    for category, count in expected.items():
        selected = (events.CATEGORIA == category).to_numpy() & in_canton
        actual = int(covers(final_mask, points[selected]).sum())
        assert actual == count
        row = next(r for r in result['incidents'] if r['ESCENARIO'] == 'C' and r['AMBITO'] == 'CANTONAL' and r['CATEGORIA'] == category)
        assert row['CUBIERTOS'] == actual
    for id, row in police.iterrows():
        reference = unary_union([baseline, *[g for key, g in disks.items() if key != id]])
        exclusive = disks[id].difference(reference)
        overlap = disks[id].intersection(reference)
        assert abs(row.AREA_EXCLUSIVA_M2 - exclusive.area) < .01
        assert abs(row.AREA_SOLAPADA_M2 - overlap.area) < .01
        assert abs(row.SOLAPE_PCT - overlap.area / disks[id].area * 100) < 1e-6
        selected = events.CATEGORIA.isin(('DELINCUENCIA', 'VIOLENCIA')).to_numpy()
        actual = int((covers(disks[id], points[selected]) & ~covers(reference, points[selected])).sum())
        assert actual == row.DV_NUEVOS
        assert abs(row.X - row.geometry.x) < 1e-6 and abs(row.Y - row.geometry.y) < 1e-6
        assert abs(row.DIST_EXISTENTE_M - existing.geometry.distance(row.geometry).min()) < 1e-6
        assert abs(row.DIST_MUNICIPAL_M - municipal.geometry.distance(row.geometry).min()) < 1e-6
        assert abs(row.DIST_POLICIA_M - police.drop(index=id).geometry.distance(row.geometry).min()) < 1e-6
        assert row.SOLAPE_PCT <= 85 and row.JUSTIFICACION
    matrix = pd.read_csv(OUT / 'MATRIZ_DISTANCIAS_POLICIA_30.csv').set_index('ID_POLICIA')
    assert matrix.shape == (30, 30)
    assert np.allclose(matrix.to_numpy(), matrix.to_numpy().T) and np.allclose(np.diag(matrix), 0)
    close = []
    for a, b in combinations(sorted(police.index), 2):
        distance = police.loc[a].geometry.distance(police.loc[b].geometry)
        assert abs(matrix.loc[a, b] - distance) < 1e-6
        if distance < 200:
            close.append((a, b))
    assert close == [('POL-02', 'POL-13')]
    pairs = pd.read_csv(OUT / 'PARES_POLICIA_MENOS_400M.csv')
    assert len(pairs) == 12 and pairs[pairs.DISTANCIA_M < 200].JUSTIFICACION.notna().all()
    assert not validation['nucleos99_abandonados'] and not validation['excepciones_mayor85']
    nucleus = pd.read_csv(OUT / 'CONTROL_NUCLEOS_GI_99.csv')
    assert not ((nucleus.ESTADO_ANTERIOR != 'SIN COBERTURA') & (nucleus.ESTADO_FINAL == 'SIN COBERTURA')).any()
    former_result = json.loads((PACKAGE.parent / 'RESULTADOS.json').read_text(encoding='utf-8'))
    for kind in ('incidents', 'hotspots', 'corridors', 'territorial', 'population'):
        assert [r for r in result[kind] if r['ESCENARIO'] != 'C'] == [r for r in former_result[kind] if r['ESCENARIO'] != 'C']
    controller = (ROOT / 'riobamba-camaras-propuesta.js').read_text(encoding='utf-8')
    assert OUT.name in controller and 'r.gapScenarioCValidated === false' in controller
    assert result['gapScenarioCValidated'] is False
    with zipfile.ZipFile(OUT / 'CIERRE_POLICIA_30_FINAL.zip') as archive:
        assert archive.testzip() is None
        for name in ('ESCENARIO_FINAL_183.gpkg', 'INFORME_FINAL.md', 'index.html',
                     'POLICIA_BENEFICIO_FINAL.csv', 'MATRIZ_DISTANCIAS_POLICIA_30.csv',
                     'AUDITORIA_REUBICACIONES_POLICIA.csv', 'VALIDACION.json'):
            assert name in archive.namelist()
    print('PASS: 103/50 y Gi* intactos; 8 reubicadas/22 congeladas; 183 equipos; '
          '30 beneficios exclusivos y distancias verificados; 0 solapes >85%; '
          '0 nucleos99 abandonados; 1 par <200 justificado; A/B intactos; ZIP valido.')


if __name__ == '__main__':
    main()
