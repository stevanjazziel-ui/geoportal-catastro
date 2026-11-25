'use strict';

window.createShobolReconstruction = async ({C,viewer,focus,leaveModel,showReconstruction,palette}) => {
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
 const mappedPolygons=areaData.features.flatMap(({geometry})=>
  geometry.type==='MultiPolygon'?geometry.coordinates:[geometry.coordinates]
 );
 const locations=mappedPolygons.flatMap(([outer])=>
  outer.map(([lon,lat])=>C.Cartographic.fromDegrees(lon,lat))
 );
 const center=C.Rectangle.center(C.Rectangle.fromCartographicArray(locations));
 const sediment=window.createShobolSediment();
 const textured=C.GroundPrimitive.supportsMaterials(viewer.scene);
 const phaseColors=palette.map(tint=>C.Color.fromCssColorString(tint).withAlpha(.93));
 const phaseMaterials=palette.map((tint,index)=>textured?
  new C.ImageMaterialProperty({image:sediment.image(tint,index),transparent:true,
   color:C.Color.WHITE.withAlpha(.93)}):
  new C.ColorMaterialProperty(phaseColors[index])
 );
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
  sediment.paint(paint,bbox);
  return output;
 }
 function contains(lon,lat){
  return clip?.context.isPointInPath(clip.path,...clip.project(lon,lat),'evenodd');
 }
 const play=byId('reconstructionPlay');
 const slider=byId('reconstructionStep');
 const timeline=byId('reconstructionTimeline');
 const status=byId('reconstructionStatus');
 const areaLabel='El perímetro levantado abarca '+number(specification.mapped_ha)+' ha.';
 let reconstruction, timer, stage=0, generation=0;

 async function loadReconstruction(){
  const footprint=await load('avance-area-campo.geojson');
  const layer=await C.GeoJsonDataSource.load(footprint,{
   clampToGround:true,fill:phaseColors[0],
   stroke:C.Color.TRANSPARENT,
  });
  layer.name='Avance ilustrativo del área levantada';
  layer.show=false;
  const time=C.JulianDate.now();
  const shapes=layer.entities.values.slice().map(entity=>{
   entity.show=false;
   entity.polygon.outline=false;
   entity.polygon.zIndex=5;
   const arrivals=Number(entity.properties.stage.getValue(time));
   const phases=phaseMaterials.map((material,index)=>{
    const phase=index===0?entity:layer.entities.add({show:false,polygon:entity.polygon.clone()});
    phase.polygon.material=material;
    return phase;
   });
   return {arrival:arrivals,phases};
  });
  await viewer.dataSources.add(layer);
  return {layer,shapes,specification};
 }
 function drawStage(next){
  const {shapes,specification}=reconstruction;
  stage=Math.max(0,Math.min(next,specification.steps));
  for(const {arrival,phases} of shapes){
   const elapsed=stage-arrival;
   const phase=elapsed<0?-1:elapsed<2?0:elapsed<7?1:2;
   phases.forEach((entity,index)=>{entity.show=index===phase;});
  }
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
   focus(C.Math.toDegrees(center.longitude),C.Math.toDegrees(center.latitude),4850);
   showReconstruction(true);
   timeline.hidden=false;
   reconstruction.layer.show=true;
   slider.max=reconstruction.specification.steps;
   status.textContent='Los dos ramales se unen y siguen aguas abajo dentro del perímetro de '+
    number(reconstruction.specification.mapped_ha)+' ha. El tono claro señala el frente. El ritmo es ilustrativo.';
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
