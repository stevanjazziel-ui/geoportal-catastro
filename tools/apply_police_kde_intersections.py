"""Apply the reviewed police KDE/road-node proposal without altering its sources."""
import csv
import json
import math
import shutil
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely import STRtree, covers, force_2d
from shapely.geometry import Point
from shapely.ops import unary_union

from build_police_camera_proposal import (
    ROOT, CLASSES, Context, UNPROJECT, coverage_class, dv_coincidences,
    geojson, pct, read_layer, records, sha,
)
from review_police_camera_efficiency import Evaluator
from build_corridor_coverage_data import line_features, feature_collection, CORRIDOR_NAMES

BASE = ROOT / "data/seguridad-riobamba"
SOURCE = BASE / "REUBICACION_POL24_20261007_B"
SOURCE_PACKAGE = SOURCE / "ESCENARIO_FINAL_183.gpkg"
REVIEW = BASE / "propuesta-policia-kde-intersecciones-20261014"
OUT = BASE / "POLICIA_KDE_INTERSECCIONES_20261015"
PACKAGE = OUT / "ESCENARIO_FINAL_183.gpkg"
ROAD_GDB = Path("D:/codex/riobamba_matrix_review_20260921/cartografia_base/RIOBAMBA_Cartografia Base.gdb")
RADIUS = 200
ROAD_TYPES = {"Expresa", "Arterial A", "Arterial B", "Arterial P", "Colectora"}
CORRIDORS = {"BOULEVARD_MACAJI_BELLAVISTA": "MACAJI", "ANILLO_VIAL": "ANILLO", "CICLOVIAS": "CICLOVIAS", "QUEBRADA_LAS_ABRAS": "LAS_ABRAS"}


def save_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")


def save_table(name, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with (OUT / (name + ".csv")).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)
    if rows:
        pyogrio.write_dataframe(pd.DataFrame(rows), PACKAGE, layer=name)


def save_layer(name, rows, visual=False):
    if rows:
        frame = gpd.GeoDataFrame([p for _, p in rows], geometry=[g for g, _ in rows], crs=32717)
    else:
        frame = gpd.GeoDataFrame({"ID": pd.Series(dtype="str")}, geometry=gpd.GeoSeries([], crs=32717))
    pyogrio.write_dataframe(frame, PACKAGE, layer=name)
    if visual:
        save_json(name + ".geojson", geojson(rows))


def lines(geometry):
    if geometry.is_empty:
        return
    if geometry.geom_type == "LineString":
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from lines(part)


def incident_metrics(events, mask, urban, canton):
    points = np.asarray([g for g, _ in events], dtype=object)
    in_urban, in_canton, covered = covers(urban, points), covers(canton, points), covers(mask, points)
    categories = np.asarray([p["CATEGORIA"] for _, p in events])
    scopes = {"BASE_COMPLETA": np.ones(len(events), dtype=bool), "URBANO": in_urban,
              "CANTONAL": in_canton, "RESTO_CANTON": in_canton & ~in_urban,
              "EXTERNO_CANTON": ~in_canton}
    output = []
    for scope, included in scopes.items():
        for category in CLASSES:
            selected = included & (categories == category)
            total, count = int(selected.sum()), int((selected & covered).sum())
            output.append({"ESCENARIO": "C", "AMBITO": scope, "CATEGORIA": category,
                           "TOTAL": total, "CUBIERTOS": count, "NO_CUBIERTOS": total-count,
                           "PCT_CUBIERTO": pct(count, total)})
    return output, covered


