from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SettingsUpdate(BaseModel):
    signal_count: Optional[int] = Field(default=None, ge=1)
    briefing_time: Optional[str] = None
    timezone: Optional[str] = None
    enabled_sources_json: Optional[List[str]] = None
    enabled_connectors_json: Optional[Dict[str, bool]] = None
    desktop_push_enabled: Optional[bool] = None
    generate_mode: Optional[str] = None
    max_interest_keywords: Optional[int] = Field(default=None, ge=1)
    mode_enabled: Optional[bool] = None
    source_region_preference: Optional[str] = None


class OnboardingRequest(BaseModel):
    role: str = ""
    role_detail: str = ""
    goals: List[str] = Field(default_factory=list)
    interest_types: List[str] = Field(default_factory=list)
    interest_type_preferences: Dict[str, List[str]] = Field(default_factory=dict)
    source_hints: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    preferred_signal_count: Optional[int] = Field(default=None, ge=1)
    briefing_time: Optional[str] = None
    connectors: Dict[str, bool] = Field(default_factory=dict)


class OnboardingPreviewRequest(BaseModel):
    keywords: List[str] = Field(default_factory=list)
    interest_type_preferences: Dict[str, List[str]] = Field(default_factory=dict)


class InformationTypePreferencesUpdate(BaseModel):
    """Optional, per-interest reader choices used by the existing router."""

    interest_type_preferences: Dict[str, List[str]] = Field(default_factory=dict)


class FeedbackLearningSettingsUpdate(BaseModel):
    enabled: bool


class FeedbackLearningRuleReset(BaseModel):
    feature: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=128)


class ConnectorUpdate(BaseModel):
    enabled: bool
    config: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    event_type: str
    payload: Optional[Dict[str, Any]] = None


class SavedSignalUpdate(BaseModel):
    saved: bool


class RecommendationPreferenceUpdate(BaseModel):
    preference: Optional[Literal["tracked", "ignored"]] = None


class RecommendationReasonUpdate(BaseModel):
    preference: Literal["tracked", "ignored"]
    reason_code: str = Field(min_length=1, max_length=64)
