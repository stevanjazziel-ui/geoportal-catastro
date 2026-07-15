#!/usr/bin/env python
from __future__ import annotations

import argparse
import getpass
import html as html_lib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from datetime import date, datetime
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path

import pandas as pd


DEFAULT_ORIGIN = "https://egobedoc.gadmriobamba.gob.ec:8081/my/passig_citizen"
DEFAULT_OUTPUT = "tramites-iprus-data.js"

HEADER_VARIANTS = {
    "estado": "estado",
    "nro tramite": "nroTramite",
    "nro. tramite": "nroTramite",
    "nro de tramite": "nroTramite",
    "nro. de tramite": "nroTramite",
    "nro del tramite": "nroTramite",
    "numero de tramite": "nroTramite",
    "codigo": "codigo",
    "tramite": "tramite",
    "nro proceso": "tramite",
    "nro. proceso": "tramite",
    "tipo de tramite": "tipoTramite",
    "tipo": "tipoTramite",
    "solicitante": "solicitante",
    "asunto": "asunto",
    "asunto:": "asunto",
    "responsable": "responsable",
    "responsable actual": "responsableActual",
    "reasignado por": "reasignadoPor",
    "cargo responsable": "cargoResponsable",
    "asignado interno": "asignadoInterno",
    "ingresado por": "ingresadoPor",
    "remitente": "remitente",
    "fecha limite": "fechaLimite",
    "tiempo restante": "tiempoRestante",
    "dias restantes": "diasRestantes",
    "prioridad": "prioridad",
    "fecha de ingreso": "fechaIngreso",
    "asignado el": "fechaIngreso",
    "expediente": "expediente",
    "observaciones": "observaciones",
}

TRAMITE_NUMBER_RE = re.compile(r"tramite\s*(?:nro|nro\.|nro\s+de|nro\s+del|no|n)?[.\sº°]*\s*(\d+)", re.IGNORECASE)
TRAMITE_CODE_RE = re.compile(r"\b[A-Z]{3,}(?:-+[A-Z0-9]+){2,}\b")
SPACES_RE = re.compile(r"\s+")
STANDALONE_ID_RE = re.compile(r"\b(\d{6,8})\b")
PAREN_ROLE_RE = re.compile(r"^(.*?)\s*\((.+)\)\s*$")
JOURNALS_CONTAINER_RE = re.compile(r'<div id="journals-container".*?</div>\s*<div id="journals-loader"', re.IGNORECASE | re.DOTALL)
JOURNAL_SPLIT_RE = re.compile(r'(?=<div id="change-\d+")')

EGOB_OUTCOME_NEGATIVE_RULES = (
    ("no_favorable", ("no favorable", "no es favorable", "tramite no favorable", "trámite no favorable")),
    ("observaciones_legales", ("tramite con observaciones legales", "trámite con observaciones legales")),
    ("informe_con_observaciones", ("informe con observaciones",)),
    (
        "subsanacion",
        (
            "se concede un plazo",
            "subsanacion",
            "subsanación",
            "subsanacion de las observaciones",
            "observaciones:",
            "debe corregir",
            "debera corregir",
            "debera realizar la correccion",
            "deberá realizar la corrección",
            "corregir",
            "correccion",
            "corrección",
            "regularizacion",
            "regularización",
            "se notifica",
        ),
    ),
)

EGOB_OUTCOME_POSITIVE_RULES = (
    (
        "tramite_iprus_favorable",
        (
            "tramite iprus favorable",
            "trámite iprus favorable",
            "se reasigna tramite iprus favorable",
            "se reasigna trámite iprus favorable",
            "reasigna tramite iprus favorable",
            "reasigna trámite iprus favorable",
        ),
    ),
)


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.lower().strip()
    text = SPACES_RE.sub(" ", text.replace("\r", " ").replace("\n", " "))
    return text


def normalize_header(value: object) -> str:
    text = normalize_text(value)
    return (
        text.replace("n.º", "nro")
        .replace("n°", "nro")
        .replace("no.", "nro")
        .replace("no ", "nro ")
    )


def flatten_columns(columns: object) -> list[str]:
    flattened: list[str] = []
    for column in list(columns):
        if isinstance(column, tuple):
            parts = [str(part).strip() for part in column if str(part).strip() and str(part).strip().lower() != "nan"]
            flattened.append(" ".join(parts))
        else:
            flattened.append(str(column).strip())
    return flattened


