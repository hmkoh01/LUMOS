from src.sources.collectors.public_institution_jobs import PublicInstitutionJobsCollector
from src.sources.collectors.base import CollectedItem, SourceQuery
from src.sources.domestic_collection_strategy import (
    analyse_public_job_title_coverage,
    dedupe_source_items,
    has_developer_role_evidence,
    support_program_matches_information_types,
    diagnostic_request_budget,
    public_job_discovery_plans,
    support_program_collection_plan,
    support_program_matches_profile,
)
from src.sources.query_planner import QueryPlanner


def test_public_job_profiles_only_use_documented_free_text_until_codebook_is_supplied():
    plans = public_job_discovery_plans(["신입 개발자 취업 인턴"])
    assert [plan.profile_id for plan in plans] == ["junior_developer", "it_software", "youth_intern", "general_junior"]
    assert all(plan.params["ongoingYn"] == "Y" for plan in plans)
    assert all("ncsCdLst" not in plan.params for plan in plans)
    assert plans[0].params["recrutPbancTtl"] == "개발"
    assert "ncsCdLst" in plans[0].requires_codebook


def test_public_job_code_filters_are_forwarded_only_when_explicitly_marked_official():
    unverified = public_job_discovery_plans(["개발자"], code_filters={"ncsCdLst": "OFFICIAL-NCS-CODE"})[0]
    assert "ncsCdLst" not in unverified.params
    plan = public_job_discovery_plans(["개발자"], code_filters={"ncsCdLst": "OFFICIAL-NCS-CODE", "unknown": "x"}, codebook_verified=True)[0]
    assert plan.params["ncsCdLst"] == "OFFICIAL-NCS-CODE"
    assert "unknown" not in plan.params
    collector = PublicInstitutionJobsCollector()
    url = collector._url("redacted", plan.params | {"recrutSe": "OFFICIAL-RECRUIT-CODE"}, 20)
    assert "recrutSe=OFFICIAL-RECRUIT-CODE" in url
    assert "ncsCdLst=OFFICIAL-NCS-CODE" in url


def test_shared_support_pool_uses_only_year_and_pagination_and_never_invents_keyword_filters():
    plan = support_program_collection_plan(year=2026)
    assert plan.params == {"sprtBizYr": "2026", "pageNo": "1", "numOfRows": "20"}
    assert plan.shared_scope == "mss_support_program:2026"
    assert diagnostic_request_budget("mss_support_program")["max_requests_per_cycle"] == 3


def test_support_profiles_require_direct_program_evidence_not_catalogue_category():
    category_only = {"title": "소상공인 판로 지원", "metrics_json": {"categories": ["창업"]}}
    technical = {"title": "기술창업 사업화 지원", "metrics_json": {"purpose": "초기 기술창업 기업의 사업화", "categories": ["소상공인"]}}
    digital = {"title": "온라인 판로 지원", "metrics_json": {"support_type": "디지털커머스"}}
    assert not support_program_matches_profile(category_only, "general_startup")
    assert support_program_matches_profile(technical, "technical_startup")
    assert support_program_matches_profile(digital, "digital_commerce")
    assert support_program_matches_profile(digital, "online_market_access")


def test_query_planner_emits_shared_domestic_plans_and_has_no_generic_fallback():
    planner = QueryPlanner()
    jobs = planner._queries_for_source("public_institution_jobs", ["신입 개발자"], "", [], "CAREER", {})
    assert jobs and all(entry["params"]["collection_scope"] == "public_institution_jobs:current-opportunities" for entry in jobs)
    support_missing_year = planner._queries_for_source("mss_support_program", ["창업 지원"], "", [], "STARTUP_PROGRAM", {})
    assert support_missing_year == []
    support = planner._queries_for_source("mss_support_program", ["창업 지원"], "", [], "STARTUP_PROGRAM", {"sprtBizYr": "2026"})
    assert support[0]["params"]["sprtBizYr"] == "2026"


