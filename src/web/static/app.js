const state = {
  profile: null,
  settings: null,
  feedbackLearning: null,
  connectors: [],
  sources: [],
  interests: [],
  interestDrafts: {},
  interestRecommendations: [],
  feedbackSignals: [],
  feedbackLoadVersion: 0,
  feedbackPossiblyTruncated: false,
  feedbackMode: null,
  recommendationCategory: "tracked",
  signals: [],
  savedSignals: [],
  hasMoreSignals: false,
  signalRunId: null,
  signalLoadVersion: 0,
  loadingMoreSignals: false,
  activeTab: "signals",
  customizeTab: "news",
  briefingPeriod: "today",
  briefingDateKey: "",
  refreshingForDateChange: false,
  firstRun: false,
  authUser: null,
  authShell: {
    mode: "local",
    plan: "로컬 MVP",
    label: "로컬 모드",
    isMock: false,
  },
  cloudAccount: null,
  featureGates: null,
  engineV2: false,
  lastDismiss: null,
  briefingOperationState: "",
  briefingPeriodSnapshot: "",
  briefingDisplayMax: null,
  firstBriefingState: "",
  displayLimit: 5,
};

const sourceCopy = {
  geeknews: ["GeekNews", "한국 개발·기술·스타트업 커뮤니티의 링크와 토론입니다."],
  kisa_press: ["KISA 보도자료", "한국인터넷진흥원의 공식 보도자료입니다."],
  kisa_research: ["KISA 연구보고서", "한국인터넷진흥원의 공식 연구보고서입니다."],
  hackernews: ["Hacker News", "개발자와 스타트업 커뮤니티에서 빠르게 반응하는 흐름을 봐요."],
  github: ["GitHub", "오픈소스 저장소의 구현 움직임과 새 프로젝트를 확인해요."],
  rss: ["RSS / 공식 블로그", "직접 고른 피드와 제품 블로그에서 업데이트를 확인해요."],
  official_ai_blogs: ["Official AI Blogs", "주요 AI 회사의 공식 발표와 연구 업데이트를 확인해요."],
  producthunt: ["Product Hunt", "새 제품 출시 흐름을 볼 수 있도록 준비하고 있어요."],
  reddit: ["Reddit", "커뮤니티 반응을 조심스럽게 선별할 수 있도록 준비하고 있어요."],
  youtube: ["YouTube", "영상과 크리에이터의 최근 흐름을 수집해요."],
  naver_news: ["Naver News", "국내 산업과 기업 뉴스를 볼 수 있도록 준비하고 있어요."],
  arxiv: ["arXiv", "연구 논문 흐름을 볼 수 있도록 준비하고 있어요."],
  company_newsroom: ["Company Newsrooms", "회사 공식 뉴스룸을 더 편하게 연결할 수 있도록 준비하고 있어요."],
};

const sourceOrder = ["hackernews", "github", "rss", "official_ai_blogs", "geeknews", "kisa_press", "kisa_research", "producthunt", "reddit", "youtube", "naver_news", "arxiv", "company_newsroom"];
const hashToTab = {
  "#today": "signals",
  "#signals": "signals",
  "#saved": "saved",
  "#tracked": "customize",
  "#ignored": "customize",
  "#recommendations": "customize",
  "#interests": "interests",
  "#sources": "customize",
  "#activity": "activity",
  "#settings": "customize",
  "#customize": "customize",
  "#customize-feedback": "customize",
};
const tabToHash = {
  signals: "#today",
  saved: "#saved",
  interests: "#interests",
  activity: "#activity",
  customize: "#customize",
};

document.addEventListener("DOMContentLoaded", () => {
  initApp().catch(console.error);
});

async function initApp() {
  const initialScrollPosition = readStoredScrollPosition();

  // Auth guard: must run before any API call.
  // Returns false when navigating away (redirect to /login).
  const proceed = await initAuth();
  if (!proceed) return;

  // Do this before binding or fetching any briefing data.  The status is
  // resolved by the authenticated server-side user mapping, not local state.
  const onboarding = await api("/api/v1/onboarding/status");
  if (!onboarding.completed) {
    window.location.replace("/onboarding");
    return;
  }
  document.body.classList.remove("app-pending");

  initAuthShell();
  bindNavigation();
  bindTopActions();
  bindBriefingPeriods();
  bindBriefingAssistantCollision();
  bindSourceChat();
  bindBetaFeedback();
  applyHashTab({ load: false });
  window.addEventListener("hashchange", applyHashTab);
  window.addEventListener("pagehide", storeScrollPosition);

  await loadInitialData();
  startBriefingDayWatcher();
  startBriefingStatusPolling();

  if (state.activeTab !== "signals") await loadTab(state.activeTab);
  restoreScrollPosition(initialScrollPosition);
}

function bindNavigation() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveTab(button.dataset.tab, { updateHash: true, load: true });
    });
  });
}

function tabFromHash(hash = location.hash) {
  return hashToTab[hash] || "signals";
}

function applyHashTab(options = {}) {
  const knownHash = Boolean(hashToTab[location.hash]);
  const tab = tabFromHash(location.hash);
  const previousCategory = state.recommendationCategory;
  const previousCustomizeTab = state.customizeTab;
  if (location.hash === "#tracked") state.recommendationCategory = "tracked";
  if (location.hash === "#ignored") state.recommendationCategory = "ignored";
  if (tab === "customize") {
    const feedback = ["#tracked", "#ignored", "#recommendations", "#customize-feedback"].includes(location.hash);
    selectCustomizeTab(feedback ? "feedback" : "news", { load: options.load !== false && state.activeTab === "customize" });
    if (feedback && previousCustomizeTab === "feedback" && state.activeTab === "customize" && options.load !== false && previousCategory !== state.recommendationCategory) loadRecommendationSignals();
  }
  if (location.hash && !knownHash) {
    history.replaceState(null, "", tabToHash.signals);
  }
  setActiveTab(tab, { updateHash: false, load: options.load !== false });
}

function setActiveTab(tab, options = {}) {
  if (["recommendations", "sources", "settings"].includes(tab)) {
    selectCustomizeTab(tab === "recommendations" ? "feedback" : "news", { load: options.load && state.activeTab === "customize" });
    tab = "customize";
  }
  const nextTab = tabToHash[tab] ? tab : "signals";
  const changed = state.activeTab !== nextTab;
  const nextHash = nextTab === "customize" && state.customizeTab === "feedback" ? "#customize-feedback" : (tabToHash[nextTab] || tabToHash.signals);
  if (options.updateHash && location.hash !== nextHash) {
    history.replaceState(null, "", nextHash);
  }
  if (!changed && !options.load) return;
  tab = nextTab;
  state.activeTab = tab;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.tab === tab));
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  document.getElementById(`view-${tab}`)?.classList.add("active");
  if (options.load && changed) loadTab(tab);
}

function selectCustomizeTab(tab, options = {}) {
  const next = tab === "feedback" ? "feedback" : "news";
  const changed = state.customizeTab !== next;
  state.customizeTab = next;
  document.querySelectorAll("[data-custom-tab]").forEach((button) => {
    const selected = button.dataset.customTab === next;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
  });
  const news = document.getElementById("customize-news");
  const feedback = document.getElementById("customize-feedback");
  if (news) news.hidden = next !== "news";
  if (feedback) feedback.hidden = next !== "feedback";
  if (options.updateHash) history.replaceState(null, "", next === "feedback" ? "#customize-feedback" : "#customize");
  if (options.load && changed) loadCustomizeTab();
}

function bindTopActions() {
  document.querySelectorAll("[data-custom-tab]").forEach((button) => button.addEventListener("click", () => selectCustomizeTab(button.dataset.customTab, { updateHash: true, load: true })));
  document.getElementById("refresh-saved-signals").addEventListener("click", loadSavedSignals);
  document.getElementById("refresh-signals").addEventListener("click", refreshBriefing);
  document.getElementById("refresh-activity").addEventListener("click", loadActivity);
  document.getElementById("settings-form").addEventListener("submit", saveSettings);
  document.getElementById("add-interest").addEventListener("click", openInterestForm);
  document.getElementById("cancel-add-interest").addEventListener("click", closeInterestForm);
  document.getElementById("add-interest-form").addEventListener("submit", addManualInterest);
  document.querySelectorAll("[data-account-action]").forEach((button) => {
    button.addEventListener("click", () => handleAccountAction(button.dataset.accountAction));
  });
  document.getElementById("setting-signal-count")?.addEventListener("change", saveSettings);
}

// Keep period selection at the presentation boundary: card rendering and
// feedback actions stay independent from the period-query API.
function bindBriefingPeriods() {
  document.querySelectorAll("[data-period]").forEach((button) => {
    button.addEventListener("click", () => {
      state.briefingPeriod = button.dataset.period || "today";
      document.querySelectorAll("[data-period]").forEach((item) => {
        const selected = item === button;
        item.classList.toggle("active", selected);
        item.setAttribute("aria-selected", String(selected));
      });
      updateBriefingHeader();
      loadSignals();
      // Reset conversation so the next Assistant message uses the new period's signals.
      assistantState.conversationId = null;
      assistantState.selectedSignalId = null;
      updateChatPeriodLabel();
    });
  });
}

// Keep the floating launcher clear of briefing content while scrolling.
// Restore it as soon as the card or empty state is clear.
function bindBriefingAssistantCollision() {
  const launcher = document.getElementById("chat-launcher");
  if (!launcher) return;
  let queued = false;
  const update = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      const active = document.getElementById("view-signals")?.classList.contains("active");
      const a = launcher.getBoundingClientRect();
      const overlaps = active && [...document.querySelectorAll("#signals-list .signal-card, #signals-list .empty-state")].some((card) => {
        const b = card.getBoundingClientRect();
        return b.width && b.height && a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
      });
      if (launcher.classList.contains("briefing-control-overlap") !== Boolean(overlaps)) {
        launcher.classList.toggle("briefing-control-overlap", Boolean(overlaps));
      }
    });
  };
  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);
  const observer = new MutationObserver(update);
  observer.observe(document.getElementById("signals-list"), { childList: true, subtree: true });
  observer.observe(document.getElementById("view-signals"), { attributes: true, attributeFilter: ["class"] });
  update();
}

function updateBriefingHeader() {
  const labels = { today: "오늘의 브리핑", week: "이번 주 브리핑", month: "이번 달 브리핑" };
  document.getElementById("signals-title").textContent = labels[state.briefingPeriod] || labels.today;
}

// The server groups briefing periods by the Korean calendar.  Keep an open
// browser tab aligned with that calendar too, including after a laptop wakes
// from sleep (when a long timeout may have been delayed).
function koreanDateKey(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function millisecondsUntilNextKoreanMidnight(now = new Date()) {
  const [year, month, day] = koreanDateKey(now).split("-").map(Number);
  // Korea has a fixed UTC+09:00 offset and no daylight-saving transition.
  const nextMidnightUtc = Date.UTC(year, month - 1, day + 1, 0, 0, 0) - (9 * 60 * 60 * 1000);
  return Math.max(1000, nextMidnightUtc - now.getTime() + 250);
}

function startBriefingDayWatcher() {
  state.briefingDateKey = koreanDateKey();
  scheduleBriefingDayCheck();
  window.addEventListener("focus", checkBriefingDayChange);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) checkBriefingDayChange();
  });
}

function scheduleBriefingDayCheck() {
  window.clearTimeout(state.briefingDayTimer);
  state.briefingDayTimer = window.setTimeout(async () => {
    await checkBriefingDayChange();
    scheduleBriefingDayCheck();
  }, millisecondsUntilNextKoreanMidnight());
}

async function checkBriefingDayChange() {
  const currentDateKey = koreanDateKey();
  if (!state.briefingDateKey) {
    state.briefingDateKey = currentDateKey;
    return;
  }
  if (currentDateKey === state.briefingDateKey || state.refreshingForDateChange) return;

  state.briefingDateKey = currentDateKey;
  if (state.activeTab !== "signals" || state.briefingPeriod !== "today") return;

  state.refreshingForDateChange = true;
  try {
    await loadSignals();
  } finally {
    state.refreshingForDateChange = false;
  }
}

async function loadInitialData() {
  showLoading("signals-list", "오늘의 소식을 확인하고 있어요.");
  await Promise.allSettled([loadProfile(), loadSettings(), loadConnectors(), loadSources(), loadInterests(false), loadSignals(false), loadEngineStatus()]);
  detectFirstRun();
  renderFirstRunPanel();
  renderSettings();
  renderSignals();
}

async function loadEngineStatus() {
  try {
    const data = await api("/api/v1/engine/status");
    state.engineV2 = Boolean(data.enabled);
    const max = Number(data.max_briefing_display);
    state.briefingDisplayMax = Number.isInteger(max) && max > 0 ? max : null;
  } catch (_) {
    state.engineV2 = false;
    state.briefingDisplayMax = null;
  }
  renderSettings();
}

function startBriefingStatusPolling() {
  refreshBriefingOperationStatus();
  window.setInterval(refreshBriefingOperationStatus, 15000);
}

async function refreshBriefingOperationStatus() {
  if (!state.engineV2) return;
  try {
    const data = await api("/api/v1/engine/operations/status");
    const previous = state.briefingOperationState;
    const previousPeriods = state.briefingPeriodSnapshot;
    state.briefingOperationState = data.state || "ready";
    state.briefingPeriodSnapshot = JSON.stringify(data.periods || {});
    // Operational diagnostics remain available through the status endpoint;
    // the briefing itself presents a single content state.
    document.getElementById("generate-banner")?.classList.add("hidden");
    const finished = ["working", "collecting", "generating"].includes(previous) && ["ready", "insufficient"].includes(data.state);
    const cardsChanged = previousPeriods && previousPeriods !== state.briefingPeriodSnapshot;
    if (finished || cardsChanged) await loadSignals();
  } catch (_) {
    // The read-only status endpoint is optional during a rolling deployment.
  }
}

async function loadTab(tab) {
  if (tab === "signals") await loadSignals();
  if (tab === "saved") await loadSavedSignals();
  if (tab === "recommendations") await loadRecommendationSignals();
  if (tab === "interests") await loadInterests();
  if (tab === "sources") await loadSources();
  if (tab === "activity") await loadActivity();
  if (tab === "settings") {
    const settingsPromises = [loadSettings(), loadConnectors()];
    if (authClient.isDevMode()) {
      settingsPromises.push(loadCloudAccountStatus(), loadFeatureGates());
    }
    await Promise.allSettled(settingsPromises);
    renderSettings();
  }
  if (tab === "customize") await loadCustomizeTab();
}

async function loadCustomizeTab() {
  if (state.customizeTab === "feedback") return loadRecommendationSignals();
  await Promise.allSettled([loadSettings()]);
  await loadSources();
}

/**
 * apiFetch — central fetch wrapper for all /api/v1/* calls.
 *
 * In supabase auth mode: automatically attaches the current Bearer token.
 * On HTTP 401 in auth mode: checks session validity and redirects to /login
 * if the session is gone (prevents redirect loops via authClient._redirecting).
 * In local mode: behaves identically to a plain fetch.
 */
async function apiFetch(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (authClient.isAuthMode()) {
    const token = await authClient.getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && authClient.isAuthMode()) {
    const session = await authClient.getSession();
    if (!session) {
      authClient.redirectToLogin();
      throw new Error("인증이 만료됐어요. 다시 로그인해주세요.");
    }
  }
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : body.error || "";
    } catch (_) {}
    const error = new Error(detail || "잠시 연결이 불안정해요. 다시 시도해보세요.");
    error.status = response.status;
    throw error;
  }
  const data = await response.json();
  if (data.success === false) throw new Error(data.error || "잠시 연결이 불안정해요. 다시 시도해보세요.");
  return data;
}
// Backward-compat alias used throughout this file.
// Mutable for the isolated UI test harness; production code always keeps the
// default apiFetch implementation.
let api = apiFetch;

