"""Independent checks against received geometry and the previous fixed proposals."""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely import covers
from shapely.geometry import shape, Point
from shapely.ops import unary_union, transform
from pyproj import Transformer
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sig-bridge"))
from bridge.store import read_json, write_json, digest, require
from recalculate_final_inventory_coverage import DESTINATION, INVENTORY


def main():
    out = DESTINATION
    package = out / "ESCENARIO_FINAL_183.gpkg"
    base = ROOT / "data/seguridad-riobamba/POLICIA_KDE_INTERSECCIONES_20261015/ESCENARIO_FINAL_183.gpkg"
    incoming = gpd.read_file(INVENTORY / "INVENTARIO_FINAL_103.gpkg")
    existing = gpd.read_file(package, layer="CAMARAS_EXISTENTES_103_FINAL")
    municipal = gpd.read_file(package, layer="PROPUESTA_MUNICIPAL_50_FINAL")
    police = gpd.read_file(package, layer="PROPUESTA_POLICIA_30_FINAL")
    require([len(existing),len(municipal),len(police)] == [103,50,30], "Conteos incorrectos")
    require(existing.ID_CAMARA.tolist() == incoming.ID_CAMARA.tolist(), "IDs de fuente alterados")
    require(existing.geometry.to_wkb().tolist() == incoming.geometry.to_wkb().tolist(), "Geometrias recibidas alteradas")
    require(int(existing.REQUIERE_CAMBIO.sum()) == 30, "Reemplazos incorrectos")
    require(existing.REQUIERE_CAMBIO.astype(bool).tolist() == incoming.REQUIERE_CAMBIO.astype(bool).tolist(), "Clasificacion recibida alterada")
    proposed_unchanged = {}
    for name, frame in (("PROPUESTA_MUNICIPAL_50_FINAL", municipal), ("PROPUESTA_POLICIA_30_FINAL", police)):
        before = gpd.read_file(base, layer=name)
        require(before.geometry.to_wkb().tolist() == frame.geometry.to_wkb().tolist(), "Propuesta movida")
        proposed_unchanged[name] = True
    stats = []
    for scope in ("URBANO", "RURAL"):
        for category in ("DELINCUENCIA", "VIOLENCIA", "CONVIVENCIA"):
            name = f"GI_{scope}_{category}"
            before, after = gpd.read_file(base, layer=name), gpd.read_file(package, layer=name)
            require(before.geometry.to_wkb().tolist() == after.geometry.to_wkb().tolist(), "Celdas Gi* cambiadas")
            fields = [c for c in before.columns if c != "geometry" and not c.startswith(("COB_","ESTADO_"))]
            pd.testing.assert_frame_equal(before[fields], after[fields], check_dtype=False)
            stats.append({"layer":name,"cells":len(after),"geometryAndStatisticsUnchanged":True})
    to_metric = Transformer.from_crs(4326,32717,always_xy=True).transform
    js = (out / "riobamba-brechas-actualizadas-data.js").read_text(encoding="utf-8")
    gaps = json.JSONDecoder().raw_decode(js.split(" = ",1)[1])[0]
    events = gpd.read_file(package, layer="INCIDENTES_CLASIFICADOS")
    results = read_json(out / "RESULTADOS.json")
    require(results["counts"] == {"existing":103,"changeIncluded":30,"municipal":50,"police":30}, "Conteo del visor obsoleto")
    require(sum(c["requiresChange"] for c in gaps["inventoryCameraOverlay"]) == 30, "Overlay obsoleto")
    radius_checks = []
    for radius in (100,150,200):
        disks = {"A":[g.buffer(radius,quad_segs=64) for g in existing.geometry]}
        disks["B"] = disks["A"]+[g.buffer(radius,quad_segs=64) for g in municipal.geometry]
        disks["C"] = disks["B"]+[g.buffer(radius,quad_segs=64) for g in police.geometry]
        masks = {key:unary_union(values) for key,values in disks.items()}
        web_mask = transform(to_metric,shape(gaps["inventoryCoverage"]["scenarios"][str(radius)]["coverage"]["geometry"]))
        require(web_mask.symmetric_difference(masks["A"]).area < .02,"Cobertura del visor incorrecta")
        replacement = unary_union([g.buffer(radius,quad_segs=64) for g in existing.loc[existing.REQUIERE_CAMBIO].geometry])
        web_replacement = transform(to_metric,shape(gaps["replacementScenarios"][str(radius)]["coverage"]["geometry"]))
        require(web_replacement.symmetric_difference(replacement).area < .02,"Cobertura de 30 incorrecta")
        previous_area = 0
        for code,mask in masks.items():
            require(mask.area >= previous_area,"Cobertura no monotona entre escenarios")
            previous_area = mask.area
            if radius == 200:
                stored = gpd.read_file(package,layer="COBERTURA_"+code).geometry.iloc[0]
                require(mask.symmetric_difference(stored).area < .01,"Union de buffers incorrecta")
                require(np.array_equal(covers(mask,events.geometry.values),events["CUB_"+code].astype(bool).values),"Incidentes incorrectos")
            by_man = gaps["scenarios"][str(radius)][code]["byMan"]
            blocks = gpd.read_file(package,layer="MANZANAS_COBERTURA")
            for block in blocks.itertuples():
                expected = block.geometry.intersection(mask).area/block.geometry.area*100
                require(abs(by_man[block.ID_MANZANA]["coveragePct"]-expected)<1e-5,"Manzana desincronizada")
        radius_checks.append({"radiusM":radius,"scenarioAreasM2":{k:m.area for k,m in masks.items()},"passed":True})
    radius_geojson = read_json(out / "RADIOS_EXISTENTES_SIMBOLOGIA_200M.geojson")["features"]
    require(len(radius_geojson)==103 and sum(f["properties"]["REQUIERE_CAMBIO"] for f in radius_geojson)==30,"Radios y simbolos inconsistentes")
    centers = existing.set_index("ID_CAMARA")
    for f in radius_geojson:
        ring = transform(to_metric,shape(f["geometry"]))
        center = centers.loc[f["properties"]["ID_CAMARA"]].geometry
        require(all(abs(center.distance(Point(c))-200)<1e-5 for c in ring.exterior.coords),"El radio no es 200 m")
    validation = read_json(out / "VALIDACION.json")
    require(not validation["publishBlocks"],"Bloqueos pendientes")
    require(all(digest(Path(p)) == h for p,h in validation["sourceHashes"].items()),"Fuente protegida modificada")
    report={"passed":True,"counts":{"existing":103,"replacement":30,"withoutReplacement":73,"municipal":50,"police":30},
        "sourceGeometryPreserved":True,"proposalsUnmoved":proposed_unchanged,"gi":stats,"radii":radius_checks,
        "buffersAreRadiusNotDiameter":True,"censusClipsAndPointCoverageValidated":True,
        "approvedException":validation.get("approvedException"),"packageSha256":digest(package)}
    write_json(out / "VERIFICACION_INDEPENDIENTE.json",report)
    print(json.dumps(report),flush=True)


if __name__ == "__main__":
    main()
