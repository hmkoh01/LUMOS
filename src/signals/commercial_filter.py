"""Conservative exclusion of commercial landing and subscription pages."""
import re
from urllib.parse import urlsplit


# Path matches are deliberately narrow: a news article may discuss a product,
# but a pricing or checkout route is not itself a signal readers should study.
COMMERCIAL_PATH_MARKERS = (
    "/pricing", "/plans", "/checkout", "/cart", "/subscribe", "/subscription",
    "/billing", "/upgrade", "/buy", "/purchase", "/sign-up", "/signup",
)
COMMERCIAL_MARKERS = (
    "start free trial", "free trial", "buy now", "add to cart", "choose your plan",
    "pricing plans", "monthly subscription", "subscribe now", "subscription plan",
    "무료 체험", "구독하기", "지금 구매", "장바구니", "요금제 선택", "월 구독",
)
COMMERCIAL_CONTENT_MARKERS = (
    "pricing", "price", "free trial", "book a call", "get started", "sign up",
    "starter", "enterprise", "per month", "/month", "monthly", "annual billing",
    "ìš”ê¸ˆ", "êµ¬ë…", "ë¬´ë£Œ ì²´í—˜", "ë¬´ë£Œ ì‹œìž‘", "ì›” ê²°ì œ",
)
EDITORIAL_MARKERS = (
    "announces", "announced", "launches", "launched", "released", "report", "analysis", "review",
    "발표", "출시", "보도", "분석", "리뷰", "인터뷰",
)


def commercial_page_reason(item):
    """Return an exclusion reason for a sales page, otherwise an empty string."""
    url = str(item.get("url") or item.get("source_url") or "")
    source = str(item.get("source") or item.get("source_name") or "").casefold()
    try:
        path = urlsplit(url).path.casefold().rstrip("/")
    except ValueError:
        path = ""
    if source != "youtube" and any(marker in path for marker in COMMERCIAL_PATH_MARKERS):
        return "commercial_url"

    # A Show HN post whose outbound link is a service's bare home page is a
    # launch/marketing landing page, not an article to read.  Project docs and
    # repository links remain eligible because they use a non-root path.
    title = str(item.get("title") or "").casefold()
    if source == "hackernews" and title.startswith("show hn:") and path in {"", "/"}:
        return "commercial_show_hn_landing"

    # Video descriptions frequently include a creator's generic subscribe CTA;
    # that does not make the video itself a commercial product page.
    if source == "youtube":
        return ""
    text = " ".join(str(item.get(key) or "") for key in ("title", "summary")).casefold()
    if any(marker in text for marker in EDITORIAL_MARKERS):
        return ""
    marker_count = sum(marker in text for marker in COMMERCIAL_MARKERS)
    return "commercial_cta" if marker_count >= 2 else ""


def commercial_context_reason(item, context):
    """Detect a sales landing page after its public body has been read.

    A collector often only sees a link title (not the destination page's
    pricing section), so this is intentionally a second, content-aware gate.
    Editorial reporting remains allowed when its title/description clearly
    identifies it as a report, launch announcement, or review.
    """
    if commercial_page_reason(item):
        return commercial_page_reason(item)
    if str(item.get("source") or item.get("source_name") or "").casefold() == "youtube":
        return ""
    if not isinstance(context, dict) or context.get("status") not in {"available", "metadata_only"}:
        return ""
    lead = " ".join(str(item.get(key) or "") for key in ("title", "summary", "description")).casefold()
    if any(marker in lead for marker in EDITORIAL_MARKERS):
        return ""
    text = " ".join(str(context.get(key) or "") for key in ("title", "description", "text")).casefold()
    marker_count = sum(marker in text for marker in COMMERCIAL_CONTENT_MARKERS)
    return "commercial_page_content" if marker_count >= 2 else ""
