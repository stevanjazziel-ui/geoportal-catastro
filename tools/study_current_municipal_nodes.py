"""Refresh the municipal-node study on the current 103/30 inventory and police release."""
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
from scipy.optimize import Bounds, LinearConstraint, linear_sum_assignment, milp
from scipy.sparse import coo_matrix, csr_matrix
from shapely import covers
from shapely.ops import unary_union

from adjust_macaji_100 import interval_constraints
from review_police_verified_main_roads import (
    ROOT, ROADS, candidates_from_shared_vertices, normalized,
)
from review_police_kde_intersections import export_geojson, source_hash

OUT = ROOT / 'data/seguridad-riobamba/MUNICIPALES_24_NODOS_ACTUALIZADOS_20261015'
PREVIOUS = ROOT / 'data/seguridad-riobamba/ESTUDIO_MUNICIPALES_24_INTERSECCIONES_20261015'
BASE = ROOT / 'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/POLICIA_30_EJES_AJUSTES_20261015'
PACKAGE = BASE / 'ESCENARIO_FINAL_183.gpkg'
MACAJI, RING, CYCLE = 'BOULEVARD_MACAJI_BELLAVISTA', 'ANILLO_VIAL', 'CICLOVIAS'
KEYS = (MACAJI, RING, CYCLE)
RADIUS, TOL = 200, .001
# Named road identity, not a fabricated projection onto the corridor geometry.
REQUIRED_AXES = {
    'MUN-028': 'Avenida 9 de Octubre', 'MUN-043': 'Avenida 9 de Octubre',
    'MUN-046': 'Avenida Edelberto Bonilla Oleas', 'MUN-049': 'Avenida 9 de Octubre',
}


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')


def table(name, rows):
    if not rows:
        return
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def disk_union(points):
    return unary_union([p.buffer(RADIUS, quad_segs=64) for p in points])


