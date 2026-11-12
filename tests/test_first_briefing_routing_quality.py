from src.engine.collection.source_support import collection_support
from src.sources.router import SourceRouter


def _categories(interest):
    return SourceRouter().classify_interests({}, [{"keyword": interest, "status": "active"}])


def test_first_briefing_interest_intents_do_not_fall_back_to_developer_sources():
    expected = {
        "AI \ud2b8\ub80c\ub4dc": "AI_TREND",
        "AI \uc624\ud508\uc18c\uc2a4 \ubc0f \uac1c\ubc1c \ub3c4\uad6c": "AI_OPEN_SOURCE",
        "\uc2e0\uc785 \uac1c\ubc1c\uc790 \ucde8\uc5c5\u00b7\uc778\ud134": "CAREER",
        "\ucc3d\uc5c5 \uc9c0\uc6d0\uc0ac\uc5c5": "STARTUP_PROGRAM",
        "\uacbd\uc81c\u00b7\uae08\ub9ac": "ECONOMY_FINANCE",
        "\uccad\ub144 \uc8fc\uac70\ubcf5\uc9c0": "YOUTH_POLICY",
        "\ucd5c\uc2e0 \uc5f0\uad6c\ub17c\ubb38": "RESEARCH",
        "\uc9c0\uc5ed \ubb38\ud654\ud589\uc0ac\u00b7\uacf5\uc5f0\u00b7\uc804\uc2dc": "CULTURE_TRAVEL_EVENT",
    }
    for interest, category in expected.items():
        categories = _categories(interest)
        assert category in categories

    # The pilot inventory only has GitHub/Hacker News.  Except for explicit
    # open-source intent, specialised first-briefing interests must wait for a
    # relevant approved source instead of receiving a low-relevance fallback.
    for interest in expected:
        if interest == "AI \uc624\ud508\uc18c\uc2a4 \ubc0f \uac1c\ubc1c \ub3c4\uad6c":
            assert collection_support(interest, ["github", "hackernews"])["status"] == "supported"
        else:
            assert collection_support(interest, ["github", "hackernews"])["status"] == "awaiting_approved_source"


def test_broad_career_words_and_unknown_interests_do_not_become_developer_technology():
    for interest in ("\ucde8\uc5c5", "\uc778\ud134", "\uc2e0\uc785 \uac1c\ubc1c\uc790"):
        assert set(_categories(interest)) == {"CAREER"}
        assert collection_support(interest, ["github", "hackernews"])["status"] == "awaiting_approved_source"

    assert _categories("\ubc18\ub824\ub3d9\ubb3c \uac74\uac15") == {}
    assert collection_support("\ubc18\ub824\ub3d9\ubb3c \uac74\uac15", ["github", "hackernews"])["status"] == "no_approved_source"
