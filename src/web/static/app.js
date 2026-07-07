const state = {
  profile: null,
  settings: null,
  connectors: [],
  sources: [],
  interests: [],
  signals: [],
  activeTab: "signals",
  onboardingStep: 1,
  onboardingRole: "예비 창업자 / PM",
  onboardingKeywords: [],
  firstRun: false,
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
  youtube: ["YouTube", "영상과 크리에이터 흐름을 볼 수 있도록 준비하고 있어요."],
  naver_news: ["Naver News", "국내 산업과 기업 뉴스를 볼 수 있도록 준비하고 있어요."],
  arxiv: ["arXiv", "연구 논문 흐름을 볼 수 있도록 준비하고 있어요."],
  company_newsroom: ["Company Newsrooms", "회사 공식 뉴스룸을 더 편하게 연결할 수 있도록 준비하고 있어요."],
};

const sourceOrder = ["hackernews", "github", "rss", "official_ai_blogs", "producthunt", "reddit", "youtube", "naver_news", "arxiv", "company_newsroom"];
const hashToTab = {
  "#today": "signals",
  "#signals": "signals",
  "#interests": "interests",
  "#sources": "sources",
  "#activity": "activity",
  "#settings": "settings",
};
const tabToHash = {
  signals: "#today",
  interests: "#interests",
  sources: "#sources",
  activity: "#activity",
  settings: "#settings",
};

document.addEventListener("DOMContentLoaded", () => {
  initAuthShell();
  bindNavigation();
  bindTopActions();
  bindOnboarding();
  applyHashTab({ load: false });
  window.addEventListener("hashchange", applyHashTab);
  loadInitialData().then(() => {
    if (state.activeTab !== "signals") loadTab(state.activeTab);
  });
});

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
  document.getElementById("refresh-signals").addEventListener("click", loadSignals);
  document.getElementById("sync-context").addEventListener("click", syncContext);
  document.getElementById("refresh-activity").addEventListener("click", loadActivity);
  document.getElementById("settings-form").addEventListener("submit", saveSettings);
  document.getElementById("account-chip")?.addEventListener("click", () => setActiveTab("settings", { updateHash: true, load: true }));
  document.querySelectorAll("[data-account-action]").forEach((button) => {
    button.addEventListener("click", () => handleAccountAction(button.dataset.accountAction));
  });
  document.getElementById("setting-signal-count")?.addEventListener("change", renderSignalCountGateNote);
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
  showLoading("signals-list", "오늘의 신호를 확인하고 있어요.");
  await Promise.allSettled([loadProfile(), loadSettings(), loadConnectors(), loadSources(), loadInterests(false), loadSignals(false)]);
  detectFirstRun();
  renderFirstRunPanel();
  renderSettings();
}

