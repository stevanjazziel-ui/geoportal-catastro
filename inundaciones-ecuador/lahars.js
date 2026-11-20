'use strict';
(async()=>{
 const $=id=>document.getElementById(id),root='data/sangolqui-lahars/';
 let C;
 const params=new URLSearchParams(location.search);
 const joint=params.get('vista')==='conjunta';
 const archive=!joint&&params.get('escenario')==='espe';
 const focusPita=!joint&&!archive&&params.get('rio')==='pita';
 const campusCenter=[-78.445069,-.315230];
 let meta,viewer,corners,terrain,regional,current,data,maxima,secondary,frame=0,timer,waterMesh,buildingMesh,request=0;
 let coverageLayer, coveragePending=false, coverageUnavailable=false, guided=false, activeView=-1;
 const riverViews=[
  {name:'Pita',button:'pita',reference:'pitaReference',color:'#9ae8ec',entities:[]},
  {name:'Santa Clara',button:'santaClara',reference:'santaReference',color:'#e2bbff',entities:[]},
 ];
 const flowColors=[[255,212,123,240],[242,150,76,245],[185,80,46,250]];
 const municipalBlue=[50,191,243,165], copernicusOrange=[248,146,70,165];
 const guideViews=archive?[
  {minute:0,name:'Cotopaxi',lon:-78.429,lat:-.566,range:23700,pitch:-55},
  {minute:50,name:'La Caldera',lon:-78.4225,lat:-.446,range:8000,pitch:-54},
  {minute:69,name:'Valle de Santa Clara',lon:-78.418,lat:-.371,range:6500,pitch:-52},
  {minute:86,name:'Sangolquí y ESPE',lon:-78.4415,lat:-.326,range:5500,pitch:-54},
 ]:[
  {minute:0,name:'Cotopaxi',lon:-78.43,lat:-.586,range:25500,pitch:-56},
  {minute:48,name:'La Caldera',lon:-78.417,lat:-.420,range:15700,pitch:-62},
  {minute:75,name:'Sangolquí y San Rafael',lon:-78.426,lat:-.347,range:14400,pitch:-62},
  ...(joint?[{minute:120,name:'Río San Pedro',lon:-78.451,lat:-.276,range:12400,pitch:-66}]:[]),
 ];
 const fmt=(v,n=2)=>Number(v).toLocaleString('es-EC',{maximumFractionDigits:n});
 function stop(){
  clearInterval(timer);
  timer=null;
  guided=false;
  activeView=-1;
  $('play').textContent='▶';
  $('play').setAttribute('aria-label','Reproducir simulación');
  $('follow').textContent='Seguir el lahar';
  $('follow').setAttribute('aria-pressed','false');
 }
 function error(e){stop();$('loading').hidden=false;$('loading').textContent='No se pudo cargar el visor: '+e.message;}
 async function compressed(asset,Type){
  const local=['localhost','127.0.0.1','[::1]'].includes(location.hostname);
  const url=(!local&&asset.url)||root+asset.file,suffix=asset.sha256?'?sha='+asset.sha256.slice(0,16):'';
  const rawRoot='https://raw.githubusercontent.com/stevanjazziel-ui/geoportal-catastro/main/';
  const mirror='https://cdn.jsdelivr.net/gh/stevanjazziel-ui/geoportal-catastro@main/';
  async function read(location){
   const response=await fetch(location+suffix);
   if(!response.ok)throw Error('No se pudo descargar '+asset.file+' (HTTP '+response.status+')');
   return response.arrayBuffer();
  }
  let bytes;
  try{bytes=await read(url);}
  catch(error){
   if(!asset.sha256||!url.startsWith(rawRoot))throw error;
   bytes=await read(mirror+url.slice(rawRoot.length));
  }
  if(asset.sha256){const digest=await crypto.subtle.digest('SHA-256',bytes);const hex=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');if(hex!==asset.sha256)throw Error('Descarga incompleta o diferente a la publicada');}
  const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  const buffer=await new Response(stream).arrayBuffer();return Type?new Type(buffer):JSON.parse(new TextDecoder().decode(buffer));
 }
 function decodeFrames(a,n,frames){if(a.length!==n*5*frames)throw Error('Número de resultados incorrecto');const stride=5*n;for(let t=1;t<frames;t++)for(let i=0;i<stride;i++)a[t*stride+i]+=a[(t-1)*stride+i];return a;}
 function sampleTerrain(a,m,lon,lat){const [w,s,e,n]=m.bbox;if(lon<w||lon>e||lat<s||lat>n)return null;const x=Math.max(0,Math.min(m.cols-1,(lon-w)/(e-w)*(m.posts?m.cols-1:m.cols)-(m.posts?0:.5))),y=Math.max(0,Math.min(m.rows-1,(n-lat)/(n-s)*(m.posts?m.rows-1:m.rows)-(m.posts?0:.5))),ix=Math.min(m.cols-2,Math.floor(x)),iy=Math.min(m.rows-2,Math.floor(y)),fx=x-ix,fy=y-iy;const z=(r,c)=>a[r*m.cols+c]*m.scale;return (z(iy,ix)*(1-fx)+z(iy,ix+1)*fx)*(1-fy)+(z(iy+1,ix)*(1-fx)+z(iy+1,ix+1)*fx)*fy;}
 function elevation(lon,lat){const bg=sampleTerrain(regional,meta.regional,lon,lat)??0,fine=sampleTerrain(terrain,meta.terrain,lon,lat);if(fine===null)return bg;const [w,s,e,n]=meta.terrain.bbox,margin=Math.min(lon-w,e-lon,lat-s,n-lat)*111000,blend=Math.min(1,Math.max(0,margin/500));return bg*(1-blend)+fine*blend;}
 function city(){const municipal=meta?.adaptation?.terrain?.model_file==='municipal_hybrid_30m.tif',lon=municipal?-78.435:-78.447,lat=municipal?-.344:-.333;viewer.camera.flyToBoundingSphere(new C.BoundingSphere(C.Cartesian3.fromDegrees(lon,lat,elevation(lon,lat)),municipal?2100:1500),{offset:new C.HeadingPitchRange(0,C.Math.toRadians(-50),municipal?9000:5500)});}
 function espe(){
  const [lon,lat]=campusCenter;
  viewer.camera.flyToBoundingSphere(new C.BoundingSphere(C.Cartesian3.fromDegrees(lon,lat,elevation(lon,lat)),850),
   {offset:new C.HeadingPitchRange(C.Math.toRadians(346),C.Math.toRadians(-66),2750),duration:1.15});
 }
 async function showCampus(){
  const result=await fetch(root+'espe-comparison.json');
  if(!result.ok)throw Error('Sin datos del campus');
  const {campus,cases}=await result.json();
  viewer.entities.add({name:'Perímetro referencial ESPE · OpenStreetMap',polyline:{
   positions:C.Cartesian3.fromDegreesArray(campus.perimeter.flat()),clampToGround:true,width:3,
   classificationType:C.ClassificationType.TERRAIN,
   material:new C.PolylineOutlineMaterialProperty({color:C.Color.WHITE,outlineColor:C.Color.fromCssColorString('#202a36'),outlineWidth:1}),
  }});
  const contacts=joint?['reference-mdt30','reference-cop30']:[current.id];
  for(const id of contacts){
   const contact=cases[id]?.campus_first_5cm;
   if(!contact)continue;
   const text_minutes=Math.floor(contact.seconds/60)+':'+String(contact.seconds%60).padStart(2,'0');
   const santa=id==='reference-cop30';
   const side=santa?'junto a Santa Clara':'en el extremo cercano al Pita';
   if(!joint)$('espeStatus').textContent='Primer flujo detectado '+side+', al minuto '+text_minutes+' del escenario.';
   viewer.entities.add({name:'Primer contacto calculado en el perímetro ESPE',
    position:C.Cartesian3.fromDegrees(contact.lon,contact.lat,elevation(contact.lon,contact.lat)+7),
    point:{pixelSize:8,color:C.Color.WHITE,outlineColor:C.Color.fromCssColorString('#203239'),outlineWidth:2,disableDepthTestDistance:Infinity},
    label:{text:(joint?(santa?'Santa Clara · ':'Pita · '):'Primer contacto ESPE · ')+text_minutes,font:'bold 14px Arial',showBackground:true,
     backgroundColor:C.Color.BLACK.withAlpha(.75),pixelOffset:new C.Cartesian2(0,-19),disableDepthTestDistance:Infinity,
     distanceDisplayCondition:new C.DistanceDisplayCondition(0,7500)}});
   const downstream=cases[id].segments.sanpedro5?.samples.findLast(sample=>sample[3]>=0);
   if(downstream){
    const [,lon,lat]=downstream;
    const color=C.Color.fromBytes(...(santa?copernicusOrange:municipalBlue));
    viewer.entities.add({name:'Alcance en el San Pedro durante 150 minutos',show:$('maximum').checked,
     position:C.Cartesian3.fromDegrees(lon,lat,elevation(lon,lat)+8),
     point:{pixelSize:8,color,outlineColor:C.Color.WHITE,outlineWidth:1.5,disableDepthTestDistance:Infinity},
     label:{text:santa?'Límite de la corrida inicial':'Límite de la corrida municipal',
      font:'bold 13px Arial',showBackground:true,backgroundColor:C.Color.BLACK.withAlpha(.72),
      pixelOffset:new C.Cartesian2(0,-16),disableDepthTestDistance:Infinity,
      distanceDisplayCondition:new C.DistanceDisplayCondition(0,24000)}});
   }
  }
  viewer.cesiumWidget.creditDisplay.addStaticCredit(new C.Credit('Perímetro ESPE © OpenStreetMap contributors · ODbL',true));
  viewer.scene.requestRender();
 }
 function flyOver(bounds, duration=1.4){
  viewer.camera.flyTo({destination:C.Rectangle.fromDegrees(...bounds),duration});
 }
 function showCoverage(){
  if(!data)return;
  stop();
  $('flow').checked=true;
  $('maximum').checked=true;
  update();
 }
 async function addRiverReferences(){
  const response=await fetch('data/lahar-study-times/timeline.json');
  if(!response.ok)throw Error('No respondieron los trazados de los ríos');
  const {segments}=await response.json();
  for(const river of riverViews){
   const reaches=segments.filter(segment=>segment.river===river.name);
   if(!reaches.length)continue;
   const reference=$(river.reference);
   const material=new C.PolylineDashMaterialProperty({color:C.Color.fromCssColorString(river.color),dashLength:15});
   for(const {coordinates} of reaches){
    river.entities.push(viewer.entities.add({
     name:`Río ${river.name} · cauce de referencia`,show:reference.checked,
     polyline:{positions:C.Cartesian3.fromDegreesArray(coordinates.flat()),width:2.5,clampToGround:true,
      classificationType:C.ClassificationType.TERRAIN,material},
    }));
   }
   const coordinates=reaches.flatMap(segment=>segment.coordinates);
   const lon=coordinates.map(point=>point[0]);
   const lat=coordinates.map(point=>point[1]);
   const latPadding=Math.max(.025,(Math.max(...lat)-Math.min(...lat))*.19);
   const bounds=[Math.min(...lon)-.028,Math.min(...lat)-latPadding,Math.max(...lon)+.028,Math.max(...lat)+latPadding];
   const focus=()=>{
    reference.checked=true;
    reference.onchange();
    showCoverage();
    flyOver(bounds);
   };
   $(river.button).onclick=focus;
   reference.onchange=()=>{
    for(const entity of river.entities)entity.show=reference.checked;
    viewer.scene.requestRender();
   };
   reference.disabled=false;
   $(river.button).disabled=false;
   if(focusPita&&river.name==='Pita')focus();
  }
  viewer.cesiumWidget.creditDisplay.addStaticCredit(new C.Credit('Cauces © OpenStreetMap contributors · ODbL',true));
  viewer.scene.requestRender();
 }
 function placeLabels(){
  const places=[
   ['Volcán Cotopaxi',-78.437,-.681],
   ['La Caldera',-78.42255,-.45633],
   ['Sangolquí',-78.4425,-.3315],
   ['San Rafael',-78.447,-.306],
  ];
  for(const [text,lon,lat] of places){
   viewer.entities.add({
    position:C.Cartesian3.fromDegrees(lon,lat,elevation(lon,lat)+8),
    point:{pixelSize:5,color:C.Color.WHITE,outlineColor:C.Color.BLACK,outlineWidth:1,disableDepthTestDistance:Infinity},
    label:{text,font:'bold 14px Arial',showBackground:true,backgroundColor:C.Color.BLACK.withAlpha(.72),
     pixelOffset:new C.Cartesian2(0,-17),disableDepthTestDistance:Infinity},
   });
  }
 }
 function caldera(){const p=meta.adaptation?.view_targets?.caldera||[-78.4229,-.4563];viewer.camera.flyToBoundingSphere(new C.BoundingSphere(C.Cartesian3.fromDegrees(p[0],p[1],elevation(p[0],p[1])),900),{offset:new C.HeadingPitchRange(0,C.Math.toRadians(-42),4200)});}
 function route(){
  const [west,south,east,north]=flowBounds();
  flyOver([west-.025,south-.025,east+.025,north+.045]);
 }
 function sanPedro(){
  showCoverage();
  flyOver([-78.491,-.315,-78.414,-.225]);
 }
 function guideCamera(view,duration=1.4){
  const {lon,lat,range,pitch}=guideViews[view];
  const center=C.Cartesian3.fromDegrees(lon,lat,elevation(lon,lat));
  // Cesium's vertical field of view is limited by width in portrait layout.
  const map=viewer.scene.canvas;
  const portraitScale=Math.max(1,Math.min(1.18,map.clientHeight/map.clientWidth));
  viewer.camera.flyToBoundingSphere(new C.BoundingSphere(center,1200),{
   offset:new C.HeadingPitchRange(0,C.Math.toRadians(pitch),range*portraitScale),duration,
  });
 }
 function followCamera(){
  const minutes=meta.times_s[frame]/60;
  const view=guideViews.findLastIndex(stage=>minutes>=stage.minute);
  if(view!==activeView){
   activeView=view;
   guideCamera(view);
  }
  $('timeLabel').textContent+=` · ${guideViews[view].name}`;
 }
 function play(useGuide){
  const last=meta.times_s.length-1;
  guided=useGuide;
  if(guided||$('maximum').checked||frame===last)frame=0;
  $('maximum').checked=false;
  if(guided)$('flow').checked=true;
  $('play').textContent='Ⅱ';
  $('play').setAttribute('aria-label','Pausar simulación');
  if(guided){
   $('follow').textContent='Pausar recorrido';
   $('follow').setAttribute('aria-pressed','true');
  }
  update();
  timer=setInterval(()=>{
   frame++;
   update();
   if(frame===last)stop();
  },guided?850:1100);
 }
 function depthClass(cm){return cm<50?0:cm<200?1:2;}
 function layers(){
  const primary={corners,data,maxima,n:meta.cell_count,palette:joint?[municipalBlue]:flowColors};
  return secondary?[primary,secondary]:[primary];
 }
 function flowBounds(){
  let west=Infinity,south=Infinity,east=-Infinity,north=-Infinity;
  for(const {corners:cells} of layers()){
   for(let i=0;i<cells.length;i+=3){
    west=Math.min(west,cells[i]);
    east=Math.max(east,cells[i]);
    south=Math.min(south,cells[i+1]);
    north=Math.max(north,cells[i+1]);
   }
  }
  return [west,south,east,north];
 }
 function coverageImage(){
  const [west,south,east,north]=flowBounds();
  // Render the original cell footprints in geographic coordinates and drape them
  // against the active terrain mesh so narrow canyons do not hide the envelope.
  const canvas=document.createElement('canvas');
  const degreesPerPixel=Math.max(east-west,north-south)/4096;
  canvas.width=Math.ceil((east-west)/degreesPerPixel);
  canvas.height=Math.ceil((north-south)/degreesPerPixel);
  const ctx=canvas.getContext('2d');
  const scaleX=canvas.width/(east-west);
  const scaleY=canvas.height/(north-south);
  for(const layer of layers()){
   const {corners:cells,maxima:depth,n,palette}=layer;
   for(let category=0;category<palette.length;category++){
    const [r,g,b,a]=palette[category];
    ctx.fillStyle=`rgba(${r},${g},${b},${joint?a/255:1})`;
    ctx.beginPath();
    for(let i=0;i<n;i++){
     if(depth[i]<5||(palette.length>1&&depthClass(depth[i])!==category))continue;
     const start=i*12;
     ctx.moveTo((cells[start]-west)*scaleX,(north-cells[start+1])*scaleY);
     for(let j=1;j<4;j++){
      const k=start+j*3;
      ctx.lineTo((cells[k]-west)*scaleX,(north-cells[k+1])*scaleY);
     }
     ctx.closePath();
    }
    ctx.fill();
   }
  }
  return {canvas,rectangle:C.Rectangle.fromDegrees(west,south,east,north)};
 }
 async function ensureCoverageLayer(){
  coveragePending=true;
  const id=request;
  let url;
  try{
   const {canvas,rectangle}=coverageImage();
   const image=await new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(Error('Sin imagen de cobertura'))));
   if(id!==request)return;
   url=URL.createObjectURL(image);
   const provider=await C.SingleTileImageryProvider.fromUrl(url,{rectangle});
   if(id!==request)return;
   coverageLayer=viewer.imageryLayers.addImageryProvider(provider);
   coverageLayer.alpha=.95;
   draw();
  }catch(_){
   if(id===request)coverageUnavailable=true;
  }finally{
   if(url)URL.revokeObjectURL(url);
   if(id===request)coveragePending=false;
  }
 }
 function draw(){
  if(waterMesh){viewer.scene.primitives.remove(waterMesh);waterMesh=null;}
  const visible=Boolean(data)&&$('flow').checked;
  const all=$('maximum').checked;
  for(const entity of viewer.entities.values){
   if(entity.name==='Alcance en el San Pedro durante 150 minutos')entity.show=all&&$('flow').checked;
  }
  if(coverageLayer)coverageLayer.show=visible&&all;
  if(!visible||(all&&coverageLayer)){viewer.scene.requestRender();return;}
  if(all&&!coveragePending&&!coverageUnavailable)void ensureCoverageLayer();
  const indices=[],positions=[],colors=[];
  for(const {corners:cells,data:frames,maxima:envelope,n,palette} of layers()){
   const offset=frame*5*n;
   for(let i=0;i<n;i++){
    const depth=all?envelope[i]:frames[offset+i];if(depth<5)continue;
    const zOffset=all||joint?2:frames[offset+4*n+i]/100+1.5;
    const rgba=palette.length===1?palette[0]:palette[depthClass(depth)],k=positions.length/3;
    for(let j=0;j<4;j++){
     const g=(i*4+j)*3, lon=cells[g],lat=cells[g+1];
     const p=C.Cartesian3.fromDegrees(lon,lat,elevation(lon,lat)+zOffset);
     positions.push(p.x,p.y,p.z);colors.push(...rgba);
    }
    indices.push(k,k+1,k+2,k,k+2,k+3);
   }
  }
  if(positions.length){const p=new Float64Array(positions);const geometry=new C.Geometry({attributes:{position:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.DOUBLE,componentsPerAttribute:3,values:p}),color:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.UNSIGNED_BYTE,componentsPerAttribute:4,normalize:true,values:new Uint8Array(colors)})},indices:new Uint32Array(indices),primitiveType:C.PrimitiveType.TRIANGLES,boundingSphere:C.BoundingSphere.fromVertices(p)});
   const appearance=new C.PerInstanceColorAppearance({flat:true,translucent:true,closed:false,renderState:{depthTest:{enabled:true},depthMask:false,cull:{enabled:false}},vertexShaderSource:'in float batchId; in vec3 position3DHigh; in vec3 position3DLow; in vec4 color; out vec4 v_color; void main(){vec4 p=czm_computePosition();v_color=color;gl_Position=czm_modelViewProjectionRelativeToEye*p;}'});
   waterMesh=viewer.scene.primitives.add(new C.Primitive({geometryInstances:new C.GeometryInstance({geometry}),appearance,asynchronous:false,allowPicking:false}));
  }viewer.scene.requestRender();
 }
 function update(){
  if(!data)return;
  const all=$('maximum').checked;
  const metrics=all?{...current.maximums,...meta.adaptation?.sampled_urban_maxima}:current.metrics_by_frame[frame];
  $('depthLabel').textContent=all?'mayor espesor muestreado en esa área durante 150 min':'mayor espesor en esa área, en el tiempo mostrado';
  $('speedLabel').textContent=all?'mayor velocidad muestreada donde hubo al menos 5 cm de flujo':'mayor velocidad en esa área, en el tiempo mostrado';
  $('time').disabled=all;
  $('time').value=frame;
  const minutes=fmt(meta.times_s[frame]/60,0);
  const origin=meta.adaptation?'desde los aportes en el Cotopaxi':'desde la entrada del flujo';
  $('timeLabel').textContent=all?'Todo el recorrido de 150 min':`${minutes} min ${origin}`;
  $('area').textContent=fmt(metrics.urban_wet_km2);
  $('depth').textContent=fmt(metrics.urban_depth_max_m)+' m';
  $('speed').textContent=fmt(metrics.urban_speed_max_m_s*3.6,1)+' km/h';
  if(joint){
   $('phase').textContent=all?'Cada color reúne lugares alcanzados en algún momento de su corrida.':'Ambas corridas avanzan con el mismo reloj desde los aportes del Cotopaxi.';
  }else if(all){
   $('phase').textContent='El color muestra el mayor espesor alcanzado en cada lugar durante los 150 minutos.';
  }else if(frame<5){
   $('phase').textContent=meta.adaptation?'Durante los primeros 15 minutos entra agua en las nueve fuentes del Cotopaxi.':'La mezcla sigue entrando al río Pita durante los primeros 15 minutos.';
  }else{
   $('phase').textContent='Terminó el aporte inicial. El flujo sigue avanzando, erosionando y depositando sedimentos.';
  }
  if(guided)followCamera();
  draw();
 }
 async function loadCase(){
  stop();
  if(coverageLayer)viewer.imageryLayers.remove(coverageLayer);
  coverageLayer=null;
  coveragePending=false;
  coverageUnavailable=false;
  $('follow').disabled=true;
  data=null;
  draw();
  const id=++request;$('loading').hidden=false;$('loading').textContent='Cargando el cálculo elegido…';$('play').disabled=true;$('time').disabled=true;$('maximum').disabled=true;current=meta.cases[0];const [encoded,max]=await Promise.all([compressed(current,Int32Array),compressed(current.max_asset,Float32Array)]);if(id!==request)return;data=decodeFrames(encoded,meta.cell_count,current.frame_count);maxima=max;if(maxima.length!==3*meta.cell_count)throw Error('Máximos incompletos');frame=archive?meta.times_s.length-1:30;$('maximum').checked=archive;$('play').disabled=false;$('maximum').disabled=false;$('follow').disabled=false;$('loading').hidden=true;$('story').textContent='Entrada hipotética de '+fmt(current.mixture_input_m3/1e6,0)+' millones de m³ de mezcla en 15 minutos. El cálculo sigue el flujo durante 150 minutos; no representa una erupción pronosticada.';$('balance').textContent='Diferencia en el balance del flujo y del lecho: '+(current.mixture_balance_relative_error*100<.001?'menor del 0,001 %':fmt(current.mixture_balance_relative_error*100,5)+' %')+'. Este control numérico no valida el escenario real.';$('report').href=root+current.report;$('input').href=root+current.id+'-input.txt';
  if(meta.adaptation){$('intro').textContent='Pulsa «Seguir el lahar» para ver el avance desde el Cotopaxi. Con «Enfocar Pita» o «Enfocar Santa Clara» puedes explorar el alcance en cada cauce.';const a=meta.adaptation;$('story').textContent='Aporte inicial de '+fmt(a.water_input_m3/1e6,2)+' millones de m³ de agua en nueve puntos del flanco norte. El modelo calcula el arrastre y depósito de sedimentos durante 150 minutos.';$('noticeTitle').textContent='Adaptación de un estudio';$('noticeText').textContent='No está validada para predecir una erupción. Usa un terreno global de 30 m y ubicaciones aproximadas de las fuentes; difiere del modelo original.';$('inputMethod').textContent='Se aplican los nueve hidrogramas de agua del estudio de 2025: liberación simultánea, pico a los 2,5 minutos y fin a los 15 minutos. La concentración inicial de sólidos es cero; aumenta por erosión. No son las antiguas entradas hipotéticas de mezcla de 10, 30 y 60 millones de m³.';$('terrainMethod').textContent='Terreno Copernicus GLO-30, de unos 30 m, que puede incluir vegetación y edificios. Se corrigieron solo depresiones que requerían elevar el terreno hasta 2 m. No es el MDT fotogramétrico fino del estudio. Las fuentes se digitalizaron de su mapa y no son sus coordenadas GIS originales. No se modificó la animación para imponer una llegada publicada.';$('studyResults').hidden=false;const b=a.city_arrival_bracket_s;$('arrival').textContent=b?fmt(b[0]/60,2)+'–'+fmt(b[1]/60,2)+' min':'No alcanzó el área en 150 min';const section=a.section;const passage=section.integrated_m3.north_m3;$('transport').textContent=passage>0&&passage<10000?fmt(passage,0)+' m³':fmt(passage/1e6,2)+' millones de m³';$('scientificReport').href=root+a.scientific_report;$('hydrograph').href=root+a.section_hydrograph;}
  if(meta.adaptation)$('terrainMethod').textContent+=' En pantalla, el espesor se dibuja sobre un terreno fijo para que la erosión no oculte el flujo. Las cotas exactas permanecen en los resultados numéricos. Los máximos del área pueden estar dentro de cañones; no son profundidades uniformes en las calles.';
  if(meta.adaptation?.terrain?.model_file==='municipal_hybrid_30m.tif'){
   $('noticeTitle').textContent='Terreno municipal incorporado';
   $('noticeText').textContent='El cálculo incorpora el MDT municipal nativo de 3 m en una malla de 30 m. Sigue siendo un escenario exploratorio sin validación predictiva local; la referencia vertical y la transición al terreno regional tienen incertidumbre.';
   $('terrainMethod').textContent='Se incorporó el MDT municipal de la capa 2023, nativo de 3 m, remuestreado a la malla física de 30 m. Fuera de su cobertura se conserva Copernicus; una transición de 500 m evita un salto brusco, sin aplicar una corrección vertical supuesta. No se excavó el río ni se impusieron tiempos de llegada. Las muestras LiDAR presentan diferencias de altura cercanas a 27–29 m frente al MDT y no se fusionaron sin resolver su referencia. El terreno visual permanece fijo; los resultados numéricos conservan erosión y depósito. Los máximos pueden estar dentro de cañones y no equivalen a una altura uniforme en las calles.';
  }
  if(archive){
   $('intro').textContent='Esta es la corrida inicial que muestra el paso por Santa Clara hasta la ESPE. Desactiva «Todo el recorrido» para elegir un minuto.';
   $('noticeTitle').textContent='Corrida inicial · Santa Clara y ESPE';
   $('noticeText').textContent='Usa terreno Copernicus de 30 m. Reproduce el recorrido por Santa Clara cerca de la ESPE y deja una interrupción en el Pita intermedio. Es un escenario exploratorio.';
  }
  $('branchComparison').hidden=current.id!=='reference-mdt30';
  if(joint){
   $('maximum').checked=true;
   $('intro').textContent='Compara en el mismo mapa los recorridos por el Pita y Santa Clara. Pulsa reproducir para ver cómo avanzan desde las fuentes.';
   $('noticeTitle').textContent='Dos simulaciones en un mapa';
   $('noticeText').textContent='El azul corresponde a la corrida con terreno municipal y el naranja a la corrida inicial. Ambos resultados usan el mismo reloj. Esta comparación muestra el alcance de cada corrida.';
   $('story').textContent='Se dibujan las celdas con 5 cm de flujo o más. El tono claro indica que ambas corridas se superponen. Usa las vistas individuales para consultar espesor y velocidad.';
   $('branchComparison').hidden=true;
   $('studyResults').hidden=true;
   $('singleMetrics').hidden=true;
   $('singleResults').hidden=true;
   $('ordinaryLegend').hidden=true;
   $('jointLegend').hidden=false;
   $('espeStatus').textContent='Santa Clara toca el campus al minuto 95:45 en la corrida inicial. La municipal toca el lado cercano al Pita al 102:15.';
   route();
  }
  update();}
 function hierarchy(coords){return new C.PolygonHierarchy(C.Cartesian3.fromDegreesArray(coords[0].slice(0,-1).flatMap(p=>[p[0],p[1]])),coords.slice(1).map(r=>new C.PolygonHierarchy(C.Cartesian3.fromDegreesArray(r.slice(0,-1).flatMap(p=>[p[0],p[1]])))));}
 async function buildings(){const json=await compressed(meta.buildings);const instances=[];for(const f of json.features){const p=f.properties,polygons=f.geometry.type==='MultiPolygon'?f.geometry.coordinates:[f.geometry.coordinates];for(const coords of polygons){if(coords[0].length<4)continue;const g=new C.PolygonGeometry({polygonHierarchy:hierarchy(coords),height:p.base_m,extrudedHeight:p.base_m+p.height_m,vertexFormat:C.PerInstanceColorAppearance.VERTEX_FORMAT});instances.push(new C.GeometryInstance({geometry:g,id:{building:true,text:fmt(p.floors,0)+' pisos · '+fmt(p.height_m,1)+' m de altura estimada. '+p.height_origin+'. No es una evaluación de daño.'},attributes:{color:C.ColorGeometryInstanceAttribute.fromColor(C.Color.fromCssColorString('#d4cfc3'))}}));}}
  buildingMesh=viewer.scene.primitives.add(new C.Primitive({geometryInstances:instances,appearance:new C.PerInstanceColorAppearance({translucent:false,closed:true}),asynchronous:true}));buildingMesh.show=$('buildings').checked;$('buildingStatus').textContent=fmt(json.features.length,0)+' construcciones municipales. Alturas aproximadas: 3 m por piso; '+fmt(meta.buildings.unknown_floors,0)+' sin dato de pisos usan un piso supuesto.';viewer.scene.requestRender();}
 try{
  $(joint?'switchJoint':archive?'switchSantaClara':'switchPita').setAttribute('aria-current','page');
  C=await window.laharCesiumReady;
  const manifest=await fetch(root+(archive?'manifest-cop30.json':'manifest.json'),{cache:'no-store'});
  if(!manifest.ok)throw Error('No se encontró la ficha del escenario');
  meta=await manifest.json();[corners,terrain,regional]=await Promise.all([compressed(meta.geometry,Float32Array),compressed(meta.terrain,Uint16Array),compressed(meta.regional,Int16Array)]);if(corners.length!==meta.cell_count*12||terrain.length!==meta.terrain.rows*meta.terrain.cols)throw Error('Geometría incompleta');
  if(joint){
   const response=await fetch(root+'manifest-cop30.json');
   if(!response.ok)throw Error('No se encontró la corrida de Santa Clara');
   const other=await response.json(),caseData=other.cases[0],n=other.cell_count;
   if(meta.times_s.length!==other.times_s.length||meta.times_s.some((time,i)=>time!==other.times_s[i]))throw Error('Los relojes de las corridas difieren');
   const [cells,states,peak]=await Promise.all([compressed(other.geometry,Float32Array),
    compressed(caseData,Int32Array),compressed(caseData.max_asset,Float32Array)]);
   if(cells.length!==n*12||peak.length!==n*3)throw Error('Datos incompletos de Santa Clara');
   secondary={corners:cells,data:decodeFrames(states,n,caseData.frame_count),maxima:peak,n,palette:[copernicusOrange]};
  }
  const scheme=new C.GeographicTilingScheme(),provider=new C.CustomHeightmapTerrainProvider({width:64,height:64,tilingScheme:scheme,credit:meta.adaptation?.terrain?.model_file==='municipal_hybrid_30m.tif'?'MDT GAD Rumiñahui · Copernicus GLO-30 © DLR/Airbus · UE/ESA · SRTM/Mapzen':meta.adaptation?'Copernicus GLO-30 © DLR/Airbus · UE/ESA · contexto Mapzen · Kestrel sin calibración local':'Contexto SRTM/Mapzen · cálculo regional Kestrel sin calibrar',callback:(x,y,level)=>{const r=scheme.tileXYToRectangle(x,y,level),a=new Float32Array(4096);for(let j=0;j<64;j++)for(let i=0;i<64;i++)a[j*64+i]=elevation(C.Math.toDegrees(r.west+(r.east-r.west)*i/63),C.Math.toDegrees(r.north-(r.north-r.south)*j/63));return a;}});
  C.Ion.defaultAccessToken='';viewer=new C.Viewer('viewer',{baseLayer:new C.ImageryLayer(window.EcuadorImagery.fallback(C)),terrainProvider:provider,baseLayerPicker:false,geocoder:false,timeline:false,animation:false,homeButton:false,sceneModePicker:false,navigationHelpButton:false,fullscreenButton:false,infoBox:false,selectionIndicator:false,requestRenderMode:true});viewer.scene.globe.depthTestAgainstTerrain=true;window.EcuadorImagery.connect(viewer,C).then(()=>{
   if(coverageLayer)viewer.imageryLayers.raiseToTop(coverageLayer);
  });
  if(archive)espe();else city();
  placeLabels();
  let referenceLayer;
  const referenceSelect=$('municipalReference');
  const referenceStatus=$('municipalStatus');
  referenceSelect.onchange=()=>{
   if(referenceLayer)viewer.imageryLayers.remove(referenceLayer);
   referenceLayer=null;
   const layer=referenceSelect.value;
   referenceStatus.textContent=layer===''?'Activa una capa para consultar el escenario del GAD Rumiñahui.':
    referenceSelect.selectedOptions[0].text+' del escenario municipal. El reloj de la animación controla nuestro cálculo.';
   if(layer!==''){
    const provider=new C.WebMapServiceImageryProvider({
     url:'https://geoide.ruminahui.gob.ec/image/services/LAHAR/lahar_cotopaxi_zona_norte/MapServer/WMSServer',
     layers:layer,parameters:{transparent:true,format:'image/png',version:'1.1.1'},
     rectangle:C.Rectangle.fromDegrees(-78.577,-.712,-78.246,-.217),tileWidth:512,tileHeight:512,
     maximumLevel:15,credit:'Mapa de lahares · GAD Rumiñahui',enablePickFeatures:false
    });
    provider.errorEvent.addEventListener(()=>{
     if(referenceLayer?.imageryProvider===provider)referenceStatus.textContent='El servicio municipal no respondió. Puedes consultar el contraste por tramos.';
    });
    referenceLayer=viewer.imageryLayers.addImageryProvider(provider);
    referenceLayer.alpha=.65;
    if(coverageLayer)viewer.imageryLayers.raiseToTop(coverageLayer);
   }
   viewer.scene.requestRender();
  };
  referenceSelect.disabled=false;
  $('scenario').value=joint?'joint':meta.cases[0].id;
  $('scenario').disabled=false;
  $('scenario').onchange=()=>{
   const url=new URL(location.href);
   url.searchParams.delete('rio');
   url.searchParams.delete('vista');
   if($('scenario').value==='joint')url.searchParams.set('vista','conjunta');
   if($('scenario').value==='reference-cop30')url.searchParams.set('escenario','espe');
   else url.searchParams.delete('escenario');
   location.assign(url.href);
  };
  $('home').onclick=()=>{stop();city();};
  $('espe').onclick=()=>{stop();espe();};
  $('sanPedro').onclick=sanPedro;
  $('caldera').onclick=()=>{stop();caldera();};
  $('route').onclick=()=>{showCoverage();route();};
  $('time').max=meta.times_s.length-1;
  $('time').oninput=()=>{stop();frame=Number($('time').value);update();};
  $('maximum').onchange=()=>{stop();update();};
  $('flow').onchange=draw;
  $('buildings').onchange=()=>{
   if(buildingMesh)buildingMesh.show=$('buildings').checked;
   viewer.scene.requestRender();
  };
  $('play').onclick=()=>{if(timer)stop();else play(false);};
  $('follow').onclick=()=>{if(guided)stop();else{stop();play(true);}};
  for(const [i,source] of (meta.setup.source_references||[meta.setup.source_reference]).entries()){viewer.entities.add({position:C.Cartesian3.fromDegrees(source.model_lon,source.model_lat,elevation(source.model_lon,source.model_lat)+8),point:{pixelSize:7,color:C.Color.ORANGE,outlineColor:C.Color.WHITE,outlineWidth:1},label:i===0&&!meta.adaptation?{text:'Entrada hipotética · río Pita',font:'12px sans-serif',pixelOffset:new C.Cartesian2(0,-20),showBackground:true}:undefined});}
  viewer.screenSpaceEventHandler.setInputAction(e=>{const p=viewer.scene.pick(e.position);$('picked').hidden=!p?.id?.building;if(p?.id?.building)$('picked').textContent=p.id.text;},C.ScreenSpaceEventType.LEFT_CLICK);
  await loadCase();
  showCampus().catch(()=>{$('espeStatus').textContent='Consulta el informe para ver el perímetro y el minuto de llegada.';});
  addRiverReferences().catch(()=>{
   $('pita').title='No respondió el trazado del Pita';
   $('santaClara').title='No respondió el trazado de Santa Clara';
  });
  buildings().catch(()=>{$('buildingStatus').textContent='No se pudieron cargar los edificios. El cálculo del flujo sigue disponible.';});
 }catch(e){error(e);}
})();
