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

    def _normalize_date_range_ascii(s: str) -> str:
        txt = " ".join(str(s or "").replace("\r", " ").replace("\n", " ").split()).strip()
        if not txt:
            return ""
        txt = txt.replace("–", "-").replace("—", "-").replace("−", "-")
        # Preserve YYYY-MM formatting (no spaces around the month dash).
        txt = re.sub(r"(\d{4})\s*-\s*(\d{2})", r"\1§§\2", txt)
        # Normalize range separators with spaces around dashes.
        txt = re.sub(r"\s*-\s*", " - ", txt)
        txt = re.sub(r"\s+", " ", txt).strip()
        txt = txt.replace("§§", "-")
        # Final safeguard: collapse any lingering YYYY - MM spacing.
        return re.sub(r"(\d{4})\s*-\s*(\d{2})", r"\1-\2", txt)

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
                # Use ASCII hyphen for PDF font compatibility (avoid tofu/□ for en-dash in some fonts).
                date_range = f"{start} - {end}" if start or end else ""

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

    # Normalize date_range separators for PDF compatibility (even for already-template-shaped entries).
    work_exp2 = normalized.get("work_experience", [])
    if isinstance(work_exp2, list) and work_exp2:
        out_work: list[dict[str, Any]] = []
        for job in work_exp2:
            if not isinstance(job, dict):
                continue
            job2: dict[str, Any] = dict(job)
            if "date_range" in job2:
                job2["date_range"] = _normalize_date_range_ascii(str(job2.get("date_range") or ""))
            # If employer is missing but embedded in title like "Role, Company", split it.
            if not str(job2.get("employer") or job2.get("company") or "").strip():
                title_raw = str(job2.get("title") or job2.get("position") or "").strip()
                if title_raw and "," in title_raw:
                    left, right = title_raw.split(",", 1)
                    left = left.strip()
                    right = right.strip()
                    if left and right:
                        job2["title"] = left
                        job2["employer"] = right
            # Canonicalize employer key if input used `company`.
            if "employer" not in job2 and "company" in job2:
                job2["employer"] = job2.get("company")
            out_work.append(job2)
        normalized["work_experience"] = out_work

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
                # Use ASCII hyphen for PDF font compatibility (avoid tofu/□ for en-dash in some fonts).
                date_range = f"{start} - {end}" if start or end else ""

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

    edu2 = normalized.get("education", [])
    if isinstance(edu2, list) and edu2:
        out_edu: list[dict[str, Any]] = []
        for edu in edu2:
            if not isinstance(edu, dict):
                continue
            edu3: dict[str, Any] = dict(edu)
            if "date_range" in edu3:
                edu3["date_range"] = _normalize_date_range_ascii(str(edu3.get("date_range") or ""))
            out_edu.append(edu3)
        normalized["education"] = out_edu

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

            def _spec_value(s: str) -> str:
                s2 = str(s or "").strip()
                m2 = _SPECIALIZATION_LINE_RE.match(s2)
                return (m2.group(2).strip() if m2 else s2).strip()

            details: list[Any] = edu2.get("details") or []
            new_details: list[Any] = []

            existing_spec_raw = edu2.get("specialization") if isinstance(edu2.get("specialization"), str) else ""
            existing_spec_val = _spec_value(existing_spec_raw) if existing_spec_raw else ""
            lifted_spec_val = ""

            for d in details:
                if not isinstance(d, str):
                    new_details.append(d)
                    continue

                m = _SPECIALIZATION_LINE_RE.match(d)
                if not m:
                    new_details.append(d)
                    continue

                d_val = (m.group(2) or "").strip()

                # If specialization already exists and matches this value, drop it from details (dedupe).
                if existing_spec_val and d_val and existing_spec_val.lower() == d_val.lower():
                    continue

                # Otherwise, lift into specialization only if specialization is empty and we haven't lifted yet.
                if (not existing_spec_val) and (not lifted_spec_val) and d_val:
                    lifted_spec_val = d_val
                    continue

                # Keep other specialization-like lines (rare, but don't delete info).
                new_details.append(d)

            if (not existing_spec_val) and lifted_spec_val:
                edu2["specialization"] = lifted_spec_val
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

    # Technical & operational skills: template expects `technical_operational_skills` (list[str]).
    # Support common alternates and string formatting.
    if "technical_operational_skills" not in normalized:
        for alt in ["tech_ops_skills", "tech_ops", "technical_skills", "operational_skills"]:
            if alt in normalized:
                normalized["technical_operational_skills"] = normalized.get(alt)
                break

    tech_ops = normalized.get("technical_operational_skills")
    if isinstance(tech_ops, str):
        parts = [p.strip() for p in re.split(r"[\n;•\u2022]", tech_ops) if p.strip()]
        normalized["technical_operational_skills"] = parts

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
