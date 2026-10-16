"""LUMOS v2 Hybrid Briefing Engine.

This module implements cooperative collection, job queuing, tiered importance
evaluation, LLM routing with caching, and personalised recommendation with
cost controls.

SAFETY: The engine is designed to be import-safe.  Importing this package
does NOT start any background tasks, schedulers, or external API calls.
All external interactions require explicit activation via configuration
flags AND runtime permission checks.
"""

ENGINE_VERSION = "2.0.0-alpha"
ENGINE_ENABLED_DEFAULT = False
