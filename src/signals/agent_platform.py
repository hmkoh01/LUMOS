"""Isolated Gemini Enterprise Agent Platform client configuration.

This module deliberately never reads ``GEMINI_API_KEY``.  It prevents the
briefing experiment from accidentally falling back to Gemini Developer API.
"""
from __future__ import annotations

import importlib.metadata
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class AgentPlatformConfigurationError(RuntimeError):
    """Raised before any Agent Platform client or request is created."""


def _version_at_least(installed: str, minimum: str) -> bool:
    def parse(value: str) -> tuple:
        return tuple(int(part) for part in value.split(".")[:3])
    return parse(installed) >= parse(minimum)


@dataclass(frozen=True)
class AgentPlatformConfig:
    api_key: str = field(repr=False)
    project: str
    location: str
    min_sdk_version: str = "2.30.1"

    @classmethod
    def from_env(cls) -> "AgentPlatformConfig":
        if os.environ.get("GOOGLE_GENAI_USE_ENTERPRISE", "").strip().lower() != "true":
            raise AgentPlatformConfigurationError("GOOGLE_GENAI_USE_ENTERPRISE=true is required")
        api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "").strip()
        if not api_key or not project or not location:
            raise AgentPlatformConfigurationError(
                "GOOGLE_API_KEY, GOOGLE_CLOUD_PROJECT, and GOOGLE_CLOUD_LOCATION are required"
            )
        return cls(api_key=api_key, project=project, location=location)

    def create_client(self, factory: Optional[Callable[..., Any]] = None) -> Any:
        """Create an Enterprise-only client with one HTTP attempt per call."""
        if factory is None:
            installed = importlib.metadata.version("google-genai")
            if not _version_at_least(installed, self.min_sdk_version):
                raise AgentPlatformConfigurationError(
                    f"google-genai>={self.min_sdk_version} required for Agent Platform; found {installed}"
                )
            from google import genai
            from google.genai import types
            factory = genai.Client
            return factory(
                enterprise=True,
                api_key=self.api_key,
                project=self.project,
                location=self.location,
                http_options=types.HttpOptions(
                    api_version="v1",
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        return factory(
            enterprise=True,
            api_key=self.api_key,
            project=self.project,
            location=self.location,
            retry_attempts=1,
            api_version="v1",
        )
