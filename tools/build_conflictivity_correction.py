"""Approved classification and reproducible six-universe KDE/Gi review, without source edits."""
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import transform, unary_union

from audit_cantonal_expansion import ROOT, read_js
from build_cantonal_analysis import gi

OUT = ROOT / "data/seguridad-riobamba/correccion-conflictividad-20261001"
NAMES = {1: "DELINCUENCIA", 2: "VIOLENCIA", 3: "CONVIVENCIA", 4: "ACTIVIDAD_INSTITUCIONAL", 5: "OTROS_REVISION"}
APPROVED = {"Bomberos": "ACTIVIDAD_INSTITUCIONAL", "Tenencia y porte de explosivos": "DELINCUENCIA", "Falta contra la integridad a servidores policiales": "ACTIVIDAD_INSTITUCIONAL", "Plantones": "ACTIVIDAD_INSTITUCIONAL"}
CANDIDATES = {"URBANO": [200, 250, 300, 400, 500, 700], "RURAL": [500, 750, 1000, 1200, 1500]}


def write_csv(name, rows):
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def components(binary):
    height, width = binary.shape
    remaining = set(int(i) for i in np.flatnonzero(binary))
    total = 0
    while remaining:
        total += 1
        pending = [remaining.pop()]
        while pending:
            index = pending.pop()
            x, y = index % width, index // width
            for next_index in ([index-1] if x else []) + ([index+1] if x+1 < width else []) + ([index-width] if y else []) + ([index+width] if y+1 < height else []):
                if next_index in remaining:
                    remaining.remove(next_index)
                    pending.append(next_index)
    return total


def grouped(items, assignments):
    groups = Counter((assignments[e["id"]]["x"], assignments[e["id"]]["y"]) for e in items)
    xy = np.array(list(groups), dtype=float)
    return xy, np.array(list(groups.values()), dtype=float)


def cross_validation(xy, multiplicity, candidates):
    scores = {}
    n = multiplicity.sum()
    # Hold out the complete exact-XY group, not just one coincident row.
    for h in candidates:
        logs, zero = [], 0
        normalizer = 1e6 / (2 * math.pi * h*h * (1-math.exp(-.5)))
        for start in range(0, len(xy), 128):
            points = xy[start:start+128]
            d2 = ((points[:, None, :] - xy[None, :, :])**2).sum(axis=2)
            kernel = np.exp(-.5*d2/(h*h)) * (d2 <= h*h)
            kernel[np.arange(len(points)), np.arange(start, start+len(points))] = 0
            predicted = (kernel @ multiplicity) * normalizer / (n-multiplicity[start:start+len(points)])
            zero += int(np.count_nonzero(predicted == 0))
            logs.extend(np.log(np.maximum(predicted, 1e-12)).tolist())
        scores[h] = {"cvMeanLogLikelihood": float(np.mean(logs)), "heldOutLocationsWithoutSupport": zero}
    return scores


def raster(xy, multiplicity, grid, h):
    west, south = grid["metricBounds"][0]
    east, north = grid["metricBounds"][1]
    cell = grid["cellSize"]
    field = np.zeros((grid["height"], grid["width"]), dtype=np.float64)
    normalizer = 1e6/(2*math.pi*h*h*(1-math.exp(-.5)))
    for (px, py), n in zip(xy, multiplicity):
        left = max(0, math.floor((px-h-west)/cell))
        right = min(grid["width"], math.ceil((px+h-west)/cell))
        top = max(0, math.floor((north-py-h)/cell))
        bottom = min(grid["height"], math.ceil((north-py+h)/cell))
        dx = west + (np.arange(left, right)+.5)*cell-px
        dy = north - (np.arange(top, bottom)+.5)*cell-py
        d2 = dy[:, None]**2+dx[None, :]**2
        field[top:bottom, left:right] += n*normalizer*np.exp(-.5*d2/(h*h))*(d2 <= h*h)
    mask = np.zeros(field.size, dtype=bool)
    mask[grid["mask"]] = True
    field.ravel()[~mask] = 0
    return field


