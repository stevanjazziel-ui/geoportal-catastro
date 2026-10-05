"""Validate the exported audit, independently from candidate ranking."""
import csv
import json
import zipfile
from collections import Counter
from pathlib import Path

import geopandas as gpd
from shapely.ops import unary_union

from audit_police_redundancy import OUT, PACKAGE, redundancy, sha


def main():
    data = json.loads((OUT / 'RESULTADOS.json').read_text(encoding='utf-8'))
    assert data['metadata']['radio_m'] == 200
    assert data['metadata']['oficial_modificado'] is False
    assert all(sha(Path(p)) == h for p, h in data['metadata']['fuentes_hash'].items())
    assert [redundancy(v) for v in (0, 49.99, 50, 70, 70.01, 85, 85.01, 100)] == [
        'BAJA', 'BAJA', 'MEDIA', 'MEDIA', 'ALTA', 'ALTA', 'MUY ALTA', 'MUY ALTA']
    counts = Counter(r['ID_POL_REVISADA'] for r in data['alternativas'])
    assert all(n == 6 for n in counts.values())
    assert len(counts) == sum(r['REVISAR'] for r in data['actual'])
    assert all(len([r for r in data['plataformaJ_cercanas'] if r['ID_POL_J'] == id]) == 5
               for id in {r['ID_POL_J'] for r in data['plataformaJ_cercanas']})
    package = OUT / 'REDUNDANCIA_POLICIA_30.gpkg'
    official = gpd.read_file(PACKAGE, layer='PROPUESTA_POLICIA_30_FINAL').set_index('ID_POLICIA')
    for mode, key in [('ACTUAL', 'actual'), ('PRUEBA', 'prueba')]:
        points = gpd.read_file(package, layer='POLICIA_' + mode).set_index('ID_POL')
        disks = gpd.read_file(package, layer='BUFFER_' + mode).set_index('ID_POL')
        exclusive = gpd.read_file(package, layer='EXCLUSIVA_' + mode).set_index('ID_POL')
        overlapping = gpd.read_file(package, layer='SUPERPUESTA_' + mode).set_index('ID_POL')
        assert len(points) == len(disks) == 30 and points.crs.to_epsg() == 32717
        assert points.geometry.is_valid.all() and points.geometry.notna().all()
        assert len({g.wkb for g in points.geometry}) == 30
        for row in data[key]:
            id = row['ID_POL']
            if mode == 'ACTUAL' or row['DECISION'] == 'MANTENER':
                assert points.loc[id].geometry.equals(official.loc[id].geometry)
            else:
                assert not points.loc[id].geometry.equals(official.loc[id].geometry)
            disk, ex, ov = disks.loc[id].geometry, exclusive.loc[id].geometry, overlapping.loc[id].geometry
            assert disk.symmetric_difference(unary_union([ex, ov])).area < .01
            assert ex.intersection(ov).area < .01
            assert abs(disk.area - row['AREA_BUFFER_M2']) < .01
            assert row['REDUNDANCIA'] == redundancy(row['SOLAPE_PREVIO_PCT'])
        with (OUT / ('AUDITORIA_30_POLICIA.csv' if mode == 'ACTUAL' else 'ESCENARIO_PRUEBA_30.csv')).open(encoding='utf-8-sig') as f:
            assert len(list(csv.DictReader(f))) == 30
    for decision in data['decisiones']:
        if decision['ITERACION'] is None:
            continue
        options = [r for r in data['alternativas'] if r['ID_POL_REVISADA'] == decision['ID_POL']]
        before = next(r for r in options if r['TIPO_OPCION'] == 'ACTUAL')
        winner = next(r for r in options if r['SELECCIONADA_PRUEBA'])
        if decision['DECISION'] == 'REUBICAR':
            assert winner['PREFERIBLE']
            assert max(winner['NIVEL_DEL_RESIDUAL'], winner['NIVEL_VIOL_RESIDUAL']) >= 90
            assert max(winner['NIVEL_DEL'], winner['NIVEL_VIOL']) >= max(before['NIVEL_DEL'], before['NIVEL_VIOL'])
            assert winner['EVENTOS_D_NUEVOS'] >= before['EVENTOS_D_NUEVOS']
            assert winner['EVENTOS_V_NUEVOS'] >= before['EVENTOS_V_NUEVOS']
            assert winner['EVENTOS_DV_NUEVOS'] > before['EVENTOS_DV_NUEVOS']
            assert winner['SOLAPE_PREVIO_PCT'] < before['SOLAPE_PREVIO_PCT']
    with zipfile.ZipFile(OUT / 'REVISION_REDUNDANCIA_POLICIA_30.zip') as archive:
        assert archive.testzip() is None
        assert {'README.md', 'RESULTADOS.json', 'index.html', 'REDUNDANCIA_POLICIA_30.gpkg'} <= set(archive.namelist())
    print('OK: fuentes intactas; 30+30 puntos; geometria actual preservada; areas exclusivas/solapadas; 5 alternativas por revision; CSV y ZIP; decisiones por beneficio, no distancia.')


if __name__ == '__main__':
    main()
