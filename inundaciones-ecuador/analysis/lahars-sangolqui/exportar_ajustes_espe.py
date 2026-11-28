"""Export the reviewed Coliseo and Garita geometry for the Sangolquí viewer."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely import Polygon, transform
from shapely.geometry import mapping, shape


TO_UTM = Transformer.from_crs(4326, 32717, always_xy=True).transform
TO_WGS = Transformer.from_crs(32717, 4326, always_xy=True).transform


def roof_part(points, heights, bottom=None):
    lon, lat = TO_WGS(*np.asarray(points).T)
    part = {"ring": [[round(x, 8), round(y, 8), round(float(z), 2)] for x, y, z in zip(lon, lat, heights, strict=True)]}
    if bottom is not None:
        part["bottom"] = bottom
    return part


def coliseum(footprint, origin, surfaces):
    se, ne, nw, sw = np.asarray(footprint.exterior.coords)[:-1]
    west, south, east, north = footprint.bounds
    x0, y0, z0 = origin
    c0, c1 = int(2 * (west - x0)), int(2 * (east - x0)) + 1
    r0, r1 = int(2 * (south - y0)), int(2 * (north - y0)) + 1
    roof = np.fmax(*(surface[r0:r1, c0:c1] for surface in surfaces)) + z0
    x = x0 + (np.arange(c0, c1) + .5) * .5
    y = y0 + (np.arange(r0, r1) + .5) * .5
    y_fraction = (y - (se[1]+sw[1])/2) / ((ne[1]+nw[1]-se[1]-sw[1])/2)
    x_west = sw[0] + y_fraction * (nw[0]-sw[0])
    x_east = se[0] + y_fraction * (ne[0]-se[0])
    cross = (x[None, :] - x_west[:, None]) / (x_east-x_west)[:, None]
    floor = 2473.2  # Bare ground on exposed margins of the coliseum.
    stations = np.linspace(0, 1, 11)
    heights = []
    for t in stations:
        keep = ((abs(cross - np.clip(t, .027, .973)) <= .028) &
                ((y_fraction > .25) & (y_fraction < .83))[:, None] & (roof > floor+3))
        if keep.sum() < 15:
            raise ValueError(f"Sin respaldo de cubierta en estación {t}")
        heights.append(round(float(np.median(roof[keep]) - floor), 2))
    if not 12 < max(heights) < 17 or min(heights) < 3 or max(heights[0], heights[-1]) > 8:
        raise ValueError(f"Perfil de cubierta inesperado {heights}")
    south_edge = sw + stations[:, None] * (se-sw)
    north_edge = nw + stations[:, None] * (ne-nw)
    parts = [roof_part([south_edge[k], south_edge[k+1], north_edge[k+1], north_edge[k]],
                       [heights[k], heights[k+1], heights[k+1], heights[k]])
             for k in range(len(heights)-1)]
    return {"name": "Coliseo Gral. Miguel Iturralde", "height": max(heights), "levels": 1, "parts": parts}


def canopy():
    outline = [(784690.45, 9965142.7), (784695.97, 9965142.3),
               (784700.6, 9965190.35), (784694.55, 9965190.9)]
    height = 7.25
    parts = [roof_part(outline, [height] * 4, bottom=6.72)]
    # Open vehicular bays between the ends and the central island.
    for x, y in [(784692.5, 9965145.5), (784695.5, 9965166.5), (784697.6, 9965188.1)]:
        pier = [(x-.34,y-.35), (x+.34,y-.35), (x+.34,y+.35), (x-.34,y+.35)]
        parts.append(roof_part(pier, [6.72] * 4))
    geometry = mapping(transform(Polygon(outline), TO_WGS, interleaved=False))
    return {"name": "Garita principal ESPE · marquesina", "height": height, "levels": 1,
            "geometry": geometry, "parts": parts,
            "note": "Cubierta y accesos abiertos reconstruidos con LiDAR y ortofoto. Apoyos representados de forma aproximada."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("buildings", type=Path)
    parser.add_argument("grid", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    features = json.loads(gzip.decompress(args.buildings.read_bytes()))["features"]
    origin = json.loads((args.grid / "verificacion.json").read_bytes())["origen_x_y_z"]
    surfaces = [np.load(args.grid / f"clase{i}.z.npy", mmap_mode="r") for i in (1, 2)]
    footprint = transform(shape(features[8648]["geometry"]), TO_UTM, interleaved=False)
    if not 2650 < footprint.area < 2700:
        raise ValueError("La huella del coliseo no corresponde al índice previsto")
    result = {"cat-8648": coliseum(footprint, origin, surfaces),
              "cat-8645": {"name": "Caseta del acceso ESPE", "height": 2.84, "levels": 1},
              "w175006659": canopy()}
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print({key: entry["height"] for key, entry in result.items()})