def make_urban_grid(territory):
    previous = read_js("riobamba-seguridad-kde-validacion-data.js", "RIOBAMBA_KDE_VALIDATION")["rasters"]["700"]
    project = Transformer.from_crs(4326, 32717, always_xy=True)
    inverse = Transformer.from_crs(32717, 4326, always_xy=True)
    geom = transform(project.transform, shape(territory["urban"]["geometry"]))
    bounds = previous["metricBounds"]
    west, south = bounds[0]
    east, north = bounds[1]
    cell = 20
    width, height = round((east-west)/cell), round((north-south)/cell)
    xx, yy = np.meshgrid(west+(np.arange(width)+.5)*cell, north-(np.arange(height)+.5)*cell)
    mask = np.flatnonzero(contains_xy(geom, xx, yy)).tolist()
    lon, lat = inverse.transform([west,east,east,west], [south,south,north,north])
    gw, ge, gs, gn = min(lon), max(lon), min(lat), max(lat)
    llx, lly = np.meshgrid(gw+(np.arange(width)+.5)*(ge-gw)/width, gn-(np.arange(height)+.5)*(gn-gs)/height)
    tx, ty = project.transform(llx, lly)
    cols, rows = np.floor((tx-west)/cell).astype(int), np.floor((north-ty)/cell).astype(int)
    warp = np.where((cols >= 0)&(cols < width)&(rows >= 0)&(rows < height), rows*width+cols, -1)
    return {"cellSize":cell, "width":width, "height":height, "metricBounds":bounds, "bounds":[[gs,gw],[gn,ge]], "mask":mask, "warpIndex":warp.ravel().tolist()}, geom


