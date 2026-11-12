"""Static contract checks for the optional feedback-reason presentation."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "src" / "web" / "static" / "app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "src" / "web" / "static" / "styles.css").read_text(encoding="utf-8")


def test_dismiss_reason_is_optional_and_rendered_in_a_separate_panel():
    assert APP_JS.count("function showToastWithUndo") == 1
    assert APP_JS.count("function showFeedbackReasonPrompt") == 1
    assert "appendFeedbackReasonChoices" not in APP_JS
    assert "이 카드를 추천에서 제외했어요" in APP_JS
    assert "buildFeedbackReasonButton" in APP_JS
    assert "function showFeedbackReasonPanel" in APP_JS
    assert "function feedbackReasonSaveErrorMessage" in APP_JS
    assert "이유 저장 기능을 준비 중이에요" in APP_JS
    assert "error.message" not in APP_JS[APP_JS.index("function feedbackReasonSaveErrorMessage"):APP_JS.index("function showToastWithUndo")]
    for code in ("unrelated_subtopic", "too_technical", "already_known", "not_needed_now", "too_general"):
        assert code in APP_JS
    assert "/recommendation-reason" in APP_JS
    assert "supportsOptionalApi(" in APP_JS
    assert '"/api/v1/signals/{signal_id}/recommendation-reason", "put"' in APP_JS


def test_feedback_panel_has_compact_desktop_and_mobile_rules():
    assert ".feedback-reason-panel" in STYLES
    assert "width: min(350px, calc(100vw - 32px))" in STYLES
    assert "bottom: 104px" in STYLES
    assert "bottom: 184px" in STYLES
    assert "feedback-reason-open .chat-launcher" in STYLES
    assert 'document.body.classList.add("feedback-reason-open")' in APP_JS
    assert "@media (max-width: 560px)" in STYLES
    assert "border-radius: 20px 20px 0 0" in STYLES
    assert ".toast-actions" in STYLES


def test_feedback_assets_use_a_new_cache_key():
    index = (ROOT / "src" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    assert "/static/app.js?v=20261112-feedback-v1" in index


def test_learning_management_removes_the_user_toggle_without_claiming_live_ranking():
    assert "내 평가 경향" in APP_JS
    assert 'data-learning-action="toggle"' not in APP_JS
    assert "피드백 기반 선호 기록 사용" not in APP_JS


def test_interest_cards_keep_unsaved_changes_local_until_the_existing_apis_save_them():
    assert "interestDrafts" in APP_JS
    assert "function queueInterestAutosave" in APP_JS
    assert "data-interest-action=\"save\"" not in APP_JS
    assert "data-interest-action=\"cancel\"" not in APP_JS
    assert "data-interest-action=\"toggle-types\"" in APP_JS
    assert "data-interest-action=\"importance\"" in APP_JS


def test_optional_backend_features_do_not_break_core_interest_loading():
    assert "async function supportsOptionalApi" in APP_JS
    assert 'fetch("/openapi.json", { cache: "no-store" })' in APP_JS
    assert 'supportsOptionalApi("/api/v1/profile/feedback-learning")' in APP_JS
    assert "supported === false ? null" in APP_JS