def update_statistics(statistics, mask):
    updated, metrics = {}, []
    for (scope, category), cells in statistics.items():
        rows, grouped = [], {}
        for geom, properties in cells:
            fraction = geom.intersection(mask).area / geom.area if geom.area else 0
            state = coverage_class(fraction)
            props = {**properties, "COB_C_PCT": 100*fraction, "ESTADO_C": state}
            rows.append((geom, props))
            level = int(props.get("NIVEL") or 0)
            row = grouped.setdefault(level, {"ESCENARIO": "C", "AMBITO": scope, "CATEGORIA": category,
                "NIVEL": level, "TOTAL": 0, "CUBIERTO": 0, "PARCIAL": 0, "SIN_COBERTURA": 0,
                "CON_ALGUNA_COBERTURA": 0, "AREA_TOTAL_M2": 0., "AREA_CUBIERTA_M2": 0.})
            row["TOTAL"] += 1
            row["AREA_TOTAL_M2"] += geom.area
            row["AREA_CUBIERTA_M2"] += geom.area*fraction
            row[{"CUBIERTO": "CUBIERTO", "PARCIALMENTE CUBIERTO": "PARCIAL", "SIN COBERTURA": "SIN_COBERTURA"}[state]] += 1
            row["CON_ALGUNA_COBERTURA"] += int(state != "SIN COBERTURA")
        for row in grouped.values():
            row["PCT_AREA_CUBIERTA"] = pct(row["AREA_CUBIERTA_M2"], row["AREA_TOTAL_M2"])
            metrics.append(row)
        updated[(scope, category)] = rows
    return updated, metrics


