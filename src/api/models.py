from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SettingsUpdate(BaseModel):
    signal_count: Optional[int] = Field(default=None, ge=1)
    briefing_time: Optional[str] = None
    timezone: Optional[str] = None
    enabled_sources_json: Optional[List[str]] = None
    enabled_connectors_json: Optional[Dict[str, bool]] = None
    desktop_push_enabled: Optional[bool] = None
    generate_mode: Optional[str] = None
    sync_before_briefing: Optional[bool] = None
    context_sync_interval_minutes: Optional[int] = Field(default=None, ge=1)
    max_interest_keywords: Optional[int] = Field(default=None, ge=1)
    mode_enabled: Optional[bool] = None


class OnboardingRequest(BaseModel):
    role: str = ""
    role_detail: str = ""
    goals: List[str] = Field(default_factory=list)
    interest_types: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    preferred_signal_count: Optional[int] = Field(default=None, ge=1)
    briefing_time: Optional[str] = None
    connectors: Dict[str, bool] = Field(default_factory=dict)


class ConnectorUpdate(BaseModel):
    enabled: bool
    config: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    event_type: str
    payload: Optional[Dict[str, Any]] = None
