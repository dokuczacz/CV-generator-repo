#!/usr/bin/env python3
"""
Estimate if CV content fits within 2-page template.

Usage:
    python count_template_space.py <cv-json-file> --language=en

Returns page estimation with safety margin.
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any


# Template space allocation (lines available per section, 2-page template)
TEMPLATE_LINES = {
    "header": 6,  # Name, title, contact info, photo
    "experience": 45,  # Main section, most space
    "education": 12,  # Education section
    "skills": 8,  # Skills section
    "languages": 5,  # Languages section
    "certifications": 6,  # Certifications section
    "footer": 2,  # Footer
}

# Characters per line (average, depends on font size and margins)
CHARS_PER_LINE = {
    "header": 60,
    "experience_title": 80,  # Job title + company
    "experience_bullet": 90,  # Responsibility bullet
    "education": 70,
    "skills": 50,
    "languages": 40,
}

# Language-specific multipliers (some languages use longer words)
LANGUAGE_MULTIPLIERS = {
    "en": 1.0,
    "de": 1.15,  # German words 15% longer on average
    "pl": 1.10,  # Polish words 10% longer
}

# Total lines available in 2-page template
TOTAL_LINES_AVAILABLE = sum(TEMPLATE_LINES.values())


def estimate_header_lines(data: Dict[str, Any]) -> int:
    """Estimate lines needed for header section."""
    lines = 3  # Name, professional title, contact (email/phone/address)
    if data.get("photo_url"):
        lines += 0  # Photo is inline, doesn't add lines
    return min(lines, TEMPLATE_LINES["header"])


def estimate_experience_lines(data: Dict[str, Any], lang: str = "en") -> int:
    """Estimate lines needed for experience section."""
    if "experience" not in data or not data["experience"]:
        return 0

    lines = 0
    multiplier = LANGUAGE_MULTIPLIERS.get(lang, 1.0)

    for exp in data["experience"]:
        # Job title + company + dates (1-2 lines)
        title_text = f"{exp.get('position', '')} - {exp.get('company', '')}"
        title_lines = max(1, int(len(title_text) * multiplier / CHARS_PER_LINE["experience_title"]) + 1)
        lines += title_lines

        # Responsibilities (1 line per bullet, unless long)
        if "responsibilities" in exp and exp["responsibilities"]:
            for bullet in exp["responsibilities"]:
                bullet_lines = max(1, int(len(bullet) * multiplier / CHARS_PER_LINE["experience_bullet"]) + 1)
                lines += bullet_lines

        # Spacing between entries
        lines += 1

    return lines


def estimate_education_lines(data: Dict[str, Any], lang: str = "en") -> int:
    """Estimate lines needed for education section."""
    if "education" not in data or not data["education"]:
        return 0

    lines = 0
    multiplier = LANGUAGE_MULTIPLIERS.get(lang, 1.0)

    for edu in data["education"]:
        # Degree + institution (1-2 lines)
        edu_text = f"{edu.get('degree', '')} - {edu.get('institution', '')}"
        edu_lines = max(1, int(len(edu_text) * multiplier / CHARS_PER_LINE["education"]) + 1)
        lines += edu_lines

        # Spacing
        lines += 1

    return lines


def estimate_skills_lines(data: Dict[str, Any]) -> int:
    """Estimate lines needed for skills section."""
    if "skills" not in data or not data["skills"]:
        return 0

    # Skills are comma-separated, wrap based on line length
    total_chars = sum(len(skill) for skill in data["skills"]) + (len(data["skills"]) * 2)  # +2 for ", "
    lines = max(1, int(total_chars / CHARS_PER_LINE["skills"]) + 1)

    return min(lines, TEMPLATE_LINES["skills"])


def estimate_languages_lines(data: Dict[str, Any]) -> int:
    """Estimate lines needed for languages section."""
    if "languages" not in data or not data["languages"]:
        return 0

    # Languages: "Language (Level)", wrap based on line length
    total_chars = sum(len(f"{lang.get('language', '')} ({lang.get('level', '')})") for lang in data["languages"])
    lines = max(1, int(total_chars / CHARS_PER_LINE["languages"]) + 1)

    return min(lines, TEMPLATE_LINES["languages"])


def estimate_certifications_lines(data: Dict[str, Any]) -> int:
    """Estimate lines needed for certifications section."""
    if "certifications" not in data or not data["certifications"]:
        return 0

    # Each certification: 1 line (name + date)
    lines = len(data["certifications"])

    return min(lines, TEMPLATE_LINES["certifications"])


def estimate_total_pages(data: Dict[str, Any], lang: str = "en") -> Dict[str, Any]:
    """
    Estimate total pages needed for CV content.

    Returns:
        Dictionary with page estimation and breakdown
    """
    # Calculate lines per section
    header_lines = estimate_header_lines(data)
    experience_lines = estimate_experience_lines(data, lang)
    education_lines = estimate_education_lines(data, lang)
    skills_lines = estimate_skills_lines(data)
    languages_lines = estimate_languages_lines(data)
    certifications_lines = estimate_certifications_lines(data)
    footer_lines = TEMPLATE_LINES["footer"]

    total_lines = (
        header_lines +
        experience_lines +
        education_lines +
        skills_lines +
        languages_lines +
        certifications_lines +
        footer_lines
    )

    # Convert lines to pages (assuming evenly distributed)
    lines_per_page = TOTAL_LINES_AVAILABLE / 2.0
    estimated_pages = total_lines / lines_per_page

    # Calculate margin
    margin_percent = ((TOTAL_LINES_AVAILABLE - total_lines) / TOTAL_LINES_AVAILABLE) * 100

    # Determine status
    if estimated_pages <= 1.8:
        status = "SAFE"
    elif estimated_pages <= 2.0:
        status = "WARNING"
    else:
        status = "ERROR"

    return {
        "estimated_pages": round(estimated_pages, 2),
        "total_lines_used": total_lines,
        "total_lines_available": TOTAL_LINES_AVAILABLE,
        "margin_percent": round(margin_percent, 1),
        "status": status,
        "breakdown": {
            "header": header_lines,
            "experience": experience_lines,
            "education": education_lines,
            "skills": skills_lines,
            "languages": languages_lines,
            "certifications": certifications_lines,
            "footer": footer_lines,
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Estimate CV page count")
    parser.add_argument("cv_file", help="Path to CV JSON file")
    parser.add_argument("--language", default="en", choices=["en", "de", "pl"], help="CV language")
    args = parser.parse_args()

    # Load CV data
    cv_path = Path(args.cv_file)
    if not cv_path.exists():
        print(json.dumps({"error": f"File not found: {args.cv_file}"}), file=sys.stderr)
        sys.exit(1)

    try:
        with open(cv_path, "r", encoding="utf-8") as f:
            cv_data = json.load(f)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}), file=sys.stderr)
        sys.exit(1)

    # Estimate pages
    result = estimate_total_pages(cv_data, lang=args.language)

    # Output JSON
    print(json.dumps(result, indent=2))

    # Exit code based on status
    sys.exit(0 if result["status"] != "ERROR" else 1)


if __name__ == "__main__":
    main()