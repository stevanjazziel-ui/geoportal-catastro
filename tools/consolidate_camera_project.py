"""Consolidate accepted cartographic geocodes and local proposals, preserving all sources."""
import argparse
import csv
import json
import math
import warnings
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely import STRtree,force_2d
from shapely.geometry import Point,shape
from shapely.ops import transform,unary_union

from audit_consolidation_sources import OUT,GDB,ROAD,ZIPS,clean
from audit_pending_camera_intersections import norm
from build_police_camera_proposal import (ROOT,Context,CLASSES,AREA_EPS,PROJECT,UNPROJECT,
    records,read_layer,parts,pct,sha,geojson,scenario_evaluation)
from build_remaining_camera_coverage import load
from optimize_municipal_cameras_50 import crossing_points,unique_candidates
from review_police_camera_efficiency import Evaluator,preferences,revision_rank

BASE=ROOT/'data/seguridad-riobamba'
ORIGINAL=BASE/'propuesta-policia-30-20261003/PROPUESTA_POLICIA_30.gpkg'
TRIAL=BASE/'escenario-100-geo-20261004/ESCENARIO_100_GEO.gpkg'
GEO=BASE/'geocodificacion-pendientes-20261003'
PREVIOUS=BASE/'propuesta-policia-30-final-100geo-20261004/PROPUESTA_POLICIA_30_REVISION_100GEO.gpkg'
PACKAGE=OUT/'CONSOLIDACION_CAMARAS_183.gpkg'
SLOTS=('POL-08','POL-20','POL-21','POL-22','POL-30')


