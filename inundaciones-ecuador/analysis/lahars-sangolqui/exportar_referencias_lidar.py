"""Export the Sangolquí LiDAR reference layers for the Cesium viewer."""

import argparse
import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from PIL import Image
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds


def terrain(source, output):
    with rasterio.open(source) as original:
        options = original.profile.copy()
        options.update(count=1, compress="deflate", predictor=3, zlevel=9)
        with rasterio.open(output / "terreno-lidar-1m.tif", "w", **options) as elevation:
            elevation.update_tags(**original.tags())
            elevation.set_band_description(1, original.descriptions[0])
            for _, window in original.block_windows(1):
                elevation.write(original.read(1, window=window), 1, window=window)
        bounds = transform_bounds(original.crs, "EPSG:4326", *original.bounds)
        width = 3072
        height = round(width * (bounds[3] - bounds[1]) / (bounds[2] - bounds[0]))
        elevations = np.full((height, width), np.nan, dtype="float32")
        grid = from_bounds(*bounds, width, height)
        reproject(rasterio.band(original, 1), elevations, dst_crs="EPSG:4326",
                  dst_transform=grid, dst_nodata=np.nan, resampling=Resampling.average)
    dy, dx = np.gradient(elevations, abs(grid.e) * 110574, grid.a * 111319)
    illumination = (.77 - .47 * dx + .43 * dy) / np.sqrt(1 + dx**2 + dy**2)
    intensity = np.clip((np.nan_to_num(illumination, nan=.6) + .15) / 1.15, 0, 1)
    dark, light = np.array([39, 68, 83]), np.array([240, 245, 236])
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :, :3] = (dark + intensity[..., None] * (light - dark)).astype(np.uint8)
    image[:, :, 3] = np.where(np.isfinite(elevations), 255, 0)
    Image.fromarray(image).save(output / "relieve.webp", lossless=True, method=4)
    return {"bounds": list(bounds), "display_pixel_m": round(grid.a * 111319, 2)}


def coordinates(points):
    return [[round(x, 7), round(y, 7)] for x, y in points]


def vectors(source):
    geometry = source / "perfiles-pita-santa-clara.gpkg"
    sections = gpd.read_file(geometry, layer="secciones_topograficas").to_crs(4326)
    samples = pd.read_csv(source / "perfiles-pita-santa-clara.csv")
    groups = {name: data.sort_values("offset_m") for name, data in samples.groupby("seccion")}
    profiles = []
    for row in sections.itertuples():
        data = groups[row.seccion]
        if list(data.offset_m) != list(range(-120, 122, 2)):
            raise ValueError(row.seccion)
        levels = [round(float(z), 2) if math.isfinite(z) else None for z in data.cota_lidar_m]
        if any(z is not None for z in levels):
            profiles.append({"id": row.seccion, "river": row.rio, "line": coordinates(row.geometry.coords),
                             "levels": levels, "banks": [row.muestras_margen_izq, row.muestras_margen_der]})
    bridges = []
    inventory = gpd.read_file(geometry, layer="puentes_por_verificar").to_crs(4326)
    for row in inventory.itertuples():
        label = str(row.nombre or "").strip()
        if not label or label.lower() == "si de todo":
            label = "Cruce sobre el " + row.rio
        deck = row.cota_superficie_tablero_candidata_m
        bridges.append({"name": label, "river": row.rio, "point": coordinates([row.geometry.coords[0]])[0],
                        "deck": round(float(deck), 2) if math.isfinite(deck) else None,
                        "source": "Cruce OpenStreetMap · revisión LiDAR municipal"})
    field = source / "referencias-epn-terreno-y-lahares.gpkg"
    choclo = gpd.read_file(field, layer="puente_el_choclo_diseno").to_crs(4326).geometry.item()
    for bridge in bridges:
        if bridge["river"] == "Santa Clara" and math.dist(bridge["point"], (choclo.x, choclo.y)) < .00018:
            bridge.update(name="Puente El Choclo", deck=2480.38, source="Registro ambiental y retornos LiDAR")
            break
    else:
        bridges.append({"name": "Puente El Choclo", "river": "Santa Clara", "deck": 2480.38,
                        "point": coordinates([choclo.coords[0]])[0], "source": "Registro ambiental y retornos LiDAR"})
    return profiles, bridges


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    profiles, bridges = vectors(args.source)
    relief = terrain(args.source / "terreno-lidar-1m.tif", args.output)
    result = {"relief": relief, "profiles": profiles, "bridges": bridges}
    (args.output / "capas.json").write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
                                            encoding="utf-8")
    print(f"Perfiles: {len(profiles)}. Cruces: {len(bridges)}. Píxel del relieve: {relief['display_pixel_m']} m.")
