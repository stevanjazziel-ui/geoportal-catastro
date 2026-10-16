"""Synchronize approved municipal status labels; never change geometry or analytical values."""
import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path
from shapely import from_wkb

from build_final_municipal_axis_release import OUT as RELEASE
from export_complete_viewer_gis import OUT as DELIVERY


def write(path,value,compact=False):
    path.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=None if compact else 2),encoding='utf-8')


def main():
    geo=json.loads((RELEASE/'PROPUESTA_MUNICIPAL_50_FINAL.geojson').read_text(encoding='utf-8'))
    updates={}
    for f in geo['features']:
        p=f['properties']
        if p['GRUPO']!='RED_ESTRUCTURAL':continue
        p.update({'ESTADO':'PROPUESTA_APROBADA_NO_INSTALADA','DECISION_FINAL':'NODOS_EJES_APROBADOS',
            'ESTADO_VALIDACION':'EXCEPCION_LOCAL_MACAJI_APROBADA' if p['ID_PROPUESTA']=='MUN-037' else 'CRUCE_PRINCIPAL_COMPROBADO',
            'JUSTIFICACION':'Ubicacion aprobada en '+p['INTERSECCION_O_NODO']+'. '+str(p.get('OBSERVACION_MANUAL') or '')+' Enlaces potenciales por misma via; no certifica vision real.'})
        updates[p['ID_PROPUESTA']]={k:p[k] for k in ('ESTADO','DECISION_FINAL','ESTADO_VALIDACION','JUSTIFICACION')}
    assert len(updates)==24
    for package in (RELEASE/'ESCENARIO_FINAL_183.gpkg',DELIVERY/'VISOR_RIOBAMBA_COMPLETO.gpkg'):
        with sqlite3.connect(package) as db:
            def geometry(blob):
                if blob is None:return None
                envelope=(blob[3]>>1)&7
                offset=8+{0:0,1:32,2:48,3:48,4:64}[envelope]
                return from_wkb(blob[offset:])
            db.create_function('ST_IsEmpty',1,lambda b:1 if b is None or geometry(b).is_empty else 0)
            for name,index in [('ST_MinX',0),('ST_MinY',1),('ST_MaxX',2),('ST_MaxY',3)]:
                db.create_function(name,1,lambda b,i=index:None if b is None or geometry(b).is_empty else geometry(b).bounds[i])
            tables=db.execute("SELECT table_name,column_name FROM gpkg_geometry_columns").fetchall()
            before={name:db.execute(f'SELECT "{column}" FROM "{name}"').fetchall() for name,column in tables}
            for name,column in tables:
                fields={r[1] for r in db.execute(f'PRAGMA table_info("{name}")')}
                if 'ID_PROPUESTA' not in fields:continue
                for key,values in updates.items():
                    allowed={k:v for k,v in values.items() if k in fields}
                    if not allowed:continue
                    clause=', '.join('"'+k+'"=?' for k in allowed)
                    db.execute(f'UPDATE "{name}" SET '+clause+' WHERE ID_PROPUESTA=?',list(allowed.values())+[key])
            assert all(before[name]==db.execute(f'SELECT "{column}" FROM "{name}"').fetchall() for name,column in tables)
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    write(RELEASE/'PROPUESTA_MUNICIPAL_50_FINAL.geojson',geo)
    package=RELEASE/'ESCENARIO_FINAL_183.gpkg'
    digest=hashlib.sha256(package.read_bytes()).hexdigest()
    gaps=json.loads((RELEASE/'coverage-inputs/RESULTADOS.json').read_text(encoding='utf-8'))
    gaps['metadata']['sourceHashes'][str(package)]=digest
    text=json.dumps(gaps,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    (RELEASE/'coverage-inputs/RESULTADOS.json').write_text(text,encoding='utf-8')
    (RELEASE/'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = '+text+';\n',encoding='utf-8')
    metadata=json.loads((DELIVERY/'MANIFIESTO.json').read_text(encoding='utf-8'));metadata['sourcePackageSha256']=digest
    write(DELIVERY/'MANIFIESTO.json',metadata)
    proof={'urbanStatusSynchronized':24,'geometryUnchanged':True,'analyticalValuesUnchanged':True,'sourcePackageSha256':digest}
    write(DELIVERY/'VALIDACION_ESTADOS.json',proof);write(RELEASE/'VALIDACION_ESTADOS.json',proof)
    for folder,name in [(RELEASE/'coverage-inputs','BRECHAS_ACTUALIZADAS.zip'),(RELEASE,'ENTREGA_POLICIA_KDE.zip')]:
        with zipfile.ZipFile(folder/name,'w',zipfile.ZIP_DEFLATED) as archive:
            for p in sorted(folder.iterdir()):
                if p.is_file() and p.suffix!='.zip':archive.write(p,p.name)
    archive=DELIVERY.parent/(DELIVERY.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zipped:
        for p in sorted(DELIVERY.iterdir()):
            if p.is_file() and not p.name.endswith('~'):zipped.write(p,DELIVERY.name+'/'+p.name)
    print(json.dumps(proof),flush=True)


if __name__=='__main__':main()
