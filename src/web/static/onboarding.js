const onboardingState = { interests: [], informationTypePreferences: {}, userId: "", draftKey: "", previewTimer: null };

document.addEventListener("DOMContentLoaded", () => initOnboarding().catch(showFatal));

async function initOnboarding() {
  await authClient.init();
  if (authClient.isAuthMode()) {
    const session = await authClient.getSession();
    if (!session) return authClient.redirectToLogin();
    onboardingState.userId = session.user.id;
  }
  onboardingState.draftKey = `lumos:onboarding-draft:${onboardingState.userId || "local"}`;
  if ((await api("/api/v1/onboarding/status")).completed) return window.location.replace("/app");
  restoreDraft();
  bindOnboarding();
  document.body.classList.remove("onboarding-page-pending");
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (authClient.isAuthMode()) {
    const token = await authClient.getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) { authClient.redirectToLogin(); throw new Error("\ub85c\uadf8\uc778\uc774 \ud544\uc694\ud569\ub2c8\ub2e4."); }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "\uc800\uc7a5\ud558\uc9c0 \ubabb\ud588\uc5b4\uc694. \ub2e4\uc2dc \uc2dc\ub3c4\ud574 \uc8fc\uc138\uc694.");
  }
  return response.json();
}

function bindOnboarding() {
  const input = document.getElementById("interest-input");
  input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); commitInterestInput(); } });
  input.addEventListener("input", () => { clearInterestError(); saveDraft(); });
  document.querySelectorAll("[data-interest]").forEach((button) => button.addEventListener("click", () => addInterest(button.dataset.interest)));
  document.getElementById("interest-add").addEventListener("click", () => { commitInterestInput(); input.focus(); });
  document.querySelectorAll("#purpose-options input, #purpose-custom, #source-hints").forEach((element) => {
    element.addEventListener("input", saveDraft); element.addEventListener("change", saveDraft);
  });
  document.getElementById("clarification-skip").addEventListener("click", () => {
    document.querySelectorAll("[data-clarification-needed='true']").forEach((group) => {
      delete onboardingState.informationTypePreferences[group.dataset.interestKeyword];
    });
    saveDraft(); schedulePreview();
  });
  document.getElementById("onboarding-form").addEventListener("submit", submitOnboarding);
  renderInterests();
}

function commitInterestInput() { const input = document.getElementById("interest-input"); addInterest(input.value); input.value = ""; saveDraft(); }

function addInterest(value) {
  for (const term of String(value || "").split(",").map((item) => item.trim()).filter(Boolean)) {
    const normalized = term.toLocaleLowerCase("ko-KR");
    if (!onboardingState.interests.some((interest) => interest.toLocaleLowerCase("ko-KR") === normalized)) onboardingState.interests.push(term);
  }
  clearInterestError(); renderInterests(); saveDraft();
}

function renderInterests() {
  const row = document.getElementById("interest-tags");
  row.innerHTML = onboardingState.interests.map((interest) => `<button type="button" class="tag" data-remove-interest="${escapeHtml(interest)}" aria-label="${escapeHtml(interest)} \uc81c\uac70"><span>${escapeHtml(interest)}</span><span aria-hidden="true">\u00d7</span></button>`).join("");
  row.querySelectorAll("[data-remove-interest]").forEach((button) => button.addEventListener("click", () => {
    const removed = button.dataset.removeInterest;
    onboardingState.interests = onboardingState.interests.filter((value) => value !== removed);
    delete onboardingState.informationTypePreferences[removed];
    renderInterests(); saveDraft();
  }));
  document.querySelectorAll("[data-interest]").forEach((button) => {
    const selected = onboardingState.interests.some((interest) => interest.toLocaleLowerCase("ko-KR") === button.dataset.interest.toLocaleLowerCase("ko-KR"));
    button.disabled = selected; button.setAttribute("aria-pressed", String(selected));
  });
  updateSubmitState(); schedulePreview();
}

