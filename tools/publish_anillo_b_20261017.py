"""Promote the validated local B delivery; no new camera optimization or recalculation."""
import argparse
import json
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import pyogrio
from scipy.spatial import cKDTree
from shapely import union_all

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sig-bridge'))
from bridge.engine import verify_derived
from bridge.store import Store,read_json,write_json,require,digest,now

SOURCE=Path('D:/codex/entregas/ANILLO_B_APLICADA_LOCAL_20261017')
RELEASE='ANILLO_B_350M_5_URBANAS_20261017'
OUT=ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES'/RELEASE
PREVIOUS=ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/REUNION_MUNICIPALES_BOYACA_20261017'
AUTH='Usuario: ok publica, despues de seleccionar B y verificar su aplicacion local. Publicar exactamente las5urbanas aprobadas con excepcion350m.'

def read(path,layer):return pyogrio.read_dataframe(path,layer=layer)

def validate():
    package=OUT/'ESCENARIO_FINAL_183.gpkg'
    expected_ids={'MUN-028','MUN-036','MUN-044','MUN-046','MUN-050'}
    frames={}
    for layer,count,field in [('CAMARAS_EXISTENTES_103_FINAL',103,'ID_CAMARA'),('PROPUESTA_MUNICIPAL_50_FINAL',50,'ID_PROPUESTA'),('PROPUESTA_POLICIA_30_FINAL',30,'ID_POLICIA')]:
        frame=read(package,layer);expected=read(SOURCE/'ESCENARIO_FINAL_183.gpkg',layer).set_index(field).loc[frame[field]]
        require(len(frame)==count and frame[field].is_unique,'Count/ID mismatch')
        require(frame.geometry.to_wkb().tolist()==expected.geometry.to_wkb().tolist(),'Geometry differs from approved B')
        frames[layer]=frame
    e,m,p=[frames[n] for n in ['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL']]
    old=read(PREVIOUS/'ESCENARIO_FINAL_183.gpkg','PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA').loc[m.ID_PROPUESTA]
    changed=m.geometry.to_wkb().to_numpy()!=old.geometry.to_wkb().to_numpy()
    require(set(m.loc[changed,'ID_PROPUESTA'])==expected_ids,'Unexpected municipal move')
    require(m.loc[changed,'GRUPO'].eq('RED_ESTRUCTURAL').all(),'Non-urban changed')
    require(m.GRUPO.value_counts().to_dict()==dict(RED_ESTRUCTURAL=24,CABECERA_RURAL=22,LAS_ABRAS=4),'Composition mismatch')
    nearest={}
    for i,row in m.loc[changed].iterrows():
        others=list(e.geometry)+list(p.geometry)+list(m.drop(index=i).geometry)
        distance=cKDTree(np.array([[g.x,g.y] for g in others])).query([row.geometry.x,row.geometry.y])[0]
        require(distance>=350-1e-8,'Spacing violation');nearest[row.ID_PROPUESTA]=float(distance)
    for code,groups in [('A',[e]),('B',[e,m]),('C',[e,m,p])]:
        expected=union_all([g.buffer(200,quad_segs=64) for f in groups for g in f.geometry])
        actual=read(package,'COBERTURA_'+code).geometry.iloc[0]
        require(expected.symmetric_difference(actual).area<.01,'Buffer mismatch')
    results=read_json(OUT/'RESULTADOS.json')
    for code,target in [('B',75.17190782355411),('C',82.73296254043306)]:
        rows={r['CORREDOR']:r for r in results['corridors'] if r['ESCENARIO']==code}
        require(abs(rows['ANILLO_VIAL']['PCT_CUBIERTO']-target)<1e-7,'Wrong Anillo coverage')
        require(rows['BOULEVARD_MACAJI_BELLAVISTA']['NO_CUBIERTO_M']<=.01,'Macaji gap')
    store=Store();store.base=PREVIOUS/'ESCENARIO_FINAL_183.gpkg';verify_derived(store,package,results)
    gaps=read_json(OUT/'coverage-inputs/RESULTADOS.json')
    require(len(gaps['inventoryCameraOverlay'])==103,'Inventory overlay mismatch')
    require(sum(r.get('provisional',False) for r in gaps['inventoryCameraOverlay'])==19,'Provisional quality lost')
    for layer,field in [('PROPUESTA_MUNICIPAL_50_FINAL','ID_PROPUESTA'),('PROPUESTA_POLICIA_30_FINAL','ID_POLICIA')]:
        web=read_json(OUT/(layer+'.geojson'))
        require(len(web['features'])==len(frames[layer]),'GeoJSON mismatch')
        local=read_json(SOURCE/(layer+'.geojson'))
        require(web==local,'Web camera data altered')
    combined=read_json(OUT/'ESCENARIO_FINAL_183.geojson')
    require(len(combined['features'])==183,'Combined web data stale')
    return dict(passed=True,approvedBExactly=True,urbanMoved=5,nearestNewDestinationsM=nearest,existing103Fixed=True,police30Fixed=True,rural22Fixed=True,abras4Fixed=True,boyacaPairFixed=True,
                buffers200mChecked=True,giKdeUnchanged=True,physicalVisionVerified=False,authorization=AUTH,approvedForPublication=True)

