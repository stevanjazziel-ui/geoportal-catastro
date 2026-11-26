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

 let groundGrain, fineGrain;
 function grainNoise(u,v,columns,rows){
  const x=u*columns,y=v*rows,ix=Math.floor(x),iy=Math.floor(y);
  const fx=x-ix,fy=y-iy;
  const sx=fx*fx*(3-2*fx),sy=fy*fy*(3-2*fy);
  const sample=(a,b)=>{
   const px=(a%columns+columns)%columns,py=(b%rows+rows)%rows;
   let hash=Math.imul(px+983,374761393)^Math.imul(py+173,668265263)^Math.imul(columns,1274126177);
   hash=Math.imul(hash^(hash>>>13),1442695041);
   return ((hash^(hash>>>16))>>>0)/4294967295;
  };
  const near=sample(ix,iy)*(1-sx)+sample(ix+1,iy)*sx;
  const far=sample(ix,iy+1)*(1-sx)+sample(ix+1,iy+1)*sx;
  return near*(1-sy)+far*sy;
 }
 function paintDeposits(context,bbox){
  if(!groundGrain){
   const size=256;
   groundGrain=document.createElement('canvas');
   groundGrain.width=groundGrain.height=size;
   const tile=groundGrain.getContext('2d');
   const field=tile.createImageData(size,size);
   for(let y=0;y<size;y++){
    for(let x=0;x<size;x++){
     const u=x/size,v=y/size;
     const warp=(grainNoise(u,v,6,6)-.5)*.22;
     const bed=grainNoise(u+warp,v+u,20,9)-.5;
     const ripples=grainNoise(u+warp,v+u,46,19)-.5;
     const patches=grainNoise(u,v,8,8)-.5;
     const grit=grainNoise(u,v,102,102)-.5;
     const tone=1.1*bed+.53*ripples+.39*patches+.23*grit;
     const wet=Math.max(0,bed-.17)*Math.max(0,ripples+.1)*2.1;
     const i=(y*size+x)*4;
     const shadow=tone<0;
     field.data[i]=shadow?70:234;
     field.data[i+1]=shadow?36:181;
     field.data[i+2]=shadow?24:122;
     field.data[i+3]=Math.min(105,Math.abs(tone)*(shadow?136:78)+wet*71);
    }
   }
   tile.putImageData(field,0,0);
  }
  if(!fineGrain){
   const size=160;
   fineGrain=document.createElement('canvas');
   fineGrain.width=fineGrain.height=size;
   const tile=fineGrain.getContext('2d');
   const field=tile.createImageData(size,size);
   for(let y=0;y<size;y++){
    for(let x=0;x<size;x++){
     const u=x/size,v=y/size;
     const warp=(grainNoise(u,v,6,6)-.5)*.17;
     const strand=grainNoise(u+warp,v+u,40,12)-.5;
     const stone=grainNoise(u,v,92,92)-.5;
     const tone=.72*strand+.48*stone;
     const glint=Math.max(0,strand-.21)*Math.max(0,stone+.16);
     const shade=tone<0,i=(y*size+x)*4;
     field.data[i]=shade?49:238;
     field.data[i+1]=shade?33:201;
     field.data[i+2]=shade?21:158;
     field.data[i+3]=Math.min(104,Math.abs(tone)*(shade?165:117)+glint*118);
    }
   }
   tile.putImageData(field,0,0);
  }
  const [west,south,east,north]=bbox;
  context.save();
  context.globalCompositeOperation='source-atop';
  const degreesPerPixel=Math.max((east-west)/context.canvas.width,(north-south)/context.canvas.height);
  for(const [grain,size] of [[groundGrain,.012],[fineGrain,.0013]]){
   const pattern=context.createPattern(grain,'repeat');
   const sx=context.canvas.width*size/(east-west)/grain.width;
   const sy=context.canvas.height*size/(north-south)/grain.height;
   pattern.setTransform(new DOMMatrix([sx,0,0,sy,-(west%size)*sx*grain.width/size,
    (north%size)*sy*grain.height/size]));
   context.globalAlpha=grain===fineGrain?.70*Math.min(1,.000027/degreesPerPixel):1;
   context.fillStyle=pattern;
   context.fillRect(0,0,context.canvas.width,context.canvas.height);
  }
  context.restore();
 }

 const cornerCut=.39;

 function exteriorSides(topology,depth,cell){
  const first=cell*4;
  return Array.from({length:4},(_,corner)=>{
   const neighbor=topology.neighbors[first+corner];
   return neighbor<0||depth[neighbor]<5?1:0;
  });
 }

 function roundedCorners(topology,counts,cell,exterior){
  return exterior.map((side,corner)=>
   side&&exterior[(corner+3)%4]&&counts[topology.corners[cell*4+corner]]===1?1:0
  );
 }

 function cellBounds(cells,index){
  let west=Infinity,south=Infinity,east=-Infinity,north=-Infinity;
  for(let j=index*12;j<index*12+12;j+=3){
   const lon=cells[j],lat=cells[j+1];
   west=Math.min(west,lon);east=Math.max(east,lon);
   south=Math.min(south,lat);north=Math.max(north,lat);
  }
  return [west,south,east,north];
 }

 function traceCell(path,points,turns){
  for(let corner=0;corner<4;corner++){
   const [x,y]=points[corner];
   const [px,py]=points[(corner+3)%4];
   const cut=turns[corner]*cornerCut;
   const startX=x+(px-x)*cut,startY=y+(py-y)*cut;
   if(corner===0)path.moveTo(startX,startY);
   else path.lineTo(startX,startY);
   if(cut){
    const [nx,ny]=points[(corner+1)%4];
    path.quadraticCurveTo(x,y,x+(nx-x)*cut,y+(ny-y)*cut);
   }
  }
  path.closePath();
 }

 function coverageProvider(C,bbox,cells,topology,depth,colors,classify){
  const rectangle=C.Rectangle.fromDegrees(...bbox);
  const tilingScheme=new C.GeographicTilingScheme({
   rectangle,numberOfLevelZeroTilesX:1,numberOfLevelZeroTilesY:1
  });
  const size=512,padding=22,buckets=64;
  const index=new Map();
  const reference=new Uint8Array(topology.vertexCount);
  const wet=[];
  for(let i=0;i<cells.length/12;i++){
   if(depth[i]<5)continue;
   wet.push(i);
   for(let j=0;j<4;j++)reference[topology.corners[i*4+j]]++;
  }
  const bucket=(value,start,end)=>
   Math.min(buckets-1,Math.max(0,Math.floor((value-start)/(end-start)*buckets)));
  const forBuckets=([w,s,e,n],visit)=>{
   const left=bucket(w,bbox[0],bbox[2]),right=bucket(e,bbox[0],bbox[2]);
   const bottom=bucket(s,bbox[1],bbox[3]),top=bucket(n,bbox[1],bbox[3]);
   for(let y=bottom;y<=top;y++){
    for(let x=left;x<=right;x++)visit(y*buckets+x);
   }
  };
  for(const i of wet){
   const bounds=cellBounds(cells,i);
   const feature={i,bounds,tone:classify(depth[i]),
    turns:roundedCorners(topology,reference,i,exteriorSides(topology,depth,i))};
   forBuckets(bounds,id=>{
    if(!index.has(id))index.set(id,[]);
    index.get(id).push(feature);
   });
  }
  const layer=document.createElement('canvas'),buffer=document.createElement('canvas');
  layer.width=layer.height=buffer.width=buffer.height=size+2*padding;
  const ink=layer.getContext('2d'),paint=buffer.getContext('2d');
  const empty=document.createElement('canvas');
  empty.width=empty.height=size;
  function tile(x,y,level){
   const {west,south,east,north}=tilingScheme.tileXYToNativeRectangle(x,y,level);
   const dx=(east-west)/size,dy=(north-south)/size;
   const padded=[west-padding*dx,south-padding*dy,east+padding*dx,north+padding*dy];
   const paths=colors.map(()=>new Path2D()),seen=new Set();
   forBuckets(padded,id=>{
    for(const feature of index.get(id)||[]){
     if(seen.has(feature.i))continue;
     const [w,s,e,n]=feature.bounds;
     if(w>padded[2]||e<padded[0]||s>padded[3]||n<padded[1])continue;
     seen.add(feature.i);
     const points=Array.from({length:4},(_,j)=>{
      const p=feature.i*12+j*3;
      return [(cells[p]-padded[0])/dx,(padded[3]-cells[p+1])/dy];
     });
     traceCell(paths[feature.tone],points,feature.turns);
    }
   });
   if(!seen.size)return Promise.resolve(empty);
   ink.clearRect(0,0,layer.width,layer.height);
   paint.clearRect(0,0,buffer.width,buffer.height);
   const envelope=new Path2D();
   for(const [i,path] of paths.entries()){
    ink.fillStyle=`rgb(${colors[i].slice(0,3).join(',')})`;
    ink.fill(path);
    envelope.addPath(path);
   }
   // Blend adjacent colors slightly and clip the result to the rounded wet footprint.
   const radius=Math.min(7.2,Math.max(.25,.000046/Math.max(dx,dy)));
   paint.filter=`blur(${radius}px)`;
   paint.drawImage(layer,0,0);
   paint.filter='none';
   ink.clearRect(0,0,layer.width,layer.height);
   ink.fill(envelope);
   paint.globalCompositeOperation='destination-in';
   paint.drawImage(layer,0,0);
   paint.globalCompositeOperation='source-over';
   paintDeposits(paint,padded);
   const result=document.createElement('canvas');
   result.width=result.height=size;
   result.getContext('2d').drawImage(buffer,padding,padding,size,size,0,0,size,size);
   return Promise.resolve(result);
  }
  return {
   tilingScheme,rectangle,minimumLevel:0,maximumLevel:7,tileWidth:size,tileHeight:size,
   hasAlphaChannel:true,errorEvent:new C.Event(),requestImage:tile,
   getTileCredits:()=>undefined,pickFeatures:()=>undefined
  };
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
  return {colors,counts};
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
    in vec3 cellColor;
    in vec2 flowPosition;
    in vec2 cellPosition;
    in vec4 dryEdges;
    in vec4 cutCorners;
    out vec4 v_color;
    out vec2 v_mud;
    out vec2 v_cell;
    flat out vec4 v_dryEdges;
    flat out vec4 v_cutCorners;
    flat out vec3 v_cellColor;
    void main(){
     v_color=color;
     v_mud=flowPosition;
     v_cell=cellPosition;
     v_dryEdges=dryEdges;
     v_cutCorners=cutCorners;
     v_cellColor=cellColor;
     gl_Position=czm_modelViewProjectionRelativeToEye*czm_computePosition();
    }`,
   fragmentShaderSource:`
    in vec4 v_color;
    in vec2 v_mud;
    in vec2 v_cell;
    flat in vec4 v_dryEdges;
    flat in vec4 v_cutCorners;
    flat in vec3 v_cellColor;
    float soilNoise(vec2 point){
     vec2 p=floor(point), f=fract(point);
     float cell=dot(p,vec2(1.0,57.0));
     vec4 h=fract(sin(vec4(cell,cell+1.0,cell+57.0,cell+58.0)*12.9898)*43758.5453);
     vec2 w=f*f*(3.0-2.0*f);
     return mix(mix(h.x,h.y,w.x),mix(h.z,h.w,w.x),w.y);
    }
    float roundBank(vec2 distances){
     const float radius=${cornerCut.toFixed(2)};
     float d=length(max(vec2(radius)-distances,vec2(0.0)));
     return 1.0-smoothstep(radius-.035,radius+.012,d);
    }
    void main(){
     vec2 flow=vec2(v_mud.x+0.34*v_mud.y,0.28*v_mud.y-0.21*v_mud.x);
     float variation=soilNoise(flow*.046)-0.5;
     float breadth=max(length(dFdx(flow)),length(dFdy(flow)));
     float sharp=1.0-smoothstep(2.0,12.0,breadth);
     float ribs=soilNoise(vec2(flow.x*.12,flow.y*.64)+variation*1.85);
     float grains=(soilNoise(v_mud*.42)-0.5)*sharp;
     vec4 distanceToEdge=vec4(v_cell.y,1.0-v_cell.x,1.0-v_cell.y,v_cell.x);
     float nearestEdge=min(min(distanceToEdge.x,distanceToEdge.y),min(distanceToEdge.z,distanceToEdge.w));
     float transition=1.0-smoothstep(.06,.25,nearestEdge);
     vec3 sediment=mix(v_cellColor,v_color.rgb,transition);
     float streak=soilNoise(vec2(flow.x*.046,flow.y*.38)+variation*1.4)-0.5;
     float sheen=pow(max(0.0,ribs-.47),2.0)*sharp;
     vec3 material=sediment*(.94+variation*.25+streak*.28+(ribs-.5)*.23*sharp+grains*.24);
     material+=vec3(.23,.24,.25)*sheen;
     vec4 fade=mix(vec4(1.0),smoothstep(vec4(0.0),vec4(.12),distanceToEdge),v_dryEdges);
     vec4 rounded=vec4(roundBank(distanceToEdge.wx),roundBank(distanceToEdge.xy),
      roundBank(distanceToEdge.yz),roundBank(distanceToEdge.zw));
     float bank=fade.x*fade.y*fade.z*fade.w;
     rounded=mix(vec4(1.0),rounded,v_cutCorners);
     bank*=rounded.x*rounded.y*rounded.z*rounded.w;
     out_FragColor=czm_gammaCorrect(vec4(material,v_color.a*bank));
    }`
  });
 }
 return {canvasProvider,hillshade,buildingShadows,coverageProvider,flowTopology,flowCornerColors,
  exteriorSides,roundedCorners,flowAppearance};
})();
