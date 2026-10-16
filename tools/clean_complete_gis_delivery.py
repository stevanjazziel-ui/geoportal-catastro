"""Checkpoint the finished delivery and exclude failed-build temporary artifacts from its ZIP."""
import hashlib
import json
import sqlite3
import zipfile
from export_complete_viewer_gis import OUT,GPKG


def main():
    with sqlite3.connect(GPKG) as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute('PRAGMA journal_mode=DELETE')
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    # This plain project was produced by a failed early save, not the final QGZ.
    (OUT/'VISOR_RIOBAMBA.qgs').unlink(missing_ok=True)
    metadata=json.loads((OUT/'MANIFIESTO.json').read_text(encoding='utf-8'))
    metadata['deliveryPackageSha256']=hashlib.sha256(GPKG.read_bytes()).hexdigest()
    (OUT/'MANIFIESTO.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    validation=json.loads((OUT/'VALIDACION_QGIS.json').read_text(encoding='utf-8'))
    validation['gpkgMB']=GPKG.stat().st_size/1e6
    (OUT/'VALIDACION_QGIS.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
    archive=OUT.parent/(OUT.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zipped:
        for p in sorted(OUT.iterdir()):
            if p.is_file() and not p.name.endswith(('~','-wal','-shm')):zipped.write(p,OUT.name+'/'+p.name)
    with zipfile.ZipFile(archive) as zipped:assert zipped.testzip() is None
    print(json.dumps({'zip':str(archive),'sha256':metadata['deliveryPackageSha256'],'zipBytes':archive.stat().st_size,'integrity':'ok'}))


if __name__=='__main__':main()
