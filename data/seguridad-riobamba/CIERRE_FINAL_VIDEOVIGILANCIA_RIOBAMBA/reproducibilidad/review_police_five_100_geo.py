"""Local five-slot review on the approved 100-GEO trial; no full optimization or source edits."""
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import pyogrio
from shapely.ops import unary_union

from build_police_camera_proposal import (ROOT,Context,CLASSES,AREA_EPS,read_layer,records,sha,pct,
    geojson,scenario_evaluation,UNPROJECT,parts)
from review_police_camera_efficiency import Evaluator,preferences,revision_rank

BASE=ROOT/'data/seguridad-riobamba'
SOURCE=BASE/'propuesta-policia-30-20261003'
PACKAGE=SOURCE/'PROPUESTA_POLICIA_30.gpkg'
TRIAL=BASE/'escenario-100-geo-20261004'
OUT=BASE/'propuesta-policia-30-final-100geo-20261004'
OUTPUT_PACKAGE=OUT/'PROPUESTA_POLICIA_30_REVISION_100GEO.gpkg'
SLOTS=('POL-08','POL-20','POL-21','POL-22','POL-30')
DESCRIPTIVE_FIELDS=('HOTSPOT_DEL','HOTSPOT_VIOL','HOTSPOT_CONV','NIVEL_DEL','NIVEL_VIOL','NIVEL_CONV',
    'DELINCUENCIA_200M','VIOLENCIA_200M','CONVIVENCIA_200M','N_TOTAL','POBLACION_ASOCIADA',
    'MANZANAS_POB_VALIDAS','MANZANAS_POB_FALTANTES','POBLACION_METODO','UPC_CERCANA','NOMBRE_UPC',
    'DIST_UPC_M','INFRA_CERCANA','DIST_INFRA_M','INTERSECCION_O_NODO','GRADO_NODO',
    'CORREDOR_COINCIDENTE','CORREDOR_METODO')


