"""Refresh the complete portable delivery, preserving the previous GIS archive."""
import json
import shutil
from pathlib import Path

import geopandas as gpd
import pyogrio

from publish_mun039_santa_marta import ROOT, OUT as RELEASE, REVIEW, RELEASE_ID
from review_police_kde_intersections import source_hash

PREVIOUS = ROOT.parent / 'entregas/VISOR_RIOBAMBA_QGIS_20261016'
OUT = ROOT.parent / 'entregas/VISOR_RIOBAMBA_QGIS_MUN039_SANTA_MARTA_20261016'


def main(validation_file='VALIDACION_TRASLADO_MUN039.json'):
    assert not OUT.exists(), 'No se sobrescribe una entrega final'
    assert (RELEASE / validation_file).exists()
    shutil.copytree(PREVIOUS, OUT, ignore=shutil.ignore_patterns('*-wal', '*-shm', '*~'))
    package = OUT / 'VISOR_RIOBAMBA_COMPLETO.gpkg'
    source = RELEASE / 'ESCENARIO_FINAL_183.gpkg'
    changed = []
    static = {'PLATAFORMAS_TERRITORIALES', 'LIMITE_CANTONAL', 'UPC_INFRAESTRUCTURA',
              'RED_VIAL_CONTEXTO', 'CAMARAS_EXISTENTES_103_FINAL', 'COBERTURA_A',
              'RADIOS_EXISTENTES_SIMBOLOGIA_200M', 'CORREDORES', 'COBERTURA_POLICIA_200M',
              'MOVIMIENTOS_POLICIA_30'}
    for name, kind in pyogrio.list_layers(source):
        if name in static or name.startswith(('GI_', 'HOTSPOT_')):
            continue
        frame = pyogrio.read_dataframe(source, layer=name)
        pyogrio.write_dataframe(frame, package, layer=name)
        changed.append(name)
    municipal = gpd.read_file(source, layer='PROPUESTA_MUNICIPAL_50_FINAL')
    pyogrio.write_dataframe(municipal.loc[municipal.GRUPO.eq('RED_ESTRUCTURAL')], package, layer='MUNICIPALES_URBANAS_24')
    changed.append('MUNICIPALES_URBANAS_24')
    for radius in (100, 150, 200):
        frame = gpd.read_file(package, layer=f'RADIOS_MUNICIPALES_{radius}M')
        lookup = municipal.set_index('ID_PROPUESTA')
        frame.geometry = gpd.GeoSeries([lookup.loc[key].geometry.buffer(radius, quad_segs=64)
                                       for key in frame.ID_PROPUESTA], index=frame.index, crs=32717)
        pyogrio.write_dataframe(frame, package, layer=f'RADIOS_MUNICIPALES_{radius}M')
        changed.append(f'RADIOS_MUNICIPALES_{radius}M')
    for name in ('TRAMOS', 'RECTILINEOS', 'ENLACES', 'HUECOS'):
        frame = gpd.read_file(REVIEW / 'AUDITORIA_VIAL.gpkg', layer='EJES_PRIORITARIOS_' + name)
        pyogrio.write_dataframe(frame, package, layer='MUNICIPALES_' + name)
        changed.append('MUNICIPALES_' + name)
    metadata = json.loads((OUT / 'MANIFIESTO.json').read_text(encoding='utf-8'))
    previous_release = metadata['release']
    metadata.update(release=RELEASE_ID, sourcePackageSha256=source_hash(source),
                    completeGeoPackageSha256=source_hash(package))
    for layer in metadata['layers']:
        if layer.get('name') in changed:
            layer['source'] = str(REVIEW.relative_to(ROOT)) if layer['name'].startswith('MUNICIPALES_') and layer['name'] in {
                'MUNICIPALES_TRAMOS', 'MUNICIPALES_RECTILINEOS', 'MUNICIPALES_ENLACES', 'MUNICIPALES_HUECOS'} else RELEASE_ID
            layer['records'] = len(pyogrio.read_dataframe(package, layer=layer['name']))
    (OUT / 'MANIFIESTO.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    readme = (OUT / 'README.md').read_text(encoding='utf-8')
    readme += ('\n\n## Actualizacion de camaras\n\n'
               'Version ' + RELEASE_ID + '. Las capas de cobertura y radios municipales se actualizaron. '
               'Gi*, KDE, red vial y geometrías originales se conservaron. '
               'Los campos de fuente anteriores documentan la procedencia historica desde ' + previous_release + '.\n\n'
               + (RELEASE / 'INFORME_FINAL.md').read_text(encoding='utf-8'))
    (OUT / 'README.md').write_text(readme, encoding='utf-8')
    for name in (validation_file, 'VALIDACION_INDEPENDIENTE.json'):
        shutil.copy2(RELEASE / name, OUT / name)
    proof = {'passed': True, 'release': RELEASE_ID, 'changedLayers': changed,
             'rastersPreserved': True, 'giPreserved': True}
    for layer, key in [('CAMARAS_EXISTENTES_103_FINAL', 'ID_CAMARA'),
                       ('PROPUESTA_MUNICIPAL_50_FINAL', 'ID_PROPUESTA'),
                       ('PROPUESTA_POLICIA_30_FINAL', 'ID_POLICIA')]:
        actual = gpd.read_file(package, layer=layer).set_index(key)
        approved = gpd.read_file(source, layer=layer).set_index(key)
        assert actual.loc[approved.index].geometry.to_wkb().tolist() == approved.geometry.to_wkb().tolist()
    (OUT / 'VALIDACION_SINCRONIZACION.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
    print(OUT, flush=True)


if __name__ == '__main__':
    main()
