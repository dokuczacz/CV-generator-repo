#!/usr/bin/env python3
"""
Fast local CV JSON schema validation.

Usage:
    python validate_schema.py <cv-json-file>
    python validate_schema.py <cv-json-file> --strict

Returns JSON with validation results.
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any, Tuple


# Required fields (must be present and non-empty)
REQUIRED_FIELDS = [
    "firstName",
    "lastName",
    "email",
    "phone",
    "address",
    "professionalTitle"
]

# Size constraints
MAX_PHOTO_URL_SIZE = 32000  # bytes (32KB, Azure Table limit is 64KB, use margin)
MAX_BULLET_LENGTH = 90  # characters
MAX_SKILL_LENGTH = 50  # characters

# Field type expectations
FIELD_TYPES = {
    "firstName": str,
    "lastName": str,
    "email": str,
    "phone": str,
    "address": str,
    "professionalTitle": str,
    "photo_url": (str, type(None)),
    "languages": list,
    "skills": list,
    "experience": list,
    "education": list,
    "certifications": list,
}


def validate_required_fields(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Check that all required fields are present and non-empty."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append({
                "field": field,
                "severity": "HIGH",
                "message": f"Missing required field '{field}'"
            })
        elif not data[field] or (isinstance(data[field], str) and not data[field].strip()):
            errors.append({
                "field": field,
                "severity": "HIGH",
                "message": f"Required field '{field}' is empty"
            })
    return errors


def validate_field_types(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Check that fields have expected types."""
    errors = []
    for field, expected_type in FIELD_TYPES.items():
        if field in data and data[field] is not None:
            if not isinstance(data[field], expected_type):
                errors.append({
                    "field": field,
                    "severity": "MEDIUM",
                    "message": f"Field '{field}' has wrong type (expected {expected_type.__name__}, got {type(data[field]).__name__})"
                })
    return errors


def validate_photo_url_size(data: Dict[str, Any]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Check photo_url size constraint."""
    errors = []
    warnings = []

    if "photo_url" in data and data["photo_url"]:
        photo_size = len(data["photo_url"])

        if photo_size > MAX_PHOTO_URL_SIZE:
            errors.append({
                "field": "photo_url",
                "severity": "HIGH",
                "message": f"photo_url exceeds {MAX_PHOTO_URL_SIZE} bytes (current: {photo_size} bytes). Azure Table Storage limit."
            })
        elif photo_size > MAX_PHOTO_URL_SIZE * 0.9:  # 90% threshold
            warnings.append({
                "field": "photo_url",
                "severity": "LOW",
                "message": f"photo_url is {photo_size} bytes, close to {MAX_PHOTO_URL_SIZE} bytes limit ({int(photo_size/MAX_PHOTO_URL_SIZE*100)}% used)"
            })

    return errors, warnings


def validate_bullet_lengths(data: Dict[str, Any]) -> Tuple[List[Dict[str, str]], int]:
    """Check that all responsibility bullets are within character limit."""
    errors = []
    max_bullet_length = 0

    if "experience" in data and isinstance(data["experience"], list):
        for i, exp in enumerate(data["experience"]):
            if "responsibilities" in exp and isinstance(exp["responsibilities"], list):
                for j, bullet in enumerate(exp["responsibilities"]):
                    bullet_len = len(bullet)
                    max_bullet_length = max(max_bullet_length, bullet_len)

                    if bullet_len > MAX_BULLET_LENGTH:
                        errors.append({
                            "field": f"experience[{i}].responsibilities[{j}]",
                            "severity": "HIGH",
                            "message": f"Bullet exceeds {MAX_BULLET_LENGTH} chars (current: {bullet_len} chars): \"{bullet[:50]}...\""
                        })

    return errors, max_bullet_length


def validate_email_format(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Basic email format validation."""
    errors = []

    if "email" in data and data["email"]:
        email = data["email"]
        if "@" not in email or "." not in email.split("@")[-1]:
            errors.append({
                "field": "email",
                "severity": "MEDIUM",
                "message": f"Email format appears invalid: {email}"
            })

    return errors


def validate_date_formats(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Check that dates are in ISO format (YYYY-MM-DD) or null."""
    errors = []

    if "experience" in data and isinstance(data["experience"], list):
        for i, exp in enumerate(data["experience"]):
            for date_field in ["startDate", "endDate"]:
                if date_field in exp and exp[date_field] is not None:
                    date_str = exp[date_field]
                    # Simple check: YYYY-MM-DD format
                    if not (isinstance(date_str, str) and len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-"):
                        errors.append({
                            "field": f"experience[{i}].{date_field}",
                            "severity": "MEDIUM",
                            "message": f"Date format should be YYYY-MM-DD (current: {date_str})"
                        })

    if "education" in data and isinstance(data["education"], list):
        for i, edu in enumerate(data["education"]):
            for date_field in ["startDate", "endDate"]:
                if date_field in edu and edu[date_field] is not None:
                    date_str = edu[date_field]
                    if not (isinstance(date_str, str) and len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-"):
                        errors.append({
                            "field": f"education[{i}].{date_field}",
                            "severity": "MEDIUM",
                            "message": f"Date format should be YYYY-MM-DD (current: {date_str})"
                        })

    return errors


def validate_cv_schema(data: Dict[str, Any], strict: bool = False) -> Dict[str, Any]:
    """
    Main validation function.

    Args:
        data: CV JSON data
        strict: Enable stricter ATS compliance checks

    Returns:
        Validation result with errors and warnings
    """
    all_errors = []
    all_warnings = []

    # Run all validation checks
    all_errors.extend(validate_required_fields(data))
    all_errors.extend(validate_field_types(data))

    photo_errors, photo_warnings = validate_photo_url_size(data)
    all_errors.extend(photo_errors)
    all_warnings.extend(photo_warnings)

    bullet_errors, max_bullet_len = validate_bullet_lengths(data)
    all_errors.extend(bullet_errors)

    all_errors.extend(validate_email_format(data))
    all_errors.extend(validate_date_formats(data))

    # Build result
    result = {
        "valid": len(all_errors) == 0,
        "errors": all_errors,
        "warnings": all_warnings,
        "stats": {
            "max_bullet_length": max_bullet_len,
            "photo_url_size": len(data.get("photo_url", "")) if data.get("photo_url") else 0,
            "required_fields_present": sum(1 for f in REQUIRED_FIELDS if f in data and data[f])
        }
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Validate CV JSON schema")
    parser.add_argument("cv_file", help="Path to CV JSON file")
    parser.add_argument("--strict", action="store_true", help="Enable strict ATS compliance checks")
    args = parser.parse_args()

    # Load CV data
    cv_path = Path(args.cv_file)
    if not cv_path.exists():
        print(json.dumps({"valid": False, "errors": [{"message": f"File not found: {args.cv_file}"}]}), file=sys.stderr)
        sys.exit(1)

    try:
        with open(cv_path, "r", encoding="utf-8") as f:
            cv_data = json.load(f)
    except json.JSONDecodeError as e:
        print(json.dumps({"valid": False, "errors": [{"message": f"Invalid JSON: {e}"}]}), file=sys.stderr)
        sys.exit(1)

    # Validate
    result = validate_cv_schema(cv_data, strict=args.strict)

    # Output JSON
    print(json.dumps(result, indent=2))

    # Exit code based on validation result
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
