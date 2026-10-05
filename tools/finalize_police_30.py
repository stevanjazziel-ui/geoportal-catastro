"""Close the approved eight relocations; freeze the other22 and all original GIS inputs."""
import csv
import json
import shutil
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely import STRtree, covers, prepare
from shapely.geometry import LineString
from shapely.ops import unary_union

from build_police_camera_proposal import (
    ROOT, CLASSES, AREA_EPS, Context, records, read_layer, geojson, sha, pct,
    parts, coverage_class, dv_coincidences, scenario_evaluation, UNPROJECT,
)
from review_police_camera_efficiency import Evaluator
from audit_police_redundancy import redundancy

BASE = ROOT / 'data/seguridad-riobamba'
SOURCE = BASE / 'CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA'
PACKAGE = SOURCE / 'CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.gpkg'
REVIEW = BASE / 'redundancia-policia-30-20261005'
OUT = BASE / 'CIERRE_POLICIA_30_FINAL_20261005'
FINAL_PACKAGE = OUT / 'ESCENARIO_FINAL_183.gpkg'
RELOCATED = {'POL-06', 'POL-07', 'POL-14', 'POL-15', 'POL-16', 'POL-17', 'POL-18', 'POL-19'}


def save_json(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')


def save_csv(name, rows):
    fields = list(dict.fromkeys(k for p in rows for k in p))
    with (OUT / (name + '.csv')).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader()
        writer.writerows(rows)


def export(name, rows, visual=True):
    if rows:
        frame = gpd.GeoDataFrame([p for _, p in rows], geometry=[g for g, _ in rows], crs=32717)
    else:
        frame = gpd.GeoDataFrame({'ID': pd.Series(dtype='str')}, geometry=[], crs=32717)
    pyogrio.write_dataframe(frame, FINAL_PACKAGE, layer=name)
    if visual:
        save_json(name + '.geojson', geojson(rows))
    return {'name': name, 'records': len(rows), 'crs': 'EPSG:32717', 'fields': list(frame.columns)}


def table(name, rows):
    save_csv(name, rows)
    pyogrio.write_dataframe(pd.DataFrame(rows), FINAL_PACKAGE, layer=name)


def population_metrics(blocks, urban, coverage):
    valid = [(g, p) for g, p in blocks if p['POBLACION'] is not None and g.intersection(urban).area > AREA_EPS]
    total = sum(p['POBLACION'] * g.intersection(urban).area / g.area for g, p in valid)
    covered = sum(p['POBLACION'] * g.intersection(urban).intersection(coverage).area / g.area for g, p in valid)
    return {'ESCENARIO': 'C', 'POBLACION_ANALIZADA': total, 'POBLACION_CUBIERTA': covered,
        'POBLACION_NO_CUBIERTA': total-covered, 'PCT_CUBIERTO': pct(covered, total),
        'MANZANAS_VALIDAS': len(valid),
        'MANZANAS_SIN_POBLACION': sum(p['POBLACION'] is None and g.intersection(urban).area > AREA_EPS for g, p in blocks),
        'AMBITO': '18 Plataformas; estimacion areal CPV2022, poblacion rural No disponible'}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    def source(name):
        return records(read_layer(PACKAGE, name))
    protected_paths = [p for p in SOURCE.rglob('*') if p.is_file() and p.suffix.lower() not in ('.log', '.lock', '.lck')]
    protected_paths += [REVIEW / 'RESULTADOS.json', REVIEW / 'REDUNDANCIA_POLICIA_30.gpkg']
    protected_paths += list(ROOT.glob('*data.js'))
    protected = {str(p): sha(p) for p in protected_paths}
    approved = json.loads((REVIEW / 'RESULTADOS.json').read_text(encoding='utf-8'))
    prior = json.loads((SOURCE / 'RESULTADOS.json').read_text(encoding='utf-8'))
    assert {r['ID_POL'] for r in approved['decisiones'] if r['DECISION'] == 'REUBICAR'} == RELOCATED
    existing, municipal, original = (source(n) for n in (
        'CAMARAS_EXISTENTES_103_FINAL', 'PROPUESTA_MUNICIPAL_50_FINAL', 'PROPUESTA_POLICIA_30_FINAL'))
    proposed = records(read_layer(REVIEW / 'REDUNDANCIA_POLICIA_30.gpkg', 'POLICIA_PRUEBA'))
    old = {p['ID_POLICIA']: (g, p) for g, p in original}
    rows_review = {p['ID_POL']: p for _, p in proposed}
    existing_points, municipal_points = [g for g, _ in existing], [g for g, _ in municipal]
    events, blocks, infrastructure = (source(n) for n in ('INCIDENTES_CLASIFICADOS', 'MANZANAS_COBERTURA', 'UPC_INFRAESTRUCTURA'))
    platforms = source('PLATAFORMAS_TERRITORIALES')
    canton = unary_union([g for g, _ in source('LIMITE_CANTONAL')])
    urban = unary_union([g for g, _ in platforms])
    corridor_rows = source('CORREDORES')
    axes = {p['CORREDOR']: g for g, p in corridor_rows}
    statistics = {(scope, cat): source('GI_' + scope + '_' + cat)
                  for scope in ('URBANO', 'RURAL') for cat in CLASSES}
    hot = [(g, p) for rows in statistics.values() for g, p in rows if p['GI_CLASS'].startswith('HOTSPOT')]
    baseline = read_layer(PACKAGE, 'COBERTURA_B').geometry.iloc[0]
    original_coverage = read_layer(PACKAGE, 'COBERTURA_C').geometry.iloc[0]
    context = Context(events, hot, dv_coincidences(statistics), baseline, existing_points,
                      municipal_points, infrastructure, blocks, urban, axes)
    candidates = {}
    for g, p in proposed:
        id = p['ID_POL']
        assert g.equals(old[id][0]) == (id not in RELOCATED)
        assert p['ID_CANDIDATO'] == next(d['CANDIDATO_PROPUESTO'] for d in approved['decisiones'] if d['ID_POL'] == id)
        c = context.candidate({'point': g, 'id': p['ID_CANDIDATO'], 'degree': p['GRADO_NODO'],
                               'props': dict(p), 'origins': set(p['INTERSECCION_O_NODO'].split('|'))})
        candidates[id] = c
    assert len(candidates) == 30
    evaluator = Evaluator(context)
    event_points = np.array([g for g, _ in events], dtype=object)
    police, metrics, exclusive_rows, overlap_rows, audits = [], [], [], [], []
    for id, c in sorted(candidates.items()):
        other = [v for key, v in candidates.items() if key != id]
        reference = unary_union([baseline] + [v['disk'] for v in other])
        evaluator.coverage = reference
        prepare(reference)
        evaluator.covered = set(np.flatnonzero(covers(reference, event_points)).tolist())
        evaluator.uncovered = [g.difference(reference) for g, _ in hot]
        evaluator.dv_uncovered = [g.difference(reference) for g, _ in context.dv]
        margin = evaluator.evaluate(c, [v['point'] for v in other])
        descriptive = context.description(c)
        previous = rows_review[id]
        exclusive, overlap = c['disk'].difference(reference), c['disk'].intersection(reference)
        assert abs(exclusive.area + overlap.area - c['disk'].area) < .01
        assert abs(margin['SOLAPE_PREVIO_PCT'] - previous['SOLAPE_PREVIO_PCT']) < 1e-6
        assert margin['EVENTOS_DV_NUEVOS'] == previous['EVENTOS_DV_NUEVOS']
        population, valid, missing = context.population(exclusive)
        reason = (f"Reubicacion aprobada desde {old[id][1]['ID_CANDIDATO']} a {c['id']}; "
                  f"conjunto final: {margin['EVENTOS_D_NUEVOS']} D + {margin['EVENTOS_V_NUEVOS']} V exclusivos, "
                  f"solape {margin['SOLAPE_PREVIO_PCT']:.2f}%. Hot Spot residual D/V "
                  f"{margin['NIVEL_DEL_RESIDUAL']}%/{margin['NIVEL_VIOL_RESIDUAL']}%; nodo vial de grado {c['degree']}."
                  if id in RELOCATED else
                  f"Mantener la ubicacion aprobada; {margin['EVENTOS_D_NUEVOS']} D + {margin['EVENTOS_V_NUEVOS']} V exclusivos; "
                  f"solape final {margin['SOLAPE_PREVIO_PCT']:.2f}%. No se cambia por proximidad.")
        if margin['SOLAPE_PREVIO_PCT'] > 70:
            reason += (f" Aceptacion justificada de solape 70-85%: Hot Spots en el entorno D/V "
                       f"{descriptive['NIVEL_DEL']}%/{descriptive['NIVEL_VIOL']}%; "
                       f"area Hot Spot D/V adicional {margin['AREA_HOTSPOT_D_NUEVA_M2']:.1f}/"
                       f"{margin['AREA_HOTSPOT_V_NUEVA_M2']:.1f} m2 y aporte exclusivo D/V positivo. "
                       "No hay duplicacion geometrica total ni solape >85%.")
        reason += ' Configuracion final del estudio; propuesta no instalada, pendiente verificacion operativa de campo.'
        lon, lat = UNPROJECT(c['point'].x, c['point'].y)
        props = {**previous, **margin, **descriptive, 'ID_POLICIA': id,
            'X': c['point'].x, 'Y': c['point'].y, 'LONGITUD': lon, 'LATITUD': lat,
            'ESTADO': 'PROPUESTA_FINAL_ESTUDIO_NO_INSTALADA', 'PROPUESTA_FINAL': True,
            'DECISION_FINAL': 'REUBICAR' if id in RELOCATED else 'MANTENER', 'JUSTIFICACION': reason,
            'SOLAPE_PCT': margin['SOLAPE_PREVIO_PCT'], 'AREA_BUFFER_M2': c['disk'].area,
            'AREA_SOLAPADA_M2': overlap.area, 'AREA_EXCLUSIVA_M2': exclusive.area,
            'D_NUEVOS': margin['EVENTOS_D_NUEVOS'], 'V_NUEVOS': margin['EVENTOS_V_NUEVOS'],
            'DV_NUEVOS': margin['EVENTOS_DV_NUEVOS'],
            'HOTSPOT_D': descriptive['HOTSPOT_DEL'], 'HOTSPOT_V': descriptive['HOTSPOT_VIOL'],
            'NIVEL_GI': f"Sitio D: {previous['GI_D_CLASE_SITIO'] or 'No disponible'}; V: {previous['GI_V_CLASE_SITIO'] or 'No disponible'}",
            'NIVEL_GI_ENTORNO_200M': max(descriptive['NIVEL_DEL'], descriptive['NIVEL_VIOL']),
            'REDUNDANCIA': redundancy(margin['SOLAPE_PREVIO_PCT']),
            'POBLACION_ADICIONAL_ESTIMADA': population,
            'MANZANAS_ADICIONALES_VALIDAS': valid, 'MANZANAS_ADICIONALES_SIN_POBLACION': missing,
            'BENEFICIO_CONTEXTO': 'Contra103+50+otras29; no sumar aportes individuales'}
        police.append((c['point'], props))
        metrics.append(props)
        exclusive_rows.append((exclusive, {'ID_POLICIA': id, 'AREA_M2': exclusive.area}))
        overlap_rows.append((overlap, {'ID_POLICIA': id, 'AREA_M2': overlap.area}))
        audits.append({'ID_POLICIA': id, 'DECISION': props['DECISION_FINAL'],
            'CANDIDATO_ANTERIOR': old[id][1]['ID_CANDIDATO'], 'CANDIDATO_FINAL': c['id'],
            'X_ANTERIOR': old[id][0].x, 'Y_ANTERIOR': old[id][0].y,
            'X_FINAL': c['point'].x, 'Y_FINAL': c['point'].y,
            'DESPLAZAMIENTO_M': old[id][0].distance(c['point']),
            'DV_ANTERIOR': next(r['EVENTOS_DV_NUEVOS'] for r in approved['actual'] if r['ID_POL'] == id),
            'DV_FINAL': margin['EVENTOS_DV_NUEVOS'],
            'SOLAPE_ANTERIOR': next(r['SOLAPE_PREVIO_PCT'] for r in approved['actual'] if r['ID_POL'] == id),
            'SOLAPE_FINAL': margin['SOLAPE_PREVIO_PCT'], 'JUSTIFICACION': reason})
    police_mask = unary_union([c['disk'] for c in candidates.values()])
    final_mask = unary_union([baseline, police_mask])
    ordered = sorted(candidates)
    distance_rows, matrix = [], []
    metrics_by_id = {p['ID_POLICIA']: p for p in metrics}
    for id in ordered:
        matrix.append({'ID_POLICIA': id, **{other: candidates[id]['point'].distance(candidates[other]['point']) for other in ordered}})
    for i, a in enumerate(ordered):
        for b in ordered[i+1:]:
            distance = candidates[a]['point'].distance(candidates[b]['point'])
            if distance >= 400:
                continue
            band = '<100 m' if distance < 100 else '100-200 m' if distance < 200 else '200-300 m' if distance < 300 else '300-400 m'
            pa, pb = metrics_by_id[a], metrics_by_id[b]
            overlap = candidates[a]['disk'].intersection(candidates[b]['disk']).area
            reason = 'Distancia descriptiva; no se impone una separacion minima.'
            if distance < 200:
                assert min(pa['DV_NUEVOS'], pb['DV_NUEVOS']) > 0
                assert min(pa['NIVEL_GI_ENTORNO_200M'], pb['NIVEL_GI_ENTORNO_200M']) >= 90
                reason = (f"Ambas necesarias por aportes independientes: {a} suma {pa['D_NUEVOS']} D/{pa['V_NUEVOS']} V "
                          f"y {b} {pb['D_NUEVOS']} D/{pb['V_NUEVOS']} V contra el resto del escenario183. "
                          f"Entornos Gi* D/V {pa['NIVEL_DEL']}%/{pa['NIVEL_VIOL']}% y {pb['NIVEL_DEL']}%/{pb['NIVEL_VIOL']}%; "
                          f"nodos viales distintos de grados {pa['GRADO_NODO']}/{pb['GRADO_NODO']}. "
                          f"Solapes globales {pa['SOLAPE_PCT']:.2f}%/{pb['SOLAPE_PCT']:.2f}%, no extremos. "
                          "No se inventa un equipamiento critico ni se impone distancia minima.")
            distance_rows.append({'ID_A': a, 'ID_B': b, 'DISTANCIA_M': distance, 'BANDA': band,
                'ALGUNA_REUBICADA': bool({a,b} & RELOCATED), 'AREA_SOLAPE_MUTUO_M2': overlap,
                'SOLAPE_MUTUO_BUFFER_PCT': pct(overlap, candidates[a]['disk'].area),
                'DV_A_EXCLUSIVOS': pa['DV_NUEVOS'], 'DV_B_EXCLUSIVOS': pb['DV_NUEVOS'], 'JUSTIFICACION': reason})
    nucleus, lost_complete = [], []
    for g, p in hot:
        if p['CATEGORIA'] not in CLASSES[:2]:
            continue
        before, after = g.intersection(original_coverage).area/g.area, g.intersection(final_mask).area/g.area
        row = {'CELL_ID': p['CELL_ID'], 'AMBITO': p['AMBITO'], 'CATEGORIA': p['CATEGORIA'], 'NIVEL': p['NIVEL'],
               'COB_ANTERIOR_PCT': 100*before, 'COB_FINAL_PCT': 100*after,
               'ESTADO_ANTERIOR': coverage_class(before), 'ESTADO_FINAL': coverage_class(after)}
        if p['NIVEL'] == 99:
            nucleus.append(row)
        if coverage_class(before) == 'CUBIERTO' and coverage_class(after) != 'CUBIERTO':
            lost_complete.append(row)
    abandoned99 = [r for r in nucleus if r['ESTADO_ANTERIOR'] != 'SIN COBERTURA' and r['ESTADO_FINAL'] == 'SIN COBERTURA']
    assert not abandoned99, 'Nucleo99 abandonado: evaluar las alternativas auditadas, sin regenerar las30.'
    assert not any(p['SOLAPE_PCT'] > 85 for p in metrics)
    assert all(metrics_by_id[id]['DV_NUEVOS'] > 0 for id in RELOCATED)
    assert not any(r['DISTANCIA_M'] < 200 and r['ALGUNA_REUBICADA'] for r in distance_rows)
    assert len(existing) == 103 and len(municipal) == 50 and len(police) == 30
    assert sum(p['REQUIERE_CAMBIO'] is True for _, p in existing) == 31
    assert len({g.wkb for g, _ in police}) == 30
    print('CONTROL_30', {'reubicadas':8, 'mantenidas':22, 'maxSolape':max(p['SOLAPE_PCT'] for p in metrics),
                         'nucleos99Abandonados':len(abandoned99), 'paresMenos200':sum(r['DISTANCIA_M']<200 for r in distance_rows)}, flush=True)
    incidents, hot_stats, corridor_stats, updated, _, _ = scenario_evaluation(context, statistics, context.dv, {'C': final_mask})
    territorial = {'ESCENARIO': 'C', 'AREA_TOTAL_URBANA_KM2': urban.area/1e6,
        'AREA_CUBIERTA_URBANA_KM2': final_mask.intersection(urban).area/1e6,
        'PCT_URBANO': pct(final_mask.intersection(urban).area, urban.area),
        'AREA_TOTAL_CANTON_KM2': canton.area/1e6, 'AREA_CUBIERTA_CANTON_KM2': final_mask.intersection(canton).area/1e6,
        'PCT_CANTON': pct(final_mask.intersection(canton).area, canton.area), 'BUFFER_DISUELTO_KM2': final_mask.area/1e6}
    population = population_metrics(blocks, urban, final_mask)
    merged = dict(prior)
    for kind, updated_rows in [('incidents', incidents), ('hotspots', hot_stats), ('corridors', corridor_stats),
                               ('territorial', [territorial]), ('population', [population])]:
        merged[kind] = [r for r in prior[kind] if r['ESCENARIO'] != 'C'] + updated_rows
    gi_fields = ['CELL_ID','AMBITO','CATEGORIA','PLATAFORMA','PARROQUIA','DISTANCE_M','CELL_SIZE_M',
                 'COUNT','GI_ZSCORE','GI_PVALUE','GI_CLASS','GI_STAR','SIGNIFICANCIA','SUMA_LOCAL','NIVEL']
    for key, rows in updated.items():
        for (ga, pa), (gb, pb) in zip(statistics[key], rows):
            assert ga.equals_exact(gb,0) and all(pa.get(k) == pb.get(k) for k in gi_fields)
    old_c = approved['escenarios']['103+50+30_OFICIAL']
    new_c = approved['escenarios']['103+50+30_PRUEBA']
    for cat in CLASSES:
        real = next(r for r in incidents if r['AMBITO']=='CANTONAL' and r['CATEGORIA']==cat)
        assert real['CUBIERTOS'] == new_c['incidentes'][cat]['cubiertos']
    comparison = []
    for cat in CLASSES:
        a, b = old_c['incidentes'][cat], new_c['incidentes'][cat]
        comparison.append({'INDICADOR': cat+' cubiertos', 'ANTERIOR': a['cubiertos'], 'FINAL': b['cubiertos'],
                           'PCT_ANTERIOR': a['porcentaje'], 'PCT_FINAL': b['porcentaje'], 'DIFERENCIA': b['cubiertos']-a['cubiertos']})
    da = sum(old_c['incidentes'][k]['cubiertos'] for k in CLASSES[:2])
    db = sum(new_c['incidentes'][k]['cubiertos'] for k in CLASSES[:2])
    comparison.append({'INDICADOR': 'D+V cubiertos', 'ANTERIOR': da, 'FINAL': db, 'DIFERENCIA': db-da})
    for category in CLASSES[:2]:
        a, b = old_c['hotspots']['URBANO_' + category], new_c['hotspots']['URBANO_' + category]
        for field, label in (('CUBIERTO','completas'), ('PARCIALMENTE CUBIERTO','parciales'),
                             ('SIN COBERTURA','sin cobertura'), ('area_cubierta_m2','area cubierta m2')):
            comparison.append({'INDICADOR': 'Hot Spots urbanos ' + category + ' ' + label,
                'ANTERIOR': a.get(field,0), 'FINAL': b.get(field,0), 'DIFERENCIA': b.get(field,0)-a.get(field,0)})
    mean_before = np.mean([r['SOLAPE_PREVIO_PCT'] for r in approved['actual']])
    mean_after = np.mean([r['SOLAPE_PCT'] for r in metrics])
    comparison += [{'INDICADOR':'Solape medio %','ANTERIOR':float(mean_before),'FINAL':float(mean_after),'DIFERENCIA':float(mean_after-mean_before)},
        {'INDICADOR':'Solape maximo %','ANTERIOR':max(r['SOLAPE_PREVIO_PCT'] for r in approved['actual']),
         'FINAL':max(r['SOLAPE_PCT'] for r in metrics)},
        {'INDICADOR':'Area exclusiva agregada policial m2','ANTERIOR':original_coverage.difference(baseline).area,
         'FINAL':final_mask.difference(baseline).area}]
    catalog = []
    def add(name, rows, visual=True):
        catalog.append(export(name, rows, visual))
    add('PROPUESTA_POLICIA_30_FINAL', police)
    add('CAMARAS_EXISTENTES_103_FINAL', existing)
    add('PROPUESTA_MUNICIPAL_50_FINAL', municipal)
    all_equipment = [(g, {**p, 'ID_EQUIPO': p['ID_CAMARA'], 'GRUPO_ESCENARIO':'EXISTENTE'}) for g,p in existing]
    all_equipment += [(g, {**p, 'ID_EQUIPO': p['ID_PROPUESTA'], 'GRUPO_ESCENARIO':'MUNICIPAL_PROPUESTA'}) for g,p in municipal]
    all_equipment += [(g, {**p, 'ID_EQUIPO': p['ID_POLICIA'], 'GRUPO_ESCENARIO':'POLICIA_PROPUESTA'}) for g,p in police]
    assert len(all_equipment) == len({p['ID_EQUIPO'] for _,p in all_equipment}) == 183
    add('ESCENARIO_FINAL_183', all_equipment)
    add('CONTROL_SOLAPES_POLICIA_FINAL', [(candidates[p['ID_POLICIA']]['disk'], p) for p in metrics])
    add('AREAS_EXCLUSIVAS_POLICIA_FINAL', exclusive_rows)
    add('AREAS_SOLAPADAS_POLICIA_FINAL', overlap_rows)
    add('SOLAPE_DISUELTO_POLICIA_FINAL', [(unary_union([g for g,_ in overlap_rows]), {'METODO':'Union de areas superpuestas; no doble conteo'})])
    add('COBERTURA_POLICIA_200M', [(police_mask, {'RADIO_M':200})])
    add('COBERTURA_C', [(final_mask, {'ESCENARIO':'C','RADIO_M':200,'TOTAL_EQUIPOS':183})])
    for name in ('COBERTURA_A','COBERTURA_B','PLATAFORMAS_TERRITORIALES','LIMITE_CANTONAL',
                 'CORREDORES','UPC_INFRAESTRUCTURA','RED_VIAL_CONTEXTO'):
        add(name, source(name), name != 'RED_VIAL_CONTEXTO')
    for cat in CLASSES:
        add('HOTSPOT_'+cat, [(g,p) for (scope,category),rows in updated.items() if category==cat
                            for g,p in rows if p['GI_CLASS'].startswith('HOTSPOT')])
    for key, rows in statistics.items():
        add('GI_'+key[0]+'_'+key[1], rows, False)
    add('HISTORICO_POLICIA_ANTERIOR', original)
    add('AUDITORIA_MOVIMIENTOS_8', [(LineString([old[id][0],candidates[id]['point']]), {'ID_POLICIA':id}) for id in sorted(RELOCATED)])
    table('AUDITORIA_REUBICACIONES_POLICIA', audits)
    table('POLICIA_BENEFICIO_FINAL', metrics)
    table('MATRIZ_DISTANCIAS_POLICIA_30', matrix)
    table('PARES_POLICIA_MENOS_400M', distance_rows)
    table('CONTROL_NUCLEOS_GI_99', nucleus)
    table('CELDAS_COMPLETAS_A_PARCIALES', lost_complete)
    table('COMPARACION_ANTERIOR_FINAL', comparison)
    table('INCIDENTES_CUBIERTOS_FINAL', incidents)
    table('HOTSPOTS_ATENDIDOS_FINAL', hot_stats)
    table('CORREDORES_CUBIERTOS_FINAL', corridor_stats)
    # Recalculate only C coverage attributes; the original points, blocks, axes and Gi* are unchanged.
    add('INCIDENTES_CLASIFICADOS', [(g,{**p,'CUB_C':final_mask.covers(g)}) for g,p in events], False)
    add('MANZANAS_COBERTURA', [(g,{**p,'COB_C_PCT':pct(g.intersection(urban).intersection(final_mask).area,g.intersection(urban).area)
        if g.intersection(urban).area>AREA_EPS else None,
        'POB_C_CUBIERTA':p['POBLACION']*g.intersection(urban).intersection(final_mask).area/g.area if p['POBLACION'] is not None else None}) for g,p in blocks], False)
    camera_tree = STRtree([g for g,_ in all_equipment])
    for key, label in [('BOULEVARD_MACAJI_BELLAVISTA','MACAJI'),('ANILLO_VIAL','ANILLO'),
                       ('CICLOVIAS','CICLOVIAS'),('QUEBRADA_LAS_ABRAS','LAS_ABRAS')]:
        residual = []
        for i, segment in enumerate(parts(axes[key].difference(final_mask),1),1):
            g,p = all_equipment[int(camera_tree.nearest(segment))]
            residual.append((segment, {'ID':f'{label}-{i:04d}','CORREDOR':key,'LONGITUD_M':segment.length,
                'CAMARA_MAS_CERCANA':p['ID_EQUIPO'],'DIST_CAMARA_M':segment.distance(g),
                'METODO_DIST':'Distancia minima del segmento al punto de camara'}))
        add('BRECHA_'+label+'_FINAL', residual)
    for filename in ('RADIOS_EXISTENTES_SIMBOLOGIA_200M.geojson','COBERTURA_MUNICIPAL_200M.geojson'):
        shutil.copy2(SOURCE/filename,OUT/filename)
    acceptance = {'estado':'FINAL', 'reubicadas':8,'mantenidas':22,'existentes':103,'municipales':50,'policiales':30,
        'total_equipos':183,'para_cambio_incluidas':31,'crs':'EPSG:32717','radio_m':200,
        'solape_medio_antes':float(mean_before),'solape_medio_final':float(mean_after),
        'solape_max_antes':max(r['SOLAPE_PREVIO_PCT'] for r in approved['actual']),
        'solape_max_final':max(r['SOLAPE_PCT'] for r in metrics),
        'niveles_redundancia':dict(Counter(p['REDUNDANCIA'] for p in metrics)),
        'excepciones_mayor85':[],'justificaciones70_85':[p['ID_POLICIA'] for p in metrics if p['SOLAPE_PCT']>70],
        'pares_por_banda':{band:sum(r['BANDA']==band for r in distance_rows) for band in ('<100 m','100-200 m','200-300 m','300-400 m')},
        'pares_menor200':[r for r in distance_rows if r['DISTANCIA_M']<200],
        'nucleos99_abandonados':abandoned99,'nuevos_pares_menor200':0,
        'celdas_completas_a_parciales':dict(Counter(r['CATEGORIA'] for r in lost_complete)),
        'gi_recalculado':False,'fuentes_protegidas_hash':protected,'ocho_seleccionadas_iterativamente':True,
        'fuente_seleccion_iterativa':str(REVIEW/'RESULTADOS.json'),'regeneracion_completa':False,
        'coordenadas_22_conservadas':True,'existentes_municipales_conservadas':True,'commit':False,'push':False,
        'campos_gi_geometrias_conservados':True,'brechas_manzanas_c_reutilizadas':False,
        'poblacion_metodo':'Estimacion areal urbana CPV2022; rural completa no disponible'}
    merged.update({'generatedAt':datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'),
        'status':'FINAL','officialPoliceSource':'PROPUESTA_POLICIA_30_FINAL', 'sourceHashes':protected,
        'catalog':catalog,'policeChanges':[a for a in audits if a['DECISION']=='REUBICAR'],
        'policeMetrics':metrics,'policeClosure':acceptance,'policeComparison':comparison,
        'giRecalculated':False,'commit':False,'push':False,'gapScenarioCValidated':False,
        'warnings':prior.get('warnings',[])+['Las brechas por manzana del escenarioC anterior no se reutilizan con esta configuracion policial.',
            'La cobertura de eventos mejora; algunas celdasD quedan parcialmente cubiertas. Ningun nucleoD/V99 previamente atendido queda totalmente sin cobertura.']})
    # The old summary's183 column would be stale; replace it from the same final result tables.
    summary = []
    for cat in CLASSES:
        summary.append({'INDICADOR':cat+' cubiertos cantonales', **{str(n):next(r['CUBIERTOS'] for r in merged['incidents']
            if r['ESCENARIO']==s and r['AMBITO']=='CANTONAL' and r['CATEGORIA']==cat) for s,n in zip('ABC',(103,153,183))}})
    merged['summary'] = summary
    save_json('RESULTADOS.json',merged)
    assert all(sha(Path(path)) == digest for path,digest in protected.items())
    save_json('VALIDACION.json',acceptance)
    write_report(merged,approved,lost_complete)
    write_map(merged,police,existing,municipal,hot,platforms,exclusive_rows,overlap_rows,original_coverage)
    for g,p in existing:
        assert any(g.equals_exact(q,0) and p==r for q,r in records(read_layer(FINAL_PACKAGE,'CAMARAS_EXISTENTES_103_FINAL')))
    for g,p in municipal:
        assert any(g.equals_exact(q,0) and p==r for q,r in records(read_layer(FINAL_PACKAGE,'PROPUESTA_MUNICIPAL_50_FINAL')))
    package_zip()
    print('FINAL',json.dumps({'control':{k:v for k,v in acceptance.items() if k not in ('fuentes_protegidas_hash','pares_menor200')},
         'comparacion':comparison},ensure_ascii=False),flush=True)


def write_report(result,approved,lost):
    c=result['policeClosure']
    lines=['# PROPUESTA FINAL POLICIA NACIONAL - 30 CAMARAS','',
        '**Estado: FINAL DEL ESTUDIO. Propuestas no instaladas; requieren validacion operativa de campo.**','',
        '## Cierre aprobado',
        '- 8 reubicadas: '+', '.join(sorted(RELOCATED))+'. Las otras 22 mantienen exactamente sus coordenadas.',
        '- 103 existentes + 50 municipales finales + 30 policiales = 183 equipos; 31 para cambio son parte de las 103.',
        '- Candidatos aprobados de la revision iterativa; no se regeneraron las 30 ni se cambiaron Gi*, KDE, fuentes o ejes.',
        '- Las ocho recomendaciones proceden de la seleccion iterativa aprobada. El conjunto final de 30 se verifico contra 103 + 50 + las otras 29.',
        '- CRS metrico EPSG:32717; radio 200 m; buffers de 64 segmentos por cuadrante y cobertura disuelta.',
        '- Gi* D/V es el criterio principal; Convivencia y corredores son complementarios. No se impone400m ni otro minimo de separacion.',
        '- Gi* del sitio y nivel maximo en el radio200m son campos diferentes. No se fabrica una significancia conjunta D/V.',
        '- Aportes exclusivos individuales no se suman; el balance anterior/final se obtiene de la union completa.','',
        '## Comparacion anterior/final','| Indicador | Anterior | Final |','|---|---:|---:|']
    for r in result['policeComparison']:
        lines.append(f"| {r['INDICADOR']} | {r['ANTERIOR']:.2f} | {r['FINAL']:.2f} |")
    lines += ['', '## Redundancia final',
        f"BAJA <50%: {c['niveles_redundancia'].get('BAJA',0)}; MEDIA [50,70]%: {c['niveles_redundancia'].get('MEDIA',0)}; ALTA (70,85]%: {c['niveles_redundancia'].get('ALTA',0)}; MUY ALTA >85%: {c['niveles_redundancia'].get('MUY ALTA',0)}.",
        'No hay excepciones >85%. Los solapes70-85% se justifican individualmente enPOLICIA_BENEFICIO_FINAL.csv.','',
        '## Pares policiales proximos']
    for band,n in c['pares_por_banda'].items():lines.append(f'- {band}: {n} pares.')
    for r in c['pares_menor200']:
        lines.append(f"- {r['ID_A']} / {r['ID_B']}: {r['DISTANCIA_M']:.2f}m. {r['JUSTIFICACION']}")
    lines += ['', '## Hot Spots prioritarios',
        '- Ningun nucleoD/V99 previamente con alguna cobertura pasa aSIN COBERTURA. Los valoresGi*, categorias, celdas y parametrizacion permanecen intactos.',
        '- Transiciones completas a parciales: '+str(c['celdas_completas_a_parciales']['DELINCUENCIA'])+' celdas de Delincuencia y '+str(c['celdas_completas_a_parciales']['VIOLENCIA'])+' de Violencia. No confundir estas transiciones con el balance neto: otras celdas pasan a completas. Ninguna de estas transiciones produce ausencia total.',
        '- El area cubierta de Hot Spots urbanos de Delincuencia disminuye ligeramente; la de Violencia aumenta. Los eventos D/V cubiertos aumentan en 152.',
        '- El control por celda y nivel99 figura enCONTROL_NUCLEOS_GI_99.csv; transiciones enCELDAS_COMPLETAS_A_PARCIALES.csv.',
        '- La cobertura por categoria, nivel y ambito se reporta enHOTSPOTS_ATENDIDOS_FINAL.csv. Los resultadosruralesGi* no se recalculan.', '',
        '## Fuentes oficiales y derivados',
        '- ESCENARIO_FINAL_183.gpkg contienePROPUESTA_POLICIA_30_FINAL(30), ESCENARIO_FINAL_183(183), CONTROL_SOLAPES_POLICIA_FINAL, AUDITORIA_REUBICACIONES_POLICIA y la matriz de distancias.',
        '- La unica fuente policial activa esPROPUESTA_POLICIA_30_FINAL en este paquete. HISTORICO_POLICIA_ANTERIOR y la revision previa no son propuestas oficiales activas.',
        '- Los atributos de coberturaC de incidentes/manzanas/Hot Spots se actualizan para el nuevo escenario; sus geometria y valores estadisticos originales no cambian.',
        '- Las capas GI_URBANO_* y GI_RURAL_* son copias integras del resultado estadistico congelado. Sus atributos historicos COB_C no deben utilizarse como cobertura final: para ese fin utilizar HOTSPOT_* y HOTSPOTS_ATENDIDOS_FINAL.',
        '- Las coberturasA/B y los ejes deMacaji, Anillo, Ciclovias, LasAbras y Cunduana se conservan; solo se evalua su interseccion con el nuevo escenarioC. No fueron objetivos de optimizacion policial.',
        '- Las brechas por manzanaC anteriores quedan invalidadas para esta configuracion; no se reutilizan ni se declaran recalculadas en este cierre. A/B permanecen intactos.',
        '- La poblacion adicional/cubierta es una estimacion areal urbanaCPV2022 en18Plataformas. Rural completa:No disponible; faltantes no se representan por cero.',
        '- MAPA_FINAL_POLICIA_NACIONAL y CONTROL_FINAL_SOLAPES son dos vistas del mismo conjunto final, no versiones alternativas.', '',
        '## Validacion',
        '103/50 conservadas;22coordenadas policiales conservadas;8movimientos aprobados;30policiales exactas;183equipos;0solapes>85%;0nucleos99abandonados;0nuevospares<200m. Fuentes originales verificadas porhash. Sin commit ni push.']
    (OUT/'INFORME_FINAL.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def write_map(result,police,existing,municipal,hot,platforms,exclusive,overlap,old_coverage):
    layers={'police':geojson(police),'existing':geojson(existing),'municipal':geojson(municipal),
        'hot':geojson([(g,{k:p[k] for k in ('CELL_ID','CATEGORIA','NIVEL','AMBITO')}) for g,p in hot if p['CATEGORIA'] in CLASSES[:2]]),
        'platforms':geojson(platforms),'buffers':geojson([(g.buffer(200,quad_segs=64),{'ID_POLICIA':p['ID_POLICIA']}) for g,p in police]),
        'exclusive':geojson(exclusive),'overlap':geojson(overlap),
        'overlapUnion':geojson([(unary_union([g for g,_ in overlap]),{})])}
    payload={'resultados':result,'capas':layers}
    template=(ROOT/'tools/final_police_map.html').read_text(encoding='utf-8')
    encoded=json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':')).replace('</','<\\/')
    (OUT/'index.html').write_text(template.replace('__FINAL_DATA__',encoded),encoding='utf-8')


def package_zip():
    with zipfile.ZipFile(OUT/'CIERRE_POLICIA_30_FINAL.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for file in OUT.iterdir():
            if file.is_file() and file.suffix!='.zip':archive.write(file,file.name)


if __name__=='__main__':main()
