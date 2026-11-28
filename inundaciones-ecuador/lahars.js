'use strict';
(async()=>{
 const $=id=>document.getElementById(id),root='data/sangolqui-lahars/';
 let C;
 const params=new URLSearchParams(location.search);
 const joint=params.get('vista')==='conjunta';
 const archive=!joint&&params.get('escenario')==='espe';
 const focusPita=!joint&&!archive&&params.get('rio')==='pita';
 const campusCenter=[-78.445069,-.315230];
 let meta,viewer,corners,terrain,regional,current,data,maxima,secondary,combinedGrid,frame=0,timer,waterMesh,buildingMesh,request=0;
 let osmBuildings,supplementalBuildings,portraitBuilding,windowDetail;
 let coverageLayer, reliefLayer, shadowLayer, referenceLayer, visualGrid, lidarReferences;
 let coverageUnavailable=false, guided=false, activeView=-1;
 const riverViews=[
  {name:'Pita',button:'pita',reference:'pitaReference',color:'#9ae8ec',entities:[]},
  {name:'Santa Clara',button:'santaClara',reference:'santaReference',color:'#e2bbff',entities:[]},
 ];
 const flowColors=[[255,212,123,240],[242,150,76,245],[185,80,46,250]];
 const cellCoordinates=[[0,0],[1,0],[1,1],[0,1]];
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
 function orderSurfaceLayers(){
  for(const layer of [reliefLayer,shadowLayer]){
   if(layer)viewer.imageryLayers.raiseToTop(layer);
  }
  lidarReferences?.raiseRelief();
  for(const layer of [referenceLayer,coverageLayer]){
   if(layer)viewer.imageryLayers.raiseToTop(layer);
  }
 }
 function gradeImagery(layer){
  layer.saturation=.94;
  layer.contrast=1.045;
  layer.brightness=1.025;
 }
 function addVisualSurface({canvas,bbox}){
  const provider=LaharVisual.canvasProvider(C,canvas,C.Rectangle.fromDegrees(...bbox));
  return viewer.imageryLayers.addImageryProvider(provider);
 }
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
  const contactVisible=new C.CallbackProperty(()=>!windowDetail||
   C.Cartesian3.distanceSquared(viewer.camera.positionWC,windowDetail.aim)>34*34,false);
  for(const id of contacts){
   const contact=cases[id]?.campus_first_5cm;
   if(!contact)continue;
   const text_minutes=Math.floor(contact.seconds/60)+':'+String(contact.seconds%60).padStart(2,'0');
   const santa=id==='reference-cop30';
   const side=santa?'junto a Santa Clara':'en el extremo cercano al Pita';
   if(!joint)$('espeStatus').textContent='Primer flujo detectado '+side+', al minuto '+text_minutes+' del escenario.';
   viewer.entities.add({name:'Primer contacto calculado en el perímetro ESPE',
    position:C.Cartesian3.fromDegrees(contact.lon,contact.lat,elevation(contact.lon,contact.lat)+7),
    point:{show:contactVisible,pixelSize:8,color:C.Color.WHITE,outlineColor:C.Color.fromCssColorString('#203239'),outlineWidth:2,disableDepthTestDistance:Infinity},
    label:{show:contactVisible,text:(joint?(santa?'Santa Clara · ':'Pita · '):'Primer contacto ESPE · ')+text_minutes,font:'bold 14px Arial',showBackground:true,
     backgroundColor:C.Color.BLACK.withAlpha(.75),pixelOffset:new C.Cartesian2(0,-19),disableDepthTestDistance:Infinity,
     distanceDisplayCondition:new C.DistanceDisplayCondition(0,7500)}});
   const downstream=cases[id].segments.sanpedro5?.samples.findLast(sample=>sample[3]>=0);
   if(downstream){
    const [,lon,lat]=downstream;
    const color=C.Color.fromCssColorString(santa?riverViews[1].color:riverViews[0].color);
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
 function alignGrids(){
  const archived=new Map();
  const key=(cells,offset)=>`${cells[offset]},${cells[offset+1]}`;
  for(let i=0;i<secondary.n;i++)archived.set(key(secondary.corners,i*12),i);
  const matched=new Int32Array(meta.cell_count).fill(-1);
  for(let i=0;i<meta.cell_count;i++){
   const first=i*12, id=key(corners,first), other=archived.get(id);
   if(other===undefined)continue;
   for(let offset=0;offset<12;offset+=3){
    if(corners[first+offset]!==secondary.corners[other*12+offset]||
       corners[first+offset+1]!==secondary.corners[other*12+offset+1])throw Error('Las cuadrículas de los escenarios difieren');
   }
   matched[i]=other;
   archived.delete(id);
  }
  const cells=new Float32Array(corners.length+12*archived.size);
  cells.set(corners);
  let offset=corners.length;
  for(const id of archived.values()){
   cells.set(secondary.corners.subarray(id*12,id*12+12),offset);
   offset+=12;
  }
  return {cells,matched,remaining:Int32Array.from(archived.values())};
 }
 function depths(all){
  const offset=frame*5*meta.cell_count;
  const primary=all?maxima:data.subarray(offset,offset+meta.cell_count);
  if(!joint)return primary;
  const archivedOffset=frame*5*secondary.n;
  const other=all?secondary.maxima:secondary.data.subarray(archivedOffset,archivedOffset+secondary.n);
  const values=new Float32Array(meta.cell_count+combinedGrid.remaining.length);
  values.set(primary.subarray(0,meta.cell_count));
  combinedGrid.matched.forEach((id,i)=>{if(id>=0)values[i]=Math.max(values[i],other[id]);});
  combinedGrid.remaining.forEach((id,i)=>{values[meta.cell_count+i]=other[id];});
  return values;
 }
 function flowBounds(){
  let west=Infinity,south=Infinity,east=-Infinity,north=-Infinity;
  const cells=combinedGrid?.cells||corners;
  for(let i=0;i<cells.length;i+=3){
   west=Math.min(west,cells[i]);
   east=Math.max(east,cells[i]);
   south=Math.min(south,cells[i+1]);
   north=Math.max(north,cells[i+1]);
  }
  return [west,south,east,north];
 }
 function ensureCoverageLayer(){
  try{
   const cells=combinedGrid?.cells||corners;
   visualGrid??=LaharVisual.flowTopology(cells);
   const provider=LaharVisual.coverageProvider(C,flowBounds(),cells,visualGrid,depths(true),flowColors,depthClass);
   coverageLayer=viewer.imageryLayers.addImageryProvider(provider);
   coverageLayer.alpha=.90;
   orderSurfaceLayers();
  }catch(_){
   coverageUnavailable=true;
  }
 }
 function draw(){
  if(waterMesh){viewer.scene.primitives.remove(waterMesh);waterMesh=null;}
  const visible=Boolean(data)&&$('flow').checked;
  const all=$('maximum').checked;
  for(const entity of viewer.entities.values){
   if(entity.name==='Alcance en el San Pedro durante 150 minutos')entity.show=all&&$('flow').checked;
  }
  if(visible&&all&&!coverageLayer&&!coverageUnavailable)ensureCoverageLayer();
  if(coverageLayer)coverageLayer.show=visible&&all;
  if(!visible||(all&&coverageLayer)){viewer.scene.requestRender();return;}
  const indices=[],positions=[],colors=[],cellColors=[],surface=[],uv=[],dryEdges=[],cutCorners=[];
  const cells=combinedGrid?.cells||corners, depth=depths(all);
  visualGrid??=LaharVisual.flowTopology(cells);
  const {colors:cornerColors,counts}=LaharVisual.flowCornerColors(visualGrid,depth,flowColors,depthClass);
  const n=meta.cell_count, offset=frame*5*n;
  const textureOffset=all?0:frame*2.4;
  for(let i=0;i<cells.length/12;i++){
    if(depth[i]<5)continue;
    const zOffset=all||joint?2:data[offset+4*n+i]/100+1.5;
    const rgba=flowColors[depthClass(depth[i])],k=positions.length/3;
    const [red,green,blue]=rgba;
    const first=i*4;
    const dry=LaharVisual.exteriorSides(visualGrid,depth,i);
    const rounded=LaharVisual.roundedCorners(visualGrid,counts,i,dry);
    let cx=0,cy=0,cz=0,mx=0,my=0;
    for(let j=0;j<4;j++){
     const g=(i*4+j)*3, lon=cells[g],lat=cells[g+1];
     const p=C.Cartesian3.fromDegrees(lon,lat,elevation(lon,lat)+zOffset);
     const colorIndex=visualGrid.corners[first+j]*3;
     positions.push(p.x,p.y,p.z);
     colors.push(cornerColors[colorIndex],cornerColors[colorIndex+1],cornerColors[colorIndex+2],rgba[3]);
     cellColors.push(red,green,blue);
     const x=(lon+78.44)*111300,y=(lat+.33)*111130+textureOffset;
     surface.push(x,y);uv.push(...cellCoordinates[j]);dryEdges.push(...dry);cutCorners.push(...rounded);
     cx+=p.x;cy+=p.y;cz+=p.z;mx+=x;my+=y;
    }
    positions.push(cx/4,cy/4,cz/4);colors.push(...rgba);
    cellColors.push(red,green,blue);
    surface.push(mx/4,my/4);uv.push(.5,.5);dryEdges.push(...dry);cutCorners.push(...rounded);
    indices.push(k,k+1,k+4,k+1,k+2,k+4,k+2,k+3,k+4,k+3,k,k+4);
  }
  if(positions.length){
   const p=new Float64Array(positions);
   const geometry=new C.Geometry({attributes:{
    position:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.DOUBLE,componentsPerAttribute:3,values:p}),
    color:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.UNSIGNED_BYTE,componentsPerAttribute:4,
     normalize:true,values:new Uint8Array(colors)}),
    cellColor:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.UNSIGNED_BYTE,componentsPerAttribute:3,
     normalize:true,values:new Uint8Array(cellColors)}),
    cellPosition:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.FLOAT,componentsPerAttribute:2,
     values:new Float32Array(uv)}),
    dryEdges:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.UNSIGNED_BYTE,componentsPerAttribute:4,
     values:new Uint8Array(dryEdges)}),
    cutCorners:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.UNSIGNED_BYTE,componentsPerAttribute:4,
     values:new Uint8Array(cutCorners)}),
    flowPosition:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.FLOAT,componentsPerAttribute:2,
     values:new Float32Array(surface)})
   },indices:new Uint32Array(indices),primitiveType:C.PrimitiveType.TRIANGLES,
   boundingSphere:C.BoundingSphere.fromVertices(p)});
   waterMesh=viewer.scene.primitives.add(new C.Primitive({geometryInstances:new C.GeometryInstance({geometry}),
    appearance:LaharVisual.flowAppearance(C),asynchronous:false,allowPicking:false}));
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
   $('noticeText').textContent='Ambas corridas usan el mismo reloj y la misma escala de espesores. En las celdas donde coinciden se muestra el mayor espesor calculado de las dos.';
   $('story').textContent='Las líneas discontinuas identifican los cauces del Pita y Santa Clara. Las vistas individuales muestran los resultados completos de cada corrida.';
   $('branchComparison').hidden=true;
   $('studyResults').hidden=true;
   $('singleMetrics').hidden=true;
   $('singleResults').hidden=true;
   $('espeStatus').textContent='Santa Clara toca el campus al minuto 95:45 en la corrida inicial. La municipal toca el lado cercano al Pita al 102:15.';
   route();
  }
  update();}
 function hierarchy(coords){return new C.PolygonHierarchy(C.Cartesian3.fromDegreesArray(coords[0].slice(0,-1).flatMap(p=>[p[0],p[1]])),coords.slice(1).map(r=>new C.PolygonHierarchy(C.Cartesian3.fromDegreesArray(r.slice(0,-1).flatMap(p=>[p[0],p[1]])))));}
 function illustratedWindow(feature,local,axes,seed,anchor,floorHeight){
  if(feature.osmId!=='w832825964')return null;
  // The marked pane is near the south end of the east facade.
  const [north,south]=feature.geometry.coordinates[0].slice(0,2).map(([lon,lat])=>
   C.Matrix4.multiplyByPoint(local,C.Cartesian3.fromDegrees(lon,lat),new C.Cartesian3())
  );
  const length=Math.hypot(north.x-south.x,north.y-south.y);
  const tx=(north.x-south.x)/length,ty=(north.y-south.y)/length;
  const spacing=3.3;
  const panel=(south.x*tx+south.y*ty+.13*length)/spacing+seed;
  const center=(Math.floor(panel)+.5-seed)*spacing;
  const along=center-(south.x*tx+south.y*ty);
  const x=south.x+tx*along,y=south.y+ty*along;
  const z=2.555*floorHeight;
  const facing=Math.atan2(-tx,ty);
  const ground=C.Matrix4.multiplyByPoint(axes,new C.Cartesian3(x,y,0),new C.Cartesian3());
  const location=C.Cartographic.fromCartesian(ground);
  return {
   shader:[x,y,z,facing],
   aim:C.Cartesian3.fromRadians(location.longitude,location.latitude,anchor+z),
   heading:C.Math.zeroToTwoPi(Math.atan2(-ty,tx))
  };
 }
 function focusIllustratedWindow(window){
  viewer.camera.flyToBoundingSphere(new C.BoundingSphere(window.aim,.55),{
   offset:new C.HeadingPitchRange(window.heading+.10,C.Math.toRadians(-4),9.5),
   duration:1.35
  });
 }
 function buildingAppearance(atlas,axes,origin,windowPortrait){
  const encoded=C.EncodedCartesian3.fromCartesian(origin);
  const vec=({x,y,z})=>`vec3(${x.toFixed(8)},${y.toFixed(8)},${z.toFixed(8)})`;
  const axis=i=>vec(C.Cartesian3.fromElements(axes[i*4],axes[i*4+1],axes[i*4+2]));
  const appearance=new C.PerInstanceColorAppearance({translucent:false,closed:true,vertexShaderSource:`
   in vec3 position3DHigh;
   in vec3 position3DLow;
   in vec3 normal;
   in vec4 color;
   in float batchId;
   out vec3 v_surface;
   out vec3 v_normal;
   flat out vec3 v_roof;
   flat out vec3 v_style;
   flat out float v_floorRows;
   out vec2 v_roofPosition;
   flat out vec3 v_roofRegion;
   flat out vec4 v_window;
   const vec3 east=${axis(0)}, north=${axis(1)}, up=${axis(2)};

   void main(){
    vec3 local=(position3DHigh-${vec(encoded.high)})+(position3DLow-${vec(encoded.low)});
    vec2 horizontal=vec2(dot(local,east),dot(local,north));
    vec4 style=czm_batchTable_surfaceStyle(batchId);
    float curvature=dot(horizontal,horizontal)/(2.0*6378137.0);
    v_surface=vec3(horizontal,dot(local,up)+curvature-style.x);
    v_normal=vec3(dot(normal,east),dot(normal,north),dot(normal,up));
    v_roof=color.rgb;
    v_style=style.yzw;
    v_floorRows=czm_batchTable_floorRows(batchId);
    vec4 box=czm_batchTable_roofBox(batchId);
    v_roofPosition=(horizontal-box.xy)*box.zw;
    v_roofRegion=czm_batchTable_roofRegion(batchId);
    v_window=czm_batchTable_illustratedWindow(batchId);
    gl_Position=czm_modelViewProjectionRelativeToEye*czm_computePosition();
   }
  `,fragmentShaderSource:`
   in vec3 v_surface;
   in vec3 v_normal;
   flat in vec3 v_roof;
   flat in vec3 v_style;
   flat in float v_floorRows;
   in vec2 v_roofPosition;
   flat in vec3 v_roofRegion;
   flat in vec4 v_window;
   const vec2 atlasSize=vec2(${atlas.canvas.width}.0,${atlas.canvas.height}.0);

   // Fade repeated details at a distance to keep oblique drone views stable.
   float band(float x,float halfWidth,float aa){
    return 1.0-smoothstep(halfWidth-aa,halfWidth+aa,abs(fract(x)-0.5));
   }

   float noise(vec2 p){
    vec2 i=floor(p), f=fract(p);
    vec4 phases=vec4(0.0,1.0,19.0,20.0)+dot(i,vec2(1.0,19.0));
    vec4 samples=fract(sin(phases*12.9898)*43758.5453);
    vec2 w=f*f*(3.0-2.0*f);
    return mix(mix(samples.x,samples.y,w.x),mix(samples.z,samples.w,w.x),w.y);
   }

   void main(){
    vec3 n=normalize(v_normal);
    float light=0.60+0.40*max(dot(n,normalize(vec3(-0.52,-0.37,0.77))),0.0);
    if(n.z>0.60){
     vec2 uv=clamp(v_roofPosition,0.0,1.0);
     vec2 pixel=v_roofRegion.xy+vec2(uv.x,1.0-uv.y)*max(0.0,v_roofRegion.z-1.0)+0.5;
     czm_materialInput roofInput;
     roofInput.st=vec2(pixel.x/atlasSize.x,1.0-pixel.y/atlasSize.y);
     roofInput.normalEC=vec3(0.0,0.0,1.0);
     vec3 aerial=czm_getMaterial(roofInput).diffuse;
     float detail=1.0-smoothstep(0.12,0.35,length(fwidth(v_roofPosition)));
     float nearRoof=1.0-smoothstep(0.42,2.2,length(fwidth(v_surface.xy)));
     float grain=(noise(v_surface.xy*0.92)-0.5)*0.15*nearRoof;
     float wear=(noise(v_surface.xy*0.24+v_style.y*13.0)-0.5)*0.20;
     float seam=band(v_surface.y/.83,.042,.025)*nearRoof*.11;
     vec3 roof=mix(v_roof*(0.95+grain+wear-seam),aerial,step(1.0,v_roofRegion.z)*detail*0.97);
     out_FragColor=czm_gammaCorrect(vec4(roof*(0.93+0.07*light),1.0));
     return;
    }
    float style=v_style.x, seed=v_style.y;
    vec2 tangent=vec2(-n.y,n.x)/max(length(n.xy),0.01);
    vec2 wall=vec2(dot(tangent,v_surface.xy),v_surface.z);
    float spacing=style==1.0?3.3:(style==2.0?5.4:mix(2.25,3.35,seed));
    vec2 panel=vec2(wall.x/spacing+seed,wall.y/v_style.z-0.055);
    vec2 aa=clamp(fwidth(panel),vec2(0.008),vec2(0.16));
    float detail=1.0-smoothstep(0.13,0.52,max(fwidth(panel.x),fwidth(panel.y)));
    float width=style==1.0?0.42:mix(0.22,0.35,seed);
    float windows=band(panel.x,width,aa.x)*band(panel.y,0.22,aa.y)*detail;
    float windowFrame=max(band(panel.x,0.014,aa.x),band(panel.y-.058,0.012,aa.y)*.64)*windows;
    float sill=band(panel.x,width+.051,aa.x)*band(panel.y+.235,0.018,aa.y)*detail;
    float trim=band(panel.x,width+.027,aa.x)*band(panel.y,0.244,aa.y)*detail;
    float floorEdge=band(panel.y+0.49,0.027,aa.y)*detail;
    float permitted=step(0.0,wall.y)*(1.0-step(v_floorRows,wall.y/v_style.z));
    windows*=permitted;
    windowFrame*=permitted;
    sill*=permitted;
    trim*=permitted;
    floorEdge*=permitted;
    vec3 plaster=mix(vec3(0.62,0.57,0.50),vec3(0.80,0.77,0.71),seed);
    float brick=step(0.83,seed)*(1.0-step(0.5,style));
    plaster=mix(plaster,vec3(0.57,0.36,0.28),brick*0.76);
    vec3 glass=mix(vec3(0.25,0.28,0.28),vec3(0.35,0.41,0.43),seed);
    if(style==1.0){plaster=mix(vec3(0.70,0.68,0.62),vec3(0.82,0.81,0.77),seed);glass=vec3(0.23,0.34,0.38);}
    if(style==2.0){
     plaster=mix(vec3(0.72,0.64,0.53),vec3(0.59,0.48,0.38),band(wall.y/9.0,0.084,0.022));
     windows*=1.0-smoothstep(4.0,5.0,wall.y);floorEdge*=0.30;
    }
    if(style==3.0){plaster=mix(vec3(0.54,0.57,0.55),vec3(0.75,0.72,0.65),seed);windows*=0.30;}
    float openings=noise(floor(panel)+vec2(seed*15.0,floor(n.x*4.5)));
    float reflection=smoothstep(0.20,0.78,fract(panel.y));
    glass*=mix(0.67,1.39,reflection)*mix(0.78,1.14,openings);
    vec2 masonry=vec2(wall.x/0.38+0.5*mod(floor(wall.y/0.135),2.0),wall.y/0.135);
    float mortar=band(masonry.x+0.5,0.029,0.04)+band(masonry.y+0.5,0.040,0.04);
    float closeDetail=1.0-smoothstep(0.22,0.8,length(fwidth(masonry)));
    plaster=mix(plaster,vec3(0.62,0.55,0.46),min(1.0,mortar)*brick*closeDetail*0.62);
    float weather=0.88+0.19*noise(wall*vec2(0.42,0.23)+seed*8.0);
    float stain=(noise(wall*vec2(1.4,0.34)+seed*23.0)-0.5)*.13;
    vec3 facade=plaster*(weather+stain)*(1.0-0.075*floorEdge);
    facade=mix(facade,vec3(.44,.40,.36),trim*.68);
    facade=mix(facade,glass,windows*(0.97-0.58*windowFrame));
    facade=mix(facade,plaster*.63,sill*.81);
    facade*=mix(0.72,1.0,smoothstep(0.0,1.12,wall.y));
    vec2 paneNormal=vec2(cos(v_window.w),sin(v_window.w));
    if(v_window.z>0.0&&dot(n.xy,paneNormal)>.97&&abs(dot(v_surface.xy-v_window.xy,paneNormal))<.34){
     float center=floor(dot(tangent,v_window.xy)/spacing+seed)+.5;
     const float portraitHeight=.82;
     const float portraitWidth=portraitHeight*1.40;
     float aboveSill=wall.y-v_window.z+.59;
     vec2 p=vec2((panel.x-center)*spacing/portraitWidth+.5,aboveSill/portraitHeight);
     float windowDetail=1.0-smoothstep(.065,.16,length(fwidth(vec2(wall.x/1.58,wall.y/1.13))));
     float panelInterior=windows*windowDetail*step(abs(panel.x-center),.48)*step(abs(wall.y-v_window.z),.65);
     float interior=(.75+.25*smoothstep(.0,.9,aboveSill))*panelInterior;
     facade=mix(facade,vec3(.45,.39,.28),interior*.46);
     if(p.x>0.0&&p.x<1.0&&p.y>0.0&&p.y<1.0){
      czm_materialInput portraitInput;
      portraitInput.st=vec2(-p.x,p.y);
      portraitInput.normalEC=vec3(0.0,0.0,1.0);
      czm_material portrait=czm_getMaterial(portraitInput);
      vec3 behindGlass=portrait.diffuse*vec3(.74,.77,.79)+vec3(.028,.041,.044);
      facade=mix(facade,behindGlass,portrait.alpha*panelInterior*.96);
     }
    }
    out_FragColor=czm_gammaCorrect(vec4(facade*light,1.0));
   }
  `});
  appearance.material=new C.Material({translucent:false,fabric:{
   uniforms:{roofImage:atlas.canvas,windowImage:windowPortrait||roofAtlas(null,0).canvas},
   source:`
    czm_material czm_getMaterial(czm_materialInput materialInput){
     czm_material material=czm_getDefaultMaterial(materialInput);
     vec2 st=materialInput.st;
     vec4 pixel=st.x<0.0?texture(windowImage,vec2(-st.x,st.y)):texture(roofImage,st);
     material.diffuse=pixel.rgb;
     material.alpha=pixel.a;
     return material;
    }`
  }});
  return appearance;
 }

 function roofAtlas(bytes,featureCount){
  const canvas=document.createElement('canvas');
  canvas.width=canvas.height=1;
  if(!bytes||bytes.length<4)return {canvas};
  const data=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  const width=data.getUint16(0,true),height=data.getUint16(2,true);
  const indexLength=featureCount*6;
  if(!width||!height||width>4096||height>4096||bytes.length!==4+indexLength+3*width*height)return {canvas};
  canvas.width=width;canvas.height=height;
  const context=canvas.getContext('2d');
  const image=context.createImageData(width,height);
  for(let src=4+indexLength,dst=0;dst<image.data.length;src+=3,dst+=4){
   image.data[dst]=bytes[src];image.data[dst+1]=bytes[src+1];image.data[dst+2]=bytes[src+2];image.data[dst+3]=255;
  }
  context.putImageData(image,0,0);
  return {canvas,index:feature=>{
   const p=4+feature*6;
   return [data.getUint16(p,true),data.getUint16(p+2,true),data.getUint16(p+4,true)];
  }};
 }

 function updateBuildingVisibility(){
  const shown=$('buildings').checked;
  const source=$('buildingSource').value;
  if(buildingMesh)buildingMesh.show=shown&&source!=='cesium';
  if(supplementalBuildings)supplementalBuildings.show=shown&&source==='combined';
  if(portraitBuilding)portraitBuilding.show=shown&&source==='combined';
  if(osmBuildings)osmBuildings.show=shown&&source==='cesium';
  if(shadowLayer)shadowLayer.show=shown&&source!=='cesium';
  viewer.scene.requestRender();
 }

 function cesiumBuildingMaterials(tiles,urban,status){
  const blank=new C.TextureUniform({typedArray:new Uint8Array(4),width:1,height:1,repeat:false});
  const shader=new C.CustomShader({lightingModel:C.LightingModel.UNLIT,uniforms:{
   u_photo:{type:C.UniformType.SAMPLER_2D,value:blank},
   u_region:{type:C.UniformType.VEC4,value:new C.Cartesian4(-1,-1,1,1)},
   u_anchor:{type:C.UniformType.VEC3,value:C.Cartesian3.fromDegrees(-78.44,-.33)}
  },fragmentShaderText:`
   void fragmentMain(FragmentInput fsInput,inout czm_modelMaterial material){
    vec3 p=fsInput.attributes.positionWC;
    vec3 n=normalize(czm_inverseViewRotation*fsInput.attributes.normalEC);
    vec3 up=normalize(p), east=normalize(vec3(-p.y,p.x,0.0)), north=cross(up,east);
    float roof=dot(n,up);
    float sun=0.68+0.32*max(0.0,dot(n,-0.52*east-0.37*north+0.77*up));
    float id=float(fsInput.featureIds.featureId_0);
    float hue=fract(sin(id*13.6531+1.71)*4311.531);
    vec3 finish=mix(vec3(0.60,0.55,0.49),vec3(0.80,0.77,0.70),hue);
    if(roof>0.65){
     vec2 lonlat=degrees(vec2(atan(p.y,p.x),atan(p.z,length(p.xy)*0.99330562)));
     vec2 uv=(lonlat-u_region.xy)/(u_region.zw-u_region.xy);
     if(all(greaterThanEqual(uv,vec2(0.0)))&&all(lessThanEqual(uv,vec2(1.0)))){
      vec4 photo=texture(u_photo,vec2(uv.x,1.0-uv.y));
      finish=mix(finish,photo.rgb,smoothstep(0.22,0.93,photo.a));
     }
    }else{
     vec3 wallDirection=normalize(cross(n,up));
     // Finish patterns are visual and fade as their projected size approaches one pixel.
     vec3 local=p-u_anchor;
     vec2 panel=vec2(dot(local,wallDirection)/mix(2.1,3.3,hue),dot(local,up)/3.0+hue);
     vec2 density=fwidth(panel);
     vec2 soft=clamp(density,vec2(.015),vec2(.16));
     vec2 vf=abs(fract(panel)-0.5);
     vec2 mask=1.0-smoothstep(vec2(.27,.18)-soft,vec2(.27,.18)+soft,vf);
     float nearDetail=1.0-smoothstep(.17,.51,max(density.x,density.y));
     if(hue<.24)finish=mix(finish,vec3(.52,.36,.30),.45);
     float patina=.93+.09*sin(local.x*.66+local.y*.48)*sin(local.z*.7+hue*5.0);
     float frame=1.0-smoothstep(.014-soft.x,.014+soft.x,vf.x);
     float sill=1.0-smoothstep(.022-soft.y,.022+soft.y,abs(fract(panel.y+.21)-.5));
     vec3 glass=mix(vec3(.19,.25,.27),vec3(.42,.47,.45),smoothstep(.18,.78,fract(panel.y)));
     finish=mix(finish*patina,glass,mask.x*mask.y*nearDetail*(.83-frame*.30));
     finish=mix(finish,vec3(.43,.41,.36),mask.x*sill*nearDetail*.61);
    }
    material.diffuse=pow(clamp(finish*sun,0.0,1.0),vec3(2.2));
   }`});
  tiles.customShader=shader;

  const base='https://geoide.ruminahui.gob.ec/image/rest/services/';
  const sources=['ortofoto_urbano_gadmur','otf/ortofotos_2026_preliminar_ws'];
  const cache=new Map();
  let flight,active,credited=false;
  async function capturePhoto(bounds,size,signal){
   const query=new URLSearchParams({bbox:bounds.join(','),bboxSR:'4326',imageSR:'4326',
    size:`${size},${size}`,format:'png32',transparent:'true',f:'image'});
   for(const source of sources){
    const url=base+source+'/MapServer/export?'+query;
    const response=await fetch(url,{signal});
    if(!response.ok||!response.headers.get('content-type')?.startsWith('image/'))continue;
    const photo=await createImageBitmap(await response.blob());
    const canvas=document.createElement('canvas');
    canvas.width=photo.width;canvas.height=photo.height;
    const ctx=canvas.getContext('2d',{willReadFrequently:true});
    ctx.drawImage(photo,0,0);
    photo.close();
    const data=ctx.getImageData(0,0,canvas.width,canvas.height);
    canvas.width=canvas.height=1;
    let count=0,total=0;
    for(let i=3;i<data.data.length;i+=509*4){count+=data.data[i]>200?1:0;total++;}
    if(count/total<.12)continue;
    return new C.TextureUniform({typedArray:new Uint8Array(data.data.buffer),width:data.width,height:data.height,repeat:false});
   }
   return null;
  }
  async function update(){
   if(!tiles.show)return;
   const camera=viewer.camera;
   const ray=camera.getPickRay(new C.Cartesian2(viewer.canvas.clientWidth*.5,viewer.canvas.clientHeight*.5));
   const point=ray&&viewer.scene.globe.pick(ray,viewer.scene);
   const target=point?C.Cartographic.fromCartesian(point):camera.positionCartographic;
   const lon=C.Math.toDegrees(target.longitude),lat=C.Math.toDegrees(target.latitude);
   const height=camera.positionCartographic.height-elevation(lon,lat);
   if(lon<urban[0]||lon>urban[2]||lat<urban[1]||lat>urban[3]||height>5800)return;
   const step=height<650?.007:.016,size=height<650?1792:1408;
   const x=Math.round(lon/step)*step,y=Math.round(lat/step)*step;
   const key=`${size}/${x.toFixed(4)}/${y.toFixed(4)}`;
   if(active===key||flight?.key===key)return;
   flight?.controller.abort();
   const controller=new AbortController(),request={key,controller};
   flight=request;
   try{
    const bounds=[x-step,y-step,x+step,y+step].map(v=>Number(v.toFixed(5)));
    let photo=cache.get(key);
    if(!photo){
     photo=await capturePhoto(bounds,size,controller.signal);
     if(!photo||flight!==request)return;
     cache.set(key,photo);
     if(cache.size>3)cache.delete(cache.keys().next().value);
    }
    shader.setUniform('u_photo',photo);
    shader.setUniform('u_region',new C.Cartesian4(...bounds));
    active=key;
    status.dataset.roofPhoto='ready';
    if(!credited){
     viewer.cesiumWidget.creditDisplay.addStaticCredit(new C.Credit('<a href="https://geoide.ruminahui.gob.ec/catastro/" target="_blank" rel="noopener">Ortofoto GAD Rumiñahui</a>',true));
     credited=true;
    }
    viewer.scene.requestRender();
   }catch(_){
    // A photo that cannot be read leaves the visual finish available.
   }finally{if(flight===request)flight=null;}
  }
  viewer.camera.moveEnd.addEventListener(update);
  $('buildingSource').addEventListener('change',update);
  $('buildings').addEventListener('change',update);
  void update();
 }

 async function addCesiumBuildings(){
  const controls=$('buildingSource'),status=$('buildingCesiumStatus');
  const accessToken=String(window.ECUADOR_IMAGERY_CONFIG?.accessToken||'').trim();
  if(!accessToken){status.textContent='Capa de Cesium pendiente de configurar.';return;}
  try{
   const resource=await C.IonResource.fromAssetId(96188,{accessToken});
   const tiles=await C.Cesium3DTileset.fromUrl(resource,{enableShowOutline:false,
    maximumScreenSpaceError:10,shadows:C.ShadowMode.DISABLED});
   // Compare the reference elevations of the two datasets in the urban corridor.
   // The observed median difference was about 25 m across the four urban samples.
   const center=C.Cartesian3.fromDegrees(-78.44,-.33);
   const lowered=C.Cartesian3.fromDegrees(-78.44,-.33,-25);
   tiles.modelMatrix=C.Matrix4.fromTranslation(C.Cartesian3.subtract(lowered,center,new C.Cartesian3()));
   tiles.style=new C.Cesium3DTileStyle({color:`Boolean(\${feature['cesium#color']}) ? color(\${feature['cesium#color']}) : color('#c1b9ac')`});
   const urban=[-78.508,-.402,-78.392,-.271],configured=new WeakSet();
   tiles.tileVisible.addEventListener(tile=>{
    const content=tile.content;
    if(!content.featuresLength||configured.has(content))return;
    for(let i=0;i<content.featuresLength;i++){
     const feature=content.getFeature(i);
     const lon=feature.getProperty('cesium#longitude'),lat=feature.getProperty('cesium#latitude');
     feature.show=Number.isFinite(lon)&&Number.isFinite(lat)&&lon>=urban[0]&&lon<=urban[2]&&lat>=urban[1]&&lat<=urban[3];
    }
    configured.add(content);
   });
   tiles.initialTilesLoaded.addEventListener(()=>{
    status.textContent='Cesium OSM Buildings disponible para Sangolquí y alrededores.';
   });
   tiles.tileFailed.addEventListener(()=>{
    status.textContent='Algunos bloques de Cesium tardaron en cargar. El catastro está disponible.';
   });
   osmBuildings=viewer.scene.primitives.add(tiles);
   controls.querySelector('[value=cesium]').disabled=false;
   status.textContent='Capa de Cesium disponible para comparar.';
   updateBuildingVisibility();
   if(!window.laharReel)cesiumBuildingMaterials(tiles,urban,status);
  }catch(_){status.textContent='No respondió la capa de Cesium. La vista combinada sigue disponible.';}
 }

 function floorLabel(levels,source){
  if(source==='review')return 'Pisos por verificar';
  if(!Number.isFinite(levels))return 'Pisos sin dato';
  const label=fmt(levels,0)+(levels===1?' piso':' pisos');
  if(source==='espe')return label+' según el estudio de la ESPE';
  if(source==='unverified')return label+' registrados en el catastro · por verificar';
  return label+(source==='osm'?' según OpenStreetMap':' según el catastro');
 }

 async function buildings(){
  const supportedFootprints=['c0ffe6b158443f76','46986134ccf2e9ea'];
  const hasSurfaceData=supportedFootprints.includes(meta.buildings.sha256?.slice(0,16));
  const readSurface=(file,sha256)=>hasSurfaceData?compressed({file,sha256,
   url:'https://raw.githubusercontent.com/stevanjazziel-ui/geoportal-catastro/main/inundaciones-ecuador/'+root+file},Uint8Array).catch(()=>null):null;
  const revisionFile='building-revision-20261124-v4.json.gz';
  const revisionsAsset={file:revisionFile,sha256:'ec7d036e62bca23ed23c420cee4b6a32aa176e960a81cef3820a03da571976a8',
   url:'https://raw.githubusercontent.com/stevanjazziel-ui/geoportal-catastro/main/inundaciones-ecuador/'+root+revisionFile};
  const lidarFile='building-lidar-sangolqui-20261127-v1.json.gz';
  const lidarAsset={file:lidarFile,sha256:'e0f52ddd17dc9f668f8c8c6c177a6b8677d628324380b51aaf3e238e413a939b',
   url:'https://raw.githubusercontent.com/stevanjazziel-ui/geoportal-catastro/main/inundaciones-ecuador/'+root+lidarFile};
  const auditFile='revision-integral-edificios-20261128.json.gz';
  const auditAsset={file:auditFile,sha256:'d2efe74e69cefc689bf57b8df36fee0f91ff413172d4a45282b089d9562b8661',
   url:'https://raw.githubusercontent.com/stevanjazziel-ui/geoportal-catastro/main/inundaciones-ecuador/'+root+auditFile};
  const [json,materials,roofBytes,revision,windowPortrait,lidar,roofModels,campusCorrections,fullAudit]=await Promise.all([compressed(meta.buildings),
   readSurface('building-materials-v1.bin.gz','fe7dfc426d1527db3cc0a74fd8104b7995adef018ade9b2281620f7de59cbe8d'),
   readSurface('building-roof-atlas-v2.bin.gz','4e240643a81ca5cc0be53fc6cb2bb01e92442435a7e9bc41bae492c586dc9dbc'),
   hasSurfaceData?compressed(revisionsAsset).catch(()=>null):null,
   C.Resource.fetchImage({url:root+'persona-ventana-espe.webp?v=1'}).catch(()=>null),
   hasSurfaceData?compressed(lidarAsset).catch(()=>null):null,
   hasSurfaceData?compressed({file:'cubiertas-lidar-3d-20261127-v1.json.gz',sha256:'5f84037566b3e84fd3eacfb6a4cabfc2e9a9b980702cef4d99617c710b787589',url:'https://raw.githubusercontent.com/stevanjazziel-ui/geoportal-catastro/main/inundaciones-ecuador/'+root+'cubiertas-lidar-3d-20261127-v1.json.gz'}).catch(()=>null):null,
   hasSurfaceData?fetch(root+'referencia-lidar/ajustes-espe.json').then(r=>r.ok?r.json():null).catch(()=>null):null,
   hasSurfaceData?compressed(auditAsset).catch(()=>null):null]);
  const verified=revision?.schema===1&&revision.cadastre.includes(meta.buildings.sha256)?revision:null;
  const lidarHeights=verified&&lidar?.schema===1&&lidar.revisionSha256===revisionsAsset.sha256?lidar:null;
  const audit=verified&&fullAudit?.schema===1&&fullAudit.revisionSha256===revisionsAsset.sha256&&
   fullAudit.cadastre.includes(meta.buildings.sha256)?fullAudit:null;
  const styles=materials?.length===json.features.length*5?materials:null;
  const atlas=roofAtlas(roofBytes,json.features.length);
  const origin=C.Cartesian3.fromDegrees(-78.44,-.33);
  const axes=C.Transforms.eastNorthUpToFixedFrame(origin);
  const local=C.Matrix4.inverseTransformation(axes,new C.Matrix4());
  const attr=value=>new C.GeometryInstanceAttribute({componentDatatype:C.ComponentDatatype.FLOAT,
   componentsPerAttribute:value.length,value});
  const roofs=[[164,166,160],[151,119,104],[178,180,176],[126,136,137],[172,139,121]];
  const instances=[],extraInstances=[],portraitInstances=[],shadowFootprints=[];
  const extras=verified?.extras||[];
  const duplicates=new Set(verified?.duplicateIndices||[]);
  const overlaps=new Set(verified?.overlappingMunicipal||[]);
  const auditedOverlaps=new Set(audit?.overlap||[]);
  const features=json.features.concat(extras.map(row=>({geometry:row.geometry,osmId:row.osmId,roofColor:row.color,levelState:row.levelState,campusReview:row.campusReview,
   properties:{floors:row.levels,height_m:row.height,height_origin:row.heightSource}})),
   (audit?.new||[]).map(row=>({geometry:row.geometry,osmId:row.id,roofColor:row.color,observedRoof:true,
    properties:{floors:null,height_m:row.height,height_origin:'lidar-2024'}})));
  const heightSource={'lidar-2024':'estimada con LiDAR municipal de 2024','lidar':'estimada con LiDAR municipal',
   'osm-height':'registrada en OpenStreetMap',
   'osm-levels':'estimada con los pisos de OpenStreetMap','catastro':'estimada con los pisos del catastro',approx:'aproximada para visualización'};
  let detailed=0,lidarCount=0,roofCount=0;
  for(const [index,feature] of features.entries()){
   if(duplicates.has(index))continue;
   const p=feature.properties,external=Boolean(feature.osmId),change=verified?.revisions[index];
   const buildingKey=external?feature.osmId:'cat-'+index;
   if(audit?.hide[buildingKey])continue;
   const corrected=campusCorrections?.[buildingKey];
   const geometry=corrected?.geometry??feature.geometry;
   const previousHeight=change?.[0]??p.height_m;
   const measuredHeight=external?lidarHeights?.complementary[feature.osmId]:lidarHeights?.municipal[index];
   const height=corrected?.height??measuredHeight??previousHeight;
   const auditedLevels=!corrected&&Boolean(audit?.review[buildingKey]);
   const levelSource=corrected?'espe':auditedLevels?'review':
    change?.[3]??feature.levelState??(external?'osm':p.floors>=5?'unverified':'catastro');
   const levels=corrected?.levels??(auditedLevels?null:change?change[1]:p.height_origin.includes('supuesto')?null:p.floors);
   const roof=verified&&roofModels?.[buildingKey];
   const polygons=geometry.type==='MultiPolygon'?geometry.coordinates:[geometry.coordinates];
   const offset=index*5;
   const source=styles?.[offset+3]??0;
   const style=corrected?3:feature.campusReview?1:styles?.[offset+4]??0;
   let wallHeight=height;
   if(roof?.length&&!corrected?.parts){
    const heights=roof.flatMap(([outer])=>outer.slice(0,-1).map(point=>point[2])).sort((a,b)=>a-b);
    wallHeight=Math.min(height,heights[Math.floor(heights.length*.25)]??height);
   }
   const hasIllustratedWindow=feature.osmId==='w832825964';
   const floorRows=corrected?.parts?0:hasIllustratedWindow?4:Number.isFinite(levels)?levels:0;
   const floorHeight=hasIllustratedWindow?3:floorRows>0?Math.max(.95,wallHeight/floorRows):3;
   const seed=((Math.imul(index+1,2654435761)>>>0)%997)/997;
   const rgb=feature.roofColor??(source?Array.from(styles.subarray(offset,offset+3)):roofs[Math.floor(seed*roofs.length)]);
   const color=C.ColorGeometryInstanceAttribute.fromColor(C.Color.fromBytes(...rgb));
   const region=(!external&&atlas.index?.(index))||[0,0,0];
   const roofRegion=attr(region);
   let west=Infinity,east=-Infinity,north=-Infinity,south=Infinity,low=Infinity,high=-Infinity;
   for(const polygon of polygons)for(const [lon,lat] of polygon[0]){
    west=Math.min(west,lon);east=Math.max(east,lon);south=Math.min(south,lat);north=Math.max(north,lat);
    const z=elevation(lon,lat);low=Math.min(low,z);high=Math.max(high,z);
   }
   if(!Number.isFinite(west+east+south+north))continue;
   const needsAnchor=external||p.base_m+height<=low+.25||p.base_m>high+1.5;
   const anchor=needsAnchor?elevation((west+east)/2,(south+north)/2):p.base_m;
   const base=Math.min(low-.20,anchor);
   const top=anchor+height;
   const illustration=illustratedWindow(feature,local,axes,seed,anchor,floorHeight);
   if(illustration)windowDetail=illustration;
   const attributes={color,surfaceStyle:attr([anchor,style,seed,floorHeight]),floorRows:attr([floorRows]),roofRegion,roofBox:attr([0,0,1,1]),
    illustratedWindow:attr(illustration?.shader||[0,0,0,0])};
   if(region[2]){
    const lower=C.Matrix4.multiplyByPoint(local,C.Cartesian3.fromDegrees(west,south,top),new C.Cartesian3());
    const upper=C.Matrix4.multiplyByPoint(local,C.Cartesian3.fromDegrees(east,north,top),new C.Cartesian3());
    attributes.roofBox=attr([lower.x,lower.y,1/Math.max(.05,upper.x-lower.x),1/Math.max(.05,upper.y-lower.y)]);
    detailed++;
   }
   const roofSource=region[2]?'Textura de cubierta derivada de la ortofoto municipal.':['Color de cubierta aproximado.','Color de cubierta tomado de la ortofoto municipal.',
    'Color de cubierta tomado de la ortofoto preliminar municipal de 2026.'][source];
   const reference=corrected?'lidar-2024':measuredHeight===undefined?
    (change?.[2]??(external?p.height_origin:levels===null?'approx':'catastro')):'lidar-2024';
   const campusName=corrected?.name??feature.campusReview;
   const name=campusName?campusName+' · ':'';
   const footprintSource=campusName?'Huella revisada con LiDAR, ortofoto y documentación del campus. ':
    feature.observedRoof?'Huella de Microsoft cotejada con cubierta LiDAR y ortofoto municipal. ':
    external?'Huella de OpenStreetMap. '+(feature.roofColor?'Color de cubierta de la ortofoto municipal. ':''):roofSource+' ';
   const heightReview=!corrected&&measuredHeight!==undefined&&Math.abs(height-previousHeight)>=2-1e-6?
    'Altura anterior del visor '+fmt(previousHeight,1)+' m. Diferencia por revisar. ':'';
   const id={building:true,text:name+floorLabel(levels,levelSource)+' · '+fmt(height,1)+' m de altura '+heightSource[reference]+
    '. '+footprintSource+
    (auditedLevels?'La altura medida difiere del número de pisos registrado. ':'')+heightReview+
    ((audit?auditedOverlaps.has(buildingKey):overlaps.has(index))?'Cruce con otra huella por revisar. ':'')+(corrected?.note??'Fachada aproximada.')};
   if(measuredHeight!==undefined&&polygons.some(coords=>coords[0].length>=4))lidarCount++;
   const destination=illustration?portraitInstances:external?extraInstances:instances;
   if(corrected?.parts){
    for(const part of corrected.parts){
     const positions=C.Cartesian3.fromDegreesArrayHeights(part.ring.flatMap(([lon,lat,z])=>[lon,lat,anchor+z]));
     const polygon=new C.PolygonGeometry({polygonHierarchy:new C.PolygonHierarchy(positions),perPositionHeight:true,
      extrudedHeight:part.bottom===undefined?base:anchor+part.bottom,vertexFormat:C.PerInstanceColorAppearance.VERTEX_FORMAT});
     destination.push(new C.GeometryInstance({geometry:polygon,id,attributes}));
    }
    id.text+=' Cubierta modelada con LiDAR.';
    roofCount++;
   }else if(roof?.length){
    const positions=ring=>C.Cartesian3.fromDegreesArrayHeights(ring.slice(0,-1).flatMap(
     ([lon,lat,z])=>[lon,lat,anchor+z]));
    for(const [outer,...holes] of roof){
     const polygonHierarchy=new C.PolygonHierarchy(positions(outer),holes.map(
      ring=>new C.PolygonHierarchy(positions(ring))));
     const polygon=new C.PolygonGeometry({polygonHierarchy,perPositionHeight:true,
      extrudedHeight:base,vertexFormat:C.PerInstanceColorAppearance.VERTEX_FORMAT});
     destination.push(new C.GeometryInstance({geometry:polygon,id,attributes}));
    }
    id.text+=' Cubierta modelada con LiDAR.';
    roofCount++;
   }else{
    for(const coords of polygons){
     if(coords[0].length<4)continue;
     const polygon=new C.PolygonGeometry({polygonHierarchy:hierarchy(coords),height:base,
      extrudedHeight:top,vertexFormat:C.PerInstanceColorAppearance.VERTEX_FORMAT});
     destination.push(new C.GeometryInstance({geometry:polygon,id,attributes}));
    }
   }
   if(!external&&Number.isFinite(height)&&height>0){
    for(const coords of polygons)if(coords[0].length>=4)shadowFootprints.push({outline:coords[0],height});
   }
  }
  buildingMesh=viewer.scene.primitives.add(new C.Primitive({geometryInstances:instances,
   appearance:buildingAppearance(atlas,axes,origin),asynchronous:true}));
  if(extraInstances.length){
   supplementalBuildings=viewer.scene.primitives.add(new C.Primitive({geometryInstances:extraInstances,
    appearance:buildingAppearance(roofAtlas(null,0),axes,origin),asynchronous:true,show:false}));
   viewer.cesiumWidget.creditDisplay.addStaticCredit(new C.Credit('<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap colaboradores · ODbL</a>',true));
  }
  if(audit?.new.length)viewer.cesiumWidget.creditDisplay.addStaticCredit(new C.Credit(
   '<a href="https://github.com/microsoft/GlobalMLBuildingFootprints" target="_blank" rel="noopener">Microsoft Building Footprints · CDLA Permissive 2.0</a>',true));
  if(portraitInstances.length){
   portraitBuilding=viewer.scene.primitives.add(new C.Primitive({geometryInstances:portraitInstances,
    appearance:buildingAppearance(roofAtlas(null,0),axes,origin,windowPortrait),asynchronous:false,show:false}));
  }
  const shadowImage=LaharVisual.buildingShadows(shadowFootprints);
  if(shadowImage){
   shadowLayer=addVisualSurface(shadowImage);
   orderSurfaceLayers();
  }
  $('buildingSource').disabled=false;
  updateBuildingVisibility();
  const revisionCount=Object.keys(verified?.revisions||{}).filter(index=>!duplicates.has(Number(index))).length;
  $('buildingStatus').textContent=fmt(json.features.length,0)+' bloques municipales.'+
   (lidarCount?' '+fmt(lidarCount,0)+' alturas LiDAR de 2024 aplicadas en Sangolquí.':
    revisionCount?' '+fmt(revisionCount,0)+' con altura o pisos revisados.':'')+
   (duplicates.size?' '+fmt(duplicates.size,0)+' huellas municipales repetidas representadas una sola vez.':'')+
   (roofCount?' '+fmt(roofCount,0)+' cubiertas 3D modeladas con LiDAR.':'')+
   (detailed?' '+fmt(detailed,0)+' con textura de cubierta aérea.':'')+
   (extras.length?' '+fmt(extras.length,0)+' huellas complementarias de OpenStreetMap.':'')+
   (audit?.summary.duplicados_nuevos?' '+fmt(audit.summary.duplicados_nuevos,0)+' superposiciones repetidas corregidas en Sangolquí.':'')+
   (audit?.new.length?' '+fmt(audit.new.length,0)+' edificios adicionales contrastados con LiDAR y ortofoto.':'');
  viewer.scene.requestRender();
  if(windowDetail&&params.get('detalle')==='ventana')focusIllustratedWindow(windowDetail);
  void addCesiumBuildings();
 }
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
   secondary={corners:cells,data:decodeFrames(states,n,caseData.frame_count),maxima:peak,n};
   combinedGrid=alignGrids();
  }
  const scheme=new C.GeographicTilingScheme(),provider=new C.CustomHeightmapTerrainProvider({width:64,height:64,tilingScheme:scheme,credit:meta.adaptation?.terrain?.model_file==='municipal_hybrid_30m.tif'?'MDT GAD Rumiñahui · Copernicus GLO-30 © DLR/Airbus · UE/ESA · SRTM/Mapzen':meta.adaptation?'Copernicus GLO-30 © DLR/Airbus · UE/ESA · contexto Mapzen · Kestrel sin calibración local':'Contexto SRTM/Mapzen · cálculo regional Kestrel sin calibrar',callback:(x,y,level)=>{const r=scheme.tileXYToRectangle(x,y,level),a=new Float32Array(4096);for(let j=0;j<64;j++)for(let i=0;i<64;i++)a[j*64+i]=elevation(C.Math.toDegrees(r.west+(r.east-r.west)*i/63),C.Math.toDegrees(r.north-(r.north-r.south)*j/63));return a;}});
  C.Ion.defaultAccessToken='';viewer=new C.Viewer('viewer',{baseLayer:new C.ImageryLayer(window.EcuadorImagery.fallback(C)),terrainProvider:provider,baseLayerPicker:false,geocoder:false,timeline:false,animation:false,homeButton:false,sceneModePicker:false,navigationHelpButton:false,fullscreenButton:false,infoBox:false,selectionIndicator:false,requestRenderMode:true});viewer.scene.globe.depthTestAgainstTerrain=true;
  lidarReferences=window.attachLidarReferences?.(viewer,C,orderSurfaceLayers);
  viewer.scene.globe.baseColor=C.Color.fromCssColorString('#59604f');
  gradeImagery(viewer.imageryLayers.get(0));
  void window.EcuadorImagery.connect(viewer,C).then(layer=>{
   if(layer)gradeImagery(layer);
   orderSurfaceLayers();
  });
  reliefLayer=addVisualSurface(LaharVisual.hillshade(meta.terrain,terrain));
  orderSurfaceLayers();
  if(archive)espe();else city();
  placeLabels();
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
    orderSurfaceLayers();
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
  $('buildings').onchange=updateBuildingVisibility;
  $('buildingSource').onchange=updateBuildingVisibility;
  $('play').onclick=()=>{if(timer)stop();else play(false);};
  $('follow').onclick=()=>{if(guided)stop();else{stop();play(true);}};
  for(const [i,source] of (meta.setup.source_references||[meta.setup.source_reference]).entries()){viewer.entities.add({position:C.Cartesian3.fromDegrees(source.model_lon,source.model_lat,elevation(source.model_lon,source.model_lat)+8),point:{pixelSize:7,color:C.Color.ORANGE,outlineColor:C.Color.WHITE,outlineWidth:1},label:i===0&&!meta.adaptation?{text:'Entrada hipotética · río Pita',font:'12px sans-serif',pixelOffset:new C.Cartesian2(0,-20),showBackground:true}:undefined});}
  viewer.screenSpaceEventHandler.setInputAction(e=>{
   const p=viewer.scene.pick(e.position);
   lidarReferences?.pick(p?.id);
   const osm=osmBuildings&&p?.primitive===osmBuildings;
   $('picked').hidden=!p?.id?.building&&!osm;
   if(p?.id?.building)$('picked').textContent=p.id.text;
   else if(osm){
    const height=p.getProperty('cesium#estimatedHeight');
    const tagged=p.getProperty('building:levels');
    const levels=/^[1-9]\d*$/.test(String(tagged))?Number(tagged):null;
    $('picked').textContent=floorLabel(levels,'osm')+(Number.isFinite(height)?' · '+fmt(height,1)+' m de altura estimada por Cesium.':'.');
   }
  },C.ScreenSpaceEventType.LEFT_CLICK);
  await loadCase();
  showCampus().catch(()=>{$('espeStatus').textContent='Consulta el informe para ver el perímetro y el minuto de llegada.';});
  addRiverReferences().catch(()=>{
   $('pita').title='No respondió el trazado del Pita';
   $('santaClara').title='No respondió el trazado de Santa Clara';
  });
  buildings().catch(()=>{$('buildingStatus').textContent='No se pudieron cargar los edificios. El cálculo del flujo sigue disponible.';});
 }catch(e){error(e);}
})();
