'use strict';
window.EcuadorImagery=(()=>{
 let state='Esri · respaldo',version=0;
 function status(text){state=text;const e=document.getElementById('imageryStatus');if(e)e.textContent='Imagen 3D: '+text;}
 function fallback(C){return new C.UrlTemplateImageryProvider({url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',maximumLevel:18,credit:'Imagen de respaldo © Esri y proveedores'});}
 async function connect(viewer,C){
  const cfg=window.ECUADOR_IMAGERY_CONFIG||{},token=String(cfg.accessToken||'').trim(),key=String(cfg.apiKey||'').trim(),request=++version;
  const google=cfg.provider==='google-ion'||cfg.provider==='google-maps';
  const name=google?'Google Satellite':'Bing Maps Aerial';
  if((cfg.provider==='google-maps'&&!key)||(cfg.provider!=='google-maps'&&!token)){
   status('Esri · '+name+' pendiente de configurar');return false;
  }
  status('conectando '+name+'…');
  let provider;
  try{
   if(google){
    if(!C.Google2DImageryProvider)throw Error('Actualizar Cesium para Google Satellite');
    const options={mapType:'satellite',language:'es',region:'EC'};
    if(cfg.provider==='google-maps')provider=await C.Google2DImageryProvider.fromUrl({...options,key});
    else{
     if(!Number.isInteger(cfg.assetId)||cfg.assetId<=0)throw Error('Falta la capa Google de la cuenta');
     C.Ion.defaultAccessToken=token;
     provider=await C.Google2DImageryProvider.fromIonAssetId({...options,assetId:cfg.assetId});
    }
   }else if(C.IonImageryProvider.fromAssetId){
    provider=await C.IonImageryProvider.fromAssetId(cfg.assetId||2,{accessToken:token});
   }else{
    provider=new C.IonImageryProvider({assetId:cfg.assetId||2,accessToken:token});
    await provider.readyPromise;
   }
   if(request!==version||viewer.isDestroyed())return false;
   const layer=viewer.imageryLayers.addImageryProvider(provider);
   status(name+(cfg.provider==='google-maps'?' · Google Maps Platform':' · Cesium ion'));
   // Preserve the existing imagery while the authorized provider loads.
   let notified=false;
   provider.errorEvent.addEventListener(()=>{if(notified)return;notified=true;status(name+' · error de carga; respaldo disponible');});
   viewer.scene.requestRender();
   return layer;
  }catch(_){
   if(request===version)status('Esri · no se pudo conectar '+name);
   // Do not echo provider errors: URLs may contain an access token.
   viewer.scene.requestRender();return false;
  }
 }
 return {fallback,connect,get status(){return state;}};
})();
