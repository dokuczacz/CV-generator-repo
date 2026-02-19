#!/usr/bin/env python3
"""
Test realistic CV with longer bullets (Swiss/EU professional CV style).

Demonstrates that the validator fix allows professional achievement descriptions
that are 100-200 characters long (common in Swiss/EU CVs for technical roles).
"""
import sys
from pathlib import Path

# Add src to path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

from validator import CVValidator

# Realistic CV with professional-length bullets (Swiss/EU style)
realistic_cv = {
    "full_name": "Mariusz Horodecki",
    "work_experience": [
        {
            "employer": "Lonza",
            "title": "Senior Manager Quality",
            "date_range": "2021-06 - 2024-10",
            "location": "Visp, Switzerland",
            "bullets": [
                # 156 chars - typical for complex technical achievement
                "Led cross-functional quality team of 12 professionals across 3 GMP facilities, implementing risk-based quality management systems that reduced deviations by 35%",
                
                # 134 chars - multi-stakeholder project impact
                "Managed regulatory compliance initiatives for FDA and EMA inspections, coordinating with 8 departments to ensure zero critical findings",
                
                # 142 chars - leadership scope with quantifiable results
                "Established quality metrics dashboard for executive reporting, enabling data-driven decisions that improved batch release time by 22%",
                
                # 98 chars - concise but complete
                "Mentored 6 quality specialists in GMP compliance, achieving 100% certification success rate"
            ]
        },
        {
            "employer": "SchlauMeyer",
            "title": "Principal Consultant",
            "date_range": "2019-01 - 2021-05",
            "location": "Basel, Switzerland",
            "bullets": [
                # 87 chars - short and effective
                "Advised pharma clients on quality system optimization for European market compliance",
                
                # 142 chars - detailed consulting impact
                "Designed and delivered regulatory compliance training programs for 15+ pharmaceutical companies, impacting 200+ quality professionals",
                
                # 95 chars - concise project summary
                "Led quality audits for 5 major pharma facilities, identifying cost-saving improvement areas"
            ]
        }
    ],
    "education": [
        {
            "institution": "University of Basel",
            "title": "PhD in Pharmaceutical Sciences",
            "date_range": "2012 - 2016",
            "details": "Dissertation: Quality by Design in Biologics Manufacturing"
        }
    ]
}

print("=" * 70)
print("Testing Realistic CV (Swiss/EU Professional Style)")
print("=" * 70)

validator = CVValidator()
result = validator.validate(realistic_cv)

print(f"\nValidation Result: {'✅ VALID' if result.is_valid else '❌ INVALID'}")
print(f"Estimated Pages: {result.estimated_pages:.2f}")
print(f"Estimated Height: {result.estimated_height_mm:.1f}mm")

print("\n--- Work Experience Bullet Analysis ---")
for i, position in enumerate(realistic_cv["work_experience"]):
    print(f"\nPosition {i}: {position['title']}, {position['employer']}")
    for j, bullet in enumerate(position["bullets"]):
        length = len(bullet)
        status = "✅" if length <= 200 else "❌"
        warning_marker = "⚠️ " if length > 100 else "  "
        print(f"  {status} {warning_marker}Bullet {j}: {length} chars")
        if length > 100:
            print(f"      \"{bullet[:60]}...\"")

print("\n--- Errors ---")
if result.errors:
    for error in result.errors:
        print(f"❌ {error.field}: {error.message}")
else:
    print("✅ No errors - All bullets accepted!")

print("\n--- Warnings ---")
if result.warnings:
    for warning in result.warnings:
        if "bullets" in warning and "verbose but OK" in warning:
            print(f"⚠️  {warning}")
else:
    print("No warnings")

print("\n" + "=" * 70)
print("Summary:")
print("=" * 70)

# Count bullet length distribution
all_bullets = []
for pos in realistic_cv["work_experience"]:
    all_bullets.extend(pos["bullets"])

short_bullets = [b for b in all_bullets if len(b) <= 100]
medium_bullets = [b for b in all_bullets if 100 < len(b) <= 150]
long_bullets = [b for b in all_bullets if 150 < len(b) <= 200]
too_long_bullets = [b for b in all_bullets if len(b) > 200]

print(f"Total bullets: {len(all_bullets)}")
print(f"  ≤100 chars (concise): {len(short_bullets)}")
print(f"  101-150 chars (medium): {len(medium_bullets)}")
print(f"  151-200 chars (verbose but OK): {len(long_bullets)}")
print(f"  >200 chars (rejected): {len(too_long_bullets)}")

if result.is_valid:
    print("\n✅ SUCCESS: CV validates correctly with professional-length bullets!")
    print("   The validator fix allows typical Swiss/EU professional achievements")
    print("   that require 100-200 characters to properly convey impact.")
else:
    print("\n❌ FAILED: CV should be valid but isn't")
    sys.exit(1)

print("=" * 70)
