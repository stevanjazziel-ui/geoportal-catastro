"""Check the accepted four MAATE road nodes against all 37 supplied real alternatives."""
import json
from collections import Counter
from shapely.ops import unary_union
from close_final_camera_study import (OUT,PREVIOUS,PACKAGE,read_layer,records,coverage,jsave,csvsave,
    Context,CLASSES,AREA_EPS,pct)


def main():
    cameras=records(read_layer(PACKAGE,'CAMARAS_EXISTENTES_103_FINAL'))
    municipal=records(read_layer(PACKAGE,'PROPUESTA_MUNICIPAL_50_FINAL'))
    events=records(read_layer(PACKAGE,'INCIDENTES_CLASIFICADOS'))
    hot=[r for cat in CLASSES for r in records(read_layer(PACKAGE,'HOTSPOT_'+cat))]
    dv=records(read_layer(PREVIOUS.parent.parent/'propuesta-policia-30-20261003/PROPUESTA_POLICIA_30.gpkg','HOTSPOT_COINCIDENCIA_DV'))
    axes={p['CORREDOR']:g for g,p in records(read_layer(PACKAGE,'CORREDORES'))}
    axis=axes['QUEBRADA_LAS_ABRAS']
    urban=unary_union([g for g,_ in records(read_layer(PACKAGE,'PLATAFORMAS_TERRITORIALES'))])
    blocks=records(read_layer(PACKAGE,'MANZANAS_COBERTURA'))
    infra=records(read_layer(PACKAGE,'UPC_INFRAESTRUCTURA'))
    context=Context(events,hot,dv,coverage(cameras),[g for g,_ in cameras],[g for g,_ in municipal],infra,blocks,urban,axes)
    critical=records(read_layer(PACKAGE,'CUNDUANA_PUNTOS_CRITICOS'))
    cleaning=unary_union([g for g,_ in records(read_layer(PACKAGE,'CUNDUANA_TRAMOS_LIMPIEZA'))])
    protection=unary_union([g for name in ('MAATE_INSUMO_05','MAATE_INSUMO_06','MAATE_INSUMO_10','MAATE_INSUMO_14') for g,_ in records(read_layer(PACKAGE,name))])
    marti=records(read_layer(PACKAGE,'MAATE_INSUMO_15'))
    pool=records(read_layer(PREVIOUS,'CANDIDATOS_ABRAS_MAATE'))
    def evaluate(point,id,reference):
        disk=point.buffer(200,quad_segs=64);new=disk.difference(reference)
        counts=Counter(p['CATEGORIA'] for g,p in events if p['AMBITO']!='EXTERNO_CANTON' and disk.covers(g) and not reference.covers(g))
        pop=context.population(disk)[0]
        environmental=sum(disk.covers(g) for g,_ in critical)
        related=sum(disk.covers(g) for g,_ in marti)
        significant=any(p['CATEGORIA'] in CLASSES[:2] and disk.intersection(g).area>AREA_EPS for g,p in hot)
        area=protection.intersection(disk).area
        dims=sum((axis.distance(point)<=1e-5,area>AREA_EPS,related>0,sum(counts.values())>0,pop is not None and pop>0,significant))
        return {'ID_CANDIDATO':id,'X':point.x,'Y':point.y,'DIMENSIONES_CON_EVIDENCIA':dims,
            'MAATE_EXCLUSIVO_M':axis.intersection(new).length,'N_PUNTOS_CUNDUANA':environmental,
            'LIMPIEZA_EXCLUSIVA_M':cleaning.intersection(new).length,'N_JOSE_MARTI':related,
            'AREA_PROTECCION_M2':area,'HOTSPOT_DV_COMPLEMENTARIO':significant,
            'D_NUEVOS':counts['DELINCUENCIA'],'V_NUEVOS':counts['VIOLENCIA'],'C_NUEVOS':counts['CONVIVENCIA'],
            'POBLACION_ASOCIADA':pop,'SOLAPE_PCT':pct(disk.intersection(reference).area,disk.area),
            'DIST_CUNDUANA_M':min(point.distance(g) for g,_ in critical),'DIST_LIMPIEZA_M':point.distance(cleaning)}
    def rank(r):return (r['N_PUNTOS_CUNDUANA'],r['LIMPIEZA_EXCLUSIVA_M'],r['DIMENSIONES_CON_EVIDENCIA'],r['N_JOSE_MARTI']>0,r['MAATE_EXCLUSIVO_M'],r['D_NUEVOS']+r['V_NUEVOS'],r['C_NUEVOS'],-r['SOLAPE_PCT'])
    comparisons=[];decisions=[]
    for point,p in municipal:
        if p['GRUPO']!='LAS_ABRAS':continue
        others=[r for r in municipal if r[1]['ID_PROPUESTA']!=p['ID_PROPUESTA']]
        reference=coverage(cameras+others)
        current=evaluate(point,p['ID_CANDIDATO'],reference)
        options=[]
        for g,q in pool:
            if any(g.distance(o)<1e-5 for o,_ in others):continue
            r=evaluate(g,q['ID_CANDIDATO'],reference)
            r['MEJORA_CLARA']=r['MAATE_EXCLUSIVO_M']>current['MAATE_EXCLUSIVO_M']+1e-6 and r['DIMENSIONES_CON_EVIDENCIA']>=current['DIMENSIONES_CON_EVIDENCIA']
            options.append(r)
        options.sort(key=lambda r:(r['MEJORA_CLARA'],rank(r)),reverse=True)
        winner=options[0] if options and options[0]['MEJORA_CLARA'] else current
        for i,r in enumerate([current]+options[:5]):comparisons.append({**r,'ID_PROPUESTA':p['ID_PROPUESTA'],'OPCION':'ACTUAL' if i==0 else 'ALTERNATIVA','ORDEN':i})
        decisions.append({'ID':p['ID_PROPUESTA'],'DECISION':'REVISAR_REEMPLAZO' if winner is not current else 'MANTENER',
            'MAATE_ACTUAL_M':current['MAATE_EXCLUSIVO_M'],'MAATE_ALTERNATIVA_M':winner['MAATE_EXCLUSIVO_M'],
            'DIMENSIONES_ACTUAL':current['DIMENSIONES_CON_EVIDENCIA'],'DIMENSIONES_ALTERNATIVA':winner['DIMENSIONES_CON_EVIDENCIA'],
            'CANDIDATO_ACTUAL':current['ID_CANDIDATO'],'CANDIDATO_ALTERNATIVA':winner['ID_CANDIDATO']})
    jsave('AUDITORIA_FINAL_LAS_ABRAS.json',{'decisions':decisions,'alternatives':comparisons,'candidates':len(pool),'method':'Regla aceptada anterior: mejora MAATE exclusiva sin perder dimensiones, con nodo exacto'})
    # Diagnostic tables are generated data, not changes to camera geometries.
    csvsave('LAS_ABRAS_ALTERNATIVAS_FINAL',comparisons)
    print(json.dumps(decisions),flush=True)


if __name__=='__main__':main()
