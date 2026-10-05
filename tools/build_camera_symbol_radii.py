"""Visual buffers only. Inventory, dissolved analysis and results are unchanged."""
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, mapping
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/seguridad-riobamba/CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA"
source = json.loads((OUT / "CAMARAS_EXISTENTES_103_FINAL.geojson").read_text(encoding="utf-8"))
project = Transformer.from_crs(4326, 32717, always_xy=True).transform
display = Transformer.from_crs(32717, 4326, always_xy=True).transform
features = []
for camera in source["features"]:
    center = transform(project, Point(camera["geometry"]["coordinates"]))
    ring = center.buffer(200, quad_segs=64)
    geometry = mapping(transform(display, ring))
    check = transform(project, Point(geometry["coordinates"][0][0]))
    assert abs(check.distance(center) - 200) < 0.00001
    features.append({"type": "Feature", "properties": {
        "ID_CAMARA": camera["properties"]["ID_CAMARA"],
        "REQUIERE_CAMBIO": camera["properties"]["REQUIERE_CAMBIO"],
        "RADIO_M": 200, "CRS_CALCULO": "EPSG:32717"},
        "geometry": geometry})
assert len(features) == 103
assert sum(f["properties"]["REQUIERE_CAMBIO"] for f in features) == 31
(OUT / "RADIOS_EXISTENTES_SIMBOLOGIA_200M.geojson").write_text(json.dumps({
    "type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
print("103 radios metricos: 72 azules, 31 morados. Calculos y fuentes intactos.")
