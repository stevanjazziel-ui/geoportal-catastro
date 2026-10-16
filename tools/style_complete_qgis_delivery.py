"""Append numerical rasters to the GeoPackage and create a portable, styled QGIS project."""
import json
import os
import sqlite3
import zipfile
from pathlib import Path

os.environ['QT_QPA_PLATFORM']='offscreen'
import numpy as np
from osgeo import gdal,osr
from qgis.core import (QgsApplication,QgsProject,QgsVectorLayer,QgsRasterLayer,QgsMarkerSymbol,
    QgsFillSymbol,QgsLineSymbol,QgsCategorizedSymbolRenderer,QgsRendererCategory,QgsRasterShader,
    QgsColorRampShader,QgsSingleBandPseudoColorRenderer,QgsMapSettings,QgsMapRendererParallelJob,
    QgsCoordinateReferenceSystem,QgsCoordinateTransform,QgsSingleSymbolRenderer,Qgis)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import QSize

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent/'entregas/VISOR_RIOBAMBA_QGIS_20261016'
PACKAGE=OUT/'VISOR_RIOBAMBA_COMPLETO.gpkg'


def main():
    app=QgsApplication([],False);app.initQgis();gdal.UseExceptions()
    metadata=json.loads((OUT/'MANIFIESTO.json').read_text(encoding='utf-8'))
    # Native GDAL copying retains the municipal road source's Z and M ordinates.
    source=ROOT.parent/'riobamba_matrix_review_20260921/cartografia_base/RIOBAMBA_Cartografia Base.gdb'
    translated=gdal.VectorTranslate(str(PACKAGE),str(source),options=gdal.VectorTranslateOptions(
        format='GPKG',accessMode='overwrite',layers=['Vialidad_urbana'],layerName='RED_VIAL_MUNICIPAL',dstSRS='EPSG:32717'))
    assert translated is not None
    translated=None
    raster_names=[]
    for spec in metadata['rasters']:
        cached=OUT/(spec['name']+'.npz')
        if cached.exists():
            with np.load(cached) as arrays:
                data=np.where(arrays['valid'],arrays['density'],-9999).astype(np.float32)
        else:
            completed=gdal.Open('GPKG:'+str(PACKAGE)+':'+spec['name'])
            assert completed is not None,spec['name']
            data=completed.GetRasterBand(1).ReadAsArray();completed=None
        memory=gdal.GetDriverByName('MEM').Create('',spec['width'],spec['height'],1,gdal.GDT_Float32)
        memory.SetGeoTransform([spec['west'],spec['cellSize'],0,spec['north'],0,-spec['cellSize']])
        srs=osr.SpatialReference();srs.ImportFromEPSG(32717);memory.SetProjection(srs.ExportToWkt())
        memory.GetRasterBand(1).WriteArray(data);memory.GetRasterBand(1).SetNoDataValue(-9999)
        with sqlite3.connect(PACKAGE) as db:
            exists=db.execute('SELECT COUNT(*) FROM gpkg_contents WHERE table_name=?',(spec['name'],)).fetchone()[0]
        if not exists:
            result=gdal.Translate(str(PACKAGE),memory,format='GPKG',creationOptions=[
                'APPEND_SUBDATASET=YES','RASTER_TABLE='+spec['name'],'RASTER_IDENTIFIER='+spec['name'],'TILE_FORMAT=TIFF'])
            assert result is not None,spec['name'];result=None
        memory=None
        dataset=gdal.Open('GPKG:'+str(PACKAGE)+':'+spec['name'])
        assert dataset and dataset.RasterXSize==spec['width'] and dataset.RasterYSize==spec['height']
        assert np.allclose(dataset.GetRasterBand(1).ReadAsArray(),data,rtol=1e-6,atol=1e-5),spec['name']
        dataset=None;raster_names.append(spec['name'])
    project=QgsProject.instance();project.setCrs(QgsCoordinateReferenceSystem('EPSG:32717'))
    project.setTitle('Visor de Seguridad Ciudadana Riobamba - entrega GIS completa')
    project.setFilePathStorage(Qgis.FilePathType.Relative)
    root=project.layerTreeRoot()
    groups={name:root.addGroup(name) for name in ['Camaras','Radios potenciales','Corredores','Hot Spots Gi*','Concentracion KDE','Manzanas y cobertura','Limites y referencias','Tablas']}
    db=sqlite3.connect(PACKAGE)
    contents=db.execute('SELECT table_name,data_type,srs_id FROM gpkg_contents').fetchall();db.close()
    layers={};invalid=[]
    colors={'existing':'#246db5','change':'#8b46b5','municipal':'#18815b','police':'#e8bd16'}
    def symbol(color,polygon=False):
        return QgsFillSymbol.createSimple({'color':QColor(color).name()+',35','outline_color':color,'outline_width':'0.25'}) if polygon else QgsMarkerSymbol.createSimple({'name':'circle','color':color,'outline_color':'white','outline_width':'0.3','size':'2.8'})
    for name,kind,srs in contents:
        if name in raster_names:continue
        layer=QgsVectorLayer(str(PACKAGE)+'|layername='+name,name,'ogr')
        if not layer.isValid():invalid.append(name);continue
        layers[name]=layer
        default=False;group='Limites y referencias'
        point_camera=('CAMARAS_EXISTENTES_103_FINAL','PROPUESTA_MUNICIPAL_50_FINAL','PROPUESTA_POLICIA_30_FINAL')
        if name in point_camera or name.startswith(('EXISTENTES_PARA','EXISTENTES_SIN','MUNICIPALES_URBANAS','MUNICIPALES_RURALES','MUNICIPALES_LAS_ABRAS')):
            group='Camaras';default=name in point_camera
            color=colors['police'] if 'POLICIA' in name else colors['municipal'] if 'MUNICIPAL' in name else colors['change'] if 'PARA_CAMBIO' in name else colors['existing']
            layer.setRenderer(QgsSingleSymbolRenderer(symbol(color)))
            if name=='CAMARAS_EXISTENTES_103_FINAL':
                layer.setRenderer(QgsCategorizedSymbolRenderer('REQUIERE_CAMBIO',[
                    QgsRendererCategory(0,symbol(colors['existing']),'Sin cambio requerido (73)'),
                    QgsRendererCategory(1,symbol(colors['change']),'Para cambio, incluidas en las103 (30)')]))
        elif name.startswith('RADIOS_'):
            group='Radios potenciales';default=name in ['RADIOS_EXISTENTES_200M','RADIOS_MUNICIPALES_200M','RADIOS_POLICIA_200M']
            color=colors['police'] if 'POLICIA' in name else colors['municipal'] if 'MUNICIPAL' in name else colors['existing']
            def fill(c):
                s=QgsFillSymbol.createSimple({'color':c,'outline_color':c,'outline_width':'0.2'});s.setOpacity(.20);return s
            if name=='RADIOS_EXISTENTES_200M':
                layer.setRenderer(QgsCategorizedSymbolRenderer('REQUIERE_CAMBIO',[QgsRendererCategory(0,fill(colors['existing']),'Radio sin cambio'),QgsRendererCategory(1,fill(colors['change']),'Radio para cambio')]))
            else:layer.setRenderer(QgsSingleSymbolRenderer(fill(color)))
        elif name in ['BOULEVARD_MACAJI_BELLAVISTA','ANILLO_VIAL','CICLOVIAS','QUEBRADA_LAS_ABRAS']:
            group='Corredores';default=True
            color={'BOULEVARD_MACAJI_BELLAVISTA':'#297d55','ANILLO_VIAL':'#a564ad','CICLOVIAS':'#246db5','QUEBRADA_LAS_ABRAS':'#16a1b2'}[name]
            layer.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({'line_color':color,'line_width':'0.8'})))
        elif name.startswith(('GI_','HOTSPOT')):
            group='Hot Spots Gi*'
            if layer.fields().indexFromName('GI_CLASS')>=0:
                values=sorted({str(f['GI_CLASS']) for f in layer.getFeatures()});categories=[]
                for value in values:
                    color='#bd0026' if value.startswith('HOTSPOT') and '99' in value else '#fd8d3c' if value.startswith('HOTSPOT') and '95' in value else '#fed976' if value.startswith('HOTSPOT') else 'transparent'
                    categories.append(QgsRendererCategory(value,QgsFillSymbol.createSimple({'color':color,'outline_style':'no'}),value))
                layer.setRenderer(QgsCategorizedSymbolRenderer('GI_CLASS',categories))
                layer.setOpacity(.65)
        elif name.startswith(('MANZANAS','COBERTURA_','BRECHA_','AREAS_')):
            group='Manzanas y cobertura'
            if layer.geometryType()==Qgis.GeometryType.Polygon:
                layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({'color':'transparent','outline_color':'#74878f','outline_width':'0.2'})))
        elif layer.geometryType()==Qgis.GeometryType.Null:group='Tablas'
        elif name in ['PLATAFORMAS_TERRITORIALES','LIMITE_CANTONAL','PARROQUIAS_CANTONALES']:
            default=name in ['PLATAFORMAS_TERRITORIALES','LIMITE_CANTONAL']
            layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple({'color':'transparent','outline_color':'#263c38','outline_width':'0.4'})))
        project.addMapLayer(layer,False);node=groups[group].addLayer(layer);node.setItemVisibilityChecked(default)
        layer.saveDefaultStyle()
    for spec in metadata['rasters']:
        name=spec['name'];layer=QgsRasterLayer('GPKG:'+str(PACKAGE)+':'+name,name,'gdal')
        assert layer.isValid(),name
        shader=QgsRasterShader();ramp=QgsColorRampShader();ramp.setColorRampType(QgsColorRampShader.Interpolated)
        palette=['#ffffb2','#fed976','#feb24c','#fd8d3c','#f03b20','#bd0026'];alpha=[0,65,115,165,200,215]
        items=[]
        for value,color,opacity in zip(spec['thresholds'],palette,alpha):
            c=QColor(color);c.setAlpha(opacity);items.append(QgsColorRampShader.ColorRampItem(value,c,str(round(value,2))))
        ramp.setColorRampItemList(items);shader.setRasterShaderFunction(ramp)
        layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(),1,shader))
        project.addMapLayer(layer,False);node=groups['Concentracion KDE'].addLayer(layer);node.setItemVisibilityChecked(name=='KDE_URBANO_TODOS')
        layer.saveDefaultStyle();layers[name]=layer
    # The project retains an optional online reference, not an offline tile download.
    osm=QgsRasterLayer('type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0','OpenStreetMap (requiere Internet)','wms')
    project.addMapLayer(osm,False);root.addLayer(osm).setItemVisibilityChecked(False)
    assert not invalid,invalid
    project.viewSettings().setDefaultViewExtent(__import__('qgis.core',fromlist=['QgsReferencedRectangle']).QgsReferencedRectangle(layers['LIMITE_CANTONAL'].extent(),project.crs()))
    filename=OUT/'VISOR_RIOBAMBA.qgz'
    if not project.write(str(filename)):
        plain=OUT/'VISOR_RIOBAMBA.qgs'
        if not project.write(str(plain)):
            raise RuntimeError('No se pudo guardar proyecto QGIS: '+project.error())
        with zipfile.ZipFile(filename,'w',zipfile.ZIP_DEFLATED) as archive:archive.write(plain,plain.name)
    for scope,extent in [('CANTONAL',layers['LIMITE_CANTONAL'].extent()),('URBANO',layers['PLATAFORMAS_TERRITORIALES'].extent())]:
        settings=QgsMapSettings();settings.setDestinationCrs(project.crs());settings.setExtent(extent);settings.setOutputSize(QSize(1400,1000));settings.setBackgroundColor(QColor('#f1f4f5'))
        visible=[node.layer() for node in root.findLayers() if node.isVisible() and node.layer()!=osm and node.layer().isSpatial()]
        settings.setLayers(visible);job=QgsMapRendererParallelJob(settings);job.start();job.waitForFinished()
        assert job.renderedImage().save(str(OUT/('MAPA_'+scope+'.png')))
    for spec in metadata['rasters']:(OUT/(spec['name']+'.npz')).unlink(missing_ok=True)
    document=['# Visor de Riobamba: entrega QGIS completa','',
        'Abrir VISOR_RIOBAMBA.qgz para conservar grupos, simbologia y mapas. El GeoPackage puede abrirse por separado.',
        'CRS metrico: EPSG:32717. Radios100/150/200m; no diametros. Todos los campos se conservan.',
        '103 existentes (30 para cambio incluidas),50 municipales (24urbanas,22rurales,4Las Abras),30 policiales.',
        'MUN-037 Junin x Puruha es excepcion local aprobada para Macaji100. Anillo sin minimo.',
        'Los rasters KDE numericos se alojan dentro del GeoPackage; no son Gi*. Gi* mantiene z,p y significancia originales.',
        'Los colores y radios son cobertura potencial: no certifican vision a traves de manzanas, curvas ni esquinas.',
        'OSM es una capa opcional online. No se incluyen mosaicos satelitales offline ni se inventan imagenes.',
        'Los cambios editados en esta copia QGIS no se publican automaticamente en el visor.',
        '', '## Capas y campos','']
    for layer in metadata['layers']:
        if 'records' not in layer:continue
        document.extend(['### '+layer['name'],f"Fuente: {layer['source']}",f"CRS: {layer['crs'] or 'Tabla sin geometria'}. Registros: {layer['records']}.",layer.get('description',''),
            'Campos: '+', '.join(f"{f['name']} ({f['type']})" for f in layer['fields']), ''])
    document += ['## Rasters KDE','']+[f"- {r['name']}: {r['width']}x{r['height']} celdas de{r['cellSize']}m; bandwidth{r['bandwidthM']}m; {r['records']} registros; EPSG:32717; NoData=-9999." for r in metadata['rasters']]
    (OUT/'README.md').write_text('\n'.join(document)+'\n',encoding='utf-8')
    with sqlite3.connect(PACKAGE) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        styles=db.execute('SELECT COUNT(*) FROM layer_styles').fetchone()[0]
    check={'gpkgIntegrity':'ok','invalidLayers':invalid,'rasterValuesVerified':len(raster_names),'savedStyles':styles,'qgisProjectWritten':True,
        'vectorTables':len(metadata['layers'])-1,'gpkgMB':PACKAGE.stat().st_size/1e6}
    (OUT/'VALIDACION_QGIS.json').write_text(json.dumps(check,indent=2),encoding='utf-8')
    archive=OUT.parent/(OUT.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(OUT.iterdir()):
            if path.is_file() and not path.name.endswith('~'):zipped.write(path,OUT.name+'/'+path.name)
    print(json.dumps({**check,'zip':str(archive),'zipMB':archive.stat().st_size/1e6}),flush=True)
    # Avoid QGIS/GDAL interpreter teardown ordering issues on Windows.
    os._exit(0)


if __name__=='__main__':main()
