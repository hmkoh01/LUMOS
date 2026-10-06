const state = {
  profile: null,
  settings: null,
  connectors: [],
  sources: [],
  interests: [],
  interestRecommendations: [],
  feedbackSignals: [],
  feedbackMode: null,
  signals: [],
  savedSignals: [],
  hasMoreSignals: false,
  signalRunId: null,
  loadingMoreSignals: false,
  activeTab: "signals",
  briefingPeriod: "today",
  onboardingStep: 1,
  onboardingRole: "예비 창업자 / PM",
  onboardingKeywords: [],
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
};

const modeLabels = {
  mock: "안정 모드",
  hybrid: "혼합 모드",
  live: "실제 소스 모드",
};

const sourceCopy = {
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

const sourceOrder = ["hackernews", "github", "rss", "official_ai_blogs", "producthunt", "reddit", "youtube", "naver_news", "arxiv", "company_newsroom"];
const hashToTab = {
  "#today": "signals",
  "#signals": "signals",
  "#saved": "saved",
  "#tracked": "tracked",
  "#ignored": "ignored",
  "#interests": "interests",
  "#sources": "sources",
  "#activity": "activity",
  "#settings": "settings",
};
const tabToHash = {
  signals: "#today",
  saved: "#saved",
  tracked: "#tracked",
  ignored: "#ignored",
  interests: "#interests",
  sources: "#sources",
  activity: "#activity",
  settings: "#settings",
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

  initAuthShell();
  bindNavigation();
  bindTopActions();
  bindBriefingPeriods();
  bindSourceChat();
  bindOnboarding();
  applyHashTab({ load: false });
  window.addEventListener("hashchange", applyHashTab);
  window.addEventListener("pagehide", storeScrollPosition);

  await loadInitialData();

  // Auto-open onboarding for first-time auth users.
  if (authClient.isAuthMode() && state.firstRun) openOnboarding();

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
  if (location.hash && !knownHash) {
    history.replaceState(null, "", tabToHash.signals);
  }
  setActiveTab(tab, { updateHash: false, load: options.load !== false });
}

function setActiveTab(tab, options = {}) {
  const nextTab = tabToHash[tab] ? tab : "signals";
  const changed = state.activeTab !== nextTab;
  const nextHash = tabToHash[nextTab] || tabToHash.signals;
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

function bindTopActions() {
  document.getElementById("generate-signals").addEventListener("click", () => generateSignals());
  document.getElementById("view-saved-signals").addEventListener("click", () => setActiveTab("saved", { updateHash: true, load: true }));
  document.getElementById("refresh-saved-signals").addEventListener("click", loadSavedSignals);
  document.getElementById("show-tracked-feedback").addEventListener("click", () => setActiveTab("tracked", { updateHash: true, load: true }));
  document.getElementById("show-ignored-feedback").addEventListener("click", () => setActiveTab("ignored", { updateHash: true, load: true }));
  document.querySelectorAll("[data-back-to-saved]").forEach((button) => button.addEventListener("click", closeFeedbackSignals));
  document.getElementById("refresh-activity").addEventListener("click", loadActivity);
  document.getElementById("settings-form").addEventListener("submit", saveSettings);
  document.getElementById("add-interest").addEventListener("click", openInterestForm);
  document.getElementById("cancel-add-interest").addEventListener("click", closeInterestForm);
  document.getElementById("add-interest-form").addEventListener("submit", addManualInterest);
  document.querySelectorAll("[data-account-action]").forEach((button) => {
    button.addEventListener("click", () => handleAccountAction(button.dataset.accountAction));
  });
  document.getElementById("setting-signal-count")?.addEventListener("change", renderSignalCountGateNote);
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
      renderPeriodDescription();
      loadSignals();
    });
  });
  renderPeriodDescription();
}

function renderPeriodDescription() {
  const copy = {
    today: "오늘 포착한 변화입니다.",
    week: "최근 7일 동안 포착한 중요한 변화입니다.",
    month: "최근 30일 동안 쌓인 중요한 변화입니다.",
  };
  setText("period-description", copy[state.briefingPeriod] || copy.today);
}