def build():
    require(not OUT.exists(),'Never overwrite release history')
    proof=read_json(SOURCE/'VERIFICACION_INDEPENDIENTE.json')
    require(proof['passed'] and proof['applied'] and not proof['published'],'No validated local B')
    for path,value in proof['sourceHashes'].items():require(digest(Path(path))==value,'Protected source changed: '+path)
    OUT.mkdir(parents=True)
    extensions={'.json','.geojson','.csv','.md','.js','.gpkg','.tif'}
    for path in SOURCE.iterdir():
        if path.is_file() and path.suffix in extensions and not path.name.startswith('SERVIDOR_'):shutil.copy2(path,OUT/path.name)
    shutil.copytree(SOURCE/'coverage-inputs',OUT/'coverage-inputs')
    results=read_json(OUT/'RESULTADOS.json')
    results.update(status='ANILLO_B_APROBADA_PUBLICACION',sourcePackage=RELEASE,published=True,authorization=AUTH,publishedPreparationAt=now())
    results['bridge'].update(published=True,authorization=AUTH)
    write_json(OUT/'RESULTADOS.json',results)
    validation=read_json(OUT/'VALIDACION.json');validation.update(published=True,authorization=AUTH);write_json(OUT/'VALIDACION.json',validation)
    receipt=read_json(OUT/'APROBACION_Y_FUENTES.json');receipt.update(publicationAuthorization=AUTH,approvedForPublication=True,localDeliveryPreserved=True,publicRelease=RELEASE);write_json(OUT/'APROBACION_Y_FUENTES.json',receipt)
    (OUT/'INFORME_FINAL.md').write_text('# Alternativa B aprobada para publicacion\n\n103 existentes y30 policiales sin cambios. 50 municipales:22rurales y4LasAbras fijas,24urbanas; cinco movimientos MUN028,036,044,046,050. Boyaca027/047 fijas. Excepcion minima350m aprobada para nuevos destinos.\n\nAnillo municipal75.17%; conPolicia82.73%. Macaji100%,0m sin cubrir. Ciclovias municipal61.45%; conPolicia62.18%.\n\nConPolicia se mantiene total D/V y CMI, no cada categoria: delincuencia-5,violencia+5,convivencia-57. SinPolicia D/V-2 y CMI-1.\n\nLas coberturas e indicadores100/150/200m fueron recalculados en la entrega local y se publican sin modificar coordenadas ni reoptimizar. KDE/Gi* sin recalculo.19 existentes siguen provisionales. Buffers y continuidad por vias no certifican vision optica ni poste.\n',encoding='utf-8')
    newproof=validate();write_json(OUT/'VERIFICACION_INDEPENDIENTE.json',newproof)
    with sqlite3.connect(OUT/'ESCENARIO_FINAL_183.gpkg') as db:
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Invalid package');db.execute('PRAGMA wal_checkpoint(TRUNCATE)');db.execute('PRAGMA journal_mode=DELETE')
    print(json.dumps(newproof,ensure_ascii=True,indent=2))

def package():
    require(read_json(OUT/'VERIFICACION_INDEPENDIENTE.json')['passed'],'No verification')
    receipt=read_json(OUT/'APROBACION_Y_FUENTES.json')
    if receipt['authorization']!=AUTH:receipt['localApplicationAuthorization']=receipt['authorization']
    receipt.update(authorization=AUTH,published=True)
    write_json(OUT/'APROBACION_Y_FUENTES.json',receipt)
    with zipfile.ZipFile(OUT/'ENTREGA_POLICIA_KDE.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.iterdir()):
            if path.is_file() and path.suffix!='.zip':archive.write(path,path.name)
    print('ZIP refreshed for publication.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--validate-only',action='store_true');parser.add_argument('--package-only',action='store_true');args=parser.parse_args()
    if args.validate_only:print(json.dumps(validate(),indent=2))
    elif args.package_only:package()
    else:build()
