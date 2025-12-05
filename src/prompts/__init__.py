"""
Vantdge Prompt Management Module

Provides centralized prompt template management with Jinja2 rendering.

Features:
- Template loading from files
- Variable substitution with Jinja2
- Caching for performance
- Reusable prompt components (partials)
"""

from .manager import PromptManager, get_prompt_manager

__all__ = [
    "PromptManager",
    "get_prompt_manager",
]

