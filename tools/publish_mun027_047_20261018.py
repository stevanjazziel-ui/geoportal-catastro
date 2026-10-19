"""Publish the approved MUN-027/047 move and recalculate package."""
import json, sqlite3, sys, zipfile
from pathlib import Path
import pyogrio
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sig-bridge'))
from bridge.store import Store,read_json,write_json,require,digest
RELEASE='MUN027_047_CANONIGO_DUCHICELA_20261018'
BASELINE='MUN035_040_GUAYAQUIL_ESMERALDAS_20261018'
OUT=ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES'/RELEASE
def read(path,layer): return pyogrio.read_dataframe(path,layer=layer).to_crs(32717)
def main():
    store=Store(); pointer_path=ROOT/'sig-bridge-active.json'; pointer=read_json(pointer_path)
    require(pointer['releaseId']==BASELINE,'Active public release changed')
    validation=read_json(OUT/'VALIDACION.json')
    require(not validation['publishBlocks'],'Unwaived validation blocks remain')
    proof=read_json(OUT/'VERIFICACION_INDEPENDIENTE.json')
    require(proof['passed'] and proof['changedMunicipal']==['MUN-027','MUN-047'],'Move verification failed')
    require(proof['existing103Fixed'] and proof['police30Fixed'] and proof['otherMunicipal48Fixed'],'Protected camera layer changed')
    require(abs(proof['macajiMunicipalPct']-97.74207666073576)<1e-7,'Previously approved Macaji exception changed')
    package=OUT/'ESCENARIO_FINAL_183.gpkg'; old=store.web/'ESCENARIO_FINAL_183.gpkg'
    require(pyogrio.read_info(package,layer='ESCENARIO_FINAL_183')['features']==183,'Scenario count mismatch')
    for layer in ['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_POLICIA_30_FINAL']:
        require(read(package,layer).geometry.to_wkb().tolist()==read(old,layer).geometry.to_wkb().tolist(),f'{layer} differs from baseline')
    a=read(old,'PROPUESTA_MUNICIPAL_50_FINAL'); b=read(package,'PROPUESTA_MUNICIPAL_50_FINAL')
    changed=set(b.loc[b.geometry.to_wkb().to_numpy()!=a.geometry.to_wkb().to_numpy(),'ID_PROPUESTA'])
    require(changed=={'MUN-027','MUN-047'},f'Unexpected municipal changes: {changed}')
    layer_dir=OUT/'CAPA_TRAMO_BOULEVARD_MACAJI_BELLAVISTA'
    require((layer_dir/'TRAMO_BOULEVARD_MACAJI_BELLAVISTA.gpkg').exists(),'Standalone Macaji layer missing')
    require((layer_dir/'TRAMO_BOULEVARD_MACAJI_BELLAVISTA.geojson').exists(),'Standalone Macaji GeoJSON missing')
    results=read_json(OUT/'RESULTADOS.json')
    require(results['published'] is False and results['bridge']['status']=='READY_WITH_USER_APPROVED_EXCEPTION','Exceptions not traced')
    receipt=read_json(OUT/'APROBACION_Y_FUENTES.json')
    require(all(Path(p).exists() and digest(Path(p))==h for p,h in receipt['baseHashes'].items() if Path(p).name!='sig-bridge-active.json'),'Source hashes changed')
    for name in ['RESULTADOS.json','VALIDACION.json','VERIFICACION_INDEPENDIENTE.json','APROBACION_Y_FUENTES.json']:
        data=read_json(OUT/name); data.update(published=True,publicRelease=RELEASE)
        if name=='RESULTADOS.json': data['bridge']['published']=True
        write_json(OUT/name,data)
    pointer.update(root='./data/seguridad-riobamba/SIG_BRIDGE_RELEASES/'+RELEASE+'/',releaseId=RELEASE)
    write_json(pointer_path,pointer)
    archive_path=OUT/'ENTREGA_POLICIA_KDE.zip'
    with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in OUT.rglob('*'):
            if path.is_file() and path!=archive_path: archive.write(path,path.relative_to(OUT))
    with sqlite3.connect(package) as db:
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Invalid GeoPackage')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)'); db.execute('PRAGMA journal_mode=DELETE')
    print(json.dumps(dict(published=True,release=RELEASE,changedMunicipal=sorted(changed),
                          nearestCameraM=proof['nearestCameraM'],macajiPct=proof['macajiMunicipalPct'],zipBytes=archive_path.stat().st_size),ensure_ascii=False))
if __name__=='__main__': main()