// Optional post-deployment features must not make an older-but-otherwise
// usable local server fail its core screens. The local OpenAPI document
// contains no user data and avoids writes to routes the running backend lacks.
const optionalApiSupport = new Map();

async function supportsOptionalApi(path, method = "get") {
  const key = `${method.toLowerCase()}:${path}`;
  if (optionalApiSupport.has(key)) return optionalApiSupport.get(key);
  try {
    const response = await fetch("/openapi.json", { cache: "no-store" });
    if (!response.ok) return null;
    const spec = await response.json();
    const supported = Boolean(spec?.paths?.[path]?.[method.toLowerCase()]);
    optionalApiSupport.set(key, supported);
    return supported;
  } catch (_) {
    // Preserve normal API behavior if capability discovery itself is absent.
    return null;
  }
}

async function loadProfile() {
  const data = await api("/api/v1/profile");
  state.profile = data.profile;
}

async function loadSettings() {
  const data = await api("/api/v1/settings");
  state.settings = data.settings;
  renderSettings();
}

async function loadConnectors() {
  const data = await api("/api/v1/connectors");
  state.connectors = data.connectors || [];
  renderSettings();
}

async function loadCloudAccountStatus() {
  if (state.authShell.isMock) return;
  try {
    state.cloudAccount = await api("/api/v1/product/cloud/account");
  } catch (error) {
    state.cloudAccount = {
      mode: "cloud_unavailable",
      connected: false,
      message: "Cloud backend 상태를 확인하지 못했어요. 로컬 모드는 계속 사용할 수 있어요.",
      error_code: "cloud_unavailable",
    };
  }
  renderAccountShell();
}

async function loadFeatureGates() {
  try {
    state.featureGates = await api("/api/v1/product/gates/status");
  } catch (error) {
    state.featureGates = {
      mode: "local",
      plan: "local_mvp",
      is_enforced: false,
      message: "현재는 로컬 모드로 모든 핵심 기능을 사용할 수 있어요.",
      gates: [],
    };
  }
  renderGateSummary();
}

async function loadSignals(render = true, scrollPosition = render ? captureScrollPosition() : null, options = {}) {
  const container = document.getElementById("signals-list");
  if (render && !options.preserve) showLoading("signals-list", "브리핑을 불러오고 있어요.");
  const period = state.briefingPeriod || "today";
  const loadVersion = ++state.signalLoadVersion;
  try {
    const data = await api(`/api/v1/signals?period=${encodeURIComponent(period)}`);
    // Polling and a period-tab change can overlap.  Never let a slower old
    // response replace the newer period's cards.
    if (loadVersion !== state.signalLoadVersion || state.briefingPeriod !== period) return;
    state.displayLimit = Math.max(1, Number(data.display_limit || state.displayLimit || 5));
    // The server is authoritative; retain this client cap to prevent stale
    // responses or a period switch from ever rendering reserve cards.
    state.signals = (data.signals || [])
      .filter((signal) => signal.status !== "archived")
      .slice(0, state.displayLimit);
    state.hasMoreSignals = Boolean(data.has_more);
    state.signalRunId = data.pipeline_run_id;
    state.firstBriefingState = data.first_briefing_state || "";
    state.signalLoadError = false;
    if (render) renderSignals();
  } catch (error) {
    if (loadVersion !== state.signalLoadVersion || state.briefingPeriod !== period) return;
    if (options.preserve) {
      showToast("브리핑을 새로 불러오지 못했어요. 다시 시도해 주세요.");
      return;
    }
    state.signalLoadError = true;
    if (render) {
      container.innerHTML = emptyState("잠시 연결이 불안정해요.", "다시 시도해보세요.", "새로고침", "retry-signals");
      bindEmptyAction("retry-signals", loadSignals);
    }
  } finally {
    restoreScrollPosition(scrollPosition);
  }
}

async function refreshBriefing() {
  const button = document.getElementById("refresh-signals");
  if (!button || button.disabled) return;
  const original = button.innerHTML;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = "불러오는 중…";
  try {
    await loadSignals(true, captureScrollPosition(), { preserve: true });
  } finally {
    button.innerHTML = original;
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

function renderSignals() {
  const container = document.getElementById("signals-list");
  if (state.signalLoadError) {
    container.innerHTML = emptyState("브리핑을 불러오지 못했어요.", "잠시 후 다시 시도해 주세요.", "다시 시도", "retry-signals");
    bindEmptyAction("retry-signals", loadSignals);
    return;
  }
  if (!state.signals.length) {
    const pending = state.firstBriefingState === "collection_pending";
    container.innerHTML = emptyState(
      pending ? "첫 브리핑을 준비하고 있어요." : "이번 기간에는 새로운 소식이 없어요.",
      pending ? "브리핑이 준비되면 이곳에서 확인할 수 있어요." : "관심사에 맞는 소식이 생기면 이곳에서 확인할 수 있어요.",
      "내 관심사 보기", "open-interests"
    );
    bindEmptyAction("open-interests", () => switchTab("interests"));
    return;
  }
  container.innerHTML = state.signals.map((signal, index) => renderSignalCard(signal, index + 1)).join("");
  bindSignalActions(container);
}

async function loadSavedSignals(render = true, scrollPosition = render ? captureScrollPosition() : null) {
  const container = document.getElementById("saved-signals-list");
  if (render) showLoading(container.id, "저장한 소식을 불러오고 있어요.");
  try {
    const data = await api("/api/v1/signals/saved");
    state.savedSignals = data.signals || [];
    if (render) renderSavedSignals();
  } catch (error) {
    if (render) {
      container.innerHTML = emptyState("저장한 소식을 불러오지 못했어요.", "잠시 후 다시 시도해주세요.", "새로고침", "retry-saved-signals");
      bindEmptyAction("retry-saved-signals", loadSavedSignals);
    }
  } finally {
    restoreScrollPosition(scrollPosition);
  }
}

function renderSavedSignals() {
  const container = document.getElementById("saved-signals-list");
  if (!state.savedSignals.length) {
    container.innerHTML = emptyState("아직 저장한 소식이 없어요.", "브리핑에서 저장하면 이곳에서 다시 볼 수 있어요.", "브리핑 보기", "open-signals");
    bindEmptyAction("open-signals", () => setActiveTab("signals", { updateHash: true, load: true }));
    return;
  }
  container.innerHTML = state.savedSignals.map((signal, index) => renderSavedSignalCard(signal, index + 1)).join("");
  container.querySelectorAll("[data-delete-saved]").forEach((button) => button.addEventListener("click", () => deleteSavedSignal(button.closest(".signal-card").dataset.signalId, button)));
  container.querySelectorAll("[data-open-url]").forEach((button) => button.addEventListener("click", () => window.open(button.dataset.openUrl, "_blank", "noopener,noreferrer")));
}

function renderSavedSignalCard(signal, rank) {
  const sourceItems = signal.source_items_json || [];
  const title = signal.display_title_ko || signal.title || "저장한 소식";
  const summary = signal.headline_summary_ko || signal.display_summary_ko || signal.summary || "";
  const url = signal.source_url || sourceItems.find((item) => item.url)?.url || "";
  const keywordOrigin = keywordOriginText(signal);
  return `<article class="signal-card saved-signal-card" data-signal-id="${signal.id}">
    <div class="signal-head"><div class="rank">${rank}</div><div><h3 class="signal-title" title="${escapeHtml(title)}">${escapeHtml(title)}</h3><p class="signal-summary">${escapeHtml(summary)}</p></div></div>
    <p class="signal-derived-from">${escapeHtml(keywordOrigin)}</p>
    <div class="signal-meta"><span class="pill">출처 ${escapeHtml(signal.source_display || sourceLabel(signal.source_name || "미확인"))}</span><span class="pill">저장한 날짜 ${escapeHtml(formatSavedDate(signal.saved_at || signal.created_at))}</span></div>
    <div class="actions"><button class="button primary" data-open-url="${escapeHtml(url)}" ${url ? "" : "disabled"}>원문 보기</button><button class="button danger" data-delete-saved>목록에서 빼기</button></div>
  </article>`;
}

async function deleteSavedSignal(signalId, button) {
  setBusy(button, true, "삭제 중");
  try {
    await api(`/api/v1/signals/${signalId}/saved`, { method: "DELETE" });
    state.savedSignals = state.savedSignals.filter((signal) => String(signal.id) !== String(signalId));
    renderSavedSignals();
    showToast("목록에서 뺐어요.");
  } catch (error) {
    showToast(error.message);
    setBusy(button, false, "목록에서 빼기");
  }
}

async function loadMoreSignals() {
  if (state.loadingMoreSignals || !state.hasMoreSignals || !state.signalRunId) return;
  state.loadingMoreSignals = true;
  const button = document.getElementById("more-signals");
  if (button) setBusy(button, true, "추가 소식을 불러오는 중…");
  try {
    await api("/api/v1/signals/more", {
      method: "POST",
      body: JSON.stringify({ pipeline_run_id: state.signalRunId }),
    });
    // Reload authoritative state: another tab may have generated a newer briefing.
    await loadSignals(false);
  } catch (error) {
    showToast(error.message);
    await loadSignals(false);
  } finally {
    state.loadingMoreSignals = false;
    renderSignals();
  }
}

function detectFirstRun() {
  const onboardingDone = Boolean(state.settings?.onboarding_completed);
  state.firstRun = Boolean(state.settings) && !onboardingDone;
}

function renderFirstRunPanel() {
  // First-run setup has its own route. Direct /app access redirects before
  // this legacy renderer can expose any setup UI.
}

async function generateSignals(triggerButton) {
  // Legacy v1 path retained only for older compatibility clients.  The
  // current UI never calls this; Engine v2 schedules work independently.
  const button = triggerButton || document.getElementById("generate-signals");
  if (!button) {
    await Promise.allSettled([loadSettings(), loadInterests(false), loadSignals(false)]);
    renderSignals();
    return;
  }
  const original = button.textContent;
  setBusy(button, true, "소식을 준비하는 중");
  const banner = document.getElementById("generate-banner");
  if (banner) banner.classList.remove("hidden");
  try {
    const mode = state.settings?.generate_mode || "hybrid";
    const data = await api("/api/v1/signals/generate", {
      method: "POST",
      body: JSON.stringify({ mode, replace_today: true }),
    });
    if (data.generated_signal_count) {
      showToast(`소식 ${data.generated_signal_count}개를 정리했어요.`);
    }
    await Promise.allSettled([loadSettings(), loadInterests(false), loadSignals(false)]);
    detectFirstRun();
    renderFirstRunPanel();
    renderSignals();
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(button, false, original);
    if (banner) banner.classList.add("hidden");
  }
}

function renderSignalCard(signal, listRank = 1) {
  const sourceItems = signal.source_items_json || [];
  const sourceUrl = signal.source_url || sourceItems.find((item) => item.url)?.url || "";
  const titleKo = signal.display_title_ko || signal.title || "오늘 확인할 소식";
  const headlineSummaryKo = signal.headline_summary_ko || signal.display_summary_ko || signal.summary || "원문에서 가져온 표현을 바탕으로 정리한 소식예요.";
  const storedReason = signal.recommendation_reason_ko || "";
  const reasonKo = needsRecommendationRewrite(storedReason) ? "" : storedReason;
  const matchedKeywords = signal.matched_keywords || signal.metadata_json?.matched_keywords || [];
  const sourceLabelText = signal.source_display || (signal.source_name ? sourceLabel(signal.source_name) : "");
  const contentType = humanCategory(signal.category);
  const dateText = signal.content_timestamp && !Number.isNaN(parseServerTimestamp(signal.content_timestamp).getTime())
    ? formatBriefingTimestamp(signal.content_timestamp) : "";
  const preference = signal.recommendation_preference || "";
  return `
    <article class="signal-card" data-signal-id="${signal.id}">
      <div class="signal-head">
        <div class="rank">${listRank}</div>
        <div>
          <h3 class="signal-title" title="${escapeHtml(titleKo)}">${escapeHtml(titleKo)}</h3>
          <p class="signal-summary">${escapeHtml(headlineSummaryKo)}</p>
        </div>
        <button class="bookmark-button ${signal.saved ? "is-saved" : ""}" type="button" data-toggle-saved aria-pressed="${signal.saved ? "true" : "false"}" aria-label="${signal.saved ? "저장 해제" : "저장"}" title="${signal.saved ? "저장 해제" : "저장"}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4.75A1.75 1.75 0 0 1 7.75 3h8.5A1.75 1.75 0 0 1 18 4.75V21l-6-3.8L6 21V4.75Z"/></svg></button>
      </div>
      <div class="signal-body">
        ${reasonKo ? `<div class="recommendation-reason"><strong>왜 추천했나요?</strong><p>${escapeHtml(reasonKo)}</p></div>` : ""}
      </div>
      ${sourceLabelText || contentType || dateText ? `<div class="signal-meta compact">${sourceLabelText ? `<span class="pill">${escapeHtml(sourceLabelText)}</span>` : ""}${contentType ? `<span class="pill">${escapeHtml(contentType)}</span>` : ""}${dateText ? `<span class="pill">${escapeHtml(dateText)}</span>` : ""}</div>` : ""}
      <div class="card-footer-actions">
        <div class="recommendation-control">
          <button class="button secondary" type="button" data-recommendation-menu aria-expanded="false">추천 조절</button>
          <div class="recommendation-menu hidden" data-recommendation-popover>
            <button type="button" data-set-preference="tracked" class="${preference === "tracked" ? "selected" : ""}"><svg class="preference-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10v10H4V10h3Zm2 10h7.1a2 2 0 0 0 1.9-1.37l2-6A2 2 0 0 0 18.1 10H14l.6-3.1A2.4 2.4 0 0 0 12.24 4L9 10v10Z"/></svg><span><strong>이런 소식 더 보기</strong><small>비슷한 소식을 더 추천받아요.</small></span></button>
            <button type="button" data-set-preference="ignored" class="${preference === "ignored" ? "selected" : ""}"><svg class="preference-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 14V4H4v10h3Zm2-10h7.1A2 2 0 0 1 18 5.37l2 6A2 2 0 0 1 18.1 14H14l.6 3.1A2.4 2.4 0 0 1 12.24 20L9 14V4Z"/></svg><span><strong>이런 소식 줄이기</strong><small>비슷한 소식의 추천을 줄여요.</small></span></button>
          </div>
        </div>
        <div class="actions card-primary-actions">
          <button class="button primary" data-open-url="${escapeHtml(sourceUrl)}" ${sourceUrl ? "" : "disabled"}>원문 보기</button>
          <button class="button secondary" data-ask-assistant="${signal.id}" data-signal-title="${escapeHtml(titleKo)}">AI에게 질문</button>
        </div>
      </div>
    </article>
  `;
}

function formatBriefingTimestamp(value) {
  if (!value) return "방금 수집";
  const date = parseServerTimestamp(value);
  if (Number.isNaN(date.getTime())) return "수집 시점 미확인";
  return `게시 ${date.toLocaleDateString("ko-KR", { month: "long", day: "numeric" })}`;
}

function helpfulTermsAndTrendText(signal, matchedKeywords) {
  const terms = [...new Set([
    ...(matchedKeywords || []),
    humanCategory(signal.category),
  ].map(humanReadableTerm).filter(Boolean))].slice(0, 3);
  return terms.join(" · ");
}

function cleanCoreSummary(value) {
  return String(value || "")
    .replace(/^이 자료의 주제:\s*[^\n]+(?:\n\s*\n)?/u, "")
    .replace(/^제공된 설명:\s*/u, "")
    .trim();
}

function humanReadableTerm(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const labels = {
    AI_LLM_AGENT: "AI·언어 모델·에이전트",
    RESEARCH: "연구",
    STARTUP_PRODUCT: "스타트업과 제품",
    DEVELOPER_TECH: "개발자 도구",
    COMPANY_TRACKING: "기업 변화",
    CONTENT_SNS: "콘텐츠와 커뮤니티",
    CAREER: "커리어",
    DOMESTIC_INDUSTRY: "국내 산업",
  };
  if (labels[raw]) return labels[raw];
  if (/^[A-Z][A-Z0-9_]*$/.test(raw) || raw.includes("_")) return "";
  return raw;
}

function needsRecommendationRewrite(reason) {
  return !reason || /최근 추천 기준에|내 관심 기준|이\(가\)|관심사.+관련된 자료/u.test(String(reason));
}

function bindSignalActions(container) {
  container.querySelectorAll("[data-toggle-saved]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest(".signal-card");
      const saved = button.getAttribute("aria-pressed") !== "true";
      const scrollPosition = captureScrollPosition();
      button.disabled = true;
      try {
        await api(`/api/v1/signals/${card.dataset.signalId}/saved`, {
          method: "PUT",
          body: JSON.stringify({ saved }),
        });
        showToast(saved ? "저장했어요." : "저장을 해제했어요.");
        await loadSignals(false);
        renderSignals();
        restoreScrollPosition(scrollPosition);
      } catch (error) {
        // A running pre-update local server may not have the new PUT route
        // yet. The long-standing feedback endpoint keeps saving available
        // until that server is restarted.
        if (error.status === 404 || error.status === 405) {
          try {
            await api(`/api/v1/signals/${card.dataset.signalId}/feedback`, {
              method: "POST",
              body: JSON.stringify({ event_type: "saved", payload: { surface: "web_app" } }),
            });
            showToast("저장했어요.");
            await loadSignals(false);
            renderSignals();
          } catch (fallbackError) {
            showToast(fallbackError.message);
          }
        } else showToast(error.message);
      } finally {
        button.disabled = false;
      }
    });
  });

  container.querySelectorAll("[data-recommendation-menu]").forEach((button) => button.addEventListener("click", () => toggleRecommendationMenu(button)));
  container.querySelectorAll("[data-set-preference]").forEach((button) => button.addEventListener("click", () => setRecommendationPreference(button)));

  container.querySelectorAll("[data-open-url]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest(".signal-card");
      const url = button.dataset.openUrl;
      if (!url) return;
      try {
        await api(`/api/v1/signals/${card.dataset.signalId}/feedback`, {
          method: "POST",
          body: JSON.stringify({ event_type: "opened", payload: { surface: "web_app" } }),
        });
        showToast("열람 기록을 남겼어요");
      } catch (_) {
        showToast("원문을 열게요");
      }
      window.open(url, "_blank", "noopener,noreferrer");
    });
  });

  container.querySelectorAll("[data-ask-assistant]").forEach((button) => {
    button.addEventListener("click", () => {
      const signalId = parseInt(button.dataset.askAssistant, 10);
      const title = button.dataset.signalTitle || "이 소식";
      openAssistantWithSignal(signalId, title);
    });
  });
}

