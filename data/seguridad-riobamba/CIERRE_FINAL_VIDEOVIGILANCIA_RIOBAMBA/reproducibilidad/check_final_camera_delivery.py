"""Check the packaged maps, layouts, relative providers and archive CRC."""
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile
import numpy as np
from PIL import Image
from close_final_camera_study import OUT,GROUPS,jsave


def main():
    results=[]
    for i in range(1,11):
        path=OUT/'mapas'/f'MAPA_{i:02}.png'
        with Image.open(path) as im:
            a=np.asarray(im.convert('RGB'))
            body=a[131:1204,45:1234]
            colored=np.count_nonzero(body.max(axis=2)-body.min(axis=2)>15)
            results.append({'map':i,'size':list(im.size),'mapPixelStd':float(body.std()),
                'coloredPixels':int(colored),'passed':body.std()>8 and colored>1000})
    with zipfile.ZipFile(OUT/'CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.qgz') as z:
        name=next(n for n in z.namelist() if n.endswith('.qgs'))
        root=ET.fromstring(z.read(name))
    providers=[node.text or '' for node in root.findall('.//projectlayers/maplayer/datasource')]
    groups=[node.get('name') for node in root.findall('./layer-tree-group/layer-tree-group')]
    layouts=root.findall('./Layouts/Layout')
    conditions={'allMapsNonblank':all(r['passed'] for r in results),'layouts10':len(layouts)==10,
        'groups14':groups==list(GROUPS),'allProvidersRelative':all(not p.lower().startswith(('d:','c:','file:')) for p in providers),
        'gisQC':json.loads((OUT/'VALIDACION.json').read_text(encoding='utf-8'))['passed'],
        'qgisQC':json.loads((OUT/'VALIDACION_QGIS.json').read_text(encoding='utf-8'))['passed']}
    jsave('VALIDACION_ENTREGA.json',{'passed':all(conditions.values()),'conditions':conditions,'maps':results,
        'visuallyInspected':['MAPA_01','MAPA_05','MAPA_08','MAPA_09'],'fontsRegistered':'Arial normal,bold,italic,bolditalic',
        'warning':'Raster pixel tests check nonblank rendering; GIS audits verify source geometries and counts.'})
    assert all(conditions.values()),conditions
    target=OUT.parent/'CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.zip'
    shutil.copy2(__file__,OUT/'reproducibilidad/check_final_camera_delivery.py')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in OUT.rglob('*'):
            if path.is_file() and path.suffix not in ('.lock','.lck') and path.name!='MUNICIPALES_CHECKPOINT.gpkg':
                z.write(path,OUT.name+'/'+path.relative_to(OUT).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(set(z.namelist()))
    print(json.dumps({'passed':True,'conditions':conditions,'zipBytes':target.stat().st_size}))


if __name__=='__main__':main()
