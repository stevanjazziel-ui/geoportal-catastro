"""Assemble all published GIS inputs and matching KDE rasters for QGIS, without editing sources."""
import json
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

from build_final_municipal_axis_release import OUT as RELEASE,RELEASE_ID
from final_municipal_axis_nodes import OUT as STUDY
from review_police_verified_main_roads import ROOT,ROADS
from review_police_kde_intersections import kde,source_hash

OUT=ROOT.parent/'entregas/VISOR_RIOBAMBA_QGIS_20261016'
GPKG=OUT/'VISOR_RIOBAMBA_COMPLETO.gpkg'


def read_js(name):
    return json.JSONDecoder().raw_decode((ROOT/name).read_text(encoding='utf-8').split('=',1)[1].lstrip())[0]


def main():
    assert (RELEASE/'VALIDACION.json').exists(),'Primero terminar la version aprobada'
    assert not (OUT/'VISOR_RIOBAMBA.qgz').exists(),'No se sobrescribe una entrega final'
    OUT.mkdir(parents=True,exist_ok=True)
    shutil.copy2(RELEASE/'ESCENARIO_FINAL_183.gpkg',GPKG)
    manifest=[]
    def add(name,frame,source,note=''):
        if isinstance(frame,gpd.GeoDataFrame):
            frame=frame.to_crs(32717)
            assert frame.geometry.is_valid.all(),name
        pyogrio.write_dataframe(frame,GPKG,layer=name)
        manifest.append({'name':name,'source':source,'crs':'EPSG:32717' if isinstance(frame,gpd.GeoDataFrame) else None,
            'records':len(frame),'fields':[{ 'name':c,'type':str(frame[c].dtype)} for c in frame.columns if c!='geometry'],'description':note})
    for name,kind in pyogrio.list_layers(GPKG):
        f=pyogrio.read_dataframe(GPKG,layer=name)
        manifest.append({'name':name,'source':RELEASE_ID+'/ESCENARIO_FINAL_183.gpkg','crs':str(f.crs) if kind else None,
            'records':len(f),'fields':[{'name':c,'type':str(f[c].dtype)} for c in f.columns if c!='geometry'],'description':'Capa o tabla de la version final publicada.'})
    cameras={key:gpd.read_file(GPKG,layer=layer) for key,layer in [('EXISTENTES','CAMARAS_EXISTENTES_103_FINAL'),('MUNICIPALES','PROPUESTA_MUNICIPAL_50_FINAL'),('POLICIA','PROPUESTA_POLICIA_30_FINAL')]}
    for group,frame in cameras.items():
        field='ID_CAMARA' if group=='EXISTENTES' else 'ID_PROPUESTA' if group=='MUNICIPALES' else 'ID_POLICIA'
        for radius in (100,150,200):
            f=frame[[field,'geometry']].copy();f['RADIO_M']=radius;f['DIAMETRO_M']=radius*2
            f['GRUPO']=group;f['COB_VISUAL_CERTIFICADA']=False
            if group=='EXISTENTES':f['REQUIERE_CAMBIO']=frame.REQUIERE_CAMBIO
            f.geometry=frame.geometry.buffer(radius,resolution=64)
            add(f'RADIOS_{group}_{radius}M',f,RELEASE_ID,'Buffers individuales de radio, no campo visual. Sin disolver ni duplicar sitios.')
    existing=cameras['EXISTENTES'];municipal=cameras['MUNICIPALES']
    for name,f in [('EXISTENTES_PARA_CAMBIO_30',existing.loc[existing.REQUIERE_CAMBIO.eq(1)]),
        ('EXISTENTES_SIN_CAMBIO_73',existing.loc[~existing.REQUIERE_CAMBIO.eq(1)]),
        ('MUNICIPALES_URBANAS_24',municipal.loc[municipal.GRUPO.eq('RED_ESTRUCTURAL')]),
        ('MUNICIPALES_RURALES_22',municipal.loc[municipal.GRUPO.eq('CABECERA_RURAL')]),
        ('MUNICIPALES_LAS_ABRAS_4',municipal.loc[municipal.GRUPO.eq('LAS_ABRAS')])]:add(name,f,RELEASE_ID)
    corridors=gpd.read_file(GPKG,layer='CORREDORES')
    for key in corridors.CORREDOR.unique():add(key,corridors.loc[corridors.CORREDOR.eq(key)],RELEASE_ID,'Geometria original del corredor; sin modificar ni simplificar.')
    for name in ('TRAMOS','RECTILINEOS','ENLACES','HUECOS'):
        add('MUNICIPALES_'+name,gpd.read_file(STUDY/'AUDITORIA_VIAL.gpkg',layer='EJES_PRIORITARIOS_'+name),str(STUDY.relative_to(ROOT)),
            'Auditoria vial potencial de los nodos aprobados. No certifica vision real ni conecta calles al girar.')
    add('RED_VIAL_OSM_NODOS',gpd.read_file(ROADS),str(ROADS),'Fuente de vertices originales compartidos; no se crean nodos geometricos.')
    municipal_source=ROOT.parent/'riobamba_matrix_review_20260921/cartografia_base/RIOBAMBA_Cartografia Base.gdb'
    add('RED_VIAL_MUNICIPAL',gpd.read_file(municipal_source,layer='Vialidad_urbana'),str(municipal_source)+'|Vialidad_urbana','Fuente municipal original, no homologada automaticamente con OSM.')
    canton=read_js('riobamba-cantonal-data.js')
    add('PARROQUIAS_CANTONALES',gpd.GeoDataFrame.from_features(canton['parishes']['features'],crs=4326),'riobamba-cantonal-data.js')
    for name in ('CABECERAS_RURALES','AMBITOS_CABECERAS_PUGS'):
        path=ROOT/'data/seguridad-riobamba/CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA'/(name+'.geojson')
        assert path.exists(),str(path)
        add(name,gpd.read_file(path),str(path.relative_to(ROOT)))
    # Export the same metric KDE calculation; never recompute or replace Gi* statistics.
    events=gpd.read_file(GPKG,layer='INCIDENTES_CLASIFICADOS')
    conflict=read_js('riobamba-conflictividad-data.js');rasters=[]
    classes=['DELINCUENCIA','VIOLENCIA','CONVIVENCIA']
    for scope in ('URBANO','RURAL','CANTONAL'):
        grid=conflict['urbanGrid'] if scope=='URBANO' else canton['kdeGrids'][scope]
        categories=['TODOS']+classes if scope!='CANTONAL' else ['TODOS']
        for category in categories:
            subset=events.loc[events.CATEGORIA.isin(classes) if category=='TODOS' else events.CATEGORIA.eq(category)]
            subset=subset.loc[subset.AMBITO.isin(['URBANO','RURAL'])] if scope=='CANTONAL' else subset.loc[subset.AMBITO.eq(scope)]
            parameters=conflict['parameters'].get(scope,{})
            parameter=parameters.get(category) or parameters.get('__ALL__') or {}
            bandwidth=200 if scope=='URBANO' else parameter.get('bandwidth',grid['bandwidth'])
            density,mask,west,north,size=kde([(p.x,p.y) for p in subset.geometry],grid,bandwidth)
            array=density.reshape(grid['height'],grid['width']);valid=mask.reshape(array.shape)
            name=f'KDE_{scope}_{category}'
            np.savez_compressed(OUT/(name+'.npz'),density=array,valid=valid)
            positive=density[density>0]
            thresholds=[float(np.quantile(positive,p)) if len(positive) else 0 for p in (.30,.50,.75,.90,.95,1)]
            rasters.append({'name':name,'crs':'EPSG:32717','west':west,'north':north,'cellSize':size,
                'width':grid['width'],'height':grid['height'],'bandwidthM':bandwidth,'records':len(subset),'thresholds':thresholds,
                'scope':scope,'source':'Misma funcion KDE metrica, datos reales clasificados; peso1por registro. Gi* sin recalcular.'})
    manifest.append({'name':'KDE_RASTERS','rasters':rasters})
    metadata={'release':RELEASE_ID,'gpkg':GPKG.name,'crs':'EPSG:32717','layers':manifest,'rasters':rasters,
        'sourcePackageSha256':source_hash(RELEASE/'ESCENARIO_FINAL_183.gpkg'),'complete':True,
        'cameraCounts':{'existing':103,'replacementIncluded':30,'municipal':50,'police':30},
        'notes':['Los mapas base OSM/satelite son servicios remotos: el QGIS agrega OSM como capa opcional en linea; no se descargan mosaicos para uso offline.',
            'Radios100/150/200m son proximidad potencial, no visibilidad a traves de manzanas. Diametro=2*radio.',
            'MUN-037 Junin x Puruha es excepcion local aprobada para conservar Macaji100. Anillo sin minimo.',
            'Los6Gi*urbanos/rurales conservan geometria, z,p,significancia y parametros originales; solo cambian atributos de cobertura.',
            'Los KDE son rasters numericos exportados con la misma formula y parametros del visor; no son Gi*.']}
    (OUT/'MANIFIESTO.json').write_text(json.dumps(metadata,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    shutil.copy2(RELEASE/'VALIDACION.json',OUT/'VALIDACION_PUBLICACION.json')
    print(json.dumps({'folder':str(OUT),'vectorTables':len(manifest)-1,'rasters':len(rasters),'sizeMB':GPKG.stat().st_size/1e6}),flush=True)


if __name__=='__main__':main()
