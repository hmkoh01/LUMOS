DEFAULT_CONNECTORS = {
    "browser_history": True,
    "local_files": True,
    "notion": False,
    "google_drive": False,
    "chatgpt_export": False,
    "claude_export": False,
}

DEFAULT_SOURCES = [
    "hackernews",
    "rss",
    "official_ai_blogs",
    "github",
]

FEEDBACK_EVENT_TYPES = {
    "saved",
    "ignored",
    "tracked",
    "opened",
    "briefing_ready",
    "briefing_shown",
    "briefing_opened",
    "briefing_dismissed",
    "briefing_refreshed",
    "briefing_generate_clicked",
    "preference_reason_set",
}

DEFAULT_SOURCE_CONFIGS = {
    "official_ai_blogs": {
        "enabled": True,
        "display_name": "Official AI Blogs",
        "priority": 90,
        "config_json": {
            "feed_urls": [
                "https://openai.com/news/rss.xml",
                "https://www.anthropic.com/news/rss.xml",
                "https://blog.google/technology/ai/rss/",
                "https://huggingface.co/blog/feed.xml",
            ],
            "keywords": ["AI agent", "LLM", "model release", "workflow automation"],
            "language": "en",
            "region": "global",
            "collector": "rss",
            "source_role": "primary",
            "verification_status": "official_source",
            "content_policy": {"excerpt_storage": "not_approved", "llm_input": "not_approved"},
            "content_filter": {
                "any_terms": ["ai", "artificial intelligence", "gemini", "model", "llm", "agent", "codex", "deepmind"],
                "allow_category_match": True,
            },
        },
    },
    "hackernews": {
        "enabled": True,
        "display_name": "Hacker News",
        "priority": 80,
        "config_json": {
            "keywords": ["AI agent", "developer tools", "startup"],
            "story_kind": "topstories",
            "language": "en",
            "region": "global",
        },
    },
    "rss": {
        "enabled": True,
        "display_name": "RSS and Official Blogs",
        "priority": 70,
        "config_json": {
            "feed_urls": [
                "https://github.blog/feed/",
                "https://vercel.com/blog/rss.xml",
                "https://blog.langchain.com/rss.xml",
            ],
            "keywords": ["developer tools", "startup", "productivity"],
            "language": "en",
            "region": "global",
            "collector": "rss",
        },
    },
    "github": {
        "enabled": True,
        "display_name": "GitHub",
        "priority": 75,
        "config_json": {
            "keywords": ["open source", "AI agent", "workflow automation"],
            "min_stars": 20,
            "sort": "updated",
            "collector": "github",
        },
    },
    "producthunt": {
        "enabled": False,
        "display_name": "Product Hunt",
        "priority": 45,
        "config_json": {"keywords": ["productivity", "AI assistant"], "collector": "placeholder"},
    },
    "reddit": {
        "enabled": False,
        "display_name": "Reddit",
        "priority": 42,
        "config_json": {"keywords": ["community reaction", "developer tools"], "collector": "placeholder"},
    },
    "youtube": {
        "enabled": False,
        "display_name": "YouTube",
        "priority": 38,
        "config_json": {"keywords": ["creator", "video trend"], "language": "ko", "region": "KR", "collector": "youtube"},
    },
    "naver_news": {
        "enabled": False,
        "display_name": "Naver News",
        "priority": 40,
        "config_json": {"keywords": ["생성형 AI", "스타트업"], "language": "ko", "region": "kr", "collector": "placeholder"},
    },
    "company_newsroom": {
        "enabled": False,
        "display_name": "Company Newsrooms",
        "priority": 35,
        "config_json": {"feed_urls": [], "keywords": [], "collector": "rss"},
    },
    "arxiv": {
        "enabled": False,
        "display_name": "arXiv",
        "priority": 37,
        "config_json": {"keywords": ["research", "agents"], "collector": "placeholder"},
    },
    # Registry entries below document a real routing target without enabling
    # it. Credentials plus reuse/AI-processing approval are required before a
    # collector may be switched on.
    "crossref": {
        "enabled": False,
        "display_name": "Crossref",
        "priority": 70,
        "config_json": {"collector": "crossref", "content_type": "research_metadata", "usage_status": "metadata_only"},
    },
    "openalex": {
        "enabled": False,
        "display_name": "OpenAlex",
        "priority": 75,
        "config_json": {"collector": "openalex", "content_type": "research", "usage_status": "permission_review"},
    },
    "mss_bizinfo": {
        "enabled": False,
        "display_name": "MSS Business Announcements",
        "priority": 80,
        "config_json": {"collector": "pending_approval", "content_type": "startup_program", "usage_status": "permission_review"},
    },
    "msit_announcements": {
        "enabled": False,
        "display_name": "MSIT Business Announcements",
        "priority": 80,
        "config_json": {"collector": "msit_announcements", "content_type": "government_rnd_announcement", "usage_status": "approved_metadata_only"},
    },
    # RSS endpoints are kept separate from the authenticated MSIT public-data
    # service. Neither is enabled until reuse and AI-processing scope is
    # explicitly approved by the operator.
    "msit_business_rss": {
        "enabled": False,
        "display_name": "MSIT Business Announcements RSS",
        "priority": 80,
        "config_json": {
            "collector": "rss", "content_type": "startup_program",
            "opportunity_only": True,
            "feed_urls": ["https://www.msit.go.kr/user/rss/rss.do?bbsSeqNo=100"],
            "source_role": "primary", "verification_status": "official_source",
            "rights_evidence_url": "https://www.msit.go.kr/contents/cont.do?mId=173&mPid=147&sCode=user",
            "requires_post_rights": True,
            "content_policy": {"excerpt_storage": "not_approved", "llm_input": "not_approved"},
            "usage_status": "permission_review",
        },
    },
    "msit_recruitment_rss": {
        "enabled": False,
        "display_name": "MSIT Recruitment RSS",
        "priority": 80,
        "config_json": {
            "collector": "rss", "content_type": "career",
            "opportunity_only": True,
            "feed_urls": ["https://www.msit.go.kr/user/rss/rss.do?bbsSeqNo=98"],
            "source_role": "primary", "verification_status": "official_source",
            "rights_evidence_url": "https://www.msit.go.kr/contents/cont.do?mId=173&mPid=147&sCode=user",
            "requires_post_rights": True,
            "content_policy": {"excerpt_storage": "not_approved", "llm_input": "not_approved"},
            "usage_status": "permission_review",
        },
    },
    "youthcenter_policy": {
        "enabled": False,
        "display_name": "Youth Center Policy",
        "priority": 80,
        "config_json": {"collector": "pending_approval", "content_type": "youth_policy", "usage_status": "permission_review"},
    },
    "tourapi": {
        "enabled": False,
        "display_name": "Korea TourAPI",
        "priority": 75,
        "config_json": {"collector": "pending_approval", "content_type": "tourism_event", "usage_status": "permission_review"},
    },
    "employment24": {
        "enabled": False,
        "display_name": "Employment24",
        "priority": 80,
        "config_json": {"collector": "pending_approval", "content_type": "career", "usage_status": "permission_review"},
    },
    "opendart": {
        "enabled": False,
        "display_name": "OpenDART",
        "priority": 85,
        "config_json": {"collector": "pending_approval", "content_type": "disclosure", "usage_status": "permission_review"},
    },
    # Pilot sources are intentionally seeded as auto but cannot be collected
    # until their redistribution and AI-processing terms are confirmed.
    "geeknews": {
        "enabled": False,
        "display_name": "GeekNews",
        "priority": 62,
        "config_json": {
            "feed_urls": ["https://news.hada.io/rss/news"],
            "language": "ko", "source_region": "domestic", "content_type": "community",
            "collector": "rss", "usage_status": "permission_review",
        },
    },
    "kisa_press": {
        "enabled": False,
        "display_name": "KISA 보도자료",
        "priority": 68,
        "config_json": {
            "feed_urls": ["https://kisa.or.kr/rss/402"],
            "language": "ko", "source_region": "domestic", "content_type": "official_announcement",
            "collector": "rss", "usage_status": "permission_review",
        },
    },
    "kisa_research": {
        "enabled": False,
        "display_name": "KISA 연구보고서",
        "priority": 68,
        "config_json": {
            "feed_urls": ["https://kisa.or.kr/rss/201"],
            "language": "ko", "source_region": "domestic", "content_type": "research_report",
            "collector": "rss", "usage_status": "permission_review",
        },
    },
}
