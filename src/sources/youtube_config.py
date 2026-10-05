"""Tunable policy values for YouTube candidate selection and scoring."""

MIN_SUBSCRIBERS = 10_000
MIN_CHANNEL_VIDEOS = 20
MIN_VIDEO_VIEWS = 3_000
# Applies to every channel type, including official and academic sources.
MIN_VIDEO_VIEWS_FLOOR = 1_000
MIN_DURATION_SECONDS = 180

AUTHORITY_WEIGHT = 0.40
RELEVANCE_WEIGHT = 0.25
CHANNEL_WEIGHT = 0.15
PERFORMANCE_WEIGHT = 0.10
FRESHNESS_WEIGHT = 0.10

CANDIDATE_POOL_SIZE = 40
YOUTUBE_BATCH_SIZE = 50

FRESHNESS_HALF_LIFE_DAYS = {
    "news": 7,
    "finance": 30,
    "ai_it": 90,
    "science": 365,
    "self_development": 730,
    "history_philosophy": 1_460,
    "default": 180,
}

SOURCE_TYPE_SCORES = {
    "OFFICIAL": 96,
    "ACADEMIC": 94,
    "MEDIA": 85,
    "EXPERT": 80,
    "CREATOR": 60,
    "UNKNOWN": 35,
}

TRUSTED_SOURCE_TYPES = {"OFFICIAL", "ACADEMIC", "MEDIA", "EXPERT"}
