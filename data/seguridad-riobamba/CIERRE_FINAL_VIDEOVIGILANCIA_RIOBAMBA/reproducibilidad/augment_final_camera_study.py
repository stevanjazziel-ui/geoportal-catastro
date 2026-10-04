"""Attach independent tradeoff/MAATE checks and a portable, unchanged road context."""
import json
import geopandas as gpd
import pyogrio
from close_final_camera_study import (OUT,PACKAGE,GROUPS,jsave,read_layer,records,coverage,Context,
    CLASSES,AREA_EPS,pct,geojson)
from review_police_camera_efficiency import Evaluator
from shapely.ops import unary_union
from collections import Counter


def main():
    data=json.loads((OUT/'RESULTADOS.json').read_text(encoding='utf-8'))
    trade=json.loads((OUT/'DIAGNOSTICO_COMPROMISO_CICLOVIAS.json').read_text(encoding='utf-8'))
    abras=json.loads((OUT/'AUDITORIA_FINAL_LAS_ABRAS.json').read_text(encoding='utf-8'))
    data['tradeoffDiagnosis']=trade;data['abrasAlternativesAudit']=abras
    if any(r['DECISION']!='MANTENER' for r in abras['decisions']):
        raise RuntimeError('Abras audit found a clear improvement; reconcile before final packaging')
    # Rebuild point attributes after moving nodes; never carry old-location metrics forward.
    cameras=records(read_layer(PACKAGE,'CAMARAS_EXISTENTES_103_FINAL'))
    municipal=records(read_layer(PACKAGE,'PROPUESTA_MUNICIPAL_50_FINAL'))
    police=records(read_layer(PACKAGE,'PROPUESTA_POLICIA_30_FINAL'))
    events=records(read_layer(PACKAGE,'INCIDENTES_CLASIFICADOS'))
    hot=[r for category in CLASSES for r in records(read_layer(PACKAGE,'HOTSPOT_'+category))]
    dv=records(read_layer(OUT.parent/'propuesta-policia-30-20261003/PROPUESTA_POLICIA_30.gpkg','HOTSPOT_COINCIDENCIA_DV'))
    axes={p['CORREDOR']:g for g,p in records(read_layer(PACKAGE,'CORREDORES'))}
    urban=unary_union([g for g,_ in records(read_layer(PACKAGE,'PLATAFORMAS_TERRITORIALES'))])
    blocks=records(read_layer(PACKAGE,'MANZANAS_COBERTURA'))
    infra=records(read_layer(PACKAGE,'UPC_INFRAESTRUCTURA'))
    a=coverage(cameras);b=unary_union([a,coverage(municipal)])
    context=Context(events,hot,dv,a,[g for g,_ in cameras],[g for g,_ in municipal],infra,blocks,urban,axes)
    evaluator=Evaluator(context)
    identity=('ID_PROPUESTA','ID_ORIGINAL','FILA_ORIGINAL','GRUPO','SUBTIPO','X','Y','LONGITUD','LATITUD',
        'PARROQUIA','ID_CANDIDATO','ORIGEN_CANDIDATO','GRADO_NODO','CRITERIO_PRINCIPAL','CRITERIOS_SECUNDARIOS',
        'JUSTIFICACION','ESTADO','ESTADO_VALIDACION','METODO_FINAL')
    municipal_final=[]
    for g,p in municipal:
        candidate=context.candidate({'point':g,'id':p['ID_CANDIDATO'],'degree':p['GRADO_NODO'],
            'origins':{p['ORIGEN_CANDIDATO']},'props':dict(p)})
        candidate['props']=context.description(candidate)
        others=[r for r in municipal if r[1]['ID_PROPUESTA']!=p['ID_PROPUESTA']]
        reference=unary_union([a,coverage(others)])
        evaluator.prepare(reference)
        metric=evaluator.evaluate(candidate,[point for point,_ in others])
        gains={key:axis.intersection(candidate['disk'].difference(reference)).length for key,axis in axes.items()}
        final={**{key:p.get(key) for key in identity},**candidate['props'],
            'COBERTURA_PREVIA':pct(candidate['disk'].intersection(a).area,candidate['disk'].area),
            'SOLAPE_OTRAS49_PCT':metric['SOLAPE_PREVIO_PCT'],
            'D_EXCLUSIVOS':metric['EVENTOS_D_NUEVOS'],'V_EXCLUSIVOS':metric['EVENTOS_V_NUEVOS'],
            'C_EXCLUSIVOS':metric['EVENTOS_C_NUEVOS'],'N_CORREDORES':sum(axis.intersection(candidate['disk']).length>1e-6 for axis in axes.values()),
            'CORREDOR':candidate['props']['CORREDOR_COINCIDENTE'],
            'BENEFICIO_CONTEXTO':'Exclusivo respecto103+otras49;no sumar entre camaras',
            **{'LONGITUD_EXCLUSIVA_'+key+'_M':value for key,value in gains.items()}}
        if p['GRUPO']=='RED_ESTRUCTURAL':
            final['CRITERIO_PRINCIPAL']='Macaji>=98%;maximizarAnillo;despuesCiclovias;sin cuotas'
            final['JUSTIFICACION']='Nodo/cruce real;unionlineal200m;criterios jerarquicos. Perdida de Ciclovias documentada en informe; pendiente revision y campo.'
        municipal_final.append((g,final))
    context.baseline=b
    police_final=[]
    identity=('ID_POLICIA','ID_CANDIDATO','X','Y','LONGITUD','LATITUD','DECISION_FINAL','JUSTIFICACION','ESTADO')
    for g,p in police:
        candidate=context.candidate({'point':g,'id':p['ID_CANDIDATO'],'degree':p['GRADO_NODO'],
            'origins':set(str(p['INTERSECCION_O_NODO']).split('|')),'props':dict(p)})
        candidate['props']=context.description(candidate)
        others=[r for r in police if r[1]['ID_POLICIA']!=p['ID_POLICIA']]
        evaluator.prepare(unary_union([b,coverage(others)]))
        metric=evaluator.evaluate(candidate,[point for point,_ in others])
        final={**{key:p.get(key) for key in identity},**candidate['props'],**metric,
            'ID_POLICIA':p['ID_POLICIA'],'BENEFICIO_MARGINAL':metric['EVENTOS_DV_NUEVOS'],
            'SOLAPE_RESTO_FINAL_PCT':metric['SOLAPE_PREVIO_PCT'],
            'EVENTOS_D_EXCLUSIVOS_FINAL':metric['EVENTOS_D_NUEVOS'],'EVENTOS_V_EXCLUSIVOS_FINAL':metric['EVENTOS_V_NUEVOS'],
            'BENEFICIO_CONTEXTO':'Exclusivo respecto103+50final+otras29;no sumar entre camaras'}
        change=next((row for row in data['policeChanges'] if row['ID_FINAL']==p['ID_POLICIA']),None)
        if change:final['JUSTIFICACION']=change['MOTIVO']
        police_final.append((g,final))
    for name,rows in (('PROPUESTA_MUNICIPAL_50_FINAL',municipal_final),('PROPUESTA_POLICIA_30_FINAL',police_final)):
        frame=gpd.GeoDataFrame([p for _,p in rows],geometry=[g for g,_ in rows],crs=32717)
        pyogrio.write_dataframe(frame,PACKAGE,layer=name)
        jsave(name+'.geojson',geojson(rows))
        for item in data['catalog']:
            if item['name']==name:item['fields']=list(frame.columns[:-1])
    data['derivedPointAttributesRebuilt']=True
    path='D:/codex/riobamba_matrix_review_20260921/cartografia_base/RIOBAMBA_Cartografia Base.gdb'
    roads=read_layer(path,'Vialidad_urbana')
    pyogrio.write_dataframe(roads,PACKAGE,layer='RED_VIAL_CONTEXTO')
    new=[{'name':'RED_VIAL_CONTEXTO','group':GROUPS[13],'records':len(roads),'crs':'EPSG:32717','source':path+':Vialidad_urbana','fields':list(roads.columns[:-1])},
        {'name':'LAS_ABRAS_ALTERNATIVAS_FINAL','group':GROUPS[12],'records':len(abras['alternatives']),'crs':'No aplica; tabla','source':'37 nodos MAATE aceptados; revision en contexto153final','fields':list(pyogrio.read_info(PACKAGE,layer='LAS_ABRAS_ALTERNATIVAS_FINAL')['fields'])}]
    names={r['name'] for r in new};data['catalog']=[r for r in data['catalog'] if r['name'] not in names]+new
    data['warnings'].append('Ciclovias baja de86.68% a56.44% en153 al aplicar prioridad estricta Anillo. Diagnostico separado conserva Ciclovias pero no sustituye configuracion final sin aprobacion.')
    jsave('RESULTADOS.json',data)
    print(json.dumps({'roadFeatures':len(roads),'abrasDecisions':abras['decisions'],'tradeoff':trade['scenarios']}))


if __name__=='__main__':main()
