"""Import the confirmed inventory without replacing active coverage or originals."""
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def flag(value):
    return str(value).strip().upper() in {"TRUE", "1", "1.0", "SI", "S\u00cd"}


def normalize(incoming, previous, confirmed=False):
    if not confirmed:
        raise ValueError("ACTUALIZ requiere confirmacion explicita como campo de reemplazo")
    required = {"ID", "ACTUALIZ", "TIPO_POS", "CONF_ESQ", "VALIDACION"}
    if not required.issubset(incoming.columns):
        raise ValueError("Faltan campos del inventario recibido")
    if incoming.crs is None or incoming.crs.to_epsg() != 32717:
        raise ValueError("El archivo recibido debe declarar EPSG:32717")
    if previous.crs is None:
        raise ValueError("El inventario anterior no tiene CRS")
    if len(incoming) != 103 or incoming.ID.isna().any() or incoming.ID.nunique() != 103:
        raise ValueError("Se requieren exactamente 103 IDs unicos y no nulos")
    if previous.ID_CAMARA.isna().any() or previous.ID_CAMARA.nunique() != len(previous):
        raise ValueError("IDs anteriores invalidos")
    if set(incoming.ID) != set(previous.ID_CAMARA):
        raise ValueError("Los IDs no coinciden con las 103 camaras anteriores")
    if incoming.geometry.isna().any() or incoming.geometry.is_empty.any():
        raise ValueError("Hay camaras sin geometria")
    if not incoming.geometry.is_valid.all() or not incoming.geom_type.eq("Point").all():
        raise ValueError("Se requieren puntos validos")
    values = incoming.ACTUALIZ.astype("string").str.strip().str.upper()
    if values.isna().any() or not values.isin(["SI", "NO"]).all():
        raise ValueError("ACTUALIZ contiene valores distintos de SI/NO")
    if int(values.eq("SI").sum()) != 30:
        raise ValueError("El universo confirmado requiere exactamente 30 para cambio")
    result = incoming.copy()
    result["ID_CAMARA"] = incoming.ID
    result["REQUIERE_CAMBIO"] = values.eq("SI").astype(bool)
    result["TIPO"] = incoming.ID.str.rsplit("-", n=1).str[-1]
    result["X"] = incoming.geometry.x
    result["Y"] = incoming.geometry.y
    lonlat = incoming.to_crs(4326)
    result["LONGITUD"] = lonlat.geometry.x
    result["LATITUD"] = lonlat.geometry.y
    result["ORIGEN_REEMPLAZO"] = "ACTUALIZ; interpretacion confirmada por el usuario"
    result["AVISO_GEO"] = incoming.TIPO_POS.map(
        lambda value: "Esquina estimada, no verificada en campo"
        if value == "ESQUINA_ESTIMADA" else "Conservar validacion y procedencia del archivo recibido"
    )
    old = previous.to_crs(32717).set_index("ID_CAMARA").loc[result.ID_CAMARA]
    old.index = result.index
    comparison = pd.DataFrame({
        "ID_CAMARA": result.ID_CAMARA,
        "CAMBIO_ANTERIOR": old.REQUIERE_CAMBIO.map(flag),
        "CAMBIO_CONFIRMADO": result.REQUIERE_CAMBIO,
        "X_ANTERIOR": old.geometry.x,
        "Y_ANTERIOR": old.geometry.y,
        "X_RECIBIDO": result.X,
        "Y_RECIBIDO": result.Y,
        "DESPLAZAMIENTO_M": result.geometry.distance(old.geometry),
        "TIPO_POS": result.TIPO_POS,
        "CONF_ESQ": result.CONF_ESQ,
    })
    return result, comparison


