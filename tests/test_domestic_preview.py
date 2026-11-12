from src.engine.llm.domestic_preview import build_domestic_preview
from src.engine.llm.domestic_preview import evaluate_personalised_item
from unittest.mock import patch

def test_metadata_previews_are_fact_first_and_withhold_missing_url():
    cases=[
        ("job_posting", "취업"), ("startup_program", "창업 지원사업"), ("youth_policy", "청년 주거"),
        ("culture_event", "서울 문화행사"), ("performance", "공연"), ("corporate_disclosure", "경제"),
    ]
    for kind, interest in cases:
        result=build_domestic_preview({"title":"source title","url":"https://official.example/x","metrics_json":{"content_kind":kind,"receipt_at":"2026-11-09"}},interest)
        assert result["status"]=="ready" and result["source_title"]=="source title"
    assert build_domestic_preview({"metrics_json":{"content_kind":"performance"}},"공연")["reason"]=="official_source_url_missing"

def test_personalisation_rejects_region_company_and_interest_mismatches():
    event={"title":"Busan music festival","url":"https://official.example/e","metrics_json":{"content_kind":"culture_event","event_status":"upcoming","region":"Busan","genre":"music"}}
    assert evaluate_personalised_item(event,"museum",preferred_region="Seoul")["reason"]=="region_mismatch"
    disclosure={"title":"Alpha Corp disclosure","author":"Alpha Corp","url":"https://dart.example/x","metrics_json":{"content_kind":"corporate_disclosure"}}
    assert evaluate_personalised_item(disclosure,"Beta Corp")["reason"]=="company_or_industry_mismatch"


def test_culture_personalisation_needs_a_region_or_concrete_event_term():
    event={"title":"Seoul Jazz Festival","url":"https://official.example/e","metrics_json":{"content_kind":"culture_event","event_status":"upcoming","region":"Seoul","genre":"jazz"}}
    assert evaluate_personalised_item(event,"culture")["reason"]=="interest_too_broad"
    assert evaluate_personalised_item(event,"Seoul culture",preferred_region="Seoul")["eligible"]=="true"
    assert evaluate_personalised_item(event,"jazz performance")["eligible"]=="true"
    assert evaluate_personalised_item(event,"Seoul festival",preferred_region="Seoul")["eligible"]=="true"
    assert evaluate_personalised_item(event,"Seoul exhibition",preferred_region="Seoul")["reason"]=="interest_mismatch"
    assert evaluate_personalised_item(event,"Busan festival",preferred_region="Busan")["reason"]=="region_mismatch"


def test_support_card_requires_more_than_a_broad_provider_category():
    item={"title":"Digital commerce programme","url":"https://official.example/p","metrics_json":{"content_kind":"startup_program","support_target":"small businesses","purpose":"online sales support","support_type":"commercialisation","categories":["startup"]}}
    assert evaluate_personalised_item(item,"startup")["reason"]=="support_interest_mismatch"


def test_explicit_support_information_type_filters_a_matching_programme_without_translation():
    item={"title":"Digital commerce programme","url":"https://official.example/p","metrics_json":{"content_kind":"startup_program","support_target":"small businesses","purpose":"online sales support","support_type":"digital commerce"}}
    with patch("src.engine.llm.domestic_preview.matches_interest", return_value=True):
        assert evaluate_personalised_item(item,"startup",selected_information_types=("digital_commerce_support",))["eligible"]=="true"
        assert evaluate_personalised_item(item,"startup",selected_information_types=("technology_startup_support",))["reason"]=="support_information_type_mismatch"


def test_developer_interest_does_not_accept_an_unrelated_internship():
    item={"title":"Dental hygienist internship","author":"Public hospital","url":"https://official.example/job","metrics_json":{"content_kind":"public_institution_job","job_type":"intern","region":"Seoul","job_classification":"healthcare"}}
    assert evaluate_personalised_item(item,"junior developer internship")["reason"]=="career_role_mismatch"


def test_performance_preview_uses_verified_metadata_and_never_uses_a_generic_placeholder():
    item={"title":"서울 재즈 페스티벌","url":"https://kopis.or.kr/por/db/pblprfr/pblprfrView.do?mt20Id=PF301231","metrics_json":{"content_kind":"performance","official_detail_content_verified":True,"event_status":"upcoming","event_start_at":"2026-11-20","event_end_at":"2026-11-23","venue":"서울광장","region":"서울","genre":"음악"}}
    assert evaluate_personalised_item(item,"재즈",preferred_region="서울")["eligible"]=="true"
    preview=build_domestic_preview(item,"재즈 공연")
    assert preview["display_title_ko"]=="서울 재즈 페스티벌 · 서울광장"
    assert "2026-11-20~2026-11-23" in preview["summary_ko"]
    assert "행사명·분야" in preview["recommendation_reason_ko"]


def test_performance_is_withheld_until_the_browser_detail_content_is_verified():
    item={"title":"공연","url":"https://kopis.or.kr/por/db/pblprfr/pblprfrView.do?mt20Id=PF301231","metrics_json":{"content_kind":"performance","event_status":"upcoming","region":"서울","genre":"음악"}}
    assert evaluate_personalised_item(item,"음악 공연",preferred_region="서울")["reason"]=="official_detail_content_unverified"


def test_disclosure_preview_names_the_company_without_inventing_a_news_event():
    item={"title":"주식등의대량보유상황보고서(일반)","author":"감성코퍼레이션","url":"https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261109000348","metrics_json":{"content_kind":"corporate_disclosure","receipt_at":"2026-11-09"}}
    preview=build_domestic_preview(item,"감성코퍼레이션")
    assert preview["display_title_ko"]=="감성코퍼레이션 주식등의대량보유상황보고서(일반)"
    assert preview["summary_ko"]=="접수일: 2026-11-09"
