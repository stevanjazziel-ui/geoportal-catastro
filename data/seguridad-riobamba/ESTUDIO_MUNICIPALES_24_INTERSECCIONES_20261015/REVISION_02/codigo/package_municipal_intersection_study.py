"""Package a local, unapplied municipal review with comparative GIS maps."""
import csv
import html
import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pyogrio
from scipy.sparse.csgraph import dijkstra
from shapely import STRtree
from shapely.geometry import LineString, MultiLineString
from shapely.ops import unary_union

import study_municipal_24_intersections as s
from render_police_kde_moves_comparison import path_data

OUT = s.OUT / "REVISION_02"
CODES = ["A_CRUCES_PRINCIPALES_CERCANOS", "C_PRIORIDAD_PRINCIPALES", "D_PRIORIDAD_CICLOVIAS"]
LABELS = {CODES[0]: "Cruces principales cercanos", CODES[1]: "23 principales + 1 local", CODES[2]: "20 principales + 4 locales"}


def read(name):
    return s.records(s.read_layer(OUT/"ESTUDIO_MUNICIPALES_24.gpkg", name))


def export(name, rows):
    previous = s.OUT
    s.OUT = OUT
    s.export(name, rows)
    s.OUT = previous


def connectivity(study, code):
    rows = read(code+"_PUNTOS")
    node_indices = [int(p["INDICE_RED"]) for _, p in rows]
    distances, predecessors = dijkstra(study.graph, directed=False, indices=node_indices, return_predecessors=True)
    edges = {}
    for line in s.parts(study.network):
        a = study.node_index[tuple(line.coords[0][:2])]
        b = study.node_index[tuple(line.coords[-1][:2])]
        if a != b:
            key = tuple(sorted((a, b)))
            if key not in edges or line.length < edges[key].length:
                edges[key] = line
    features, pairs = [], []
    for i, (point, props) in enumerate(rows):
        for j in range(i+1, len(rows)):
            target = node_indices[j]
            length = float(distances[i, target])
            value = {"ID_A": props["ID_PROPUESTA"], "ID_B": rows[j][1]["ID_PROPUESTA"],
                "DIST_EUCLIDEA_M": point.distance(rows[j][0]), "DIST_RED_M": length if np.isfinite(length) else None,
                "HASTA_400M_POR_RED": bool(np.isfinite(length) and length <= 400+s.TOL), "VISIBILIDAD_CERTIFICADA": False}
            pairs.append(value)
            if not value["HASTA_400M_POR_RED"]:
                continue
            route, current = [], target
            while current != node_indices[i]:
                previous = int(predecessors[i, current])
                if previous < 0:
                    raise RuntimeError("Ruta no reconstruible")
                route.append(edges[tuple(sorted((current, previous)))])
                current = previous
            geometry = MultiLineString(route)
            assert abs(geometry.length-length) < s.TOL
            features.append((geometry, value))
    previous = s.OUT
    s.OUT = OUT
    s.table(code+"_PARES_POR_RED.csv", pairs)
    s.OUT = previous
    export(code+"_ENLACES_400M", features)
    return features


