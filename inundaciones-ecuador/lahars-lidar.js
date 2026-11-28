'use strict';
window.attachLidarReferences = (viewer, C, orderSurfaceLayers) => {
 const $ = id => document.getElementById(id);
 const path = 'data/sangolqui-lahars/referencia-lidar/';
 const controls = {relief: $('lidarRelief'), profiles: $('lidarProfiles'), bridges: $('lidarBridges')};
 const entries = new Map();
 let data, imagery;

 const format = n => n.toLocaleString('es-EC', {maximumFractionDigits: 2});
 const color = hex => C.Color.fromCssColorString(hex);
 const riverColor = name => color(name === 'Pita' ? '#66e9fb' : '#f9ace9');
 const layers = {
  async relief() {
   const provider = await C.SingleTileImageryProvider.fromUrl(path + 'relieve.webp', {
    rectangle: C.Rectangle.fromDegrees(...data.relief.bounds),
    credit: 'Relieve derivado del LiDAR municipal de Rumiñahui, 2024'
   });
   imagery = viewer.imageryLayers.addImageryProvider(provider);
   imagery.alpha = .84;
   orderSurfaceLayers();
   return imagery;
  },
  async profiles() {
   const group = new C.CustomDataSource('Perfiles LiDAR');
   for (const row of data.profiles) {
    group.entities.add({name: row.id, properties: {lidarRecord: row},
     polyline: {positions: C.Cartesian3.fromDegreesArray(row.line.flat()), width: 3,
      material: riverColor(row.river), clampToGround: true, classificationType: C.ClassificationType.TERRAIN}});
   }
   return viewer.dataSources.add(group);
  },
  async bridges() {
   const group = new C.CustomDataSource('Puentes revisados');
   for (const row of data.bridges) {
    group.entities.add({name: row.name, position: C.Cartesian3.fromDegrees(...row.point),
     properties: {lidarRecord: row}, point: {heightReference: C.HeightReference.CLAMP_TO_GROUND,
      pixelSize: 10, color: color('#fff0b3'), outlineColor: color('#4a330e'),
      outlineWidth: 2, disableDepthTestDistance: Infinity}});
   }
   return viewer.dataSources.add(group);
  }
 };

 function plot(row, canvas) {
  const values = row.levels.filter(z => z !== null);
  const min = Math.floor(Math.min(...values));
  const span = Math.max(1, Math.ceil(Math.max(...values)) - min);
  const ctx = canvas.getContext('2d');
  const left = 42, right = canvas.width - 14, top = 12, bottom = canvas.height - 24;
  const x = i => left + i * (right-left) / (row.levels.length-1);
  const y = z => bottom - (z-min) * (bottom-top) / span;
  ctx.fillStyle = '#f3f6f4';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#dce6e7';
  ctx.fillRect(x(54), top, x(66)-x(54), bottom-top);
  ctx.strokeStyle = '#98abae';
  ctx.strokeRect(left, top, right-left, bottom-top);
  ctx.font = '12px system-ui';
  ctx.fillStyle = '#20373d';
  ctx.fillText(format(min+span), 2, top+6);
  ctx.fillText(format(min), 2, bottom);
  ctx.fillText('−120 m', left, bottom+17);
  ctx.fillText('0', x(60)-3, bottom+17);
  ctx.fillText('+120 m', right-44, bottom+17);
  ctx.strokeStyle = '#116171';
  ctx.lineWidth = 2;
  ctx.beginPath();
  let gap = true;
  row.levels.forEach((z,i) => {
   if(z === null) {gap = true; return;}
   if(gap) ctx.moveTo(x(i), y(z)); else ctx.lineTo(x(i), y(z));
   gap = false;
  });
  ctx.stroke();
  ctx.fillStyle = '#116171';
  row.levels.forEach((z,i) => {if(z !== null) ctx.fillRect(x(i)-1, y(z)-1, 2, 2);});
  canvas.setAttribute('aria-label', 'Perfil de terreno entre ' + format(Math.min(...values)) +
   ' y ' + format(Math.max(...values)) + ' metros en la referencia interna del LiDAR.');
 }

 async function sync(key) {
  const control = controls[key];
  if (!control.checked && !entries.has(key)) return;
  control.disabled = true;
  try {
   if (!data) {
    const response = await fetch(path + 'capas.json');
    if (!response.ok) throw new Error('Datos LiDAR indisponibles');
    data = await response.json();
   }
   if (!entries.has(key)) entries.set(key, await layers[key]());
   entries.get(key).show = control.checked;
   const status = controls.profiles.checked || controls.bridges.checked
    ? 'Selecciona un perfil o un puente en el mapa para consultar sus datos.'
    : controls.relief.checked ? 'Los vacíos muestran zonas sin suelo observado en el LiDAR.'
    : 'Activa una capa para verla en el mapa.';
   $('lidarStatus').textContent = status;
  } catch (error) {
   control.checked = false;
   $('lidarStatus').textContent = 'No se pudo cargar esta capa. Vuelve a activarla para reintentar.';
   console.warn(error);
  } finally {
   control.disabled = false;
   viewer.scene.requestRender();
  }
 }
 for (const key of Object.keys(controls)) {
  controls[key].disabled = false;
  controls[key].addEventListener('change', () => { void sync(key); });
 }
 return {
  raiseRelief() { if (imagery) viewer.imageryLayers.raiseToTop(imagery); },
  pick(entity) {
   const row = entity?.properties?.lidarRecord?.getValue(viewer.clock.currentTime);
   if (!row) return;
   $('lidarReference').open = true;
   $('lidarInfo').hidden = false;
   const canvas = $('lidarProfileChart');
   canvas.hidden = !row.levels;
   $('lidarName').textContent = row.levels ? 'Río ' + row.river + ' · ' + row.id : row.name;
   $('lidarDescription').textContent = row.levels
    ? 'Cotas internas del LiDAR (m). Muestras por margen: ' + row.banks.join(' y ') + '. Los huecos representan falta de datos.'
    : row.source + '. ' + (row.deck === null ? 'Sin cota de tablero verificada.' :
     'Superficie candidata del tablero: ' + format(row.deck) + ' m en la referencia interna del LiDAR.') +
     ' Fondo del cauce y altura libre pendientes de verificación.';
   if (row.levels) plot(row, canvas);
  }
 };
};
