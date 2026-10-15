"""Read-only municipal intersection study. Never edits the visor or active GIS files."""
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from scipy.optimize import Bounds, LinearConstraint, linear_sum_assignment, milp
from scipy.sparse import coo_matrix, csr_matrix, hstack
from scipy.sparse.csgraph import dijkstra
from shapely import STRtree, force_2d
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from build_police_camera_proposal import ROOT, read_layer, records, sha, geojson, UNPROJECT
from adjust_macaji_100 import interval_constraints
from review_police_kde_intersections import parts, ROAD_GDB, MAJOR

BASE = ROOT / "data/seguridad-riobamba"
SOURCE = BASE / "POLICIA_KDE_INTERSECCIONES_20261015"
PACKAGE = SOURCE / "ESCENARIO_FINAL_183.gpkg"
OUT = BASE / "ESTUDIO_MUNICIPALES_24_INTERSECCIONES_20261015"
MACAJI, RING, CYCLE = "BOULEVARD_MACAJI_BELLAVISTA", "ANILLO_VIAL", "CICLOVIAS"
KEYS = (MACAJI, RING, CYCLE)
RADIUS, TOL = 200, .001


def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")


def table(name, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (OUT/name).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def export(name, rows):
    if rows:
        frame = gpd.GeoDataFrame([p for _, p in rows], geometry=[g for g, _ in rows], crs=32717)
        pyogrio.write_dataframe(frame, OUT/"ESTUDIO_MUNICIPALES_24.gpkg", layer=name)
    save(name+".geojson", geojson(rows))


def buffer(rows):
    return unary_union([g.buffer(RADIUS, quad_segs=64) for g, _ in rows])


def road_data():
    roads = read_layer(ROAD_GDB, "Vialidad_urbana")
    network = unary_union(list(roads.geometry))
    lines = list(parts(network))
    degree = Counter(tuple(c[:2]) for line in lines for c in (line.coords[0], line.coords[-1]))
    coordinates = sorted(degree)
    index = {xy: i for i, xy in enumerate(coordinates)}
    rr, cc, vv = [], [], []
    # Retain the shortest parallel edge, not their sum in the sparse matrix.
    edges = {}
    for line in lines:
        a, b = index[tuple(line.coords[0][:2])], index[tuple(line.coords[-1][:2])]
        if a != b:
            key = tuple(sorted((a, b)))
            edges[key] = min(edges.get(key, math.inf), line.length)
    for (a, b), length in edges.items():
        rr.extend((a, b)); cc.extend((b, a)); vv.extend((length, length))
    graph = csr_matrix((vv, (rr, cc)), shape=(len(coordinates), len(coordinates)))
    digest = hashlib.sha256()
    for geom, props in records(roads):
        digest.update(geom.wkb)
        digest.update(json.dumps({k: props.get(k) for k in ("NOMBRE", "TXT", "TIPOLOGIA_")}, sort_keys=True).encode())
    return roads, network, coordinates, degree, index, graph, digest.hexdigest()


class Study:
    def __init__(self):
        self.existing = records(read_layer(PACKAGE, "CAMARAS_EXISTENTES_103_FINAL"))
        self.municipal = records(read_layer(PACKAGE, "PROPUESTA_MUNICIPAL_50_FINAL"))
        self.police = records(read_layer(PACKAGE, "PROPUESTA_POLICIA_30_FINAL"))
        self.original = [r for r in self.municipal if r[1]["GRUPO"] == "RED_ESTRUCTURAL"]
        self.frozen = [r for r in self.municipal if r[1]["GRUPO"] != "RED_ESTRUCTURAL"]
        assert len(self.original) == 24 and len(self.frozen) == 26
        assert Counter(p["GRUPO"] for _, p in self.frozen) == {"CABECERA_RURAL": 22, "LAS_ABRAS": 4}
        self.fixed = buffer(self.existing + self.frozen)
        self.police_mask = buffer(self.police)
        self.before = buffer(self.existing+self.municipal)
        axes = records(read_layer(PACKAGE, "CORREDORES"))
        self.axes = {key: unary_union([g for g, p in axes if p["CORREDOR"] == key]) for key in KEYS}
        self.roads, self.network, self.xy, self.degree, self.node_index, self.graph, self.road_hash = road_data()
        self.nodes = [Point(xy) for xy in self.xy]
        self.node_tree = STRtree(self.nodes)
        self.road_tree = STRtree(list(self.roads.geometry))
        self.major = unary_union(list(self.roads[self.roads.TIPOLOGIA_.astype(str).str.strip().isin(MAJOR)].geometry))
        canton = read_layer(PACKAGE, "LIMITE_CANTONAL").geometry.union_all()
        fixed_points = STRtree([g for g, _ in self.existing+self.frozen+self.police])
        self.candidates = []
        for xy in self.xy:
            point = Point(xy)
            if self.degree[xy] < 3 or not canton.covers(point):
                continue
            if point.distance(fixed_points.geometries[int(fixed_points.nearest(point))]) < 1e-6:
                continue
            self.candidates.append((point, {"ID_CANDIDATO": f"NODO-{self.node_index[xy]:05d}",
                "GRADO_NODO": self.degree[xy], "VIA_PRINCIPAL": self.major.distance(point) <= .05,
                "INDICE_RED": self.node_index[xy]}))
        self.principal = [r for r in self.candidates if r[1]["VIA_PRINCIPAL"]]
        self.baseline = self.coverage(self.before)
        self.logs = []

    def node_description(self, point, props):
        nearby = [int(i) for i in self.road_tree.query(point.buffer(.05))
                  if self.roads.geometry.iloc[int(i)].distance(point) <= .05]
        names = sorted({str(self.roads.iloc[i].TXT).strip() for i in nearby
            if pd.notna(self.roads.iloc[i].TXT) and str(self.roads.iloc[i].TXT).strip()
            and "sin nombre" not in str(self.roads.iloc[i].TXT).lower()})
        parishes = sorted({str(self.roads.iloc[i].NOMBRE).strip() for i in nearby
            if pd.notna(self.roads.iloc[i].NOMBRE) and str(self.roads.iloc[i].NOMBRE).strip()})
        types = sorted({str(self.roads.iloc[i].TIPOLOGIA_).strip() for i in nearby if pd.notna(self.roads.iloc[i].TIPOLOGIA_)})
        node_label = " x ".join(names) if len(names) >= 2 else ("Nodo en "+names[0]+" (otra via sin nombre confirmado)" if names else "Cruce sin nombres viales confirmados")
        return {**props, "CRUCE_O_NODO": node_label, "PARROQUIA_RED": " | ".join(parishes),
                "ID_TRAMOS_TARGET_FID": "|".join(str(int(self.roads.iloc[i].TARGET_FID)) for i in sorted(nearby)),
                "CAMPO_NOMBRE_VIAL": "TXT", "NOMBRES_CRUCE_PENDIENTES": len(names) < 2 or any("\ufffd" in name for name in names),
                "VIAS": " | ".join(names), "TIPOLOGIAS": " | ".join(types),
                "FUENTE": "Cartografia municipal / Vialidad_urbana", "CRS": "EPSG:32717"}

    def coverage(self, mask):
        return {key: {"totalM": axis.length, "coveredM": axis.intersection(mask).length,
            "uncoveredM": axis.difference(mask).length, "pct": 100*axis.intersection(mask).length/axis.length}
            for key, axis in self.axes.items()}

    def nearest(self, catalog):
        distances = np.asarray([[point.distance(candidate) for candidate, _ in catalog] for point, _ in self.original])
        rows, cols = linear_sum_assignment(distances)
        return [(self.original[i], catalog[j]) for i, j in zip(rows, cols)]

    def describe_scenario(self, code, pairing, note, solver=None):
        urban = [(candidate, props) for _, (candidate, props) in pairing]
        mask = unary_union([self.fixed, buffer(urban)])
        system = unary_union([mask, self.police_mask])
        nodes = [int(p["INDICE_RED"]) for _, p in urban]
        distances = dijkstra(self.graph, directed=False, indices=nodes)
        links = []
        pairs = set()
        # 400 m illustrates two theoretical reaches of 200 m along the network.
        # It is a diagnostic threshold from the user's sketch, never a visibility guarantee.
        for i, (before, (point, props)) in enumerate(pairing):
            reachable = [(float(distances[i, target]), j) for j, target in enumerate(nodes) if i != j and np.isfinite(distances[i, target])]
            distance, other = min(reachable, default=(None, None))
            if other is not None and distance <= 2*RADIUS + TOL:
                pairs.add(tuple(sorted((i, other))))
            links.append({"ID_PROPUESTA": before[1]["ID_PROPUESTA"],
                "CAMARA_PROPUESTA_MAS_CERCANA_POR_RED": pairing[other][0][1]["ID_PROPUESTA"] if other is not None else None,
                "DIST_RED_A_OTRA_24_M": distance,
                "CONEXION_TEORICA_HASTA_400M": distance is not None and distance <= 2*RADIUS+TOL})
        movements, point_rows, arrows = [], [], []
        for i, ((old, prior), (point, candidate)) in enumerate(pairing):
            props = self.node_description(point, candidate)
            lon, lat = UNPROJECT(point.x, point.y)
            overlap = point.buffer(RADIUS, quad_segs=64).intersection(unary_union([self.fixed]+[q.buffer(RADIUS, quad_segs=64) for j, (q, _) in enumerate(urban) if j != i])).area
            disk_area = point.buffer(RADIUS, quad_segs=64).area
            row = {"ESCENARIO": code, "ID_PROPUESTA": prior["ID_PROPUESTA"], "X_ANTES": old.x, "Y_ANTES": old.y,
                "X_ESTUDIO": point.x, "Y_ESTUDIO": point.y, "LONGITUD_ESTUDIO": lon, "LATITUD_ESTUDIO": lat,
                "DESPLAZAMIENTO_M": old.distance(point), "AZIMUT_GRADOS": (math.degrees(math.atan2(point.x-old.x, point.y-old.y))+360)%360 if old.distance(point) > 1e-6 else None,
                **props, **links[i], "SOLAPE_MUNICIPAL_PCT": 100*overlap/disk_area,
                "ESTADO": "ALTERNATIVA_NO_APLICADA", "VISIBILIDAD_CERTIFICADA": False}
            movements.append(row); point_rows.append((point, row))
            if old.distance(point) > 1e-6:
                arrows.append((LineString([old, point]), row))
        coverage = self.coverage(mask)
        displacements = [r["DESPLAZAMIENTO_M"] for r in movements]
        result = {"scenario": code, "description": note, "corridorsMunicipal": coverage,
            "corridorsSystem183": self.coverage(system), "policeUsedForMunicipalTargets": False,
            "municipalTotal": 50, "urbanStructural": 24, "principalIntersections": sum(p["VIA_PRINCIPAL"] for _, p in urban),
            "movedOver1m": sum(d > 1 for d in displacements), "totalDisplacementM": sum(displacements),
            "medianDisplacementM": float(np.median(displacements)), "maxDisplacementM": max(displacements),
            "meanOverlapPct": float(np.mean([r["SOLAPE_MUNICIPAL_PCT"] for r in movements])),
            "maxOverlapPct": max(r["SOLAPE_MUNICIPAL_PCT"] for r in movements),
            "camerasWithAnother24Within400mByRoad": sum(r["CONEXION_TEORICA_HASTA_400M"] for r in links),
            "uniqueNearestRoadLinksWithin400m": len(pairs), "solver": solver,
            "hardGoalsMet": coverage[MACAJI]["uncoveredM"] <= TOL and coverage[RING]["pct"] >= 80-1e-8,
            "cycleBaselinePreserved": coverage[CYCLE]["coveredM"] >= self.baseline[CYCLE]["coveredM"]-TOL}
        table(code+"_MOVIMIENTOS.csv", movements)
        export(code+"_PUNTOS", point_rows)
        export(code+"_MOVIMIENTOS", arrows)
        return result

    def solve_catalog(self, catalog, label, priority="main", time_limit=60):
        # Drop nodes incapable of affecting any unprotected corridor interval.
        targets = {key: axis.difference(self.fixed) for key, axis in self.axes.items()}
        pool = [(g, p) for g, p in catalog if any(g.distance(axis) < RADIUS for axis in targets.values() if not axis.is_empty)]
        _, impossible, disks, lengths = interval_constraints([(key, axis, self.fixed) for key, axis in self.axes.items()], pool)
        if impossible.get(MACAJI, 0) > TOL:
            log = {"label": label, "status": "MACAJI_NO_CUBRIBLE_EN_CATALOGO", "catalogCount": len(pool), "uncoverableM": impossible}
            self.logs.append(log)
            print(json.dumps(log), flush=True)
            return None
        intervals = [(key, support, length) for (key, support), length in lengths.items()]
        n, m = len(pool), len(intervals)
        total = n+m
        rr, cc, vv = [], [], []
        lower, upper = [], []
        for index, (key, support, length) in enumerate(intervals):
            if key == MACAJI:
                for candidate in support:
                    rr.append(index); cc.append(candidate); vv.append(1.)
                lower.append(1.); upper.append(np.inf)
            else:
                rr.append(index); cc.append(n+index); vv.append(1.)
                for candidate in support:
                    rr.append(index); cc.append(candidate); vv.append(-1.)
                lower.append(-np.inf); upper.append(0.)
        matrix = coo_matrix((vv, (rr, cc)), shape=(m, total)).tocsr()
        constraints = [LinearConstraint(matrix, lower, upper),
            LinearConstraint(csr_matrix(np.r_[np.ones(n), np.zeros(m)][None, :]), 24, 24)]
        weights = {key: np.r_[np.zeros(n), [length if label == key else 0. for label, _, length in intervals]] for key in KEYS}
        fixed_lengths = {key: axis.intersection(self.fixed).length for key, axis in self.axes.items()}
        constraints.append(LinearConstraint(csr_matrix(weights[RING][None, :]), .8*self.axes[RING].length-fixed_lengths[RING], np.inf))
        major_weights = np.r_[[int(p["VIA_PRINCIPAL"]) for _, p in pool], np.zeros(m)]
        objectives = [("PRIORIDAD_VIAS_PRINCIPALES", -major_weights), ("MAX_CICLOVIAS", -weights[CYCLE])]
        if priority == "cycle":
            objectives.reverse()
        solution = None
        for phase, objective in objectives:
            trial = milp(objective, integrality=np.r_[np.ones(n), np.zeros(m)], bounds=Bounds(np.zeros(total), np.ones(total)),
                constraints=constraints, options={"time_limit": time_limit, "mip_rel_gap": 1e-6})
            log = {"label": label, "phase": phase, "catalogCount": n, "status": int(trial.status),
                "message": trial.message, "objective": float(trial.fun) if trial.x is not None else None,
                "gap": float(trial.mip_gap) if trial.x is not None else None}
            self.logs.append(log); print(json.dumps(log), flush=True)
            if trial.x is None:
                if solution is None:
                    return None
                break
            solution = trial
            if phase == "PRIORIDAD_VIAS_PRINCIPALES":
                count = int(round(major_weights @ solution.x))
                constraints.append(LinearConstraint(csr_matrix(major_weights[None, :]), count, count))
            else:
                constraints.append(LinearConstraint(csr_matrix(weights[CYCLE][None, :]), weights[CYCLE] @ solution.x-TOL, np.inf))
        primary_proven = all(r["status"] == 0 for r in self.logs if r["label"] == label)
        # Keep both coverage objectives fixed, then minimize real ID-to-node transport.
        extra = 24*n
        wide = total+extra
        rr, cc, vv = [], [], []
        costs = np.zeros(wide)
        for old_index, (point, _) in enumerate(self.original):
            for candidate_index, (candidate, _) in enumerate(pool):
                variable = total+old_index*n+candidate_index
                rr.extend((old_index, 24+candidate_index)); cc.extend((variable, variable)); vv.extend((1., 1.))
                costs[variable] = point.distance(candidate)
        for candidate_index in range(n):
            rr.append(24+candidate_index); cc.append(candidate_index); vv.append(-1.)
        transport = coo_matrix((vv, (rr, cc)), shape=(24+n, wide)).tocsr()
        demand = np.r_[np.ones(24), np.zeros(n)]
        wide_constraints = [LinearConstraint(hstack([c.A, csr_matrix((c.A.shape[0], extra))], format="csr"), c.lb, c.ub) for c in constraints]
        wide_constraints.append(LinearConstraint(transport, demand, demand))
        distance_solution = milp(costs, integrality=np.r_[np.ones(n), np.zeros(m+extra)], bounds=Bounds(np.zeros(wide), np.ones(wide)),
            constraints=wide_constraints, options={"time_limit": time_limit, "mip_rel_gap": 1e-6})
        log = {"label": label, "phase": "MIN_DESPLAZAMIENTO_CON_OBJETIVOS_FIJOS", "status": int(distance_solution.status),
            "objective": float(distance_solution.fun) if distance_solution.x is not None else None,
            "gap": float(distance_solution.mip_gap) if distance_solution.x is not None else None}
        self.logs.append(log); print(json.dumps(log), flush=True)
        if distance_solution.x is not None:
            solution = distance_solution
        selected = [pool[i] for i in np.flatnonzero(solution.x[:n] > .5)]
        assert len(selected) == 24
        pairing = self.nearest(selected)
        candidate_mask = unary_union([self.fixed, *[g.buffer(RADIUS, quad_segs=64) for g, _ in selected]])
        assert self.axes[MACAJI].difference(candidate_mask).length <= TOL
        assert self.axes[RING].intersection(candidate_mask).length >= .8*self.axes[RING].length-TOL
        note = ("Prioridad vias principales y despues Ciclovias" if priority == "main" else "Prioridad Ciclovias y despues vias principales")
        return self.describe_scenario(label, pairing, "Seleccion conjunta en nodos reales; Macaji100 y Anillo>=80. "+note+"; distancia minimizada manteniendo los objetivos anteriores.",
            {"status": int(solution.status), "primaryObjectivesOptimalInCatalog": primary_proven,
             "displacementOptimalGivenPrimaryObjectives": distance_solution.status == 0, "catalogCount": n})

    def run(self):
        protected = {str(path): sha(path) for path in SOURCE.iterdir() if path.is_file()}
        protected.update({str(ROOT/name): sha(ROOT/name) for name in ("visor-seguridad-riobamba-v2.html", "riobamba-camaras-propuesta.js", "riobamba-conflictividad-data.js")})
        audit, alternatives = [], []
        for point, prior in self.original:
            closest_index = int(self.node_tree.nearest(point))
            nearest_node = self.nodes[closest_index]
            ranked = sorted(self.principal, key=lambda row: point.distance(row[0]))[:5]
            old_road = self.roads.iloc[int(self.road_tree.nearest(point))]
            row = {"ID_PROPUESTA": prior["ID_PROPUESTA"], "X_ACTUAL": point.x, "Y_ACTUAL": point.y,
                "ORIGEN_ACTUAL": prior.get("ORIGEN_CANDIDATO"), "GRADO_REGISTRADO": prior.get("GRADO_NODO"),
                "DIST_RED_VIAL_M": point.distance(old_road.geometry), "VIA_ACTUAL_PROXIMA": str(old_road.TXT),
                "PARROQUIA_RED_ACTUAL": str(old_road.NOMBRE),
                "TIPO_VIA_ACTUAL_PROXIMA": str(old_road.TIPOLOGIA_), "DIST_NODO_RED_M": point.distance(nearest_node),
                "GRADO_NODO_CERCANO": self.degree[self.xy[closest_index]],
                "EN_INTERSECCION_VERIFICADA": point.distance(nearest_node) <= .05 and self.degree[self.xy[closest_index]] >= 3,
                "DIST_INTERSECCION_PRINCIPAL_M": point.distance(ranked[0][0]),
                "ID_INTERSECCION_PRINCIPAL": ranked[0][1]["ID_CANDIDATO"]}
            audit.append(row)
            for rank, (candidate, props) in enumerate(ranked, 1):
                local_mask = unary_union([self.fixed, *[q.buffer(RADIUS, quad_segs=64) for q, p in self.original if p["ID_PROPUESTA"] != prior["ID_PROPUESTA"]], candidate.buffer(RADIUS, quad_segs=64)])
                coverage = self.coverage(local_mask)
                alternatives.append({"ID_PROPUESTA": prior["ID_PROPUESTA"], "ORDEN_PROXIMIDAD": rank,
                    **self.node_description(candidate, props), "X_ESTUDIO": candidate.x, "Y_ESTUDIO": candidate.y,
                    "DESPLAZAMIENTO_M": point.distance(candidate),
                    "MACAJI_SIN_COBERTURA_M_SI_SOLO_SE_MUEVE_ESTA": coverage[MACAJI]["uncoveredM"],
                    "ANILLO_PCT_SI_SOLO_SE_MUEVE_ESTA": coverage[RING]["pct"],
                    "CICLOVIAS_PCT_SI_SOLO_SE_MUEVE_ESTA": coverage[CYCLE]["pct"], "APLICADA": False})
        table("AUDITORIA_24_ACTUALES.csv", audit)
        table("ALTERNATIVAS_5_POR_CAMARA.csv", alternatives)
        export("ACTUALES_24", self.original)
        export("EXISTENTES_103_REFERENCIA", self.existing)
        export("MUNICIPALES_26_FIJAS", self.frozen)
        export("POLICIA_30_FIJA", self.police)
        export("CORREDORES_ORIGINALES", [(g, {"CORREDOR": key}) for key, g in self.axes.items()])
        scenarios = [self.describe_scenario("A_CRUCES_PRINCIPALES_CERCANOS", self.nearest(self.principal),
            "24 intersecciones principales distintas de menor desplazamiento conjunto; sin forzar conservacion de cobertura. Diagnostico, no propuesta aprobada.",
            {"assignmentOptimalInCatalog": True})]
        save("AVANCE.json", {"audit": audit, "scenarios": scenarios, "candidateCounts": {"allIntersections": len(self.candidates), "principalIntersections": len(self.principal)}})
        print("AUDITORIA", json.dumps({"verifiedCurrentIntersections": sum(r["EN_INTERSECCION_VERIFICADA"] for r in audit),
            "candidateCounts": {"all": len(self.candidates), "principal": len(self.principal)}, "nearestScenario": scenarios[0]}), flush=True)
        for catalog, label, priority in [(self.principal, "B_PRINCIPALES_CON_COBERTURA", "main"),
                (self.candidates, "C_PRIORIDAD_PRINCIPALES", "main"), (self.candidates, "D_PRIORIDAD_CICLOVIAS", "cycle")]:
            result = self.solve_catalog(catalog, label, priority=priority)
            if result:
                scenarios.append(result)
        result = {"generatedAt": datetime.now(ZoneInfo("America/Guayaquil")).isoformat(timespec="seconds"),
            "status": "ESTUDIO_NO_APLICADO", "applied": False, "commit": False, "push": False,
            "metricCrs": "EPSG:32717", "radiusM": RADIUS, "geometricToleranceM": TOL,
            "scope": "24 municipales estructurales urbanas; 103 existentes, 22 rurales, 4 Las Abras y 30 policiales fijas",
            "sourceHashes": protected, "roadSource": str(ROAD_GDB), "roadLayer": "Vialidad_urbana", "roadContentSha256": self.road_hash,
            "sourceRoads": len(self.roads), "allCandidateIntersections": len(self.candidates), "principalCandidateIntersections": len(self.principal),
            "currentVerifiedIntersections": sum(r["EN_INTERSECCION_VERIFICADA"] for r in audit), "audit": audit,
            "baselineMunicipal": self.baseline, "baselineSystem183": self.coverage(unary_union([self.before, self.police_mask])),
            "scenarios": scenarios, "solver": self.logs,
            "limitations": ["Cruces topologicos de ejes GIS en 2D: validar pasos a desnivel, poste y esquina operativa en campo.",
                "Los 400m por red ilustran dos alcances de200m; no son certificacion de visibilidad ni condicion dura para todos los puntos.",
                "Continuidad parcial por cantidad limitada de camaras. No se agrandan radios ni se cuentan otras30policiales para cumplir metas municipales.",
                "No se cambia KDE ni Gi*. KDE y eventos son contexto, no sustituyen los objetivos territoriales municipales.",
                "La factibilidad y optimalidad son relativas al catalogo GIS, no al conjunto de todas las esquinas fisicas existentes.",
                "Desplazamiento calculado entre coordenadas propuestas, no obra ejecutada. No hay autorizacion de implantacion."]}
        assert all(sha(Path(path)) == digest for path, digest in protected.items())
        save("RESULTADOS.json", result)
        write_report(result)
        print("ESTUDIO_TERMINADO", json.dumps({"currentVerifiedIntersections": result["currentVerifiedIntersections"],
            "scenarios": [{k: v for k, v in scenario.items() if k not in ("description", "corridorsSystem183")} for scenario in scenarios]}), flush=True)


def write_report(result):
    rows = ["# Estudio de 24 municipales: intersecciones y trazabilidad", "", "ESTUDIO NO APLICADO AL VISOR. Publicar el estudio no implica aprobar ni aplicar ubicaciones.", "",
        result["scope"], "", f"Cruces actuales verificados en la red municipal: {result['currentVerifiedIntersections']} de24.",
        "", "## Comparacion", "", "| Escenario | Macaji % | Macaji sin cubrir m | Anillo % | Ciclovias % | Principales | Movidas >1m | Total movido m | Mediana m | Maximo m | Cumple metas |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    b = result["baselineMunicipal"]
    rows.append(f"| ACTUAL | {b[MACAJI]['pct']:.3f} | {b[MACAJI]['uncoveredM']:.3f} | {b[RING]['pct']:.3f} | {b[CYCLE]['pct']:.3f} | - | 0 | 0 | 0 | 0 | Referencia |")
    for s in result["scenarios"]:
        c = s["corridorsMunicipal"]
        rows.append(f"| {s['scenario']} | {c[MACAJI]['pct']:.3f} | {c[MACAJI]['uncoveredM']:.3f} | {c[RING]['pct']:.3f} | {c[CYCLE]['pct']:.3f} | {s['principalIntersections']} | {s['movedOver1m']} | {s['totalDisplacementM']:.1f} | {s['medianDisplacementM']:.1f} | {s['maxDisplacementM']:.1f} | {s['hardGoalsMet']} |")
    rows += ["", "Los porcentajes de la tabla usan103existentes+50municipales. Las30policiales permanecen fijas y solo se reportan aparte en RESULTADOS.json.",
        "", "## Trazabilidad", "", "AUDITORIA_24_ACTUALES.csv identifica la situacion actual; ALTERNATIVAS_5_POR_CAMARA.csv contiene cinco cruces principales cercanos por camara y su efecto individual, no sumable.",
        "Cada escenario conserva ID_PROPUESTA, coordenadas anteriores y estudiadas, distancia, azimut, ID del nodo, grado, vias, tipologias, fuente y conexion teorica por red.",
        "La asignacion de24IDs a24posiciones seleccionadas minimiza el desplazamiento para esa seleccion; no implica que el desplazamiento sea optimo global entre todas las selecciones factibles.",
        "", "## Catalogos y solucionador", "", "```json", json.dumps(result["solver"], ensure_ascii=False, indent=2), "```", "", "## Limitaciones", ""]
    rows += ["- "+line for line in result["limitations"]]
    rows += ["", "No se modifica ninguna fuente ni archivo del visor. Revisar resultados antes de decidir una implementacion."]
    (OUT/"INFORME.md").write_text("\n".join(rows)+"\n", encoding="utf-8")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/"ESTUDIO_MUNICIPALES_24.gpkg").exists():
        raise RuntimeError("El estudio ya existe; conservarlo y utilizar otra carpeta para una revision posterior.")
    Study().run()
