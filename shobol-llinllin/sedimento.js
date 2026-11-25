'use strict';

window.createShobolSediment = () => {
 const size=256;
 const repeatAt=(frequency,x,y)=>{
  const ix=Math.floor(x),iy=Math.floor(y);
  const fx=x-ix,fy=y-iy;
  const sx=fx*fx*(3-2*fx),sy=fy*fy*(3-2*fy);
  const sample=(a,b)=>{
   const px=(a%frequency+frequency)%frequency,py=(b%frequency+frequency)%frequency;
   let word=Math.imul(px+1,374761393)^Math.imul(py+1,668265263)^Math.imul(frequency,1442695041);
   word=Math.imul(word^(word>>>13),1274126177);
   return ((word^(word>>>16))>>>0)/4294967295;
  };
  const top=sample(ix,iy)*(1-sx)+sample(ix+1,iy)*sx;
  const bottom=sample(ix,iy+1)*(1-sx)+sample(ix+1,iy+1)*sx;
  return top*(1-sy)+bottom*sy;
 };
 const relief=new Float32Array(size*size);
 const brightness=new Float32Array(size*size);
 const sheen=new Float32Array(size*size);
 const gravel=new Float32Array(size*size);
 for(let y=0,i=0;y<size;y++){
  for(let x=0;x<size;x++,i++){
   const u=x/size,v=y/size;
   const warp=.16*(repeatAt(6,u*6,v*6)-.5);
   const folds=repeatAt(28,(u+warp)*28,v*28);
   const channels=repeatAt(16,(u+v+warp)*16,v*16);
   const washes=repeatAt(5,u*5,v*5);
   const grit=repeatAt(105,u*105,v*105);
   relief[i]=.44*folds+.30*channels+.26*washes;
   brightness[i]=.13*(grit-.5)+.12*(washes-.5);
   const thread=repeatAt(42,(u+warp)*42,(v+u)*8);
   sheen[i]=Math.max(0,thread-.63)*Math.max(0,channels-.36)*2.3;
   gravel[i]=Math.max(0,grit-.79)*Math.max(0,1.35-washes)*1.9;
  }
 }
 const createTile=(color,opacity,wetness)=>{
  const tile=document.createElement('canvas');
  tile.width=tile.height=size;
  const context=tile.getContext('2d');
  const image=context.createImageData(size,size);
  for(let y=0,i=0;y<size;y++){
   for(let x=0;x<size;x++,i++){
    const r=relief[i];
    const neighboring=relief[((y+2)%size)*size+(x+size-2)%size];
    const shadow=Math.max(0,neighboring-r);
    const grain=brightness[i]+.52*(r-.5)+.53*(r-neighboring)-.18*shadow*wetness;
    const warmth=.06*(r-.5);
    const reflected=sheen[i]*wetness;
    const stone=gravel[i]*(1-wetness)*.42;
    image.data[i*4]=color[0]*(1+grain+warmth-stone)+86*reflected;
    image.data[i*4+1]=color[1]*(1+grain-stone)+105*reflected;
    image.data[i*4+2]=color[2]*(1+grain-warmth-stone)+114*reflected;
    image.data[i*4+3]=opacity;
   }
  }
  context.putImageData(image,0,0);
  return tile;
 };
 const detail=createTile([157,97,62],87,.57);
 return {
  image:(tint,phase)=>createTile(
   tint.slice(1).match(/../g).map(hex=>parseInt(hex,16)),255,[.96,.64,.28][phase]
  ),
  paint(context,bbox){
   const [west,south,east,north]=bbox;
   const degrees=0.0023;
   const pattern=context.createPattern(detail,'repeat');
   const sx=context.canvas.width*degrees/(east-west)/size;
   const sy=context.canvas.height*degrees/(north-south)/size;
   pattern.setTransform(new DOMMatrix([sx,0,0,sy,-((west%degrees)/degrees)*size*sx,((north%degrees)/degrees)*size*sy]));
   context.save();
   context.globalCompositeOperation='source-atop';
   context.fillStyle=pattern;
   context.fillRect(0,0,context.canvas.width,context.canvas.height);
   context.restore();
  }
 };
};