function schedulePreview() {
  window.clearTimeout(onboardingState.previewTimer);
  const section = document.getElementById("information-types-section");
  if (!onboardingState.interests.length) { section.hidden = true; document.getElementById("information-type-options").innerHTML = ""; document.getElementById("source-availability").innerHTML = ""; return; }
  onboardingState.previewTimer = window.setTimeout(loadPreview, 180);
}

async function loadPreview() {
  try {
    const result = await api("/api/v1/onboarding/preview", { method: "POST", body: JSON.stringify({ keywords: onboardingState.interests, interest_type_preferences: onboardingState.informationTypePreferences }) });
    renderInformationTypes(result.interests || []);
  } catch (_) {
    // Preview is advisory only. A transport failure must not block signup.
    document.getElementById("information-types-section").hidden = true;
  }
}

function renderInformationTypes(interests) {
  const section = document.getElementById("information-types-section");
  const optionsRoot = document.getElementById("information-type-options");
  const availabilityRoot = document.getElementById("source-availability");
  const known = new Set(interests.map((item) => item.keyword));
  Object.keys(onboardingState.informationTypePreferences).forEach((keyword) => { if (!known.has(keyword)) delete onboardingState.informationTypePreferences[keyword]; });
  const groups = interests.filter((item) => {
    const chosen = onboardingState.informationTypePreferences[item.keyword] || [];
    return Boolean(item.clarification?.needed) || chosen.length > 0;
  });
  // Specific interests do not need an extra question, but their source state
  // must remain visible so an unsupported topic is never implied to work.
  section.hidden = interests.length === 0;
  optionsRoot.innerHTML = groups.map((item) => {
    const chosen = new Set(onboardingState.informationTypePreferences[item.keyword] || []);
    const choices = item.information_type_options.map((option) => `<label class="information-type-choice"><input type="checkbox" data-preference-interest="${escapeHtml(item.keyword)}" data-type-id="${escapeHtml(option.id)}" ${chosen.has(option.id) ? "checked" : ""} /><span>${escapeHtml(option.label)}</span></label>`).join("");
    const isClarification = Boolean(item.clarification?.needed);
    const prompt = isClarification ? "\uc5b4\ub5a4 \uc18c\uc2dd\uc744 \ub354 \ubc1b\uace0 \uc2f6\uc73c\uc138\uc694?" : "\uc120\ud0dd\ud55c \uc815\ubcf4 \uc720\ud615";
    const guidance = chosen.size > 2 ? `<p class="clarification-guidance">\uc5ec\ub7ec \uc720\ud615\uc744 \uace0\ub97c \uc218 \uc788\uc9c0\ub9cc, 1~2\uac1c\ub97c \uace0\ub974\uba74 \uccab \ube0c\ub9ac\ud551\uc758 \ubc29\ud5a5\uc774 \ub354 \uc120\uba85\ud574\uc838\uc694.</p>` : "";
    return `<section class="information-type-group" data-interest-keyword="${escapeHtml(item.keyword)}" data-clarification-needed="${isClarification}"><h3>${escapeHtml(item.keyword)} <small>${prompt}</small></h3><div class="information-type-choice-list">${choices}</div>${guidance}</section>`;
  }).join("");
  document.getElementById("clarification-skip").hidden = !groups.some((item) => item.clarification?.needed);
  availabilityRoot.innerHTML = interests.map((item) => `<p class="source-availability-item"><strong>${escapeHtml(item.keyword)}</strong> · ${escapeHtml((item.availability || {}).message || "\uc815\ubcf4\uc6d0 \uc0c1\ud0dc\ub97c \ud655\uc778\ud558\uace0 \uc788\uc5b4\uc694.")}</p>`).join("");
  optionsRoot.querySelectorAll("[data-preference-interest]").forEach((input) => input.addEventListener("change", () => {
    const keyword = input.dataset.preferenceInterest; const selected = new Set(onboardingState.informationTypePreferences[keyword] || []);
    if (input.checked) selected.add(input.dataset.typeId); else selected.delete(input.dataset.typeId);
    if (selected.size) onboardingState.informationTypePreferences[keyword] = [...selected]; else delete onboardingState.informationTypePreferences[keyword];
    renderInformationTypes(interests); saveDraft(); schedulePreview();
  }));
}

