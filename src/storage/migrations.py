SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS user_settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        signal_count INTEGER NOT NULL DEFAULT 3,
        briefing_time TEXT NOT NULL DEFAULT '08:00',
        timezone TEXT NOT NULL DEFAULT 'Asia/Seoul',
        enabled_sources_json TEXT NOT NULL,
        enabled_connectors_json TEXT NOT NULL,
        desktop_push_enabled INTEGER NOT NULL DEFAULT 1,
        generate_mode TEXT NOT NULL DEFAULT 'mock',
        sync_before_briefing INTEGER NOT NULL DEFAULT 1,
        context_sync_interval_minutes INTEGER NOT NULL DEFAULT 360,
        max_interest_keywords INTEGER NOT NULL DEFAULT 50,
        mode_enabled INTEGER NOT NULL DEFAULT 1,
        onboarding_completed INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_profile (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        role TEXT NOT NULL DEFAULT '',
        role_detail TEXT NOT NULL DEFAULT '',
        goals_json TEXT NOT NULL DEFAULT '[]',
        interest_types_json TEXT NOT NULL DEFAULT '[]',
        raw_onboarding_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS connectors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        connector_type TEXT NOT NULL UNIQUE,
        enabled INTEGER NOT NULL DEFAULT 0,
        auth_status TEXT NOT NULL DEFAULT 'not_connected',
        config_json TEXT NOT NULL DEFAULT '{}',
        last_sync_at TEXT,
        last_status TEXT,
        last_error TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS interest_graph (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT NOT NULL,
        category TEXT,
        weight REAL NOT NULL DEFAULT 1.0,
        source TEXT NOT NULL DEFAULT 'manual',
        evidence_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'active',
        last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(keyword, category, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_routes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pipeline_run_id INTEGER,
        route_date TEXT NOT NULL,
        source TEXT NOT NULL,
        query TEXT NOT NULL,
        limit_count INTEGER NOT NULL DEFAULT 10,
        reason TEXT NOT NULL DEFAULT '',
        category TEXT,
        status TEXT NOT NULL DEFAULT 'planned',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS context_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        connector_type TEXT NOT NULL,
        item_id TEXT NOT NULL,
        dedupe_key TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        text_snippet TEXT NOT NULL DEFAULT '',
        url TEXT,
        path TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT,
        updated_at TEXT,
        collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS context_sync_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        connector_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'running',
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        item_count INTEGER NOT NULL DEFAULT 0,
        keyword_count INTEGER NOT NULL DEFAULT 0,
        summary_json TEXT NOT NULL DEFAULT '{}',
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id TEXT NOT NULL UNIQUE,
        enabled INTEGER NOT NULL DEFAULT 0,
        display_name TEXT NOT NULL DEFAULT '',
        config_json TEXT NOT NULL DEFAULT '{}',
        priority INTEGER NOT NULL DEFAULT 50,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pipeline_run_id INTEGER,
        dedupe_key TEXT,
        source TEXT NOT NULL,
        source_item_id TEXT,
        url TEXT,
        title TEXT NOT NULL,
        summary TEXT,
        author TEXT,
        published_at TEXT,
        metrics_json TEXT NOT NULL DEFAULT '{}',
        raw_json TEXT NOT NULL DEFAULT '{}',
        collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS signal_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pipeline_run_id INTEGER,
        dedupe_key TEXT,
        source_item_id INTEGER,
        route_id INTEGER,
        score REAL NOT NULL DEFAULT 0.0,
        score_breakdown_json TEXT NOT NULL DEFAULT '{}',
        matched_keywords_json TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'new',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pipeline_run_id INTEGER,
        dedupe_key TEXT,
        signal_date TEXT NOT NULL,
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        why_it_matters TEXT NOT NULL,
        category TEXT,
        recommended_action TEXT,
        source_name TEXT,
        source_url TEXT,
        source_items_json TEXT NOT NULL DEFAULT '[]',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        confidence REAL NOT NULL DEFAULT 0.0,
        rank INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'new',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        shown_at TEXT,
        archived_reason TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'running',
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        triggered_by TEXT NOT NULL DEFAULT 'manual',
        settings_snapshot_json TEXT NOT NULL DEFAULT '{}',
        profile_snapshot_json TEXT NOT NULL DEFAULT '{}',
        interest_snapshot_json TEXT NOT NULL DEFAULT '[]',
        selected_sources_json TEXT NOT NULL DEFAULT '[]',
        summary_json TEXT NOT NULL DEFAULT '{}',
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_interest_graph_keyword ON interest_graph(keyword)",
    "CREATE INDEX IF NOT EXISTS idx_signals_date_rank ON signals(signal_date, rank)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_events_signal ON feedback_events(signal_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_context_items_dedupe ON context_items(dedupe_key)",
    "CREATE INDEX IF NOT EXISTS idx_context_items_connector ON context_items(connector_type, collected_at)",
    "CREATE INDEX IF NOT EXISTS idx_context_sync_runs_started ON context_sync_runs(started_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_source_configs_enabled ON source_configs(enabled, priority)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_source_items_dedupe ON source_items(dedupe_key)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_signal_candidates_dedupe ON signal_candidates(dedupe_key)",
    "CREATE INDEX IF NOT EXISTS idx_signals_dedupe ON signals(signal_date, dedupe_key)",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started ON pipeline_runs(started_at DESC)",
]


MIGRATION_COLUMNS = {
    "source_routes": {
        "pipeline_run_id": "INTEGER",
    },
    "source_items": {
        "pipeline_run_id": "INTEGER",
        "dedupe_key": "TEXT",
    },
    "signal_candidates": {
        "pipeline_run_id": "INTEGER",
        "dedupe_key": "TEXT",
    },
    "signals": {
        "pipeline_run_id": "INTEGER",
        "dedupe_key": "TEXT",
        "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        "archived_reason": "TEXT",
    },
    "user_settings": {
        "generate_mode": "TEXT NOT NULL DEFAULT 'mock'",
        "sync_before_briefing": "INTEGER NOT NULL DEFAULT 1",
        "context_sync_interval_minutes": "INTEGER NOT NULL DEFAULT 360",
        "max_interest_keywords": "INTEGER NOT NULL DEFAULT 50",
    },
    "interest_graph": {
        "status": "TEXT NOT NULL DEFAULT 'active'",
    },
}