function bindOnboarding() {
  document.getElementById("close-onboarding").addEventListener("click", closeOnboarding);
  document.getElementById("onboarding-prev").addEventListener("click", () => setOnboardingStep(state.onboardingStep - 1));
  document.getElementById("onboarding-next").addEventListener("click", () => setOnboardingStep(state.onboardingStep + 1));
  document.getElementById("onboarding-form").addEventListener("submit", completeOnboarding);
  document.querySelectorAll("[data-role]").forEach((button) => {
    button.addEventListener("click", () => {
      state.onboardingRole = button.dataset.role;
      document.querySelectorAll("[data-role]").forEach((item) => item.classList.toggle("selected", item === button));
    });
  });
  document.querySelectorAll("[data-suggestion]").forEach((button) => {
    button.addEventListener("click", () => addKeyword(button.dataset.suggestion));
  });
  const input = document.getElementById("keyword-input");
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      addKeyword(input.value);
      input.value = "";
    }
  });
}

async function loadInitialData() {
  showLoading("signals-list", "오늘의 소식을 확인하고 있어요.");
  await Promise.allSettled([loadProfile(), loadSettings(), loadConnectors(), loadSources(), loadInterests(false), loadSignals(false)]);
  detectFirstRun();
  renderFirstRunPanel();
  renderSettings();
}

async function loadTab(tab) {
  if (tab === "signals") await loadSignals();
  if (tab === "saved") await loadSavedSignals();
  if (tab === "tracked" || tab === "ignored") await openFeedbackSignals(tab);
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
  if (!response.ok) throw new Error("잠시 연결이 불안정해요. 다시 시도해보세요.");
  const data = await response.json();
  if (data.success === false) throw new Error(data.error || "잠시 연결이 불안정해요. 다시 시도해보세요.");
  return data;
}
// Backward-compat alias used throughout this file.
const api = apiFetch;

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

async function loadSignals(render = true, scrollPosition = render ? captureScrollPosition() : null) {
  const container = document.getElementById("signals-list");
  if (render) showLoading("signals-list", "브리핑을 불러오고 있어요.");
  try {
    const period = state.briefingPeriod || "today";
    const data = await api(`/api/v1/signals?period=${encodeURIComponent(period)}`);
    state.signals = (data.signals || []).filter((signal) => signal.status !== "archived");
    state.hasMoreSignals = Boolean(data.has_more);
    state.signalRunId = data.pipeline_run_id;
    if (render) renderSignals();
  } catch (error) {
    if (render) {
      container.innerHTML = emptyState("잠시 연결이 불안정해요.", "다시 시도해보세요.", "새로고침", "retry-signals");
      bindEmptyAction("retry-signals", loadSignals);
    }
  } finally {
    restoreScrollPosition(scrollPosition);
  }
}

function renderSignals() {
  const container = document.getElementById("signals-list");
  if (!state.signals.length) {
    const labels = { today: "오늘", week: "이번 주", month: "이번 달" };
    const periodLabel = labels[state.briefingPeriod] || labels.today;
    container.innerHTML = emptyState(
      `${periodLabel} 브리핑은 아직 없어요.`,
      state.briefingPeriod === "today"
        ? "지금 새로 받아보면 관심사에 맞는 변화를 한국어로 정리해드릴게요."
        : "이 기간에 해당하는 소식이 쌓이면 여기에서 확인할 수 있어요.",
      state.briefingPeriod === "today" ? "소식 새로 받기" : "오늘 브리핑 보기",
      state.briefingPeriod === "today" ? "generate" : "open-today"
    );
    bindEmptyAction("generate", () => generateSignals());
    bindEmptyAction("open-today", () => document.querySelector('[data-period="today"]')?.click());
    return;
  }
  renderPeriodDescription();
  container.innerHTML = state.signals.map(renderSignalCard).join("") + `
    <div class="more-signals" aria-live="polite">
      ${state.hasMoreSignals
        ? `<button class="button secondary" id="more-signals" ${state.loadingMoreSignals ? "disabled" : ""}>${state.loadingMoreSignals ? "추가 소식을 불러오는 중…" : "추가 신호 보기"}</button>`
        : `<p>이번 브리핑에서 더 보여드릴 자료가 없어요. 새로운 자료는 ‘소식 새로 받기’로 찾아보세요.</p>`}
    </div>`;
  bindSignalActions(container);
  document.getElementById("more-signals")?.addEventListener("click", loadMoreSignals);
}

