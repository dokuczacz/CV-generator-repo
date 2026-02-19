"""
Product configuration: centralized magic numbers, limits, toggles, and retry policies.

This module replaces scattered os.environ.get() calls and hardcoded constants.
- Hard limits are NOT configurable (security/template bounds).
- Toggles and retries CAN be overridden via env vars for labs/testing.
- Defaults are production-ready.

Environment vars (optional overrides):
  CV_ENABLE_AI=0/1
  CV_ENABLE_COVER_LETTER=0/1
  CV_REQUIRE_JOB_TEXT=0/1
  OPENAI_MODEL=<str>
  OPENAI_STORE=0/1
  OPENAI_JSON_SCHEMA_MAX_ATTEMPTS=<int>
  OPENAI_DASHBOARD_INCLUDE_SYSTEM_PROMPT=0/1
  CV_SINGLE_CALL_EXECUTION=0/1
  USE_STRUCTURED_OUTPUT=0/1
  CV_BULK_TRANSLATION_MIN_OUTPUT_TOKENS=<int>
  CV_BULK_TRANSLATION_MAX_OUTPUT_TOKENS=<int>
  CV_MAX_MODEL_CALLS / CV_MAX_TURNS=<int>
  CV_EXECUTION_LATCH=0/1
  CV_DELTA_MODE=0/1
  CV_PDF_ALWAYS_REGENERATE=0/1
  STORAGE_CONTAINER_PDFS=<str>
  STORAGE_CONTAINER_ARTIFACTS=<str>

Lab / Debug vars (development only):
  CV_OPENAI_TRACE=0/1
  CV_OPENAI_TRACE_DIR=<path>
  CV_OPENAI_TRACE_FULL=0/1
  CV_CONTEXT_PACK_MODE=<str>
  CV_DEBUG_PROMPT_LOG=0/1
  CV_GENERATION_STRICT_TEMPLATE=0/1
  CV_ENABLE_DEBUG_EXPORT=0/1
  REQUIRE_OPENAI_PROMPT_ID=0/1
  REQUIRE_OPENAI_PROMPT_ID_PER_STAGE=0/1
  OPENAI_PROMPT_ID=<str>
  OPENAI_PROMPT_ID_<STAGE>=<str>
"""

import os
from typing import Any


# ============================================================================
# HARD LIMITS (non-configurable, security-critical, template-critical)
# ============================================================================

# Work experience bullets: absolute maximum character count per bullet.
WORK_EXPERIENCE_HARD_LIMIT_CHARS: int = 200

# Maximum bullets per work role (cannot be overridden).
MAX_BULLETS_PER_ROLE: int = 5

# Minimum bullets per work role (don't drop below this when compressing).
MIN_BULLETS_PER_ROLE: int = 1

# Maximum CV length (pages).
MAX_PAGES_CV: int = 2

# Generic PDF text fetch limit (bytes).
MAX_TEXT_FETCH_BYTES: int = 20000

# Default text fetch timeout (seconds).
TEXT_FETCH_TIMEOUT_SEC: float = 8.0


# ============================================================================
# TOGGLES (configurable via env vars, but with sensible defaults)
# ============================================================================

def _get_bool_config(env_key: str, default: bool) -> bool:
    """Fetch a boolean config from env var; default if not set or empty."""
    val = str(os.environ.get(env_key) or "").strip()
    if not val:
        return default
    return val == "1"


def _get_int_config(env_key: str, default: int, min_val: int = None) -> int:
    """Fetch an int config from env var; enforce minimum if set."""
    val = str(os.environ.get(env_key) or "").strip()
    if not val:
        return default
    try:
        result = int(val)
        if min_val is not None:
            result = max(result, min_val)
        return result
    except ValueError:
        return default


def _get_str_config(env_key: str, default: str) -> str:
    """Fetch a string config from env var."""
    val = str(os.environ.get(env_key) or "").strip()
    return val if val else default


# Feature toggles
CV_ENABLE_AI: bool = _get_bool_config("CV_ENABLE_AI", True)
CV_ENABLE_COVER_LETTER: bool = _get_bool_config("CV_ENABLE_COVER_LETTER", False)
CV_REQUIRE_JOB_TEXT: bool = _get_bool_config("CV_REQUIRE_JOB_TEXT", False)

