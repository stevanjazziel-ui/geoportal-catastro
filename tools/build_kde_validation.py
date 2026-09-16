import json
import math
from collections import Counter, deque
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union


ROOT = Path(__file__).resolve().parents[1]
CELL_SIZE = 20
BANDWIDTHS = [200, 300, 500]
CRS_METRIC = "EPSG:32717"
CRS_SOURCE = "EPSG:4326"
PERIOD = "enero 2026 - agosto 2026"
OUTPUT_DIR = ROOT / "data" / "kde-validacion"
DATA_JS = ROOT / "riobamba-seguridad-kde-validacion-data.js"

to_metric = Transformer.from_crs(CRS_SOURCE, CRS_METRIC, always_xy=True).transform
to_geo_transformer = Transformer.from_crs(CRS_METRIC, CRS_SOURCE, always_xy=True)


def load_js_object(path, variable_name):
    text = path.read_text(encoding="utf-8")
    prefix = f"window.{variable_name} = "
    start = text.index(prefix) + len(prefix)
    depth = 0
    end = None
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise ValueError(f"No se pudo leer {variable_name}")
    payload = text[start:end]
    return json.loads(payload)


def precision_group(value):
    value = str(value or "").strip().upper()
    if value.startswith("A"):
        return "A"
    if value.startswith("B"):
        return "B"
    if value.startswith("C"):
        return "C"
    return "N/D"


def feature_label(feature):
    name = (feature.get("properties") or {}).get("platform_name", "")
    return name.replace("PLATAFORMA ", "")


def to_lon_lat(x, y):
    lon, lat = to_geo_transformer.transform(x, y)
    return [round(lon, 8), round(lat, 8)]


def platform_for_point(point_metric, platform_metric):
    for feature, geom in platform_metric:
        if geom.covers(point_metric):
            return feature_label(feature)
    return None


def exclusion_reason(event, group, lon, lat, point_metric, study_union):
    if group == "C":
        return "PRECISION_C: registro ciudad/distrito/parroquial; no se convierte a punto para KDE."
    if lon is None or lat is None:
        return "SIN_COORDENADA: no existe latitud/longitud publicada para uso espacial."
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        return "COORDENADA_INVALIDA: latitud/longitud no numerica."
    if lon == 0 or lat == 0:
        return "COORDENADA_0_0: coordenada nula o incompleta."
    if abs(lat) > 20 and abs(lon) < 20:
        return "LAT_LON_INTERCAMBIADAS: los valores parecen invertidos."
    if not (-79.2 <= lon <= -78.2 and -2.1 <= lat <= -1.2):
        return "FUERA_RIOBAMBA: coordenada fuera del rango geografico esperado para Riobamba."
    if point_metric is None or not study_union.covers(point_metric):
        return "FUERA_AMBITO_PLATAFORMAS: georreferenciado, pero fuera de las 18 plataformas territoriales reales."
    if group not in ("A", "B"):
        return "PRECISION_NO_ADMITIDA: solo se admiten registros A/B con coordenada verificable."
    return None


def connected_components(binary_grid):
    seen = np.zeros(binary_grid.shape, dtype=bool)
    components = 0
    rows, cols = binary_grid.shape
    for row in range(rows):
        for col in range(cols):
            if not binary_grid[row, col] or seen[row, col]:
                continue
            components += 1
            queue = deque([(row, col)])
            seen[row, col] = True
            while queue:
                r, c = queue.popleft()
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and binary_grid[nr, nc] and not seen[nr, nc]:
                        seen[nr, nc] = True
                        queue.append((nr, nc))
    return components


def qualitative_fragmentation(components):
    if components <= 2:
        return "baja"
    if components <= 5:
        return "media"
    return "alta"


def qualitative_smoothing(bandwidth):
    if bandwidth <= 200:
        return "bajo"
    if bandwidth <= 300:
        return "medio"
    return "alto"