async function loadSavedSignals(render = true, scrollPosition = render ? captureScrollPosition() : null) {
  const container = document.getElementById("saved-signals-list");
  if (render) showLoading("saved-signals-list", "저장한 소식을 불러오고 있어요.");
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
    container.innerHTML = emptyState("저장한 소식이 없어요.", "오늘의 소식에서 저장을 누르면 이곳에서 원문을 다시 볼 수 있어요.", "오늘의 소식 보기", "open-signals");
    bindEmptyAction("open-signals", () => setActiveTab("signals", { updateHash: true, load: true }));
    return;
  }
  container.innerHTML = state.savedSignals.map((signal, index) => renderSavedSignalCard(signal, index + 1)).join("");
  container.querySelectorAll("[data-delete-saved]").forEach((button) => {
    button.addEventListener("click", () => deleteSavedSignal(button.closest(".signal-card").dataset.signalId, button));
  });
  container.querySelectorAll("[data-open-url]").forEach((button) => {
    button.addEventListener("click", () => window.open(button.dataset.openUrl, "_blank", "noopener,noreferrer"));
  });
}

function renderSavedSignalCard(signal, rank) {
  const sourceItems = signal.source_items_json || [];
  const title = signal.display_title_ko || signal.title || "저장한 소식";
  const summary = signal.headline_summary_ko || signal.display_summary_ko || signal.summary || "";
  const url = signal.source_url || sourceItems.find((item) => item.url)?.url || "";
  const keywordOrigin = keywordOriginText(signal);
  return `<article class="signal-card saved-signal-card" data-signal-id="${signal.id}">
    <div class="signal-head"><div class="rank">${rank}</div><div><h3 class="signal-title">${escapeHtml(title)}</h3><p class="signal-summary">${escapeHtml(summary)}</p></div></div>
    <p class="signal-derived-from">${escapeHtml(keywordOrigin)}</p>
    <div class="signal-meta"><span class="pill">출처 ${escapeHtml(signal.source_display || sourceLabel(signal.source_name || "미확인"))}</span><span class="pill">저장한 날짜 ${escapeHtml(formatSavedDate(signal.saved_at || signal.created_at))}</span></div>
    <div class="actions"><button class="button primary" data-open-url="${escapeHtml(url)}" ${url ? "" : "disabled"}>원문 보기</button><button class="button danger" data-delete-saved>저장 목록에서 삭제</button></div>
  </article>`;
}

