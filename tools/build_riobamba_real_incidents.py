import argparse
import json
from collections import Counter
from datetime import datetime
from math import isfinite
from pathlib import Path

import openpyxl
from shapely.geometry import Point, shape


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = Path(r"C:/Users/PC/Downloads/Base de Datos Emergencias_SC_Riobamba (2).xlsx")
DEFAULT_CLASSIFICATION = ROOT / "data" / "seguridad-riobamba" / "clasificacion-incidentes-2026.json"
PLATFORMS = ROOT / "riobamba-censo-data" / "riobamba_plataformas.geojson"
OUTPUT = ROOT / "visor-seguridad-riobamba-data.js"
ANALYTIC_REVIEW = ROOT / "data/seguridad-riobamba/revision-metodologica-20261001/AUDITORIA_Y_CLASIFICACION.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Construye la fuente oficial de incidentes 2026 del visor.")
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--classification", type=Path, default=DEFAULT_CLASSIFICATION)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


def platform_for_point(lng, lat, platforms):
    point = Point(float(lng), float(lat))
    for feature, geometry in platforms:
        if geometry.covers(point):
            return feature["properties"]["platform_name"].replace("PLATAFORMA ", "")
    return None


def main():
    args = parse_args()
    classification_doc = json.loads(args.classification.read_text(encoding="utf-8-sig"))
    classification = {
        item["subtipo"].strip(): item
        for item in classification_doc["clasificacion_subtipos"]
    }
    review = json.loads(ANALYTIC_REVIEW.read_text(encoding="utf-8"))
    analytic = {row["SUBTIPO"]: row for row in review["classification"]}
    platforms_doc = json.loads(PLATFORMS.read_text(encoding="utf-8"))
    platforms = [(feature, shape(feature["geometry"])) for feature in platforms_doc["features"]]

    sheet = openpyxl.load_workbook(args.workbook, read_only=True, data_only=True)["Export"]
    source_rows = sheet.iter_rows(values_only=True)
    headers = [str(value).strip() for value in next(source_rows)]
    records = [dict(zip(headers, values)) for values in source_rows]
    records = [record for record in records if any(value is not None for value in record.values())]

    source_subtypes = {str(record["Subtipo"]).strip() for record in records}
    missing = sorted(source_subtypes - set(classification))
    unused = sorted(set(classification) - source_subtypes)
    if missing or unused:
        raise ValueError(f"Clasificacion no reconciliada. Faltan={missing}; sin uso={unused}")

    events = []
    category_rows = Counter()
    category_emergencies = Counter()
    parish_rows = Counter()
    parish_emergencies = Counter()
    hotspot_rows = Counter()
    hotspot_emergencies = Counter()
    platform_rows = Counter()
    platform_emergencies = Counter()
    dates = []

    for index, record in enumerate(records, start=2):
        subtype = str(record["Subtipo"]).strip()
        classified = classification[subtype]
        decision = analytic[subtype]
        category = decision["CLASIFICACION_NUEVA_PROPUESTA"]
        class_id = int(decision["CLASE_PROPUESTA"])
        hotspot_eligible = class_id in (1, 2, 3)
        weight = int(record["Emergencias"])
        lng = float(record["longitud"])
        lat = float(record["latitud"])
        valid_coordinate = isfinite(lng) and isfinite(lat) and -79.2 <= lng <= -78.2 and -2.1 <= lat <= -1.2
        date_value = record["Fecha"]
        date = date_value.date() if isinstance(date_value, datetime) else datetime.fromisoformat(str(date_value)).date()
        date_text = date.isoformat()
        parish = str(record["Parroquia"]).strip()
        platform = platform_for_point(lng, lat, platforms)
        events.append({
            "id": f"SC-2026-{index - 1:05d}",
            "date": date_text,
            "category": category,
            "analyticalClassId": class_id,
            "originalCategory": classified["categoria"].strip(),
            "originalHotspotEligible": classified["incluir_hotspot"].strip().upper() == "SI",
            "classificationStatus": "PENDIENTE_REVISION" if class_id == 5 else "CLASIFICACION_ANALITICA_OPERATIVA",
            "classificationReason": decision["MOTIVO"],
            "subtype": subtype,
            "parish": parish,
            "weight": weight,
            "hotspotEligible": hotspot_eligible,
            "precision": "A - Coordenada georreferenciada",
            "location": f"Parroquia {parish}",
            "source": "Base Emergencias Seguridad Ciudadana Riobamba 2026",
            "lat": lat,
            "lng": lng,
            "mappable": valid_coordinate,
            "coordinateAccuracy": "Coordenada original; precision de campo no verificada independientemente",
            "platform": platform,
        })
        dates.append(date)
        category_rows[category] += 1
        category_emergencies[category] += weight
        parish_rows[parish] += 1
        parish_emergencies[parish] += weight
        hotspot_key = "SI" if hotspot_eligible else "NO"
        hotspot_rows[hotspot_key] += 1
        hotspot_emergencies[hotspot_key] += weight
        platform_key = platform or "FUERA DE PLATAFORMAS"
        platform_rows[platform_key] += 1
        platform_emergencies[platform_key] += weight

    total_emergencies = sum(int(event["weight"]) for event in events)
    output = {
        "sourceWorkbook": args.workbook.name,
        "sourceClassification": args.classification.name,
        "analyticalClassification": str(ANALYTIC_REVIEW.relative_to(ROOT)),
        "analyticalClasses": {"1": "DELINCUENCIA", "2": "VIOLENCIA", "3": "CONVIVENCIA / INCIVILIDADES", "4": "ACTIVIDAD INSTITUCIONAL / POLICIAL", "5": "OTROS / REVISION"},
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "period": {"from": min(dates).isoformat(), "to": max(dates).isoformat()},
        "summary": {
            "totalRows": len(events),
            "totalEmergencies": total_emergencies,
            "validCoordinateRows": sum(event["mappable"] for event in events),
            "missingCoordinateRows": 0,
            "invalidCoordinateRows": sum(not event["mappable"] for event in events),
            "subtypes": len(source_subtypes),
            "hotspotRows": dict(hotspot_rows),
            "hotspotEmergencies": dict(hotspot_emergencies),
            "categoryRows": dict(category_rows.most_common()),
            "categoryEmergencies": dict(category_emergencies.most_common()),
            "parishRows": dict(parish_rows.most_common()),
            "parishEmergencies": dict(parish_emergencies.most_common()),
            "platformRows": dict(platform_rows.most_common()),
            "platformEmergencies": dict(platform_emergencies.most_common()),
        },
        "events": events,
        "ecu911": {
            "serviceCounts": [],
            "parishes": [],
            "topSubtypes": [],
            "topByParish": {},
            "totalRows": len(events),
            "securityRows": len(events),
        },
        "methodology": [
            {
                "precision": "A",
                "meaning": "Coordenada georreferenciada original",
                "use": "Punto original para análisis espacial",
            },
            {
                "precision": "Clasificación",
                "meaning": "Cinco clases analiticas trazables por subtipo; originales conservados",
                "use": "Solo clases 1, 2 y 3 participan en KDE, Gi*, tasas y brechas; clase 5 pendiente de revision",
            },
            {
                "precision": "Peso",
                "meaning": "Campo Emergencias",
                "use": "Valor original para consulta; los analisis espaciales y conteos de incidentes usan peso 1 por registro",
            },
        ],
    }
    payload = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        f"window.RIOBAMBA_SECURITY_DATA = {payload};\n"
        "window.RIOBAMBA_SECURITY_EVENTS = window.RIOBAMBA_SECURITY_DATA.events;\n",
        encoding="utf-8",
    )
    print(json.dumps(output["summary"], ensure_ascii=False))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
