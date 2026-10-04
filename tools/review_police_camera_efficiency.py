"""Review four police slots against unselected road nodes; preserve all original packages."""
import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import pyogrio
from shapely import STRtree
from shapely.ops import unary_union

from build_police_camera_proposal import (
    ROOT, Context, coverage_class, records, read_layer, sha, pct, CLASSES,
    original_statistics, scenario_evaluation, geojson, parts, UNPROJECT, AREA_EPS)

SOURCE = ROOT / 'data/seguridad-riobamba/propuesta-policia-30-20261003'
PACKAGE = SOURCE / 'PROPUESTA_POLICIA_30.gpkg'
OUT = ROOT / 'data/seguridad-riobamba/propuesta-policia-30-revision-20261003'
SLOTS = ('POL-20','POL-21','POL-22','POL-30')


def write_json(name, value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf-8')


def write_csv(name, rows):
    fields=list(dict.fromkeys(k for p in rows for k in p))
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fields)
        writer.writeheader()
        writer.writerows(rows)


def export(name, rows, visual=True):
    frame=gpd.GeoDataFrame([p for _,p in rows],geometry=[g for g,_ in rows],crs=32717)
    pyogrio.write_dataframe(frame,OUT/'PROPUESTA_POLICIA_30_REVISION.gpkg',layer=name)
    if visual:write_json(name+'.geojson',geojson(rows))
    return {'name':name,'records':len(frame),'crs':'EPSG:32717','fields':list(frame.columns[:-1])}


def preferences(candidate, current):
    """Improve observed D/V coverage and redundancy; report area/level tradeoffs separately."""
    return (candidate['COINCIDENCIA_DV_RESIDUAL_M2']>AREA_EPS
        and candidate['EVENTOS_D_NUEVOS']>=current['EVENTOS_D_NUEVOS']
        and candidate['EVENTOS_V_NUEVOS']>=current['EVENTOS_V_NUEVOS']
        and candidate['EVENTOS_DV_NUEVOS']>current['EVENTOS_DV_NUEVOS']
        and candidate['SOLAPE_PREVIO_PCT']<current['SOLAPE_PREVIO_PCT'])


def revision_rank(row):
    return (row['EVENTOS_DV_NUEVOS'],row['NIVEL_DV_RESIDUAL'],
        row['COINCIDENCIA_DV_RESIDUAL_M2'],row['AREA_HOTSPOT_D_NUEVA_M2']+row['AREA_HOTSPOT_V_NUEVA_M2'],
        -row['SOLAPE_PREVIO_PCT'],row['EVENTOS_C_NUEVOS'],row['GRADO_NODO'])


