'use strict';
let cesiumView=null,cesiumMesh=null,cesiumCity=null;
function cesiumStart(){
 if(cesiumView)return cesiumView;
 const C=Cesium;C.Ion.defaultAccessToken='';
 cesiumView=new C.Viewer('plot',{imageryProvider:new C.UrlTemplateImageryProvider({url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',credit:'Imagery © Esri y proveedores'}),terrainProvider:new C.EllipsoidTerrainProvider(),baseLayerPicker:false,geocoder:false,timeline:false,animation:false,homeButton:true,sceneModePicker:true,navigationHelpButton:true,fullscreenButton:false,infoBox:false,selectionIndicator:false,requestRenderMode:true});
 cesiumView.scene.globe.depthTestAgainstTerrain=true;
 cesiumView.scene.screenSpaceCameraController.minimumZoomDistance=100;
 cesiumView.homeButton.viewModel.command.beforeExecute.addEventListener(e=>{e.cancel=true;cesiumCity=null;drawCesiumTerrain();});
 cesiumView.screenSpaceEventHandler.setInputAction(ev=>{const p=cesiumView.scene.pick(ev.position);if(p?.id?.cityId)selectCity(p.id.cityId,true);},C.ScreenSpaceEventType.LEFT_CLICK);
 return cesiumView;
}
function drawCesiumTerrain(){
 if(!detailData||!selected)return;
 if(typeof Cesium==='undefined'){toast('No se pudo cargar Cesium. Comprueba la conexión.');return;}
 const C=Cesium,v=cesiumStart(),sim=activeSimulation,d=sim||detailData,n=d.n,b=d.bbox,depth=sim?sim.frames[simFrame]:null;
 const points=new Float64Array(n*n*3),rgba=new Uint8Array(n*n*4),indices=[];
 const palette=[[80,140,160],[105,150,113],[221,181,102],[203,125,92],[153,161,151]];
 for(let y=0;y<n;y++)for(let x=0;x<n;x++){
  const i=y*n+x,z=d.dem[y][x],h=depth?depth[y][x]:simMode==='hand'&&d.hand[y][x]!==null?Math.max(0,water-d.hand[y][x]):0;
  const p=C.Cartesian3.fromDegrees(b[0]+(x+.5)*(b[2]-b[0])/n,b[3]-(y+.5)*(b[3]-b[1])/n,z+(h>=.05?h:0));
  points.set([p.x,p.y,p.z],i*3);
  const c=h>=.05?[25,Math.round(165-65*Math.min(h/2,1)),Math.round(215-55*Math.min(h/2,1))]:sim?[140,164,116]:palette[d.class[y][x]];
  rgba.set([...c,h>=.05?175:sim||simMode==='hand'?0:85],i*4);
  if(y<n-1&&x<n-1){const k=i;indices.push(k,k+n,k+1,k+1,k+n,k+n+1);}
 }
 const geometry=new C.Geometry({attributes:{position:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.DOUBLE,componentsPerAttribute:3,values:points}),color:new C.GeometryAttribute({componentDatatype:C.ComponentDatatype.UNSIGNED_BYTE,componentsPerAttribute:4,normalize:true,values:rgba})},indices:new Uint32Array(indices),primitiveType:C.PrimitiveType.TRIANGLES,boundingSphere:C.BoundingSphere.fromVertices(points)});
 const appearance=new C.PerInstanceColorAppearance({flat:true,translucent:true,closed:false,renderState:{depthTest:{enabled:true},depthMask:false,cull:{enabled:false}},vertexShaderSource:'in float batchId; in vec3 position3DHigh; in vec3 position3DLow; in vec4 color; out vec4 v_color; void main(){vec4 p=czm_computePosition();v_color=color;gl_Position=czm_modelViewProjectionRelativeToEye*p;}'});
 if(cesiumMesh)v.scene.primitives.remove(cesiumMesh);
 cesiumMesh=v.scene.primitives.add(new C.Primitive({geometryInstances:new C.GeometryInstance({geometry}),appearance,asynchronous:false,allowPicking:false}));
 if(cesiumCity!==selected.id||v.__terrainGrid!==n){
  v.__terrainGrid=n; const scheme=new C.GeographicTilingScheme(),heights=d.dem,box=b.slice(),size=n;
  v.terrainProvider=new C.CustomHeightmapTerrainProvider({width:32,height:32,tilingScheme:scheme,credit:'Relieve local Mapzen · resolución de simulación ~153 m',callback:(tx,ty,level)=>{
   const rect=scheme.tileXYToRectangle(tx,ty,level),out=new Float32Array(1024);
   for(let iy=0;iy<32;iy++)for(let ix=0;ix<32;ix++){
    const lon=C.Math.toDegrees(rect.west+(rect.east-rect.west)*ix/31),lat=C.Math.toDegrees(rect.north-(rect.north-rect.south)*iy/31);
    if(lon<box[0]||lon>box[2]||lat<box[1]||lat>box[3])continue;
    const gx=Math.max(0,Math.min(size-1,(lon-box[0])/(box[2]-box[0])*size-.5)),gy=Math.max(0,Math.min(size-1,(box[3]-lat)/(box[3]-box[1])*size-.5));
    const x0=Math.floor(gx),y0=Math.floor(gy),x1=Math.min(x0+1,size-1),y1=Math.min(y0+1,size-1),fx=gx-x0,fy=gy-y0;
    out[iy*32+ix]=(heights[y0][x0]*(1-fx)+heights[y0][x1]*fx)*(1-fy)+(heights[y1][x0]*(1-fx)+heights[y1][x1]*fx)*fy;
   }return out;
  }});
  v.entities.removeAll();
  for(const c of catalog)v.entities.add({cityId:c.id,name:c.name,position:C.Cartesian3.fromDegrees(c.lon,c.lat,(c.elevation_median||0)+30),point:{pixelSize:c.id===selected.id?9:6,color:C.Color.fromCssColorString(colors[c.priority]),outlineColor:C.Color.WHITE,outlineWidth:2,disableDepthTestDistance:Number.POSITIVE_INFINITY},label:{text:c.name,font:'12px sans-serif',pixelOffset:new C.Cartesian2(0,-17),showBackground:true,distanceDisplayCondition:new C.DistanceDisplayCondition(0,200000)}});
  v.camera.flyToBoundingSphere(geometry.boundingSphere,{duration:0,offset:new C.HeadingPitchRange(0,-.75,geometry.boundingSphere.radius*2.8)});cesiumCity=selected.id;
 }
 v.resize();v.scene.requestRender();
 const hint=document.querySelector('.terrainhint');hint.textContent='Agua azul semitransparente · celdas simuladas ~153 m · terreno regional sin calibración';
}
renderTerrain=drawCesiumTerrain;
window.drawCesiumTerrain=drawCesiumTerrain;
window.addEventListener('resize',()=>{if(cesiumView){cesiumView.resize();cesiumView.scene.requestRender();}});
document.addEventListener('fullscreenchange',()=>{if(cesiumView)cesiumView.resize();});
if(view==='terrain'&&detailData)drawCesiumTerrain();
