'use strict';
(async()=>{
 const C=window.Cesium;
 const byId=id=>document.getElementById(id);
 const root='data/shobol/';
 const published=location.hostname==='stevanjazziel-ui.github.io';
 const repository='https://raw.githubusercontent.com/stevanjazziel-ui/geoportal-catastro/main/shobol-llinllin/';
 const largeAssets=new Set(['drenaje_d8.geojson','nube-sfm.json','tileset.json','superficie-fotogrametrica-parcial.glb']);
 const assetUrl=file=>(published&&(file.startsWith('photos/')||largeAssets.has(file))?repository:'')+root+file;
 const number=(n,d=1)=>Number(n).toLocaleString('es-EC',{maximumFractionDigits:d});
 const colors={capturas:'#f5d97e','orientacion-laser':'#8d8dc9',huellas_foto:'#e9cc8a',evidencias:'#f6954d',
  microcuencas:'#8cd7ba',drenaje_d8:'#78c9eb',referencias:'#ccbaf1',edificios_osm:'#d3c7a8',construcciones_3d:'#d8c9af',
  hidrografia_osm:'#4db4f0',vias_osm:'#d7cb99',puentes_osm:'#e9ac80',areas_interpretadas:'#e6a259',
  perfiles:'#c5eca6'};
 const depthScale=[[.05,'#eac17e','5–20 cm'],[.2,'#cf8846','20–50 cm'],[.5,'#91492e','50 cm o más']];
 const speedScale=[[.01,'#cce8d4','< 0,3 m/s'],[.3,'#58aa9c','0,3–1 m/s'],[1,'#225d67','1 m/s o más']];
 const debrisScale=[[.15,'#f5c483','15–50 cm'],[.5,'#e27642','50 cm–1 m'],[1,'#a43921','1 m o más']];
 const defaultLayers=new Set(['areas_interpretadas','edificios_osm','hidrografia_osm']);
 const photoLayers=new Set(['capturas','evidencias']);
 const routeStops=[
  {photo:'0003',label:'Quebrada',heading:255,range:740,
   summary:'Se distingue una franja oscura en el fondo de la quebrada.'},
  {photo:'0007',label:'Parcelas',heading:250,range:700,
   summary:'La franja se ensancha al salir de la quebrada y llega a terrenos agrícolas.'},
  {photo:'0028',label:'Vías y viviendas',heading:265,range:650,
   summary:'La huella pasa cerca de caminos y viviendas. El cruce de la foto está por identificar.'},
  {photo:'0033',label:'Tramo bajo',heading:285,range:800,
   summary:'Una superficie más ancha en las parcelas podría corresponder a material depositado.'},
 ];
 const routeSegments=[
  ['0043','0003','0002','0005','0006','0007','0008'],
  ['0025','0027','0029','0036','0030','0031','0034','0032','0033'],
 ];
 const cache=new Map();
 let caseToken=0,requestedCase='',active=null,frame=0,player=null,tourTimer=null,selectedPhoto=null,layerError=false;
 let debrisMeta, priorFootprintVisibility;
 const layerObjects=new Map();
 const evidenceByPhoto=new Map();

 async function payload(file,Type){
  const response=await fetch(assetUrl(file));
  if(!response.ok)throw Error('No se pudo cargar '+file);
  if(!Type)return response.json();
  const stream=response.body.pipeThrough(new DecompressionStream('gzip'));
  return new Type(await new Response(stream).arrayBuffer());
 }
 function coordinateIndex(meta,lon,lat){
  const [w,s,e,n]=meta.bbox;
  return [(lon-w)/(e-w)*meta.cols-.5,(n-lat)/(n-s)*meta.rows-.5];
 }
 function sampler(meta,heights){
  return (lon,lat)=>{
   let [x,y]=coordinateIndex(meta,lon,lat);
   if(x<-.5||y<-.5||x>meta.cols-.5||y>meta.rows-.5)return 0;
   x=Math.max(0,Math.min(meta.cols-1,x));
   y=Math.max(0,Math.min(meta.rows-1,y));
   const j=Math.min(meta.cols-2,Math.floor(x)),i=Math.min(meta.rows-2,Math.floor(y));
   const dx=x-j,dy=y-i,k=i*meta.cols+j;
   return ((1-dx)*heights[k]+dx*heights[k+1])*(1-dy)+
          ((1-dx)*heights[k+meta.cols]+dx*heights[k+meta.cols+1])*dy;
  };
 }
 function localTerrain(meta,elevation){
  const scheme=new C.GeographicTilingScheme();
  return new C.CustomHeightmapTerrainProvider({width:64,height:64,tilingScheme:scheme,
   credit:'Relieve Copernicus GLO-30 © DLR/Airbus · UE/ESA',
   callback:(x,y,level)=>{
    const rect=scheme.tileXYToRectangle(x,y,level),heights=new Float32Array(4096);
    const west=C.Math.toDegrees(rect.west),east=C.Math.toDegrees(rect.east),
          north=C.Math.toDegrees(rect.north),south=C.Math.toDegrees(rect.south);
    for(let row=0;row<64;row++)for(let col=0;col<64;col++){
     heights[row*64+col]=elevation(west+(east-west)*col/63,north+(south-north)*row/63);
    }
    return heights;
   }});
 }
 function reliefLighting(meta,heights){
  const {rows,cols,bbox}=meta;
  const [west,south,east,north]=bbox;
  const latitude=C.Math.toRadians((south+north)/2);
  const dx=111320*Math.cos(latitude)*(east-west)/cols;
  const dy=111130*(north-south)/rows;
  const sun=C.Cartesian3.normalize(new C.Cartesian3(-.55,.28,.79),new C.Cartesian3());
  const canvas=document.createElement('canvas');
  canvas.width=cols;canvas.height=rows;
  const paint=canvas.getContext('2d');
  const pixels=paint.createImageData(cols,rows);
  for(let y=1;y<rows-1;y++){
   for(let x=1;x<cols-1;x++){
    const i=y*cols+x;
    const slopeX=(heights[i+1]-heights[i-1])/(2*dx);
    const slopeY=(heights[i-cols]-heights[i+cols])/(2*dy);
    const incidence=(-sun.x*slopeX-sun.y*slopeY+sun.z)/Math.hypot(slopeX,slopeY,1)-sun.z;
    const fade=Math.min(1,Math.min(x,y,cols-1-x,rows-1-y)/12);
    const shadow=incidence<0;
    const opacity=fade*Math.min(.30,Math.abs(incidence)*(shadow?.62:.65));
    const offset=i*4;
    pixels.data[offset]=shadow?28:244;
    pixels.data[offset+1]=shadow?35:232;
    pixels.data[offset+2]=shadow?36:196;
    pixels.data[offset+3]=Math.round(255*opacity);
   }
  }
  paint.putImageData(pixels,0,0);
  return canvas;
 }
 function color(str){return C.Color.fromCssColorString(str);}
 function hexRgb(value){return [1,3,5].map(i=>parseInt(value.slice(i,i+2),16));}
 function timeText(caseData,minute){
  const date=new Date(Date.parse(caseData.start_local)+minute*60000);
  return new Intl.DateTimeFormat('es-EC',{timeZone:'America/Guayaquil',hour:'2-digit',minute:'2-digit',
   hourCycle:'h23',day:'numeric',month:'short'}).format(date);
 }
 function elapsed(seconds){
  const minutes=Math.floor(seconds/60);
  return minutes+' min '+String(seconds%60).padStart(2,'0')+' s';
 }

 try{
  const manifest=await payload('manifest.json');
  const buildings=manifest.layers.construcciones_3d;
  if(buildings){
   defaultLayers.delete('edificios_osm');
   defaultLayers.add('construcciones_3d');
  }
  const elevations=await payload(manifest.terrain.file,Float32Array);
  if(elevations.length!==manifest.terrain.rows*manifest.terrain.cols)throw Error('Terreno incompleto');
  const elevation=sampler(manifest.terrain,elevations);
  const satelliteFallback=new C.UrlTemplateImageryProvider({
   url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
   maximumLevel:16,credit:'Imagen de respaldo © Esri y proveedores'});
  const context=manifest.context_imagery;
  const contextProvider=context?await C.SingleTileImageryProvider.fromUrl(assetUrl(context.file),{
   rectangle:C.Rectangle.fromDegrees(...context.bbox),
   credit:'Contiene datos modificados de Copernicus Sentinel-2 (2020)',
  }).catch(()=>null):null;
  let globeBase=satelliteFallback;
  if(contextProvider){
   // A global base prevents a local context image from stretching at its borders.
   const baseCanvas=document.createElement('canvas');
   baseCanvas.width=baseCanvas.height=2;
   const basePaint=baseCanvas.getContext('2d');
   basePaint.fillStyle='#465044';
   basePaint.fillRect(0,0,2,2);
   globeBase=await C.SingleTileImageryProvider.fromUrl(baseCanvas.toDataURL());
  }
  const viewer=new C.Viewer('viewer',{terrainProvider:localTerrain(manifest.terrain,elevation),
   baseLayer:new C.ImageryLayer(globeBase),animation:false,timeline:false,
   geocoder:false,homeButton:false,sceneModePicker:false,navigationHelpButton:false,
   baseLayerPicker:false,selectionIndicator:false,infoBox:false,fullscreenButton:false,
   requestRenderMode:true,maximumRenderTimeChange:Infinity});
  if(contextProvider)viewer.imageryLayers.addImageryProvider(contextProvider);
  const satellite=contextProvider?viewer.imageryLayers.addImageryProvider(satelliteFallback):viewer.imageryLayers.get(0);
  const gradeImagery=layer=>{
   layer.saturation=.94;
   layer.contrast=1.045;
   layer.brightness=1.025;
  };
  gradeImagery(satellite);
  viewer.scene.globe.depthTestAgainstTerrain=true;
  viewer.scene.globe.maximumScreenSpaceError=2;
  viewer.scene.backgroundColor=color('#384a43');
  viewer.scene.screenSpaceCameraController.minimumZoomDistance=25;
  viewer.cesiumWidget.creditDisplay.addStaticCredit(new C.Credit(
   '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap colaboradores · ODbL</a>',true));
  let reliefLayer,buildingShadows;
  const orderSurfaceLayers=()=>{
   if(reliefLayer)viewer.imageryLayers.raiseToTop(reliefLayer);
   if(buildingShadows)viewer.imageryLayers.raiseToTop(buildingShadows);
  };
  void EcuadorImagery.connect(viewer,C).then(layer=>{
   if(layer)gradeImagery(layer);
   orderSurfaceLayers();
  });
  const shading=reliefLighting(manifest.terrain,elevations);
  void C.SingleTileImageryProvider.fromUrl(shading.toDataURL(),{
   rectangle:C.Rectangle.fromDegrees(...manifest.terrain.bbox)
  }).then(provider=>{
   reliefLayer=viewer.imageryLayers.addImageryProvider(provider);
   orderSurfaceLayers();
   viewer.scene.requestRender();
  }).catch(error=>console.warn('Sombreado del relieve',error));
  const overlayCanvas=document.createElement('canvas');
  const paint=overlayCanvas.getContext('2d');
  let overlay;
  let reconstruction;
  let routeLayer;
  const routeButtons=[];

  function look(lon,lat,heading,pitch,range){
   const center=C.Cartesian3.fromDegrees(lon,lat,elevation(lon,lat)+15);
   viewer.camera.lookAt(center,new C.HeadingPitchRange(C.Math.toRadians(heading),C.Math.toRadians(pitch),range));
   viewer.camera.lookAtTransform(C.Matrix4.IDENTITY);
   viewer.scene.requestRender();
  }
  function haltTour(){
   clearTimeout(tourTimer);
   tourTimer=null;
   byId('tour').textContent='Recorrido con fotos';
   if(viewer.camera.cancelFlight)viewer.camera.cancelFlight();
  }
  function clearRouteStop(){
   byId('routeFrame').hidden=true;
   for(const button of routeButtons)button.setAttribute('aria-pressed','false');
  }
  function home(){
   haltTour();
   clearRouteStop();
   look(-78.8025,-1.598,255,-47,3850);
  }
  if(buildings){
   byId('buildingsDetails').hidden=false;
   const summary=buildings.summary;
   const measured=summary.height_sources['Relieve de inspección']||0;
   const satellite=summary.height_sources['Google Open Buildings 2.5D de 2023']||0;
   const indicative=summary.height_sources['Altura de referencia']||0;
   byId('buildingSummary').textContent=number(summary.total,0)+' construcciones en el corredor. '+
    (measured?number(measured,0)+' alturas estimadas con el levantamiento. ':'')+
    (satellite?number(satellite,0)+' estimaciones satelitales. ':'')+
    (indicative?number(indicative,0)+' volúmenes con altura referencial de 3,2 m. ':'')+
    'Los acabados de fachada y cubierta son aproximados.';
   byId('buildingFocus').onclick=()=>{
    haltTour();
    clearRouteStop();
    look(-78.7985,-1.5991,250,-36,490);
   };
   viewer.cesiumWidget.creditDisplay.addStaticCredit(new C.Credit(
    '<a href="https://github.com/microsoft/GlobalMLBuildingFootprints" target="_blank" rel="noopener">Microsoft Global ML Building Footprints</a>',true));
   if(satellite)viewer.cesiumWidget.creditDisplay.addStaticCredit(new C.Credit(
    '<a href="https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1" target="_blank" rel="noopener">Google Open Buildings 2.5D (CC BY 4.0)</a>',true));
  }
  const tourPath=[
    [-78.805,-1.5977,254,-51,3800],[-78.8117,-1.5976,270,-40,1250],
    [-78.8071,-1.5974,255,-37,1130],[-78.8026,-1.5969,255,-46,1030],
    [-78.7992,-1.5984,263,-43,900],[-78.7967,-1.5998,290,-42,1100],
    [-78.8007,-1.5986,255,-52,3150],
  ];
  function tourFrame(progress){
   const i=Math.min(tourPath.length-2,Math.floor(progress*(tourPath.length-1)));
   const u=progress*(tourPath.length-1)-i;
   const t=u*u*(3-2*u);
   look(...tourPath[i].map((from,j)=>from+(tourPath[i+1][j]-from)*t));
  }
  function showRouteStop(index){
   reconstruction?.stopReconstruction();
   if(requestedCase){
    byId('case').value='';
    void chooseCase();
   }
   const stop=routeStops[index];
   const [lon,lat]=evidenceByPhoto.get(stop.photo);
   const item=photoRecords.get(stop.photo);
   selectPhoto(stop.photo);
   byId('routePhoto').src=assetUrl(item.thumbnail);
   byId('routePhoto').alt=item.interpretation;
   byId('routePlace').textContent=(index+1)+' de '+routeStops.length+' · '+stop.label;
   byId('routeSummary').textContent=stop.summary;
   byId('routeFrame').hidden=false;
   routeButtons.forEach((button,i)=>button.setAttribute('aria-pressed',String(i===index)));
   const target=C.Cartesian3.fromDegrees(lon,lat,elevation(lon,lat)+14);
   viewer.camera.flyToBoundingSphere(new C.BoundingSphere(target,1),{
    offset:new C.HeadingPitchRange(C.Math.toRadians(stop.heading),C.Math.toRadians(-51),stop.range),
    duration:1.5,
   });
  }
  function flyTour(){
   showRouteStop(0);
   byId('tour').textContent='Detener recorrido';
   let index=0;
   const advance=()=>{
    if(++index===routeStops.length){haltTour();return;}
    showRouteStop(index);
    tourTimer=setTimeout(advance,6500);
   };
   tourTimer=setTimeout(advance,6500);
  }
  byId('home').onclick=home;
  byId('tour').onclick=()=>tourTimer?haltTour():flyTour();
  home();
  byId('loading').hidden=true;

  async function activateLayer(key,on,preload=false){
   let object=layerObjects.get(key);
   if((on||preload)&&!object){
    const item=manifest.layers[key];
    const data=await payload(item.file);
    const tint=color(colors[key]);
    if(key==='capturas'||key==='evidencias'||key==='referencias'||key==='orientacion-laser'){
     object=new C.CustomDataSource(item.label);
     for(const entry of data.features){
      const [lon,lat]=entry.geometry.coordinates;
      const props=entry.properties;
      if(key==='evidencias')evidenceByPhoto.set(props.photo,[lon,lat]);
      object.entities.add({id:key+'-'+(props.photo||props.id),name:props.type||item.label,
       properties:{photo:props.photo},position:C.Cartesian3.fromDegrees(lon,lat,elevation(lon,lat)+(key==='capturas'?25:0)),
       point:{pixelSize:key==='referencias'?7:9,color:tint,outlineColor:C.Color.BLACK,outlineWidth:1.3,
        heightReference:key==='capturas'?C.HeightReference.NONE:C.HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance:900}});
      if(key==='capturas'){
       photoRecords.set(props.photo,props);
       byId('photo').add(new Option('Foto '+props.photo+' · '+props.interpretation,props.photo));
      }
     }
     await viewer.dataSources.add(object);
     if(key==='capturas')byId('photo').disabled=false;
    }else if(key==='construcciones_3d'){
     object=viewer.scene.primitives.add(window.createShobolBuildings(C,data,elevation));
     const projection=window.projectShobolBuildingShadows(data);
     if(projection){
      const provider=await C.SingleTileImageryProvider.fromUrl(projection.canvas.toDataURL(),{
       rectangle:C.Rectangle.fromDegrees(...projection.bounds)
      }).catch(()=>null);
      if(provider){
       buildingShadows=viewer.imageryLayers.addImageryProvider(provider);
       orderSurfaceLayers();
      }
     }
    }else{
     object=await C.GeoJsonDataSource.load(data,{clampToGround:true,stroke:tint,strokeWidth:key==='puentes_osm'?4:2,
      fill:tint.withAlpha(key==='edificios_osm'?.9:.15)});
     if(key==='areas_interpretadas'){
      for(const e of object.entities.values){
       if(!e.polygon)continue;
       const soil=e.properties.label.getValue()==='Sector de suelo desnudo con bancos';
       e.polygon.material=color(soil?'#a9aaa1':'#e58251').withAlpha(soil?.16:.45);
      }
     }
     if(key==='edificios_osm'){
      for(const e of object.entities.values){
       if(!e.polygon)continue;
       const levels=Number(e.properties?.levels?.getValue());
       e.polygon.height=0;
       e.polygon.heightReference=C.HeightReference.CLAMP_TO_GROUND;
       e.polygon.extrudedHeight=levels>0&&levels<15?3*levels:3;
       e.polygon.extrudedHeightReference=C.HeightReference.RELATIVE_TO_GROUND;
      }
     }
     await viewer.dataSources.add(object);
    }
    layerObjects.set(key,object);
   }
   if(object){
    object.show=on;
    if(key==='construcciones_3d'&&buildingShadows)buildingShadows.show=on;
    viewer.scene.requestRender();
   }
  }
  const photoRecords=new Map();
  const initialLayers=[];
  for(const [key,item] of Object.entries(manifest.layers)){
   if(buildings&&key==='edificios_osm')continue;
   const label=document.createElement('label');
   const input=document.createElement('input');
   input.type='checkbox';
   input.dataset.layer=key;
   input.checked=defaultLayers.has(key);
   label.append(input,item.label);
   byId('layers').append(label);
   const update=(preload=false)=>activateLayer(key,input.checked,preload).catch(error=>{
    layerError=true;input.checked=false;console.warn(error);label.title=error.message;
   });
   input.onchange=()=>update();
   if(input.checked||photoLayers.has(key))initialLayers.push(update(true));
  }
  let surveyMesh;
  if(manifest.mesh){
   const label=document.createElement('label'),input=document.createElement('input');
   input.type='checkbox';
   input.id='surveyMesh';
   label.append(input,'Superficie fotogramétrica parcial');
   byId('layers').append(label);
   input.onchange=async()=>{
    try{
     if(input.checked&&!surveyMesh){
      input.disabled=true;
      surveyMesh=await C.Cesium3DTileset.fromUrl(assetUrl(manifest.mesh.tileset),{maximumScreenSpaceError:12});
      viewer.scene.primitives.add(surveyMesh);
     }
     if(surveyMesh)surveyMesh.show=input.checked;
     viewer.scene.requestRender();
    }catch(error){
     label.title=error.message;
     input.checked=false;
    }finally{input.disabled=false;}
   };
  }
  if(manifest.point_cloud){
   const title=document.createElement('label'),input=document.createElement('input');
   input.type='checkbox';
   title.append(input,manifest.point_cloud.dense?'Nube densa fotogramétrica':'Nube fotogramétrica parcial');
   byId('layers').append(title);
   let points;
   input.onchange=async()=>{
    if(input.checked&&!points){
     const rows=await payload(manifest.point_cloud.file);
     points=viewer.scene.primitives.add(new C.PointPrimitiveCollection());
     for(const [lon,lat,z,r,g,b] of rows){
      points.add({position:C.Cartesian3.fromDegrees(lon,lat,z),color:C.Color.fromBytes(r,g,b),pixelSize:2.6});
     }
    }
    if(points)points.show=input.checked;
    viewer.scene.requestRender();
   };
  }
  function selectPhoto(id){
   const item=photoRecords.get(id);
   selectedPhoto=item||null;
   byId('photoDetail').hidden=!item;
   if(!item)return;
   byId('photo').value=id;
   byId('photoImage').src=assetUrl(item.thumbnail);
   byId('photoImage').alt=item.interpretation;
   byId('photoText').textContent=item.interpretation+'. '+item.observations+' Captura '+item.datetime_local.slice(11,19)+
    ' · inclinación '+number(item.camera_pitch_deg)+'° · '+item.sensor_width_px+' × '+item.sensor_height_px+' px.';
  }
  byId('photo').onchange=()=>selectPhoto(byId('photo').value);
  byId('focusPhoto').onclick=()=>{
   if(!selectedPhoto)return;
   haltTour();
   const [lon,lat]=evidenceByPhoto.get(selectedPhoto.photo)||[selectedPhoto.laser_lon??selectedPhoto.lon,
                                                           selectedPhoto.laser_lat??selectedPhoto.lat];
   look(lon,lat,selectedPhoto.camera_yaw_deg,-37,500);
  };
  for(const item of manifest.cases)byId('case').add(new Option(item.label,item.id));
  byId('case').disabled=false;
  function stop(){
   if(player)clearInterval(player);
   player=null;
   byId('play').textContent='Reproducir';
  }
  function mapSlice(){
   if(active.debris){
    const area=active.meta.rows*active.meta.cols;
    const selected=byId('debrisExtent').checked?active.meta.times_s.length:frame;
    return active.data.subarray(selected*area,(selected+1)*area);
   }
   const variable=byId('variable').value;
   const area=active.meta.rows*active.meta.cols,steps=active.meta.times.length;
   const index={depth:frame,speed:steps+frame,maxDepth:2*steps,maxSpeed:2*steps+1}[variable];
   return active.data.subarray(index*area,(index+1)*area);
  }
  function depthFrames(item,data){
   const area=item.rows*item.cols;
   const counts=item.times.map((_,step)=>{
    let count=0;
    const start=step*area;
    for(let i=start;i<start+area;i++)if(data[i]>=5)count++;
    return count;
   });
   const peak=counts.indexOf(Math.max(...counts));
   const first=counts.findIndex(count=>count>0);
   return {counts,peak,first};
  }
  function draw(){
   if(!active)return;
   const tag=byId('variable').value;
   const speed=tag==='speed'||tag==='maxSpeed';
   const scale=active.debris?debrisScale:speed?speedScale:depthScale;
   const width=active.meta.cols,height=active.meta.rows;
   overlayCanvas.width=width;overlayCanvas.height=height;
   const image=paint.createImageData(width,height);
   const values=mapSlice();
   const thresholds=scale.map(([x,c])=>[Math.round(x*100),hexRgb(c)]);
   for(let i=0;i<values.length;i++){
    const value=values[i];
    if(value<thresholds[0][0])continue;
    const rgb=value>=thresholds[2][0]?thresholds[2][1]:value>=thresholds[1][0]?thresholds[1][1]:thresholds[0][1];
    image.data.set([...rgb,active.debris?248:213],i*4);
   }
   paint.putImageData(image,0,0);
   const texture=active.debris&&reconstruction?reconstruction.clipModel(overlayCanvas,active.meta.bbox):overlayCanvas;
   overlay.rectangle.material=new C.ImageMaterialProperty({image:texture.toDataURL(),transparent:true});
   if(active.debris){
    byId('timeLabel').textContent=byId('debrisExtent').checked?'Alcance máximo del escenario':
     elapsed(active.meta.times_s[frame])+' desde el inicio simulado';
   }else{
    const maximum=tag.startsWith('max');
    const empty=!maximum&&!speed&&active.depth.counts[frame]===0;
    byId('timeLabel').textContent=maximum?'Máximo de la corrida':
     timeText(active.meta,active.meta.times[frame])+(empty?' · Sin agua de 5 cm o más':'');
   }
   byId('time').value=frame;
   byId('legendTitle').textContent=active.debris?'Espesor simulado del aluvión':
    speed?'Velocidad calculada':'Profundidad calculada';
   byId('scale').replaceChildren(...scale.map(([,tint,text])=>{
    const label=document.createElement('span');
    const mark=document.createElement('i');
    mark.style.background=tint;
    label.append(mark,text);
    return label;
   }));
   viewer.scene.requestRender();
  }
  async function chooseCase(id=byId('case').value){
   if(id)reconstruction?.stopReconstruction();
   stop();
   const token=++caseToken;
   const debris=id==='aluvion';
   requestedCase=id;
   const footprint=byId('layers').querySelector('[data-layer="areas_interpretadas"]');
   if(footprint){
    if(debris&&priorFootprintVisibility===undefined)priorFootprintVisibility=footprint.checked;
    if(debris||priorFootprintVisibility!==undefined){
     footprint.checked=debris?false:priorFootprintVisibility;
     const area=layerObjects.get('areas_interpretadas');
     if(area)area.show=footprint.checked;
     if(!debris)priorFootprintVisibility=undefined;
    }
   }
   if(routeLayer)routeLayer.show=!id;
   byId('routeKey').hidden=Boolean(id)||!routeLayer;
   if(id){haltTour();clearRouteStop();}
   active=null;
   if(overlay)viewer.entities.remove(overlay);
   overlay=null;
   byId('timeline').hidden=true;
   byId('legend').hidden=true;
   byId('picked').hidden=true;
   byId('debrisProbe').hidden=true;
   byId('debrisPanel').hidden=!debris;
   byId('simulateDebris').textContent=reconstruction?(debris?'Repetir escenario':'Escenario hidráulico'):
    debris?'Repetir aluvión':'Simular aluvión';
   byId('variable').disabled=true;
   if(!id){
    byId('result').textContent='El mapa muestra las huellas interpretadas de las fotos.';
    viewer.scene.requestRender();
    return;
   }
   const result=byId(debris?'debrisResult':'result');
   result.textContent='Cargando resultados calculados…';
   try{
    const item=debris?(debrisMeta??=await payload('aluvion-escenario-v1.json')):
     manifest.cases.find(row=>row.id===id);
    const steps=debris?item.times_s.length:item.times.length;
    if(!cache.has(id))cache.set(id,await payload(item.file,Uint16Array));
    if(caseToken!==token)return;
    const data=cache.get(id);
    const grids=debris?steps+1:2*steps+2;
    if(data.length!==grids*item.cols*item.rows)throw Error('Trama incompleta');
    const depth=debris?null:depthFrames(item,data);
    active={meta:item,data,depth,debris,preview:!debris};
    overlay=viewer.entities.add({rectangle:{coordinates:C.Rectangle.fromDegrees(...item.bbox),
     material:new C.ImageMaterialProperty({transparent:true}),heightReference:C.HeightReference.CLAMP_TO_GROUND,
     classificationType:C.ClassificationType.TERRAIN,zIndex:3}});
    frame=debris?item.first_frame:depth.peak;
    byId('time').max=steps-1;
    byId('variable').disabled=debris;
    byId('timeline').hidden=false;
    byId('legend').hidden=false;
    if(debris){
     result.textContent='Volumen supuesto de '+number(item.volume_m3,0)+' m³. '+
      (reconstruction?'La capa de espesores está recortada al perímetro levantado. '+
        'Máximo del cálculo completo: ':'Espesor máximo en el mapa: ')+number(item.max_map_m,1)+' m.';
     byId('debrisExtent').checked=false;
    }else{
     const area=number(item.max_footprint_km2*100,2);
     result.textContent=item.max_footprint_km2>0?
      'Máximo de la corrida: '+number(item.max_depth_m,2)+' m · '+area+' ha con al menos 5 cm. Ensayo sin calibración de campo.':
      'Con esta lluvia y estas pérdidas, la corrida queda por debajo de 5 cm.';
    }
    draw();
   }catch(error){
    if(caseToken===token)result.textContent=error.message;
   }
  }
  byId('case').onchange=()=>chooseCase();
  byId('simulateDebris').onclick=async()=>{
   const button=byId('simulateDebris');
   button.disabled=true;
   try{
    byId('case').value='';
    await chooseCase('aluvion');
    if(!active?.debris)return;
    home();
    byId('play').click();
   }finally{button.disabled=false;}
  };
  byId('debrisExtent').onchange=()=>{stop();draw();};
  byId('variable').onchange=draw;
  byId('time').oninput=()=>{
   active.preview=false;byId('debrisExtent').checked=false;frame=Number(byId('time').value);draw();
  };
  byId('reset').onclick=()=>{stop();active.preview=false;byId('debrisExtent').checked=false;frame=0;draw();};
  byId('play').onclick=()=>{
   if(player){stop();return;}
   if(!active)return;
   if(active.preview){
    frame=Math.max(0,active.depth.first-1);
    active.preview=false;
   }
   const last=Number(byId('time').max);
   if(frame>=last)frame=active.debris?active.meta.first_frame:0;
   byId('debrisExtent').checked=false;
   const variable=byId('variable');
   if(variable.value==='maxDepth')variable.value='depth';
   if(variable.value==='maxSpeed')variable.value='speed';
   draw();
   byId('play').textContent='Pausar';
   player=setInterval(()=>{
    frame++;
    if(frame>=last)stop();
    draw();
   },(active.debris?220:330)/Number(byId('speed').value));
  };
  byId('speed').onchange=()=>{if(player){stop();byId('play').click();}};
  viewer.screenSpaceEventHandler.setInputAction(event=>{
   const chosen=viewer.scene.pick(event.position);
   const building=chosen?.id?.building;
   if(building){
    byId('buildingsDetails').open=true;
    byId('buildingInfo').hidden=false;
    byId('buildingInfo').textContent=number(building.height_m,1)+' m · '+building.height_source+
     '. Huella de '+building.footprint_source+'. Acabado y forma de cubierta aproximados.';
    return;
   }
   const routeStop=chosen?.id?.properties?.routeStop?.getValue();
   if(Number.isInteger(routeStop)){
    haltTour();
    showRouteStop(routeStop);
    return;
   }
   const photo=chosen?.id?.properties?.photo?.getValue();
   if(photo)selectPhoto(photo);
   const ray=viewer.camera.getPickRay(event.position);
   const hit=ray&&viewer.scene.globe.pick(ray,viewer.scene);
   if(!hit||!active)return;
   const p=C.Cartographic.fromCartesian(hit);
   const lon=C.Math.toDegrees(p.longitude),lat=C.Math.toDegrees(p.latitude);
   if(active.debris&&reconstruction&&!reconstruction.contains(lon,lat)){
    byId('debrisProbe').hidden=true;
    return;
   }
   const [xc,yc]=coordinateIndex(active.meta,lon,lat);
   const x=Math.round(xc),y=Math.round(yc);
   if(x<0||y<0||x>=active.meta.cols||y>=active.meta.rows)return;
   const value=mapSlice()[y*active.meta.cols+x]/100;
   if(active.debris){
    byId('debrisProbe').hidden=false;
    byId('debrisProbe').textContent='Espesor simulado en el punto · '+number(value,2)+' m · '+byId('timeLabel').textContent+'.';
    return;
   }
   const variable=byId('variable').value;
   byId('picked').hidden=false;
   byId('picked').textContent='Celda del escenario · '+number(value,2)+
    (variable==='speed'||variable==='maxSpeed'?' m/s':' m')+' · '+active.meta.resolution_m+' m de resolución.';
  },C.ScreenSpaceEventType.LEFT_CLICK);
  const weather=manifest.weather;
  const soil=weather.moisture_before_alert.soil_moisture_0_to_7cm;
  byId('weatherSummary').textContent='ECMWF IFS estimó '+number(weather.local_day_accumulated_mm)+' mm el 22 de noviembre.'+
   ' En la capa de 0–7 cm, estimó '+number(soil.value_m3m3,3)+' m³/m³ a las 18:00.'+
   (soil.percentile?' Percentil '+number(soil.percentile)+' respecto de 2017–2025.':'');
  const sat=manifest.satellite;
  byId('satelliteSummary').textContent=sat?
   'Comparación de escenas con control local de nubes. Cobertura posterior disponible: '+sat.after_scene.length+' escenas.' :
   'Cotejo óptico en preparación.';
  byId('satelliteLink').hidden=!sat?.analysis.some(row=>row.datetime);
  const basin=manifest.terrain_summary.basins.at(-1);
  byId('profiles').textContent='El drenaje derivado reúne '+number(basin.km2,2)+' km² en el sector bajo.';
  home();
  await Promise.all(initialLayers);
  byId('photoCount').textContent=photoRecords.size;
  if(routeStops.every(({photo})=>photoRecords.has(photo)&&evidenceByPhoto.has(photo))){
   routeLayer=await viewer.dataSources.add(new C.CustomDataSource('Recorrido aproximado entre fotos'));
   for(const segment of routeSegments){
    const points=segment.map(id=>evidenceByPhoto.get(id));
    if(points.some(point=>!point))continue;
    routeLayer.entities.add({polyline:{positions:C.Cartesian3.fromDegreesArray(points.flat()),
     clampToGround:true,classificationType:C.ClassificationType.TERRAIN,width:6,zIndex:5,
     material:new C.PolylineDashMaterialProperty({color:color('#ffd36b'),gapColor:color('#172820').withAlpha(.65),
      dashLength:22})}});
   }
   routeStops.forEach(({photo,label},index)=>{
    const [lon,lat]=evidenceByPhoto.get(photo);
    routeLayer.entities.add({position:C.Cartesian3.fromDegrees(lon,lat,elevation(lon,lat)+24),
     properties:{routeStop:index},
     point:{pixelSize:14,color:color('#ffd36b'),outlineColor:color('#172820'),outlineWidth:2,
      disableDepthTestDistance:Infinity},
     label:{text:(index+1)+' · '+label,font:'bold 14px system-ui',showBackground:true,
      backgroundColor:color('#172820').withAlpha(.92),pixelOffset:new C.Cartesian2(0,-15),
      verticalOrigin:C.VerticalOrigin.BOTTOM,disableDepthTestDistance:Infinity}});
    const button=document.createElement('button');
    button.type='button';
    button.textContent=label;
    button.setAttribute('aria-pressed','false');
    button.onclick=()=>{haltTour();showRouteStop(index);};
    routeButtons.push(button);
    byId('routeStops').append(button);
   });
   routeLayer.show=!requestedCase;
   byId('routeKey').hidden=!routeLayer.show;
   byId('routeStops').hidden=false;
   byId('tour').disabled=false;
   viewer.scene.requestRender();
  }
  const options=new URLSearchParams(location.search);
  if(window.createShobolReconstruction){
   reconstruction=await window.createShobolReconstruction({C,viewer,palette:debrisScale.map(([,tint])=>tint),
    focus:(lon,lat,range)=>{
     haltTour();
     clearRouteStop();
     look(lon,lat,252,-54,range);
    },
    leaveModel:async()=>{
     byId('case').value='';
     await chooseCase('');
    },
    showReconstruction:visible=>{
     if(routeLayer)routeLayer.show=!visible&&!requestedCase;
     byId('routeKey').hidden=!routeLayer?.show;
     const interpreted=layerObjects.get('areas_interpretadas');
     const toggle=byId('layers').querySelector('[data-layer="areas_interpretadas"]');
     if(interpreted&&toggle)interpreted.show=!visible&&toggle.checked;
     viewer.scene.requestRender();
    },
   }).catch(error=>{console.warn(error);return null;});
   if(reconstruction){
    byId('mapReconstruct').hidden=false;
    byId('simulateDebris').classList.remove('primary');
    byId('simulateDebris').textContent='Escenario hidráulico';
   }
   if(options.get('vista')==='huella')void reconstruction?.startReconstruction();
  }
  byId('simulateDebris').disabled=false;
  if(options.has('qa')){
   window.shobolQA={viewer,ready:!layerError,case:()=>active?.meta.id,frame:()=>frame,
                   tour:flyTour,tourFrame,home,show:look,overlay:()=>overlay?.rectangle,photoRecords,
                   mesh:()=>surveyMesh,values:()=>active?mapSlice():null};
  }
  if(options.get('sim')==='aluvion')byId('simulateDebris').click();
  if(buildings&&options.get('vista')==='construcciones'){
   byId('buildingsDetails').open=true;
   byId('buildingFocus').click();
  }
 }catch(error){
  console.error(error);
  byId('loading').hidden=false;
  byId('loading').textContent='No se pudo abrir el visor. '+error.message;
 }
})();
