"""
CV Character Limit Validator - Enforces 2-Page Maximum for Swiss Market

This module validates CV content against strict character limits to ensure
the rendered PDF fits exactly 2 A4 pages (210x297mm).

Limits are based on:
- Available space: ~440mm vertical (after margins, header)
- Line height: ~4.5mm per line (11pt Arial, 1.3 line-height)
- Section spacing: 6mm per section
- Entry overhead: 5mm per entry header

Golden Rule: REJECT if estimated pages > 2.0
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import math


@dataclass
class ValidationError:
    """Represents a single validation error"""
    field: str
    current_value: Any
    limit: Any
    excess: Any
    message: str
    suggestion: str


@dataclass
class ValidationResult:
    """Result of CV validation"""
    is_valid: bool
    errors: List[ValidationError]
    warnings: List[str]
    estimated_pages: float
    estimated_height_mm: float
    details: Dict[str, Any]


# Character limits optimized for 2-page A4 layout
CV_LIMITS = {
    "full_name": {
        "max_chars": 50,
        "height_mm": 8,  # 16pt font
        "reason": "Header name, 16pt font"
    },
    "address_lines": {
        "max_items": 2,
        "max_chars_per_item": 60,
        "height_mm": 4.5,  # per line
        "reason": "Contact block"
    },
    "work_experience": {
        "max_entries": 5,
        "total_height_mm": 130,
        "per_entry": {
            "date_range": {
                "max_chars": 25,
                "pattern": r"^(\d{4}-\d{2}|\d{2}/\d{4})\s*(–\s*(\d{4}-\d{2}|\d{2}/\d{4}|Present))?$",
                "reason": "Format: 2020-01 – 2025-04 OR 01/2020 – 04/2025"
            },
            "employer": {
                "max_chars": 60,
                "reason": "Company name"
            },
            "location": {
                "max_chars": 50,
                "reason": "City, Country"
            },
            "title": {
                "max_chars": 80,
                "reason": "Job title/position"
            },
            "bullets": {
                "max_count": 4,
                "max_chars_per_bullet": 90,  # Testing with 90, may adjust
                "height_mm_per_bullet": 4.5,
                "reason": "Achievement bullets"
            }
        }
    },
    "education": {
        "max_entries": 3,
        "total_height_mm": 50,
        "per_entry": {
            "date_range": {
                "max_chars": 20,
                "reason": "Years: 2012-2015"
            },
            "institution": {
                "max_chars": 70,
                "reason": "University/school name"
            },
            "title": {
                "max_chars": 90,
                "reason": "Degree title"
            },
            "details": {
                "max_chars": 150,
                "reason": "Additional details (combined)"
            }
        }
    },
    "further_experience": {
        "max_entries": 4,
        "total_height_mm": 80,
        "per_entry": {
            "date_range": {
                "max_chars": 25,
                "pattern": r"^(\d{4}-\d{2}|\d{2}/\d{4}|since\s+(\d{4}-\d{2}|\d{2}/\d{4}))\s*(–\s*(\d{4}-\d{2}|\d{2}/\d{4}|Present))?$",
                "reason": "Format: 2020-01 – 2025-04 OR 01/2020 – 04/2025 OR since 01/2024"
            },
            "organization": {
                "max_chars": 70,
                "reason": "Organization/Institution name"
            },
            "title": {
                "max_chars": 90,
                "reason": "Position/Role/Activity"
            },
            "bullets": {
                "max_count": 3,
                "max_chars_per_bullet": 80,
                "height_mm_per_bullet": 4.5,
                "reason": "Activity description"
            }
        }
    },
    "languages": {
        "max_items": 5,
        "max_chars_per_item": 50,
        "total_height_mm": 28,
        "reason": "Language proficiency list"
    },
    "it_ai_skills": {
        "max_items": 8,
        "max_chars_per_item": 70,
        "total_height_mm": 45,
        "reason": "Technical skills list"
    },
    "interests": {
        "max_chars": 350,
        "max_lines": 7,
        "total_height_mm": 35,
        "reason": "Personal interests"
    }
}

# Space constants
HEADER_HEIGHT_MM = 60  # Name + contact + photo
MARGINS_HEIGHT_MM = 40  # Top + bottom
SECTION_TITLE_HEIGHT_MM = 6  # Per section
PAGE_HEIGHT_MM = 297  # A4
MAX_PAGES = 2.0  # Hard limit

# Soft/hard tolerance: prefer page-fit over micro character policing.
SOFT_CHAR_RATIO = 1.10  # +10% warning threshold
HARD_CHAR_RATIO = 2.00  # extreme outliers become errors (safety guard)


def _soft_limit(max_chars: int) -> int:
    return int(math.ceil(max_chars * SOFT_CHAR_RATIO))


def _hard_limit(max_chars: int) -> int:
    return int(math.ceil(max_chars * HARD_CHAR_RATIO))


class CVValidator:
    """Validates CV content against 2-page constraints"""
    
    def __init__(self):
        self.limits = CV_LIMITS
        
    def validate(self, cv_data: Dict[str, Any]) -> ValidationResult:
        """
        Validate CV data against all constraints.
        
        Args:
            cv_data: CV dictionary to validate
            
        Returns:
            ValidationResult with errors and page estimation
        """
        errors = []
        warnings = []
        height_details = {}
        
        # Validate each section (soft warnings for small overages; hard errors only for extreme outliers).
        errors.extend(self._validate_string_field(cv_data, "full_name", warnings))
        errors.extend(self._validate_string_field(cv_data, "interests", warnings))

        errors.extend(self._validate_list_field(cv_data, "address_lines", warnings))
        errors.extend(self._validate_list_field(cv_data, "languages", warnings))
        errors.extend(self._validate_list_field(cv_data, "it_ai_skills", warnings))

        errors.extend(self._validate_work_experience(cv_data.get("work_experience", []), warnings))
        errors.extend(self._validate_education(cv_data.get("education", []), warnings))
        errors.extend(self._validate_further_experience(cv_data.get("further_experience", []), warnings))
        
        # Estimate total height
        estimated_height = self._estimate_height(cv_data, height_details)
        estimated_pages = estimated_height / PAGE_HEIGHT_MM

        # Template-specific layout rule: hard page break after Work experience.
        # If either page exceeds the physical A4 height, WeasyPrint will spill to a 3rd page.
        page1_height = height_details.get("page1_estimated_height_mm")
        page2_height = height_details.get("page2_estimated_height_mm")
        if page1_height and page1_height > PAGE_HEIGHT_MM:
            errors.append(ValidationError(
                field="_page1_overflow",
                current_value=page1_height,
                limit=PAGE_HEIGHT_MM,
                excess=page1_height - PAGE_HEIGHT_MM,
                message="Page 1 content exceeds A4 height (template forces a page break)",
                suggestion="Reduce Education/Work Experience content (fewer entries/bullets or shorter text)."
            ))
        if page2_height and page2_height > PAGE_HEIGHT_MM:
            errors.append(ValidationError(
                field="_page2_overflow",
                current_value=page2_height,
                limit=PAGE_HEIGHT_MM,
                excess=page2_height - PAGE_HEIGHT_MM,
                message="Page 2 content exceeds A4 height (will spill to a 3rd page)",
                suggestion="Reduce Further Experience / Languages / Skills / Interests / References content."
            ))
        
        # Check page limit
        if estimated_pages > MAX_PAGES:
            errors.append(ValidationError(
                field="_total_pages",
                current_value=estimated_pages,
                limit=MAX_PAGES,
                excess=estimated_pages - MAX_PAGES,
                message=f"CV exceeds {MAX_PAGES} pages limit",
                suggestion=f"Reduce content by ~{int((estimated_pages - MAX_PAGES) * 100)}%. "
                          f"Consider removing oldest work experience or reducing bullet points."
            ))
        
        # Generate warnings for close calls
        if 1.9 <= estimated_pages <= 2.0:
            warnings.append(f"CV is very close to 2-page limit ({estimated_pages:.2f} pages). "
                          f"Any small addition may exceed limit.")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            estimated_pages=round(estimated_pages, 2),
            estimated_height_mm=round(estimated_height, 1),
            details=height_details
        )
    
    def _validate_string_field(self, cv_data: Dict, field: str, warnings: List[str]) -> List[ValidationError]:
        """Validate a simple string field"""
        errors = []
        value = cv_data.get(field, "")
        
        if field not in self.limits:
            return errors
            
        limits = self.limits[field]
        max_chars = limits.get("max_chars")
        
        if max_chars:
            vlen = len(value)
            soft = _soft_limit(max_chars)
            hard = _hard_limit(max_chars)
            if vlen > hard:
                errors.append(
                    ValidationError(
                        field=field,
                        current_value=vlen,
                        limit=hard,
                        excess=vlen - hard,
                        message=f"{field}: {vlen} chars exceeds hard limit of {hard}",
                        suggestion=f"Reduce by {vlen - hard} characters",
                    )
                )
            elif vlen > soft:
                warnings.append(f"{field}: {vlen} chars (soft cap {soft}, hard cap {hard})")
        
        return errors
    
    def _validate_list_field(self, cv_data: Dict, field: str, warnings: List[str]) -> List[ValidationError]:
        """Validate a list field (e.g., languages, skills)"""
        errors = []
        items = cv_data.get(field, [])
        
        if field not in self.limits:
            return errors
            
        limits = self.limits[field]
        max_items = limits.get("max_items")
        max_chars = limits.get("max_chars_per_item")
        
        if max_items and len(items) > max_items:
            warnings.append(f"{field}: {len(items)} items (recommended max {max_items})")
        
        if max_chars:
            soft = _soft_limit(max_chars)
            hard = _hard_limit(max_chars)
            for i, item in enumerate(items):
                item_str = str(item)
                ilen = len(item_str)
                if ilen > hard:
                    errors.append(
                        ValidationError(
                            field=f"{field}[{i}]",
                            current_value=ilen,
                            limit=hard,
                            excess=ilen - hard,
                            message=f"{field}[{i}]: {ilen} chars exceeds hard limit {hard}",
                            suggestion=f"Shorten by {ilen - hard} characters",
                        )
                    )
                elif ilen > soft:
                    warnings.append(f"{field}[{i}]: {ilen} chars (soft cap {soft}, hard cap {hard})")
        
        return errors
    
    def _validate_work_experience(self, entries: List[Dict], warnings: List[str]) -> List[ValidationError]:
        """Validate work experience entries"""
        errors = []
        limits = self.limits["work_experience"]
        
        if len(entries) > limits["max_entries"]:
            warnings.append(f"work_experience: {len(entries)} entries (recommended max {limits['max_entries']})")
        
        for i, entry in enumerate(entries):
            per_entry = limits["per_entry"]
            
            # Validate each field
            for field, field_limits in per_entry.items():
                if field == "bullets":
                    bullets = entry.get(field, [])
                    max_bullets = field_limits["max_count"]
                    max_chars = field_limits["max_chars_per_bullet"]
                    
                    if len(bullets) > max_bullets:
                        warnings.append(
                            f"work_experience[{i}].bullets: {len(bullets)} bullets (recommended max {max_bullets})"
                        )

                    soft = _soft_limit(max_chars)
                    hard = _hard_limit(max_chars)
                    for j, bullet in enumerate(bullets):
                        blen = len(bullet)
                        if blen > hard:
                            errors.append(
                                ValidationError(
                                    field=f"work_experience[{i}].bullets[{j}]",
                                    current_value=blen,
                                    limit=hard,
                                    excess=blen - hard,
                                    message=f"Entry {i}, bullet {j}: {blen} chars exceeds hard limit {hard}",
                                    suggestion=f"Shorten: '{bullet[:40]}...' by {blen - hard} chars",
                                )
                            )
                        elif blen > soft:
                            warnings.append(
                                f"work_experience[{i}].bullets[{j}]: {blen} chars (soft cap {soft}, hard cap {hard})"
                            )
                else:
                    value = entry.get(field, "")
                    max_chars = field_limits.get("max_chars")
                    if max_chars:
                        vlen = len(value)
                        soft = _soft_limit(max_chars)
                        hard = _hard_limit(max_chars)
                        if vlen > hard:
                            errors.append(
                                ValidationError(
                                    field=f"work_experience[{i}].{field}",
                                    current_value=vlen,
                                    limit=hard,
                                    excess=vlen - hard,
                                    message=f"Entry {i}.{field}: {vlen} chars exceeds hard limit {hard}",
                                    suggestion=f"Shorten by {vlen - hard} characters",
                                )
                            )
                        elif vlen > soft:
                            warnings.append(
                                f"work_experience[{i}].{field}: {vlen} chars (soft cap {soft}, hard cap {hard})"
                            )
        
        return errors
    
    def _validate_education(self, entries: List[Dict], warnings: List[str]) -> List[ValidationError]:
        """Validate education entries"""
        errors = []
        limits = self.limits["education"]
        
        if len(entries) > limits["max_entries"]:
            warnings.append(f"education: {len(entries)} entries (recommended max {limits['max_entries']})")
        
        for i, entry in enumerate(entries):
            per_entry = limits["per_entry"]
            
            for field, field_limits in per_entry.items():
                if field == "details":
                    # Details can be a list
                    details = entry.get(field, [])
                    if isinstance(details, list):
                        combined = "; ".join(details)
                    else:
                        combined = str(details)
                    
                    max_chars = field_limits["max_chars"]
                    clen = len(combined)
                    soft = _soft_limit(max_chars)
                    hard = _hard_limit(max_chars)
                    if clen > hard:
                        errors.append(
                            ValidationError(
                                field=f"education[{i}].details",
                                current_value=clen,
                                limit=hard,
                                excess=clen - hard,
                                message=f"Education {i} details: {clen} chars exceeds hard limit {hard}",
                                suggestion=f"Reduce details by {clen - hard} characters",
                            )
                        )
                    elif clen > soft:
                        warnings.append(f"education[{i}].details: {clen} chars (soft cap {soft}, hard cap {hard})")
                else:
                    value = entry.get(field, "")
                    max_chars = field_limits.get("max_chars")
                    if max_chars:
                        vlen = len(value)
                        soft = _soft_limit(max_chars)
                        hard = _hard_limit(max_chars)
                        if vlen > hard:
                            errors.append(
                                ValidationError(
                                    field=f"education[{i}].{field}",
                                    current_value=vlen,
                                    limit=hard,
                                    excess=vlen - hard,
                                    message=f"Education {i}.{field}: {vlen} chars exceeds hard limit {hard}",
                                    suggestion=f"Shorten by {vlen - hard} characters",
                                )
                            )
                        elif vlen > soft:
                            warnings.append(f"education[{i}].{field}: {vlen} chars (soft cap {soft}, hard cap {hard})")
        
        return errors
    
    def _validate_further_experience(self, entries: List[Dict], warnings: List[str]) -> List[ValidationError]:
        """Validate further experience entries"""
        errors = []
        limits = self.limits["further_experience"]
        
        if len(entries) > limits["max_entries"]:
            warnings.append(f"further_experience: {len(entries)} entries (recommended max {limits['max_entries']})")
        
        for i, entry in enumerate(entries):
            per_entry = limits["per_entry"]
            
            for field, field_limits in per_entry.items():
                if field == "bullets":
                    bullets = entry.get(field, [])
                    if len(bullets) > field_limits["max_count"]:
                        warnings.append(
                            f"further_experience[{i}].bullets: {len(bullets)} bullets (recommended max {field_limits['max_count']})"
                        )

                    max_chars = field_limits["max_chars_per_bullet"]
                    soft = _soft_limit(max_chars)
                    hard = _hard_limit(max_chars)
                    for j, bullet in enumerate(bullets):
                        blen = len(bullet)
                        if blen > hard:
                            errors.append(
                                ValidationError(
                                    field=f"further_experience[{i}].bullets[{j}]",
                                    current_value=blen,
                                    limit=hard,
                                    excess=blen - hard,
                                    message=f"Further Experience {i} bullet {j}: {blen} chars exceeds hard limit {hard}",
                                    suggestion=f"Reduce by {blen - hard} characters",
                                )
                            )
                        elif blen > soft:
                            warnings.append(
                                f"further_experience[{i}].bullets[{j}]: {blen} chars (soft cap {soft}, hard cap {hard})"
                            )
                else:
                    value = entry.get(field, "")
                    max_chars = field_limits.get("max_chars")
                    if max_chars:
                        vlen = len(value)
                        soft = _soft_limit(max_chars)
                        hard = _hard_limit(max_chars)
                        if vlen > hard:
                            errors.append(
                                ValidationError(
                                    field=f"further_experience[{i}].{field}",
                                    current_value=vlen,
                                    limit=hard,
                                    excess=vlen - hard,
                                    message=f"Further Experience {i}.{field}: {vlen} chars exceeds hard limit {hard}",
                                    suggestion=f"Shorten by {vlen - hard} characters",
                                )
                            )
                        elif vlen > soft:
                            warnings.append(
                                f"further_experience[{i}].{field}: {vlen} chars (soft cap {soft}, hard cap {hard})"
                            )
        
        return errors
    
    def _estimate_height(self, cv_data: Dict, details: Dict) -> float:
        """
        Estimate total CV height in mm.
        
        Returns estimated height with breakdown in details dict.
        """
        total = 0
        
        # Header
        header_height = HEADER_HEIGHT_MM
        total += header_height
        details["header"] = header_height
        
        def _lines(s: str, chars_per_line: int) -> int:
            s = s or ""
            return int(math.ceil(len(s) / float(chars_per_line))) if s else 0

        # Profile section
        profile = cv_data.get("profile", "")
        profile = profile.strip() if isinstance(profile, str) else ""
        profile_lines = _lines(profile, 70)
        profile_height = (SECTION_TITLE_HEIGHT_MM + (max(1, profile_lines) * 4.5)) if profile else 0
        total += profile_height
        details["profile"] = profile_height
        
        # Work experience
        work_entries = cv_data.get("work_experience", [])
        work_height = SECTION_TITLE_HEIGHT_MM
        per_bullet_chars = self.limits["work_experience"]["per_entry"]["bullets"]["max_chars_per_bullet"]
        for entry in work_entries:
            work_height += 5  # Entry header
            bullets = entry.get("bullets", [])
            bullet_lines = sum(max(1, _lines(str(b), per_bullet_chars)) for b in bullets) if bullets else 0
            work_height += bullet_lines * 4.5  # 4.5mm per rendered line
            work_height += 3  # Entry margin
        total += work_height
        details["work_experience"] = work_height
        
        # Education
        edu_entries = cv_data.get("education", [])
        edu_height = SECTION_TITLE_HEIGHT_MM + (len(edu_entries) * 15)
        total += edu_height
        details["education"] = edu_height
        
        # Languages
        lang_items = cv_data.get("languages", [])
        lang_height = SECTION_TITLE_HEIGHT_MM + (len(lang_items) * 4.5)
        total += lang_height
        details["languages"] = lang_height
        
        # IT/AI Skills
        skill_items = cv_data.get("it_ai_skills", [])
        skill_height = SECTION_TITLE_HEIGHT_MM + (len(skill_items) * 5)
        total += skill_height
        details["it_ai_skills"] = skill_height
        
        # Further Experience
        further_exp_items = cv_data.get("further_experience", [])
        fe_bullet_chars = self.limits["further_experience"]["per_entry"]["bullets"]["max_chars_per_bullet"]
        further_exp_height = SECTION_TITLE_HEIGHT_MM
        for entry in further_exp_items:
            further_exp_height += 6  # entry header (date + title)
            bullets = entry.get("bullets", [])
            bullet_lines = sum(max(1, _lines(str(b), fe_bullet_chars)) for b in bullets) if bullets else 0
            further_exp_height += bullet_lines * 4.5
            further_exp_height += 2  # entry margin
        total += further_exp_height
        details["further_experience"] = further_exp_height
        
        # Interests
        interests = cv_data.get("interests", "")
        interests_lines = max(1, _lines(str(interests), 70))
        interests_height = SECTION_TITLE_HEIGHT_MM + (interests_lines * 4.5)
        total += interests_height
        details["interests"] = interests_height

        # References (always rendered by the template; defaults to a short sentence)
        references = cv_data.get("references") or "Will be announced on request."
        references_lines = max(1, _lines(str(references), 70))
        references_height = SECTION_TITLE_HEIGHT_MM + (references_lines * 4.5)
        total += references_height
        details["references"] = references_height
        
        # Add margins
        total += MARGINS_HEIGHT_MM
        details["margins"] = MARGINS_HEIGHT_MM

        # Template page split: Page 1 = header + education + work; Page 2 = rest.
        # Include margins per page to catch spillover realistically.
        page1 = header_height + edu_height + work_height + MARGINS_HEIGHT_MM
        page2 = further_exp_height + lang_height + skill_height + interests_height + references_height + MARGINS_HEIGHT_MM
        details["page1_estimated_height_mm"] = round(page1, 1)
        details["page2_estimated_height_mm"] = round(page2, 1)
        
        return total
    
    def get_limits_summary(self) -> Dict[str, Any]:
        """Return a summary of all character limits for documentation"""
        summary = {}
        for section, limits in self.limits.items():
            if "per_entry" in limits:
                summary[section] = {
                    "max_entries": limits.get("max_entries"),
                    "per_entry": limits["per_entry"]
                }
            elif "max_chars_per_item" in limits:
                summary[section] = {
                    "max_items": limits.get("max_items"),
                    "max_chars_per_item": limits["max_chars_per_item"]
                }
            else:
                summary[section] = {
                    "max_chars": limits.get("max_chars"),
                    "max_lines": limits.get("max_lines")
                }
        return summary


def validate_cv(cv_data: Dict[str, Any]) -> ValidationResult:
    """
    Convenience function to validate CV data.
    
    Args:
        cv_data: CV dictionary to validate
        
    Returns:
        ValidationResult
    """
    validator = CVValidator()
    return validator.validate(cv_data)


if __name__ == "__main__":
    # Example validation
    validator = CVValidator()
    
    # Print limits summary
    print("CV CHARACTER LIMITS FOR 2-PAGE MAXIMUM:\n")
    import json
    print(json.dumps(validator.get_limits_summary(), indent=2))
