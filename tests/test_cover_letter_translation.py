#!/usr/bin/env python3
"""Test cover letter signoff translation fix.

This script tests the i18n module and verifies that German cover letters
use the correct closing phrase.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.i18n import get_cover_letter_signoff, load_translations


def test_translations_load():
    """Test that translations load correctly."""
    translations = load_translations()
    assert "en" in translations, "English translations missing"
    assert "de" in translations, "German translations missing"
    assert "pl" in translations, "Polish translations missing"
    print("✓ Translations loaded successfully")
    return True


def test_cover_letter_signoffs():
    """Test cover letter signoffs for all languages."""
    test_cases = [
        ("en", "Kind regards"),
        ("de", "Mit freundlichen Grüßen"),
        ("pl", "Z poważaniem"),
        ("DE", "Mit freundlichen Grüßen"),  # Test uppercase
        ("En", "Kind regards"),  # Test mixed case
        ("fr", "Kind regards"),  # Test fallback to English
    ]
    
    for lang, expected in test_cases:
        result = get_cover_letter_signoff(lang)
        assert result == expected, f"Language {lang}: expected '{expected}', got '{result}'"
        print(f"✓ {lang}: {result}")
    
    return True


def test_signoff_formatting():
    """Test that signoff is correctly formatted in cover letter."""
    # Simulate what happens in function_app.py
    target_language = "de"
    full_name = "Mariusz Horodecki"
    
    signoff_phrase = get_cover_letter_signoff(target_language)
    signoff = f"{signoff_phrase},\n{full_name}"
    
    expected = "Mit freundlichen Grüßen,\nMariusz Horodecki"
    assert signoff == expected, f"Expected '{expected}', got '{signoff}'"
    print(f"✓ German signoff formatting: {repr(signoff)}")
    
    # Test English
    target_language = "en"
    signoff_phrase = get_cover_letter_signoff(target_language)
    signoff = f"{signoff_phrase},\n{full_name}"
    expected = "Kind regards,\nMariusz Horodecki"
    assert signoff == expected, f"Expected '{expected}', got '{signoff}'"
    print(f"✓ English signoff formatting: {repr(signoff)}")
    
    return True


def main():
    """Run all tests."""
    print("Testing cover letter signoff translations...\n")
    
    try:
        test_translations_load()
        print()
        test_cover_letter_signoffs()
        print()
        test_signoff_formatting()
        print("\n✅ All tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
