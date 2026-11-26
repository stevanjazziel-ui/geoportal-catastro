'use strict';

window.LaharVisual=(()=>{
 const sun=[-.52,-.37,.77];
 const lightLength=Math.hypot(...sun);
 const sunlight=sun.map(value=>value/lightLength);

 function canvasProvider(C,canvas,rectangle){
  const tilingScheme=new C.GeographicTilingScheme({
   rectangle,numberOfLevelZeroTilesX:1,numberOfLevelZeroTilesY:1
  });
  return {
   tilingScheme,rectangle,minimumLevel:0,maximumLevel:0,
   tileWidth:canvas.width,tileHeight:canvas.height,hasAlphaChannel:true,
   errorEvent:new C.Event(),requestImage:()=>Promise.resolve(canvas),
   getTileCredits:()=>undefined,pickFeatures:()=>undefined
  };
 }

 function hillshade(meta,heights){
  const [west,south,east,north]=meta.bbox;
  const scale=Math.min(1,1800/Math.max(meta.rows,meta.cols));
  const canvas=document.createElement('canvas');
  canvas.width=Math.round(meta.cols*scale);canvas.height=Math.round(meta.rows*scale);
  const {width,height}=canvas;
  const context=canvas.getContext('2d');
  const image=context.createImageData(width,height);
  const dx=111320*Math.cos((south+north)*Math.PI/360)*(east-west)/meta.cols;
  const dy=111130*(north-south)/meta.rows;
  const stride=Math.max(1,Math.round(1/scale));
  for(let y=1;y<height-1;y++){
   const row=Math.min(meta.rows-1-stride,Math.max(stride,Math.round((y+.5)*meta.rows/height-.5)));
   for(let x=1;x<width-1;x++){
    const col=Math.min(meta.cols-1-stride,Math.max(stride,Math.round((x+.5)*meta.cols/width-.5)));
    const source=row*meta.cols+col;
    const eastSlope=(heights[source+stride]-heights[source-stride])*meta.scale/(2*stride*dx);
    const offset=stride*meta.cols;
    const northSlope=(heights[source-offset]-heights[source+offset])*meta.scale/(2*stride*dy);
    const sunlit=(-sunlight[0]*eastSlope-sunlight[1]*northSlope+sunlight[2])/
     Math.hypot(eastSlope,northSlope,1)-sunlight[2];
    const dark=sunlit<0, target=(y*width+x)*4;
    const edge=Math.min(1,Math.min(x,y,width-1-x,height-1-y)/12);
    image.data[target]=dark?28:244;
    image.data[target+1]=dark?35:232;
    image.data[target+2]=dark?36:204;
    image.data[target+3]=Math.round(255*edge*Math.min(.27,Math.abs(sunlit)*.59));
   }
  }
  context.putImageData(image,0,0);
  return {canvas,bbox:meta.bbox};
 }

 function buildingShadows(footprints){
  if(!footprints.length)return null;
  let west=Infinity,south=Infinity,east=-Infinity,north=-Infinity;
  for(const {outline} of footprints){
   for(const [lon,lat] of outline){
    west=Math.min(west,lon);south=Math.min(south,lat);
    east=Math.max(east,lon);north=Math.max(north,lat);
   }
  }
  const margin=.0006;
  const bbox=[west-margin,south-margin,east+margin,north+margin];
  const spanX=bbox[2]-bbox[0],spanY=bbox[3]-bbox[1];
  const canvas=document.createElement('canvas');
  const imageScale=Math.min(111000,4096/Math.max(spanX,spanY));
  canvas.width=Math.ceil(spanX*imageScale);canvas.height=Math.ceil(spanY*imageScale);
  const sx=canvas.width/spanX,sy=canvas.height/spanY;
  const lonMetres=111320*Math.cos((south+north)*Math.PI/360);
  const path=new Path2D();
  function face(points){
   let area=0;
   for(let i=0;i<points.length;i++){
    const [x,y]=points[i],[nx,ny]=points[(i+1)%points.length];
    area+=x*ny-y*nx;
   }
   if(area<0)points.reverse();
   path.moveTo(...points[0]);
   for(let i=1;i<points.length;i++)path.lineTo(...points[i]);
   path.closePath();
  }
  for(const {outline,height} of footprints){
   const base=outline.slice(0,-1).map(([lon,lat])=>[(lon-bbox[0])*sx,(bbox[3]-lat)*sy]);
   const dx=-sun[0]*height/sun[2]*sx/lonMetres;
   const dy=sun[1]*height/sun[2]*sy/111130;
   const roof=base.map(([x,y])=>[x+dx,y+dy]);
   face(roof.slice());
   for(let i=0;i<base.length;i++){
    const next=(i+1)%base.length;
    face([base[i],base[next],roof[next],roof[i]]);
   }
  }
  const context=canvas.getContext('2d');
  context.fillStyle='rgba(24,28,26,.24)';
  context.filter='blur(0.65px)';
  context.fill(path);
  return {canvas,bbox};
 }

 let groundGrain;
 function paintDeposits(context,bbox){
  if(!groundGrain){
   const size=192;
   groundGrain=document.createElement('canvas');
   groundGrain.width=groundGrain.height=size;
   const tile=groundGrain.getContext('2d');
   const field=tile.createImageData(size,size);
   let seed=61417;
   for(let y=0;y<size;y++){
    for(let x=0;x<size;x++){
     seed=(Math.imul(seed,1664525)+1013904223)>>>0;
     const eta=seed/4294967296-.5;
     const u=2*Math.PI*x/size,v=2*Math.PI*y/size;
     const veins=Math.sin(8*u+3*v+1.8*Math.sin(3*v))*.24+
      Math.sin(3*u-5*v+.5*Math.sin(7*u))*.30+eta*.21;
     const i=(y*size+x)*4;
     field.data[i]=145+68*veins;field.data[i+1]=83+56*veins;
     field.data[i+2]=51+47*veins;field.data[i+3]=61+58*veins;
    }
   }
   tile.putImageData(field,0,0);
  }
  const [west,south,east,north]=bbox;
  const pattern=context.createPattern(groundGrain,'repeat');
  const size=.017;
  const sx=context.canvas.width*size/(east-west)/groundGrain.width;
  const sy=context.canvas.height*size/(north-south)/groundGrain.height;
  pattern.setTransform(new DOMMatrix([sx,0,0,sy,-(west%size)*sx*groundGrain.width/size,
   (north%size)*sy*groundGrain.height/size]));
  context.save();
  context.globalCompositeOperation='source-atop';
  context.fillStyle=pattern;
  context.fillRect(0,0,context.canvas.width,context.canvas.height);
  context.restore();
 }

 function flowTopology(cells){
  const corners=new Int32Array(cells.length/3);
  const vertices=new Map();
  for(let i=0;i<corners.length;i++){
   const key=cells[i*3]+','+cells[i*3+1];
   if(!vertices.has(key))vertices.set(key,vertices.size);
   corners[i]=vertices.get(key);
  }
  const neighbors=new Int32Array(corners.length).fill(-1);
  const edges=new Map();
  for(let i=0;i<corners.length;i++){
   const cell=i>>2,edge=i%4;
   const a=corners[i],b=corners[cell*4+(edge+1)%4];
   const key=Math.min(a,b)*vertices.size+Math.max(a,b);
   const paired=edges.get(key);
   if(paired===undefined)edges.set(key,i);
   else{
    neighbors[i]=paired>>2;
    neighbors[paired]=cell;
    edges.delete(key);
   }
  }
  return {corners,neighbors,vertexCount:vertices.size};
 }

 function flowCornerColors(topology,depth,palette,classify){
  const {corners,vertexCount}=topology;
  const sums=new Uint16Array(vertexCount*3),counts=new Uint8Array(vertexCount);
  for(let i=0;i<corners.length/4;i++){
   if(depth[i]<5)continue;
   const rgb=palette[classify(depth[i])];
   for(let edge=0;edge<4;edge++){
    const vertex=corners[i*4+edge],p=vertex*3;
    sums[p]+=rgb[0];sums[p+1]+=rgb[1];sums[p+2]+=rgb[2];
    counts[vertex]++;
   }
  }
  const colors=new Uint8Array(sums.length);
  for(let vertex=0;vertex<vertexCount;vertex++){
   const count=counts[vertex];
   if(!count)continue;
   const p=vertex*3;
   colors[p]=Math.round(sums[p]/count);
   colors[p+1]=Math.round(sums[p+1]/count);
   colors[p+2]=Math.round(sums[p+2]/count);
  }
  return colors;
 }

 function flowAppearance(C){
  return new C.PerInstanceColorAppearance({
   flat:true,translucent:true,closed:false,
   renderState:{depthTest:{enabled:true},depthMask:false,cull:{enabled:false}},
   vertexShaderSource:`
    in float batchId;
    in vec3 position3DHigh;
    in vec3 position3DLow;
    in vec4 color;
    in vec2 flowPosition;
    in vec2 cellPosition;
    in vec4 dryEdges;
    out vec4 v_color;
    out vec2 v_mud;
    out vec2 v_cell;
    flat out vec4 v_dryEdges;
    void main(){
     v_color=color;
     v_mud=flowPosition;
     v_cell=cellPosition;
     v_dryEdges=dryEdges;
     gl_Position=czm_modelViewProjectionRelativeToEye*czm_computePosition();
    }`,
   fragmentShaderSource:`
    in vec4 v_color;
    in vec2 v_mud;
    in vec2 v_cell;
    flat in vec4 v_dryEdges;
    float soilNoise(vec2 point){
     vec2 p=floor(point), f=fract(point);
     float cell=dot(p,vec2(1.0,57.0));
     vec4 h=fract(sin(vec4(cell,cell+1.0,cell+57.0,cell+58.0)*12.9898)*43758.5453);
     vec2 w=f*f*(3.0-2.0*f);
     return mix(mix(h.x,h.y,w.x),mix(h.z,h.w,w.x),w.y);
    }
    void main(){
     vec2 flow=vec2(v_mud.x+0.34*v_mud.y,0.28*v_mud.y-0.21*v_mud.x);
     float variation=soilNoise(flow*.046)-0.5;
     float breadth=max(length(dFdx(flow)),length(dFdy(flow)));
     float sharp=1.0-smoothstep(2.0,12.0,breadth);
     float ribs=soilNoise(vec2(flow.x*.12,flow.y*.64)+variation*1.85);
     float grains=(soilNoise(v_mud*.42)-0.5)*sharp;
     float sheen=pow(max(0.0,ribs-.36),2.0)*sharp;
     vec3 material=v_color.rgb*(.96+variation*.21+(ribs-.5)*.29*sharp+grains*.20);
     material+=vec3(.19,.21,.23)*sheen;
     vec4 distanceToEdge=vec4(v_cell.y,1.0-v_cell.x,1.0-v_cell.y,v_cell.x);
     vec4 fade=mix(vec4(1.0),smoothstep(vec4(0.0),vec4(.35),distanceToEdge),v_dryEdges);
     float bank=fade.x*fade.y*fade.z*fade.w;
     out_FragColor=czm_gammaCorrect(vec4(material,v_color.a*bank));
    }`
  });
 }
 return {canvasProvider,hillshade,buildingShadows,paintDeposits,flowTopology,flowCornerColors,flowAppearance};
})();
