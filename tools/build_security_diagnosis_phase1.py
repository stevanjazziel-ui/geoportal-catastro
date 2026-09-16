import json
from statistics import median
from datetime import datetime
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
TO_METERS = Transformer.from_crs("EPSG:4326", "EPSG:32717", always_xy=True).transform


def load_json(path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


stats = load_json(ROOT / "riobamba-censo-data" / "riobamba_plataformas_stats.json")
platform_geojson = load_json(ROOT / "riobamba-censo-data" / "riobamba_plataformas.geojson")
manzana_geojson = load_json(ROOT / "riobamba-censo-data" / "riobamba_manzanas.geojson")
manzana_stats = load_json(ROOT / "riobamba-censo-data" / "riobamba_manzanas_stats.json")


def read_js_object(path, variable):
    text = path.read_text(encoding="utf-8")
    prefix = f"window.{variable} = "
    payload = text.split(prefix, 1)[1]
    marker = "\nwindow."
    if marker in payload:
        payload = payload.split(marker, 1)[0]
    return json.loads(payload.rstrip().rstrip(";"))


cameras = read_js_object(ROOT / "riobamba-camaras-data.js", "RIOBAMBA_CAMERAS_DATA")
police = read_js_object(ROOT / "policia-06d01-data.js", "RIOBAMBA_POLICE_SIG_DATA")
security = read_js_object(ROOT / "visor-seguridad-riobamba-data.js", "RIOBAMBA_SECURITY_DATA")
boulevards = load_json(ROOT / "data" / "premio-habitat" / "premio-habitat-boulevares.geojson")
connections = load_json(ROOT / "data" / "premio-habitat" / "premio-habitat-conexiones.geojson")

CAMERA_SCENARIO_RADII_M = (100, 150, 200)
CAMERA_RADIUS_M = 150
BOULEVARD_RADIUS_M = 100
POLICE_RADIUS_M = 500


platform_geoms = {}
for feature in platform_geojson["features"]:
    name = feature["properties"]["platform_name"]
    geom = shape(feature["geometry"])
    platform_geoms[name] = {
        "geom": geom,
        "geomMeters": transform(TO_METERS, geom),
    }


by_man = manzana_stats.get("byMan", {})
POPULATION_FIELDS = [
    "population_total",
    "male",
    "female",
    "age_0_4",
    "age_5_11",
    "age_12_17",
    "age_18_29",
    "age_30_64",
    "age_65_plus",
]


def empty_population_allocations():
    return {
        name: {
            "manzanasTouched": set(),
            "manzanasWeighted": 0.0,
            "splitManzanas": 0,
            "areaM2": item["geomMeters"].area,
            **{field: 0.0 for field in POPULATION_FIELDS},
        }
        for name, item in platform_geoms.items()
    }


population_allocations = empty_population_allocations()
manzanas_with_population = 0
manzanas_intersected = 0
manzanas_split = 0
population_allocated_total = 0.0

for feature in manzana_geojson.get("features", []):
    code = (feature.get("properties") or {}).get("man")
    stats_row = by_man.get(code) or {}
    population = float(stats_row.get("population_total") or 0)
    geom_m = transform(TO_METERS, shape(feature["geometry"]))
    if geom_m.is_empty or geom_m.area <= 0:
        continue
    if population > 0:
        manzanas_with_population += 1
    intersections = []
    for platform_name, item in platform_geoms.items():
        intersection = geom_m.intersection(item["geomMeters"])
        if not intersection.is_empty and intersection.area > 0.01:
            intersections.append((platform_name, intersection.area / geom_m.area))
    if not intersections:
        continue
    manzanas_intersected += 1
    if len(intersections) > 1:
        manzanas_split += 1
    for platform_name, fraction in intersections:
        bucket = population_allocations[platform_name]
        bucket["manzanasTouched"].add(code)
        bucket["manzanasWeighted"] += fraction
        if len(intersections) > 1:
            bucket["splitManzanas"] += 1
        for field in POPULATION_FIELDS:
            bucket[field] += float(stats_row.get(field) or 0) * fraction
        population_allocated_total += population * fraction


def find_platform_for_point(lng, lat):
    if lng is None or lat is None:
        return None
    point = Point(float(lng), float(lat))
    for name, item in platform_geoms.items():
        geom = item["geom"]
        if geom.contains(point) or geom.touches(point):
            return name
    return None


def precision_geo(event):
    precision = str(event.get("precision") or "").strip().upper()
    if precision.startswith("A"):
        return "A"
    if precision.startswith("B"):
        return "B"
    return "C"


event_quality = {
    "total": len(security.get("events", [])),
    "byPrecisionGeo": {"A": 0, "B": 0, "C": 0},
    "spatialValidAB": 0,
    "notUsedForSpatialAnalysis": 0,
}
for event in security.get("events", []):
    precision = precision_geo(event)
    event_quality["byPrecisionGeo"][precision] += 1
    if precision in ("A", "B") and event.get("mappable") and event.get("lat") is not None and event.get("lng") is not None:
        event_quality["spatialValidAB"] += 1
    else:
        event_quality["notUsedForSpatialAnalysis"] += 1


def empty_platform_metrics():
    return {
        name: {
            "incidents": 0,
            "incidentsA": 0,
            "incidentsB": 0,
            "incidentTypes": {},
            "eventPointsM": [],
            "incidentsNearBoulevard": 0,
            "incidentsCoveredByCamera": 0,
            "incidentsNearPolice": 0,
            "policeInfrastructure": 0,
            "policeTypes": {},
            "policePersonnel": 0,
            "policePointsM": [],
            "populationNearPolice500": 0.0,
            "populationWeightedPoliceDistanceSum": 0.0,
            "populationWeightedPoliceDistancePopulation": 0.0,
            "incidentPoliceDistanceSum": 0.0,
            "incidentPoliceDistanceCount": 0,
            "nearestIncidentPoliceDistanceM": None,
            "cameras": 0,
            "camerasReplacement": 0,
            "cameraEvents2025": 0,
            "cameraPointsM": [],
            "cameraCoveredPopulation": 0.0,
            "cameraCoveredPopulation100": 0.0,
            "cameraCoveredPopulation150": 0.0,
            "cameraCoveredPopulation200": 0.0,
            "cameraCoveredAreaPct": 0,
            "cameraCoveredAreaPct100": 0,
            "cameraCoveredAreaPct150": 0,
            "cameraCoveredAreaPct200": 0,
            "camerasNearBoulevard": 0,
            "populationExposed100": 0.0,
            "populationExposed250": 0.0,
            "populationExposed500": 0.0,
            "boulevardLengthM": 0.0,
            "connectionLengthM": 0.0,
            "populationNearBoulevard": 0,
        }
        for name in platform_geoms
    }


metrics = empty_platform_metrics()
unassigned = {
    "events": 0,
    "policeInfrastructure": 0,
    "cameras": 0,
}

for event in security.get("events", []):
    precision = precision_geo(event)
    if precision not in ("A", "B"):
        continue
    if not event.get("mappable") or event.get("lat") is None or event.get("lng") is None:
        continue
    platform_name = find_platform_for_point(event.get("lng"), event.get("lat"))
    if not platform_name:
        unassigned["events"] += 1
        continue
    bucket = metrics[platform_name]
    bucket["incidents"] += 1
    bucket[f"incidents{precision}"] += 1
    bucket["eventPointsM"].append(transform(TO_METERS, Point(float(event.get("lng")), float(event.get("lat")))))
    category = event.get("category") or "Sin categoria"
    bucket["incidentTypes"][category] = bucket["incidentTypes"].get(category, 0) + 1

for feature in police.get("infrastructure", {}).get("features", []):
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    platform_name = find_platform_for_point(coords[0], coords[1]) if len(coords) >= 2 else None
    if not platform_name:
        unassigned["policeInfrastructure"] += 1
        continue
    props = feature.get("properties", {})
    bucket = metrics[platform_name]
    bucket["policeInfrastructure"] += 1
    kind = props.get("type") or "Sin tipo"
    bucket["policeTypes"][kind] = bucket["policeTypes"].get(kind, 0) + 1
    bucket["policePointsM"].append(transform(TO_METERS, Point(float(coords[0]), float(coords[1]))))
    try:
        bucket["policePersonnel"] += int(float(props.get("personnel") or 0))
    except (TypeError, ValueError):
        pass

for camera in cameras.get("cameras", []):
    platform_name = find_platform_for_point(camera.get("lng"), camera.get("lat"))
    if not platform_name:
        unassigned["cameras"] += 1
        continue
    bucket = metrics[platform_name]
    bucket["cameras"] += 1
    bucket["cameraPointsM"].append(transform(TO_METERS, Point(float(camera.get("lng")), float(camera.get("lat")))))
    if camera.get("requiresChange"):
        bucket["camerasReplacement"] += 1
    if camera.get("events2025") is not None:
        bucket["cameraEvents2025"] += int(camera.get("events2025") or 0)

for key, geojson in [("boulevardLengthM", boulevards), ("connectionLengthM", connections)]:
    for feature in geojson.get("features", []):
        line = transform(TO_METERS, shape(feature["geometry"]))
        if line.is_empty:
            continue
        for platform_name, item in platform_geoms.items():
            clipped = line.intersection(item["geomMeters"])
            if not clipped.is_empty:
                metrics[platform_name][key] += clipped.length

network_lines_m = [
    transform(TO_METERS, shape(feature["geometry"]))
    for geojson in (boulevards, connections)
    for feature in geojson.get("features", [])
    if feature.get("geometry")
]
network_union = unary_union(network_lines_m) if network_lines_m else None
network_buffer = network_union.buffer(BOULEVARD_RADIUS_M) if network_union and not network_union.is_empty else None

all_camera_points = [point for bucket in metrics.values() for point in bucket["cameraPointsM"]]
all_police_points = [point for bucket in metrics.values() for point in bucket["policePointsM"]]
all_event_points = [point for bucket in metrics.values() for point in bucket["eventPointsM"]]
camera_union = unary_union([point.buffer(CAMERA_RADIUS_M) for point in all_camera_points]) if all_camera_points else None
camera_buffers = {
    radius: unary_union([point.buffer(radius) for point in all_camera_points]) if all_camera_points else None
    for radius in CAMERA_SCENARIO_RADII_M
}
police_union = unary_union([point.buffer(POLICE_RADIUS_M) for point in all_police_points]) if all_police_points else None
police_access_union = unary_union([point.buffer(500) for point in all_police_points]) if all_police_points else None
exposure_buffers = {
    radius: unary_union([point.buffer(radius) for point in all_event_points]) if all_event_points else None
    for radius in (100, 250, 500)
}

man_to_platform = stats.get("manToPlatform", {})
for feature in manzana_geojson.get("features", []):
    code = (feature.get("properties") or {}).get("man")
    platform_name = man_to_platform.get(code)
    if not platform_name or platform_name not in metrics:
        continue
    population = int((by_man.get(code) or {}).get("population_total") or 0)
    if not population:
        continue
    geom_m = transform(TO_METERS, shape(feature["geometry"]))
    representative = geom_m.representative_point()
    if network_buffer and network_buffer.covers(representative):
        metrics[platform_name]["populationNearBoulevard"] += population
    if police_access_union and police_access_union.covers(representative):
        metrics[platform_name]["populationNearPolice500"] += population
    if all_police_points:
        nearest_police = min(representative.distance(point) for point in all_police_points)
        metrics[platform_name]["populationWeightedPoliceDistanceSum"] += nearest_police * population
        metrics[platform_name]["populationWeightedPoliceDistancePopulation"] += population

for feature in manzana_geojson.get("features", []):
    code = (feature.get("properties") or {}).get("man")
    stats_row = by_man.get(code) or {}
    population = float(stats_row.get("population_total") or 0)
    if not population:
        continue
    geom_m = transform(TO_METERS, shape(feature["geometry"]))
    if geom_m.is_empty or geom_m.area <= 0:
        continue
    for platform_name, item in platform_geoms.items():
        manzana_platform = geom_m.intersection(item["geomMeters"])
        if manzana_platform.is_empty or manzana_platform.area <= 0.01:
            continue
        for radius, buffer_geom in exposure_buffers.items():
            if not buffer_geom or buffer_geom.is_empty:
                continue
            exposed = manzana_platform.intersection(buffer_geom)
            if exposed.is_empty:
                continue
            metrics[platform_name][f"populationExposed{radius}"] += population * (exposed.area / geom_m.area)
        for radius, buffer_geom in camera_buffers.items():
            if not buffer_geom or buffer_geom.is_empty:
                continue
            covered = manzana_platform.intersection(buffer_geom)
            if covered.is_empty:
                continue
            metrics[platform_name][f"cameraCoveredPopulation{radius}"] += population * (covered.area / geom_m.area)

for platform_name, bucket in metrics.items():
    geom_m = platform_geoms[platform_name]["geomMeters"]
    if camera_union and not geom_m.is_empty and geom_m.area:
        bucket["cameraCoveredAreaPct"] = min(100, camera_union.intersection(geom_m).area / geom_m.area * 100)
    for radius, buffer_geom in camera_buffers.items():
        if buffer_geom and not geom_m.is_empty and geom_m.area:
            bucket[f"cameraCoveredAreaPct{radius}"] = min(100, buffer_geom.intersection(geom_m).area / geom_m.area * 100)
    bucket["cameraCoveredPopulation"] = bucket[f"cameraCoveredPopulation{CAMERA_RADIUS_M}"]
    for event_point in bucket["eventPointsM"]:
        if network_union and event_point.distance(network_union) <= BOULEVARD_RADIUS_M:
            bucket["incidentsNearBoulevard"] += 1
        if camera_union and camera_union.covers(event_point):
            bucket["incidentsCoveredByCamera"] += 1
        if police_union and police_union.covers(event_point):
            bucket["incidentsNearPolice"] += 1
        if all_police_points:
            distance = min(event_point.distance(point) for point in all_police_points)
            bucket["incidentPoliceDistanceSum"] += distance
            bucket["incidentPoliceDistanceCount"] += 1
            if bucket["nearestIncidentPoliceDistanceM"] is None or distance < bucket["nearestIncidentPoliceDistanceM"]:
                bucket["nearestIncidentPoliceDistanceM"] = distance
    for camera_point in bucket["cameraPointsM"]:
        if network_union and camera_point.distance(network_union) <= BOULEVARD_RADIUS_M:
            bucket["camerasNearBoulevard"] += 1


population_by_platform = {
    name: int(round(bucket["population_total"]))
    for name, bucket in population_allocations.items()
}
density_values = [
    population_by_platform[item["platform_name"]] / (population_allocations[item["platform_name"]]["areaM2"] / 1_000_000)
    for item in stats["platforms"]
    if population_allocations[item["platform_name"]]["areaM2"] > 0 and population_by_platform[item["platform_name"]] > 0
]
median_density = median(density_values) if density_values else 0
incident_rates = [
    metrics[item["platform_name"]]["incidents"] / population_by_platform[item["platform_name"]] * 1000
    for item in stats["platforms"]
    if population_by_platform[item["platform_name"]] > 0 and metrics[item["platform_name"]]["incidents"] > 0
]
median_incident_rate = median(incident_rates) if incident_rates else 0


def classify_deficit(score):
    if score >= 6:
        return "CRITICO"
    if score >= 4:
        return "ALTO"
    if score >= 2:
        return "MEDIO"
    return "BAJO"


def classify_institutional_coverage(bucket):
    score = int(bucket["cameras"] > 0) + int(bucket["policeInfrastructure"] > 0) + int((bucket["boulevardLengthM"] + bucket["connectionLengthM"]) > 0)
    if score >= 3:
        return "ALTA"
    if score == 2:
        return "MEDIA"
    return "BAJA"


def territorial_typology(bucket, density, incident_rate, deficit, coverage):
    high_conflict = bucket["incidents"] >= 2 or (bucket["incidents"] > 0 and incident_rate >= median_incident_rate)
    high_density = density >= median_density
    low_coverage = coverage == "BAJA" or deficit in ("ALTO", "CRITICO")
    if high_conflict and low_coverage:
        return "Alta conflictividad + baja cobertura"
    if high_conflict:
        return "Alta conflictividad + cobertura presente"
    if high_density and low_coverage:
        return "Alta densidad + deficit potencial"
    if low_coverage:
        return "Baja cobertura institucional"
    return "Cobertura relativa / conflictividad baja"

platforms = []
for item in stats["platforms"]:
    pop_bucket = population_allocations[item["platform_name"]]
    area_m2 = float(pop_bucket["areaM2"])
    area_km2 = area_m2 / 1_000_000
    area_ha = area_m2 / 10_000
    population = int(round(pop_bucket["population_total"]))
    bucket = metrics[item["platform_name"]]
    incident_rate = round(bucket["incidents"] / population * 1000, 2) if population else "N/D"
    camera_covered_population_pct = round(bucket["cameraCoveredPopulation"] / population * 100, 2) if population else "N/D"
    camera_coverage_pct_by_radius = {
        str(radius): round(bucket[f"cameraCoveredPopulation{radius}"] / population * 100, 2) if population else "N/D"
        for radius in CAMERA_SCENARIO_RADII_M
    }
    institutional_coverage = classify_institutional_coverage(bucket)
    deficit_score = 0
    density = population / area_km2 if area_km2 else 0
    if bucket["incidents"] >= 3:
        deficit_score += 2
    elif bucket["incidents"] > 0 and incident_rate != "N/D" and incident_rate >= median_incident_rate:
        deficit_score += 1
    if density >= median_density:
        deficit_score += 1
    if camera_covered_population_pct == "N/D" or camera_covered_population_pct < 25:
        deficit_score += 2
    elif camera_covered_population_pct < 50:
        deficit_score += 1
    if bucket["policeInfrastructure"] == 0:
        deficit_score += 1
    if bucket["cameras"] == 0:
        deficit_score += 1
    video_deficit = classify_deficit(deficit_score)
    hotspot_count = 1 if bucket["incidents"] >= 2 else 0
    low_coverage_hotspots = hotspot_count if hotspot_count and video_deficit in ("ALTO", "CRITICO") else 0
    boulevard_total_length = bucket["boulevardLengthM"] + bucket["connectionLengthM"]
    boulevard_density = round(boulevard_total_length / area_km2, 2) if area_km2 else "N/D"
    hotspot_near_boulevard = 1 if hotspot_count and bucket["incidentsNearBoulevard"] > 0 else 0
    population_police_distance = (
        round(bucket["populationWeightedPoliceDistanceSum"] / bucket["populationWeightedPoliceDistancePopulation"], 2)
        if bucket["populationWeightedPoliceDistancePopulation"]
        else "N/D"
    )
    incident_police_distance = (
        round(bucket["incidentPoliceDistanceSum"] / bucket["incidentPoliceDistanceCount"], 2)
        if bucket["incidentPoliceDistanceCount"]
        else "N/D"
    )
    critical_zone = "Priorizar evaluacion territorial" if video_deficit in ("ALTO", "CRITICO") else "Seguimiento ordinario"
    if bucket["incidents"] == 0 and bucket["cameras"] == 0 and bucket["policeInfrastructure"] == 0:
        critical_zone = "Validar demanda local con trabajo de campo"
    typology = territorial_typology(bucket, density, incident_rate if incident_rate != "N/D" else 0, video_deficit, institutional_coverage)
    platforms.append({
        "platformId": int(item["platform_id"]),
        "platform": item["platform_name"].replace("PLATAFORMA ", ""),
        "platformName": item["platform_name"],
        "areaM2": round(area_m2, 2),
        "areaHa": round(area_ha, 4),
        "areaKm2": round(area_km2, 4),
        "manzanas": len(pop_bucket["manzanasTouched"]),
        "manzanasWeighted": round(pop_bucket["manzanasWeighted"], 2),
        "splitManzanas": int(pop_bucket["splitManzanas"]),
        "population": population,
        "male": int(round(pop_bucket["male"])),
        "female": int(round(pop_bucket["female"])),
        "age0_4": int(round(pop_bucket["age_0_4"])),
        "age5_11": int(round(pop_bucket["age_5_11"])),
        "age12_17": int(round(pop_bucket["age_12_17"])),
        "age18_29": int(round(pop_bucket["age_18_29"])),
        "age30_64": int(round(pop_bucket["age_30_64"])),
        "age65Plus": int(round(pop_bucket["age_65_plus"])),
        "densityPopKm2": round(population / area_km2, 2) if area_km2 else None,
        "incidents": bucket["incidents"],
        "incidentsA": bucket["incidentsA"],
        "incidentsB": bucket["incidentsB"],
        "incidentsC": "N/D",
        "precisionGeoUsed": "A/B",
        "incidentRate1000": incident_rate,
        "incidentTypes": sorted(
            [{"type": key, "count": value} for key, value in bucket["incidentTypes"].items()],
            key=lambda row: row["count"],
            reverse=True,
        ),
        "hotspots": hotspot_count,
        "hotspotMethod": "Preliminar: plataforma con 2 o mas eventos georreferenciables asignados",
        "populationExposed100": int(round(bucket["populationExposed100"])),
        "populationExposed250": int(round(bucket["populationExposed250"])),
        "populationExposed500": int(round(bucket["populationExposed500"])),
        "policeInfrastructure": bucket["policeInfrastructure"],
        "policeTypes": bucket["policeTypes"],
        "policePersonnel": bucket["policePersonnel"] or "N/D",
        "populationPerPoliceInfrastructure": round(population / bucket["policeInfrastructure"], 2) if bucket["policeInfrastructure"] else "N/D",
        "populationPerPoliceOfficer": round(population / bucket["policePersonnel"], 2) if bucket["policePersonnel"] else "N/D",
        "populationNearPolice500": int(round(bucket["populationNearPolice500"])),
        "avgPopulationDistancePoliceM": population_police_distance,
        "avgIncidentDistancePoliceM": incident_police_distance,
        "nearestIncidentDistancePoliceM": round(bucket["nearestIncidentPoliceDistanceM"], 2) if bucket["nearestIncidentPoliceDistanceM"] is not None else "N/D",
        "cameras": bucket["cameras"],
        "cameraTotal": bucket["cameras"],
        "camerasReplacement": bucket["camerasReplacement"],
        "cameraReplacement": bucket["camerasReplacement"],
        "cameraEvents2025": bucket["cameraEvents2025"] or "N/D",
        "cameraCoverageRadiusM": CAMERA_RADIUS_M,
        "cameraCoveredPopulation": int(round(bucket["cameraCoveredPopulation"])),
        "cameraCoveredPopulation100": int(round(bucket["cameraCoveredPopulation100"])),
        "cameraCoveredPopulation150": int(round(bucket["cameraCoveredPopulation150"])),
        "cameraCoveredPopulation200": int(round(bucket["cameraCoveredPopulation200"])),
        "cameraUncoveredPopulation": max(0, population - int(round(bucket["cameraCoveredPopulation"]))),
        "cameraCoveredPopulationPct": camera_covered_population_pct,
        "cameraCoveragePctByRadius": camera_coverage_pct_by_radius,
        "cameraCoveredAreaPct": round(bucket["cameraCoveredAreaPct"], 2),
        "cameraCoveredAreaPct100": round(bucket["cameraCoveredAreaPct100"], 2),
        "cameraCoveredAreaPct150": round(bucket["cameraCoveredAreaPct150"], 2),
        "cameraCoveredAreaPct200": round(bucket["cameraCoveredAreaPct200"], 2),
        "incidentsCoveredByCamera": bucket["incidentsCoveredByCamera"],
        "videoDeficit": video_deficit,
        "videoDeficitScore": deficit_score,
        "boulevardLengthM": round(bucket["boulevardLengthM"], 2),
        "connectionLengthM": round(bucket["connectionLengthM"], 2),
        "boulevardTotalLengthM": round(boulevard_total_length, 2),
        "boulevardDensityMPerKm2": boulevard_density,
        "populationNearBoulevard": bucket["populationNearBoulevard"],
        "incidentsNearBoulevard": bucket["incidentsNearBoulevard"],
        "hotspotNearBoulevard": hotspot_near_boulevard,
        "camerasNearBoulevard": bucket["camerasNearBoulevard"],
        "incidentsNearPolice": bucket["incidentsNearPolice"],
        "lowCoverageHotspots": low_coverage_hotspots,
        "criticalZones": critical_zone,
        "institutionalCoverage": institutional_coverage,
        "territorialTypology": typology,
        "dataStatus": {
            "population": "DATO CALCULADO por interseccion areal manzana-plataforma; si una manzana cruza limites se estima por fraccion de area",
            "area": "DATO CALCULADO desde geometria real de plataformas",
            "securityIndicators": "DATO CALCULADO desde registros A/B georreferenciables; registros C quedan para estadistica general y no para hotspots puntuales",
            "institutionalCoverage": "DATO CALCULADO por punto dentro de plataforma, radio tecnico y longitud intersectada",
        },
    })

platforms.sort(key=lambda row: row["platform"])

def geojson_geometry_types(geojson):
    return sorted({feature.get("geometry", {}).get("type", "N/D") for feature in geojson.get("features", [])})


def geojson_fields(geojson):
    fields = set()
    for feature in geojson.get("features", []):
        fields.update((feature.get("properties") or {}).keys())
    return sorted(fields)


audit = [
    {
        "name": "Plataformas territoriales",
        "file": "riobamba-censo-data/riobamba_plataformas.geojson",
        "geometry": ", ".join(geojson_geometry_types(platform_geojson)),
        "records": len(platform_geojson.get("features", [])),
        "fields": geojson_fields(platform_geojson),
        "crs": "EPSG:4326 en GeoJSON; calculos geometricos reproyectados a EPSG:32717",
        "source": "GAD Riobamba / capa territorial cargada en el visor",
        "date": "N/D",
        "spatialPrecision": "Geometria oficial de plataformas usada sin redibujar ni simplificar",
        "duplicates": "No evaluado como duplicado geometrico; 18 nombres de plataforma unicos esperados",
        "emptyFields": "N/D",
        "relationships": "Unidad territorial principal para ANALISIS_PLATAFORMAS",
        "variableClass": "DATO ORIGINAL",
    },
    {
        "name": "Manzanas censales",
        "file": "riobamba-censo-data/riobamba_manzanas.geojson + riobamba_manzanas_stats.json",
        "geometry": ", ".join(geojson_geometry_types(manzana_geojson)),
        "records": len(manzana_geojson.get("features", [])),
        "fields": geojson_fields(manzana_geojson) + ["population_total", "male", "female", "age_* desde tabla estadistica"],
        "crs": "EPSG:4326 en GeoJSON; interseccion areal reproyectada a EPSG:32717",
        "source": "INEC CPV 2022 / insumo censal cargado en el visor",
        "date": "Censo 2022",
        "spatialPrecision": "Poligonos de manzana censal",
        "duplicates": "No se modifican atributos originales",
        "emptyFields": "Manzanas sin registro estadistico quedan sin aporte poblacional",
        "relationships": "Interseccion areal con plataformas para poblacion y exposicion",
        "variableClass": "DATO ORIGINAL + DATO CALCULADO",
    },
    {
        "name": "Eventos de seguridad",
        "file": "visor-seguridad-riobamba-data.js",
        "geometry": "Puntos para registros mapeables; agregados parroquiales se mantienen separados",
        "records": len(security.get("events", [])),
        "fields": sorted({key for event in security.get("events", []) for key in event.keys()}),
        "crs": "EPSG:4326 para coordenadas lat/lng",
        "source": "Fuentes publicas ya cargadas en visor",
        "date": "2024-2026 segun registros disponibles",
        "spatialPrecision": "Campo precision existente; registros no mapeables no se convierten en puntos",
        "duplicates": "N/D",
        "emptyFields": "N/D",
        "relationships": "Cruce espacial por punto dentro de plataforma",
        "variableClass": "DATO ORIGINAL + DATO CALCULADO",
    },
    {
        "name": "Infraestructura policial",
        "file": "policia-06d01-data.js",
        "geometry": "Puntos",
        "records": len(police.get("infrastructure", {}).get("features", [])),
        "fields": sorted({key for feature in police.get("infrastructure", {}).get("features", []) for key in (feature.get("properties") or {}).keys()}),
        "crs": "EPSG:4326 para coordenadas",
        "source": "Paquete SIG Policia 06D01 cargado en visor",
        "date": "N/D",
        "spatialPrecision": "Punto de infraestructura/dependencia, no todos son UPC",
        "duplicates": "N/D",
        "emptyFields": "Personal puede estar vacio o N/D",
        "relationships": "Cruce espacial por punto dentro de plataforma",
        "variableClass": "DATO ORIGINAL + DATO CALCULADO",
    },
    {
        "name": "Videovigilancia municipal",
        "file": "riobamba-camaras-data.js",
        "geometry": "Puntos",
        "records": len(cameras.get("cameras", [])),
        "fields": sorted({key for camera in cameras.get("cameras", []) for key in camera.keys()}),
        "crs": "EPSG:4326 para coordenadas",
        "source": "Informe de camaras / georreferenciacion verificada previamente",
        "date": "2026 / eventos 2025 cuando existe dato",
        "spatialPrecision": "Subconjunto municipal de 30 camaras; no se usan 103 ECU911 como municipales",
        "duplicates": "N/D",
        "emptyFields": "Eventos 2025 puede ser N/D",
        "relationships": "Cruce espacial por punto dentro de plataforma y escenarios de cobertura",
        "variableClass": "DATO ORIGINAL + ESCENARIO",
    },
    {
        "name": "Bulevares seguros y conexiones",
        "file": "data/premio-habitat/premio-habitat-boulevares.geojson + conexiones",
        "geometry": ", ".join(sorted(set(geojson_geometry_types(boulevards) + geojson_geometry_types(connections)))),
        "records": len(boulevards.get("features", [])) + len(connections.get("features", [])),
        "fields": sorted(set(geojson_fields(boulevards) + geojson_fields(connections))),
        "crs": "EPSG:4326 en GeoJSON; longitudes reproyectadas a EPSG:32717",
        "source": "Boulevares y conexiones cargados en visor",
        "date": "N/D",
        "spatialPrecision": "Lineas territoriales complementarias",
        "duplicates": "N/D",
        "emptyFields": "N/D",
        "relationships": "Longitud intersectada y proximidad como variable complementaria",
        "variableClass": "DATO ORIGINAL + DATO CALCULADO",
    },
]

inventory = [
    {
        "component": "Plataformas territoriales",
        "file": "riobamba-censo-data/riobamba_plataformas.geojson",
        "records": len(platforms),
        "role": "Unidad principal de analisis",
        "dataType": "DATO ORIGINAL + area calculada",
        "status": "Geometrias reales activas",
    },
    {
        "component": "Manzanas censales y poblacion",
        "file": "riobamba-censo-data/riobamba_manzanas.geojson + riobamba_plataformas_stats.json",
        "records": manzanas_intersected,
        "role": "Poblacion/exposicion por plataforma",
        "dataType": "DATO ORIGINAL + interseccion areal calculada",
        "status": f"{int(round(population_allocated_total)):,} habitantes estimados por fraccion de area".replace(",", "."),
    },
    {
        "component": "Eventos georreferenciables",
        "file": "visor-seguridad-riobamba-data.js",
        "records": len(security.get("events", [])),
        "role": "Insumo para conflictividad territorial",
        "dataType": "DATO ORIGINAL geocodificado/verificado previamente + conteo por plataforma calculado",
        "status": "No se usan registros parroquiales como puntos; hotspots son conteo preliminar por plataforma",
    },
    {
        "component": "Informacion general por parroquia",
        "file": "visor-seguridad-riobamba-data.js",
        "records": len(security.get("ecu911", {}).get("parishes", [])),
        "role": "Contexto estadistico",
        "dataType": "DATO ORIGINAL agregado",
        "status": "No convertido a puntos",
    },
    {
        "component": "Infraestructura policial",
        "file": "policia-06d01-data.js",
        "records": len(police.get("infrastructure", {}).get("features", [])),
        "role": "Cobertura/presencia institucional",
        "dataType": "DATO ORIGINAL espacial + conteo por plataforma calculado",
        "status": "Sin circuitos/subcircuitos como unidad principal",
    },
    {
        "component": "Videovigilancia",
        "file": "riobamba-camaras-data.js",
        "records": len(cameras.get("cameras", [])),
        "role": "Insumo de cobertura",
        "dataType": "DATO ORIGINAL + georreferenciacion verificada + conteo por plataforma calculado",
        "status": "Subconjunto municipal de 30 camaras",
    },
    {
        "component": "Bulevares seguros y conexiones",
        "file": "data/premio-habitat/premio-habitat-boulevares.geojson",
        "records": len(boulevards.get("features", [])) + len(connections.get("features", [])),
        "role": "Insumo territorial complementario",
        "dataType": "DATO ORIGINAL espacial + longitud intersectada por plataforma calculada",
        "status": "No es unidad principal del estudio",
    },
]

output = {
    "generatedAt": datetime.now().isoformat(timespec="seconds"),
    "phase": "ETAPA 6 - Bulevares como variable territorial complementaria",
    "masterTableName": "ANALISIS_PLATAFORMAS",
    "methodNotes": [
        "La unidad principal son las 18 plataformas territoriales reales.",
        "No se usan circuitos/subcircuitos como unidad principal.",
        "Etapas 1 a 6 implementadas: base poblacional areal + clasificacion A/B/C + concentracion/exposicion + infraestructura/accesibilidad + videovigilancia/cobertura/deficit + boulevares como variable complementaria.",
        "La poblacion por plataforma se estima por interseccion areal manzana-plataforma: POB_EST = POB_MANZANA * AREA_INTERSECCION / AREA_MANZANA.",
        "Se calculan conteos por plataforma cuando existe geometria verificable.",
        f"La cobertura potencial de camaras usa escenarios {', '.join(str(radius) for radius in CAMERA_SCENARIO_RADII_M)} m; el visor resume {CAMERA_RADIUS_M} m como escenario principal.",
        f"La poblacion cercana a boulevares/conexiones usa centroides de manzana dentro de {BOULEVARD_RADIUS_M} m.",
        f"La cercania institucional policial usa un radio tecnico inicial de {POLICE_RADIUS_M} m.",
        "Hotspots y deficit de videovigilancia son indicadores preliminares; no constituyen un indice ponderado definitivo.",
        "No se inventan coordenadas ni indicadores faltantes.",
    ],
    "summary": {
        "platforms": len(platforms),
        "populationWithPlatform": int(round(population_allocated_total)),
        "populationWithoutPlatform": max(0, int(round(float(manzana_stats.get("summary", {}).get("population_total", 0)) - population_allocated_total))),
        "manzanasAssigned": manzanas_intersected,
        "manzanasWithoutPlatform": max(0, len(manzana_geojson.get("features", [])) - manzanas_intersected),
        "manzanasWithPopulation": manzanas_with_population,
        "manzanasSplitByPlatforms": manzanas_split,
        "mappedIncidentsAssigned": sum(row["incidents"] for row in platforms),
        "incidentSpatialQuality": event_quality,
        "policeInfrastructureAssigned": sum(row["policeInfrastructure"] for row in platforms),
        "populationNearPolice500": sum(row["populationNearPolice500"] for row in platforms if isinstance(row["populationNearPolice500"], int)),
        "camerasAssigned": sum(row["cameras"] for row in platforms),
        "cameraCoverageRadiusM": CAMERA_RADIUS_M,
        "boulevardLengthM": round(sum(row["boulevardLengthM"] for row in platforms), 2),
        "connectionLengthM": round(sum(row["connectionLengthM"] for row in platforms), 2),
        "boulevardTotalLengthM": round(sum(row["boulevardTotalLengthM"] for row in platforms), 2),
        "cameraCoveredPopulation": sum(row["cameraCoveredPopulation"] for row in platforms if isinstance(row["cameraCoveredPopulation"], int)),
        "cameraCoveredPopulation100": sum(row["cameraCoveredPopulation100"] for row in platforms if isinstance(row["cameraCoveredPopulation100"], int)),
        "cameraCoveredPopulation150": sum(row["cameraCoveredPopulation150"] for row in platforms if isinstance(row["cameraCoveredPopulation150"], int)),
        "cameraCoveredPopulation200": sum(row["cameraCoveredPopulation200"] for row in platforms if isinstance(row["cameraCoveredPopulation200"], int)),
        "cameraUncoveredPopulation": sum(row["cameraUncoveredPopulation"] for row in platforms if isinstance(row["cameraUncoveredPopulation"], int)),
        "populationNearBoulevard": sum(row["populationNearBoulevard"] for row in platforms if isinstance(row["populationNearBoulevard"], int)),
        "incidentsNearBoulevard": sum(row["incidentsNearBoulevard"] for row in platforms if isinstance(row["incidentsNearBoulevard"], int)),
        "hotspotsNearBoulevard": sum(row["hotspotNearBoulevard"] for row in platforms if isinstance(row["hotspotNearBoulevard"], int)),
        "hotspots": sum(row["hotspots"] for row in platforms if isinstance(row["hotspots"], int)),
        "populationExposed100": sum(row["populationExposed100"] for row in platforms if isinstance(row["populationExposed100"], int)),
        "populationExposed250": sum(row["populationExposed250"] for row in platforms if isinstance(row["populationExposed250"], int)),
        "populationExposed500": sum(row["populationExposed500"] for row in platforms if isinstance(row["populationExposed500"], int)),
        "lowCoverageHotspots": sum(row["lowCoverageHotspots"] for row in platforms if isinstance(row["lowCoverageHotspots"], int)),
        "videoDeficitHighOrCritical": sum(1 for row in platforms if row["videoDeficit"] in ("ALTO", "CRITICO")),
        "unassigned": unassigned,
        "assumptions": {
            "cameraRadiusM": CAMERA_RADIUS_M,
            "cameraScenarioRadiiM": list(CAMERA_SCENARIO_RADII_M),
            "boulevardRadiusM": BOULEVARD_RADIUS_M,
            "policeRadiusM": POLICE_RADIUS_M,
            "medianDensityPopKm2": round(median_density, 2),
            "medianIncidentRate1000": round(median_incident_rate, 2),
        },
    },
    "methodControl": [
        {
            "result": "Poblacion por plataforma",
            "source": "Manzanas censales CPV 2022 + plataformas territoriales reales",
            "date": "Censo 2022",
            "precision": "Poligonos de manzana y plataforma",
            "method": "Interseccion areal en EPSG:32717",
            "parameters": "FRAC_AREA = AREA_INTERSECCION / AREA_MANZANA; POB_EST = POB_MANZANA * FRAC_AREA",
            "limitations": "Estimacion areal uniforme dentro de cada manzana; no reemplaza microdatos ni distribucion intra-manzana real",
        },
        {
            "result": "Area por plataforma",
            "source": "Geometria original de plataformas territoriales",
            "date": "N/D",
            "precision": "Limites originales de la capa",
            "method": "Area geodesica proyectada a EPSG:32717",
            "parameters": "AREA_M2 y AREA_KM2 derivados de geometria real",
            "limitations": "Depende de la calidad de la capa de plataformas cargada",
        },
        {
            "result": "Conflictividad territorial",
            "source": "Eventos de seguridad cargados en visor",
            "date": "2024-2026 segun registros disponibles",
            "precision": "PRECISION_GEO A/B/C derivada del campo precision",
            "method": "Cruce espacial de registros A y B mapeables dentro de plataformas",
            "parameters": "INC_TOTAL, INC_A, INC_B, INC_TIPO y TASA_INC_1000 = INC_TOTAL / POBLACION * 1000",
            "limitations": "Registros C no se convierten en puntos ni se usan para KDE/hotspots; el conteo depende de registros publicados y georreferenciables",
        },
        {
            "result": "Exposicion poblacional a conflictividad",
            "source": "Incidentes A/B georreferenciables + manzanas censales CPV 2022",
            "date": "2024-2026 incidentes; Censo 2022 poblacion",
            "precision": "Buffers euclidianos alrededor de puntos A/B; registros C excluidos",
            "method": "Union de buffers 100/250/500 m intersectada con manzana y plataforma; poblacion estimada por fraccion de area expuesta",
            "parameters": "POB_EXP_100, POB_EXP_250, POB_EXP_500",
            "limitations": "Escenario de proximidad, no mide exposicion real individual ni desplazamientos cotidianos",
        },
        {
            "result": "Accesibilidad a infraestructura policial",
            "source": "Infraestructura policial 06D01 + manzanas censales + incidentes A/B",
            "date": "N/D infraestructura; Censo 2022; incidentes 2024-2026",
            "precision": "Distancia euclidiana desde centroides representativos de manzana e incidentes georreferenciables",
            "method": "Distancia minima a infraestructura policial mas cercana y poblacion dentro de 500 m",
            "parameters": "DIST_INF_MEDIA, DIST_INC_INF_MEDIA, DIST_INC_INF_MIN, POB_CERCA_INF_500",
            "limitations": "No representa tiempo de respuesta ni accesibilidad por red vial; no asume que toda dependencia es UPC",
        },
        {
            "result": "Cobertura poblacional de videovigilancia",
            "source": "30 camaras municipales + manzanas censales CPV 2022",
            "date": "2026 camaras; Censo 2022 poblacion",
            "precision": "Escenarios euclidianos de cobertura potencial",
            "method": "Union de buffers de camaras 100/150/200 m intersectada con manzana y plataforma; evita doble conteo por union espacial",
            "parameters": "CAM_TOTAL, CAM_CAMBIO, POB_CUB_CAM, POB_NO_CUB_CAM, PCT_POB_CUB, PCT_AREA_CUB",
            "limitations": "Cobertura potencial, no distancia garantizada de identificacion ni calidad visual real",
        },
        {
            "result": "Deficit de videovigilancia",
            "source": "Conflictividad A/B + exposicion poblacional + cobertura potencial de camaras + presencia institucional",
            "date": "Datos disponibles en visor",
            "precision": "Clasificacion exploratoria por plataforma",
            "method": "Reglas exploratorias sin ponderaciones definitivas; combina incidentes, densidad, cobertura poblacional de camaras, infraestructura y camaras",
            "parameters": "DEFICIT_VIDEO = BAJO/MEDIO/ALTO/CRITICO; videoDeficitScore conserva trazabilidad inicial",
            "limitations": "No es ranking final ni AHP; requiere validacion tecnica antes de decisiones de inversion",
        },
        {
            "result": "Bulevares seguros como variable complementaria",
            "source": "Bulevares y conexiones cargados en el visor",
            "date": "N/D",
            "precision": "Lineas intersectadas con plataformas en EPSG:32717",
            "method": "Longitud por plataforma, densidad lineal por km2 y proximidad de poblacion/incidentes a 100 m",
            "parameters": "LONG_BOULEV, DENS_BOULEV, POB_CERCA_BOULEV, INC_CERCA_BOULEV, HOTSPOT_CERCA_BOULEV",
            "limitations": "Variable territorial complementaria; no se interpreta cercania a bulevar como seguridad garantizada",
        },
    ],
    "audit": audit,
    "inventory": inventory,
    "platformMaster": platforms,
    "byPlatformName": {row["platformName"]: row for row in platforms},
}

js_payload = (
    "window.RIOBAMBA_SECURITY_DIAGNOSIS = "
    + json.dumps(output, ensure_ascii=False, indent=2)
    + ";\n"
)
output_path = ROOT / "riobamba-seguridad-diagnostico-data.js"
try:
    output_path.write_text(js_payload, encoding="utf-8")
except PermissionError:
    output_path = Path("D:/codex/riobamba-seguridad-diagnostico-data.js")
    output_path.write_text(js_payload, encoding="utf-8")
print(json.dumps(output["summary"], ensure_ascii=False))
print(f"wrote {output_path}")
