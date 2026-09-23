"""Best-effort English -> Korean translation for article titles and summaries.

Uses the free MyMemory translation API (no key required). Network or quota
failures degrade gracefully: callers get None back and fall back to the
original text, so a slow or unreachable translation service never blocks
signal generation.
"""
import re
from typing import Optional

import httpx

_TRANSLATE_URL = "https://api.mymemory.translated.net/get"
_MAX_CHARS = 480  # MyMemory's free-tier limit is ~500 characters per request.
_cache: dict = {}

# Generic MT frequently mistranslates recurring tech jargon in this app's HN/GitHub
# content (e.g. "AI agent" -> "AI 상담원", a customer-support rep, not a software
# agent). Correct the handful of terms that show up often enough to matter.
# "상담원" ends in a consonant (받침) and "에이전트" doesn't, so any particle
# attached by the original translation is remapped too (과 -> 와, 이 -> 가, ...).
_AGENT_MISTRANSLATION = re.compile(r"AI\s*상담원(이|가|은|는|을|를|과|와)?")
_PARTICLE_AFTER_VOWEL = {"이": "가", "은": "는", "을": "를", "과": "와"}


def _apply_jargon_corrections(text: str) -> str:
    def _fix_agent(match: "re.Match") -> str:
        particle = match.group(1) or ""
        return "AI 에이전트" + _PARTICLE_AFTER_VOWEL.get(particle, particle)

    return _AGENT_MISTRANSLATION.sub(_fix_agent, text)


def translate_to_korean(text: str, timeout: float = 4.0) -> Optional[str]:
    text = (text or "").strip()
    if not text:
        return None
    text = text[:_MAX_CHARS]
    if text in _cache:
        return _cache[text]
    try:
        response = httpx.get(
            _TRANSLATE_URL,
            params={"q": text, "langpair": "en|ko"},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        translated = ((data.get("responseData") or {}).get("translatedText") or "").strip()
        if not translated or translated.lower() == text.lower():
            return None
        translated = _apply_jargon_corrections(translated)
        _cache[text] = translated
        return translated
    except Exception:
        return None
