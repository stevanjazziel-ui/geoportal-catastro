"""Build the user-approved municipal axis revision, preserving the other 159 cameras."""
import json
import shutil
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

from final_municipal_axis_nodes import OUT as REVIEW
from review_police_verified_main_roads import ROOT, ROADS, candidates_from_shared_vertices
import recalculate_current_gaps as dependencies

sys.path.insert(0,str(ROOT/'sig-bridge'))
from bridge.engine import calculate,save_layer,verify_derived
from bridge.store import Store,read_json,write_json,digest,require,clean,now

RELEASE_ID='MUNICIPALES_NODOS_PRIORITARIOS_20261016'
OUT=ROOT/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES'/RELEASE_ID
AUTHORIZATION='Si, publicar esa solucion y sus coberturas reales. Macaji100; Anillo68,41; Ciclovias59,25; MUN-037 Junin x Puruha.'


def main():
    require(not OUT.exists(),'No se sobrescribe una entrega')
    store=Store();base=store.web
    target=gpd.read_file(REVIEW/'ESTUDIO_24_NODOS.gpkg',layer='EJES_PRIORITARIOS').to_crs(32717)
    plan=read_json(REVIEW/'RESULTADOS.json')
    require(len(target)==24 and target.ID_PROPUESTA.is_unique,'Se requieren24ID urbanos')
    require(len(plan['localExceptions'])==1 and plan['localExceptions'][0]['CRUCE']=='Junín x Puruhá','La excepcion aprobada cambio')
    hashes={str(p):digest(p) for p in [store.base,REVIEW/'RESULTADOS.json',REVIEW/'ESTUDIO_24_NODOS.gpkg']}
    hashes.update({str(p):digest(p) for p in ROADS.parent.glob(ROADS.stem+'.*') if p.is_file()})
    roads=gpd.read_file(ROADS).to_crs(32717)
    urban=gpd.read_file(store.base,layer='PLATAFORMAS_TERRITORIALES').geometry.union_all()
    nodes={(c['point'].x,c['point'].y):c for c in candidates_from_shared_vertices(roads,urban,require_principal=False)}
    manual={};changes=[]
    for key,spec in store.config['layers'].items():
        frame=gpd.read_file(store.base,layer=spec['source'])
        if 'OBSERVACION_MANUAL' not in frame:frame['OBSERVACION_MANUAL']=''
        if key=='municipal':
            for index,row in frame.loc[frame.GRUPO.eq('RED_ESTRUCTURAL')].iterrows():
                point=target.loc[target.ID_PROPUESTA.eq(row.ID_PROPUESTA)].geometry.iloc[0]
                changes.append({'layer':'municipal','id':row.ID_PROPUESTA,'geometryChanged':not row.geometry.equals(point),
                    'fields':[],'distanceM':row.geometry.distance(point),'note':'Nodos/ejes aprobados; Macaji100; Anillo sin minimo'})
                frame.at[index,'geometry']=point
        manual[key]=frame
    def validate(store,changes,municipal,police,urban):
        checks=[]
        for point,props in municipal:
            if props['GRUPO']!='RED_ESTRUCTURAL':continue
            key=props['ID_PROPUESTA'];node=nodes.get((point.x,point.y))
            require(node is not None,'No es un nodo vial original: '+key)
            local=key=='MUN-037' and not node['principal']
            require(bool(node['principal']) or local,'Excepcion local no autorizada: '+key)
            cruce=' x '.join(node['roads'])
            require(not local or cruce=='Junín x Puruhá','Cruce local distinto al aprobado')
            props.update({'ID_CANDIDATO':next(r['ID_CANDIDATO'] for r in plan['scenario']['movements'] if r['ID_PROPUESTA']==key),
                'INTERSECCION_O_NODO':cruce,'GRADO_NODO':node['degree'],'DISTANCIA_NODO_M':0,
                'TIPO_VIA_PRINCIPAL':'|'.join(node['highways']),'FUENTE_CRUCE':ROADS.name,
                'OSM_IDS':'|'.join(node['osmIds']),'EJE_PRINCIPAL':'|'.join(node['principal']),
                'JERARQUIA_OSM_PRINCIPAL':bool(node['principal']),'EXCEPCION_LOCAL_MACAJI':local,
                'BRIDGE_NODO_VALIDADO':True,'METODO_FINAL':'NODOS_EJES_MACAJI100_ANILLO_SIN_MINIMO',
                'CRITERIO_UBICACION':'Cruces principales y enlaces potenciales por mismo eje. Macaji100; sin minimo Anillo.',
                'OBSERVACION_MANUAL':'Junin x Puruha: excepcion local aprobada para mantener Macaji100.' if local else 'Cruce principal comprobado; alcance hacia las vias, no a traves de manzanas.',
                'COBERTURA_VISUAL_CERTIFICADA':False})
            checks.append({'id':key,'nodeDistanceM':0,'degree':node['degree'],'principalRoad':bool(node['principal']),
                'roads':node['roads'],'source':ROADS.name,'osmIds':node['osmIds'],'passed':True,'approvedLocalException':local})
        require(len(checks)==24,'Auditoria municipal incompleta')
        return checks,[]
    OUT.mkdir(parents=True)
    receipt={'revision':RELEASE_ID,'changes':changes,'baseHashes':hashes,'createdAt':now(),'authorization':AUTHORIZATION}
    print('Recalculando B/C y coberturas dependientes',flush=True)
    validation=calculate(store,OUT,OUT,manual,receipt,node_validator=validate)
    require(not validation['publishBlocks'],str(validation['publishBlocks']))
    package=OUT/'ESCENARIO_FINAL_183.gpkg'
    # Restore the fixed police proposal's approved provenance; refresh only coverage aliases.
    police=gpd.read_file(package,layer='PROPUESTA_POLICIA_30_FINAL')
    previous=gpd.read_file(store.base,layer='PROPUESTA_POLICIA_30_FINAL').set_index('ID_POLICIA')
    for i,row in police.iterrows():
        for field in ('DECISION','DECISION_FINAL','JUSTIFICACION','CRITERIO','OBSERVACION_MANUAL','SELECCION_PREVIA_HISTORICA'):
            if field in previous:police.at[i,field]=previous.loc[row.ID_POLICIA,field]
        for alias,field in [('SOLAPE_PCT','SOLAPE_PREVIO_PCT'),('DIST_EXISTENTE_M','DIST_EXISTENTE'),('DIST_MUNICIPAL_M','DIST_MUNICIPAL')]:
            if field in police:police.at[i,alias]=row[field]
    records=lambda f:[(r.geometry,clean({k:v for k,v in r._asdict().items() if k not in ('Index','geometry')})) for r in f.itertuples()]
    police_rows=records(police);save_layer(package,'PROPUESTA_POLICIA_30_FINAL',police_rows,OUT)
    existing=gpd.read_file(package,layer='CAMARAS_EXISTENTES_103_FINAL')
    municipal=gpd.read_file(package,layer='PROPUESTA_MUNICIPAL_50_FINAL')
    fixed_m=municipal.loc[~municipal.GRUPO.eq('RED_ESTRUCTURAL')]
    old_m=gpd.read_file(store.base,layer='PROPUESTA_MUNICIPAL_50_FINAL').set_index('ID_PROPUESTA')
    require(all(r.geometry.equals(old_m.loc[r.ID_PROPUESTA].geometry) for r in fixed_m.itertuples()),'26 municipales alteradas')
    require(all(r.geometry.equals(previous.loc[r.ID_POLICIA].geometry) for r in police.itertuples()),'Policia alterada')
    save_layer(package,'ESCENARIO_FINAL_183',[(g,{**p,'ID_EQUIPO':p['ID_CAMARA'],'GRUPO_ESCENARIO':'EXISTENTE'}) for g,p in records(existing)]
        +[(g,{**p,'ID_EQUIPO':p['ID_PROPUESTA'],'GRUPO_ESCENARIO':'MUNICIPAL_PROPUESTA'}) for g,p in records(municipal)]
        +[(g,{**p,'ID_EQUIPO':p['ID_POLICIA'],'GRUPO_ESCENARIO':'POLICIA_PROPUESTA'}) for g,p in police_rows])
    results=read_json(OUT/'RESULTADOS.json');results['policeMetrics']=[p for _,p in police_rows]
    pd.DataFrame(results['policeMetrics']).to_csv(OUT/'POLICIA_BENEFICIO_FINAL.csv',index=False,encoding='utf-8-sig')
    pyogrio.write_dataframe(pd.DataFrame(results['policeMetrics']),package,layer='POLICIA_BENEFICIO_FINAL')
    validation.update({'status':'PASS_APPROVED_LOCAL_EXCEPTION','authorization':AUTHORIZATION,'fixed159Unchanged':True,
        'principalUrbanNodes':23,'localException':'MUN-037 Junin x Puruha','ringMinimumPct':None,'macajiMinimumPct':100,
        'approvedException':{'authorization':AUTHORIZATION,'scope':'LOCAL_JUNCTION_MACAJI','camera':'MUN-037','ringFloorRemoved':True}})
    results.update({'status':'MUNICIPALES_NODOS_EJES_APROBADOS','sourcePackage':RELEASE_ID,'authorization':AUTHORIZATION,
        'bridge':validation,'counts':{'existing':103,'changeIncluded':30,'municipal':50,'police':30},
        'municipalAxisReview':{'principalNodes':23,'localExceptions':plan['localExceptions'],'linkCount':plan['selectionLinkCount'],
            'ringMinimumPct':None,'macajiMinimumPct':100,'visibilityCertified':False}})
    write_json(OUT/'RESULTADOS.json',results);write_json(OUT/'VALIDACION.json',validation)
    corridor=read_json(OUT/'CORRIDOR_COVERAGE_200M.json');corridor['metadata']['sourcePackage']=RELEASE_ID
    write_json(OUT/'CORRIDOR_COVERAGE_200M.json',corridor)
    print('Recalculando 100/150/200m y recortes censales',flush=True)
    folder=OUT/'coverage-inputs';folder.mkdir()
    dependencies.main(final=package,out=folder,js_output=OUT/'riobamba-brechas-actualizadas-data.js',expected_replacements=30)
    gaps=read_json(folder/'RESULTADOS.json');prior=read_json(base/'coverage-inputs/RESULTADOS.json')
    gaps['metadata']['sourceInventory']=prior['metadata']['sourceInventory'];gaps['inventoryCameraOverlay']=prior['inventoryCameraOverlay']
    text=json.dumps(gaps,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    (folder/'RESULTADOS.json').write_text(text,encoding='utf-8')
    (OUT/'riobamba-brechas-actualizadas-data.js').write_text('window.RIOBAMBA_UPDATED_GAPS = '+text+';\n',encoding='utf-8')
    write_json(OUT/'APROBACION_Y_FUENTES.json',receipt)
    pd.DataFrame(plan['scenario']['movements']).to_csv(OUT/'MOVIMIENTOS_MUNICIPALES_24.csv',index=False,encoding='utf-8-sig')
    (OUT/'INFORME_FINAL.md').write_text('# Municipales: nodos y ejes aprobados\n\n23 cruces principales y MUN-037 Junin x Puruha como excepcion local aprobada. Macaji100; Anillo sin minimo.\n\n'
        '159 camaras fijas:103existentes (30para cambio incluidas),26municipales y30policiales. Solo cambian24municipales urbanas.\n\n'
        'Los enlaces potenciales siguen una misma via hasta200m por extremo, no se presupone vision al girar ni a traves de manzanas. No se certifica continuidad optica ni cobertura completa de todos los corredores.\n',encoding='utf-8')
    require(all(digest(Path(p))==h for p,h in hashes.items()),'Cambio de fuente durante calculo')
    verify_derived(store,package,results)
    for folder,name in [(folder,'BRECHAS_ACTUALIZADAS.zip'),(OUT,'ENTREGA_POLICIA_KDE.zip')]:
        with zipfile.ZipFile(folder/name,'w',zipfile.ZIP_DEFLATED) as archive:
            for p in sorted(folder.iterdir()):
                if p.is_file() and p.suffix!='.zip':archive.write(p,p.name)
    print(json.dumps({'release':RELEASE_ID,'validation':validation['status'],'corridors':[r for r in results['corridors'] if r['ESCENARIO']=='B']},ensure_ascii=True),flush=True)


if __name__=='__main__':main()
