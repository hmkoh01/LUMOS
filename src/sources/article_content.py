"""Bounded public-page reading. No model, login, cookies or private context uploads."""
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx


_TITLE_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "about", "your", "our", "you", "new",
    "article", "articles", "post", "posts", "blog", "home", "menu", "search", "author", "profile",
    "글", "기사", "작성자", "프로필", "메뉴", "홈", "더보기",
}
_TITLE_NOISE = re.compile(r"^(?:by\s+.+|author|writer|profile|articles?|posts?|blog|home|menu|search|작성자|프로필|기사 목록)$", re.I)


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.meta = {}
        self.blocks = []
        self.current = None
        self.page_title = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            if key:
                self.meta[key.lower()] = attrs.get("content", "")
        if tag in {"meta", "link", "img", "input", "br", "hr", "source", "wbr"}:
            return
        self.stack.append(tag)
        if tag in {"title", "h1", "h2", "p", "li"} and not self._ignored():
            self._flush()
            self.current = [tag, [], "article" in self.stack or "main" in self.stack]

    def handle_endtag(self, tag):
        if self.current and tag == self.current[0]:
            self._flush()
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            self.stack = self.stack[:index]

    def handle_data(self, data):
        if self.current and not self._ignored():
            self.current[1].append(data)

    def _ignored(self):
        return any(tag in self.stack for tag in {"script", "style", "nav", "footer", "aside", "form", "button", "noscript"})

    def _flush(self):
        if self.current:
            tag, pieces, scoped = self.current
            text = re.sub(r"\s+", " ", "".join(pieces)).strip()
            if tag == "title":
                self.page_title = text
            elif text:
                self.blocks.append((tag, text, scoped))
        self.current = None

    def result(self, url, fallback_title=""):
        self._flush()
        paragraphs = [text for tag, text, scoped in self.blocks if tag in {"p", "li"} and scoped and len(text) >= 45]
        if not paragraphs:
            paragraphs = [text for tag, text, _ in self.blocks if tag in {"p", "li"} and len(text) >= 45]
        paragraphs = list(dict.fromkeys(paragraphs))
        description = self.meta.get("og:description") or self.meta.get("description", "")
        title, title_basis = choose_article_title(
            headings=[text for tag, text, _ in self.blocks if tag == "h1"],
            og_title=self.meta.get("og:title", ""),
            page_title=self.page_title,
            fallback_title=fallback_title,
            description=description,
            body="\n".join(paragraphs),
            author=self.meta.get("author") or self.meta.get("article:author", ""),
            site_name=self.meta.get("og:site_name", ""),
        )
        return {"status": "available" if paragraphs or description else "metadata_only",
                "url": url, "title": title, "title_basis": title_basis,
                "site_name": self.meta.get("og:site_name", ""), "description": description[:1200],
                "text": "\n".join(paragraphs)[:12000], "basis": "public_page"}


def choose_article_title(headings, og_title, page_title, description, body, author="", site_name="", fallback_title=""):
    """Choose a content title, not merely the first structural page heading.

    Public pages frequently use an ``h1`` for a person, a category, or a site
    chrome. Candidate titles are therefore compared with the available article
    description/body and rejected when they look like a byline or navigation.
    """
    candidates = [("h1", text) for text in headings]
    candidates.extend([("og_title", og_title), ("page_title", page_title)])
    # The collector's title is useful evidence too.  In particular, some
    # newsletter platforms use their publication name as the h1 while the
    # feed/HN item contains the actual article headline.
    candidates.append(("source_title", fallback_title))
    author_key = _title_key(author)
    content_words = set(_title_words(f"{description} {body}"))
    best = (float("-inf"), "", "fallback")
    for source, value in candidates:
        title = _clean_title_candidate(value, site_name)
        if not title:
            continue
        key = _title_key(title)
        if not key or _TITLE_NOISE.fullmatch(title) or (author_key and key == author_key):
            continue
        words = _title_words(title)
        if not words:
            continue
        overlap = len(set(words) & content_words)
        score = {"h1": 12, "og_title": 10, "page_title": 4, "source_title": 9}.get(source, 0)
        score += min(18, overlap * 4)
        score += 4 if 12 <= len(title) <= 150 else -5
        # A capitalized personal name is only acceptable when the page text
        # clearly supports it as the subject; otherwise prefer a content title.
        if _looks_like_person_name(title) and overlap < 2:
            continue
        if source == "page_title" and site_name and site_name.casefold() in title.casefold():
            score -= 5
        if score > best[0]:
            best = (score, title, source)
    if best[1]:
        return best[1], best[2]
    content_title = _content_fallback_title(description, body)
    if content_title:
        return content_title, "content_sentence"
    return _clean_title_candidate(og_title or page_title or (headings[0] if headings else ""), site_name), "fallback"


