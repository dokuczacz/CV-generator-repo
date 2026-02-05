"""Prompt registry: load and cache prompts from external files.

Single source of truth for all AI system prompts used in the backend.
Prompts are loaded once on startup and cached in memory.
"""

import os
from pathlib import Path
from typing import Dict, Optional


class PromptRegistry:
    """Load and cache prompts from PROMPTS_DIR."""

    def __init__(self, prompts_dir: Optional[str] = None):
        """Initialize registry with path to prompts directory.
        
        Args:
            prompts_dir: Path to directory containing prompt files.
                        Defaults to src/prompts/ relative to this file.
        """
        if prompts_dir is None:
            prompts_dir = os.path.join(os.path.dirname(__file__), "prompts")
        self.prompts_dir = prompts_dir
        self._cache: Dict[str, str] = {}

    def get_prompt(self, stage: str) -> str:
        """Load and cache a prompt by stage name.
        
        Args:
            stage: Stage name (e.g., "job_posting", "work_experience", "cover_letter").
        
        Returns:
            Prompt text as a string.
        
        Raises:
            FileNotFoundError: If prompt file does not exist.
        """
        if stage in self._cache:
            return self._cache[stage]

        filename = f"{stage}.txt"
        filepath = os.path.join(self.prompts_dir, filename)

        if not os.path.exists(filepath):
            raise FileNotFoundError(
                f"Prompt file not found: {filepath}. "
                f"Available stages should have corresponding .txt files in {self.prompts_dir}/"
            )

        with open(filepath, "r", encoding="utf-8") as f:
            prompt_text = f.read().strip()

        self._cache[stage] = prompt_text
        return prompt_text

    def clear_cache(self):
        """Clear the in-memory cache (useful for testing)."""
        self._cache.clear()


# Global singleton instance (lazy-loaded in function_app.py)
_global_registry: Optional[PromptRegistry] = None


def get_prompt_registry() -> PromptRegistry:
    """Get or create the global prompt registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = PromptRegistry()
    return _global_registry


def get_prompt(stage: str) -> str:
    """Convenience function: get a prompt by stage name.
    
    Args:
        stage: Stage name.
    
    Returns:
        Prompt text.
    """
    return get_prompt_registry().get_prompt(stage)