def figure(study, result):
    scenarios = [None, result["scenarios"][1], result["scenarios"][2]]
    sets = [study.original, read(CODES[1]+"_PUNTOS"), read(CODES[2]+"_PUNTOS")]
    points = [g for rows in sets for g, _ in rows]
    bounds = unary_union(points).buffer(350).bounds
    west, south, east, north = bounds
    width, height, panel_width, panel_height, top = 1800, 1130, 560, 720, 200
    body = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<defs><marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6Z" fill="#626d78"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#f4f7f8"/>',
        '<text x="36" y="48" font-family="Arial" font-size="30" font-weight="700" fill="#12394d">24 MUNICIPALES · ESTUDIO DE INTERSECCIONES</text>',
        '<text x="36" y="82" font-family="Arial" font-size="18" fill="#425863">Comparación previa a implementar. Las 103 existentes, 26 municipales restantes y 30 policiales permanecen fijas.</text>',
        '<text x="36" y="112" font-family="Arial" font-size="17" font-weight="700" fill="#9a3434">NO APLICADO · Radio geométrico 200 m · Los enlaces por calle no certifican visibilidad.</text>']
    for panel, rows in enumerate(sets):
        left = 36+panel*584
        scale = min((panel_width-36)/(east-west), (panel_height-36)/(north-south))
        ox = left+(panel_width-(east-west)*scale)/2
        oy = top+(panel_height-(north-south)*scale)/2
        def project(x, y):
            return ox+(x-west)*scale, oy+(north-y)*scale
        title = "ACTUAL" if panel == 0 else ("MÁS VÍAS PRINCIPALES" if panel == 1 else "MÁS CICLOVÍAS")
        coverage = result["baselineMunicipal"] if panel == 0 else scenarios[panel]["corridorsMunicipal"]
        body.append(f'<text x="{left}" y="155" font-family="Arial" font-size="21" font-weight="700" fill="#12394d">{title}</text>')
        body.append(f'<text x="{left}" y="183" font-family="Arial" font-size="15" fill="#425863">Macají {coverage[s.MACAJI]["pct"]:.2f}% · Anillo {coverage[s.RING]["pct"]:.2f}% · Ciclovías {coverage[s.CYCLE]["pct"]:.2f}%</text>')
        body.append(f'<clipPath id="clip{panel}"><rect x="{left}" y="{top}" width="{panel_width}" height="{panel_height}"/></clipPath>')
        body.append(f'<rect x="{left}" y="{top}" width="{panel_width}" height="{panel_height}" fill="#fff" stroke="#bbcbd1"/>')
        body.append(f'<g clip-path="url(#clip{panel})">')
        for geom, props in s.records(study.roads):
            d = path_data(geom, project)
            primary = str(props.get("TIPOLOGIA_")).strip() in s.MAJOR
            body.append(f'<path d="{d}" fill="none" stroke="{"#bcc8cd" if primary else "#e7ecee"}" stroke-width="{1.2 if primary else .7}"/>')
        for key, color in [(s.MACAJI, "#bb3656"), (s.RING, "#9971ab"), (s.CYCLE, "#218f9d")]:
            body.append(f'<path d="{path_data(study.axes[key], project)}" fill="none" stroke="{color}" stroke-width="2.3" opacity=".8"/>')
        for geom, props in study.existing+study.police+study.frozen:
            x, y = project(geom.x, geom.y)
            color = "#e8bd16" if props.get("ID_POLICIA") else ("#4f9a70" if props.get("ID_PROPUESTA") else ("#8b46b5" if props.get("REQUIERE_CAMBIO") else "#246db5"))
            body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.4" fill="{color}" stroke="#fff" stroke-width=".8" opacity=".8"/>')
        for geom, props in rows:
            x, y = project(geom.x, geom.y)
            body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{RADIUS*scale:.2f}" fill="#18815b" fill-opacity=".045" stroke="#18815b" stroke-width=".9" stroke-opacity=".35"/>')
        if panel:
            code = CODES[panel]
            for geom, _ in read(code+"_ENLACES_400M"):
                body.append(f'<path d="{path_data(geom, project)}" fill="none" stroke="#1166aa" stroke-width="3" opacity=".75"/>')
            old_lookup = {p["ID_PROPUESTA"]: g for g, p in study.original}
            for geom, props in rows:
                old = old_lookup[props["ID_PROPUESTA"]]
                x, y = project(old.x, old.y); nx, ny = project(geom.x, geom.y)
                if old.distance(geom) > 1:
                    body.append(f'<path d="M{x:.2f},{y:.2f} L{nx:.2f},{ny:.2f}" stroke="#626d78" stroke-width="1.1" stroke-dasharray="4 3" opacity=".65" marker-end="url(#arrow)"/>')
                    body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.5" fill="#fff" stroke="#626d78"/>')
        for geom, props in rows:
            x, y = project(geom.x, geom.y)
            label = props["ID_PROPUESTA"].split("-")[1]
            body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6" fill="#18815b" stroke="#fff" stroke-width="1.4"/>')
            body.append(f'<text x="{x+7:.2f}" y="{y-7:.2f}" font-family="Arial" font-size="11" font-weight="700" fill="#12394d" stroke="#fff" stroke-width="3" paint-order="stroke">{label}</text>')
        body.append('</g>')
        if panel:
            value = scenarios[panel]
            body.append(f'<text x="{left}" y="955" font-family="Arial" font-size="17" fill="#12394d">{value["movedOver1m"]} movidas · {value["principalIntersections"]}/24 cruces principales</text>')
            body.append(f'<text x="{left}" y="985" font-family="Arial" font-size="17" fill="#12394d">Mediana {value["medianDisplacementM"]:.0f} m · máximo {value["maxDisplacementM"]:.0f} m</text>')
        else:
            body.append(f'<text x="{left}" y="955" font-family="Arial" font-size="17" fill="#12394d">3/24 cruces exactos en la red municipal consultada</text>')
            body.append(f'<text x="{left}" y="985" font-family="Arial" font-size="16" fill="#425863">Otros 2 nodos de otra fuente: diferencias 0,94 y 2,21 m</text>')
    body += ['<text x="36" y="1040" font-family="Arial" font-size="17" fill="#425863">Verde: municipales y radio 200 m · Gris: desplazamiento · Azul grueso: enlace por vía ≤400 m entre estas 24</text>',
        '<text x="36" y="1073" font-family="Arial" font-size="16" fill="#425863">Corredores: Macají rojo · Anillo violeta · Ciclovías turquesa. Referencias fijas: existentes azul/morado y Policía amarillo.</text>',
        '<text x="36" y="1105" font-family="Arial" font-size="16" fill="#9a3434">Ambas alternativas conservan Macají100/Anillo80, pero reducen Ciclovías. No se ha aprobado ni aplicado ninguna.</text>', '</svg>']
    (OUT/"COMPARACION_MUNICIPALES_24.svg").write_text("\n".join(body), encoding="utf-8")


