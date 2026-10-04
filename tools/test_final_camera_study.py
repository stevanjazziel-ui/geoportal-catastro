"""Independent geometry, source, statistical and count checks for the closing run."""
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pyogrio
from shapely import covers
from shapely.ops import unary_union

from close_final_camera_study import OUT, PACKAGE, PREVIOUS, POLICE_SOURCE, KEYS, ROOT
from build_police_camera_proposal import read_layer, records, sha, CLASSES, coverage_class


def main():
    data=json.loads((OUT/'RESULTADOS.json').read_text(encoding='utf-8'))
    checks=[]
    def check(label, condition):
        checks.append({'check':label,'passed':bool(condition)})
    c=read_layer(PACKAGE,'CAMARAS_EXISTENTES_103_FINAL')
    m=read_layer(PACKAGE,'PROPUESTA_MUNICIPAL_50_FINAL')
    p=read_layer(PACKAGE,'PROPUESTA_POLICIA_30_FINAL')
    check('103 existentes,50 municipales,30 policiales,183 total',len(c)==103 and len(m)==50 and len(p)==30 and len(c)+len(m)+len(p)==183)
    for frame,id_field in ((c,'ID_CAMARA'),(m,'ID_PROPUESTA'),(p,'ID_POLICIA')):
        check(id_field+' IDs unicos;0 nulos;0 invalidos;EPSG32717',frame[id_field].nunique()==len(frame) and frame.geometry.notna().all() and frame.geometry.is_valid.all() and frame.crs.to_epsg()==32717)
        check(id_field+' XY finitos no cero y sincronizados',all(math.isfinite(g.x) and math.isfinite(g.y) and (g.x,g.y)!=(0,0) and abs(g.x-r.X)<1e-7 and abs(g.y-r.Y)<1e-7 for _,r in frame.iterrows() for g in [r.geometry]))
    previous_c=read_layer(PREVIOUS,'CAMARAS_EXISTENTES_103_CONSOLIDADA')
    check('103 geometrias existentes aceptadas intactas',c.geometry.to_wkb().equals(previous_c.geometry.to_wkb()))
    check('103 atributos existentes intactos',all(c[col].equals(previous_c[col]) for col in previous_c.columns if col!='geometry'))
    raw=read_layer(PREVIOUS,'INVENTARIO_ORIGINAL_103');copy=read_layer(PACKAGE,'INVENTARIO_ORIGINAL_103')
    check('Inventario administrativo original no sobrescrito',raw.equals(copy))
    sites={}
    for _,r in c.iterrows():sites.setdefault(r.geometry.wkb,[]).append(r.ID_CAMARA)
    expected={frozenset(ids) for ids in (('RIO-007-DOMO','RIO-008-FIJA'),('RIO-016-DOMO','RIO-017-FIJA'),('RIO-099-DOMO','RIO-100-FIJA'))}
    check('Tres pares documentales;103 equipos en100 emplazamientos',len(sites)==100 and {frozenset(ids) for ids in sites.values() if len(ids)>1}==expected)
    check('RIO085 diferencia0.41m y016017 misma geometria',c.loc[c.ID_CAMARA=='RIO-085-DOMO'].DIFERENCIA_M.iloc[0]==.41 and c.loc[c.ID_CAMARA=='RIO-016-DOMO'].geometry.iloc[0].equals(c.loc[c.ID_CAMARA=='RIO-017-FIJA'].geometry.iloc[0]))
    audit=read_layer(PACKAGE,'AUDITORIA_GEOREFERENCIACION_CAMARAS')
    check('Auditoria cuatro recuperadas y campos requeridos',len(audit)==4 and {'ID','DIRECCION_DOCUMENTAL','DIRECCION_CARTOGRAFICA','X','Y','METODO_GEO','FUENTE_GEO','CONFIANZA_GEO','OBSERVACION_GEO'}<=set(audit.columns))
    check('22 rurales+4Abras+24estructurales',Counter(m.GRUPO)=={'CABECERA_RURAL':22,'LAS_ABRAS':4,'RED_ESTRUCTURAL':24})
    check('Dos rurales por11parroquias',len(Counter(m.loc[m.GRUPO=='CABECERA_RURAL'].PARROQUIA))==11 and set(Counter(m.loc[m.GRUPO=='CABECERA_RURAL'].PARROQUIA).values())=={2})
    previous_m=read_layer(PREVIOUS,'PROPUESTA_50_CONSOLIDADA').set_index('ID_PROPUESTA')
    check('22 rurales y4Abras aceptadas congeladas',all(r.GRUPO=='RED_ESTRUCTURAL' or r.geometry.equals(previous_m.loc[r.ID_PROPUESTA].geometry) for _,r in m.iterrows()))
    candidates=read_layer(PACKAGE,'CANDIDATOS_ESTRUCTURALES').set_index('ID_CANDIDATO')
    check('24estructurales pertenecen a nodos/cruces reales, sin interpolacion',all(r.geometry.equals(candidates.loc[r.ID_CANDIDATO].geometry) for _,r in m.loc[m.GRUPO=='RED_ESTRUCTURAL'].iterrows()))
    check('Sin nuevos emplazamientos duplicados municipales/policiales',m.geometry.to_wkb().nunique()==50 and p.geometry.to_wkb().nunique()==30 and len(set(c.geometry.to_wkb()) & set(m.geometry.to_wkb()))==0 and len(set(m.geometry.to_wkb()) & set(p.geometry.to_wkb()))==0)
    masks={s:read_layer(PACKAGE,'COBERTURA_'+s).geometry.iloc[0] for s in ('A','B','C','B_ANTERIOR','C_ANTERIOR')}
    for s,points in (('A',list(c.geometry)),('B',list(c.geometry)+list(m.geometry)),('C',list(c.geometry)+list(m.geometry)+list(p.geometry))):
        union=unary_union([g.buffer(200,quad_segs=64) for g in {g.wkb:g for g in points}.values()])
        check('Cobertura '+s+' union200m real no suma de superficies',union.symmetric_difference(masks[s]).area<1e-5)
    buffers=read_layer(PACKAGE,'BUFFERS_SITIOS_200M')
    check('Buffers sitios representan183 equipos;radio200m',buffers.N_CAMARAS.sum()==183 and (buffers.RADIO_M==200).all() and all(abs(g.area-math.pi*200**2)<15 for g in buffers.geometry))
    canton=read_layer(PACKAGE,'LIMITE_CANTONAL').geometry.iloc[0]
    outside_c=c.loc[~c.geometry.map(canton.covers)].ID_CAMARA.tolist()
    check('Puntos fuera del canton:soloRIO075original;propuestas todas dentro',outside_c==['RIO-075-DOMO'] and m.geometry.map(canton.covers).all() and p.geometry.map(canton.covers).all())
    for scope in ('URBANO','RURAL'):
        for cat in CLASSES:
            name='GI_'+scope+'_'+cat
            old=read_layer(POLICE_SOURCE,name);new=read_layer(PACKAGE,name)
            check(name+' Gi/geometria/z/p/nivel/parametros congelados',old.geometry.to_wkb().equals(new.geometry.to_wkb()) and all(old[col].equals(new[col]) for col in old.columns if col!='geometry' and not col.startswith(('COB_','ESTADO_'))))
    events=read_layer(PACKAGE,'INCIDENTES_CLASIFICADOS');old_events=read_layer(PREVIOUS,'INCIDENTES_ANALITICOS')
    check('Incidentes sin movimientos, categorias sin cambios, Cunduana separado',events.geometry.to_wkb().equals(old_events.geometry.to_wkb()) and all(events[col].equals(old_events[col]) for col in old_events.columns if col!='geometry' and not col.startswith('CUB_')))
    event_points=events.loc[events.AMBITO!='EXTERNO_CANTON']
    for frame,id_field,other,base in ((m,'ID_PROPUESTA',m,masks['A']),(p,'ID_POLICIA',p,masks['B'])):
        for _,r in frame.iterrows():
            disk=r.geometry.buffer(200,quad_segs=64)
            within=event_points.loc[covers(disk,event_points.geometry.array)]
            check(r[id_field]+' eventos200m recalculados en coordenada final',r.DELINCUENCIA_200M==sum(within.CATEGORIA=='DELINCUENCIA') and r.VIOLENCIA_200M==sum(within.CATEGORIA=='VIOLENCIA') and r.CONVIVENCIA_200M==sum(within.CATEGORIA=='CONVIVENCIA'))
            rest=unary_union([base]+[g.buffer(200,quad_segs=64) for g in other.loc[other[id_field]!=r[id_field]].geometry])
            exclusive=within.loc[~covers(rest,within.geometry.array)]
            fields=('D_EXCLUSIVOS','V_EXCLUSIVOS') if id_field=='ID_PROPUESTA' else ('EVENTOS_D_EXCLUSIVOS_FINAL','EVENTOS_V_EXCLUSIVOS_FINAL')
            check(r[id_field]+' aportes exclusivos finales sincronizados',r[fields[0]]==sum(exclusive.CATEGORIA=='DELINCUENCIA') and r[fields[1]]==sum(exclusive.CATEGORIA=='VIOLENCIA'))
    for r in data['incidents']:
        mask=events.CATEGORIA==r['CATEGORIA']
        if r['AMBITO']=='CANTONAL':mask &= events.AMBITO!='EXTERNO_CANTON'
        elif r['AMBITO']!='BASE_COMPLETA':mask &= events.AMBITO==r['AMBITO']
        points=events.loc[mask].geometry.array
        check(f"Eventos {r['ESCENARIO']} {r['AMBITO']} {r['CATEGORIA']}",len(points)==r['TOTAL'] and int(np.count_nonzero(covers(masks[r['ESCENARIO']],points)))==r['CUBIERTOS'])
    for r in data['hotspots']:
        frame=read_layer(PACKAGE,'GI_'+r['AMBITO']+'_'+r['CATEGORIA'])
        frame=frame.loc[frame.GI_CLASS==f"HOTSPOT {r['NIVEL']}%"]
        fractions=[g.intersection(masks[r['ESCENARIO']]).area/g.area for g in frame.geometry]
        counts=Counter(coverage_class(f) for f in fractions)
        check(f"Hotspots {r['ESCENARIO']} {r['AMBITO']} {r['CATEGORIA']} {r['NIVEL']}",len(frame)==r['TOTAL'] and counts['CUBIERTO']==r['CUBIERTO'] and counts['PARCIALMENTE CUBIERTO']==r['PARCIAL'] and counts['SIN COBERTURA']==r['SIN_COBERTURA'])
    axes={r.CORREDOR:r.geometry for _,r in read_layer(PACKAGE,'CORREDORES').iterrows()}
    for r in data['corridors']:
        axis=axes[r['CORREDOR']]
        check('Corredor '+r['ESCENARIO']+' '+r['CORREDOR'],abs(axis.intersection(masks[r['ESCENARIO']]).length-r['CUBIERTO_M'])<1e-5)
    check('Macaji>=98% SIN utilizar Policia',axes[KEYS[0]].intersection(masks['B']).length/axes[KEYS[0]].length>=.98-1e-9)
    for key,label in zip(KEYS+('QUEBRADA_LAS_ABRAS',),('MACAJI','ANILLO','CICLOVIAS','LAS_ABRAS')):
        residual=read_layer(PACKAGE,'BRECHA_'+label+'_FINAL')
        check(label+' longitud cubierta+remanente=original',abs(residual.geometry.length.sum()+axes[key].intersection(masks['C']).length-axes[key].length)<1e-5)
        all_points={str(r.get('ID_CAMARA') or r.get('ID_PROPUESTA') or r.get('ID_POLICIA')):g for frame in (c,m,p) for g,r in records(frame)}
        check(label+' extremos/longitud/distancia nearest verificadas',all(abs(r.geometry.length-r.LONGITUD_M)<1e-6 and tuple(r.geometry.coords[0])==(r.INICIO_X,r.INICIO_Y) and tuple(r.geometry.coords[-1])==(r.FIN_X,r.FIN_Y) and abs(r.DIST_CAMARA_M-min(r.geometry.distance(g) for g in all_points.values()))<1e-6 for _,r in residual.iterrows()))
    old_p=read_layer(PREVIOUS,'PROPUESTA_POLICIA_30_FINAL').set_index('ID_POLICIA')
    changes={r['ID_FINAL']:r for r in data['policeChanges']}
    check('POLICIA_CAMBIOS solo incluye cambios reales',all((r.ID_POLICIA in changes)==(not r.geometry.equals(old_p.loc[r.ID_POLICIA].geometry)) for _,r in p.iterrows()))
    check('Reemplazos dominan D/V y solape;no criterio corredores',all(r['D_DESPUES']>=r['D_ANTES'] and r['V_DESPUES']>=r['V_ANTES'] and r['DV_NUEVOS_DESPUES']>r['DV_NUEVOS_ANTES'] and r['SOLAPE_DESPUES']<r['SOLAPE_ANTES'] for r in changes.values()))
    urban=unary_union(list(read_layer(PACKAGE,'PLATAFORMAS_TERRITORIALES').geometry));blocks=read_layer(PACKAGE,'MANZANAS_COBERTURA')
    for r in data['population']:
        valid=blocks.loc[blocks.POBLACION.notna() & (blocks.AREA_URBANA_M2>.01)]
        total=sum(q.POBLACION*q.geometry.intersection(urban).area/q.geometry.area for _,q in valid.iterrows())
        covered=sum(q.POBLACION*q.geometry.intersection(urban).intersection(masks[r['ESCENARIO']]).area/q.geometry.area for _,q in valid.iterrows())
        check('Poblacion areal '+r['ESCENARIO'],abs(total-r['POBLACION_ANALIZADA'])<1e-5 and abs(covered-r['POBLACION_CUBIERTA'])<1e-5 and 0<=covered<=total)
    full=read_layer(PACKAGE,'EJE_QUEBRADA_LAS_ABRAS_MAATE').geometry.iloc[0]
    clip=read_layer(PACKAGE,'LAS_ABRAS_MAATE_REFERENCIA_CANTON').geometry.iloc[0]
    check('MAATE completo conservado;analisis solo cantonal',full.intersection(canton).symmetric_difference(clip).length<1e-5)
    for item in data['catalog']:
        frame=pyogrio.read_dataframe(PACKAGE,layer=item['name'])
        condition=len(frame)==item['records']
        if 'geometry' in frame:
            condition=condition and frame.crs.to_epsg()==32717 and frame.geometry.dropna().is_valid.all() and frame.geometry.isna().sum()==(4 if item['name']=='INVENTARIO_ORIGINAL_103' else 0)
        check(item['name']+' conteos/CRS/nulos/validas',condition)
    for name,_ in pyogrio.list_layers(PREVIOUS):
        if name.startswith(('MAATE_INSUMO_','CUNDUANA_','LAS_ABRAS_ACTUAL','EJE_QUEBRADA_LAS_ABRAS_MAATE','ABRAS_DIFERENCIAS')):
            old=read_layer(PREVIOUS,name);new=read_layer(PACKAGE,name)
            check(name+' originales intactos',old.equals(new))
    authorized=data.get('publicationUiChanges',{})
    check('Cambios UI autorizados limitados al visor V2',set(authorized).issubset({str(ROOT/'visor-seguridad-riobamba-v2.html')}))
    check('Fuentes GIS intactas y cambio UI documentado con SHA256',all(
        (authorized[path]['before']==digest and sha(Path(path))==authorized[path]['after'])
        if path in authorized else sha(Path(path))==digest for path,digest in data['sourceHashes'].items()))
    check('Abras37nodos auditados;cuatro mantenidas sin mejoras claras',data.get('abrasAlternativesAudit',{}).get('candidates')==37 and all(r['DECISION']=='MANTENER' for r in data['abrasAlternativesAudit']['decisions']))
    check('Atributos derivados de puntos reconstruidos, no heredados de posiciones viejas',data.get('derivedPointAttributesRebuilt') is True)
    result={'passed':all(r['passed'] for r in checks),'nChecks':len(checks),'failed':[r for r in checks if not r['passed']],
        'checks':checks,'existingOutsideCanton':outside_c,'commit':False,'push':False}
    (OUT/'VALIDACION.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='checks'}))
    assert result['passed'],result['failed']


if __name__=='__main__':main()
