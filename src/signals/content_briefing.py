"""Evidence selection and conservative Korean headlines; no generative service."""
import re
from html import unescape

# Words that are capitalized only because they start a sentence, or that are too
# generic to ever be a real named entity worth pointing a reader toward.
_ENTITY_STOPWORDS = {
    "the", "this", "that", "these", "those", "it", "they", "we", "you", "i", "he", "she",
    "a", "an", "in", "on", "at", "for", "with", "and", "but", "or", "so", "if", "show",
    "ask", "tell", "launch", "hn", "every", "some", "many", "most", "new", "now", "today",
    "how", "what", "when", "where", "why", "who", "our", "your", "their", "his", "her",
    "its", "not", "just", "all", "there", "here", "one", "two", "three", "also", "is",
    "are", "was", "were", "be", "been", "will", "would", "can", "could", "do", "does",
}


def extract_related_mentions(text, exclude):
    """Find other named entities mentioned in the article (products, companies, tools)
    so readers get a concrete next topic instead of a generic templated suggestion."""
    candidates = re.findall(
        r"\b[A-Z][A-Za-z0-9]*(?:\.[A-Za-z]+)?(?:\s+[A-Z][A-Za-z0-9]+){0,2}\b", text or "")
    seen, mentions = set(), []
    for candidate in candidates:
        words = candidate.split()
        if all(word.lower() in _ENTITY_STOPWORDS for word in words):
            continue
        key = candidate.lower()
        if key in exclude or key in seen or len(candidate) < 3:
            continue
        seen.add(key)
        mentions.append(candidate)
    return mentions


def plain(text):
    return " ".join(re.sub(r"<[^>]*>", " ", unescape(str(text or ""))).split())


def sentences(text):
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text)
            if len(part.strip()) >= 25]


def select_evidence(title, description, text):
    """Select complete content statements; discard preambles, ads and rhetorical leads."""
    terms = set(re.findall(r"[a-z]{3,}", title.lower())) - {
        "ask", "show", "the", "and", "for", "with", "that", "this", "how", "you", "your", "our", "just"}
    candidates = list(dict.fromkeys(sentences(description) + sentences(text)))
    ranked = []
    for index, sentence in enumerate(candidates):
        if len(sentence) > 480 or sentence.endswith(":"):
            continue  # Do not translate a mid-sentence truncation as a complete statement.
        lower = sentence.lower()
        if re.search(r"^(just to preface|admittedly|anyways|i'm \d|i've (always|been obsessed)|bring two|sign up|subscribe|\d+ days free)", lower):
            continue
        if re.search(r"(how are you all|need a shower|feel really gross|before (lunch|you have made tea)|free trial|book a call)", lower):
            continue
        words = set(re.findall(r"[a-z]{3,}", lower))
        score = len(words & terms) * 1.5 + max(0, 1.2 - index * .04)
        score += 3 if re.search(r"\b(includes?|built in|automated|agent|monitoring|invoices|working on|develop|intends|approves?|rules|records?|tools)\b", lower) else 0
        score += 2 if len(sentence) > 100 and re.search(r"[,;:]", sentence) else 0
        score += 5 if re.search(r"\b(person|human)\b.*\b(approves?|approval|reviews?)\b", lower) else 0
        score -= 4 if re.search(r"^(starting today|every app)", lower) and len(sentence) < 100 else 0
        score -= 4 if re.search(r"(i just had|career|years old|i feel|scares me|hobbies|you built an app|your team sees)", lower) else 0
        ranked.append((score, index, sentence, words))
    selected, word_sets = [], []
    for _, index, sentence, words in sorted(ranked, key=lambda row: (-row[0], row[1])):
        if any(len(words & previous) / max(1, min(len(words), len(previous))) > .78 for previous in word_sets):
            continue
        selected.append((index, sentence))
        word_sets.append(words)
        if len(selected) == 3:
            break
    # Preserve the source's exposition order in the explanation.
    return [sentence for _, sentence in sorted(selected)]


def content_headline(title, description, text, site_name, translate):
    """Templates match explicit propositions, never infer facts from interest keywords."""
    combined = plain(description + " " + text)
    # A common release statement: every app on a named platform includes X.
    match = re.search(r"Every app on ([\w .-]{1,50}?) (?:now )?(?:comes with|includes) ([\w -]{3,60}?) built in", combined, re.I)
    if match:
        feature = translate(match[2].strip())
        if feature:
            return f"{match[1].strip()}, 모든 앱에 {feature} 기본 제공", match[0]
    # First-party operations descriptions: use the publisher only when the text says 'our company'.
    match = re.search(r"An AI agent (?:does|handles) the routine work of running our company", combined, re.I)
    if match:
        return f"{site_name + ', ' if site_name else ''}AI 에이전트로 회사의 반복 업무 처리", match[0]
    # Extract the described feature instead of translating a forum author's rhetorical headline.
    match = re.search(r"(?:working on|building|developing) a feature that (?:does |provides |handles )?([^.!?]{10,180})", combined, re.I)
    if match:
        feature = re.split(r",\s*(?:so|and)\b", match[1], maxsplit=1, flags=re.I)[0].strip()
        translated = translate(feature)
        if translated:
            concerned = re.search(r"\b(scared|scares|worried|worry|concern|gross)\b", combined, re.I)
            return f"{translated} 기능 개발{'에 대한 고민' if concerned else ' 사례'}", match[0]
    # Prefer the publisher's descriptive headline over an aggregator's submitted title.
    return "", ""


def shorten_headline(text, limit=52):
    """Keep the source headline scannable without adding a new claim."""
    headline = plain(text).rstrip(".?!")
    if len(headline) <= limit:
        return headline
    cut = headline.rfind(" ", 0, limit + 1)
    if cut >= max(12, limit // 2):
        return headline[:cut].rstrip(" ,:;-") + "…"
    return headline[:limit].rstrip() + "…"


def make_content_briefing(title, summary, context, translate):
    text = context.get("text", "")
    description = plain(context.get("description") or summary)
    actual_title = plain(context.get("title") or title)
    evidence = select_evidence(actual_title, description, text)
    headline, headline_evidence = content_headline(actual_title, description, text, context.get("site_name", ""), translate)
    translated = [translate(sentence) or sentence for sentence in evidence]
    headline_summary = ""
    if not headline and evidence:
        # Keep the source's article title as the headline. The fuller statement
        # belongs below it, where readers can scan it as a short summary.
        headline = shorten_headline(translate(actual_title) or actual_title)
        headline_summary = translated[0]
        headline_evidence = evidence[0]
    exclude = {word.lower() for word in re.findall(r"[A-Za-z]+", actual_title)}
    site_name = plain(context.get("site_name") or "")
    if site_name:
        exclude.add(site_name.lower())
    related_mentions = extract_related_mentions(f"{description} {text}", exclude)
    return {"headline": headline, "headline_summary": headline_summary,
            "evidence": evidence, "translated_evidence": translated,
            "headline_evidence": headline_evidence, "article_title": actual_title,
            "related_mentions": related_mentions}
