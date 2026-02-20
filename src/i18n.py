"""Internationalization (i18n) utilities for CV Generator.

Loads translations from i18n/translations.json and provides helper functions
to retrieve localized strings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

# Cache for translations
_translations_cache: Optional[Dict[str, Any]] = None


def load_translations() -> Dict[str, Any]:
    """Load translations from JSON file (cached).
    
    Returns:
        Dictionary with language codes as keys (en, de, pl).
    """
    global _translations_cache
    
    if _translations_cache is not None:
        return _translations_cache
    
    translations_path = Path(__file__).parent / "i18n" / "translations.json"
    
    try:
        with open(translations_path, "r", encoding="utf-8") as f:
            _translations_cache = json.load(f)
        return _translations_cache
    except FileNotFoundError:
        # Fallback to empty translations if file not found
        _translations_cache = {}
        return _translations_cache


def get_cover_letter_signoff(language: str = "en") -> str:
    """Get the appropriate cover letter signoff for a language.
    
    Args:
        language: Language code (en, de, pl). Defaults to "en".
    
    Returns:
        Localized signoff phrase (e.g., "Kind regards", "Mit freundlichen Grüßen").
    """
    translations = load_translations()
    
    # Normalize language code to lowercase
    lang = str(language).lower().strip()
    
    # Default to English if language not found
    if lang not in translations:
        lang = "en"
    
    # Get cover_letter.signoff, with fallback to "Kind regards"
    return translations.get(lang, {}).get("cover_letter", {}).get("signoff", "Kind regards")


