"""Compare one slot against the published final29; never replace any official point."""
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pyogrio
from shapely import covers
from shapely.ops import unary_union

from audit_police_redundancy import Audit, CANDIDATES
from build_police_camera_proposal import ROOT, CLASSES, sha, geojson, coverage_class
from review_police_camera_efficiency import revision_rank

SOURCE = ROOT / 'data/seguridad-riobamba/CIERRE_POLICIA_30_FINAL_20261005'
PACKAGE = SOURCE / 'ESCENARIO_FINAL_183.gpkg'
OUT = ROOT / 'data/seguridad-riobamba/comparacion-pol20-20261005'


def main(slot='POL-20', source=SOURCE, destination=OUT):
    SOURCE, OUT = Path(source), Path(destination)
    PACKAGE = SOURCE / 'ESCENARIO_FINAL_183.gpkg'
    suffix = slot.replace('-', '')
    distance_field = 'DIST_DESDE_' + suffix + '_M'
    OUT.mkdir(parents=True, exist_ok=True)
    protected = {str(p): sha(p) for p in SOURCE.iterdir() if p.is_file()}
    protected[str(CANDIDATES)] = sha(CANDIDATES)
    for name in ('riobamba-camaras-propuesta.js', 'riobamba-cantonal-view.js',
                 'visor-seguridad-riobamba-v2.html'):
        protected[str(ROOT / name)] = sha(ROOT / name)
    audit = Audit(package=PACKAGE)
    other, reference = audit.reference(audit.active, slot)
    original = audit.active[slot]
    current_mask = unary_union([reference, original['disk']])
    before = audit.basic(original, other)
    official = audit.original_props[slot]
    assert (before['EVENTOS_D_NUEVOS'], before['EVENTOS_V_NUEVOS']) == (official['D_NUEVOS'], official['V_NUEVOS'])
    assert abs(before['SOLAPE_PREVIO_PCT'] - official['SOLAPE_PCT']) < 1e-6
    assert len(other) == 29
    current_dv = {i for i in original['events'] if i not in audit.evaluator.covered
                  and audit.events[i][1]['CATEGORIA'] in CLASSES[:2]}
    current_platforms = [g for g, _ in audit.platforms if g.covers(original['point'])]
    # These99 cells would lose their last coverage if this slot alone were removed.
    required99 = [(g, p, g.intersection(reference).area) for g, p in audit.context.hot if p['CATEGORIA'] in CLASSES[:2]
                  and p['NIVEL'] == 99
                  and coverage_class(g.intersection(current_mask).area / g.area) != 'SIN COBERTURA'
                  and coverage_class(g.intersection(reference).area / g.area) == 'SIN COBERTURA']
    eligible = []
    for candidate in audit.candidates.values():
        if candidate['id'] in audit.official_ids or candidate['scope'] != original['scope']:
            continue
        if min(candidate['distanceExisting'], candidate['distanceMunicipal']) <= 1e-5:
            continue
        row = audit.basic(candidate, other)
        if max(row['NIVEL_DEL_RESIDUAL'], row['NIVEL_VIOL_RESIDUAL']) < 90:
            continue
        lost99 = [p['AMBITO'] + ':' + p['CATEGORIA'] + ':' + p['CELL_ID']
                  for g, p, existing_area in required99
                  if coverage_class((existing_area + g.intersection(candidate['disk']).difference(reference).area) / g.area) == 'SIN COBERTURA']
        row.update({distance_field: candidate['point'].distance(original['point']),
                    'NUCLEOS99_ABANDONADOS': len(lost99), 'IDS_99_ABANDONADOS': '|'.join(lost99),
                    'DV_ACTUALES_CONSERVADOS': len(current_dv.intersection(candidate['events'])),
                    'MISMA_PLATAFORMA': any(g.covers(candidate['point']) for g in current_platforms)})
        row['MENOR_SOLAPE_SIN_REDUCIR_DV'] = (row['EVENTOS_D_NUEVOS'] >= before['EVENTOS_D_NUEVOS']
            and row['EVENTOS_V_NUEVOS'] >= before['EVENTOS_V_NUEVOS']
            and row['SOLAPE_PREVIO_PCT'] < before['SOLAPE_PREVIO_PCT']
            and max(row['NIVEL_DEL'], row['NIVEL_VIOL']) >= max(before['NIVEL_DEL'], before['NIVEL_VIOL'])
            and not lost99)
        row['PREFERIBLE'] = row['MENOR_SOLAPE_SIN_REDUCIR_DV'] and row['EVENTOS_DV_NUEVOS'] > before['EVENTOS_DV_NUEVOS']
        eligible.append(row)
    eligible.sort(key=lambda r: (r['PREFERIBLE'], revision_rank(r), r['ID_CANDIDATO']), reverse=True)
    assert len(eligible) >= 5
    selected = [dict(before, **{distance_field:0.}, NUCLEOS99_ABANDONADOS=0,
                     IDS_99_ABANDONADOS='', PREFERIBLE=False, MENOR_SOLAPE_SIN_REDUCIR_DV=False,
                     DV_ACTUALES_CONSERVADOS=len(current_dv), MISMA_PLATAFORMA=True)] + eligible[:5]
    local = sorted((r for r in eligible if r['MISMA_PLATAFORMA']),
        key=lambda r: (r['MENOR_SOLAPE_SIN_REDUCIR_DV'], r['DV_ACTUALES_CONSERVADOS'],
                       revision_rank(r), r['ID_CANDIDATO']), reverse=True)[:1]
    closest = sorted((r for r in eligible if r['MENOR_SOLAPE_SIN_REDUCIR_DV']),
                     key=lambda r: r[distance_field])[:1]
    additional = []
    local_label = 'LOCAL_' + official['PLATAFORMA'].replace(' ', '_')
    for label, rows in ((local_label, local), ('MEJORA_MAS_CERCANA', closest)):
        if rows:
            additional.append(dict(rows[0], OPCION_COMPLEMENTARIA=label))
    if slot != 'POL-20':
        preserving = [r for r in eligible if r['MENOR_SOLAPE_SIN_REDUCIR_DV']
                      and r['DV_ACTUALES_CONSERVADOS'] == len(current_dv)]
        for label, pool, key in (
                ('CERCANA_CONSERVA_EVENTOS', preserving, lambda r:r[distance_field]),
                ('MENOR_SOLAPE_LOCAL_CONSERVA_EVENTOS', [r for r in preserving if r['MISMA_PLATAFORMA']],
                 lambda r:(r['SOLAPE_PREVIO_PCT'], r[distance_field]))):
            if pool:
                additional.append(dict(min(pool,key=key), OPCION_COMPLEMENTARIA=label))
    selected += additional
    records = []
    for index, row in enumerate(selected):
        candidate = original if index == 0 else audit.candidates[row['ID_CANDIDATO']]
        detail, exclusive, overlap = audit.detail(candidate, other, row)
        mask = unary_union([reference, candidate['disk']])
        original_events = covers(current_mask, audit.event_points)
        candidate_events = covers(mask, audit.event_points)
        for category, label in zip(CLASSES, ('D', 'V', 'C')):
            valid = np.array([p['CATEGORIA'] == category and p['AMBITO'] != 'EXTERNO_CANTON'
                              for _, p in audit.events])
            detail['PERDIDOS_' + label] = int((original_events & ~candidate_events & valid).sum())
            detail['GANADOS_' + label] = int((~original_events & candidate_events & valid).sum())
            detail['TOTAL_CUBIERTO_' + label] = int((candidate_events & valid).sum())
        detail.update({'OPCION': row.get('OPCION_COMPLEMENTARIA', 'ACTUAL' if index == 0 else 'ALTERNATIVA_' + str(index)),
                       'ESTADO': 'COMPARACION_NO_INCORPORADA', 'RADIO_M': 200})
        assert abs(exclusive.area + overlap.area - candidate['disk'].area) < .01
        assert detail['EVENTOS_DV_NUEVOS'] == detail['EVENTOS_D_NUEVOS'] + detail['EVENTOS_V_NUEVOS']
        records.append((candidate['point'], detail))
    near_preferred = sorted((r for r in eligible if r['PREFERIBLE']), key=lambda r:r[distance_field])[:1]
    data = {'metadata': {'generatedAt': datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'),
        'reviewed': slot, 'officialModified': False, 'fixedPolice': 29, 'existing': 103, 'municipal': 50,
        'radio_m': 200, 'crs': 'EPSG:32717', 'giRecalculated': False, 'commit': False, 'push': False,
        'candidateCount': len(audit.candidates), 'significantResidualCandidates': len(eligible),
        'preferableCount': sum(r['PREFERIBLE'] for r in eligible),
        'context': f'103 existentes + 50 municipales finales + otras29 policiales finales; excluir solo {slot}.',
        'rules': 'Mas D+V exclusivos, sin reducir D o V individualmente; menor solape; remanente Gi* D o V >=90%; '
                 'mantener maximo nivel de entorno y no dejar sin cobertura nucleosD/V99 antes atendidos. '
                 'Sin corte de distancia ni optimizacion por corredores.',
        'sources': protected, 'package':str(PACKAGE), 'currentExclusiveDV':len(current_dv)}, 'comparison': [p for _, p in records[:6]],
        'complementary': [p for _,p in records[6:]], 'nearestPreferable': near_preferred}
    (OUT / 'RESULTADOS.json').write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
    fields = list(dict.fromkeys(k for _, p in records for k in p))
    with (OUT / ('COMPARACION_' + suffix + '.csv')).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows(p for _, p in records[:6])
    with (OUT / 'ALTERNATIVAS_LOCAL_Y_CERCANA.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows(p for _,p in records[6:])
    frame = gpd.GeoDataFrame([p for _, p in records[:6]], geometry=[g for g, _ in records[:6]], crs=32717)
    pyogrio.write_dataframe(frame, OUT / ('COMPARACION_' + suffix + '.gpkg'), layer='ACTUAL_Y_5_ALTERNATIVAS')
    if additional:
        extra = gpd.GeoDataFrame([p for _,p in records[6:]], geometry=[g for g,_ in records[6:]], crs=32717)
        pyogrio.write_dataframe(extra, OUT / ('COMPARACION_' + suffix + '.gpkg'), layer='ALTERNATIVAS_LOCAL_Y_CERCANA')
    (OUT / 'ACTUAL_Y_5_ALTERNATIVAS.geojson').write_text(json.dumps(geojson(records[:6]), ensure_ascii=False), encoding='utf-8')
    (OUT / 'ALTERNATIVAS_LOCAL_Y_CERCANA.geojson').write_text(json.dumps(geojson(records[6:]), ensure_ascii=False), encoding='utf-8')
    best = data['comparison'][1]
    lines = ['# Comparacion puntual de ' + slot, '',
        'La propuesta publicada NO se modifica. CRS EPSG:32717; radio200m. Gi* no recalculado.', '',
        'Referencia comun:103 existentes +50 municipales finales +lasotras29 policiales finales.',
        f'No se suman aportes individuales de alternativas; cada fila sustituye hipoteticamente solo {slot}.', '',
        '| Opcion | Candidato | Plataforma | D nuevos | V nuevos | D+V | Solape % | Area exclusiva m2 | Desplazamiento m | D/V anteriores conservados | Preferible |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|']
    for _, p in records[:6]:
        lines.append(f"| {p['OPCION']} | {p['ID_CANDIDATO']} | {p['PLATAFORMA']} | {p['EVENTOS_D_NUEVOS']} | {p['EVENTOS_V_NUEVOS']} | {p['EVENTOS_DV_NUEVOS']} | {p['SOLAPE_PREVIO_PCT']:.2f} | {p['AREA_EXCLUSIVA_M2']:.1f} | {p[distance_field]:.1f} | {p['DV_ACTUALES_CONSERVADOS']} | {'SI' if p['PREFERIBLE'] else 'NO'} |")
    lines += ['', '## Interpretacion',
        f"Se evaluaron {len(eligible)} nodos con remanente significativo D/V; {data['metadata']['preferableCount']} cumplen la comparacion de mejora.",
        f"La alternativa mejor situada en la comparacion es {best['ID_CANDIDATO']}; {'cumple' if best['PREFERIBLE'] else 'no cumple'} todas las condiciones de mejora.",
        'El ranking prioriza eventos D/V exclusivos; no necesariamente devuelve los nodos de menor solape absoluto ni los mas proximos al punto actual.',
        'Los nodos pueden estar en otra Plataforma. La distancia al punto actual se reporta sin imponer un radio arbitrario de busqueda.',
        'Gi* en el sitio y nivel maximo en el radio son campos distintos; una interseccion con D/V no es una nueva prueba estadistica conjunta.',
        'PERDIDOS_D/V/C y GANADOS_D/V/C muestran cambios de observaciones concretas: no se supone que mantener un conteo conserve exactamente los mismos eventos.',
        'Cada alternativa se compara contra los mismos29 puntos fijos. Consultar PERDIDOS_D/V y GANADOS_D/V para no confundir nuevos conteos con conservar las mismas observaciones.',
        'No se presupone mejora en todas las superficies: consultar AREA_HOTSPOT_D/V_NUEVA_M2 y sus valores actuales en elCSV antes de decidir.',
        'La poblacion asociada es una estimacion areal CPV2022 urbana, no poblacion rural completa.',
        'UPC y corredores son descriptivos, no criterios de seleccion. Ningun nodo se declara instalado ni validado en campo.',
        'Las coordenadas actuales y las otras29, fuentes y visor se verifican sin cambios por hash. Sin commit/push.']
    if near_preferred:
        n = near_preferred[0]
        lines += [f"La alternativa preferible mas cercana entre todos los nodos evaluados es {n['ID_CANDIDATO']}: {n[distance_field]:.1f}m; {n['EVENTOS_DV_NUEVOS']}D/V; solape {n['SOLAPE_PREVIO_PCT']:.2f}%. Conserva {n['DV_ACTUALES_CONSERVADOS']}/{len(current_dv)} eventos exclusivos anteriores. No se incorpora automaticamente."]
    lines += ['', '## Control local y mejora mas cercana',
        'Este control admite mantener el mismo numero de D/V si baja el solape; no se confunde con la regla estricta de aumentar D/V utilizada en el ranking principal.']
    for _, p in records[6:]:
        lines.append(f"- {p['OPCION']}: {p['ID_CANDIDATO']}, {p['PLATAFORMA']}, desplazamiento {p[distance_field]:.1f}m; D/V {p['EVENTOS_D_NUEVOS']}/{p['EVENTOS_V_NUEVOS']}, solape {p['SOLAPE_PREVIO_PCT']:.2f}%; conserva {p['DV_ACTUALES_CONSERVADOS']}/{len(current_dv)} eventos exclusivos actuales. Menor solape sin reducir D/V: {'SI' if p['MENOR_SOLAPE_SIN_REDUCIR_DV'] else 'NO'}. No incorporada.")
    (OUT / 'COMPARACION.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    assert all(sha(Path(p)) == h for p, h in protected.items())
    columns = ('OPCION', 'ID_CANDIDATO', 'PLATAFORMA', 'EVENTOS_D_NUEVOS', 'EVENTOS_V_NUEVOS',
               'SOLAPE_PREVIO_PCT', distance_field, 'PREFERIBLE', 'NUCLEOS99_ABANDONADOS', 'DV_ACTUALES_CONSERVADOS')
    print(json.dumps({'evaluados': len(eligible), 'preferibles': data['metadata']['preferableCount'],
        'opciones': [{k:p[k] for k in columns} for _,p in records],
        'preferible_mas_cercana': [{k:p[k] for k in columns if k in p} for p in near_preferred],
        'fuentes_intactas': True, 'oficial_modificado': False}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
