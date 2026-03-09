from __future__ import annotations

from src import product_config
from src.orchestrator.wizard.execution_strategy import resolve_execution_strategy


def test_payload_override_wins_over_experiment_mode(monkeypatch) -> None:
    monkeypatch.setattr(product_config, "CV_EXECUTION_STRATEGY", "auto", raising=False)
    monkeypatch.setattr(product_config, "EXPERIMENT_MODE", "variant_unified", raising=False)

    strategy, source = resolve_execution_strategy(
        payload={"execution_strategy": "separate"},
        meta={"execution_strategy": "unified"},
    )

    assert strategy == "separate"
    assert source == "payload"


def test_session_strategy_wins_over_config(monkeypatch) -> None:
    monkeypatch.setattr(product_config, "CV_EXECUTION_STRATEGY", "unified", raising=False)
    monkeypatch.setattr(product_config, "EXPERIMENT_MODE", "baseline", raising=False)

    strategy, source = resolve_execution_strategy(
        payload={},
        meta={"execution_strategy": "separate"},
    )

    assert strategy == "separate"
    assert source == "session"


def test_auto_uses_experiment_mode_fallback(monkeypatch) -> None:
    monkeypatch.setattr(product_config, "CV_EXECUTION_STRATEGY", "auto", raising=False)
    monkeypatch.setattr(product_config, "EXPERIMENT_MODE", "variant_split", raising=False)

    strategy, source = resolve_execution_strategy(payload={}, meta={})

    assert strategy == "unified"
    assert source == "experiment_mode"
