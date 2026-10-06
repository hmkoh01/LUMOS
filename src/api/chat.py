"""Source-grounded chat for the LUMOS web UI.

This intentionally answers only from signals already selected for the user;
it does not send personal context or source content to an external AI service.
"""
import re
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str


def _terms(value: str) -> set[str]:
    return {term.casefold() for term in re.findall(r"[\w가-힣]{2,}", value or "")}


@router.post("/chat")
def chat(
    request: ChatRequest,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    question = request.message.strip()
    if not question:
        return {"answer": "궁금한 점을 입력해 주세요.", "sources": []}
    signals = store.get_today_signals(include_archived=False, user_id=current_user.id)
    if not signals:
        return {"answer": "아직 추천한 원문이 없어요. 먼저 오늘의 소식을 받아오면 그 자료를 바탕으로 함께 볼 수 있어요.", "sources": []}
    query_terms = _terms(question)
    scored = []
    for signal in signals:
        text = " ".join(str(signal.get(key) or "") for key in (
            "display_title_ko", "headline_summary_ko", "detail_summary_ko", "original_title", "original_snippet", "summary"
        ))
        score = len(query_terms & _terms(text))
        scored.append((score, signal))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    matches = [signal for score, signal in scored if score > 0][:3] or [signal for _, signal in scored[:2]]
    sources = [{"title": signal.get("original_title") or signal.get("display_title_ko") or signal.get("title") or "추천 원문",
                "url": signal.get("source_url") or ""} for signal in matches]
    summaries = [str(signal.get("detail_summary_ko") or signal.get("headline_summary_ko") or signal.get("summary") or "").strip() for signal in matches]
    summaries = [summary for summary in summaries if summary]
    answer = "추천한 원문을 기준으로 보면, " + (" ".join(summaries[:2]) if summaries else "아래 원문에서 세부 내용을 확인할 수 있어요.")
    answer += " 아래 원문을 열어 맥락과 최신 내용을 함께 확인해 보세요."
    return {"answer": answer, "sources": sources}
