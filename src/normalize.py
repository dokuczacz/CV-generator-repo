from __future__ import annotations

import re
from typing import Any, Dict


_SPECIALIZATION_LINE_RE = re.compile(
    r"(?i)^\s*(specialization|major|focus|concentration|schwerpunkt|fachrichtung|vertiefung)\s*:\s*(.+?)\s*$"
)


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

    # Transform work_experience from GPT schema to template schema.
    # IMPORTANT: Do not overwrite already-template-shaped entries.
    work_exp = normalized.get("work_experience", [])
    if work_exp and isinstance(work_exp, list):
        needs_transform = False
        for job in work_exp:
            if not isinstance(job, dict):
                continue
            # Heuristic: GPT schema uses company/position/start_date/end_date; template uses employer/title/date_range.
            if any(k in job for k in ("company", "position", "start_date", "end_date", "description")):
                needs_transform = True
                break

        if needs_transform:
            transformed_work = []
            for job in work_exp:
                if not isinstance(job, dict):
                    continue

                start = job.get("start_date", "")
                end = job.get("end_date", "")
                date_range = f"{start} – {end}" if start or end else ""

                bullets = []
                if job.get("bullets") and isinstance(job.get("bullets"), list):
                    bullets = job.get("bullets")
                elif job.get("description"):
                    bullets = [job.get("description")]

                transformed = {
                    "date_range": date_range,
                    "employer": job.get("company", ""),
                    "location": job.get("location", ""),
                    "title": job.get("position", ""),
                    "bullets": bullets,
                }
                transformed_work.append(transformed)
            normalized["work_experience"] = transformed_work

    # Transform education from GPT schema to template schema.
    # IMPORTANT: Do not overwrite already-template-shaped entries.
    education = normalized.get("education", [])
    if education and isinstance(education, list):
        needs_transform = False
        for edu in education:
            if not isinstance(edu, dict):
                continue
            if any(k in edu for k in ("school", "degree", "field", "start_date", "end_date")):
                needs_transform = True
                break

        if needs_transform:
            transformed_edu = []
            for edu in education:
                if not isinstance(edu, dict):
                    continue

                start = edu.get("start_date", "")
                end = edu.get("end_date", "")
                date_range = f"{start} – {end}" if start or end else ""

                degree = edu.get("degree", "")
                field = edu.get("field", "")
                title = f"{degree} {field}".strip() if degree or field else ""

                specialization = ""
                for k in ("specialization", "major", "focus", "concentration"):
                    v = edu.get(k)
                    if isinstance(v, str) and v.strip():
                        specialization = v.strip()
                        break

                transformed = {
                    "date_range": date_range,
                    "institution": edu.get("school", ""),
                    "title": title,
                    "details": [],
                }
                if specialization:
                    transformed["specialization"] = specialization
                transformed_edu.append(transformed)
            normalized["education"] = transformed_edu

    # Normalize education specialization presentation:
    # - If `details` contains a "Specialization: X" line, lift it into `specialization`
    #   and remove it from details to avoid duplication.
    education2 = normalized.get("education", [])
    if education2 and isinstance(education2, list):
        out_edu: list[dict[str, Any]] = []
        for edu in education2:
            if not isinstance(edu, dict):
                continue
            edu2 = dict(edu)
            if not isinstance(edu2.get("details"), list):
                edu2["details"] = []

            if not (isinstance(edu2.get("specialization"), str) and edu2["specialization"].strip()):
                details: list[Any] = edu2.get("details") or []
                specialization_val = ""
                new_details: list[Any] = []
                for d in details:
                    if specialization_val:
                        new_details.append(d)
                        continue
                    if not isinstance(d, str):
                        new_details.append(d)
                        continue
                    m = _SPECIALIZATION_LINE_RE.match(d)
                    if m:
                        specialization_val = m.group(2).strip()
                        continue
                    new_details.append(d)
                if specialization_val:
                    edu2["specialization"] = specialization_val
                    edu2["details"] = new_details

            out_edu.append(edu2)
        normalized["education"] = out_edu

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

    # Skills: template expects `it_ai_skills` (list[str]).
    # Many payloads use `skills` instead; map it conservatively.
    if "it_ai_skills" not in normalized and "skills" in normalized:
        skills = normalized.get("skills")
        if isinstance(skills, list):
            normalized["it_ai_skills"] = [str(x).strip() for x in skills if str(x).strip()]

    # Support alternate privacy field name.
    if "data_privacy" not in normalized and "data_privacy_consent" in normalized:
        normalized["data_privacy"] = normalized.get("data_privacy_consent")

    # Summary/profile: template uses `profile` (string). Some payloads use `summary`.
    if "profile" not in normalized and "summary" in normalized:
        summary_text = normalized.get("summary")
        if isinstance(summary_text, str) and summary_text.strip():
            normalized["profile"] = summary_text

    # Support professional summary list by mapping to legacy `profile` (even if template doesn't render it).
    summary = normalized.get("professional_summary")
    if "profile" not in normalized and summary:
        if isinstance(summary, list):
            normalized["profile"] = " ".join([str(x).strip() for x in summary if str(x).strip()])
        elif isinstance(summary, str):
            normalized["profile"] = summary

    return normalized
