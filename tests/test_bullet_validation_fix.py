#!/usr/bin/env python3
"""
Verify bullet validation behavior on mixed bullet lengths.
"""
import sys
from pathlib import Path

# Add src to path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

from validator import CVValidator

# Test CV with mixed bullet lengths
test_cv = {
    "full_name": "Test User",
    "work_experience": [
        {
            "employer": "Test Corp",
            "title": "Test Role",
            "date_range": "2020-01 - 2025-01",
            "bullets": [
                # Exactly 50 chars - should pass cleanly (no warning)
                "Short bullet that fits nicely under soft limit",
                
                # Exactly 110 chars - should pass with soft warning (over 100 soft limit)
                "This bullet is designed to clearly exceed the soft limit of one hundred characters to trigger warning text x",
                
                # Exactly 150 chars - should pass with soft warning (verbose but OK)
                "This is a longer bullet that is carefully crafted to be exactly one hundred and fifty characters long to demonstrate the soft warning for verbose content",
                
                # Exactly 210 chars - should ERROR (exceeds hard limit of 200)
                "This extremely long bullet point intentionally exceeds the hard character limit of two hundred characters and should trigger a validation error to demonstrate that the system correctly rejects excessively verbose"
            ]
        }
    ]
}

def test_bullet_validation_mixed_lengths():
    validator = CVValidator()
    result = validator.validate(test_cv)

    expected_errors = 1
    expected_warnings_min = 2

    assert len(result.errors) == expected_errors
    assert len(result.warnings) >= expected_warnings_min
    assert any("bullets[3]" in err.field for err in result.errors)
    assert not any(
        "bullets[0]" in err.field or "bullets[1]" in err.field or "bullets[2]" in err.field
        for err in result.errors
    )