def run(source, baseline, output, confirmed):
    source, baseline, output = Path(source).resolve(), Path(baseline).resolve(), Path(output).resolve()
    source_hash, baseline_hash = sha256(source), sha256(baseline)
    with zipfile.ZipFile(source) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP corrupto")
        candidates = [n for n in archive.namelist() if n.lower().endswith(".shp")]
        if candidates != ["CAMARAS_103_ESQUINAS.shp"]:
            raise ValueError("La capa recibida no es la esperada")
        readme = archive.read("LEEME.txt").decode("utf-8-sig")
    incoming = gpd.read_file("/vsizip/" + source.as_posix() + "/" + candidates[0])
    previous = gpd.read_file(baseline, layer="CAMARAS_EXISTENTES_103_FINAL")
    normalized, comparison = normalize(incoming, previous, confirmed)
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source, output / source.name)
    package = output / "INVENTARIO_FINAL_103.gpkg"
    normalized.to_file(package, layer="CAMARAS_EXISTENTES_103_FINAL", driver="GPKG", index=False)
    for name, rows in (
        ("CAMARAS_EXISTENTES_103_FINAL", normalized),
        ("CAMARAS_PARA_CAMBIO_30", normalized.loc[normalized.REQUIERE_CAMBIO]),
        ("CAMARAS_SIN_CAMBIO_73", normalized.loc[~normalized.REQUIERE_CAMBIO]),
    ):
        rows.to_crs(4326).to_file(output / (name + ".geojson"), driver="GeoJSON", index=False)
    comparison.to_csv(output / "COMPARACION_INVENTARIO.csv", index=False, encoding="utf-8-sig")
    reread = gpd.read_file(package, layer="CAMARAS_EXISTENTES_103_FINAL")
    if reread.geometry.to_wkb().tolist() != incoming.geometry.to_wkb().tolist():
        raise ValueError("La exportacion altero las geometrias recibidas")
    if int(reread.REQUIERE_CAMBIO.sum()) != 30:
        raise ValueError("La exportacion altero la clasificacion confirmada")
    if sha256(source) != source_hash or sha256(baseline) != baseline_hash:
        raise ValueError("Cambio una fuente durante la importacion")
    changed_flag = comparison.CAMBIO_ANTERIOR != comparison.CAMBIO_CONFIRMADO
    report = {
        "source": str(source), "sourceSha256": source_hash,
        "previous": str(baseline), "previousSha256": baseline_hash,
        "crs": "EPSG:32717", "webCrs": "EPSG:4326",
        "total": len(normalized), "replacement": 30, "withoutReplacement": 73,
        "replacementField": "ACTUALIZ", "confirmedBy": "Usuario: esas 30 son las que se van a cambiar",
        "previousReplacement": int(comparison.CAMBIO_ANTERIOR.sum()),
        "changedReplacementIds": comparison.loc[changed_flag, "ID_CAMARA"].tolist(),
        "movedOverOneCentimeter": int(comparison.DESPLAZAMIENTO_M.gt(.01).sum()),
        "maxDisplacementM": float(comparison.DESPLAZAMIENTO_M.max()),
        "estimatedCornerIds": normalized.loc[normalized.TIPO_POS.eq("ESQUINA_ESTIMADA"), "ID_CAMARA"].tolist(),
        "sourceReadme": readme,
        "geometryPreservedExactly": True, "activeInViewer": False,
        "coverageRecalculated": False, "published": False,
        "nextRequired": "Recalcular y validar coberturas dependientes antes de activar el inventario en el visor",
        "files": {p.name: sha256(p) for p in sorted(output.iterdir()) if p.is_file()},
    }
    (output / "IMPORTACION.json").write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    (output / "README.md").write_text(
        "# Inventario final recibido: 103 camaras\n\n"
        "El usuario confirma ACTUALIZ=SI como PARA CAMBIO (30); NO como SIN CAMBIO (73). "
        "Los 30 forman parte de los 103, no son camaras adicionales.\n\n"
        "El ZIP original y las geometrias se conservan sin modificaciones. "
        "GeoPackage EPSG:32717; GeoJSON EPSG:4326. X/Y proceden de la geometria actual, no de X_ANT/Y_ANT. "
        "TIPO se obtiene del sufijo del ID; los demas atributos originales se conservan.\n\n"
        "REQUIERE_CAMBIO es la clasificacion confirmada; ACTUALIZ permanece como atributo original. "
        "TIPO_POS, CONF_ESQ, VALIDACION, VAL_NUEVA, FUENTE_N y AVISO_GEO preservan las limitaciones espaciales. "
        "Hay 11 esquinas estimadas no verificadas. La aceptacion administrativa no certifica postes reales.\n\n"
        "IMPORTACION.json contiene hashes, conteos y estado; COMPARACION_INVENTARIO.csv "
        "documenta cada cambio respecto al inventario anterior.\n\n"
        "Este paquete es un insumo versionado, NO una entrega activa ni un recalculo. "
        "No se modifican resultados, propuestas municipales/policiales, KDE o Gi*. "
        "Las coberturas anteriores no deben presentarse como calculadas con estas ubicaciones. "
        "Recalcular los derivados y sincronizar inventario, simbolos, controles y conteos antes de publicar.\n",
        encoding="ascii",
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--confirm-actualiz-is-replacement", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.baseline, args.output, args.confirm_actualiz_is_replacement), indent=2, ensure_ascii=True))