def corridor_view(axes, masks, existing, municipal, police):
    groups = {"existing": existing, "municipal": municipal, "police": police}
    group_names = {"existing": "103 existentes", "municipal": "50 municipales", "police": "30 Policia"}
    labels = {"A": "EXISTENTES 103", "B": "EXISTENTES + MUNICIPALES 153", "C": "SISTEMA COMPLETO 183"}
    output = {"metadata": {"radiusM": RADIUS, "metricCrs": "EPSG:32717", "visualCrs": "EPSG:4326",
        "sourcePackage": OUT.name, "corridors": list(axes), "scenarioLabels": labels},
        "corridorNames": CORRIDOR_NAMES, "scenarios": {}}
    for code, included in [("A", ("existing",)), ("B", ("existing", "municipal")), ("C", tuple(groups))]:
        cameras = []
        for group in included:
            for point, props in groups[group]:
                camera_id = props.get("ID_CAMARA") or props.get("ID_PROPUESTA") or props.get("ID_POLICIA")
                lon, lat = UNPROJECT(point.x, point.y)
                cameras.append({"point": point, "disk": point.buffer(RADIUS, quad_segs=64),
                    "props": {**props, "ID": camera_id}, "id": camera_id, "group": group,
                    "origin": group_names[group], "type": props.get("TIPO") or "Camara",
                    "requiresChange": bool(props.get("REQUIERE_CAMBIO")) if group == "existing" else False,
                    "lng": lon, "lat": lat})
        current = {"label": labels[code], "corridors": {}, "cameras": []}
        for key, axis in axes.items():
            covered, gap = axis.intersection(masks[code]), axis.difference(masks[code])
            contributing, references = [], []
            for camera in cameras:
                length = camera["disk"].intersection(axis).length
                value = {k: camera[k] for k in ("id", "group", "origin", "type", "requiresChange", "lng", "lat")}
                value.update({"lengthM": length, "status": "CONTRIBUYE" if length > .01 else "REFERENCIA_SIN_INTERSECCION"})
                if length > .01:
                    contributing.append(value)
                if camera["props"].get("CORREDOR") == key:
                    references.append(value)
            current["corridors"][key] = {"name": CORRIDOR_NAMES[key], "totalM": axis.length,
                "coveredM": covered.length, "uncoveredM": gap.length, "coveredPct": pct(covered.length, axis.length),
                "covered": feature_collection(line_features(covered, key, "CUBIERTO", key+"-CUB", cameras)),
                "uncovered": feature_collection(line_features(gap, key, "SIN_COBERTURA", key+"-SIN", cameras)),
                "cameras": contributing, "referenceCameras": references}
        for camera in cameras:
            relevant = []
            for key, corridor in current["corridors"].items():
                contribution = next((r for r in corridor["cameras"] if r["id"] == camera["id"]), None)
                reference = next((r for r in corridor["referenceCameras"] if r["id"] == camera["id"]), None)
                value = contribution or reference
                if value:
                    relevant.append({"key": key, "name": CORRIDOR_NAMES[key], "lengthM": value["lengthM"], "status": value["status"]})
            if relevant:
                current["cameras"].append({**{k: camera[k] for k in ("id", "group", "origin", "type", "requiresChange", "lng", "lat")}, "corridors": relevant})
        output["scenarios"][code] = current
    return output


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    protected = {str(path): sha(path) for path in SOURCE.iterdir() if path.is_file()}
    review = json.loads((REVIEW / "RESULTADOS.json").read_text(encoding="utf-8"))
    for name, digest in review["source_sha256"].items():
        assert sha(ROOT / name) == digest, f"La fuente revisada cambio: {name}"
    prior = json.loads((SOURCE / "RESULTADOS.json").read_text(encoding="utf-8"))
    with (REVIEW / "MOVIMIENTOS_POLICIA_30.csv").open(encoding="utf-8-sig", newline="") as stream:
        moves = list(csv.DictReader(stream))
    assert len(moves) == 30 and len({p["ID_POLICIA"] for p in moves}) == 30
    if PACKAGE.exists():
        assert PACKAGE.resolve().parent == OUT.resolve()
        PACKAGE.unlink()

    def source(name):
        return records(read_layer(SOURCE_PACKAGE, name))

    immutable = {name: source(name) for name in ["CAMARAS_EXISTENTES_103_FINAL", "PROPUESTA_MUNICIPAL_50_FINAL",
        "PLATAFORMAS_TERRITORIALES", "LIMITE_CANTONAL", "UPC_INFRAESTRUCTURA", "RED_VIAL_CONTEXTO", "CORREDORES"]}
    existing, municipal = immutable["CAMARAS_EXISTENTES_103_FINAL"], immutable["PROPUESTA_MUNICIPAL_50_FINAL"]
    platforms = immutable["PLATAFORMAS_TERRITORIALES"]
    urban = unary_union([g for g, _ in platforms])
    canton = unary_union([g for g, _ in immutable["LIMITE_CANTONAL"]])
    axes = {key: unary_union([g for g, p in immutable["CORREDORES"] if p["CORREDOR"] == key]) for key in CORRIDORS}
    events, blocks = source("INCIDENTES_CLASIFICADOS"), source("MANZANAS_COBERTURA")
    statistics = {(scope, cat): source("GI_" + scope + "_" + cat) for scope in ("URBANO", "RURAL") for cat in CLASSES}
    hot = [(g, p) for rows in statistics.values() for g, p in rows if str(p["GI_CLASS"]).startswith("HOTSPOT")]
    baseline = unary_union([g for g, _ in source("COBERTURA_B")])
    masks = {code: unary_union([g for g, _ in source("COBERTURA_" + code)]) for code in ("A", "B")}
    context = Context(events, hot, dv_coincidences(statistics), baseline, [g for g, _ in existing],
                      [g for g, _ in municipal], immutable["UPC_INFRAESTRUCTURA"], blocks, urban, axes)
    old = {p["ID_POLICIA"]: (g, p) for g, p in source("PROPUESTA_POLICIA_30_FINAL")}

    roads = gpd.read_file(ROAD_GDB, layer="Vialidad_urbana").to_crs(32717)
    road_geoms = list(roads.geometry)
    road_tree = STRtree(road_geoms)
    network = unary_union([force_2d(g) for g in road_geoms])
    degree = Counter(tuple(coord[:2]) for line in lines(network) for coord in (line.coords[0], line.coords[-1]))
    node_xy = list(degree)
    node_tree = STRtree([Point(xy) for xy in node_xy])
    candidates, audits = {}, []
    for move in moves:
        camera_id = move["ID_POLICIA"]
        point = Point(float(move["X_DESPUES"]), float(move["Y_DESPUES"]))
        previous = old[camera_id][0]
        assert previous.distance(Point(float(move["X_ANTES"]), float(move["Y_ANTES"]))) < 1e-6
        node = node_xy[int(node_tree.nearest(point))]
        distance = point.distance(Point(node))
        nearby = [int(i) for i in road_tree.query(point.buffer(.05)) if point.distance(road_geoms[int(i)]) <= .05]
        principal = [i for i in nearby if str(roads.iloc[i]["TIPOLOGIA_"]).strip() in ROAD_TYPES]
        assert distance < 1e-6 and degree[node] >= 3 and principal and urban.covers(point), camera_id
        names = sorted({str(roads.iloc[i]["NOMBRE"]).strip() for i in nearby if pd.notna(roads.iloc[i]["NOMBRE"]) and str(roads.iloc[i]["NOMBRE"]).strip()})
        node_name = " x ".join(names) if len(names) >= 2 else "Nodo vial en " + (names[0] if names else move["NOMBRE_VIA_PRINCIPAL"])
        candidate = context.candidate({"point": point, "id": move["ID_CANDIDATO_NUEVO"], "degree": degree[node], "props": {}, "origins": {node_name}})
        candidate["scope"] = "URBANO"
        candidate["props"] = context.description(candidate)
        candidates[camera_id] = candidate
        audits.append({"ID_POLICIA": camera_id, "X_ANTES": previous.x, "Y_ANTES": previous.y,
            "X_DESPUES": point.x, "Y_DESPUES": point.y, "DESPLAZAMIENTO_M": previous.distance(point),
            "DECISION": "REUBICAR" if previous.distance(point) > 1 else "MANTENER",
            "INTERSECCION_O_NODO": node_name, "GRADO_NODO": degree[node], "DISTANCIA_NODO_M": distance,
            "TIPO_VIA_PRINCIPAL": "|".join(sorted({str(roads.iloc[i]["TIPOLOGIA_"]).strip() for i in principal})),
            "MASA_KDE_DV_NUEVA_SELECCION": float(move["MASA_KDE_DV_NUEVA"]),
            "SOLAPE_DURANTE_SELECCION_PCT": float(move["SOLAPE_PREVIO_PCT"])})
    assert len({c["point"].wkb for c in candidates.values()}) == 30
    evaluator = Evaluator(context)
    police, exclusive_rows, overlap_rows = [], [], []
    for audit in audits:
        camera_id = audit["ID_POLICIA"]
        c = candidates[camera_id]
        others = [v for key, v in candidates.items() if key != camera_id]
        evaluator.prepare(unary_union([baseline] + [other["disk"] for other in others]))
        metrics = evaluator.evaluate(c, [other["point"] for other in others])
        exclusive, overlap = c["disk"].difference(evaluator.coverage), c["disk"].intersection(evaluator.coverage)
        lon, lat = UNPROJECT(c["point"].x, c["point"].y)
        platform_names = [p["platform_name"] for g, p in platforms if g.covers(c["point"])]
        props = {**c["props"], **metrics, **audit, "ID_CANDIDATO": c["id"], "X": c["point"].x, "Y": c["point"].y,
            "LONGITUD": lon, "LATITUD": lat, "PLATAFORMA": "|".join(platform_names),
            "ESTADO": "PROPUESTA_KDE_INTERSECCION_NO_INSTALADA", "DECISION_FINAL": audit["DECISION"],
            "CRITERIO": "KDE urbano Delincuencia + Violencia; Gi* de referencia", "RADIO_M": RADIUS,
            "COBERTURA_VISUAL_CERTIFICADA": False, "AREA_BUFFER_M2": c["disk"].area,
            "AREA_EXCLUSIVA_M2": exclusive.area, "AREA_SOLAPADA_M2": overlap.area,
            "SOLAPE_PCT": metrics["SOLAPE_PREVIO_PCT"], "BENEFICIO_CONTEXTO": "103 existentes + 50 municipales + otras 29 policiales; no sumar aportes individuales",
            "JUSTIFICACION": f"Interseccion real de grado {c['degree']}: {audit['INTERSECCION_O_NODO']}. Seleccion por aporte marginal de KDE urbano D+V; Gi* como referencia. En el conjunto final aporta {metrics['EVENTOS_D_NUEVOS']} D y {metrics['EVENTOS_V_NUEVOS']} V exclusivos; solape {metrics['SOLAPE_PREVIO_PCT']:.2f}%. Continuidad visual por ejes como objetivo parcial; requiere validar orientacion y obstaculos en campo."}
        police.append((c["point"], props))
        exclusive_rows.append((exclusive, {"ID_POLICIA": camera_id, "AREA_M2": exclusive.area}))
        overlap_rows.append((overlap, {"ID_POLICIA": camera_id, "AREA_M2": overlap.area}))
    police_mask = unary_union([c["disk"] for c in candidates.values()])
    masks["C"] = unary_union([baseline, police_mask])
    assert baseline.difference(masks["C"]).area < .01
    assert len(existing) == 103 and len(municipal) == 50 and sum(bool(p["REQUIERE_CAMBIO"]) for _, p in existing) == 31
    assert Counter(p["GRUPO"] for _, p in municipal) == {"CABECERA_RURAL": 22, "LAS_ABRAS": 4, "RED_ESTRUCTURAL": 24}

    for name, rows in immutable.items():
        save_layer(name, rows)
    for name in ["CAMARAS_EXISTENTES_103_FINAL.geojson", "PROPUESTA_MUNICIPAL_50_FINAL.geojson", "RADIOS_EXISTENTES_SIMBOLOGIA_200M.geojson", "COBERTURA_MUNICIPAL_200M.geojson", "PLATAFORMAS_TERRITORIALES.geojson", "CORREDORES.geojson"]:
        shutil.copy2(SOURCE / name, OUT / name)
    for code in ("A", "B"):
        save_layer("COBERTURA_" + code, source("COBERTURA_" + code))
    save_layer("COBERTURA_C", [(masks["C"], {"ESCENARIO": "C", "RADIO_M": RADIUS, "TOTAL_EQUIPOS": 183})], True)
    save_layer("COBERTURA_POLICIA_200M", [(police_mask, {"RADIO_M": RADIUS, "TOTAL_EQUIPOS": 30})], True)
    save_layer("COBERTURA_MUNICIPAL_200M", source("COBERTURA_MUNICIPAL_200M"))
    save_layer("PROPUESTA_POLICIA_30_FINAL", police, True)
    save_layer("AREAS_EXCLUSIVAS_POLICIA_FINAL", exclusive_rows, True)
    save_layer("AREAS_SOLAPADAS_POLICIA_FINAL", overlap_rows, True)
    save_layer("ESCENARIO_FINAL_183", [(g, {**p, "ID_EQUIPO": p["ID_CAMARA"], "GRUPO_ESCENARIO": "EXISTENTE"}) for g, p in existing]
        + [(g, {**p, "ID_EQUIPO": p["ID_PROPUESTA"], "GRUPO_ESCENARIO": "MUNICIPAL_PROPUESTA"}) for g, p in municipal]
        + [(g, {**p, "ID_EQUIPO": p["ID_POLICIA"], "GRUPO_ESCENARIO": "POLICIA_PROPUESTA"}) for g, p in police])
    incidents_c, event_covered = incident_metrics(events, masks["C"], urban, canton)
    source_totals = {(r["AMBITO"], r["CATEGORIA"]): r["TOTAL"] for r in prior["incidents"] if r["ESCENARIO"] == "C"}
    assert all(source_totals[(r["AMBITO"], r["CATEGORIA"])] == r["TOTAL"] for r in incidents_c)
    save_layer("INCIDENTES_CLASIFICADOS", [(g, {**p, "CUB_C": bool(covered)}) for (g, p), covered in zip(events, event_covered)])
    updated_blocks = []
    for geom, props in blocks:
        fraction = geom.intersection(masks["C"]).area / geom.area if geom.area else 0
        updated_blocks.append((geom, {**props, "COB_C_PCT": 100*fraction,
            "POB_C_CUBIERTA": props["POBLACION"]*fraction if props.get("POBLACION") is not None else None}))
    save_layer("MANZANAS_COBERTURA", updated_blocks)
    updated_stats, hotspots_c = update_statistics(statistics, masks["C"])
    for (scope, category), rows in updated_stats.items():
        save_layer("GI_" + scope + "_" + category, rows)
        save_layer(("HOTSPOT_" if scope == "URBANO" else "HOTSPOT_RURAL_") + category, [(g, p) for g, p in rows if str(p["GI_CLASS"]).startswith("HOTSPOT")])
    for category in CLASSES:
        save_json("HOTSPOT_" + category + ".geojson", geojson([(g, p) for (scope, cat), rows in updated_stats.items() if cat == category for g, p in rows if str(p["GI_CLASS"]).startswith("HOTSPOT")]))

    corridors_c = []
    for key, axis in axes.items():
        covered, gap = axis.intersection(masks["C"]), axis.difference(masks["C"])
        corridors_c.append({"ESCENARIO": "C", "CORREDOR": key, "TOTAL_M": axis.length,
            "CUBIERTO_M": covered.length, "NO_CUBIERTO_M": gap.length, "PCT_CUBIERTO": pct(covered.length, axis.length)})
        segments = [(part, {"ID": f"{CORRIDORS[key]}-{i:04d}", "CORREDOR": key, "LONGITUD_M": part.length}) for i, part in enumerate(lines(gap), 1)]
        save_layer("BRECHA_" + CORRIDORS[key] + "_FINAL", segments, True)
    assert next(r for r in corridors_c if r["CORREDOR"] == "BOULEVARD_MACAJI_BELLAVISTA")["NO_CUBIERTO_M"] < .01
    population_c = dict(next(r for r in prior["population"] if r["ESCENARIO"] == "C"))
    population_c["POBLACION_CUBIERTA"] = context.population(masks["C"])[0]
    population_c["POBLACION_NO_CUBIERTA"] = population_c["POBLACION_ANALIZADA"] - population_c["POBLACION_CUBIERTA"]
    population_c["PCT_CUBIERTO"] = pct(population_c["POBLACION_CUBIERTA"], population_c["POBLACION_ANALIZADA"])
    territorial_c = {"ESCENARIO": "C", "AREA_TOTAL_URBANA_KM2": urban.area/1e6,
        "AREA_CUBIERTA_URBANA_KM2": masks["C"].intersection(urban).area/1e6,
        "PCT_URBANO": pct(masks["C"].intersection(urban).area, urban.area),
        "AREA_TOTAL_CANTON_KM2": canton.area/1e6, "AREA_CUBIERTA_CANTON_KM2": masks["C"].intersection(canton).area/1e6,
        "PCT_CANTON": pct(masks["C"].intersection(canton).area, canton.area), "BUFFER_DISUELTO_KM2": masks["C"].area/1e6}
    results = {"generatedAt": datetime.now(ZoneInfo("America/Guayaquil")).isoformat(), "status": "POLICIA_KDE_INTERSECCIONES_APLICADA",
        "radiusM": RADIUS, "crsMetric": "EPSG:32717", "sourcePackage": str(SOURCE_PACKAGE.relative_to(ROOT)),
        "sourceHashes": protected, "counts": {"existing": 103, "changeIncluded": 31, "municipal": 50, "police": 30},
        "selectionMethod": review["selection_method"], "giRecalculated": False,
        "policeChanges": audits, "policeMetrics": [p for _, p in police], "kdeComparison": review["comparison_before_after"],
        "warnings": ["Continuidad visual por ejes como objetivo parcial por cantidad de camaras; no visibilidad certificada.", "Radios geometricos de 200 m; validar poste, orientacion y obstaculos en campo.", "KDE principal D+V; Gi* de referencia. Corredores como efecto secundario."]}
    for key, current in [("territorial", [territorial_c]), ("population", [population_c]), ("incidents", incidents_c), ("hotspots", hotspots_c), ("corridors", corridors_c)]:
        results[key] = [row for row in prior[key] if row["ESCENARIO"] != "C"] + current
        assert [row for row in results[key] if row["ESCENARIO"] != "C"] == [row for row in prior[key] if row["ESCENARIO"] != "C"]
    for name, rows in [("POLICIA_BENEFICIO_FINAL", results["policeMetrics"]), ("MOVIMIENTOS_POLICIA_30", audits),
        ("INCIDENTES_CUBIERTOS_FINAL", results["incidents"]), ("HOTSPOTS_ATENDIDOS_FINAL", results["hotspots"]), ("CORREDORES_CUBIERTOS_FINAL", results["corridors"])]:
        save_table(name, rows)
    save_json("RESULTADOS.json", results)
    save_json("CORRIDOR_COVERAGE_200M.json", corridor_view(axes, masks, existing, municipal, police))
    validation = {"status": "PASS", "policeCount": 30, "uniquePoliceNodes": 30,
        "relocatedOver1m": sum(r["DESPLAZAMIENTO_M"] > 1 for r in audits), "allOnPrincipalIntersections": True,
        "minimumNodeDegree": min(r["GRADO_NODO"] for r in audits), "maximumNodeDistanceM": max(r["DISTANCIA_NODO_M"] for r in audits),
        "existing103Preserved": True, "municipal50Preserved": True, "giStatisticsPreserved": True,
        "kdeSourcePreserved": True, "scenariosABPreserved": True, "originalFilesPreserved": all(sha(Path(path)) == digest for path, digest in protected.items())}
    assert validation["originalFilesPreserved"]
    for category, short in [("DELINCUENCIA", "D"), ("VIOLENCIA", "V")]:
        observed = next(r["CUBIERTOS"] for r in incidents_c if r["AMBITO"] == "URBANO" and r["CATEGORIA"] == category)
        assert observed == review["comparison_before_after"]["events_" + short + "_after"]
    save_json("VALIDACION.json", validation)
    report = "# Policia: KDE urbano e intersecciones principales\n\n"
    report += "Se aplica la alternativa revisada de 30 camaras policiales; 29 reubicaciones y una posicion conservada. Las 103 existentes y las 50 municipales se conservan.\n\n"
    report += "Criterio principal: aporte marginal de KDE urbano Delincuencia + Violencia; kernel gaussiano truncado de 200 m, celda de 20 m y peso 1 por registro. Gi* permanece como referencia sin recalculo. Los nodos son intersecciones reales de grado >=3 sobre vias Expresa, Arterial A/B/P o Colectora de la cartografia municipal.\n\n"
    report += "Se busca continuidad de observacion por ejes, con cumplimiento parcial por cantidad limitada de camaras. La union de radios geometricos no certifica linea de vista. Validar poste, altura, orientacion y obstaculos en campo.\n\n"
    report += "Coberturas y atributos de las nuevas posiciones recalculados en EPSG:32717. Se conserva la asignacion estricta de eventos a manzanas; no se mueven incidentes ni se recalcula brecha territorial.\n\n"
    report += "| Corredor | Cobertura sistema 183 | Sin cobertura (m) |\n|---|---:|---:|\n"
    for row in corridors_c:
        report += f"| {row['CORREDOR']} | {row['PCT_CUBIERTO']:.3f}% | {row['NO_CUBIERTO_M']:.3f} |\n"
    report += "\nLos corredores son efectos secundarios de la ubicacion policial, no objetivos de su seleccion.\n"
    (OUT / "INFORME_FINAL.md").write_text(report, encoding="utf-8")
    with zipfile.ZipFile(OUT / "ENTREGA_POLICIA_KDE.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.iterdir()):
            if path.suffix.lower() in {".gpkg", ".csv", ".json", ".geojson", ".md"}:
                archive.write(path, arcname=path.name)
    print(json.dumps({"validation": validation, "territorial": territorial_c, "population": population_c,
        "urbanIncidents": [r for r in incidents_c if r["AMBITO"] == "URBANO"], "corridors": corridors_c}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
