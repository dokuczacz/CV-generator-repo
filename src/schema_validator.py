"""
Schema validation and detection for CV data
Enforces canonical schema and detects common agent errors
"""

import logging
from typing import Dict, Any, List, Tuple, Optional


class SchemaValidationError(Exception):
    """Raised when CV data schema is incorrect"""
    pass


# Canonical schema keys (what we expect)
CANONICAL_KEYS = {
    "full_name", "email", "phone", "photo_url",
    "work_experience", "education", "skills",
    "languages", "certifications", "summary", "language"
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
    
    if "languages" in cv_data:
        if not isinstance(cv_data["languages"], list):
            errors.append("languages must be an array")
    
    return (len(errors) == 0, errors)


def build_schema_error_response(cv_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build helpful error response with schema guidance
    
    Args:
        cv_data: Invalid CV data
    
    Returns:
        Error response dictionary with examples
    """
    wrong_keys = detect_schema_mismatch(cv_data)
    
    return {
        "error": "Schema validation failed",
        "wrong_keys_detected": wrong_keys or [],
        "guidance": "You sent CV data with incorrect schema keys. Use the canonical schema shown below.",
        "canonical_schema": {
            "full_name": "string (required)",
            "email": "string (required)",
            "phone": "string (required)",
            "photo_url": "string (optional, data URI)",
            "work_experience": "array (required, min 1 entry)",
            "education": "array (required, min 1 entry)",
            "skills": "array (optional)",
            "languages": "array (optional)",
            "certifications": "array (optional)",
            "summary": "string (optional)",
            "language": "string (optional, e.g., 'en', 'de', 'pl')"
        },
        "example": {
            "full_name": "John Doe",
            "email": "john@example.com",
            "phone": "+1234567890",
            "work_experience": [
                {
                    "date_range": "2020-2024",
                    "employer": "Acme Corp",
                    "title": "Senior Engineer",
                    "bullets": ["Led team of 5 engineers", "Improved system performance by 40%"]
                }
            ],
            "education": [
                {
                    "date_range": "2016-2020",
                    "institution": "MIT",
                    "title": "BSc Computer Science",
                    "details": ["GPA: 3.9/4.0"]
                }
            ],
            "skills": ["Python", "React", "AWS"],
            "languages": ["English", "Spanish"],
            "language": "en"
        },
        "your_data_keys": list(cv_data.keys()) if isinstance(cv_data, dict) else "not a dict",
        "action_required": "Rebuild cv_data using the canonical schema above, then retry this tool call."
    }


def log_schema_debug_info(cv_data: Dict[str, Any], context: str = ""):
    """
    Log detailed schema debugging information
    
    Args:
        cv_data: CV data to inspect
        context: Context string for logging
    """
    prefix = f"[{context}] " if context else ""
    
    logging.info(f"{prefix}CV data keys: {list(cv_data.keys()) if isinstance(cv_data, dict) else 'not a dict'}")
    
    if isinstance(cv_data, dict):
        # Check for wrong keys
        wrong_keys = detect_schema_mismatch(cv_data)
        if wrong_keys:
            logging.warning(f"{prefix}WRONG KEYS DETECTED: {wrong_keys}")
        
        # Log presence of canonical keys
        logging.info(f"{prefix}full_name: {bool(cv_data.get('full_name'))}")
        logging.info(f"{prefix}email: {bool(cv_data.get('email'))}")
        logging.info(f"{prefix}phone: {bool(cv_data.get('phone'))}")
        
        # Log work_experience
        we = cv_data.get("work_experience")
        if isinstance(we, list):
            logging.info(f"{prefix}work_experience: {len(we)} entries")
        else:
            logging.warning(f"{prefix}work_experience: MISSING or not an array")
        
        # Log education
        edu = cv_data.get("education")
        if isinstance(edu, list):
            logging.info(f"{prefix}education: {len(edu)} entries")
        else:
            logging.warning(f"{prefix}education: MISSING or not an array")