def test_developer_collection_requires_job_role_evidence_not_intern_word_alone():
    query = SourceQuery(source="public_institution_jobs", query="junior_developer", params={
        "collection_scope": "public_institution_jobs:current-opportunities",
        "direct_evidence_terms": ["개발", "software", "developer"],
    })
    intern_only = CollectedItem(source="public_institution_jobs", source_item_id="1", title="청년 인턴 채용", url="https://example.invalid", metrics_json={"job_type": "인턴"})
    developer = CollectedItem(source="public_institution_jobs", source_item_id="2", title="소프트웨어 개발자 인턴 채용", url="https://example.invalid", metrics_json={"job_type": "인턴"})
    assert not PublicInstitutionJobsCollector._matches(intern_only, query)
    assert PublicInstitutionJobsCollector._matches(developer, query)


def test_intern_profile_requires_intern_evidence_but_not_developer_role_evidence():
    query = SourceQuery(source="public_institution_jobs", query="youth_intern", params={
        "collection_scope": "public_institution_jobs:current-opportunities",
        "direct_evidence_terms": ["인턴", "intern"],
        "requires_developer_role_evidence": False,
    })
    intern = CollectedItem(source="public_institution_jobs", source_item_id="1", title="청년 인턴 채용", url="https://example.invalid", metrics_json={"job_type": "인턴", "recruitment_type": "체험형"})
    unrelated = CollectedItem(source="public_institution_jobs", source_item_id="2", title="일반 신입 채용", url="https://example.invalid", metrics_json={"job_type": "정규직"})
    assert PublicInstitutionJobsCollector._matches(intern, query)
    assert not PublicInstitutionJobsCollector._matches(unrelated, query)


def test_future_diagnostics_can_compare_requested_and_actual_page_shape_without_source_text():
    budget = diagnostic_request_budget("public_institution_jobs")
    assert budget == {
        "source": "public_institution_jobs",
        "max_requests_per_cycle": 4,
        "max_rows_per_request": 20,
        "max_candidate_records": 80,
    }


def test_current_title_profiles_document_it_role_recall_gaps_without_guessing_codes():
    coverage = analyse_public_job_title_coverage([
        "신입 개발자 채용", "소프트웨어 엔지니어", "청년 인턴", "전산직 6급 채용",
        "정보보안 담당자", "IT 기술직", "SW 직무 채용",
    ])
    assert coverage["developer"] == ["신입 개발자 채용"]
    assert coverage["software"] == ["소프트웨어 엔지니어"]
    assert coverage["intern"] == ["청년 인턴"]
    assert coverage["uncovered_it_role"] == ["전산직 6급 채용", "정보보안 담당자", "IT 기술직", "SW 직무 채용"]


def test_multi_profile_merge_deduplicates_by_official_identifier_before_personal_ranking():
    merged = dedupe_source_items([
        {"source_item_id": "J-1"}, {"source_item_id": "J-2"}, {"source_item_id": "J-1"},
    ])
    assert [item["source_item_id"] for item in merged] == ["J-1", "J-2"]


def test_developer_role_evidence_rejects_organisation_names_containing_development():
    assert not has_developer_role_evidence("한국체육산업개발(주) 지원직 채용")
    assert not has_developer_role_evidence("한국개발연구원 연구직 채용")
    assert has_developer_role_evidence("소프트웨어 개발자 신입 채용")
    assert has_developer_role_evidence("SW 직무 인턴 채용")
    assert not has_developer_role_evidence("기계 엔지니어 채용")
    assert not has_developer_role_evidence("설비 엔지니어 채용")
    assert not has_developer_role_evidence("품질 엔지니어 채용")
    assert not has_developer_role_evidence("토목 엔지니어 채용")
    assert has_developer_role_evidence("백엔드 개발자 신입 채용")
    assert has_developer_role_evidence("소프트웨어 엔지니어 채용")


def test_support_information_type_selection_does_not_turn_digital_commerce_into_technology_startup():
    item = {"title": "온라인 판로 지원", "metrics_json": {"support_type": "디지털커머스", "purpose": "소상공인 온라인 판매 지원"}}
    assert support_program_matches_information_types(item, ["digital_commerce_support"])
    assert support_program_matches_information_types(item, ["online_market_access"])
    assert not support_program_matches_information_types(item, ["technology_startup_support"])