def jsave(name,data):
    (OUT/name).write_text(json.dumps(clean(data),ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')


def csvsave(name,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as stream:
        w=csv.DictWriter(stream,fields);w.writeheader();w.writerows(clean(rows))


def coverage(rows):
    unique={g.wkb:g for g,_ in rows if g is not None}
    return unary_union([g.buffer(200,quad_segs=64) for g in unique.values()])


def export(name,rows,group,visual=False,source='Derivado del presente procesamiento'):
    if not rows:return None
    frame=gpd.GeoDataFrame([p for _,p in rows],geometry=[g for g,_ in rows],crs=32717)
    pyogrio.write_dataframe(frame,PACKAGE,layer=name)
    if visual:jsave(name+'.geojson',geojson(rows))
    return {'name':name,'group':group,'records':len(rows),'crs':'EPSG:32717',
        'source':source,'fields':list(frame.columns[:-1])}


def consolidate_inventory(accepted,canton):
    if not accepted:raise ValueError('Explicit acceptance of the census prison node is required')
    raw=records(read_layer(ORIGINAL,'CAMARAS_EXISTENTES_103'))
    trial={p['ID_CAMARA']:(g,p) for g,p in records(read_layer(TRIAL,'ESCENARIO_100_GEO'))}
    audit=json.loads((GEO/'REVISION.json').read_text(encoding='utf-8'))
    candidates={r['ID_CAMARA']:r for r in audit['candidates']}
    refs=json.loads((OUT/'AUDITORIA_INSUMOS.json').read_text(encoding='utf-8'))
    prison=next(r for r in refs['evidencePrison'] if r['layer']=='Bienestar_social' and r['fid']==18)
    prison_point=shape(prison['geometry'])
    exact=pyogrio.read_dataframe(ROAD,fid_as_index=True).to_crs(32717)
    final,review=[],[]
    for g,original in raw:
        p=dict(original);id=p['ID_CAMARA']
        p.update(PRECISION_ORIGINAL=p['PRECISION'],DIRECCION_DOCUMENTAL=p['DIRECCION'],DIRECCION_CARTOGRAFICA=None,
            METODO_GEO='COORDENADA_ORIGINAL_INVENTARIO',FUENTE_GEO='Inventario original del proyecto',
            CONFIANZA_GEO='APROXIMADA_ORIGINAL',OBSERVACION_GEO=p['PRECISION'],ESTADO_GEO='LOCALIZADA_ORIGINAL')
        if id=='RIO-085-DOMO':
            g,previous=trial[id]
            p.update({key:previous.get(key) for key in ('FUENTE_1','FUENTE_2','DIFERENCIA_M','METODO_GEO')})
            p.update(DIRECCION_CARTOGRAFICA='Jose de Orozco x Baltazar Paredes',
                FUENTE_GEO=previous['FUENTE_1']+'; '+previous['FUENTE_2'],CONFIANZA_GEO='CORROBORADA_CARTOGRAFICAMENTE',
                ESTADO_GEO='CANDIDATO_VALIDADO',OBSERVACION_GEO='Ubicacion aceptada sin desplazamiento; dos fuentes, diferencia 0.41 m. Poste no verificado en campo.')
            p['PRECISION']='Cruce vial corroborado cartograficamente; poste sin verificacion de campo'
        elif id in ('RIO-016-DOMO','RIO-017-FIJA','RIO-103-DOMO'):
            r=candidates[id];g=Point(r['X'],r['Y'])
            # FIDs come from the source audit, not the DataFrame row order.
            assert exact.loc[r['FID_A']].geometry.distance(g)<1e-6
            assert exact.loc[r['FID_B']].geometry.distance(g)<1e-6
            p.update(DIRECCION_CARTOGRAFICA=r['DIRECCION_REVISADA'],METODO_GEO='INTERSECCION_VIAL_CENSAL_EXACTA',
                FUENTE_GEO=r['SOURCE']+':nom_eje; FID '+str(r['FID_A'])+'/'+str(r['FID_B']),
                CONFIANZA_GEO='MEDIA',ESTADO_GEO='LOCALIZADA_CARTOGRAFICA_CON_LIMITACIONES',
                FID_EJE_A=r['FID_A'],FID_EJE_B=r['FID_B'])
            p['PRECISION']='Geocodificacion censal con confianza MEDIA; no verificacion de campo'
            if id in ('RIO-016-DOMO','RIO-017-FIJA'):
                p['DIRECCION_DOCUMENTAL']='Leopoldo Freire y Calle V'
                p['METODO_GEO']='INTERSECCION_CENSAL_Y_REFERENCIA_TERRITORIAL_ACEPTADA'
                p['FUENTE_GEO']+='; GDB Bienestar_social FID18; red OSM local de Riobamba'
                p['DIST_REFERENCIA_CARCEL_M']=g.distance(prison_point)
                p['DIST_FREIRE_MUNICIPAL_M']=r['DIST_EJE_FREIRE_GDB_M']
                p['OBSERVACION_GEO']=('Usuario acepta el nodo censal Freire x Y con confianza MEDIA despues de revisar la referencia municipal Centro de Rehabilitacion Social, a '
                    f'{g.distance(prison_point):.2f} m. Documento conserva Calle V; CSV original dice Calle Y. No se afirma equivalencia V/Y. '
                    'La GDB rotula Freire a 943.98 m; en el sector la red municipal es sin nombre y la red OSM local rotula Leopoldo Freire. '
                    'Candidato antes descartado, ahora aceptado expresamente con esta discrepancia. Dos equipos, mismo emplazamiento cartografico; instalacion fisica pendiente de campo.')
            else:
                p['OBSERVACION_GEO']=('Cruce unico Luis Urdaneta x Manuel Zambrano en red censal; incorporacion cartografica solicitada para consolidacion. '
                    'Fuente CPV2021, anio 2020, valida=fals. No se encontro corroboracion municipal suficiente ni se certifica posicion fisica del poste.')
        assert g is not None and g.is_valid and not g.is_empty
        assert math.isfinite(g.x) and math.isfinite(g.y) and (g.x,g.y)!=(0,0)
        lon,lat=UNPROJECT(g.x,g.y)
        p.update(X=g.x,Y=g.y,LONGITUD=lon,LATITUD=lat,GEOMETRIA_VALIDA=True,DENTRO_CANTON=canton.covers(g))
        final.append((g,p))
        if id in candidates:review.append((g,p))
    assert len(final)==103 and len({p['ID_CAMARA'] for _,p in final})==103
    by_id={p['ID_CAMARA']:g for g,p in final}
    assert by_id['RIO-016-DOMO'].equals(by_id['RIO-017-FIJA'])
    assert by_id['RIO-085-DOMO'].equals(trial['RIO-085-DOMO'][0])
    for g,p in raw:
        if g is not None:assert g.equals(by_id[p['ID_CAMARA']])
    return raw,final,review


def census_blocks():
    stats=load('riobamba-censo-data/riobamba_manzanas_stats.json')['byMan']
    rows=[]
    for f in load('riobamba-censo-data/riobamba_manzanas.geojson')['features']:
        g=transform(PROJECT,shape(f['geometry']))
        id=f['properties']['man'];value=stats.get(id,{}).get('population_total')
        valid=value is not None and math.isfinite(value) and value>=0
        rows.append((g,{**f['properties'],'ID_MANZANA':id,'POBLACION':value if valid else None}))
    return rows


def prepare_environment(canton):
    audit=json.loads((OUT/'AUDITORIA_INSUMOS.json').read_text(encoding='utf-8'))
    new={};catalog=[]
    for i,r in enumerate(audit['layers'],1):
        rows=records(read_layer(r['path']))
        name=('CUNDUANA_PUNTOS_CRITICOS' if r['name']=='Puntos Criticos Cunduana' or norm(r['name'])=='puntos criticos cunduana' else
            'CUNDUANA_TRAMOS_LIMPIEZA' if r['name']=='Tramos para limpieza' else 'MAATE_INSUMO_'+str(i).zfill(2))
        new[r['name']]=rows
        info=export(name,rows,'09_CUNDUANA_PUNTOS_CRITICOS' if i<=2 else '08_QUEBRADA_LAS_ABRAS',True,r['path'])
        info['originalName']=r['name'];catalog.append(info)
    axis=unary_union([g for g,_ in new['Eje_Quebrada_Las_Abras_MAATE']])
    reference=axis.intersection(canton)
    old=unary_union([g for g,p in records(read_layer(ORIGINAL,'CORREDORES_REFERENCIA')) if p['CORREDOR']=='QUEBRADA_LAS_ABRAS'])
    common=old.intersection(reference)
    common_full=old.intersection(axis)
    delta={'LONGITUD_ACTUAL_M':old.length,'LONGITUD_MAATE_COMPLETA_M':axis.length,
        'LONGITUD_MAATE_DENTRO_CANTON_M':reference.length,'LONGITUD_COINCIDENTE_EXACTA_M':common.length,
        'LONGITUD_SOLO_ACTUAL_M':old.difference(reference).length,
        'LONGITUD_SOLO_MAATE_M':reference.difference(old).length,
        'LONGITUD_COINCIDENTE_COMPLETA_M':common_full.length,
        'LONGITUD_SOLO_ACTUAL_VS_COMPLETA_M':old.difference(axis).length,
        'LONGITUD_SOLO_MAATE_COMPLETA_M':axis.difference(old).length,
        'METODO':'Interseccion lineal exacta; no snapping ni tolerancia. No equivale a coincidencia visual entre ejes digitalizados distintos.',
        'DECISION':'Referencia operativa: eje MAATE suministrado, copia recortada al canton. Original completo y eje anterior conservados. Atribucion MAATE del insumo, sin certificacion externa de oficialidad.'}
    sensitivity=[]
    for tolerance in (1,5,10,20):
        sensitivity.append({'TOLERANCIA_M':tolerance,'ACTUAL_PROXIMO_A_MAATE_M':old.intersection(reference.buffer(tolerance)).length,
            'MAATE_PROXIMO_A_ACTUAL_M':reference.intersection(old.buffer(tolerance)).length,
            'USO':'Diagnostico de digitalizacion, no modificar ejes ni seleccionar automaticamente tolerancia'})
    comparisons={'LAS_ABRAS_ACTUAL':[(old,{'FUENTE':'Referencia anterior del proyecto','LONGITUD_M':old.length})],
        'EJE_QUEBRADA_LAS_ABRAS_MAATE':[(axis,{'FUENTE':'ZIP entregado: Eje_Quebrada_Las_Abras_MAATE','LONGITUD_M':axis.length})],
        'LAS_ABRAS_MAATE_REFERENCIA_CANTON':[(reference,{'FUENTE':'MAATE suministrado, recorte analitico cantonal','LONGITUD_M':reference.length})],
        'ABRAS_DIFERENCIAS':[(g,{'CLASE':key,'LONGITUD_M':g.length,'AMBITO':'Eje anterior frente a MAATE cantonal'}) for g,key in ((common,'COINCIDENTE_EXACTO'),(old.difference(reference),'SOLO_ACTUAL'),(reference.difference(old),'SOLO_MAATE')) if not g.is_empty],
        'ABRAS_DIFERENCIAS_COMPLETAS':[(g,{'CLASE':key,'LONGITUD_M':g.length,'AMBITO':'Ejes completos, sin recortar'}) for g,key in ((common_full,'COINCIDENTE_EXACTO'),(old.difference(axis),'SOLO_ACTUAL'),(axis.difference(old),'SOLO_MAATE')) if not g.is_empty]}
    for name,rows in comparisons.items():catalog.append(export(name,rows,'08_QUEBRADA_LAS_ABRAS',True))
    jsave('COMPARACION_ABRAS.json',{'comparison':delta,'sensitivity':sensitivity})
    return new,reference,delta,sensitivity,catalog


def revise_abras(context,canton,new,axis,municipal):
    original={p['ID_PROPUESTA']:(g,p) for g,p in municipal}
    fixed=[r for r in municipal if r[1]['GRUPO']!='LAS_ABRAS']
    slots=[p['ID_PROPUESTA'] for _,p in municipal if p['GRUPO']=='LAS_ABRAS']
    assert len(fixed)==46 and len(slots)==4
    active={p['ID_PROPUESTA']:(g,dict(p)) for g,p in municipal}
    road_u=read_layer(GDB,'Vialidad_urbana');road_c=read_layer(ROAD)
    nodes=[]
    for name,roads in (('CRUCE_MAATE_RED_MUNICIPAL',road_u),('CRUCE_MAATE_RED_CENSAL',road_c)):
        nodes.extend((g,name,0) for g in crossing_points(axis.intersection(unary_union(list(roads.geometry)))))
    pool=unique_candidates(nodes,canton)
    for i,c in enumerate(pool,1):c['id']=f'MAATE-NODO-{i:03d}';context.candidate(c)
    cunduana=next(rows for name,rows in new.items() if norm(name)=='puntos criticos cunduana')
    cleaning=unary_union([g for g,_ in new['Tramos para limpieza']])
    protection=unary_union([g for name,rows in new.items() if 'franja' in norm(name) for g,_ in rows])
    marti=next(rows for name,rows in new.items() if norm(name).startswith('puntos franjas de proteccion jose marti'))
    def evaluate(c,reference):
        disk=c['disk'];newarea=disk.difference(reference)
        counts=Counter(context.events[i][1]['CATEGORIA'] for i in c['events'] if not reference.covers(context.events[i][0]))
        pop,found,missing=context.population(disk)
        environmental=sum(disk.covers(g) for g,_ in cunduana)
        related_marti=sum(disk.covers(g) for g,_ in marti)
        cleanup=cleaning.intersection(newarea).length
        significant=any(context.hot[i][1]['CATEGORIA'] in CLASSES[:2] for i,_ in c['hot'])
        protection_area=protection.intersection(disk).area
        road_axis=axis.distance(c['point'])<=1e-5
        dimensions=sum((road_axis,protection_area>AREA_EPS,related_marti>0,sum(counts.values())>0,pop is not None and pop>0,significant))
        return {'ID_CANDIDATO':c['id'],'X':c['point'].x,'Y':c['point'].y,'ORIGEN':'|'.join(sorted(c['origins'])),
            'N_PUNTOS_CUNDUANA_200M':environmental,'LIMPIEZA_NUEVA_M':cleanup,'N_REFERENCIAS_JOSE_MARTI':related_marti,
            'AREA_PROTECCION_M2':protection_area,'CRUCE_MAATE_VIAL':road_axis,'DIMENSIONES_CON_EVIDENCIA':dimensions,
            'LONGITUD_MAATE_NUEVA_M':axis.intersection(newarea).length,
            'D_NUEVOS':counts['DELINCUENCIA'],'V_NUEVOS':counts['VIOLENCIA'],'C_NUEVOS':counts['CONVIVENCIA'],
            'POBLACION_ASOCIADA':pop,'POB_MANZANAS_VALIDAS':found,'POB_MANZANAS_FALTANTES':missing,
            'HOTSPOT_DV_COMPLEMENTARIO':significant,'SOLAPE_PCT':pct(disk.intersection(reference).area,disk.area),
            'DIST_EJE_MAATE_M':axis.distance(c['point'])}
    def rank(r):
        return (r['N_PUNTOS_CUNDUANA_200M'],r['LIMPIEZA_NUEVA_M'],r['DIMENSIONES_CON_EVIDENCIA'],
            r['N_REFERENCIAS_JOSE_MARTI']>0,r['LONGITUD_MAATE_NUEVA_M'],r['D_NUEVOS']+r['V_NUEVOS'],r['C_NUEVOS'],-r['SOLAPE_PCT'])
    decisions,comparison=[],[]
    for slot in slots:
        others=[r for id,r in active.items() if id!=slot]
        reference=unary_union([context.baseline,coverage(others)])
        g,p=active[slot]
        current=context.candidate({'point':g,'id':p['ID_CANDIDATO'],'degree':p['GRADO_NODO'],'origins':{p['ORIGEN_CANDIDATO']}})
        before=evaluate(current,reference)
        eligible=[evaluate(c,reference) for c in pool if all(c['point'].distance(q)>1e-5 for q,_ in others)]
        # A move must improve real MAATE coverage and maintain or increase supported dimensions.
        for r in eligible:r['MEJORA_CLARA']=r['LONGITUD_MAATE_NUEVA_M']>before['LONGITUD_MAATE_NUEVA_M']+1e-6 and r['DIMENSIONES_CON_EVIDENCIA']>=before['DIMENSIONES_CON_EVIDENCIA']
        eligible.sort(key=lambda r:(r['MEJORA_CLARA'],rank(r)),reverse=True)
        winner=eligible[0] if eligible and eligible[0]['MEJORA_CLARA'] else before
        changed=winner['ID_CANDIDATO']!=before['ID_CANDIDATO']
        c=next((c for c in pool if c['id']==winner['ID_CANDIDATO']),current)
        lon,lat=UNPROJECT(c['point'].x,c['point'].y)
        reason=(f"{'Reemplazo propuesto' if changed else 'Mantener'}: longitud MAATE adicional {before['LONGITUD_MAATE_NUEVA_M']:.1f} a {winner['LONGITUD_MAATE_NUEVA_M']:.1f} m; "
            f"dimensiones con evidencia {before['DIMENSIONES_CON_EVIDENCIA']} a {winner['DIMENSIONES_CON_EVIDENCIA']}. "
            'Nodo/cruce real y evidencia local, no intervalos iguales; Cunduana distante no se atribuye como beneficio. Pendiente validacion de campo.')
        active[slot]=(c['point'],{**p,'X':c['point'].x,'Y':c['point'].y,'LONGITUD':lon,'LATITUD':lat,
            'ID_CANDIDATO':c['id'],'ORIGEN_CANDIDATO':winner['ORIGEN'],'JUSTIFICACION_ORIGINAL':p['JUSTIFICACION'],
            'JUSTIFICACION':reason,'CRITERIO_PRINCIPAL':'Cruce vial y evidencia territorial sobre eje MAATE cantonal',
            'CRITERIOS_SECUNDARIOS':'Proteccion, Jose Marti, poblacion, incidentes, Gi* complementario y longitud adicional',
            'ESTADO_VALIDACION':'PROPUESTA_CONSOLIDADA_PARA_REVISION'})
        comparison.extend({**r,'ID_PROPUESTA':slot,'OPCION':'ACTUAL' if i==0 else 'ALTERNATIVA','ORDEN':i} for i,r in enumerate([before]+eligible[:5]))
        decisions.append({'ID':slot,'DECISION':'REEMPLAZAR' if changed else 'MANTENER','X_ANTES':g.x,'Y_ANTES':g.y,
            'X_NUEVA':c['point'].x,'Y_NUEVA':c['point'].y,'MOVIMIENTO_M':g.distance(c['point']),
            'CRITERIO_ANTERIOR':p['CRITERIO_PRINCIPAL'],'CRITERIO_NUEVO':active[slot][1]['CRITERIO_PRINCIPAL'],
            'LONGITUD_ANTES_M':before['LONGITUD_MAATE_NUEVA_M'],'LONGITUD_DESPUES_M':winner['LONGITUD_MAATE_NUEVA_M'],
            'DIMENSIONES_ANTES':before['DIMENSIONES_CON_EVIDENCIA'],'DIMENSIONES_DESPUES':winner['DIMENSIONES_CON_EVIDENCIA'],
            'MOTIVO':reason})
    revised=list(active.values())
    for id,(g,p) in original.items():
        if p['GRUPO']!='LAS_ABRAS':assert active[id][0].equals(g)
    assert Counter(p['GRUPO'] for _,p in revised)==Counter(p['GRUPO'] for _,p in municipal)
    return revised,decisions,comparison,[(c['point'],{'ID_CANDIDATO':c['id'],'ORIGEN':'|'.join(sorted(c['origins']))}) for c in pool]


def review_police(context,original):
    candidates={p['ID_CANDIDATO']:context.candidate({'point':g,'id':p['ID_CANDIDATO'],'degree':p['GRADO_NODO'],
        'props':p,'origins':set(p['INTERSECCION_O_NODO'].split('|'))}) for g,p in records(read_layer(ORIGINAL,'CANDIDATOS_POLICIA'))}
    active={p['ID_POLICIA']:candidates[p['ID_CANDIDATO']] for _,p in original}
    original_ids={p['ID_CANDIDATO'] for _,p in original}
    evaluator=Evaluator(context);decisions,options=[],[]
    for slot in SLOTS:
        others={id:c for id,c in active.items() if id!=slot}
        reference=unary_union([context.baseline]+[c['disk'] for c in others.values()]);evaluator.prepare(reference)
        before=evaluator.evaluate(active[slot],[c['point'] for c in others.values()]);eligible=[]
        for c in candidates.values():
            if c['id'] in original_ids or c['id'] in {v['id'] for v in others.values()} or c['scope']!=active[slot]['scope']:continue
            if min(c['distanceExisting'],c['distanceMunicipal'])<=1e-5:continue
            r=evaluator.evaluate(c,[v['point'] for v in others.values()])
            if r['COINCIDENCIA_DV_RESIDUAL_M2']<=AREA_EPS:continue
            r['PREFERIBLE']=preferences(r,before);eligible.append(r)
        eligible.sort(key=lambda r:(r['PREFERIBLE'],revision_rank(r)),reverse=True)
        winner=eligible[0] if eligible and eligible[0]['PREFERIBLE'] else before
        changed=winner['ID_CANDIDATO']!=before['ID_CANDIDATO']
        active[slot]=candidates[winner['ID_CANDIDATO']]
        options.extend({**r,'ID_POLICIA':slot,'OPCION':'ACTUAL' if i==0 else 'ALTERNATIVA','ORDEN':i} for i,r in enumerate([before]+eligible[:5]))
        reason=(f"{'Reemplazo propuesto' if changed else 'Mantener'}; exclusivos D/V {before['EVENTOS_DV_NUEVOS']} a {winner['EVENTOS_DV_NUEVOS']}, "
            f"solape {before['SOLAPE_PREVIO_PCT']:.2f}% a {winner['SOLAPE_PREVIO_PCT']:.2f}%. "
            f"Nivel residual D/V {before['NIVEL_DV_RESIDUAL']}% a {winner['NIVEL_DV_RESIDUAL']}%. "
            'Evidencia Gi* original, sin optimizacion completa ni criterios de corredores; areas/niveles pueden disminuir. Validacion de campo pendiente.')
        decisions.append({'ID':slot,'DECISION':'REEMPLAZAR' if changed else 'MANTENER','CANDIDATO_ACTUAL':before['ID_CANDIDATO'],
            'CANDIDATO_PROPUESTO':winner['ID_CANDIDATO'],'DV_ANTES':before['EVENTOS_DV_NUEVOS'],'DV_DESPUES':winner['EVENTOS_DV_NUEVOS'],
            'SOLAPE_ANTES':before['SOLAPE_PREVIO_PCT'],'SOLAPE_DESPUES':winner['SOLAPE_PREVIO_PCT'],
            'NIVEL_ANTES':before['NIVEL_DV_RESIDUAL'],'NIVEL_DESPUES':winner['NIVEL_DV_RESIDUAL'],
            'AREA_D_ANTES_M2':before['AREA_HOTSPOT_D_NUEVA_M2'],'AREA_D_DESPUES_M2':winner['AREA_HOTSPOT_D_NUEVA_M2'],
            'AREA_V_ANTES_M2':before['AREA_HOTSPOT_V_NUEVA_M2'],'AREA_V_DESPUES_M2':winner['AREA_HOTSPOT_V_NUEVA_M2'],'JUSTIFICACION':reason})
        print(json.dumps(decisions[-1],ensure_ascii=False),flush=True)
    rows=[]
    for id,c in active.items():
        others=[v for key,v in active.items() if key!=id]
        evaluator.prepare(unary_union([context.baseline]+[v['disk'] for v in others]))
        m=evaluator.evaluate(c,[v['point'] for v in others]);description=context.description(c)
        decision=next((r for r in decisions if r['ID']==id),None)
        lon,lat=UNPROJECT(c['point'].x,c['point'].y)
        rows.append((c['point'],{**description,'ID_POLICIA':id,'ID_CANDIDATO':c['id'],'X':c['point'].x,'Y':c['point'].y,
            'LONGITUD':lon,'LATITUD':lat,'DECISION':decision['DECISION'] if decision else 'CONGELADA_NO_REVISADA',
            **m,'BENEFICIO_CONTEXTO':'Exclusivo frente a 103+50+otras29 finales, no sumable',
            'JUSTIFICACION':decision['JUSTIFICACION'] if decision else 'Ubicacion congelada; beneficio reevaluado sin mover el punto.'}))
    for g,p in original:
        if p['ID_POLICIA'] not in SLOTS:assert active[p['ID_POLICIA']]['point'].equals(g)
    return rows,decisions,options


def main(accepted):
    OUT.mkdir(parents=True,exist_ok=True)
    prior=json.loads((BASE/'escenario-100-geo-20261004/RESULTADOS.json').read_text(encoding='utf-8'))
    # Take a fresh snapshot: pending unpublished UI work is not reverted or replaced.
    protected={path:sha(Path(path)) for path in prior['metadata']['sourceHashes']}
    for folder in ('propuesta-policia-30-20261003','propuesta-policia-30-final-100geo-20261004','escenario-100-geo-20261004','geocodificacion-pendientes-20261003'):
        for p in (BASE/folder).rglob('*'):
            if p.is_file() and p.suffix not in ('.lock','.lck','.log'):protected[str(p)]=sha(p)
    for p in ZIPS:protected[str(p)]=sha(p)
    for p in GDB.iterdir():
        if p.is_file() and p.suffix not in ('.lock','.lck'):protected[str(p)]=sha(p)
    canton=read_layer(ORIGINAL,'LIMITE_CANTONAL').geometry.iloc[0]
    platforms=records(read_layer(ORIGINAL,'PLATAFORMAS'));urban=unary_union([g for g,_ in platforms])
    inventory,cameras,camera_audit=consolidate_inventory(accepted,canton)
    new,axis,axis_comparison,sensitivity,catalog=prepare_environment(canton)
    events=records(read_layer(ORIGINAL,'INCIDENTES_ESCENARIOS'))
    stats={(scope,cat):records(read_layer(ORIGINAL,'GI_'+scope+'_'+cat)) for scope in ('URBANO','RURAL') for cat in CLASSES}
    hot=[(g,p) for rows in stats.values() for g,p in rows if p['GI_CLASS'].startswith('HOTSPOT')]
    dv=records(read_layer(ORIGINAL,'HOTSPOT_COINCIDENCIA_DV'))
    infrastructure=records(read_layer(ORIGINAL,'UPC_INFRAESTRUCTURA'));blocks=census_blocks()
    municipal_original=records(read_layer(ORIGINAL,'PROPUESTA_50_CONGELADA'))
    police_original=records(read_layer(ORIGINAL,'PROPUESTA_POLICIA_30'))
    lines=records(read_layer(ORIGINAL,'CORREDORES_REFERENCIA'))
    axes={key:unary_union([g for g,p in lines if p['CORREDOR']==key]) for key in dict.fromkeys(p['CORREDOR'] for _,p in lines)}
    axes['QUEBRADA_LAS_ABRAS']=axis
    a=coverage(cameras);a100=read_layer(TRIAL,'COBERTURA_A100').geometry.iloc[0]
    current_context=Context(events,hot,dv,a,[g for g,_ in cameras],[g for g,_ in municipal_original],infrastructure,blocks,urban,axes)
    municipal,moves,abras_options,abras_candidates=revise_abras(current_context,canton,new,axis,municipal_original)
    b=unary_union([a,coverage(municipal)])
    context=Context(events,hot,dv,b,[g for g,_ in cameras],[g for g,_ in municipal],infrastructure,blocks,urban,axes)
    police,decisions,police_options=review_police(context,police_original)
    masks={'A100':a100,'A':a,'B100':unary_union([a100,coverage(municipal_original)]),
        'B0':unary_union([a,coverage(municipal_original)]),'B':b,'C0':unary_union([b,coverage(police_original)]),'C':unary_union([b,coverage(police)])}
    incident_stats,hot_stats,corridor_stats,updated,_,_=scenario_evaluation(context,stats,dv,masks)
    territorial,population,block_results=[],[],[]
    for g,p in blocks:
        part=g.intersection(urban);props=dict(p)
        for scenario,mask in masks.items():
            area=part.intersection(mask).area
            props['COB_'+scenario+'_PCT']=pct(area,part.area) if part.area>AREA_EPS else None
            props['POB_'+scenario+'_CUBIERTA']=p['POBLACION']*area/g.area if p['POBLACION'] is not None else None
        props['AREA_URBANA_M2']=part.area
        block_results.append((g,props))
    for scenario,mask in masks.items():
        territorial.append({'ESCENARIO':scenario,'AREA_TOTAL_CANTON_KM2':canton.area/1e6,'AREA_CUBIERTA_CANTON_KM2':mask.intersection(canton).area/1e6,
            'PCT_CANTON':pct(mask.intersection(canton).area,canton.area),'AREA_TOTAL_URBANA_KM2':urban.area/1e6,
            'AREA_CUBIERTA_URBANA_KM2':mask.intersection(urban).area/1e6,'PCT_URBANO':pct(mask.intersection(urban).area,urban.area),
            'AREA_BUFFER_DISUELTO_KM2':mask.area/1e6})
        valid=[(g,p) for g,p in block_results if p['POBLACION'] is not None and p['AREA_URBANA_M2']>AREA_EPS]
        total=sum(p['POBLACION']*p['AREA_URBANA_M2']/g.area for g,p in valid)
        covered=sum(p['POB_'+scenario+'_CUBIERTA'] for _,p in valid)
        population.append({'ESCENARIO':scenario,'POBLACION_ANALIZADA':total,'POBLACION_POT_CUBIERTA':covered,
            'POBLACION_FUERA':total-covered,'PCT_POB_CUBIERTA':pct(covered,total),'AMBITO':'Union de 18 Plataformas; no poblacion rural cantonal completa',
            'MANZANAS_VALIDAS':len(valid),'MANZANAS_SIN_POBLACION':sum(p['POBLACION'] is None and p['AREA_URBANA_M2']>AREA_EPS for _,p in block_results)})
    marginal_municipal=[]
    for i,(g,p) in enumerate(municipal):
        disk=g.buffer(200,quad_segs=64);reference=unary_union([a,coverage(municipal[:i]+municipal[i+1:])])
        counters=Counter(q['CATEGORIA'] for point,q in events if q['AMBITO']!='EXTERNO_CANTON' and disk.covers(point) and not reference.covers(point))
        before_current=a100.intersection(disk).area;after_current=a.intersection(disk).area
        additions=[q['ID_CAMARA'] for point,q in cameras if q['ID_CAMARA'] in ('RIO-016-DOMO','RIO-017-FIJA','RIO-103-DOMO') and disk.intersection(point.buffer(200,quad_segs=64)).area>AREA_EPS]
        gains={key:axis.intersection(disk.difference(reference)).length for key,axis in axes.items()}
        r={'ID':p['ID_PROPUESTA'],'GRUPO':p['GRUPO'],'D_EXCLUSIVOS':counters['DELINCUENCIA'],'V_EXCLUSIVOS':counters['VIOLENCIA'],
            'C_EXCLUSIVOS':counters['CONVIVENCIA'],'SOLAPE_EXISTENTES_100_PCT':pct(before_current,disk.area),
            'SOLAPE_EXISTENTES_103_PCT':pct(after_current,disk.area),'SOLAPE_OTRAS49_PCT':pct(disk.intersection(reference).area,disk.area),
            'NUEVAS_EXISTENTES_RELACIONADAS':'|'.join(additions) or None,'DIST_EXISTENTE_M':min(g.distance(point) for point,_ in cameras),
            **{'LONGITUD_EXCLUSIVA_'+key+'_M':v for key,v in gains.items()}}
        marginal_municipal.append(r)
        p.update(REQUIERE_REVISION_REDUNDANCIA=bool(additions),COBERTURA_PREVIA=r['SOLAPE_EXISTENTES_103_PCT'],
            BENEFICIO_MARGINAL_M=sum(gains.values()),BENEFICIO_CONTEXTO='Exclusivo frente a 103+otras49; no sumable',
            **{'NUEVO_'+key+'_M':v for key,v in gains.items()},**r)
    effect_police=[]
    def exclusive(rows,base):
        answer={}
        for i,(point,p) in enumerate(rows):
            disk=point.buffer(200,quad_segs=64);reference=unary_union([base,coverage(rows[:i]+rows[i+1:])])
            counts=Counter(q['CATEGORIA'] for g,q in events if q['AMBITO']!='EXTERNO_CANTON' and disk.covers(g) and not reference.covers(g))
            answer[p['ID_POLICIA']]={'DV':counts['DELINCUENCIA']+counts['VIOLENCIA'],'SOLAPE':pct(reference.intersection(disk).area,disk.area)}
        return answer
    contexts={'100_ORIGINAL':exclusive(police_original,masks['B100']),
        '103_MUNICIPALES_ORIGINALES':exclusive(police_original,masks['B0']),
        '103_MUNICIPALES_CONSOLIDADAS':exclusive(police_original,masks['B']),
        '103_FINAL':exclusive(police,masks['B'])}
    for _,p in police_original:
        effect_police.append({'ID':p['ID_POLICIA'],**{field+'_'+key:value for key,d in contexts.items() for field,value in d[p['ID_POLICIA']].items()}})
    buffers=[]
    grouped={}
    for g,p in cameras:grouped.setdefault(g.wkb,(g,[]))[1].append(p['ID_CAMARA'])
    for g,ids in grouped.values():buffers.append((g.buffer(200,quad_segs=64),{'IDS_CAMARA':'|'.join(ids),'N_EQUIPOS':len(ids),'RADIO_M':200}))
    catalog.extend([export('CAMARAS_EXISTENTES_103_CONSOLIDADA',cameras,'01_CAMARAS_EXISTENTES',True),
        export('AUDITORIA_CAMARAS_EXISTENTES',camera_audit,'01_CAMARAS_EXISTENTES',True),
        export('INVENTARIO_ORIGINAL_103',inventory,'01_CAMARAS_EXISTENTES'),
        export('ESCENARIO_103_GEO',cameras,'01_CAMARAS_EXISTENTES'),
        export('PROPUESTA_50_CONSOLIDADA',municipal,'02_PROPUESTA_MUNICIPAL',True),
        export('PROPUESTA_50_ORIGINAL',municipal_original,'02_PROPUESTA_MUNICIPAL'),
        export('LAS_ABRAS_4_ORIGINAL',[r for r in municipal_original if r[1]['GRUPO']=='LAS_ABRAS'],'02_PROPUESTA_MUNICIPAL',True),
        export('LAS_ABRAS_4_REVISADA',[r for r in municipal if r[1]['GRUPO']=='LAS_ABRAS'],'02_PROPUESTA_MUNICIPAL',True),
        export('CANDIDATOS_ABRAS_MAATE',abras_candidates,'02_PROPUESTA_MUNICIPAL',True),
        export('PROPUESTA_POLICIA_30_FINAL',police,'03_PROPUESTA_POLICIA',True),
        export('POLICIA_30_ORIGINAL',police_original,'03_PROPUESTA_POLICIA'),
        export('POLICIA_REVISION_100_GEO',records(read_layer(PREVIOUS,'PROPUESTA_POLICIA_30_REVISION')),'03_PROPUESTA_POLICIA'),
        export('INCIDENTES_ANALITICOS',[(g,{**{k:v for k,v in p.items() if not k.startswith('CUB')},
            **{'CUB_'+s:mask.covers(g) for s,mask in masks.items()}}) for g,p in events],'05_INCIDENTES',True),
        export('CORREDORES_REFERENCIA_ANTERIOR',lines,'06_CORREDORES'),
        export('CORREDORES_CONSOLIDADOS',[(g,{'CORREDOR':key,'LONGITUD_M':g.length}) for key,g in axes.items()],'06_CORREDORES',True),
        export('UPC_INFRAESTRUCTURA',infrastructure,'10_INFRAESTRUCTURA_POLICIAL',True),
        export('BUFFERS_EXISTENTES_SITIOS_200M',buffers,'11_COBERTURAS'),
        export('PLATAFORMAS_TERRITORIALES',platforms,'12_DIAGNOSTICO_FINAL',True),
        export('LIMITE_CANTONAL',[(canton,{'FUENTE':'Limite original del proyecto'})],'12_DIAGNOSTICO_FINAL',True),
        export('MANZANAS_COBERTURA',block_results,'12_DIAGNOSTICO_FINAL')])
    rural_pkg=BASE/'optimizacion-municipal-50-20261003/PROPUESTA_50_OPTIMIZADA.gpkg'
    for name,_ in pyogrio.list_layers(rural_pkg):
        if 'CABECERA' in name:catalog.append(export(name,records(read_layer(rural_pkg,name)),'07_CABECERAS_RURALES',True))
    for (scope,cat),rows in updated.items():catalog.append(export('GI_'+scope+'_'+cat,rows,'04_HOTSPOTS'))
    for cat in CLASSES:catalog.append(export('HOTSPOT_'+cat,[(g,p) for (scope,c),rows in updated.items() if c==cat for g,p in rows if p['GI_CLASS'].startswith('HOTSPOT')],'04_HOTSPOTS',True))
    for s,g in masks.items():catalog.append(export('COBERTURA_'+s,[(g,{'ESCENARIO':s,'RADIO_M':200})],'11_COBERTURAS',True))
    catalog=[r for r in catalog if r]
    for name,rows in (('AUDITORIA_CAMARAS_EXISTENTES',[p for _,p in camera_audit]),('COMPARACION_LAS_ABRAS_4',moves),
        ('ALTERNATIVAS_LAS_ABRAS',abras_options),('POLICIA_DECISIONES_CINCO',decisions),('POLICIA_ACTUALES_Y_25_ALTERNATIVAS',police_options),
        ('REEVALUACION_MUNICIPAL_50',marginal_municipal),('EFECTO_CAMARAS_NUEVAS_POLICIA',effect_police),
        ('COBERTURA_TERRITORIAL',territorial),('COBERTURA_POBLACIONAL',population),('INCIDENTES_CUBIERTOS',incident_stats),
        ('HOTSPOTS_ATENDIDOS',hot_stats),('CORREDORES_CUBIERTOS',corridor_stats)):
        csvsave(name+'.csv',rows)
        if name!='AUDITORIA_CAMARAS_EXISTENTES':pyogrio.write_dataframe(pd.DataFrame(clean(rows)),PACKAGE,layer=name)
    unchanged=all(sha(Path(path))==digest for path,digest in protected.items());assert unchanged
    quality={'inventory':len(cameras),'geometries':sum(g is not None for g,_ in cameras),'null':0,'duplicateIds':0,
        'uniqueSites':len(grouped),'coincidentGroups':[ids for _,ids in grouped.values() if len(ids)>1],
        'municipal':len(municipal),'municipalGroups':dict(Counter(p['GRUPO'] for _,p in municipal)),
        'police':len(police),'frozenMunicipal':46,'frozenPolice':25,'existingOutsideCanton':[p['ID_CAMARA'] for _,p in cameras if not p['DENTRO_CANTON']],
        'sourcesUnchanged':unchanged,'giRecomputed':False,'commit':False,'push':False,'sourceHashes':protected}
    result={'generatedAt':datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'),'quality':quality,
        'cameraAudit':[p for _,p in camera_audit],'axisComparison':axis_comparison,'axisSensitivity':sensitivity,
        'abrasMoves':moves,'policeDecisions':decisions,'policeOptions':police_options,'municipalReevaluation':marginal_municipal,
        'policeEffects':effect_police,'territorial':territorial,'population':population,'incidents':incident_stats,
        'hotspots':hot_stats,'corridors':corridor_stats,'catalog':catalog,
        'warnings':['Confianza MEDIA de 016/017 aceptada por usuario; V/Y y 943.98m documentados, no confirmacion del poste.',
            'RIO-103 geocodificada por cruce censal exacto; corroboracion municipal insuficiente, confianza MEDIA.',
            'Cunduana es ambiental, distante de MAATE; no entra en incidentes ni Gi* ni seleccion policial.',
            'Cobertura potencial circular, no visibilidad real; superficies disueltas, sitios coincidentes sin doble conteo.',
            'Poblacion cubierta es estimacion areal CPV2022 en 18Plataformas; no se extrapola a toda la poblacion rural.',
            'Nivel D/V residual es coincidencia geometrica de pruebas individuales, no nueva significancia conjunta.',
            'Reemplazos propuestos pueden reducir area o nivel Gi* atendido aunque aumenten eventos; no optimo global.',
            'Eje MAATE suministrado adoptado operativamente dentro del canton; atribucion oficial no certificada externamente.',
            'Coincidencia lineal exacta sensible a digitalizacion, segmentacion y redondeo GEOS al recortar. No representa equivalencia fisica de trazados; revisar tambien las sensibilidades documentadas.',
            'Nodo vial no certifica poste, energia, permisos ni viabilidad de instalacion. No publicado.']}
    jsave('RESULTADOS.json',result)
    csvsave('CATALOGO_CAPAS.csv',catalog)
    make_report(result)
    print(json.dumps({'quality':{k:v for k,v in quality.items() if k!='sourceHashes'},'abrasMoves':moves,
        'policeDecisions':decisions,'territorial':territorial,'population':population},ensure_ascii=False),flush=True)


def make_report(result):
    def table(rows,fields):
        def fmt(v):
            if v is None:return 'No disponible'
            if isinstance(v,float):return f'{v:.3f}'
            return str(v).replace('|',' / ')
        return '\n'.join(['| '+' | '.join(fields)+' |','| '+' | '.join('---' for _ in fields)+' |']+
            ['| '+' | '.join(fmt(r.get(k)) for k in fields)+' |' for r in rows])
    final=[]
    def row(name,values,unit):final.append({'INDICADOR':name,'103':values[0],'103+50':values[1],'103+50+30':values[2],'UNIDAD':unit})
    for field,label,unit in (('AREA_CUBIERTA_CANTON_KM2','Superficie potencial cubierta cantonal','km2'),
        ('PCT_CANTON','Porcentaje territorial cantonal','%'),('AREA_CUBIERTA_URBANA_KM2','Superficie potencial cubierta en 18Plataformas','km2'),
        ('PCT_URBANO','Porcentaje territorial en 18Plataformas','%')):
        row(label,[next(r[field] for r in result['territorial'] if r['ESCENARIO']==s) for s in ('A','B','C')],unit)
    for field,label,unit in (('POBLACION_POT_CUBIERTA','Poblacion urbana potencialmente cubierta','habitantes estimados'),
        ('PCT_POB_CUBIERTA','Porcentaje poblacional urbano potencialmente cubierto','%')):
        row(label,[next(r[field] for r in result['population'] if r['ESCENARIO']==s) for s in ('A','B','C')],unit)
    for cat in CLASSES:
        row(cat+' eventos cubiertos',[next(r['PCT_CUBIERTO'] for r in result['incidents'] if r['ESCENARIO']==s and r['AMBITO']=='CANTONAL' and r['CATEGORIA']==cat) for s in ('A','B','C')],'%')
        for scope in ('URBANO','RURAL'):
            for field,label in (('CUBIERTO','completos'),('PARCIAL','parciales'),('SIN_COBERTURA','sin cobertura')):
                row(cat+' Hot Spots '+scope+' '+label,[sum(r[field] for r in result['hotspots'] if r['ESCENARIO']==s and r['AMBITO']==scope and r['CATEGORIA']==cat) for s in ('A','B','C')],'celdas 99/95/90')
    for corridor in ('ANILLO_VIAL','CICLOVIAS','BOULEVARD_MACAJI_BELLAVISTA','QUEBRADA_LAS_ABRAS'):
        row(corridor,[next(r['PCT_CUBIERTO'] for r in result['corridors'] if r['ESCENARIO']==s and r['CORREDOR']==corridor) for s in ('A','B','C')],'% longitud')
    csvsave('COMPARACION_FINAL_103_153_183.csv',final)
    result['finalComparison']=final
    jsave('RESULTADOS.json',result)
    lines=['# Consolidacion cartografica y evaluacion de 183 equipos existentes/propuestos','',
        '**Sin commit ni push. 103 existentes + 50 municipales + 30 policiales.**',
        '## Calidad y alcance','103 registros existentes con geometria, 100 emplazamientos distintos. Tres pares comparten punto y direccion documental: 007/008, 016/017 y 099/100. Los pares 007/008 y 099/100 ya eran coincidentes en el inventario original; no se eliminan ni desplazan. Cada emplazamiento produce un solo buffer de superficie. Los 99 puntos originales y RIO-085 no cambian. Las tres incorporaciones son geocodificaciones cartograficas, no certificacion de postes. La discrepancia de 016/017 fue aceptada expresamente con confianza MEDIA.',
        '## Auditoria de los cuatro registros',table(result['cameraAudit'],['ID_CAMARA','DIRECCION_DOCUMENTAL','DIRECCION_CARTOGRAFICA','X','Y','METODO_GEO','FUENTE_GEO','CONFIANZA_GEO','OBSERVACION_GEO']),
        '## Nuevo insumo ambiental','Cunduana: 10 puntos y dos tramos de limpieza, 2687.916m. Atributos y geometrias originales conservados. No son incidentes policiales; no entran en Gi*. Se conservan todas las 13 capas de Las Abras entregadas, incluso copias geometricamente duplicadas, con nombres y rutas en el catalogo.',
        '## Eje MAATE y diferencias',table([result['axisComparison']],list(result['axisComparison'])),table(result['axisSensitivity'],list(result['axisSensitivity'][0])),
        'La interseccion exacta puede ser pequena por diferencias de digitalizacion. Las sensibilidades no se usan para modificar ejes ni ocultar diferencias. Se preserva el eje completo de 8.977km; el analisis operativo usa solamente los 5.215km dentro del canton. ABRAS_DIFERENCIAS compara el eje anterior con MAATE cantonal; ABRAS_DIFERENCIAS_COMPLETAS compara ambos ejes completos. Los campos con COMPLETA corresponden al segundo ambito; los demas de diferencia al primero. No mezclar las longitudes completas con diferencias recortadas.',
        'Cunduana esta a aproximadamente 3.0-3.7km del nuevo eje; no se inventa coincidencia con Las Abras ni beneficio dentro de radios 200m. Las capas Jose Marti son los puntos/franjas suministrados; no se inventa un limite de urbanizacion.',
        '## Reglas locales para las cuatro de Las Abras','Solo se consideran intersecciones geometricas reales MAATE-vialidad dentro del canton. Se comparan con 103 existentes +46 municipales congeladas +otras3 de Las Abras. Una sustitucion debe mejorar longitud marginal MAATE y no reducir el numero de dimensiones con evidencia. Orden lexicografico: evidencia Cunduana/limpieza si existe, dimensiones documentadas, referencia Jose Marti, longitud nueva, D/V y Convivencia complementarios, menor solape. Dimensiones: cruce vial-MAATE, franja, Jose Marti, eventos nuevos, poblacion urbana y Hot Spot D/V. No hay AHP, pesos ni intervalos iguales. Este conteo es descriptivo/operativo, no un indice validado universalmente.',
        table(result['abrasMoves'],list(result['abrasMoves'][0])),
        '## Reevaluacion de municipales','22 cabeceras y24estructurales conservan exactamente su posicion. REEVALUACION_MUNICIPAL_50.csv identifica solape adicional de las nuevas existentes y beneficio exclusivo contra otras49; no sumar marginales. No se desplazan otros puntos por proximidad.',
        '## Revision policial local','Se parte de las 30 originales; los cuatro cambios de la corrida anterior siguen como propuestas no aprobadas y se conservan separados. Solo se revisan POL-08/20/21/22/30; otras25 congeladas. Mismos candidatos originales y Gi* intacto. Coincidencia D/V residual significativa, aumentar eventos D+V sin reducir D o V y reducir solape. Sin umbrales arbitrarios de distancia, solape o eventos; corredores/Cunduana/limpieza no participan en seleccion.',
        table(result['policeDecisions'],list(result['policeDecisions'][0])),
        'POLICIA_ACTUALES_Y_25_ALTERNATIVAS.csv conserva actual +5 alternativas por punto; EFECTO_CAMARAS_NUEVAS_POLICIA.csv separa efecto 100 a103 con municipales originales, cambio Las Abras y revision policial.',
        'En la comparacion 100 a103 con propuestas originales congeladas, ninguna policial cambia su beneficio exclusivo D/V ni su solape mas alla de precision numerica. La nueva relacion municipal detectada es MUN-036 con el sitio016/017: solape de existentes pasa de0.061% a1.426%; se conserva la propuesta. Incorporar las tres pendientes aumenta cobertura de5eventosD,3V y19Convivencia en el escenario de existentes.',
        '## Comparacion final',table(final,list(final[0])),
        'Hot Spots completamente cubiertos, parcialmente cubiertos y sin cobertura se distinguen; no se suman categorias como si fueran celdas unicas. Urbanas y rurales tienen dimensiones diferentes. Gi*, z-score, p-value y geometria no se recalculan.',
        '## Comparacion100 a103',table([r for r in result['territorial'] if r['ESCENARIO'] in ('A100','A')],list(result['territorial'][0])),
        table([r for r in result['population'] if r['ESCENARIO'] in ('A100','A')],list(result['population'][0])),
        table([r for r in result['incidents'] if r['ESCENARIO'] in ('A100','A') and r['AMBITO']=='CANTONAL'],list(result['incidents'][0])),
        '## Metodos de cobertura','Radios de 200m en EPSG:32717, 64 segmentos por cuadrante. Disolver sitios/escenarios; no sumar discos superpuestos. 016/017 comparten un solo buffer de superficie. Territorial cantonal usa el limite original; urbano usa union18Plataformas. Todos los registros existentes se conservan incluso fuera de plataformas.',
        'Poblacion: estimacion areal CPV2022 por manzana, fraccion de superficie cubierta dentro de union18Plataformas, con denominador de poblacion analizada en el mismo ambito. Valores faltantes se mantienen No disponible; no se usa177213 como denominador de un subconjunto ni se estima toda la poblacion rural. NO es visibilidad real ni cobertura efectiva.',
        'Incidentes: coordenadas originales, peso1 por observacion; D/V/C analiticos, 11142 cantonales mas8externos conservados. No nearest-neighbor a manzanas; no utilizar Cunduana como categoria policial.',
        '## Advertencias',*['- '+v for v in result['warnings']],
        '## Catalogo y grupos GIS',table(result['catalog'],['group','name','records','crs','source']),
        'GeoPackage consolidado en EPSG:32717. Proyecto QGIS con12grupos, capas originales y derivados identificados. GeoJSON visual EPSG:4326. ZIP conserva fuentes entregadas, auditorias, CSV, informe, mapas y archivos GIS.',
        '**Las propuestas finales requieren revision y validacion operativa; no hay publicacion ni sustitucion del visor.**']
    (OUT/'INFORME_CONSOLIDACION.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')


def refresh_geocoding_metadata(accepted):
    result=json.loads((OUT/'RESULTADOS.json').read_text(encoding='utf-8'))
    canton=read_layer(ORIGINAL,'LIMITE_CANTONAL').geometry.iloc[0]
    _,cameras,audit=consolidate_inventory(accepted,canton)
    previous=records(read_layer(PACKAGE,'CAMARAS_EXISTENTES_103_CONSOLIDADA'))
    assert all(g.equals(old) and p['ID_CAMARA']==q['ID_CAMARA'] for (g,p),(old,q) in zip(cameras,previous))
    for name,rows,visual in (('CAMARAS_EXISTENTES_103_CONSOLIDADA',cameras,True),('AUDITORIA_CAMARAS_EXISTENTES',audit,True),('ESCENARIO_103_GEO',cameras,False)):
        entry=export(name,rows,'01_CAMARAS_EXISTENTES',visual)
        result['catalog']=[entry if r['name']==name else r for r in result['catalog']]
    result['cameraAudit']=[p for _,p in audit]
    _,_,delta,sensitivity,environment=prepare_environment(canton)
    result['axisComparison']=delta;result['axisSensitivity']=sensitivity
    by_name={r['name']:r for r in environment}
    result['catalog']=[by_name.pop(r['name'],r) for r in result['catalog']]+list(by_name.values())
    csvsave('AUDITORIA_CAMARAS_EXISTENTES.csv',result['cameraAudit'])
    csvsave('CATALOGO_CAPAS.csv',result['catalog']);make_report(result)
    print('Metadatos actualizados; coordenadas y todos los resultados numericos intactos.')


if __name__=='__main__':
    warnings.filterwarnings('ignore',category=UserWarning)
    parser=argparse.ArgumentParser();parser.add_argument('--accept-census-prison',action='store_true')
    parser.add_argument('--refresh-geocoding-metadata',action='store_true');args=parser.parse_args()
    if args.refresh_geocoding_metadata:refresh_geocoding_metadata(args.accept_census_prison)
    else:main(args.accept_census_prison)
