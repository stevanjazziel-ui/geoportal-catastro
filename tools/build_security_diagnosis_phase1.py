import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


stats = load_json(ROOT / "riobamba-censo-data" / "riobamba_plataformas_stats.json")


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
        "incidents": "N/D",
        "incidentRate1000": "N/D",
        "hotspots": "N/D",
        "policeInfrastructure": "N/D",
        "policePersonnel": "N/D",
        "populationPerPoliceInfrastructure": "N/D",
        "populationPerPoliceOfficer": "N/D",
        "cameras": "N/D",
        "camerasReplacement": "N/D",
        "cameraCoveredPopulation": "N/D",
        "cameraCoveredPopulationPct": "N/D",
        "cameraCoveredAreaPct": "N/D",
        "videoDeficit": "N/D",
        "boulevardLengthM": "N/D",
        "populationNearBoulevard": "N/D",
        "incidentsNearBoulevard": "N/D",
        "lowCoverageHotspots": "N/D",
        "criticalZones": "N/D",
        "dataStatus": {
            "population": "DATO CALCULADO desde manzanas censales CPV 2022 asignadas a plataforma",
            "area": "DATO CALCULADO desde geometria real de plataformas",
            "securityIndicators": "N/D en Fase 1; se calculara en fases posteriores",
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
        "role": "Insumo para conflictividad y hotspots",
        "dataType": "DATO ORIGINAL geocodificado/verificado previamente",
        "status": "No se usan registros parroquiales como puntos",
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
        "dataType": "DATO ORIGINAL espacial",
        "status": "Sin circuitos/subcircuitos como unidad principal",
    },
    {
        "component": "Videovigilancia",
        "file": "riobamba-camaras-data.js",
        "records": len(cameras.get("cameras", [])),
        "role": "Insumo de cobertura",
        "dataType": "DATO ORIGINAL + georreferenciacion verificada",
        "status": "Subconjunto municipal de 30 camaras",
    },
    {
        "component": "Bulevares seguros y conexiones",
        "file": "data/premio-habitat/premio-habitat-boulevares.geojson",
        "records": 38,
        "role": "Insumo territorial complementario",
        "dataType": "DATO ORIGINAL espacial",
        "status": "No es unidad principal del estudio",
    },
]

output = {
    "generatedAt": datetime.now().isoformat(timespec="seconds"),
    "phase": "FASE 1 - Inventario + tabla maestra + plataformas + poblacion",
    "methodNotes": [
        "La unidad principal son las 18 plataformas territoriales reales.",
        "No se usan circuitos/subcircuitos como unidad principal.",
        "Los campos no calculados se mantienen como N/D.",
        "No se inventan coordenadas ni indicadores faltantes.",
    ],
    "summary": {
        "platforms": len(platforms),
        "populationWithPlatform": int(stats["summary"]["population_total_with_platform"]),
        "populationWithoutPlatform": int(stats["summary"]["population_total_without_platform"]),
        "manzanasAssigned": int(stats["summary"]["manzanas_assigned"]),
        "manzanasWithoutPlatform": int(stats["summary"]["manzanas_without_platform"]),
    },
    "inventory": inventory,
    "platformMaster": platforms,
    "byPlatformName": {row["platformName"]: row for row in platforms},
}

(ROOT / "riobamba-seguridad-diagnostico-data.js").write_text(
    "window.RIOBAMBA_SECURITY_DIAGNOSIS = "
    + json.dumps(output, ensure_ascii=False, indent=2)
    + ";\n",
    encoding="utf-8",
)
print(json.dumps(output["summary"], ensure_ascii=False))