async function loadTab(tab) {
  if (tab === "signals") await loadSignals();
  if (tab === "interests") await loadInterests();
  if (tab === "sources") await loadSources();
  if (tab === "activity") await loadActivity();
  if (tab === "settings") {
    await Promise.allSettled([loadSettings(), loadConnectors(), loadCloudAccountStatus(), loadFeatureGates()]);
    renderSettings();
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) throw new Error("잠시 연결이 불안정해요. 다시 시도해보세요.");
  const data = await response.json();
  if (data.success === false) throw new Error(data.error || "잠시 연결이 불안정해요. 다시 시도해보세요.");
  return data;
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

async function loadSignals(render = true) {
  const container = document.getElementById("signals-list");
  if (render) showLoading("signals-list", "오늘의 신호를 불러오고 있어요.");
  try {
    const data = await api("/api/v1/signals/today");
    state.signals = (data.signals || []).filter((signal) => signal.status !== "archived");
    if (render) renderSignals();
  } catch (error) {
    if (render) {
      container.innerHTML = emptyState("잠시 연결이 불안정해요.", "다시 시도해보세요.", "새로고침", "retry-signals");
      bindEmptyAction("retry-signals", loadSignals);
    }
  }
}

function renderSignals() {
  const container = document.getElementById("signals-list");
  document.getElementById("signals-status").textContent = state.signals.length
    ? `오늘의 신호 ${state.signals.length}개가 준비됐어요.`
    : "아직 오늘의 신호가 없어요. 지금 받아볼까요?";
  if (!state.signals.length) {
    container.innerHTML = emptyState(
      "아직 오늘의 신호가 없어요.",
      "지금 새로 받아보면 관심사에 맞는 변화를 한국어로 정리해드릴게요.",
      "지금 새로 받기",
      "generate"
    );
    bindEmptyAction("generate", () => generateSignals());
    return;
  }
  container.innerHTML = state.signals.map(renderSignalCard).join("");
  bindSignalActions(container);
}

function detectFirstRun() {
  const onboardingDone = Boolean(state.settings?.onboarding_completed);
  const activeInterests = state.interests.filter((item) => item.status === "active");
  state.firstRun = !state.profile || !onboardingDone || activeInterests.length < 1 || state.signals.length < 1;
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
        <p>30초만 설정하면 오늘 볼 신호를 한국어로 정리해드릴게요.</p>
      </div>
      <button class="button primary" data-open-onboarding>시작하기</button>
    </div>
  `;
  panel.querySelector("[data-open-onboarding]").addEventListener("click", openOnboarding);
}

async function generateSignals(triggerButton) {
  const button = triggerButton || document.getElementById("generate-signals");
  const original = button.textContent;
  setBusy(button, true, "신호를 고르는 중");
  try {
    const mode = state.settings?.generate_mode || "hybrid";
    const data = await api("/api/v1/signals/generate", {
      method: "POST",
      body: JSON.stringify({ mode, replace_today: true }),
    });
    if ((data.failed_sources || []).length || Object.keys(data.errors_by_source || {}).length) {
      showToast("일부 소스에서 데이터를 가져오지 못했지만, 가능한 소스로 신호를 만들었어요.");
    } else {
      showToast("오늘의 신호를 한국어로 정리했어요.");
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
  const titleKo = signal.display_title_ko || signal.title || "오늘 확인할 신호";
  const summaryKo = signal.display_summary_ko || signal.summary || "원문에서 가져온 표현을 바탕으로 정리한 신호예요.";
  const whyKo = signal.why_it_matters_ko || signal.why_it_matters || "지금 흐름을 이해하는 데 도움이 되는 변화예요.";
  const reasonKo = signal.recommendation_reason_ko || recommendationReason(signal);
  const actionKo = signal.recommended_action_ko || signal.recommended_action || "원문을 빠르게 훑고 계속 추적할 흐름인지 표시해보세요.";
  const originalTitle = signal.original_title || signal.title || sourceItems[0]?.title || "";
  const originalSnippet = signal.original_snippet || signal.summary || sourceItems[0]?.summary || "";
  return `
    <article class="signal-card" data-signal-id="${signal.id}">
      <div class="signal-head">
        <div class="rank">${signal.rank || 1}</div>
        <div>
          <h3 class="signal-title">${escapeHtml(titleKo)}</h3>
          <p class="signal-summary">${escapeHtml(summaryKo)}</p>
        </div>
      </div>
      <div class="signal-meta">
        <span class="pill">출처 ${escapeHtml(sourceLabel(signal.source_name || sourceItems[0]?.source || "선별 소스"))}</span>
        <span class="pill">관련도 ${confidence || 70}%</span>
        <span class="pill">관련 소스 ${sourceItems.length || 1}개</span>
        ${statusPill(signal.status)}
      </div>
      <div class="signal-body">
        <div class="info-box"><strong>왜 중요한가</strong><p>${escapeHtml(whyKo)}</p></div>
        <div class="info-box"><strong>왜 나에게 추천됐나요?</strong><p>${escapeHtml(reasonKo)}</p></div>
        <div class="info-box"><strong>다음에 볼 것</strong><p>${escapeHtml(actionKo)}</p></div>
      </div>
      <div class="actions">
        <button class="button secondary" data-feedback="saved">저장</button>
        <button class="button secondary" data-feedback="ignored">관심 없음</button>
        <button class="button secondary" data-feedback="tracked">계속 추적</button>
        <button class="button ghost" data-open-url="${escapeHtml(sourceUrl)}" ${sourceUrl ? "" : "disabled"}>원문 보기</button>
      </div>
      <details class="details">
        <summary>자세히 보기</summary>
        <div class="details-content">
          <div class="detail-block"><strong>원문 제목</strong><p>${escapeHtml(originalTitle || "원문 제목을 찾지 못했어요.")}</p></div>
          <div class="detail-block"><strong>원문 snippet</strong><p>${escapeHtml(originalSnippet || "원문에서 가져온 짧은 설명이 아직 없어요.")}</p></div>
          <p>일부 정보는 원문에서 가져온 표현이에요. 핵심 내용은 한국어 브리핑으로 다시 정리했어요.</p>
          <p>${signal.pipeline_run_id ? "이번 브리핑을 만든 내부 기록이 있어요." : "브리핑 기록은 아직 연결되지 않았어요."}</p>
          <p>현재 생성 방식은 ${modeLabels[state.settings?.generate_mode || "hybrid"] || "혼합 모드"}예요.</p>
          ${sourceItems.length ? `<div class="related-list">${sourceItems.map(renderRelatedItem).join("")}</div>` : ""}
          <div class="diagnostic-box">
            <strong>브리핑 참고 정보</strong>
            <span>관련도는 ${confidence || 70}%로 계산됐어요.</span>
            <span>${signal.pipeline_run_id ? `이번 브리핑 기록 번호는 ${signal.pipeline_run_id}예요.` : "이번 브리핑 기록 번호는 아직 없어요."}</span>
            <span>생성 방식은 ${modeLabels[state.settings?.generate_mode || "hybrid"] || "혼합 모드"}예요.</span>
          </div>
        </div>
      </details>
    </article>
  `;
}

function renderRelatedItem(item) {
  return `<div class="related-item"><strong>${escapeHtml(sourceLabel(item.source || "소스"))}</strong><span>${escapeHtml(item.title || item.url || "관련 원문")}</span></div>`;
}

function bindSignalActions(container) {
  container.querySelectorAll("[data-feedback]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest(".signal-card");
      const eventType = button.dataset.feedback;
      const messages = { saved: "저장했어요", ignored: "비슷한 신호를 줄일게요", tracked: "이 흐름을 계속 지켜볼게요" };
      setBusy(button, true, "처리 중");
      try {
        await api(`/api/v1/signals/${card.dataset.signalId}/feedback`, {
          method: "POST",
          body: JSON.stringify({ event_type: eventType, payload: { surface: "web_app" } }),
        });
        showToast(messages[eventType]);
        await loadSignals(false);
        renderSignals();
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
}

async function loadInterests(render = true) {
  const container = document.getElementById("interests-list");
  if (render) showLoading("interests-list", "관심사를 불러오고 있어요.");
  try {
    const data = await api("/api/v1/interests?include_muted=true&limit=100");
    state.interests = data.interests || [];
    if (render) renderInterests();
  } catch (error) {
    if (render) {
      container.innerHTML = emptyState("잠시 연결이 불안정해요.", "다시 시도해보세요.", "새로고침", "retry-interests");
      bindEmptyAction("retry-interests", loadInterests);
    }
  }
}

function renderInterests() {
  const container = document.getElementById("interests-list");
  if (!state.interests.length) {
    container.innerHTML = emptyState(
      "아직 추천 기준이 충분하지 않아요.",
      "관심 키워드를 추가하면 더 정확한 신호를 받을 수 있어요.",
      "관심사 추가하기",
      "open-onboarding"
    );
    bindEmptyAction("open-onboarding", openOnboarding);
    return;
  }
  container.innerHTML = state.interests.map(renderInterestCard).join("");
  bindInterestActions(container);
}

function renderInterestCard(interest) {
  return `
    <article class="card" data-keyword="${escapeHtml(interest.keyword)}">
      <div class="card-title"><h3>${escapeHtml(interest.keyword)}</h3>${interestStatusChip(interest.status)}</div>
      <div class="pill-row">
        <span class="pill">중요도 ${weightLabel(interest.weight)}</span>
        <span class="pill">${sourceNameForInterest(interest.source)}</span>
      </div>
      <p>${escapeHtml(evidenceSentence(interest))}</p>
      <div class="actions">
        ${interest.status === "muted" ? `<button class="button secondary" data-interest-action="unmute">다시 사용</button>` : `<button class="button secondary" data-interest-action="mute">숨기기</button>`}
        <button class="button secondary" data-interest-action="up">중요도 올리기</button>
        <button class="button secondary" data-interest-action="down">중요도 낮추기</button>
        <button class="button danger" data-interest-action="delete">삭제</button>
      </div>
      <details class="details">
        <summary>이 관심사가 생긴 이유</summary>
        <div class="details-content"><p>${escapeHtml(evidenceSentence(interest))}</p></div>
      </details>
    </article>
  `;
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
        await loadInterests();
      } catch (error) {
        showToast(error.message);
      } finally {
        setBusy(button, false, original);
      }
    });
  });
}

async function syncContext() {
  const button = document.getElementById("sync-context");
  const original = button.textContent;
  setBusy(button, true, "동기화 중");
  try {
    await api("/api/v1/context/sync", { method: "POST", body: JSON.stringify({ limit: 100 }) });
    showToast("개인 맥락 동기화를 마쳤어요");
    await Promise.allSettled([loadInterests(), loadActivity()]);
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(button, false, original);
  }
}

async function loadSources() {
  const container = document.getElementById("sources-list");
  showLoading("sources-list", "소스 설정을 확인하고 있어요.");
  try {
    const [catalogData, configData] = await Promise.all([api("/api/v1/sources/catalog"), api("/api/v1/sources/configs")]);
    state.sources = catalogData.sources || [];
    const sources = sourceOrder.map((id) => state.sources.find((source) => source.source_id === id)).filter(Boolean);
    const enabledCount = sources.filter((source) => source.current_enabled).length;
    const emptyBanner = !enabledCount
      ? `<div class="empty-state"><h3>켜진 소스가 없어요.</h3><p>Hacker News, GitHub, RSS 중 하나를 켜면 신호를 만들 수 있어요.</p><button class="button primary" data-action="seed-sources">기본 소스 켜기</button></div>`
      : "";
    container.innerHTML = emptyBanner + sources.map(renderSourceCard).join("");
    bindSourceActions(container);
    bindEmptyAction("seed-sources", seedDefaultSources);
  } catch (error) {
    container.innerHTML = emptyState("잠시 연결이 불안정해요.", "다시 시도해보세요.", "새로고침", "retry-sources");
    bindEmptyAction("retry-sources", loadSources);
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
        <span>${source.current_enabled ? "켜져 있어요" : "꺼져 있어요"}</span>
        <input type="checkbox" data-source-enabled ${source.current_enabled ? "checked" : ""} ${status === "준비 중" ? "disabled" : ""} />
      </label>
      ${source.source_id === "github" ? `<p>GitHub 토큰은 선택 사항이에요. GITHUB_TOKEN 환경변수를 설정하면 더 안정적으로 수집할 수 있어요.</p>` : ""}
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

async function loadActivity() {
  const container = document.getElementById("activity-list");
  showLoading("activity-list", "활동 기록을 불러오고 있어요.");
  try {
    const [pipelineData, syncData, feedbackData] = await Promise.all([
      api("/api/v1/pipeline/runs?limit=12"),
      api("/api/v1/context/sync-runs?limit=12"),
      api("/api/v1/feedback/events?limit=12"),
    ]);
    const items = [
      ...(pipelineData.runs || []).map(activityFromPipeline),
      ...(syncData.runs || []).map(activityFromSync),
      ...(feedbackData.events || []).map(activityFromFeedback),
    ].sort((a, b) => new Date(b.time) - new Date(a.time));
    if (!items.length) {
      container.innerHTML = `<div class="empty-state"><h3>아직 활동 기록이 없어요.</h3><p>오늘의 신호를 받으면 이곳에 기록이 남아요.</p></div>`;
      return;
    }
    container.innerHTML = items.slice(0, 18).map(renderActivityItem).join("");
  } catch (error) {
    container.innerHTML = emptyState("잠시 연결이 불안정해요.", "다시 시도해보세요.", "새로고침", "retry-activity");
    bindEmptyAction("retry-activity", loadActivity);
  }
}

function activityFromPipeline(run) {
  const summary = run.summary_json || {};
  const hasWarnings = run.error_message || Object.keys(summary.errors_by_source || {}).length;
  return {
    time: run.completed_at || run.started_at,
    title: `${formatTime(run.completed_at || run.started_at)} 오늘의 신호를 만들었어요`,
    body: `총 ${run.source_item_count || 0}개 후보를 확인하고 신호 ${run.signal_count || 0}개를 골랐어요.`,
    detail: hasWarnings ? "일부 소스에서 데이터를 가져오지 못했지만, 가능한 소스로 신호를 만들었어요." : "브리핑 생성이 정상적으로 끝났어요.",
    raw: run,
  };
}

function activityFromSync(run) {
  return {
    time: run.completed_at || run.started_at,
    title: `${formatTime(run.completed_at || run.started_at)} 개인 맥락을 살펴봤어요`,
    body: `${connectorLabel(run.connector_type)}에서 새 항목 ${run.item_count || 0}개와 관심사 ${run.keyword_count || 0}개를 찾았어요.`,
    detail: run.error_message ? "일부 내용을 읽지 못했지만, 가능한 범위에서 반영했어요." : "동기화가 정상적으로 끝났어요.",
    raw: run,
  };
}

function activityFromFeedback(event) {
  const messages = { saved: "신호를 저장했어요", ignored: "비슷한 신호를 줄이기로 했어요", tracked: "흐름을 계속 추적하기로 했어요", opened: "원문을 열어봤어요" };
  return {
    time: event.created_at,
    title: `${formatTime(event.created_at)} ${messages[event.event_type] || "활동을 기록했어요"}`,
    body: event.signal_title ? `관련 신호: ${event.signal_title}` : "브리핑 사용 흐름을 반영했어요.",
    detail: "이 기록은 다음 신호를 더 잘 고르는 데 사용돼요.",
    raw: event,
  };
}

function renderActivityItem(item) {
  return `
    <article class="activity-item">
      <div class="card-title"><h3>${escapeHtml(item.title)}</h3></div>
      <p>${escapeHtml(item.body)}</p>
      <details class="details">
        <summary>자세히 보기</summary>
        <div class="details-content">
          <p>${escapeHtml(item.detail)}</p>
          <pre class="technical-box">${escapeHtml(JSON.stringify(item.raw, null, 2))}</pre>
        </div>
      </details>
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
  setBusy(submit, true, "첫 신호를 준비하는 중");
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
        goals: ["오늘 볼 신호를 빠르게 이해하기"],
        interest_types: state.onboardingKeywords,
        keywords: state.onboardingKeywords,
        preferred_signal_count: signalCount,
        briefing_time: briefingTime,
        connectors: { browser_history: browserEnabled, local_files: localEnabled },
      }),
    });
    await api("/api/v1/settings", {
      method: "PUT",
      body: JSON.stringify({ generate_mode: mode, sync_before_briefing: true, signal_count: signalCount, briefing_time: briefingTime }),
    });
    await api("/api/v1/connectors/browser_history", { method: "PUT", body: JSON.stringify({ enabled: browserEnabled, config: {} }) });
    await api("/api/v1/connectors/local_files", { method: "PUT", body: JSON.stringify({ enabled: localEnabled, config: { folders } }) });
    await api("/api/v1/sources/configs/seed-defaults", { method: "POST", body: JSON.stringify({ overwrite: false }) });
    await Promise.allSettled([loadProfile(), loadSettings(), loadConnectors(), loadInterests(false)]);
    closeOnboarding();
    switchTab("signals");
    await generateSignals(submit);
    showToast("첫 오늘의 신호가 준비됐어요.");
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(submit, false, original);
  }
}

