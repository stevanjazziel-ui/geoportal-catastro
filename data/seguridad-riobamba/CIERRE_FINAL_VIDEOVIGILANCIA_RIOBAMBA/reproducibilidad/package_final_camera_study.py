"""Portable GIS, ten real cartographic layouts, report and review ZIP; no publication."""
import csv
import json
import os
import shutil
import zipfile
from pathlib import Path

_dll_handles=[os.add_dll_directory(p) for p in ('C:/Program Files/QGIS 3.40.10/apps/Qt5/bin','C:/Program Files/QGIS 3.40.10/bin','C:/Program Files/QGIS 3.40.10/apps/qgis-ltr/bin')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from qgis.core import (Qgis,QgsApplication,QgsProject,QgsVectorLayer,QgsCoordinateReferenceSystem,
    QgsFillSymbol,QgsMarkerSymbol,QgsLineSymbol,QgsRendererCategory,QgsCategorizedSymbolRenderer,
    QgsReferencedRectangle,QgsRectangle,QgsPrintLayout,QgsLayoutItemMap,QgsLayoutItemLabel,
    QgsLayoutItemLegend,QgsLayoutItemScaleBar,QgsLayoutPoint,QgsLayoutSize,QgsLayoutExporter,
    QgsLayoutItemPage)
from qgis.PyQt.QtGui import QColor,QFont,QFontDatabase

from close_final_camera_study import OUT,PACKAGE,SOURCE,GROUPS,KEYS


def table(fields,rows):
    def value(v):
        if v is None:return 'No disponible'
        if isinstance(v,float):return f'{v:,.3f}'
        return str(v).replace('|',' / ').replace('\n',' ')
    return '\n'.join(['| '+' | '.join(fields)+' |','| '+' | '.join('---' for _ in fields)+' |']+
        ['| '+' | '.join(value(r.get(k)) for k in fields)+' |' for r in rows])


def report(data):
    qa=json.loads((OUT/'VALIDACION.json').read_text(encoding='utf-8'))
    assert qa['passed'],'Cannot package failed GIS checks'
    mac_b=next(r for r in data['corridors'] if r['ESCENARIO']=='B' and r['CORREDOR']==KEYS[0])
    mac_c=next(r for r in data['corridors'] if r['ESCENARIO']=='C' and r['CORREDOR']==KEYS[0])
    comparison=[]
    for key in data['optimization'][-1]['percent']:
        before=next(r for r in data['corridors'] if r['ESCENARIO']=='B_ANTERIOR' and r['CORREDOR']==key)
        after=next(r for r in data['corridors'] if r['ESCENARIO']=='B' and r['CORREDOR']==key)
        comparison.append({'CORREDOR':key,'ANTES_PCT':before['PCT_CUBIERTO'],'FINAL_153_PCT':after['PCT_CUBIERTO'],
            'DIFERENCIA_PP':after['PCT_CUBIERTO']-before['PCT_CUBIERTO']})
    audit=json.loads((OUT/'CAMARAS_RECUPERADAS.geojson').read_text(encoding='utf-8'))
    lines=['# Cierre final del estudio de videovigilancia - Riobamba','',
        '**Entrega final. Publicacion autorizada por el usuario; se conservan las limitaciones y advertencias del estudio.**',
        '## Resumen ejecutivo',
        '103 existentes con103geometrias,0nulas;50municipales=22rurales+4LasAbras+24estructurales;30Policia;183equipos. Existentes ocupan100emplazamientos por tres pares documentales co-localizados, sin doble conteo en cobertura.',
        f"Las nuevas municipales desplazan {sum(r['CAMBIO'] for r in data['municipalChanges'])} puntos. Se modifican {len(data['policeChanges'])} policiales tras cerrar las50; las demas conservan su posicion.",
        table(['INDICADOR','103','153','183'],data['summary']),
        '## Restriccion y prioridades municipales',
        f"Macaji anterior=91.9369%; FINAL SIN Policia={mac_b['PCT_CUBIERTO']:.5f}%; con183={mac_c['PCT_CUBIERTO']:.5f}%. Longitudtotal={mac_b['TOTAL_M']/1000:.6f}km; cubierta153={mac_b['CUBIERTO_M']/1000:.6f}km; remanente153={mac_b['NO_CUBIERTO_M']:.3f}m. La condicion>=98% se cumple antes de revisar Policia.",
        'Se mantienen26municipales aceptadas y se seleccionan24 entre nodos/cruces reales. MILP HiGHS: variables binarias por candidato, union de intervalos lineales de cobertura200m, no muestreo raster ni suma de buffers. Macaji>=98% es restriccion; maximizar Anillo y luego maximizar Ciclovias sin sacrificar Anillo (tolerancia numerica0.001m). Sin cuotas individuales ni pesos arbitrarios. Identificadores municipales se emparejan minimizando desplazamiento, no determinan la seleccion.',
        table(['CORREDOR','ANTES_PCT','FINAL_153_PCT','DIFERENCIA_PP'],comparison),
        '**ADVERTENCIA RELEVANTE: la prioridad estricta de maximizar Anillo produce una perdida importante de Ciclovias. No se oculta ni se presenta esta configuracion como mejora en los tres corredores. Recuperar la cobertura previa de Ciclovias requiere revisar el compromiso entre prioridades; no se cambia automaticamente la orden del usuario ni se transfieren rurales/policiales.**',
        '## Diagnostico de la condicion no cumplida: conservar Ciclovias',
        'Dos comprobaciones auxiliares usan los mismos nodos, radios y26municipales fijas:1)mantener24estructurales,Macaji>=98% y conservar la cobertura anterior deCiclovias;2)minimizar el numero de estructurales necesario para conservar simultaneamente Anillo maximo y Ciclovias anterior. Ninguna modifica las50finales ni crea una propuesta oficial nueva. No son nuevas ponderaciones; sirven para explicar el compromiso y la solucion minima necesaria.',
        table(['case','status','message','structuralCameras','municipalTotal','percent','mipGap','dualBound'],data['tradeoffDiagnosis']['scenarios']),
        'Si una corrida termina por limite de tiempo, se reporta incumbente y cota, NO se declara minimo global. Un resultado alternativo con24requiere autorizacion para modificar la prioridad estricta de Anillo. Un resultado conmasde24NO se incorpora porque se mantienen exactamente50municipales.',
        table(['phase','objective','status','message','seconds','mipGap','nodes','modelCoveredM'],data['optimization']),
        'La solucion es optima numericamente dentro del universo de candidatos real disponible, con las tolerancias reportadas. No demuestra optimalidad sobre cualquier poste o emplazamiento no cartografiado. Las fases ordenadas de Anillo y Ciclovias quedan en OPTIMIZACION_ESTRUCTURAL.json.',
        '## Distribucion y movimientos municipales',table(['ID','GRUPO','DISTANCIA_MOVIMIENTO_M','CAMBIO','MOTIVO'],data['municipalChanges']),
        'Se conservan2por cada11cabeceras y4Abras aceptadas. Las posiciones propuestas requieren inspeccion de poste, energia, permisos y campo visual.',
        '## Policia: revision marginal despues de cerrar153',
        'Se inicia con las30 del ultimo paquete consolidado, no con una seleccion nueva. Se recalculan las30 frente a103+50final+otras29. Se revisan las5observadas y otras con perdida de eventos D/V y aumento de solape tras la nueva configuracion municipal. Un reemplazo requiere esa perdida comprobada, alternativa con coincidencia D/V significativa residual, masD+V, sin disminuir D ni V individualmente y menos solape. No se usan cortes de distancia,90%solape ni minimos de eventos. Corredores y UPC se reportan, no optimizan la seleccion policial. La revision es local secuencial, no optimizacion completa de30.',
        table(['ID_ANTERIOR','CANDIDATO_ANTERIOR','CANDIDATO_FINAL','DV_NUEVOS_ANTES','DV_NUEVOS_DESPUES','SOLAPE_ANTES','SOLAPE_DESPUES','MOTIVO'],data['policeChanges']),
        'POLICIA_CAMBIOS_FINAL.csv contiene solo reemplazos reales. Los aportes exclusivos no se suman para obtener ganancia global; las comparaciones de escenarios se calculan con la union completa. Tablas detalladas conservan superficie y nivel de significancia, que pueden variar aunque crezca el numero de eventos.',
        '## Georreferenciacion de las cuatro recuperadas',
        table(['ID','X','Y','DIRECCION_DOCUMENTAL','DIRECCION_CARTOGRAFICA','METODO_GEO','FUENTE_GEO','CONFIANZA_GEO','OBSERVACION_GEO'],[r['properties'] for r in audit['features']]),
        'Inventario original conservado separado.016/017son dos equipos en un emplazamiento censal aceptado con confianzaMEDIA; discrepanciaV/Y y943.98m municipal documentada; no se certifica la nomenclaturaV/Y ni el poste.085conserva corroboracion0.41m.103cruce censal exacto, corroboracion municipal limitada. Ninguna coordenada cartografica se presenta como levantamiento de campo.',
        '## Las Abras y Cunduana',
        table(list(data['axisComparison']),[data['axisComparison']]),
        'Se adopta operativamente MAATE dentro del canton, conservando MAATE completo, eje anterior y todos los13insumosMAATE y2Cunduana. No se certifica externamente su oficialidad. Coincidencia geometrica exacta es sensible a noding/redondeo; no equivale a coincidencia fisica. Sensibilidades1/5/10/20m se conservan como diagnostico, sin modificar geometria.',
        table(['ID','DECISION','EJE_MAATE_DIST_M','MAATE_CUBIERTO_M','MAATE_EXCLUSIVO_M','POBLACION_ASOCIADA','CUNDUANA_PUNTOS_200M','MOTIVO'],data['abrasReview']),
        table(['ID','DECISION','MAATE_ACTUAL_M','MAATE_ALTERNATIVA_M','DIMENSIONES_ACTUAL','DIMENSIONES_ALTERNATIVA'],data['abrasAlternativesAudit']['decisions']),
        'Se revisaron los37cruces reales MAATE anteriores frente a103+otras49municipales finales. No se encontro mejora de longitud exclusiva sin perder dimensiones de evidencia. LAS_ABRAS_ALTERNATIVAS_FINAL.csv conserva actual+5alternativas y camposCunduana,limpieza,proteccion,JoseMarti,poblacion,D/V/C yGi*complementario.',
        'Cunduana es ambiental, distante de MAATE; no se integra a incidentes, Gi* ni al objetivo policial. Mapas y capas muestran sus posiciones reales, no coincidencias inventadas.',
        '## Cobertura y unidades',
        'Radio200m, no diametro. EPSG:32717, buffer con64segmentos por cuadrante, UNION/DISSOLVE e interseccion; fracciones no sumadas entre camaras. Tres escenariosA103,B153,C183. Cobertura territorial urbana y cantonal se reportan por separado. Cobertura poblacional es estimacion arealCPV2022 dentro de18Plataformas (union29.293km2), con poblacion valida y faltantes explicitos; no equivale a poblacion rural completa ni a visibilidad real.',
        table(list(data['territorial'][0]),data['territorial']),table(list(data['population'][0]),data['population']),
        '## Hot Spots congelados y remanentes',
        'Las6mallasGi* mantienenWKB,Gi,z-score,p-value,90/95/99,distancias,ambitos,categorias. Solo se agregan campos de relacion con cobertura. Convivencia es complementaria policial. Coincidencia espacialD/V no es una nueva prueba conjunta. No se recalcula KDE ni Gi*.',
        table(list(data['hotspots'][0]),[r for r in data['hotspots'] if r['ESCENARIO']=='C']),
        'Hot Spot atendido completo:fraccion>=1-1e-8; sin cobertura:<=1e-8; resto:parcial. Tolerancia numerica, no umbral operativo de suficiencia. Los remanentes se reportan separados por nivel y ambito.',
        '## Brechas lineales finales',
        'BRECHA_MACAJI_FINAL,ANILLO,CICLOVIAS,LAS_ABRAS=corredor menos unionC183. IDs,longitud,extremos,camaracercana y distancia. DIST_CAMARA_M es distancia minima entre el segmento completo y el punto de la camara, no desde su centro ni un indicador de separacion maxima. La distancia de un remanente puede ser casi200m por comenzar en el limite delbuffer. Estas brechas lineales no son una clasificacion de brechas por manzana.',
        table(['ESCENARIO','CORREDOR','TOTAL_M','CUBIERTO_M','NO_CUBIERTO_M','PCT_CUBIERTO'],[r for r in data['corridors'] if r['ESCENARIO'] in ('A','B','C')]),
        '## Control de calidad',f"{qa['nChecks']} controles GIS: {sum(r['passed'] for r in qa['checks'])} aprobados, {len(qa['failed'])} fallidos.",
        'Se verifican counts,CRS,nulos,invalidas,IDs,0/0,fueraambito,coincidencias,union200m,longitudes,nearest,estadisticasGi*,atributos fuentes,calculos poblacion,incidentes y SHA256. RIO075original fuera del canton se conserva y advierte; no se elimina para aparentar103dentro. Inventarioadministrativooriginal conserva4nulos, pero capaFINAL tiene0.',
        '## Advertencias','\n'.join('- '+w for w in data['warnings']),
        '**La publicacion no elimina la advertencia de perdida de Ciclovias ni certifica viabilidad de instalacion en campo.**']
    (OUT/'INFORME_FINAL.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
    with (OUT/'CATALOGO_CAPAS.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        w=csv.DictWriter(stream,['name','group','records','crs','source','fields']);w.writeheader()
        w.writerows({**r,'fields':', '.join(r['fields'])} for r in data['catalog'])


def main():
    data=json.loads((OUT/'RESULTADOS.json').read_text(encoding='utf-8'))
    report(data)
    app=QgsApplication([],False);app.initQgis()
    fonts=[]
    for filename in ('arial.ttf','arialbd.ttf','ariali.ttf','arialbi.ttf'):
        font_id=QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+filename)
        if font_id>=0:fonts.extend(QFontDatabase.applicationFontFamilies(font_id))
    if not fonts:raise RuntimeError('No readable font registered for cartographic layouts')
    app.setFont(QFont(fonts[0],9))
    project=QgsProject.instance();project.setCrs(QgsCoordinateReferenceSystem('EPSG:32717'))
    project.setFileName(str(OUT/'CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.qgz'));project.setFilePathStorage(Qgis.FilePathType.Relative)
    root=project.layerTreeRoot();groups={name:root.addGroup(name) for name in GROUPS};layers={}
    for item in data['catalog']:
        name=item['name'];group=item['group']
        layer=QgsVectorLayer(str(PACKAGE)+'|layername='+name,name,'ogr')
        if not layer.isValid():raise ValueError(name)
        if layer.geometryType()==Qgis.GeometryType.Point:
            color='#18815b' if 'MUNICIPAL' in name else '#e8bd16' if 'POLICIA' in name else '#246db5' if 'CAMARAS' in name else '#ba6779' if 'CUNDUANA' in name else '#467b62'
            layer.renderer().setSymbol(QgsMarkerSymbol.createSimple({'name':'circle','color':color,'outline_color':'white','size':'1.9'}))
            if name=='CAMARAS_EXISTENTES_103_FINAL':
                categories=[QgsRendererCategory(False,QgsMarkerSymbol.createSimple({'name':'circle','color':'#246db5','outline_color':'white','size':'1.9'}),'Existente'),
                    QgsRendererCategory(True,QgsMarkerSymbol.createSimple({'name':'square','color':'#8b46b5','outline_color':'white','size':'1.9'}),'Requiere cambio (31)')]
                layer.setRenderer(QgsCategorizedSymbolRenderer('REQUIERE_CAMBIO',categories))
        elif layer.geometryType()==Qgis.GeometryType.Line:
            color='#bf5761' if name.startswith('BRECHA_') else '#279775' if name.startswith('CUBIERTO_') else '#946f39' if name=='LAS_ABRAS_ACTUAL' else '#598fac'
            layer.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color':color,'line_width':'0.55' if name.startswith(('BRECHA','CUBIERTO')) else '0.35'}))
        elif layer.geometryType()==Qgis.GeometryType.Polygon:
            fill='246,205,88,60' if name.startswith(('COBERTURA','BUFFERS')) else '215,227,232,18'
            layer.renderer().setSymbol(QgsFillSymbol.createSimple({'color':fill,'outline_color':'80,110,118,120','outline_width':'0.14'}))
            if name in ('COBERTURA_A','COBERTURA_MUNICIPAL_200M','COBERTURA_POLICIA_200M'):
                color={'COBERTURA_A':'#246db5','COBERTURA_MUNICIPAL_200M':'#18815b','COBERTURA_POLICIA_200M':'#e8bd16'}[name]
                symbol=QgsFillSymbol.createSimple({'color':color,'outline_color':color,'outline_width':'0.14'})
                symbol.setOpacity(.22);layer.renderer().setSymbol(symbol)
            if layer.fields().indexFromName('GI_CLASS')>=0:
                base=next((v for k,v in {'DELINCUENCIA':'#d66575','VIOLENCIA':'#9471b8','CONVIVENCIA':'#6aa875'}.items() if k in name),'#d66575')
                categories=[]
                for label,color,alpha in [('HOTSPOT 99%',base,.48),('HOTSPOT 95%',base,.30),('HOTSPOT 90%',base,.17),
                    ('NO SIGNIFICATIVO','#cdd3d7',.12),('COLDSPOT 90%','#67b8ea',.17),('COLDSPOT 95%','#358bd3',.30),('COLDSPOT 99%','#2869b1',.48)]:
                    symbol=QgsFillSymbol.createSimple({'color':color,'outline_color':color,'outline_width':'0.12'});symbol.setOpacity(alpha)
                    categories.append(QgsRendererCategory(label,symbol,label))
                layer.setRenderer(QgsCategorizedSymbolRenderer('GI_CLASS',categories))
        project.addMapLayer(layer,False);node=groups[group].addLayer(layer)
        node.setItemVisibilityChecked(name in ('CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL','COBERTURA_A','COBERTURA_MUNICIPAL_200M','COBERTURA_POLICIA_200M','CORREDORES','PLATAFORMAS_TERRITORIALES','LIMITE_CANTONAL'))
        layers[name]=layer
    urban=layers['PLATAFORMAS_TERRITORIALES'];project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(urban.extent(),urban.crs()))
    roads=layers['RED_VIAL_CONTEXTO']
    if roads.isValid():roads.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color':'175,189,194,180','line_width':'0.10'}))
    views=[('01','103 camaras existentes',['CAMARAS_EXISTENTES_103_FINAL','COBERTURA_A'],'CAMARAS_EXISTENTES_103_FINAL'),
        ('02','50 propuestas municipales',['PROPUESTA_MUNICIPAL_50_FINAL','CORREDORES','COBERTURA_MUNICIPAL_200M'],'PROPUESTA_MUNICIPAL_50_FINAL'),
        ('03','30 Policia y Hot Spots D/V',['PROPUESTA_POLICIA_30_FINAL','HOTSPOT_DELINCUENCIA','HOTSPOT_VIOLENCIA','COBERTURA_POLICIA_200M'],'PROPUESTA_POLICIA_30_FINAL'),
        ('04','Sistema completo:183 equipos',['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL','COBERTURA_A','COBERTURA_MUNICIPAL_200M','COBERTURA_POLICIA_200M'],'PROPUESTA_MUNICIPAL_50_FINAL')]
    for number,key,label in (('05',KEYS[0],'MACAJI'),('06',KEYS[1],'ANILLO'),('07',KEYS[2],'CICLOVIAS'),('08','QUEBRADA_LAS_ABRAS','LAS_ABRAS')):
        metric=next(r for r in data['corridors'] if r['ESCENARIO']=='C' and r['CORREDOR']==key)
        names=['CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL',
            'CUBIERTO_'+label+'_FINAL','BRECHA_'+label+'_FINAL','COBERTURA_A','COBERTURA_MUNICIPAL_200M','COBERTURA_POLICIA_200M']
        if label=='LAS_ABRAS':names+=['CUNDUANA_PUNTOS_CRITICOS','CUNDUANA_TRAMOS_LIMPIEZA','LAS_ABRAS_ACTUAL']
        views.append((number,f"{label}: {metric['PCT_CUBIERTO']:.2f}% cubierto (183)",names,'CUBIERTO_'+label+'_FINAL'))
    views.extend([('09','Hot Spots Delincuencia:estadistica congelada',['HOTSPOT_DELINCUENCIA','COBERTURA_C'],'HOTSPOT_DELINCUENCIA'),
        ('10','Hot Spots Violencia:estadistica congelada',['HOTSPOT_VIOLENCIA','COBERTURA_C'],'HOTSPOT_VIOLENCIA')])
    maps=OUT/'mapas';maps.mkdir(exist_ok=True)
    outputs=[]
    for number,title,names,extent_name in views:
        layout=QgsPrintLayout(project);layout.initializeDefaults();layout.setName('MAPA_'+number)
        page=layout.pageCollection().pages()[0];page.setPageSize(QgsLayoutSize(297,230))
        heading=QgsLayoutItemLabel(layout);heading.setText('RIOBAMBA | '+title);heading.setFont(QFont('Arial',14,QFont.Bold));heading.setFontColor(QColor('#143c50'))
        heading.attemptMove(QgsLayoutPoint(8,5));heading.attemptResize(QgsLayoutSize(280,13));layout.addLayoutItem(heading)
        map_item=QgsLayoutItemMap(layout);layout.addLayoutItem(map_item);map_item.attemptMove(QgsLayoutPoint(8,23));map_item.attemptResize(QgsLayoutSize(208,188))
        map_layers=[layers[n] for n in names]+[layers['PLATAFORMAS_TERRITORIALES']]
        if roads.isValid():map_layers.append(roads)
        map_layers.append(layers['LIMITE_CANTONAL']);map_item.setLayers(map_layers);map_item.setKeepLayerSet(True)
        extent=QgsRectangle(layers[extent_name].extent())
        if number=='08':extent.combineExtentWith(layers['CUNDUANA_PUNTOS_CRITICOS'].extent());extent.combineExtentWith(layers['LAS_ABRAS_MAATE_REFERENCIA_CANTON'].extent())
        extent.scale(1.12);map_item.zoomToExtent(extent)
        legend=QgsLayoutItemLegend(layout);layout.addLayoutItem(legend);legend.setTitle('Capas');legend.setLinkedMap(map_item);legend.setAutoUpdateModel(False)
        legend.model().rootGroup().clear()
        labels={'CAMARAS_EXISTENTES_103_FINAL':'Existentes (103)','PROPUESTA_MUNICIPAL_50_FINAL':'Municipales (50)',
            'PROPUESTA_POLICIA_30_FINAL':'Policia (30)','CORREDORES':'Corredores reales',
            'COBERTURA_A':'Cobertura 103:200m','COBERTURA_C':'Cobertura 183:200m',
            'COBERTURA_MUNICIPAL_200M':'Radio Municipio:200m','COBERTURA_POLICIA_200M':'Radio Policia:200m',
            'HOTSPOT_DELINCUENCIA':'Hot Spots Delincuencia','HOTSPOT_VIOLENCIA':'Hot Spots Violencia',
            'CUNDUANA_PUNTOS_CRITICOS':'Puntos Cunduana','CUNDUANA_TRAMOS_LIMPIEZA':'Tramos de limpieza',
            'LAS_ABRAS_ACTUAL':'Las Abras:eje anterior'}
        for name in names:
            node=legend.model().rootGroup().addLayer(layers[name]);node.setUseLayerName(False)
            node.setName(labels.get(name,'Sin cobertura' if name.startswith('BRECHA_') else 'Tramos cubiertos' if name.startswith('CUBIERTO_') else name))
        legend.attemptMove(QgsLayoutPoint(220,25));legend.attemptResize(QgsLayoutSize(68,145))
        legend.setLegendFilterByMapEnabled(True)
        if number in ('01','02','04','09','10'):
            inset=QgsLayoutItemMap(layout);layout.addLayoutItem(inset)
            inset.attemptMove(QgsLayoutPoint(220,150));inset.attemptResize(QgsLayoutSize(68,57))
            inset.setLayers(map_layers);inset.setKeepLayerSet(True)
            inset_extent=QgsRectangle(urban.extent());inset_extent.scale(1.08);inset.zoomToExtent(inset_extent)
            inset.setFrameEnabled(True)
            inset_label=QgsLayoutItemLabel(layout);inset_label.setText('Detalle urbano')
            inset_label.setFont(QFont(fonts[0],9));inset_label.attemptMove(QgsLayoutPoint(220,142))
            inset_label.attemptResize(QgsLayoutSize(68,8));layout.addLayoutItem(inset_label)
        scale=QgsLayoutItemScaleBar(layout);layout.addLayoutItem(scale);scale.setStyle('Single Box');scale.setLinkedMap(map_item)
        scale.setUnits(Qgis.DistanceUnit.Kilometers);scale.setUnitLabel('km');scale.setFont(QFont(fonts[0],8));scale.applyDefaultSize()
        scale.attemptMove(QgsLayoutPoint(10,199))
        footer=QgsLayoutItemLabel(layout);footer.setText('EPSG:32717 | Radio200m | Union disuelta | Fuentes reales del proyecto | 04oct2026 | Entrega final')
        footer.setFont(QFont('Arial',8));footer.attemptMove(QgsLayoutPoint(8,215));footer.attemptResize(QgsLayoutSize(280,10));layout.addLayoutItem(footer)
        project.layoutManager().addLayout(layout)
        exporter=QgsLayoutExporter(layout);settings=QgsLayoutExporter.ImageExportSettings();settings.dpi=145
        png=maps/('MAPA_'+number+'.png');status=exporter.exportToImage(str(png),settings)
        if status!=QgsLayoutExporter.Success:raise RuntimeError('Map export '+number)
        outputs.append({'map':int(number),'title':title,'png':str(png.relative_to(OUT)),'layers':names})
    if not project.write():raise RuntimeError('Project write')
    count=len(project.mapLayers());project.clear()
    valid=project.read(str(OUT/'CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.qgz')) and len(project.mapLayers())==count and all(l.isValid() for l in project.mapLayers().values())
    if not valid:raise RuntimeError('Portable project roundtrip')
    (OUT/'VALIDACION_QGIS.json').write_text(json.dumps({'passed':True,'layers':count,'groups':len(GROUPS),'layouts':10,'relativePaths':True,'maps':outputs},indent=2),encoding='utf-8')
    project.clear();app.exitQgis()
    (OUT/'README.md').write_text('# CIERRE FINAL VIDEOVIGILANCIA RIOBAMBA\n\nEntrega LOCAL para revision, sin commit ni push.\n\nAbrir el .qgz con el .gpkg al lado:14grupos y10layouts. mapas/ contiene10PNG. index.html permite revisar los mapas y descargar resultados sin servidor.\n\nCRS:EPSG32717. Buffer200m disuelto.103existentes +50municipales(22rural+4Abras+24estructural)+30Policia=183.\n\nINFORME_FINAL.md contiene resumen, metodologia y advertencias. CATALOGO_CAPAS.csv lista fuente,CRS,conteo y todos los campos. VALIDACION.json contiene controles GIS; VALIDACION_QGIS.json verifica el proyecto.\n\nADVERTENCIA:la prioridad estricta Anillo tras Macaji>=98% reduce mucho Ciclovias; requiere decision antes de aprobacion. Las coordenadas cartograficas no certifican postes ni viabilidad de campo.\n\ninsumos_originales conserva los15insumos ambientales entregados. reproducibilidad contiene scripts yhelpers; necesitan el entorno GIS y fuentes externas documentadas para recalculo, no para abrir este paquete.\n',encoding='utf-8')
    html=['<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Cierre final | Riobamba</title><style>body{margin:0;background:#edf3f5;color:#183a4b;font:14px Arial}header{background:#153f53;color:white;padding:16px 22px}h1{font-size:20px;margin:0}main{max-width:1220px;margin:auto;padding:20px}nav{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}a{color:#17628e}figure{margin:0 0 24px;background:white;border:1px solid #d9e2e7}figure img{width:100%;display:block}figcaption{padding:12px;font-weight:bold}.notice{border-left:4px solid #bb8027;padding:12px;background:#fff5dc}</style><header><h1>Cierre final de videovigilancia · Riobamba</h1><p>183 equipos · Radio 200 m · Revisión local, sin publicar</p></header><main><p class="notice">Macají ≥98 % se cumple con las 153 cámaras. La prioridad estricta de Anillo reduce Ciclovías; revisar esta pérdida antes de aprobar.</p><nav><a href="CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.gpkg">GeoPackage</a><a href="CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.qgz">Proyecto QGIS</a><a href="INFORME_FINAL.md">Informe</a><a href="INDICADORES_103_153_183.csv">Comparación</a><a href="VALIDACION.json">Controles</a></nav>']
    for row in outputs:html.append(f'<figure id="mapa-{row["map"]}"><figcaption>Mapa {row["map"]}: {row["title"]}</figcaption><img src="{row["png"]}" alt="{row["title"]}" loading="lazy"></figure>')
    html.append('</main></html>')
    (OUT/'index.html').write_text('\n'.join(html).replace('Revisión local, sin publicar','Entrega final · publicación autorizada').replace('revisar esta pérdida antes de aprobar','esta limitación permanece documentada'),encoding='utf-8')
    readme=OUT/'README.md'
    readme.write_text(readme.read_text(encoding='utf-8').replace('Entrega LOCAL para revision, sin commit ni push.','Entrega final para publicacion autorizada.').replace('requiere decision antes de aprobacion','limitacion conservada en la entrega publicada')+'\nSimbologia:103existentes azules;31para cambio cuadrado morado;50municipales verdes;30Policia amarillas. Radios200m del color de cada grupo. Las31 forman parte de103, no son adicionales.\n',encoding='utf-8')
    scripts=OUT/'reproducibilidad';scripts.mkdir(exist_ok=True)
    for name in ('close_final_camera_study.py','test_final_camera_study.py','package_final_camera_study.py',
        'consolidate_camera_project.py','build_police_camera_proposal.py','review_police_camera_efficiency.py',
        'optimize_municipal_cameras_50.py','build_current_camera_diagnosis.py','build_remaining_camera_coverage.py',
        'finalize_police_efficiency_review.py','review_police_five_100_geo.py','diagnose_final_corridor_tradeoff.py',
        'audit_final_abras.py','augment_final_camera_study.py','publish_final_camera_styles.py'):
        shutil.copy2(Path(__file__).parent/name,scripts/name)
    target=OUT.parent/'CIERRE_FINAL_VIDEOVIGILANCIA_RIOBAMBA.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in OUT.rglob('*'):
            if path.is_file() and path.suffix not in ('.lock','.lck') and path.name!='MUNICIPALES_CHECKPOINT.gpkg':archive.write(path,Path(OUT.name)/path.relative_to(OUT))
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:raise RuntimeError('ZIP CRC validation')
    print(json.dumps({'zip':str(target),'bytes':target.stat().st_size,'layers':count,'groups':14,'maps':10}))


if __name__=='__main__':main()
