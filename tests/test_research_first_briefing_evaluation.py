from datetime import date

from src.engine.config import EngineConfig
from src.engine.evaluation.scorer import evaluate_candidates
from src.engine.models import Period, RawCandidate


def _paper(title, published_at):
    return RawCandidate(
        dedupe_key=title, source="openalex", url="https://doi.org/10.1000/example",
        title=title, summary="", published_at=published_at,
        metrics={"content_kind": "research_metadata", "publication_date_precision": "day"},
    )


def test_llm_research_interest_matches_large_language_model_metadata_without_matching_general_news():
    paper = _paper("A statistical framework for evaluating the repeatability and reproducibility of large language models", "2026-10-27T00:00:00")
    monthly = evaluate_candidates([paper], Period.MONTHLY, ["LLM research paper"], EngineConfig(), reference_date=date(2026, 11, 8))
    assert len(monthly) == 1
    assert monthly[0].score_breakdown["interest_match"] == 1.0

    non_research = _paper("Large Language Model product announcement", "2026-10-27T00:00:00")
    non_research.metrics["content_kind"] = "official_update"
    assert evaluate_candidates([non_research], Period.MONTHLY, ["LLM research paper"], EngineConfig(), reference_date=date(2026, 11, 8)) == []