async function deleteSavedSignal(signalId, button) {
  setBusy(button, true, "삭제 중");
  try {
    await api(`/api/v1/signals/${signalId}/saved`, { method: "DELETE" });
    state.savedSignals = state.savedSignals.filter((signal) => String(signal.id) !== String(signalId));
    renderSavedSignals();
    showToast("저장한 소식에서 삭제했어요.");
  } catch (error) {
    showToast(error.message);
    setBusy(button, false, "저장 목록에서 삭제");
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
  const panel = document.getElementById("first-run-panel");
  if (!state.firstRun) {
    panel.innerHTML = "";
    return;
  }
  panel.innerHTML = `
    <div class="first-run-card">
      <div>
        <p class="eyebrow">첫 브리핑 준비</p>
        <h3>아직 LUMOS가 당신의 관심사를 몰라요.</h3>
        <p>30초만 설정하면 오늘 볼 소식을 한국어로 정리해드릴게요.</p>
      </div>
      <button class="button primary" data-open-onboarding>시작하기</button>
    </div>
  `;
  panel.querySelector("[data-open-onboarding]").addEventListener("click", openOnboarding);
}

async function generateSignals(triggerButton) {
  const button = triggerButton || document.getElementById("generate-signals");
  const original = button.textContent;
  setBusy(button, true, "소식을 고르는 중");
  try {
    const mode = state.settings?.generate_mode || "hybrid";
    const data = await api("/api/v1/signals/generate", {
      method: "POST",
      body: JSON.stringify({ mode, replace_today: true }),
    });
    if (!data.generated_signal_count) {
      showToast((data.failed_sources || []).length || Object.keys(data.errors_by_source || {}).length
        ? "소스 연결에 실패해 새 소식을 만들지 못했어요. 활동 탭에서 오류를 확인해주세요."
        : "이번 수집에서는 관심사에 맞는 새 소식을 찾지 못했어요. 관심사와 소스 설정을 확인해주세요.");
    } else if ((data.failed_sources || []).length || Object.keys(data.errors_by_source || {}).length) {
      showToast("일부 소스에서 데이터를 가져오지 못했지만, 가능한 소스로 소식을 만들었어요.");
    } else {
      showToast(`관심사에 맞는 소식 ${data.generated_signal_count}개를 정리했어요.`);
    }
    await Promise.allSettled([loadSettings(), loadInterests(false), loadSignals(false)]);
    detectFirstRun();
    renderFirstRunPanel();
    renderSignals();
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(button, false, original);
  }
}

function renderSignalCard(signal) {
  const sourceItems = signal.source_items_json || [];
  const confidence = Math.round(Number(signal.confidence || 0) * 100);
  const sourceUrl = signal.source_url || sourceItems.find((item) => item.url)?.url || "";
  const titleKo = signal.display_title_ko || signal.title || "오늘 확인할 소식";
  const headlineSummaryKo = signal.headline_summary_ko || signal.display_summary_ko || signal.summary || "원문에서 가져온 표현을 바탕으로 정리한 소식예요.";
  const storedReason = signal.recommendation_reason_ko || "";
  const reasonKo = needsRecommendationRewrite(storedReason) ? recommendationReason(signal) : storedReason;
  const actionKo = signal.recommended_action_ko || signal.recommended_action || "원문을 빠르게 훑고 계속 추적할 흐름인지 표시해보세요.";
  const originalTitle = signal.original_title || signal.title || sourceItems[0]?.title || "";
  const originalSnippet = signal.original_snippet || signal.summary || sourceItems[0]?.summary || "";
  const matchedKeywords = signal.matched_keywords || signal.metadata_json?.matched_keywords || [];
  const helpfulTermsAndTrend = helpfulTermsAndTrendText(signal, matchedKeywords);
  const coreSummary = cleanCoreSummary(signal.detail_summary_ko) || originalSnippet || headlineSummaryKo;
  const derivedFromKo = signal.derived_from_ko
    || (matchedKeywords.length ? `'${matchedKeywords[0]}' 키워드에서 찾은 소식` : "");
  return `
    <article class="signal-card" data-signal-id="${signal.id}">
      <div class="signal-head">
        <div class="rank">${signal.rank || 1}</div>
        <div>
          <h3 class="signal-title">${escapeHtml(titleKo)}</h3>
          ${derivedFromKo ? `<p class="signal-derived-from">${escapeHtml(derivedFromKo)}</p>` : ""}
          <p class="signal-summary">${escapeHtml(headlineSummaryKo)}</p>
        </div>
      </div>
      <div class="signal-meta">
        <span class="pill">출처 ${escapeHtml(signal.source_display || "출처 미확인")}</span>
        ${signal.collected_via ? `<span class="pill">수집 경로: ${escapeHtml(signal.collected_via)}</span>` : ""}
        <span class="pill">${escapeHtml(formatBriefingTimestamp(signal.content_timestamp || signal.created_at || signal.updated_at))}</span>
        <span class="pill">${signal.data_kind === "mock" ? "샘플 자료 · 실제 최신 정보 아님" : signal.data_kind === "live" ? "외부 소스 수집 자료" : "수집 유형 미확인"}</span>
        ${signal.generation_mode ? `<span class="pill">생성 당시 방식: ${escapeHtml(modeLabels[signal.generation_mode] || signal.generation_mode)}</span>` : ""}
        <span class="pill">관련도 ${confidence || 70}%</span>
        <span class="pill">관련 소스 ${sourceItems.length || 1}개</span>
        ${statusPill(signal.status)}
      </div>
      <div class="signal-body">
        <div class="info-box"><strong>핵심 요약</strong><p>${escapeHtml(headlineSummaryKo)}</p></div>
        <div class="info-box"><strong>왜 중요한지</strong><p>${escapeHtml(reasonKo)}</p></div>
      </div>
      <div class="actions">
        <button class="button secondary" data-feedback="saved">저장</button>
        <button class="button secondary" data-feedback="ignored">관심 없음</button>
        <button class="button secondary" data-feedback="tracked">계속 추적</button>
        <button class="button primary" data-open-url="${escapeHtml(sourceUrl)}" ${sourceUrl ? "" : "disabled"}>원문 보기</button>
        <button class="button ghost" data-ask-assistant="${signal.id}" data-signal-title="${escapeHtml(titleKo)}">Assistant에게 물어보기</button>
      </div>
      <details class="details">
        <summary>자세히 보기</summary>
        <div class="details-content">
          <p class="detail-summary">
            <strong>원문 제목</strong> ${escapeHtml(originalTitle || "확인되지 않았어요.")}<br><br>
            <strong>내용 정리</strong> ${escapeHtml(coreSummary)}<br><br>
            <strong>알면 좋을 용어·트렌드</strong> ${escapeHtml(helpfulTermsAndTrend)}
          </p>
        </div>
      </details>
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
  container.querySelectorAll("[data-feedback]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest(".signal-card");
      const eventType = button.dataset.feedback;
      const messages = { saved: "저장했어요", ignored: "비슷한 소식을 줄일게요", tracked: "이 흐름을 계속 지켜볼게요" };
      const scrollPosition = captureScrollPosition();
      setBusy(button, true, "처리 중");
      try {
        await api(`/api/v1/signals/${card.dataset.signalId}/feedback`, {
          method: "POST",
          body: JSON.stringify({ event_type: eventType, payload: { surface: "web_app" } }),
        });
        showToast(messages[eventType]);
        await loadSignals(false);
        renderSignals();
        restoreScrollPosition(scrollPosition);
      } catch (error) {
        showToast(error.message);
      } finally {
        setBusy(button, false, button.textContent === "처리 중" ? messages[eventType] || "완료" : button.textContent);
      }
    });
  });

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
  container.innerHTML = state.interests.map(renderInterestCard).join("");
  bindInterestActions(container);
  renderInterestRecommendations(container);
}

function renderInterestRecommendations(container) {
  const recommendations = state.interestRecommendations || [];
  if (!recommendations.length) return;
  const section = document.createElement("section");
  section.className = "interest-recommendations";
  section.innerHTML = `<div class="recommendation-heading"><div><p class="eyebrow">추천 키워드</p><h3>관심사와 최근 흐름에서 찾았어요</h3></div><p>아직 내 관심사에는 없지만 함께 살펴볼 만한 키워드예요.</p></div><div class="recommendation-list">${recommendations.map(renderInterestRecommendation).join("")}</div>`;
  container.appendChild(section);
  section.querySelectorAll("[data-recommendation-action]").forEach((button) => {
    button.addEventListener("click", () => handleInterestRecommendation(button));
  });
}

async function openFeedbackSignals(mode, scrollPosition = captureScrollPosition()) {
  const panel = document.getElementById(`feedback-${mode}-signals-panel`);
  state.feedbackMode = mode;
  showLoading(panel.id, "피드백한 소식을 불러오고 있어요.");
  try {
    const data = await api(`/api/v1/signals/feedback/${mode}`);
    state.feedbackSignals = data.signals || [];
    renderFeedbackSignals();
  } catch (error) {
    panel.innerHTML = emptyState("소식을 불러오지 못했어요.", "잠시 후 다시 시도해주세요.", "저장한 소식으로 돌아가기", "back-to-saved");
    bindEmptyAction("back-to-saved", closeFeedbackSignals);
  } finally {
    restoreScrollPosition(scrollPosition);
  }
}

function closeFeedbackSignals() {
  state.feedbackMode = null;
  setActiveTab("saved", { updateHash: true, load: true });
}

function renderFeedbackSignals() {
  const panel = document.getElementById(`feedback-${state.feedbackMode}-signals-panel`);
  const mode = state.feedbackMode;
  panel.innerHTML = state.feedbackSignals.length ? `<div class="stack">${state.feedbackSignals.map((signal, index) => renderFeedbackSignalCard(signal, index + 1)).join("")}</div>` : emptyState("아직 설정한 소식이 없어요.", "오늘의 소식에서 피드백을 선택하면 이곳에서 다시 볼 수 있어요.", "저장한 소식으로 돌아가기", "back-to-saved");
  panel.querySelectorAll("[data-open-url]").forEach((button) => button.addEventListener("click", () => window.open(button.dataset.openUrl, "_blank", "noopener,noreferrer")));
  panel.querySelectorAll("[data-clear-feedback]").forEach((button) => button.addEventListener("click", () => clearFeedbackSignal(button.closest(".signal-card").dataset.signalId, button)));
  panel.querySelector('[data-action="back-to-saved"]')?.addEventListener("click", closeFeedbackSignals);
}

function renderFeedbackSignalCard(signal, listRank) {
  const title = signal.display_title_ko || signal.title || "피드백한 소식";
  const summary = signal.headline_summary_ko || signal.display_summary_ko || signal.summary || "";
  const url = signal.source_url || "";
  const keywordOrigin = keywordOriginText(signal);
  const source = signal.source_display || sourceLabel(signal.source_name || "미확인");
  return `<article class="signal-card" data-signal-id="${signal.id}"><div class="signal-head"><div class="rank">${listRank}</div><div><h3 class="signal-title">${escapeHtml(title)}</h3><p class="signal-summary">${escapeHtml(summary)}</p></div></div><p class="signal-derived-from">${escapeHtml(keywordOrigin)}</p><div class="signal-meta"><span class="pill">출처 ${escapeHtml(source)}</span><span class="pill">설정한 날짜 ${escapeHtml(formatSavedDate(signal.feedback_at))}</span></div><div class="actions"><button class="button primary" data-open-url="${escapeHtml(url)}" ${url ? "" : "disabled"}>원문 보기</button><button class="button ghost" data-clear-feedback>설정 취소</button></div></article>`;
}

async function clearFeedbackSignal(signalId, button) {
  const scrollPosition = captureScrollPosition();
  setBusy(button, true, "취소 중");
  try {
    await api(`/api/v1/signals/${signalId}/feedback/${state.feedbackMode}`, { method: "DELETE" });
    state.feedbackSignals = state.feedbackSignals.filter((signal) => String(signal.id) !== String(signalId));
    renderFeedbackSignals();
    restoreScrollPosition(scrollPosition);
    showToast("피드백 설정을 취소했어요.");
  } catch (error) {
    showToast(error.message);
    setBusy(button, false, "설정 취소");
  }
}

function renderInterestRecommendation(recommendation) {
  return `<article class="recommendation-card" data-keyword="${escapeHtml(recommendation.keyword)}"><div><strong>${escapeHtml(recommendation.keyword)}</strong><p>${escapeHtml(recommendation.reason)}</p></div><div class="recommendation-actions"><button class="button secondary" data-recommendation-action="add">추가</button><button class="button ghost" data-recommendation-action="dismiss">삭제</button></div></article>`;
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
  return `
    <article class="card interest-card" data-keyword="${escapeHtml(interest.keyword)}" data-interest-status="${escapeHtml(interest.status)}">
      <div class="card-title"><h3>${escapeHtml(interest.keyword)}</h3>${interestStatusChip(interest.status)}</div>
      ${renderImportanceDots(interest.weight)}
      <div class="interest-actions">
        <button class="button secondary" data-interest-action="up">중요도 올리기</button>
        <button class="button secondary" data-interest-action="down">중요도 낮추기</button>
        ${interest.status === "muted" ? `<button class="button secondary" data-interest-action="unmute">다시 사용</button>` : `<button class="button secondary" data-interest-action="mute">숨기기</button>`}
        <button class="button danger" data-interest-action="delete">삭제</button>
      </div>
    </article>
  `;
}

function renderImportanceDots(weight) {
  const level = Math.max(1, Math.min(5, Math.round(Number(weight) || 1)));
  const dots = Array.from({ length: 5 }, (_, index) => `<span class="importance-dot${index < level ? " filled" : ""}" aria-hidden="true"></span>`).join("");
  return `<div class="importance-dots" aria-label="중요도 ${level}단계, 5단계 중">${dots}</div>`;
}

function bindInterestActions(container) {
  container.querySelectorAll("[data-interest-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest(".card");
      const keyword = card.dataset.keyword;
      const action = button.dataset.interestAction;
      const interest = state.interests.find((item) => item.keyword === keyword) || { weight: 1 };
      const original = button.textContent;
      setBusy(button, true, "저장 중");
      try {
        if (action === "mute") await api(`/api/v1/interests/${encodeURIComponent(keyword)}/mute`, { method: "POST" });
        if (action === "unmute") await api(`/api/v1/interests/${encodeURIComponent(keyword)}/unmute`, { method: "POST" });
        if (action === "delete") await api(`/api/v1/interests/${encodeURIComponent(keyword)}`, { method: "DELETE" });
        if (action === "up" || action === "down") {
          const nextWeight = Math.max(0.1, Number(interest.weight || 1) + (action === "up" ? 1 : -1));
          await api(`/api/v1/interests/${encodeURIComponent(keyword)}`, { method: "PUT", body: JSON.stringify({ weight: nextWeight }) });
        }
        showToast("관심사 설정을 반영했어요");
        await Promise.all([loadInterests(), loadSignals(false)]);
      } catch (error) {
        showToast(error.message);
      } finally {
        setBusy(button, false, original);
      }
    });
  });
}

async function loadSources(scrollPosition = captureScrollPosition()) {
  const container = document.getElementById("sources-list");
  showLoading("sources-list", "소스 설정을 확인하고 있어요.");
  try {
    const [catalogData, configData] = await Promise.all([api("/api/v1/sources/catalog"), api("/api/v1/sources/configs")]);
    state.sources = catalogData.sources || [];
    const sources = sourceOrder.map((id) => state.sources.find((source) => source.source_id === id)).filter(Boolean);
    const enabledCount = sources.filter((source) => source.current_enabled).length;
    const emptyBanner = !enabledCount
      ? `<div class="empty-state"><h3>사용 중인 소스가 없어요.</h3><p>Hacker News, GitHub, RSS 중 하나를 사용하면 소식을 만들 수 있어요.</p><button class="button primary" data-action="seed-sources">기본 소스 사용하기</button></div>`
      : "";
    container.innerHTML = emptyBanner + sources.map(renderSourceCard).join("");
    bindSourceActions(container);
    bindEmptyAction("seed-sources", seedDefaultSources);
  } catch (error) {
    container.innerHTML = emptyState("잠시 연결이 불안정해요.", "다시 시도해보세요.", "새로고침", "retry-sources");
    bindEmptyAction("retry-sources", loadSources);
  } finally {
    restoreScrollPosition(scrollPosition);
  }
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
  container.querySelectorAll("[data-save-source]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest(".card");
      const sourceId = card.dataset.sourceId;
      const source = state.sources.find((item) => item.source_id === sourceId);
      const config = { ...(source?.config_json || {}) };
      const textarea = card.querySelector("[data-feed-urls]");
      if (textarea) config.feed_urls = textarea.value.split("\n").map((line) => line.trim()).filter(Boolean);
      const original = button.textContent;
      setBusy(button, true, "저장 중");
      try {
        await api(`/api/v1/sources/configs/${sourceId}`, {
          method: "PUT",
          body: JSON.stringify({ enabled: Boolean(card.querySelector("[data-source-enabled]")?.checked), config_json: config }),
        });
        showToast("소스 설정을 저장했어요");
        await loadSources();
      } catch (error) {
        showToast(error.message);
      } finally {
        setBusy(button, false, original);
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
  const messages = { saved: "소식을 저장했어요", ignored: "비슷한 소식을 줄이기로 했어요", tracked: "흐름을 계속 추적하기로 했어요", opened: "원문을 열어봤어요" };
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

function openOnboarding() {
  document.getElementById("onboarding-modal").classList.remove("hidden");
  setOnboardingStep(1);
}

function closeOnboarding() {
  document.getElementById("onboarding-modal").classList.add("hidden");
}

function setOnboardingStep(step) {
  state.onboardingStep = Math.max(1, Math.min(3, step));
  document.querySelectorAll(".onboarding-step").forEach((panel) => panel.classList.toggle("active", Number(panel.dataset.step) === state.onboardingStep));
  document.querySelectorAll("[data-step-dot]").forEach((dot) => dot.classList.toggle("active", Number(dot.dataset.stepDot) <= state.onboardingStep));
  document.getElementById("onboarding-prev").disabled = state.onboardingStep === 1;
  document.getElementById("onboarding-next").classList.toggle("hidden", state.onboardingStep === 3);
  document.getElementById("onboarding-submit").classList.toggle("hidden", state.onboardingStep !== 3);
}

function addKeyword(value) {
  String(value || "").split(",").map((item) => item.trim()).filter(Boolean).forEach((keyword) => {
    if (!state.onboardingKeywords.includes(keyword)) state.onboardingKeywords.push(keyword);
  });
  renderKeywordTags();
}

function renderKeywordTags() {
  const row = document.getElementById("keyword-tags");
  row.innerHTML = state.onboardingKeywords.map((keyword) => `<button type="button" class="tag" data-remove-keyword="${escapeHtml(keyword)}">${escapeHtml(keyword)} ×</button>`).join("");
  row.querySelectorAll("[data-remove-keyword]").forEach((button) => {
    button.addEventListener("click", () => {
      state.onboardingKeywords = state.onboardingKeywords.filter((item) => item !== button.dataset.removeKeyword);
      renderKeywordTags();
    });
  });
}

async function completeOnboarding(event) {
  event.preventDefault();
  addKeyword(document.getElementById("keyword-input").value);
  document.getElementById("keyword-input").value = "";
  if (!state.onboardingKeywords.length) {
    showToast("관심 키워드를 하나 이상 입력해주세요.");
    setOnboardingStep(2);
    return;
  }
  const submit = document.getElementById("onboarding-submit");
  const original = submit.textContent;
  setBusy(submit, true, "첫 소식을 준비하는 중");
  try {
    const roleCustom = document.getElementById("onboarding-role-custom").value.trim();
    const role = roleCustom || state.onboardingRole;
    const signalCount = Number(document.getElementById("onboarding-signal-count").value || 3);
    const briefingTime = document.getElementById("onboarding-briefing-time").value || "08:00";
    const mode = document.querySelector("input[name='onboarding-mode']:checked")?.value || "hybrid";
    const browserEnabled = document.getElementById("onboarding-browser").checked;
    const localEnabled = document.getElementById("onboarding-local").checked;
    const folders = document.getElementById("onboarding-local-folders").value.split("\n").map((line) => line.trim()).filter(Boolean);

    await api("/api/v1/onboarding", {
      method: "POST",
      body: JSON.stringify({
        role,
        role_detail: role,
        goals: ["오늘 볼 소식을 빠르게 이해하기"],
        interest_types: state.onboardingKeywords,
        keywords: state.onboardingKeywords,
        preferred_signal_count: signalCount,
        briefing_time: briefingTime,
        connectors: { browser_history: browserEnabled, local_files: localEnabled },
      }),
    });
    await api("/api/v1/settings", {
      method: "PUT",
      body: JSON.stringify({ generate_mode: mode, signal_count: signalCount, briefing_time: briefingTime }),
    });
    await api("/api/v1/sources/configs/seed-defaults", { method: "POST", body: JSON.stringify({ overwrite: false }) });
    await Promise.allSettled([loadProfile(), loadSettings(), loadConnectors(), loadInterests(false)]);
    closeOnboarding();
    switchTab("signals");
    await generateSignals(submit);
    showToast("첫 오늘의 소식이 준비됐어요.");
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(submit, false, original);
  }
}

async function saveSettings(event) {
  event.preventDefault();
  const scrollPosition = captureScrollPosition();
  const selectedMode = document.querySelector("input[name='generate-mode']:checked")?.value || "hybrid";
  const submit = event.submitter || event.currentTarget.querySelector("button[type='submit']");
  const original = submit.textContent;
  setBusy(submit, true, "저장 중");
  try {
    await api("/api/v1/settings", {
      method: "PUT",
      body: JSON.stringify({
        signal_count: Number(document.getElementById("setting-signal-count").value),
        briefing_time: document.getElementById("setting-briefing-time").value || "08:00",
        mode_enabled: document.getElementById("setting-auto-briefing").checked,
        generate_mode: selectedMode,
      }),
    });
    showToast("설정을 저장했어요");
    await Promise.allSettled([loadSettings(), loadConnectors()]);
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(submit, false, original);
    restoreScrollPosition(scrollPosition);
  }
}

function renderSettings() {
  if (!state.settings) return;
  renderAccountShell();
  renderGateSummary();
  setValue("setting-signal-count", state.settings.signal_count || 3);
  renderSignalCountGateNote();
  setValue("setting-briefing-time", state.settings.briefing_time || "08:00");
  setChecked("setting-auto-briefing", state.settings.mode_enabled !== false);
  const modeInput = document.querySelector(`input[name="generate-mode"][value="${state.settings.generate_mode || "hybrid"}"]`);
  if (modeInput) modeInput.checked = true;
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
  const signalGate = (state.featureGates?.gates || []).find((gate) => gate.feature_key === "today_signal_count");
  const limit = Number(signalGate?.limit_value || 3);
  const value = Number(select.value || 3);
  note.textContent = value > limit
    ? `현재는 저장할 수 있어요. 다만 ${state.featureGates?.plan || "Free"} 기준에서는 오늘의 소식 ${limit}개가 기본이에요.`
    : "";
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
  const labels = { saved: "저장됨", ignored: "관심 없음", tracked: "계속 추적 중", active: "사용 중", new: "새 소식" };
  return `<span class="status-chip subtle">${labels[status] || "사용 중"}</span>`;
}

function interestStatusChip(status) {
  const labels = { active: "사용 중", muted: "숨김", deleted: "삭제됨" };
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

// ─── Auth functions ───────────────────────────────────────────────────────

/**
 * Initialize auth state at app startup.
 * Returns true  → proceed with app initialisation.
 * Returns false → navigating to /login (don't proceed).
 */
async function initAuth() {
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
  state.profile = null;
  state.settings = null;
  state.connectors = [];
  state.sources = [];
  state.interests = [];
  state.interestRecommendations = [];
  state.feedbackSignals = [];
  state.feedbackMode = null;
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
}
