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
assert.match(html, /YouTube/);
assert.doesNotMatch(html, /수집 경로: Hacker News/);
assert.doesNotMatch(html, /샘플 자료 · 실제 최신 정보 아님/);
assert.doesNotMatch(html, /생성 당시 방식: 혼합 모드/);
assert.doesNotMatch(html, /관련 소스/);
assert.match(html, /AI에게 질문/);
assert.doesNotMatch(html, /자세히 보기/);
assert.match(html, /data-toggle-saved/);
assert.match(html, /https:\/\/youtu.be\/test/);
assert.doesNotMatch(html, /추가 신호 보기/);
vm.runInContext(`
  state.signals = [{id: 10, rank: 9, title: 'Newest'}, {id: 11, rank: 2, title: 'Older'}];
  state.hasMoreSignals = false;
  renderSignals();
`, context);
assert.match(element('signals-list').innerHTML, /<div class="rank">1<\/div>/);
assert.match(element('signals-list').innerHTML, /<div class="rank">2<\/div>/);
vm.runInContext(`state.signals = [{id: 1, title: 'Original signal'}];`, context);
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
console.log('Signal rendering, compact metadata and action grouping checks passed');
