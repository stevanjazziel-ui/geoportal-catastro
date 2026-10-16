"""Build the specifically authorized MUN-039 move; retain all other 182 geometries."""
import json
from pathlib import Path

import geopandas as gpd

import audit_municipal_street_reach as audit
import build_final_municipal_axis_release as builder
import finalize_axis_publication as finalize
import validate_final_municipal_axis_release as independent
from review_police_verified_main_roads import candidates_from_shared_vertices, normalized

ROOT = builder.ROOT
RELEASE_ID = 'MUN039_SANTA_MARTA_20261016'
OUT = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES' / RELEASE_ID
REVIEW = ROOT / 'data/seguridad-riobamba/REVISION_MUN039_SANTA_MARTA_20261016'
AUTHORIZATION = ('Mover MUN-039 a avenida 9 de Octubre x Santa Marta y publicar. '
                 'MUN-028, MUN-035, MUN-040 y MUN-046 se mantienen. '
                 'No se autoriza aplicar la reoptimizacion general de 400 m.')


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')


def main():
    assert not OUT.exists(), 'No se sobrescribe una version existente'
    active = json.loads((ROOT / 'sig-bridge-active.json').read_text(encoding='utf-8'))
    base = ROOT / active['root'] / 'ESCENARIO_FINAL_183.gpkg'
    read = lambda layer: gpd.read_file(base, layer=layer).to_crs(32717)
    original = read('PROPUESTA_MUNICIPAL_50_FINAL')
    target = original.loc[original.GRUPO.eq('RED_ESTRUCTURAL')].copy()
    roads = gpd.read_file(builder.ROADS).to_crs(32717)
    nodes = candidates_from_shared_vertices(roads, read('PLATAFORMAS_TERRITORIALES').geometry.union_all(), require_principal=False)
    matches = [c for c in nodes if {'avenida 9 de octubre', 'santa marta'} <= {normalized(n) for n in c['roads']}]
    assert len(matches) == 1, 'El cruce solicitado debe ser unico y verificable'
    chosen = matches[0]
    old = target.loc[target.ID_PROPUESTA.eq('MUN-039')].iloc[0]
    target.loc[target.ID_PROPUESTA.eq('MUN-039'), 'geometry'] = chosen['point']
    plan = json.loads((builder.REVIEW / 'RESULTADOS.json').read_text(encoding='utf-8'))
    approved = {r['ID_PROPUESTA']: r for r in plan['scenario']['movements']}
    movements = []
    for row in target.itertuples():
        previous = original.loc[original.ID_PROPUESTA.eq(row.ID_PROPUESTA)].iloc[0]
        item = dict(approved[row.ID_PROPUESTA])
        item.update(X_ANTES=previous.geometry.x, Y_ANTES=previous.geometry.y,
                    X_PROPUESTO=row.geometry.x, Y_PROPUESTO=row.geometry.y,
                    DESPLAZAMIENTO_M=previous.geometry.distance(row.geometry))
        if row.ID_PROPUESTA == 'MUN-039':
            item.update(ID_CANDIDATO='MUN-' + chosen['id'], CRUCE=' x '.join(chosen['roads']),
                        EJE_PRINCIPAL=' | '.join(chosen['principal']),
                        OSM_IDS=' | '.join(chosen['osmIds']), GRADO_NODO=chosen['degree'])
        movements.append(item)
    plan['scenario']['movements'] = movements
    REVIEW.mkdir(exist_ok=False)
    target.to_file(REVIEW / 'ESTUDIO_24_NODOS.gpkg', layer='EJES_PRIORITARIOS', driver='GPKG', index=False)
    fixed = [(r.ID_CAMARA, r.geometry, False) for r in read('CAMARAS_EXISTENTES_103_FINAL').itertuples()]
    fixed += [(r.ID_PROPUESTA, r.geometry, False) for r in original.loc[~original.GRUPO.eq('RED_ESTRUCTURAL')].itertuples()]
    fixed += [(r.ID_POLICIA, r.geometry, False) for r in read('PROPUESTA_POLICIA_30_FINAL').itertuples()]
    audit.OUT = REVIEW
    road_audit = audit.audit_scenario('EJES_PRIORITARIOS', target, fixed, audit.road_catalog(roads),
                                    {(c['point'].x, c['point'].y): c for c in nodes})
    plan['selectionLinkCount'] = road_audit['camerasWithPotentialSameAxisLink']
    plan['scenarios'] = [road_audit]
    plan['authorization'] = AUTHORIZATION
    save(REVIEW / 'RESULTADOS.json', plan)
    builder.REVIEW, builder.OUT, builder.RELEASE_ID, builder.AUTHORIZATION = REVIEW, OUT, RELEASE_ID, AUTHORIZATION
    builder.main()
    independent.OUT, independent.REVIEW, independent.PREVIOUS = OUT, REVIEW, base
    independent.main()
    after = gpd.read_file(OUT / 'ESCENARIO_FINAL_183.gpkg', layer='PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    changed = [r.ID_PROPUESTA for r in original.itertuples() if not r.geometry.equals(after.loc[r.ID_PROPUESTA].geometry)]
    assert changed == ['MUN-039'], changed
    # The dedicated request retains these cameras despite the pending global spacing audit.
    frozen_ids = ['MUN-028', 'MUN-035', 'MUN-040', 'MUN-046']
    for key in frozen_ids:
        assert after.loc[key].geometry.equals(original.set_index('ID_PROPUESTA').loc[key].geometry)
    nearest = min((chosen['point'].distance(p), key) for key, p, _ in fixed)
    all_other = [(r.ID_PROPUESTA, r.geometry) for r in original.itertuples() if r.ID_PROPUESTA != 'MUN-039']
    nearest = min([nearest] + [(chosen['point'].distance(p), key) for key, p in all_other])
    assert nearest[0] >= 400, 'El cruce solicitado introduce una proximidad menor a 400 m'
    proof = {'passed': True, 'changedIds': changed, 'fixed182Unchanged': True,
             'explicitlyRetained': frozen_ids, 'intersection': chosen['roads'], 'osmIds': chosen['osmIds'],
             'movementM': old.geometry.distance(chosen['point']), 'nearestOtherCamera': nearest[1],
             'nearestStraightDistanceM': nearest[0], 'crs': 'EPSG:32717',
             'global400mRevisionApplied': False,
             'note': 'Solo se aplica MUN-039. Los otros casos de proximidad siguen pendientes de revision.'}
    save(OUT / 'VALIDACION_TRASLADO_MUN039.json', proof)
    validation = json.loads((OUT / 'VALIDACION.json').read_text(encoding='utf-8'))
    validation.update(fixed182Unchanged=True, changedIds=changed, explicitRetainedMunicipal=frozen_ids)
    save(OUT / 'VALIDACION.json', validation)
    results = json.loads((OUT / 'RESULTADOS.json').read_text(encoding='utf-8'))
    results.update(status='MUN039_SANTA_MARTA_APROBADA', changedIds=changed, fixed182Unchanged=True,
                   global400mRevisionApplied=False, singleCameraMove=proof)
    results['bridge'] = validation
    save(OUT / 'RESULTADOS.json', results)
    (OUT / 'INFORME_FINAL.md').write_text(
        '# Traslado aprobado de MUN-039\n\n'
        'Solo cambia MUN-039: avenida 9 de Octubre x Santa Marta. Desplazamiento 143,59 m.\n\n'
        'Las otras 182 geometrías permanecen fijas, incluidas MUN-028, MUN-035, MUN-040 y MUN-046.\n\n'
        'Se recalculan coberturas potenciales de 100/150/200 m. Macají continúa al 100 %. '
        'No se modifica Gi*, KDE, corredores ni inventario original.\n\n'
        'No se ha aplicado una reoptimización general para separación de 400 m. Los demás casos detectados '
        'permanecen pendientes; no se afirma que toda la propuesta cumpla dicha separación.\n', encoding='utf-8')
    finalize.OUT, finalize.PREVIOUS, finalize.AUTHORIZATION = OUT, base, AUTHORIZATION
    finalize.main()
    print(json.dumps(proof, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
