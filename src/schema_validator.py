"""
Schema validation and detection for CV data
Enforces canonical schema and detects common agent errors
"""

from typing import Dict, Any, List, Tuple, Optional


class SchemaValidationError(Exception):
    """Raised when CV data schema is incorrect"""
    pass


# Canonical schema keys (what we expect)
CANONICAL_KEYS = {
    "full_name", "email", "phone", "photo_url",
    "work_experience", "education",
    # Template-aligned fields
    "address_lines", "birth_date", "nationality",
    "profile", "it_ai_skills", "interests",
    "further_experience", "references", "data_privacy",
    # Legacy/compat fields still accepted/normalized
    "skills", "technical_operational_skills", "certifications", "summary",
    "languages", "language"
}

# Wrong keys that agents sometimes send
WRONG_KEYS = {
    "personal_info", "employment_history", "personal",
    "cv_source", "experience", "contact", "profiles",
    "metadata", "employment", "headline"
}

# Required top-level keys for minimum viable CV
REQUIRED_KEYS = {"full_name", "email", "phone", "work_experience", "education"}


def detect_schema_mismatch(cv_data: Dict[str, Any]) -> Optional[List[str]]:
    """
    Detect if agent sent wrong schema keys
    
    Args:
        cv_data: CV data dictionary to validate
    
    Returns:
        List of wrong keys found, or None if schema is correct
    """
    if not isinstance(cv_data, dict):
        return ["cv_data must be a dictionary"]
    
    found_keys = set(cv_data.keys())
    found_wrong = WRONG_KEYS & found_keys
    
    if found_wrong:
        return list(found_wrong)
    
    return None


def validate_canonical_schema(cv_data: Dict[str, Any], strict: bool = False) -> Tuple[bool, List[str]]:
    """
    Validate CV data against canonical schema
    
    Args:
        cv_data: CV data dictionary to validate
        strict: If True, require all REQUIRED_KEYS to be present
    
    Returns:
        (is_valid, error_messages)
    """
    errors = []
    
    # Check for wrong keys
    wrong_keys = detect_schema_mismatch(cv_data)
    if wrong_keys:
        errors.append(f"Wrong schema keys detected: {', '.join(wrong_keys)}")
    
    # Check for required keys (if strict mode)
    if strict:
        missing = REQUIRED_KEYS - set(cv_data.keys())
        if missing:
            errors.append(f"Missing required keys: {', '.join(missing)}")
    
    # Validate data types for key fields
    if "work_experience" in cv_data:
        if not isinstance(cv_data["work_experience"], list):
            errors.append("work_experience must be an array")
        elif len(cv_data["work_experience"]) == 0 and strict:
            errors.append("work_experience must contain at least one entry")
    
    if "education" in cv_data:
        if not isinstance(cv_data["education"], list):
            errors.append("education must be an array")
        elif len(cv_data["education"]) == 0 and strict:
            errors.append("education must contain at least one entry")
        else:
            # Validate per-entry required fields
            for i, edu in enumerate(cv_data["education"]):
                if not isinstance(edu, dict):
                    errors.append(f"education[{i}] must be an object")
                    continue
                # institution is required and must be non-empty
                inst = edu.get("institution", "")
                if not isinstance(inst, str) or not inst.strip():
                    errors.append(f"education[{i}].institution is required and must be non-empty")
                # title is required and must be non-empty
                title = edu.get("title", "")
                if not isinstance(title, str) or not title.strip():
                    errors.append(f"education[{i}].title is required and must be non-empty")
    
    if "languages" in cv_data:
        if not isinstance(cv_data["languages"], list):
            errors.append("languages must be an array")
    
    return (len(errors) == 0, errors)


