#!/usr/bin/env python3
"""Build the privacy-minimized data bundle for the Avalúos dashboard.

The source CSV is exported from the SharePoint workbook sheet
"MATRIZ DE CONTROL INTERNO". Applicant names, observations and notary fields
are deliberately excluded from the public-facing bundle.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


DEFAULT_SOURCE = Path("tmp/matriz-control-interno-2026.csv")
DEFAULT_DASHBOARD_SOURCE = Path("tmp/matriz-dashboard-2026.csv")
DEFAULT_OUTPUT = Path("tramites-avaluos-data.js")


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalized_key(value: object) -> str:
    text = clean(value).upper()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def parse_date(value: object):
    text = clean(value)
    if not text:
        return None
    for pattern in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            parsed = datetime.strptime(text, pattern)
        except ValueError:
            continue
        if 2024 <= parsed.year <= 2030:
            return parsed
    return None


def iso_date(value: object) -> str:
    parsed = parse_date(value)
    return parsed.date().isoformat() if parsed else ""


def parse_days(value: object):
    text = clean(value)
    if not text:
        return None
    try:
        number = float(text.replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(number) or number < 0 or number > 730:
        return None
    return int(round(number))


def normalize_state(value: object) -> str:
    key = normalized_key(value)
    if key == "FINALIZADO":
        return "FINALIZADO"
    if key in {"EN PROCESO", "PROCESO"}:
        return "EN PROCESO"
    return "SIN ESTADO"


def normalize_result(value: object) -> str:
    key = normalized_key(value)
    if key in {"FAVORABLE", "FAVORTABLE", "FAVORBALE", "FAVOBORABLE", "SI"}:
        return "FAVORABLE"
    if re.fullmatch(r"NO\s*FAVORABLE", key):
        return "NO FAVORABLE"
    if key in {"EN PROCESO", "DIGITACION"}:
        return "EN REVISIÓN"
    return "SIN RESULTADO"


TECHNICIAN_ALIASES = {
    "MARCELO LOGROŃO": "LOGROÑO MARCELO",
    "LOGROŃO MARCELO": "LOGROÑO MARCELO",
    "JORGE SUAREZ": "SUAREZ JORGE",
}


def normalize_technician(value: object) -> str:
    text = clean(value).upper()
    return TECHNICIAN_ALIASES.get(text, text) or "SIN TÉCNICO"


def find_header(rows: list[list[str]]) -> int:
    for index, row in enumerate(rows):
        if row and clean(row[0]) == "No." and any("TRÁMITE" in clean(cell) for cell in row):
            return index
    raise ValueError("No se encontró la fila de encabezados de la matriz")


def case_key(row: dict[str, str], index: int, columns: dict[str, str]) -> str:
    egob = clean(row.get(columns["egob"]))
    soy = clean(row.get(columns["soy"]))
    if egob and soy:
        return f"E:{egob}|S:{soy}"
    if egob:
        return f"E:{egob}"
    if soy:
        return f"S:{soy}"
    return f"R:{index + 1}"


def event_score(row: dict[str, str], index: int, columns: dict[str, str]):
    dates = [
        parse_date(row.get(columns["reassigned"])),
        parse_date(row.get(columns["dispatch"])),
    ]
    valid_dates = [date for date in dates if date]
    latest = max(valid_dates) if valid_dates else datetime(1900, 1, 1)
    return latest, index


def numeric(value: object, default=0):
    text = clean(value).replace("%", "").replace(",", ".")
    if not text:
        return default
    try:
        number = float(text)
    except ValueError:
        return default
    return int(number) if number.is_integer() else number


def find_dashboard_row(rows: list[list[str]], required: set[str]) -> int:
    required_keys = {normalized_key(value) for value in required}
    for index, row in enumerate(rows):
        row_keys = {normalized_key(value) for value in row if clean(value)}
        if required_keys.issubset(row_keys):
            return index
    raise ValueError(f"No se encontró la tabla del Dashboard: {sorted(required)}")


def header_positions(row: list[str]) -> dict[str, int]:
    return {normalized_key(value): index for index, value in enumerate(row) if clean(value)}


def parse_institutional_dashboard(source: Path) -> dict:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    months = [
        "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
        "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
    ]

    type_header_index = find_dashboard_row(
        rows,
        {"TRÁMITE", "EN PROCESO", "FINALIZADO", "TOTAL", "T. PROMEDIO SUBPROCESO"},
    )
    type_positions = header_positions(rows[type_header_index])
    type_columns = {
        "name": type_positions[normalized_key("TRÁMITE")],
        "process": type_positions[normalized_key("EN PROCESO")],
        "finished": type_positions[normalized_key("FINALIZADO")],
        "total": type_positions[normalized_key("TOTAL")],
        "average": type_positions[normalized_key("T. PROMEDIO SUBPROCESO")],
        "progress": type_positions[normalized_key("GRADO DE AVANCE")],
    }
    month_columns = {month: type_positions[month] for month in months}

    types = []
    for row in rows[type_header_index + 1 :]:
        name = clean(row[type_columns["name"]] if len(row) > type_columns["name"] else "")
        if not name:
            break
        entry = {
            "name": name,
            "inProcess": numeric(row[type_columns["process"]]),
            "finished": numeric(row[type_columns["finished"]]),
            "total": numeric(row[type_columns["total"]]),
            "averageDays": numeric(row[type_columns["average"]], None),
            "progress": numeric(row[type_columns["progress"]], 0) / 100,
            "months": {
                month: numeric(row[column]) if len(row) > column else 0
                for month, column in month_columns.items()
            },
        }
        types.append(entry)

    area_header_index = find_dashboard_row(rows, {"JEFATURA", "CANTIDAD DE TRÁMITES"})
    area_positions = header_positions(rows[area_header_index])
    area_name_column = area_positions[normalized_key("JEFATURA")]
    area_total_column = area_positions[normalized_key("CANTIDAD DE TRÁMITES")]
    areas = []
    for row in rows[area_header_index + 1 :]:
        name = clean(row[area_name_column] if len(row) > area_name_column else "")
        if not name:
            break
        areas.append({"name": name, "total": numeric(row[area_total_column])})

    technician_header_index = find_dashboard_row(
        rows,
        {
            "FUNCIONARIO",
            "TOTAL TRÁMITES ASIGNADOS",
            "TRÁMITES ASIGNADOS EN PROCESO",
            "TRÁMITES ASIGNADOS FINALIZADOS",
        },
    )
    technician_positions = header_positions(rows[technician_header_index])
    technician_columns = {
        "name": technician_positions[normalized_key("FUNCIONARIO")],
        "total": technician_positions[normalized_key("TOTAL TRÁMITES ASIGNADOS")],
        "process": technician_positions[normalized_key("TRÁMITES ASIGNADOS EN PROCESO")],
        "finished": technician_positions[normalized_key("TRÁMITES ASIGNADOS FINALIZADOS")],
    }
    type_names = {normalized_key(entry["name"]): entry["name"] for entry in types}
    technician_type_columns = {
        type_names[key]: column
        for key, column in technician_positions.items()
        if key in type_names
    }
    technicians = []
    for row in rows[technician_header_index + 1 :]:
        name = clean(row[technician_columns["name"]] if len(row) > technician_columns["name"] else "")
        if not name:
            break
        technicians.append(
            {
                "name": name,
                "total": numeric(row[technician_columns["total"]]),
                "inProcess": numeric(row[technician_columns["process"]]),
                "finished": numeric(row[technician_columns["finished"]]),
                "types": {
                    type_name: numeric(row[column]) if len(row) > column else 0
                    for type_name, column in technician_type_columns.items()
                },
            }
        )

    monthly = []
    monthly_header_index = None
    for index, row in enumerate(rows[:-1]):
        row_keys = [normalized_key(value) for value in row]
        next_keys = [normalized_key(value) for value in rows[index + 1]]
        if all(month in row_keys for month in months) and next_keys.count("EN PROCESO") >= 12:
            monthly_header_index = index
            break
    if monthly_header_index is not None:
        month_header = rows[monthly_header_index]
        state_header = rows[monthly_header_index + 1]
        month_pairs = {}
        for column, value in enumerate(month_header):
            month = normalized_key(value)
            if month in months and column + 1 < len(state_header):
                month_pairs[month] = (column, column + 1)
        monthly_rows = []
        known_types = {normalized_key(entry["name"]) for entry in types}
        for row in rows[monthly_header_index + 2 :]:
            row_keys = {normalized_key(value) for value in row if clean(value)}
            if row_keys.intersection(known_types):
                monthly_rows.append(row)
            elif monthly_rows:
                break
        for month in months:
            process_column, finished_column = month_pairs[month]
            in_process = sum(numeric(row[process_column]) if len(row) > process_column else 0 for row in monthly_rows)
            finished = sum(numeric(row[finished_column]) if len(row) > finished_column else 0 for row in monthly_rows)
            monthly.append({"month": month, "inProcess": in_process, "finished": finished, "total": in_process + finished})
    else:
        for month in months:
            total = sum(entry["months"][month] for entry in types)
            monthly.append({"month": month, "inProcess": 0, "finished": total, "total": total})

    annual_in_process = sum(entry["inProcess"] for entry in types)
    annual_finished = sum(entry["finished"] for entry in types)
    annual_total = sum(entry["total"] for entry in types)
    return {
        "sourceSheet": "DASHBOARD",
        "exportedAt": datetime.fromtimestamp(source.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
        "annual": {
            "total": annual_total,
            "inProcess": annual_in_process,
            "finished": annual_finished,
            "completion": annual_finished / annual_total if annual_total else 0,
        },
        "monthly": monthly,
        "types": types,
        "areas": areas,
        "technicians": technicians,
    }


def build_bundle(source: Path, dashboard_source: Path | None = None) -> dict:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        raw_rows = list(csv.reader(handle))

    header_index = find_header(raw_rows)
    header = raw_rows[header_index]
    dict_rows = [dict(zip(header, row)) for row in raw_rows[header_index + 1 :]]

    columns = {
        "egob": header[1],
        "soy": header[2],
        "area": header[4],
        "technician": header[5],
        "reassigned": header[6],
        "type": header[7],
        "result": header[10],
        "dispatch": header[12],
        "state": header[13],
        "days": header[14],
    }

    valid_rows = []
    for index, row in enumerate(dict_rows):
        identifiers = [
            clean(row.get(columns["egob"])),
            clean(row.get(columns["soy"])),
            clean(row.get(columns["type"])),
            clean(row.get(columns["technician"])),
        ]
        if any(identifiers):
            valid_rows.append((index, row))

    groups: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for index, row in valid_rows:
        groups[case_key(row, index, columns)].append((index, row))

    records = []
    invalid_days = 0
    for key, movements in groups.items():
        current_index, current = max(
            movements,
            key=lambda item: event_score(item[1], item[0], columns),
        )
        days = parse_days(current.get(columns["days"]))
        if clean(current.get(columns["days"])) and days is None:
            invalid_days += 1

        egob = clean(current.get(columns["egob"]))
        soy = clean(current.get(columns["soy"]))
        record = {
            "id": key,
            "egob": egob,
            "soy": soy,
            "tipo": clean(current.get(columns["type"])).upper() or "SIN TIPO",
            "area": clean(current.get(columns["area"])).upper() or "SIN ÁREA",
            "tecnico": normalize_technician(current.get(columns["technician"])),
            "reasignacion": iso_date(current.get(columns["reassigned"])),
            "despacho": iso_date(current.get(columns["dispatch"])),
            "estado": normalize_state(current.get(columns["state"])),
            "resultado": normalize_result(current.get(columns["result"])),
            "dias": days,
            "movimientos": len(movements),
            "filaOrigen": current_index + header_index + 2,
        }
        records.append(record)

    records.sort(
        key=lambda record: (
            record["reasignacion"] or record["despacho"],
            record["egob"],
            record["soy"],
        ),
        reverse=True,
    )

    state_counts = Counter(record["estado"] for record in records)
    result_counts = Counter(record["resultado"] for record in records)
    area_counts = Counter(record["area"] for record in records)
    type_counts = Counter(record["tipo"] for record in records)
    technician_counts = Counter(record["tecnico"] for record in records)

    source_modified = datetime.fromtimestamp(source.stat().st_mtime).astimezone()
    bundle = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {
            "workbook": "MATRIZ DE CONTROL DIRECCIÓN DE AVALUOS Y CATASTROS 2026.xlsx",
            "sheet": "MATRIZ DE CONTROL INTERNO",
            "exportedAt": source_modified.isoformat(timespec="seconds"),
            "privacy": "No incluye nombres de solicitantes, notarías ni observaciones.",
        },
        "quality": {
            "sourceRows": len(dict_rows),
            "usableRows": len(valid_rows),
            "excludedBlankRows": len(dict_rows) - len(valid_rows),
            "uniqueCases": len(records),
            "casesWithMultipleMovements": sum(len(items) > 1 for items in groups.values()),
            "invalidCurrentDurations": invalid_days,
        },
        "summary": {
            "states": dict(state_counts),
            "results": dict(result_counts),
            "areas": dict(area_counts),
            "types": dict(type_counts),
            "technicians": dict(technician_counts),
        },
        "institutionalDashboard": (
            parse_institutional_dashboard(dashboard_source)
            if dashboard_source and dashboard_source.exists()
            else None
        ),
        "records": records,
    }
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dashboard-source", type=Path, default=DEFAULT_DASHBOARD_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    bundle = build_bundle(args.source, args.dashboard_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    args.output.write_text(
        "window.TRAMITES_AVALUOS_DATA=" + payload + ";\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "records": len(bundle["records"]),
                "states": bundle["summary"]["states"],
                "quality": bundle["quality"],
                "institutionalAnnual": bundle["institutionalDashboard"]["annual"] if bundle["institutionalDashboard"] else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