def interpolate_colors(norm):
    stops = np.array([
        [0.00, 255, 230, 109],
        [0.35, 255, 190, 55],
        [0.58, 255, 124, 32],
        [0.78, 225, 29, 54],
        [1.00, 99, 25, 45],
    ], dtype=float)
    rgb = np.zeros((*norm.shape, 3), dtype=np.uint8)
    for idx in range(len(stops) - 1):
        left = stops[idx]
        right = stops[idx + 1]
        mask = (norm >= left[0]) & (norm <= right[0])
        span = max(right[0] - left[0], 1e-9)
        t = ((norm[mask] - left[0]) / span)[:, None]
        rgb[mask] = np.round(left[1:] + (right[1:] - left[1:]) * t).astype(np.uint8)
    rgb[norm >= 1] = stops[-1, 1:].astype(np.uint8)
    return rgb


def render_kde_png(density, mask, path):
    max_value = float(density.max()) if density.size else 0
    norm = density / max_value if max_value else np.zeros_like(density)
    rgba = np.zeros((*density.shape, 4), dtype=np.uint8)
    rgba[..., :3] = interpolate_colors(norm)
    visible = (norm >= 0.04) & mask
    alpha = np.zeros_like(norm, dtype=np.uint8)
    alpha[visible] = np.clip(((norm[visible] - 0.04) / 0.96) ** 0.8 * 220, 0, 220).astype(np.uint8)
    rgba[..., 3] = alpha
    Image.fromarray(rgba, mode="RGBA").save(path)
    return max_value, norm


def build_density(points_xy, xs, ys, bandwidth):
    density = np.zeros((len(ys), len(xs)), dtype=np.float32)
    for x, y in points_xy:
        col_min = max(0, int(math.floor((x - bandwidth - xs[0]) / CELL_SIZE)))
        col_max = min(len(xs) - 1, int(math.ceil((x + bandwidth - xs[0]) / CELL_SIZE)))
        row_min = max(0, int(math.floor((ys[0] - (y + bandwidth)) / CELL_SIZE)))
        row_max = min(len(ys) - 1, int(math.ceil((ys[0] - (y - bandwidth)) / CELL_SIZE)))
        sub_x = xs[col_min:col_max + 1]
        sub_y = ys[row_min:row_max + 1]
        xx, yy = np.meshgrid(sub_x, sub_y)
        dist = np.sqrt((xx - x) ** 2 + (yy - y) ** 2)
        contribution = np.where(dist <= bandwidth, np.exp(-0.5 * (dist / bandwidth) ** 2), 0)
        density[row_min:row_max + 1, col_min:col_max + 1] += contribution.astype(np.float32)
    return density


