from __future__ import annotations

from typing import Any, Dict


def normalize_cv_data(cv_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize incoming CV JSON into the shape expected by the template/validator.

    This is intentionally conservative: it only performs safe shape conversions.
    """

    normalized: Dict[str, Any] = dict(cv_data)

    # Support alternate name field: 'name' -> 'full_name'
    if "full_name" not in normalized and "name" in normalized:
        normalized["full_name"] = normalized.get("name")

    # Support alternate work_experience field names
    if "work_experience" not in normalized:
        if "experience" in normalized:
            normalized["work_experience"] = normalized.get("experience")
        elif "employment" in normalized:
            normalized["work_experience"] = normalized.get("employment")

    # Transform work_experience from GPT schema to template schema
    work_exp = normalized.get("work_experience", [])
    if work_exp and isinstance(work_exp, list):
        transformed_work = []
        for job in work_exp:
            if not isinstance(job, dict):
                continue
            
            # Build date_range from start_date/end_date
            start = job.get("start_date", "")
            end = job.get("end_date", "")
            date_range = f"{start} – {end}" if start or end else ""
            
            # Transform to template schema
            transformed = {
                "date_range": date_range,
                "employer": job.get("company", ""),
                "location": job.get("location", ""),
                "title": job.get("position", ""),
                "bullets": [job.get("description", "")] if job.get("description") else []
            }
            transformed_work.append(transformed)
        normalized["work_experience"] = transformed_work

    # Transform education from GPT schema to template schema
    education = normalized.get("education", [])
    if education and isinstance(education, list):
        transformed_edu = []
        for edu in education:
            if not isinstance(edu, dict):
                continue
            
            # Build date_range from start_date/end_date
            start = edu.get("start_date", "")
            end = edu.get("end_date", "")
            date_range = f"{start} – {end}" if start or end else ""
            
            # Build title from degree + field
            degree = edu.get("degree", "")
            field = edu.get("field", "")
            title = f"{degree} {field}".strip() if degree or field else ""
            
            # Transform to template schema
            transformed = {
                "date_range": date_range,
                "institution": edu.get("school", ""),
                "title": title,
                "details": []
            }
            transformed_edu.append(transformed)
        normalized["education"] = transformed_edu

    # Ensure further_experience exists (can be empty)
    if "further_experience" not in normalized:
        normalized["further_experience"] = []

    # Ensure languages exists (can be empty)
    if "languages" not in normalized:
        normalized["languages"] = []

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
