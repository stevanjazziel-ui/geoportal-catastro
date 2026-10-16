"""Refresh authorized release metadata and downloadable archives after independent validation."""
import json
import zipfile
from build_final_municipal_axis_release import OUT,AUTHORIZATION
from study_current_municipal_nodes import PACKAGE as PREVIOUS


def main():
    validation=json.loads((OUT/'VALIDACION.json').read_text(encoding='utf-8'))
    validation.setdefault('approvedException',{'scope':'LOCAL_JUNCTION_MACAJI','camera':'MUN-037','ringFloorRemoved':True})
    validation['approvedException']['authorization']=AUTHORIZATION
    results=json.loads((OUT/'RESULTADOS.json').read_text(encoding='utf-8'))
    results['bridge']=validation
    for name,data in [('RESULTADOS.json',results),('VALIDACION.json',validation)]:
        (OUT/name).write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    baseline=json.loads((PREVIOUS.parent/'RESULTADOS.json').read_text(encoding='utf-8'))
    comparison={key:{'before':baseline[key],'after':results[key]} for key in ('territorial','population','incidents','hotspots','corridors')}
    (OUT/'COMPARACION_COBERTURAS.json').write_text(json.dumps(comparison,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    independent=json.loads((OUT/'VALIDACION_INDEPENDIENTE.json').read_text(encoding='utf-8'))
    (OUT/'VERIFICACION_INDEPENDIENTE.json').write_text(json.dumps(independent,indent=2),encoding='utf-8')
    for folder,name in [(OUT/'coverage-inputs','BRECHAS_ACTUALIZADAS.zip'),(OUT,'ENTREGA_POLICIA_KDE.zip')]:
        with zipfile.ZipFile(folder/name,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.iterdir()):
                if path.is_file() and path.suffix!='.zip':archive.write(path,path.name)
    print('Release and archive metadata finalized.')


if __name__=='__main__':main()
