'use strict';
const el=id=>document.getElementById(id),fmt=n=>Number(n).toLocaleString('es-EC',{maximumFractionDigits:3});
let inputs,tides;
function option(parent,value,label){const o=document.createElement('option');o.value=value;o.textContent=label;parent.append(o);}
function chart(target,values,dates,unit,lower=null,upper=null){
 if(!values.length){el(target).textContent='No hay datos para este periodo.';return;}
 const w=520,h=250,l=53,r=13,t=22,b=42,lo=Math.min(...(lower||values)),hi=Math.max(...(upper||values)),span=Math.max(hi-lo,.01),min=lo-.08*span,max=hi+.08*span;
 const x=i=>l+i*(w-l-r)/Math.max(1,values.length-1),y=v=>t+(max-v)/(max-min)*(h-t-b),line=a=>a.map((v,i)=>`${x(i).toFixed(2)},${y(v).toFixed(2)}`).join(' ');
 const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.classList.add('chart');svg.setAttribute('role','img');svg.setAttribute('aria-label',`${unit}; ${dates[0]} a ${dates.at(-1)}`);
 const add=(name,attrs,text)=>{let n=document.createElementNS(ns,name);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;svg.append(n);return n;};
 for(let i=0;i<5;i++){const v=min+(max-min)*i/4;add('line',{x1:l,y1:y(v),x2:w-r,y2:y(v),stroke:'#e5ece0'});add('text',{x:l-8,y:y(v)+4,'text-anchor':'end'},fmt(v));}
 if(lower&&upper)add('polygon',{points:line(upper)+' '+lower.map((v,i)=>`${x(i).toFixed(2)},${y(v).toFixed(2)}`).reverse().join(' '),fill:'#c7e9e1'});
 add('polyline',{points:line(values),fill:'none',stroke:'#197b69','stroke-width':2});add('text',{x:l,y:12},unit);
 [0,Math.floor((values.length-1)/2),values.length-1].forEach((i,k)=>add('text',{x:x(i),y:h-17,'text-anchor':k===0?'start':k===2?'end':'middle'},dates[i].slice(5,16).replace('T',' ')));
 values.forEach((v,i)=>{let c=add('circle',{cx:x(i),cy:y(v),r:3,fill:'#197b69','fill-opacity':.1});let title=document.createElementNS(ns,'title');title.textContent=`${dates[i]} · ${fmt(v)} ${unit}`;c.append(title);});
 el(target).replaceChildren(svg);
}
function tide(){const s=el('station').value,first=tides.dates.findIndex(x=>x.startsWith(el('date').value));if(first<0){el('tideChart').textContent='Selecciona una fecha disponible de 2026.';return;}const values=tides.stations[s].slice(first,first+73),dates=tides.dates.slice(first,first+73);chart('tideChart',values,dates,'m · MLWS');el('tideDetail').textContent=`${dates[0]} — ${dates.at(-1)} · mínimo ${fmt(Math.min(...values))} m · máximo ${fmt(Math.max(...values))} m`;
}
function flow(){const d=inputs.flows[Number(el('river').value)];chart('flowChart',d.flow_median,d.datetime,'m³/s · UTC',d.flow_uncertainty_lower,d.flow_uncertainty_upper);el('flowDetail').textContent=`Tramo ${d.metadata.river_id} · ${d.datetime.length} puntos · emisión ${d.metadata.gen_date} · asociación pendiente de verificar`;el('flowSource').href=d.source_url;}
function city(){const c=inputs.cities.find(c=>c.id===el('city').value),box=el('cityDetail');box.replaceChildren();let p=document.createElement('p');p.className='pending';p.textContent='Modelo compuesto pendiente: faltan geometría local, referencias y validación.';box.append(p);let ul=document.createElement('ul');for(const r of c.river_candidates){let li=document.createElement('li');li.textContent=`Tramo candidato ${r.river_id}: ${fmt(r.distance_km)} km al punto de referencia${r.flow_downloaded?' · serie descargada':''}.`;ul.append(li);}if(!c.river_candidates.length){let li=document.createElement('li');li.textContent='No hay un candidato a menos de 30 km en el recorte consultado.';ul.append(li);}box.append(ul);p=document.createElement('p');p.textContent='Pendientes: verificar entradas y cauces; obtener secciones y estructuras; identificar la referencia vertical del terreno; incorporar red y capacidades; contrastar con observaciones. Donde aplique marea: nivelación MLWS, batimetría, estado inicial y sincronización temporal.';box.append(p);}
Promise.all([fetch('data/compound/inputs.json').then(r=>{if(!r.ok)throw Error('No se pudo cargar la revisión');return r.json();}),fetch('data/compound/tides2026.json').then(r=>{if(!r.ok)throw Error('No se pudieron cargar las mareas');return r.json();})]).then(([a,b])=>{
 inputs=a;tides=b;Object.keys(b.stations).forEach(s=>option(el('station'),s,s.replaceAll('_',' ')));el('station').value='RIO_GUAYAS';a.flows.forEach((d,i)=>{const c=a.cities.find(c=>c.river_candidates.some(r=>r.river_id===d.metadata.river_id));option(el('river'),i,`${c?.name||'Referencia'} · ${d.metadata.river_id}`);});a.cities.forEach(c=>option(el('city'),c.id,c.name));el('city').value='3652567';
 const s=a.swmm_verification;el('swmmDetail').textContent=`Comprobación EPA Extran: ${s.nodes.length} nodos, ${s.links.length} enlaces y ${fmt(s.duration_seconds/3600)} h. Error de continuidad: ${fmt(Math.abs(s.routing_continuity_error_percent))} %. El balance numérico no demuestra exactitud territorial.`;
 tide();flow();city();el('loadStatus').textContent='Datos cargados · descarga fija del 12 de noviembre de 2026; no es un servicio de actualización automática.';
 el('station').addEventListener('change',tide);el('date').addEventListener('change',tide);el('river').addEventListener('change',flow);el('city').addEventListener('change',city);
}).catch(e=>el('loadStatus').textContent=e.message);
