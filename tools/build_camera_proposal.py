"""Evaluate supplied camera locations; never optimize, relocate or edit source datasets."""
import argparse
import csv
import hashlib
import json
import math
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pyogrio
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import Point, shape, mapping
from shapely.ops import transform, unary_union, nearest_points

from build_remaining_camera_coverage import ROOT, PROTECTED, read_js, load

OUT = ROOT / 'data/seguridad-riobamba/propuesta-camaras-20261002'
CSV = Path('C:/Users/PC/Downloads/PROPUESTA_CAMARAS_RIOBAMBA_200M.csv')
GPKG = Path('D:/codex/exportaciones/INSUMOS_CAMARAS_PROPUESTAS_20261002_CON_ANILLO/INSUMOS_CAMARAS_PROPUESTAS.gpkg')
PROJECT = Transformer.from_crs(4326, 32717, always_xy=True).transform
UNPROJECT = Transformer.from_crs(32717, 4326, always_xy=True).transform
CLASSES = ('DELINCUENCIA', 'VIOLENCIA', 'CONVIVENCIA')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percent(value, total):
    return value / total * 100 if total else None


def feature(geom, props):
    return {'type': 'Feature', 'properties': props, 'geometry': mapping(transform(UNPROJECT, geom))}


def collection(features):
    return {'type': 'FeatureCollection', 'features': features}


