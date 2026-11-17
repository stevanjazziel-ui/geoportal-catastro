"""Publish only a finished, checked literature adaptation, keeping native states.

The transport encoder exports every twelfth 15-second native state (3 minutes).
Scientific arrival/section analysis uses all 601 states, never the display cadence.
"""
from pathlib import Path
import importlib, json, os, shutil, sys
from study_reference import ROOT, WORK


def link(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if os.path.samefile(source,target):return
        target.unlink()
    try:os.link(source,target)
    except OSError:shutil.copy2(source,target)


def main():
    report=json.loads((WORK/'report.json').read_text(encoding='utf-8'))
    assert report['completed_time_s']==9000 and report['native_frames_checked']==601
    assert report['volume_balance_relative_error']<.001
    original=report['scenario']; folder=WORK/'runs/viewer-reference-cop30'
    for frame in range(51):link(WORK/'runs/reference-cop30'/f'{frame*12:06d}.nc',folder/f'{frame:06d}.nc')
    link(WORK/'prepared/display-maximums.nc',folder/'Maximums.nc')
    link(WORK/'runs/reference-cop30/Volume.txt',folder/'Volume.txt')
    link(WORK/'prepared/cop_conditioned_30m.tif',WORK/'prepared/pita_domain_30m.tif')
    for f in ['S01W079.hgt.gz','municipal-buildings.geojson']:link(ROOT/'sources'/f,WORK/'sources'/f)
    link(ROOT/'runs/benchmark-o3/Volume.txt',WORK/'runs/benchmark/Volume.txt')
    sources=[{'model_lon':s['lon'],'model_lat':s['lat'],'id':s['id']} for s in original['sources']]
    setup={**original,'scenario_type':'Literature-based adaptation; independent terrain and digitized source positions',
           'not_a_reproduction_of_1877':True,'source_reference':sources[0],'source_references':sources,
           'cases':[{'id':'reference-cop30','dx_m':30,'mixture_input_m3':original['water_input_m3'],
                     'water_input_m3':original['water_input_m3'],'peak_m3_s':original['sum_rounded_peaks_m3_s'],
                     'input':'inputs/reference-cop30.txt','output':'runs/viewer-reference-cop30',
                     'title':'Basado en el estudio · nueve aportes desde el Cotopaxi',
                     'input_phase':'water','native_state_stride':12}]}
    (WORK/'inputs/scenario-manifest.json').write_text(json.dumps(setup,ensure_ascii=False,indent=2),encoding='utf-8')
    import pack_viewer
    pack_viewer.ROOT=WORK
    pack_viewer.main()
    output=pack_viewer.OUT
    manifest=json.loads((output/'manifest.json').read_text(encoding='utf-8'))
    manifest['version']='sangolqui-kestrel-study2025-cop30-v2'
    manifest['notice']='Adaptacion exploratoria de nueve aportes de agua del estudio de 2025; terreno global y fuentes digitalizadas, sin validacion predictiva local.'
    manifest['adaptation']={**original,'status':'completed','completed_time_s':9000,
                           'city_arrival_bracket_s':report['first_urban_wetting_bracket_s'],
                           'section':report['section'],'scientific_report':'study-summary.html',
                           'scientific_data':'study-report.json',
                           'section_hydrograph':'section-hydrograph.csv',
                           'predictive_validation_passed':False}
    from pyproj import Transformer
    geo=Transformer.from_crs(32717,4326,always_xy=True)
    section=next(s for s in report['published_section_context']['sections'] if s['id']=='caldera-pita')
    center=[sum(p[k] for p in section['endpoints'])/2 for k in range(2)]
    manifest['adaptation']['view_targets']={'caldera':geo.transform(*center)}
    manifest['cases'][0]['title']=setup['cases'][0]['title']
    pita_audit=output/'pita-propagation-audit.json'
    if pita_audit.exists():
        audit=json.loads(pita_audit.read_text(encoding='utf-8'))
        if audit.get('case_input_sha256')==original['input_sha256']:
            manifest['known_pita_gap']={'status':'unresolved','audit':pita_audit.name,
                'map':'pita-propagation-audit.png','case':'reference-cop30',
                'notice':'Pita intermediate corridor is not represented. No-flow is not a safety result.'}
    # Hash-addressed public payloads retain full precision without filling Pages.
    assets=[manifest[k] for k in ('geometry','terrain','buildings')]
    assets += [a for c in manifest['cases'] for a in (c,c['max_asset'])]
    for asset in assets:
        original_path=output/asset['file']
        assert original_path.stat().st_size<95_000_000,'Split oversized payload; do not reduce model precision'
        name=original_path.stem+'-'+asset['sha256'][:16]+original_path.suffix
        shutil.copy2(original_path,output/name)
        asset.update(file=name,payload_delivery='github_raw',
                     url='https://raw.githubusercontent.com/stevanjazziel-ui/geoportal-catastro/main/inundaciones-ecuador/data/sangolqui-lahars/'+name)
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    shutil.copy2(WORK/'report.json',output/'study-report.json')
    shutil.copy2(WORK/'section-hydrograph.csv',output/'section-hydrograph.csv')
    shutil.copy2(WORK/'manifest.json',output/'source-terrain-audit.json')
    shutil.copy2(ROOT/'runs/benchmark-native-restart-v2/report.json',output/'native-restart-check.json')
    terrain_audit=ROOT/'sources/municipal-terrain-audit'
    for source_name,target_name in [('report.json','municipal-terrain-comparison.json'),
                                    ('terrain-profiles.png','municipal-terrain-profiles.png'),
                                    ('samples.csv.gz','municipal-terrain-samples.csv.gz')]:
        shutil.copy2(terrain_audit/source_name,output/target_name)
    from compare_historical_deposits import render as historical_comparison
    historical_comparison(output)
    from render_study_report import render
    render(output)
    if (WORK/'execution-history.json').exists():shutil.copy2(WORK/'execution-history.json',output/'execution-history.json')
    # Run independent verification against every exported native field, through
    # georeferencing reconstructed from the actual compressed browser geometry.
    import verify_delivery
    verify_delivery.ROOT=WORK
    verify_delivery.main()
    manifest['delivery_verified']=True
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    shutil.copy2(WORK/'prepared/delivery-validation.json',ROOT/'prepared/delivery-validation.json')
    print('Finished adaptation packaged and independently verified.',flush=True)


if __name__=='__main__':main()
