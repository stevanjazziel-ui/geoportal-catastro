"""Read-only audit of final police30; trial relocations never overwrite official data."""
import csv
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyogrio
from shapely import STRtree, covers, prepare
from shapely.ops import unary_union

from build_police_camera_proposal import (
    ROOT, CLASSES, AREA_EPS, Context, dv_coincidences, records, read_layer,
    geojson, sha, coverage_class,
)
from review_police_camera_efficiency import Evaluator, revision_rank

SOURCE = ROOT / 'data/seguridad-riobamba/CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA'
PACKAGE = SOURCE / 'CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.gpkg'
CANDIDATES = ROOT / 'data/seguridad-riobamba/propuesta-policia-30-20261003/PROPUESTA_POLICIA_30.gpkg'
OUT = ROOT / 'data/seguridad-riobamba/redundancia-policia-30-20261005'
ORDER = {'MUY ALTA': 0, 'ALTA': 1, 'MEDIA': 2, 'BAJA': 3}


def redundancy(value):
    if value < 50:
        return 'BAJA'
    if value <= 70:
        return 'MEDIA'
    if value <= 85:
        return 'ALTA'
    return 'MUY ALTA'


def priority(row):
    return row['SOLAPE_PREVIO_PCT'] > 85 and row['EVENTOS_DV_NUEVOS'] <= 2


def sorted_rows(rows):
    return sorted(rows, key=lambda r: (ORDER[r['REDUNDANCIA']], r['EVENTOS_DV_NUEVOS'],
                                      -r['SOLAPE_PREVIO_PCT'], r['ID_POL']))


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                     separators=(',', ':')), encoding='utf-8')


def write_csv(name, rows):
    fields = list(dict.fromkeys(k for p in rows for k in p))
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


