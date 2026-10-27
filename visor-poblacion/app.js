const D=window.TERRITORY,$=id=>document.getElementById(id),num=n=>new Intl.NumberFormat('es-EC').format(n),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const map=L.map('map',{preferCanvas:true}).setView([-1.66,-78.65],11);
const base=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);
const satellite=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Tiles © Esri'});
L.control.layers({'Calles':base,'Satélite':satellite},null,{position:'topright'}).addTo(map);L.control.scale({imperial:false}).addTo(map);
map.createPane('platforms');map.getPane('platforms').style.zIndex=410;map.createPane('barrios');map.getPane('barrios').style.zIndex=420;
const fc=features=>({type:'FeatureCollection',features}),color=n=>n>=300?'#145954':n>=150?'#21877e':n>=50?'#59bba7':'#b9e5da';
const bounds=L.geoJSON(fc(D.parishes),{style:{color:'#466370',weight:1.5,fillOpacity:0,dashArray:'6 5'},interactive:false}).addTo(map).getBounds();map.fitBounds(bounds);
let groups=[],active=[];
function popup(p){return `<b>${esc(p.name)}</b><br><strong>${num(p.pop)}</strong> habitantes<br>${p.type?`${esc(p.zone)} · ${esc(p.type)}<br>Parroquia: ${esc(p.parish)}<br>Hombres: ${num(p.male)} · Mujeres: ${num(p.female)}<br>`:'Población asignada espacialmente<br>'}${p.platform?esc(p.platform)+'<br>':''}${p.barrio?'Barrio: '+esc(p.barrio):''}`;}
for(const id of ['parish','platform']){const key=id==='parish'?'parish':'name';const source=id==='parish'?D.units:D.platforms;[...new Set(source.map(f=>f.properties[key]))].filter(Boolean).sort((a,b)=>a.localeCompare(b,'es')).forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;$(id).append(o)});}
function render(fit=false){groups.forEach(g=>map.removeLayer(g));groups=[];const zone=$('zone').value,parish=$('parish').value,platform=$('platform').value,q=$('search').value.trim().toLocaleLowerCase('es');
active=D.units.filter(f=>{const p=f.properties;return(!zone||p.zone===zone)&&(!parish||p.parish===parish)&&(!platform||p.platform===platform)&&(!q||[p.name,p.barrio,p.parish].some(s=>s.toLocaleLowerCase('es').includes(q)))});
const ps=new Set(active.map(f=>f.properties.platform)),bs=new Set(active.map(f=>f.properties.barrio));
const pf=D.platforms.filter(f=>(!platform||f.properties.name===platform)&&(!zone&&!parish&&!q||ps.has(f.properties.name)));
const bf=D.barrios.filter(f=>(!platform||f.properties.platform===platform)&&(!q||f.properties.name.toLocaleLowerCase('es').includes(q)||bs.has(f.properties.name))&&(!zone&&!parish||bs.has(f.properties.name)));
const add=(features,options)=>{const g=L.geoJSON(fc(features),options).addTo(map);groups.push(g);return g};
if($('showPopulation').checked)add(active,{style:f=>({color:'#285f59',weight:.35,fillColor:color(f.properties.pop),fillOpacity:.64}),pointToLayer:(f,ll)=>L.circleMarker(ll,{radius:Math.min(13,3+Math.sqrt(f.properties.pop)/4),color:'#145954',weight:1,fillColor:color(f.properties.pop),fillOpacity:.85}),onEachFeature:(f,l)=>l.bindPopup(popup(f.properties))});
if($('showPlatforms').checked)add(pf,{pane:'platforms',style:{color:'#d19b33',weight:2.5,fillOpacity:.025},onEachFeature:(f,l)=>l.bindPopup(popup(f.properties)).bindTooltip(esc(f.properties.name),{sticky:true})});
if($('showBarrios').checked)add(bf,{pane:'barrios',style:{color:'#615bbb',weight:1.2,fillOpacity:.02},onEachFeature:(f,l)=>{l.bindPopup(popup(f.properties));l.bindTooltip(esc(f.properties.name),{permanent:$('showNames').checked,direction:'center',className:'barrio-label'});}});
$('selectedPop').textContent=num(active.reduce((s,f)=>s+f.properties.pop,0))+' hab.';$('selectedCount').textContent=`${num(active.length)} unidades censales · ${bf.length} polígonos de barrio · población georreferenciada`;
$('mapSubtitle').textContent=[zone,parish,platform].filter(Boolean).join(' · ')||'Cantón · Chimborazo';
const result=$('results');result.replaceChildren();if(q){active.slice(0,40).forEach(f=>{const b=document.createElement('button');b.textContent=f.properties.name+' · '+num(f.properties.pop)+' hab.';b.onclick=()=>{const g=L.geoJSON(f);map.fitBounds(g.getBounds().pad(.5),{maxZoom:17});L.popup().setLatLng(g.getBounds().getCenter()).setContent(popup(f.properties)).openOn(map)};result.append(b)});if(!active.length)result.textContent='No se encontraron coincidencias.';}
if(fit&&active.length)map.fitBounds(L.geoJSON(fc(platform&&!zone&&!parish&&!q?pf:active)).getBounds().pad(.08),{maxZoom:15});}
for(const id of ['zone','parish','platform'])$(id).onchange=()=>render(true);
for(const id of ['showPlatforms','showBarrios','showPopulation','showNames'])$(id).onchange=()=>render();
let timer;$('search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>render(true),250)};
$('reset').onclick=()=>{for(const id of ['zone','parish','platform','search'])$(id).value='';render();map.fitBounds(bounds)};render();