RADIUS = 200


def main():
    result = json.loads((OUT/"RESULTADOS.json").read_text(encoding="utf-8"))
    study = s.Study()
    # Refresh road labels only; coordinates and solved scenarios are immutable here.
    for row in result["audit"]:
        point = s.Point(row["X_ACTUAL"], row["Y_ACTUAL"])
        road = study.roads.iloc[int(study.road_tree.nearest(point))]
        row["VIA_ACTUAL_PROXIMA"] = str(road.TXT)
        row["PARROQUIA_RED_ACTUAL"] = str(road.NOMBRE)
    previous = s.OUT
    s.OUT = OUT
    s.table("AUDITORIA_24_ACTUALES.csv", result["audit"])
    with (OUT/"ALTERNATIVAS_5_POR_CAMARA.csv").open(encoding="utf-8-sig", newline="") as stream:
        alternatives = list(csv.DictReader(stream))
    alternatives = [{**row, **study.node_description(s.Point(float(row["X_ESTUDIO"]), float(row["Y_ESTUDIO"])), {})} for row in alternatives]
    s.table("ALTERNATIVAS_5_POR_CAMARA.csv", alternatives)
    for code in CODES:
        rows = [(point, {**props, **study.node_description(point, {})}) for point, props in read(code+"_PUNTOS")]
        export(code+"_PUNTOS", rows)
        s.table(code+"_MOVIMIENTOS.csv", [props for _, props in rows])
        old = {p["ID_PROPUESTA"]: g for g, p in study.original}
        export(code+"_MOVIMIENTOS", [(LineString([old[p["ID_PROPUESTA"]], point]), p) for point, p in rows if point.distance(old[p["ID_PROPUESTA"]]) > 1e-6])
    s.OUT = previous
    result["roadContentSha256"] = study.road_hash
    result["roadNameField"] = "TXT"
    result["parishNameField"] = "NOMBRE"
    (OUT/"RESULTADOS.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    previous = s.OUT
    s.OUT = OUT
    s.write_report(result)
    s.OUT = previous
    for code in CODES:
        connectivity(study, code)
    figure(study, result)
    data = {"results": result, "actual": json.loads((OUT/"ACTUALES_24.geojson").read_text(encoding="utf-8")),
        "existing": json.loads((OUT/"EXISTENTES_103_REFERENCIA.geojson").read_text(encoding="utf-8")),
        "police": json.loads((OUT/"POLICIA_30_FIJA.geojson").read_text(encoding="utf-8")),
        "fixed": json.loads((OUT/"MUNICIPALES_26_FIJAS.geojson").read_text(encoding="utf-8")),
        "corridors": json.loads((OUT/"CORREDORES_ORIGINALES.geojson").read_text(encoding="utf-8")), "scenarios": {}}
    for code in CODES:
        data["scenarios"][code] = {"label": LABELS[code], **{key: json.loads((OUT/(code+suffix+".geojson")).read_text(encoding="utf-8")) for key, suffix in [("points", "_PUNTOS"), ("moves", "_MOVIMIENTOS"), ("links", "_ENLACES_400M")]}}
    (OUT/"review-data.js").write_text("window.MUNICIPAL_REVIEW="+json.dumps(data, ensure_ascii=False, separators=(",", ":"))+";", encoding="utf-8")
    template = (Path(__file__).with_name("municipal_intersection_review.html")).read_text(encoding="utf-8")
    (OUT/"index.html").write_text(template, encoding="utf-8")
    validation = {"status": "PASS", "applied": False, "commit": False, "push": False,
        "sourceFilesUnchanged": all(s.sha(Path(path)) == digest for path, digest in result["sourceHashes"].items()), "scenarios": []}
    for code in CODES:
        rows = read(code+"_PUNTOS")
        assert len(rows) == 24 and len({g.wkb for g, _ in rows}) == 24
        assert all(study.nodes[int(p["INDICE_RED"])].distance(g) < 1e-6 and p["GRADO_NODO"] >= 3 for g, p in rows)
        value = next(r for r in result["scenarios"] if r["scenario"] == code)
        mask = unary_union([study.fixed, buffer_rows(rows)])
        computed = study.coverage(mask)
        assert all(abs(computed[key]["coveredM"]-value["corridorsMunicipal"][key]["coveredM"]) < s.TOL for key in s.KEYS)
        assert abs(sum(p["DESPLAZAMIENTO_M"] for _, p in rows)-value["totalDisplacementM"]) < .001
        validation["scenarios"].append({"id": code, "points": 24, "distinctVerifiedNodes": 24, "hardGoalsMet": value["hardGoalsMet"]})
    assert validation["sourceFilesUnchanged"]
    (OUT/"VALIDACION.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    previous = s.OUT
    s.OUT = OUT
    s.table("RESUMEN_ESCENARIOS.csv", [{"ESCENARIO": row["scenario"],
        "MACAJI_PCT": row["corridorsMunicipal"][s.MACAJI]["pct"], "ANILLO_PCT": row["corridorsMunicipal"][s.RING]["pct"],
        "CICLOVIAS_PCT": row["corridorsMunicipal"][s.CYCLE]["pct"], "CRUCES_PRINCIPALES": row["principalIntersections"],
        "MOVIDAS_MAS_1M": row["movedOver1m"], "DISTANCIA_TOTAL_M": row["totalDisplacementM"],
        "MEDIANA_M": row["medianDisplacementM"], "MAXIMO_M": row["maxDisplacementM"], "CUMPLE_MACAJI100_ANILLO80": row["hardGoalsMet"]} for row in result["scenarios"]])
    s.OUT = previous
    report = (OUT/"INFORME.md").read_text(encoding="utf-8")
    report += "\n## Control de interpretacion\n\n"
    report += "Los 3 cruces exactos actuales se comprueban con tolerancia geometrica de0.05m en Vialidad_urbana. Otras2posiciones provienen de nodos de otra red y difieren0.94/2.21m; esa diferencia no prueba por si sola un error de campo. No confundir no coincidencia exacta entre fuentes con ubicacion fisica incorrecta.\n\n"
    report += "La alternativaC prioriza el numero de cruces en vias principales, despues Ciclovias y finalmente el desplazamiento. La alternativaD prioriza Ciclovias, despues vias principales y finalmente el desplazamiento. Ambas exigen Macaji100 y Anillo80. El solucionador demuestra sus objetivos dentro del catalogo, no visibilidad real.\n\n"
    report += "Los nombres de calles proceden deTXT. NOMBRE corresponde a parroquia y se conserva separadamente comoPARROQUIA_RED. Los cruces sin dos nombres confirmados se senalan como pendientes; no se sustituyen por nombres parroquiales ni etiquetas inventadas.\n\n"
    report += "ID_TRAMOS_TARGET_FID identifica los segmentos deVialidad_urbana incidentes en cada nodo; permite auditar tambien los cruces sin nombre o con caracteres ilegibles en la fuente.\n\n"
    report += "Los enlaces azules y los pares por red comparan exclusivamente estas24municipales; no representan la conectividad de todo el sistema183. Se entregan los276pares por escenario, incluidos desconectados y mayores de400m.\n\n"
    report += "Ninguna seleccion solo en cruces conserva la actual cobertura de Ciclovias64.5948% al exigir Macaji100/Anillo80 en este catalogo; el maximo obtenido y demostrado es58.6819%. Esto no autoriza reducir la cobertura ni implementar la alternativa.\n\n"
    report += "## Desplazamientos de la alternativaC\n\n| ID | Distancia m | Nodo | Via principal |\n|---|---:|---|---|\n"
    for _, props in sorted(read(CODES[1]+"_PUNTOS"), key=lambda row: row[1]["ID_PROPUESTA"]):
        report += f"| {props['ID_PROPUESTA']} | {props['DESPLAZAMIENTO_M']:.2f} | {props['CRUCE_O_NODO']} | {props['VIA_PRINCIPAL']} |\n"
    (OUT/"INFORME.md").write_text(report, encoding="utf-8")
    (OUT/"README.md").write_text("# Estudio municipal no aplicado\n\nAbrir index.html mediante servidor HTTP para comparar mapas, o COMPARACION_MUNICIPALES_24.png para la imagen estatica. INFORME.md y RESULTADOS.json documentan parametros, catalogos, restricciones y SHA256 de fuentes.\n\nGeoPackage en EPSG:32717; derivados GeoJSON en EPSG:4326. ACTUALES_24 conserva las posiciones actuales. Capas con _PUNTOS son alternativas no aprobadas; _MOVIMIENTOS son desplazamientos rectos; _ENLACES_400M son rutas de la red GIS entre estas24municipales, no visibilidad certificada. Los CSV _PARES_POR_RED incluyen todos los276pares por escenario.\n\nEl codigo requiere el proyecto y sus fuentes originales locales; no es un instalador autonomo. No ejecutar sobre datos oficiales sin revision. No se hicieron commit ni push, ni se modifico el visor.\n", encoding="utf-8")
    print(json.dumps(validation), flush=True)


def buffer_rows(rows):
    return unary_union([g.buffer(RADIUS, quad_segs=64) for g, _ in rows])


def archive():
    code = OUT/"codigo"
    code.mkdir(exist_ok=True)
    for name in ("study_municipal_24_intersections.py", "package_municipal_intersection_study.py", "municipal_intersection_review.html"):
        shutil.copy2(Path(__file__).with_name(name), code/name)
    with zipfile.ZipFile(OUT/"ESTUDIO_MUNICIPALES_24.zip", "w", zipfile.ZIP_DEFLATED) as package:
        for path in sorted(OUT.rglob("*")):
            if path.is_file() and path.suffix != ".zip" and path.name != "AVANCE.json":
                package.write(path, path.relative_to(OUT))
    print(OUT/"ESTUDIO_MUNICIPALES_24.zip", flush=True)


if __name__ == "__main__":
    import sys
    if "--archive" in sys.argv:
        archive()
    else:
        main()