class Audit:
    def __init__(self):
        def layer(name):
            return records(read_layer(PACKAGE, name))
        self.existing = layer('CAMARAS_EXISTENTES_103_FINAL')
        self.municipal = layer('PROPUESTA_MUNICIPAL_50_FINAL')
        self.official = layer('PROPUESTA_POLICIA_30_FINAL')
        self.events = layer('INCIDENTES_CLASIFICADOS')
        self.platforms = layer('PLATAFORMAS_TERRITORIALES')
        self.roads = layer('RED_VIAL_CONTEXTO')
        self.canton = layer('LIMITE_CANTONAL')
        self.infrastructure = layer('UPC_INFRAESTRUCTURA')
        self.blocks = layer('MANZANAS_COBERTURA')
        self.statistics = {(scope, cat): layer('GI_' + scope + '_' + cat)
                           for scope in ('URBANO', 'RURAL') for cat in CLASSES}
        self.gi_trees = {key: STRtree([g for g, _ in rows]) for key, rows in self.statistics.items()}
        hot = [(g, p) for rows in self.statistics.values() for g, p in rows
               if p['GI_CLASS'].startswith('HOTSPOT')]
        self.base = read_layer(PACKAGE, 'COBERTURA_B').geometry.iloc[0]
        self.cover_a = read_layer(PACKAGE, 'COBERTURA_A').geometry.iloc[0]
        self.urban = unary_union([g for g, _ in self.platforms])
        corridors = layer('CORREDORES')
        axes = {key: unary_union([g for g, p in corridors if p['CORREDOR'] == key])
                for key in dict.fromkeys(p['CORREDOR'] for _, p in corridors)}
        self.context = Context(self.events, hot, dv_coincidences(self.statistics), self.base,
                               [g for g, _ in self.existing], [g for g, _ in self.municipal],
                               self.infrastructure, self.blocks, self.urban, axes)
        self.evaluator = Evaluator(self.context)
        self.event_points = np.array([g for g, _ in self.events], dtype=object)
        self.original_props = {p['ID_POLICIA']: p for _, p in self.official}
        self.candidates = {}
        raw = records(read_layer(CANDIDATES, 'CANDIDATOS_POLICIA'))
        for g, p in raw:
            c = self.context.candidate({'point': g, 'id': p['ID_CANDIDATO'],
                                        'degree': p['GRADO_NODO'], 'props': dict(p)})
            self.candidates[c['id']] = c
        self.active = {p['ID_POLICIA']: self.candidates[p['ID_CANDIDATO']] for _, p in self.official}
        assert len(self.existing) == 103 and len(self.municipal) == 50 and len(self.active) == 30
        assert all(g.equals(self.active[p['ID_POLICIA']]['point']) for g, p in self.official)
        self.official_ids = {c['id'] for c in self.active.values()}
        self.road_tree = STRtree([g for g, _ in self.roads])

    def reference(self, active, slot):
        other = {id: c for id, c in active.items() if id != slot}
        coverage = unary_union([self.base] + [c['disk'] for c in other.values()])
        self.evaluator.coverage = coverage
        prepare(coverage)
        self.evaluator.covered = set(np.flatnonzero(covers(coverage, self.event_points)).tolist())
        self.evaluator.uncovered = [g.difference(coverage) for g, _ in self.context.hot]
        self.evaluator.dv_uncovered = [g.difference(coverage) for g, _ in self.context.dv]
        return other, coverage

    def basic(self, c, other):
        return self.evaluator.evaluate(c, [v['point'] for v in other.values()])

    def gi_at_site(self, c):
        fields = {}
        for cat, label in zip(CLASSES[:2], ('D', 'V')):
            key = (c['scope'], cat)
            matches = [int(i) for i in self.gi_trees[key].query(c['point'], predicate='intersects')]
            cells = sorted([self.statistics[key][i][1] for i in matches], key=lambda p: p['CELL_ID'])
            fields['GI_' + label + '_CELDAS_SITIO'] = '|'.join(p['CELL_ID'] for p in cells) or None
            fields['GI_' + label + '_CLASE_SITIO'] = '|'.join(p['GI_CLASS'] for p in cells) or None
            # A boundary can belong to two cells: retain every cell, never select the larger z-score.
            fields['GI_' + label + '_ZSCORE_SITIO'] = cells[0]['GI_ZSCORE'] if len(cells) == 1 else None
            fields['GI_' + label + '_PVALUE_SITIO'] = cells[0]['GI_PVALUE'] if len(cells) == 1 else None
        return fields

    def detail(self, c, other, row=None):
        row = dict(row or self.basic(c, other))
        coverage = self.evaluator.coverage
        exclusive = c['disk'].difference(coverage)
        overlap = c['disk'].intersection(coverage)
        population, valid, missing = self.context.population(exclusive)
        associated, av, am = self.context.population(c['disk'])
        hit = [p['platform_name'] for g, p in self.platforms if g.covers(c['point'])]
        row.update({'PLATAFORMA': '|'.join(hit) or 'FUERA DE PLATAFORMAS',
                    'AREA_BUFFER_M2': c['disk'].area, 'AREA_SOLAPADA_M2': overlap.area,
                    'AREA_EXCLUSIVA_M2': exclusive.area,
                    'APORTE_EXCLUSIVO_PCT': 100 * exclusive.area / c['disk'].area,
                    'REDUNDANCIA': redundancy(row['SOLAPE_PREVIO_PCT']),
                    'POBLACION_ADICIONAL_ESTIMADA': population,
                    'POBLACION_ASOCIADA_ESTIMADA': associated,
                    'MANZANAS_ADICIONALES_VALIDAS': valid, 'MANZANAS_ADICIONALES_SIN_POBLACION': missing,
                    'POBLACION_ADICIONAL_PARCIAL': bool(missing),
                    'POBLACION_ASOCIADA_PARCIAL': bool(am),
                    'CORREDOR_COINCIDENTE': '|'.join(k for k, axis in self.context.axes.items()
                                                  if axis.intersection(c['disk']).length > 1e-6) or None})
        for threshold in (200, 300, 400):
            for label, key in (('EXISTENTE', 'DIST_EXISTENTE_M'), ('MUNICIPAL', 'DIST_MUNICIPAL_M'),
                               ('POLICIA', 'DIST_POLICIA_M')):
                row[f'{label}_MENOS_{threshold}M'] = row[key] < threshold
        for category, label in zip(CLASSES[:2], ('D', 'V')):
            touched, first, completed = [], [], []
            for i, _ in c['hot']:
                geom, props = self.context.hot[i]
                if props['CATEGORIA'] != category or props['AMBITO'] != c['scope']:
                    continue
                added = geom.intersection(exclusive).area
                if added <= AREA_EPS:
                    continue
                touched.append(props['CELL_ID'])
                prev = geom.intersection(coverage).area / geom.area
                after = (geom.intersection(coverage).area + added) / geom.area
                if coverage_class(prev) == 'SIN COBERTURA':
                    first.append(props['CELL_ID'])
                if coverage_class(prev) != 'CUBIERTO' and coverage_class(after) == 'CUBIERTO':
                    completed.append(props['CELL_ID'])
            row['HOTSPOT_' + label] = c['props'].get('HOTSPOT_' + ('DEL' if label == 'D' else 'VIOL'))
            row['HOTSPOTS_' + label + '_CON_APORTE'] = len(touched)
            row['HOTSPOTS_' + label + '_PRIMERA_ATENCION'] = len(first)
            row['HOTSPOTS_' + label + '_COMPLETADOS'] = len(completed)
            row['IDS_HOTSPOTS_' + label + '_CON_APORTE'] = '|'.join(touched) or None
        row.update(self.gi_at_site(c))
        nearest_road = int(self.road_tree.nearest(c['point']))
        row['DIST_RED_VIAL_CONTEXTO_M'] = c['point'].distance(self.roads[nearest_road][0])
        row['VIA_CONTEXTO_CERCANA'] = self.roads[nearest_road][1].get('NOMBRE')
        assert abs(exclusive.area + overlap.area - c['disk'].area) < .01
        assert abs(row['SOLAPE_PREVIO_PCT'] + row['APORTE_EXCLUSIVO_PCT'] - 100) < 1e-7
        return row, exclusive, overlap

    def scenario(self, coverage):
        prepare(coverage)
        selected = covers(coverage, self.event_points)
        incidents = {}
        for cat in CLASSES:
            indices = [i for i, (_, p) in enumerate(self.events) if p['CATEGORIA'] == cat
                       and p['AMBITO'] != 'EXTERNO_CANTON']
            count = int(selected[indices].sum())
            incidents[cat] = {'total': len(indices), 'cubiertos': count,
                              'porcentaje': 100 * count / len(indices) if indices else None}
        hot = {}
        for scope in ('URBANO', 'RURAL'):
            for cat in CLASSES:
                cells = [(g, p) for g, p in self.context.hot if p['AMBITO'] == scope and p['CATEGORIA'] == cat]
                counts = Counter(coverage_class(g.intersection(coverage).area / g.area) for g, _ in cells)
                hot[scope + '_' + cat] = {'total': len(cells), **dict(counts),
                    'area_cubierta_m2': sum(g.intersection(coverage).area for g, _ in cells)}
        return {'incidentes': incidents, 'hotspots': hot, 'area_m2': coverage.area,
                'poblacion_urbana_estimada': self.context.population(coverage)[0],
                'corredores_m': {k: axis.intersection(coverage).length for k, axis in self.context.axes.items()}}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sources = [PACKAGE, SOURCE / 'RESULTADOS.json', CANDIDATES]
    sources += list(ROOT.glob('riobamba*.js'))
    sources += list((ROOT / 'data/seguridad-riobamba/hotspot-urbano-200m-20261002').glob('*.*'))
    protected = {str(p): sha(p) for p in sources if p.is_file()}
    audit = Audit()
    current = dict(audit.active)
    rows, geometries = [], {}
    for slot, c in current.items():
        other, _ = audit.reference(current, slot)
        row, exclusive, overlap = audit.detail(c, other)
        row.update({'ID_POL': slot, 'REVISAR': row['SOLAPE_PREVIO_PCT'] > 70,
                    'MAXIMA_PRIORIDAD': priority(row)})
        props = audit.original_props[slot]
        assert abs(row['SOLAPE_PREVIO_PCT'] - props['SOLAPE_RESTO_FINAL_PCT']) < 1e-6
        assert row['EVENTOS_D_NUEVOS'] == props['EVENTOS_D_EXCLUSIVOS_FINAL']
        assert row['EVENTOS_V_NUEVOS'] == props['EVENTOS_V_EXCLUSIVOS_FINAL']
        rows.append(row)
        geometries[slot] = (exclusive, overlap)
    rows = sorted_rows(rows)
    print('AUDITORIA_ACTUAL', [(r['ID_POL'], round(r['SOLAPE_PREVIO_PCT'], 2),
                                r['EVENTOS_DV_NUEVOS'], r['PLATAFORMA']) for r in rows], flush=True)
    reviewed = [r for r in rows if r['REVISAR']]
    reviewed.sort(key=lambda r: (not r['MAXIMA_PRIORIDAD'], r['EVENTOS_DV_NUEVOS'], -r['SOLAPE_PREVIO_PCT']))
    comparisons, decisions = [], {}
    trial = dict(current)
    for iteration, original in enumerate(reviewed, 1):
        slot = original['ID_POL']
        other, _ = audit.reference(trial, slot)
        before = audit.basic(trial[slot], other)
        reserved = {c['id'] for c in trial.values()}
        eligible = []
        for c in audit.candidates.values():
            if c['id'] in reserved or c['id'] in audit.official_ids or c['scope'] != trial[slot]['scope']:
                continue
            if min(c['distanceExisting'], c['distanceMunicipal']) <= 1e-5:
                continue
            result = audit.basic(c, other)
            if max(result['NIVEL_DEL_RESIDUAL'], result['NIVEL_VIOL_RESIDUAL']) < 90:
                continue
            # Retain D/V evidence and improve events + overlap, not mere point separation.
            result['PREFERIBLE'] = (
                result['EVENTOS_D_NUEVOS'] >= before['EVENTOS_D_NUEVOS']
                and result['EVENTOS_V_NUEVOS'] >= before['EVENTOS_V_NUEVOS']
                and result['EVENTOS_DV_NUEVOS'] > before['EVENTOS_DV_NUEVOS']
                and result['SOLAPE_PREVIO_PCT'] < before['SOLAPE_PREVIO_PCT']
                and max(result['NIVEL_DEL'], result['NIVEL_VIOL']) >= max(before['NIVEL_DEL'], before['NIVEL_VIOL']))
            eligible.append(result)
        eligible.sort(key=lambda r: (r['PREFERIBLE'], revision_rank(r), r['ID_CANDIDATO']), reverse=True)
        top = eligible[:5]
        before_detail = audit.detail(trial[slot], other, before)[0]
        options = [dict(before_detail, TIPO_OPCION='ACTUAL', ORDEN=0, PREFERIBLE=False)]
        for position, result in enumerate(top, 1):
            detail = audit.detail(audit.candidates[result['ID_CANDIDATO']], other, result)[0]
            detail.update({'TIPO_OPCION': 'ALTERNATIVA', 'ORDEN': position})
            options.append(detail)
        replace = bool(top and top[0]['PREFERIBLE'])
        winner = options[1] if replace else options[0]
        if replace:
            trial[slot] = audit.candidates[winner['ID_CANDIDATO']]
        reason = (f"Reubicar en escenario de prueba: D/V adicionales {before['EVENTOS_DV_NUEVOS']} a "
                  f"{winner['EVENTOS_DV_NUEVOS']}, sin perder D o V individualmente; solape "
                  f"{before['SOLAPE_PREVIO_PCT']:.2f}% a {winner['SOLAPE_PREVIO_PCT']:.2f}%. "
                  f"Nodo vial de grado {winner['GRADO_NODO']}, Hot Spot residual D/V "
                  f"{winner['NIVEL_DEL_RESIDUAL']}%/{winner['NIVEL_VIOL_RESIDUAL']}%. "
                  "No se exige que ambas categorias sean significativas en la misma celda. "
                  "Las superficies/niveles pueden variar: consultar alternativas. "
                  "Pendiente validacion operativa de campo." if replace else
                  f"Mantener: entre {len(eligible)} nodos residuales del mismo ambito, ninguno mejora "
                  "simultaneamente eventos D/V y solape sin perder D o V, conservando evidencia D o V "
                  "residual y el nivel maximo significativo en el entorno. La proximidad no obliga a reubicar.")
        decisions[slot] = {'ID_POL': slot, 'DECISION': 'REUBICAR' if replace else 'MANTENER',
            'CANDIDATO_ACTUAL': before['ID_CANDIDATO'], 'CANDIDATO_PROPUESTO': winner['ID_CANDIDATO'],
            'DV_ANTES_ITERACION': before['EVENTOS_DV_NUEVOS'], 'DV_DESPUES_ITERACION': winner['EVENTOS_DV_NUEVOS'],
            'SOLAPE_ANTES_ITERACION': before['SOLAPE_PREVIO_PCT'], 'SOLAPE_DESPUES_ITERACION': winner['SOLAPE_PREVIO_PCT'],
            'ITERACION': iteration, 'N_ALTERNATIVAS_EVALUADAS': len(eligible), 'JUSTIFICACION': reason}
        for option in options:
            option.update({'ID_POL_REVISADA': slot, 'ITERACION': iteration,
                           'SELECCIONADA_PRUEBA': option['ID_CANDIDATO'] == winner['ID_CANDIDATO']})
            comparisons.append(option)
        print('ITERACION', decisions[slot], flush=True)
    for row in rows:
        slot = row['ID_POL']
        if slot not in decisions:
            decisions[slot] = {'ID_POL': slot, 'DECISION': 'MANTENER',
                'CANDIDATO_ACTUAL': row['ID_CANDIDATO'], 'CANDIDATO_PROPUESTO': row['ID_CANDIDATO'],
                'ITERACION': None, 'N_ALTERNATIVAS_EVALUADAS': 0,
                'JUSTIFICACION': f"Solape {row['SOLAPE_PREVIO_PCT']:.2f}% y {row['EVENTOS_DV_NUEVOS']} "
                    f"eventos D/V exclusivos; no combina solape >70% con aporte bajo. "
                    f"Entorno Hot Spot D/V {row['NIVEL_DEL']}%/{row['NIVEL_VIOL']}%. Mantener ubicacion."}
        row.update({'DECISION': decisions[slot]['DECISION'], 'JUSTIFICACION': decisions[slot]['JUSTIFICACION']})
    final_rows, trial_geom = [], {}
    for slot, c in trial.items():
        other, _ = audit.reference(trial, slot)
        row, exclusive, overlap = audit.detail(c, other)
        row.update({'ID_POL': slot, 'DECISION': decisions[slot]['DECISION'],
                    'JUSTIFICACION': decisions[slot]['JUSTIFICACION']})
        final_rows.append(row)
        trial_geom[slot] = (exclusive, overlap)
    assert len(trial) == len(final_rows) == 30
    assert len({c['id'] for c in trial.values()}) == 30
    assert len({c['point'].wkb for c in trial.values()}) == 30
    nearest = []
    for row in rows:
        if 'PLATAFORMA J' not in row['PLATAFORMA']:
            continue
        slot = row['ID_POL']
        point = current[slot]['point']
        pool = [(g, p['ID_CAMARA'], 'EXISTENTE') for g, p in audit.existing]
        pool += [(g, p['ID_PROPUESTA'], 'MUNICIPAL') for g, p in audit.municipal]
        pool += [(c['point'], id, 'POLICIAL') for id, c in current.items() if id != slot]
        closest = sorted(pool, key=lambda x: (point.distance(x[0]), x[1]))[:5]
        nearest.extend({'ID_POL_J': slot, 'ORDEN': i, 'ID_CERCANA': id, 'GRUPO': group,
                        'DISTANCIA_M': point.distance(g)} for i, (g, id, group) in enumerate(closest, 1))
    official_c = unary_union([audit.base] + [c['disk'] for c in current.values()])
    trial_c = unary_union([audit.base] + [c['disk'] for c in trial.values()])
    assert official_c.symmetric_difference(read_layer(PACKAGE, 'COBERTURA_C').geometry.iloc[0]).area < .1
    scenarios = {name: audit.scenario(coverage) for name, coverage in
                 [('103', audit.cover_a), ('103+50', audit.base), ('103+50+30_OFICIAL', official_c),
                  ('103+50+30_PRUEBA', trial_c)]}
    for cat in CLASSES[:2]:
        assert scenarios['103+50+30_PRUEBA']['incidentes'][cat]['cubiertos'] >= scenarios['103+50+30_OFICIAL']['incidentes'][cat]['cubiertos']
    for row in rows:
        # Independent point-in-disk/exclusion check, not the candidate event cache.
        c = current[row['ID_POL']]
        others = unary_union([audit.base] + [o['disk'] for id, o in current.items() if id != row['ID_POL']])
        for cat, field in [('DELINCUENCIA', 'EVENTOS_D_NUEVOS'), ('VIOLENCIA', 'EVENTOS_V_NUEVOS')]:
            n = sum(c['disk'].covers(g) and not others.covers(g) for g, p in audit.events
                    if p['CATEGORIA'] == cat and p['AMBITO'] != 'EXTERNO_CANTON')
            assert n == row[field]
    data = {'metadata': {'fecha': '2026-10-05', 'crs_calculo': 'EPSG:32717', 'radio_m': 200,
                'inventario': 103, 'municipales': 50, 'policiales': 30,
                'oficial_modificado': False, 'fuentes_hash': protected,
                'referencia': '103 + 50 municipales finales + otras 29 policiales; excluir siempre la propia',
                'revision': 'Se comparan todos los solapes >70%; prioridad maxima >85% y DV<=2; no se inventa un umbral de aporte bajo.',
                'candidatos': len(audit.candidates), 'poblacion': 'Estimacion areal CPV2022 en 18 Plataformas; no censo rural completo.',
                'distancias': 'Euclidianas entre puntos, no distancias por red ni tiempos de respuesta.'},
            'actual': rows, 'prueba': sorted_rows(final_rows), 'decisiones': list(decisions.values()),
            'alternativas': comparisons, 'plataformaJ_cercanas': nearest, 'escenarios': scenarios,
            'validacion': {'geometrias_areas_cuadran': True, 'eventos_verificados_independientemente': True,
                          'reproduce_resultados_finales': True, 'policiales_prueba': 30,
                          'iterativo': True, 'sin_distancia_minima': True}}
    assert all(sha(Path(path)) == digest for path, digest in protected.items())
    data['validacion']['fuentes_sin_cambios'] = True
    write_json('RESULTADOS.json', data)
    write_csv('AUDITORIA_30_POLICIA.csv', rows)
    write_csv('ALTERNATIVAS_ITERATIVAS.csv', comparisons)
    write_csv('DECISIONES.csv', list(decisions.values()))
    write_csv('ESCENARIO_PRUEBA_30.csv', sorted_rows(final_rows))
    write_csv('PLATAFORMA_J_5_CERCANAS.csv', nearest)
    export_map(audit, data, current, trial, geometries, trial_geom)
    write_report(data)
    files = [p for p in OUT.iterdir() if p.is_file() and p.suffix != '.zip']
    with zipfile.ZipFile(OUT / 'REVISION_REDUNDANCIA_POLICIA_30.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, file.name)
    print('FINAL', json.dumps({'redundancia': dict(Counter(r['REDUNDANCIA'] for r in rows)),
        'reubicar': [r['ID_POL'] for r in rows if r['DECISION'] == 'REUBICAR'],
        'escenarios': {k: v['incidentes'] for k, v in scenarios.items()},
        'fuentes_sin_cambios': data['validacion']['fuentes_sin_cambios']}, ensure_ascii=False), flush=True)


def export_map(audit, data, current, trial, geometries, trial_geom):
    package = OUT / 'REDUNDANCIA_POLICIA_30.gpkg'
    layers = {}
    for mode, active, geom, rows in [('ACTUAL', current, geometries, data['actual']),
                                    ('PRUEBA', trial, trial_geom, data['prueba'])]:
        props = {p['ID_POL']: p for p in rows}
        layers['POLICIA_' + mode] = [(c['point'], props[id]) for id, c in active.items()]
        layers['BUFFER_' + mode] = [(c['disk'], {'ID_POL': id, 'REDUNDANCIA': props[id]['REDUNDANCIA']}) for id, c in active.items()]
        layers['EXCLUSIVA_' + mode] = [(geom[id][0], {'ID_POL': id}) for id in active]
        layers['SUPERPUESTA_' + mode] = [(geom[id][1], {'ID_POL': id}) for id in active]
    layers['ALTERNATIVAS'] = [(audit.candidates[r['ID_CANDIDATO']]['point'], r)
                              for r in data['alternativas'] if r['TIPO_OPCION'] == 'ALTERNATIVA']
    for name, rows in layers.items():
        frame = gpd.GeoDataFrame([p for _, p in rows], geometry=[g for g, _ in rows], crs=32717)
        pyogrio.write_dataframe(frame, package, layer=name)
    layers['EXISTENTES'] = [(g, {k: p[k] for k in ('ID_CAMARA', 'REQUIERE_CAMBIO')}) for g, p in audit.existing]
    layers['MUNICIPALES'] = [(g, {'ID_PROPUESTA': p['ID_PROPUESTA']}) for g, p in audit.municipal]
    layers['PLATAFORMAS'] = [(g, {'platform_name': p['platform_name']}) for g, p in audit.platforms]
    layers['CANTON'] = [(g, {}) for g, _ in audit.canton]
    layers['HOTSPOTS_DV'] = [(g, {k: p[k] for k in ('CELL_ID', 'CATEGORIA', 'NIVEL', 'AMBITO')})
                             for g, p in audit.context.hot if p['CATEGORIA'] in CLASSES[:2]]
    visual = {name: geojson(rows) for name, rows in layers.items()}
    write_index(visual, data)


def write_index(visual, data):
    payload = {'resultados': data, 'capas': visual}
    template = (ROOT / 'tools/police_redundancy_map.html').read_text(encoding='utf-8')
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).replace('</', '<\\/')
    (OUT / 'index.html').write_text(template.replace('__AUDIT_DATA__', text), encoding='utf-8')