function closeRecommendationMenus(except = null) {
  document.querySelectorAll("[data-recommendation-popover]").forEach((menu) => {
    if (menu !== except) menu.classList.add("hidden");
  });
  document.querySelectorAll("[data-recommendation-menu]").forEach((button) => {
    if (!except || button.nextElementSibling !== except) button.setAttribute("aria-expanded", "false");
  });
}

function toggleRecommendationMenu(button) {
  const menu = button.nextElementSibling;
  const opening = menu.classList.contains("hidden");
  closeRecommendationMenus(opening ? menu : null);
  menu.classList.toggle("hidden", !opening);
  button.setAttribute("aria-expanded", String(opening));
}

// Per-card lock: prevents double-click and ensures sequential processing.
const _dismissLocks = new Set();
let _dismissGeneration = 0;

const feedbackReasonOptions = {
  ignored: [
    ["unrelated_subtopic", "관심 없는 세부 주제"],
    ["too_technical", "너무 전문적이거나 어려움"],
    ["already_known", "이미 알고 있는 정보"],
    ["not_needed_now", "지금 필요하지 않음"],
    ["too_general", "정보가 너무 일반적임"],
  ],
  tracked: [
    ["directly_relevant", "내 관심사와 직접 관련"],
    ["practical_useful", "실제로 활용할 수 있음"],
    ["easy_to_understand", "쉽게 이해할 수 있음"],
    ["timely", "지금 확인할 만함"],
  ],
};

async function setRecommendationPreference(button) {
  const card = button.closest(".signal-card");
  const signalId = card.dataset.signalId;
  const preference = button.dataset.setPreference;
  const current = card.querySelector("[data-set-preference].selected")?.dataset.setPreference || null;
  const next = current === preference ? null : preference;

  // Per-card lock: reject if this card already has an in-flight request.
  if (_dismissLocks.has(signalId)) return;
  _dismissLocks.add(signalId);
  button.disabled = true;
  closeRecommendationMenus();

  // Capture the period at call time — if it changes mid-flight, discard stale results.
  const callPeriod = state.briefingPeriod;
  const callGeneration = ++_dismissGeneration;
  // An earlier read must not put a card back while its dismissal is pending.
  if (state.engineV2 && next === "ignored") ++state.signalLoadVersion;
  const callLoadVersion = state.signalLoadVersion;
  let optimisticDismiss = null;

  try {
    // Engine v2 dismiss path: remove card, backfill, show undo toast.
    if (state.engineV2 && next === "ignored") {
      const dismissedIndex = state.signals.findIndex((s) => String(s.id) === String(signalId));
      const dismissedSignal = dismissedIndex >= 0 ? state.signals[dismissedIndex] : null;
      optimisticDismiss = { dismissedIndex, dismissedSignal };
      if (dismissedIndex >= 0) {
        state.signals.splice(dismissedIndex, 1);
        renderSignals();
      }
      const data = await api("/api/v1/engine/briefing/dismiss", {
        method: "POST",
        body: JSON.stringify({ signal_id: Number(signalId), period: callPeriod || "today" }),
      });

      // Discard if period changed while awaiting.
      if (state.briefingPeriod !== callPeriod) return;

      const replacement = data.replacement;
      // A read may have completed while the dismissal was in flight. Keep its
      // result from restoring the dismissed card or duplicating the reserve.
      state.signals = state.signals.filter((signal) =>
        String(signal.id) !== String(signalId) && (!replacement || String(signal.id) !== String(replacement.id))
      );
      if (replacement) {
        const insertAt = Math.min(dismissedIndex >= 0 ? dismissedIndex : state.signals.length, state.signals.length);
        state.signals.splice(insertAt, 0, replacement);
      }
      renderSignals();

      state.lastDismiss = { signalId, dismissedSignal, dismissedIndex, replacement, generation: callGeneration };
      showToastWithUndo("비슷한 소식을 줄일게요.", async () => {
        // Stale check: if another dismiss happened after this one, skip undo.
        if (state.lastDismiss?.generation !== callGeneration) return;
        try {
          await api("/api/v1/engine/briefing/undo-dismiss", {
            method: "POST",
            body: JSON.stringify({ signal_id: Number(signalId) }),
          });
          if (replacement) {
            state.signals = state.signals.filter((s) => String(s.id) !== String(replacement.id));
          }
          if (dismissedSignal && dismissedIndex >= 0) {
            state.signals.splice(Math.min(dismissedIndex, state.signals.length), 0, dismissedSignal);
          }
          state.lastDismiss = null;
          renderSignals();
          showToast("되돌렸어요.");
        } catch (err) {
          showToast(err.message || "되돌리지 못했어요.");
        }
      }, { signalId, preference: "ignored" });
      return;
    }

    // Engine v2 undo path: clearing a previous "ignored" preference.
    if (state.engineV2 && current === "ignored" && next === null) {
      await api("/api/v1/engine/briefing/undo-dismiss", {
        method: "POST",
        body: JSON.stringify({ signal_id: Number(signalId) }),
      });
      if (state.briefingPeriod !== callPeriod) return;
      showToast("추천 선택을 해제했어요.");
      await loadSignals(false);
      renderSignals();
      return;
    }

    // Default v1 path (tracked, or v2 disabled).
    await api(`/api/v1/signals/${signalId}/recommendation-preference`, {
      method: "PUT",
      body: JSON.stringify({ preference: next }),
    });
    if (state.briefingPeriod !== callPeriod) return;
    if (next === "tracked") showFeedbackReasonPrompt(signalId, "tracked", "비슷한 소식을 더 추천할게요.");
    else if (next === "ignored") showFeedbackReasonPrompt(signalId, "ignored", "비슷한 소식을 줄일게요.");
    else showToast("추천 선택을 해제했어요.");
    await loadSignals(false);
    renderSignals();
  } catch (error) {
    if (optimisticDismiss?.dismissedSignal && state.briefingPeriod === callPeriod &&
        state.signalLoadVersion === callLoadVersion &&
        !state.signals.some((signal) => String(signal.id) === String(signalId))) {
      state.signals.splice(Math.min(optimisticDismiss.dismissedIndex, state.signals.length), 0, optimisticDismiss.dismissedSignal);
      renderSignals();
    }
    showToast(error.message);
    button.disabled = false;
  } finally {
    _dismissLocks.delete(signalId);
  }
}

// Feedback completion is intentionally compact.  Reason collection opens in
// a separate, optional panel so a successful dismissal never expands into a
// large notification over the briefing itself.
const feedbackReasonLabels = {
  unrelated_subtopic: "관심 없는 주제예요",
  too_technical: "내용이 너무 어려워요",
  already_known: "이미 알고 있는 소식이에요",
  not_needed_now: "지금은 필요하지 않아요",
  too_general: "내용이 너무 일반적이에요",
  directly_relevant: "관심사와 직접 관련 있어요",
  practical_useful: "실제로 도움이 돼요",
  easy_to_understand: "이해하기 쉬워요",
  timely: "지금 확인할 만해요",
};

function closeFeedbackReasonPanel() {
  document.getElementById("feedback-reason-panel")?.remove();
  document.body.classList.remove("feedback-reason-open");
}

function buildFeedbackReasonButton(signalId, preference) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "toast-reason";
  button.textContent = "이유 알려주기";
  button.addEventListener("click", async () => {
    const supported = await supportsOptionalApi(
      "/api/v1/signals/{signal_id}/recommendation-reason", "put"
    );
    if (supported === false) {
      showToast("이유 저장 기능을 준비 중이에요. 페이지를 새로고침한 뒤 다시 시도해 주세요.");
      return;
    }
    showFeedbackReasonPanel(signalId, preference);
  });
  return button;
}

function feedbackReasonSaveErrorMessage(error) {
  // Do not expose framework messages such as "Not Found" in the feedback
  // panel. A 404 here usually means a rolling deployment has served the new
  // UI before the matching optional-reason route is available.
  if (error?.status === 404) {
    return "이유 저장 기능을 준비 중이에요. 페이지를 새로고침한 뒤 다시 시도해 주세요.";
  }
  if (error?.status === 400) {
    return "현재 카드 평가와 이유가 맞지 않아요. 다시 평가한 뒤 이유를 선택해 주세요.";
  }
  return "이유를 저장하지 못했어요. 다시 시도해 주세요.";
}

function showFeedbackReasonPanel(signalId, preference) {
  closeFeedbackReasonPanel();
  const options = feedbackReasonOptions[preference] || [];
  if (!options.length) return;
  const panel = document.createElement("section");
  panel.id = "feedback-reason-panel";
  panel.className = "feedback-reason-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "false");
  panel.setAttribute("aria-labelledby", "feedback-reason-title");
  panel.innerHTML = `
    <div class="feedback-reason-panel-heading">
      <div><strong id="feedback-reason-title">추천이 맞지 않았던 이유</strong><p>선택하지 않아도 괜찮아요.</p></div>
      <button type="button" class="feedback-reason-close" aria-label="이유 선택 닫기">×</button>
    </div>
    <div class="feedback-reason-options">${options.map(([code]) =>
      `<button type="button" data-feedback-reason="${escapeHtml(code)}">${escapeHtml(feedbackReasonLabels[code] || code)}</button>`).join("")}</div>
    <p class="feedback-reason-status" role="status" aria-live="polite"></p>`;
  document.body.appendChild(panel);
  document.body.classList.add("feedback-reason-open");
  panel.querySelector(".feedback-reason-close")?.addEventListener("click", closeFeedbackReasonPanel);
  panel.querySelector("[data-feedback-reason]")?.focus();
  panel.querySelectorAll("[data-feedback-reason]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (panel.dataset.saving === "true") return;
      panel.dataset.saving = "true";
      panel.querySelectorAll("button").forEach((item) => { item.disabled = true; });
      try {
        await api(`/api/v1/signals/${encodeURIComponent(signalId)}/recommendation-reason`, {
          method: "PUT", body: JSON.stringify({ preference, reason_code: button.dataset.feedbackReason }),
        });
        closeFeedbackReasonPanel();
        showToast("의견을 반영했어요");
      } catch (error) {
        panel.dataset.saving = "false";
        panel.querySelectorAll("button").forEach((item) => { item.disabled = false; });
        const status = panel.querySelector(".feedback-reason-status");
        if (status) status.textContent = feedbackReasonSaveErrorMessage(error);
      }
    });
  });
}

function showToastWithUndo(message, onUndo, feedbackContext = null) {
  const toast = document.getElementById("toast");
  toast.innerHTML = "";
  const text = document.createElement("span");
  text.className = "toast-message";
  text.textContent = feedbackContext?.preference === "ignored" ? "이 카드를 추천에서 제외했어요" : message;
  const actions = document.createElement("span");
  actions.className = "toast-actions";
  const undo = document.createElement("button");
  undo.className = "toast-undo";
  undo.type = "button";
  undo.textContent = "실행 취소";
  undo.addEventListener("click", () => {
    closeFeedbackReasonPanel();
    toast.classList.remove("show");
    clearTimeout(showToast.timer);
    onUndo();
  });
  actions.appendChild(undo);
  if (feedbackContext) actions.appendChild(buildFeedbackReasonButton(feedbackContext.signalId, feedbackContext.preference));
  toast.append(text, actions);
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 5000);
}

function showFeedbackReasonPrompt(signalId, preference, message) {
  const toast = document.getElementById("toast");
  toast.innerHTML = "";
  const text = document.createElement("span");
  text.className = "toast-message";
  text.textContent = preference === "ignored" ? "이 카드를 추천에서 제외했어요" : message;
  const actions = document.createElement("span");
  actions.className = "toast-actions";
  actions.appendChild(buildFeedbackReasonButton(signalId, preference));
  toast.append(text, actions);
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 5000);
}

document.addEventListener("click", (event) => {
  if (!event.target.closest(".recommendation-control")) closeRecommendationMenus();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeRecommendationMenus();
    closeFeedbackReasonPanel();
  }
});

async function loadInterests(render = true, scrollPosition = render ? captureScrollPosition() : null) {
  const container = document.getElementById("interests-list");
  if (render) showLoading("interests-list", "관심사를 불러오고 있어요.");
  try {
    const [data, recommendations] = await Promise.all([
      api("/api/v1/interests?include_muted=true&limit=100"),
      api("/api/v1/interests/recommendations"),
    ]);
    state.interests = (data.interests || []).filter((interest) => interest.status !== "deleted");
    state.interestRecommendations = recommendations.recommendations || [];
    if (render) renderInterests();
  } catch (error) {
    if (render) {
      container.innerHTML = emptyState("잠시 연결이 불안정해요.", "다시 시도해보세요.", "새로고침", "retry-interests");
      bindEmptyAction("retry-interests", loadInterests);
    }
  } finally {
    restoreScrollPosition(scrollPosition);
  }
}

function renderInterests() {
  const container = document.getElementById("interests-list");
  if (!state.interests.length) {
    container.innerHTML = emptyState(
      "아직 추천 기준이 충분하지 않아요.",
      "관심 키워드를 추가하면 더 정확한 소식을 받을 수 있어요.",
      "관심사 추가하기",
      "add-interest-keyword"
    );
    bindEmptyAction("add-interest-keyword", openInterestForm);
    renderInterestRecommendations(container);
    return;
  }
  // Keep the clipped list surface separate from the auxiliary panels below it.
  // Feedback and recommendations must not inherit the list's overflow boundary.
  container.innerHTML = `<div class="interest-list">${state.interests.map(renderInterestCard).join("")}</div>`;
  bindInterestActions(container);
  renderInterestRecommendations(container);
}

