const D=window.TERRITORY,$=id=>document.getElementById(id),num=n=>new Intl.NumberFormat('es-EC').format(n),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const map=L.map('map',{preferCanvas:true}).setView([-1.66,-78.65],11);
const base=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,className:'osm-base-tiles',attribution:'© OpenStreetMap contributors'});
const diagnostic=L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:20,className:'diagnostic-base-tiles',attribution:'© OpenStreetMap contributors © CARTO'});
const satellite=L.tileLayer('https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',{subdomains:'0123',maxZoom:20,opacity:.5,attribution:'Imagery © Google'}).addTo(map);
L.control.layers({'OpenStreetMap':base,'Base diagnóstico':diagnostic,'Google Maps (satelital 50%)':satellite},null,{position:'topright'}).addTo(map);L.control.scale({imperial:false}).addTo(map);
map.createPane('platforms');map.getPane('platforms').style.zIndex=410;map.createPane('barrios');map.getPane('barrios').style.zIndex=420;
map.createPane('cabeceras');map.getPane('cabeceras').style.zIndex=430;
map.createPane('barrioLabels');map.getPane('barrioLabels').style.zIndex=680;map.getPane('barrioLabels').style.pointerEvents='none';
const fc=features=>({type:'FeatureCollection',features}),color=n=>n>=300?'#145954':n>=150?'#21877e':n>=50?'#59bba7':'#b9e5da';
const bounds=L.geoJSON(fc(D.parishes),{style:{color:'#466370',weight:1.5,fillOpacity:0,dashArray:'6 5'},interactive:false}).addTo(map).getBounds();map.fitBounds(bounds);
let groups=[],active=[];
let barrioLabelLayers=[],visibleBarrioKeys=new Set();
function renderBarrioLabels(){barrioLabelLayers.forEach(l=>map.removeLayer(l));barrioLabelLayers=[];const zoom=map.getZoom();if(!$('showBarrios').checked||zoom<14)return;
const scoped=Boolean($('platform').value),distance=scoped?(zoom>=16?58:78):(zoom>=16?78:108),limit=scoped?(zoom>=16?90:55):(zoom>=16?150:90),placed=[];
const viewport=map.getBounds().pad(scoped?.1:.18),candidates=window.BARRIOS_LABELS.filter(p=>p.area_m2>=1000&&p.source_keys.some(k=>visibleBarrioKeys.has(k))&&viewport.contains([p.lat,p.lon])).sort((a,b)=>b.area_m2-a.area_m2);
for(const p of candidates){const point=map.latLngToLayerPoint([p.lat,p.lon]);if(placed.some(other=>point.distanceTo(other)<distance))continue;placed.push(point);barrioLabelLayers.push(L.marker([p.lat,p.lon],{pane:'barrioLabels',interactive:false,keyboard:false,icon:L.divIcon({className:'barrio-label-icon',html:`<div class="barrio-label">${esc(p.name)}</div>`,iconSize:[100,28],iconAnchor:[50,14]})}).addTo(map));if(placed.length>=limit)break;}}
map.on('zoomend moveend',renderBarrioLabels);
const cabeceras=window.CABECERAS.features;
const cabecerasPrincipales=cabeceras.filter(f=>f.properties.is_cabecera);
const cabeceraCodes=new Map();
for(const f of cabecerasPrincipales){const name=f.properties.name;if(!cabeceraCodes.has(name))cabeceraCodes.set(name,new Set());for(const code of f.properties.unit_codes)cabeceraCodes.get(name).add(code);}
for(const name of [...cabeceraCodes.keys()].sort((a,b)=>a.localeCompare(b,'es'))){const o=document.createElement('option');o.value=name;o.textContent=name;$('cabecera').append(o);}
const cabeceraStyle=f=>({color:f.properties.is_cabecera?'#a04886':'#687787',weight:3,dashArray:f.properties.is_cabecera?'9 5':'3 7',fill:false});
const cabecerasLayer=L.geoJSON(fc(cabeceras),{pane:'cabeceras',interactive:false,style:cabeceraStyle}).addTo(map);
function updateCabeceras(){if($('showCabeceras').checked){if(!map.hasLayer(cabecerasLayer))cabecerasLayer.addTo(map)}else map.removeLayer(cabecerasLayer);}
function focusCabeceras(){const name=$('cabecera').value;$('showCabeceras').checked=true;updateCabeceras();cabecerasLayer.setStyle(f=>({...cabeceraStyle(f),...(name&&f.properties.name===name&&f.properties.is_cabecera?{weight:5,dashArray:''}:{})}));render();$('selection').hidden=false;$('openStats').hidden=true;const selected=cabecerasPrincipales.filter(f=>!name||f.properties.name===name);map.fitBounds(L.geoJSON(fc(selected)).getBounds().pad(.12),{maxZoom:15});}
$('showCabeceras').onchange=updateCabeceras;
$('cabecera').onchange=focusCabeceras;
$('focusCabeceras').onclick=focusCabeceras;
const cabeceraRows=[...cabeceraCodes.keys()].sort((a,b)=>a.localeCompare(b,'es')).map(name=>{const fs=cabecerasPrincipales.filter(f=>f.properties.name===name);return {name,pop:fs.reduce((s,f)=>s+f.properties.pop,0)}});
for(const row of cabeceraRows){const tr=document.createElement('tr'),nameCell=document.createElement('td'),popCell=document.createElement('td'),button=document.createElement('button');button.textContent=row.name;button.onclick=()=>{$('cabecera').value=row.name;focusCabeceras()};nameCell.append(button);popCell.textContent=num(row.pop);tr.append(nameCell,popCell);$('cabeceraTable').append(tr);}
$('cabecerasTotal').textContent=num(cabeceraRows.reduce((s,row)=>s+row.pop,0))+' hab. referenciales';

