"""Reopen the portable QGIS project and verify data, render rules and ZIP integrity."""
import json
import os
import sqlite3
import zipfile
from collections import Counter
from pathlib import Path

os.environ['QT_QPA_PLATFORM']='offscreen'
from qgis.core import QgsApplication,QgsProject,QgsExpression,QgsExpressionContext,QgsExpressionContextUtils

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent/'entregas/VISOR_RIOBAMBA_QGIS_20261016'


def main():
    app=QgsApplication([],False);app.initQgis();project=QgsProject()
    assert project.read(str(OUT/'VISOR_RIOBAMBA.qgz')),project.error()
    bad=[layer.name() for layer in project.mapLayers().values() if not layer.isValid()]
    assert not bad,bad
    cameras=project.mapLayersByName('CAMARAS_EXISTENTES_103_FINAL')[0]
    expression=QgsExpression(cameras.renderer().classAttribute())
    context=QgsExpressionContext();context.appendScope(QgsExpressionContextUtils.layerScope(cameras))
    counts=Counter()
    for feature in cameras.getFeatures():
        context.setFeature(feature);counts[str(expression.evaluate(context))]+=1
    assert counts=={'CAMBIO':30,'SIN_CAMBIO':73},counts
    with sqlite3.connect(OUT/'VISOR_RIOBAMBA_COMPLETO.gpkg') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        counts_sql={name:db.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0] for name in
            ['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL']}
        assert list(counts_sql.values())==[103,50,30]
        approved=db.execute("SELECT COUNT(*) FROM PROPUESTA_MUNICIPAL_50_FINAL WHERE GRUPO='RED_ESTRUCTURAL' AND ESTADO='PROPUESTA_APROBADA_NO_INSTALADA'").fetchone()[0]
        assert approved==24
        srs=db.execute("SELECT DISTINCT srs_id FROM gpkg_contents WHERE data_type!='attributes'").fetchall()
        assert srs==[(32717,)],srs
        rasters=db.execute("SELECT COUNT(*) FROM gpkg_contents WHERE table_name LIKE 'KDE_%'").fetchone()[0]
        assert rasters==9
    archive=OUT.parent/(OUT.name+'.zip')
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        assert OUT.name+'/VISOR_RIOBAMBA.qgz' in zipped.namelist()
        assert OUT.name+'/VISOR_RIOBAMBA_COMPLETO.gpkg' in zipped.namelist()
    report={'projectReopened':True,'invalidLayers':bad,'cameraCounts':counts_sql,'existingSymbolCategories':dict(counts),
        'rastersInsideGeoPackage':rasters,'metricCrs':'EPSG:32717','zipIntegrity':'ok','layers':len(project.mapLayers())}
    (OUT/'VALIDACION_REAPERTURA.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(OUT.iterdir()):
            if path.is_file() and not path.name.endswith('~'):zipped.write(path,OUT.name+'/'+path.name)
    print(json.dumps(report),flush=True)
    os._exit(0)


if __name__=='__main__':main()
