'use strict';

window.createShobolReconstruction = async ({C,viewer,focus,leaveModel,showReconstruction}) => {
 const byId=id=>document.getElementById(id);
 const root='data/shobol/avance/';
 const load=async file=>{
  const response=await fetch(root+file);
  if(!response.ok)throw new Error('No se pudo cargar '+file);
  return response.json();
 };
 const [areaData,specification]=await Promise.all([
  load('area-recorte.geojson'),load('avance-area-campo.json')
 ]);
 const number=(value,maximumFractionDigits=2)=>Number(value).toLocaleString('es-EC',{maximumFractionDigits});
 const area=await C.GeoJsonDataSource.load(areaData,{
  clampToGround:true,stroke:C.Color.fromCssColorString('#54f5df'),strokeWidth:4,
  fill:C.Color.TRANSPARENT
 });
 area.name='Área delimitada en campo';
 const borderColor=C.Color.fromCssColorString('#54f5df');
 const mappedPolygons=[];
 const extent=C.Rectangle.fromCartesianArray(area.entities.values.flatMap(entity=>
  entity.polygon.hierarchy.getValue(C.JulianDate.now()).positions
 ));
 for(const feature of areaData.features){
  const geometry=feature.geometry;
  const polygons=geometry.type==='MultiPolygon'?geometry.coordinates:[geometry.coordinates];
  mappedPolygons.push(...polygons);
  for(const rings of polygons){
   for(const ring of rings){
    area.entities.add({polyline:{
     positions:C.Cartesian3.fromDegreesArray(ring.flatMap(point=>point.slice(0,2))),
     clampToGround:true,classificationType:C.ClassificationType.TERRAIN,
     width:3.5,material:borderColor,zIndex:8,
    }});
   }
  }
 }
 let clip;
 function clipModel(canvas,bbox){
  if(clip?.bbox!==bbox){
   const [west,south,east,north]=bbox;
   const mask=document.createElement('canvas');
   const output=document.createElement('canvas');
   mask.width=output.width=canvas.width*8;
   mask.height=output.height=canvas.height*8;
   const project=(lon,lat)=>[(lon-west)/(east-west)*mask.width,(north-lat)/(north-south)*mask.height];
   const path=new Path2D();
   for(const rings of mappedPolygons){
    for(const [first,...rest] of rings){
     path.moveTo(...project(...first));
     for(const point of rest)path.lineTo(...project(...point));
     path.closePath();
    }
   }
   const context=mask.getContext('2d');
   context.fill(path,'evenodd');
   clip={bbox,mask,output,project,path,context};
  }
  const {mask,output}=clip;
  const paint=output.getContext('2d');
  paint.clearRect(0,0,output.width,output.height);
  paint.imageSmoothingEnabled=false;
  paint.drawImage(canvas,0,0,output.width,output.height);
  paint.globalCompositeOperation='destination-in';
  paint.drawImage(mask,0,0);
  paint.globalCompositeOperation='source-over';
  return output;
 }
 function contains(lon,lat){
  return clip?.context.isPointInPath(clip.path,...clip.project(lon,lat),'evenodd');
 }
 area.show=false;
 await viewer.dataSources.add(area);
 const showArea=value=>{
  byId('reconstructionArea').checked=value;
  area.show=value;
  viewer.scene.requestRender();
 };
 byId('reconstructionArea').onchange=e=>showArea(e.currentTarget.checked);
 const play=byId('reconstructionPlay');
 const slider=byId('reconstructionStep');
 const timeline=byId('reconstructionTimeline');
 const status=byId('reconstructionStatus');
 const areaLabel='El perímetro levantado abarca '+number(specification.mapped_ha)+' ha.';
 let reconstruction, timer, stage=0, generation=0;

 async function loadReconstruction(){
  const footprint=await load('avance-area-campo.geojson');
  const layer=await C.GeoJsonDataSource.load(footprint,{
   clampToGround:true,fill:C.Color.fromCssColorString('#c97945').withAlpha(.86),
   stroke:C.Color.TRANSPARENT,
  });
  layer.name='Avance ilustrativo del área levantada';
  layer.show=false;
  const time=C.JulianDate.now();
  const shapes=layer.entities.values.map(entity=>{
   entity.show=false;
   entity.polygon.zIndex=5;
   return [entity,Number(entity.properties.stage.getValue(time))];
  });
  await viewer.dataSources.add(layer);
  return {layer,shapes,specification};
 }
 function drawStage(next){
  const {shapes,specification}=reconstruction;
  stage=Math.max(0,Math.min(next,specification.steps));
  for(const [entity,arrival] of shapes)entity.show=arrival<=stage;
  slider.value=stage;
  byId('reconstructionProgress').textContent=number(specification.covered_percent[stage],1)+
   ' % de la huella mostrada';
  viewer.scene.requestRender();
 }
 function pause(){
  clearInterval(timer);
  timer=null;
  play.textContent='Reproducir';
 }
 function playback(){
  if(timer){pause();return;}
  if(stage===reconstruction.specification.steps)drawStage(0);
  play.textContent='Pausar';
  timer=setInterval(()=>{
   drawStage(stage+1);
   if(stage===reconstruction.specification.steps)pause();
  },540);
 }
 function stopReconstruction(){
  ++generation;
  pause();
  if(!reconstruction?.layer.show)return;
  reconstruction.layer.show=false;
  timeline.hidden=true;
  status.textContent=areaLabel;
  showReconstruction(false);
  viewer.scene.requestRender();
 }
 async function startReconstruction(){
  const token=++generation;
  const button=byId('mapReconstruct');
  button.disabled=true;
  try{
   if(!reconstruction){
    status.textContent='Preparando el avance cartográfico…';
    reconstruction=await loadReconstruction();
   }
   if(token!==generation)return;
   await leaveModel();
   if(token!==generation)return;
   pause();
   showArea(true);
   const center=C.Rectangle.center(extent);
   focus(C.Math.toDegrees(center.longitude),C.Math.toDegrees(center.latitude),4850);
   showReconstruction(true);
   timeline.hidden=false;
   reconstruction.layer.show=true;
   slider.max=reconstruction.specification.steps;
   status.textContent='Los dos ramales se unen y siguen aguas abajo dentro del perímetro de '+
    number(reconstruction.specification.mapped_ha)+' ha. El ritmo de la animación es ilustrativo.';
   drawStage(1);
   playback();
  }catch(error){
   status.textContent='No se pudo cargar el avance de la huella.';
   console.error(error);
  }finally{button.disabled=false;}
 }
 byId('mapReconstruct').onclick=()=>void startReconstruction();
 play.onclick=playback;
 slider.oninput=()=>{pause();drawStage(Number(slider.value));};
 byId('reconstructionFull').onclick=()=>{pause();drawStage(reconstruction.specification.steps);};
 byId('reconstructionClose').onclick=stopReconstruction;
 status.textContent=areaLabel;
 byId('reconstructionSummary').hidden=false;
 return {startReconstruction,stopReconstruction,clipModel,contains};
};
