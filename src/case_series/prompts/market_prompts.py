"""
Market Intelligence Prompt Builders

Functions for building prompts for market intelligence gathering.
"""

from typing import Dict, Any, List, Optional

from src.prompts import get_prompt_manager


def build_epidemiology_prompt(
    disease: str,
    search_results: List[Dict[str, Any]],
    disease_variants: Optional[List[str]] = None,
) -> str:
    """
    Build prompt for extracting epidemiology data.

    Extracts prevalence, incidence, and patient population estimates.

    Args:
        disease: Disease name
        search_results: List of web search results with url, title, content
        disease_variants: Optional list of disease name variants searched

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    return prompts.render(
        "case_series/extract_epidemiology",
        disease=disease,
        search_results=search_results,
        disease_variants=disease_variants or [disease],
    )


def build_treatments_prompt(
    disease: str,
    search_results: List[Dict[str, Any]],
) -> str:
    """
    Build prompt for extracting treatment/standard of care data.

    Extracts approved drugs, efficacy data, and treatment paradigm.

    Args:
        disease: Disease name
        search_results: List of web search results

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    return prompts.render(
        "case_series/extract_treatments",
        disease=disease,
        search_results=search_results,
    )


def build_pipeline_prompt(
    disease: str,
    search_results: List[Dict[str, Any]],
) -> str:
    """
    Build prompt for extracting pipeline/clinical trials data.

    Extracts drugs in development, trial phases, and expected timelines.

    Args:
        disease: Disease name
        search_results: List of web search results

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    return prompts.render(
        "case_series/extract_pipeline",
        disease=disease,
        search_results=search_results,
    )


def build_tam_prompt(
    disease: str,
    epidemiology: Dict[str, Any],
    treatments: Dict[str, Any],
    search_results: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Build prompt for calculating Total Addressable Market (TAM).

    Calculates market size based on prevalence and treatment costs.

    Args:
        disease: Disease name
        epidemiology: Epidemiology data dict
        treatments: Treatment/SOC data dict
        search_results: Optional additional search results

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    return prompts.render(
        "case_series/calculate_tam",
        disease=disease,
        epidemiology=epidemiology,
        treatments=treatments,
        search_results=search_results or [],
    )


def build_drugs_by_mechanism_prompt(
    mechanism: str,
    search_results: List[Dict[str, Any]],
) -> str:
    """
    Build prompt for extracting drugs by mechanism of action.

    Args:
        mechanism: Mechanism of action (e.g., "JAK inhibitor")
        search_results: List of search results about the mechanism

    Returns:
        Rendered prompt string
    """
    prompts = get_prompt_manager()

    return prompts.render(
        "case_series/extract_drugs_by_mechanism",
        mechanism=mechanism,
        search_results=search_results,
    )
