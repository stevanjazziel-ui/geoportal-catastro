const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const root=fs.existsSync(path.join(__dirname,'dist'))?path.join(__dirname,'dist'):path.join(__dirname,'..');
const source=fs.readFileSync(path.join(root,'riobamba.js'),'utf8');
const meta=JSON.parse(fs.readFileSync(path.join(root,'data/riobamba-local/manifest.json'),'utf8'));
const select=()=>({value:'',replaceChildren(...options){this.options=options;this.value=options[0]?.value||'';}});
const fields={scenario:select(),duration:select(),drainage:select(),maximum:{checked:false},rainTotal:{}};
const ctx={meta,$:id=>fields[id],Option:function(text,value){this.text=text;this.value=value;},frame:0,current:null,
 fmt:(x,d=2)=>Number(x).toLocaleString('es-EC',{maximumFractionDigits:d,minimumFractionDigits:d})};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf(' function family'),source.indexOf(' async function binary'))+
 ';this.api={chooseRainOptions,chooseDrainage,waterFrameIndex,selectedStats,selectionSummary,family};',ctx);
ctx.api.chooseRainOptions();ctx.api.chooseDrainage();
assert.equal(fields.scenario.options.length,3);assert.equal(fields.duration.options.length,48);
assert.deepEqual(fields.duration.options.map(o=>Number(o.value)),Array.from({length:48},(_,i)=>(i+1)*15));
for(const c of meta.cases){
 ctx.current=c;fields.scenario.value=ctx.api.family(c);fields.drainage.value=c.id;
 for(let minutes=15;minutes<=720;minutes+=15){
  fields.duration.value=String(minutes);const cutoff=minutes/15;
  ctx.frame=48;fields.maximum.checked=false;
  assert.equal(ctx.api.waterFrameIndex(),cutoff);
  assert.strictEqual(ctx.api.selectedStats(),c.cumulative_stats_by_frame[cutoff]);
  ctx.frame=0;assert.equal(ctx.api.waterFrameIndex(),0);
  assert.strictEqual(ctx.api.selectedStats(),c.cumulative_stats_by_frame[0]);
  fields.maximum.checked=true;assert.equal(ctx.api.waterFrameIndex(),49+cutoff);
  assert.strictEqual(ctx.api.selectedStats(),c.cumulative_stats_by_frame[cutoff]);
  ctx.api.selectionSummary();assert(fields.rainTotal.textContent.includes(ctx.fmt(c.rain_mm_h*minutes/60,2)));
 }
}
console.log('Verified 432 UI selections: fixed rates, quarter-hour cutoffs, correct cumulative frames, no future statistics.');
