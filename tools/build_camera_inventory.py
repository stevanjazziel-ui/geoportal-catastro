"""Restore the report inventory without modifying the agreed replacement subset."""
import ast
import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(r"C:\Users\PC\Downloads\BASE_MAESTRA_SEGURIDAD_RIOBAMBA_V2.zip")
MEMBER = "04_VIDEOVIGILANCIA/camaras_ecu911_riobamba_2026.csv"
study_path = ROOT / "riobamba-camaras-data.js"
study_bytes = study_path.read_bytes()
study = json.loads(study_bytes.decode("utf-8").split(" = ", 1)[1].strip().removesuffix(";"))["cameras"]
study_by_id = {camera["id"]: camera for camera in study}

# Reuse the established street transcription and geocoder, never its synthetic fallback.
legacy_path = ROOT / "tools/build_riobamba_cameras_data.py"
tree = ast.parse(legacy_path.read_text(encoding="utf-8"))
definitions = []
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "features" for target in node.targets):
        break
    definitions.append(node)
namespace = {"__file__": str(legacy_path)}
exec(compile(ast.Module(body=definitions, type_ignores=[]), str(legacy_path), "exec"), namespace)
transcription = {row[0]: row for row in namespace["CAMERAS"]}
with zipfile.ZipFile(PACKAGE) as archive:
    source_bytes = archive.read(MEMBER)
rows = list(csv.DictReader(io.StringIO(source_bytes.decode("utf-8-sig"))))
assert len(rows) == 103 and len({row["ID_CAMARA"] for row in rows}) == 103
id_aliases = {"RIO-068-IA": "RIO-068-LA"}
assert {id_aliases.get(row["ID_CAMARA"], row["ID_CAMARA"]) for row in rows if row["REQUIERE_CAMBIO"] == "SI"} == set(study_by_id)
ambiguous_streets = {"baquerizo moreno", "luis urdaneta", "javier esponosa", "baltazar paredes"}
inventory = []
for row in rows:
    camera_id = id_aliases.get(row["ID_CAMARA"], row["ID_CAMARA"])
    clean = transcription[camera_id]
    located = None
    if camera_id in study_by_id:
        located = study_by_id[camera_id]
    elif camera_id in namespace["MANUAL"]:
        lat, lng, method = namespace["MANUAL"][camera_id]
        located = dict(lat=lat, lng=lng, method=method, distanceMeters=None, confidence="media")
    elif clean[4] and clean[5] and not ambiguous_streets.intersection(clean[4:6]):
        candidate = namespace["geocode_pair"](clean[4], clean[5])
        if candidate and candidate["distanceMeters"] <= 140:
            located = candidate
    institution = row["INSTITUCION"].replace("Gal\ufffdpagos", "Galápagos").replace("Donaci\ufffdn", "Donación")
    inventory.append({
        "n": int(row["N"]), "id": camera_id, "sourceId": row["ID_CAMARA"], "type": clean[1],
        "address": clean[2], "reference": clean[3], "sourceAddress": row["DIRECCION"],
        "megaphone": row["MEGAFONO"] == "SI", "requiresChange": row["REQUIERE_CAMBIO"] == "SI",
        "institution": institution, "administracion": institution,
        "studyCamera": camera_id in study_by_id,
        "ambitoEstudio": "MUNICIPAL" if camera_id in study_by_id else "INVENTARIO",
        "lat": located["lat"] if located else None, "lng": located["lng"] if located else None,
        "mappable": bool(located), "confidence": located["confidence"] if located else "No disponible",
        "method": located["method"] if located else "Sin cruce verificable; pendiente de ubicación. No se asigna un punto artificial.",
        "distanceMeters": located.get("distanceMeters") if located else None,
        "events2025": float(row["EVENTOS_2025"]) if row["EVENTOS_2025"] else None,
        "sourcePackage": PACKAGE.name, "sourceMember": MEMBER,
        "source": "Informe Estado de Cámaras Cantón Riobamba, 14-01-2026 (ECU 911)",
        "locationStatus": "Ubicación aproximada; requiere verificación de campo" if located else "Pendiente de ubicación",
    })
result = {"metadata": {
    "totalRecords": len(inventory), "replacementRecords": len(study),
    "source": PACKAGE.name, "member": MEMBER,
    "sourceSha256": hashlib.sha256(source_bytes).hexdigest(),
    "studySha256": hashlib.sha256(study_bytes).hexdigest(),
    "idAliases": id_aliases,
    "note": "Inventario de 103 cámaras. La fuente no proporciona coordenadas. Se conservan las 31 ubicaciones del estudio y las geocodificaciones documentadas; las demás quedan pendientes, sin puntos artificiales.",
    "analysisUniverse": "Las 31 cámaras acordadas para cambio; el inventario completo no alimenta cobertura, brechas ni otros análisis.",
}, "cameras": inventory}
(ROOT / "riobamba-camaras-inventario-data.js").write_text(
    "window.RIOBAMBA_CAMERA_INVENTORY = " + json.dumps(result, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
assert study_path.read_bytes() == study_bytes
print(json.dumps({"records": len(inventory), "unique": len({c["id"] for c in inventory}),
    "replacement": len(study), "located": sum(c["mappable"] for c in inventory),
    "pending": [c["id"] for c in inventory if not c["mappable"]],
    "types": dict(Counter(c["type"] for c in inventory)), "studyUnchanged": True}, ensure_ascii=False))
