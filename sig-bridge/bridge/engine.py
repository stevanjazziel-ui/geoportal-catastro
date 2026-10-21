"""Adapters for existing coverage methods, not new KDE/Gi* or camera optimization."""
import copy
import json
import math
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely import STRtree, covers, force_2d
from shapely.geometry import Point
from shapely.ops import unary_union

from .store import ROOT, BridgeError, clean, digest, now, read_json, require, write_json

sys.path.insert(0, str(ROOT / "tools"))
from build_police_camera_proposal import Context, CLASSES, UNPROJECT, dv_coincidences, geojson, pct, records, read_layer
from build_camera_population_comparison import population_comparison
from apply_police_kde_intersections import incident_metrics, update_statistics, corridor_view, CORRIDORS, lines


def dependency_plan(changes):
    geometry = {r["layer"] for r in changes if r["geometryChanged"]}
    attributes = {r["layer"] for r in changes if r["fields"]}
    scenarios = set()
    if "municipal" in geometry:
        scenarios.update(("B", "C"))
    if "police" in geometry:
        scenarios.add("C")
    jobs = []
    if scenarios:
        jobs += ["buffers", "territorial", "incident_coverage", "hotspot_coverage", "block_coverage", "population"]
    if scenarios or "corridors" in geometry:
        jobs += ["corridor_coverage"]
    if "blocks" in geometry | attributes:
        jobs += ["block_coverage", "population"]
        scenarios.update(("A", "B", "C"))
    if geometry or attributes:
        jobs += ["camera_attributes", "exclusive_coverage"]
    pending = ["census_global_and_other_modules"] if "blocks" in geometry | attributes else []
    return {"scenarios": sorted(scenarios), "jobs": sorted(set(jobs)), "pendingAdapters": pending,
            "recalculateKde": False, "recalculateGi": False, "optimizeCameras": False}


def save_layer(package, name, rows, output=None):
    if rows:
        frame = gpd.GeoDataFrame([clean(p) for _, p in rows], geometry=[g for g, _ in rows], crs=32717)
    else:
        frame = gpd.GeoDataFrame({"ID": pd.Series(dtype="str")}, geometry=gpd.GeoSeries([], crs=32717))
    pyogrio.write_dataframe(frame, package, layer=name)
    if output:
        write_json(output / (name + ".geojson"), clean(geojson(rows)))


def file_hashes(directory):
    return {p.relative_to(directory).as_posix(): digest(p) for p in sorted(directory.rglob("*")) if p.is_file()}


def audit_nodes(store, changed, municipal, police, urban):
    moved = {r["id"] for r in changed if r["geometryChanged"] and r["layer"] in ("municipal", "police")}
    if not moved:
        return [], []
    road_path = (store.root / store.config["roadSource"]).resolve()
    require(road_path.is_dir(), "Falta la fuente vial original para validar intersecciones")
    road_files = {p.name: digest(p) for p in road_path.iterdir() if p.is_file() and not p.name.lower().endswith((".lock", ".lck"))}
    roads = read_layer(road_path, "Vialidad_urbana")
    tree = STRtree(list(roads.geometry))
    network = unary_union(list(roads.geometry))
    degree = Counter(tuple(c[:2]) for line in lines(network) for c in (line.coords[0], line.coords[-1]))
    coordinates = list(degree)
    nodes = [Point(c) for c in coordinates]
    node_tree = STRtree(nodes)
    rows, failures = [], []
    for geom, props in municipal + police:
        camera_id = props.get("ID_PROPUESTA") or props.get("ID_POLICIA")
        if camera_id not in moved:
            continue
        nearest = int(node_tree.nearest(geom))
        nearby = [int(i) for i in tree.query(geom.buffer(.05)) if roads.geometry.iloc[int(i)].distance(geom) <= .05]
        major = {"Expresa", "Arterial A", "Arterial B", "Arterial P", "Colectora"}
        principal = any(str(roads.iloc[i].TIPOLOGIA_).strip() in major for i in nearby)
        names = sorted({str(roads.iloc[i].TXT).strip() for i in nearby if pd.notna(roads.iloc[i].TXT) and str(roads.iloc[i].TXT).strip()})
        passed = geom.distance(nodes[nearest]) <= .05 and degree[coordinates[nearest]] >= 3 and principal and urban.covers(geom)
        row = {"id": camera_id, "nodeDistanceM": geom.distance(nodes[nearest]), "degree": degree[coordinates[nearest]],
               "principalRoad": principal, "urban": urban.covers(geom), "roads": names,
               "targetFids": [clean(roads.iloc[i].TARGET_FID) for i in nearby], "passed": bool(passed)}
        rows.append(row)
        props.update({"INTERSECCION_O_NODO": " x ".join(names) or "Nombres viales pendientes",
                      "GRADO_NODO": degree[coordinates[nearest]], "DISTANCIA_NODO_M": row["nodeDistanceM"],
                      "TIPO_VIA_PRINCIPAL": "|".join(sorted({str(roads.iloc[i].TIPOLOGIA_) for i in nearby})),
                      "BRIDGE_NODO_VALIDADO": passed})
        if not passed:
            failures.append("Cruce principal no validado: " + camera_id)
    require(all(digest(road_path / p) == h for p, h in road_files.items()), "La red vial cambio durante la validacion")
    return rows, failures


