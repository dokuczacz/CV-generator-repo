from __future__ import annotations

from typing import Any, Dict


def normalize_cv_data(cv_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize incoming CV JSON into the shape expected by the template/validator.

    This is intentionally conservative: it only performs safe shape conversions.
    """

    normalized: Dict[str, Any] = dict(cv_data)

    # Interests: template expects a string.
    interests = normalized.get("interests")
    if isinstance(interests, list):
        # Join list items into a readable single line.
        normalized["interests"] = "; ".join([str(x).strip() for x in interests if str(x).strip()])

    # Support alternate privacy field name.
    if "data_privacy" not in normalized and "data_privacy_consent" in normalized:
        normalized["data_privacy"] = normalized.get("data_privacy_consent")

    # Support professional summary list by mapping to legacy `profile` (even if template doesn't render it).
    summary = normalized.get("professional_summary")
    if "profile" not in normalized and summary:
        if isinstance(summary, list):
            normalized["profile"] = " ".join([str(x).strip() for x in summary if str(x).strip()])
        elif isinstance(summary, str):
            normalized["profile"] = summary

    return normalized