async function saveSettings(event) {
  event.preventDefault();
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
        sync_before_briefing: document.getElementById("setting-sync-before").checked,
        context_sync_interval_minutes: Number(document.getElementById("setting-sync-interval").value),
        generate_mode: selectedMode,
      }),
    });
    await api("/api/v1/connectors/browser_history", { method: "PUT", body: JSON.stringify({ enabled: document.getElementById("connector-browser").checked, config: {} }) });
    await api("/api/v1/connectors/local_files", {
      method: "PUT",
      body: JSON.stringify({
        enabled: document.getElementById("connector-local").checked,
        config: { folders: document.getElementById("connector-local-folders").value.split("\n").map((line) => line.trim()).filter(Boolean) },
      }),
    });
    showToast("설정을 저장했어요");
    await Promise.allSettled([loadSettings(), loadConnectors()]);
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(submit, false, original);
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
  setChecked("setting-sync-before", state.settings.sync_before_briefing !== false);
  setValue("setting-sync-interval", state.settings.context_sync_interval_minutes || 360);
  const modeInput = document.querySelector(`input[name="generate-mode"][value="${state.settings.generate_mode || "hybrid"}"]`);
  if (modeInput) modeInput.checked = true;
  const browser = state.connectors.find((item) => item.connector_type === "browser_history");
  const local = state.connectors.find((item) => item.connector_type === "local_files");
  setChecked("connector-browser", Boolean(browser?.enabled));
  setChecked("connector-local", Boolean(local?.enabled));
  setValue("connector-local-folders", (local?.config_json?.folders || []).join("\n"));
}

