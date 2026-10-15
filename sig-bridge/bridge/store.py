"""Immutable revision snapshots, constrained edits and optimistic concurrency."""
import contextlib
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pyogrio
from shapely import force_2d

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "sig-bridge/config/project.json"


class BridgeError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise BridgeError(message)


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def package_digest(package):
    """Hash committed content, including SQLite WAL, independent of page layout."""
    hasher = hashlib.sha256()
    for name, _ in sorted(pyogrio.list_layers(package).tolist()):
        frame = pyogrio.read_dataframe(package, layer=name)
        fields = sorted(c for c in frame.columns if c != "geometry")
        rows = sorted(json.dumps(clean({c: row[c] for c in fields}), sort_keys=True, ensure_ascii=False) +
                      row.geometry.wkb_hex for _, row in frame.iterrows())
        hasher.update((name + str(frame.crs) + "\n".join(rows)).encode("utf-8"))
    return hasher.hexdigest()


class Store:
    def __init__(self, root=ROOT, config=None, workspace=None):
        self.root = Path(root).resolve()
        self.config = config or read_json(self.root / "sig-bridge/config/project.json")
        self.workspace = Path(workspace or self.root / self.config["runtimeRoot"]).resolve()
        self.base = self.inside(self.config["basePackage"])
        self.web = self.inside(self.config["baseWebRoot"])
        active = self.root / "sig-bridge-active.json"
        if active.is_file() and read_json(active).get("root"):
            relative = read_json(active)["root"]
            require(bool(re.fullmatch(r"\./data/seguridad-riobamba/SIG_BRIDGE_RELEASES/[A-Za-z0-9_-]+/", relative)), "Registro activo no valido")
            self.web = self.inside(relative)
            self.base = self.web / "ESCENARIO_FINAL_183.gpkg"

    def for_revision(self, revision_id):
        metadata = read_json(self.revision(revision_id) / "revision.json")
        bound = Store(self.root, self.config, self.workspace)
        bound.base = self.inside(metadata.get("basePackage", self.config["basePackage"]))
        bound.web = self.inside(metadata.get("baseWebRoot", self.config["baseWebRoot"]))
        return bound

    def inside(self, relative):
        path = (self.root / relative).resolve()
        require(path.is_relative_to(self.root), "Ruta fuera del repositorio")
        return path

    def revision(self, revision_id):
        require(bool(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", revision_id)), "ID de revision no valido")
        path = self.workspace / "revisions" / revision_id
        require((path / "revision.json").is_file(), "Revision inexistente")
        return path

    def hashes(self):
        paths = {self.base}
        paths.update(p for p in self.web.iterdir() if p.suffix.lower() in (".json", ".geojson", ".csv", ".md"))
        paths.update(self.root.glob("riobamba-*.js"))
        paths.update(self.root.glob("riobamba-*.css"))
        paths.update((self.root / "sig-bridge/bridge").glob("*.py"))
        paths.update((self.root / "tools").glob("*.py"))
        paths.update(self.root / name for name in ("sig-bridge-release.js", "sig-bridge/cli.py"))
        paths.update(self.root / name for name in ("visor-seguridad-riobamba-v2.html", "visor-seguridad-riobamba-data.js", "policia-06d01-data.js"))
        return {p.relative_to(self.root).as_posix(): digest(p) for p in sorted(paths) if p.is_file()}

    def road_hashes(self):
        if not self.config.get("roadSource"):
            return {}
        directory = (self.root / self.config["roadSource"]).resolve()
        require(directory.is_dir() and directory.is_relative_to(self.root.parent), "Fuente vial externa no disponible en su raiz declarada")
        return {p.name: digest(p) for p in sorted(directory.iterdir()) if p.is_file() and not p.name.lower().endswith((".lock", ".lck"))}

    def guard(self, metadata):
        require(metadata["configSha256"] == digest(self.root / "sig-bridge/config/project.json"), "Configuracion modificada: crear una nueva revision")
        for relative, expected in metadata["baseHashes"].items():
            require(digest(self.inside(relative)) == expected, "Fuente modificada desde la revision: " + relative)
        require(metadata.get("roadHashes", {}) == self.road_hashes(), "La cartografia vial cambio desde esta revision")

    @contextlib.contextmanager
    def lock(self):
        self.workspace.mkdir(parents=True, exist_ok=True)
        path = self.workspace / "bridge.lock"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise BridgeError("Hay otra operacion del Bridge; no se sobrescribe su trabajo") from None
        try:
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            yield
        finally:
            path.unlink(missing_ok=True)

    def create(self, author, reason, parent=None):
        require(bool(author.strip()) and bool(reason.strip()), "Autor y motivo obligatorios")
        with self.lock():
            revision_id = datetime.now().strftime("REV_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8]
            path = self.workspace / "revisions" / revision_id
            path.mkdir(parents=True, exist_ok=False)
            parent_path = self.revision(parent) if parent else None
            source = self.for_revision(parent) if parent else self
            hashes = source.hashes()
            meta = {"id": revision_id, "createdAt": now(), "author": author, "reason": reason,
                    "parent": parent, "basePackage": source.base.relative_to(self.root).as_posix(),
                    "baseWebRoot": source.web.relative_to(self.root).as_posix(),
                    "baseHashes": hashes, "roadHashes": self.road_hashes(), "configSha256": digest(self.root / "sig-bridge/config/project.json")}
            if parent_path:
                self.guard(read_json(parent_path / "revision.json"))
                self.validate(parent)
                self.backup(parent_path / "manual.gpkg", path / "manual.gpkg")
            else:
                for key, spec in self.config["layers"].items():
                    frame = pyogrio.read_dataframe(self.base, layer=spec["source"])
                    frame = frame[[spec["id"], *spec["editable"], "geometry"]].copy()
                    frame["OBSERVACION_MANUAL"] = ""
                    pyogrio.write_dataframe(frame, path / "manual.gpkg", layer=key)
            write_json(path / "revision.json", meta)
            # Seal an independent initial state for a verifiable recovery operation.
            self.backup(path / "manual.gpkg", path / "initial.gpkg")
            write_json(path / "initial.json", {"sha256": digest(path / "initial.gpkg")})
            self.guard(meta)
            return meta

    @staticmethod
    def backup(source, destination):
        require(not Path(destination).exists(), "El destino ya existe; no se sobrescribe una revision")
        with contextlib.closing(sqlite3.connect(f"file:{Path(source).as_posix()}?mode=ro", uri=True)) as src:
            with contextlib.closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
                dst.commit()

    def validate_package(self, package):
        changes, frames = [], {}
        actual_layers = {str(row[0]) for row in pyogrio.list_layers(package)}
        require(actual_layers == set(self.config["layers"]), "Capas editables anadidas/eliminadas sin autorizacion")
        for key, spec in self.config["layers"].items():
            original = pyogrio.read_dataframe(self.base, layer=spec["source"])
            frame = pyogrio.read_dataframe(package, layer=key)
            expected_fields = {spec["id"], *spec["editable"], "geometry", "OBSERVACION_MANUAL"}
            require(set(frame.columns) == expected_fields, "Esquema editable alterado: " + key)
            require(frame.crs is not None and frame.crs.to_epsg() == 32717, "CRS requerido EPSG:32717: " + key)
            require(len(frame) == spec["count"], "Conteo alterado: " + key)
            require(frame[spec["id"]].notna().all() and frame[spec["id"]].is_unique, "ID nulo/duplicado: " + key)
            require(set(frame[spec["id"]]) == set(original[spec["id"]]), "Los identificadores no pueden modificarse: " + key)
            require(frame.geometry.notna().all() and (~frame.geometry.is_empty).all() and frame.geometry.is_valid.all(), "Geometrias nulas/vacias/invalidas: " + key)
            family = spec["geometry"]
            require(all(g.geom_type == family if family == "Point" else family in g.geom_type for g in frame.geometry), "Tipo geometrico incompatible: " + key)
            require(all(len(g.bounds) == 4 and all(math.isfinite(c) for c in g.bounds) for g in frame.geometry), "Coordenadas no finitas: " + key)
            originals = original.set_index(spec["id"])
            for _, row in frame.iterrows():
                old = originals.loc[row[spec["id"]]]
                moved = not force_2d(row.geometry).equals_exact(force_2d(old.geometry), 0)
                fields = [name for name in spec["editable"] if clean(row[name]) != clean(old[name])]
                require(not row.geometry.has_z, "Guardar geometrias 2D; no se eliminan Z silenciosamente")
                if moved and spec.get("groupField"):
                    require(old[spec["groupField"]] in spec["editableGroups"], "Grupo congelado: " + str(row[spec["id"]]))
                if "POBLACION" in frame.columns:
                    population = clean(row.POBLACION)
                    require(population is None or (isinstance(population, (int, float)) and population >= 0), "Poblacion negativa/no numerica")
                note = row.OBSERVACION_MANUAL
                require(isinstance(note, str) or note is None, "Observacion manual debe ser texto")
                if moved or fields or (isinstance(note, str) and note.strip()):
                    changes.append({"layer": key, "id": str(row[spec["id"]]), "geometryChanged": moved,
                        "beforeWkb": force_2d(old.geometry).wkb_hex, "afterWkb": row.geometry.wkb_hex,
                        "distanceM": old.geometry.distance(row.geometry) if family == "Point" else None,
                        "fields": fields, "before": {f: clean(old[f]) for f in fields},
                        "after": {f: clean(row[f]) for f in fields}, "note": note})
            frames[key] = frame
        return frames, changes

    def validate(self, revision_id):
        path = self.revision(revision_id)
        metadata = read_json(path / "revision.json")
        source = self.for_revision(revision_id)
        source.guard(metadata)
        _, changes = source.validate_package(path / "manual.gpkg")
        return {"id": revision_id, "status": "VALIDATED", "changes": changes, "manualSha256": package_digest(path / "manual.gpkg")}

    def snapshot(self, revision_id):
        path = self.revision(revision_id)
        metadata = read_json(path / "revision.json")
        source = self.for_revision(revision_id)
        source.guard(metadata)
        run = self.workspace / "runs" / revision_id / (datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8])
        run.mkdir(parents=True, exist_ok=False)
        before = package_digest(path / "manual.gpkg")
        self.backup(path / "manual.gpkg", run / "input.gpkg")
        require(before == package_digest(path / "manual.gpkg") == package_digest(run / "input.gpkg"), "Edicion concurrente: guardar y repetir")
        frames, changes = source.validate_package(run / "input.gpkg")
        receipt = {"revision": revision_id, "createdAt": now(), "manualSha256": before,
                   "snapshotSha256": digest(run / "input.gpkg"), "changes": changes, "baseHashes": metadata["baseHashes"],
                   "configSha256": metadata["configSha256"], "revisionSha256": digest(path / "revision.json")}
        write_json(run / "input.json", receipt)
        return run, frames, receipt

    def history(self):
        return sorted([read_json(p) for p in (self.workspace / "revisions").glob("*/revision.json")], key=lambda p: p["createdAt"])

    def restore(self, revision_id, author, reason, initial=False):
        source = self.revision(revision_id)
        package = source / ("initial.gpkg" if initial else "manual.gpkg")
        if initial:
            require(digest(source / "initial.gpkg") == read_json(source / "initial.json")["sha256"], "Estado inicial alterado")
        # Recover edits into a new current-version revision, never reuse historic calculations.
        # This also permits recovery after bridge-code upgrades, subject to today's ID/group rules.
        self.validate_package(package)
        created = self.create(author, reason)
        target = self.revision(created["id"])
        before = package_digest(package)
        self.backup(package, target / "restored.gpkg")
        require(before == package_digest(package) == package_digest(target / "restored.gpkg"), "La revision a recuperar cambio durante la lectura")
        self.validate_package(target / "restored.gpkg")
        shutil.copyfile(target / "restored.gpkg", target / "manual.gpkg")
        shutil.copyfile(target / "restored.gpkg", target / "initial.gpkg")
        write_json(target / "initial.json", {"sha256": digest(target / "initial.gpkg")})
        meta = read_json(target / "revision.json")
        meta.update({"restoredFrom": revision_id, "restoredInitial": initial, "restoredContentSha256": before})
        write_json(target / "revision.json", meta)
        return meta
