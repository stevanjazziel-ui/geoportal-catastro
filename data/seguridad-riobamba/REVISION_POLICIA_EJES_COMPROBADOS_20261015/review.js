"use strict";
(async function () {
  const load = async name => {const r=await fetch(name);if(!r.ok)throw Error(`${name}: ${r.status}`);return r.json();};
  const publication=await load('PUBLICACION.json').catch(()=>null);
  if(publication?.applied){
    const notice=document.querySelector('header p');
    notice.textContent='ESTUDIO PREVIO: la versi\u00f3n aprobada incorpora los ajustes finales de POL-05 y POL-17. ';
    const link=document.createElement('a');link.href=publication.viewer;link.textContent='Abrir visor actualizado';notice.appendChild(link);
    document.querySelector('.pane h2').textContent='Ubicaciones anteriores a esta revisi\u00f3n';
    document.querySelectorAll('.pane h2')[1].textContent='Estudio previo a los ajustes finales';
  }
  const [report,before,after,existing,municipal,mainRoads,localRoads,platforms,trace,routeFeatures] = await Promise.all([
    'RESULTADOS.json','POLICIA_PUBLICADA_30.geojson','PROPUESTA_POLICIA_30_REVISION.geojson',
    'EXISTENTES_103_FIJAS.geojson','MUNICIPALES_50_FIJAS.geojson','EJES_PRINCIPALES.geojson','RED_VIAL_CONTEXTO.geojson','PLATAFORMAS.geojson',
    'TRAZABILIDAD.json','ENLACES_POTENCIALES_POR_CALLES.geojson'
  ].map(load));
  const esc = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const format=(v,d=1)=>Number(v).toLocaleString('es-EC',{maximumFractionDigits:d});
  const coords=f=>[f.geometry.coordinates[1],f.geometry.coordinates[0]];
  const ids=after.features.map(f=>f.properties.ID_POLICIA).sort();
  const select=document.getElementById('camera');
  select.innerHTML=ids.map(id=>`<option>${id}</option>`).join('');
  const requestedCamera=new URLSearchParams(location.search).get('camera');
  select.value=ids.includes(requestedCamera)?requestedCamera:'POL-08';
  const maps=['before','after'].map(id=>L.map(id,{preferCanvas:true,zoomAnimation:false}));
  const continuityLayer=L.geoJSON(routeFeatures,{style:{color:'#087f8c',weight:4,opacity:.8},
    onEachFeature:(f,l)=>l.bindTooltip(`${f.properties.CAMARA_A} - ${f.properties.CAMARA_B}: ${format(f.properties.LONGITUD_POR_CALLES_M)} m por calles; cobertura potencial, no visibilidad certificada`)});
  const panes=[];
  for(let index=0;index<2;index++){
    const map=maps[index];
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);
    const image=L.imageOverlay(report.kdeImage,report.kdeBounds,{opacity:.7,interactive:false}).addTo(map);
    L.geoJSON(localRoads,{interactive:false,style:{color:'#c1cbd0',weight:1,opacity:.5}}).addTo(map);
    L.geoJSON(mainRoads,{style:{color:'#405a63',weight:3,opacity:.75},onEachFeature:(f,l)=>l.bindTooltip(`${f.properties.name} (${f.properties.highway})`)}).addTo(map);
    L.geoJSON(platforms,{interactive:false,style:{color:'#357c70',weight:1,fill:false,opacity:.5}}).addTo(map);
    const fixed=L.featureGroup();
    for(const [data,color] of [[existing,null],[municipal,'#18815b']]){
      for(const f of data.features){
        const c=color||(f.properties.REQUIERE_CAMBIO?'#8b46b5':'#246db5');
        L.circleMarker(coords(f),{radius:4,color:'#fff',weight:1,fillColor:c,fillOpacity:.9})
          .bindTooltip(f.properties.ID_CAMARA||f.properties.ID_PROPUESTA).addTo(fixed);
      }
    }
    fixed.addTo(map);
    const rings=L.featureGroup().addTo(map),markers=L.featureGroup().addTo(map);
    const dataset=index===0?before:after;
    for(const f of dataset.features){
      const id=f.properties.ID_POLICIA;
      L.circle(coords(f),{radius:200,color:'#b8940d',weight:1,fillColor:'#e8bd16',fillOpacity:.14,interactive:false}).addTo(rings);
      L.circleMarker(coords(f),{radius:6,color:'#fff',weight:2,fillColor:'#e8bd16',fillOpacity:1})
        .bindTooltip(id,{permanent:false,className:'camera-label'}).on('click',()=>{select.value=id;focus();}).addTo(markers);
    }
    panes.push({image,fixed,rings,highlight:L.featureGroup().addTo(map)});
  }
  continuityLayer.addTo(maps[1]);
  function focus(){
    const id=select.value;
    const old=before.features.find(f=>f.properties.ID_POLICIA===id);
    const next=after.features.find(f=>f.properties.ID_POLICIA===id);
    const p=next.properties;
    const history=trace.byCamera[id];
    const bounds=L.latLngBounds([coords(old),coords(next)]).pad(.7);
    maps.forEach((map,i)=>{
      map.fitBounds(bounds,{maxZoom:18,animate:false,padding:[50,50]});
      panes[i].highlight.clearLayers();
      L.polyline([coords(old),coords(next)],{color:'#983e62',weight:2,dashArray:'5 4',interactive:false}).addTo(panes[i].highlight);
      L.circleMarker(coords(i===0?old:next),{radius:9,color:'#183c4a',weight:2,fillColor:'#e8bd16',fillOpacity:1})
        .bindTooltip(id,{permanent:true,direction:'top',className:'camera-label'}).addTo(panes[i].highlight);
    });
    for(const neighborId of history.linkedPoliceNeighbors){
      const neighbor=after.features.find(f=>f.properties.ID_POLICIA===neighborId);
      L.circleMarker(coords(neighbor),{radius:7,color:'#087f8c',weight:2,fillColor:'#e8bd16',fillOpacity:1})
        .bindTooltip(neighborId,{permanent:true,direction:'top',className:'camera-label'}).addTo(panes[1].highlight);
    }
    document.getElementById('case').innerHTML=`<strong>${esc(id)}</strong> &middot; ${esc(p.CRUCE)} &middot; desplazamiento: <strong>${format(p.DESPLAZAMIENTO_M,2)} m</strong> &middot; ${p.GRADO_NODO} brazos &middot; ${esc(p.JERARQUIA_OSM)} &middot; pendiente de revisi&oacute;n`;
    document.getElementById('selectedChain').textContent=`${id}: ${history.linkedPoliceNeighbors.length ? `enlaces potenciales con ${history.linkedPoliceNeighbors.join(', ')}` : history.note}. No se garantiza continuidad visual.`;
    document.getElementById('chainView').disabled=!history.linkIds.length;
    document.getElementById('history').innerHTML='<table><thead><tr><th>Versi&oacute;n</th><th>Hito</th><th>X / Y (UTM)</th><th>Desplazamiento previo</th><th>Fuente</th></tr></thead><tbody>'+history.history.map(h=>`<tr><td>${esc(h.FECHA_VERSION)}</td><td>${esc(h.HITO)}</td><td>${format(h.X,2)} / ${format(h.Y,2)}</td><td>${h.DESPLAZAMIENTO_DESDE_HITO_ANTERIOR_M==null?'--':format(h.DESPLAZAMIENTO_DESDE_HITO_ANTERIOR_M,2)+' m'}</td><td><a href="../${esc(h.FUENTE)}" title="${esc(h.FUENTE)}" target="_blank" rel="noopener">Fuente</a></td></tr>`).join('')+'</tbody></table>';
    document.querySelectorAll('[data-camera-row]').forEach(row=>row.classList.toggle('selected',row.dataset.cameraRow===id));
  }
  select.addEventListener('change',focus);
  document.getElementById('overview').addEventListener('click',()=>maps.forEach(map=>map.fitBounds(L.geoJSON(platforms).getBounds(),{padding:[15,15],animate:false})));
  document.getElementById('chainView').addEventListener('click',()=>{
    const ids=new Set(trace.byCamera[select.value].linkIds);
    const selected={type:'FeatureCollection',features:routeFeatures.features.filter(f=>ids.has(f.properties.ID_ENLACE))};
    const bounds=L.geoJSON(selected).getBounds();
    if(bounds.isValid())maps.forEach(map=>map.fitBounds(bounds,{padding:[30,30],maxZoom:17,animate:false}));
  });
  document.getElementById('continuity').addEventListener('change',e=>e.target.checked?continuityLayer.addTo(maps[1]):maps[1].removeLayer(continuityLayer));
  for(const [id,key] of [['kde','image'],['fixed','fixed'],['radii','rings']]){
    document.getElementById(id).addEventListener('change',event=>maps.forEach((map,i)=>event.target.checked?panes[i][key].addTo(map):map.removeLayer(panes[i][key])));
  }
  const compare=report.comparison;
  document.getElementById('traceSummary').textContent=`${trace.historyRows} registros de historial (${trace.historyVersions} versiones por ID). ${trace.potentialLinks} enlaces potenciales por calles; ${trace.linksNeedingOtherCameraCoverage} requieren apoyo de otros radios. ${trace.isolatedFromOtherPoliceInThisControl.length} policiales sin enlace comprobado a otra policial en este control. Esto no determina aislamiento respecto a todas las existentes y municipales. Solo se ilustran rutas potencialmente cubiertas; no seguimiento visual verificado.`;
  const rows=[
    ['KDE Delincuencia cubierto',100*compare.kdeBefore.DELINCUENCIA,100*compare.kdeAfter.DELINCUENCIA,'%'],
    ['KDE Violencia cubierto',100*compare.kdeBefore.VIOLENCIA,100*compare.kdeAfter.VIOLENCIA,'%'],
    ['Eventos Delincuencia cubiertos',compare.eventsBefore.DELINCUENCIA,compare.eventsAfter.DELINCUENCIA,''],
    ['Eventos Violencia cubiertos',compare.eventsBefore.VIOLENCIA,compare.eventsAfter.VIOLENCIA,''],
    ['&Aacute;rea Hot Spot Delincuencia cubierta',100*compare.hotspotBefore.DELINCUENCIA,100*compare.hotspotAfter.DELINCUENCIA,'%'],
    ['&Aacute;rea Hot Spot Violencia cubierta',100*compare.hotspotBefore.VIOLENCIA,100*compare.hotspotAfter.VIOLENCIA,'%'],
    ...report.corridorsSecondaryOnly.map(r=>[r.corridor,r.beforePct,r.afterPct,'%'])
  ];
  document.getElementById('metrics').innerHTML='<table><thead><tr><th>Indicador &middot; sistema completo</th><th>Publicado</th><th>Alternativa</th></tr></thead><tbody>'+rows.map(([label,a,b,unit])=>`<tr><td>${label}</td><td>${format(a,2)}${unit}</td><td>${format(b,2)}${unit}</td></tr>`).join('')+'</tbody></table>';
  document.getElementById('summary').textContent=`30 policiales; 103 existentes y 50 municipales fijas. ${report.candidateCount} cruces candidatos. Desplazamiento medio ${format(report.displacements.meanM)} m; máximo ${format(report.displacements.maxM)} m. KDE y Gi* del visor no se modifican. La alternativa requiere revisar pérdidas de cobertura y desplazamientos extensos antes de aplicar.`;
  document.getElementById('moves').innerHTML=after.features.map(f=>{
    const p=f.properties;
    return `<tr data-camera-row="${esc(p.ID_POLICIA)}"><td><button type="button" data-camera="${esc(p.ID_POLICIA)}">${esc(p.ID_POLICIA)}</button></td><td>${esc(p.CRUCE)}</td><td>${format(p.DESPLAZAMIENTO_M,2)} m</td><td>${esc(p.EJE_PRINCIPAL)}</td><td>${esc(p.OSM_IDS)}</td></tr>`;
  }).join('');
  document.querySelectorAll('[data-camera]').forEach(button=>button.addEventListener('click',()=>{select.value=button.dataset.camera;focus();document.getElementById('case').scrollIntoView({block:'start'});}));
  focus();
})().catch(error=>{document.getElementById('case').textContent=`No se pudo cargar la revisión: ${error.message}`;console.error(error);});
