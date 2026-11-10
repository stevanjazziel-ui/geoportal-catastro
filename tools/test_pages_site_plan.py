"""Preserve current viewer assets/downloads while omitting historical SIG scenes."""
from prepare_pages_site import plan,ROOT
included,excluded,keep=plan();included=set(included);excluded=set(excluded)
assert not included&excluded
assert sum((ROOT/p).stat().st_size for p in included)<1_000_000_000
for name in ['visor-seguridad-riobamba-v2.html','riobamba-camaras-propuesta.js','sig-bridge-active.json','data/seguridad-riobamba/COBERTURA_RECTA_20261110/LINEAS_PRINCIPALES_200M.geojson','data/seguridad-riobamba/COBERTURA_RECTA_20261110/EXTENSION_VISUAL_50M.geojson','data/seguridad-riobamba/COBERTURA_RECTA_20261110/BRECHA_MACAJI_TRAMO_200M.geojson','data/seguridad-riobamba/COBERTURA_RECTA_20261110/COBERTURA_LINEAL_Y_BRECHAS.gpkg','data/seguridad-riobamba/SIG_BRIDGE_RELEASES/CAMARAS_AJUSTADAS_USUARIO_20261109/ENTREGA_POLICIA_KDE.zip','data/seguridad-riobamba/SIG_BRIDGE_RELEASES/CAMARAS_AJUSTADAS_USUARIO_20261109/ESCENARIO_FINAL_183.gpkg']:
 assert name in included,name
assert all(p.startswith(('data/seguridad-riobamba/','.github/','sig-bridge/workspace/')) for p in excluded)
assert all((ROOT/p).is_file() for p in excluded)
print('PASS: site below 1 GB, current camera rays and GIS downloads retained, other portal files retained, repository history untouched.')
