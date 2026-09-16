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

CAMERA_RADIUS_M = 250
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


def find_platform_for_point(lng, lat):
    if lng is None or lat is None:
        return None
    point = Point(float(lng), float(lat))
    for name, item in platform_geoms.items():
        geom = item["geom"]
        if geom.contains(point) or geom.touches(point):
            return name
    return None


def empty_platform_metrics():
    return {
        name: {
            "incidents": 0,
            "incidentTypes": {},
            "eventPointsM": [],
            "incidentsNearBoulevard": 0,
            "incidentsCoveredByCamera": 0,
            "incidentsNearPolice": 0,
            "policeInfrastructure": 0,
            "policeTypes": {},
            "policePersonnel": 0,
            "policePointsM": [],
            "cameras": 0,
            "camerasReplacement": 0,
            "cameraEvents2025": 0,
            "cameraPointsM": [],
            "cameraCoveredPopulation": 0,
            "cameraCoveredAreaPct": 0,
            "camerasNearBoulevard": 0,
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
    if not event.get("mappable") or event.get("lat") is None or event.get("lng") is None:
        continue
    platform_name = find_platform_for_point(event.get("lng"), event.get("lat"))
    if not platform_name:
        unassigned["events"] += 1
        continue
    bucket = metrics[platform_name]
    bucket["incidents"] += 1
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
camera_union = unary_union([point.buffer(CAMERA_RADIUS_M) for point in all_camera_points]) if all_camera_points else None
police_union = unary_union([point.buffer(POLICE_RADIUS_M) for point in all_police_points]) if all_police_points else None

by_man = manzana_stats.get("byMan", {})
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
    if camera_union and camera_union.covers(representative):
        metrics[platform_name]["cameraCoveredPopulation"] += population
    if network_buffer and network_buffer.covers(representative):
        metrics[platform_name]["populationNearBoulevard"] += population

for platform_name, bucket in metrics.items():
    geom_m = platform_geoms[platform_name]["geomMeters"]
    if camera_union and not geom_m.is_empty and geom_m.area:
        bucket["cameraCoveredAreaPct"] = min(100, camera_union.intersection(geom_m).area / geom_m.area * 100)
    for event_point in bucket["eventPointsM"]:
        if network_union and event_point.distance(network_union) <= BOULEVARD_RADIUS_M:
            bucket["incidentsNearBoulevard"] += 1
        if camera_union and camera_union.covers(event_point):
            bucket["incidentsCoveredByCamera"] += 1
        if police_union and police_union.covers(event_point):
            bucket["incidentsNearPolice"] += 1
    for camera_point in bucket["cameraPointsM"]:
        if network_union and camera_point.distance(network_union) <= BOULEVARD_RADIUS_M:
            bucket["camerasNearBoulevard"] += 1


population_by_platform = {item["platform_name"]: int(item["population_total"]) for item in stats["platforms"]}
density_values = [
    int(item["population_total"]) / (float(item["area"]) / 100)
    for item in stats["platforms"]
    if float(item["area"]) > 0 and int(item["population_total"]) > 0
]
median_density = median(density_values) if density_values else 0
incident_rates = [
    metrics[item["platform_name"]]["incidents"] / int(item["population_total"]) * 1000
    for item in stats["platforms"]
    if int(item["population_total"]) > 0 and metrics[item["platform_name"]]["incidents"] > 0
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
    area_ha = float(item["area"])
    area_km2 = area_ha / 100
    population = int(item["population_total"])
    bucket = metrics[item["platform_name"]]
    incident_rate = round(bucket["incidents"] / population * 1000, 2) if population else "N/D"
    camera_covered_population_pct = round(bucket["cameraCoveredPopulation"] / population * 100, 2) if population else "N/D"
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
    critical_zone = "Priorizar evaluacion territorial" if video_deficit in ("ALTO", "CRITICO") else "Seguimiento ordinario"
    if bucket["incidents"] == 0 and bucket["cameras"] == 0 and bucket["policeInfrastructure"] == 0:
        critical_zone = "Validar demanda local con trabajo de campo"
    typology = territorial_typology(bucket, density, incident_rate if incident_rate != "N/D" else 0, video_deficit, institutional_coverage)
    platforms.append({
        "platformId": int(item["platform_id"]),
        "platform": item["platform_name"].replace("PLATAFORMA ", ""),
        "platformName": item["platform_name"],
        "areaHa": round(area_ha, 4),
        "areaKm2": round(area_km2, 4),
        "manzanas": int(item["manzanas"]),
        "population": population,
        "male": int(item["male"]),
        "female": int(item["female"]),
        "age0_4": int(item["age_0_4"]),
        "age5_11": int(item["age_5_11"]),
        "age12_17": int(item["age_12_17"]),
        "age18_29": int(item["age_18_29"]),
        "age30_64": int(item["age_30_64"]),
        "age65Plus": int(item["age_65_plus"]),
        "densityPopKm2": round(population / area_km2, 2) if area_km2 else None,
        "incidents": bucket["incidents"],
        "incidentRate1000": incident_rate,
        "incidentTypes": sorted(
            [{"type": key, "count": value} for key, value in bucket["incidentTypes"].items()],
            key=lambda row: row["count"],
            reverse=True,
        ),
        "hotspots": hotspot_count,
        "hotspotMethod": "Preliminar: plataforma con 2 o mas eventos georreferenciables asignados",
        "policeInfrastructure": bucket["policeInfrastructure"],
        "policeTypes": bucket["policeTypes"],
        "policePersonnel": bucket["policePersonnel"] or "N/D",
        "populationPerPoliceInfrastructure": round(population / bucket["policeInfrastructure"], 2) if bucket["policeInfrastructure"] else "N/D",
        "populationPerPoliceOfficer": round(population / bucket["policePersonnel"], 2) if bucket["policePersonnel"] else "N/D",
        "cameras": bucket["cameras"],
        "camerasReplacement": bucket["camerasReplacement"],
        "cameraEvents2025": bucket["cameraEvents2025"] or "N/D",
        "cameraCoveredPopulation": bucket["cameraCoveredPopulation"],
        "cameraCoveredPopulationPct": camera_covered_population_pct,
        "cameraCoveredAreaPct": round(bucket["cameraCoveredAreaPct"], 2),
        "incidentsCoveredByCamera": bucket["incidentsCoveredByCamera"],
        "videoDeficit": video_deficit,
        "videoDeficitScore": deficit_score,
        "boulevardLengthM": round(bucket["boulevardLengthM"], 2),
        "connectionLengthM": round(bucket["connectionLengthM"], 2),
        "populationNearBoulevard": bucket["populationNearBoulevard"],
        "incidentsNearBoulevard": bucket["incidentsNearBoulevard"],
        "camerasNearBoulevard": bucket["camerasNearBoulevard"],
        "incidentsNearPolice": bucket["incidentsNearPolice"],
        "lowCoverageHotspots": low_coverage_hotspots,
        "criticalZones": critical_zone,
        "institutionalCoverage": institutional_coverage,
        "territorialTypology": typology,
        "dataStatus": {
            "population": "DATO CALCULADO desde manzanas censales CPV 2022 asignadas a plataforma",
            "area": "DATO CALCULADO desde geometria real de plataformas",
            "securityIndicators": "DATO CALCULADO preliminar desde puntos georreferenciables; hotspot no reemplaza un analisis kernel definitivo",
            "institutionalCoverage": "DATO CALCULADO por punto dentro de plataforma, radio tecnico y longitud intersectada",
        },
    })

platforms.sort(key=lambda row: row["platform"])

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
        "records": int(stats["summary"]["manzanas_assigned"]),
        "role": "Poblacion/exposicion por plataforma",
        "dataType": "DATO ORIGINAL + agregacion calculada",
        "status": f"{int(stats['summary']['population_total_with_platform']):,} habitantes asignados".replace(",", "."),
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
    "phase": "Fases integradas - Diagnostico territorial operativo preliminar",
    "methodNotes": [
        "La unidad principal son las 18 plataformas territoriales reales.",
        "No se usan circuitos/subcircuitos como unidad principal.",
        "Se calculan conteos por plataforma cuando existe geometria verificable.",
        f"La cobertura potencial de camaras usa un radio tecnico inicial de {CAMERA_RADIUS_M} m; no equivale a alcance visual real ni analitica forense.",
        f"La poblacion cercana a boulevares/conexiones usa centroides de manzana dentro de {BOULEVARD_RADIUS_M} m.",
        f"La cercania institucional policial usa un radio tecnico inicial de {POLICE_RADIUS_M} m.",
        "Hotspots y deficit de videovigilancia son indicadores preliminares; no constituyen un indice ponderado definitivo.",
        "No se inventan coordenadas ni indicadores faltantes.",
    ],
    "summary": {
        "platforms": len(platforms),
        "populationWithPlatform": int(stats["summary"]["population_total_with_platform"]),
        "populationWithoutPlatform": int(stats["summary"]["population_total_without_platform"]),
        "manzanasAssigned": int(stats["summary"]["manzanas_assigned"]),
        "manzanasWithoutPlatform": int(stats["summary"]["manzanas_without_platform"]),
        "mappedIncidentsAssigned": sum(row["incidents"] for row in platforms),
        "policeInfrastructureAssigned": sum(row["policeInfrastructure"] for row in platforms),
        "camerasAssigned": sum(row["cameras"] for row in platforms),
        "boulevardLengthM": round(sum(row["boulevardLengthM"] for row in platforms), 2),
        "connectionLengthM": round(sum(row["connectionLengthM"] for row in platforms), 2),
        "cameraCoveredPopulation": sum(row["cameraCoveredPopulation"] for row in platforms if isinstance(row["cameraCoveredPopulation"], int)),
        "populationNearBoulevard": sum(row["populationNearBoulevard"] for row in platforms if isinstance(row["populationNearBoulevard"], int)),
        "hotspots": sum(row["hotspots"] for row in platforms if isinstance(row["hotspots"], int)),
        "lowCoverageHotspots": sum(row["lowCoverageHotspots"] for row in platforms if isinstance(row["lowCoverageHotspots"], int)),
        "videoDeficitHighOrCritical": sum(1 for row in platforms if row["videoDeficit"] in ("ALTO", "CRITICO")),
        "unassigned": unassigned,
        "assumptions": {
            "cameraRadiusM": CAMERA_RADIUS_M,
            "boulevardRadiusM": BOULEVARD_RADIUS_M,
            "policeRadiusM": POLICE_RADIUS_M,
            "medianDensityPopKm2": round(median_density, 2),
            "medianIncidentRate1000": round(median_incident_rate, 2),
        },
    },
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
