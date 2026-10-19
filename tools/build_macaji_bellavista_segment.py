"""Extract the Macaji-Bellavista route shown in the supplied reference image."""

import json
from pathlib import Path

import geopandas as gpd
from pyproj import Geod
from shapely.geometry import MultiLineString


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "data/seguridad-riobamba/SIG_BRIDGE_RELEASES/MUN027_047_CANONIGO_DUCHICELA_20261018"
SOURCE = RELEASE / "CORREDORES.geojson"
TARGET = RELEASE / "CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA"
STEM = "TRAMO_BOULEVARD_MACAJI_BELLAVISTA"
FULL_PARTS = (0, 1, 2, 3, 9, 10, 14, 15, 16, 17, 18, 22, 23, 27, 29, 31)


def main():
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    corridor = next(
        feature for feature in source["features"]
        if feature["properties"]["CORREDOR"] == "BOULEVARD_MACAJI_BELLAVISTA"
    )
    parts = corridor["geometry"]["coordinates"]
    assert len(parts) == 32
    assert parts[15][0] == [-78.66677629360314, -1.665828474924947]
    assert parts[23][0] == [-78.63597102599094, -1.671376235663872]

    # Part 7 joins the western approach at its fifth vertex. Its remaining
    # vertices continue south beyond the route in the reference image.
    lines = [parts[index] for index in FULL_PARTS] + [parts[7][:5]]
    geod = Geod(ellps="WGS84")
    length_m = sum(geod.line_length(*zip(*line)) for line in lines)
    assert 5600 < length_m < 5800

    properties = {
        **corridor["properties"],
        "LONGITUD_M": round(length_m, 2),
        "OBSERVACION_MANUAL": "Subtramo segun MACAJI BELLAVISTA(1).png",
        "NOMBRE": "Tramo Bulevar Macaji-Bellavista",
        "FUENTE": "CORREDORES.geojson; MACAJI BELLAVISTA(1).png",
        "CAPA": "Tramo Bulevar Macaji-Bellavista",
        "SEGMENTOS_ORIGEN": ",".join(map(str, FULL_PARTS)) + ";7[0:5]",
    }
    collection = {
        "type": "FeatureCollection",
        "name": STEM,
        "features": [{
            "type": "Feature",
            "properties": properties,
            "geometry": {"type": "MultiLineString", "coordinates": lines},
        }],
    }
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / f"{STEM}.geojson").write_text(
        json.dumps(collection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    geopackage = TARGET / f"{STEM}.gpkg"
    geopackage.unlink(missing_ok=True)
    frame = gpd.GeoDataFrame(
        [properties], geometry=[MultiLineString(lines)], crs="EPSG:4326"
    )
    frame.to_file(geopackage, layer="BOULEVARD_MACAJI_BELLAVISTA", driver="GPKG", engine="pyogrio")
    print(f"{len(lines)} parts, {length_m:.2f} m: {TARGET / (STEM + '.geojson')}")


if __name__ == "__main__":
    main()