def _clean_title_candidate(value, site_name):
    title = re.sub(r"\s+", " ", str(value or "")).strip()
    if site_name:
        title = re.sub(rf"\s*[|\-–—]\s*{re.escape(site_name)}\s*$", "", title, flags=re.I).strip()
    return title[:300]


def _title_key(value):
    return " ".join(_title_words(value))


def _title_words(value):
    return [word.casefold() for word in re.findall(r"[A-Za-z0-9가-힣]{2,}", str(value or ""))
            if word.casefold() not in _TITLE_STOPWORDS]


def _looks_like_person_name(value):
    return bool(re.fullmatch(r"(?:[A-Z][a-z]+\s+){1,3}[A-Z][a-z]+", value.strip()))


def _content_fallback_title(description, body):
    """Use an explicit opening proposition only when all page title candidates fail."""
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", f"{description} {body}"):
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if 20 <= len(sentence) <= 180 and not _TITLE_NOISE.fullmatch(sentence):
            return sentence
    return ""


def parse_article(html, url, fallback_title=""):
    parser = ArticleParser()
    parser.feed(html)
    return parser.result(url, fallback_title=fallback_title)


def validate_public_url(url):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Not a public article URL")
    if parts.port not in {None, 80, 443}:
        raise ValueError("Non-standard article port")
    addresses = socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("Private address is not an article source")


def fetch_article(url, fallback_title=""):
    try:
        with httpx.Client(timeout=6.0, follow_redirects=False, headers={"User-Agent": "LUMOS/0.1 article-preview"}) as client:
            for _ in range(4):
                validate_public_url(url)
                with client.stream("GET", url) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    response.raise_for_status()
                    if "html" not in response.headers.get("content-type", "").lower():
                        return {"status": "unavailable", "basis": "unsupported_format"}
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 600_000:
                            return {"status": "unavailable", "basis": "page_too_large"}
                        chunks.append(chunk)
                    return parse_article(
                        b"".join(chunks).decode(response.encoding or "utf-8", errors="replace"),
                        url,
                        fallback_title=fallback_title,
                    )
    except (httpx.HTTPError, ValueError, OSError):
        pass
    return {"status": "unavailable", "basis": "fetch_failed"}


def article_context(item, allow_fetch=True):
    raw = item.get("raw_json") or {}
    cached = raw.get("article_context")
    if cached:
        return cached
    url = item.get("url") or item.get("source_url") or ""
    host = (urlsplit(url).hostname or "").lower()
    if raw.get("mock") or raw.get("data_kind") == "mock" or host == "example.com" or item.get("source") == "mock":
        return {"status": "sample", "basis": "sample", "text": item.get("summary", "")}
    if host == "news.ycombinator.com" and raw.get("search_text"):
        return {"status": "available", "basis": "post_text", "text": raw["search_text"][:12000], "url": url}
    # Only registered collectors' public source items may initiate article requests.
    if allow_fetch and item.get("source") in {"hackernews", "rss", "github", "official_ai_blogs", "company_newsroom"}:
        return fetch_article(url, fallback_title=item.get("title", ""))
    return {"status": "unavailable", "basis": "collected_description"}