def clean_spaces(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ").replace("–", "-").replace("—", "-")
    return SPACES_RE.sub(" ", text.replace("\r", " ").replace("\n", " ")).strip()


def normalize_multiline_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ").replace("–", "-").replace("—", "-")
    parts = [SPACES_RE.sub(" ", chunk).strip() for chunk in re.split(r"[\r\n]+", text)]
    return "\n".join(part for part in parts if part)


def split_cell_lines(value: object) -> list[str]:
    if value is None:
        return []

    raw_text = normalize_multiline_text(value)
    lines = [chunk.strip() for chunk in re.split(r"[\r\n]+", raw_text) if chunk.strip()]
    if lines:
        return lines

    text = clean_spaces(raw_text)
    return [text] if text else []


class TableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[tuple[str, bool]]]] = []
        self._current_table: list[list[tuple[str, bool]]] | None = None
        self._current_row: list[tuple[str, bool]] | None = None
        self._current_cell_parts: list[str] | None = None
        self._current_cell_is_header = False
        self._table_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._current_table = []
            return

        if self._table_depth != 1:
            return

        if tag == "tr":
            self._current_row = []
            return

        if tag in {"th", "td"}:
            self._current_cell_parts = []
            self._current_cell_is_header = tag == "th"
            return

        if tag == "br" and self._current_cell_parts is not None:
            self._current_cell_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._table_depth == 1 and self._current_cell_parts is not None:
            self._current_cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            if self._table_depth == 1 and self._current_table is not None:
                self.tables.append(self._current_table)
                self._current_table = None
            self._table_depth = max(0, self._table_depth - 1)
            return

        if self._table_depth != 1:
            return

        if tag in {"th", "td"} and self._current_row is not None and self._current_cell_parts is not None:
            text = "".join(self._current_cell_parts).strip()
            self._current_row.append((text, self._current_cell_is_header))
            self._current_cell_parts = None
            self._current_cell_is_header = False
            return

        if tag == "tr" and self._current_table is not None and self._current_row is not None:
            if self._current_row:
                self._current_table.append(self._current_row)
            self._current_row = None


def parse_tables_with_builtin_parser(html: str) -> list[pd.DataFrame]:
    parser = TableHtmlParser()
    parser.feed(html)

    frames: list[pd.DataFrame] = []
    for raw_table in parser.tables:
        if not raw_table:
            continue

        header_index = 0
        for index, row in enumerate(raw_table):
            if any(is_header for _, is_header in row):
                header_index = index
                break

        header_row = [clean_spaces(text) or f"columna_{index + 1}" for index, (text, _) in enumerate(raw_table[header_index])]
        data_rows = raw_table[header_index + 1 :]
        normalized_rows: list[list[str]] = []
        for row in data_rows:
            cells = [normalize_multiline_text(text) for text, _ in row]
            if len(cells) < len(header_row):
                cells.extend([""] * (len(header_row) - len(cells)))
            normalized_rows.append(cells[: len(header_row)])

        frames.append(pd.DataFrame(normalized_rows, columns=header_row))

    return frames


