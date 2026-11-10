"""Activate the verified adjusted-camera release authorized for publication."""
import json,zipfile
from apply_adjusted_cameras_20261109 import ROOT,OUT,RELEASE
from bridge.store import read_json,write_json,require
def main():
 proof=read_json(OUT/'VERIFICACION_INDEPENDIENTE.json')
 require(proof.get('all183GeometriesEqualApprovedSource') is True,'Falta validacion de posiciones ajustadas')
 proof['approvedGeometryExceptions']=read_json(OUT/'VALIDACION.json').get('approvedGeometryException',{}).get('warnings',[])
 write_json(OUT/'VERIFICACION_INDEPENDIENTE.json',proof)
 validation=read_json(OUT/'VALIDACION_IMPORTACION_Y_RADIOS.json')
 require(validation['combined183CoverageExact'],'Cobertura no coincide')
 for name in ['RESULTADOS.json','APROBACION_Y_FUENTES.json']:
  d=read_json(OUT/name);d['published']=True;d['publicationRequested']=True;write_json(OUT/name,d)
 with zipfile.ZipFile(OUT/'ENTREGA_POLICIA_KDE.zip','w',zipfile.ZIP_DEFLATED) as z:
  for p in sorted(OUT.rglob('*')):
   if p.is_file() and p.suffix!='.zip' and not p.name.endswith('~'):z.write(p,p.relative_to(OUT).as_posix())
 write_json(ROOT/'sig-bridge-active.json',{'schemaVersion':1,'root':'./'+OUT.relative_to(ROOT).as_posix()+'/','releaseId':RELEASE,'coverageData':'riobamba-brechas-actualizadas-data.js'})
 print('RELEASE_ACTIVA_LOCAL',RELEASE,flush=True)
if __name__=='__main__':main()