function renderFeedbackLearningManagement() {
  const container = document.getElementById("feedback-learning-management");
  if (!container) return;
  const learning = state.feedbackLearning;
  if (!learning) { container.replaceChildren(); return; }
  const preferences = Array.isArray(learning.preferences) ? learning.preferences : [];
  container.innerHTML = `
    <details class="feedback-learning-panel">
      <summary class="feedback-learning-heading">
        <div><h3 id="feedback-learning-management-title">내 평가 경향</h3><p>${preferences.length ? "반복된 평가에서 발견한 경향이에요." : "아직 발견된 평가 경향이 없어요."}</p></div>
      </summary>
      <div class="feedback-learning-content">
        <div class="feedback-learning-items">${preferences.length ? preferences.map((preference) => `
          <div class="feedback-learning-item"><span>${escapeHtml(preference.label)}</span>
          <button class="button ghost" type="button" data-learning-action="reset-rule" data-feature="${escapeHtml(preference.feature)}" data-value="${escapeHtml(preference.value)}">초기화</button></div>`).join("")
          : `<p class="feedback-learning-empty">아직 기록된 선호가 없어요.</p>`}</div>
        ${preferences.length ? `<div class="feedback-learning-actions"><button class="button secondary" type="button" data-learning-action="reset-all">기록된 선호 초기화</button></div>` : ""}
      </div>
    </details>`;
  container.querySelector("[data-learning-action='reset-all']")?.addEventListener("click", async () => {
    try { await api("/api/v1/profile/feedback-learning", { method: "DELETE" }); await loadRecommendationSignals(); showToast("기록된 선호를 초기화했어요."); }
    catch (error) { showToast(error.message); }
  });
  container.querySelectorAll("[data-learning-action='reset-rule']").forEach((button) => button.addEventListener("click", async () => {
    try {
      await api("/api/v1/profile/feedback-learning/rule", { method: "DELETE", body: JSON.stringify({ feature: button.dataset.feature, value: button.dataset.value }) });
      await loadRecommendationSignals(); showToast("기록된 선호를 초기화했어요.");
    } catch (error) { showToast(error.message); }
  }));
}

function renderInterestRecommendations(container) {
  const recommendations = state.interestRecommendations || [];
  if (!recommendations.length) return;
  const section = document.createElement("section");
  section.className = "interest-recommendations";
  section.innerHTML = `<div class="recommendation-heading"><div><h3>이런 관심사는 어때요?</h3><p>필요하다면 관심사에 추가해 보세요.</p></div></div><div class="recommendation-list">${recommendations.map(renderInterestRecommendation).join("")}</div>`;
  container.appendChild(section);
  section.querySelectorAll("[data-recommendation-action]").forEach((button) => {
    button.addEventListener("click", () => handleInterestRecommendation(button));
  });
}

async function loadRecommendationSignals(render = true, scrollPosition = render ? captureScrollPosition() : null) {
  const container = document.getElementById("recommendation-signals-list");
  const loadVersion = ++state.feedbackLoadVersion;
  if (render) { setText("feedback-count", ""); showLoading(container.id, "평가 내역을 불러오고 있어요."); }
  try {
    const feedbackLearningRequest = (async () => {
      const supported = await supportsOptionalApi("/api/v1/profile/feedback-learning");
      return supported === false ? null : api("/api/v1/profile/feedback-learning").catch(() => null);
    })();
    const [tracked, ignored, feedbackLearning] = await Promise.all([
      api("/api/v1/signals/feedback/tracked"), api("/api/v1/signals/feedback/ignored"), feedbackLearningRequest,
    ]);
    if (loadVersion !== state.feedbackLoadVersion) return;
    // Each existing feedback endpoint returns at most 100 items and does not
    // provide a total, so do not claim an exhaustive count at that boundary.
    state.feedbackPossiblyTruncated = (tracked.signals || []).length >= 100 || (ignored.signals || []).length >= 100;
    const entries = [
      ...(tracked.signals || []).map((signal) => ({ ...signal, recommendation_preference: "tracked" })),
      ...(ignored.signals || []).map((signal) => ({ ...signal, recommendation_preference: "ignored" })),
    ];
    state.feedbackSignals = entries.sort((a, b) => {
      const time = (item) => {
        if (!item.feedback_at) return -Infinity;
        const value = parseServerTimestamp(item.feedback_at).getTime();
        return Number.isNaN(value) ? -Infinity : value;
      };
      return time(b) - time(a) || 0;
    });
    state.feedbackLearning = feedbackLearning;
    if (render) { renderRecommendationSignals(); renderFeedbackLearningManagement(); }
  } catch (error) {
    if (loadVersion !== state.feedbackLoadVersion) return;
    if (render) {
      setText("feedback-count", "");
      container.innerHTML = emptyState("추천 선택을 불러오지 못했어요.", "잠시 후 다시 시도해주세요.", "새로고침", "retry-recommendations");
      bindEmptyAction("retry-recommendations", loadRecommendationSignals);
    }
  } finally {
    restoreScrollPosition(scrollPosition);
  }
}

function renderRecommendationSignals() {
  const container = document.getElementById("recommendation-signals-list");
  setText("feedback-count", `${state.feedbackPossiblyTruncated ? "최근" : "총"} ${state.feedbackSignals.length}건`);
  if (!state.feedbackSignals.length) {
    container.innerHTML = `<div class="feedback-empty"><p>아직 평가한 소식이 없어요.</p><button class="button secondary" type="button" data-action="open-signals">브리핑 보기</button></div>`;
    bindEmptyAction("open-signals", () => setActiveTab("signals", { updateHash: true, load: true }));
    return;
  }
  container.innerHTML = state.feedbackSignals.map((signal, index) => renderFeedbackSignalCard(signal, index + 1)).join("");
  container.querySelectorAll("[data-clear-feedback]").forEach((button) => button.addEventListener("click", () => clearFeedbackSignal(button.closest(".signal-card").dataset.signalId, button)));
  container.querySelectorAll("[data-open-url]").forEach((button) => button.addEventListener("click", () => window.open(button.dataset.openUrl, "_blank", "noopener,noreferrer")));
}

function renderFeedbackSignalCard(signal, listRank) {
  const title = signal.display_title_ko || signal.title || "피드백한 소식";
  const summary = signal.headline_summary_ko || signal.display_summary_ko || signal.summary || "";
  const url = signal.source_url || "";
  const keywords = (signal.matched_keywords || signal.metadata_json?.matched_keywords || []).slice(0, 3).map(String).filter(Boolean);
  const source = signal.source_display || (signal.source_name ? sourceLabel(signal.source_name) : "");
  const reason = feedbackReasonLabels[signal.feedback_reason_code] || "";
  const more = (signal.recommendation_preference || state.recommendationCategory) === "tracked";
  return `<article class="signal-card feedback-management-item" data-signal-id="${signal.id}">
    <div class="feedback-item-content"><span class="feedback-item-rating">${more ? "더 보고 싶어요" : "덜 보고 싶어요"}</span><h3>${escapeHtml(title)}</h3>${summary ? `<p class="feedback-item-summary">${escapeHtml(summary)}</p>` : ""}<div class="feedback-item-meta">${source ? `<span>${escapeHtml(source)}</span>` : ""}${signal.feedback_at && !Number.isNaN(parseServerTimestamp(signal.feedback_at).getTime()) ? `<span>${escapeHtml(formatSavedDate(signal.feedback_at))}</span>` : ""}${keywords.length ? `<span>${escapeHtml(keywords.join(" · "))}</span>` : ""}${reason ? `<span>평가 이유: ${escapeHtml(reason)}</span>` : ""}</div></div>
    <div class="feedback-item-actions">${url ? `<button class="button ghost" data-open-url="${escapeHtml(url)}">원문 보기</button>` : ""}<button class="button secondary" data-clear-feedback>${more ? "더 보기 취소" : "제외 취소"}</button></div></article>`;
}

async function clearFeedbackSignal(signalId, button) {
  const scrollPosition = captureScrollPosition();
  const original = button.textContent;
  setBusy(button, true, "취소 중");
  try {
    await api(`/api/v1/signals/${signalId}/recommendation-preference`, { method: "PUT", body: JSON.stringify({ preference: null }) });
    state.feedbackSignals = state.feedbackSignals.filter((signal) => String(signal.id) !== String(signalId));
    renderRecommendationSignals();
    restoreScrollPosition(scrollPosition);
    showToast("평가를 취소했어요.");
    await loadRecommendationSignals();
  } catch (error) {
    showToast(error.message);
    setBusy(button, false, original);
  }
}

function renderInterestRecommendation(recommendation) {
  return `<article class="recommendation-card" data-keyword="${escapeHtml(recommendation.keyword)}"><strong>${escapeHtml(recommendation.keyword)}</strong><div class="recommendation-actions"><button class="button secondary" data-recommendation-action="add">추가</button><button class="button ghost" data-recommendation-action="dismiss">추천에서 제외</button></div></article>`;
}

async function handleInterestRecommendation(button) {
  const card = button.closest(".recommendation-card");
  const keyword = card.dataset.keyword;
  const action = button.dataset.recommendationAction;
  const original = button.textContent;
  setBusy(button, true, action === "add" ? "추가 중" : "삭제 중");
  try {
    if (action === "add") await api("/api/v1/interests", { method: "POST", body: JSON.stringify({ keyword }) });
    else await api(`/api/v1/interests/recommendations/${encodeURIComponent(keyword)}/dismiss`, { method: "POST" });
    await loadInterests();
    showToast(action === "add" ? "관심 키워드를 추가했어요." : "추천 키워드에서 삭제했어요.");
  } catch (error) {
    showToast(error.message);
    setBusy(button, false, original);
  }
}

function openInterestForm() {
  document.getElementById("add-interest-form").classList.remove("hidden");
  document.getElementById("add-interest").setAttribute("aria-expanded", "true");
  document.getElementById("new-interest-keyword").focus();
}

function closeInterestForm() {
  document.getElementById("add-interest-form").classList.add("hidden");
  document.getElementById("add-interest").setAttribute("aria-expanded", "false");
  document.getElementById("add-interest-error").textContent = "";
  document.getElementById("add-interest").focus();
}

async function addManualInterest(event) {
  event.preventDefault();
  const input = document.getElementById("new-interest-keyword");
  const error = document.getElementById("add-interest-error");
  const keyword = input.value.trim();
  error.textContent = "";
  if (!keyword) {
    error.textContent = "키워드를 입력해주세요.";
    input.focus();
    return;
  }
  const button = event.currentTarget.querySelector("button[type='submit']");
  setBusy(button, true, "추가 중");
  try {
    await api("/api/v1/interests", { method: "POST", body: JSON.stringify({ keyword }) });
    input.value = "";
    closeInterestForm();
    await Promise.all([loadInterests(), loadSettings()]);
    detectFirstRun();
    renderFirstRunPanel();
    showToast("관심 키워드를 추가했어요");
  } catch (failure) {
    error.textContent = failure.message;
    openInterestForm();
  } finally {
    setBusy(button, false, "추가");
  }
}

function renderInterestCard(interest) {
  const selectedTypes = informationTypePreferencesFor(interest.keyword);
  const selectedLabels = Array.isArray(interest.information_type_labels) ? interest.information_type_labels : selectedTypes;
  const importance = interestImportance(interest.weight);
  return `
    <article class="interest-list-item" data-keyword="${escapeHtml(interest.keyword)}" data-interest-status="${escapeHtml(interest.status)}">
      <div class="interest-card-header">
        <div class="interest-list-main">
          <h3>${escapeHtml(interest.keyword)}</h3>
          ${selectedLabels.length ? `<div class="interest-type-chips" aria-label="선택한 정보 유형">${selectedLabels.map((label) => `<span class="interest-type-chip">${escapeHtml(label)}</span>`).join("")}</div>` : ""}
          ${interest.status === "muted" ? `<p class="interest-muted-label">잠시 숨김</p>` : ""}
        </div>
        <span class="interest-priority-badge">중요도: <strong>${escapeHtml(importance.label)}</strong></span>
      </div>
      <div class="interest-list-actions">
        <button class="button secondary interest-edit-button" type="button" data-interest-action="edit" aria-label="${escapeHtml(interest.keyword)} 수정">수정</button>
      </div>
    </article>
  `;
}

function interestImportance(weight) {
  const numeric = Math.max(0, Number(weight) || 0);
  const level = numeric < 0.75 ? "low" : numeric < 2 ? "medium" : "high";
  return { level, label: { low: "낮음", medium: "보통", high: "높음" }[level] };
}

function importanceWeight(level) {
  // Viewing does not round or rewrite an existing weight. These values are
  // only sent when the reader explicitly changes the three-level setting.
  return { low: 0.5, medium: 1, high: 2 }[level];
}

function informationTypePreferences() {
  const raw = state.profile?.raw_onboarding_json || {};
  return raw.interest_type_preferences && typeof raw.interest_type_preferences === "object"
    ? raw.interest_type_preferences : {};
}

function informationTypePreferencesFor(keyword) {
  const target = String(keyword || "").trim().toLocaleLowerCase();
  const preferences = informationTypePreferences();
  const entry = Object.entries(preferences).find(([storedKeyword]) => String(storedKeyword).trim().toLocaleLowerCase() === target);
  return Array.isArray(entry?.[1]) ? entry[1] : [];
}

