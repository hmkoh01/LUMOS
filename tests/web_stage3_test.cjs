const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    innerHTML: '', textContent: '', value: '', disabled: false,
    querySelectorAll() { return []; }, querySelector() { return null; },
    addEventListener() {}, classList: { add() {}, remove() {}, toggle() {} },
  });
  return elements.get(id);
}
const submit = { disabled: false };
const context = vm.createContext({
  document: { addEventListener() {}, getElementById: element, querySelectorAll() { return []; }, querySelector() { return submit; } },
  window: { addEventListener() {}, scrollX: 0, scrollY: 0 },
  setTimeout() {}, clearTimeout() {},
});
vm.runInContext(fs.readFileSync('src/web/static/app.js', 'utf8'), context);
vm.runInContext(`
  state.recommendationCategory = 'ignored';
  globalThis.item = renderFeedbackSignalCard({id: 1, title: 'Test title', source_display: 'Test source', feedback_reason_code: 'too_technical'}, 1);
  renderAccountShell = () => {};
  renderGateSummary = () => {};
  state.settings = { signal_count: 7 };
  state.briefingDisplayMax = 5;
  renderSettings();
`, context);
assert.match(context.item, /덜 보고 싶어요/);
assert.match(context.item, /제외 취소/);
assert.match(context.item, /내용이 너무 어려워요/);
assert.doesNotMatch(context.item, /목록에서 빼기/);
assert.match(element('setting-signal-count').innerHTML, /저장된 설정: 7개/);
assert.match(element('signal-count-gate-note').textContent, /최대 5개/);
element('setting-signal-count').value = '3';
vm.runInContext('renderSignalCountGateNote()', context);
assert.equal(element('signal-count-gate-note').textContent, '');
(async () => {
  vm.runInContext(`api = async () => ({settings: {signal_count: 3}});`, context);
  await vm.runInContext('saveSettings({preventDefault(){}})', context);
  assert.equal(vm.runInContext('state.settings.signal_count', context), 3);
  assert.equal(element('signal-count-save-status').textContent, '저장했어요.');
  element('setting-signal-count').value = '4';
  vm.runInContext(`api = async () => {throw new Error('internal error')}`, context);
  await vm.runInContext('saveSettings({preventDefault(){}})', context);
  assert.equal(element('setting-signal-count').value, '3');
  assert.equal(element('signal-count-save-status').textContent, '저장하지 못했어요. 다시 선택해 주세요.');
  vm.runInContext(`
    api = async () => ({sources: [
      {source_id:'ready', display_name:'Available source', available:true, effective_enabled:true, implemented_status:'implemented'},
      {source_id:'opendart', display_name:'OpenDART', available:true, effective_enabled:true, implemented_status:'implemented'},
      {source_id:'off', display_name:'Disabled source', available:true, effective_enabled:false, implemented_status:'implemented'},
      {source_id:'unavailable', display_name:'Hidden source', available:false, availability_reason:'permission_review'}
    ]});
  `, context);
  await vm.runInContext('loadSources(null)', context);
  const html = element('sources-list').innerHTML;
  assert.match(html, /Available source/);
  assert.doesNotMatch(html, /Hidden source|Disabled source|OpenDART|permission_review|연결 필요|준비 중/);
  console.log('Stage 3 settings, feedback and source presentation checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
