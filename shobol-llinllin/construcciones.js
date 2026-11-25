'use strict';

window.createShobolBuildings = (C, data, elevation) => {
 const origin=C.Cartesian3.fromDegrees(-78.805,-1.598);
 const axes=C.Transforms.eastNorthUpToFixedFrame(origin);
 const [east,north,up]=[0,4,8].map(i=>new C.Cartesian3(axes[i],axes[i+1],axes[i+2]));
 const encoded=C.EncodedCartesian3.fromCartesian(origin);
 const vec=({x,y,z})=>`vec3(${x.toFixed(8)},${y.toFixed(8)},${z.toFixed(8)})`;
 const styleAttribute=values=>new C.GeometryInstanceAttribute({
  componentDatatype:C.ComponentDatatype.FLOAT,componentsPerAttribute:4,value:values
 });
 const instances=[];
 for(const {geometry,properties} of data.features){
  const height=Number(properties.height_m);
  if(!Number.isFinite(height)||height<=0)continue;
  const polygons=geometry.type==='MultiPolygon'?geometry.coordinates:[geometry.coordinates];
  const signature=Array.from(properties.id).reduce((hash,char)=>Math.imul(hash,31)+char.charCodeAt(0),0);
  const seed=(Math.imul(signature,1540483477)>>>0)/4294967296;
  const paint=C.Color.fromCssColorString(properties.roof_color||'#888d87');
  for(const [outer,...holes] of polygons){
   if(outer.length<4)continue;
   const positions=ring=>ring.slice(0,-1).map(([lon,lat])=>C.Cartesian3.fromDegrees(lon,lat));
   const shell=positions(outer);
   const heights=outer.slice(0,-1).map(([lon,lat])=>elevation(lon,lat)).sort((a,b)=>a-b);
   const anchor=heights[Math.floor(heights.length/2)];
   const base=heights[0]-.35;
   const top=Math.max(heights.at(-1)+.7,anchor+height);
   let longest=0, angle=0;
   for(let i=0;i<shell.length;i++){
    const edge=C.Cartesian3.subtract(shell[(i+1)%shell.length],shell[i],new C.Cartesian3());
    const length=C.Cartesian3.magnitudeSquared(edge);
    if(length<=longest)continue;
    longest=length;
    angle=Math.atan2(C.Cartesian3.dot(edge,north),C.Cartesian3.dot(edge,east));
   }
   const floorModule=height/Math.max(1,Math.round(height/2.85));
   instances.push(new C.GeometryInstance({
    id:{building:properties},
    geometry:new C.PolygonGeometry({
     polygonHierarchy:new C.PolygonHierarchy(shell,holes.map(ring=>new C.PolygonHierarchy(positions(ring)))),
     height:base,extrudedHeight:top,closeBottom:false,
     vertexFormat:C.PerInstanceColorAppearance.VERTEX_FORMAT
    }),
    attributes:{color:C.ColorGeometryInstanceAttribute.fromColor(paint),
     surfaceStyle:styleAttribute([anchor,seed,floorModule,angle])}
   }));
  }
 }
 const appearance=new C.PerInstanceColorAppearance({
  closed:true,translucent:false,
  vertexShaderSource:`
   in vec3 position3DHigh;
   in vec3 position3DLow;
   in vec3 normal;
   in vec4 color;
   in float batchId;
   out vec3 v_surface;
   out vec3 v_normal;
   flat out vec3 v_roof;
   flat out vec3 v_style;
   const vec3 east=${vec(east)}, north=${vec(north)}, up=${vec(up)};

   void main(){
    vec3 offset=(position3DHigh-${vec(encoded.high)})+(position3DLow-${vec(encoded.low)});
    vec2 local=vec2(dot(offset,east),dot(offset,north));
    vec4 style=czm_batchTable_surfaceStyle(batchId);
    float curvature=dot(local,local)/12756274.0;
    v_surface=vec3(local,dot(offset,up)+curvature-style.x);
    v_normal=vec3(dot(normal,east),dot(normal,north),dot(normal,up));
    v_roof=color.rgb;
    v_style=style.yzw;
    gl_Position=czm_modelViewProjectionRelativeToEye*czm_computePosition();
   }
  `,
  fragmentShaderSource:`
   in vec3 v_surface;
   in vec3 v_normal;
   flat in vec3 v_roof;
   flat in vec3 v_style;

   float randomCell(vec2 p){
    return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);
   }

   float surfaceNoise(vec2 p){
    vec2 cell=floor(p), f=fract(p);
    vec2 w=f*f*(3.0-2.0*f);
    return mix(mix(randomCell(cell),randomCell(cell+vec2(1,0)),w.x),
      mix(randomCell(cell+vec2(0,1)),randomCell(cell+vec2(1,1)),w.x),w.y);
   }

   float stripe(float x,float width){
    float fuzzy=clamp(fwidth(x),0.004,0.25);
    return 1.0-smoothstep(width-fuzzy,width+fuzzy,abs(fract(x)-0.5));
   }

   void main(){
    vec3 n=normalize(v_normal);
    float shade=0.67+0.33*max(0.0,dot(n,normalize(vec3(-0.55,0.28,0.79))));
    float seed=v_style.x;
    if(n.z>0.6){
     vec2 ridge=vec2(cos(v_style.z),sin(v_style.z));
     vec2 roof=vec2(dot(v_surface.xy,ridge),dot(v_surface.xy,vec2(-ridge.y,ridge.x)));
     float ceramic=smoothstep(0.08,0.22,v_roof.r-v_roof.b);
     float span=mix(0.76,0.31,ceramic);
     float sheet=roof.y/span;
     float ribDetail=1.0-smoothstep(0.13,0.76,fwidth(sheet));
     float ribShade=stripe(sheet-0.055,0.049)*ribDetail;
     float ribLight=stripe(sheet+0.055,0.049)*ribDetail;
     float tilePhase=roof.x/0.46+0.5*mod(floor(sheet),2.0);
     float tileDetail=1.0-smoothstep(0.18,0.8,fwidth(tilePhase));
     float joints=stripe(tilePhase,0.07)*ceramic*tileDetail;
     float colorShift=(randomCell(vec2(0.0,floor(sheet)))-0.5)*ribDetail;
     float streaks=surfaceNoise(roof*vec2(0.28,1.6)+seed*7.0)-0.5;
     float grit=surfaceNoise(roof*2.3)-0.5;
     float weather=surfaceNoise(roof*0.37+seed*9.0)-0.5;
     vec3 finish=v_roof*(0.97+0.22*weather+0.14*streaks+0.10*grit+
      0.11*colorShift+0.15*ribLight-0.24*ribShade-0.14*joints);
     out_FragColor=czm_gammaCorrect(vec4(finish*shade,1.0));
     return;
    }
    vec2 tangent=normalize(vec2(-n.y,n.x));
    vec2 wall=vec2(dot(tangent,v_surface.xy),v_surface.z);
    float brick=smoothstep(0.66,0.87,seed);
    vec3 plaster=mix(vec3(0.59,0.60,0.55),vec3(0.88,0.82,0.70),seed);
    plaster=mix(plaster,vec3(0.61,0.37,0.29),brick*0.78);
    vec2 panel=vec2(wall.x/mix(2.7,3.9,seed)+seed,wall.y/v_style.y+0.04);
    float closeUp=1.0-smoothstep(0.16,0.65,max(fwidth(panel.x),fwidth(panel.y)));
    float windowVariant=randomCell(floor(panel)+vec2(seed*21.0,floor(n.x*4.0)));
    float windowWidth=mix(0.15,0.25,windowVariant);
    float frame=stripe(panel.x,windowWidth+0.032)*stripe(panel.y,0.223);
    float glazing=stripe(panel.x,windowWidth)*stripe(panel.y,0.186);
    float mullion=max(stripe(panel.x,0.012),stripe(panel.y-0.055,0.012)*0.76);
    float sill=stripe(panel.x,windowWidth+0.047)*stripe(panel.y+0.222,0.017);
    float upperShade=stripe(panel.y-0.164,0.038);
    float paneLight=mix(0.78,1.35,smoothstep(0.16,0.73,fract(panel.y)))*(1.0-0.19*upperShade);
    vec3 glass=mix(vec3(0.16,0.22,0.23),vec3(0.29,0.34,0.34),windowVariant)*paneLight;
    float entrance=step(0.84,windowVariant)*step(0.0,wall.y)*(1.0-smoothstep(0.69,0.74,wall.y/v_style.y));
    float door=entrance*stripe(panel.x,0.145)*closeUp;
    vec2 masonry=vec2(wall.x/0.32+0.5*mod(floor(wall.y/0.13),2.0),wall.y/0.13);
    float joints=max(stripe(masonry.x,0.04),stripe(masonry.y,0.05));
    float mortar=brick*joints*(1.0-smoothstep(0.18,0.9,length(fwidth(masonry))));
    float patina=0.86+0.20*surfaceNoise(wall*vec2(0.52,0.43)+seed*14.0);
    float stain=surfaceNoise(wall*vec2(1.2,0.24)+seed*28.0)-0.5;
    float pores=(surfaceNoise(wall*7.5)-0.5)*(1.0-smoothstep(0.1,0.8,length(fwidth(wall*7.5))));
    float masonryTone=(randomCell(floor(masonry))-0.5)*brick;
    vec3 facade=mix(plaster*(patina+0.15*stain+0.11*pores+0.14*masonryTone),
     vec3(0.73,0.65,0.54),mortar*0.67);
    facade*=mix(0.68,1.0,smoothstep(-0.15,0.72,wall.y));
    facade=mix(facade,vec3(0.46,0.44,0.39),sill*closeUp*0.63);
    facade=mix(facade,vec3(0.44,0.41,0.35),frame*closeUp*(1.0-entrance)*0.86);
    facade=mix(facade,glass,glazing*closeUp*(1.0-entrance)*(1.0-0.48*mullion));
    facade=mix(facade,vec3(0.31,0.29,0.26)*(0.9+0.17*stain),door);
    out_FragColor=czm_gammaCorrect(vec4(facade*shade,1.0));
   }
  `
 });
 return new C.Primitive({geometryInstances:instances,appearance,asynchronous:true});
};