def recalculate(store, revision_id):
    store = store.for_revision(revision_id)
    with store.lock():
        run, manual, receipt = store.snapshot(revision_id)
        output = run / "web"
        output.mkdir()
        try:
            result = calculate(store, run, output, manual, receipt)
            store.guard(read_json(store.revision(revision_id) / "revision.json"))
            require(store.validate(revision_id)["manualSha256"] == receipt["manualSha256"], "La edicion cambio durante el calculo; ejecutar nuevamente")
            manifest = {"runId": run.name, "revision": revision_id, "status": "READY" if not result["publishBlocks"] else "REVIEW_REQUIRED",
                        "createdAt": now(), "input": receipt, "validation": result, "files": file_hashes(output)}
            write_json(run / "manifest.json", manifest)
            write_json(store.revision(revision_id) / "latest.json", {"runId": run.name})
            return manifest
        except Exception as exc:
            write_json(run / "failure.json", {"createdAt": now(), "error": str(exc), "revision": revision_id})
            raise


def calculate(store, run, output, manual, receipt, existing_override=None, node_validator=None):
    config = store.config
    radius = config["radiusM"]
    require(radius == 200 and config["bufferQuadrantSegments"] == 64, "Cambiar el metodo requiere un adaptador aprobado")
    plan = dependency_plan(receipt["changes"])
    inventory_update = existing_override is not None
    if inventory_update:
        require(len(existing_override) == 103 and existing_override.ID_CAMARA.is_unique,
                "El inventario recibido requiere 103 IDs unicos")
        require(existing_override.crs.to_epsg() == 32717, "Inventario requerido en EPSG:32717")
        require(int(existing_override.REQUIERE_CAMBIO.sum()) == 30, "Se requieren 30 para cambio")
        plan = dependency_plan([{"layer": "municipal", "geometryChanged": True, "fields": []}])
        plan["scenarios"] = ["A", "B", "C"]
        plan["inventoryUpdated"] = True
    for path in store.web.iterdir():
        if path.is_file() and path.suffix.lower() in (".geojson", ".json", ".csv", ".md"):
            shutil.copy2(path, output / path.name)
    package = output / "ESCENARIO_FINAL_183.gpkg"
    store.backup(store.base, package)
    data = {}
    for name, _ in pyogrio.list_layers(store.base):
        if pyogrio.read_info(store.base, layer=name)["crs"]:
            data[name] = records(read_layer(store.base, name))
    prior = read_json(store.web / "RESULTADOS.json")
    results = copy.deepcopy(prior)
    replacements = {}
    for key, frame in manual.items():
        spec = config["layers"][key]
        edits = frame.set_index(spec["id"])
        rows = []
        for geom, properties in data[spec["source"]]:
            props = dict(properties)
            row = edits.loc[props[spec["id"]]]
            point = force_2d(row.geometry)
            props.update({name: clean(row[name]) for name in spec["editable"]})
            props["OBSERVACION_MANUAL"] = clean(row.OBSERVACION_MANUAL)
            if spec["geometry"] == "Point":
                lon, lat = UNPROJECT(point.x, point.y)
                props.update({"X": point.x, "Y": point.y, "LONGITUD": lon, "LATITUD": lat})
            rows.append((point, props))
        replacements[spec["source"]] = rows
    data.update(replacements)
    if inventory_update:
        data["CAMARAS_EXISTENTES_103_FINAL"] = records(existing_override)
        save_layer(package, "CAMARAS_EXISTENTES_103_FINAL", data["CAMARAS_EXISTENTES_103_FINAL"], output)
    existing, municipal, police = [data[name] for name in ("CAMARAS_EXISTENTES_103_FINAL", "PROPUESTA_MUNICIPAL_50_FINAL", "PROPUESTA_POLICIA_30_FINAL")]
    require([len(existing), len(municipal), len(police)] == [103, 50, 30], "Universo de camaras alterado")
    prior_groups = Counter(p["GRUPO"] for _, p in records(read_layer(store.base, "PROPUESTA_MUNICIPAL_50_FINAL")))
    require(Counter(p["GRUPO"] for _, p in municipal) == prior_groups, "Composicion municipal alterada")
    urban = unary_union([g for g, _ in data["PLATAFORMAS_TERRITORIALES"]])
    canton = unary_union([g for g, _ in data["LIMITE_CANTONAL"]])
    axes = {key: unary_union([g for g, p in data["CORREDORES"] if p["CORREDOR"] == key]) for key in CORRIDORS}
    masks = {code: data["COBERTURA_"+code][0][0] for code in ("A", "B", "C")}
    camera_moved = inventory_update or any(r["geometryChanged"] and r["layer"] in ("municipal", "police") for r in receipt["changes"])
    blocks_changed = any(r["layer"] == "blocks" and (r["geometryChanged"] or r["fields"]) for r in receipt["changes"])
    if camera_moved:
        if inventory_update:
            masks["A"] = unary_union([g.buffer(radius, quad_segs=64) for g, _ in existing])
        if "B" in plan["scenarios"]:
            masks["B"] = unary_union([masks["A"], *[g.buffer(radius, quad_segs=64) for g, _ in municipal]])
        masks["C"] = unary_union([masks["B"], *[g.buffer(radius, quad_segs=64) for g, _ in police]])
    node_audit, publish_blocks = (node_validator or audit_nodes)(store, receipt["changes"], municipal, police, urban)
    publish_blocks += ["Adaptador pendiente: " + p for p in plan["pendingAdapters"]]
    events, blocks = data["INCIDENTES_CLASIFICADOS"], data["MANZANAS_COBERTURA"]
    statistics = {(scope, cat): data["GI_"+scope+"_"+cat] for scope in ("URBANO", "RURAL") for cat in CLASSES}
    if plan["jobs"]:
        hot = [(g, p) for rows in statistics.values() for g, p in rows if str(p["GI_CLASS"]).startswith("HOTSPOT")]
        context = Context(events, hot, dv_coincidences(statistics), masks["B"], [g for g, _ in existing],
                          [g for g, _ in municipal], data["UPC_INFRAESTRUCTURA"], blocks, urban, axes)
        if camera_moved or blocks_changed:
            for scenario in plan["scenarios"]:
                mask = masks[scenario]
                if camera_moved:
                    save_layer(package, "COBERTURA_"+scenario, [(mask, {"ESCENARIO": scenario, "RADIO_M": radius})], output)
                    area = {"ESCENARIO": scenario, "AREA_TOTAL_URBANA_KM2": urban.area/1e6,
                            "AREA_CUBIERTA_URBANA_KM2": mask.intersection(urban).area/1e6,
                            "PCT_URBANO": pct(mask.intersection(urban).area, urban.area),
                            "AREA_TOTAL_CANTON_KM2": canton.area/1e6, "AREA_CUBIERTA_CANTON_KM2": mask.intersection(canton).area/1e6,
                            "PCT_CANTON": pct(mask.intersection(canton).area, canton.area), "BUFFER_DISUELTO_KM2": mask.area/1e6}
                    replace_scenario(results, "territorial", scenario, [area])
                    incident_rows, included = incident_metrics(events, mask, urban, canton)
                    for row in incident_rows:
                        row["ESCENARIO"] = scenario
                    replace_scenario(results, "incidents", scenario, incident_rows)
                    events = [(g, {**p, "CUB_"+scenario: bool(value)}) for (g, p), value in zip(events, included)]
                    current_stats, summaries = update_statistics(statistics, mask)
                    for row in summaries:
                        row["ESCENARIO"] = scenario
                    replace_scenario(results, "hotspots", scenario, summaries)
                    for key, rows in current_stats.items():
                        statistics[key] = [(g, {**old_p, "COB_"+scenario+"_PCT": p["COB_C_PCT"], "ESTADO_"+scenario: p["ESTADO_C"]})
                                           for (g, p), (_, old_p) in zip(rows, statistics[key])]
                updated = []
                for geom, props in blocks:
                    fraction = geom.intersection(mask).area / geom.area
                    updated.append((geom, {**props, "COB_"+scenario+"_PCT": 100*fraction,
                        "POB_"+scenario+"_CUBIERTA": props["POBLACION"]*fraction if props.get("POBLACION") is not None else None}))
                blocks = updated
                pop = dict(next(r for r in results["population"] if r["ESCENARIO"] == scenario))
                pop["POBLACION_CUBIERTA"] = context.population(mask)[0]
                if blocks_changed:
                    pop["POBLACION_ANALIZADA"] = sum(p["POBLACION"]*g.intersection(urban).area/g.area for g, p in blocks if p.get("POBLACION") is not None)
                pop["POBLACION_NO_CUBIERTA"] = pop["POBLACION_ANALIZADA"]-pop["POBLACION_CUBIERTA"]
                pop["PCT_CUBIERTO"] = pct(pop["POBLACION_CUBIERTA"], pop["POBLACION_ANALIZADA"])
                replace_scenario(results, "population", scenario, [pop])
            save_layer(package, "MANZANAS_COBERTURA", blocks)
            if camera_moved:
                save_layer(package, "INCIDENTES_CLASIFICADOS", events)
                for (scope, cat), rows in statistics.items():
                    save_layer(package, f"GI_{scope}_{cat}", rows)
                    save_layer(package, ("HOTSPOT_" if scope == "URBANO" else "HOTSPOT_RURAL_")+cat,
                               [(g, p) for g, p in rows if str(p["GI_CLASS"]).startswith("HOTSPOT")])
                for cat in CLASSES:
                    write_json(output / ("HOTSPOT_"+cat+".geojson"), clean(geojson([(g, p) for (scope, c), rows in statistics.items() if c == cat for g, p in rows if str(p["GI_CLASS"]).startswith("HOTSPOT")])))
        if "corridor_coverage" in plan["jobs"]:
            corridor_rows = []
            for scenario, mask in masks.items():
                for key, axis in axes.items():
                    covered, gap = axis.intersection(mask), axis.difference(mask)
                    corridor_rows.append({"ESCENARIO": scenario, "CORREDOR": key, "TOTAL_M": axis.length,
                        "CUBIERTO_M": covered.length, "NO_CUBIERTO_M": gap.length, "PCT_CUBIERTO": pct(covered.length, axis.length)})
                    if scenario == "C":
                        save_layer(package, "BRECHA_"+CORRIDORS[key]+"_FINAL", [(part, {"ID": f"{CORRIDORS[key]}-{i:04d}",
                            "CORREDOR": key, "LONGITUD_M": part.length}) for i, part in enumerate(lines(gap), 1)], output)
            results["corridors"] = corridor_rows
        # Re-evaluate point attributes and exclusivity against all other final cameras, never reselect them.
        for group, rows in (("municipal", municipal), ("police", police)):
            for i, (point, props) in enumerate(rows):
                others = [g for j, (g, _) in enumerate(rows) if j != i]
                previous = masks["A"] if group == "municipal" else masks["B"]
                prior_union = unary_union([previous, *[g.buffer(radius, quad_segs=64) for g in others]])
                c = context.candidate({"point": point, "id": props.get("ID_PROPUESTA") or props.get("ID_POLICIA"),
                    "degree": props.get("GRADO_NODO") or 0, "origins": {props.get("INTERSECCION_O_NODO") or "Ubicacion manual; nodo pendiente"}})
                c["scope"] = "URBANO" if urban.covers(point) else "RURAL"
                c["overlapB"] = 100*c["disk"].intersection(prior_union).area/c["disk"].area
                values = context.description(c)
                props.update(values)
                covered_points = np.asarray(covers(prior_union, np.asarray([g for g, _ in events], dtype=object)))
                disk_events = np.asarray(covers(c["disk"], np.asarray([g for g, _ in events], dtype=object)))
                category_values = np.asarray([p["CATEGORIA"] if p["AMBITO"] != "EXTERNO_CANTON" else "" for _, p in events])
                overlap = c["disk"].intersection(prior_union)
                props.update({"EVENTOS_D_NUEVOS": int((~covered_points & disk_events & (category_values == "DELINCUENCIA")).sum()),
                    "EVENTOS_V_NUEVOS": int((~covered_points & disk_events & (category_values == "VIOLENCIA")).sum()),
                    "SOLAPE_PREVIO_PCT": 100*overlap.area/c["disk"].area,
                    "AREA_BUFFER_M2": c["disk"].area, "AREA_EXCLUSIVA_M2": c["disk"].difference(prior_union).area,
                    "AREA_SOLAPADA_M2": overlap.area, "COBERTURA_VISUAL_CERTIFICADA": False,
                    "BRIDGE_REVISION": receipt["revision"]})
                if not inventory_update:
                    props.update({"DECISION_FINAL": "REVISION_MANUAL_NO_REOPTIMIZADA",
                        "JUSTIFICACION": "Evaluacion de revision manual; sin nueva optimizacion. " + str(props.get("OBSERVACION_MANUAL") or "")})
                props["EVENTOS_DV_NUEVOS"] = props["EVENTOS_D_NUEVOS"]+props["EVENTOS_V_NUEVOS"]
                props["DIST_POLICIA_M"] = min(point.distance(g) for g, p in police if p is not props) if group == "police" else min(point.distance(g) for g, _ in police)
                props["DIST_MUNICIPAL"] = min(point.distance(g) for g in others) if group == "municipal" else min(point.distance(g) for g, _ in municipal)
                for key, axis in axes.items():
                    props["LONGITUD_EXCLUSIVA_"+key+"_M"] = axis.intersection(c["disk"].difference(prior_union)).length
        node_map = {r["id"]: r for r in node_audit}
        for point, props in municipal + police:
            row = node_map.get(props.get("ID_PROPUESTA") or props.get("ID_POLICIA"))
            if row:
                props["INTERSECCION_O_NODO"] = " x ".join(row["roads"]) or "Nombre vial pendiente"
        results["policeMetrics"] = [p for _, p in police]
        for name, rows in (("PROPUESTA_MUNICIPAL_50_FINAL", municipal), ("PROPUESTA_POLICIA_30_FINAL", police), ("CORREDORES", data["CORREDORES"])):
            save_layer(package, name, rows, output)
        if camera_moved:
            if inventory_update:
                save_layer(package, "RADIOS_EXISTENTES_SIMBOLOGIA_200M", [(g.buffer(radius, quad_segs=64),
                    {"ID_CAMARA": p["ID_CAMARA"], "REQUIERE_CAMBIO": bool(p["REQUIERE_CAMBIO"]),
                     "RADIO_M": radius, "CRS_CALCULO": "EPSG:32717"}) for g, p in existing], output)
            save_layer(package, "COBERTURA_MUNICIPAL_200M", [(unary_union([g.buffer(radius, quad_segs=64) for g, _ in municipal]), {"RADIO_M": radius})], output)
            save_layer(package, "COBERTURA_POLICIA_200M", [(unary_union([g.buffer(radius, quad_segs=64) for g, _ in police]), {"RADIO_M": radius})], output)
        save_layer(package, "ESCENARIO_FINAL_183", [(g, {**p, "ID_EQUIPO": p["ID_CAMARA"], "GRUPO_ESCENARIO": "EXISTENTE"}) for g, p in existing]
            + [(g, {**p, "ID_EQUIPO": p["ID_PROPUESTA"], "GRUPO_ESCENARIO": "MUNICIPAL_PROPUESTA"}) for g, p in municipal]
            + [(g, {**p, "ID_EQUIPO": p["ID_POLICIA"], "GRUPO_ESCENARIO": "POLICIA_PROPUESTA"}) for g, p in police])
        save_layer(package, "AREAS_EXCLUSIVAS_POLICIA_FINAL", [(g.buffer(radius, quad_segs=64).difference(unary_union([masks["B"], *[q.buffer(radius, quad_segs=64) for j, (q, _) in enumerate(police) if i != j]])), {"ID_POLICIA": p["ID_POLICIA"]}) for i, (g, p) in enumerate(police)], output)
        save_layer(package, "AREAS_SOLAPADAS_POLICIA_FINAL", [(g.buffer(radius, quad_segs=64).intersection(unary_union([masks["B"], *[q.buffer(radius, quad_segs=64) for j, (q, _) in enumerate(police) if i != j]])), {"ID_POLICIA": p["ID_POLICIA"]}) for i, (g, p) in enumerate(police)], output)
        write_json(output / "CORRIDOR_COVERAGE_200M.json", clean(corridor_view(axes, masks, existing, municipal, police)))
    elif receipt["changes"]:
        for key, spec in config["layers"].items():
            if any(r["layer"] == key for r in receipt["changes"]):
                save_layer(package, spec["source"], replacements[spec["source"]], output if key != "blocks" else None)
    for key, minimum in config["publishConstraints"].items():
        row = next(r for r in results["corridors"] if r["ESCENARIO"] == "B" and r["CORREDOR"] == key)
        if (minimum == 100 and row["NO_CUBIERTO_M"] > config["corridorToleranceM"]) or (minimum < 100 and row["PCT_CUBIERTO"] < minimum-1e-8):
            publish_blocks.append(f"Restriccion municipal {key}: {row['PCT_CUBIERTO']:.5f}% < {minimum}%")
    if len({g.wkb for g, _ in municipal+police}) != 80:
        publish_blocks.append("Dos propuestas comparten exactamente el mismo emplazamiento; revisar antes de publicar")
    validation = {"status": "REVIEW_REQUIRED" if publish_blocks else "PASS", "plan": plan, "nodeAudit": node_audit,
        "publishBlocks": publish_blocks, "sourcePreserved": True, "existingCount": 103, "municipalCount": 50, "policeCount": 30,
        "giRecalculated": False, "kdeRecalculated": False, "optimized": False, "revision": receipt["revision"]}
    results.update({"generatedAt": now(), "status": "SIG_BRIDGE_LOCAL_REVISION", "bridge": validation,
                    "sourceHashes": receipt["baseHashes"], "giRecalculated": False})
    results["populationComparison"] = population_comparison(existing, municipal, police, blocks, urban)
    write_json(output / "RESULTADOS.json", clean(results))
    write_json(output / "VALIDACION.json", clean(validation))
    # Replace stale downloadable tables, rather than retaining historical final metrics.
    for name, rows in (("POLICIA_BENEFICIO_FINAL", results["policeMetrics"]), ("INCIDENTES_CUBIERTOS_FINAL", results["incidents"]),
            ("HOTSPOTS_ATENDIDOS_FINAL", results["hotspots"]), ("CORREDORES_CUBIERTOS_FINAL", results["corridors"])):
        frame = pd.DataFrame(clean(rows))
        frame.to_csv(output / (name+".csv"), index=False, encoding="utf-8-sig")
        pyogrio.write_dataframe(frame, package, layer=name)
    moves = [{"ID": r["id"], "CAPA": r["layer"], "DISTANCIA_M": r["distanceM"], "OBSERVACION": r["note"]} for r in receipt["changes"]]
    pd.DataFrame(moves or [{"ID": "", "CAPA": "SIN_CAMBIOS"}]).to_csv(output / "MOVIMIENTOS_REVISION.csv", index=False, encoding="utf-8-sig")
    old_police = {p["ID_POLICIA"]: g for g, p in records(read_layer(store.base, "PROPUESTA_POLICIA_30_FINAL"))}
    police_moves = [{"ID_POLICIA": p["ID_POLICIA"], "X_ANTES": old_police[p["ID_POLICIA"]].x,
        "Y_ANTES": old_police[p["ID_POLICIA"]].y, "X_DESPUES": g.x, "Y_DESPUES": g.y,
        "DESPLAZAMIENTO_M": old_police[p["ID_POLICIA"]].distance(g)} for g, p in police]
    results["policeChanges"] = police_moves
    write_json(output / "RESULTADOS.json", clean(results))
    pd.DataFrame(police_moves).to_csv(output / "MOVIMIENTOS_POLICIA_30.csv", index=False, encoding="utf-8-sig")
    pyogrio.write_dataframe(pd.DataFrame(police_moves), package, layer="MOVIMIENTOS_POLICIA_30")
    (output / "INFORME_FINAL.md").write_text("# SIG Bridge: revision local\n\n" +
        f"Revision {receipt['revision']}. Radio 200 m. No optimiza camaras ni recalcula KDE/Gi*.\n\n" +
        "Publicacion bloqueada: " + ("; ".join(publish_blocks) or "no; requiere aprobacion expresa") + "\n", encoding="utf-8")
    with zipfile.ZipFile(output / "ENTREGA_POLICIA_KDE.zip", "w", zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(output.iterdir()):
            if path.suffix != ".zip":
                zipped.write(path, path.name)
    verify_derived(store, package, results, existing_override)
    return validation


def verify_derived(store, package, results, existing_override=None):
    """Cross-check generated artifacts before they can become the current preview."""
    for name, expected_count, id_field in (("CAMARAS_EXISTENTES_103_FINAL",103,"ID_CAMARA"),
            ("PROPUESTA_MUNICIPAL_50_FINAL",50,"ID_PROPUESTA"), ("PROPUESTA_POLICIA_30_FINAL",30,"ID_POLICIA")):
        frame = read_layer(package, name)
        old = read_layer(store.base, name)
        require(len(frame) == expected_count and frame[id_field].is_unique and set(frame[id_field]) == set(old[id_field]), "Inventario/IDs alterados: "+name)
        require(frame.geometry.is_valid.all(), "Geometria de camara invalida")
        if name.startswith("CAMARAS_EXISTENTES"):
            expected = old if existing_override is None else existing_override
            expected = expected.set_index("ID_CAMARA").loc[frame.ID_CAMARA]
            require([g.wkb for g in frame.geometry] == [g.wkb for g in expected.geometry], "El inventario no coincide con su fuente aprobada")
    existing = read_layer(package, "CAMARAS_EXISTENTES_103_FINAL")
    municipal = read_layer(package, "PROPUESTA_MUNICIPAL_50_FINAL")
    police = read_layer(package, "PROPUESTA_POLICIA_30_FINAL")
    disks = {"A": [g.buffer(200,quad_segs=64) for g in existing.geometry]}
    disks["B"] = disks["A"]+[g.buffer(200,quad_segs=64) for g in municipal.geometry]
    disks["C"] = disks["B"]+[g.buffer(200,quad_segs=64) for g in police.geometry]
    for code, values in disks.items():
        expected = unary_union(values)
        actual = read_layer(package, "COBERTURA_"+code).geometry.iloc[0]
        require(expected.symmetric_difference(actual).area < .01, "Buffer/escenario incoherente: "+code)
    for scope in ("URBANO","RURAL"):
        for category in CLASSES:
            name = f"GI_{scope}_{category}"
            before, after = read_layer(store.base,name), read_layer(package,name)
            require([g.wkb for g in before.geometry] == [g.wkb for g in after.geometry], "Celdas Gi* alteradas")
            fields = [c for c in before.columns if c != "geometry" and not c.startswith(("COB_", "ESTADO_"))]
            pd.testing.assert_frame_equal(before[fields], after[fields], check_dtype=False)
    for key in ("territorial","population","incidents","hotspots","corridors"):
        require(bool(results[key]), "Resultado incompleto: "+key)


def replace_scenario(results, key, scenario, rows):
    results[key] = [r for r in results[key] if r["ESCENARIO"] != scenario] + rows


def latest_run(store, revision_id, verify=True):
    revision = store.revision(revision_id)
    latest = read_json(revision / "latest.json")
    run_id = latest["runId"]
    require(Path(run_id).name == run_id, "Run ID no valido")
    run = store.workspace / "runs" / revision_id / run_id
    manifest = read_json(run / "manifest.json")
    if verify:
        require(digest(revision / "revision.json") == manifest["input"]["revisionSha256"], "Metadatos de revision modificados despues del calculo")
        store.guard(read_json(revision / "revision.json"))
        require(store.validate(revision_id)["manualSha256"] == manifest["input"]["manualSha256"], "Resultados obsoletos: hay cambios QGIS sin recalcular")
        require(file_hashes(run / "web") == manifest["files"], "Resultados modificados despues de validar")
    return run, manifest
