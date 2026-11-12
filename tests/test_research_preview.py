from src.engine.llm.research_preview import build_research_preview


def test_research_preview_is_metadata_only_and_separates_review_material():
    preview = build_research_preview({
        "title": "A Survey of Large Language Models", "url": "https://doi.org/10.1000/example", "published_at": "2026-11-05T00:00:00",
        "metrics_json": {"content_kind": "research_metadata", "publication_date": "2026-11-05", "research_role": "reference_review", "doi": "https://doi.org/10.1000/example", "topics": ["Natural language processing"]},
    }, ["LLM \uc5f0\uad6c\ub17c\ubb38"])
    assert preview["research_role"] == "reference_review"
    assert "Natural language processing" in preview["recommendation_reason_ko"]
    assert "LLM \uc5f0\uad6c\ub17c\ubb38" not in preview["recommendation_reason_ko"]
    assert preview["source_title"] == "A Survey of Large Language Models"
    assert preview["doi"] == "https://doi.org/10.1000/example"
    assert "A Survey" not in preview["display_title_ko"]
    assert preview["display_title_ko"] == "\ub300\uaddc\ubaa8 \uc5b8\uc5b4 \ubaa8\ub378\uc744 \uc815\ub9ac\ud55c \uc5f0\uad6c"


def test_unknown_english_title_is_held_for_original_text_review_not_misrepresented():
    preview = build_research_preview({
        "title": "On zxyq systems", "url": "https://doi.org/10.1000/example", "published_at": "2026-11-05",
        "metrics_json": {"content_kind": "research_metadata", "publication_date": "2026-11-05"},
    }, ["LLM \uc5f0\uad6c\ub17c\ubb38"])
    assert preview is None


def test_title_rules_handle_review_evaluation_and_non_ai_domains_without_generic_labels():
    cases = [
        ("Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", "\uac80\uc0c9\uc73c\ub85c \uc815\ubcf4\ub97c \ubcf4\uc644\ud558\ub294 \uc5b8\uc5b4 \ubaa8\ub378\uc744 \ub2e4\ub8ec \uc5f0\uad6c"),
        ("Evaluating Large Language Models", "\ub300\uaddc\ubaa8 \uc5b8\uc5b4 \ubaa8\ub378\uc758 \ud3c9\uac00\ub97c \ub2e4\ub8ec \uc5f0\uad6c"),
        ("A Review of Monetary Policy", "\ud1b5\ud654 \uc815\ucc45\uc744 \uc815\ub9ac\ud55c \uc5f0\uad6c"),
        ("Job Market Evaluation", "\uace0\uc6a9 \uc2dc\uc7a5\uc758 \ud3c9\uac00\ub97c \ub2e4\ub8ec \uc5f0\uad6c"),
    ]
    for source_title, expected in cases:
        preview = build_research_preview({
            "title": source_title, "url": "https://doi.org/10.1000/example", "published_at": "2026-11-05",
            "metrics_json": {"content_kind": "research_metadata", "publication_date": "2026-11-05"},
        }, ["\uad00\uc2ec\uc0ac"])
        assert preview["display_title_ko"] == expected


def test_explicit_source_title_subject_is_preserved_in_research_preview():
    cases = [
        ("A statistical framework for evaluating the repeatability and reproducibility of large language models", "\ub300\uaddc\ubaa8 \uc5b8\uc5b4 \ubaa8\ub378 \uacb0\uacfc\uc758 \uc7ac\ud604\uc131 \ud3c9\uac00\ub97c \ub2e4\ub8ec \uc5f0\uad6c"),
        ("Less can be more for predicting properties with large language models", "\ub300\uaddc\ubaa8 \uc5b8\uc5b4 \ubaa8\ub378\uc744 \ud65c\uc6a9\ud55c \ud2b9\uc131 \uc608\uce21\uc744 \ub2e4\ub8ec \uc5f0\uad6c"),
        ("Large language models in geospatial science", "\uc9c0\ub9ac\uacf5\uac04 \uacfc\ud559\uc5d0\uc11c\uc758 \ub300\uaddc\ubaa8 \uc5b8\uc5b4 \ubaa8\ub378 \ud65c\uc6a9\uc744 \ub2e4\ub8ec \uc5f0\uad6c"),
    ]
    for source_title, expected in cases:
        preview = build_research_preview({
            "title": source_title, "url": "https://doi.org/10.1000/example", "published_at": "2026-11-05",
            "metrics_json": {"content_kind": "research_metadata", "publication_date": "2026-11-05"},
        }, ["LLM \uc5f0\uad6c\ub17c\ubb38"])
        assert preview["display_title_ko"] == expected
