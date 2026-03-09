from __future__ import annotations

from src import product_config


def normalize_execution_strategy(raw: str | None) -> str:
    """Normalize user/session execution strategy to: separate | unified | auto."""
    val = str(raw or "").strip().lower()
    if val in {"separate", "multi", "multi_call", "multi-call", "stage", "staged", "legacy"}:
        return "separate"
    if val in {"unified", "single", "single_call", "single-call", "one_call", "one-call"}:
        return "unified"
    if val in {"auto", ""}:
        return "auto"
    return "auto"


def resolve_execution_strategy(*, payload: dict | None, meta: dict | None) -> tuple[str, str]:
    """Resolve effective strategy with precedence: payload -> session -> config -> experiment mode."""
    payload_val = normalize_execution_strategy((payload or {}).get("execution_strategy"))
    if payload_val in {"separate", "unified"}:
        return payload_val, "payload"

    meta_val = normalize_execution_strategy((meta or {}).get("execution_strategy"))
    if meta_val in {"separate", "unified"}:
        return meta_val, "session"

    cfg_val = normalize_execution_strategy(getattr(product_config, "CV_EXECUTION_STRATEGY", "auto"))
    if cfg_val in {"separate", "unified"}:
        return cfg_val, "config"

    # Backward compatibility with existing experiment knobs.
    experiment_mode = str(getattr(product_config, "EXPERIMENT_MODE", "baseline") or "baseline").strip().lower()
    if experiment_mode in {"variant_split", "variant_unified"}:
        return "unified", "experiment_mode"
    return "separate", "experiment_mode"