def write_report(data):
    lines = ['# Revision final de redundancia espacial - 30 camaras policiales', '',
        '## Alcance y metodo',
        '- Solo auditoria y escenario de prueba. Los 103 puntos existentes, 50 municipales y 30 policiales oficiales permanecen intactos.',
        '- EPSG:32717; radio 200 m; buffer con 64 segmentos por cuadrante, igual que la corrida final.',
        '- Cada aporte exclusivo se mide contra 103 + 50 + las OTRAS 29 policiales. No se suman aportes individuales.',
        '- Redundancia: BAJA <50%; MEDIA [50,70]%; ALTA (70,85]%; MUY ALTA >85%. Los extremos compartidos se resuelven explicitamente.',
        '- Se revisan todos los solapes >70%, incluso cuando su aporte D/V no es bajo. Prioridad maxima: >85% y D/V <=2. No se invento otro umbral de bajo aporte.',
        '- Alternativas: banco congelado de nodos viales del proyecto, mismo ambito; no se seleccionan puntos oficiales ni duplicados exactos de existentes/municipales.',
        '- Preferible: mas D+V nuevos, sin disminuir D o V por separado, menor solape, evidencia residual significativa de D O V y sin reducir el maximo nivel significativo del entorno de 200 m. No se exige coincidencia simultanea de ambas categorias.',
        '- Orden lexicografico entre alternativas: preferible; D/V nuevos; nivel y area de coincidencia D/V residual; area D+V nueva; menor solape; Convivencia; grado vial. Sin ponderaciones ni distancia minima.',
        '- En cada iteracion la alternativa y el punto actual se comparan contra exactamente las mismas otras29. Una recomendacion modifica solo el escenario de prueba antes de revisar la siguiente.',
        '- Gi* del SITIO se obtiene de la celda que contiene el punto; NIVEL_DEL/VIOL representa el maximo Hot Spot dentro del buffer. No son equivalentes.',
        '- En limites de celdas se conservan todas las clases/IDs; z/p escalar queda No disponible si hay mas de una. No se inventa un nivel conjunto D/V.',
        '- Hot Spots CON_APORTE: celdas con area adicional positiva; PRIMERA_ATENCION: antes sin cobertura y ahora con alguna; COMPLETADOS: antes parciales y ahora cubiertas. Atendido no significa eliminado.',
        '- Poblacion adicional: estimacion proporcional de area exclusiva intersectada con manzanas CPV2022 dentro de las 18 Plataformas. Sin poblacion valida: No disponible; faltantes: estimacion parcial.',
        '- Distancias entre puntos son euclidianas, no recorridos ni tiempos. Banderas <200/<300/<400 m son descriptivas, nunca reglas de reubicacion.',
        '- Corredores, UPC y via cercana son contexto. No se optimiza Anillo, Ciclovias, Macaji-Bellavista, Las Abras ni Cunduana.',
        '- Nodo vial documental no acredita por si solo factibilidad de instalacion; requiere inspeccion de campo. No se inventa infraestructura critica ni justificacion operativa.', '',
        '## Tabla de las 30 - escenario oficial actual',
        '| ID | Plataforma | Solape % | Exclusiva m2 | D | V | D+V | Redundancia | Recomendacion |',
        '|---|---|---:|---:|---:|---:|---:|---|---|']
    for r in data['actual']:
        lines.append(f"| {r['ID_POL']} | {r['PLATAFORMA']} | {r['SOLAPE_PREVIO_PCT']:.2f} | {r['AREA_EXCLUSIVA_M2']:.1f} | {r['EVENTOS_D_NUEVOS']} | {r['EVENTOS_V_NUEVOS']} | {r['EVENTOS_DV_NUEVOS']} | {r['REDUNDANCIA']} | {r['DECISION']} |")
    lines += ['', '## Balance conjunto oficial vs prueba',
        '| Categoria | Eventos cubiertos oficial | Eventos cubiertos prueba | Diferencia |',
        '|---|---:|---:|---:|']
    before = data['escenarios']['103+50+30_OFICIAL']
    after = data['escenarios']['103+50+30_PRUEBA']
    for cat in CLASSES:
        a, b = before['incidentes'][cat]['cubiertos'], after['incidentes'][cat]['cubiertos']
        lines.append(f'| {cat} | {a} | {b} | {b-a:+d} |')
    lines += ['', '| Hot Spot urbano | Completos oficial/prueba | Parciales oficial/prueba | Sin cobertura oficial/prueba | Area cubierta oficial/prueba (m2) |',
        '|---|---:|---:|---:|---:|']
    for cat in CLASSES:
        a, b = before['hotspots']['URBANO_' + cat], after['hotspots']['URBANO_' + cat]
        lines.append(f"| {cat} | {a.get('CUBIERTO',0)}/{b.get('CUBIERTO',0)} | {a.get('PARCIALMENTE CUBIERTO',0)}/{b.get('PARCIALMENTE CUBIERTO',0)} | {a.get('SIN COBERTURA',0)}/{b.get('SIN COBERTURA',0)} | {a['area_cubierta_m2']:.1f}/{b['area_cubierta_m2']:.1f} |")
    hd_before, hd_after = before['hotspots']['URBANO_DELINCUENCIA'], after['hotspots']['URBANO_DELINCUENCIA']
    area_change = hd_after['area_cubierta_m2'] - hd_before['area_cubierta_m2']
    lines += ['', f"La mejora de eventos no implica mejora de todas las superficies: el area cubierta de Hot Spots urbanos D cambia {area_change:+.1f} m2; las celdas D completas pasan de {hd_before.get('CUBIERTO',0)} a {hd_after.get('CUBIERTO',0)}. Los niveles Gi* no cambian. Convivencia es complementaria y tambien presenta cambios de superficie. Estas contrapartidas requieren revision antes de aplicar las recomendaciones."]
    lines += ['', '## Recomendaciones iterativas']
    for d in data['decisiones']:
        lines += [f"### {d['ID_POL']} - {d['DECISION']}", d['JUSTIFICACION']]
    lines += ['', '## Plataforma J',
        'La referencia visual no identifica un ID unico. Se auditaron todas las policiales cuyo punto cae en Plataforma J; las cinco mas cercanas a cada una figuran en PLATAFORMA_J_5_CERCANAS.csv.']
    for r in data['actual']:
        if 'PLATAFORMA J' in r['PLATAFORMA']:
            lines.append(f"- {r['ID_POL']}: solape {r['SOLAPE_PREVIO_PCT']:.2f}%; exclusiva {r['AREA_EXCLUSIVA_M2']:.1f} m2; D/V {r['EVENTOS_D_NUEVOS']}/{r['EVENTOS_V_NUEVOS']}; entorno Hot Spot D/V {r['NIVEL_DEL']}%/{r['NIVEL_VIOL']}%; {r['DECISION']}.")
    lines += ['', '## Archivos',
        '- AUDITORIA_30_POLICIA.csv: detalle completo actual, distancias, niveles, areas, beneficios y recomendaciones.',
        '- ALTERNATIVAS_ITERATIVAS.csv: actual + hasta5 alternativas por cada caso revisado, mismo contexto de iteracion.',
        '- DECISIONES.csv: recomendaciones; ESCENARIO_PRUEBA_30.csv: reevaluacion final conjunta del escenario de prueba.',
        '- REDUNDANCIA_POLICIA_30.gpkg: puntos, buffers, exclusivas, superposiciones actuales/prueba y alternativas, EPSG:32717.',
        '- RESULTADOS.json: resultados completos, escenarios y hashes de fuentes.',
        '- index.html: mapa interactivo con tabla completa y comparador actual/prueba.', '',
        '## Validacion',
        '30 policiales en ambos escenarios; areas cuadran; eventos exclusivos cotejados independientemente; reproduce la corrida final; fuentes protegidas conservan sus hashes. Sin commit ni push.']
    (OUT / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def refresh_report():
    """Refresh presentation only from saved GIS results, without rerunning the audit."""
    data = json.loads((OUT / 'RESULTADOS.json').read_text(encoding='utf-8'))
    package = OUT / 'REDUNDANCIA_POLICIA_30.gpkg'
    visual = {name: geojson(records(read_layer(package, name))) for name, _ in pyogrio.list_layers(package)}
    for name, layer, fields in [
        ('EXISTENTES', 'CAMARAS_EXISTENTES_103_FINAL', ('ID_CAMARA', 'REQUIERE_CAMBIO')),
        ('MUNICIPALES', 'PROPUESTA_MUNICIPAL_50_FINAL', ('ID_PROPUESTA',)),
        ('PLATAFORMAS', 'PLATAFORMAS_TERRITORIALES', ('platform_name',)),
        ('CANTON', 'LIMITE_CANTONAL', ())]:
        visual[name] = geojson([(g, {k: p[k] for k in fields}) for g, p in records(read_layer(PACKAGE, layer))])
    hot = [row for cat in CLASSES[:2] for row in records(read_layer(PACKAGE, 'HOTSPOT_' + cat))]
    visual['HOTSPOTS_DV'] = geojson([(g, {k: p[k] for k in ('CELL_ID', 'CATEGORIA', 'NIVEL', 'AMBITO')}) for g, p in hot])
    write_index(visual, data)
    write_report(data)
    with zipfile.ZipFile(OUT / 'REVISION_REDUNDANCIA_POLICIA_30.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in OUT.iterdir():
            if file.is_file() and file.suffix != '.zip':
                archive.write(file, file.name)
    assert all(sha(Path(path)) == digest for path, digest in data['metadata']['fuentes_hash'].items())
    print('Informe y mapa actualizados; calculos y fuentes preservados.')


if __name__ == '__main__':
    refresh_report() if '--refresh-report' in sys.argv else main()