function clearInterestError() { document.getElementById("interest-error").textContent = ""; document.getElementById("interest-input").removeAttribute("aria-invalid"); }
function updateSubmitState() { const submit = document.getElementById("onboarding-submit"); if (!submit.dataset.submitting) submit.disabled = onboardingState.interests.length === 0; }
function selectedGoals() { const goals = [...document.querySelectorAll("#purpose-options input:checked")].map((input) => input.value); const custom = document.getElementById("purpose-custom").value.trim(); if (custom) goals.push(custom); return goals; }
function sourceHints() { return document.getElementById("source-hints").value.split(/\n|,/).map((value) => value.trim()).filter(Boolean).slice(0, 20); }

function saveDraft() {
  if (!onboardingState.draftKey) return;
  sessionStorage.setItem(onboardingState.draftKey, JSON.stringify({ interests: onboardingState.interests, interestInput: document.getElementById("interest-input")?.value || "", goals: selectedGoals(), customPurpose: document.getElementById("purpose-custom")?.value || "", informationTypePreferences: onboardingState.informationTypePreferences, sourceHints: document.getElementById("source-hints")?.value || "" }));
}

function restoreDraft() {
  try {
    const draft = JSON.parse(sessionStorage.getItem(onboardingState.draftKey) || "null"); if (!draft) return;
    onboardingState.interests = Array.isArray(draft.interests) ? draft.interests : [];
    onboardingState.informationTypePreferences = draft.informationTypePreferences && typeof draft.informationTypePreferences === "object" ? draft.informationTypePreferences : {};
    document.getElementById("interest-input").value = draft.interestInput || ""; document.getElementById("purpose-custom").value = draft.customPurpose || ""; document.getElementById("source-hints").value = draft.sourceHints || "";
    const goals = new Set(draft.goals || []); document.querySelectorAll("#purpose-options input").forEach((input) => { input.checked = goals.has(input.value); });
  } catch (_) { sessionStorage.removeItem(onboardingState.draftKey); }
}

async function submitOnboarding(event) {
  event.preventDefault(); commitInterestInput();
  if (!onboardingState.interests.length) { const input = document.getElementById("interest-input"); document.getElementById("interest-error").textContent = "\ub9de\ucda4 \ube0c\ub9ac\ud551\uc744 \uc704\ud574 \uad00\uc2ec\uc0ac\ub97c \ud558\ub098 \uc774\uc0c1 \ucd94\uac00\ud574 \uc8fc\uc138\uc694."; input.setAttribute("aria-invalid", "true"); input.focus(); return; }
  const submit = document.getElementById("onboarding-submit"); submit.dataset.submitting = "true"; submit.disabled = true; submit.textContent = "\ube0c\ub9ac\ud551\uc744 \uc900\ube44\ud558\uace0 \uc788\uc5b4\uc694…";
  try {
    await api("/api/v1/onboarding", { method: "POST", body: JSON.stringify({ keywords: onboardingState.interests, goals: selectedGoals(), interest_type_preferences: onboardingState.informationTypePreferences, source_hints: sourceHints(), preferred_signal_count: 5 }) });
    sessionStorage.removeItem(onboardingState.draftKey); window.location.replace("/app");
  } catch (error) { document.getElementById("interest-error").textContent = error.message; document.getElementById("interest-input").setAttribute("aria-invalid", "true"); delete submit.dataset.submitting; submit.disabled = false; submit.textContent = "\ub9de\ucda4 \ube0c\ub9ac\ud551 \uc2dc\uc791\ud558\uae30"; }
}

function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]); }
function showFatal(error) { console.error(error); document.body.classList.remove("onboarding-page-pending"); document.querySelector(".onboarding-page-card").innerHTML = "<p>\uc628\ubcf4\ub529 \uc815\ubcf4\ub97c \ubd88\ub7ec\uc624\uc9c0 \ubabb\ud588\uc5b4\uc694. \uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574 \uc8fc\uc138\uc694.</p>"; }
