"""Refresh incident-dependent summaries without rebuilding camera/population geometry."""
import json
import math
from statistics import median
from collections import Counter
from pathlib import Path
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union
from audit_cantonal_expansion import read_js, ROOT
from build_cantonal_analysis import gi


def main():
    source = read_js("visor-seguridad-riobamba-data.js", "RIOBAMBA_SECURITY_DATA")
    correction = read_js("riobamba-conflictividad-data.js", "RIOBAMBA_CONFLICTIVITY_CORRECTION")
    territory = read_js("riobamba-cantonal-data.js", "RIOBAMBA_CANTONAL_DATA")
    diagnosis = read_js("riobamba-seguridad-diagnostico-data.js", "RIOBAMBA_SECURITY_DIAGNOSIS")
    method = read_js("riobamba-metodologia-data.js", "RIOBAMBA_METHODOLOGY")
    spatial = read_js("riobamba-incidentes-spatial-data.js", "RIOBAMBA_INCIDENT_SPATIAL")
    cameras = read_js("riobamba-camaras-data.js", "RIOBAMBA_CAMERAS_DATA")["cameras"]
    police = read_js("policia-06d01-data.js", "RIOBAMBA_POLICE_SIG_DATA")["infrastructure"]["features"]
    project = Transformer.from_crs(4326, 32717, always_xy=True).transform
    classes = ["DELINCUENCIA", "VIOLENCIA", "CONVIVENCIA", "ACTIVIDAD_INSTITUCIONAL", "OTROS_REVISION"]
    events = [{**e, "category":correction["dictionary"][e["subtype"]], "analyticalClassId":classes.index(correction["dictionary"][e["subtype"]])+1} for e in source["events"]]
    urban = [e for e in events if e["analyticalClassId"] <= 3 and territory["assignments"][e["id"]]["scope"] == "URBANO"]
    pts = {e["id"]:Point(territory["assignments"][e["id"]]["x"],territory["assignments"][e["id"]]["y"]) for e in urban}
    camera_points = [transform(project, Point(c["lng"],c["lat"])) for c in cameras]
    police_points = unary_union([transform(project,shape(f["geometry"])) for f in police])
    roads = unary_union([transform(project,shape(f["geometry"])) for name in ("boulevares","conexiones") for f in json.loads((ROOT/f"data/premio-habitat/premio-habitat-{name}.geojson").read_text(encoding="utf-8"))["features"]])
    camera_ids = {str(r):[e["id"] for e in events if e["analyticalClassId"] <= 3 and min(Point(territory["assignments"][e["id"]]["x"],territory["assignments"][e["id"]]["y"]).distance(p) for p in camera_points) <= r] for r in (100,150,200)}
    for radius, scenario in method["cameraScenarios"].items():
        scenario["incidentIdsCovered"] = camera_ids[radius]
    method["classNames"] = {str(i+1):name for i,name in enumerate(classes)}
    method["urbanCounts"] = {str(i):sum(e["analyticalClassId"] == i for e in urban) for i in (1,2,3)}
    method["urbanRates100000"] = {i:n/177213*100000 for i,n in method["urbanCounts"].items()}
    platform_geo = json.loads((ROOT/"riobamba-censo-data/riobamba_plataformas.geojson").read_text(encoding="utf-8"))["features"]
    platform_geoms = {f["properties"]["platform_name"]:transform(project,shape(f["geometry"])) for f in platform_geo}
    grid = spatial["giGrid"]
    centers = [(c["x"],c["y"]) for c in grid["cells"]]
    neighbors = [[j for j,(x,y) in enumerate(centers) if (x-cx)**2+(y-cy)**2 <= 500**2+1e-6] for cx,cy in centers]
    index = {(c["row"],c["col"]):i for i,c in enumerate(grid["cells"])}
    counts = [0]*len(centers)
    for p in pts.values():
        counts[index[(math.floor((p.y-grid["minY"])/grid["cellSize"]),math.floor((p.x-grid["minX"])/grid["cellSize"]))]] += 1
    results = gi(counts,neighbors)
    buffers = {r:unary_union([p.buffer(r) for p in set(pts.values())]) for r in (100,250,500)}
    blocks = json.loads((ROOT/"riobamba-censo-data/riobamba_manzanas.geojson").read_text(encoding="utf-8-sig"))["features"]
    block_stats = json.loads((ROOT/"riobamba-censo-data/riobamba_manzanas_stats.json").read_text(encoding="utf-8-sig"))["byMan"]
    exposure = {name:{r:0.0 for r in buffers} for name in platform_geoms}
    uncovered_exposure = {name:{r:0.0 for r in (100,150,200)} for name in platform_geoms}
    uncovered_buffers = {r:buffers[250].difference(unary_union([p.buffer(r,quad_segs=64) for p in camera_points])) for r in (100,150,200)}
    for f in blocks:
        population = block_stats.get(f["properties"].get("man"),{}).get("population_total",0) or 0
        if not population: continue
        geometry = transform(project,shape(f["geometry"]))
        if not geometry.area: continue
        for name,platform in platform_geoms.items():
            part = geometry.intersection(platform)
            if part.area <= .01: continue
            for r,buffer in buffers.items(): exposure[name][r] += population * part.intersection(buffer).area / geometry.area
            for r,buffer in uncovered_buffers.items(): uncovered_exposure[name][r] += population * part.intersection(buffer).area / geometry.area
    for row in diagnosis["platformMaster"]:
        name = row["platformName"]
        items = [e for e in urban if territory["assignments"][e["id"]]["unit"] == name]
        local_pts = [pts[e["id"]] for e in items]
        row["incidents"] = row["incidentsA"] = len(items)
        row["incidentRate1000"] = len(items)/row["population"]*1000 if row["population"] else None
        row["incidentTypes"] = [{"type":k,"count":v} for k,v in Counter(e["category"] for e in items).most_common()]
        row["incidentsCoveredByCamera"] = sum(e["id"] in set(camera_ids["150"]) for e in items)
        row["incidentsNearPolice"] = sum(p.distance(police_points) <= 500 for p in local_pts)
        row["incidentsNearBoulevard"] = sum(p.distance(roads) <= 100 for p in local_pts)
        row["avgIncidentDistancePoliceM"] = sum(p.distance(police_points) for p in local_pts)/len(items) if items else None
        row["nearestIncidentDistancePoliceM"] = min((p.distance(police_points) for p in local_pts),default=None)
        hot = [c for c,r in zip(grid["cells"],results) if r["GI_CLASS"].startswith("HOT") and c["platform"] == name]
        row["hotspots"] = row["giHotspots"] = len(hot)
        row["hotspotMethod"] = "Gi* descriptivo general analitico actualizado; nominal sin FDR, 250/500 m. No sustituye los tres analisis por categoria."
        row["hotspotNearBoulevard"] = sum(transform(project,shape(c["geometry"])).distance(roads) <= 100 for c in hot)
        for r in buffers: row[f"populationExposed{r}"] = round(exposure[name][r])
        row["typologyFactors"][0] = f"{len(items)} registros analiticos"
        fields = row["masterFields"]
        fields.update(INC_TOTAL=len(items),TASA_INC_1000=row["incidentRate1000"],NUM_HOTSPOTS=len(hot),POB_EXP_250=row["populationExposed250"],POB_EXP_500=row["populationExposed500"],INC_CERCA_BOULEV=row["incidentsNearBoulevard"])
        all_local = [e for e in events if territory["assignments"][e["id"]]["scope"] == "URBANO" and territory["assignments"][e["id"]]["unit"] == name]
        counts_by_class = {str(i):sum(e["analyticalClassId"] == i for e in all_local) for i in (1,2,3,4,5)}
        local_method = method["byPlatformName"][name]
        local_method["counts"] = counts_by_class
        local_method["rates1000"] = {i:n/row["population"]*1000 if row["population"] else None for i,n in counts_by_class.items() if int(i) <= 3}
        local_method["predominantClass"] = max((1,2,3),key=lambda i:counts_by_class[str(i)])
        local_method["predominantSubtype"] = Counter(e["subtype"] for e in items).most_common(1)
        local_method["months"] = dict(Counter(e["date"][:7] for e in items))
        local_method["boulevardNearbyByClass"] = {str(i):sum(pts[e["id"]].distance(roads) <= 100 for e in items if e["analyticalClassId"] == i) for i in (1,2,3)}
        for radius, scenario in method["cameraScenarios"].items():
            covered = set(camera_ids[radius])
            scenario["byPlatformName"][name]["incidentsByClass"] = {str(i):{"total":counts_by_class[str(i)],"covered":sum(e["id"] in covered for e in items if e["analyticalClassId"] == i)} for i in (1,2,3)}
            scenario["byPlatformName"][name]["exposedUncoveredPopulation250"] = uncovered_exposure[name][int(radius)]
        diagnosis["byPlatformName"][name] = row
    for key in ("populationExposed100","populationExposed250","populationExposed500","incidentsNearBoulevard","hotspotsNearBoulevard","hotspots"):
        row_key = "hotspotNearBoulevard" if key == "hotspotsNearBoulevard" else key
        diagnosis["summary"][key] = sum(r[row_key] for r in diagnosis["platformMaster"])
    diagnosis["summary"]["mappedIncidentsAssigned"] = len(urban)
    diagnosis["summary"]["unassigned"]["events"] = sum(e["analyticalClassId"] <= 3 for e in events) - len(urban)
    diagnosis["summary"]["incidentSpatialQuality"]["spatialValidAB"] = sum(e["analyticalClassId"] <= 3 for e in events)
    quality = diagnosis["summary"]["incidentSpatialQuality"]
    analytic = [e for e in events if e["analyticalClassId"] <= 3]
    institutional = [e for e in events if e["analyticalClassId"] == 4]
    other = [e for e in events if e["analyticalClassId"] == 5]
    quality.update(conflictRows=len(analytic),conflictEmergencies=sum(e["weight"] for e in analytic),
                   institutionalRowsExcluded=len(institutional),otherReviewRowsExcluded=len(other),
                   institutionalEmergenciesExcluded=sum(e["weight"] for e in institutional),notUsedForSpatialAnalysis=len(institutional)+len(other))
    diagnosis["summary"]["assumptions"]["medianIncidentRate1000"] = median(r["incidentRate1000"] for r in diagnosis["platformMaster"] if r["incidentRate1000"] is not None)
    correction["derivedDiagnosis"] = diagnosis
    correction["derivedMethodology"] = method
    (ROOT/"riobamba-conflictividad-data.js").write_text("window.RIOBAMBA_CONFLICTIVITY_CORRECTION = "+json.dumps(correction,ensure_ascii=False,separators=(",",":"))+";\n",encoding="utf-8")
    print(json.dumps({"urbanAnalytic":len(urban),"cameraUniverse":len(cameras),"cameraIncidentCounts":{r:len(ids) for r,ids in camera_ids.items()},"diagnosisPlatforms":len(diagnosis["platformMaster"])}))


if __name__ == "__main__": main()