class Evaluator:
    def __init__(self, context):
        self.context=context

    def prepare(self, coverage):
        self.coverage=coverage
        self.covered={i for i,(g,_) in enumerate(self.context.events) if coverage.covers(g)}
        self.uncovered=[g.difference(coverage) for g,_ in self.context.hot]
        self.dv_uncovered=[g.difference(coverage) for g,_ in self.context.dv]

    def evaluate(self, c, other_points):
        counts=self.context.new_counts(c,self.covered)
        areas={cat:0. for cat in CLASSES}
        levels={cat:0 for cat in CLASSES}
        new_dv,level_dv,states=0.,0,set()
        for i,_ in c['hot']:
            g,p=self.context.hot[i]
            if p['AMBITO']!=c['scope']:continue
            area=c['disk'].intersection(self.uncovered[i]).area
            if area>AREA_EPS:
                areas[p['CATEGORIA']]+=area
                levels[p['CATEGORIA']]=max(levels[p['CATEGORIA']],p['NIVEL'])
        for i,_ in c['dv']:
            g,p=self.context.dv[i]
            if p['AMBITO']!=c['scope']:continue
            area=c['disk'].intersection(self.dv_uncovered[i]).area
            if area>AREA_EPS:
                new_dv+=area
                level_dv=max(level_dv,p['NIVEL_MIN_DV'])
                states.add(coverage_class(g.intersection(self.coverage).area/g.area))
        p=c['props']
        return {'ID_CANDIDATO':c['id'],'X':c['point'].x,'Y':c['point'].y,
            'AMBITO_HOTSPOT':c['scope'],'NIVEL_DEL':p['NIVEL_DEL'],'NIVEL_VIOL':p['NIVEL_VIOL'],
            'COINCIDENCIA_DV':bool(c['dv']),'NIVEL_DEL_RESIDUAL':levels['DELINCUENCIA'],
            'NIVEL_VIOL_RESIDUAL':levels['VIOLENCIA'],'NIVEL_DV_RESIDUAL':level_dv,
            'EVENTOS_D_NUEVOS':counts['DELINCUENCIA'],'EVENTOS_V_NUEVOS':counts['VIOLENCIA'],
            'EVENTOS_DV_NUEVOS':counts['DELINCUENCIA']+counts['VIOLENCIA'],'EVENTOS_C_NUEVOS':counts['CONVIVENCIA'],
            'AREA_HOTSPOT_D_NUEVA_M2':areas['DELINCUENCIA'],'AREA_HOTSPOT_V_NUEVA_M2':areas['VIOLENCIA'],
            'COINCIDENCIA_DV_RESIDUAL_M2':new_dv,'ESTADO_HOTSPOT_DV_PREVIO':'|'.join(sorted(states)) or 'SIN REMANENTE D/V',
            'SOLAPE_PREVIO_PCT':pct(c['disk'].intersection(self.coverage).area,c['disk'].area),
            'DIST_EXISTENTE_M':c['distanceExisting'],'DIST_MUNICIPAL_M':c['distanceMunicipal'],
            'DIST_POLICIA_M':min(c['point'].distance(point) for point in other_points),
            'UPC_CERCANA':p['UPC_CERCANA'],'NOMBRE_UPC':p['NOMBRE_UPC'],'DIST_UPC_M':p['DIST_UPC_M'],
            'INTERSECCION_O_NODO':p['INTERSECCION_O_NODO'],'GRADO_NODO':c['degree']}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    prior=json.loads((SOURCE/'RESULTADOS.json').read_text(encoding='utf-8'))
    protected={str(p):sha(p) for p in SOURCE.rglob('*') if p.is_file() and p.suffix not in ('.log','.lock','.lck')}
    protected.update(prior['metadata']['sourceHashes'])
    assert all(sha(Path(p))==digest for p,digest in protected.items())
    original=records(read_layer(PACKAGE,'PROPUESTA_POLICIA_30'))
    originals={p['ID_POLICIA']:(g,p) for g,p in original}
    cameras=records(read_layer(PACKAGE,'CAMARAS_EXISTENTES_103'))
    municipal=records(read_layer(PACKAGE,'PROPUESTA_50_CONGELADA'))
    events=records(read_layer(PACKAGE,'INCIDENTES_ESCENARIOS'))
    platforms=records(read_layer(PACKAGE,'PLATAFORMAS'))
    stats=original_statistics()
    hot=[(g,p) for rows in stats.values() for g,p in rows if p['GI_CLASS'].startswith('HOTSPOT')]
    dv=records(read_layer(PACKAGE,'HOTSPOT_COINCIDENCIA_DV'))
    current=read_layer(PACKAGE,'COBERTURA_A').geometry.iloc[0]
    base=read_layer(PACKAGE,'COBERTURA_B').geometry.iloc[0]
    previous=read_layer(PACKAGE,'COBERTURA_C').geometry.iloc[0]
    lines=records(read_layer(PACKAGE,'CORREDORES_REFERENCIA'))
    axes={key:unary_union([g for g,p in lines if p['CORREDOR']==key]) for key in dict.fromkeys(p['CORREDOR'] for _,p in lines)}
    context=Context(events,hot,dv,base,[g for g,_ in cameras if g is not None],[g for g,_ in municipal],
        [],[],unary_union([g for g,_ in platforms]),axes)
    raw=records(read_layer(PACKAGE,'CANDIDATOS_POLICIA'))
    candidates={p['ID_CANDIDATO']:context.candidate({'point':g,'id':p['ID_CANDIDATO'],'degree':p['GRADO_NODO'],'props':p}) for g,p in raw}
    original_ids={p['ID_CANDIDATO'] for _,p in original}
    active={id:candidates[p['ID_CANDIDATO']] for id,(_,p) in originals.items()}
    evaluator=Evaluator(context)
    comparisons,decisions,all_evaluated,contexts=[],[],[],[]
    for step,slot in enumerate(SLOTS,1):
        others={id:c for id,c in active.items() if id!=slot}
        reference=unary_union([base]+[c['disk'] for c in others.values()])
        evaluator.prepare(reference)
        current_row=evaluator.evaluate(active[slot],[c['point'] for c in others.values()])
        used={c['id'] for c in others.values()}
        eligible=[]
        for c in candidates.values():
            if c['id'] in original_ids or c['id'] in used or c['scope']!=active[slot]['scope']:continue
            row=evaluator.evaluate(c,[o['point'] for o in others.values()])
            if row['COINCIDENCIA_DV_RESIDUAL_M2']<=AREA_EPS:continue
            row['PREFERIBLE_AL_ACTUAL']=preferences(row,current_row)
            row['ID_POLICIA_REVISADA']=slot
            row['ITERACION_REVISION']=step
            row['JUSTIFICACION']=(f"Nodo vial {row['ID_CANDIDATO']}, coincidencia significativa D/V residual al {row['NIVEL_DV_RESIDUAL']}%. "
                f"Respecto a existentes + municipales + otras29 policiales: {row['EVENTOS_D_NUEVOS']} D y {row['EVENTOS_V_NUEVOS']} V nuevos; "
                f"area D/V nueva {row['AREA_HOTSPOT_D_NUEVA_M2']:.1f}/{row['AREA_HOTSPOT_V_NUEVA_M2']:.1f} m2; "
                f"solape {row['SOLAPE_PREVIO_PCT']:.2f}%. {'Mejora eventos D/V sin perder D o V y reduce solape; area y nivel estadistico pueden cambiar y requieren revision.' if row['PREFERIBLE_AL_ACTUAL'] else 'No mejora simultaneamente eventos D/V y solape sin perder D o V; consultar valores sin aplicar cortes automaticos.'} "
                "Requiere validacion de campo. UPC y corredores no determinan la seleccion.")
            eligible.append(row)
        eligible.sort(key=lambda r:(r['PREFERIBLE_AL_ACTUAL'],revision_rank(r)),reverse=True)
        assert len(eligible)>=5,slot
        current_row.update({'ID_POLICIA_REVISADA':slot,'ITERACION_REVISION':step,'TIPO_OPCION':'ACTUAL','ORDEN_ALTERNATIVA':0,
            'PREFERIBLE_AL_ACTUAL':False,'JUSTIFICACION':'Punto original comparado con exactamente las mismas otras29 camaras que sus alternativas.'})
        top=[{**r,'TIPO_OPCION':'ALTERNATIVA','ORDEN_ALTERNATIVA':i} for i,r in enumerate(eligible[:5],1)]
        comparisons.extend([current_row]+top)
        all_evaluated.extend(eligible)
        winner=eligible[0] if eligible[0]['PREFERIBLE_AL_ACTUAL'] else current_row
        replace=winner is not current_row
        if replace:active[slot]=candidates[winner['ID_CANDIDATO']]
        reason=(f"Reemplazo propuesto: {current_row['EVENTOS_DV_NUEVOS']} a {winner['EVENTOS_DV_NUEVOS']} eventos D/V marginales, "
            f"sin reducir D o V por separado, solape {current_row['SOLAPE_PREVIO_PCT']:.2f}% a {winner['SOLAPE_PREVIO_PCT']:.2f}%; "
            f"coincidencia D/V residual {current_row['NIVEL_DV_RESIDUAL']}% a {winner['NIVEL_DV_RESIDUAL']}%. "
            f"Area D nueva {current_row['AREA_HOTSPOT_D_NUEVA_M2']:.1f} a {winner['AREA_HOTSPOT_D_NUEVA_M2']:.1f} m2; "
            f"area V nueva {current_row['AREA_HOTSPOT_V_NUEVA_M2']:.1f} a {winner['AREA_HOTSPOT_V_NUEVA_M2']:.1f} m2. "
            "Propuesta provisional: no supone mejora en todas las superficies o niveles. No se uso un umbral fijo de distancia, solape o eventos." if replace else
            "Mantener: ninguna alternativa mejora eventos D/V y solape sin perder D o V, conservando remanente significativo D/V. Proximidad por si sola no obliga a reemplazar.")
        old=originals[slot][1]
        decision={'ID':slot,'DECISION':'REEMPLAZAR' if replace else 'MANTENER','MANTENER_REEMPLAZAR':'REEMPLAZAR' if replace else 'MANTENER',
            'CANDIDATO_ANTERIOR':current_row['ID_CANDIDATO'],'CANDIDATO_NUEVO':winner['ID_CANDIDATO'],'MOTIVO':reason,
            'EVENTOS_DV_ANTES':current_row['EVENTOS_DV_NUEVOS'],'EVENTOS_DV_DESPUES':winner['EVENTOS_DV_NUEVOS'],
            'EVENTOS_D_ANTES':current_row['EVENTOS_D_NUEVOS'],'EVENTOS_D_DESPUES':winner['EVENTOS_D_NUEVOS'],
            'EVENTOS_V_ANTES':current_row['EVENTOS_V_NUEVOS'],'EVENTOS_V_DESPUES':winner['EVENTOS_V_NUEVOS'],
            'SOLAPE_ANTES':current_row['SOLAPE_PREVIO_PCT'],'SOLAPE_DESPUES':winner['SOLAPE_PREVIO_PCT'],
            'AREA_D_ANTES_M2':current_row['AREA_HOTSPOT_D_NUEVA_M2'],'AREA_D_DESPUES_M2':winner['AREA_HOTSPOT_D_NUEVA_M2'],
            'AREA_V_ANTES_M2':current_row['AREA_HOTSPOT_V_NUEVA_M2'],'AREA_V_DESPUES_M2':winner['AREA_HOTSPOT_V_NUEVA_M2'],
            'NIVEL_DV_ANTES':current_row['NIVEL_DV_RESIDUAL'],'NIVEL_DV_DESPUES':winner['NIVEL_DV_RESIDUAL'],
            'EVENTOS_DV_HISTORICOS':old['BENEFICIO_MARGINAL'],'SOLAPE_HISTORICO':old['SOLAPE_UNION_PREVIA_PCT'],
            'CANDIDATOS_COMPARADOS':len(eligible),'ALTERNATIVAS_PREFERIBLES':sum(r['PREFERIBLE_AL_ACTUAL'] for r in eligible),
            'ITERACION_REVISION':step,'CONTEXTO':'Actuales + 50 municipales + otras29 policiales; cambios anteriores de revision conservados'}
        decisions.append(decision)
        contexts.append((reference,{'ID_POLICIA_REVISADA':slot,'ITERACION_REVISION':step,'RADIO_M':200}))
        print(json.dumps(decision,ensure_ascii=False),flush=True)
    future=unary_union([base]+[c['disk'] for c in active.values()])
    assert len(active)==30 and len({c['point'].wkb for c in active.values()})==30
    for id,(g,_) in originals.items():
        if id not in SLOTS:assert active[id]['point'].equals(g)
    masks={'A':current,'B':base,'C0':previous,'C':future}
    inc,hot_stats,corridors,updated,dv_rows,dv_remaining=scenario_evaluation(context,stats,dv,masks)
    proposal=[]
    for id,c in active.items():
        rest=unary_union([base]+[v['disk'] for key,v in active.items() if key!=id])
        evaluator.prepare(rest)
        m=evaluator.evaluate(c,[v['point'] for key,v in active.items() if key!=id])
        lon,lat=UNPROJECT(c['point'].x,c['point'].y)
        original_props=originals[id][1]
        decision=next((d for d in decisions if d['ID']==id),None)
        justification=decision['MOTIVO'] if decision else original_props['JUSTIFICACION']
        props={**c['props'],'ID_POLICIA':id,'X':c['point'].x,'Y':c['point'].y,'LONGITUD':lon,'LATITUD':lat,
            'SELECCIONADO':True,
            'DECISION_REVISION':decision['DECISION'] if decision else 'FIJA_NO_REVISADA',
            'PRIORIDAD':1,'CATEGORIA_PRINCIPAL':'DELINCUENCIA + VIOLENCIA','DIST_POLICIA':m['DIST_POLICIA_M'],
            'BENEFICIO_MARGINAL':m['EVENTOS_DV_NUEVOS'],'EVENTOS_D_EXCLUSIVOS_FINAL':m['EVENTOS_D_NUEVOS'],
            'EVENTOS_V_EXCLUSIVOS_FINAL':m['EVENTOS_V_NUEVOS'],'EVENTOS_C_EXCLUSIVOS_FINAL':m['EVENTOS_C_NUEVOS'],
            'SOLAPE_RESTO_FINAL_PCT':m['SOLAPE_PREVIO_PCT'],'AREA_D_EXCLUSIVA_FINAL_M2':m['AREA_HOTSPOT_D_NUEVA_M2'],
            'AREA_V_EXCLUSIVA_FINAL_M2':m['AREA_HOTSPOT_V_NUEVA_M2'],
            **{'NUEVOS_EVENTOS_'+cat+'_CUBIERTOS':m[key] for cat,key in (
                ('DELINCUENCIA','EVENTOS_D_NUEVOS'),('VIOLENCIA','EVENTOS_V_NUEVOS'),('CONVIVENCIA','EVENTOS_C_NUEVOS'))},
            'BENEFICIO_HISTORICO_ORIGINAL':original_props['BENEFICIO_MARGINAL'],
            'SOLAPE_HISTORICO_ORIGINAL':original_props['SOLAPE_UNION_PREVIA_PCT'],
            'BENEFICIO_CONTEXTO':'Aporte exclusivo frente aB+otras29 del conjunto revisado; no sumar entre camaras',
            'JUSTIFICACION':justification,'ESTADO':'PROPUESTA_PARA_VALIDACION_POLICIA'}
        proposal.append((c['point'],props))
    alternatives=[(candidates[p['ID_CANDIDATO']]['point'],p) for p in comparisons]
    remainder=[]
    for rows in updated.values():
        for g,p in rows:
            if p['GI_CLASS'].startswith('HOTSPOT'):remainder.extend((part,p) for part in parts(g.difference(future),2) if part.area>AREA_EPS)
    system80=[(g,{'ID_NUEVA':p['ID_PROPUESTA'],'INSTITUCION':'MUNICIPAL'}) for g,p in municipal]+[(g,{'ID_NUEVA':p['ID_POLICIA'],'INSTITUCION':'POLICIA_NACIONAL'}) for g,p in proposal]
    layers={'PROPUESTA_POLICIA_30_REVISION':proposal,'PROPUESTA_POLICIA_30_ANTERIOR':original,
        'COMPARACION_ALTERNATIVAS':alternatives,'PROPUESTA_50_CONGELADA':municipal,'CAMARAS_EXISTENTES_103':cameras,
        'SISTEMA_80_REVISION':system80,'PLATAFORMAS':platforms,'CORREDORES_REFERENCIA':lines,
        'UPC_INFRAESTRUCTURA':records(read_layer(PACKAGE,'UPC_INFRAESTRUCTURA')),
        'CONTEXTOS_REVISION':contexts,'HOTSPOT_COINCIDENCIA_DV':dv_rows,'COINCIDENCIA_DV_RESIDUAL':dv_remaining,
        'HOTSPOTS_RESIDUALES':remainder,**{'COBERTURA_'+s:[(g,{'ESCENARIO':s,'RADIO_M':200})] for s,g in masks.items()},
        'INCIDENTES_ESCENARIOS':[(g,{**p,**{'CUB_'+s:mask.covers(g) for s,mask in masks.items()}}) for g,p in events]}
    for (scope,cat),rows in updated.items():layers['GI_'+scope+'_'+cat]=rows
    info=[export(name,rows,not name.startswith('GI_')) for name,rows in layers.items()]
    for cat in CLASSES:write_json('HOTSPOT_'+cat+'.geojson',geojson([(g,p) for (scope,c),rows in updated.items() if c==cat for g,p in rows if p['GI_CLASS'].startswith('HOTSPOT')]))
    for name,rows in [('DECISIONES',decisions),('ALTERNATIVAS_4_PUNTOS',comparisons),('TODAS_ALTERNATIVAS_EVALUADAS',all_evaluated),
        ('PROPUESTA_POLICIA_30_REVISION',[p for _,p in proposal]),('COMPARACION_INCIDENTES',inc),('COMPARACION_HOTSPOTS',hot_stats),('EFECTO_CORREDORES',corridors)]:write_csv(name+'.csv',rows)
    metadata={'generatedAt':datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'),'crsMetric':'EPSG:32717',
        'radiusM':200,'reviewedSlots':list(SLOTS),'fixedPolice':26,'municipalFrozen':50,'inventory':103,'located':99,'police':30,
        'newTotal':80,'sourceHashes':protected,'giRecalculated':False,'viewerModified':False,'commit':False,'push':False,
        'sequence':list(SLOTS),'preferenceRule':'Coincidencia D/V residual significativa; mayor numero D+V nuevo, sin reducir D o V por separado y con menor solape que el actual. Sin umbrales de distancia, solape o minimo fijo de eventos. Las areas y niveles se comparan explicitamente, sin veto automatico por perdida de superficie de una categoria.',
        'rankAmongPreferred':'Mas eventos D/V nuevos; mayor nivel residual de coincidencia; area nueva coincidente; areaD+V; menor solape; Conv; grado nodo. No corredores ni UPC.',
        'comparisonContext':'Para cada slot quitar solo ese punto, conservar otras29 incluyendo reemplazos previos. Todas sus alternativas usan exactamente esa misma union. Excluir todos los30 candidatos originales de alternativas.',
        'historicalWarning':'Los1/1/1/4 originales eran aportes iterativos historicos. ANTES/DESPUES de revision son marginales contra otras29; no mezclar los contextos.',
        'significanceWarning':'Se conserva Gi* original. Una alternativa puede mantener significancia con nivel nominal diferente; los niveles y coberturas99/95/90 se reportan explicitamente, sin fingir igualdad estadistica.',
        'populationWarning':'Poblacion asociada estimacion CPV2022 areal previa; informativa, no entra en seleccion.',
        'geometryWarning':'Ubicaciones propuestas en nodos de cartografia vial, pendientes de inspeccion, poste, energia, permisos, cota ycampo visual.',
        'newProposalBenefitContext':'Aporte exclusivo por punto frente aotras29 en revision final; no historico ni sumable para obtener ganancia total.',
        'protectedFilesUnchanged':all(sha(Path(p))==digest for p,digest in protected.items())}
    assert metadata['protectedFilesUnchanged']
    data={'metadata':metadata,'decisions':decisions,'alternatives':comparisons,'proposals':[p for _,p in proposal],
        'incidents':inc,'hotspots':hot_stats,'corridors':corridors,'layers':info}
    write_json('RESULTADOS.json',data)
    report(data)
    print(json.dumps({'decisions':[{k:d[k] for k in ('ID','DECISION','EVENTOS_DV_ANTES','EVENTOS_DV_DESPUES','SOLAPE_ANTES','SOLAPE_DESPUES')} for d in decisions],
        'cantonal':[r for r in inc if r['AMBITO']=='CANTONAL' and r['ESCENARIO'] in ('C0','C')]},ensure_ascii=False,indent=2),flush=True)


