"""
Shared disease term expansion using MeSH API.

Provides consistent disease synonym discovery for use across:
- Pipeline Intelligence (clinical trial search)
- Disease Intelligence (PubMed epidemiology search)
- Disease Analysis (unified workflow)
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Import MeSH client (optional dependency)
try:
    from src.drug_extraction_system.api_clients.mesh_client import MeSHClient
    MESH_CLIENT_AVAILABLE = True
except ImportError:
    MESH_CLIENT_AVAILABLE = False
    logger.debug("MeSH client not available - disease term expansion will be limited")


@dataclass
class DiseaseTermExpansion:
    """Result of disease term expansion."""
    original_name: str
    mesh_id: Optional[str] = None
    preferred_name: Optional[str] = None
    search_terms: List[str] = field(default_factory=list)

    @property
    def synonyms(self) -> List[str]:
        """Alias for search_terms for backwards compatibility."""
        return self.search_terms


def expand_disease_terms(
    disease_name: str,
    mesh_client: Optional[Any] = None,
) -> DiseaseTermExpansion:
    """
    Expand disease name to comprehensive search terms using MeSH.

    This is the canonical function for disease term expansion used by
    both Pipeline Intelligence and Disease Intelligence.

    Args:
        disease_name: Original disease name (e.g., "Sjogren's syndrome")
        mesh_client: Optional pre-configured MeSH client. If None, creates one.

    Returns:
        DiseaseTermExpansion with mesh_id, preferred_name, and search_terms

    Example:
        >>> result = expand_disease_terms("Sjogren's syndrome")
        >>> result.search_terms
        ["sjogren's syndrome", "sjögren syndrome", "sjogrens syndrome", ...]
        >>> result.mesh_id
        "D012859"
    """
    search_terms = set([disease_name.lower()])
    mesh_id = None
    preferred_name = disease_name

    # Get or create MeSH client
    client = mesh_client
    if client is None and MESH_CLIENT_AVAILABLE:
        try:
            client = MeSHClient()
        except Exception as e:
            logger.debug(f"Failed to create MeSH client: {e}")
            client = None

    # Try MeSH lookup with different name variations
    if client:
        # Get first word without apostrophes for fallback search
        first_word = disease_name.split()[0] if " " in disease_name else disease_name
        first_word_clean = first_word.replace("'s", "").replace("'s", "").replace("'", "")

        # Try original name first, then variations without apostrophes/special chars
        name_variations = [
            disease_name,
            disease_name.replace("'s", "s").replace("'s", "s"),  # Remove possessive
            disease_name.replace("'", "").replace("'", ""),  # Remove apostrophes
            first_word_clean,  # First word without apostrophes (e.g., "Sjogren" from "Sjogren's")
        ]

        for name_var in name_variations:
            try:
                mesh_data = client.get_disease_search_terms(name_var)
                if mesh_data and mesh_data.get("mesh_id"):
                    mesh_id = mesh_data.get("mesh_id")
                    preferred_name = mesh_data.get("preferred_name", disease_name)
                    for term in mesh_data.get("search_terms", []):
                        search_terms.add(term.lower())
                    logger.info(f"MeSH match found via '{name_var}': {preferred_name} ({mesh_id})")
                    break
            except Exception as e:
                logger.debug(f"MeSH lookup failed for '{name_var}': {e}")
                continue

    # Add common variations programmatically
    for term in list(search_terms):
        # Handle apostrophe variations
        search_terms.add(term.replace("'s", "s"))
        search_terms.add(term.replace("'s", "'s"))
        search_terms.add(term.replace("'", ""))
        # Handle umlaut variations
        search_terms.add(term.replace("ö", "o"))
        search_terms.add(term.replace("ü", "u"))
        search_terms.add(term.replace("ä", "a"))

    # Remove empty strings and duplicates
    search_terms_list = [t for t in search_terms if t.strip()]

    logger.info(f"Expanded '{disease_name}' to {len(search_terms_list)} search terms")

    return DiseaseTermExpansion(
        original_name=disease_name,
        mesh_id=mesh_id,
        preferred_name=preferred_name,
        search_terms=search_terms_list,
    )


async def expand_disease_terms_async(
    disease_name: str,
    mesh_client: Optional[Any] = None,
) -> DiseaseTermExpansion:
    """
    Async wrapper for expand_disease_terms.

    The underlying MeSH API calls are synchronous, but this provides
    a consistent async interface for services that are fully async.
    """
    # MeSH lookups are HTTP-based and relatively fast, so we just call sync
    return expand_disease_terms(disease_name, mesh_client)
