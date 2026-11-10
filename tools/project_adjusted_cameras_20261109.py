"""Portable QGIS view of the approved adjusted positions and recalculated radii."""
import pathlib,os
os.environ['QT_QPA_PLATFORM']='offscreen'
from qgis.core import QgsApplication,QgsProject,QgsVectorLayer,QgsCoordinateReferenceSystem,QgsMarkerSymbol,QgsFillSymbol,QgsLineSymbol,QgsRasterLayer,QgsReadWriteContext
app=QgsApplication([],False);app.initQgis();p=QgsProject.instance();p.setCrs(QgsCoordinateReferenceSystem('EPSG:32717'))
R=pathlib.Path(__file__).resolve().parents[1];out=R/'data/seguridad-riobamba/SIG_BRIDGE_RELEASES/CAMARAS_AJUSTADAS_USUARIO_20261109';gp=out/'ESCENARIO_FINAL_183.gpkg'
p.setFileName(str(out/'ABRIR_CAMARAS_AJUSTADAS.qgs'));p.setTitle('Camaras ajustadas por usuario - radios 200 m')
root=p.layerTreeRoot();cameras=root.addGroup('Camaras ajustadas - 183');radios=root.addGroup('Radios de influencia potencial - 200 m');context=root.addGroup('Contexto')
def layer(name,title,group,subset=''):
 l=QgsVectorLayer(str(gp)+'|layername='+name,title,'ogr');assert l.isValid(),title
 if subset:l.setSubsetString(subset)
 p.addMapLayer(l,False);group.addLayer(l);return l
for name,title,color,subset in [('CAMARAS_EXISTENTES_103_FINAL','Actuales sin cambio - 73','#2673ba','"REQUIERE_CAMBIO" = 0'),('CAMARAS_EXISTENTES_103_FINAL','Recambios del inventario - 30','#c47a17','"REQUIERE_CAMBIO" = 1'),('PROPUESTA_MUNICIPAL_50_FINAL','Municipales - 50','#168566',''),('PROPUESTA_POLICIA_30_FINAL','Policia - 30','#813eb3','')]:
 l=layer(name,title,cameras,subset);l.renderer().setSymbol(QgsMarkerSymbol.createSimple({'name':'circle','color':color,'outline_color':'white','outline_width':'.3','size':'3.2'}))
for name,title,color in [('RADIOS_EXISTENTES_SIMBOLOGIA_200M','Radios existentes 103','#2673ba'),('RADIOS_MUNICIPALES_200M','Radios municipales 50','#168566'),('RADIOS_POLICIA_200M','Radios Policia 30','#813eb3')]:
 l=layer(name,title,radios);l.renderer().setSymbol(QgsFillSymbol.createSimple({'color':color,'outline_color':color,'outline_width':'.15'}));l.setOpacity(.15)
axes=layer('CORREDORES','Ejes urbanos',context);axes.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color':'#d54835','line_width':'.6'}))
platforms=layer('PLATAFORMAS_TERRITORIALES','Plataformas',context);platforms.renderer().setSymbol(QgsFillSymbol.createSimple({'color':'0,0,0,0','outline_color':'#596d79','outline_width':'.3'}))
upc=layer('UPC_INFRAESTRUCTURA','Infraestructura policial - 18 UPC',context);root.findLayer(upc.id()).setItemVisibilityChecked(False)
p.viewSettings().setDefaultViewExtent(__import__('qgis.core',fromlist=['QgsReferencedRectangle']).QgsReferencedRectangle(platforms.extent(),p.crs()))
assert p.write();assert all(l.isValid() for l in p.mapLayers().values());print('QGIS_AJUSTADO',len(p.mapLayers()),'capas validas',flush=True);os._exit(0)