def components(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == 'LineString':
        return [geom]
    return [part for child in getattr(geom, 'geoms', []) for part in components(child)]


def problem_level(dv_gi, rate, rate_p66, conv_gi, conv_records):
    if dv_gi >= 95:
        return 'ALTA', 'Gi* delincuencia/violencia >=95%'
    if dv_gi >= 90 or (rate is not None and rate > rate_p66):
        return 'MEDIA', 'Gi* D/V 90% o tasa D/V > P66'
    if conv_gi >= 95 and conv_records > 0:
        return 'MEDIA', 'Gi* convivencia >=95% y convivencia observada en la manzana'
    return ('BAJA', 'Informacion valida sin criterios Alta/Media') if rate is not None else (None, 'Tasa no disponible y sin evidencia Gi*')


def classify(coverage, population_level, problem, low=33, high=66):
    if coverage is None or population_level is None or problem is None:
        return 'SIN EVIDENCIA', 'Informacion insuficiente'
    coverage_level = 'BAJA' if coverage < low else 'PARCIAL' if coverage <= high else 'BUENA'
    supported_population = population_level in ('MEDIA', 'ALTA')
    if coverage_level == 'BAJA' and supported_population and problem == 'ALTA':
        return 'ALTA', 'Baja cobertura + poblacion media/alta + problematica alta'
    if (coverage_level == 'BAJA' and supported_population and problem == 'MEDIA') or (coverage_level == 'PARCIAL' and supported_population and problem == 'ALTA'):
        return 'MEDIA', 'Baja cobertura + poblacion media/alta + problematica media; o parcial + poblacion media/alta + problematica alta'
    return 'BAJA', 'Buena cobertura o situacion evaluada que no cumple Alta/Media'


def write_review(display):
    metadata = display['metadata']
    method = metadata['gapMethod']
    state = display['scenarios']['200']
    actual, future = state['metrics']['actual'], state['metrics']['future']
    def table(headers, rows):
        clean = lambda v: str(v if v is not None else 'No disponible').replace('|', '/').replace('\n', ' ')
        return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] + ['| ' + ' | '.join(clean(v) for v in row) + ' |' for row in rows])
    def n(value, digits=0):
        return 'No disponible' if value is None else f'{value:,.{digits}f}'
    lines = ['# Revision local: propuesta de50 camaras', '', '**SIN COMMIT/PUSH. Revision humana pendiente.**',
        '', '**BRECHAS PROVISIONALES: pendiente revisar atribucion de incidentes en calles a manzanas. No son resultados definitivos para priorizar.**',
        '', '[Abrir visor local](http://127.0.0.1:8767/visor-seguridad-riobamba-v2.html?analysis=cameraProposal)', '',
        '## Control de entrada',
        '-50 propuestas:22 cabeceras,4 Las Abras,24 red estructural.11 parroquias, dos propuestas por SECTOR en cada una.',
        '-103 existentes conservadas:99 con ubicacion aproximada,4 sin geometria. Futuro153 teoricas/149 ubicadas.',
        '-50 coordenadas unicas,48 IDs fuente unicos: dos IDs de San Juan/San Luis se repiten. Se conserva ID_PROP y se identifica cada fila con ID_INTERNO.',
        '-Sin coordenadas0,0. Incidentes y camaras existentes no se desplazan. Propuesta corregida autorizada en CSV separado;22 rurales intactas. CRSmetricoEPSG:32717. Redondeo X/Y vs lon/lat <0.1m.',
        '-Originales y calculos previos verificados por SHA256. No se recalculan KDE, poblacion ni accesibilidad policial. Gi* urbano usa fuente separada100/200m; Gi* rural intacto.',
        '', '## Advertencias',
        f'{len(metadata["outsideCanton"])} propuestas estan fuera del limite cantonal disponible; cabeceras originales no se eliminan ni reasignan:',
        table(['ID_PROP', 'Sector', 'Distancia fuera m'], [[c['ID_PROP'], c['SECTOR'], n(c['distanceOutsideCantonM'], 1)] for c in metadata['outsideCanton']]),
        '', f'Las Abras: los3 archivos originales se conservan completos. Union original={n(metadata["abrasOriginalUnionLengthM"]/1000, 3)}km; evaluacion={n(metadata["abrasLengthAfterUnionM"]/1000, 3)}km; recorte derivado intr cantonal={metadata["abrasInsideCantonOnly"]}; coincidencias descontadas={n(metadata["abrasOverlapRemovedM"]/1000, 3)}km.',
        'Las cabeceras municipales se analizan con XY; las dimensiones Z/M no se usan como distancia ni se modifica el GPKG original.',
        'JUSTIFICACION no existe en CSV: No disponible. HOT_SCORE es un campo externo, no se usa como Gi* ni como ponderacion.',
        'La asignacion por SECTOR no certifica proximidad a cabecera. Se informa cuantas propuestas realmente estan dentro de200m del centro municipal.',
        f'Asignacion estricta de incidentes: {metadata["eventAssignment"]["byScope"]["URBANO"]["withoutBlock"]} de {metadata["eventAssignment"]["byScope"]["URBANO"]["total"]} registros urbanos no intersectan una manzana. Fuera de manzana no significa ausencia de eventos: pueden estar en calles. Estos registros SI participan en Gi* y cobertura de incidentes; no se fuerzan a centroides o a la manzana mas cercana.',
        '', '## Percentiles fijos y reglas',
        f'P33 poblacion={method["populationP33"]}; P66 poblacion={method["populationP66"]}; N={method["populationPercentileN"]}.',
        f'P33 incidencia={method["incidenceP33"]}; P66 incidencia={method["incidenceP66"]}; N={method["incidencePercentileN"]}. Incidencia=D/V por1000 habitantes de cada manzana, no anualizada.',
        'P66=0 refleja en gran parte la atribucion estricta incompleta, NO ausencia territorial de D/V. Se muestran percentiles y clasificacion como validacion provisional; no deben usarse como brecha definitiva hasta revisar la asociacion calle/manzana.',
        'Umbrales de cobertura33/66% configurables. Reglas booleanas; no AHP, sumas ponderadas ni indice de riesgo. Poblacion y problematica constantes entre comparaciones.',
        'Gi* D/V asociado por interseccion de area positiva con el poligono, maximo nominal95/99% ->problematica alta;90% o tasa>P66 ->media. Convivencia>=95% con evento propio puede ser media, nunca alta por si sola.',
        'Ver METODOLOGIA_BRECHAS.md para reglas, fuentes, datos faltantes y limitaciones. Manzanas rurales conservadas como SIN EVIDENCIA para estas reglas urbanas.',
        '', '## Validacion de brechas',
        table(['Radio', 'Actual alta', 'Actual media', 'Actual baja', 'Sin evidencia', 'Futura alta', 'Futura media', 'Futura baja', 'Sin evidencia futura'],
              [[v['radius'], v['actual']['ALTA'], v['actual']['MEDIA'], v['actual']['BAJA'], v['actual']['SIN EVIDENCIA'], v['future']['ALTA'], v['future']['MEDIA'], v['future']['BAJA'], v['future']['SIN EVIDENCIA']] for v in display['gapValidation']]),
        '', '##10 ejemplos, escenario200m',
        table(['Manzana', 'Cob.actual%', 'Cob.futura%', 'Poblacion/nivel', 'Problematica', 'Hotspot D/V%', 'Regla actual', 'Cambio'],
              [[r['ID_MANZANA'], n(r['COB_ACTUAL_200'], 2), n(r['COB_FUTURE_200'], 2), f'{r["POBLACION"]}/{r["POBLACION_NIVEL"]}', r['PROBLEMATICA'], r['GI_DV_NIVEL'], r['REGLA_ACTUAL_200'], r['CAMBIO_BRECHA_200']] for r in display['gapExamples']]),
        '', 'Los mismos10 ejemplos con100/150m estan disponibles en el visor y VALIDACION_Y_COMPARACION.json.',
        '', '## Impacto a200m',
        table(['Indicador', 'Actual', 'Actual+50', 'Diferencia'],
              [['Area urbana cubierta km2', n(actual['coveredUrbanAreaKm2'], 3), n(future['coveredUrbanAreaKm2'], 3), n(future['coveredUrbanAreaKm2']-actual['coveredUrbanAreaKm2'], 3)],
               ['Area urbana cubierta%', n(actual['coveredAreaPct'], 2), n(future['coveredAreaPct'], 2), n(future['coveredAreaPct']-actual['coveredAreaPct'], 2)+'p.p.'],
               ['Poblacion urbana cubierta estimada', n(actual['populationCovered']), n(future['populationCovered']), n(future['populationCovered']-actual['populationCovered'])],
               ['Poblacion urbana cubierta%', n(actual['populationPct'], 2), n(future['populationPct'], 2), n(future['populationPct']-actual['populationPct'], 2)+'p.p.'],
               ['Manzanas brecha alta', actual['gapCounts']['ALTA'], future['gapCounts']['ALTA'], future['gapCounts']['ALTA']-actual['gapCounts']['ALTA']],
               ['Poblacion en manzanas brecha alta', n(actual['gapPopulation'].get('ALTA', 0)), n(future['gapPopulation'].get('ALTA', 0)), n(future['gapPopulation'].get('ALTA', 0)-actual['gapPopulation'].get('ALTA', 0))]]),
        '', f'Poblacion analizada={n(actual["populationAnalyzed"], 2)}; estimacion areal de las manzanas con dato en la union18 Plataformas. Poblacion por clase de brecha es poblacion completa de las manzanas: denominadores diferentes, no se confunden.',
        '', '## Corredores200m',
        table(['Corredor', 'Total km', 'Actual km', 'Futuro km', '%actual', '%futuro', 'Vacio restante km', 'Segmentos'],
              [[c['corridor'], n(c['totalM']/1000, 3), n(c['actualCoveredM']/1000, 3), n(c['futureCoveredM']/1000, 3), n(c['actualPct'], 2), n(c['futurePct'], 2), n(c['uncoveredM']/1000, 3), c['uncoveredSegments']] for c in state['corridors']]),
        '', '## Incidentes200m',
        table(['Categoria', 'Registros', 'Cubiertos actual', '%actual', 'Cubiertos futuro', '%futuro'],
              [[k, actual['incidents'][k]['total'], actual['incidents'][k]['covered'], n(actual['incidents'][k]['pct'], 2), future['incidents'][k]['covered'], n(future['incidents'][k]['pct'], 2)] for k in CLASSES]),
        '', 'Peso1 por observacion real, no por Emergencias. ACTIVIDAD_INSTITUCIONAL/OTROS_REVISION excluidos. Toda la base clasificada, no solo el ambito urbano.',
        '', '## Hotspots por ambito/categoria200m',
        table(['Ambito/categoria', 'Total', 'Con interseccion actual', 'Con interseccion futura', 'Sin cobertura futura', '%area futura cubierta'],
              [[k, v['actual']['total'], v['actual']['withCoverage'], v['future']['withCoverage'], v['future']['uncovered'], n(v['future']['pctAreaCovered'], 2)] for k, v in state['hotspots'].items()]),
        '', 'Una interseccion positiva no significa cobertura completa de la celda. Gi* urbano nuevo100/200m; rural original intacto. Significancia nominal bilateral sin FDR; rural exploratorio.',
        '', '## Cabeceras200m',
        table(['Parroquia', 'Existentes en parroquia', 'Propuestas porSECTOR', 'Total teorico asignado', 'Propuestas<=200m centro', '%entorno actual', '%entorno futuro'],
              [[c['parish'], c['existingInOperativeParish'], c['proposedAssignedBySector'], c['theoreticalFutureInAssignedParish'], c['proposedWithin200mOfCenter'], n(c['actualCoveragePctWithin200m'], 2), n(c['futureCoveragePctWithin200m'], 2)] for c in state['cabeceras']]),
        '', 'Entorno de referencia fijo200m del punto municipal. El radio de evaluacion de camaras cambia100/150/200m sin cambiar este denominador.',
        '', '## Posibles redundancias y sectores pendientes',
        f'{len(display["redundancies"])} propuestas con>=95% de solapamiento de su disco200m con las demas camaras. Umbral descriptivo: no se certifica redundancia ni este indicador mueve puntos automaticamente.',
        f'{len(state["voids"]["features"])} segmentos permanecen sin cobertura futura200m; estan listados en el visor y exportados con camara mas cercana y distancia.',
        'Hotspots sin cobertura: identificables por COB_FUTURE_200=0 en las seis capas independientes y listados en el visor. Los corredores, manzanas y celdas no se mezclan como si fueran una sola unidad.',
        '', '## Entregables y archivos modificados',
        '-visor-seguridad-riobamba-v2.html: entrada del modulo y adaptador de interfaz; se mantiene el formato y los analisis previos.',
        '-riobamba-camaras-propuesta.js / .css: mapa, controles, fichas, comparaciones, tablas y metodologia del modulo nuevo.',
        '-tools/build_camera_proposal.py: calculos reproducibles desde fuentes originales, tres ejes Las Abras.',
        '-tools/test_camera_proposal.py: limites33/66%, faltantes, convivencia, hashes, coordenadas, union/radios, monotonia, reglas y CRS/cuentasGPKG.',
        '-riobamba-hotspot-urbano-200m-data.js y tools/build_urban_gi_200.py: tres categorias urbanas100/200m; fuentes rurales no sobrescritas.',
        '-riobamba-cantonal-view.js: etiquetas urbanas100/200m; logica rural sin modificaciones.',
        '-tools/audit_incident_block_assignment.py / test_incident_block_audit.py: distancias y mapa de control; sin asignaciones nearest.',
        '-tools/refine_camera_corridors.py / test_urban_gi_corridors.py: correccion versionada y verificacion de fuentes, Gi*, longitudes y rural intacto.',
        '-data/seguridad-riobamba/hotspot-urbano-200m-20261002/, auditoria-calles-manzanas-20261002/ y correccion-propuesta-corredores-20261002/: comparaciones, auditoria y nueva propuesta.',
        '-data/seguridad-riobamba/propuesta-camaras-20261002/: capasGeoJSON, GeoPackage, auditorias, resultados, metodologia e informe.',
        '-Capturas de mapas actual/propuesto/futuro200m, Las Abras y movil: D:/codex/evaluacion-camaras-20261002/.',
        '', 'El visor contiene los mapas50,103 inventariadas(99 ubicadas),153 teoricas(149 ubicadas), cobertura200m y sensibilidad100/150m, las4 redes, vacios, seisHotspots, incidentes por clase, brechas antes/despues, tabla comparativa y listas de revision.',
        'Las capasGIS estan en EVALUACION_PROPUESTA_CAMARAS.gpkg, CRS32717; conteos en AUDITORIA_CAPAS.json. README.md describe fuentes y campos.',
        '', '## Validacion y limitaciones',
        'Pruebas de reglas/geometria ejecutadas por tools/test_camera_proposal.py. Cobertura futura contiene la actual; no aumenta ninguna brecha. Cambios de radio/escenario verificables en el visor con KPI, mapa, tablas y fichas.',
        'La cobertura es geometrica potencial, no visibilidad real ni cobertura funcional garantizada. Las ubicaciones existentes son aproximadas, los nuevos criterios provienen de CSV externo y requieren revision de campo.',
        '', '**Detenido para revision. Incidentes, manzanas, camaras existentes y22 rurales originales intactos. Reubicaciones propuestas autorizadas en CSV versionado; sin commit/push.**']
    if display.get('refinement'):
        refinement = display['refinement']
        lines += ['', '## Correccion de corredores, radio200m',
            table(['Corredor', 'Total km', '%actual', '%propuesta original', '%corregida', 'Sin cobertura km'],
                [[r['corridor'], n(r['totalM']/1000, 3), n(r['actualPct'], 2), n(r['originalProposalPct'], 2), n(r['correctedProposalPct'], 2), n(r['uncoveredCorrectedM']/1000, 3)] for r in refinement['corridors']]),
            '', f'Reubicaciones: {dict(Counter(r["TIPO"] for r in refinement["movements"]))}. Las22 rurales conservan todos sus valores originales. La lista y coordenadas anteriores/nuevas se incluyen en el visor.',
            table(['ID', 'Tipo', 'X anterior', 'Y anterior', 'X nueva', 'Y nueva', 'Desplazamiento m'],
                [[r['ID_PROP'],r['TIPO'],n(r['oldX'],3),n(r['oldY'],3),n(r['newX'],3),n(r['newY'],3),n(r['movementM'],2)] for r in refinement['movements']]),
            '', 'Seleccion discreta de cruces GIS con solver HiGHS; muestreo10m solo para seleccion. Longitudes finales calculadas por interseccion exacta, no por proximidad de camaras.',
            'La separacion300-350m se evalua como preferencia secundaria de continuidad, sin sacrificar la longitud cubierta del anillo ni reducir cobertura total Macaji/ciclovias. No se certifica continuidad total: se muestran vacios reales.',
            str(refinement['urbanSolver'])]
    gi_validation = OUT.parent / 'hotspot-urbano-200m-20261002' / 'VALIDACION_COMPARACION.json'
    if gi_validation.exists() and metadata['urbanHotspotDistanceM'] == 200:
        gi_rows = json.loads(gi_validation.read_text(encoding='utf-8'))['comparison']
        lines += ['', '## Gi* urbano200m: conteos y comparacion',
            '[Comparacion cartografica de las tres categorias](../hotspot-urbano-200m-20261002/comparacion.html)',
            table(['Categoria', 'Eventos', 'Hot99', 'Hot95', 'Hot90', 'Area anterior km2', 'Area nueva km2', 'Interseccion/union %'],
                [[r['category'], r['records'], r['newLevels'].get('HOTSPOT 99%', 0), r['newLevels'].get('HOTSPOT 95%', 0), r['newLevels'].get('HOTSPOT 90%', 0), n(r['oldHotAreaKm2'], 3), n(r['newHotAreaKm2'], 3), n(r['hotAreaIoUPct'], 2)] for r in gi_rows]),
            'Cambian simultaneamente malla250->100m y distancia500->200m. Los conteos de celdas no son directamente comparables. Rural conserva exactamente sus fuentes y parametros.']
    if display.get('previousEvaluation'):
        old_hotspots = display['previousEvaluation']['scenarios']['200']['hotspots']
        lines += ['', '## Efecto Gi* urbano sobre la evaluacion200m',
            table(['Categoria', '%area hot actual anterior', '%actual nueva', '%futura anterior', '%futura corregida'],
                [[k.removeprefix('URBANO_'), n(old_hotspots[k]['actual']['pctAreaCovered'], 2), n(v['actual']['pctAreaCovered'], 2), n(old_hotspots[k]['future']['pctAreaCovered'], 2), n(v['future']['pctAreaCovered'], 2)] for k, v in state['hotspots'].items() if k.startswith('URBANO_')]),
            'Actual usa las mismas99 ubicaciones: cambia el soporte/distancia Gi*. Futura incorpora ademas la reubicacion autorizada de propuestas. No atribuir toda diferencia a una sola causa.',
            '[Auditoria de incidentes sin asignar, sin alterar coordenadas](../auditoria-calles-manzanas-20261002/mapa-auditoria.html)']
    (OUT / 'INFORME_REVISION.md').write_text('\n\n'.join(lines), encoding='utf-8')
    with zipfile.ZipFile(OUT / 'EVALUACION_PROPUESTA_CAMARAS.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ('EVALUACION_PROPUESTA_CAMARAS.gpkg', 'README.md', 'METODOLOGIA_BRECHAS.md', 'INFORME_REVISION.md',
                     'AUDITORIA_INPUT.json', 'AUDITORIA_CAPAS.json', 'VALIDACION_Y_COMPARACION.json'):
            archive.write(OUT / name, name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--abras', type=Path, nargs='+', required=True, help='User-selected existing axes, never reconstructed.')
    parser.add_argument('--proposal', type=Path, default=CSV, help='Versioned proposal CSV; original uploaded CSV is never overwritten.')
    parser.add_argument('--abras-cantonal', action='store_true', help='Derived evaluation axis inside canton; originals stay complete.')
    parser.add_argument('--coverage-low', type=float, default=33)
    parser.add_argument('--coverage-high', type=float, default=66)
    args = parser.parse_args()
    assert 0 <= args.coverage_low < args.coverage_high <= 100
    protected = {name: sha(ROOT / name) for name in PROTECTED}
    source_files = [args.proposal, CSV, GPKG] + [p for axis in args.abras for p in sorted(axis.parent.glob(axis.stem + '.*')) if p.suffix.lower() not in ('.lock', '.lck')]
    if (ROOT/'riobamba-hotspot-urbano-200m-data.js').exists():
        source_files.append(ROOT/'riobamba-hotspot-urbano-200m-data.js')
    source_hashes = {str(path): sha(path) for path in source_files}
    with args.proposal.open(encoding='utf-8-sig', newline='') as stream:
        original = list(csv.DictReader(stream))
    counts = Counter(row['TIPO'] for row in original)
    expected = {'CABECERA_RURAL': 22, 'QUEBRADA_LAS_ABRAS': 4, 'CORREDOR_ESTRUCTURAL': 24}
    assert len(original) == 50 and dict(counts) == expected, f'DETENER: distribucion incorrecta: {counts}'
    rural_counts = Counter(row['SECTOR'] for row in original if row['TIPO'] == 'CABECERA_RURAL')
    assert len(rural_counts) == 11 and set(rural_counts.values()) == {2}
    OUT.mkdir(parents=True, exist_ok=True)
    baseline_file = OUT/'EVALUACION_ANTERIOR_RESUMEN.json'
    if args.proposal != CSV and not baseline_file.exists() and (OUT/'RESULTADOS.json').exists():
        previous = json.loads((OUT/'RESULTADOS.json').read_text(encoding='utf-8'))
        baseline_file.write_text(json.dumps({'metadata': previous['metadata'], 'gapValidation': previous['gapValidation'],
            'scenarios': {radius: {key: state[key] for key in ('metrics', 'hotspots', 'corridors')} for radius, state in previous['scenarios'].items()}}, indent=2), encoding='utf-8')
    territory = read_js('riobamba-cantonal-data.js')
    correction = read_js('riobamba-conflictividad-data.js')
    canton = transform(PROJECT, shape(territory['canton']['geometry']))
    platforms = load('riobamba-censo-data/riobamba_plataformas.geojson')
    urban = unary_union([transform(PROJECT, shape(f['geometry'])) for f in platforms['features']])
    proposal_points, proposed, duplicates = [], [], defaultdict(list)
    for n, row in enumerate(original, 1):
        x, y, lon, lat = [float(row[key]) for key in ('X', 'Y', 'LONGITUD', 'LATITUD')]
        assert all(math.isfinite(v) for v in (x, y, lon, lat)) and (x, y) != (0, 0)
        point = Point(x, y)
        assert point.is_valid and -180 <= lon <= 180 and -90 <= lat <= 90
        xy_error = math.hypot(x-PROJECT(lon, lat)[0], y-PROJECT(lon, lat)[1])
        assert xy_error < .1, f'CRS incoherente: {row["ID_PROP"]}'
        camera = {**row, 'id': f'PROP_CSV_{n:03d}', 'sourceRow': n+1, 'X': x, 'Y': y,
                  'lng': lon, 'lat': lat, 'designRadius': 200, 'JUSTIFICACION': row.get('JUSTIFICACION'),
                  'insideCanton': canton.covers(point), 'distanceOutsideCantonM': canton.distance(point),
                  'xyLatLngDifferenceM': xy_error}
        duplicates[row['ID_PROP']].append({'row': n+1, 'sector': row['SECTOR']})
        proposal_points.append(point)
        proposed.append(camera)
    assert len({(p.x, p.y) for p in proposal_points}) == 50, 'DETENER: puntos exactamente duplicados; revisar fuente.'
    duplicate_ids = {key: rows for key, rows in duplicates.items() if len(rows) > 1}
    inventory = read_js('riobamba-camaras-inventario-data.js')['cameras']
    located = [c for c in inventory if c.get('lng') is not None and c.get('lat') is not None]
    actual_points = [Point(PROJECT(c['lng'], c['lat'])) for c in located]
    all_points = actual_points + proposal_points
    all_ids = [c['id'] for c in located] + [c['id'] for c in proposed]
    assert len(inventory) == 103 and len(located) == 99 and len(all_points) == 149
    corridors = {}
    corridor_features = []
    for key in ('BOULEVARD_MACAJI_BELLAVISTA', 'CICLOVIAS', 'ANILLO_VIAL'):
        frame = pyogrio.read_dataframe(GPKG, layer=key).to_crs(32717)
        corridors[key] = unary_union(frame.geometry)
        corridor_features += [feature(g, {'TIPO_CORREDOR': key}) for g in frame.geometry]
    abras_geoms, abras_sources = [], []
    for axis in args.abras:
        abras = pyogrio.read_dataframe(axis).to_crs(32717)
        abras_geoms.extend(abras.geometry)
        abras_sources.append({'source': str(axis), 'records': len(abras), 'originalLengthM': sum(abras.geometry.length)})
        corridor_features += [feature(g, {'TIPO_CORREDOR': 'QUEBRADA_LAS_ABRAS', 'FUENTE_TRAMO': axis.name}) for g in abras.geometry]
    corridors['QUEBRADA_LAS_ABRAS'] = unary_union(abras_geoms)
    abras_original_length = corridors['QUEBRADA_LAS_ABRAS'].length
    if args.abras_cantonal:
        corridors['QUEBRADA_LAS_ABRAS'] = corridors['QUEBRADA_LAS_ABRAS'].intersection(canton)
        corridor_features = [f for f in corridor_features if f['properties']['TIPO_CORREDOR'] != 'QUEBRADA_LAS_ABRAS']
        corridor_features += [feature(g, {'TIPO_CORREDOR': 'QUEBRADA_LAS_ABRAS', 'AMBITO': 'RECORTE_DERIVADO_DENTRO_CANTON'}) for g in components(corridors['QUEBRADA_LAS_ABRAS'])]
    # Population and observed incidence are fixed across every radius and scenario.
    block_features = load('riobamba-censo-data/riobamba_manzanas.geojson')['features']
    block_geoms = [transform(PROJECT, shape(f['geometry'])) for f in block_features]
    block_tree = STRtree(block_geoms)
    pop_source = load('riobamba-censo-data/riobamba_manzanas_stats.json')['byMan']
    ownership = load('riobamba-censo-data/riobamba_plataformas_stats.json')['manToPlatform']
    records = []
    for event in read_js('visor-seguridad-riobamba-data.js')['events']:
        category = correction['dictionary'][event['subtype']]
        if category in CLASSES:
            records.append({**event, 'category': category, 'point': Point(PROJECT(event['lng'], event['lat']))})
    block_events = [Counter() for _ in block_geoms]
    multi_block_events, unassigned_events = [], 0
    assignment_scopes = {key: {'total': 0, 'withBlock': 0, 'withoutBlock': 0} for key in ('URBANO', 'EXTERNO')}
    for event in records:
        hits = block_tree.query(event['point'], predicate='intersects').tolist()
        scope = 'URBANO' if urban.covers(event['point']) else 'EXTERNO'
        assignment_scopes[scope]['total'] += 1
        assignment_scopes[scope]['withBlock' if hits else 'withoutBlock'] += 1
        if not hits:
            unassigned_events += 1
            continue
        # Boundary/overlap ties get one reproducible owner; never count a row twice.
        owner = min(hits, key=lambda i: block_features[i]['properties']['man'])
        if len(hits) > 1:
            multi_block_events.append(event['id'])
        block_events[owner][event['category']] += 1
    urban_gi = read_js('riobamba-hotspot-urbano-200m-data.js') if (ROOT/'riobamba-hotspot-urbano-200m-data.js').exists() else None
    grid_sources = {'URBANO': urban_gi['grid'] if urban_gi else read_js('riobamba-incidentes-spatial-data.js')['giGrid'], 'RURAL': territory['ruralGrid']}
    hotspot_rows, hotspot_geoms, dv_hot, conv_hot = [], [], [], []
    for scope, grid in grid_sources.items():
        for category in CLASSES:
            gi_source = urban_gi['byClass'][category] if scope == 'URBANO' and urban_gi else correction['gi'][scope][category]
            for cell, result in zip(grid['cells'], gi_source['results']):
                if not result['GI_CLASS'].startswith('HOTSPOT'):
                    continue
                level = int(result['GI_CLASS'].split()[1].rstrip('%'))
                geom = transform(PROJECT, shape(cell['geometry']))
                row = {'id': f'{scope}-{category}-{cell["cellId"]}', 'CELL_ID': cell['cellId'], 'scope': scope,
                       'category': category, 'level': level, **result}
                hotspot_rows.append(row)
                hotspot_geoms.append(geom)
                if scope == 'URBANO':
                    (conv_hot if category == 'CONVIVENCIA' else dv_hot).append((geom, level))
    dv_tree = STRtree([g for g, _ in dv_hot])
    conv_tree = STRtree([g for g, _ in conv_hot])
    urban_block_hotspots = {r['ID_MANZANA']: r for r in urban_gi['blockIndicators']} if urban_gi else {}
    fixed = []
    for n, (f, geom) in enumerate(zip(block_features, block_geoms)):
        code = f['properties']['man']
        population = pop_source.get(code, {}).get('population_total')
        valid_population = population is not None and math.isfinite(float(population)) and population >= 0
        urban_part = geom.intersection(urban)
        urban_block = urban_part.area > .01
        rate = (block_events[n]['DELINCUENCIA']+block_events[n]['VIOLENCIA'])/population*1000 if valid_population and population > 0 else None
        dv_level = max([dv_hot[i][1] for i in dv_tree.query(geom, predicate='intersects')
                        if geom.intersection(dv_hot[i][0]).area > .01] or [0]) if urban_block else None
        conv_level = max([conv_hot[i][1] for i in conv_tree.query(geom, predicate='intersects')
                          if geom.intersection(conv_hot[i][0]).area > .01] or [0]) if urban_block else None
        fixed.append({'ID_MANZANA': code, 'POBLACION': population if valid_population else None,
                      **{field: urban_block_hotspots.get(code, {}).get(field) for field in ('HOTSPOT_DEL', 'HOTSPOT_VIOL', 'HOTSPOT_CONV')},
                      'ESTADO_METODOLOGIA': 'PROVISIONAL_ASIGNACION_INCIDENTES',
                      'PLATAFORMA': ownership.get(code), 'URBANA_OPERATIVA': urban_block,
                      'TASA_DV_1000': rate, 'GI_DV_NIVEL': dv_level, 'GI_CONV_NIVEL': conv_level,
                      'N_DELINCUENCIA': block_events[n]['DELINCUENCIA'], 'N_VIOLENCIA': block_events[n]['VIOLENCIA'],
                      'N_CONVIVENCIA': block_events[n]['CONVIVENCIA'], 'URBAN_FRACTION': urban_part.area/geom.area})
    valid_urban = [r for r in fixed if r['URBANA_OPERATIVA'] and r['POBLACION'] is not None]
    pop_p33, pop_p66 = np.percentile([r['POBLACION'] for r in valid_urban], [33, 66], method='linear').tolist()
    incidence = [r['TASA_DV_1000'] for r in valid_urban if r['TASA_DV_1000'] is not None]
    inc_p33, inc_p66 = np.percentile(incidence, [33, 66], method='linear').tolist()
    for row in fixed:
        p = row['POBLACION']
        row['POBLACION_NIVEL'] = None if p is None else 'BAJA' if p < pop_p33 else 'ALTA' if p > pop_p66 else 'MEDIA'
        if row['URBANA_OPERATIVA']:
            row['PROBLEMATICA'], row['PROBLEMATICA_REGLA'] = problem_level(row['GI_DV_NIVEL'], row['TASA_DV_1000'], inc_p66,
                                                                         row['GI_CONV_NIVEL'], row['N_CONVIVENCIA'])
        else:
            row['PROBLEMATICA'], row['PROBLEMATICA_REGLA'] = None, 'Fuera del ambito urbano de los percentiles'
    metadata = {'generatedAt': datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'), 'crs': 'EPSG:32717',
        'designRadius': 200, 'radii': [100, 150, 200], 'inventoried': 103, 'locatedExisting': 99, 'proposed': 50,
        'theoreticalFuture': 153, 'locatedFuture': 149, 'pendingExistingIds': [c['id'] for c in inventory if c not in located],
        'distribution': dict(counts), 'duplicateSourceIds': duplicate_ids,
        'outsideCanton': [{k:c[k] for k in ('id', 'ID_PROP', 'SECTOR', 'distanceOutsideCantonM')} for c in proposed if not c['insideCanton']],
        'coordinateAuthority': 'X/Y metricos originales del CSV; latitud/longitud originales se conservan para trazabilidad. Diferencia maxima de redondeo <0.1m.',
        'maxCoordinateDifferenceM': max(c['xyLatLngDifferenceM'] for c in proposed), 'source': str(args.proposal), 'originalSource': str(CSV), 'sourceHashes': source_hashes,
        'proposalCorrected': args.proposal != CSV,
        'urbanHotspotDistanceM': urban_gi['metadata']['HOTSPOT_URBANO_DISTANCE_M'] if urban_gi else 500,
        'urbanHotspotCellM': urban_gi['grid']['cellSize'] if urban_gi else 250,
        'ruralHotspotDistanceM': territory['ruralGrid']['neighborDistance'],
        'protectedHashes': protected, 'abrasSources': abras_sources, 'abrasLengthAfterUnionM': corridors['QUEBRADA_LAS_ABRAS'].length,
        'abrasOverlapRemovedM': sum(r['originalLengthM'] for r in abras_sources)-abras_original_length,
        'abrasOriginalUnionLengthM': abras_original_length, 'abrasInsideCantonOnly': args.abras_cantonal,
        'gapMethod': {'name': 'BRECHAS DE COBERTURA Y PRIORIDAD TERRITORIAL',
        'validationStatus': 'PROVISIONAL_ASIGNACION_INCIDENTES',
        'coverageLow': args.coverage_low, 'coverageHigh': args.coverage_high, 'populationP33': pop_p33, 'populationP66': pop_p66,
        'incidenceP33': inc_p33, 'incidenceP66': inc_p66, 'populationPercentileN': len(valid_urban), 'incidencePercentileN': len(incidence),
        'incidenceDefinition': '(DELINCUENCIA+VIOLENCIA)/poblacion de la manzana *1000; poblacion0 -> tasa no disponible',
        'percentileMethod': 'Percentiles 33 y66 con interpolacion lineal; fijos entre radios y escenarios', 'weighted': False},
        'eventAssignment': {'boundaryOrOverlapTies': len(multi_block_events), 'withoutBlock': unassigned_events,
            'byScope': assignment_scopes,
            'rule': 'Interseccion punto/poligono original; empates al menor ID_MANZANA, una sola asignacion'},
        'redundancyScreening': {'radiusM': 200, 'overlapPctThreshold': 95,
            'rule': 'Porcentaje del disco individual intersectado por union de las demas camaras, excluyendo la propia',
            'interpretation': 'Senal descriptiva para revision; no certifica redundancia operativa'},
        'limitations': ['Cobertura potencial geometrica, no visibilidad garantizada ni operatividad comprobada.',
            '99 camaras existentes tienen ubicacion aproximada; cuatro registros no generan buffers.',
            'Poblacion estimada arealmente solo en manzanas urbanas con dato; no representa poblacion rural total.',
            'Gi* nominal bilateral sin FDR; rural exploratorio por escasez de eventos y exceso de ceros.',
            'Brechas por reglas operativas de este estudio, no peligrosidad ni metodologia universal.',
            'Dos IDs fuente se repiten; se conservan y se usa clave interna por fila, sin duplicar ni perder puntos.',
            f'{sum(not c["insideCanton"] for c in proposed)} propuestas fuera del limite cantonal disponible; cabeceras originales conservadas. Cambios autorizados de red estructural/Las Abras en version separada.',
            'Los tres archivos de Las Abras tienen partes coincidentes; se conservan todos y la longitud se mide en su union.',
            'P33/P66 de incidencia D/V son cero: un evento positivo puede activar problematica media. No se reajustan los percentiles.',
            f'{assignment_scopes["URBANO"]["withoutBlock"]} de {assignment_scopes["URBANO"]["total"]} incidentes urbanos no intersectan manzana: tasa y brecha provisionales, pendiente validar atribucion de calles.',
            'JUSTIFICACION no figura en el CSV: No disponible, sin inventar texto. HOT_SCORE no sustituye resultados Gi* propios.']}
    cabin = pyogrio.read_dataframe(GPKG, layer='CABECERAS_PARROQUIALES_RURALES').to_crs(32717)
    parishes = {f['properties']['name']: transform(PROJECT, shape(f['geometry'])) for f in territory['parishes']['features']}
    scenarios, gpkg_layers, gap_examples, validation = {}, {}, [], []
    for radius in (100, 150, 200):
        actual = unary_union([p.buffer(radius, quad_segs=64) for p in actual_points])
        new = unary_union([p.buffer(radius, quad_segs=64) for p in proposal_points])
        future = actual.union(new)
        geometries = {'actual': actual, 'proposals': new, 'future': future}
        assert all(g.is_valid for g in geometries.values()) and actual.difference(future).area < .001
        result = {'coverage': {key: feature(g, {'scenario': key, 'radius_m': radius}) for key, g in geometries.items()},
                  'metrics': {}, 'corridors': [], 'hotspots': {}, 'cabeceras': []}
        ring = corridors['ANILLO_VIAL']
        result['ringSegments'] = {key: collection([feature(g, {'scenario': key, 'status': status, 'lengthM': g.length})
                for status, geom in (('CUBIERTO', ring.intersection(coverage)), ('SIN_COBERTURA', ring.difference(coverage)))
                for g in components(geom)]) for key, coverage in (('actual', actual), ('future', future))}
        if radius == 200:
            for key, coverage in (('actual', actual), ('future', future)):
                for suffix, geom in (('CUBIERTO', ring.intersection(coverage)), ('SIN_COBERTURA', ring.difference(coverage))):
                    name = f'ANILLO_VIAL_{suffix}' if key == 'future' else f'ACTUAL_ANILLO_VIAL_{suffix}'
                    parts = components(geom)
                    gpkg_layers[name] = gpd.GeoDataFrame([{'ESCENARIO': key, 'RADIO_M': 200, 'LONGITUD_M': g.length} for g in parts], geometry=parts, crs=32717)
        for key, coverage in geometries.items():
            population_covered, population_total = 0., 0.
            gap_counts, gap_population = Counter(), defaultdict(float)
            for row, geom in zip(fixed, block_geoms):
                fraction = min(1., max(0., geom.intersection(coverage).area/geom.area))
                row[f'COB_{key.upper()}_{radius}'] = fraction*100
                applicable = row['URBANA_OPERATIVA']
                level, rule = classify(fraction*100 if applicable else None, row['POBLACION_NIVEL'], row['PROBLEMATICA'], args.coverage_low, args.coverage_high)
                row[f'BRECHA_{key.upper()}_{radius}'] = level
                if key in ('actual', 'future'):
                    row[f'REGLA_{key.upper()}_{radius}'] = rule
                if applicable:
                    gap_counts[level] += 1
                    if row['POBLACION'] is not None:
                        population_total += row['POBLACION']*row['URBAN_FRACTION']
                        population_covered += row['POBLACION']*geom.intersection(urban).intersection(coverage).area/geom.area
                        gap_population[level] += row['POBLACION']
            event_stats = {}
            for category in CLASSES:
                items = [e for e in records if e['category'] == category]
                covered = sum(coverage.covers(e['point']) for e in items)
                event_stats[category] = {'total': len(items), 'covered': covered, 'pct': percent(covered, len(items))}
            result['metrics'][key] = {'urbanAreaKm2': urban.area/1e6, 'coveredUrbanAreaKm2': urban.intersection(coverage).area/1e6,
                'coveredAreaPct': percent(urban.intersection(coverage).area, urban.area), 'fullDissolvedAreaKm2': coverage.area/1e6,
                'populationAnalyzed': population_total, 'populationCovered': population_covered, 'populationPct': percent(population_covered, population_total),
                'incidents': event_stats, 'gapCounts': {level: gap_counts[level] for level in ('ALTA', 'MEDIA', 'BAJA', 'SIN EVIDENCIA')},
                'gapPopulation': dict(gap_population), 'gapBlocks': sum(gap_counts.values())}
            export_name = 'PROPUESTAS' if key == 'proposals' else key.upper()
            gpkg_layers[f'BUFFER_{export_name}_{radius}M'] = gpd.GeoDataFrame([{'ESCENARIO': key, 'RADIO_M': radius}], geometry=[coverage], crs=32717)
        vacios = []
        for corridor, axis in corridors.items():
            total = axis.length
            current_length = axis.intersection(actual).length
            future_length = axis.intersection(future).length
            segments = components(axis.difference(future))
            for n, segment in enumerate(segments, 1):
                index = min(range(len(all_points)), key=lambda i: segment.distance(all_points[i]))
                props = {'ID': f'{corridor}-{radius}-{n}', 'TIPO_CORREDOR': corridor, 'LONGITUD_M': segment.length,
                         'COBERTURA': 'SIN_COBERTURA_POTENCIAL', 'CAMARA_CERCANA': all_ids[index], 'DIST_CAMARA': segment.distance(all_points[index])}
                vacios.append((segment, props))
            result['corridors'].append({'corridor': corridor, 'totalM': total, 'actualCoveredM': current_length,
                'futureCoveredM': future_length, 'actualPct': percent(current_length, total), 'futurePct': percent(future_length, total),
                'uncoveredM': axis.difference(future).length, 'uncoveredSegments': len(segments)})
        result['voids'] = collection([feature(g, props) for g, props in vacios])
        gpkg_layers[f'VACIOS_COBERTURA_{radius}M'] = gpd.GeoDataFrame([props for _, props in vacios], geometry=[g for g, _ in vacios], crs=32717)
        for scope in ('URBANO', 'RURAL'):
            for category in CLASSES:
                indexes = [i for i, r in enumerate(hotspot_rows) if r['scope'] == scope and r['category'] == category]
                stats = {}
                for key, coverage in geometries.items():
                    parts = [hotspot_geoms[i].intersection(coverage).area/hotspot_geoms[i].area for i in indexes]
                    stats[key] = {'total': len(parts), 'withCoverage': sum(p > 1e-8 for p in parts),
                                  'fullyCovered': sum(p >= .999999 for p in parts), 'partiallyCovered': sum(1e-8 < p < .999999 for p in parts),
                                  'uncovered': sum(p <= 1e-8 for p in parts), 'pctAreaCovered': percent(sum(hotspot_geoms[i].intersection(coverage).area for i in indexes), sum(hotspot_geoms[i].area for i in indexes))}
                    for i, p in zip(indexes, parts):
                        hotspot_rows[i][f'COB_{key.upper()}_{radius}'] = p*100
                result['hotspots'][f'{scope}_{category}'] = stats
        for _, center in cabin.iterrows():
            reference = center.geometry.buffer(200, quad_segs=64)
            name = str(center['PARROQUIA'])
            canonical = next((key for key in rural_counts if key.upper() == name.upper()), None)
            shape_parish = next((g for key, g in parishes.items() if key.upper() == name.upper()), None)
            existing_count = sum(shape_parish.covers(p) for p in actual_points) if shape_parish is not None else None
            proposed_count = rural_counts.get(canonical, 0)
            result['cabeceras'].append({'parish': name, 'existingInOperativeParish': existing_count, 'proposedAssignedBySector': proposed_count,
                'theoreticalFutureInAssignedParish': existing_count+proposed_count if existing_count is not None else None,
                'proposedWithin200mOfCenter': sum(reference.covers(p) for c, p in zip(proposed, proposal_points) if c['SECTOR'] == canonical),
                'actualCoveragePctWithin200m': percent(reference.intersection(actual).area, reference.area),
                'futureCoveragePctWithin200m': percent(reference.intersection(future).area, reference.area)})
        for row in fixed:
            row[f'CAMBIO_BRECHA_{radius}'] = f"{row[f'BRECHA_ACTUAL_{radius}']} -> {row[f'BRECHA_FUTURE_{radius}']}"
            row[f'COB_{radius}'] = row[f'COB_ACTUAL_{radius}']
            row[f'BRECHA_{radius}'] = row[f'BRECHA_ACTUAL_{radius}']
        scenarios[str(radius)] = result
        assert result['metrics']['future']['populationCovered']+.001 >= result['metrics']['actual']['populationCovered']
        assert result['metrics']['future']['coveredUrbanAreaKm2']+.000001 >= result['metrics']['actual']['coveredUrbanAreaKm2']
        assert all(r['futureCoveredM']+.001 >= r['actualCoveredM'] for r in result['corridors'])
        for row in fixed:
            order = {'ALTA': 3, 'MEDIA': 2, 'BAJA': 1, 'SIN EVIDENCIA': 0}
            assert order[row[f'BRECHA_FUTURE_{radius}']] <= order[row[f'BRECHA_ACTUAL_{radius}']]
        validation.append({'radius': radius, 'actual': result['metrics']['actual']['gapCounts'], 'future': result['metrics']['future']['gapCounts'], 'monotonicImpact': True})
    # Spatial association is descriptive only and never feeds an invented location score.
    for camera, point in zip(proposed, proposal_points):
        nearest = min(range(len(actual_points)), key=lambda i: point.distance(actual_points[i]))
        camera['existingNearestId'] = located[nearest]['id']
        camera['existingDistanceM'] = point.distance(actual_points[nearest])
        camera['existingCovered'] = {str(r): scenarios[str(r)]['coverage']['actual']['geometry'] is not None and camera['existingDistanceM'] <= r for r in (100, 150, 200)}
        camera['corridorsAssociated'] = [{'name': key, 'distanceM': axis.distance(point)} for key, axis in corridors.items() if axis.distance(point) <= 200]
        camera['hotspotsAssociated'] = [hotspot_rows[i]['id'] for i in range(len(hotspot_rows)) if hotspot_geoms[i].intersects(point.buffer(200, quad_segs=64))]
        camera['platform'] = next((f['properties']['platform_name'] for f in platforms['features'] if transform(PROJECT, shape(f['geometry'])).covers(point)), None)
        individual = point.buffer(200, quad_segs=64)
        others = unary_union([p.buffer(200, quad_segs=64) for p in all_points if p is not point])
        camera['uniqueContributionAreaM2'] = individual.difference(others).area
        camera['overlapWithOtherCamerasPct'] = percent(individual.intersection(others).area, individual.area)
    redundancies = [{k:c[k] for k in ('id', 'ID_PROP', 'SECTOR', 'existingDistanceM', 'uniqueContributionAreaM2', 'overlapWithOtherCamerasPct')}
                    for c in proposed if c['overlapWithOtherCamerasPct'] >= 95]
    continuity = []
    for key, axis in corridors.items():
        selected = [i for i, p in enumerate(all_points) if axis.distance(p) <= 200]
        for line_index, line in enumerate(components(axis), 1):
            local = [i for i in selected if line.distance(all_points[i]) <= 200]
            local.sort(key=lambda i: line.project(all_points[i]))
            for left, right in zip(local, local[1:]):
                d = all_points[left].distance(all_points[right])
                continuity.append({'corridor': key, 'component': line_index, 'cameraA': all_ids[left], 'cameraB': all_ids[right],
                    'distanceAlongM': line.project(all_points[right])-line.project(all_points[left]),
                    'distanceM': d, 'bufferRelation200m': 'SOLAPAMIENTO' if d < 400-.01 else 'CONTINUIDAD_TANGENTE' if d <= 400+.01 else 'VACIO_ENTRE_RADIOS',
                    'note': 'Relacion geometrica de discos; no garantiza cobertura de todo el eje ni visibilidad real.'})
    example_ids = []
    for level in ('ALTA', 'MEDIA', 'BAJA', 'SIN EVIDENCIA'):
        example_ids += [row['ID_MANZANA'] for row in fixed if row['URBANA_OPERATIVA'] and row['BRECHA_ACTUAL_200'] == level][:3]
    for row in fixed:
        if len(example_ids) >= 10:
            break
        if row['URBANA_OPERATIVA'] and row['ID_MANZANA'] not in example_ids:
            example_ids.append(row['ID_MANZANA'])
    gap_examples = [row for code in example_ids[:10] for row in fixed if row['ID_MANZANA'] == code]
    display = {'metadata': metadata, 'cameras': proposed, 'scenarios': scenarios, 'redundancies': redundancies,
               'continuity': continuity, 'gapValidation': validation, 'gapExamples': gap_examples}
    if baseline_file.exists():
        display['previousEvaluation'] = json.loads(baseline_file.read_text(encoding='utf-8'))
    refinement_file = ROOT/'data/seguridad-riobamba/correccion-propuesta-corredores-20261002/COMPARACION_CORREDORES.json'
    if args.proposal != CSV and refinement_file.exists():
        display['refinement'] = json.loads(refinement_file.read_text(encoding='utf-8'))
        movements = display['refinement']['movements']
        gpkg_layers['CAMARAS_PROPUESTAS_POSICION_ANTERIOR'] = gpd.GeoDataFrame([{'ID_PROP': r['ID_PROP'], 'TIPO': r['TIPO'], 'DESPLAZAMIENTO_M': r['movementM']} for r in movements],
            geometry=[Point(r['oldX'], r['oldY']) for r in movements], crs=32717)
    gpkg_layers['CAMARAS_PROPUESTAS_50'] = gpd.GeoDataFrame([{**r, 'X': c['X'], 'Y': c['Y'], 'ID_INTERNO': c['id'], 'RADIO_DISENO': 200} for r, c in zip(original, proposed)], geometry=proposal_points, crs=32717)
    gpkg_layers['MANZANAS_BRECHAS_COMPARADAS'] = gpd.GeoDataFrame(fixed, geometry=block_geoms, crs=32717)
    gpkg_layers['HOTSPOTS_COBERTURA_COMPARADA'] = gpd.GeoDataFrame(hotspot_rows, geometry=hotspot_geoms, crs=32717)
    for scope in ('URBANO', 'RURAL'):
        for category in CLASSES:
            indexes = [i for i, row in enumerate(hotspot_rows) if row['scope'] == scope and row['category'] == category]
            if indexes:
                gpkg_layers[f'HOTSPOT_{scope}_{category}'] = gpd.GeoDataFrame([hotspot_rows[i] for i in indexes], geometry=[hotspot_geoms[i] for i in indexes], crs=32717)
    gpkg_layers['CORREDORES_ANALIZADOS'] = gpd.GeoDataFrame([{'TIPO_CORREDOR': key} for key in corridors], geometry=list(corridors.values()), crs=32717)
    package = OUT / 'EVALUACION_PROPUESTA_CAMARAS.gpkg'
    if package.exists():
        package.unlink()
    for name, frame in gpkg_layers.items():
        frame.to_file(package, layer=name, driver='GPKG', engine='pyogrio')
        check = pyogrio.read_dataframe(package, layer=name)
        assert len(check) == len(frame) and check.crs.to_epsg() == 32717
    proposal_features = collection([{'type': 'Feature', 'properties': c, 'geometry': {'type': 'Point', 'coordinates': [c['lng'], c['lat']]}} for c in proposed])
    (OUT / 'CAMARAS_PROPUESTAS_50.geojson').write_text(json.dumps(proposal_features, ensure_ascii=False), encoding='utf-8')
    (OUT / 'CORREDORES_ANALIZADOS.geojson').write_text(json.dumps(collection(corridor_features), ensure_ascii=False), encoding='utf-8')
    (OUT / 'HOTSPOTS_COBERTURA_COMPARADA.geojson').write_text(json.dumps(collection([feature(g, r) for g, r in zip(hotspot_geoms, hotspot_rows)]), ensure_ascii=False), encoding='utf-8')
    (OUT / 'MANZANAS_BRECHAS_COMPARADAS.geojson').write_text(json.dumps(collection([feature(g, r) for g, r in zip(block_geoms, fixed)]), ensure_ascii=False), encoding='utf-8')
    assert {name: sha(ROOT/name) for name in PROTECTED} == protected
    assert {name: sha(Path(name)) for name in source_hashes} == source_hashes
    metadata['originalSourcesUnchanged'] = True
    (OUT / 'RESULTADOS.json').write_text(json.dumps(display, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    report = {'metadata': metadata, 'gapValidation': validation, 'gapExamples': gap_examples, 'possibleRedundancies': redundancies,
              'corridors': {r: scenarios[r]['corridors'] for r in scenarios}, 'metrics': {r: scenarios[r]['metrics'] for r in scenarios},
              'hotspots': {r: scenarios[r]['hotspots'] for r in scenarios}, 'cabeceras': {r: scenarios[r]['cabeceras'] for r in scenarios}}
    (OUT / 'VALIDACION_Y_COMPARACION.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    documentation = f'''# BRECHAS DE COBERTURA Y PRIORIDAD TERRITORIAL

Esta clasificación constituye una herramienta operativa de priorización territorial para el presente estudio. No representa por sí sola una medida de peligrosidad, riesgo delictivo ni una metodología universal de brecha de videovigilancia.

ESTADO: PROVISIONAL_ASIGNACION_INCIDENTES. La validacion detecta que {assignment_scopes['URBANO']['withoutBlock']} de {assignment_scopes['URBANO']['total']} incidentes urbanos no intersectan una manzana. Esto puede deberse a ubicaciones en calles. No implica ausencia de eventos y explica en gran parte los percentiles de incidencia cero. No se publica ni se usa como fuente definitiva de priorizacion hasta aprobar una regla de atribucion calle/manzana. No se mueven puntos ni se modifica ningun poligono. Todos estos registros se conservan en las evaluaciones de Gi* y cobertura de incidentes.

## Ambito y fuentes
Manzanas originales CPV2022 que intersectan con area positiva la union de las18 Plataformas (ambito urbano operativo, no limite urbano legal). Las manzanas externas se conservan como SIN EVIDENCIA. Coordenadas de incidentes originales y diccionario corregido. Gi* URBANO recalculado separadamente: malla{metadata['urbanHotspotCellM']}m / distancia{metadata['urbanHotspotDistanceM']}m, DELINCUENCIA, VIOLENCIA y CONVIVENCIA independientes. Gi* RURAL y sus fuentes originales sin cambios, distancia{metadata['ruralHotspotDistanceM']}m. EPSG:32717; peso1; incidentes sin mover.

## Cobertura
COB_X =100 * area(manzana intersectada por union de buffers) / area(manzana). Radios de evaluacion100/150/200m; radio de diseno de propuesta200m. Union antes de intersectar, sin doble conteo. Cada registro espacialmente valido aporta un disco (quad_segs64); cuatro camaras existentes no tienen coordenadas y no generan cobertura. Los discos se conservan continuos fuera de Plataformas. Baja <{args.coverage_low}%; parcial {args.coverage_low} a {args.coverage_high}% incluidos; buena >{args.coverage_high}%. Umbrales configurables mediante --coverage-low y --coverage-high al generar resultados, nunca cambiados entre comparaciones.

## Poblacion
P33={pop_p33}; P66={pop_p66}; N={len(valid_urban)} manzanas urbanas con dato no negativo. Percentil33/66 con interpolacion lineal. Baja <P33; media P33 a P66 inclusive; alta >P66. Se mantienen fijos entre radios y escenarios. NULL no se sustituye por0; cero observado se conserva.

## Problematica
Incidencia D/V=(N_DELINCUENCIA+N_VIOLENCIA)/poblacion*1000. P33 incidencia={inc_p33}; P66 incidencia={inc_p66}; N={len(incidence)} manzanas con poblacion>0. No es una tasa anualizada: solo periodo de la base disponible. Con poblacion0, tasa no disponible. Cada evento se asigna al poligono original que lo contiene; limites/solapes se resuelven una sola vez al menor ID_MANZANA ({len(multi_block_events)} casos). {unassigned_events} incidentes no intersectan una manzana disponible: no se fuerzan a centroides.

Gi* asociado por interseccion con area>0.01m2 con la manzana; se conserva el mayor nivel hotspot D/V. No se usan coldspots ni concentracion KDE como significancia. Esta regla de superposicion puede alcanzar manzanas sin eventos propios por la vecindad Gi* y debe revisarse territorialmente.
P33 y P66 de incidencia son cero bajo interseccion estricta. No equivalen a ausencia territorial de D/V porque la mayoria de los puntos urbanos no esta dentro de los poligonos. Cualquier tasa positiva supera P66. Se muestran estos valores como control provisional, sin reajustarlos para obtener otra clasificacion.
ALTA: Gi*D/V95/99%. MEDIA: Gi*D/V90%, o incidencia>P66 sin Gi*>=95. Convivencia complementaria: Gi*convivencia>=95% y al menos un evento de convivencia registrado en la manzana puede producir MEDIA, nunca ALTA por si sola. BAJA: resto con tasa valida. Si no hay tasa valida ni evidencia Gi* suficiente, problematica no disponible. Gi* nominal bilateral, sin FDR; no equivale a peligrosidad.

## Reglas booleanas, orden de aplicacion
1. Si falta poblacion, cobertura o problematica: SIN EVIDENCIA.
2. Baja cobertura + poblacion media/alta + problematica alta: ALTA.
3. Baja cobertura + poblacion media/alta + problematica media; o cobertura parcial + poblacion media/alta + problematica alta: MEDIA.
4. Buena cobertura o cualquier otra situacion evaluada: BAJA.
No hay ponderaciones, score, AHP ni indice multicriterio. Poblacion y problematica constantes entre radios y escenarios. CAMBIO_BRECHA_100/150/200 conserva transiciones ACTUAL -> FUTURE. Geometria de representacion: manzana completa; no se modifica su delimitacion.

## Simbologia
ALTA #D98C95; MEDIA #D9B65D; BAJA #A8C9A5; SIN EVIDENCIA gris claro/transparente.

## Denominadores y limitaciones
Las cuentas de brecha son manzanas urbanas operativas. La poblacion por clase de brecha es poblacion completa de esas manzanas; la poblacion potencialmente cubierta general se estima arealmente en la porcion urbana, y se etiqueta de forma distinta. Cobertura poblacional no certifica visibilidad real; asume distribucion uniforme intramanzana. No hay poblacion rural georreferenciada completa. Cabeceras: propuestas por SECTOR (dos por parroquia), existentes por parroquia operativa; conteos teóricos no certifican pertenencia espacial de las propuestas. Se informa aparte cobertura dentro de un entorno fijo de200m de cada centro original. Las ubicaciones existentes son aproximadas.

## Validacion
VALIDACION_Y_COMPARACION.json contiene percentiles, cuentas por radio/escenario y10 ejemplos con cobertura, poblacion, problematica, Gi*, regla y resultado. Propuestas corregidas en CSV versionado por autorizacion del usuario;22 rurales intactas. ID_PROP original se preserva aunque se repita; ID_INTERNO es una clave por fila, no otra camara. Originales verificados por SHA256. No commit/push; revision humana pendiente.
'''
    (OUT / 'METODOLOGIA_BRECHAS.md').write_text(documentation, encoding='utf-8')
    readme = '''# Evaluacion local de la propuesta de 50 camaras

SIN COMMIT/PUSH. Revision humana pendiente. No se optimizan ni mueven ubicaciones.
103 inventariadas, 99 existentes ubicadas, 50 propuestas, 153 futuras teoricas / 149 ubicadas.
CSV original: PROPUESTA_CAMARAS_RIOBAMBA_200M.csv. ID_PROP preservado; ID_INTERNO resuelve dos IDs repetidos entre San Juan y San Luis sin perder filas. Cinco propuestas fuera del limite cantonal disponible se conservan y documentan.

## Fuentes
- Inventario103: Informe Estado de Camaras Canton Riobamba,14-01-2026. Ubicaciones aproximadas, cuatro sin geometria.
- Propuesta: CSV proporcionado por el usuario, diseno externo200m. X/Y originales EPSG:32717.
- Manzanas/poblacion: CPV2022 y geometrias originales del proyecto. NULL no es0.
- Plataformas:18 geometrias reales del GAD, union urbana operativa, no limite urbano legal.
- Incidentes: base georreferenciada original y clasificacion corregida del proyecto, peso1 por fila. D/V/Convivencia separadas.
- Gi*: urbano recalculado separadamente en malla100m, distancia200m; rural original sin cambios en malla1000m/distancia2000m. Tres categorias separadas. Nominal bilateral sin FDR; rural exploratorio.
- Macaji-Bellavista/Ciclovias/Anillo: ejes originales del paquete GIS del proyecto. Ciclovias incluye existentes y proyectadas.
- Las Abras: los tres archivos seleccionados por el usuario, conservados sin reconstruccion. Coincidencias disueltas para medir longitud unica; no son tres lineas completamente independientes.

## GeoPackage
EVALUACION_PROPUESTA_CAMARAS.gpkg: todas las capas tienen CRS EPSG:32717.
- CAMARAS_PROPUESTAS_50 (50 puntos): todos los campos originales; X,Y metricos; ID_INTERNO clave por fila; RADIO_DISENO=200. JUSTIFICACION no existe en el CSV.
- BUFFER_ACTUAL_100M/150M/200M (1 geometria disuelta por capa): ESCENARIO,RADIO_M. Solo99 existentes con ubicacion.
- BUFFER_PROPUESTAS_100M/150M/200M (1 por capa):50 propuestas, areas superpuestas no duplicadas.
- BUFFER_FUTURE_100M/150M/200M (1 por capa): union99+50, nunca suma de areas individuales.
- VACIOS_COBERTURA_100M/150M/200M (conteos en AUDITORIA_CAPAS.json): segmentos originales no cubiertos en escenario futuro. ID,TIPO_CORREDOR,LONGITUD_M,COBERTURA,CAMARA_CERCANA,DIST_CAMARA en metros.
- CORREDORES_ANALIZADOS (4 geometrias):TIPO_CORREDOR, union por red para evitar duplicidad en longitudes. Los tramos individuales tambien se conservan en CORREDORES_ANALIZADOS.geojson.
- HOTSPOTS_COBERTURA_COMPARADA: geometria original de celdas HOTSPOT; scope,category,CELL_ID,COUNT,GI_ZSCORE,GI_PVALUE,GI_CLASS,level; COB_ACTUAL/PROPOSALS/FUTURE_100/150/200 (%area). Las seis combinaciones de ambito/categoria permanecen identificables y separadas en el visor.
- HOTSPOT_URBANO/RURAL_DELINCUENCIA/VIOLENCIA/CONVIVENCIA: tambien exportadas como seis capas separadas, con los mismos atributos estadisticos y de cobertura.
- MANZANAS_BRECHAS_COMPARADAS (3757 geometrias originales):ID_MANZANA,POBLACION,PLATAFORMA,URBANA_OPERATIVA,N_DELINCUENCIA,N_VIOLENCIA,N_CONVIVENCIA,TASA_DV_1000,GI_DV_NIVEL,GI_CONV_NIVEL,POBLACION_NIVEL,PROBLEMATICA,PROBLEMATICA_REGLA,URBAN_FRACTION; COB_ACTUAL/PROPOSALS/FUTURE_100/150/200 (%area completa),BRECHA_ACTUAL/PROPOSALS/FUTURE_100/150/200,REGLA_ACTUAL/FUTURE_100/150/200,CAMBIO_BRECHA_100/150/200. COB_100/150/200 y BRECHA_100/150/200 son alias del escenario ACTUAL.
- ESTADO_METODOLOGIA=PROVISIONAL_ASIGNACION_INCIDENTES: la mayoria de los incidentes urbanos no intersecta manzanas; falta aprobar como atribuir los puntos de calles. Las brechas se entregan para inspeccion, no como resultado definitivo. Los mismos puntos SI se usan en Gi* y cobertura de incidentes.

## Archivos complementarios
- RESULTADOS.json: escenarios disueltos, indicadores y asociaciones de camaras.
- VALIDACION_Y_COMPARACION.json: conteos por radio,10 ejemplos, cabeceras, incidentes, Gi*, corredores y comparacion actual/futura.
- AUDITORIA_INPUT.json: SHA256 de originales, coordenadas/duplicados, limitaciones, tramos Las Abras y percentiles fijos.
- METODOLOGIA_BRECHAS.md: reglas booleanas, parametros y limitaciones. No AHP, indice ponderado ni peligrosidad.
- GeoJSON de visualizacion:EPSG:4326. No usar grados para distancias. GeoPackage es la salida metrica de procesamiento.

Los conteos de cabeceras por SECTOR no certifican que cada propuesta este cerca del centro: la proximidad al punto municipal se reporta por separado. Poblacion cubierta es estimacion areal urbana, no cobertura visual real. Brechas fuera del ambito urbano: SIN EVIDENCIA, sin percentiles rurales improvisados.
Para analisis de cabeceras se utiliza XY; la medida M del GPKG fuente no se utiliza para distancias ni se modifica en el archivo original.
Posible redundancia: umbral descriptivo>=95% de solapamiento del disco200m con la union de las demas camaras. No garantiza redundancia funcional. No se modifica ninguna camara.
'''
    (OUT / 'README.md').write_text(readme, encoding='utf-8')
    (OUT / 'AUDITORIA_CAPAS.json').write_text(json.dumps({name: {'records': len(frame), 'crs': 'EPSG:32717'} for name, frame in gpkg_layers.items()}, indent=2), encoding='utf-8')
    assert {name: sha(ROOT/name) for name in PROTECTED} == protected
    assert {name: sha(Path(name)) for name in source_hashes} == source_hashes
    metadata['originalSourcesUnchanged'] = True
    (OUT / 'AUDITORIA_INPUT.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    write_review(display)
    print(json.dumps({'proposal': 50, 'existing': 103, 'locatedFuture': 149, 'distribution': dict(counts),
        'populationP33': pop_p33, 'populationP66': pop_p66, 'incidenceP33': inc_p33, 'incidenceP66': inc_p66,
        'gapValidation': validation, 'duplicateIds': duplicate_ids, 'outsideCanton': metadata['outsideCanton'],
        'redundancies': len(redundancies), 'abras': [str(p) for p in args.abras], 'originalsUnchanged': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
