"""Independently validate the hypothetical options without modifying the published183."""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import covers
from shapely.ops import unary_union

from compare_pol20_final import OUT, PACKAGE, sha, coverage_class


def main(destination=OUT, package=PACKAGE, slot='POL-20'):
    OUT, PACKAGE = Path(destination), Path(package)
    suffix = slot.replace('-', '')
    result = json.loads((OUT / 'RESULTADOS.json').read_text(encoding='utf-8'))
    metadata = result['metadata']
    assert metadata['officialModified'] is False and metadata['fixedPolice'] == 29
    assert all(sha(Path(p)) == digest for p, digest in metadata['sources'].items())
    police = gpd.read_file(PACKAGE, layer='PROPUESTA_POLICIA_30_FINAL').set_index('ID_POLICIA')
    base = gpd.read_file(PACKAGE, layer='COBERTURA_B').geometry.iloc[0]
    reference = unary_union([base, *[g.buffer(200, quad_segs=64) for g in police.drop(index=slot).geometry]])
    current = unary_union([reference, police.loc[slot].geometry.buffer(200, quad_segs=64)])
    rows = gpd.read_file(OUT / ('COMPARACION_' + suffix + '.gpkg'), layer='ACTUAL_Y_5_ALTERNATIVAS')
    extra = gpd.read_file(OUT / ('COMPARACION_' + suffix + '.gpkg'), layer='ALTERNATIVAS_LOCAL_Y_CERCANA')
    assert len(rows) == 6 and len(extra) == len(result['complementary']) and rows.crs.to_epsg() == extra.crs.to_epsg() == 32717
    assert rows.geometry.iloc[0].equals_exact(police.loc[slot].geometry, 0)
    assert len(json.loads((OUT / 'ACTUAL_Y_5_ALTERNATIVAS.geojson').read_text(encoding='utf-8'))['features']) == 6
    assert len(pd.read_csv(OUT / ('COMPARACION_' + suffix + '.csv'))) == 6
    events = gpd.read_file(PACKAGE, layer='INCIDENTES_CLASIFICADOS')
    pts = events.geometry.to_numpy()
    previous_events, prior = covers(current, pts), covers(reference, pts)
    significant = []
    for category in ('DELINCUENCIA', 'VIOLENCIA'):
        hot = gpd.read_file(PACKAGE, layer='HOTSPOT_' + category)
        significant += [g for g in hot[hot.NIVEL == 99].geometry if coverage_class(g.intersection(current).area/g.area) != 'SIN COBERTURA']
    for row in pd.concat([rows, extra], ignore_index=True).itertuples():
        disk = row.geometry.buffer(200, quad_segs=64)
        mask = unary_union([reference, disk])
        assert abs(row.AREA_EXCLUSIVA_M2 - disk.difference(reference).area) < .01
        assert abs(row.SOLAPE_PREVIO_PCT - disk.intersection(reference).area/disk.area*100) < 1e-6
        candidate_events = covers(mask, pts)
        for category, label in (('DELINCUENCIA', 'D'), ('VIOLENCIA', 'V'), ('CONVIVENCIA', 'C')):
            valid = (events.CATEGORIA.eq(category) & events.AMBITO.ne('EXTERNO_CANTON')).to_numpy()
            total = int((candidate_events & valid).sum())
            new = int((covers(disk, pts) & ~prior & valid).sum())
            assert getattr(row, 'EVENTOS_' + label + '_NUEVOS') == new
            assert getattr(row, 'TOTAL_CUBIERTO_' + label) == total
            gained = int((~previous_events & candidate_events & valid).sum())
            lost = int((previous_events & ~candidate_events & valid).sum())
            assert getattr(row, 'GANADOS_' + label) == gained and getattr(row, 'PERDIDOS_' + label) == lost
        abandoned = sum(coverage_class(g.intersection(mask).area/g.area) == 'SIN COBERTURA' for g in significant)
        assert abandoned == row.NUCLEOS99_ABANDONADOS
        assert abs(min(police.drop(index=slot).geometry.distance(row.geometry)) - row.DIST_POLICIA_M) < 1e-6
        assert abs(row.geometry.distance(police.loc[slot].geometry) - getattr(row,'DIST_DESDE_' + suffix + '_M')) < 1e-6
        if row.OPCION == 'MEJORA_MAS_CERCANA' and slot == 'POL-20':
            assert row.EVENTOS_DV_NUEVOS == row.DV_ACTUALES_CONSERVADOS == 10
            assert abs(row.DIST_DESDE_POL20_M - 29.249479487307127) < 1e-6
        if row.OPCION == 'ACTUAL' and slot == 'POL-20':
            assert (row.TOTAL_CUBIERTO_D, row.TOTAL_CUBIERTO_V, row.TOTAL_CUBIERTO_C) == (1783, 989, 4999)
        if row.OPCION.endswith('CONSERVA_EVENTOS'):
            exclusive_before = previous_events & ~prior & events.CATEGORIA.isin(['DELINCUENCIA','VIOLENCIA']).to_numpy()
            assert int((exclusive_before & candidate_events).sum()) == row.DV_ACTUALES_CONSERVADOS == metadata['currentExclusiveDV']
            assert row.NUCLEOS99_ABANDONADOS == 0
    print('PASS: ' + slot + ' actual +5 alternativas y controles locales; CRS y radios200m; '
          'areas/solapes y D/V/C verificados; conteos de ganancias/perdidas correctos; '
          'Gi99 no abandonados; fuentes y otras29 intactas. Sin commit/push.')


if __name__ == '__main__':
    main()
