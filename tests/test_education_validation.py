"""
Test education entry validation - institution and title must be non-empty.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.schema_validator import validate_canonical_schema
from src.validator import validate_cv, ValidationError


class TestEducationSchemaValidation:
    """Test schema_validator.py education field validation."""

    def test_valid_education_passes(self):
        """Education with institution and title should pass."""
        cv_data = {
            "full_name": "Test User",
            "email": "test@example.com",
            "phone": "+41 77 123 4567",
            "work_experience": [
                {"date_range": "2020-2024", "employer": "Test", "title": "Engineer", "bullets": []}
            ],
            "education": [
                {
                    "date_range": "2015-2019",
                    "institution": "University of Zurich",
                    "title": "BSc Computer Science",
                    "details": []
                }
            ]
        }
        is_valid, errors = validate_canonical_schema(cv_data, strict=True)
        assert is_valid, f"Expected valid, got errors: {errors}"

    def test_missing_institution_fails(self):
        """Education without institution should fail."""
        cv_data = {
            "full_name": "Test User",
            "email": "test@example.com",
            "phone": "+41 77 123 4567",
            "work_experience": [
                {"date_range": "2020-2024", "employer": "Test", "title": "Engineer", "bullets": []}
            ],
            "education": [
                {
                    "date_range": "2015-2019",
                    "title": "BSc Computer Science",  # missing institution
                    "details": []
                }
            ]
        }
        is_valid, errors = validate_canonical_schema(cv_data, strict=True)
        assert not is_valid, "Expected validation to fail for missing institution"
        assert any("institution" in e for e in errors), f"Expected institution error, got: {errors}"

    def test_empty_institution_fails(self):
        """Education with empty institution should fail."""
        cv_data = {
            "full_name": "Test User",
            "email": "test@example.com",
            "phone": "+41 77 123 4567",
            "work_experience": [
                {"date_range": "2020-2024", "employer": "Test", "title": "Engineer", "bullets": []}
            ],
            "education": [
                {
                    "date_range": "2015-2019",
                    "institution": "",  # empty
                    "title": "BSc Computer Science",
                    "details": []
                }
            ]
        }
        is_valid, errors = validate_canonical_schema(cv_data, strict=True)
        assert not is_valid, "Expected validation to fail for empty institution"
        assert any("institution" in e for e in errors), f"Expected institution error, got: {errors}"

    def test_whitespace_institution_fails(self):
        """Education with whitespace-only institution should fail."""
        cv_data = {
            "full_name": "Test User",
            "email": "test@example.com",
            "phone": "+41 77 123 4567",
            "work_experience": [
                {"date_range": "2020-2024", "employer": "Test", "title": "Engineer", "bullets": []}
            ],
            "education": [
                {
                    "date_range": "2015-2019",
                    "institution": "   ",  # whitespace only
                    "title": "BSc Computer Science",
                    "details": []
                }
            ]
        }
        is_valid, errors = validate_canonical_schema(cv_data, strict=True)
        assert not is_valid, "Expected validation to fail for whitespace institution"
        assert any("institution" in e for e in errors), f"Expected institution error, got: {errors}"

    def test_missing_title_fails(self):
        """Education without title should fail."""
        cv_data = {
            "full_name": "Test User",
            "email": "test@example.com",
            "phone": "+41 77 123 4567",
            "work_experience": [
                {"date_range": "2020-2024", "employer": "Test", "title": "Engineer", "bullets": []}
            ],
            "education": [
                {
                    "date_range": "2015-2019",
                    "institution": "University of Zurich",
                    # missing title
                    "details": []
                }
            ]
        }
        is_valid, errors = validate_canonical_schema(cv_data, strict=True)
        assert not is_valid, "Expected validation to fail for missing title"
        assert any("title" in e for e in errors), f"Expected title error, got: {errors}"

    def test_empty_title_fails(self):
        """Education with empty title should fail."""
        cv_data = {
            "full_name": "Test User",
            "email": "test@example.com",
            "phone": "+41 77 123 4567",
            "work_experience": [
                {"date_range": "2020-2024", "employer": "Test", "title": "Engineer", "bullets": []}
            ],
            "education": [
                {
                    "date_range": "2015-2019",
                    "institution": "University of Zurich",
                    "title": "",  # empty
                    "details": []
                }
            ]
        }
        is_valid, errors = validate_canonical_schema(cv_data, strict=True)
        assert not is_valid, "Expected validation to fail for empty title"
        assert any("title" in e for e in errors), f"Expected title error, got: {errors}"

    def test_multiple_education_entries_validated(self):
        """All education entries should be validated."""
        cv_data = {
            "full_name": "Test User",
            "email": "test@example.com",
            "phone": "+41 77 123 4567",
            "work_experience": [
                {"date_range": "2020-2024", "employer": "Test", "title": "Engineer", "bullets": []}
            ],
            "education": [
                {
                    "date_range": "2015-2019",
                    "institution": "University of Zurich",
                    "title": "BSc Computer Science",
                    "details": []
                },
                {
                    "date_range": "2010-2015",
                    "institution": "",  # invalid in second entry
                    "title": "High School Diploma",
                    "details": []
                }
            ]
        }
        is_valid, errors = validate_canonical_schema(cv_data, strict=True)
        assert not is_valid, "Expected validation to fail for second entry"
        assert any("education[1].institution" in e for e in errors), f"Expected education[1] error, got: {errors}"

    def test_date_range_is_optional(self):
        """date_range should be optional for education entries."""
        cv_data = {
            "full_name": "Test User",
            "email": "test@example.com",
            "phone": "+41 77 123 4567",
            "work_experience": [
                {"date_range": "2020-2024", "employer": "Test", "title": "Engineer", "bullets": []}
            ],
            "education": [
                {
                    # no date_range
                    "institution": "University of Zurich",
                    "title": "BSc Computer Science",
                    "details": []
                }
            ]
        }
        is_valid, errors = validate_canonical_schema(cv_data, strict=True)
        assert is_valid, f"Expected valid (date_range is optional), got errors: {errors}"


class TestEducationSemanticValidation:
    """Test validator.py education field validation (semantic layer)."""

    def test_valid_education_no_errors(self):
        """Valid education entries should not produce validation errors."""
        cv_data = {
            "full_name": "Test User",
            "education": [
                {
                    "date_range": "2015-2019",
                    "institution": "University of Zurich",
                    "title": "BSc Computer Science",
                    "details": []
                }
            ],
            "work_experience": []
        }
        result = validate_cv(cv_data)
        edu_errors = [e for e in result.errors if "education" in e.field and ("institution" in e.field or "title" in e.field)]
        assert len(edu_errors) == 0, f"Expected no education field errors, got: {edu_errors}"

    def test_missing_institution_produces_error(self):
        """Missing institution should produce a validation error."""
        cv_data = {
            "full_name": "Test User",
            "education": [
                {
                    "date_range": "2015-2019",
                    # missing institution
                    "title": "BSc Computer Science",
                    "details": []
                }
            ],
            "work_experience": []
        }
        result = validate_cv(cv_data)
        inst_errors = [e for e in result.errors if "institution" in e.field]
        assert len(inst_errors) == 1, f"Expected 1 institution error, got: {inst_errors}"
        assert "required" in inst_errors[0].message.lower() or "missing" in inst_errors[0].message.lower()

    def test_empty_institution_produces_error(self):
        """Empty institution should produce a validation error."""
        cv_data = {
            "full_name": "Test User",
            "education": [
                {
                    "date_range": "2015-2019",
                    "institution": "",
                    "title": "BSc Computer Science",
                    "details": []
                }
            ],
            "work_experience": []
        }
        result = validate_cv(cv_data)
        inst_errors = [e for e in result.errors if "institution" in e.field]
        assert len(inst_errors) == 1, f"Expected 1 institution error, got: {inst_errors}"

    def test_missing_title_produces_error(self):
        """Missing title should produce a validation error."""
        cv_data = {
            "full_name": "Test User",
            "education": [
                {
                    "date_range": "2015-2019",
                    "institution": "University of Zurich",
                    # missing title
                    "details": []
                }
            ],
            "work_experience": []
        }
        result = validate_cv(cv_data)
        title_errors = [e for e in result.errors if "title" in e.field and "education" in e.field]
        assert len(title_errors) == 1, f"Expected 1 title error, got: {title_errors}"

    def test_empty_title_produces_error(self):
        """Empty title should produce a validation error."""
        cv_data = {
            "full_name": "Test User",
            "education": [
                {
                    "date_range": "2015-2019",
                    "institution": "University of Zurich",
                    "title": "",
                    "details": []
                }
            ],
            "work_experience": []
        }
        result = validate_cv(cv_data)
        title_errors = [e for e in result.errors if "title" in e.field and "education" in e.field]
        assert len(title_errors) == 1, f"Expected 1 title error, got: {title_errors}"

    def test_error_includes_helpful_suggestion(self):
        """Validation errors should include helpful suggestions."""
        cv_data = {
            "full_name": "Test User",
            "education": [
                {
                    "date_range": "2015-2019",
                    "institution": "",
                    "title": "",
                    "details": []
                }
            ],
            "work_experience": []
        }
        result = validate_cv(cv_data)
        edu_errors = [e for e in result.errors if "education" in e.field]
        for error in edu_errors:
            assert error.suggestion, f"Error missing suggestion: {error}"
            assert len(error.suggestion) > 10, f"Suggestion too short: {error.suggestion}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
