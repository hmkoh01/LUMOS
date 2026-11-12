const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function el(id, dataset = {}) {
  const classes = new Set();
  return {id, dataset, hidden:false, attributes:{}, disabled:false, value:'', textContent:'', innerHTML:'',
    classList:{add(v){classes.add(v)},remove(v){classes.delete(v)},contains(v){return classes.has(v)},toggle(v,on){if(on === undefined) on=!classes.has(v); on ? classes.add(v) : classes.delete(v)}},
    setAttribute(k,v){this.attributes[k]=v}, addEventListener(name,fn){this[name]=fn}, querySelectorAll(){return []}};
}
const ids = new Map();
function get(id){if(!ids.has(id))ids.set(id,el(id)); return ids.get(id)}
const nav=['signals','saved','interests','customize'].map(x=>el('nav-'+x,{tab:x}));
const views=['signals','saved','interests','customize','activity'].map(x=>get('view-'+x));
const tabs=['news','feedback'].map(x=>el('tab-'+x,{customTab:x}));
const location={hash:'#today'};
const ctx=vm.createContext({location, history:{replaceState(_a,_b,h){location.hash=h}}, document:{
  addEventListener(){}, getElementById:get,
  querySelectorAll(s){return s==='.nav-item'?nav:s==='.view'?views:s==='[data-custom-tab]'?tabs:[]},
  querySelector(){return null},
},window:{addEventListener(){},scrollX:0,scrollY:0},setTimeout(){},clearTimeout(){}});
vm.runInContext(fs.readFileSync('src/web/static/app.js','utf8'),ctx);
vm.runInContext('loadCustomizeTab = () => {}; loadRecommendationSignals = () => {}',ctx);
for(const [hash,internal,category] of [['#sources','news',null],['#settings','news',null],['#recommendations','feedback',null],['#tracked','feedback','tracked'],['#ignored','feedback','ignored']]) {
  location.hash=hash; vm.runInContext('applyHashTab({load:false})',ctx);
  assert.equal(vm.runInContext('state.activeTab',ctx),'customize');
  assert.equal(vm.runInContext('state.customizeTab',ctx),internal);
  if(category) assert.equal(vm.runInContext('state.recommendationCategory',ctx),category);
  assert.equal(get('customize-news').hidden, internal!=='news');
  assert.equal(get('customize-feedback').hidden, internal!=='feedback');
  assert.equal(nav[3].classList.contains('active'),true);
}
vm.runInContext('selectCustomizeTab("news", {updateHash:true})',ctx);
assert.equal(location.hash,'#customize');
vm.runInContext('selectCustomizeTab("feedback", {updateHash:true})',ctx);
assert.equal(location.hash,'#customize-feedback');
const html=fs.readFileSync('src/web/static/index.html','utf8');
assert.deepEqual([...html.matchAll(/class="nav-item(?: active)?" data-tab="([^"]+)"/g)].map(x=>x[1]),['signals','saved','interests','customize']);
const radios=['both','domestic','international'].map(v=>Object.assign(el('region-'+v),{value:v,checked:v==='both'}));
ctx.fixtureContainer={querySelectorAll(s){return s==="input[name='source-region']"?radios:[]}};
vm.runInContext(`state.settings = {source_region_preference:'both',signal_count:3}; state.briefingDisplayMax=5;
  globalThis.calls=[]; api=async (path,options)=>{calls.push({path,body:JSON.parse(options.body)}); return {settings:{source_region_preference:'domestic',signal_count:3}}};
  showToast=()=>{}; bindSourceActions(fixtureContainer);`,ctx);
(async()=>{
  radios[1].checked=true; radios[0].checked=false;
  await radios[1].change();
  assert.equal(vm.runInContext('state.settings.source_region_preference',ctx),'domestic');
  assert.equal(ctx.calls[0].path,'/api/v1/settings');
  vm.runInContext(`api=async()=>{throw Error('failure')}`,ctx);
  radios[2].checked=true; radios[1].checked=false;
  await radios[2].change();
  assert.equal(radios[1].checked,true);
  assert.equal(radios[2].checked,false);
  vm.runInContext(`state.feedbackSignals=[{id:10},{id:11}]; globalThis.feedbackCalls=[];
    api=async(path,options)=>{feedbackCalls.push({path,body:JSON.parse(options.body)});return {}};
    renderRecommendationSignals=()=>{}; restoreScrollPosition=()=>{};`,ctx);
  await vm.runInContext('clearFeedbackSignal(10,{textContent:"",disabled:false})',ctx);
  assert.equal(ctx.feedbackCalls[0].path,'/api/v1/signals/10/recommendation-preference');
  assert.equal(ctx.feedbackCalls[0].body.preference,null);
  assert.equal(vm.runInContext('state.feedbackSignals.length',ctx),1);
  console.log('Customization navigation, region saving and feedback cancellation passed');
})().catch(e=>{console.error(e);process.exitCode=1});
