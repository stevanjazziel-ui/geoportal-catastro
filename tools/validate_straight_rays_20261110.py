"""Independent metric checks: exact camera origins, no bends, collinear 50m."""
import json,pathlib
import geopandas as gpd
from shapely.geometry import Point,LineString
from shapely import union_all
R=pathlib.Path(__file__).resolve().parents[1];O=R/'data/seguridad-riobamba/COBERTURA_RECTA_20261110';B=R/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/CAMARAS_AJUSTADAS_USUARIO_20261109'
def main():
 cameras={}
 for layer,key in [('CAMARAS_EXISTENTES_103_FINAL','ID_CAMARA'),('PROPUESTA_MUNICIPAL_50_FINAL','ID_PROPUESTA'),('PROPUESTA_POLICIA_30_FINAL','ID_POLICIA')]:
  d=gpd.read_file(B/'ESCENARIO_FINAL_183.gpkg',layer=layer);cameras.update(zip(d[key],d.geometry))
 a=gpd.read_file(O/'LINEAS_PRINCIPALES_200M.geojson').to_crs(32717);b=gpd.read_file(O/'EXTENSION_VISUAL_50M.geojson').to_crs(32717);ext={(r.ID_CAMARA,r.BRAZO):r.geometry for r in b.itertuples()}
 for r in a.itertuples():
  p=cameras[r.ID_CAMARA];line=r.geometry;e=ext[(r.ID_CAMARA,r.BRAZO)]
  assert len(line.coords)==len(e.coords)==2
  assert Point(line.coords[0]).distance(p)<1e-6
  assert abs(line.length-200)<1e-6 and abs(e.length-50)<1e-6
  assert Point(line.coords[-1]).distance(Point(e.coords[0]))<1e-6
  assert LineString([line.coords[0],e.coords[-1]]).distance(Point(line.coords[-1]))<1e-6
 axis=union_all(gpd.read_file(B/'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA/TRAMO_BOULEVARD_MACAJI_BELLAVISTA.geojson').to_crs(32717).geometry)
 expected=axis.difference(union_all([p.buffer(200,quad_segs=64) for p in cameras.values()]));gaps=union_all(gpd.read_file(O/'BRECHA_MACAJI_TRAMO_200M.geojson').to_crs(32717).geometry)
 assert expected.hausdorff_distance(gaps)<1e-6 and abs(expected.length-gaps.length)<1e-6
 previous=json.loads((R/'data/seguridad-riobamba/COBERTURA_DIRECCIONAL_20261110/RESUMEN.json').read_text(encoding='utf-8'));summary=json.loads((O/'RESUMEN.json').read_text(encoding='utf-8'))
 assert summary['sourceCameraGeometrySha256']==previous['sourceCameraGeometrySha256']
 assert abs(summary['uncoveredMacaji200M']-previous['uncoveredMacaji200M'])<1e-8
 report={'passed':True,'straightPrimaryRays':len(a),'collinearVisualExtensions':len(b),'twoVerticesPerLine':True,'exactCameraOrigins':True,'primaryLengthM':200,'visualExtensionLengthM':50,'cameraCoordinatesUnchanged':True,'gapMethodUnchanged':True,'extra50NotIncluded':True,'macajiUncoveredM':expected.length}
 (O/'VERIFICACION_RECTAS.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