def report(data):
    def table(fields,rows):
        def value(v):
            if v is None:return 'No disponible'
            if isinstance(v,float):return f'{v:.3f}'
            return str(v).replace('|',' / ').replace('\n',' ')
        return '\n'.join(['| '+' | '.join(fields)+' |','| '+' | '.join('---' for _ in fields)+' |']+
            ['| '+' | '.join(value(r.get(k)) for k in fields)+' |' for r in rows])
    m=data['metadata']
    lines=['# Revision final de eficiencia de Policia30','',
        '**Sin commit ni push. 50 municipales y otras26 policiales inmoviles. Gi* original intacto.**','',
        '## Comparacion justa',m['comparisonContext'],m['historicalWarning'],
        'Se revisan secuencialmente POL-20, POL-21, POL-22 y POL-30. La secuencia se conserva en metadatos y se exportan cuatro uniones de referencia en CONTEXTOS_REVISION. No es una optimizacion global de las30.',
        '## Criterio de sustitucion',m['preferenceRule'],m['rankAmongPreferred'],
        'Las recomendaciones priorizan eventos D/V adicionales con menor redundancia. NO se afirma dominancia en todas las dimensiones: puede disminuir el area nueva de Hot Spots o pasar de99/95 a90%. Las tablas conservan esas contrapartidas para aprobar o rechazar cada sustitucion; no se modifica la metodologia Gi*.',
        'La tolerancia de0,01m2 procede del calculo original y se usa exclusivamente para error numerico en area. No es un umbral operativo. Se conserva el mismo universo de nodos y el ambito urbano de las cuatro propuestas.',
        'Los99/95/90 son niveles originales de Gi*, no recalculados. NIVEL_DEL/NIVEL_VIOL son los maximos dentro del radio; NIVEL_DV_RESIDUAL corresponde a coincidencias aun sin cobertura. No son intercambiables.',
        m['significanceWarning'],'## Decisiones',table(list(data['decisions'][0]),data['decisions']),
        '## Actual + cinco alternativas por punto',
        table(['ID_POLICIA_REVISADA','TIPO_OPCION','ORDEN_ALTERNATIVA','ID_CANDIDATO','NIVEL_DEL','NIVEL_VIOL','NIVEL_DV_RESIDUAL','COINCIDENCIA_DV',
            'EVENTOS_D_NUEVOS','EVENTOS_V_NUEVOS','EVENTOS_DV_NUEVOS','AREA_HOTSPOT_D_NUEVA_M2','AREA_HOTSPOT_V_NUEVA_M2',
            'SOLAPE_PREVIO_PCT','DIST_EXISTENTE_M','DIST_MUNICIPAL_M','DIST_POLICIA_M','UPC_CERCANA','INTERSECCION_O_NODO','PREFERIBLE_AL_ACTUAL','JUSTIFICACION'],data['alternatives']),
        'TODAS_ALTERNATIVAS_EVALUADAS.csv conserva todas las opciones con coincidencia residual D/V evaluadas en cada paso, no solo las primeras cinco.',
        '## Eventos: actual, +50, +80 anterior, +80 revisado',table(list(data['incidents'][0]),data['incidents']),
        '## Hot Spots por categoria, ambito y nivel',table(list(data['hotspots'][0]),data['hotspots']),
        'Completa/parcial/sin cobertura son fracciones geometricas originales. Una nueva cobertura mayor por categoria puede redistribuir cobertura entre niveles. Consultar tablas99/95/90 antes de aprobar. No equivale a intervencion eficaz o reduccion futura de incidentes.',
        '## Efecto INCIDENTAL de corredores',table(list(data['corridors'][0]),data['corridors']),
        'No se utiliza Anillo Vial ni ningun corredor para elegir candidatos; no se mueven las50 municipales.',
        '## Propuesta revisada de30',table(['ID_POLICIA','ID_CANDIDATO','X','Y','DECISION_REVISION','BENEFICIO_MARGINAL','SOLAPE_RESTO_FINAL_PCT','JUSTIFICACION'],data['proposals']),
        m['newProposalBenefitContext'],m['populationWarning'],m['geometryWarning'],
        '## Capas y campos',table(['name','records','crs','fields'],[{**r,'fields':', '.join(r['fields'])} for r in data['layers']]),
        'GeoPackage en EPSG:32717, GeoJSON de mapa en EPSG:4326. Los paquetes anteriores se conservan completos y con SHA256; no se sobrescriben.',
        '**Detenido para revision. Ninguna propuesta implica autorizacion operativa definitiva.**']
    (OUT/'INFORME_REVISION.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
    (OUT/'README.md').write_text('# Policia30: revision de cuatro puntos\n\nPROPUESTA_POLICIA_30_REVISION.gpkg: propuesta final y capas de auditoria en EPSG:32717.\nDECISIONES.csv: cambios y motivos. ALTERNATIVAS_4_PUNTOS.csv: cuatroactuales +20alternativas.\nTODAS_ALTERNATIVAS_EVALUADAS.csv: universo comparado. CONTEXTOS_REVISION: cobertura de referencia de cada paso.\nINFORME_REVISION.md: metodologia, contextos, comparaciones, campos ylimitaciones.\n\nA=actuales; B=actuales+50; C0=+30 policiales anteriores; C=+30 policiales revisadas. Radios200m, union disuelta, eventos de peso1.\nGi* original intacto. Sin commit nipush. No optimizacion del Anillo.\n',encoding='utf-8')


if __name__=='__main__':main()