def coerce_value(field: str, value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.isoformat(timespec="seconds")

    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")

    if isinstance(value, date):
        return value.isoformat()

    if field in {"fechaLimite", "fechaIngreso"} and isinstance(value, str):
        return to_iso_like(value)

    if field == "diasRestantes" and isinstance(value, str):
        match = re.search(r"-?\d+", normalize_text(value))
        if match:
            return int(match.group(0))

    if field == "nroTramite" and isinstance(value, str):
        match = re.search(r"\d+", value.replace(",", ""))
        if match:
            return int(match.group(0))

    if field in {"nroTramite", "diasRestantes"}:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if float(value).is_integer():
                return int(value)
            return float(value)

    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return int(value)
        return value

    return normalize_multiline_text(value) if isinstance(value, str) else value


def score_table(frame: pd.DataFrame) -> tuple[int, dict[str, str]]:
    mapping: dict[str, str] = {}
    score = 0
    for column in flatten_columns(frame.columns):
        normalized = normalize_header(column)
        target = HEADER_VARIANTS.get(normalized)
        if not target:
            for candidate, candidate_target in HEADER_VARIANTS.items():
                if normalized.startswith(candidate + " ") or normalized.endswith(" " + candidate):
                    target = candidate_target
                    break
        if target:
            mapping[column] = target
            score += 1
    return score, mapping


def choose_table(frames: list[pd.DataFrame], forced_index: int | None) -> tuple[pd.DataFrame, dict[str, str], int]:
    if forced_index is not None:
        if forced_index < 0 or forced_index >= len(frames):
            raise IndexError(f"table-index fuera de rango: {forced_index}. Se detectaron {len(frames)} tablas.")
        frame = frames[forced_index]
        _, mapping = score_table(frame)
        return frame, mapping, forced_index

    best_score = -1
    best_mapping: dict[str, str] = {}
    best_frame: pd.DataFrame | None = None
    best_index = -1

    for index, frame in enumerate(frames):
        score, mapping = score_table(frame)
        if score > best_score:
            best_score = score
            best_mapping = mapping
            best_frame = frame
            best_index = index

    if best_frame is None or best_score < 5:
        raise ValueError(
            "No se encontro una tabla con suficiente coincidencia de columnas. "
            f"Mejor score detectado: {best_score}."
        )

    return best_frame, best_mapping, best_index


def to_iso_like(value: str) -> str:
    text = clean_spaces(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", text):
        return text.replace(" ", "T", 1) + ":00"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", text):
        return text.replace(" ", "T", 1)
    return text


def classify_priority(days: int | None) -> str:
    if days is None:
        return "Sin fecha"
    if days < 0:
        return "Vencido"
    if days == 0:
        return "Vence hoy"
    if days <= 1:
        return "Crítico"
    if days <= 3:
        return "Urgente"
    return "Normal"


def parse_due_date_field(value: object) -> dict[str, object]:
    text = clean_spaces(value)
    if not text:
        return {}

    lines = split_cell_lines(value)
    date_match = re.search(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?", text)
    date_value = to_iso_like(date_match.group(0)) if date_match else (to_iso_like(lines[0]) if lines else to_iso_like(text))
    remaining_lines = lines[1:] if len(lines) > 1 else []
    remaining_text = clean_spaces(" ".join(remaining_lines))
    if not remaining_text and date_match:
        remaining_text = clean_spaces(text.replace(date_match.group(0), "", 1))

    days = None
    if remaining_text:
        days_match = re.search(r"(-?\d+)\s*d", normalize_text(remaining_text))
        if days_match:
            days = int(days_match.group(1))
    if days is None:
        days_match = re.search(r"(-?\d+)\s*d", normalize_text(text))
        if days_match:
            days = int(days_match.group(1))

    result: dict[str, object] = {"fechaLimite": date_value}
    if remaining_text:
        result["tiempoRestante"] = remaining_text
    if days is not None:
        result["diasRestantes"] = days
        result["prioridad"] = classify_priority(days)
    return result


def parse_subject_field(value: object) -> dict[str, object]:
    text = clean_spaces(value)
    if not text:
        return {}

    result: dict[str, object] = {"asunto": text}
    if " - " in text:
        left, right = text.rsplit(" - ", 1)
        result["solicitante"] = clean_spaces(left)
        if "IPRUS" in right.upper():
            result["tipoTramite"] = clean_spaces(right)
    else:
        result["solicitante"] = text
    return result


def extract_session_context(html: str, username_hint: str = "") -> dict[str, str]:
    def extract_one(pattern: str) -> str:
        match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return clean_spaces(html_lib.unescape(match.group(1)))

    username = extract_one(r'<div id="loggedas">\s*<a[^>]*>(.*?)</a>')
    display_name = extract_one(r'<div class="dropdown-user-name">\s*(.*?)\s*</div>')
    email_matches = re.findall(r'<div class="dropdown-user-email"[^>]*>\s*(.*?)\s*</div>', html, flags=re.IGNORECASE | re.DOTALL)
    cleaned = [clean_spaces(html_lib.unescape(item)) for item in email_matches if clean_spaces(html_lib.unescape(item))]

    return {
        "username": username or clean_spaces(username_hint),
        "display_name": display_name,
        "email": cleaned[0] if cleaned else "",
        "department": cleaned[1] if len(cleaned) > 1 else "",
    }


def html_fragment_to_text(fragment: str) -> str:
    text = re.sub(r"(?is)<br\s*/?>", "\n", fragment)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return clean_spaces(text)


def extract_journal_entries(issue_html: str) -> list[dict[str, object]]:
    container_match = JOURNALS_CONTAINER_RE.search(issue_html)
    if not container_match:
        return []

    container = container_match.group(0)
    parts = JOURNAL_SPLIT_RE.split(container)
    entries: list[dict[str, object]] = []

    for part in parts[1:]:
        entry_id_match = re.search(r'<div id="change-(\d+)"', part)
        if not entry_id_match:
            continue

        author_match = re.search(
            r'<span class="journal-entry__author">\s*(.*?)\s*(?:<small>\((.*?)\)</small>)?\s*</span>',
            part,
            flags=re.IGNORECASE | re.DOTALL,
        )
        time_match = re.search(
            r'<span class="journal-entry__time">\s*([^<]+)',
            part,
            flags=re.IGNORECASE | re.DOTALL,
        )
        note_match = re.search(
            r'<div class="journal-entry__note">\s*<strong>Nota:</strong>\s*(.*?)\s*</div>',
            part,
            flags=re.IGNORECASE | re.DOTALL,
        )
        index_match = re.search(
            r'<span class="journal-entry__index">#(\d+)</span>',
            part,
            flags=re.IGNORECASE | re.DOTALL,
        )
        detail_matches = re.findall(r"<li>(.*?)</li>", part, flags=re.IGNORECASE | re.DOTALL)

        entry_type = "Registro"
        if 'class="reassignment"' in part:
            entry_type = "Reasignación"
        elif 'class="archived"' in part:
            entry_type = "Archivado"

        entries.append(
            {
                "journalId": entry_id_match.group(1),
                "index": int(index_match.group(1)) if index_match else None,
                "entryType": entry_type,
                "author": html_fragment_to_text(author_match.group(1)) if author_match else "",
                "authorRole": html_fragment_to_text(author_match.group(2)) if author_match and author_match.group(2) else "",
                "timestamp": clean_spaces(time_match.group(1)) if time_match else "",
                "note": html_fragment_to_text(note_match.group(1)) if note_match else "",
                "details": [html_fragment_to_text(item) for item in detail_matches if html_fragment_to_text(item)],
            }
        )

    return entries


def classify_egob_outcome(
    note: str,
    details: list[str] | None = None,
    entry_type: str | None = None,
) -> tuple[str | None, str | None]:
    parts = [note]
    if details:
        parts.extend(details)
    normalized = normalize_text(" ".join(part for part in parts if part))
    normalized_entry_type = normalize_text(entry_type or "")
    if not normalized:
        return None, None

    for rule, patterns in EGOB_OUTCOME_NEGATIVE_RULES:
        if any(pattern in normalized for pattern in patterns):
            return "NO FAVORABLE", rule

    if normalized_entry_type.startswith("reasignacion"):
        for rule, patterns in EGOB_OUTCOME_POSITIVE_RULES:
            if any(pattern in normalized for pattern in patterns):
                return "FAVORABLE", rule

    return None, None


def summarize_issue_tracking(issue_id: str, issue_html: str) -> dict[str, object]:
    entries = extract_journal_entries(issue_html)
    relevant_entries: list[dict[str, object]] = []

    for entry in entries:
        outcome, rule = classify_egob_outcome(
            str(entry.get("note") or ""),
            [str(item) for item in entry.get("details") or []],
            str(entry.get("entryType") or ""),
        )
        if outcome:
            relevant_entries.append(
                {
                    "journalId": entry.get("journalId"),
                    "entryType": entry.get("entryType"),
                    "timestamp": entry.get("timestamp"),
                    "author": entry.get("author"),
                    "authorRole": entry.get("authorRole"),
                    "note": entry.get("note"),
                    "outcome": outcome,
                    "rule": rule,
                }
            )

    latest_reassignment = next(
        (
            entry
            for entry in reversed(entries)
            if entry.get("entryType") == "Reasignación" and clean_spaces(entry.get("note"))
        ),
        None,
    )
    latest_relevant = relevant_entries[-1] if relevant_entries else None

    return {
        "issueId": str(issue_id),
        "egobOutcome": latest_relevant.get("outcome") if latest_relevant else "EN REVISIÓN",
        "egobOutcomeRule": latest_relevant.get("rule") if latest_relevant else "",
        "egobOutcomeNote": latest_relevant.get("note") if latest_relevant else "",
        "egobOutcomeAt": latest_relevant.get("timestamp") if latest_relevant else "",
        "egobOutcomeAuthor": latest_relevant.get("author") if latest_relevant else "",
        "egobOutcomeAuthorRole": latest_relevant.get("authorRole") if latest_relevant else "",
        "egobOutcomeEntryType": latest_relevant.get("entryType") if latest_relevant else "",
        "egobLatestReassignmentNote": latest_reassignment.get("note") if latest_reassignment else "",
        "egobLatestReassignmentAt": latest_reassignment.get("timestamp") if latest_reassignment else "",
        "egobLatestReassignmentAuthor": latest_reassignment.get("author") if latest_reassignment else "",
        "egobJournalCount": len(entries),
        "egobRelevantNotes": relevant_entries[-5:],
    }


def get_issue_tracking_key(record: dict[str, object]) -> str:
    issue_id = record.get("issueId") or record.get("nroTramite")
    if issue_id is None:
        return ""
    return clean_spaces(issue_id)


def extract_issue_tracking_fields(record: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in record.items()
        if key.startswith("egob") or key in {"issueId"}
    }


def build_issue_tracking_cache(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    cache: dict[str, dict[str, object]] = {}
    for collection_name in ("records", "historyRecords", "history"):
        for record in payload.get(collection_name) or []:
            key = get_issue_tracking_key(record)
            if not key:
                continue
            tracking = extract_issue_tracking_fields(record)
            if tracking:
                cache[key] = tracking
    return cache


def apply_issue_tracking_cache(records: list[dict[str, object]], cache: dict[str, dict[str, object]]) -> None:
    for record in records:
        key = get_issue_tracking_key(record)
        if not key:
            continue
        tracking = cache.get(key)
        if tracking:
            record.update(tracking)


def parse_tramite_field(value: object) -> dict[str, object]:
    text = clean_spaces(value)
    if not text:
        return {}

    lines = split_cell_lines(value)
    code_match = TRAMITE_CODE_RE.search(text.upper())
    code = code_match.group(0) if code_match else None
    if not code:
        code = next((line for line in lines if line.upper().count("-") >= 3 and "IPRUS" in line.upper()), None)

    number = None
    for line in lines or [text]:
        number_match = TRAMITE_NUMBER_RE.search(normalize_text(line))
        if number_match:
            number = int(number_match.group(1))
            break
        fallback_match = STANDALONE_ID_RE.search(line)
        if fallback_match:
            number = int(fallback_match.group(1))
            break

    remaining = text
    if code:
        remaining = remaining.replace(code, "", 1).strip()
    remaining = re.sub(r"(?i)tramite\s*(?:nro|nro\.|nro\s+de|nro\s+del|no|n)?[.\sº°]*\s*\d+\b", "", remaining)
    remaining = clean_spaces(remaining)

    tipo = None
    remaining_lines = []
    for line in lines:
        if code and clean_spaces(line).upper() == code.upper():
            continue
        if TRAMITE_NUMBER_RE.search(normalize_text(line)):
            continue
        remaining_lines.append(clean_spaces(line))

    if remaining_lines:
        tipo = clean_spaces(" ".join(remaining_lines))
    elif remaining and "IPRUS" in remaining.upper():
        tipo = remaining

    result: dict[str, object] = {"tramite": text}
    if code:
        result["codigo"] = code
    if number is not None:
        result["nroTramite"] = number
        result["issueId"] = str(number)
    if tipo:
        result["tipoTramite"] = tipo
    return result


def parse_solicitante_field(value: object) -> dict[str, object]:
    text = clean_spaces(value)
    if not text:
        return {}

    lines = split_cell_lines(value)
    result: dict[str, object] = {"solicitante": lines[0] if lines else text}

    ingresado_match = re.search(r"(?i)ingresado por\s*(.+)$", text)
    if ingresado_match:
        result["ingresadoPor"] = clean_spaces(ingresado_match.group(1))
    elif len(lines) > 1:
        result["ingresadoPor"] = clean_spaces(" ".join(lines[1:]))

    return result


def parse_responsable_field(value: object) -> dict[str, object]:
    text = clean_spaces(value)
    if not text:
        return {}

    paren_match = PAREN_ROLE_RE.match(text)
    if paren_match:
        return {
            "responsable": clean_spaces(paren_match.group(1)),
            "cargoResponsable": clean_spaces(paren_match.group(2)),
        }

    lines = split_cell_lines(value)
    result: dict[str, object] = {"responsable": lines[0] if lines else text}

    if len(lines) > 1:
        result["cargoResponsable"] = clean_spaces(" ".join(lines[1:]))

    return result


def enrich_record(item: dict[str, object], session_context: dict[str, str] | None = None) -> dict[str, object]:
    enriched = dict(item)

    if enriched.get("tramite"):
        enriched.update(parse_tramite_field(enriched.get("tramite")))

    if enriched.get("asunto"):
        enriched.update(parse_subject_field(enriched.get("asunto")))

    if enriched.get("solicitante"):
        enriched.update(parse_solicitante_field(enriched.get("solicitante")))

    if enriched.get("responsableActual"):
        enriched.update(parse_responsable_field(enriched.get("responsableActual")))
    elif enriched.get("reasignadoPor"):
        reassigned_info = parse_responsable_field(enriched.get("reasignadoPor"))
        if reassigned_info.get("responsable"):
            enriched["reasignadoPor"] = reassigned_info["responsable"]
        if reassigned_info.get("cargoResponsable"):
            enriched["reasignadoPorCargo"] = reassigned_info["cargoResponsable"]
    elif enriched.get("responsable") and not enriched.get("cargoResponsable"):
        enriched.update(parse_responsable_field(enriched.get("responsable")))

    if enriched.get("remitente") and not enriched.get("ingresadoPor"):
        enriched["ingresadoPor"] = clean_spaces(enriched.get("remitente"))

    if enriched.get("fechaLimite"):
        enriched.update(parse_due_date_field(enriched.get("fechaLimite")))

    if session_context:
        if not clean_spaces(enriched.get("responsable")):
            enriched["responsable"] = session_context.get("display_name") or session_context.get("username") or ""
        if not clean_spaces(enriched.get("cargoResponsable")) and session_context.get("department"):
            enriched["cargoResponsable"] = session_context["department"]
        if not clean_spaces(enriched.get("asignadoInterno")) and session_context.get("username"):
            enriched["asignadoInterno"] = session_context["username"].lower()

    if enriched.get("asignadoInterno"):
        enriched["asignadoInterno"] = clean_spaces(enriched.get("asignadoInterno"))

    return enriched


def summarize_records(records: list[dict[str, object]]) -> dict[str, dict[str, int] | int]:
    priorities: dict[str, int] = {}
    states: dict[str, int] = {}
    responsibles: dict[str, int] = {}

    for item in records:
        prioridad = str(item.get("prioridad") or "Sin prioridad")
        estado = str(item.get("estado") or "Sin estado")
        responsable = str(item.get("responsable") or "Sin responsable")
        priorities[prioridad] = priorities.get(prioridad, 0) + 1
        states[estado] = states.get(estado, 0) + 1
        responsibles[responsable] = responsibles.get(responsable, 0) + 1

    return {
        "total": len(records),
        "priorities": priorities,
        "states": states,
        "responsibles": responsibles,
    }


def sort_history_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    def history_sort_key(item: dict[str, object]) -> tuple[str, str]:
        return (
            str(item.get("historyArchivedAt") or item.get("generatedAt") or ""),
            str(item.get("codigo") or item.get("id") or ""),
        )

    return sorted(records, key=history_sort_key, reverse=True)


def load_existing_payload(output_path: Path) -> dict[str, object]:
    if not output_path.exists():
        return {}

    try:
        text = output_path.read_text(encoding="utf-8")
        prefix = "window.TRAMITES_IPRUS_DATA = "
        if not text.startswith(prefix):
            return {}
        raw_json = text[len(prefix):].strip()
        if raw_json.endswith(";"):
            raw_json = raw_json[:-1].strip()
        return json.loads(raw_json)
    except (OSError, json.JSONDecodeError):
        return {}


def merge_history(
    current_records: list[dict[str, object]],
    previous_payload: dict[str, object],
    *,
    archived_at: str,
) -> list[dict[str, object]]:
    current_ids = {str(record.get("id")) for record in current_records if record.get("id")}
    previous_active = previous_payload.get("records") or []
    previous_history = previous_payload.get("historyRecords") or previous_payload.get("history") or []

    history_by_id: dict[str, dict[str, object]] = {}

    for record in previous_history:
        record_id = str(record.get("id") or "").strip()
        if not record_id or record_id in current_ids:
            continue
        history_by_id[record_id] = dict(record)

    previous_seen_at = previous_payload.get("generatedAt") or previous_payload.get("sourceDate") or archived_at
    for record in previous_active:
        record_id = str(record.get("id") or "").strip()
        if not record_id or record_id in current_ids:
            continue

        archived_record = dict(record)
        archived_record.setdefault("historyArchivedAt", archived_at)
        archived_record["historyLastSeenAt"] = previous_seen_at
        archived_record["historyStatus"] = "Historico"

        existing = history_by_id.get(record_id)
        if existing:
            archived_record["historyArchivedAt"] = existing.get("historyArchivedAt") or archived_record["historyArchivedAt"]
            archived_record["historyLastSeenAt"] = previous_seen_at
            archived_record["historyStatus"] = existing.get("historyStatus") or archived_record["historyStatus"]
        history_by_id[record_id] = archived_record

    return sort_history_records(list(history_by_id.values()))


def create_payload(
    records: list[dict[str, object]],
    *,
    source_file: str,
    source_path: str,
    source_note: str,
    history_records: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    today = date.today().isoformat()
    history_records = history_records or []
    return {
        "title": "CONTROL DE TRAMITES IPRUS FUERA DE ZONA PATRIMONIAL",
        "sourceFile": source_file,
        "sourcePath": source_path,
        "sourceNote": source_note,
        "sourceDate": today,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "records": records,
        "summary": summarize_records(records),
        "historyRecords": history_records,
        "historySummary": summarize_records(history_records),
    }


def write_js_module(payload: dict[str, object], output_path: Path) -> None:
    content = "window.TRAMITES_IPRUS_DATA = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def parse_html_tables(
    html: str,
    table_index: int | None,
    session_context: dict[str, str] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    try:
        frames = pd.read_html(StringIO(html))
    except ImportError:
        frames = parse_tables_with_builtin_parser(html)
    except ValueError as error:
        frames = parse_tables_with_builtin_parser(html)
        if not frames:
            raise ValueError(
                "El HTML autenticado no contiene tablas legibles. "
                "Puede ser una pagina de login fallida o una bandeja cargada por JavaScript."
            ) from error

    if not frames:
        raise ValueError(
            "No se detectaron tablas utilizables en el HTML autenticado. "
            "Puede ser necesario inspeccionar llamadas XHR o endpoints internos."
        )

    frame, mapping, selected_index = choose_table(frames, table_index)
    frame = frame.copy()
    frame.columns = flatten_columns(frame.columns)

    records: list[dict[str, object]] = []
    for row_index, row in frame.iterrows():
        item: dict[str, object] = {}
        for column, target_field in mapping.items():
            item[target_field] = coerce_value(target_field, row.get(column))

        item = enrich_record(item, session_context=session_context)
        if not any(value not in (None, "") for value in item.values()):
            continue

        item["sourceRow"] = int(row_index) + 1
        item["id"] = item.get("codigo") or str(item.get("nroTramite") or (row_index + 1))
        records.append(item)

    meta = {
        "tableCount": len(frames),
        "selectedTableIndex": selected_index,
        "selectedColumns": list(mapping.keys()),
        "mappedFields": mapping,
    }
    return records, meta


def resolve_credentials(args: argparse.Namespace) -> tuple[str, str]:
    username = (args.username or os.getenv("EGOBEDOC_USERNAME") or "").strip()
    password = args.password or os.getenv("EGOBEDOC_PASSWORD") or ""

    if args.html_source:
        return username, password

    if not username:
        try:
            username = input("Usuario CAS: ").strip()
        except EOFError:
            username = ""

    if not password:
        try:
            password = getpass.getpass("Clave CAS: ")
        except EOFError:
            password = ""

    return username, password


def load_connect_module():
    cache = getattr(load_connect_module, "_cache", None)
    if cache is not None:
        return cache

    module_path = Path(__file__).resolve().with_name("connect-egobedoc-cas.py")
    spec = importlib.util.spec_from_file_location("egobedoc_cas_runtime", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("No se pudo cargar el conector CAS local.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    load_connect_module._cache = module
    return module


def fetch_authenticated_html(
    args: argparse.Namespace,
    username: str,
    password: str,
    temp_dir: str,
) -> tuple[str, dict[str, object], object]:
    if not username or not password:
        raise RuntimeError(
            "Faltan credenciales CAS. Ejecuta el script con --username/--password, variables de entorno, o responde al prompt."
        )

    connect_module = load_connect_module()
    client = connect_module.EgoBedocCasClient(verify=not args.insecure)
    response = client.login(args.origin, username, password)
    if args.path:
        response = client.session.get(
            connect_module.urljoin(args.origin, args.path),
            allow_redirects=True,
            timeout=client.timeout,
        )
    if "/cas/login" in response.url.lower():
        raise RuntimeError("CAS no devolvio una sesion autenticada.")

    info = connect_module.summarize_response(response, args.origin, client.session)
    html_path = Path(temp_dir) / "passig_citizen.html"
    html = response.text

    if args.save_html:
        save_path = Path(args.save_html)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(html, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")

    return html, info, client


def fetch_issue_detail_html(
    args: argparse.Namespace,
    client: object,
    issue_id: str,
    temp_dir: str,
) -> str:
    issue_html_path = Path(temp_dir) / f"issue-{issue_id}.html"
    response = client.session.get(
        f"{args.origin.rsplit('/my/', 1)[0]}/issues/{issue_id}",
        allow_redirects=True,
        timeout=client.timeout,
    )
    if "/cas/login" in response.url.lower():
        raise RuntimeError(f"La sesion expiro mientras se consultaba el tramite {issue_id}.")
    issue_html_path.write_text(response.text, encoding="utf-8")
    return response.text


def enrich_records_with_issue_tracking(
    records: list[dict[str, object]],
    args: argparse.Namespace,
    *,
    client: object | None,
    temp_dir: str | None,
    cache: dict[str, dict[str, object]],
    fetch_missing_only: bool,
) -> dict[str, int]:
    apply_issue_tracking_cache(records, cache)
    stats = {"fetched": 0, "reused": 0, "failed": 0}

    if not client or not temp_dir or args.skip_issue_details:
        return stats

    for record in records:
        issue_id = get_issue_tracking_key(record)
        if not issue_id:
            continue

        if fetch_missing_only and record.get("egobOutcome") and record.get("egobLatestReassignmentNote"):
            stats["reused"] += 1
            continue

        try:
            issue_html = fetch_issue_detail_html(args, client, issue_id, temp_dir)
            tracking = summarize_issue_tracking(issue_id, issue_html)
            record.pop("egobSyncError", None)
            record.update(tracking)
            cache[issue_id] = extract_issue_tracking_fields(record)
            stats["fetched"] += 1
        except Exception as error:  # noqa: BLE001 - preferimos no abortar toda la sincronizacion por un tramite
            record["egobSyncError"] = clean_spaces(error)
            if issue_id in cache:
                record.update(cache[issue_id])
                stats["reused"] += 1
            else:
                stats["failed"] += 1

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sincroniza la bandeja passig_citizen de eGOB/e-Bedoc y actualiza tramites-iprus-data.js."
    )
    parser.add_argument("--origin", default=DEFAULT_ORIGIN, help="Ruta protegida de origen.")
    parser.add_argument("--path", help="Ruta autenticada adicional a consultar despues del login.")
    parser.add_argument("--username", help="Usuario CAS. Tambien puede usarse EGOBEDOC_USERNAME.")
    parser.add_argument("--password", help="Clave CAS. Tambien puede usarse EGOBEDOC_PASSWORD.")
    parser.add_argument("--insecure", action="store_true", help="Desactiva la verificacion TLS.")
    parser.add_argument("--html-source", help="Ruta local a un HTML ya descargado para parsear en modo offline.")
    parser.add_argument("--save-html", help="Guarda el HTML autenticado descargado.")
    parser.add_argument("--save-meta-json", help="Guarda metadatos de la tabla seleccionada.")
    parser.add_argument("--table-index", type=int, help="Indice manual de la tabla HTML a usar.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Archivo JS de salida.")
    parser.add_argument("--skip-issue-details", action="store_true", help="Omite la lectura del historico individual de cada tramite.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    connection_info: dict[str, object] = {}
    session_context: dict[str, str] = {}
    detail_stats = {"active": {"fetched": 0, "reused": 0, "failed": 0}, "history": {"fetched": 0, "reused": 0, "failed": 0}}
    client = None

    with tempfile.TemporaryDirectory() as temp_dir:
        if args.html_source:
            html_path = Path(args.html_source).expanduser().resolve()
            html_source = html_path.read_text(encoding="utf-8", errors="ignore")
            source_file = html_path.name
            source_path = str(html_path)
            source_note = "Fuente: HTML local parseado desde eGOB/e-Bedoc"
            session_context = extract_session_context(html_source, args.username or "")
        else:
            username, password = resolve_credentials(args)
            html_source, connection_info, client = fetch_authenticated_html(args, username, password, temp_dir)
            source_file = "passig_citizen.html"
            source_path = args.origin
            source_note = "Fuente: sincronizacion autenticada desde eGOB/e-Bedoc via CAS"
            session_context = extract_session_context(html_source, username)
            if session_context:
                connection_info["sessionContext"] = session_context

        output_path = Path(args.output).expanduser().resolve()
        records, meta = parse_html_tables(html_source, args.table_index, session_context=session_context)
        previous_payload = load_existing_payload(output_path)
        issue_tracking_cache = build_issue_tracking_cache(previous_payload)
        detail_stats["active"] = enrich_records_with_issue_tracking(
            records,
            args,
            client=client,
            temp_dir=temp_dir,
            cache=issue_tracking_cache,
            fetch_missing_only=False,
        )
        history_records = merge_history(
            records,
            previous_payload,
            archived_at=datetime.now().isoformat(timespec="seconds"),
        )
        detail_stats["history"] = enrich_records_with_issue_tracking(
            history_records,
            args,
            client=client,
            temp_dir=temp_dir,
            cache=issue_tracking_cache,
            fetch_missing_only=False,
        )
        payload = create_payload(
            records,
            source_file=source_file,
            source_path=source_path,
            source_note=source_note,
            history_records=history_records,
        )

        write_js_module(payload, output_path)

        if args.save_meta_json:
            meta_payload = {
                "connection": connection_info,
                "table": meta,
                "recordCount": len(records),
                "issueTracking": detail_stats,
                "generatedAt": datetime.now().isoformat(timespec="seconds"),
            }
            meta_path = Path(args.save_meta_json).expanduser().resolve()
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        print(
            json.dumps(
                {
                    "output": str(output_path),
                    "records": len(records),
                    "historyRecords": len(history_records),
                    "selectedTableIndex": meta["selectedTableIndex"],
                    "selectedColumns": meta["selectedColumns"],
                    "source": source_path,
                    "issueTracking": detail_stats,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
