"""Display provenance from collected metadata, never from headline guesses."""
from urllib.parse import urlsplit


LABELS = {"hackernews": "Hacker News", "github": "GitHub", "youtube": "YouTube",
          "rss": "RSS", "official_ai_blogs": "공식 AI 블로그", "company_newsroom": "기업 뉴스룸",
          "mock": "샘플 데이터"}


def source_metadata(item):
    raw = item.get("raw_json") or {}
    source = item.get("source") or item.get("source_name") or ""
    url = item.get("url") or item.get("source_url") or ""
    context = raw.get("article_context") or {}
    if context.get("status") == "available" and context.get("url"):
        url = context["url"]
    try:
        host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        host = ""
    # Old synthetic rows may have lost raw_json; their reserved example URL is evidence.
    mock = bool(raw.get("mock")) or source == "mock" or host == "example.com"
    collector = LABELS.get(source, source or "수집 경로 미확인")
    if mock:
        label = "샘플 데이터"
    elif host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com"):
        label = "YouTube"
    elif host == "news.ycombinator.com":
        label = "Hacker News"
    elif host == "github.com":
        label = "GitHub"
    else:
        label = context.get("site_name") or raw.get("feed_title") or host or "출처 미확인"
    kind = "mock" if mock else raw.get("data_kind", "unknown")
    return {"source_display": label, "collected_via": collector,
            "data_kind": kind, "generation_mode": raw.get("generation_mode", "unknown"),
            "author": item.get("author") or "", "published_at": item.get("published_at") or ""}
