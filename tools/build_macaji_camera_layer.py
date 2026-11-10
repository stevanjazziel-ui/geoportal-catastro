"""Select cameras on the approved axis using a 30 m road-position tolerance."""
import json
from pathlib import Path
import geopandas as gpd
from shapely import union_all

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / json.loads((ROOT / 'sig-bridge-active.json').read_text())['root']
axis = union_all(gpd.read_file(BASE / 'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA/TRAMO_BOULEVARD_MACAJI_BELLAVISTA.geojson').to_crs(32717).geometry)
features = []
for group, filename in [('existing', 'CAMARAS_EXISTENTES_103_FINAL'), ('municipal', 'PROPUESTA_MUNICIPAL_50_FINAL'), ('police', 'PROPUESTA_POLICIA_30_FINAL')]:
    source = json.loads((BASE / (filename + '.geojson')).read_text(encoding='utf-8'))
    projected = gpd.GeoDataFrame.from_features(source['features'], crs=4326).to_crs(32717)
    for feature, distance in zip(source['features'], projected.distance(axis)):
        if distance <= 30:
            feature['properties'].update(GRUPO_ORIGEN_VISOR=group, DISTANCIA_EJE_M=float(distance), TOLERANCIA_EJE_M=30)
            features.append(feature)
out = ROOT / 'data/seguridad-riobamba/COBERTURA_RECTA_20261110/CAMARAS_MACAJI_BELLAVISTA.geojson'
out.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'{len(features)} cameras; existing={sum(f["properties"]["GRUPO_ORIGEN_VISOR"] == "existing" for f in features)}; municipal={sum(f["properties"]["GRUPO_ORIGEN_VISOR"] == "municipal" for f in features)}')