def save_json(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')


def save_csv(name,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as stream:
        w=csv.DictWriter(stream,fields);w.writeheader();w.writerows(rows)


def export(name,rows,visual=False):
    f=gpd.GeoDataFrame([p for _,p in rows],geometry=[g for g,_ in rows],crs=32717)
    pyogrio.write_dataframe(f,OUTPUT_PACKAGE,layer=name)
    if visual:save_json(name+'.geojson',geojson(rows))
    return {'name':name,'records':len(rows),'crs':'EPSG:32717','fields':list(f.columns[:-1])}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    trial=json.loads((TRIAL/'RESULTADOS.json').read_text(encoding='utf-8'))
    protected=dict(trial['metadata']['sourceHashes'])
    for folder in (SOURCE,TRIAL):
        for p in folder.rglob('*'):
            if p.is_file() and p.suffix not in ('.lock','.lck','.log'):protected[str(p)]=sha(p)
    assert all(sha(Path(p))==value for p,value in protected.items())
    original=records(read_layer(PACKAGE,'PROPUESTA_POLICIA_30'))
    originals={p['ID_POLICIA']:(g,p) for g,p in original}
    located=records(read_layer(TRIAL/'ESCENARIO_100_GEO.gpkg','ESCENARIO_100_GEO'))
    inventory=records(read_layer(PACKAGE,'CAMARAS_EXISTENTES_103'))
    municipal=records(read_layer(PACKAGE,'PROPUESTA_50_CONGELADA'))
    events=records(read_layer(PACKAGE,'INCIDENTES_ESCENARIOS'))
    platforms=records(read_layer(PACKAGE,'PLATAFORMAS'))
    stats={(scope,cat):records(read_layer(PACKAGE,'GI_'+scope+'_'+cat))
        for scope in ('URBANO','RURAL') for cat in CLASSES}
    hot=[(g,p) for rows in stats.values() for g,p in rows if p['GI_CLASS'].startswith('HOTSPOT')]
    dv=records(read_layer(PACKAGE,'HOTSPOT_COINCIDENCIA_DV'))
    current=read_layer(TRIAL/'ESCENARIO_100_GEO.gpkg','COBERTURA_A100').geometry.iloc[0]
    baseline=read_layer(TRIAL/'ESCENARIO_100_GEO.gpkg','COBERTURA_B100').geometry.iloc[0]
    previous=read_layer(TRIAL/'ESCENARIO_100_GEO.gpkg','COBERTURA_C100').geometry.iloc[0]
    lines=records(read_layer(PACKAGE,'CORREDORES_REFERENCIA'))
    axes={key:unary_union([g for g,p in lines if p['CORREDOR']==key]) for key in dict.fromkeys(p['CORREDOR'] for _,p in lines)}
    context=Context(events,hot,dv,baseline,[g for g,_ in located],[g for g,_ in municipal],[],[],
        unary_union([g for g,_ in platforms]),axes)
    assert len(located)==100 and len(inventory)==103 and len(municipal)==50
    raw=records(read_layer(PACKAGE,'CANDIDATOS_POLICIA'))
    candidates={p['ID_CANDIDATO']:context.candidate({'point':g,'id':p['ID_CANDIDATO'],
        'degree':p['GRADO_NODO'],'props':p}) for g,p in raw}
    selected_original={p['ID_CANDIDATO'] for _,p in original}
    active={id:candidates[p['ID_CANDIDATO']] for id,(_,p) in originals.items()}
    fixed25=unary_union([baseline]+[c['disk'] for id,c in active.items() if id not in SLOTS])
    evaluator=Evaluator(context)
    def evaluate(c,others):
        row=evaluator.evaluate(c,[o['point'] for o in others.values()])
        row.update({key:c['props'].get(key) for key in ('POBLACION_ASOCIADA','POBLACION_METODO',
            'MANZANAS_POB_VALIDAS','MANZANAS_POB_FALTANTES','CORREDOR_COINCIDENTE','CORREDOR_METODO')})
        return row
    comparisons,decisions,evaluated,contexts=[],[],[],[]
    for step,slot in enumerate(SLOTS,1):
        others={id:c for id,c in active.items() if id!=slot}
        reference=unary_union([baseline]+[c['disk'] for c in others.values()])
        assert fixed25.difference(reference).area<1e-6
        evaluator.prepare(reference)
        before=evaluate(active[slot],others)
        used={c['id'] for c in others.values()}
        eligible=[]
        for c in candidates.values():
            if c['id'] in selected_original or c['id'] in used or c['scope']!=active[slot]['scope']:continue
            if c['distanceExisting']<=1e-5 or c['distanceMunicipal']<=1e-5:continue
            row=evaluate(c,others)
            if row['COINCIDENCIA_DV_RESIDUAL_M2']<=AREA_EPS:continue
            row['PREFERIBLE_AL_ACTUAL']=preferences(row,before)
            row['ID_POLICIA_REVISADA']=slot;row['ITERACION_REVISION']=step
            row['JUSTIFICACION']=(f"Nodo vial original {row['ID_CANDIDATO']} de grado{row['GRADO_NODO']}; "
                f"coincidencia geometrica D/V residual con nivel minimo nominal{row['NIVEL_DV_RESIDUAL']}%. "
                f"Aporte {row['EVENTOS_D_NUEVOS']} D+{row['EVENTOS_V_NUEVOS']} V; "
                f"solape {row['SOLAPE_PREVIO_PCT']:.2f}% contra100GEO+50+otras29. "
                "La ubicacion es un nodo cartografico, no un poste validado; requiere inspeccion de campo. "
                "Poblacion, UPC y corredores son descriptivos y no determinan la seleccion.")
            eligible.append(row)
        eligible.sort(key=lambda row:(row['PREFERIBLE_AL_ACTUAL'],revision_rank(row)),reverse=True)
        assert len(eligible)>=5,slot
        before.update({'ID_POLICIA_REVISADA':slot,'ITERACION_REVISION':step,'TIPO_OPCION':'ACTUAL',
            'ORDEN_ALTERNATIVA':0,'PREFERIBLE_AL_ACTUAL':False,
            'JUSTIFICACION':'Camara original comparada con sus alternativas contra exactamente100GEO+50+las mismas otras29.'})
        top=[{**row,'TIPO_OPCION':'ALTERNATIVA','ORDEN_ALTERNATIVA':i} for i,row in enumerate(eligible[:5],1)]
        comparisons.extend([before]+top);evaluated.extend(eligible)
        winner=eligible[0] if eligible[0]['PREFERIBLE_AL_ACTUAL'] else before
        replace=winner is not before
        if replace:active[slot]=candidates[winner['ID_CANDIDATO']]
        reason=(f"Reemplazo propuesto: aporte exclusivo D/V {before['EVENTOS_DV_NUEVOS']} a{winner['EVENTOS_DV_NUEVOS']}; "
            f"D {before['EVENTOS_D_NUEVOS']} a{winner['EVENTOS_D_NUEVOS']}, V {before['EVENTOS_V_NUEVOS']} a{winner['EVENTOS_V_NUEVOS']}; "
            f"solape {before['SOLAPE_PREVIO_PCT']:.2f}% a{winner['SOLAPE_PREVIO_PCT']:.2f}%. "
            f"Mantiene remanente significativo D/V en nodo vial de grado{winner['GRADO_NODO']}. "
            f"Nivel minimo residual {before['NIVEL_DV_RESIDUAL']}% a{winner['NIVEL_DV_RESIDUAL']}%; "
            f"area D {before['AREA_HOTSPOT_D_NUEVA_M2']:.1f} a{winner['AREA_HOTSPOT_D_NUEVA_M2']:.1f}m2, "
            f"V {before['AREA_HOTSPOT_V_NUEVA_M2']:.1f} a{winner['AREA_HOTSPOT_V_NUEVA_M2']:.1f}m2. "
            "No implica mejora en todas las areas o niveles ni validacion operativa de campo." if replace else
            "Mantener: entre los candidatos de la misma escala con coincidencia D/V residual significativa, ninguno mejora D+V "
            "sin reducir D o V por separado y reduciendo solape. Proximidad o redundancia solas no obligan a reemplazar.")
        row={'ID':slot,'DECISION':'REEMPLAZAR' if replace else 'MANTENER',
            'CANDIDATO_ACTUAL':before['ID_CANDIDATO'],'CANDIDATO_PROPUESTO':winner['ID_CANDIDATO'],
            'HOTSPOT_D':winner['NIVEL_DEL'],'HOTSPOT_V':winner['NIVEL_VIOL'],
            'DV_NUEVOS_ANTES':before['EVENTOS_DV_NUEVOS'],'DV_NUEVOS_DESPUES':winner['EVENTOS_DV_NUEVOS'],
            'SOLAPE_ANTES':before['SOLAPE_PREVIO_PCT'],'SOLAPE_DESPUES':winner['SOLAPE_PREVIO_PCT'],
            'JUSTIFICACION':reason,'D_ANTES':before['EVENTOS_D_NUEVOS'],'D_DESPUES':winner['EVENTOS_D_NUEVOS'],
            'V_ANTES':before['EVENTOS_V_NUEVOS'],'V_DESPUES':winner['EVENTOS_V_NUEVOS'],
            'NIVEL_DV_RESIDUAL_ANTES':before['NIVEL_DV_RESIDUAL'],'NIVEL_DV_RESIDUAL_DESPUES':winner['NIVEL_DV_RESIDUAL'],
            'AREA_D_ANTES_M2':before['AREA_HOTSPOT_D_NUEVA_M2'],'AREA_D_DESPUES_M2':winner['AREA_HOTSPOT_D_NUEVA_M2'],
            'AREA_V_ANTES_M2':before['AREA_HOTSPOT_V_NUEVA_M2'],'AREA_V_DESPUES_M2':winner['AREA_HOTSPOT_V_NUEVA_M2'],
            'DV_HISTORICO_99GEO':originals[slot][1]['BENEFICIO_MARGINAL'],
            'SOLAPE_HISTORICO_99GEO':originals[slot][1]['SOLAPE_UNION_PREVIA_PCT'],
            'ITERACION_REVISION':step,'CANDIDATOS_COMPARADOS':len(eligible),
            'ALTERNATIVAS_PREFERIBLES':sum(r['PREFERIBLE_AL_ACTUAL'] for r in eligible),
            'CONTEXTO':'100GEO+50+otras29; conservar reemplazos previos de esta revision'}
        decisions.append(row)
        contexts.append((reference,{'ID_POLICIA_REVISADA':slot,'ITERACION_REVISION':step,'RADIO_M':200}))
        print(json.dumps(row,ensure_ascii=False),flush=True)
    for id,(g,_) in originals.items():
        if id not in SLOTS:assert active[id]['point'].equals(g)
    assert len(active)==30 and len({c['point'].wkb for c in active.values()})==30
    final=unary_union([baseline]+[c['disk'] for c in active.values()])
    masks={'A':current,'B':baseline,'C0':previous,'C':final}
    inc,hot_stats,corridors,updated,dv_rows,dv_remaining=scenario_evaluation(context,stats,dv,masks)
    proposals=[]
    for id,c in active.items():
        others={key:v for key,v in active.items() if key!=id}
        reference=unary_union([baseline]+[v['disk'] for v in others.values()])
        evaluator.prepare(reference);m=evaluate(c,others)
        lon,lat=UNPROJECT(c['point'].x,c['point'].y)
        decision=next((r for r in decisions if r['ID']==id),None)
        props={**{key:c['props'].get(key) for key in DESCRIPTIVE_FIELDS},
            'ID_POLICIA':id,'ID_CANDIDATO':c['id'],'X':c['point'].x,'Y':c['point'].y,'LONGITUD':lon,'LATITUD':lat,
            'AMBITO_HOTSPOT':c['scope'],'COINCIDENCIA_DV':bool(c['dv']),
            'DECISION_REVISION':decision['DECISION'] if decision else 'FIJA_NO_REVISADA',
            'DIST_EXISTENTE':c['distanceExisting'],'DIST_MUNICIPAL':c['distanceMunicipal'],'DIST_POLICIA':m['DIST_POLICIA_M'],
            'COBERTURA_PREVIA':c['overlapB'],'SOLAPE_RESTO_FINAL_PCT':m['SOLAPE_PREVIO_PCT'],
            'BENEFICIO_MARGINAL':m['EVENTOS_DV_NUEVOS'],'EVENTOS_D_EXCLUSIVOS_FINAL':m['EVENTOS_D_NUEVOS'],
            'EVENTOS_V_EXCLUSIVOS_FINAL':m['EVENTOS_V_NUEVOS'],'EVENTOS_C_EXCLUSIVOS_FINAL':m['EVENTOS_C_NUEVOS'],
            'AREA_D_EXCLUSIVA_FINAL_M2':m['AREA_HOTSPOT_D_NUEVA_M2'],'AREA_V_EXCLUSIVA_FINAL_M2':m['AREA_HOTSPOT_V_NUEVA_M2'],
            'BENEFICIO_CONTEXTO':'Exclusivo frente a100GEO+50+otras29 finales; no sumable',
            'JUSTIFICACION':decision['JUSTIFICACION'] if decision else 'Punto congelado; no revisado ni desplazado.',
            'ESTADO':'PROPUESTA_PARA_VALIDACION_POLICIA'}
        proposals.append((c['point'],props))
    alternative_rows=[(candidates[r['ID_CANDIDATO']]['point'],r) for r in comparisons]
    residual=[]
    for rows in updated.values():
        for g,p in rows:
            if p['GI_CLASS'].startswith('HOTSPOT'):
                residual.extend((part,p) for part in parts(g.difference(final),2) if part.area>AREA_EPS)
    layers={'PROPUESTA_POLICIA_30_REVISION':proposals,'POLICIA_30_ORIGINAL':original,
        'COMPARACION_CINCO_PUNTOS':alternative_rows,'PROPUESTA_50_CONGELADA':municipal,
        'ESCENARIO_100_GEO':located,'INVENTARIO_ORIGINAL_103':inventory,'PLATAFORMAS':platforms,
        'CONTEXTOS_COMPARACION':contexts,'BASE_100_50_25_FIJAS':[(fixed25,{'N_POLICIA_FIJA':25,'RADIO_M':200})],
        'RADIOS_PROPUESTA_FINAL':[(c['disk'],{'ID_POLICIA':id,'RADIO_M':200}) for id,c in active.items()],
        'RADIOS_ALTERNATIVAS':[(candidates[r['ID_CANDIDATO']]['disk'],r) for r in comparisons],
        'HOTSPOT_COINCIDENCIA_DV':dv_rows,'COINCIDENCIA_DV_RESIDUAL':dv_remaining,'HOTSPOTS_RESIDUALES':residual,
        'CORREDORES_REFERENCIA':lines,'UPC_INFRAESTRUCTURA':records(read_layer(PACKAGE,'UPC_INFRAESTRUCTURA')),
        **{'COBERTURA_'+s:[(g,{'ESCENARIO':s,'RADIO_M':200})] for s,g in masks.items()},
        'INCIDENTES_ESCENARIOS':[(g,{**{k:v for k,v in p.items() if not k.startswith('CUB')},
            **{'CUB_'+s:mask.covers(g) for s,mask in masks.items()}}) for g,p in events]}
    for (scope,cat),rows in updated.items():layers['GI_'+scope+'_'+cat]=rows
    info=[export(name,rows,name in ('PROPUESTA_POLICIA_30_REVISION','POLICIA_30_ORIGINAL','COMPARACION_CINCO_PUNTOS',
        'RADIOS_ALTERNATIVAS','RADIOS_PROPUESTA_FINAL','PLATAFORMAS','CORREDORES_REFERENCIA')) for name,rows in layers.items()]
    for cat in CLASSES:save_json('HOTSPOT_'+cat+'.geojson',geojson([(g,p) for (scope,c),rows in updated.items() if c==cat for g,p in rows if p['GI_CLASS'].startswith('HOTSPOT')]))
    for name,rows in (('DECISIONES_CINCO',decisions),('ACTUALES_Y_25_ALTERNATIVAS',comparisons),
        ('TODOS_CANDIDATOS_COMPARADOS',evaluated),('PROPUESTA_POLICIA_30_REVISION',[p for _,p in proposals]),
        ('COMPARACION_INCIDENTES',inc),('COMPARACION_HOTSPOTS',hot_stats),('EFECTO_SECUNDARIO_CORREDORES',corridors)):
        save_csv(name+'.csv',rows)
    assert all(sha(Path(p))==value for p,value in protected.items())
    metadata={'generatedAt':datetime.now(ZoneInfo('America/Guayaquil')).isoformat(timespec='seconds'),
        'crsMetric':'EPSG:32717','radiusM':200,'bufferQuadSegments':64,'inventory':103,'located':100,'pending':3,
        'municipalFrozen':50,'police':30,'fixedPolice':25,'reviewedSlots':list(SLOTS),'sequence':list(SLOTS),
        'sourceHashes':protected,'protectedFilesUnchanged':True,'giRecalculated':False,'policeFullyOptimized':False,
        'inventoryModified':False,'viewerModified':False,'commit':False,'push':False,
        'comparisonContext':'Revision local secuencial: quitar solo el punto revisado;100GEO+50+otras29, manteniendo25fijas y reemplazos previos. Actual y5alternativas comparados contra la MISMA union.',
        'preferenceRule':'Coincidencia geometrica D/V residual significativa; aumentar D+V sin disminuir D o V por separado y reducir solape. Sin umbrales fijos de separacion, solape o minimo de eventos.',
        'rank':'Preferibles primero; eventosD+V, nivelD/Vresidual, areaD/Vcoincidente, areaD+V, menor solape, Convivencia, grado nodo. No poblacion,UPC,corredores.',
        'candidateUniverse':'Candidatos viales originales, sin generar una nueva optimizacion de30. Excluir30originalmente seleccionados, candidatos ya usados y coincidencia exacta con100existentes/50municipales. Misma escala estadistica del punto revisado.',
        'populationMethod':'Estimacion arealCPV2022 asociada al radio200m del candidato, calculada previamente e independiente de cobertura existente; no recalculada ni usada como criterio.',
        'levelWarning':'Niveles nominalesGi*originales99/95/90. CoincidenciaD/V es superposicion geometrica, no una nueva significancia conjunta. Una sustitucion puede reducir area o nivel de una categoria: se reporta explicitamente.',
        'fieldWarning':'Nodo vial cartografico no certifica poste, energia, permiso, campo visual o visibilidad. Propuesta pendiente de validacion operativa.',
        'contextWarning':'Los1/1/1/4 reportados originalmente eran aportes iterativos99GEO. Antes/despues actuales son exclusivos frente aotras29; POL-22 puede tener0 en este contexto. No sumar beneficios individuales.',
        'scenarios':{'A':'100 GEO','B':'100 GEO+50 municipales','C0':'B+30 policiales originales fijas','C':'B+30 policiales con revision de5puntos'}}
    data={'metadata':metadata,'decisions':decisions,'alternatives':comparisons,'proposals':[p for _,p in proposals],
        'incidents':inc,'hotspots':hot_stats,'corridors':corridors,'layers':info}
    save_json('RESULTADOS.json',data);report(data)
    print(json.dumps({'decisions':decisions,'cantonalIncidents':[r for r in inc if r['AMBITO']=='CANTONAL']},ensure_ascii=False,indent=2),flush=True)


def report(data):
    def table(rows,fields):
        def fmt(v):
            if v is None:return 'No disponible'
            if isinstance(v,float):return f'{v:.3f}'
            return str(v).replace('|',' / ')
        return '\n'.join(['| '+' | '.join(fields)+' |','| '+' | '.join('---' for _ in fields)+' |']+
            ['| '+' | '.join(fmt(r.get(k)) for k in fields)+' |' for r in rows])
    m=data['metadata']
    changes=[]
    for cat in CLASSES:
        before=next(r for r in data['incidents'] if r['ESCENARIO']=='C0' and r['AMBITO']=='CANTONAL' and r['CATEGORIA']==cat)
        after=next(r for r in data['incidents'] if r['ESCENARIO']=='C' and r['AMBITO']=='CANTONAL' and r['CATEGORIA']==cat)
        changes.append({'CATEGORIA':cat,'EVENTOS_ANTES':before['CUBIERTOS'],'EVENTOS_DESPUES':after['CUBIERTOS'],
            'CAMBIO_EVENTOS':after['CUBIERTOS']-before['CUBIERTOS'],
            'PCT_ANTES':before['PCT_CUBIERTO'],'PCT_DESPUES':after['PCT_CUBIERTO']})
    urban_changes=[]
    for cat in CLASSES:
        before=[r for r in data['hotspots'] if r['ESCENARIO']=='C0' and r['AMBITO']=='URBANO' and r['CATEGORIA']==cat]
        after=[r for r in data['hotspots'] if r['ESCENARIO']=='C' and r['AMBITO']=='URBANO' and r['CATEGORIA']==cat]
        urban_changes.append({'CATEGORIA':cat,'COMPLETAS_ANTES':sum(r['CUBIERTO'] for r in before),
            'COMPLETAS_DESPUES':sum(r['CUBIERTO'] for r in after),
            'SIN_COBERTURA_ANTES':sum(r['SIN_COBERTURA'] for r in before),
            'SIN_COBERTURA_DESPUES':sum(r['SIN_COBERTURA'] for r in after),
            'CAMBIO_AREA_CUBIERTA_M2':sum(r['AREA_CUBIERTA_M2'] for r in after)-sum(r['AREA_CUBIERTA_M2'] for r in before)})
    lines=['# Revision final local de cinco camaras policiales con100GEO','',
        '**Solo propuesta para revision. Sin commit ni push.25policiales y50municipales congeladas. Inventario yGi* intactos.**',
        '## Contextos comparables',m['comparisonContext'],m['contextWarning'],
        'La cobertura BASE_100_50_25_FIJAS identifica el escenario residual inicial de las25congeladas. La comparacion individual conserva adicionalmente las otras4revisables para no sobrevalorar alternativas con cobertura ya atendida. Se procede en orden POL-08,20,21,22,30; no se reoptimiza el universo completo.',
        '## Criterio y alternativas',m['preferenceRule'],m['rank'],m['candidateUniverse'],m['levelWarning'],
        'El umbral0,01m2 procede de la tolerancia numerica original; no es un minimo operativo de cobertura.1e-5m se utiliza solo para coincidencias numericas exactas, no separacion minima entre camaras.',
        '## Decisiones',table(data['decisions'],['ID','DECISION','CANDIDATO_ACTUAL','CANDIDATO_PROPUESTO','HOTSPOT_D','HOTSPOT_V',
            'DV_NUEVOS_ANTES','DV_NUEVOS_DESPUES','SOLAPE_ANTES','SOLAPE_DESPUES','JUSTIFICACION']),
        '## Balance de la revision frente a las 30 originales',
        table(changes,list(changes[0])),table(urban_changes,list(urban_changes[0])),
        '**Contrapartida importante:** aumentan los eventos cubiertos, pero disminuye la cobertura completa de celdas urbanas D/V y parte de su area cubierta. Las alternativas de POL-08, POL-21 y POL-22 mantienen evidencia significativa, pero su coincidencia residual baja de nivel nominal 99% a 90%. No existe una mejora simultanea de todos los objetivos. Los cuatro reemplazos son propuestas para revision, no sustituciones publicadas ni una decision operativa definitiva.',
        'Los conteos completos incluyen niveles 99/95/90 sin sumarlos entre categorias. Las celdas que pasan de cobertura completa a parcial no se describen como totalmente desatendidas. La cobertura rural y sus resultados estadisticos no cambian.',
        '## Detalles de niveles, areas y contexto',table(data['decisions'],list(data['decisions'][0])),
        '## Cinco actuales y25alternativas',table(data['alternatives'],list(data['alternatives'][0])),
        'TODOS_CANDIDATOS_COMPARADOS.csv conserva todos los candidatos residuales D/V evaluados en cada paso. La ordenacion es local y secuencial; no implica optimo global.',
        '## Escenarios100GEO / +50 / +30 original / +30 revisadas',
        table([r for r in data['incidents'] if r['AMBITO']=='CANTONAL'],list(data['incidents'][0])),
        'COMPARACION_INCIDENTES.csv conserva BASE_COMPLETA, URBANO, RESTO_CANTON y EXTERNO_CANTON. Los externos no entran en seleccion. Cada registro real tiene peso1 y conserva coordenadas.',
        '## Hot Spots cubiertos/no cubiertos',table(data['hotspots'],list(data['hotspots'][0])),
        'CUBIERTO=fraccion>=1-1e-8; PARCIAL=>1e-8 y<1-1e-8; SIN<=1e-8. No se equipara una interseccion parcial con celda completamente atendida. Urbano y rural mantienen sus respectivas mallas, parametros, valores estadisticos y geometrias originales.',
        '## Corredores: beneficio secundario',table(data['corridors'],list(data['corridors'][0])),
        'AnilloVial, Ciclovias, Macaji-Bellavista yLasAbras no determinan seleccion, desempate ni cuotas. Se informa el efecto posterior, sin recolocar las50municipales.',
        '## Propuesta completa30',table(data['proposals'],['ID_POLICIA','ID_CANDIDATO','X','Y','DECISION_REVISION',
            'BENEFICIO_MARGINAL','SOLAPE_RESTO_FINAL_PCT','POBLACION_ASOCIADA','UPC_CERCANA','DIST_UPC_M','CORREDOR_COINCIDENTE']),
        'Estos beneficios finales contraotras29 pueden variar respecto a la comparacion en el paso de decision. No son aditivos. Los25puntos congelados no cambian, aunque se actualiza su beneficio ante las nuevas alternativas.',
        '## Limitaciones',m['populationMethod'],m['fieldWarning'],
        '103inventariadas:100localizadas/candidatas validadas,3pendientes; no se fuerza completar103. RIO-085 provisional, las99anteriores conservan precision original aproximada.',
        '## Archivos y CRS',table(data['layers'],['name','records','crs']),
        'GeoPackageEPSG:32717; GeoJSONvisualEPSG:4326. Incluye seis capasGi*estadisticamente intactas, coberturas ycontextos de comparacion, inventario original separado, escenario100,30policiales,50municipales y30opciones comparadas.',
        'RESULTADOS.json: parametros ySHA256. ACTUALES_Y_25_ALTERNATIVAS.csv: indicadores completos. DECISIONES_CINCO.csv: decisiones. INFORME_REVISION_CINCO.md: metodologia yresultados.',
        '**Detenido para revision; no se sustituye ninguna propuesta publicada ni se publica.**']
    (OUT/'INFORME_REVISION_CINCO.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':main()
