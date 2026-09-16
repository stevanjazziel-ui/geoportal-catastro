import json
from datetime import datetime
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
TO_METERS = Transformer.from_crs("EPSG:4326", "EPSG:32717", always_xy=True).transform


def load_json(path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


stats = load_json(ROOT / "riobamba-censo-data" / "riobamba_plataformas_stats.json")
platform_geojson = load_json(ROOT / "riobamba-censo-data" / "riobamba_plataformas.geojson")


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
            "policeInfrastructure": 0,
            "policeTypes": {},
            "policePersonnel": 0,
            "cameras": 0,
            "camerasReplacement": 0,
            "cameraEvents2025": 0,
            "boulevardLengthM": 0.0,
            "connectionLengthM": 0.0,
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

platforms = []
for item in stats["platforms"]:
    area_ha = float(item["area"])
    area_km2 = area_ha / 100
    population = int(item["population_total"])
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
        "incidents": metrics[item["platform_name"]]["incidents"],
        "incidentRate1000": round(metrics[item["platform_name"]]["incidents"] / population * 1000, 2) if population else "N/D",
        "incidentTypes": sorted(
            [{"type": key, "count": value} for key, value in metrics[item["platform_name"]]["incidentTypes"].items()],
            key=lambda row: row["count"],
            reverse=True,
        ),
        "hotspots": "N/D",
        "policeInfrastructure": metrics[item["platform_name"]]["policeInfrastructure"],
        "policeTypes": metrics[item["platform_name"]]["policeTypes"],
        "policePersonnel": metrics[item["platform_name"]]["policePersonnel"] or "N/D",
        "populationPerPoliceInfrastructure": round(population / metrics[item["platform_name"]]["policeInfrastructure"], 2) if metrics[item["platform_name"]]["policeInfrastructure"] else "N/D",
        "populationPerPoliceOfficer": round(population / metrics[item["platform_name"]]["policePersonnel"], 2) if metrics[item["platform_name"]]["policePersonnel"] else "N/D",
        "cameras": metrics[item["platform_name"]]["cameras"],
        "camerasReplacement": metrics[item["platform_name"]]["camerasReplacement"],
        "cameraEvents2025": metrics[item["platform_name"]]["cameraEvents2025"] or "N/D",
        "cameraCoveredPopulation": "N/D",
        "cameraCoveredPopulationPct": "N/D",
        "cameraCoveredAreaPct": "N/D",
        "videoDeficit": "N/D",
        "boulevardLengthM": round(metrics[item["platform_name"]]["boulevardLengthM"], 2),
        "connectionLengthM": round(metrics[item["platform_name"]]["connectionLengthM"], 2),
        "populationNearBoulevard": "N/D",
        "incidentsNearBoulevard": "N/D",
        "lowCoverageHotspots": "N/D",
        "criticalZones": "N/D",
        "dataStatus": {
            "population": "DATO CALCULADO desde manzanas censales CPV 2022 asignadas a plataforma",
            "area": "DATO CALCULADO desde geometria real de plataformas",
            "securityIndicators": "DATO CALCULADO preliminar desde puntos georreferenciables; hotspots/deficit quedan N/D",
            "institutionalCoverage": "DATO CALCULADO por punto dentro de plataforma y longitud intersectada",
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
        "status": "No se usan registros parroquiales como puntos; hotspots quedan para fase posterior",
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
    "phase": "FASE 1 ampliada - Tabla maestra territorial con cruces preliminares",
    "methodNotes": [
        "La unidad principal son las 18 plataformas territoriales reales.",
        "No se usan circuitos/subcircuitos como unidad principal.",
        "Se calculan conteos por plataforma cuando existe geometria verificable.",
        "Hotspots, deficit de videovigilancia y coberturas poblacionales quedan como N/D hasta su fase tecnica.",
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
        "unassigned": unassigned,
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
