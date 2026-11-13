'use strict';
window.EcuadorImagery=(()=>{
 let state='Esri · respaldo',version=0;
 function status(text){state=text;const e=document.getElementById('imageryStatus');if(e)e.textContent='Imagen 3D: '+text;}
 function fallback(C){return new C.UrlTemplateImageryProvider({url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',maximumLevel:18,credit:'Imagen de respaldo © Esri y proveedores'});}
 async function connect(viewer,C){
  const cfg=window.ECUADOR_IMAGERY_CONFIG||{},token=String(cfg.accessToken||'').trim(),request=++version;
  if(!token){status('Esri · Bing pendiente de configurar');return false;}
  status('conectando Bing Maps Aerial…');
  let provider;
  try{
   provider=new C.IonImageryProvider({assetId:2,accessToken:token});
   await provider.readyPromise;
   if(request!==version||viewer.isDestroyed())return false;
   const layer=viewer.imageryLayers.addImageryProvider(provider);
   status('Bing Maps Aerial · Cesium ion');
   // Keep the existing imagery underneath until Bing has loaded its tiles.
   let notified=false;
   provider.errorEvent.addEventListener(()=>{if(notified)return;notified=true;status('Bing Aerial · error de carga; respaldo disponible');});
   viewer.scene.requestRender();
   return layer;
  }catch(_){
   if(request===version)status('Esri · no se pudo autorizar Bing Aerial');
   // Do not echo provider errors: URLs may contain an access token.
   viewer.scene.requestRender();return false;
  }
 }
 return {fallback,connect,get status(){return state;}};
})();
