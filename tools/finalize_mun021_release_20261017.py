"""Finalize a successfully recalculated MUN-021 release before activation."""
import json
import sqlite3
import zipfile
import sys
from pathlib import Path
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sig-bridge'))
from bridge.store import read_json, write_json, require
from apply_mun021_lican_20261017 import OUT, RELEASE

def main():
    proof = read_json(OUT/'VERIFICACION_INDEPENDIENTE.json')
    require(proof['passed'] and proof['changedMunicipal']==['MUN-021'], 'No successful independent validation')
    results = read_json(OUT/'RESULTADOS.json')
    for name, rows in [('POLICIA_BENEFICIO_FINAL', results['policeMetrics']),('INCIDENTES_CUBIERTOS_FINAL', results['incidents']),('HOTSPOTS_ATENDIDOS_FINAL',results['hotspots']),('CORREDORES_CUBIERTOS_FINAL',results['corridors'])]:
        # Re-export from the current, recalculated package to avoid stale downloads.
        frame = pyogrio.read_dataframe(OUT/'ESCENARIO_FINAL_183.gpkg',layer=name)
        frame.to_csv(OUT/(name+'.csv'),index=False,encoding='utf-8-sig')
    receipt = read_json(OUT/'APROBACION_Y_FUENTES.json')
    police_moves = pyogrio.read_dataframe(OUT/'ESCENARIO_FINAL_183.gpkg',layer='MOVIMIENTOS_POLICIA_30')
    police_moves.to_csv(OUT/'MOVIMIENTOS_POLICIA_30.csv',index=False,encoding='utf-8-sig')
    (OUT/'MOVIMIENTOS_MUNICIPALES.csv').write_text('ID,DESPLAZAMIENTO_M,DESTINO\nMUN-021,673.2695857006688,Pedro Vicente Maldonado x Hurones\n',encoding='utf-8')
    for filename in ['RESULTADOS.json','VALIDACION.json','VERIFICACION_INDEPENDIENTE.json','APROBACION_Y_FUENTES.json']:
        data = read_json(OUT/filename)
        data.update(published=True, publicRelease=RELEASE)
        if filename=='RESULTADOS.json': data['bridge'].update(published=True)
        write_json(OUT/filename,data)
    with sqlite3.connect(OUT/'ESCENARIO_FINAL_183.gpkg') as db:
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Invalid GPKG')
    with zipfile.ZipFile(OUT/'ENTREGA_POLICIA_KDE.zip','w',zipfile.ZIP_DEFLATED) as z:
        for path in OUT.iterdir():
            if path.is_file() and path.suffix!='.zip': z.write(path,path.name)
    print(json.dumps(dict(passed=True,release=RELEASE,files=len(list(OUT.iterdir())))))

if __name__=='__main__': main()
