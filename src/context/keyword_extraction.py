import re
from collections import Counter
from typing import Dict, Iterable, List


EN_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "about", "your",
    "you", "are", "was", "were", "have", "has", "had", "not", "but", "can",
    "will", "our", "their", "they", "them", "what", "when", "where", "which",
    "how", "why", "all", "new", "more", "use", "using", "used", "via",
}
KO_STOPWORDS = {"그리고", "하지만", "있는", "없는", "으로", "에서", "에게", "관련", "대한", "이번", "최근"}


def normalize_keyword(keyword: str) -> str:
    keyword = re.sub(r"https?://\S+", " ", keyword or "")
    keyword = re.sub(r"[^\w가-힣\-\s]", " ", keyword, flags=re.UNICODE)
    return " ".join(keyword.lower().split())


def extract_keywords(text: str, max_keywords: int = 20) -> List[Dict[str, object]]:
    normalized = normalize_keyword(text)
    tokens = re.findall(r"[a-z0-9][a-z0-9\-]{2,}|[가-힣]{2,}", normalized)
    filtered = [
        token
        for token in tokens
        if token not in EN_STOPWORDS and token not in KO_STOPWORDS and not token.isdigit()
    ]
    if not filtered:
        return []
    counts = Counter(filtered)
    max_count = counts.most_common(1)[0][1]
    results = []
    for keyword, count in counts.most_common(max_keywords):
        results.append(
            {
                "keyword": keyword,
                "score": round(count / max_count, 4),
                "evidence": {"count": count},
            }
        )
    return results


def merge_keyword_scores(keyword_groups: Iterable[List[Dict[str, object]]], max_keywords: int = 30) -> List[Dict[str, object]]:
    scores: Dict[str, float] = {}
    evidence: Dict[str, Dict[str, object]] = {}
    for group in keyword_groups:
        for item in group:
            keyword = normalize_keyword(str(item.get("keyword", "")))
            if not keyword:
                continue
            scores[keyword] = scores.get(keyword, 0.0) + float(item.get("score", 0.0))
            evidence[keyword] = item.get("evidence", {})
    return [
        {"keyword": keyword, "score": round(score, 4), "evidence": evidence.get(keyword, {})}
        for keyword, score in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:max_keywords]
    ]


class KeywordExtractor:
    def extract(self, text: str, top_n: int = 10):
        return [(item["keyword"], item["score"]) for item in extract_keywords(text, max_keywords=top_n)]
