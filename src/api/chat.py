"""LUMOS Assistant API — RAG-based chat grounded in the user's own signals."""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.assistant.service import AssistantService
from src.storage.sqlite_store import SQLiteStore

router = APIRouter(tags=["assistant"])


# ── request / response models ─────────────────────────────────────────────────

class AssistantChatRequest(BaseModel):
    message: str
    period: str = "week"                      # today | week | month | all
    selected_signal_id: Optional[int] = None
    conversation_id: Optional[int] = None


class CitationOut(BaseModel):
    signal_id: int
    title: str
    source_name: str
    url: str
    published_at: Optional[str] = None


class AssistantChatResponse(BaseModel):
    success: bool = True
    answer: str
    conversation_id: int
    message_id: int
    sources: List[CitationOut]


class ConversationOut(BaseModel):
    id: int
    title: str
    period: str
    message_count: int
    created_at: str
    updated_at: str


class ConversationMessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: List[CitationOut]
    created_at: str


# ── dependency ────────────────────────────────────────────────────────────────

def get_assistant_service(store: SQLiteStore = Depends(get_store)) -> AssistantService:
    return AssistantService(store=store)


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/assistant/chat", response_model=AssistantChatResponse)
def assistant_chat(
    request: AssistantChatRequest,
    service: AssistantService = Depends(get_assistant_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    message = request.message.strip()
    if not message:
        return AssistantChatResponse(
            answer="궁금한 점을 입력해 주세요.",
            conversation_id=0,
            message_id=0,
            sources=[],
        )

    period = request.period if request.period in {"today", "week", "month", "all"} else "week"

    result = service.chat(
        user_id=current_user.id,
        message=message,
        period=period,
        selected_signal_id=request.selected_signal_id,
        conversation_id=request.conversation_id,
    )

    return AssistantChatResponse(
        answer=result.answer,
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        sources=[
            CitationOut(
                signal_id=c.signal_id,
                title=c.title,
                source_name=c.source_name,
                url=c.url,
                published_at=c.published_at,
            )
            for c in result.sources
        ],
    )


@router.get("/assistant/conversations")
def list_conversations(
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    convs = store.list_conversations(user_id=current_user.id)
    return {
        "success": True,
        "conversations": [
            ConversationOut(
                id=c["id"],
                title=c["title"],
                period=c["period"],
                message_count=c.get("message_count", 0),
                created_at=c["created_at"],
                updated_at=c["updated_at"],
            ).model_dump()
            for c in convs
        ],
    }


@router.get("/assistant/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: int,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    import json as _json
    msgs = store.get_conversation_messages(conversation_id, current_user.id)
    out = []
    for m in msgs:
        try:
            sources_raw = _json.loads(m.get("sources_json") or "[]")
        except (_json.JSONDecodeError, TypeError):
            sources_raw = []
        out.append(
            ConversationMessageOut(
                id=m["id"],
                role=m["role"],
                content=m["content"],
                sources=[
                    CitationOut(
                        signal_id=s.get("signal_id", 0),
                        title=s.get("title", ""),
                        source_name=s.get("source_name", ""),
                        url=s.get("url", ""),
                        published_at=s.get("published_at"),
                    )
                    for s in sources_raw
                ],
                created_at=m["created_at"],
            ).model_dump()
        )
    return {"success": True, "messages": out}


@router.delete("/assistant/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    deleted = store.delete_conversation(conversation_id, current_user.id)
    return {"success": deleted}


# ── legacy /chat endpoint (kept for backward compat) ──────────────────────────

class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
def chat_legacy(
    request: ChatRequest,
    service: AssistantService = Depends(get_assistant_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Backward-compatible endpoint — delegates to AssistantService."""
    message = request.message.strip()
    if not message:
        return {"answer": "궁금한 점을 입력해 주세요.", "sources": []}
    result = service.chat(user_id=current_user.id, message=message, period="week")
    return {
        "answer": result.answer,
        "sources": [{"title": c.title, "url": c.url} for c in result.sources],
    }
