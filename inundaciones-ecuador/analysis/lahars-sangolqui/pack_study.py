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


def main(case_id='reference-cop30',output=None):
    report=json.loads((WORK/'report.json').read_text(encoding='utf-8'))
    assert report['completed_time_s']==9000 and report['native_frames_checked']==601
    assert report['volume_balance_relative_error']<.001
    original=report['scenario']; folder=WORK/'runs'/('viewer-'+case_id)
    for frame in range(51):link(WORK/'runs'/case_id/f'{frame*12:06d}.nc',folder/f'{frame:06d}.nc')
    link(WORK/'prepared/display-maximums.nc',folder/'Maximums.nc')
    link(WORK/'runs'/case_id/'Volume.txt',folder/'Volume.txt')
    link(WORK/'prepared'/original['terrain'].get('model_file','cop_conditioned_30m.tif'),WORK/'prepared/pita_domain_30m.tif')
    for f in ['S01W079.hgt.gz','municipal-buildings.geojson']:link(ROOT/'sources'/f,WORK/'sources'/f)
    link(ROOT/'runs/benchmark-o3/Volume.txt',WORK/'runs/benchmark/Volume.txt')
    sources=[{'model_lon':s['lon'],'model_lat':s['lat'],'id':s['id']} for s in original['sources']]
    setup={**original,'scenario_type':'Literature-based adaptation; independent terrain and digitized source positions',
           'not_a_reproduction_of_1877':True,'source_reference':sources[0],'source_references':sources,
           'cases':[{'id':case_id,'dx_m':30,'mixture_input_m3':original['water_input_m3'],
                     'water_input_m3':original['water_input_m3'],'peak_m3_s':original['sum_rounded_peaks_m3_s'],
                     'input':f'inputs/{case_id}.txt','output':'runs/viewer-'+case_id,
                     'title':'Basado en el estudio · nueve aportes desde el Cotopaxi',
                     'input_phase':'water','native_state_stride':12}]}
    if case_id=='reference-mdt30':setup['display_grid']=[3200,2000]
    (WORK/'inputs/scenario-manifest.json').write_text(json.dumps(setup,ensure_ascii=False,indent=2),encoding='utf-8')
    import pack_viewer
    pack_viewer.ROOT=WORK
    if output is not None:pack_viewer.OUT=Path(output)
    pack_viewer.main()
    output=pack_viewer.OUT
    manifest=json.loads((output/'manifest.json').read_text(encoding='utf-8'))
    manifest['version']='sangolqui-kestrel-'+WORK.name
    manifest['notice']='Adaptacion exploratoria de nueve aportes de agua del estudio de 2025; terreno global y fuentes digitalizadas, sin validacion predictiva local.'
    manifest['adaptation']={**original,'status':'completed','completed_time_s':9000,
                           'city_arrival_bracket_s':report['first_urban_wetting_bracket_s'],
                           'section':report['section'],'scientific_report':'study-summary.html',
                           'scientific_data':'study-report.json',
                           'section_hydrograph':'section-hydrograph.csv',
                           'sampled_urban_maxima':{
                               'urban_depth_max_m':report['urban_max_depth_m'],
                               'urban_speed_max_m_s':report['urban_max_speed_m_s'],
                               'native_cadence_s':15,'minimum_flow_depth_m':.05,
                               'scope':'601 native states; speed only where simultaneous H>=5cm. Independent aggregate depth/speed maxima need not occur together.'},
                           'predictive_validation_passed':False}
    from pyproj import Transformer
    geo=Transformer.from_crs(32717,4326,always_xy=True)
    section=next(s for s in report['published_section_context']['sections'] if s['id']=='caldera-pita')
    center=[sum(p[k] for p in section['endpoints'])/2 for k in range(2)]
    manifest['adaptation']['view_targets']={'caldera':geo.transform(*center)}
    manifest['cases'][0]['title']=setup['cases'][0]['title']
    if case_id=='reference-mdt30':
        manifest['cases'][0]['title']='Relieve municipal · avance calculado desde el Cotopaxi'
        manifest['notice']='MDT municipal nativo3m remuestreado para una malla física30m; transición al terreno regional con referencia vertical sin confirmar. Adaptación exploratoria, sin validación predictiva local.'
        for source_path,target_name in [(ROOT/'sources/ruminahui-geoservicios-dtm/native3m-audit.json','municipal-native3m-audit.json'),
                                        (ROOT/'sources/ruminahui-lidar/ground-check/report.json','lidar-ground-comparison.json'),
                                        (WORK/'prepared/thread-benchmark.json','thread-benchmark.json'),
                                        (WORK/'prepared/active-thread-benchmark.json','active-thread-benchmark.json'),
                                        (WORK/'prepared/integration-check.json','integration-check.json'),
                                        (WORK/'prepared/municipal-integration-profiles.png','municipal-integration-profiles.png')]:
            shutil.copy2(source_path,output/target_name)
        native_audit_path=output/'municipal-native3m-audit.json'
        native_audit=json.loads(native_audit_path.read_text(encoding='utf-8'))
        native_audit['applied_to_model_at_download']=native_audit.get('applied_to_hydraulic_model',False)
        native_audit.update(applied_to_hydraulic_model=True,applied_case_id=case_id,
                            computational_grid_m=30,model_terrain_sha256=original['terrain']['conditioned_sha256'])
        native_audit_path.write_text(json.dumps(native_audit,ensure_ascii=False,indent=2),encoding='utf-8')
    pita_audit=output/'pita-propagation-audit.json'
    if case_id=='reference-mdt30' and not pita_audit.exists():
        from audit_pita_gap import main as audit_pita
        audit_pita(work=WORK,output=output)
    if pita_audit.exists():
        audit=json.loads(pita_audit.read_text(encoding='utf-8'))
        if audit.get('case_input_sha256')==original['input_sha256'] and not audit.get('route_coverage_complete',False):
            manifest['known_pita_gap']={'status':'unresolved','audit':pita_audit.name,
                'map':'pita-propagation-audit.png','case':case_id,
                'notice':'Pita intermediate corridor is not represented. No-flow is not a safety result.'}
    if case_id=='reference-mdt30':
        assert pita_audit.exists(),'Require the independent Pita route audit'
        assert audit.get('case_input_sha256')==original['input_sha256']
        assert audit.get('route_coverage_complete',False),'Route still incomplete; retain results locally and investigate before publishing a correction'
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
    import compare_historical_deposits
    compare_historical_deposits.WORK=WORK
    historical_comparison(output)
    from render_study_report import render
    import render_study_report
    render_study_report.WORK=WORK
    render(output)
    if (WORK/'execution-history.json').exists():shutil.copy2(WORK/'execution-history.json',output/'execution-history.json')
    # Run independent verification against every exported native field, through
    # georeferencing reconstructed from the actual compressed browser geometry.
    import verify_delivery
    verify_delivery.ROOT=WORK
    verify_delivery.OUT=output
    verify_delivery.main()
    manifest['delivery_verified']=True
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    shutil.copy2(WORK/'prepared/delivery-validation.json',ROOT/'prepared/delivery-validation.json')
    print('Finished adaptation packaged and independently verified.',flush=True)


if __name__=='__main__':main()
