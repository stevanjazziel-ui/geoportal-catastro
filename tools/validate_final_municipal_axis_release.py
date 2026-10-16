"""Independent real-data validation before activating the approved municipal release."""
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import covers
from shapely.ops import unary_union

from build_final_municipal_axis_release import OUT,REVIEW
from study_current_municipal_nodes import PACKAGE as PREVIOUS


def main():
    package=OUT/'ESCENARIO_FINAL_183.gpkg'
    read=lambda name:gpd.read_file(package,layer=name).to_crs(32717)
    old=lambda name:gpd.read_file(PREVIOUS,layer=name).to_crs(32717)
    existing,municipal,police=[read(n) for n in ('CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL')]
    assert [len(existing),len(municipal),len(police)]==[103,50,30]
    assert existing.REQUIERE_CAMBIO.astype(bool).sum()==30
    for name,frame,key in [('CAMARAS_EXISTENTES_103_FINAL',existing,'ID_CAMARA'),('PROPUESTA_POLICIA_30_FINAL',police,'ID_POLICIA')]:
        previous=old(name).set_index(key).loc[frame[key]]
        assert previous.geometry.to_wkb().tolist()==frame.geometry.to_wkb().tolist()
    frozen=municipal.loc[~municipal.GRUPO.eq('RED_ESTRUCTURAL')]
    assert old('PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA').loc[frozen.ID_PROPUESTA].geometry.to_wkb().tolist()==frozen.geometry.to_wkb().tolist()
    target=gpd.read_file(REVIEW/'ESTUDIO_24_NODOS.gpkg',layer='EJES_PRIORITARIOS').set_index('ID_PROPUESTA')
    selected=municipal.loc[municipal.GRUPO.eq('RED_ESTRUCTURAL')]
    assert target.loc[selected.ID_PROPUESTA].geometry.to_wkb().tolist()==selected.geometry.to_wkb().tolist()
    assert len({p.wkb for p in list(municipal.geometry)+list(police.geometry)})==80
    validation=json.loads((OUT/'VALIDACION.json').read_text(encoding='utf-8'))
    assert not validation['publishBlocks'] and len(validation['nodeAudit'])==24
    assert [r['id'] for r in validation['nodeAudit'] if not r['principalRoad']]==['MUN-037']
    for scope in ('URBANO','RURAL'):
        for category in ('DELINCUENCIA','VIOLENCIA','CONVIVENCIA'):
            name='GI_'+scope+'_'+category
            before,after=old(name),read(name)
            assert before.geometry.to_wkb().tolist()==after.geometry.to_wkb().tolist()
            fields=[c for c in before.columns if c!='geometry' and not c.startswith(('COB_','ESTADO_'))]
            pd.testing.assert_frame_equal(before[fields],after[fields],check_dtype=False)
    gaps=json.loads((OUT/'coverage-inputs/RESULTADOS.json').read_text(encoding='utf-8'))
    blocks=read('MANZANAS_COBERTURA');events=read('INCIDENTES_CLASIFICADOS')
    checks=[]
    for radius in (100,150,200):
        actual=unary_union([p.buffer(radius,quad_segs=64) for p in existing.geometry])
        b=unary_union([actual,*[p.buffer(radius,quad_segs=64) for p in municipal.geometry]])
        c=unary_union([b,*[p.buffer(radius,quad_segs=64) for p in police.geometry]])
        for code,mask in [('A',actual),('B',b),('C',c)]:
            for row in blocks.itertuples():
                pct=100*row.geometry.intersection(mask).area/row.geometry.area
                assert abs(gaps['scenarios'][str(radius)][code]['byMan'][row.ID_MANZANA]['coveragePct']-pct)<1e-5
            if radius==200:
                assert read('COBERTURA_'+code).geometry.iloc[0].symmetric_difference(mask).area<.01
                assert np.array_equal(covers(mask,events.geometry.values),events['CUB_'+code].astype(bool).values)
        checks.append(radius)
    results=json.loads((OUT/'RESULTADOS.json').read_text(encoding='utf-8'))
    macaji=next(r for r in results['corridors'] if r['ESCENARIO']=='B' and r['CORREDOR']=='BOULEVARD_MACAJI_BELLAVISTA')
    assert macaji['NO_CUBIERTO_M']<=.001
    report={'passed':True,'counts':[103,50,30],'replacementIncluded':30,'fixed159Unchanged':True,
        'urban24MatchApproved':True,'sixGiGeometryAndStatisticsUnchanged':True,'censusRadiiChecked':checks,
        'macajiUncoveredM':macaji['NO_CUBIERTO_M'],'ringFloor':None,'localException':'MUN-037 Junin x Puruha'}
    (OUT/'VALIDACION_INDEPENDIENTE.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