def plot(field, grid, geometries, points, title, file, reference, extent=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    fig, ax = plt.subplots(figsize=(5, 5), dpi=110)
    palette = LinearSegmentedColormap.from_list("neutral", ["#F1F8E9","#C5E1A5","#80CBC4","#26A69A","#00695C"])
    normalized = np.log1p(field)/math.log1p(reference)
    rgba = palette(np.clip(normalized,0,1))
    rgba[:, :, 3] = np.where(field > 0, .75*np.maximum(normalized,0)**.65, 0)
    (west,south),(east,north) = grid["metricBounds"]
    ax.imshow(rgba, extent=[west,east,south,north], origin="upper", interpolation="nearest")
    for geom in geometries:
        polygons = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for polygon in polygons:
            x, y = polygon.exterior.xy
            ax.plot(x,y,color="#3e5964",linewidth=.5)
    if len(points):
        ax.scatter(points[:,0],points[:,1],s=1.5,c="#263238",alpha=.3)
    if extent:
        ax.set_xlim(extent[0],extent[2]); ax.set_ylim(extent[1],extent[3])
    else:
        bounds = unary_union(geometries).bounds
        ax.set_xlim(bounds[0],bounds[2]); ax.set_ylim(bounds[1],bounds[3])
    ax.set_aspect("equal"); ax.set_axis_off(); ax.set_title(title, fontsize=9)
    fig.text(.5,.025,"EPSG:32717 | peso1 | escala log fija compartida | no peligrosidad",ha="center",fontsize=7)
    fig.savefig(OUT/file, bbox_inches="tight",facecolor="white")
    plt.close(fig)


def main():
    source = read_js("visor-seguridad-riobamba-data.js", "RIOBAMBA_SECURITY_DATA")
    territory = read_js("riobamba-cantonal-data.js", "RIOBAMBA_CANTONAL_DATA")
    assignments = territory["assignments"]
    dictionary = json.loads((OUT/"DICCIONARIO_PROPUESTO.json").read_text(encoding="utf-8"))
    for rule in dictionary:
        rule["CATEGORIA_ANALITICA"] = APPROVED.get(rule["SUBTIPO"], rule["CATEGORIA_ANALITICA"])
        rule["ESTADO"] = "APROBADO_OPERATIVO" if rule["CATEGORIA_ANALITICA"] != "OTROS_REVISION" else "EXCLUIDO_PENDIENTE_REVISION"
    by_subtype = {r["SUBTIPO"]:r["CATEGORIA_ANALITICA"] for r in dictionary}
    ids = {name:id for id,name in NAMES.items()}
    xy_counts = Counter((e["lng"],e["lat"]) for e in source["events"])
    derived = [{**e, "category":by_subtype[e["subtype"]], "CATEGORIA_ANALITICA":by_subtype[e["subtype"]], "analyticalClassId":ids[by_subtype[e["subtype"]]], "hotspotEligible":ids[by_subtype[e["subtype"]]] <= 3,
                "RECURRENCIA_XY":xy_counts[(e["lng"],e["lat"])], "FLAG_COORD":"MUY_ALTA_REPETICION" if xy_counts[(e["lng"],e["lat"])] >= 30 else "ALTA_REPETICION" if xy_counts[(e["lng"],e["lat"])] >= 10 else "REPETIDA" if xy_counts[(e["lng"],e["lat"])] >= 2 else "NORMAL"} for e in source["events"]]
    totals = Counter(e["category"] for e in derived)
    assert dict(totals) == {"DELINCUENCIA":2533,"VIOLENCIA":1590,"CONVIVENCIA":7027,"ACTIVIDAD_INSTITUCIONAL":14778,"OTROS_REVISION":788}
    grid, urban = make_urban_grid(territory)
    grids = {"URBANO":grid, "RURAL":territory["kdeGrids"]["RURAL"]}
    to_m = Transformer.from_crs(4326,32717,always_xy=True).transform
    platforms = json.loads((ROOT/"riobamba-censo-data/riobamba_plataformas.geojson").read_text(encoding="utf-8"))["features"]
    geometries = {"URBANO":[transform(to_m,shape(f["geometry"])) for f in platforms], "RURAL":[transform(to_m,shape(f["geometry"])) for f in territory["parishes"]["features"]]}
    parameters, evaluations, fields, quality = {}, [], {}, []
    for scope in CANDIDATES:
        parameters[scope] = {}
        for name in ("DELINCUENCIA","VIOLENCIA","CONVIVENCIA"):
            items = [e for e in derived if assignments[e["id"]]["scope"] == scope and e["category"] == name]
            xy, n = grouped(items,assignments)
            scores = cross_validation(xy,n,CANDIDATES[scope])
            recommended = max(CANDIDATES[scope],key=lambda h:(scores[h]["cvMeanLogLikelihood"],-h))
            parameters[scope][name] = {"bandwidth":recommended,"cellSize":grids[scope]["cellSize"],"records":len(items),"selection":"Mayor log-verosimilitud predictiva media dejando fuera cada grupo XY completo; empate: menor radio; recomendacion provisional.","atCandidateBoundary":recommended in (min(CANDIDATES[scope]),max(CANDIDATES[scope]))}
            for h in CANDIDATES[scope]:
                field = raster(xy,n,grids[scope],h)
                fields[(scope,name,h)] = field
            threshold = float(fields[(scope,name,recommended)].max())*.35
            baseline = components(fields[(scope,name,min(CANDIDATES[scope]))] > 0)
            for h in CANDIDATES[scope]:
                field = fields[(scope,name,h)]
                peak = np.unravel_index(np.argmax(field),field.shape)
                px = grids[scope]["metricBounds"][0][0]+(peak[1]+.5)*grids[scope]["cellSize"]
                py = grids[scope]["metricBounds"][1][1]-(peak[0]+.5)*grids[scope]["cellSize"]
                influence = Counter((assignments[e["id"]]["x"],assignments[e["id"]]["y"],e["FLAG_COORD"]) for e in items)
                weights = [(count*math.exp(-.5*((x-px)**2+(y-py)**2)/(h*h)),flag) for (x,y,flag),count in influence.items() if (x-px)**2+(y-py)**2 <= h*h]
                support = components(field > 0)
                evaluations.append({"scope":scope,"category":name,"records":len(items),"bandwidth":h,"cellSize":grids[scope]["cellSize"],"concentrations":components(field >= threshold),"fixedConcentrationThreshold":threshold,
                                    "influenceAreaKm2":float(np.count_nonzero(field))*grids[scope]["cellSize"]**2/1e6,"supportComponents":support,"supportComponentsMergedVsSmallest":baseline-support,
                                    "maxDensityEventsKm2":float(field.max()),"highRecurrenceShareAtMaximumPct":100*sum(w for w,f in weights if f in ("ALTA_REPETICION","MUY_ALTA_REPETICION"))/sum(w for w,_ in weights),**scores[h],"recommended":h == recommended})
            quality.append({"CATEGORIA":name,"AMBITO":scope,"N_EVENTOS":len(items),"N_COORD_UNICAS":len(xy),"PORCENTAJE_REGISTROS_EN_XY_REPETIDA":100*float(n[n>1].sum())/len(items),"MAX_REPETICION_XY":int(n.max()),"BANDWIDTH_RECOMENDADO":recommended})
            print(json.dumps({"scope":scope,"category":name,"parameters":parameters[scope][name]},ensure_ascii=False),flush=True)
    reference = max(float(field.max()) for field in fields.values())
    for (scope,name,h), field in fields.items():
        items = [e for e in derived if assignments[e["id"]]["scope"] == scope and e["category"] == name]
        xy,_ = grouped(items,assignments)
        plot(field,grids[scope],geometries[scope],xy,f"{scope} - {name} | N={len(items)} | h={h} m",f"KDE_{scope}_{name}_{h}.png",reference)
    # Preserve grid/weights; only the newly approved analytical class changes the inputs.
    spatial = read_js("riobamba-incidentes-spatial-data.js","RIOBAMBA_INCIDENT_SPATIAL")
    urban_grid = spatial["giGrid"]
    gi_outputs = {}
    for scope, gi_grid in (("URBANO",urban_grid),("RURAL",territory["ruralGrid"])):
        cells = gi_grid["cells"]
        cell_index = {(c["row"],c["col"]):i for i,c in enumerate(cells)}
        neighbors = gi_grid.get("neighbors")
        if not neighbors:
            centers = np.array([[c["x"],c["y"]] for c in cells])
            radius = gi_grid.get("neighborDistance",500)
            neighbors = [np.flatnonzero(((centers-p)**2).sum(axis=1) <= radius**2+1e-6).tolist() for p in centers]
        gi_outputs[scope] = {}
        for name in ("DELINCUENCIA","VIOLENCIA","CONVIVENCIA"):
            items = [e for e in derived if assignments[e["id"]]["scope"] == scope and e["category"] == name]
            counts = [0]*len(cells)
            for e in items:
                a = assignments[e["id"]]
                index = cell_index.get((math.floor((a["y"]-gi_grid["minY"])/gi_grid["cellSize"]),math.floor((a["x"]-gi_grid["minX"])/gi_grid["cellSize"])))
                assert index is not None, (scope,e["id"])
                counts[index] += 1
            result = gi(counts,neighbors)
            gi_outputs[scope][name] = {"records":len(items),"levels":dict(Counter(r["GI_CLASS"] for r in result)),"results":result}
            write_csv(f"GI_{scope}_{name}.csv",[{"CELL_ID":c["cellId"],"UNIDAD":c.get("PARROQUIA",c.get("platform","")),**r} for c,r in zip(cells,result)])
    central = unary_union([g for f,g in zip(platforms,geometries["URBANO"]) if f["properties"]["platform_name"] in ("PLATAFORMA H","PLATAFORMA I","PLATAFORMA J","PLATAFORMA K")])
    west,south = grid["metricBounds"][0]; north=grid["metricBounds"][1][1]
    xx,yy=np.meshgrid(west+(np.arange(grid["width"])+.5)*20,north-(np.arange(grid["height"])+.5)*20)
    central_mask=contains_xy(central,xx,yy)
    central_metrics=[]
    for label,items,h in [(f"PUBLICADO_{name}_700",[e for e in source["events"] if assignments[e["id"]]["scope"] == "URBANO" and e["analyticalClassId"] == class_id],700) for class_id,name in NAMES.items() if class_id <= 3] + [(f"NUEVO_{name}",[e for e in derived if assignments[e["id"]]["scope"] == "URBANO" and e["category"] == name],parameters["URBANO"][name]["bandwidth"]) for name in ("DELINCUENCIA","VIOLENCIA","CONVIVENCIA")] + [("CONTRAFACTUAL_TODOS_700",[e for e in derived if assignments[e["id"]]["scope"] == "URBANO"],700),("CONTRAFACTUAL_INSTITUCIONAL_700",[e for e in derived if assignments[e["id"]]["scope"] == "URBANO" and e["analyticalClassId"] == 4],700)]:
        xy,n=grouped(items,assignments); field=raster(xy,n,grid,h)
        central_metrics.append({"ESCENARIO":label,"N_EVENTOS":len(items),"BANDWIDTH":h,"MASA_KDE_CENTRAL_HIJK":float(field[central_mask].sum())*400/1e6,"MAX_DENSIDAD_CENTRAL":float(field[central_mask].max()),"AREA_INFLUENCIA_CENTRAL_KM2":float(np.count_nonzero(field[central_mask]))*400/1e6})
        plot(field,grid,geometries["URBANO"],xy,label+f" | N={len(items)}",f"CENTRO_{label}.png",reference,central.bounds)
    result = {"metadata":{"approval":"Usuario: ok a las cuatro reglas y conservar cruce espacial; pendiente revision local antes de commit/push.","crs":"EPSG:32717","period":source["period"],"weight":1,"populationField":"NONE","kernel":"Gaussiano truncado en h, normalizado para volumen1; intensidades eventos/km2. Forma del kernel constante entre candidatos.","formula":"sum exp(-d2/(2h2))*1e6/(2*pi*h2*(1-exp(-.5))), d<=h","selection":"Leave-one-exact-XY-group-out: log verosimilitud media con piso1e-12/km2; todas las observaciones se conservan en el raster final. Provisional, no certifica escala de intervencion ni optimalidad fuera de los candidatos.","scope":"Interseccion geometrica aprobada, no etiqueta parroquial; 850 SIN_ASIGNAR no forzados.","ruralOpacity":.45,"urbanOpacity":.68,"colorScale":"log1p(intensidad)/log1p(referencia maxima fija de las33 pruebas); misma referencia incluso al filtrar.","classificationApprovalLimit":"Las cuatro reglas son operativas autorizadas por el usuario, no certificacion juridica de los subtipos.","sourceHashes":{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('visor-seguridad-riobamba-data.js','riobamba-cantonal-data.js','riobamba-camaras-data.js','riobamba-censo-data/riobamba_plataformas.geojson')},"references":["https://scikit-learn.org/stable/modules/density.html","https://pro.arcgis.com/en/pro-app/3.4/tool-reference/spatial-analyst/how-kernel-density-works.htm"]},
              "dictionary":by_subtype,"recurrenceById":{e["id"]:e["RECURRENCIA_XY"] for e in derived},"totals":dict(totals),"scopeCounts":{s:dict(Counter(e["category"] for e in derived if assignments[e["id"]]["scope"] == s)) for s in ('URBANO','RURAL','SIN_ASIGNAR')},"parameters":parameters,"evaluations":evaluations,"quality":quality,"colorReference":reference,"urbanGrid":grid,"gi":gi_outputs,"centralComparison":central_metrics}
    OUT.mkdir(exist_ok=True)
    (ROOT/"riobamba-conflictividad-data.js").write_text("window.RIOBAMBA_CONFLICTIVITY_CORRECTION = "+json.dumps(result,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf-8")
    (OUT/"RESULTADOS_RECALCULO.json").write_text(json.dumps({k:v for k,v in result.items() if k not in ('urbanGrid','recurrenceById','gi')},ensure_ascii=False,indent=2),encoding="utf-8")
    write_csv("DICCIONARIO_APROBADO.csv",dictionary)
    write_csv("CONTROL_COORDENADAS_APROBADO.csv",quality)
    write_csv("COMPARACION_BANDWIDTH.csv",evaluations)
    write_csv("COMPARACION_CENTRO_HIJK.csv",central_metrics)
    write_csv("BASE_ANALITICA_APROBADA.csv",[{"ID":e["id"],"SUBTIPO":e["subtype"],"LONGITUD":e["lng"],"LATITUD":e["lat"],"CATEGORIA_ANALITICA":e["category"],"AMBITO":assignments[e["id"]]["scope"],"RECURRENCIA_XY":e["RECURRENCIA_XY"],"FLAG_COORD":e["FLAG_COORD"],"PESO":1} for e in derived])
    print(json.dumps({"totals":dict(totals),"scopes":result["scopeCounts"],"parameters":parameters,"colorReference":reference,"gi":{s:{n:{k:v for k,v in r.items() if k!='results'} for n,r in rows.items()} for s,rows in gi_outputs.items()}},ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main()
