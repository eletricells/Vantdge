"""
Prompt Templates for Case Series Analysis

Provides clean function-based access to prompt templates.
Templates are stored as Jinja2 files and rendered at runtime.
"""

from src.case_series.prompts.extraction_prompts import (
    build_main_extraction_prompt,
    build_section_identification_prompt,
    build_efficacy_extraction_prompt,
    build_safety_extraction_prompt,
)
from src.case_series.prompts.filtering_prompts import (
    build_paper_filter_prompt,
    build_disease_classification_prompt,
)
from src.case_series.prompts.market_prompts import (
    build_epidemiology_prompt,
    build_treatments_prompt,
    build_pipeline_prompt,
    build_tam_prompt,
)

__all__ = [
    # Extraction
    "build_main_extraction_prompt",
    "build_section_identification_prompt",
    "build_efficacy_extraction_prompt",
    "build_safety_extraction_prompt",
    # Filtering
    "build_paper_filter_prompt",
    "build_disease_classification_prompt",
    # Market
    "build_epidemiology_prompt",
    "build_treatments_prompt",
    "build_pipeline_prompt",
    "build_tam_prompt",
]
