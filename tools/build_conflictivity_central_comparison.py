"""Isolate classification, bandwidth and recurrence effects in H-I-J-K."""
import json
import math
from datetime import datetime, timezone
import numpy as np
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import transform, unary_union
from pyproj import Transformer
from audit_cantonal_expansion import ROOT, read_js
from build_conflictivity_correction import grouped, raster, plot, write_csv


def main():
    d = read_js("riobamba-conflictividad-data.js","RIOBAMBA_CONFLICTIVITY_CORRECTION")
    source = read_js("visor-seguridad-riobamba-data.js","RIOBAMBA_SECURITY_DATA")["events"]
    territory = read_js("riobamba-cantonal-data.js","RIOBAMBA_CANTONAL_DATA")
    assignments, grid = territory["assignments"], d["urbanGrid"]
    events = [{**e,"category":d["dictionary"][e["subtype"]]} for e in source if assignments[e["id"]]["scope"] == "URBANO"]
    old = [e for e in source if assignments[e["id"]]["scope"] == "URBANO"]
    project = Transformer.from_crs(4326,32717,always_xy=True).transform
    features = json.loads((ROOT/"riobamba-censo-data/riobamba_plataformas.geojson").read_text(encoding="utf-8"))["features"]
    geoms = [transform(project,shape(f["geometry"])) for f in features]
    central = unary_union([g for f,g in zip(features,geoms) if f["properties"]["platform_name"] in ("PLATAFORMA H","PLATAFORMA I","PLATAFORMA J","PLATAFORMA K")])
    x = grid["metricBounds"][0][0]+(np.arange(grid["width"])+.5)*20
    y = grid["metricBounds"][1][1]-(np.arange(grid["height"])+.5)*20
    xx, yy = np.meshgrid(x,y)
    mask = contains_xy(central,xx,yy)
    scenarios = []
    for i,name in enumerate(("DELINCUENCIA","VIOLENCIA","CONVIVENCIA"),1):
        scenarios.extend([(f"PUBLICADO_{name}_700",[e for e in old if e["analyticalClassId"] == i],700),
                          (f"CORREGIDO_{name}_700",[e for e in events if e["category"] == name],700),
                          (f"NUEVO_{name}",[e for e in events if e["category"] == name],d["parameters"]["URBANO"][name]["bandwidth"])])
    reclassified_institutional = [e for e in old if e["analyticalClassId"] <= 3 and d["dictionary"][e["subtype"]] == "ACTIVIDAD_INSTITUCIONAL"]
    scenarios.extend([("PUBLICADO_GENERAL_ANALITICO_700",[e for e in old if e["analyticalClassId"] <= 3],700),
                      ("PUBLICADO_RECLASIFICADO_INSTITUCIONAL_700",reclassified_institutional,700),
                      ("CONTRAFACTUAL_TODOS_700",events,700),
                      ("CONTRAFACTUAL_INSTITUCIONAL_700",[e for e in events if e["category"] == "ACTIVIDAD_INSTITUCIONAL"],700)])
    metrics = []
    for label,items,h in scenarios:
        xy,n = grouped(items,assignments)
        field = raster(xy,n,grid,h)
        repeated = [e for e in items if d["recurrenceById"][e["id"]] >= 10]
        rx,rn = grouped(repeated,assignments)
        recurrent_field = raster(rx,rn,grid,h)
        mass = float(field[mask].sum())*.0004
        recurrent_mass = float(recurrent_field[mask].sum())*.0004
        metrics.append({"ESCENARIO":label,"N_EVENTOS":len(items),"BANDWIDTH":h,"MASA_KDE_CENTRAL_HIJK":mass,"MAX_DENSIDAD_CENTRAL":float(field[mask].max()),"AREA_INFLUENCIA_CENTRAL_KM2":float(np.count_nonzero(field[mask]))*.0004,"MASA_CENTRAL_XY_ALTA_REPETICION":recurrent_mass,"PORCENTAJE_MASA_CENTRAL_XY_ALTA_REPETICION":100*recurrent_mass/mass if mass else 0})
        plot(field,grid,geoms,xy,label+f" | N={len(items)}",f"CENTRO_{label}.png",d["colorReference"],central.bounds)
    d["centralComparison"] = metrics
    institutional_metric = next(r for r in metrics if r["ESCENARIO"] == "PUBLICADO_RECLASIFICADO_INSTITUCIONAL_700")
    old_metric = next(r for r in metrics if r["ESCENARIO"] == "PUBLICADO_GENERAL_ANALITICO_700")
    d["centralAudit"] = {"publishedRecordsReclassifiedInstitutionalGlobal":sum(e["analyticalClassId"] <= 3 and d["dictionary"][e["subtype"]] == "ACTIVIDAD_INSTITUCIONAL" for e in source),"publishedUrbanRecordsReclassifiedInstitutional":len(reclassified_institutional),"institutionalContributionToPublishedCentralMassPctUnderNewDictionary":100*institutional_metric["MASA_KDE_CENTRAL_HIJK"]/old_metric["MASA_KDE_CENTRAL_HIJK"],"publishedExclusionDefinition":"Las clases originales 4/5 ya se excluian. Cuatro registros originalmente Violencia pasan ahora a institucional; dos pertenecen al ambito urbano operativo.","comparisonDefinition":"PUBLICADO usa clasificacion fuente anterior; CORREGIDO_*_700 cambia solo clasificacion; NUEVO cambia solo radio respecto a CORREGIDO. General y contrafactuales son diagnosticos, no nuevos selectores de analisis.","highRecurrenceDefinition":"RECURRENCIA_XY global >=10; aporte lineal integrado en H-I-J-K, no prueba error de geocodificacion ni causalidad."}
    d["metadata"]["FECHA_PROCESAMIENTO"] = datetime.now(timezone.utc).isoformat()
    d["metadata"]["FUENTE"] = sorted({e["source"] for e in source})
    out = ROOT/"data/seguridad-riobamba/correccion-conflictividad-20261001"
    (out/"RESULTADOS_RECALCULO.json").write_text(json.dumps({k:v for k,v in d.items() if k not in ("urbanGrid","recurrenceById","gi","derivedDiagnosis","derivedMethodology")},ensure_ascii=False,indent=2),encoding="utf-8")
    # Render the same clipped Gi* cells used by the interactive map, including holes.
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon, Patch
    colors = {"HOTSPOT 99%":"#7f1d1d","HOTSPOT 95%":"#dc2626","HOTSPOT 90%":"#fca5a5","NO SIGNIFICATIVO":"#f3f4f6","COLDSPOT 90%":"#93c5fd","COLDSPOT 95%":"#2563eb","COLDSPOT 99%":"#1e3a8a"}
    urban_grid = read_js("riobamba-incidentes-spatial-data.js","RIOBAMBA_INCIDENT_SPATIAL")["giGrid"]
    for scope,gi_grid in (("URBANO",urban_grid),("RURAL",territory["ruralGrid"])):
        outlines = geoms if scope == "URBANO" else [transform(project,shape(f["geometry"])) for f in territory["parishes"]["features"]]
        for category,values in d["gi"][scope].items():
            fig,ax = plt.subplots(figsize=(6,6),dpi=110)
            for cell,result in zip(gi_grid["cells"],values["results"]):
                geometry = transform(project,shape(cell["geometry"]))
                for polygon in (list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]):
                    ax.add_patch(Polygon(polygon.exterior.coords,facecolor=colors[result["GI_CLASS"]],edgecolor="white",linewidth=.2))
                    for hole in polygon.interiors: ax.add_patch(Polygon(hole.coords,facecolor="white",edgecolor="white",linewidth=.2))
            for geometry in outlines:
                for polygon in (list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]):
                    ax.plot(*polygon.exterior.xy,color="#263a33",linewidth=.7)
            xmin,ymin,xmax,ymax=unary_union(outlines).bounds
            ax.set_xlim(xmin,xmax);ax.set_ylim(ymin,ymax);ax.set_aspect("equal");ax.set_axis_off()
            ax.set_title(f"Gi* {scope} - {category} | N={values['records']}",fontsize=10)
            ax.legend(handles=[Patch(facecolor=color,label=label) for label,color in colors.items()],loc="lower left",fontsize=6)
            fig.text(.5,.02,"EPSG:32717 | significancia nominal exploratoria, sin FDR",ha="center",fontsize=8)
            fig.savefig(out/f"GI_{scope}_{category}.png",bbox_inches="tight",facecolor="white");plt.close(fig)
    (ROOT/"riobamba-conflictividad-data.js").write_text("window.RIOBAMBA_CONFLICTIVITY_CORRECTION = "+json.dumps(d,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf-8")
    write_csv("COMPARACION_CENTRO_HIJK.csv",metrics)
    print(json.dumps(metrics,ensure_ascii=False))


if __name__ == "__main__": main()
