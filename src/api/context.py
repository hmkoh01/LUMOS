from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import CurrentUser, get_current_user, get_store
from src.storage.sqlite_store import DEFAULT_LOCAL_USER_ID, SQLiteStore

router = APIRouter(tags=["context"])


TREND_RECOMMENDATIONS = [
    ("AI 에이전트", ["agent", "ai agent", "에이전트"], "AI 기반 업무 자동화"),
    ("AI 업무 자동화", ["automation", "workflow", "자동화"], "반복 업무와 워크플로 자동화"),
    ("생성형 AI", ["llm", "generative ai", "model", "생성형 ai"], "생성형 AI와 모델 업데이트"),
    ("멀티모달 AI", ["multimodal", "vision", "video", "멀티모달"], "텍스트·이미지·영상 AI"),
    ("AI 검색", ["search", "retrieval", "rag", "검색"], "AI 검색과 정보 탐색"),
    ("AI 생산성 도구", ["productivity", "copilot", "assistant", "생산성"], "개인과 팀의 생산성 도구"),
    ("개발자 도구", ["developer tools", "github", "developer", "개발자"], "개발 생산성 도구"),
    ("오픈소스 AI", ["open source", "github", "huggingface", "오픈소스"], "오픈소스 AI 생태계"),
    ("스타트업 제품", ["startup", "product", "launch", "스타트업"], "신제품과 스타트업 움직임"),
    ("B2B SaaS", ["saas", "b2b", "enterprise"], "기업용 소프트웨어와 SaaS"),
    ("AI 마케팅 자동화", ["marketing", "marketer", "마케팅"], "마케팅 업무의 AI 활용"),
    ("콘텐츠 자동화", ["content", "creator", "콘텐츠"], "콘텐츠 제작과 배포 자동화"),
    ("데이터 분석 자동화", ["data", "analytics", "analysis", "데이터"], "데이터 분석 업무 자동화"),
    ("노코드 자동화", ["no-code", "nocode", "zapier", "노코드"], "비개발자용 업무 자동화"),
    ("AI 안전성", ["safety", "security", "evaluation", "안전성"], "AI 안전성과 평가"),
    ("제품 분석", ["product analytics", "metrics", "retention"], "제품 지표와 사용자 분석"),
    ("AI 코딩 도구", ["coding agent", "code assistant", "copilot", "AI 코딩"], "AI 기반 소프트웨어 개발"),
    ("LLM 평가", ["llm evaluation", "benchmark", "eval", "모델 평가"], "언어 모델의 품질 평가"),
    ("RAG", ["rag", "retrieval augmented", "벡터 검색"], "검색 결합형 AI 서비스"),
    ("AI 인프라", ["inference", "gpu", "serving", "AI 인프라"], "AI 모델 운영 인프라"),
    ("디자인 도구", ["design", "figma", "creative", "디자인"], "디자인과 창작 생산성"),
    ("사용자 리서치", ["user research", "customer interview", "사용자 조사"], "고객 이해와 제품 검증"),
    ("그로스", ["growth", "acquisition", "activation", "그로스"], "제품 성장과 사용자 확보"),
    ("개발자 경험", ["developer experience", "dx", "developer workflow"], "개발자 워크플로 개선"),
    ("데이터 엔지니어링", ["data engineering", "data pipeline", "warehouse"], "데이터 파이프라인 구축"),
    ("사이버 보안", ["cybersecurity", "security", "보안"], "제품과 데이터 보안"),
    ("핀테크", ["fintech", "payment", "payments", "금융 기술"], "금융 기술과 결제 서비스"),
    ("헬스케어 AI", ["healthcare ai", "medical ai", "헬스케어"], "의료와 건강 분야의 AI 활용"),
]

RECOMMENDATION_COUNT = 4


