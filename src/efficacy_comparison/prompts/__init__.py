"""
Extraction prompts for the Efficacy Comparison module.

This module contains prompt templates for extracting comprehensive
efficacy data from clinical trial publications.
"""

from .extraction_prompts import (
    build_trial_metadata_prompt,
    build_baseline_extraction_prompt,
    build_efficacy_extraction_prompt,
    TRIAL_METADATA_SYSTEM_PROMPT,
    BASELINE_SYSTEM_PROMPT,
    EFFICACY_SYSTEM_PROMPT,
)

__all__ = [
    "build_trial_metadata_prompt",
    "build_baseline_extraction_prompt",
    "build_efficacy_extraction_prompt",
    "TRIAL_METADATA_SYSTEM_PROMPT",
    "BASELINE_SYSTEM_PROMPT",
    "EFFICACY_SYSTEM_PROMPT",
]