/* Retired modal editor. Card-local editing below owns the same API contract. */
/*
function closeInterestEditor({ restoreFocus = true } = {}) {
  const modal = document.querySelector(".interest-editor-modal");
  if (!modal) return;
  const opener = modal._opener;
  modal.remove();
  if (restoreFocus && opener && document.contains(opener)) opener.focus();
}

function openInterestEditor(interest, opener) {
  const selected = new Set(informationTypePreferencesFor(interest.keyword));
  const options = Array.isArray(interest.information_type_options) ? interest.information_type_options : [];
  const importance = interestImportance(interest.weight);
  const modal = document.createElement("div");
  modal.className = "interest-editor-modal";
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-labelledby", "interest-editor-title");
  modal._opener = opener;
  modal.innerHTML = `
    <div class="interest-editor-backdrop" data-interest-editor-close></div>
    <section class="interest-editor-panel">
      <header class="interest-editor-header">
        <div><p class="eyebrow">관심사 설정</p><h3 id="interest-editor-title">${escapeHtml(interest.keyword)}</h3></div>
        <button class="icon-button" type="button" aria-label="편집 닫기" data-interest-editor-close>×</button>
      </header>
      <div class="interest-editor-body">
        ${options.length ? `<fieldset class="interest-editor-section"><legend>보고 싶은 소식 종류</legend><div class="interest-type-editor-options">${options.map((option) => `
          <label class="information-type-option"><input type="checkbox" value="${escapeHtml(option.id)}" ${selected.has(option.id) ? "checked" : ""}><span>${escapeHtml(option.label)}</span></label>`).join("")}</div></fieldset>` : ""}
        <fieldset class="interest-editor-section"><legend>중요도</legend><div class="importance-level-options" role="radiogroup" aria-label="중요도">${[["low", "낮음"], ["medium", "보통"], ["high", "높음"]].map(([value, label]) => `<label><input type="radio" name="interest-importance" value="${value}" ${importance.level === value ? "checked" : ""}><span>${label}</span></label>`).join("")}</div></fieldset>
        <p class="interest-editor-error" role="alert" aria-live="polite"></p>
        <div class="interest-editor-secondary-actions">
          <button class="text-button" type="button" data-interest-editor-action="${interest.status === "muted" ? "unmute" : "mute"}">${interest.status === "muted" ? "다시 보기" : "잠시 숨기기"}</button>
          <button class="text-button danger" type="button" data-interest-editor-action="delete">관심사 삭제</button>
        </div>
        <section class="interest-editor-delete-confirmation hidden" role="alertdialog" aria-label="관심사 삭제 확인"></section>
      </div>
      <footer class="interest-editor-footer"><button class="button secondary" type="button" data-interest-editor-close>취소</button><button class="button primary" type="button" data-interest-editor-action="save">저장</button></footer>
    </section>`;
  document.body.appendChild(modal);
  modal.querySelector("[data-interest-editor-close]")?.focus();
  modal.querySelectorAll("[data-interest-editor-close]").forEach((button) => button.addEventListener("click", () => closeInterestEditor()));
  modal.querySelector("[data-interest-editor-action='save']")?.addEventListener("click", () => saveInterestEditor(interest, modal));
  modal.querySelector("[data-interest-editor-action='mute']")?.addEventListener("click", () => toggleInterestMuted(interest, modal));
  modal.querySelector("[data-interest-editor-action='unmute']")?.addEventListener("click", () => toggleInterestMuted(interest, modal));
  modal.querySelector("[data-interest-editor-action='delete']")?.addEventListener("click", () => confirmInterestDeletion(interest, modal));
}

async function saveInterestTypePreferences(keyword, values) {
  const epoch = interestAutosaveEpoch;
  const next = { ...informationTypePreferences() };
  const storedKey = Object.keys(next).find((item) => item.trim().toLocaleLowerCase() === String(keyword).trim().toLocaleLowerCase());
  if (values.length) next[storedKey || keyword] = values;
  else delete next[storedKey || keyword];
  const result = await api("/api/v1/profile/information-type-preferences", {
    method: "PUT", body: JSON.stringify({ interest_type_preferences: next }),
  });
  if (epoch === interestAutosaveEpoch) state.profile = result.profile;
}

function selectedInterestTypeValues(modal) {
  return Array.from(modal.querySelectorAll(".interest-type-editor-options input:checked")).map((input) => input.value).sort();
}

function sameValues(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function editorError(modal, message = "") {
  const node = modal.querySelector(".interest-editor-error");
  if (node) node.textContent = message;
}

async function saveInterestEditor(interest, modal) {
  const saveButton = modal.querySelector("[data-interest-editor-action='save']");
  const typeEditor = modal.querySelector(".interest-type-editor-options");
  const values = selectedInterestTypeValues(modal);
  const current = informationTypePreferencesFor(interest.keyword).slice().sort();
  const level = modal.querySelector("input[name='interest-importance']:checked")?.value;
  const targetWeight = importanceWeight(level);
  editorError(modal);
  setBusy(saveButton, true, "저장 중");
  try {
    // Some precise interests have retained type labels but no editable options
    // in the current taxonomy. Saving priority must never clear that data.
    if (typeEditor && !sameValues(current, values)) await saveInterestTypePreferences(interest.keyword, values);
    if (Number.isFinite(targetWeight) && targetWeight !== Number(interest.weight || 0)) {
      await api(`/api/v1/interests/${encodeURIComponent(interest.keyword)}`, { method: "PUT", body: JSON.stringify({ weight: targetWeight }) });
    }
    closeInterestEditor({ restoreFocus: false });
    await Promise.all([loadInterests(), loadSignals(false)]);
    showToast("관심사 설정을 저장했어요.");
  } catch (error) {
    editorError(modal, "저장하지 못했어요. 잠시 후 다시 시도해 주세요.");
    setBusy(saveButton, false, "저장");
  }
}

async function toggleInterestMuted(interest, modal) {
  const action = interest.status === "muted" ? "unmute" : "mute";
  const button = modal.querySelector(`[data-interest-editor-action='${action}']`);
  setBusy(button, true, action === "mute" ? "숨기는 중" : "다시 표시하는 중");
  editorError(modal);
  try {
    await api(`/api/v1/interests/${encodeURIComponent(interest.keyword)}/${action}`, { method: "POST" });
    closeInterestEditor({ restoreFocus: false });
    await Promise.all([loadInterests(), loadSignals(false)]);
    showToast(action === "mute" ? "관심사를 잠시 숨겼어요." : "관심사를 다시 표시해요.");
  } catch (error) {
    editorError(modal, "설정을 바꾸지 못했어요. 잠시 후 다시 시도해 주세요.");
    setBusy(button, false, action === "mute" ? "잠시 숨기기" : "다시 보기");
  }
}

function confirmInterestDeletion(interest, modal) {
  const confirmation = modal.querySelector(".interest-editor-delete-confirmation");
  confirmation.classList.remove("hidden");
  confirmation.innerHTML = `<strong>관심사를 삭제할까요?</strong><p>관심사 목록에서만 삭제합니다. 필요한 경우 다시 추가할 수 있어요.</p><div><button class="button secondary" type="button" data-interest-delete-action="cancel">취소</button><button class="button danger" type="button" data-interest-delete-action="confirm">삭제</button></div>`;
  confirmation.querySelector("[data-interest-delete-action='cancel']")?.addEventListener("click", () => confirmation.classList.add("hidden"));
  confirmation.querySelector("[data-interest-delete-action='confirm']")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    setBusy(button, true, "삭제 중");
    try {
      await api(`/api/v1/interests/${encodeURIComponent(interest.keyword)}`, { method: "DELETE" });
      closeInterestEditor({ restoreFocus: false });
      await Promise.all([loadInterests(), loadSignals(false)]);
      showToast("관심사를 삭제했어요.");
    } catch (error) {
      editorError(modal, "삭제하지 못했어요. 잠시 후 다시 시도해 주세요.");
      setBusy(button, false, "삭제");
    }
  });
  confirmation.querySelector("[data-interest-delete-action='cancel']")?.focus();
}

function bindInterestActions(container) {
  container.querySelectorAll("[data-interest-action='edit']").forEach((button) => {
    button.addEventListener("click", () => {
      const row = button.closest("[data-keyword]");
      const interest = state.interests.find((item) => item.keyword === row?.dataset.keyword);
      if (interest) openInterestEditor(interest, button);
    });
  });
}

*/

async function saveInterestTypePreferences(keyword, values) {
  const epoch = interestAutosaveEpoch;
  const next = { ...informationTypePreferences() };
  const storedKey = Object.keys(next).find((item) => item.trim().toLocaleLowerCase() === String(keyword).trim().toLocaleLowerCase());
  if (values.length) next[storedKey || keyword] = values;
  else delete next[storedKey || keyword];
  const result = await api("/api/v1/profile/information-type-preferences", {
    method: "PUT", body: JSON.stringify({ interest_type_preferences: next }),
  });
  if (epoch === interestAutosaveEpoch) state.profile = result.profile;
}

