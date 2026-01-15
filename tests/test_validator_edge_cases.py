"""
Test validator with edge cases to ensure 2-page enforcement works correctly.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.validator import validate_cv
import json

MAX_HEIGHT_MM = 594.0  # 2 pages = 2 * 297mm

print("Testing Validator Edge Cases")
print("=" * 60)

# Edge Case 1: Minimal CV (should pass easily)
print("\n1. MINIMAL CV (should pass)")
print("-" * 60)
minimal_cv = {
    "full_name": "John Doe",
    "address_lines": ["Zurich"],
    "phone": "+41 77 123 4567",
    "email": "john@example.com",
    "profile": "Software engineer with 5 years experience.",
    "work_experience": [
        {
            "date_range": "2020-01 – Present",
            "employer": "Tech Corp",
            "title": "Software Engineer",
            "bullets": ["Developed applications"]
        }
    ]
}

result = validate_cv(minimal_cv)
print(f"Valid: {result.is_valid}")
print(f"Estimated pages: {result.estimated_pages:.2f}")
print(f"Height: {result.estimated_height_mm:.1f}mm / {MAX_HEIGHT_MM:.1f}mm")
if not result.is_valid:
    print(f"Errors: {len(result.errors)}")

# Edge Case 2: Exactly at limits (should pass)
print("\n2. EXACTLY AT LIMITS (should pass)")
print("-" * 60)
at_limits_cv = {
    "full_name": "Jane Smith",
    "address_lines": ["Street 123", "8000 Zurich"],
    "phone": "+41 77 123 4567",
    "email": "jane@example.com",
    "profile": "A" * 500,  # Exactly 500 chars
    "work_experience": [
        {
            "date_range": "2020-01 – 2025-01",
            "employer": "Company " + str(i),
            "title": "Position " + str(i),
            "bullets": ["X" * 90 for _ in range(4)]  # 4 bullets, 90 chars each
        }
        for i in range(5)  # 5 positions (max)
    ],
    "education": [
        {
            "date_range": "2015 – 2019",
            "institution": "University",
            "title": "Degree",
            "details": ["Detail 1"]
        }
        for _ in range(3)  # 3 entries (max)
    ],
    "languages": ["Language " + str(i) for i in range(5)],  # 5 items (max)
    "it_ai_skills": ["Skill " + str(i) for i in range(8)],  # 8 items (max)
    "trainings": ["Training " + str(i) for i in range(8)],  # 8 items (max)
    "interests": "B" * 350,  # Exactly 350 chars
    "data_privacy": "C" * 180  # Exactly 180 chars
}

result = validate_cv(at_limits_cv)
print(f"Valid: {result.is_valid}")
print(f"Estimated pages: {result.estimated_pages:.2f}")
print(f"Height: {result.estimated_height_mm:.1f}mm / {MAX_HEIGHT_MM:.1f}mm")
if not result.is_valid:
    print(f"Errors: {len(result.errors)}")
    for error in result.errors[:3]:
        print(f"  - {error.message}")

# Edge Case 3: One char over on multiple fields (should fail)
print("\n3. ONE CHAR OVER ON MULTIPLE FIELDS (should fail)")
print("-" * 60)
over_limit_cv = {
    "full_name": "Bob Johnson",
    "address_lines": ["Zurich"],
    "phone": "+41 77 123 4567",
    "email": "bob@example.com",
    "profile": "X" * 501,  # 1 char over
    "work_experience": [
        {
            "date_range": "2020-01 – Present",
            "employer": "Company",
            "title": "Engineer",
            "bullets": ["Y" * 91]  # 1 char over
        }
    ]
}

result = validate_cv(over_limit_cv)
print(f"Valid: {result.is_valid}")
print(f"Estimated pages: {result.estimated_pages:.2f}")
print(f"Errors found: {len(result.errors)}")
for error in result.errors:
    print(f"  - {error.field}: {error.current_value} > {error.limit} (excess: {error.excess})")

# Edge Case 4: 6 work positions (should fail)
print("\n4. TOO MANY WORK POSITIONS (should fail)")
print("-" * 60)
too_many_positions = {
    "full_name": "Alice Brown",
    "address_lines": ["Zurich"],
    "phone": "+41 77 123 4567",
    "email": "alice@example.com",
    "profile": "Profile text",
    "work_experience": [
        {
            "date_range": "2020-01 – Present",
            "employer": f"Company {i}",
            "title": "Engineer",
            "bullets": ["Did stuff"]
        }
        for i in range(6)  # 6 positions (limit is 5)
    ]
}

result = validate_cv(too_many_positions)
print(f"Valid: {result.is_valid}")
print(f"Errors found: {len(result.errors)}")
for error in result.errors:
    print(f"  - {error.message}")

# Edge Case 5: 5 bullets per position (should fail)
print("\n5. TOO MANY BULLETS PER POSITION (should fail)")
print("-" * 60)
too_many_bullets = {
    "full_name": "Charlie Davis",
    "address_lines": ["Zurich"],
    "phone": "+41 77 123 4567",
    "email": "charlie@example.com",
    "profile": "Profile",
    "work_experience": [
        {
            "date_range": "2020-01 – Present",
            "employer": "Company",
            "title": "Engineer",
            "bullets": ["Bullet " + str(i) for i in range(5)]  # 5 bullets (limit is 4)
        }
    ]
}

result = validate_cv(too_many_bullets)
print(f"Valid: {result.is_valid}")
print(f"Errors found: {len(result.errors)}")
for error in result.errors:
    print(f"  - {error.message}")

# Edge Case 6: Estimated exactly 2.0 pages (should pass)
print("\n6. ESTIMATED EXACTLY 2.0 PAGES (should pass)")
print("-" * 60)
print("Testing boundary condition at exactly 2.0 pages...")

# Calculate content that should be exactly at 594mm
exactly_two_pages = {
    "full_name": "Test User",
    "address_lines": ["Address Line 1", "Address Line 2"],
    "phone": "+41 77 123 4567",
    "email": "test@example.com",
    "profile": "P" * 500,
    "work_experience": [
        {
            "date_range": "2020-01 – 2025-01",
            "employer": "Company " + str(i),
            "title": "Senior Position Title " + str(i),
            "bullets": ["X" * 90 for _ in range(4)]
        }
        for i in range(5)
    ],
    "education": [
        {
            "date_range": "2015 – 2019",
            "institution": "University of Zurich",
            "title": "Master of Science in Computer Science",
            "details": ["Thesis: AI and Machine Learning"]
        }
        for _ in range(3)
    ],
    "languages": ["Language with description " + str(i) for i in range(5)],
    "it_ai_skills": ["Programming language and framework " + str(i) for i in range(8)],
    "trainings": ["Training course with provider and date information " + str(i) for i in range(8)],
    "interests": "I" * 350,
    "data_privacy": "D" * 180
}

result = validate_cv(exactly_two_pages)
print(f"Valid: {result.is_valid}")
print(f"Estimated pages: {result.estimated_pages:.2f}")
print(f"Height: {result.estimated_height_mm:.1f}mm / {MAX_HEIGHT_MM:.1f}mm")
print(f"Buffer: {MAX_HEIGHT_MM - result.estimated_height_mm:.1f}mm")

# Summary
print("\n" + "=" * 60)
print("EDGE CASE TESTING COMPLETE")
print("=" * 60)
print("\nValidator is working correctly if:")
print("✓ Case 1 (minimal) passes")
print("✓ Case 2 (at limits) passes")
print("✓ Case 3 (1 char over) fails with correct errors")
print("✓ Case 4 (6 positions) fails")
print("✓ Case 5 (5 bullets) fails")
print("✓ Case 6 (exactly 2.0 pages) passes")
