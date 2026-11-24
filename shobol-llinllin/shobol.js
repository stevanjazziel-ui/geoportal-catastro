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
  microcuencas:'#8cd7ba',drenaje_d8:'#78c9eb',referencias:'#ccbaf1',edificios_osm:'#d3c7a8',
  hidrografia_osm:'#4db4f0',vias_osm:'#d7cb99',puentes_osm:'#e9ac80',areas_interpretadas:'#e6a259',
  perfiles:'#c5eca6'};
 const depthScale=[[.05,'#eac17e','5–20 cm'],[.2,'#cf8846','20–50 cm'],[.5,'#91492e','50 cm o más']];
 const speedScale=[[.01,'#cce8d4','< 0,3 m/s'],[.3,'#58aa9c','0,3–1 m/s'],[1,'#225d67','1 m/s o más']];
 const defaultLayers=new Set(['capturas','evidencias','areas_interpretadas','edificios_osm','hidrografia_osm']);
 const cache=new Map();
 let caseToken=0,active=null,frame=0,player=null,tourId=0,selectedPhoto=null,layerError=false;
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
 function color(str){return C.Color.fromCssColorString(str);}
 function hexRgb(value){return [1,3,5].map(i=>parseInt(value.slice(i,i+2),16));}
 function timeText(caseData,minute){
  const date=new Date(Date.parse(caseData.start_local)+minute*60000);
  return new Intl.DateTimeFormat('es-EC',{timeZone:'America/Guayaquil',hour:'2-digit',minute:'2-digit',
   hourCycle:'h23',day:'numeric',month:'short'}).format(date);
 }

 try{
  const manifest=await payload('manifest.json');
  const elevations=await payload(manifest.terrain.file,Float32Array);
  if(elevations.length!==manifest.terrain.rows*manifest.terrain.cols)throw Error('Terreno incompleto');
  const elevation=sampler(manifest.terrain,elevations);
  const satelliteFallback=new C.UrlTemplateImageryProvider({
   url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
   maximumLevel:16,credit:'Imagen de respaldo © Esri y proveedores'});
  const viewer=new C.Viewer('viewer',{terrainProvider:localTerrain(manifest.terrain,elevation),
   baseLayer:new C.ImageryLayer(satelliteFallback),animation:false,timeline:false,
   geocoder:false,homeButton:false,sceneModePicker:false,navigationHelpButton:false,
   baseLayerPicker:false,selectionIndicator:false,infoBox:false,fullscreenButton:false,
   requestRenderMode:true,maximumRenderTimeChange:Infinity});
  viewer.scene.globe.depthTestAgainstTerrain=true;
  viewer.scene.globe.maximumScreenSpaceError=2;
  viewer.scene.backgroundColor=color('#384a43');
  viewer.scene.screenSpaceCameraController.minimumZoomDistance=25;
  viewer.cesiumWidget.creditDisplay.addStaticCredit(new C.Credit(
   '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap colaboradores · ODbL</a>',true));
  void EcuadorImagery.connect(viewer,C);
  const overlayCanvas=document.createElement('canvas');
  const paint=overlayCanvas.getContext('2d');
  let overlay;

  function look(lon,lat,heading,pitch,range){
   const center=C.Cartesian3.fromDegrees(lon,lat,elevation(lon,lat)+15);
   viewer.camera.lookAt(center,new C.HeadingPitchRange(C.Math.toRadians(heading),C.Math.toRadians(pitch),range));
   viewer.camera.lookAtTransform(C.Matrix4.IDENTITY);
   viewer.scene.requestRender();
  }
  function haltTour(){
   tourId++;
   byId('tour').textContent='Recorrido 3D';
  }
  function home(){
   haltTour();
   look(-78.8025,-1.598,255,-47,3850);
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
  function flyTour(duration=90000){
   const id=++tourId,started=performance.now();
   byId('tour').textContent='Detener recorrido';
   const animate=now=>{
    if(id!==tourId)return;
    const progress=Math.min(1,(now-started)/duration);
    tourFrame(progress);
    if(progress<1)requestAnimationFrame(animate);
    else haltTour();
   };
   requestAnimationFrame(animate);
  }
  byId('home').onclick=home;
  byId('tour').onclick=()=>byId('tour').textContent.startsWith('Detener')?haltTour():flyTour();
  home();
  byId('loading').hidden=true;

  async function activateLayer(key,on){
   let object=layerObjects.get(key);
   if(on&&!object){
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
    }else{
     object=await C.GeoJsonDataSource.load(data,{clampToGround:true,stroke:tint,strokeWidth:key==='puentes_osm'?4:2,
      fill:tint.withAlpha(key==='edificios_osm'?.9:.15)});
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
    viewer.scene.requestRender();
   }
  }
  const photoRecords=new Map();
  const initialLayers=[];
  for(const [key,item] of Object.entries(manifest.layers)){
   const label=document.createElement('label');
   const input=document.createElement('input');
   input.type='checkbox';
   input.checked=defaultLayers.has(key);
   label.append(input,item.label);
   byId('layers').append(label);
   const update=()=>activateLayer(key,input.checked).catch(error=>{
    layerError=true;input.checked=false;console.warn(error);label.title=error.message;
   });
   input.onchange=update;
   if(input.checked)initialLayers.push(update());
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
   const variable=byId('variable').value;
   const area=active.meta.rows*active.meta.cols,steps=active.meta.times.length;
   const index={depth:frame,speed:steps+frame,maxDepth:2*steps,maxSpeed:2*steps+1}[variable];
   return active.data.subarray(index*area,(index+1)*area);
  }
  function draw(){
   if(!active)return;
   const tag=byId('variable').value;
   const speed=tag==='speed'||tag==='maxSpeed';
   const scale=speed?speedScale:depthScale;
   const width=active.meta.cols,height=active.meta.rows;
   overlayCanvas.width=width;overlayCanvas.height=height;
   const image=paint.createImageData(width,height);
   const values=mapSlice();
   const thresholds=scale.map(([x,c])=>[Math.round(x*100),hexRgb(c)]);
   for(let i=0;i<values.length;i++){
    const value=values[i];
    if(value<thresholds[0][0])continue;
    const rgb=value>=thresholds[2][0]?thresholds[2][1]:value>=thresholds[1][0]?thresholds[1][1]:thresholds[0][1];
    image.data.set([...rgb,213],i*4);
   }
   paint.putImageData(image,0,0);
   overlay.rectangle.material=new C.ImageMaterialProperty({image:overlayCanvas.toDataURL(),transparent:true});
   byId('timeLabel').textContent=(tag.startsWith('max')?'Máximo de la corrida · ':'Hora Ecuador · ')+
    timeText(active.meta,active.meta.times[frame]);
   byId('time').value=frame;
   byId('legendTitle').textContent=speed?'Velocidad calculada':'Profundidad calculada';
   byId('scale').replaceChildren(...scale.map(([,tint,text])=>{
    const label=document.createElement('span');
    const mark=document.createElement('i');
    mark.style.background=tint;
    label.append(mark,text);
    return label;
   }));
   viewer.scene.requestRender();
  }
  async function chooseCase(){
   stop();
   const id=byId('case').value,token=++caseToken;
   active=null;
   if(overlay)viewer.entities.remove(overlay);
   overlay=null;
   byId('timeline').hidden=true;
   byId('legend').hidden=true;
   byId('picked').hidden=true;
   byId('variable').disabled=true;
   if(!id){
    byId('result').textContent='Vista de evidencia. Selecciona un ensayo para consultar los cálculos de agua.';
    return;
   }
   const item=manifest.cases.find(row=>row.id===id);
   byId('result').textContent='Cargando resultados calculados…';
   try{
    if(!cache.has(id))cache.set(id,await payload(item.file,Uint16Array));
    if(caseToken!==token)return;
    const data=cache.get(id);
    if(data.length!==(2*item.times.length+2)*item.cols*item.rows)throw Error('Trama incompleta');
    active={meta:item,data};
    overlay=viewer.entities.add({rectangle:{coordinates:C.Rectangle.fromDegrees(...item.bbox),
     material:new C.ImageMaterialProperty({transparent:true}),heightReference:C.HeightReference.CLAMP_TO_GROUND,
     classificationType:C.ClassificationType.TERRAIN,zIndex:3}});
    frame=0;
    byId('time').max=item.times.length-1;
    byId('variable').disabled=false;
    byId('timeline').hidden=false;
    byId('legend').hidden=false;
    const area=number(item.max_footprint_km2*100,2);
    byId('result').textContent=item.max_footprint_km2>0?
     'Máximo de la corrida: '+number(item.max_depth_m,2)+' m · '+area+' ha con al menos 5 cm. Ensayo sin calibración de campo.':
     'Con esta lluvia y estas pérdidas, la corrida queda por debajo de 5 cm.';
    draw();
   }catch(error){
    if(caseToken===token)byId('result').textContent=error.message;
   }
  }
  byId('case').onchange=chooseCase;
  byId('variable').onchange=draw;
  byId('time').oninput=()=>{frame=Number(byId('time').value);draw();};
  byId('reset').onclick=()=>{stop();frame=0;draw();};
  byId('play').onclick=()=>{
   if(player){stop();return;}
   if(!active)return;
   if(frame>=active.meta.times.length-1)frame=0;
   byId('play').textContent='Pausar';
   player=setInterval(()=>{
    frame++;
    if(frame>=active.meta.times.length-1)stop();
    draw();
   },330/Number(byId('speed').value));
  };
  byId('speed').onchange=()=>{if(player){stop();byId('play').click();}};
  viewer.screenSpaceEventHandler.setInputAction(event=>{
   const chosen=viewer.scene.pick(event.position);
   const photo=chosen?.id?.properties?.photo?.getValue();
   if(photo)selectPhoto(photo);
   const ray=viewer.camera.getPickRay(event.position);
   const hit=ray&&viewer.scene.globe.pick(ray,viewer.scene);
   if(!hit||!active)return;
   const p=C.Cartographic.fromCartesian(hit);
   const [xc,yc]=coordinateIndex(active.meta,C.Math.toDegrees(p.longitude),C.Math.toDegrees(p.latitude));
   const x=Math.round(xc),y=Math.round(yc);
   if(x<0||y<0||x>=active.meta.cols||y>=active.meta.rows)return;
   const value=mapSlice()[y*active.meta.cols+x]/100;
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
  if(new URLSearchParams(location.search).has('qa')){
   window.shobolQA={viewer,ready:!layerError,case:()=>active?.meta.id,frame:()=>frame,
                   tour:flyTour,tourFrame,home,show:look,overlay:()=>overlay?.rectangle,photoRecords,
                   mesh:()=>surveyMesh};
  }
 }catch(error){
  console.error(error);
  byId('loading').hidden=false;
  byId('loading').textContent='No se pudo abrir el visor. '+error.message;
 }
})();
