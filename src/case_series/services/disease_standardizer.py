"""
Disease Standardizer Service

Normalizes disease names to canonical forms for consistent
aggregation and market intelligence lookup.

Uses DiseaseTaxonomy for hierarchical disease/subtype extraction.
"""

import logging
import unicodedata
from typing import Dict, List, Optional, Any, Tuple

from src.case_series.protocols.llm_protocol import LLMClient
from src.case_series.protocols.database_protocol import CaseSeriesRepositoryProtocol
from src.case_series.taxonomy import get_default_taxonomy, DiseaseTaxonomy

logger = logging.getLogger(__name__)


# Default disease name variants for search expansion
DEFAULT_DISEASE_VARIANTS = {
    "Primary Sjogren's syndrome": [
        "Sjogren syndrome", "Sjögren's disease", "Sjögren syndrome",
        "sicca syndrome", "primary Sjögren's"
    ],
    "Systemic Lupus Erythematosus": ["SLE", "lupus erythematosus", "systemic lupus"],
    "Rheumatoid Arthritis": ["RA", "rheumatoid"],
    "Atopic Dermatitis": ["AD", "atopic eczema", "eczema"],
    "Dermatomyositis": ["DM", "inflammatory myopathy"],
    "Alopecia Areata": ["AA", "alopecia totalis", "alopecia universalis"],
    "Giant Cell Arteritis": ["GCA", "temporal arteritis"],
    "Takayasu arteritis": ["TAK", "Takayasu's arteritis", "large vessel vasculitis"],
    "Juvenile Idiopathic Arthritis": ["JIA", "juvenile arthritis", "juvenile rheumatoid arthritis"],
    "Adult-onset Still's Disease": ["AOSD", "Still's disease", "adult Still disease"],
    "Graft-versus-Host Disease": ["GVHD", "graft versus host", "GvHD"],
    "Inflammatory Bowel Disease": ["IBD", "Crohn's disease", "ulcerative colitis"],
    "Psoriatic Arthritis": ["PsA", "psoriatic"],
    "Ankylosing Spondylitis": ["AS", "axial spondyloarthritis", "axSpA"],
    "Myasthenia Gravis": ["MG", "myasthenia"],
    "Immune Thrombocytopenia": ["ITP", "immune thrombocytopenic purpura"],
}

# Default parent disease mappings
DEFAULT_PARENT_MAPPINGS = {
    # SLE variants
    "Systemic Lupus Erythematosus with alopecia universalis and arthritis": "Systemic Lupus Erythematosus",
    "SLE with cutaneous manifestations": "Systemic Lupus Erythematosus",
    "refractory systemic lupus erythematosus": "Systemic Lupus Erythematosus",
    # Alopecia variants
    "severe alopecia areata with atopic dermatitis in children": "Alopecia Areata",
    "pediatric alopecia universalis": "Alopecia Areata",
    "alopecia totalis": "Alopecia Areata",
    # Dermatomyositis variants
    "refractory dermatomyositis": "Dermatomyositis",
    "anti-MDA5 antibody-positive dermatomyositis": "Dermatomyositis",
    "Juvenile dermatomyositis-associated calcinosis": "Juvenile Dermatomyositis",
    # JIA variants
    "juvenile idiopathic arthritis associated uveitis": "Juvenile Idiopathic Arthritis",
    "Systemic juvenile idiopathic arthritis with lung disease": "Systemic Juvenile Idiopathic Arthritis",
    # Atopic Dermatitis variants
    "atopic dermatitis": "Atopic Dermatitis",
    "moderate-to-severe atopic dermatitis": "Atopic Dermatitis",
}