class Study:
    def __init__(self):
        read = lambda name: gpd.read_file(PACKAGE, layer=name).to_crs(32717)
        self.existing = read('CAMARAS_EXISTENTES_103_FINAL')
        self.municipal = read('PROPUESTA_MUNICIPAL_50_FINAL')
        self.police = read('PROPUESTA_POLICIA_30_FINAL')
        self.original = self.municipal.loc[self.municipal.GRUPO.eq('RED_ESTRUCTURAL')].reset_index(drop=True)
        self.frozen = self.municipal.loc[~self.municipal.GRUPO.eq('RED_ESTRUCTURAL')].reset_index(drop=True)
        assert [len(self.existing), len(self.original), len(self.frozen), len(self.police)] == [103,24,26,30]
        assert Counter(self.frozen.GRUPO) == {'CABECERA_RURAL':22, 'LAS_ABRAS':4}
        self.fixed = disk_union(list(self.existing.geometry)+list(self.frozen.geometry))
        self.police_mask = disk_union(self.police.geometry)
        self.before = unary_union([self.fixed, disk_union(self.original.geometry)])
        self.corridors = read('CORREDORES')
        self.axes = {key: self.corridors.loc[self.corridors.CORREDOR.eq(key)].geometry.union_all() for key in KEYS}
        self.urban = read('PLATAFORMAS_TERRITORIALES')
        self.roads = gpd.read_file(ROADS).to_crs(32717)
        self.candidates = candidates_from_shared_vertices(self.roads, self.urban.geometry.union_all(), require_principal=False)
        occupied = {p.wkb for p in list(self.existing.geometry)+list(self.frozen.geometry)+list(self.police.geometry)}
        self.candidates = [c for c in self.candidates if c['point'].wkb not in occupied]
        for c in self.candidates:
            c['id'] = 'MUN-'+c['id']
        self.principal = [c for c in self.candidates if c['principal']]
        events = read('INCIDENTES_CLASIFICADOS')
        self.events = events.loc[events.AMBITO.eq('URBANO')]
        self.logs = []

    def coverage(self, mask):
        return {key: {'totalM':axis.length, 'coveredM':axis.intersection(mask).length,
                      'uncoveredM':axis.difference(mask).length,
                      'pct':100*axis.intersection(mask).length/axis.length}
                for key, axis in self.axes.items()}

    def allowed(self, camera, candidate):
        expected = REQUIRED_AXES.get(camera)
        return not expected or normalized(expected) in {normalized(n) for n in candidate['principal']}

    def describe(self, name, pairing, solver=None):
        points = [c['point'] for _, c in pairing]
        municipal_mask = unary_union([self.fixed, disk_union(points)])
        system = unary_union([municipal_mask, self.police_mask])
        records = []
        for index, candidate in pairing:
            before = self.original.iloc[index]
            point = candidate['point']
            others = unary_union([self.fixed, *[c['point'].buffer(RADIUS,quad_segs=64)
                for j,c in pairing if j != index]])
            disk = point.buffer(RADIUS,quad_segs=64)
            records.append({'ID_PROPUESTA':before.ID_PROPUESTA,'GRUPO':'RED_ESTRUCTURAL',
                'X_ANTES':before.geometry.x,'Y_ANTES':before.geometry.y,
                'X_PROPUESTO':point.x,'Y_PROPUESTO':point.y,
                'DESPLAZAMIENTO_M':before.geometry.distance(point),
                'ID_CANDIDATO':candidate['id'],'CRUCE':' x '.join(candidate['roads']),
                'EJE_PRINCIPAL':' | '.join(candidate['principal']),
                'VIA_PRINCIPAL':bool(candidate['principal']),'JERARQUIA_OSM':' | '.join(candidate['highways']),
                'GRADO_NODO':candidate['degree'],'OSM_IDS':' | '.join(candidate['osmIds']),
                'EJE_EXIGIDO':REQUIRED_AXES.get(before.ID_PROPUESTA),
                'CUMPLE_EJE_EXIGIDO':self.allowed(before.ID_PROPUESTA,candidate),
                'DISTANCIA_GEOMETRIA_ANILLO_M':point.distance(self.axes[RING]),
                'SOLAPE_B_PCT':100*disk.intersection(others).area/disk.area,
                'FUENTE_VIAL':ROADS.name,'APLICADA':False,'VISIBILIDAD_CERTIFICADA':False})
        assert len({p.wkb for p in points}) == 24
        export_geojson(OUT / (name+'_24.geojson'), [(c['point'], r) for (_,c),r in zip(pairing, records)])
        table(name+'_MOVIMIENTOS.csv', records)
        frame = gpd.GeoDataFrame(records, geometry=points, crs=32717)
        frame.to_file(OUT / 'ESTUDIO_24_NODOS.gpkg', layer=name, driver='GPKG', index=False)
        counts = {}
        for category in ('DELINCUENCIA','VIOLENCIA','CONVIVENCIA'):
            selected = self.events.loc[self.events.CATEGORIA.eq(category)].geometry.values
            counts[category] = int(covers(system,selected).sum())
        coverage = self.coverage(municipal_mask)
        result = {'name':name,'applied':False,'municipal':coverage,'system183':self.coverage(system),
            'principalCount':sum(r['VIA_PRINCIPAL'] for r in records),
            'movedCount':sum(r['DESPLAZAMIENTO_M'] > .001 for r in records),
            'totalDisplacementM':sum(r['DESPLAZAMIENTO_M'] for r in records),
            'maxDisplacementM':max(r['DESPLAZAMIENTO_M'] for r in records),
            'meanOverlapPct':float(np.mean([r['SOLAPE_B_PCT'] for r in records])),
            'maxOverlapPct':max(r['SOLAPE_B_PCT'] for r in records),
            'hardGoalsMet':coverage[MACAJI]['uncoveredM']<=TOL and coverage[RING]['pct']>=80-1e-8,
            'fourRoadAxesSatisfied':all(r['CUMPLE_EJE_EXIGIDO'] for r in records),
            'urbanEventsInPotentialBuffers':counts,'solver':solver,'movements':records}
        save(name+'.json', result)
        return result

    def nearest(self):
        distances = np.array([[row.geometry.distance(c['point']) if self.allowed(row.ID_PROPUESTA,c) else np.inf
            for c in self.principal] for row in self.original.itertuples()])
        a,b = linear_sum_assignment(distances)
        return self.describe('A_CRUCES_PROXIMOS', [(int(i),self.principal[int(j)]) for i,j in zip(a,b)])

    def solve(self, name, priority='main', time_limit=45):
        targets = {key:axis.difference(self.fixed) for key,axis in self.axes.items()}
        pool = [c for c in self.candidates if any(c['point'].distance(axis)<RADIUS
            for axis in targets.values() if not axis.is_empty)]
        rows = [(c['point'],c) for c in pool]
        _, impossible, _, lengths = interval_constraints([(key,axis,self.fixed) for key,axis in self.axes.items()],rows)
        if impossible.get(MACAJI,0)>TOL:
            self.logs.append({'scenario':name,'status':'MACAJI_NO_CUBRIBLE_EN_CATALOGO','uncoverableM':impossible})
            return None
        intervals = [(key,support,length) for (key,support),length in lengths.items()]
        n,m = len(pool),len(intervals)
        pairs = [(i,j) for i,row in enumerate(self.original.itertuples())
            for j,c in enumerate(pool) if self.allowed(row.ID_PROPUESTA,c)]
        size = n+m+len(pairs)
        rr,cc,vv,lower,upper = [],[],[],[],[]
        def add(entries,lo,hi):
            row = len(lower)
            for col,value in entries: rr.append(row);cc.append(col);vv.append(value)
            lower.append(lo);upper.append(hi)
        for k,(key,support,length) in enumerate(intervals):
            if key==MACAJI: add([(j,1) for j in support],1,np.inf)
            else: add([(n+k,1)]+[(j,-1) for j in support],-np.inf,0)
        for i in range(24): add([(n+m+k,1) for k,(camera,_) in enumerate(pairs) if camera==i],1,1)
        for j in range(n): add([(j,-1)]+[(n+m+k,1) for k,(_,candidate) in enumerate(pairs) if candidate==j],0,0)
        matrix = coo_matrix((vv,(rr,cc)),shape=(len(lower),size)).tocsr()
        constraints = [LinearConstraint(matrix,lower,upper)]
        weights = {key:np.r_[np.zeros(n),[length if kind==key else 0 for kind,_,length in intervals],np.zeros(len(pairs))] for key in KEYS}
        constraints.append(LinearConstraint(csr_matrix(weights[RING][None,:]),
            .8*self.axes[RING].length-self.axes[RING].intersection(self.fixed).length,np.inf))
        main_weights = np.r_[[int(bool(c['principal'])) for c in pool],np.zeros(m+len(pairs))]
        transport = np.r_[np.zeros(n+m),[self.original.iloc[i].geometry.distance(pool[j]['point']) for i,j in pairs]]
        objectives = [('MAX_EJES_PRINCIPALES',-main_weights),('MAX_CICLOVIAS',-weights[CYCLE])]
        if priority=='cycle': objectives.reverse()
        objectives.append(('MIN_DESPLAZAMIENTO',transport))
        solution = None
        for phase,cost in objectives:
            trial = milp(cost,integrality=np.r_[np.ones(n),np.zeros(m+len(pairs))],
                bounds=Bounds(np.zeros(size),np.ones(size)),constraints=constraints,
                options={'time_limit':time_limit,'mip_rel_gap':1e-6})
            log = {'scenario':name,'phase':phase,'status':int(trial.status),'message':trial.message,
                'objective':float(trial.fun) if trial.x is not None else None,
                'gap':float(trial.mip_gap) if trial.x is not None else None,'catalogCount':n}
            self.logs.append(log); print(json.dumps(log),flush=True); save('SOLVER_AVANCE.json',self.logs)
            if trial.x is None:
                if solution is None: return None
                break
            solution = trial
            if phase=='MAX_EJES_PRINCIPALES':
                count = int(round(main_weights@solution.x))
                constraints.append(LinearConstraint(csr_matrix(main_weights[None,:]),count,count))
            elif phase=='MAX_CICLOVIAS':
                constraints.append(LinearConstraint(csr_matrix(weights[CYCLE][None,:]),weights[CYCLE]@solution.x-TOL,np.inf))
        selected = [pool[int(i)] for i in np.flatnonzero(solution.x[:n]>.5)]
        assert len(selected)==24
        distances = np.array([[row.geometry.distance(c['point']) if self.allowed(row.ID_PROPUESTA,c) else np.inf
            for c in selected] for row in self.original.itertuples()])
        a,b = linear_sum_assignment(distances)
        assert np.isfinite(distances[a,b]).all()
        result = self.describe(name,[(int(i),selected[int(j)]) for i,j in zip(a,b)],
            {'logs':[r for r in self.logs if r['scenario']==name],
             'allPhasesOptimalInCatalog':all(r['status']==0 for r in self.logs if r['scenario']==name)})
        assert result['hardGoalsMet'] and result['fourRoadAxesSatisfied']
        return result


