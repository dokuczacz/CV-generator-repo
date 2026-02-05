import os


def test_bulk_translation_output_budget_minimum(monkeypatch):
    monkeypatch.setenv("CV_BULK_TRANSLATION_MIN_OUTPUT_TOKENS", "2400")
    monkeypatch.setenv("CV_BULK_TRANSLATION_MAX_OUTPUT_TOKENS", "900")  # misconfigured / too low

    from function_app import _bulk_translation_output_budget

    budget = _bulk_translation_output_budget(user_text="x" * 1000, requested_tokens=900)
    assert budget >= 2400


def test_bulk_translation_output_budget_caps(monkeypatch):
    monkeypatch.delenv("CV_BULK_TRANSLATION_MIN_OUTPUT_TOKENS", raising=False)
    monkeypatch.delenv("CV_BULK_TRANSLATION_MAX_OUTPUT_TOKENS", raising=False)

    from function_app import _bulk_translation_output_budget

    budget = _bulk_translation_output_budget(user_text="x" * 100_000, requested_tokens=50_000)
    assert budget <= 8192

