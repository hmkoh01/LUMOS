"""Run the offline briefing quality evaluation — v2.

Usage:
    python -m tests.eval.run_evaluation

Does NOT touch production data, user settings, or live sources.
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.signals.korean_briefing import build_korean_briefing
from tests.eval.dataset import (
    EVAL_ITEMS, dataset_summary, get_multi_profile_pairs,
)
from tests.eval.briefing_evaluator import evaluate_batch


def generate_briefing(item: dict, role: str = "예비 창업자") -> dict:
    return build_korean_briefing(
        title=item["title"],
        summary=item["summary"],
        source=item["source"],
        category=_infer_category(item),
        matched_keywords=item.get("matched_keywords", []),
        role=role,
        action_hint="",
        content_context=None,
    )


def _infer_category(item: dict) -> str:
    source = item.get("source", "")
    if source in ("kisa_press", "kisa_research"):
        return "SECURITY_PRIVACY"
    if source in ("geeknews", "github"):
        return "DEVELOPER_TECH"
    if source == "hackernews":
        return "AI_LLM_AGENT"
    return "AI_LLM_AGENT"


def print_report(result: dict, multi_result: dict = None):
    print("=" * 78)
    print("  LUMOS 브리핑 품질 평가 보고서 v2 (오프라인)")
    print("=" * 78)

    ds = dataset_summary()
    print(f"\n평가 데이터셋: {ds['total']}건 + 다중 프로필 {ds['multi_profile_total']}건")
    print(f"  출처: {dict(ds['origin'])}")
    print(f"  언어: {dict(ds['language'])}")
    print(f"  유형: {dict(ds['content_type'])}")
    print(f"  지역: {dict(ds['region'])}")
    print(f"  신규성: {dict(ds['novelty'])}")

    # ── Dimension summary ──
    print(f"\n{'=' * 78}")
    print("  차원별 평가 결과")
    print(f"{'=' * 78}")
    for dim, stats in result["dimension_summary"].items():
        if stats["avg_score"] is not None:
            filled = int(stats["avg_score"] * 20)
            bar = "#" * filled + "." * (20 - filled)
            uneval = f" +{stats['unevaluated_count']}건 미평가" if stats["unevaluated_count"] else ""
            print(f"  {dim:<28s} {bar} {stats['avg_score']:.2f}  "
                  f"(통과 {stats['pass_rate']:.0%}, n={stats['evaluated_count']}{uneval})")
        else:
            print(f"  {dim:<28s} {'?' * 20} N/A   "
                  f"(전체 {stats['unevaluated_count']}건 사람 평가 대기)")

    # Cross-briefing
    cross = result["cross_briefing"]
    print(f"\n  브리핑 간 템플릿 반복 검사: {'통과' if cross['pass'] else 'X 문제 발견'}")
    if not cross["pass"]:
        for line in cross["details"].split(";"):
            print(f"    {line.strip()}")

    # ── Known issues from evaluator analysis ──
    print(f"\n{'=' * 78}")
    print("  기존 평가기 v1 대비 수정된 채점 규칙")
    print(f"{'=' * 78}")
    changes = [
        ("korean_readability",
         "v1: 형식만 검사 -> 100%",
         "v2: MT 번역체 패턴 탐지 추가, 번역 불완전 경고 추가"),
        ("recommendation_detail",
         "v1: 특정 1개 템플릿만 검사 -> 100%",
         "v2: 정규식으로 모든 템플릿 패턴 탐지, 기사 고유 내용 반영 여부 확인"),
        ("interest_relevance",
         "v1: 정확 문자열 일치만 -> 12%",
         "v2: 영한 동의어 매핑 지원, 원본/브리핑 분리 평가, 매칭 품질 문제 구분"),
        ("factual_fidelity",
         "v1: 완전 placeholder (N/A)",
         "v2: 수치·고유명사 표면 검사 추가 + 사람 평가 시트 제공"),
        ("novelty_detection",
         "v1: 이진 분류 (new/existing)",
         "v2: 4단계 분류 (최초 공개/업데이트/발견/판단불가), 빈 제목은 데이터 품질 문제로 분리"),
        ("cross_repetition",
         "v1: 1/3 이하만 검출",
         "v2: 50%/75% 두 단계 경고, 각 필드별 고유값 비율 보고"),
    ]
    for dim, before, after in changes:
        print(f"\n  [{dim}]")
        print(f"    이전: {before}")
        print(f"    이후: {after}")

    # ── Per-item failures ──
    print(f"\n{'=' * 78}")
    print("  항목별 상세 (문제 또는 경고가 있는 항목)")
    print(f"{'=' * 78}")
    issue_count = 0
    for item in result["item_results"]:
        failed = [c for c in item["checks"] if c["pass"] is False]
        warned = [c for c in item["checks"]
                  if c["pass"] is True and "(경고)" in c.get("details", "")]
        if failed or warned:
            issue_count += 1
            print(f"\n  [{item['item_id']}] {item['title']}")
            for check in failed:
                print(f"    X {check['dimension']}: {check['details'][:100]}")
            for check in warned:
                print(f"    ! {check['dimension']}: {check['details'][:100]}")

    if issue_count == 0:
        print("  (문제/경고 항목 없음)")

    # ── Multi-profile comparison ──
    if multi_result:
        print(f"\n{'=' * 78}")
        print("  다중 프로필 비교 (동일 소식, 다른 사용자 역할)")
        print(f"{'=' * 78}")

        # Group by item_id
        by_item = {}
        for item in multi_result["item_results"]:
            base_id = item["item_id"].rsplit("-", 1)[0] if "-" in item["item_id"] else item["item_id"]
            by_item.setdefault(base_id, []).append(item)

        for item_id, items in by_item.items():
            print(f"\n  [{item_id}] {items[0]['title']}")
            # Check if recommendation_reason differs across profiles
            reasons = set()
            for item in items:
                for check in item["checks"]:
                    if check["dimension"] == "recommendation_detail":
                        # Get the actual briefing reason
                        pass
                print(f"    {item['profile']}: ", end="")
                scores = {c["dimension"]: c.get("score", "N/A") for c in item["checks"]
                          if c["dimension"] in ("recommendation_detail", "interest_relevance")}
                print(f"추천={scores.get('recommendation_detail', '?')}, "
                      f"관련성={scores.get('interest_relevance', '?')}")

    # ── Sample briefings ──
    print(f"\n{'=' * 78}")
    print("  사람 평가용 브리핑 샘플 (3건 — 한국어/영어/혼합)")
    print(f"{'=' * 78}")
    sample_ids = ["eval-01", "eval-06", "eval-16"]
    for item in result["item_results"]:
        if item["item_id"] in sample_ids:
            src = next(i for i in EVAL_ITEMS if i["id"] == item["item_id"])
            briefing = generate_briefing(src)
            print(f"\n  [{item['item_id']}] 원문={src['language']}, {src['content_type']}, {src['region']}")
            print(f"    원문:   {src['title'][:70]}")
            print(f"    제목:   {briefing['display_title_ko']}")
            print(f"    요약:   {briefing['display_summary_ko'][:120]}...")
            print(f"    왜:     {briefing['why_it_matters_ko']}")
            print(f"    추천:   {briefing['recommendation_reason_ko']}")
            print(f"    행동:   {briefing['recommended_action_ko']}")
            print(f"    한계:   {briefing['detail_limitation_ko'][:80]}...")
            # Show factual fidelity check result
            ff = next(c for c in item["checks"] if c["dimension"] == "factual_fidelity")
            print(f"    사실성: {ff['details']}")

    # ── Human evaluation guidance ──
    print(f"\n{'=' * 78}")
    print("  사람 평가 체크리스트")
    print(f"{'=' * 78}")
    human_checks = {}
    for item in result["item_results"]:
        for check in item["checks"]:
            if check.get("needs_human") and check.get("human_note"):
                human_checks[check["dimension"]] = check["human_note"]
    for i, (dim, note) in enumerate(sorted(human_checks.items()), 1):
        print(f"  {i}. [{dim}] {note}")

    # ── Factual fidelity evaluation sheet ──
    print(f"\n{'=' * 78}")
    print("  사실 충실도 사람 평가 시트 (각 브리핑에 대해 작성)")
    print(f"{'=' * 78}")
    ff_item = next((item for item in result["item_results"]
                    if item["item_id"] == "eval-01"), None)
    if ff_item:
        ff_check = next(c for c in ff_item["checks"] if c["dimension"] == "factual_fidelity")
        if "human_evaluation_sheet" in ff_check:
            for key, question in ff_check["human_evaluation_sheet"].items():
                print(f"  {key}: {question}")

    # ── Summary ──
    print(f"\n{'=' * 78}")
    total_auto = sum(1 for item in result["item_results"]
                     for c in item["checks"]
                     if not c["needs_human"] and c["pass"] is not None)
    total_auto_pass = sum(1 for item in result["item_results"]
                         for c in item["checks"]
                         if not c["needs_human"] and c["pass"] is True)
    total_human_needed = sum(1 for item in result["item_results"]
                            for c in item["checks"] if c["needs_human"])
    total_unevaluated = sum(1 for item in result["item_results"]
                           for c in item["checks"] if c["score"] is None)
    print(f"  완전 자동 검사:  {total_auto_pass}/{total_auto} 통과")
    print(f"  사람 평가 필요:  {total_human_needed}건")
    print(f"  미평가 (N/A):    {total_unevaluated}건 (통과 건수 미포함)")
    print(f"{'=' * 78}\n")


def main():
    print("브리핑 생성 중...\n")

    # 1. Standard evaluation (25 items, default profile)
    pairs = []
    for item in EVAL_ITEMS:
        briefing = generate_briefing(item)
        pairs.append((briefing, item))
    result = evaluate_batch(pairs)

    # 2. Multi-profile evaluation (3 items x 3 profiles = 9 briefings)
    multi_items = get_multi_profile_pairs()
    multi_pairs = []
    for item in multi_items:
        role = item.get("eval_role", "예비 창업자")
        briefing = generate_briefing(item, role=role)
        multi_pairs.append((briefing, item))
    multi_result = evaluate_batch(multi_pairs) if multi_pairs else None

    print_report(result, multi_result)

    # Save raw JSON
    output_path = os.path.join(os.path.dirname(__file__), "evaluation_result.json")
    combined = {
        "standard": result,
        "multi_profile": multi_result,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2, default=str)
    print(f"상세 결과: {output_path}")


if __name__ == "__main__":
    main()
