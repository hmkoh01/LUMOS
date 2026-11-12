const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const items = new Map();
function element(id) {
  if (!items.has(id)) items.set(id, {id, innerHTML:'', textContent:'', disabled:false, attrs:{},
    setAttribute(k,v){this.attrs[k]=v}, removeAttribute(k){delete this.attrs[k]},
    addEventListener(){}, querySelectorAll(){return []}, querySelector(){return null}, replaceChildren(){this.innerHTML=''},
    classList:{add(){},remove(){},toggle(){}} });
  return items.get(id);
}
const ctx = vm.createContext({document:{addEventListener(){},getElementById:element,querySelectorAll(){return []}},
  window:{addEventListener(){},scrollX:0,scrollY:0},setTimeout(){},clearTimeout(){}});
vm.runInContext(fs.readFileSync('src/web/static/app.js','utf8'),ctx);
const queue=[];
ctx.request=(path)=>new Promise((resolve,reject)=>queue.push({path,resolve,reject}));
vm.runInContext(`api=request; showToast=(message)=>{globalThis.lastToast=message};
  state.signals=[{id:1,title:'Existing'}]; renderSignals();`,ctx);
(async()=>{
  const before=element('signals-list').innerHTML;
  let task=vm.runInContext('refreshBriefing()',ctx);
  assert.equal(element('refresh-signals').disabled,true);
  assert.equal(element('signals-list').innerHTML,before);
  await vm.runInContext('refreshBriefing()',ctx);
  assert.equal(queue.length,1);
  assert.match(queue[0].path,/period=today/);
  queue.shift().resolve({signals:[{id:2,title:'Updated'}]}); await task;
  assert.equal(vm.runInContext('state.signals[0].id',ctx),2);
  assert.equal(element('refresh-signals').disabled,false);
  const current=element('signals-list').innerHTML;
  task=vm.runInContext('refreshBriefing()',ctx); queue.shift().reject(Error('Bad Request')); await task;
  assert.equal(element('signals-list').innerHTML,current);
  assert.doesNotMatch(ctx.lastToast,/Bad Request/);
  task=vm.runInContext('refreshBriefing()',ctx);
  vm.runInContext('state.briefingPeriod="week"',ctx);
  const week=vm.runInContext('loadSignals(true,null)',ctx);
  const old=queue.shift(), fresh=queue.shift();
  fresh.resolve({signals:[{id:3,title:'Week'}]}); await week;
  old.resolve({signals:[{id:4,title:'Stale'}]}); await task;
  assert.equal(vm.runInContext('state.signals[0].id',ctx),3);
  assert.equal(vm.runInContext('state.briefingPeriod',ctx),'week');
  vm.runInContext(`supportsOptionalApi=async()=>false; api=async(path)=>({signals:path.endsWith('tracked')
    ? [{id:10,title:'Older',feedback_at:'2026-10-01T00:00:00Z'}]
    : [{id:11,title:'Newer',feedback_at:'2026-11-01T00:00:00Z'},{id:12,title:'Undated'}]});`,ctx);
  await vm.runInContext('loadRecommendationSignals()',ctx);
  assert.equal(vm.runInContext('state.feedbackSignals.map(x=>x.id).join(",")',ctx),'11,10,12');
  assert.match(element('signals-list').innerHTML,/Week/);
  assert.match(element('recommendation-signals-list').innerHTML,/더 보고 싶어요/);
  assert.match(element('recommendation-signals-list').innerHTML,/덜 보고 싶어요/);
  assert.equal(element('feedback-count').textContent,'총 3건');
  console.log('Briefing refresh, response races and combined feedback passed');
})().catch(error=>{console.error(error);process.exitCode=1});