# OpenAI settings
OPENAI_MODEL: str = _get_str_config("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_STORE: bool = _get_bool_config("OPENAI_STORE", True)
OPENAI_JSON_SCHEMA_MAX_ATTEMPTS: int = _get_int_config("OPENAI_JSON_SCHEMA_MAX_ATTEMPTS", 2, min_val=1)
OPENAI_DASHBOARD_INCLUDE_SYSTEM_PROMPT: bool = _get_bool_config("OPENAI_DASHBOARD_INCLUDE_SYSTEM_PROMPT", True)

# Execution modes
CV_SINGLE_CALL_EXECUTION: bool = _get_bool_config("CV_SINGLE_CALL_EXECUTION", True)
USE_STRUCTURED_OUTPUT: bool = _get_bool_config("USE_STRUCTURED_OUTPUT", False)
CV_EXECUTION_LATCH: bool = _get_bool_config("CV_EXECUTION_LATCH", True)
CV_DELTA_MODE: bool = _get_bool_config("CV_DELTA_MODE", True)

# PDF generation
CV_PDF_ALWAYS_REGENERATE: bool = _get_bool_config("CV_PDF_ALWAYS_REGENERATE", False)

# Translation token limits
CV_BULK_TRANSLATION_MIN_OUTPUT_TOKENS: int = _get_int_config(
    "CV_BULK_TRANSLATION_MIN_OUTPUT_TOKENS", 2400, min_val=2400
)
CV_BULK_TRANSLATION_MAX_OUTPUT_TOKENS: int = _get_int_config(
    "CV_BULK_TRANSLATION_MAX_OUTPUT_TOKENS", 6000, min_val=6000
)

# Retry and iteration limits
CV_MAX_MODEL_CALLS: int = _get_int_config(
    "CV_MAX_MODEL_CALLS",
    _get_int_config("CV_MAX_TURNS", 5),  # Fallback to CV_MAX_TURNS if CV_MAX_MODEL_CALLS not set
    min_val=1
)

# Storage containers
STORAGE_CONTAINER_PDFS: str = _get_str_config("STORAGE_CONTAINER_PDFS", "cv-pdfs")
STORAGE_CONTAINER_ARTIFACTS: str = _get_str_config("STORAGE_CONTAINER_ARTIFACTS", "cv-artifacts")


# ============================================================================
# DEBUG / LAB VARS (development-only, not for production)
# ============================================================================

CV_OPENAI_TRACE: bool = _get_bool_config("CV_OPENAI_TRACE", False)
CV_OPENAI_TRACE_DIR: str = _get_str_config("CV_OPENAI_TRACE_DIR", "tmp/openai_trace")
CV_OPENAI_TRACE_FULL: bool = _get_bool_config("CV_OPENAI_TRACE_FULL", False)
CV_CONTEXT_PACK_MODE: str = _get_str_config("CV_CONTEXT_PACK_MODE", "").lower()
CV_DEBUG_PROMPT_LOG: bool = _get_bool_config("CV_DEBUG_PROMPT_LOG", False)
CV_GENERATION_STRICT_TEMPLATE: bool = _get_bool_config("CV_GENERATION_STRICT_TEMPLATE", False)
CV_ENABLE_DEBUG_EXPORT: bool = _get_bool_config("CV_ENABLE_DEBUG_EXPORT", False)

# Prompt ID enforcement (for labs/testing)
REQUIRE_OPENAI_PROMPT_ID: bool = _get_bool_config("REQUIRE_OPENAI_PROMPT_ID", False)
REQUIRE_OPENAI_PROMPT_ID_PER_STAGE: bool = _get_bool_config("REQUIRE_OPENAI_PROMPT_ID_PER_STAGE", False)
OPENAI_PROMPT_ID: str = _get_str_config("OPENAI_PROMPT_ID", "")


def get_stage_prompt_id(stage: str) -> str | None:
    """Get a stage-specific prompt ID override (for labs/testing)."""
    val = (os.environ.get(f"OPENAI_PROMPT_ID_{stage}") or "").strip()
    return val if val else None


# ============================================================================
# TIMEOUTS (global defaults, can be adjusted per function)
# ============================================================================

OPENAI_RESPONSE_TIMEOUT_SEC: float = 60.0
