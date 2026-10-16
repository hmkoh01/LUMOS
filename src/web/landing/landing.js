document.addEventListener("click", (event) => {
  const copyTarget = event.target.closest("[data-copy-template]");
  if (copyTarget) {
    event.preventDefault();
    copyTemplate(copyTarget);
    return;
  }

  const target = event.target.closest("[data-info]");
  if (!target) return;
  event.preventDefault();
  const message = target.dataset.info || "현재는 베타 준비 중입니다.";
  showLandingToast(message);
});

function copyTemplate(button) {
  const targetId = button.dataset.templateTarget;
  const template = targetId ? document.getElementById(targetId) : null;
  if (!template) {
    showLandingToast("복사할 신청 질문을 찾지 못했어요.");
    return;
  }
  const text = template.value || template.textContent || "";
  copyText(text.trim())
    .then(() => showLandingToast("신청 질문을 복사했어요. 이메일에 붙여넣어 주세요."))
    .catch(() => showLandingToast("복사하지 못했어요. 질문을 직접 선택해서 복사해 주세요."));
}

function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  return new Promise((resolve, reject) => {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    try {
      const ok = document.execCommand("copy");
      document.body.removeChild(textarea);
      ok ? resolve() : reject(new Error("copy failed"));
    } catch (error) {
      document.body.removeChild(textarea);
      reject(error);
    }
  });
}

function showLandingToast(message) {
  let toast = document.getElementById("landing-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "landing-toast";
    toast.style.position = "fixed";
    toast.style.left = "50%";
    toast.style.bottom = "24px";
    toast.style.transform = "translateX(-50%)";
    toast.style.padding = "12px 16px";
    toast.style.borderRadius = "14px";
    toast.style.background = "#111827";
    toast.style.color = "#fff";
    toast.style.boxShadow = "0 12px 28px rgba(15, 23, 42, 0.24)";
    toast.style.zIndex = "100";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.style.opacity = "1";
  window.clearTimeout(window.__landingToastTimer);
  window.__landingToastTimer = window.setTimeout(() => {
    toast.style.opacity = "0";
  }, 2600);
}

document.addEventListener("DOMContentLoaded", () => {
  renderLandingAccount().catch(() => {});
});

async function renderLandingAccount() {
  if (typeof authClient === "undefined") return;
  await authClient.init();
  if (!authClient.isAuthMode()) return;
  const user = (await authClient.getSession())?.user;
  if (!user) return;
  const actions = document.getElementById("landing-auth-actions");
  if (!actions) return;
  const name = user.user_metadata?.full_name || user.user_metadata?.name || user.email || "내 계정";
  const initial = String(name).trim().slice(0, 1).toUpperCase();
  const safeName = escapeLandingHtml(name);
  actions.innerHTML = `<div class="landing-account-menu">
    <button class="landing-account-trigger" type="button" aria-expanded="false" aria-controls="landing-account-popover">
      <span class="landing-avatar" aria-hidden="true">${escapeLandingHtml(initial)}</span><span class="landing-account-name">${safeName}</span>
    </button>
    <div class="landing-account-popover" id="landing-account-popover" hidden>
      <div class="landing-account-summary"><strong>${safeName}</strong><small>${escapeLandingHtml(user.email || "")}</small></div>
      <a href="/app#settings">내 계정 설정</a>
      <button type="button" data-landing-logout>로그아웃</button>
    </div>
  </div><a class="landing-briefing-button" href="/app">내 브리핑 <span aria-hidden="true">→</span></a>`;
  const trigger = actions.querySelector(".landing-account-trigger");
  const popover = actions.querySelector(".landing-account-popover");
  trigger?.addEventListener("click", () => {
    const opening = popover.hidden;
    popover.hidden = !opening;
    trigger.setAttribute("aria-expanded", String(opening));
  });
  document.addEventListener("click", (event) => {
    if (!actions.contains(event.target)) {
      popover.hidden = true;
      trigger?.setAttribute("aria-expanded", "false");
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      popover.hidden = true;
      trigger?.setAttribute("aria-expanded", "false");
      trigger?.focus();
    }
  });
  actions.querySelector("[data-landing-logout]")?.addEventListener("click", async () => {
    await authClient.signOut();
    window.location.assign("/");
  });
}

function escapeLandingHtml(value) {
  return String(value || "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}
