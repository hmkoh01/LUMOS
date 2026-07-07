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
