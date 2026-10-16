"""Compare template-based vs LLM-based briefing quality — v2.

Usage:
    python -m tests.eval.run_llm_comparison [--model MODEL_ID]

Requires GEMINI_API_KEY in .env or environment.
Does NOT modify production data.
"""
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tests.eval.dataset import EVAL_ITEMS, EVAL_PROFILES, MULTI_PROFILE_ITEM_IDS, dataset_summary
from src.signals.korean_briefing import build_korean_briefing
from src.signals.llm_briefing import (
    BriefingLLMClient,
    generate_llm_briefing,
    clear_cache,
)
from src.signals.llm_briefing_validator import validate_content_briefing, validate_personalization


def _load_env():
    """Load .env file into os.environ (override=False)."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _infer_category(item: dict) -> str:
    source = item.get("source", "")
    if source in ("kisa_press", "kisa_research"):
        return "SECURITY_PRIVACY"
    if source in ("geeknews", "github"):
        return "DEVELOPER_TECH"
    return "AI_LLM_AGENT"


def generate_template_briefing(item: dict, role: str = "예비 창업자") -> dict:
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


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------
def compare_single(item: dict, role: str, keywords: list, client: BriefingLLMClient) -> dict:
    template = generate_template_briefing(item, role)
    llm = generate_llm_briefing(item, role=role, keywords=keywords, client=client)

    gen = llm.get("_generation", {})
    content_ok = gen.get("content_status") in ("success", "cached")
    person_ok = gen.get("personalize_status") == "success"

    if not content_ok:
        overall = gen.get("content_status", "unknown")
    elif not person_ok:
        overall = "content_only"
    else:
        overall = "success"

    c = {
        "item_id": item["id"],
        "title": item["title"][:70],
        "language": item["language"],
        "source": item["source"],
        "role": role,
        "llm_status": overall,
        "content_status": gen.get("content_status", "unknown"),
        "personalize_status": gen.get("personalize_status", "unknown"),
    }

    for field in ("display_title_ko", "display_summary_ko",
                   "recommendation_reason_ko", "why_it_matters_ko", "recommended_action_ko"):
        c[f"template_{field}"] = template.get(field, "")
        c[f"llm_{field}"] = llm.get(field, "")

    c["llm_grounded_facts"] = llm.get("grounded_facts", [])
    c["llm_key_entities"] = llm.get("key_entities", [])
    c["llm_key_numbers"] = llm.get("key_numbers", [])
    c["llm_is_new_event"] = llm.get("is_new_event")
    c["llm_content_type_label"] = llm.get("content_type_label", "")
    c["llm_information_gaps"] = llm.get("information_gaps", "")
    c["llm_limitation_ko"] = llm.get("limitation_ko", "")
    c["llm_relevance_confidence"] = llm.get("relevance_confidence", "")
    c["llm_validation"] = llm.get("_validation", {})

    content_meta = gen.get("content_metadata", {})
    person_meta = gen.get("personalize_metadata", {})
    c["content_latency_ms"] = content_meta.get("latency_ms", 0)
    c["personalize_latency_ms"] = person_meta.get("latency_ms", 0)
    c["total_latency_ms"] = c["content_latency_ms"] + c["personalize_latency_ms"]
    c["content_retries"] = content_meta.get("retries", 0)
    c["personalize_retries"] = person_meta.get("retries", 0)
    c["content_error_code"] = content_meta.get("error_code", "")
    c["personalize_error_code"] = person_meta.get("error_code", "")
    c["model_version"] = content_meta.get("model_version", "")

    return c


# ---------------------------------------------------------------------------
# Quality metrics
# ---------------------------------------------------------------------------
def evaluate_quality(comparisons: list) -> dict:
    m = {"total": len(comparisons), "llm_success": 0, "llm_content_only": 0,
         "llm_blocked": 0, "llm_failed": 0}

    template_recs, llm_recs = [], []
    entity_scores = []
    fabrication_count = 0
    grounding_verified, grounding_unverified = 0, 0

    for c in comparisons:
        s = c["llm_status"]
        if s == "success":
            m["llm_success"] += 1
        elif s == "content_only":
            m["llm_content_only"] += 1
        elif s == "blocked":
            m["llm_blocked"] += 1
        else:
            m["llm_failed"] += 1

        template_recs.append(c.get("template_recommendation_reason_ko", ""))
        llm_recs.append(c.get("llm_recommendation_reason_ko", ""))

        v = c.get("llm_validation", {}).get("checks", {})
        ep = v.get("entity_preservation", {})
        if ep and ep.get("source_entities"):
            entity_scores.append(ep.get("ratio", 0))
        nf = v.get("number_fabrication", {})
        if nf and not nf.get("pass", True):
            fabrication_count += 1
        fg = v.get("fact_grounding", {})
        grounding_verified += fg.get("verified", 0)
        grounding_unverified += fg.get("unverified", 0)

    successful = m["llm_success"]
    m["template_rec_unique"] = len(set(r for r in template_recs if r))
    m["template_rec_unique_ratio"] = m["template_rec_unique"] / max(len(template_recs), 1)
    m["llm_rec_unique"] = len(set(r for r in llm_recs if r))
    m["llm_rec_unique_ratio"] = m["llm_rec_unique"] / max(successful, 1) if successful else 0
    m["entity_preservation_avg"] = sum(entity_scores) / len(entity_scores) if entity_scores else 0
    m["number_fabrication_count"] = fabrication_count
    m["grounding_verified"] = grounding_verified
    m["grounding_unverified"] = grounding_unverified

    return m


# ---------------------------------------------------------------------------
# Human evaluation sheet
# ---------------------------------------------------------------------------
def generate_human_eval_sheet(comparisons: list, output_path: str):
    """Generate a blind comparison sheet for human evaluation."""
    eligible = [c for c in comparisons if c["llm_status"] == "success"]
    if len(eligible) > 20:
        eligible = eligible[:20]

    sheet = []
    for idx, c in enumerate(eligible, 1):
        # Randomize order (A/B) so evaluator doesn't know which is template/LLM
        methods = [("template", "A"), ("llm", "B")]
        if random.random() > 0.5:
            methods = [("llm", "A"), ("template", "B")]

        entry = {
            "eval_id": idx,
            "item_id": c["item_id"],
            "source_title": c["title"],
            "source_language": c["language"],
            "role": c["role"],
            "_method_key": {m[1]: m[0] for m in methods},  # for scoring later
        }

        for method_name, label in methods:
            prefix = f"{method_name}_"
            entry[f"briefing_{label}_title"] = c.get(f"{prefix}display_title_ko", "")
            entry[f"briefing_{label}_summary"] = c.get(f"{prefix}display_summary_ko", "")
            entry[f"briefing_{label}_recommendation"] = c.get(f"{prefix}recommendation_reason_ko", "")
            entry[f"briefing_{label}_why"] = c.get(f"{prefix}why_it_matters_ko", "")
            entry[f"briefing_{label}_action"] = c.get(f"{prefix}recommended_action_ko", "")

        entry["evaluation"] = {
            "factual_fidelity_A": None,  # 1-5
            "factual_fidelity_B": None,
            "korean_readability_A": None,  # 1-5
            "korean_readability_B": None,
            "recommendation_specificity_A": None,  # 1-5
            "recommendation_specificity_B": None,
            "user_relevance_A": None,  # 1-5
            "user_relevance_B": None,
            "unnecessary_speculation_A": None,  # 1-5 (lower=more speculation)
            "unnecessary_speculation_B": None,
            "overall_preference": None,  # "A", "B", or "tie"
            "notes": "",
        }
        sheet.append(entry)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sheet, f, ensure_ascii=False, indent=2)
    return len(sheet)


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------
def print_report(comparisons, multi_comparisons, metrics, multi_metrics, cost):
    P = print
    P("=" * 78)
    P("  LUMOS 브리핑 생성 방식 비교 보고서 v2 (템플릿 vs LLM)")
    P("=" * 78)

    ds = dataset_summary()
    P(f"\n평가 데이터: 표준 {ds['total']}건 + 다중 프로필 {ds['multi_profile_total']}건")
    P(f"프로필 수: {len(EVAL_PROFILES)}개")

    # 1. Call status
    P(f"\n{'=' * 78}")
    P("  1. LLM 호출 상태")
    P(f"{'=' * 78}")
    P(f"  완전 성공 (콘텐츠+개인화): {metrics['llm_success']}건")
    P(f"  콘텐츠만 성공: {metrics.get('llm_content_only', 0)}건")
    P(f"  차단 (권한 미확인): {metrics['llm_blocked']}건")
    P(f"  실패: {metrics['llm_failed']}건")
    P(f"  재시도 총 횟수: {cost.get('total_retries', 0)}회")
    err_codes = cost.get("error_codes", {})
    if err_codes:
        P(f"  오류 코드 분포: {err_codes}")

    # 2. Recommendation uniqueness
    P(f"\n{'=' * 78}")
    P("  2. 추천 이유 고유성")
    P(f"{'=' * 78}")
    P(f"  템플릿: {metrics['template_rec_unique']}개 고유값 / {metrics['total']}건"
      f" ({metrics['template_rec_unique_ratio']:.0%})")
    s = metrics["llm_success"]
    P(f"  LLM:    {metrics['llm_rec_unique']}개 고유값 / {s}건"
      f" ({metrics['llm_rec_unique_ratio']:.0%})")

    # 3. Fact grounding
    P(f"\n{'=' * 78}")
    P("  3. 사실 근거 추적")
    P(f"{'=' * 78}")
    P(f"  근거 확인된 주장: {metrics['grounding_verified']}건")
    P(f"  근거 미확인 주장: {metrics['grounding_unverified']}건 (LLM 인용이 원문에서 발견 안 됨)")
    total_g = metrics["grounding_verified"] + metrics["grounding_unverified"]
    if total_g:
        P(f"  근거 확인율: {metrics['grounding_verified'] / total_g:.0%}")
    P(f"  수치 날조: {metrics['number_fabrication_count']}건")
    P(f"  고유명사 보존율: {metrics['entity_preservation_avg']:.0%}")

    # 4. Side-by-side examples
    P(f"\n{'=' * 78}")
    P("  4. 비교 사례")
    P(f"{'=' * 78}")

    shown = 0
    for c in comparisons:
        if c["llm_status"] != "success":
            continue
        if shown >= 5:
            break
        shown += 1
        _print_comparison(c)

    # 5. Multi-profile
    if multi_comparisons:
        P(f"\n{'=' * 78}")
        P("  5. 다중 프로필 비교")
        P(f"{'=' * 78}")
        _print_multi_profile(multi_comparisons)

    # 6. Grounding details
    P(f"\n{'=' * 78}")
    P("  6. 근거 추적 상세 (최대 3건)")
    P(f"{'=' * 78}")
    shown_g = 0
    for c in comparisons:
        if c["llm_status"] != "success":
            continue
        facts = c.get("llm_grounded_facts", [])
        if not facts:
            continue
        if shown_g >= 3:
            break
        shown_g += 1
        P(f"\n  [{c['item_id']}] {c['title']}")
        v = c.get("llm_validation", {}).get("checks", {}).get("fact_grounding", {})
        for d in v.get("details", [])[:4]:
            found = "O" if d.get("quote_found") else "X"
            P(f"    [{found}] 주장: {d.get('claim', '')[:80]}")
            P(f"        인용: {d.get('source_quote', '')[:80]}")
            P(f"        유형: {d.get('type', '?')}, 일치율: {d.get('match_ratio', '?')}")

    # 7. Blocked & failed
    blocked = [c for c in comparisons if c["llm_status"] == "blocked"]
    if blocked:
        P(f"\n{'=' * 78}")
        P("  7. 차단된 항목")
        P(f"{'=' * 78}")
        for c in blocked:
            P(f"  [{c['item_id']}] {c['title']} (출처: {c['source']})")

    failed = [c for c in comparisons if c["llm_status"] in ("failed", "content_only")]
    if failed:
        P(f"\n{'=' * 78}")
        P("  8. 실패 항목")
        P(f"{'=' * 78}")
        for c in failed:
            err = c.get("content_error_code") or c.get("personalize_error_code") or "?"
            P(f"  [{c['item_id']}] {c['title']} (상태: {c['llm_status']}, 오류: {err})")

    # 9. Cost
    P(f"\n{'=' * 78}")
    P("  9. 비용 상세")
    P(f"{'=' * 78}")
    P(f"  모델: {cost.get('model', '?')}")
    P(f"  성공 호출: {cost.get('successful_calls', 0)}, 실패: {cost.get('failed_calls', 0)}")
    P(f"  콘텐츠 호출: {cost.get('content_calls', 0)}건, 비용: ${cost.get('content_cost_usd', 0):.6f}")
    P(f"  개인화 호출: {cost.get('personalize_calls', 0)}건, 비용: ${cost.get('personalize_cost_usd', 0):.6f}")
    P(f"  입력 토큰: {cost.get('total_input_tokens', 0):,}")
    P(f"  출력 토큰: {cost.get('total_output_tokens', 0):,}")
    P(f"  추론 토큰: {cost.get('total_thinking_tokens', 0):,}")
    P(f"  평균 지연: {cost.get('avg_latency_ms', 0):.0f}ms")
    P(f"  총 비용: ${cost.get('total_cost_usd', 0):.6f}")

    all_lat = [c["total_latency_ms"] for c in comparisons
               if c["llm_status"] == "success" and c["total_latency_ms"] > 0]
    if all_lat:
        P(f"  브리핑당 평균: {sum(all_lat)/len(all_lat):.0f}ms, 최대: {max(all_lat):.0f}ms")

    # 10. Human eval
    P(f"\n{'=' * 78}")
    P("  10. 사람 평가")
    P(f"{'=' * 78}")
    P("  상태: 미완료 — 자동 평가만 수행됨")
    P("  블라인드 비교 시트가 human_eval_sheet.json에 생성됨")
    P("  평가 항목: 사실 충실도, 한국어 이해도, 추천 구체성, 사용자 관련성, 불필요한 추측")

    # Summary
    P(f"\n{'=' * 78}")
    P("  요약")
    P(f"{'=' * 78}")
    P(f"  추천 고유율: 템플릿={metrics['template_rec_unique_ratio']:.0%}, LLM={metrics['llm_rec_unique_ratio']:.0%}")
    P(f"  근거 확인율: {metrics['grounding_verified']}/{total_g} ({metrics['grounding_verified']/max(total_g,1):.0%})" if total_g else "  근거 확인: 데이터 없음")
    P(f"  고유명사 보존: {metrics['entity_preservation_avg']:.0%}")
    P(f"  수치 날조: {metrics['number_fabrication_count']}건")
    P(f"  총 비용: ${cost.get('total_cost_usd', 0):.6f}")
    P(f"  사람 평가: 미완료")
    P(f"{'=' * 78}\n")


def _print_comparison(c):
    P = print
    P(f"\n  [{c['item_id']}] {c['title']}")
    P(f"  언어={c['language']}, 출처={c['source']}, 모델={c.get('model_version','?')}")

    for label, field in [("제목", "display_title_ko"), ("요약", "display_summary_ko"),
                         ("추천 이유", "recommendation_reason_ko"),
                         ("왜 중요한지", "why_it_matters_ko"),
                         ("다음 행동", "recommended_action_ko")]:
        t = c.get(f"template_{field}", "")[:120]
        l = c.get(f"llm_{field}", "")[:120]
        P(f"  [{label}]")
        P(f"    템플릿: {t}")
        P(f"    LLM:    {l}")

    if c.get("llm_grounded_facts"):
        P(f"  [근거 추적] {len(c['llm_grounded_facts'])}건")
    if c.get("llm_key_entities"):
        P(f"  [고유명사] {', '.join(c['llm_key_entities'][:8])}")
    if c.get("llm_relevance_confidence"):
        P(f"  [관련성 확신도] {c['llm_relevance_confidence']}")

    v = c.get("llm_validation", {})
    if v.get("issues"):
        P(f"  [X] {'; '.join(v['issues'])}")
    if v.get("warnings"):
        P(f"  [!] {'; '.join(v['warnings'][:3])}")
    P(f"  [지연] {c['total_latency_ms']:.0f}ms (재시도: {c.get('content_retries',0)}+{c.get('personalize_retries',0)})")


def _print_multi_profile(multi_comparisons):
    P = print
    by_item = {}
    for c in multi_comparisons:
        by_item.setdefault(c["item_id"], []).append(c)

    for item_id, items in by_item.items():
        P(f"\n  [{item_id}] {items[0]['title']}")

        # Template: should be identical across profiles
        t_recs = set(c.get("template_recommendation_reason_ko", "") for c in items)
        P(f"  템플릿: {len(t_recs)}개 고유값 {'(동일)' if len(t_recs) <= 1 else '(차이 있음)'}")

        # LLM: compare across profiles
        for c in items:
            status = c["llm_status"]
            role = c["role"]
            if status == "blocked":
                P(f"    {role}: 차단")
                continue
            if status not in ("success",):
                P(f"    {role}: {status} (오류: {c.get('content_error_code') or c.get('personalize_error_code', '?')})")
                continue
            rec = c.get("llm_recommendation_reason_ko", "")[:100]
            conf = c.get("llm_relevance_confidence", "?")
            P(f"    {role} [관련성={conf}]:")
            P(f"      추천: {rec}")

        # Count distinct LLM recs
        llm_recs = set(c.get("llm_recommendation_reason_ko", "") for c in items if c["llm_status"] == "success")
        llm_recs.discard("")
        if llm_recs:
            if len(llm_recs) > 1:
                P(f"  LLM: {len(llm_recs)}개 고유값 (역할별 차별화)")
            elif len(llm_recs) == 1:
                P(f"  LLM: 1개 고유값 (차별화 미발생 — 근거 부족 가능)")
        else:
            P(f"  LLM: 성공한 개인화 없음")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Override LUMOS_LLM_MODEL")
    args = parser.parse_args()

    _load_env()

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set.")
        sys.exit(1)

    model = args.model or os.environ.get("LUMOS_LLM_MODEL", "").strip() or None
    client = BriefingLLMClient(api_key=api_key, model=model)
    print(f"모델: {client._model}")
    print(f"프롬프트 버전: v2 (fact grounding)")
    print(f"표준 데이터: {len(EVAL_ITEMS)}건, 프로필: {len(EVAL_PROFILES)}개\n")

    # Standard evaluation
    print("표준 평가...")
    comparisons = []
    for item in EVAL_ITEMS:
        c = compare_single(item, "예비 창업자", item.get("matched_keywords", []), client)
        comparisons.append(c)
        icon = {"success": "O", "content_only": "C", "blocked": "B"}.get(c["llm_status"], "X")
        print(f"  [{icon}] {item['id']}: {item['title'][:50]}... ({c['total_latency_ms']:.0f}ms)")

    metrics = evaluate_quality(comparisons)

    # Multi-profile evaluation
    print(f"\n다중 프로필 평가 ({len(MULTI_PROFILE_ITEM_IDS)}건 x {len(EVAL_PROFILES)}역할)...")
    multi = []
    items_by_id = {item["id"]: item for item in EVAL_ITEMS}

    for item_id in MULTI_PROFILE_ITEM_IDS:
        item = items_by_id.get(item_id)
        if not item:
            continue
        for profile in EVAL_PROFILES:
            keywords = profile.get("keywords", item.get("matched_keywords", []))
            c = compare_single(item, profile["role"], keywords, client)
            c["profile"] = profile["id"]
            multi.append(c)
            icon = {"success": "O", "content_only": "C", "blocked": "B"}.get(c["llm_status"], "X")
            print(f"  [{icon}] {item_id}/{profile['id']}: {c['total_latency_ms']:.0f}ms")

    multi_metrics = evaluate_quality(multi) if multi else None

    # Cost summary
    cost = client.tracker.summary()
    cost["model"] = client._model

    # Print report
    print()
    print_report(comparisons, multi, metrics, multi_metrics, cost)

    # Human eval sheet
    sheet_path = os.path.join(os.path.dirname(__file__), "human_eval_sheet.json")
    n_sheet = generate_human_eval_sheet(comparisons, sheet_path)
    print(f"사람 평가 시트: {sheet_path} ({n_sheet}건)")

    # Save JSON
    output_path = os.path.join(os.path.dirname(__file__), "llm_comparison_result.json")
    output = {
        "model": client._model,
        "prompt_version": "v2",
        "standard_comparisons": comparisons,
        "multi_profile_comparisons": multi,
        "standard_metrics": metrics,
        "multi_profile_metrics": multi_metrics,
        "cost": cost,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"상세 결과: {output_path}")


if __name__ == "__main__":
    main()
