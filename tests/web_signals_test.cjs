const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = new Map();
const scrollCalls = [];
const sessionValues = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    innerHTML: '', textContent: '', disabled: false,
    addEventListener(name, callback) { this[name] = callback; },
    querySelectorAll() { return []; },
  });
  return elements.get(id);
}
const context = vm.createContext({
  document: { addEventListener() {}, getElementById: element },
  location: { hash: '#today' },
  window: {
    scrollX: 42,
    scrollY: 84,
    addEventListener() {},
    requestAnimationFrame(callback) { callback(); },
    scrollTo(x, y) { scrollCalls.push({ x, y }); },
  },
  sessionStorage: {
    getItem(key) { return sessionValues.get(key) || null; },
    setItem(key, value) { sessionValues.set(key, value); },
  },
  setTimeout() {}, clearTimeout() {},
});
vm.runInContext(fs.readFileSync('src/web/static/app.js', 'utf8'), context);
vm.runInContext(`
  state.settings = {generate_mode: 'live'};
  state.signals = [{id: 1, rank: 1, source_display: 'YouTube', collected_via: 'Hacker News',
    data_kind: 'mock', generation_mode: 'hybrid', display_title_ko: '자료 제목',
    detail_summary_ko: '확보한 설명 <script>alert(1)</script>', detail_limitation_ko: '제목만 확보했어요.',
    original_title: 'Original title', source_url: 'https://youtu.be/test'}];
  state.hasMoreSignals = true;
  state.signalRunId = 10;
  renderSignals();
`, context);
const html = element('signals-list').innerHTML;
assert.match(html, /출처 YouTube/);
assert.match(html, /수집 경로: Hacker News/);
assert.match(html, /샘플 자료 · 실제 최신 정보 아님/);
assert.match(html, /생성 당시 방식: 혼합 모드/);
assert.match(html, /내용 정리/);
assert.match(html, /&lt;script&gt;/);
assert.doesNotMatch(html, /<script>/);
assert.match(html, /data-feedback="saved"/);
assert.match(html, /https:\/\/youtu.be\/test/);
assert.match(html, /추가 신호 보기/);
assert.equal(typeof element('more-signals').click, 'function');
vm.runInContext(`
  globalThis.feedbackCard = renderFeedbackSignalCard({
    id: 3, source_display: 'Hacker News', feedback_at: '2026-10-03T09:00:00',
    matched_keywords: ['AI agent'], title: 'Feedback signal'
  }, 1);
  globalThis.savedCard = renderSavedSignalCard({
    id: 4, source_display: 'RSS', saved_at: '2026-10-03T09:00:00',
    matched_keywords: ['productivity'], title: 'Saved signal'
  }, 1);
`, context);
assert.match(vm.runInContext('feedbackCard', context), /AI agent/);
assert.match(vm.runInContext('feedbackCard', context), /Hacker News/);
assert.match(vm.runInContext('savedCard', context), /productivity/);
vm.runInContext(`
  globalThis.mutedInterestCard = renderInterestCard({ keyword: 'hidden keyword', weight: 1, status: 'muted' });
`, context);
assert.match(vm.runInContext('mutedInterestCard', context), /data-interest-status="muted"/);
assert.equal(vm.runInContext('captureScrollPosition().x', context), 42);
assert.equal(vm.runInContext('captureScrollPosition().y', context), 84);
vm.runInContext('storeScrollPosition(); restoreScrollPosition({ x: 10, y: 20 });', context);
assert.deepEqual(JSON.parse(sessionValues.get('lumos:scroll-position:#today')), { x: 42, y: 84 });
assert.deepEqual(scrollCalls.at(-1), { x: 10, y: 20 });
vm.runInContext('state.hasMoreSignals = false; renderSignals();', context);
assert.match(element('signals-list').innerHTML, /더 보여드릴 자료가 없어요/);
assert.doesNotMatch(element('signals-list').innerHTML, /id="more-signals"/);

async function main() {
  vm.runInContext(`
    state.hasMoreSignals = true;
    let requestCount = 0;
    let releaseRequest;
    api = async (url, options) => {
      if (url.endsWith('/more')) {
        requestCount++;
        if (JSON.parse(options.body).pipeline_run_id !== 10) throw Error('Wrong run');
        await new Promise(resolve => { releaseRequest = resolve; });
        return {};
      }
      return { signals: [...state.signals, {id: 2, title: '추가 자료'}], has_more: false, pipeline_run_id: 10 };
    };
    const firstRequest = loadMoreSignals();
    const duplicateRequest = loadMoreSignals();
  `, context);
  assert.equal(vm.runInContext('requestCount', context), 1);
  assert.equal(element('more-signals').disabled, true);
  vm.runInContext('releaseRequest();', context);
  await vm.runInContext('Promise.all([firstRequest, duplicateRequest])', context);
  assert.equal(vm.runInContext('state.signals.length', context), 2);
  assert.equal(vm.runInContext('state.loadingMoreSignals', context), false);
  assert.match(element('signals-list').innerHTML, /더 보여드릴 자료가 없어요/);
  vm.runInContext(`
    state.hasMoreSignals = true;
    showToast = () => {};
    api = async (url) => {
      if (url.endsWith('/more')) throw Error('network error');
      return {signals: state.signals, has_more: true, pipeline_run_id: 10};
    };
  `, context);
  await vm.runInContext('loadMoreSignals()', context);
  assert.equal(vm.runInContext('state.loadingMoreSignals', context), false);
  assert.match(element('signals-list').innerHTML, /추가 신호 보기/);
  console.log('Signal rendering, provenance, escaping, pagination, double-click and retry checks passed');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
