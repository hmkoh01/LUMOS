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
                "https://blog.langchain.com/rss/",
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
        "config_json": {"keywords": ["creator", "video trend"], "collector": "placeholder"},
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
}