for(const id of ['parish','platform']){const key=id==='parish'?'parish':'name';const source=id==='parish'?D.units:D.platforms;[...new Set(source.map(f=>f.properties[key]))].filter(Boolean).sort((a,b)=>a.localeCompare(b,'es')).forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;$(id).append(o)});}
function render(fit=false){groups.forEach(g=>map.removeLayer(g));groups=[];const zone=$('zone').value,parish=$('parish').value,platform=$('platform').value,q=$('search').value.trim().toLocaleLowerCase('es'),cabecera=$('cabecera').value,codes=cabeceraCodes.get(cabecera);
active=D.units.filter(f=>{const p=f.properties;return(!codes||codes.has(p.code))&&(!zone||p.zone===zone)&&(!parish||p.parish===parish)&&(!platform||p.platform===platform)&&(!q||[p.name,p.barrio,p.parish].some(s=>s.toLocaleLowerCase('es').includes(q)))});
const ps=new Set(active.map(f=>f.properties.platform)),bs=new Set(active.map(f=>f.properties.barrio));
const pf=D.platforms.filter(f=>(!platform||f.properties.name===platform)&&(!zone&&!parish&&!q&&!cabecera||ps.has(f.properties.name)));
const bf=D.barrios.filter(f=>(!platform||f.properties.platform===platform)&&(!q||f.properties.name.toLocaleLowerCase('es').includes(q)||bs.has(f.properties.name))&&(!zone&&!parish&&!cabecera||bs.has(f.properties.name)));
const add=(features,options)=>{const g=L.geoJSON(fc(features),options).addTo(map);groups.push(g);return g};
if($('showPopulation').checked)add(active,{style:f=>({color:'#285f59',weight:.35,fillColor:color(f.properties.pop),fillOpacity:.64}),pointToLayer:(f,ll)=>L.circleMarker(ll,{interactive:false,radius:Math.min(13,3+Math.sqrt(f.properties.pop)/4),color:'#145954',weight:1,fillColor:color(f.properties.pop),fillOpacity:.85}),interactive:false});
if($('showPlatforms').checked){add(pf,{pane:'platforms',interactive:false,style:{color:'#fff',weight:7,fillOpacity:0}});const outlines=add(pf,{pane:'platforms',style:{color:'#193041',weight:3.5,fillOpacity:.015},interactive:false});outlines.eachLayer(l=>{const p=l.feature.properties,center=l.getBounds().getCenter(),code=p.name.replace('PLATAFORMA ','');const tag=L.marker(center,{interactive:false,icon:L.divIcon({className:'platform-tag',html:`<div><span>PLATAFORMA</span><strong>${esc(code)}</strong></div>`,iconSize:[64,37],iconAnchor:[32,18]})}).addTo(map);groups.push(tag)});}
if($('showBarrios').checked){add(bf,{pane:'barrios',interactive:false,style:{color:'#fff',weight:platform?4.5:4,opacity:.95,fill:false}});add(bf,{pane:'barrios',style:{color:'#164e70',weight:platform?2.4:2,opacity:1,fill:false},interactive:false});}
visibleBarrioKeys=new Set(bf.map(f=>f.properties.name+'|'+f.properties.platform));renderBarrioLabels();
$('selectedPop').textContent=num(active.reduce((s,f)=>s+f.properties.pop,0))+' hab.';$('selectedCount').textContent=`${num(active.length)} unidades censales · ${bf.length} polígonos de barrio · población georreferenciada`;
$('mapSubtitle').textContent=[cabecera?'Cabecera '+cabecera:'',zone,parish,platform].filter(Boolean).join(' · ')||'Cantón · Chimborazo';
$('analysisTitle').textContent=cabecera?'Población referencial · '+cabecera:platform?'Estadísticas de '+platform:zone||parish||q?'Estadísticas de la selección':'Estadísticas de todo el cantón';
const cabeceraFeatures=cabecerasPrincipales.filter(f=>!cabecera||f.properties.name===cabecera),assignedPop=cabeceraFeatures.reduce((s,f)=>s+f.properties.pop,0),crossing=cabeceraFeatures.reduce((s,f)=>s+f.properties.crossing_units,0);
$('cabeceraSummary').textContent=(cabecera||'Todas las cabeceras')+': '+num(assignedPop)+' hab. asignados, antes de otros filtros. '+num(crossing)+' manzanas asignadas cruzan los límites.';
for(const [id,key,area] of [['urbanPop','pop','URBANO'],['ruralPop','pop','RURAL'],['malePop','male',''],['femalePop','female','']])$(id).textContent=num(active.filter(f=>!area||f.properties.zone===area).reduce((s,f)=>s+f.properties[key],0))+' hab.';
const result=$('results');result.replaceChildren();if(q){active.slice(0,40).forEach(f=>{const b=document.createElement('button');b.textContent=f.properties.name+' · '+num(f.properties.pop)+' hab.';b.onclick=()=>{const g=L.geoJSON(f);map.fitBounds(g.getBounds().pad(.5),{maxZoom:17})};result.append(b)});if(!active.length)result.textContent='No se encontraron coincidencias.';}
if(fit&&active.length)map.fitBounds(L.geoJSON(fc(platform&&!zone&&!parish&&!q&&!cabecera?pf:active)).getBounds().pad(.08),{maxZoom:15});}
for(const id of ['zone','parish','platform'])$(id).onchange=()=>render(true);
for(const id of ['showPlatforms','showBarrios','showPopulation'])$(id).onchange=()=>render();
let timer;$('search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>render(true),250)};
$('reset').onclick=()=>{for(const id of ['zone','parish','platform','search','cabecera'])$(id).value='';cabecerasLayer.setStyle(cabeceraStyle);render();map.fitBounds(bounds)};render();
$('closeStats').onclick=()=>{$('selection').hidden=true;$('openStats').hidden=false};
$('openStats').onclick=()=>{$('selection').hidden=false;$('openStats').hidden=true};