def _interest_recommendations(store: SQLiteStore, user_id: int = DEFAULT_LOCAL_USER_ID):
    """Return a full, fixed-size set of interest suggestions when candidates exist."""
    interests = store.get_interests(
        limit=None, include_muted=True, include_deleted=True, user_id=user_id
    )
    known = {str(item["keyword"]).strip().casefold() for item in interests}
    active_text = " ".join(item["keyword"] for item in interests if item.get("status") == "active").casefold()
    recent_text = " ".join(
        f"{item.get('title', '')} {item.get('summary', '')}" for item in store.get_recent_source_items(limit=80)
    ).casefold()
    suggestions = []
    for keyword, terms, topic in TREND_RECOMMENDATIONS:
        if keyword.casefold() in known:
            continue
        recent_match = any(term in recent_text for term in terms)
        personal_match = any(term in active_text for term in terms)
        score = (2 if recent_match else 0) + (1 if personal_match else 0)
        if recent_match:
            reason = f"최근 수집한 소스에서 {topic} 관련 표현이 보여 추천해요."
        elif personal_match:
            reason = f"현재 관심사와 연결되는 {topic} 주제라 추천해요."
        else:
            reason = f"최근 AI·제품 흐름에서 함께 살펴볼 만한 {topic} 주제예요."
        suggestions.append({"keyword": keyword, "reason": reason, "score": score})
    return sorted(suggestions, key=lambda item: (-item["score"], item["keyword"]))[:RECOMMENDATION_COUNT]


class InterestUpdate(BaseModel):
    weight: Optional[float] = Field(default=None, ge=0)
    category: Optional[str] = None
    status: Optional[str] = None


class InterestCreate(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)


@router.post("/interests")
def add_interest(
    request: InterestCreate,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    if not request.keyword.strip():
        raise HTTPException(status_code=422, detail="키워드를 입력해주세요.")
    return {"success": True, "interest": store.add_manual_interest(request.keyword, user_id=current_user.id)}


@router.get("/context/items")
def get_context_items(
    connector_type: Optional[str] = None,
    limit: int = 50,
    search: Optional[str] = None,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    return {
        "success": True,
        "items": store.get_context_items(
            connector_type=connector_type,
            limit=max(1, min(limit, 200)),
            search=search,
            user_id=current_user.id,
        ),
    }


@router.get("/interests")
def get_interests(
    status: Optional[str] = None,
    limit: int = 50,
    include_muted: bool = False,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    return {
        "success": True,
        "interests": store.get_interests(
            status=status,
            limit=max(1, min(limit, 500)),
            include_muted=include_muted,
            include_deleted=False,
            user_id=current_user.id,
        ),
    }


@router.get("/interests/recommendations")
def get_interest_recommendations(
    store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    return {"success": True, "recommendations": _interest_recommendations(store, current_user.id)}


@router.post("/interests/recommendations/{keyword}/dismiss")
def dismiss_interest_recommendation(
    keyword: str, store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    store.add_manual_interest(keyword, user_id=current_user.id)
    store.delete_interest(keyword, user_id=current_user.id)
    return {"success": True}


@router.put("/interests/{keyword}")
def update_interest(
    keyword: str,
    request: InterestUpdate,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    return {"success": True, "interest": store.update_interest(keyword, request.dict(exclude_none=True), user_id=current_user.id)}


@router.post("/interests/{keyword}/mute")
def mute_interest(
    keyword: str, store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    return {"success": True, "interest": store.mute_interest(keyword, user_id=current_user.id)}


@router.post("/interests/{keyword}/unmute")
def unmute_interest(
    keyword: str, store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    return {"success": True, "interest": store.unmute_interest(keyword, user_id=current_user.id)}


@router.delete("/interests/{keyword}")
def delete_interest(
    keyword: str, store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    return {"success": True, "deleted": store.delete_interest(keyword, user_id=current_user.id)}


@router.get("/interests/{keyword}/evidence")
def get_interest_evidence(
    keyword: str, store: SQLiteStore = Depends(get_store), current_user: CurrentUser = Depends(get_current_user)
):
    return {"success": True, "evidence": store.get_interest_evidence(keyword, user_id=current_user.id)}


@router.post("/context/prune-interests")
def prune_interests(
    max_keywords: Optional[int] = None,
    store: SQLiteStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
):
    limit = max_keywords or store.get_settings(user_id=current_user.id)["max_interest_keywords"]
    return {"success": True, "result": store.prune_interests(limit, user_id=current_user.id)}
