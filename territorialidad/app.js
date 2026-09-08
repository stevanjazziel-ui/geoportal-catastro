(()=>{
  'use strict';
  const data=window.TERRITORIALIDAD;
  const $=id=>document.getElementById(id);
  if(!data||!window.TERRITORY_GEOMETRY||!window.TerritorialModel){$('loadStatus').textContent='No se cargó la matriz. Recarga la página.';return;}
  const model=TerritorialModel.create(data);
  const state={territory:'ALL',scope:'urban',period:'current',area:'all',query:'',view:'cards',sort:'source',limit:16};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=n=>new Intl.NumberFormat('es-EC').format(n);
  const usd=n=>n===null||n===undefined?'Sin monto comparable':new Intl.NumberFormat('es-EC',{style:'currency',currency:'USD',maximumFractionDigits:2,minimumFractionDigits:2}).format(n);
  const usdMini=n=>{if(n===null||n===undefined)return 'Sin monto';const abs=Math.abs(n),f=v=>new Intl.NumberFormat('es-EC',{maximumFractionDigits:2,minimumFractionDigits:0}).format(v);return abs>=1000000?'$'+f(n/1000000)+' M':abs>=1000?'$'+f(n/1000)+' mil':usd(n);};
  const label=c=>model.territoryMap.get(c)?.name||c;
  const shortArea=area=>({'DESARROLLO SOCIAL':'Desarrollo Social','SECRETARIA GENERAL':'Secretaría General','HABITAT':'Hábitat','CONTROL MUNICIPAL':'Control Municipal','RIOBAMBA EP':'Riobamba EP','ADMINISTRATIVO':'Administrativo','OBRAS PÚBLICAS':'Obras Públicas','DESARROLLO ECONOMICO':'Desarrollo Económico','TICS':'TICS','CULTURA':'Cultura','COOPERACIÓN':'Cooperación','AMBIENTE':'Ambiente','PATRIMONIO':'Patrimonio','RIESGOS':'Riesgos'}[area]||area);
  let map,polygons,basemaps={},selectionLayer,visibleRecords=[],counts=new Map(),previousFocus;
  const sourceRows=new Map(data.records.map(r=>[r.id,r]));
  const visibleCodes=r=>r.codes.filter(model.isUrbanCode);
  const platformAmount=b=>model.isSpecificPlatformBudget(b)?b.value:null;
  const title=()=>state.territory==='GENERAL'?'General':state.territory==='ALL'||state.territory==='URBAN'?'Proyectos específicos':label(state.territory);
  const cleanText=v=>String(v??'').replace(/\s+/g,' ').trim();
  const serviceText=r=>cleanText(r.description).replace(/^(servicio|gestión|gestion|obra|bien|consultoría|consultoria)\s*[:/.-]\s*/i,'')||'Servicio no registrado';
  const hasPopulation=v=>/poblaci[oó]n|beneficiari|habitantes|personas|niñ|adolescen|adult|familias|estudiantes|usuarios|moradores|ciudadan|turistas|participantes/i.test(cleanText(v));
  const reachValue=r=>cleanText(r.indicator)||cleanText(r.coverage)||'No registrado';
  const reachLabel=r=>hasPopulation(reachValue(r))?'Población alcanzada':'Alcance reportado';
  function budgetCaption(b){
    const pieces=[];
    if(model.isSpecificPlatformBudget(b))pieces.push('Monto específico de plataforma');
    else if(b.codes.length===1&&!model.isUrbanCode(b.codes[0]))pieces.push('Registro fuera del visor urbano');
    if(b.fromComponent)pieces.push('Tomado del componente presupuestario');
    if(b.value!==null&&!b.comparable)pieces.push('Anual / promedio, excluido de sumas');
    if(!pieces.length)pieces.push('Sin monto específico');
    return pieces.join(' · ');
  }
  function amountText(b){const amount=platformAmount(b);return amount!==null?usd(amount):'Sin monto específico';}
  const noteText=n=>{const t=TerritorialModel.normalize(n);return (t.includes(['bloque','presupuestario','combinado'].join(' '))||(t.includes('presupuesto')&&t.includes('agrupado')&&t.includes('matriz')))?'':String(n).trim();};
  function getCounts(){
    const rows=model.filter({...state,territory:'ALL'}),out=new Map(data.territories.map(t=>[t.code,0]));
    rows.forEach(r=>visibleCodes(r).forEach(c=>out.set(c,(out.get(c)||0)+1)));
    return out;
  }
  function renderList(){
    $('territoryList').innerHTML=data.territories.filter(t=>t.type==='Urbana').map(t=>`<button class="territory-button ${state.territory===t.code?'active':''}" data-territory="${esc(t.code)}" aria-pressed="${state.territory===t.code}"><span class="territory-code">${esc(t.code)}</span><span class="name">${esc(t.name)}</span></button>`).join('');
    $('allCount').textContent='';
    $('all').classList.toggle('active',state.territory==='ALL');
    $('all').setAttribute('aria-pressed',String(state.territory==='ALL'));
    $('general').classList.toggle('active',state.territory==='GENERAL');
    $('general').setAttribute('aria-pressed',String(state.territory==='GENERAL'));
    $('scopeNote').textContent='Cada plataforma muestra solo proyectos con código único. Los registros A–Q o de varias plataformas van en General.';
    document.querySelectorAll('[data-scope]').forEach(b=>{b.classList.toggle('active',b.dataset.scope===state.scope);b.setAttribute('aria-pressed',String(b.dataset.scope===state.scope));});
  }
  function card(r){
    const b=model.budgetMap.get(r.budgetId),warnings=r.notes.length+b.notes.length;
    return `<article class="record-card"><div class="record-top"><span class="area-tag">${esc(shortArea(r.area))}</span></div><span class="service-label">Servicio realizado</span><h4>${esc(serviceText(r))}</h4><div class="record-facts"><div><span>${esc(reachLabel(r))}</span><strong>${esc(reachValue(r))}</strong></div></div><div class="tags">${visibleCodes(r).length===1?visibleCodes(r).map(c=>`<span class="tag">${esc(label(c))}</span>`).join(''):''}${warnings?'<span class="tag warn">Datos por revisar</span>':''}${r.images.length?`<span class="tag">${r.images.length} ${r.images.length===1?'imagen':'imágenes'}</span>`:''}</div><div class="record-bottom"><div class="record-money">${esc(amountText(b))}<small>${esc(budgetCaption(b))}</small></div><button class="record-button" data-detail="${esc(r.id)}" aria-label="Abrir ficha de ${esc(shortArea(r.area))}">Ver ficha ↗</button></div></article>`;
  }
  function renderRecords(){
    const rows=model.sorted(visibleRecords,state.sort).slice(0,state.limit);
    if(!rows.length){$('records').innerHTML='<div class="empty"><strong>No hay intervenciones con estos filtros.</strong>Prueba otra dirección, período o término de búsqueda.</div>';$('more').hidden=true;return;}
    if(state.view==='cards')$('records').innerHTML=`<div class="record-grid">${rows.map(card).join('')}</div>`;
    else $('records').innerHTML=`<div class="table-wrap"><table><thead><tr><th>Dirección</th><th>Servicio</th><th>Alcance</th><th>Monto específico</th><th>Consulta</th></tr></thead><tbody>${rows.map(r=>{const b=model.budgetMap.get(r.budgetId);return `<tr><td>${esc(shortArea(r.area))}<small>${esc(data.periods[r.period])}</small></td><td class="table-title">${esc(serviceText(r))}<small>${esc(visibleCodes(r).length>3?`${visibleCodes(r).length} plataformas`:visibleCodes(r).map(label).join(', ')||'Sin asignar')}</small></td><td>${esc(reachValue(r))}<small>${esc(reachLabel(r))}</small></td><td class="table-amount">${esc(amountText(b))}<small>${esc(budgetCaption(b))}</small></td><td><button data-detail="${esc(r.id)}" aria-label="Abrir ficha de ${esc(shortArea(r.area))}">Ver ficha</button></td></tr>`;}).join('')}</tbody></table></div>`;
    $('more').hidden=rows.length>=visibleRecords.length;
    $('more').textContent='Mostrar más';
  }
  function render(){
    visibleRecords=model.filter(state);counts=getCounts();renderList();
    const s=model.summarize(visibleRecords);
    $('selectionTitle').textContent=title();$('periodLabel').textContent=data.periods[state.period];
    const top=s.countByArea[0];
    const platformCount=new Set(visibleRecords.flatMap(visibleCodes)).size;
    $('stats').innerHTML=`<div class="stat"><span class="label">Intervenciones</span><strong>${num(s.count)}</strong><small>${state.territory==='GENERAL'?'Registros generales':'Proyectos específicos'}</small></div><div class="stat"><span class="label">Direcciones</span><strong>${num(s.areas)}</strong><small>Con información en la selección</small></div><div class="stat"><span class="label">Plataformas</span><strong>${num(platformCount)}</strong><small>${state.territory==='GENERAL'?'Cubiertas por registros generales':'Con proyectos específicos'}</small></div><div class="stat money"><span class="label">Monto específico</span><strong>${s.specific===null?'—':usd(s.specific)}</strong><small>${state.territory==='GENERAL'?'No se atribuye por plataforma':'Solo código único de plataforma'}</small></div>`;
    const areaAmounts=s.countByArea.map(a=>{const areaSummary=model.summarize(visibleRecords.filter(r=>r.area===a.area)),hasAmount=areaSummary.specific!==null;return {...a,amount:areaSummary.specific??0,hasAmount};}).sort((a,b)=>(b.hasAmount?b.amount:-1)-(a.hasAmount?a.amount:-1)||b.count-a.count);
    const max=Math.max(1,...areaAmounts.map(a=>a.hasAmount?a.amount:0));
    $('chart').innerHTML=areaAmounts.map(a=>`<button class="bar-row" data-area="${esc(a.area)}" aria-label="Filtrar ${esc(shortArea(a.area))}, ${a.hasAmount?esc(usd(a.amount)):'sin monto comparable'}"><span class="bar-name">${esc(shortArea(a.area))}</span><span class="bar-track"><span class="bar-fill" style="display:block;width:${a.hasAmount?a.amount/max*100:0}%"></span></span><span class="bar-amount">${a.hasAmount?esc(usdMini(a.amount)):'Sin monto'}</span></button>`).join('')||'<p class="scope-note">Sin información en esta selección.</p>';
    document.querySelectorAll('[data-period]').forEach(b=>{b.classList.toggle('active',b.dataset.period===state.period);b.setAttribute('aria-pressed',String(b.dataset.period===state.period));});
    document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===state.view);b.setAttribute('aria-pressed',String(b.dataset.view===state.view));});
    renderRecords();updateMap();
  }
  function color(n){return n===0?'#e3e9df':n<=10?'#c4d8b2':n<=30?'#86b684':n<=60?'#438761':'#205238';}
  function updateMap(){
    $('mapTitle').textContent=state.territory==='ALL'||state.territory==='URBAN'||state.territory==='GENERAL'?'Riobamba':title();
    $('mapSubtitle').textContent=state.territory==='GENERAL'?'GENERAL':data.periods[state.period].toUpperCase();
    $('mapHint').textContent=state.territory==='GENERAL'?'Registros que cubren varias plataformas urbanas.':state.territory==='ALL'||state.territory==='URBAN'?'Haz clic en un polígono para consultar su ficha.':'Plataforma seleccionada. Revisa su ficha territorial.';
    if(!polygons)return;
    polygons.eachLayer(layer=>{
      const c=layer.feature.properties.code,active=c===state.territory;
      layer.setStyle({fillColor:color(counts.get(c)||0),fillOpacity:active?.62:.40,color:active?'#173b25':'#5b7952',weight:active?3:1.2});
      const tt=layer.getTooltip();if(tt){layer.setTooltipContent(esc(c));const el=tt.getElement();if(el)el.classList.toggle('selected',active);}
      if(active)layer.bringToFront();
    });
  }
  function chooseTerritory(code,zoom=true){
    if(code==='RURAL'||(model.territoryMap.has(code)&&!model.isUrbanCode(code)))code='URBAN';
    if(!['ALL','URBAN','GENERAL'].includes(code)&&!model.territoryMap.has(code))throw new Error('Territorio no válido');
    state.territory=code;state.limit=16;state.scope='urban';
    render();
    if(map&&polygons&&zoom){
      const target=polygons.getLayers().find(l=>l.feature.properties.code===code);
      if(target)map.fitBounds(target.getBounds(),{padding:[65,65],maxZoom:15,animate:false});
      else map.fitBounds(polygons.getBounds(),{padding:[40,40],animate:false});
    }
  }
  function showDetail(id){
    const r=sourceRows.get(id);if(!r)throw new Error('Ficha no válida');
    const b=model.budgetMap.get(r.budgetId);
    $('dialogEyebrow').textContent=`${shortArea(r.area)} · ${data.periods[r.period]}`;
    const notes=[...new Set([...r.notes,...b.notes])];
    function field(name,value){return `<div><dt>${esc(name)}</dt><dd>${esc(value??'No registrado')}</dd></div>`;}
    $('dialogContent').innerHTML=`<p class="source-line">${esc(visibleCodes(r).map(label).join(' · ')||'Sin asignación territorial')}</p><h2 class="detail-title">${esc(serviceText(r))}</h2><div class="detail-summary"><div><span>Servicio realizado</span><strong>${esc(serviceText(r))}</strong></div><div><span>${esc(reachLabel(r))}</span><strong>${esc(reachValue(r))}</strong></div></div><div class="detail-budget"><span class="eyebrow">MONTO ESPECÍFICO DE PLATAFORMA</span><strong>${esc(amountText(b))}</strong><p>${esc(budgetCaption(b))}</p></div>${notes.map(noteText).filter(Boolean).map(n=>`<div class="warning-box">${esc(n)}</div>`).join('')}<dl class="detail-fields">${field('Indicador de gestión',r.indicator)}${field('Ubicación registrada',r.location)}${field('Cobertura original',r.coverage)}${field('Código territorial',r.originalCode)}${field('Territorio',r.territory)}${field('Tipo de territorio',r.type)}${field('Observaciones',r.observation)}</dl><section class="detail-section"><h3>Datos del período</h3><dl class="detail-fields">${Object.entries(r.fields).map(([col,f])=>field(f.label,f.value)).join('')}</dl></section>${r.images.length?`<section class="detail-section"><h3>Evidencia de soporte</h3><div class="photos">${r.images.map((src,i)=>`<a href="${esc(src)}" target="_blank" rel="noopener"><img src="${esc(src)}" loading="lazy" alt="Evidencia ${i+1} de ${esc(shortArea(r.area))}">Abrir imagen ${i+1}</a>`).join('')}</div></section>`:''}<section class="detail-section"><p class="source-line">Fuente: ${esc(data.source)}. Se conserva la redacción original de la matriz.</p></section>`;
    previousFocus=document.activeElement;$('detailDialog').showModal();$('detailDialog').scrollTop=0;$('closeDetail').focus();
  }
  function initMap(){
    if(!window.L){$('mapHint').textContent='No se pudo cargar el mapa. Puedes consultar todas las intervenciones en la lista.';return;}
    map=L.map('map',{zoomControl:false,scrollWheelZoom:false,zoomSnap:.5}).setView([-1.67,-78.65],12);
    L.control.zoom({position:'bottomright'}).addTo(map);
    basemaps.street=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:20,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'});
    basemaps.satellite=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxNativeZoom:18,maxZoom:20,attribution:'Tiles &copy; Esri'});
    basemaps.street.addTo(map);
    polygons=L.geoJSON(window.TERRITORY_GEOMETRY,{onEachFeature:(feature,layer)=>{
      const c=feature.properties.code;
      layer.bindTooltip(esc(c),{permanent:true,direction:'center',className:'platform-label'});
      layer.on('click',()=>chooseTerritory(c,false));
      layer.on('mouseover',()=>layer.setStyle({weight:3}));
      layer.on('mouseout',updateMap);
      layer.on('add',()=>{const el=layer.getElement();if(el){el.setAttribute('tabindex','0');el.setAttribute('role','button');el.setAttribute('aria-label',`Consultar Plataforma ${c}`);el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();chooseTerritory(c,false);}});}});
    }}).addTo(map);
    map.fitBounds(polygons.getBounds(),{padding:[40,40],animate:false});
    $('loadStatus').textContent=`${data.areas.length} áreas`;
  }
  $('area').innerHTML='<option value="all">Todas las direcciones</option>'+data.areas.map(a=>`<option value="${esc(a)}">${esc(shortArea(a))}</option>`).join('');
  $('area').addEventListener('change',e=>{state.area=e.target.value;state.limit=16;if(state.area!=='all')state.territory='ALL';render();});
  $('query').addEventListener('input',e=>{state.query=e.target.value;state.limit=16;render();});
  $('sort').addEventListener('change',e=>{state.sort=e.target.value;renderRecords();});
  $('all').addEventListener('click',()=>chooseTerritory('ALL'));
  $('general').addEventListener('click',()=>chooseTerritory('GENERAL'));
  $('more').addEventListener('click',()=>{state.limit+=16;renderRecords();});
  document.addEventListener('click',e=>{
    const b=e.target.closest('button');if(!b)return;
    if(b.dataset.territory)chooseTerritory(b.dataset.territory);
    if(b.dataset.period){state.period=b.dataset.period;state.limit=16;render();}
    if(b.dataset.scope){state.scope='urban';chooseTerritory('URBAN');}
    if(b.dataset.view){state.view=b.dataset.view;render();}
    if(b.dataset.area){state.area=b.dataset.area;$('area').value=state.area;state.limit=16;render();}
    if(b.dataset.detail)showDetail(b.dataset.detail);
  });
  $('basemap').addEventListener('change',e=>{if(!map)return;Object.values(basemaps).forEach(l=>map.removeLayer(l));basemaps[e.target.value].addTo(map);});
  $('labels').addEventListener('change',e=>polygons?.eachLayer(l=>e.target.checked?l.openTooltip():l.closeTooltip()));
  $('fit').addEventListener('click',()=>{if(map&&polygons)map.fitBounds(polygons.getBounds(),{padding:[40,40],animate:false});});
  $('closeDetail').addEventListener('click',()=>$('detailDialog').close());
  $('detailDialog').addEventListener('close',()=>previousFocus?.focus());
  $('methodButton').addEventListener('click',()=>$('methodDialog').showModal());
  $('closeMethod').addEventListener('click',()=>$('methodDialog').close());
  $('areasCount').textContent=`${data.areas.length} áreas`;
  $('sourceName').textContent=data.source;
  $('methodText').textContent='El visor muestra únicamente el monto específico: presupuestos asignados a una sola plataforma urbana. Los demás presupuestos no aparecen como monto por plataforma.';
  $('cartographyText').textContent='La consulta se limita a las 18 plataformas urbanas del mapa. Los registros rurales de la matriz no se muestran ni se suman.';
  initMap();render();
  const context=document.modelContext;
  if(context?.registerTool){
    const lifecycle=new AbortController();
    const tool={name:'consultar_territorio',title:'Consultar plataforma urbana',description:'Selecciona una plataforma urbana y período en el visor y devuelve el resumen visible.',inputSchema:{type:'object',properties:{territory:{type:'string',enum:['ALL','URBAN','GENERAL',...data.territories.filter(t=>t.type==='Urbana').map(t=>t.code)]},period:{type:'string',enum:Object.keys(data.periods)}},required:['territory','period'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:true},execute:input=>{
      if(!input||!Object.hasOwn(data.periods,input.period)||!['ALL','URBAN','GENERAL',...data.territories.filter(t=>t.type==='Urbana').map(t=>t.code)].includes(input.territory))throw new Error('Territorio o período no válido.');
      state.period=input.period;chooseTerritory(input.territory);return {territory:title(),period:data.periods[state.period],...model.summarize(visibleRecords)};
    }};
    try{Promise.resolve(context.registerTool(tool,{signal:lifecycle.signal})).catch(()=>{});}catch{}
    window.addEventListener('pagehide',()=>lifecycle.abort(),{once:true});
  }
})();