function initAuthShell() {
  const mockAuth = new URLSearchParams(location.search).get("mockAuth");
  if (mockAuth === "free" || mockAuth === "pro") {
    state.authShell = {
      mode: "mock",
      plan: mockAuth === "pro" ? "Pro" : "Free",
      label: mockAuth === "pro" ? "Mock Pro 계정" : "Mock Free 계정",
      isMock: true,
    };
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
  return `하루 신호 ${signalLimit}개 · 소스 ${sourceLimit}개 · ${autoBriefing}`;
}

function formatDateTime(value) {
  if (!value) return "아직 없음";
  try {
    return new Date(value).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
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
    ? `현재는 저장할 수 있어요. 다만 ${state.featureGates?.plan || "Free"} 기준에서는 오늘의 신호 ${limit}개가 기본이에요.`
    : "";
}

function gateTitle(key) {
  return {
    today_signal_count: "오늘 신호 개수",
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
  const labels = { saved: "저장됨", ignored: "줄이는 중", tracked: "추적 중", active: "사용 중", new: "새 신호" };
  return `<span class="status-chip subtle">${labels[status] || "사용 중"}</span>`;
}

function interestStatusChip(status) {
  const labels = { active: "사용 중", muted: "숨김", deleted: "삭제됨" };
  const className = status === "active" ? "ready" : status === "muted" ? "warning" : "off";
  return `<span class="status-chip ${className}">${labels[status] || "사용 중"}</span>`;
}

function sourceStatusChip(status) {
  const className = status === "준비됨" || status === "토큰 선택" ? "ready" : status === "꺼짐" ? "off" : "warning";
  return `<span class="status-chip ${className}">${status}</span>`;
}

function sourceStatus(source) {
  if (source.implemented_status !== "implemented") return "준비 중";
  if (!source.current_enabled) return "꺼짐";
  const config = source.config_json || {};
  if (["rss", "official_ai_blogs", "company_newsroom"].includes(source.source_id) && !(config.feed_urls || []).length) return "URL 필요";
  if (source.source_id === "github") return "토큰 선택";
  return "준비됨";
}

function recommendationReason(signal) {
  if (signal.category) return `${humanCategory(signal.category)} 흐름과 내 관심 기준이 맞았어요.`;
  return "최근 관심 흐름과 잘 맞는 신호예요.";
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
  return labels[category] || "관심";
}

function formatTime(value) {
  if (!value) return "방금";
  const date = new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return "방금";
  return date.toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit" });
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
