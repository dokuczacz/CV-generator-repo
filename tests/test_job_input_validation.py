from function_app import _is_http_url, _looks_like_job_posting_text


def test_is_http_url_detects_valid_urls():
    assert _is_http_url("https://jobs.example.com/offer/123") is True
    assert _is_http_url("http://example.org/job") is True
    assert _is_http_url("jobs.example.com/offer") is False


def test_job_posting_text_accepts_realistic_posting():
    text = (
        "Operational Excellence Manager - Vibe-X\n"
        "What you'll do: Lead performance improvement projects, drive standard work and VSM, "
        "facilitate workshops, and support value-chain diagnostics.\n"
        "What we're looking for: Hands-on cycle-time reduction, Lean Six Sigma, manufacturing background, "
        "strong communication and leadership skills."
    )
    ok, reason = _looks_like_job_posting_text(text)
    assert ok is True
    assert reason.startswith("ok_")


def test_job_posting_text_rejects_candidate_notes():
    text = (
        "ok in GL solution I created from scratch construction company, "
        "in Expondo I solved quality issue and reduced claims by 70%, "
        "in Sumitomo I built team and this is referring to my experience."
    )
    ok, reason = _looks_like_job_posting_text(text)
    assert ok is False
    assert reason == "looks_like_candidate_notes"


def test_job_posting_text_rejects_too_short_input():
    ok, reason = _looks_like_job_posting_text("Senior engineer role")
    assert ok is False
    assert reason == "too_short"