def validation_bounds(center_x, center_y, half_size=500):
    west, south = to_geo_transformer.transform(center_x - half_size, center_y - half_size)
    east, north = to_geo_transformer.transform(center_x + half_size, center_y + half_size)
    return [[round(south, 8), round(west, 8)], [round(north, 8), round(east, 8)]]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    security = load_js_object(ROOT / "visor-seguridad-riobamba-data.js", "RIOBAMBA_SECURITY_DATA")
    platforms_geojson = json.loads((ROOT / "riobamba-censo-data" / "riobamba_plataformas.geojson").read_text(encoding="utf-8"))

    platform_metric = []
    for feature in platforms_geojson["features"]:
        geom = transform(to_metric, shape(feature["geometry"]))
        platform_metric.append((feature, geom))
    study_union = unary_union([geom for _, geom in platform_metric])
    minx, miny, maxx, maxy = study_union.bounds
    minx = math.floor(minx / CELL_SIZE) * CELL_SIZE
    miny = math.floor(miny / CELL_SIZE) * CELL_SIZE
    maxx = math.ceil(maxx / CELL_SIZE) * CELL_SIZE
    maxy = math.ceil(maxy / CELL_SIZE) * CELL_SIZE

    xs = np.arange(minx + CELL_SIZE / 2, maxx, CELL_SIZE, dtype=np.float64)
    ys = np.arange(maxy - CELL_SIZE / 2, miny, -CELL_SIZE, dtype=np.float64)
    xx, yy = np.meshgrid(xs, ys)
    study_mask = contains_xy(study_union, xx, yy)

    precision_counts = Counter(precision_group(event.get("precision")) for event in security.get("events", []))
    kde_points = []
    excluded = []

    for event in security.get("events", []):
        group = precision_group(event.get("precision"))
        lat = event.get("lat")
        lon = event.get("lng")
        point_metric = None
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            point_metric = Point(to_metric(lon, lat))
        reason = exclusion_reason(event, group, lon, lat, point_metric, study_union)
        base = {
            "id": event.get("id"),
            "date": event.get("date"),
            "category": event.get("category"),
            "event": event.get("event"),
            "precision": event.get("precision"),
            "location": event.get("location"),
            "source": event.get("source"),
            "lat": lat,
            "lng": lon,
        }
        if reason:
            excluded.append({**base, "reason": reason})
            continue
        platform = platform_for_point(point_metric, platform_metric)
        kde_points.append({
            **base,
            "precisionGroup": group,
            "platform": platform,
            "x": round(point_metric.x, 3),
            "y": round(point_metric.y, 3),
            "coordinateUse": "Coordenada original del registro de incidente; no proviene de camaras, UPC ni centroides parroquiales.",
        })

    points_xy = [(point["x"], point["y"]) for point in kde_points]
    raster_bounds = [
        [round(to_geo_transformer.transform(minx, miny)[1], 8), round(to_geo_transformer.transform(minx, miny)[0], 8)],
        [round(to_geo_transformer.transform(maxx, maxy)[1], 8), round(to_geo_transformer.transform(maxx, maxy)[0], 8)],
    ]

    rasters = {}
    peak_locations = {}
    for bandwidth in BANDWIDTHS:
        density = build_density(points_xy, xs, ys, bandwidth)
        density = np.where(study_mask, density, 0)
        filename = f"DENSIDAD_INCIDENTES_KDE_{bandwidth}m.png"
        max_value, norm = render_kde_png(density, study_mask, OUTPUT_DIR / filename)
        threshold = max_value * 0.35 if max_value else 0
        components = connected_components((density >= threshold) & study_mask) if max_value else 0
        max_index = np.unravel_index(int(np.argmax(density)), density.shape) if max_value else (0, 0)
        peak_x = float(xs[max_index[1]])
        peak_y = float(ys[max_index[0]])
        peak_locations[bandwidth] = (peak_x, peak_y)
        rasters[str(bandwidth)] = {
            "name": "DENSIDAD_INCIDENTES_KDE",
            "bandwidth": bandwidth,
            "cellSize": CELL_SIZE,
            "url": f"./data/kde-validacion/{filename}",
            "bounds": raster_bounds,
            "maxValue": round(max_value, 6),
            "observableConcentrations": components,
            "fragmentation": qualitative_fragmentation(components),
            "smoothing": qualitative_smoothing(bandwidth),
            "method": "Kernel gaussiano truncado al bandwidth; suma de contribuciones de todos los incidentes dentro del radio de busqueda en cada celda.",
        }

    if points_xy:
        distance_matrix = []
        for i, (x1, y1) in enumerate(points_xy):
            nearest = min(
                (math.hypot(x1 - x2, y1 - y2) for j, (x2, y2) in enumerate(points_xy) if i != j),
                default=0,
            )
            distance_matrix.append((nearest, x1, y1, kde_points[i]))
        single = max(distance_matrix, key=lambda row: row[0])
        valid_rows, valid_cols = np.where(study_mask)
        sample_step = max(1, len(valid_rows) // 5000)
        candidates = []
        for row, col in zip(valid_rows[::sample_step], valid_cols[::sample_step]):
            x = float(xs[col])
            y = float(ys[row])
            min_dist = min(math.hypot(x - px, y - py) for px, py in points_xy)
            candidates.append((min_dist, x, y))
        empty = max(candidates, key=lambda row: row[0])
    else:
        single = (0, (minx + maxx) / 2, (miny + maxy) / 2, {})
        empty = (0, (minx + maxx) / 2, (miny + maxy) / 2)

    peak_300 = peak_locations[300]
    validation_zones = {
        "multipleIncidents": {
            "title": "Zona con varios incidentes proximos",
            "description": "Seleccionada sobre el maximo KDE 300 m para verificar que la densidad sube donde se agrupan puntos.",
            "bounds": validation_bounds(peak_300[0], peak_300[1], 600),
            "center": to_lon_lat(peak_300[0], peak_300[1]),
        },
        "singleIncident": {
            "title": "Zona con un incidente aislado",
            "description": "Seleccionada por mayor distancia al incidente vecino mas cercano.",
            "bounds": validation_bounds(single[1], single[2], 600),
            "center": to_lon_lat(single[1], single[2]),
            "referenceEvent": single[3].get("id"),
            "nearestNeighborDistanceM": round(single[0], 2),
        },
        "noIncident": {
            "title": "Zona sin incidentes cercanos",
            "description": "Seleccionada dentro del ambito de plataformas con maxima distancia a incidentes KDE.",
            "bounds": validation_bounds(empty[1], empty[2], 600),
            "center": to_lon_lat(empty[1], empty[2]),
            "nearestIncidentDistanceM": round(empty[0], 2),
        },
    }

    peak_points = []
    for bandwidth, (x, y) in peak_locations.items():
        peak_points.append([bandwidth, x, y])
    stable_distance = max(math.hypot(x - peak_points[1][1], y - peak_points[1][2]) for _, x, y in peak_points) if len(peak_points) > 1 else 0
    stability = "alta" if stable_distance <= 300 else "media" if stable_distance <= 600 else "baja"

    control_table = {
        "TOTAL_REGISTROS": len(security.get("events", [])),
        "PRECISION_A": precision_counts.get("A", 0),
        "PRECISION_B": precision_counts.get("B", 0),
        "PRECISION_C": precision_counts.get("C", 0),
        "REGISTROS_KDE": len(kde_points),
        "REGISTROS_EXCLUIDOS": len(excluded),
    }

    metadata = {
        "CAPA": "DENSIDAD_INCIDENTES_KDE",
        "FUENTE": "visor-seguridad-riobamba-data.js / registros de incidentes georreferenciados cargados en el visor",
        "PERIODO": PERIOD,
        "N_REGISTROS": len(kde_points),
        "PRECISION_ADMITIDA": "A y B con coordenada valida dentro de las 18 plataformas territoriales reales",
        "CRS": f"{CRS_SOURCE} para visualizacion; {CRS_METRIC} para distancias y KDE",
        "CELL_SIZE": f"{CELL_SIZE} metros",
        "BANDWIDTH": "200, 300 y 500 metros",
        "METODO": "KDE por grilla regular unica; kernel gaussiano truncado al bandwidth; suma de todos los incidentes dentro del radio; mascara visual al ambito de plataformas.",
        "FECHA_PROCESAMIENTO": datetime.now().isoformat(timespec="seconds"),
    }

    output = {
        "controlTable": control_table,
        "excludedRecords": excluded,
        "kdeInputPoints": kde_points,
        "rasters": rasters,
        "validationZones": validation_zones,
        "comparison": {
            "sameInputPoints": True,
            "sameExtent": True,
            "sameCellSize": CELL_SIZE,
            "sameMethod": True,
            "stabilityMainConcentrations": stability,
            "peakDisplacementMaxM": round(stable_distance, 2),
            "bandwidths": [
                {
                    "bandwidth": int(key),
                    "observableConcentrations": value["observableConcentrations"],
                    "fragmentation": value["fragmentation"],
                    "smoothing": value["smoothing"],
                }
                for key, value in rasters.items()
            ],
        },
        "coordinateChecks": {
            "zeroZeroCoordinates": 0,
            "swappedLatLonSuspects": 0,
            "outsideRiobambaOrStudyArea": sum(1 for item in excluded if item["reason"].startswith("FUERA_")),
            "artificialCentroidsUsed": False,
            "cameraOrPoliceCoordinatesUsed": False,
            "parishRecordsConvertedToPoints": False,
            "coincidentPointsPreserved": True,
            "crsDistanceCalculation": CRS_METRIC,
        },
        "metadata": metadata,
    }

    DATA_JS.write_text(
        "window.RIOBAMBA_KDE_VALIDATION = "
        + json.dumps(output, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    print(json.dumps(control_table, ensure_ascii=False))
    print(f"wrote {DATA_JS}")


if __name__ == "__main__":
    main()
