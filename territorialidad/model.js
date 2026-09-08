(function(root){
  'use strict';
  const normalize=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  function create(data){
    const budgetMap=new Map(data.budgets.map(b=>[b.id,b]));
    const territoryMap=new Map(data.territories.map(t=>[t.code,t]));
    const text=new Map(data.records.map(r=>[r.id,normalize([r.description,r.indicator,r.location,r.observation,r.area,r.territory,...r.codes].join(' '))]));
    const isUrbanCode=code=>territoryMap.get(code)?.type==='Urbana';
    const urbanCodes=record=>record.codes.filter(isUrbanCode);
    const isSpecificPlatformRecord=record=>record.codes.length===1&&isUrbanCode(record.codes[0]);
    const isGeneralPlatformRecord=record=>urbanCodes(record).length>1;
    const hasUrbanScope=record=>record.codes.some(isUrbanCode);
    const isSpecificPlatformBudget=budget=>budget?.comparable&&budget.value!==null&&budget.codes.length===1&&isUrbanCode(budget.codes[0]);
    function matchesTerritory(record,territory){
      if(!hasUrbanScope(record))return false;
      if(territory==='GENERAL')return isGeneralPlatformRecord(record);
      if(!territory||territory==='ALL'||territory==='URBAN')return isSpecificPlatformRecord(record);
      if(territory==='RURAL')return false;
      return isUrbanCode(territory)&&isSpecificPlatformRecord(record)&&record.codes[0]===territory;
    }
    function filter(state){
      const query=normalize(state.query||'').trim();
      return data.records.filter(r=>r.period===state.period && (state.area==='all'||!state.area||r.area===state.area) && matchesTerritory(r,state.territory) && (!query||text.get(r.id).includes(query)));
    }
    function summarize(records){
      const budgets=[...new Set(records.map(r=>r.budgetId))].map(id=>budgetMap.get(id));
      const valid=budgets.filter(b=>b.comparable&&b.value!==null);
      const specific=valid.filter(isSpecificPlatformBudget);
      const shared=valid.filter(b=>b.codes.length>1&&b.codes.some(isUrbanCode));
      const unassigned=valid.filter(b=>!b.codes.length);
      const countByArea=data.areas.map(area=>({area,count:records.filter(r=>r.area===area).length})).filter(x=>x.count).sort((a,b)=>b.count-a.count);
      return {count:records.length,areas:countByArea.length,countByArea,
        specific:specific.length?specific.reduce((s,b)=>s+b.value,0):null,
        shared:null,
        specificCount:specific.length,sharedCount:shared.length,excluded:budgets.length-valid.length,
        unassigned:unassigned.length,images:records.filter(r=>r.images.length).length,
        warnings:records.filter(r=>r.notes.length||budgetMap.get(r.budgetId).notes.length).length};
    }
    function sorted(records,sort){
      const result=records.slice();
      if(sort==='amount')result.sort((a,b)=>(isSpecificPlatformBudget(budgetMap.get(b.budgetId))?budgetMap.get(b.budgetId).value:-Infinity)-(isSpecificPlatformBudget(budgetMap.get(a.budgetId))?budgetMap.get(a.budgetId).value:-Infinity));
      return result;
    }
    return {filter,summarize,sorted,budgetMap,territoryMap,matchesTerritory,isUrbanCode,isSpecificPlatformBudget,isSpecificPlatformRecord,isGeneralPlatformRecord};
  }
  root.TerritorialModel={create,normalize};
  if(typeof module!=='undefined')module.exports=root.TerritorialModel;
})(typeof window!=='undefined'?window:globalThis);
