import json
import pathlib

import pyproj
import shapefile


BASE = pathlib.Path(__file__).resolve().parents[1]
SRC = BASE / "policia_sig_06d01"
OUT = BASE / "policia-06d01-data.js"

TRANSFORMER = pyproj.Transformer.from_crs("EPSG:32717", "EPSG:4326", always_xy=True)


def norm(value):
    if value is None:
        return ""
    return str(value).strip()


def transform_point(point):
    lon, lat = TRANSFORMER.transform(point[0], point[1])
    return [round(lon, 7), round(lat, 7)]


def polygon_geometry(shape):
    points = shape.points
    parts = list(shape.parts) + [len(points)]
    rings = []
    for start, end in zip(parts, parts[1:]):
        ring = [transform_point(point) for point in points[start:end]]
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        if len(ring) >= 4:
            rings.append(ring)
    return {"type": "Polygon", "coordinates": rings}


def point_geometry(shape):
    return {"type": "Point", "coordinates": transform_point(shape.points[0])}


def read_layer(name, keep_fields, geometry_reader):
    reader = shapefile.Reader(str(SRC / f"{name}.shp"), encoding="utf-8")
    fields = [field[0] for field in reader.fields[1:]]
    features = []
    for shape_record in reader.iterShapeRecords():
        record = dict(zip(fields, shape_record.record))
        props = {target: norm(record.get(source)) for source, target in keep_fields.items()}
        for key in ("areaKm2", "population", "personnel", "vehicles", "motorcycles"):
            if key in props and props[key] != "":
                try:
                    props[key] = round(float(props[key]), 2)
                except ValueError:
                    pass
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": geometry_reader(shape_record.shape),
            }
        )
    return {"type": "FeatureCollection", "features": features}


data = {
    "sourceZip": r"C:\Users\PC\Downloads\Paquete_SIG_Policia_06D01_Riobamba.zip",
    "crs": "EPSG:32717 convertido a WGS84 para Leaflet",
    "district": read_layer(
        "Distrito_06D01",
        {
            "cod_distri": "code",
            "nam_distri": "name",
            "zona": "zone",
            "comando": "command",
            "dpa_despro": "province",
        },
        polygon_geometry,
    ),
    "circuits": read_layer(
        "Circuitos_06D01",
        {
            "cod_circui": "code",
            "nam_circui": "name",
            "cod_distri": "districtCode",
            "zona": "zone",
            "comando": "command",
            "areakm": "areaKm2",
        },
        polygon_geometry,
    ),
    "subcircuits": read_layer(
        "Subcircuitos_06D01",
        {
            "cod_subcir": "code",
            "nam_subcir": "name",
            "cod_circui": "circuitCode",
            "nam_circui": "circuit",
            "tipo": "type",
            "clase": "class",
            "poblacion": "population",
            "infraestru": "infrastructure",
            "categoria": "category",
            "areakm": "areaKm2",
            "tipo_upc": "upcType",
        },
        polygon_geometry,
    ),
    "infrastructure": read_layer(
        "Infraestructura_Policial_06D01",
        {
            "codigo_inf": "code",
            "tipo_infra": "type",
            "nombre_inf": "name",
            "direccion_": "address",
            "estado_de_": "status",
            "modelo": "model",
            "condicion_": "condition",
            "cod_circui": "circuitCode",
            "nombre_cir": "circuit",
            "cod_subcir": "subcircuitCode",
            "nombre_sub": "subcircuit",
            "total_de_p": "personnel",
            "total_de_1": "vehicles",
            "total_de_m": "motorcycles",
            "observacio": "observation",
        },
        point_geometry,
    ),
}

data["summary"] = {
    "districts": len(data["district"]["features"]),
    "circuits": len(data["circuits"]["features"]),
    "subcircuits": len(data["subcircuits"]["features"]),
    "infrastructure": len(data["infrastructure"]["features"]),
}

OUT.write_text(
    "window.RIOBAMBA_POLICE_SIG_DATA = "
    + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    + ";\n",
    encoding="utf-8",
)
print(f"Wrote {OUT} with {data['summary']}")
