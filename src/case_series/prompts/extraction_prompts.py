"""
Extraction Prompt Builders

Functions for building prompts for case series data extraction.
Uses underlying Jinja2 templates from src/prompts/templates/case_series/.
"""

from typing import Dict, Any, List, Optional

from src.prompts import get_prompt_manager


def build_main_extraction_prompt(
    drug_name: str,
    drug_info: Dict[str, Any],
    paper_title: str,
    paper_content: str,
    max_content_length: int = 40000,
    is_full_text: bool = False,
) -> str:
    """
    Build prompt for main case series data extraction.

    This is used for single-pass extraction from abstracts or short content.

    Args:
        drug_name: Name of the drug
        drug_info: Dict with mechanism, target, approved_indications
        paper_title: Title of the paper
        paper_content: Abstract or full text content
        max_content_length: Maximum content length to include
        is_full_text: Whether content is full text (vs abstract)

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    # Determine content label based on content type
    content_label = "Full Text" if is_full_text else "Abstract"

    return prompts.render(
        "case_series/main_extraction",
        drug_name=drug_name,
        mechanism=drug_info.get('mechanism', 'Unknown'),
        target=drug_info.get('target', 'Unknown'),
        approved_indications=drug_info.get('approved_indications', []),
        paper_title=paper_title,
        content_label=content_label,
        content=paper_content[:max_content_length] if paper_content else "",
    )


def build_section_identification_prompt(
    drug_name: str,
    paper_title: str,
    paper_content: str,
    max_content_length: int = 30000,
) -> str:
    """
    Build prompt for Stage 1: Section identification.

    Identifies data-containing sections (tables, figures, results).

    Args:
        drug_name: Name of the drug
        paper_title: Title of the paper
        paper_content: Full text content
        max_content_length: Maximum content length to include

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    return prompts.render(
        "case_series/stage1_sections",
        drug_name=drug_name,
        paper_title=paper_title,
        paper_content=paper_content[:max_content_length],
    )


def build_efficacy_extraction_prompt(
    drug_name: str,
    drug_info: Dict[str, Any],
    paper_content: str,
    sections: Dict[str, Any],
    max_content_length: int = 35000,
) -> str:
    """
    Build prompt for Stage 2: Detailed efficacy extraction.

    Extracts structured efficacy endpoints with quality assessment.

    Args:
        drug_name: Name of the drug
        drug_info: Dict with mechanism info
        paper_content: Full text content
        sections: Sections identified in Stage 1
        max_content_length: Maximum content length to include

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    # Defensive handling: sections might be None or not a dict
    efficacy_tables = []
    if isinstance(sections, dict):
        tables_val = sections.get('efficacy_tables', [])
        if isinstance(tables_val, list):
            efficacy_tables = [t for t in tables_val if t is not None]
        elif isinstance(tables_val, str):
            efficacy_tables = [tables_val]
    tables_info = ", ".join(str(t) for t in efficacy_tables) or "None identified"

    return prompts.render(
        "case_series/stage2_efficacy",
        drug_name=drug_name,
        mechanism=drug_info.get('mechanism', 'Unknown'),
        efficacy_tables=tables_info,
        paper_content=paper_content[:max_content_length],
    )


def build_safety_extraction_prompt(
    drug_name: str,
    paper_content: str,
    sections: Dict[str, Any],
    max_content_length: int = 30000,
) -> str:
    """
    Build prompt for Stage 3: Detailed safety extraction.

    Extracts structured safety endpoints with MedDRA classification.

    Args:
        drug_name: Name of the drug
        paper_content: Full text content
        sections: Sections identified in Stage 1
        max_content_length: Maximum content length to include

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    # Defensive handling: sections might be None or not a dict
    safety_tables = []
    if isinstance(sections, dict):
        tables_val = sections.get('safety_tables', [])
        if isinstance(tables_val, list):
            safety_tables = [t for t in tables_val if t is not None]
        elif isinstance(tables_val, str):
            safety_tables = [tables_val]
    tables_info = ", ".join(str(t) for t in safety_tables) or "None identified"

    return prompts.render(
        "case_series/stage3_safety",
        drug_name=drug_name,
        safety_tables=tables_info,
        paper_content=paper_content[:max_content_length],
    )


def build_drug_info_prompt(
    drug_name: str,
    dailymed_content: Optional[str] = None,
    drugs_com_content: Optional[str] = None,
) -> str:
    """
    Build prompt for extracting drug information.

    Args:
        drug_name: Name of the drug
        dailymed_content: Optional content from DailyMed
        drugs_com_content: Optional content from Drugs.com

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    return prompts.render(
        "case_series/extract_drug_info",
        drug_name=drug_name,
        dailymed_content=dailymed_content or "",
        drugs_com_content=drugs_com_content or "",
    )


def build_disease_standardization_prompt(
    diseases: List[str],
    canonical_diseases: Optional[List[str]] = None,
) -> str:
    """
    Build prompt for standardizing disease names.

    Args:
        diseases: List of raw disease names to standardize
        canonical_diseases: Optional list of known canonical names

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    return prompts.render(
        "case_series/standardize_diseases",
        diseases=diseases,
        canonical_diseases=canonical_diseases or [],
    )
