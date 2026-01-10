"""
Filtering Prompt Builders

Functions for building prompts for paper filtering and classification.
"""

from typing import Dict, Any, List, Optional

from src.prompts import get_prompt_manager


def build_paper_filter_prompt(
    drug_name: str,
    papers: List[Dict[str, Any]],
    approved_indications: List[str],
) -> str:
    """
    Build prompt for filtering papers for relevance.

    Filters out papers that are:
    - Not about the drug
    - About approved indications only
    - Reviews/editorials without clinical data

    Args:
        drug_name: Name of the drug
        papers: List of paper dicts with title, abstract, pmid
        approved_indications: List of approved indications to exclude

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    # Format papers as text for the template
    papers_text_parts = []
    for i, paper in enumerate(papers, 1):
        pmid = paper.get('pmid', f'paper_{i}')
        title = paper.get('title', 'No title')
        abstract = paper.get('abstract', 'No abstract')[:1500]
        papers_text_parts.append(f"--- Paper {i} (PMID: {pmid}) ---\nTitle: {title}\nAbstract: {abstract}\n")

    papers_text = "\n".join(papers_text_parts)
    exclude_indications = ", ".join(approved_indications) if approved_indications else "None"

    return prompts.render(
        "case_series/filter_papers",
        drug_name=drug_name,
        papers_text=papers_text,
        exclude_indications=exclude_indications,
        batch_size=len(papers),
    )


def build_disease_classification_prompt(
    drug_name: str,
    papers: List[Dict[str, Any]],
    approved_indications: List[str],
) -> str:
    """
    Build prompt for classifying papers by disease.

    Extracts the disease/condition being studied from each paper.

    Args:
        drug_name: Name of the drug
        papers: List of paper dicts with title, abstract, pmid
        approved_indications: List of approved indications for context

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    return prompts.render(
        "case_series/classify_papers_by_disease",
        drug_name=drug_name,
        papers=papers,
        approved_indications=approved_indications,
    )


def build_disease_and_drug_classification_prompt(
    papers: List[Dict[str, Any]],
) -> str:
    """
    Build prompt for classifying papers by disease and drug.

    Used when analyzing multiple drugs simultaneously.

    Args:
        papers: List of paper dicts with title, abstract, pmid

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    return prompts.render(
        "case_series/classify_papers_by_disease_and_drug",
        papers=papers,
    )


def build_disease_mapping_prompt(
    diseases: List[str],
    known_mappings: Optional[Dict[str, str]] = None,
) -> str:
    """
    Build prompt for inferring disease name mappings.

    Maps variant disease names to canonical forms.

    Args:
        diseases: List of raw disease names
        known_mappings: Optional dict of known mappings

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    return prompts.render(
        "case_series/infer_disease_mapping",
        diseases=diseases,
        known_mappings=known_mappings or {},
    )