function sameValues(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

// Card-local drafts deliberately stay in memory until the reader chooses
// 저장. They never mutate an interest or the profile while the card is edited.
function interestDraftFor(interest) {
  const key = interest.keyword;
  if (!state.interestDrafts[key]) {
    state.interestDrafts[key] = {
      typeIds: informationTypePreferencesFor(key).slice().sort(),
      importance: interestImportance(interest.weight).level,
      typesOpen: false,
      deleteConfirm: false,
      error: "",
    };
  }
  return state.interestDrafts[key];
}

function labelsForInterestTypes(interest, typeIds) {
  const options = Array.isArray(interest.information_type_options) ? interest.information_type_options : [];
  const labels = new Map(options.map((option) => [option.id, option.label]));
  const stored = Array.isArray(interest.information_type_labels) ? interest.information_type_labels : [];
  return typeIds.map((typeId, index) => labels.get(typeId) || stored[index] || typeId);
}

function interestDraftChanged(interest, draft) {
  const currentTypes = informationTypePreferencesFor(interest.keyword).slice().sort();
  return !sameValues(currentTypes, draft.typeIds.slice().sort())
    || interestImportance(interest.weight).level !== draft.importance;
}

function renderInterestCard(interest) {
  const draft = interestDraftFor(interest);
  const options = Array.isArray(interest.information_type_options) ? interest.information_type_options : [];
  const labels = labelsForInterestTypes(interest, draft.typeIds);
  const muted = interest.status === "muted";
  return `
    <article class="interest-list-item" data-keyword="${escapeHtml(interest.keyword)}" data-interest-status="${escapeHtml(interest.status)}">
      <header class="interest-card-header">
        <div class="interest-list-main"><h3>${escapeHtml(interest.keyword)}</h3>${muted ? `<p class="interest-muted-label">잠시 숨김</p>` : ""}</div>
      </header>
      ${labels.length || options.length ? `<section class="interest-card-section interest-card-types" aria-label="보고 싶은 소식">
        <div class="interest-card-section-heading"><span>보고 싶은 소식</span>${options.length ? `<button class="text-button" type="button" data-interest-action="toggle-types">${labels.length ? "소식 종류 수정" : "+ 소식 종류 선택"}</button>` : ""}</div>
        ${labels.length ? `<div class="interest-type-chips" aria-label="선택한 정보 유형">${labels.map((label) => `<span class="interest-type-chip">${escapeHtml(label)}</span>`).join("")}</div>` : ""}
        ${draft.typesOpen && options.length ? `<div class="interest-type-editor-options interest-card-type-editor">${options.map((option) => `<label class="information-type-option"><input type="checkbox" data-interest-type="${escapeHtml(option.id)}" ${draft.typeIds.includes(option.id) ? "checked" : ""}><span>${escapeHtml(option.label)}</span></label>`).join("")}</div>` : ""}
      </section>` : ""}
      <section class="interest-card-section" aria-label="중요도">
        <span class="interest-card-section-label">중요도</span>
        <div class="importance-level-options interest-card-importance" role="radiogroup" aria-label="${escapeHtml(interest.keyword)} 중요도">${[["low", "낮음"], ["medium", "보통"], ["high", "높음"]].map(([value, label]) => `<button type="button" role="radio" aria-checked="${draft.importance === value}" class="${draft.importance === value ? "selected" : ""}" data-interest-action="importance" data-importance="${value}">${label}</button>`).join("")}</div>
      </section>
      <footer class="interest-card-footer">
        <div class="interest-card-management"><button class="text-button" type="button" data-interest-action="toggle-muted">${muted ? "다시 보기" : "잠시 숨기기"}</button><button class="text-button danger" type="button" data-interest-action="delete">관심사 삭제</button></div>
        ${draft.deleteConfirm ? `<div class="interest-card-delete-confirmation" role="alert"><p>이 관심사를 삭제할까요?</p><div><button class="button secondary" type="button" data-interest-action="delete-cancel">취소</button><button class="button danger" type="button" data-interest-action="delete-confirm">삭제</button></div></div>` : ""}
        ${draft.error ? `<p class="interest-card-error" role="alert">${escapeHtml(draft.error)}</p>` : ""}
      </footer>
    </article>`;
}

// The information-type endpoint replaces the complete profile map. Serialize
// all card writes so concurrent interests cannot overwrite one another.
let interestAutosaveQueue = Promise.resolve();
let interestAutosaveEpoch = 0;
function queueInterestAutosave(interest, kind, debounce = false) {
  const draft = interestDraftFor(interest);
  if (kind === "types") {
    clearTimeout(draft.timer);
    draft.timer = null;
    if (debounce) {
      draft.timer = setTimeout(() => { draft.timer = null; queueInterestAutosave(interest, kind); }, 350);
      return;
    }
  }
  draft.pending = (draft.pending || 0) + 1;
  draft.saving = true;
  draft.savingSince = draft.savingSince || Date.now();
  clearTimeout(draft.savingDisplayTimer);
  const epoch = interestAutosaveEpoch;
  interestAutosaveQueue = interestAutosaveQueue.catch(() => {}).then(async () => {
    if (epoch !== interestAutosaveEpoch) return;
    const target = kind === "types" ? draft.typeIds.slice().sort() : draft.importance;
    try {
      if (kind === "types") {
        const previous = informationTypePreferencesFor(interest.keyword).slice().sort();
        if (!sameValues(previous, target)) await saveInterestTypePreferences(interest.keyword, target);
      } else if (interestImportance(interest.weight).level !== target) {
        await api(`/api/v1/interests/${encodeURIComponent(interest.keyword)}`, { method: "PUT", body: JSON.stringify({ weight: importanceWeight(target) }) });
        interest.weight = importanceWeight(target);
        const current = state.interests.find((item) => item.keyword === interest.keyword);
        if (current) current.weight = interest.weight;
      }
      draft.error = "";
    } catch (_) {
      if (epoch === interestAutosaveEpoch) {
        if (kind === "types" && sameValues(draft.typeIds.slice().sort(), target)) draft.typeIds = informationTypePreferencesFor(interest.keyword).slice().sort();
        if (kind === "importance" && draft.importance === target) draft.importance = interestImportance(interest.weight).level;
        draft.error = "저장하지 못했어요. 다시 선택해 주세요.";
      }
    } finally {
      draft.pending = Math.max(0, draft.pending - 1);
      if (draft.pending === 0) {
        const remaining = Math.max(0, 800 - (Date.now() - draft.savingSince));
        draft.savingDisplayTimer = setTimeout(() => {
          if (draft.pending === 0) { draft.saving = false; draft.savingSince = 0; }
          if (epoch === interestAutosaveEpoch && state.activeTab === "interests") renderInterests();
        }, remaining);
      }
      if (epoch === interestAutosaveEpoch && state.activeTab === "interests") renderInterests();
    }
  });
}

window.addEventListener("beforeunload", (event) => {
  if (Object.values(state.interestDrafts).some((draft) => draft.saving || draft.timer)) {
    event.preventDefault();
    event.returnValue = "";
  }
});

async function saveInterestCardDraft(interest, button) {
  const draft = interestDraftFor(interest);
  const currentTypes = informationTypePreferencesFor(interest.keyword).slice().sort();
  const nextTypes = draft.typeIds.slice().sort();
  const targetWeight = importanceWeight(draft.importance);
  draft.error = "";
  setBusy(button, true, "저장 중");
  try {
    if (!sameValues(currentTypes, nextTypes)) await saveInterestTypePreferences(interest.keyword, nextTypes);
    if (Number.isFinite(targetWeight) && targetWeight !== Number(interest.weight || 0)) {
      await api(`/api/v1/interests/${encodeURIComponent(interest.keyword)}`, { method: "PUT", body: JSON.stringify({ weight: targetWeight }) });
      interest.weight = targetWeight;
    }
    delete state.interestDrafts[interest.keyword];
    await Promise.all([loadInterests(), loadSignals(false)]);
    showToast("관심사 설정을 저장했어요.");
  } catch (_) {
    draft.error = "저장하지 못했어요. 잠시 후 다시 시도해 주세요.";
    renderInterests();
  }
}

async function toggleInterestMutedInline(interest, button) {
  const pending = interestDraftFor(interest);
  if (pending.timer || pending.saving) { pending.error = "저장이 끝난 후 다시 시도해 주세요."; renderInterests(); return; }
  const action = interest.status === "muted" ? "unmute" : "mute";
  setBusy(button, true, action === "mute" ? "숨기는 중" : "다시 표시하는 중");
  try {
    await api(`/api/v1/interests/${encodeURIComponent(interest.keyword)}/${action}`, { method: "POST" });
    delete state.interestDrafts[interest.keyword];
    await Promise.all([loadInterests(), loadSignals(false)]);
    showToast(action === "mute" ? "관심사를 잠시 숨겼어요." : "관심사를 다시 표시해요.");
  } catch (_) {
    const draft = interestDraftFor(interest);
    draft.error = "설정을 바꾸지 못했어요. 잠시 후 다시 시도해 주세요.";
    renderInterests();
  }
}

async function deleteInterestInline(interest, button) {
  const pending = interestDraftFor(interest);
  if (pending.timer || pending.saving) { pending.error = "저장이 끝난 후 다시 시도해 주세요."; renderInterests(); return; }
  setBusy(button, true, "삭제 중");
  try {
    await api(`/api/v1/interests/${encodeURIComponent(interest.keyword)}`, { method: "DELETE" });
    delete state.interestDrafts[interest.keyword];
    await Promise.all([loadInterests(), loadSignals(false)]);
    showToast("관심사를 삭제했어요.");
  } catch (_) {
    const draft = interestDraftFor(interest);
    draft.error = "삭제하지 못했어요. 잠시 후 다시 시도해 주세요.";
    renderInterests();
  }
}

function bindInterestActions(container) {
  container.querySelectorAll("[data-keyword]").forEach((card) => {
    const interest = state.interests.find((item) => item.keyword === card.dataset.keyword);
    if (!interest) return;
    card.querySelectorAll("[data-interest-action]").forEach((button) => button.addEventListener("click", () => {
      const action = button.dataset.interestAction;
      const draft = interestDraftFor(interest);
      if (action === "toggle-types") { draft.typesOpen = !draft.typesOpen; renderInterests(); }
      if (action === "importance" && draft.importance !== button.dataset.importance) { draft.importance = button.dataset.importance; draft.error = ""; queueInterestAutosave(interest, "importance"); renderInterests(); }
      if (action === "toggle-muted") toggleInterestMutedInline(interest, button);
      if (action === "delete") { draft.deleteConfirm = true; renderInterests(); }
      if (action === "delete-cancel") { draft.deleteConfirm = false; renderInterests(); }
      if (action === "delete-confirm") deleteInterestInline(interest, button);
    }));
    card.querySelectorAll("[data-interest-type]").forEach((input) => input.addEventListener("change", () => {
      const draft = interestDraftFor(interest);
      const typeId = input.dataset.interestType;
      draft.typeIds = input.checked ? [...new Set([...draft.typeIds, typeId])] : draft.typeIds.filter((item) => item !== typeId);
      draft.error = "";
      queueInterestAutosave(interest, "types", true);
      renderInterests();
    }));
  });
}

async function loadSources(scrollPosition = captureScrollPosition()) {
  const container = document.getElementById("sources-list");
  showLoading("sources-list", "소스 설정을 확인하고 있어요.");
  try {
    const catalogData = await api("/api/v1/sources/catalog");
    state.sources = catalogData.sources || [];
    // The catalogue's availability is not proof of a user-scoped pilot or
    // actual collection. Only show routable selections with ordinary access.
    const sources = state.sources.filter((source) => source.available === true && source.implemented_status === "implemented" && source.effective_enabled === true && source.source_id !== "opendart");
    const names = { hackernews: "Hacker News", github: "GitHub", rss: "RSS", official_ai_blogs: "공식 AI 블로그", company_newsroom: "기업 뉴스룸", youtube: "YouTube", crossref: "Crossref", openalex: "OpenAlex", producthunt: "Product Hunt", reddit: "Reddit", naver_news: "네이버 뉴스", arxiv: "arXiv", mss_bizinfo: "중소벤처기업 지원사업", mss_support_program: "중소벤처기업 지원사업", public_institution_jobs: "공공기관 채용", public_service_jobs: "공공부문 채용", seoul_culture_events: "서울 문화행사", kopis: "KOPIS", youthcenter_policy: "온통청년", tourapi: "한국관광공사 TourAPI", employment24: "고용24", msit_announcements: "과학기술정보통신부 공고", msit_business_rss: "과학기술정보통신부 사업공고", msit_recruitment_rss: "과학기술정보통신부 채용공고", geeknews: "GeekNews", kisa_press: "KISA 보도자료", kisa_research: "KISA 연구보고서" };
    const region = state.settings?.source_region_preference || "both";
    container.innerHTML = `
      <section class="source-settings-panel" aria-labelledby="source-settings-heading">
        <h2 id="source-settings-heading">소식 지역</h2>
        <div class="source-settings-section">
        <div class="region-options" role="radiogroup" aria-label="소식 지역 선택">
          ${renderRegionOption("both", "국내 + 해외 모두", "두 지역에 관심이 있어요.", "모두", region)}
          ${renderRegionOption("domestic", "국내 소식 중심", "국내 소식에 더 관심이 있어요.", "국내 선호", region)}
          ${renderRegionOption("international", "해외 소식 중심", "해외 소식에 더 관심이 있어요.", "해외 선호", region)}
        </div></div>
        <p class="region-helper">표시되는 소식은 관심사와 이용 가능한 출처에 따라 달라져요.</p>
        <details class="source-available"><summary>참고 정보원</summary><p>관심사와 소식의 유무에 따라 실제 참고하는 출처는 달라져요.</p>${sources.length ? `<div class="source-available-list">${sources.map((source) => `<span>${escapeHtml(names[source.source_id] || source.display_name || source.source_id)}</span>`).join("")}</div>` : `<p>현재 표시할 수 있는 출처가 없어요.</p>`}</details>
      </section>`;
    bindSourceActions(container);
  } catch (error) {
    container.innerHTML = emptyState("잠시 연결이 불안정해요.", "다시 시도해보세요.", "새로고침", "retry-sources");
    bindEmptyAction("retry-sources", loadSources);
  } finally {
    restoreScrollPosition(scrollPosition);
  }
}

function renderRegionOption(value, title, description, tag, selected) {
  return `<label class="region-option"><input class="visually-hidden" type="radio" name="source-region" value="${value}" ${value === selected ? "checked" : ""} /><span class="region-option-content"><strong>${title}</strong></span></label>`;
}

function renderSourceManagementCard(source) {
  const [name, desc] = sourceCopy[source.source_id] || [source.display_name, source.description];
  const config = source.config_json || {};
  const isRssLike = ["rss", "official_ai_blogs", "company_newsroom"].includes(source.source_id);
  const mode = source.selection_mode || "auto";
  const availability = source.available ? "사용 가능"
    : source.capabilities?.distribution_status === "permission_review" ? "이용 조건 확인 필요"
    : source.implemented_status === "placeholder" ? "준비 중" : "연결 필요";
  const modeLabel = mode === "auto" ? "자동 추천" : mode === "enabled" ? "직접 사용" : "사용 안 함";
  const feedCount = isRssLike ? (config.feed_urls || []).length : 0;
  const feedNote = feedCount > 0 ? ` · 피드 ${feedCount}개` : "";
  return `<div class="source-list-item" data-source-id="${escapeHtml(source.source_id)}">
    <button class="source-item-header" type="button" aria-expanded="false">
      <div class="source-item-info"><span class="source-item-name">${escapeHtml(name)}</span><span class="source-item-desc">${escapeHtml(desc)}</span></div>
      <div class="source-item-badges"><span class="source-item-availability${source.available ? " available" : ""}">${escapeHtml(availability)}</span><span class="source-item-sep">·</span><span class="source-item-mode-badge">${escapeHtml(modeLabel)}${escapeHtml(feedNote)}</span></div>
      <span class="source-item-arrow" aria-hidden="true"></span>
    </button>
    <div class="source-item-detail" hidden>
      <div class="source-mode-row"><span class="source-mode-label">선택 방식</span><div class="segment-control" role="radiogroup" aria-label="${escapeHtml(name)} 선택 방식">${["auto", "enabled", "disabled"].map(v => `<label class="segment-option${mode === v ? " active" : ""}"><input type="radio" name="mode-${escapeHtml(source.source_id)}" value="${v}" ${mode === v ? "checked" : ""} class="visually-hidden" /><span>${v === "auto" ? "자동 추천" : v === "enabled" ? "직접 사용" : "사용 안 함"}</span></label>`).join("")}</div></div>
      ${!source.available ? `<p class="source-item-note">${escapeHtml(source.availability_reason || "연결 조건을 확인해주세요.")}</p>` : ""}
      ${isRssLike ? `<div class="source-rss-editor"><label class="form-group"><span>RSS feed URL</span><textarea data-feed-urls rows="3" placeholder="한 줄에 하나씩 입력하세요.">${escapeHtml((config.feed_urls || []).join("\n"))}</textarea></label><button class="button secondary" data-save-source>피드 저장</button></div>` : ""}
      <span class="source-save-status" aria-live="polite"></span>
    </div>
  </div>`;
}

function renderSourceCard(source) {
  const [name, description] = sourceCopy[source.source_id] || [source.display_name, source.description];
  const config = source.config_json || {};
  const isRssLike = ["rss", "official_ai_blogs", "company_newsroom"].includes(source.source_id);
  const status = sourceStatus(source);
  return `
    <article class="card" data-source-id="${source.source_id}">
      <div class="card-title"><h3>${escapeHtml(name)}</h3>${sourceStatusChip(status)}</div>
      <p>${escapeHtml(description)}</p>
      <label class="toggle-row">
        <span>사용하기</span>
        <input type="checkbox" data-source-enabled ${source.current_enabled ? "checked" : ""} ${status === "준비 중" ? "disabled" : ""} />
      </label>
      ${source.source_id === "github" ? `<p>GitHub 토큰은 선택 사항이에요. GITHUB_TOKEN 환경변수를 설정하면 더 안정적으로 수집할 수 있어요.</p>` : ""}
      ${source.source_id === "youtube" ? `<p>YouTube Data API 키를 연결하면 실제 영상을 수집해요. 서버의 YOUTUBE_API_KEY 환경변수에 키를 설정해주세요.</p>` : ""}
      ${isRssLike ? `<label class="form-group"><span>RSS feed URL</span><textarea data-feed-urls rows="4" placeholder="한 줄에 하나씩 입력하세요.">${escapeHtml((config.feed_urls || []).join("\n"))}</textarea></label>` : ""}
      <button class="button secondary" data-save-source ${status === "준비 중" ? "disabled" : ""}>저장</button>
    </article>
  `;
}

function bindSourceActions(container) {
  /* ── Expand / collapse source items ── */
  container.querySelectorAll(".source-item-header").forEach((btn) => {
    btn.addEventListener("click", () => {
      const item = btn.closest(".source-list-item");
      const detail = item.querySelector(".source-item-detail");
      const opening = detail.hidden;
      detail.hidden = !opening;
      btn.setAttribute("aria-expanded", String(opening));
      item.classList.toggle("expanded", opening);
    });
  });

  /* ── Segment control: auto-save mode changes ── */
  let modeSaveController = null;
  container.querySelectorAll(".segment-control input[type='radio']").forEach((radio) => {
    radio.addEventListener("change", async () => {
      const item = radio.closest(".source-list-item");
      const sourceId = item.dataset.sourceId;
      const source = state.sources.find((s) => s.source_id === sourceId);
      const config = { ...(source?.config_json || {}) };
      const statusEl = item.querySelector(".source-save-status");
      item.querySelectorAll(".segment-option").forEach((o) => o.classList.toggle("active", o.querySelector("input").checked));
      const modeLabel = radio.value === "auto" ? "자동 추천" : radio.value === "enabled" ? "직접 사용" : "사용 안 함";
      const badge = item.querySelector(".source-item-mode-badge");
      const feedPart = badge.textContent.includes(" · ") ? badge.textContent.slice(badge.textContent.indexOf(" · ")) : "";
      badge.textContent = modeLabel + feedPart;
      if (modeSaveController) modeSaveController.abort();
      modeSaveController = new AbortController();
      statusEl.textContent = "저장 중…";
      statusEl.className = "source-save-status saving";
      try {
        await api(`/api/v1/sources/configs/${sourceId}`, { method: "PUT", body: JSON.stringify({ selection_mode: radio.value, config_json: config }) });
        statusEl.textContent = "저장 완료";
        statusEl.className = "source-save-status saved";
        setTimeout(() => { if (statusEl.textContent === "저장 완료") { statusEl.textContent = ""; statusEl.className = "source-save-status"; } }, 2000);
      } catch (error) {
        statusEl.textContent = "저장 실패";
        statusEl.className = "source-save-status failed";
        showToast(error.message);
      }
    });
  });

  /* ── RSS feed save buttons ── */
  container.querySelectorAll("[data-save-source]").forEach((button) => {
    button.addEventListener("click", async () => {
      const item = button.closest(".source-list-item");
      const sourceId = item.dataset.sourceId;
      const source = state.sources.find((s) => s.source_id === sourceId);
      const config = { ...(source?.config_json || {}) };
      const textarea = item.querySelector("[data-feed-urls]");
      if (textarea) config.feed_urls = textarea.value.split("\n").map((l) => l.trim()).filter(Boolean);
      const modeRadio = item.querySelector(".segment-control input:checked");
      const mode = modeRadio?.value || source?.selection_mode || "auto";
      const original = button.textContent;
      setBusy(button, true, "저장 중");
      try {
        await api(`/api/v1/sources/configs/${sourceId}`, { method: "PUT", body: JSON.stringify({ selection_mode: mode, config_json: config }) });
        showToast("피드 설정을 저장했어요");
        const feedCount = config.feed_urls?.length || 0;
        const badge = item.querySelector(".source-item-mode-badge");
        const modeLabel = mode === "auto" ? "자동 추천" : mode === "enabled" ? "직접 사용" : "사용 안 함";
        badge.textContent = modeLabel + (feedCount > 0 ? ` · 피드 ${feedCount}개` : "");
      } catch (error) {
        showToast(error.message);
      } finally {
        setBusy(button, false, original);
      }
    });
  });

  /* ── Region preference: auto-save ── */
  container.querySelectorAll("input[name='source-region']").forEach((input) => {
    input.addEventListener("change", async () => {
      if (state.settingsSaving) return;
      const previous = state.settings?.source_region_preference || "both";
      state.settingsSaving = true;
      setSettingsControlsBusy(true);
      try {
        const data = await api("/api/v1/settings", { method: "PUT", body: JSON.stringify({ source_region_preference: input.value }) });
        state.settings = data.settings;
        showToast("소식 지역 설정을 저장했어요.");
      } catch (error) {
        container.querySelectorAll("input[name='source-region']").forEach((radio) => { radio.checked = radio.value === previous; });
        showToast("지역 설정을 저장하지 못했어요. 다시 시도해 주세요.");
      } finally {
        state.settingsSaving = false;
        setSettingsControlsBusy(false);
      }
    });
  });
}

async function seedDefaultSources() {
  try {
    await api("/api/v1/sources/configs/seed-defaults", { method: "POST", body: JSON.stringify({ overwrite: true }) });
    showToast("기본 소스를 켰어요");
    await loadSources();
  } catch (error) {
    showToast(error.message);
  }
}

async function loadActivity(scrollPosition = captureScrollPosition()) {
  const container = document.getElementById("activity-list");
  showLoading("activity-list", "활동 기록을 불러오고 있어요.");
  try {
    const [pipelineData, feedbackData] = await Promise.all([
      api("/api/v1/pipeline/runs?limit=12"),
      api("/api/v1/feedback/events?limit=12"),
    ]);
    const items = [
      ...(pipelineData.runs || []).map(activityFromPipeline),
      ...(feedbackData.events || []).map(activityFromFeedback),
    ].sort((a, b) => parseServerTimestamp(b.time) - parseServerTimestamp(a.time));
    if (!items.length) {
      container.innerHTML = `<div class="empty-state"><h3>아직 활동 기록이 없어요.</h3><p>오늘의 소식을 받으면 이곳에 기록이 남아요.</p></div>`;
      return;
    }
    container.innerHTML = items.slice(0, 18).map(renderActivityItem).join("");
    container.querySelectorAll("[data-activity-source-url]").forEach((button) => {
      button.addEventListener("click", () => {
        window.open(button.dataset.activitySourceUrl, "_blank", "noopener,noreferrer");
      });
    });
  } catch (error) {
    container.innerHTML = emptyState("잠시 연결이 불안정해요.", "다시 시도해보세요.", "새로고침", "retry-activity");
    bindEmptyAction("retry-activity", loadActivity);
  } finally {
    restoreScrollPosition(scrollPosition);
  }
}

function activityFromPipeline(run) {
  return {
    time: run.completed_at || run.started_at,
    title: `${formatTime(run.completed_at || run.started_at)} 오늘의 소식을 만들었어요`,
    body: `총 ${run.source_item_count || 0}개 후보를 확인하고 소식 ${run.signal_count || 0}개를 골랐어요.`,
  };
}

function activityFromFeedback(event) {
  const messages = { saved: "소식을 저장했어요", ignored: "비슷한 소식을 줄이기로 했어요", tracked: "관심 있는 소식으로 표시했어요", opened: "원문을 열어봤어요" };
  return {
    time: event.created_at,
    title: `${formatTime(event.created_at)} ${messages[event.event_type] || "활동을 기록했어요"}`,
    body: event.signal_title ? `관련 소식: ${event.signal_title}` : "브리핑 사용 흐름을 반영했어요.",
    sourceUrl: event.event_type === "opened" ? event.signal_url || "" : "",
  };
}

function renderActivityItem(item) {
  const sourceButton = item.sourceUrl
    ? `<div class="activity-actions"><button type="button" class="button primary" data-activity-source-url="${escapeHtml(item.sourceUrl)}">원문 보기</button></div>`
    : "";
  return `
    <article class="activity-item">
      <div class="card-title"><h3>${escapeHtml(item.title)}</h3></div>
      <p>${escapeHtml(item.body)}</p>
      ${sourceButton}
    </article>
  `;
}

async function saveSettings(event) {
  event.preventDefault();
  const select = document.getElementById("setting-signal-count");
  const status = document.getElementById("signal-count-save-status");
  const selectedCount = Number(select.value);
  if (!state.briefingDisplayMax || !Number.isInteger(selectedCount) || selectedCount < 1 || selectedCount > state.briefingDisplayMax) {
    renderSignalCountGateNote();
    return;
  }
  if (state.settingsSaving || selectedCount === Number(state.settings?.signal_count)) return;
  state.settingsSaving = true;
  setSettingsControlsBusy(true);
  status.textContent = "저장 중…";
  try {
    const result = await api("/api/v1/settings", {
      method: "PUT",
      body: JSON.stringify({
        signal_count: selectedCount,
      }),
    });
    state.settings = result.settings;
    status.textContent = "저장했어요.";
  } catch (error) {
    status.textContent = "저장하지 못했어요. 다시 선택해 주세요.";
  } finally {
    state.settingsSaving = false;
    setSettingsControlsBusy(false);
    renderSettings();
  }
}

function setSettingsControlsBusy(busy) {
  const select = document.getElementById("setting-signal-count");
  if (select) select.disabled = busy || !state.briefingDisplayMax;
  document.querySelectorAll("input[name='source-region']").forEach((input) => { input.disabled = busy; });
}

function renderSettings() {
  if (!state.settings) return;
  renderAccountShell();
  renderGateSummary();
  const select = document.getElementById("setting-signal-count");
  const savedCount = Math.max(1, Number(state.settings.signal_count || 3));
  const max = state.briefingDisplayMax;
  if (select) {
    select.disabled = !max || Boolean(state.settingsSaving);
    select.innerHTML = max
      ? `${savedCount > max ? `<option value="${savedCount}" disabled>저장된 설정: ${savedCount}개</option>` : ""}${Array.from({ length: max }, (_, i) => `<option value="${i + 1}">${i + 1}개</option>`).join("")}`
      : '<option value="">설정을 확인할 수 없어요</option>';
    if (max) select.value = String(savedCount);
  }
  renderSignalCountGateNote();
}

function initAuthShell() {
  // Hide the dev-only account card in production (supabase mode, LUMOS_DEV_MODE not set).
  if (!authClient.isDevMode()) {
    document.getElementById("account-shell")?.classList.add("hidden");
  }

  const mockAuth = new URLSearchParams(location.search).get("mockAuth");
  if (mockAuth === "free" || mockAuth === "pro") {
    state.authShell = {
      mode: "mock",
      plan: mockAuth === "pro" ? "Pro" : "Free",
      label: mockAuth === "pro" ? "Mock Pro 계정" : "Mock Free 계정",
      isMock: true,
    };
    return;
  }
  if (authClient.isAuthMode() && state.authUser) {
    const email = state.authUser.email || "";
    const name = state.authUser.user_metadata?.full_name || state.authUser.user_metadata?.name || email;
    state.authShell = {
      mode: "supabase",
      plan: "베타",
      label: name || "로그인됨",
      isMock: false,
      email,
    };
    renderUserMenu();
  }
}

function renderAccountShell() {
  const account = state.authShell;
  const chipLabel = document.getElementById("account-chip-label");
  if (chipLabel) chipLabel.textContent = account.label;
  setText("account-status-chip", account.label);

  if (account.isMock) {
    setText("account-summary", `${account.label} 상태로 표시하고 있어요.`);
    setText("account-connection", "개발 확인용 mock 계정 · 실제 로그인 아님");
    setText("account-device", "Mock 기기 등록 상태 · 실제 Cloud Backend와 연결되지 않았어요.");
    setText("account-plan", `Mock 요금제: ${account.plan} · 결제나 구독 상태가 아니에요.`);
    setText("account-cloud-status", "개발/QA용 mock 표시 · 실제 Cloud 연결 아님");
    setText("account-entitlements", "Mock 표시만 사용 중");
    setText("account-entitlement-status", "개발/QA용 mock 표시");
    setText("account-grace-until", "해당 없음");
    setText("account-last-checked", "브라우저 query 표시");
    setText("account-token-storage", "Mock 표시 · 실제 token 저장 없음");
    setText("account-note", "이 표시는 개발/QA용 mock 상태입니다. 실제 계정, 구독, 기기 등록은 아직 연결되지 않았어요.");
    return;
  }

  const cloud = state.cloudAccount;
  if (cloud?.connected) {
    const user = cloud.user || {};
    const device = cloud.device || {};
    const entitlement = cloud.entitlements || {};
    setText("account-summary", "개발용 cloud backend 연결이 확인됐어요. 실제 상용 로그인은 아직 아니에요.");
    setText("account-connection", `${user.email || "개발용 계정"} · 개발용 cloud 연결됨`);
    setText("account-device", `${device.device_name || "이 기기"} · ${device.status || "active"}`);
    setText("account-plan", `개발용 plan: ${cloud.plan || "free"} · 결제 기반 구독 아님`);
    setText("account-cloud-status", cloud.message || "연결됨");
    setText("account-entitlements", formatEntitlementSummary(entitlement));
    setText("account-entitlement-status", formatEntitlementCacheStatus(cloud.entitlement_cache));
    setText("account-grace-until", formatDateTime(cloud.entitlement_cache?.grace_until));
    setText("account-last-checked", formatDateTime(cloud.last_checked_at));
    setText("account-token-storage", formatTokenStorage(cloud.token_storage));
    setText("account-note", "dev token은 현재 실행 중인 local app 메모리에만 보관됩니다. 앱을 다시 시작하면 연결 상태가 초기화돼요.");
    return;
  }

  setText("account-summary", "지금은 이 기기에서만 LUMOS를 사용하고 있어요.");
  setText("account-connection", "로그인 안 됨 · 로컬 모드");
  setText("account-device", "이 기기에서 실행 중 · 기기 등록은 아직 연결되지 않았어요.");
  setText("account-plan", "현재: 로컬 MVP · 향후 Free / Pro / Team 요금제와 연결 예정");
  setText("account-cloud-status", cloud?.message || "연결 안 됨 · 개발용 cloud 테스트는 선택 사항이에요.");
  setText("account-entitlements", cloud?.entitlements ? formatEntitlementSummary(cloud.entitlements) : "아직 cloud 권한을 확인하지 않았어요.");
  setText("account-entitlement-status", formatEntitlementCacheStatus(cloud?.entitlement_cache));
  setText("account-grace-until", formatDateTime(cloud?.entitlement_cache?.grace_until));
  setText("account-last-checked", formatDateTime(cloud?.last_checked_at));
  setText("account-token-storage", formatTokenStorage(cloud?.token_storage));
  setText("account-note", cloud?.error_code === "cloud_unavailable"
    ? "Cloud backend가 실행 중인지 확인해 주세요: python run.py cloud"
    : "나중에 로그인하면 구독 상태, 기기 등록, 설정 동기화 기능을 연결할 수 있어요.");
}

async function handleAccountAction(action) {
  if (action === "architecture") {
    showToast("계정 구조는 docs/product 문서에 정리되어 있어요.");
    return;
  }
  if (action === "roadmap") {
    showToast("제품화 로드맵은 README와 docs/product에서 확인할 수 있어요.");
    return;
  }
  if (action === "connect") {
    await runCloudAccountAction(action, "/api/v1/product/cloud/dev-connect", "개발용 cloud 연결을 확인하고 있어요.", "개발용 cloud 연결이 확인됐어요.");
    return;
  }
  if (action === "disconnect") {
    await runCloudAccountAction(action, "/api/v1/product/cloud/dev-disconnect", "개발용 연결을 해제하고 있어요.", "로컬 모드로 돌아왔어요.");
    return;
  }
  if (action === "usage-test") {
    await runCloudAccountAction(action, "/api/v1/product/cloud/usage-test", "사용량 이벤트 테스트를 보내고 있어요.", "사용량 이벤트 테스트를 보냈어요.");
    return;
  }
  showToast("현재는 로컬 모드로 사용할 수 있어요.");
}

async function runCloudAccountAction(action, path, busyText, successText) {
  const button = document.querySelector(`[data-account-action="${action}"]`);
  const original = button?.textContent || "";
  setBusy(button, true, busyText);
  try {
    const payload = action === "connect"
      ? { email: "demo@lumos.local", name: "Demo User", plan: "pro" }
      : {};
    state.cloudAccount = await api(path, { method: "POST", body: JSON.stringify(payload) });
    await loadFeatureGates();
    renderAccountShell();
    showToast(state.cloudAccount.message || successText);
  } catch (error) {
    state.cloudAccount = {
      mode: "cloud_unavailable",
      connected: false,
      message: "Cloud backend가 실행 중인지 확인해 주세요: python run.py cloud",
      error_code: "cloud_unavailable",
    };
    renderAccountShell();
    showToast("Cloud backend가 실행 중인지 확인해 주세요: python run.py cloud");
  } finally {
    setBusy(button, false, original);
  }
}

function formatEntitlementSummary(entitlements = {}) {
  const signalLimit = entitlements.max_signals_per_day ?? "-";
  const sourceLimit = entitlements.max_sources ?? "-";
  const autoBriefing = entitlements.auto_briefing_enabled ? "자동 브리핑 가능" : "자동 브리핑 제한";
  return `하루 소식 ${signalLimit}개 · 소스 ${sourceLimit}개 · ${autoBriefing}`;
}

function formatDateTime(value) {
  if (!value) return "아직 없음";
  try {
    return parseServerTimestamp(value).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
  } catch (error) {
    return value;
  }
}

function formatTokenStorage(value) {
  if (value === "keyring") return "OS 보안 저장소 prototype";
  if (value === "keyring_unavailable_memory") return "OS 보안 저장소 사용 불가 · 메모리 전용";
  return "메모리 전용";
}

function formatEntitlementCacheStatus(cache) {
  if (!cache) return "로컬 모드로 사용 중이에요.";
  if (cache.status === "valid") return "방금 Cloud에서 확인됨";
  if (cache.status === "grace") return "Cloud 연결 실패 · Offline grace 적용 중";
  if (cache.status === "expired") return "만료됨 · 로컬 모드로 사용 중";
  return cache.message || "로컬 모드로 사용 중이에요.";
}

function renderGateSummary() {
  const message = document.getElementById("gate-summary-message");
  const list = document.getElementById("gate-summary-list");
  if (!message || !list) return;
  const gates = state.featureGates?.gates || [];
  message.textContent = state.featureGates?.message || "현재는 안내만 표시하고 모든 핵심 기능을 계속 사용할 수 있어요.";
  if (!gates.length) {
    list.innerHTML = `<div class="gate-summary-item"><strong>로컬 모드</strong>현재는 안내만 표시하고 기능을 막지 않아요.</div>`;
    return;
  }
  list.innerHTML = gates.map((gate) => `
    <div class="gate-summary-item">
      <strong>${escapeHtml(gateTitle(gate.feature_key))}</strong>
      ${escapeHtml(gate.message_ko || "")}
    </div>
  `).join("");
  renderSignalCountGateNote();
}

function renderSignalCountGateNote() {
  const note = document.getElementById("signal-count-gate-note");
  const select = document.getElementById("setting-signal-count");
  if (!note || !select) return;
  const limit = state.briefingDisplayMax;
  const value = Number(select.value);
  note.textContent = !limit ? "설정 가능한 소식 수를 확인하지 못했어요. 새로고침해 주세요."
    : value > limit ? `현재 설정은 ${value}개지만 브리핑에는 최대 ${limit}개가 표시돼요. 저장하려면 개수를 다시 선택해 주세요.` : "";
}

function gateTitle(key) {
  return {
    today_signal_count: "오늘 소식 개수",
    daily_generate_limit: "하루 생성 횟수",
    source_count: "소스 수",
    auto_briefing: "자동 브리핑",
    advanced_sources: "고급 source",
    context_connectors: "개인 맥락 connector",
    history_retention: "기록 보관",
    team_workspace: "팀 workspace",
    cloud_sync: "Cloud sync",
    export_share: "Export / Share",
  }[key] || key;
}

function switchTab(tab) {
  document.querySelector(`.nav-item[data-tab="${tab}"]`)?.click();
}

function emptyState(title, body, buttonText, action) {
  return `<div class="empty-state"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(body)}</p><button class="button primary" data-action="${action}">${escapeHtml(buttonText)}</button></div>`;
}

function bindEmptyAction(action, handler) {
  document.querySelectorAll(`[data-action="${action}"]`).forEach((button) => button.addEventListener("click", handler));
}

function scrollStorageKey() {
  if (typeof location === "undefined") return "lumos:scroll-position";
  return `lumos:scroll-position:${location.hash || "#today"}`;
}

function captureScrollPosition() {
  if (typeof window === "undefined") return null;
  return { x: window.scrollX || 0, y: window.scrollY || 0 };
}

function storeScrollPosition() {
  const position = captureScrollPosition();
  if (!position || typeof sessionStorage === "undefined") return;
  sessionStorage.setItem(scrollStorageKey(), JSON.stringify(position));
}

function readStoredScrollPosition() {
  if (typeof sessionStorage === "undefined") return null;
  try {
    const position = JSON.parse(sessionStorage.getItem(scrollStorageKey()) || "null");
    return Number.isFinite(position?.x) && Number.isFinite(position?.y) ? position : null;
  } catch (_) {
    return null;
  }
}

function restoreScrollPosition(position) {
  if (!position || typeof window === "undefined" || typeof window.scrollTo !== "function") return;
  const restore = () => window.scrollTo(position.x, position.y);
  if (typeof window.requestAnimationFrame === "function") {
    window.requestAnimationFrame(() => window.requestAnimationFrame(restore));
  } else {
    setTimeout(restore, 0);
  }
}

function showLoading(containerId, message) {
  const container = document.getElementById(containerId);
  if (container) container.innerHTML = `<div class="loading-card"><span class="spinner"></span>${escapeHtml(message)}</div>`;
}

function setBusy(button, busy, text) {
  if (!button) return;
  button.disabled = busy;
  button.textContent = text;
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function statusPill(status) {
  const labels = { saved: "저장됨", ignored: "관심 없음", tracked: "관심 있음", active: "사용 중", new: "새 소식" };
  return `<span class="status-chip subtle">${labels[status] || "사용 중"}</span>`;
}

function interestStatusChip(status) {
  // This label describes only the reader's interest setting. Availability of
  // a matching live source is communicated separately in the card body.
  const labels = { active: "관심사 설정됨", muted: "브리핑에서 숨김", deleted: "삭제됨" };
  const className = status === "active" ? "ready" : status === "muted" ? "warning" : "off";
  return `<span class="status-chip ${className}">${labels[status] || "사용 중"}</span>`;
}

function sourceStatusChip(status) {
  const className = status === "준비됨" || status === "토큰 선택" ? "ready" : status === "사용 안 함" ? "off" : "warning";
  return `<span class="status-chip ${className}">${status}</span>`;
}

function sourceStatus(source) {
  if (source.implemented_status !== "implemented") return "준비 중";
  if (!source.current_enabled) return "사용 안 함";
  const config = source.config_json || {};
  if (["rss", "official_ai_blogs", "company_newsroom"].includes(source.source_id) && !(config.feed_urls || []).length) return "URL 필요";
  if (source.source_id === "youtube" && !source.api_key_ready) return "API 키 필요";
  if (source.source_id === "github") return "토큰 선택";
  return "준비됨";
}

function recommendationReason(signal) {
  const topic = humanCategory(signal.category) || "관심 분야";
  return `${topic} 분야에서 최근 어떤 변화가 나타나는지 확인할 수 있어, 실제 적용이나 시장 변화로 이어질지 판단하는 데 도움이 될 만해 추천했어요.`;
}

function keywordOriginText(signal) {
  const keywords = signal.matched_keywords || signal.metadata_json?.matched_keywords || [];
  const visibleKeywords = keywords.map((keyword) => String(keyword).trim()).filter(Boolean).slice(0, 3);
  return visibleKeywords.length
    ? `'${visibleKeywords.join(", ")}' 키워드에서 찾은 원문이에요.`
    : "설정한 관심사에서 찾은 원문이에요.";
}

function weightLabel(weight) {
  const value = Number(weight || 0);
  if (value >= 6) return "높음";
  if (value >= 2.5) return "보통";
  return "낮음";
}

function sourceNameForInterest(source) {
  const labels = { manual: "직접 입력", browser_history: "브라우저 기록", local_files: "로컬 파일", feedback: "피드백", onboarding: "온보딩", personal_context: "개인 맥락" };
  return labels[source] || "추천 기준";
}

function evidenceSentence(interest) {
  const keyword = interest.keyword;
  if (interest.source === "browser_history") return `최근 브라우저 기록에서 '${keyword}' 관련 페이지를 자주 봤어요.`;
  if (interest.source === "local_files") return `로컬 파일에서 '${keyword}'이라는 표현이 여러 번 등장했어요.`;
  if (interest.source === "feedback") return `이전 반응을 바탕으로 '${keyword}' 흐름을 더 중요하게 보고 있어요.`;
  if (interest.source === "onboarding") return `처음 설정할 때 '${keyword}'에 관심이 있다고 알려줬어요.`;
  if (interest.source === "manual") return "직접 추가한 관심사로 보고 있어요.";
  return `최근 맥락에서 '${keyword}' 흐름이 반복해서 보였어요.`;
}

function sourceLabel(source) {
  return sourceCopy[source]?.[0] || source;
}

function connectorLabel(type) {
  const labels = { browser_history: "브라우저 기록", local_files: "로컬 파일", notion: "Notion", google_drive: "Google Drive", chatgpt_export: "ChatGPT 내보내기", claude_export: "Claude 내보내기" };
  return labels[type] || "개인 맥락";
}

function humanCategory(category) {
  const labels = { AI_LLM_AGENT: "AI와 에이전트", RESEARCH: "연구", STARTUP_PRODUCT: "스타트업과 제품", DEVELOPER_TECH: "개발자 도구", COMPANY_TRACKING: "기업 변화", CONTENT_SNS: "콘텐츠와 커뮤니티", CAREER: "커리어", DOMESTIC_INDUSTRY: "국내 산업" };
  return labels[category] || "";
}

function formatTime(value) {
  if (!value) return "방금";
  const date = parseServerTimestamp(value);
  if (Number.isNaN(date.getTime())) return "방금";
  return date.toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit" });
}

function formatSavedDate(value) {
  if (!value) return "날짜 미확인";
  const date = parseServerTimestamp(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  return date.toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric" });
}

function parseServerTimestamp(value) {
  const normalized = String(value || "").trim().replace(" ", "T");
  // SQLite CURRENT_TIMESTAMP is UTC but omits its timezone suffix. Preserve
  // explicitly supplied offsets while marking bare database timestamps as UTC.
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  return new Date(hasTimezone ? normalized : `${normalized}Z`);
}

function setValue(id, value) {
  const element = document.getElementById(id);
  if (element) element.value = value;
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function setChecked(id, value) {
  const element = document.getElementById(id);
  if (element) element.checked = Boolean(value);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// ─── Assistant chat state ────────────────────────────────────────────────────
const assistantState = {
  conversationId: null,
  selectedSignalId: null,
  loading: false,
};

function bindSourceChat() {
  const launcher = document.getElementById("chat-launcher");
  const panel = document.getElementById("chat-panel");
  const closeBtn = document.getElementById("chat-close");
  const newBtn = document.getElementById("chat-new");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");

  const setOpen = (open) => {
    panel.classList.toggle("open", open);
    document.querySelector(".app-shell")?.classList.toggle("chat-open", open);
    launcher.classList.toggle("hidden", open);
    panel.setAttribute("aria-hidden", String(!open));
    launcher.setAttribute("aria-expanded", String(open));
    if (open) {
      updateChatPeriodLabel();
      input.focus();
    }
  };

  launcher.addEventListener("click", () => setOpen(!panel.classList.contains("open")));
  closeBtn.addEventListener("click", () => setOpen(false));

  newBtn?.addEventListener("click", () => {
    assistantState.conversationId = null;
    assistantState.selectedSignalId = null;
    clearChatMessages();
  });

  // Suggestion chips
  document.getElementById("chat-messages")?.addEventListener("click", (e) => {
    const btn = e.target.closest(".chat-suggestion");
    if (btn) {
      input.value = btn.textContent.trim();
      input.focus();
    }
  });

  // Enter to submit (Shift+Enter = newline)
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (assistantState.loading) return;
    const message = input.value.trim();
    if (!message) return;

    appendChatMessage("user", message);
    input.value = "";
    setAssistantLoading(true);

    try {
      const body = {
        message,
        period: state.briefingPeriod || "today",
        conversation_id: assistantState.conversationId,
        selected_signal_id: assistantState.selectedSignalId,
      };
      assistantState.selectedSignalId = null; // use only once

      const data = await api("/api/v1/assistant/chat", {
        method: "POST",
        body: JSON.stringify(body),
      });

      assistantState.conversationId = data.conversation_id;
      appendChatMessage("assistant", data.answer, data.sources || []);
    } catch {
      appendChatMessage("assistant", "답변을 준비하지 못했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setAssistantLoading(false);
    }
  });
}

function setAssistantLoading(loading) {
  assistantState.loading = loading;
  const input = document.getElementById("chat-input");
  const submit = document.getElementById("chat-submit");
  if (input) input.disabled = loading;
  if (submit) submit.disabled = loading;
  if (loading) {
    const container = document.getElementById("chat-messages");
    container?.insertAdjacentHTML(
      "beforeend",
      '<div class="chat-message assistant chat-loading" id="chat-loading-indicator"><span></span><span></span><span></span></div>'
    );
    container.scrollTop = container.scrollHeight;
  } else {
    document.getElementById("chat-loading-indicator")?.remove();
    document.getElementById("chat-input")?.focus();
  }
}

function updateChatPeriodLabel() {
  const labels = { today: "오늘", week: "이번 주", month: "이번 달", all: "전체" };
  const label = labels[state.briefingPeriod] || "이번 주";
  const el = document.getElementById("chat-period-label");
  if (el) el.textContent = `${label} 브리핑 기반 질문`;
}

function clearChatMessages() {
  const container = document.getElementById("chat-messages");
  if (!container) return;
  container.innerHTML = `
    <div class="chat-welcome">
      <p>브리핑 소식을 기반으로 질문해보세요.</p>
      <div class="chat-suggestions">
        <button class="chat-suggestion" type="button">이번 주 가장 큰 변화는?</button>
        <button class="chat-suggestion" type="button">저장한 소식 요약해 줘</button>
        <button class="chat-suggestion" type="button">AI 관련 소식 정리해줘</button>
      </div>
    </div>`;
}

function openAssistantWithSignal(signalId, signalTitle) {
  // Cancel any in-flight request so the form doesn't stay permanently disabled.
  if (assistantState.loading) {
    setAssistantLoading(false);
  }
  assistantState.conversationId = null;
  assistantState.selectedSignalId = signalId;
  clearChatMessages();

  const panel = document.getElementById("chat-panel");
  const launcher = document.getElementById("chat-launcher");
  panel.classList.add("open");
  document.querySelector(".app-shell")?.classList.add("chat-open");
  launcher.classList.add("hidden");
  panel.setAttribute("aria-hidden", "false");
  launcher.setAttribute("aria-expanded", "true");

  updateChatPeriodLabel();

  const input = document.getElementById("chat-input");
  if (input) {
    input.value = `"${signalTitle}" 소식에 대해 더 자세히 알려줘`;
    input.focus();
  }
}

function appendChatMessage(role, text, sources = []) {
  const container = document.getElementById("chat-messages");
  // Remove welcome placeholder on first real message
  container.querySelector(".chat-welcome")?.remove();

  const citationHtml = sources.length
    ? `<div class="chat-citations">${sources
        .filter((s) => s.title)
        .map(
          (s) =>
            `<a class="chat-citation" href="${escapeHtml(s.url || "")}" target="_blank" rel="noopener noreferrer" ${s.url ? "" : 'tabindex="-1" aria-disabled="true"'}>
              <span class="citation-source">${escapeHtml(s.source_name || "출처")}</span>
              <span class="citation-title">${escapeHtml(s.title)}</span>
            </a>`
        )
        .join("")}</div>`
    : "";

  container.insertAdjacentHTML(
    "beforeend",
    `<div class="chat-message ${escapeHtml(role)}">${escapeHtml(text)}${citationHtml}</div>`
  );
  container.scrollTop = container.scrollHeight;
}

// ─── Beta feedback ────────────────────────────────────────────────────────

function bindBetaFeedback() {
  document.getElementById("open-beta-feedback")?.addEventListener("click", openBetaFeedback);
  document.getElementById("close-beta-feedback")?.addEventListener("click", closeBetaFeedback);
  document.getElementById("close-beta-feedback-success")?.addEventListener("click", closeBetaFeedback);
  document.getElementById("beta-feedback-form")?.addEventListener("submit", submitBetaFeedback);
  document.getElementById("beta-feedback-modal")?.addEventListener("click", (e) => {
    if (e.target === document.getElementById("beta-feedback-modal")) closeBetaFeedback();
  });
}

function openBetaFeedback() {
  const modal = document.getElementById("beta-feedback-modal");
  const form = document.getElementById("beta-feedback-form");
  const success = document.getElementById("beta-feedback-success");
  const error = document.getElementById("beta-feedback-error");
  if (!modal) return;
  form?.classList.remove("hidden");
  success?.classList.add("hidden");
  if (error) error.textContent = "";
  document.getElementById("beta-feedback-message").value = "";
  modal.classList.remove("hidden");
  document.getElementById("beta-feedback-message")?.focus();
}

function closeBetaFeedback() {
  document.getElementById("beta-feedback-modal")?.classList.add("hidden");
}

async function submitBetaFeedback(event) {
  event.preventDefault();
  const submit = document.getElementById("beta-feedback-submit");
  const errorEl = document.getElementById("beta-feedback-error");
  const message = document.getElementById("beta-feedback-message")?.value.trim();
  const feedbackType = document.querySelector("input[name='beta-feedback-type']:checked")?.value || "기타";

  if (!message) {
    if (errorEl) errorEl.textContent = "내용을 입력해 주세요.";
    return;
  }
  if (errorEl) errorEl.textContent = "";

  const original = submit.textContent;
  setBusy(submit, true, "보내는 중");
  try {
    await api("/api/v1/beta/feedback", {
      method: "POST",
      body: JSON.stringify({ feedback_type: feedbackType, message }),
    });
    document.getElementById("beta-feedback-form")?.classList.add("hidden");
    document.getElementById("beta-feedback-success")?.classList.remove("hidden");
  } catch {
    if (errorEl) errorEl.textContent = "전송에 실패했어요. 잠시 후 다시 시도해 주세요.";
  } finally {
    setBusy(submit, false, original);
  }
}

// ─── Auth functions ───────────────────────────────────────────────────────

/**
 * Initialize auth state at app startup.
 * Returns true  → proceed with app initialisation.
 * Returns false → navigating to /login (don't proceed).
 */
async function initAuth() {
  // Some existing Supabase projects still use /app as their configured OAuth
  // callback URL. Accept that callback long enough for the SDK to persist the
  // session, then keep the post-login experience on the public home page.
  const authHash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const arrivedFromAuthCallback = authHash.has("access_token") || authHash.has("code") || new URLSearchParams(window.location.search).has("code");
  try {
    await authClient.init();
  } catch (e) {
    // Config fetch failed — continue in local mode (degraded).
    console.warn("Auth init failed, running in local mode:", e);
    return true;
  }

  if (!authClient.isAuthMode()) return true;

  // Detect OAuth errors returned as query params (e.g. user cancelled Google OAuth).
  // Supabase redirects back to /app with ?error=access_denied in this case.
  const urlParams = new URLSearchParams(window.location.search);
  const oauthError = urlParams.get("error");
  if (oauthError) {
    const reason = oauthError === "access_denied" ? "oauth_cancel" : oauthError;
    authClient.redirectToLogin(reason);
    return false;
  }

  const session = await authClient.getSession();
  if (!session) {
    authClient.redirectToLogin();
    return false;
  }

  state.authUser = session.user;

  if (arrivedFromAuthCallback) {
    window.location.replace("/");
    return false;
  }

  // Redirect to /login on sign-out (e.g. token revoked in another tab).
  authClient.onAuthStateChange((event) => {
    if (event === "SIGNED_OUT") authClient.redirectToLogin();
  });

  return true;
}

/** Render the sidebar user menu when in Supabase auth mode. */
function renderUserMenu() {
  const menu = document.getElementById("user-menu");
  if (!menu) return;
  if (!authClient.isAuthMode() || !state.authUser) {
    menu.classList.add("hidden");
    return;
  }
  const user = state.authUser;
  const display =
    user.user_metadata?.full_name ||
    user.user_metadata?.name ||
    user.email ||
    "사용자";
  setText("user-display", display);
  menu.classList.remove("hidden");

  // Bind logout button once.
  const btn = document.getElementById("logout-button");
  if (btn && !btn.dataset.bound) {
    btn.dataset.bound = "1";
    btn.addEventListener("click", handleLogout);
  }
}

/** Sign out: clear Supabase session, reset client state, redirect to /login. */
async function handleLogout() {
  const btn = document.getElementById("logout-button");
  if (btn) { btn.disabled = true; btn.textContent = "로그아웃 중…"; }
  await authClient.signOut();
  resetClientState();
  window.location.href = "/login";
}

/**
 * Reset all mutable client state so that a subsequent user login sees
 * a clean slate (prevents data leakage between accounts).
 */
function resetClientState() {
  Object.values(state.interestDrafts).forEach((draft) => clearTimeout(draft.timer));
  interestAutosaveEpoch += 1;
  state.profile = null;
  state.settings = null;
  state.connectors = [];
  state.sources = [];
  state.interests = [];
  state.interestDrafts = {};
  state.interestRecommendations = [];
  state.feedbackLearning = null;
  state.feedbackSignals = [];
  state.feedbackMode = null;
  state.recommendationCategory = "tracked";
  state.signals = [];
  state.savedSignals = [];
  state.hasMoreSignals = false;
  state.signalRunId = null;
  state.loadingMoreSignals = false;
  state.firstRun = false;
  state.authUser = null;
  state.cloudAccount = null;
  state.featureGates = null;
  state.authShell = { mode: "local", plan: "로컬 MVP", label: "로컬 모드", isMock: false };
  // Reset assistant chat state so a subsequent login sees a clean panel.
  assistantState.conversationId = null;
  assistantState.selectedSignalId = null;
  assistantState.loading = false;
}