def main():
    assert not OUT.exists(), 'No se sobrescribe un estudio anterior'
    assert json.loads((ROOT/'sig-bridge-active.json').read_text())['releaseId']==BASE.name
    OUT.mkdir(parents=True)
    protected = [PACKAGE,ROOT/'sig-bridge-active.json',ROOT/'riobamba-conflictividad-data.js',
        ROOT/'riobamba-hotspot-urbano-200m-data.js',ROOT/'visor-seguridad-riobamba-v2.html']
    protected += [p for p in ROADS.parent.glob(ROADS.stem+'.*') if p.is_file()]
    hashes = {str(p):source_hash(p) for p in protected}
    study = Study()
    def export_frame(name, frame, ids):
        export_geojson(OUT/name, [(row.geometry,{k:getattr(row,k) for k in ids}) for row in frame.itertuples()])
    export_frame('ACTUALES_24.geojson',study.original,['ID_PROPUESTA','GRUPO'])
    export_frame('MUNICIPALES_26_FIJAS.geojson',study.frozen,['ID_PROPUESTA','GRUPO'])
    export_frame('EXISTENTES_103_FIJAS.geojson',study.existing,['ID_CAMARA','REQUIERE_CAMBIO'])
    export_frame('POLICIA_30_FIJA.geojson',study.police,['ID_POLICIA'])
    export_frame('CORREDORES.geojson',study.corridors,['CORREDOR'])
    old_results = []
    previous_files = list((PREVIOUS/'REVISION_02').glob('*_PUNTOS.geojson'))
    previous_files += list((PREVIOUS/'REVISION_03_ANILLO').glob('*_24_PUNTOS.geojson'))
    for path in previous_files:
        hashes[str(path)] = source_hash(path)
        frame = gpd.read_file(path).to_crs(32717)
        b = unary_union([study.fixed,disk_union(frame.geometry)])
        old_results.append({'source':str(path.relative_to(ROOT)),'municipal':study.coverage(b),
            'system183':study.coverage(unary_union([b,study.police_mask])),
            'applied':False,'note':'Reevaluacion de geometria anterior, no validacion de ejes OSM'})
    combined_principal = unary_union([study.fixed,disk_union(c['point'] for c in study.principal)])
    principal_uncoverable = study.axes[MACAJI].difference(combined_principal).length
    print('Catalogo',len(study.candidates),'principales',len(study.principal),
          'Macaji imposible solo principales m',principal_uncoverable,flush=True)
    scenarios = [study.nearest()]
    save('AVANCE.json',{'scenarios':scenarios,'oldRebased':old_results})
    for name,priority in [('C_PRIORIDAD_EJES','main'),('D_PRIORIDAD_CICLOVIAS','cycle')]:
        result = study.solve(name,priority)
        if result: scenarios.append(result)
        save('AVANCE.json',{'scenarios':scenarios,'oldRebased':old_results,'solver':study.logs})
    report = {'generatedAt':datetime.now(ZoneInfo('America/Guayaquil')).isoformat(),
        'status':'ESTUDIO_ACTUALIZADO_NO_APLICADO','applied':False,'published':False,
        'counts':{'municipal':50,'urbanEditable':24,'ruralFixed':22,'abrasFixed':4,'existingFixed':103,'policeFixed':30},
        'baseRelease':BASE.name,'metricCrs':'EPSG:32717','radiusM':RADIUS,'geometryToleranceM':TOL,
        'roadSource':str(ROADS),'candidateCount':len(study.candidates),'principalCandidateCount':len(study.principal),
        'principalOnlyMacajiUncoverableM':principal_uncoverable,'fourRequiredAxes':REQUIRED_AXES,
        'baselineMunicipal':study.coverage(study.before),
        'baselineSystem183':study.coverage(unary_union([study.before,study.police_mask])),
        'oldRebased':old_results,'scenarios':scenarios,'solver':study.logs,'sourceHashes':hashes,
        'limitations':[
            'Cruces originales compartidos OSM, >=3 brazos y dos vias nombradas. Se excluyen puentes/tuneles no comprobados; requiere verificacion fisica de postes y pasos a nivel.',
            'Solo se ajustan 24 urbanas. No se usan las 30 policiales para cumplir Macaji100 y Anillo80 del escenario municipal B.',
            'Los cuatro IDs senalados se restringen al eje vial nombrado. La distancia a la geometria del Anillo se informa sin desplazar artificialmente el punto ni el corredor.',
            'OSM y cartografia municipal no se homologan automaticamente: sus ejes presentan desfases geometricos y diferencias de jerarquia.',
            'Buffers de 200m son proximidad potencial, no campo visual. Vision solo en direccion de las vias; no a traves de manzanas o tras esquinas.',
            'No se fuerza una separacion de400m ni una continuidad total. Las orientaciones y obstaculos requieren comprobacion en campo.',
            'Optimizacion limitada al catalogo de vertices comprobados; se informa estado/gap real del solver. No se afirma optimo universal.',
            'No se modifica KDE, Gi*, inventario, propuestas activas, geometrias originales ni menu del visor.',
        ]}
    assert all(source_hash(Path(p))==h for p,h in hashes.items())
    report['sourcesUnchanged']=True
    save('RESULTADOS.json',report)
    save('VALIDACION.json',{'passed':True,'fixed159Unchanged':True,'sourcesUnchanged':True,
        'metricCrs':'EPSG:32717','originalSharedVertices':True,'applied':False,'published':False})
    shutil.copyfile(ROOT/'tools/current_municipal_nodes_review.html',OUT/'index.html')
    lines = ['# Municipales: estudio actualizado de 24 nodos urbanos', '',
        'NO APLICADO. NO PUBLICADO. No se ha alterado el visor activo.', '',
        '50 municipales = 24 estructurales urbanas en revision +22 rurales fijas +4 Las Abras fijas. '
        'Las 103 existentes (30 para cambio incluidas) y las 30 policiales recien publicadas permanecen fijas.', '',
        'Base: '+BASE.name+'. Calculo EPSG:32717; radio200m, quad_segs64, union real de buffers. '
        'Los porcentajes B usan103+50, sin usar Policia para alcanzar las metas municipales.', '',
        '## Comparacion actualizada', '',
        '| Escenario | Macaji % | Sin cobertura Macaji m | Anillo % | Ciclovias % | Principales | Movidas | Total movido m | Maximo m |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in scenarios:
        cov=r['municipal']
        lines.append(f"| {r['name']} | {cov[MACAJI]['pct']:.3f} | {cov[MACAJI]['uncoveredM']:.3f} | {cov[RING]['pct']:.3f} | {cov[CYCLE]['pct']:.3f} | {r['principalCount']} | {r['movedCount']} | {r['totalDisplacementM']:.2f} | {r['maxDisplacementM']:.2f} |")
    lines += ['', '## Ejes e intersecciones', '',
        'Todos los puntos estudiados son vertices compartidos originales, con tres o mas brazos y dos calles nombradas. '
        'Se excluyen puentes y tuneles no comprobados. No se crean intersecciones por un simple cruce geometrico.', '',
        'MUN-028,043,049 se vinculan al eje nombrado Avenida9deOctubre; MUN-046 al eje AvenidaEdelbertoBonillaOleas. '
        'La identidad se exige por la via fuente, no por proyectar puntos al corredor. '
        'Se informa la distancia al eje GIS del Anillo, que no coincide exactamente con las calzadas OSM.', '',
        f'Incluso seleccionando todos los nodos principales disponibles, quedan {principal_uncoverable:.3f} m de Macaji sin cubrir. '
        'No se afirma imposibilidad universal: es una limitacion del catalogo comprobado y el alcance200m. '
        'Las alternativas factibles pueden requerir nodos de calles locales; se enumeran sin presentarlos como principales.', '',
        '## Criterios y trazabilidad', '',
        'A: cruces principales distintos mas proximos, diagnostico sin forzar cobertura. '
        'C/D: seleccion conjunta con Macaji100 y Anillo>=80; C prioriza principales antes de Ciclovias; D invierte esos dos criterios. '
        'El desplazamiento se minimiza despues. No hay umbral arbitrario de separacion o solape. '
        'Los estados y gaps del solver se conservan; no se afirma optimalidad cuando se agota el tiempo.', '',
        'Cada ID conserva coordenadas anteriores/propuestas, fuente vial, IDsOSM, brazos, jerarquia y desplazamiento. '
        'Las 24 posiciones seleccionadas se asignan minimizando transporte con restricciones de eje para los cuatro IDs senalados.', '',
        '## Limitaciones', '']
    lines += ['- '+line for line in report['limitations']]
    (OUT/'INFORME.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with zipfile.ZipFile(OUT/'ESTUDIO_24_NODOS.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.iterdir()):
            if path.is_file() and path.suffix!='.zip': archive.write(path,path.name)
    print(json.dumps({'status':report['status'],'scenarios':[
        {k:v for k,v in row.items() if k not in ('movements','solver')} for row in scenarios]},ensure_ascii=True),flush=True)


if __name__=='__main__':
    main()
