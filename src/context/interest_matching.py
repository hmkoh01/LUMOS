"""Conservative lexical matching; aliases are not a general semantic model."""
import re
import unicodedata


ALIASES = (
    ("마케팅", "마케터", "marketing", "marketer", "marketers"),
    ("데이터 마케터", "데이터 마케팅", "데이터 기반 마케팅", "마케팅 데이터 분석", "data driven marketing", "marketing analytics", "marketing attribution", "data marketing"),
    ("퍼포먼스 마케터", "퍼포먼스 마케팅", "performance marketing", "conversion optimization"),
    ("콘텐츠 기획자", "콘텐츠 기획", "콘텐츠 전략", "content strategy", "content planning", "content strategist", "content marketing"),
    ("콘텐츠", "컨텐츠", "content creation", "content marketing", "creator economy"),
    ("인공지능", "ai", "artificial intelligence"),
    ("생성형 ai", "생성형 인공지능", "generative ai"),
    ("취업", "채용", "recruitment", "hiring", "job search"),
    ("스타트업", "startup", "startups"),
    ("자동화", "automation"),
    ("추천 시스템", "recommendation system", "recommender system"),
)

# Words people use to declare an interest that carry no topical meaning on their own.
# Filtered out before a keyword phrase is used for matching, both from fixed English
# connectors and from common Korean filler/deictic words.
STOPWORDS = {
    "a", "the", "of", "for", "and", "driven",
    "요즘", "최근", "요새", "진짜", "정말", "좀", "약간", "관련", "분야", "부분", "쪽", "등",
}

# Conversational scaffolding people type when they mean "I'm interested in <topic>"
# rather than typing the bare topic itself, e.g. "생성형 AI 에이전트에 관심이 많아요"
# or "스타트업 투자 소식 알려주세요". Stripped repeatedly (innermost scaffolding first)
# so a newly typed sentence reduces to the same core phrase a bare keyword would.
_LEADING_PATTERNS = (
    r"^(?:저는|나는|제가|저희는|우리는)\s*",
)

_TRAILING_PATTERNS = (
    r"(?:에|에는|에도)?\s*관심(?:이|을)?\s*(?:많아요|많습니다|있어요|있습니다|가져요|가요|생겼어요|둬요|둡니다)\s*[.!~]*$",
    r"(?:을|를)?\s*(?:알고\s*싶어요|알고싶어요|궁금해요|궁금합니다|보고\s*싶어요|보고싶어요|받고\s*싶어요|받고싶어요|"
    r"추적하고\s*싶어요|추적하고싶어요|따라가고\s*싶어요|팔로우하고\s*싶어요|챙겨보고\s*싶어요)\s*[.!~]*$",
    r"(?:관련|에\s*대한|와\s*관련된)?\s*(?:소식|뉴스|정보|트렌드|업데이트)\s*(?:을|를)?\s*"
    r"(?:알려주세요|주세요|보여주세요|보고싶어요|받고싶어요)?\s*[.!~]*$",
    r"(?:에|에는)\s*대해\s*(?:알고\s*싶어요|알려주세요|다뤄주세요)?\s*[.!~]*$",
    r"[.!?~]+$",
)


def normalize(text):
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", str(text)).casefold()))


def _strip_declaration_scaffolding(text):
    """Reduce a naturally-typed interest sentence to its core topic phrase."""
    cleaned = str(text or "").strip()
    for pattern in _LEADING_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned).strip()
    changed = True
    while changed and cleaned:
        changed = False
        for pattern in _TRAILING_PATTERNS:
            stripped = re.sub(pattern, "", cleaned).strip()
            if stripped != cleaned:
                cleaned = stripped
                changed = True
    return cleaned


def interest_terms(keyword):
    core = _strip_declaration_scaffolding(keyword)
    normalized = normalize(core) or normalize(keyword)
    for aliases in ALIASES:
        if normalized.replace(" ", "") in [normalize(alias).replace(" ", "") for alias in aliases]:
            return list(dict.fromkeys([normalized, *map(normalize, aliases)]))
    return [normalized] if normalized else []


def _meaningful_words(term):
    return [word for word in term.split() if word not in STOPWORDS and len(word) > 1]


def matches_interest(text, keyword):
    text = normalize(text)
    for term in interest_terms(keyword):
        if re.search(r"[가-힣]", term) and term.replace(" ", "") in text.replace(" ", ""):
            return True
        # English word boundaries prevent AI from matching "said" or "retail".
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text):
            return True
        words = _meaningful_words(term)
        if len(words) >= 2 and all(re.fullmatch(r"[a-z]+", word) for word in words):
            # Compound English interests require every meaningful word, even in a
            # different order, within a short window.
            tokens = text.split()
            if any(all(word in tokens[index:index + 10] for word in words) for index in range(len(tokens))):
                return True
        elif len(words) >= 2 and any(re.search(r"[가-힣]", word) for word in words):
            # A naturally-typed Korean interest ("생성형 AI 에이전트 트렌드") rarely
            # reappears verbatim in an article, so require every meaningful word to
            # be present somewhere in the text rather than an exact contiguous phrase.
            compact_text = text.replace(" ", "")
            if all(word in compact_text for word in words):
                return True
    return False
