"""Check release inventory, exact approved locations and optional public data."""
import argparse
import json
import sqlite3
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pyogrio

ROOT=Path(__file__).resolve().parents[1]
RELEASE='MACAJI_COMPENSACION_021_043_20261021'
OUT=ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES'/RELEASE
BASE=ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/MUN045_CRUCE_PRENSA_9OCTUBRE_20261019/ESCENARIO_FINAL_183.gpkg'
APPROVED=Path(r'D:\codex\entregas\MACAJI_COMPENSACION_MUN021_043_20261021\MACAJI_BELLAVISTA_ESPEJO_PRIMERA.gpkg')


def main(public=False):
    pointer=json.loads((ROOT/'sig-bridge-active.json').read_text(encoding='utf-8'))
    assert pointer['releaseId']==RELEASE
    package=OUT/'ESCENARIO_FINAL_183.gpkg'
    actual=pyogrio.read_dataframe(package,layer='PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    approved=pyogrio.read_dataframe(APPROVED,layer='MUNICIPALES_50_CONTINUIDAD').set_index('ID_PROPUESTA')
    baseline=pyogrio.read_dataframe(BASE,layer='PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    assert len(actual)==50 and actual.index.is_unique and set(actual.index)==set(approved.index)
    assert all(actual.loc[key].geometry.wkb==approved.loc[key].geometry.wkb for key in actual.index)
    for key in ('MUN-028','MUN-047'):
        assert actual.loc[key].geometry.wkb==baseline.loc[key].geometry.wkb
    for key,target in [('MUN-021','MUN-040'),('MUN-043','MUN-041')]:
        assert actual.loc[key].geometry.wkb==baseline.loc[target].geometry.wkb
    for name,count in [('CAMARAS_EXISTENTES_103_FINAL',103),('PROPUESTA_POLICIA_30_FINAL',30),('UPC_INFRAESTRUCTURA',18)]:
        old=pyogrio.read_dataframe(BASE,layer=name)
        new=pyogrio.read_dataframe(package,layer=name)
        assert len(new)==count and old.geometry.to_wkb().tolist()==new.geometry.to_wkb().tolist()
    municipal_json=json.loads((OUT/'PROPUESTA_MUNICIPAL_50_FINAL.geojson').read_text(encoding='utf-8'))
    assert len(municipal_json['features'])==50
    for feature in municipal_json['features']:
        props=feature['properties']
        point=actual.loc[props['ID_PROPUESTA']].geometry
        assert abs(props['X']-point.x)<1e-6 and abs(props['Y']-point.y)<1e-6
    assert len(json.loads((OUT/'ESCENARIO_FINAL_183.geojson').read_text(encoding='utf-8'))['features'])==183
    required=['RESULTADOS.json','CAMARAS_EXISTENTES_103_FINAL.geojson','PROPUESTA_MUNICIPAL_50_FINAL.geojson',
        'PROPUESTA_POLICIA_30_FINAL.geojson','RADIOS_EXISTENTES_SIMBOLOGIA_200M.geojson','COBERTURA_MUNICIPAL_200M.geojson',
        'COBERTURA_POLICIA_200M.geojson','PLATAFORMAS_TERRITORIALES.geojson','CORREDORES.geojson',
        'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA/TRAMO_BOULEVARD_MACAJI_BELLAVISTA.geojson']
    required+=['BRECHA_'+name+'_FINAL.geojson' for name in ('MACAJI','ANILLO','CICLOVIAS','LAS_ABRAS')]
    for name in required:
        assert (OUT/name).is_file(),name
        json.loads((OUT/name).read_text(encoding='utf-8'))
    with sqlite3.connect(package) as db:
        assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
    if public:
        origin='https://stevanjazziel-ui.github.io/geoportal-catastro/'
        def get(url):
            with urlopen(Request(url,headers={'Cache-Control':'no-cache','User-Agent':'Riobamba-release-check'}),timeout=30) as response:
                assert response.status==200
                return json.load(response)
        remote_pointer=get(origin+'sig-bridge-active.json?verify='+str(time.time_ns()))
        assert remote_pointer['releaseId']==RELEASE,remote_pointer
        remote=get(origin+remote_pointer['root'].removeprefix('./')+'PROPUESTA_MUNICIPAL_50_FINAL.geojson')
        assert remote==municipal_json
    print(json.dumps({'passed':True,'public':public,'release':RELEASE,'municipal':50,
        'existing_intact':103,'police_intact':30,'upc_intact':18,'fixed':['MUN-028','MUN-047'],
        'destinations':{'MUN-021':'Esmeraldas x Eugenio Espejo','MUN-043':'Primera Constituyente x Brasil'}}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--public',action='store_true')
    main(parser.parse_args().public)