class DiseaseStandardizer:
    """
    Standardizes disease names to canonical forms.

    Uses a combination of:
    - DiseaseTaxonomy for hierarchical disease/subtype extraction
    - Static mappings from database/defaults
    - LLM-based fuzzy matching for unknown diseases
    """

    def __init__(
        self,
        repository: Optional[CaseSeriesRepositoryProtocol] = None,
        llm_client: Optional[LLMClient] = None,
        taxonomy: Optional[DiseaseTaxonomy] = None,
    ):
        """
        Initialize the disease standardizer.

        Args:
            repository: Optional repository for loading mappings
            llm_client: Optional LLM client for fuzzy matching
            taxonomy: Optional taxonomy (uses default if not provided)
        """
        self._repository = repository
        self._llm_client = llm_client
        self._taxonomy = taxonomy or get_default_taxonomy()
        self._variants: Optional[Dict[str, List[str]]] = None
        self._parent_mappings: Optional[Dict[str, str]] = None

    def normalize_unicode(self, text: str) -> str:
        """
        Normalize Unicode characters (ö → o, é → e, etc.).

        Args:
            text: Text with potential Unicode characters

        Returns:
            ASCII-normalized text
        """
        if not text:
            return text
        # NFKD decomposition separates base chars from diacritics
        normalized = unicodedata.normalize('NFKD', text)
        # Remove diacritical marks (category 'Mn')
        ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        return ascii_text

    def standardize(self, disease: str) -> str:
        """
        Standardize a single disease name.

        Args:
            disease: Raw disease name

        Returns:
            Canonical disease name
        """
        if not disease:
            return disease

        # Step 0: Unicode normalization (Sjögren → Sjogren)
        disease = self.normalize_unicode(disease)

        # FIRST: Try taxonomy-based normalization
        canonical = self._taxonomy.normalize(disease)
        if canonical:
            return canonical

        disease_lower = disease.lower().strip()

        # SECOND: Check parent mappings
        parent_mappings = self._get_parent_mappings()
        for variant, parent in parent_mappings.items():
            # Also normalize the variant for comparison
            variant_normalized = self.normalize_unicode(variant).lower()
            if variant_normalized == disease_lower:
                return parent

        # THIRD: Check disease variants
        variants = self._get_disease_variants()
        for canonical, variant_list in variants.items():
            # Normalize canonical name for comparison
            canonical_normalized = self.normalize_unicode(canonical).lower()
            if disease_lower == canonical_normalized:
                return canonical
            for variant in variant_list:
                variant_normalized = self.normalize_unicode(variant).lower()
                if disease_lower == variant_normalized:
                    return canonical

        # No match found - return with title case for consistency
        return disease.strip().title()

    def extract_disease_and_subtype(self, raw_disease: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract canonical disease and subtype from raw text.

        Uses taxonomy for proper hierarchy extraction.

        Args:
            raw_disease: Raw disease text (e.g., "amyopathic dermatomyositis")

        Returns:
            Tuple of (canonical_disease, subtype) e.g., ("Dermatomyositis", "Amyopathic")
        """
        return self._taxonomy.extract_disease_and_subtype(raw_disease)

    def get_disease_category(self, disease: str) -> Optional[str]:
        """
        Get the therapeutic category for a disease.

        Args:
            disease: Disease name

        Returns:
            Category name (e.g., "Inflammatory Myopathies") or None
        """
        entry = self._taxonomy.get_disease(disease)
        if entry:
            return entry.category
        return None

    def get_standard_endpoints(self, disease: str) -> List[str]:
        """
        Get standard clinical endpoints for a disease.

        Args:
            disease: Disease name

        Returns:
            List of standard endpoint names
        """
        endpoints = self._taxonomy.get_standard_endpoints(disease)
        return [ep.name for ep in endpoints]

    def normalize_endpoint(self, endpoint: str, disease: str) -> Optional[str]:
        """
        Normalize endpoint name using disease context.

        Args:
            endpoint: Raw endpoint name
            disease: Disease for context

        Returns:
            Normalized endpoint name or None
        """
        return self._taxonomy.normalize_endpoint(endpoint, disease)

    def standardize_batch(self, diseases: List[str]) -> Dict[str, str]:
        """
        Standardize a batch of disease names.

        Args:
            diseases: List of raw disease names

        Returns:
            Dict mapping raw names to canonical names
        """
        result = {}
        for disease in diseases:
            result[disease] = self.standardize(disease)
        return result

    def get_parent_disease(self, disease: str) -> str:
        """
        Get the parent/canonical disease for a specific variant.

        Used to group related diseases for market intelligence.

        Args:
            disease: Disease name (possibly a subtype)

        Returns:
            Parent disease name, or the input if no parent found
        """
        # FIRST: Try taxonomy-based parent lookup
        parent = self._taxonomy.get_parent_disease(disease)
        if parent:
            return parent

        # SECOND: Check static parent mappings
        parent_mappings = self._get_parent_mappings()
        disease_lower = disease.lower().strip()

        for variant, parent in parent_mappings.items():
            if variant.lower() == disease_lower:
                return parent

        return disease

    def get_search_variants(self, disease: str) -> List[str]:
        """
        Get all search variants for a disease.

        Used to expand search queries for better coverage.

        Args:
            disease: Canonical disease name

        Returns:
            List of variant names including the original
        """
        variants = self._get_disease_variants()
        disease_lower = disease.lower().strip()

        # Find canonical form
        canonical = disease
        for can_name, var_list in variants.items():
            if can_name.lower() == disease_lower:
                canonical = can_name
                break
            for var in var_list:
                if var.lower() == disease_lower:
                    canonical = can_name
                    break

        # Return all variants
        result = [canonical]
        if canonical in variants:
            result.extend(variants[canonical])

        return result

    async def standardize_with_llm(
        self,
        diseases: List[str],
        known_canonicals: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """
        Use LLM to standardize disease names.

        Falls back to simple standardization if LLM not available.

        Args:
            diseases: List of raw disease names
            known_canonicals: Optional list of known canonical names

        Returns:
            Dict mapping raw names to canonical names
        """
        if not self._llm_client:
            return self.standardize_batch(diseases)

        # Build prompt for LLM
        from src.case_series.prompts.extraction_prompts import build_disease_standardization_prompt

        prompt = build_disease_standardization_prompt(
            diseases=diseases,
            canonical_diseases=known_canonicals,
        )

        try:
            response = await self._llm_client.complete(prompt, max_tokens=2000)

            # Parse JSON response
            import json
            result = json.loads(response)

            if isinstance(result, dict):
                return result
            elif isinstance(result, list):
                # Convert list of {raw, canonical} to dict
                return {item['raw']: item['canonical'] for item in result}
        except Exception as e:
            logger.warning(f"LLM standardization failed: {e}, using fallback")

        return self.standardize_batch(diseases)

    def _get_disease_variants(self) -> Dict[str, List[str]]:
        """Get disease variant mappings."""
        if self._variants is not None:
            return self._variants

        if self._repository:
            try:
                variants = self._repository.get_disease_variants()
                if variants:
                    self._variants = variants
                    return self._variants
            except Exception as e:
                logger.warning(f"Failed to load disease variants: {e}")

        self._variants = DEFAULT_DISEASE_VARIANTS.copy()
        return self._variants

    def _get_parent_mappings(self) -> Dict[str, str]:
        """Get parent disease mappings."""
        if self._parent_mappings is not None:
            return self._parent_mappings

        if self._repository:
            try:
                mappings = self._repository.get_disease_parent_mappings()
                if mappings:
                    self._parent_mappings = mappings
                    return self._parent_mappings
            except Exception as e:
                logger.warning(f"Failed to load parent mappings: {e}")

        self._parent_mappings = DEFAULT_PARENT_MAPPINGS.copy()
        return self._parent_mappings

    # =========================================================================
    # Hierarchy Methods for UI Display
    # =========================================================================

    def get_hierarchical_diseases(
        self,
        diseases: List[str],
    ) -> Dict[str, List[str]]:
        """
        Organize diseases into parent-child hierarchy.

        Args:
            diseases: List of disease names from extractions

        Returns:
            Dict mapping parent_disease -> [child_disease_1, child_disease_2, ...]
            Parent diseases without children map to empty list.
            Diseases that ARE the parent also appear as children for display.
        """
        hierarchy: Dict[str, List[str]] = {}

        for disease in diseases:
            if not disease:
                continue

            # Get the parent for this disease
            parent = self.get_parent_disease(disease)

            if parent not in hierarchy:
                hierarchy[parent] = []

            # Add the disease as a child (even if it's also the parent)
            if disease not in hierarchy[parent]:
                hierarchy[parent].append(disease)

        # Sort children within each parent
        for parent in hierarchy:
            hierarchy[parent] = sorted(hierarchy[parent])

        return hierarchy

    def get_display_hierarchy(
        self,
        diseases: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Build display-ready hierarchy structure.

        Groups diseases by parent, with structure suitable for UI rendering.

        Args:
            diseases: List of disease names from extractions

        Returns:
            List of dicts with structure:
            [
                {
                    "parent": "Systemic Lupus Erythematosus",
                    "parent_normalized": "Systemic Lupus Erythematosus",
                    "children": [
                        {"name": "Lupus Nephritis", "normalized": "Lupus Nephritis", "is_same_as_parent": False},
                        {"name": "SLE", "normalized": "Systemic Lupus Erythematosus", "is_same_as_parent": True}
                    ],
                    "child_count": 2,
                    "is_parent_only": False  # True if parent has no distinct children
                }
            ]
        """
        # Get raw hierarchy
        hierarchy = self.get_hierarchical_diseases(diseases)

        result = []
        for parent, children in sorted(hierarchy.items()):
            # Normalize parent
            parent_normalized = self.standardize(parent)

            # Build children list
            child_list = []
            for child in children:
                child_normalized = self.standardize(child)
                is_same_as_parent = (
                    child.lower() == parent.lower() or
                    child_normalized.lower() == parent_normalized.lower()
                )
                child_list.append({
                    "name": child,
                    "normalized": child_normalized,
                    "is_same_as_parent": is_same_as_parent,
                })

            # Determine if parent has any distinct children
            distinct_children = [c for c in child_list if not c["is_same_as_parent"]]
            is_parent_only = len(distinct_children) == 0

            result.append({
                "parent": parent,
                "parent_normalized": parent_normalized,
                "children": child_list,
                "child_count": len(children),
                "distinct_child_count": len(distinct_children),
                "is_parent_only": is_parent_only,
            })

        return result

    def assign_parent_diseases(
        self,
        extractions: List[Any],
    ) -> List[Any]:
        """
        Assign parent_disease attribute to each extraction.

        Args:
            extractions: List of CaseSeriesExtraction objects

        Returns:
            Same list with parent_disease assigned on each extraction
        """
        for ext in extractions:
            disease = getattr(ext, 'disease_normalized', None) or getattr(ext, 'disease', None)
            if disease:
                parent = self.get_parent_disease(disease)
                # Only set parent if different from disease itself
                ext.parent_disease = parent if parent.lower() != disease.lower() else None

        return extractions
