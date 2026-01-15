"""
EndpointStandardizer Service

Standardizes endpoint names to canonical forms and discovers new endpoints.
Uses a combination of regex matching, fuzzy matching, and LLM classification.
"""

import json
import logging
import re
from typing import Dict, List, Optional, Tuple

import anthropic

from src.utils.config import get_settings

from src.efficacy_comparison.models import (
    EfficacyEndpoint,
    EndpointCategory,
    EndpointDefinition,
)
from src.efficacy_comparison.prompts.extraction_prompts import build_endpoint_discovery_prompt

logger = logging.getLogger(__name__)


# Haiku model for endpoint classification
CLASSIFICATION_MODEL = "claude-3-5-haiku-20241022"


# =============================================================================
# ENDPOINT LIBRARY - Canonical endpoint definitions
# =============================================================================

ENDPOINT_LIBRARY: Dict[str, EndpointDefinition] = {
    # Atopic Dermatitis endpoints
    "IGA 0/1": EndpointDefinition(
        endpoint_name_canonical="IGA 0/1",
        endpoint_name_full="Investigator Global Assessment score of 0 (clear) or 1 (almost clear)",
        aliases=["IGA response", "IGA success", "IGA 0 or 1", "IGA score 0/1", "vIGA-AD 0/1", "IGA-AD 0/1"],
        therapeutic_area="Dermatology",
        diseases=["Atopic Dermatitis", "Psoriasis"],
        endpoint_type="efficacy",
        endpoint_category_typical="Primary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 12", "Week 16"],
        response_threshold="Score of 0 or 1 with ≥2 point improvement",
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Skin",
    ),
    "EASI-50": EndpointDefinition(
        endpoint_name_canonical="EASI-50",
        endpoint_name_full="50% improvement in Eczema Area and Severity Index from baseline",
        aliases=["EASI 50", "EASI50", "50% EASI improvement", "EASI-50 response"],
        therapeutic_area="Dermatology",
        diseases=["Atopic Dermatitis"],
        endpoint_type="efficacy",
        endpoint_category_typical="Secondary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 12", "Week 16"],
        response_threshold="≥50% reduction from baseline",
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Skin",
    ),
    "EASI-75": EndpointDefinition(
        endpoint_name_canonical="EASI-75",
        endpoint_name_full="75% improvement in Eczema Area and Severity Index from baseline",
        aliases=["EASI 75", "EASI75", "75% EASI improvement", "EASI-75 response"],
        therapeutic_area="Dermatology",
        diseases=["Atopic Dermatitis"],
        endpoint_type="efficacy",
        endpoint_category_typical="Primary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 12", "Week 16", "Week 52"],
        response_threshold="≥75% reduction from baseline",
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Skin",
    ),
    "EASI-90": EndpointDefinition(
        endpoint_name_canonical="EASI-90",
        endpoint_name_full="90% improvement in Eczema Area and Severity Index from baseline",
        aliases=["EASI 90", "EASI90", "90% EASI improvement", "EASI-90 response"],
        therapeutic_area="Dermatology",
        diseases=["Atopic Dermatitis"],
        endpoint_type="efficacy",
        endpoint_category_typical="Secondary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 12", "Week 16"],
        response_threshold="≥90% reduction from baseline",
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Skin",
    ),
    "Pruritus NRS": EndpointDefinition(
        endpoint_name_canonical="Pruritus NRS",
        endpoint_name_full="Peak Pruritus Numerical Rating Scale",
        aliases=["PP-NRS", "Itch NRS", "pruritus score", "peak pruritus", "itch score", "NRS pruritus"],
        therapeutic_area="Dermatology",
        diseases=["Atopic Dermatitis"],
        endpoint_type="PRO",
        endpoint_category_typical="Secondary",
        measurement_type="continuous",
        direction="lower_better",
        typical_timepoints=["Week 4", "Week 12", "Week 16"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Skin",
    ),
    "DLQI": EndpointDefinition(
        endpoint_name_canonical="DLQI",
        endpoint_name_full="Dermatology Life Quality Index",
        aliases=["DLQI score", "dermatology quality of life"],
        therapeutic_area="Dermatology",
        diseases=["Atopic Dermatitis", "Psoriasis"],
        endpoint_type="PRO",
        endpoint_category_typical="Secondary",
        measurement_type="continuous",
        direction="lower_better",
        typical_timepoints=["Week 12", "Week 16"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=2,
        organ_domain="Skin",
    ),
    "POEM": EndpointDefinition(
        endpoint_name_canonical="POEM",
        endpoint_name_full="Patient-Oriented Eczema Measure",
        aliases=["POEM score"],
        therapeutic_area="Dermatology",
        diseases=["Atopic Dermatitis"],
        endpoint_type="PRO",
        endpoint_category_typical="Secondary",
        measurement_type="continuous",
        direction="lower_better",
        typical_timepoints=["Week 12", "Week 16"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=2,
        organ_domain="Skin",
    ),
    "SCORAD": EndpointDefinition(
        endpoint_name_canonical="SCORAD",
        endpoint_name_full="SCORing Atopic Dermatitis",
        aliases=["SCORAD score", "total SCORAD"],
        therapeutic_area="Dermatology",
        diseases=["Atopic Dermatitis"],
        endpoint_type="efficacy",
        endpoint_category_typical="Secondary",
        measurement_type="continuous",
        direction="lower_better",
        typical_timepoints=["Week 12", "Week 16"],
        is_validated=True,
        regulatory_acceptance="EMA",
        quality_tier=2,
        organ_domain="Skin",
    ),
    # Psoriasis endpoints
    "PASI-75": EndpointDefinition(
        endpoint_name_canonical="PASI-75",
        endpoint_name_full="75% improvement in Psoriasis Area and Severity Index",
        aliases=["PASI 75", "PASI75", "75% PASI"],
        therapeutic_area="Dermatology",
        diseases=["Psoriasis", "Plaque Psoriasis"],
        endpoint_type="efficacy",
        endpoint_category_typical="Primary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 12", "Week 16"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Skin",
    ),
    "PASI-90": EndpointDefinition(
        endpoint_name_canonical="PASI-90",
        endpoint_name_full="90% improvement in Psoriasis Area and Severity Index",
        aliases=["PASI 90", "PASI90", "90% PASI"],
        therapeutic_area="Dermatology",
        diseases=["Psoriasis", "Plaque Psoriasis"],
        endpoint_type="efficacy",
        endpoint_category_typical="Secondary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 12", "Week 16"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Skin",
    ),
    # Rheumatoid Arthritis endpoints
    "ACR20": EndpointDefinition(
        endpoint_name_canonical="ACR20",
        endpoint_name_full="American College of Rheumatology 20% response",
        aliases=["ACR 20", "ACR-20", "ACR20 response"],
        therapeutic_area="Rheumatology",
        diseases=["Rheumatoid Arthritis"],
        endpoint_type="efficacy",
        endpoint_category_typical="Primary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 12", "Week 24"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Joint",
    ),
    "ACR50": EndpointDefinition(
        endpoint_name_canonical="ACR50",
        endpoint_name_full="American College of Rheumatology 50% response",
        aliases=["ACR 50", "ACR-50", "ACR50 response"],
        therapeutic_area="Rheumatology",
        diseases=["Rheumatoid Arthritis"],
        endpoint_type="efficacy",
        endpoint_category_typical="Secondary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 12", "Week 24"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Joint",
    ),
    "ACR70": EndpointDefinition(
        endpoint_name_canonical="ACR70",
        endpoint_name_full="American College of Rheumatology 70% response",
        aliases=["ACR 70", "ACR-70", "ACR70 response"],
        therapeutic_area="Rheumatology",
        diseases=["Rheumatoid Arthritis"],
        endpoint_type="efficacy",
        endpoint_category_typical="Secondary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 12", "Week 24"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Joint",
    ),
    "DAS28-CRP": EndpointDefinition(
        endpoint_name_canonical="DAS28-CRP",
        endpoint_name_full="Disease Activity Score 28 joints using CRP",
        aliases=["DAS28", "DAS-28", "DAS28 CRP", "DAS28-CRP remission"],
        therapeutic_area="Rheumatology",
        diseases=["Rheumatoid Arthritis"],
        endpoint_type="efficacy",
        endpoint_category_typical="Secondary",
        measurement_type="continuous",
        direction="lower_better",
        typical_timepoints=["Week 12", "Week 24"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Joint",
    ),
    "HAQ-DI": EndpointDefinition(
        endpoint_name_canonical="HAQ-DI",
        endpoint_name_full="Health Assessment Questionnaire Disability Index",
        aliases=["HAQ", "HAQ-DI score", "HAQ score"],
        therapeutic_area="Rheumatology",
        diseases=["Rheumatoid Arthritis", "Psoriatic Arthritis"],
        endpoint_type="PRO",
        endpoint_category_typical="Secondary",
        measurement_type="continuous",
        direction="lower_better",
        typical_timepoints=["Week 12", "Week 24"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=2,
        organ_domain="Joint",
    ),
    # SLE endpoints
    "SRI-4": EndpointDefinition(
        endpoint_name_canonical="SRI-4",
        endpoint_name_full="SLE Responder Index 4",
        aliases=["SRI4", "SRI 4", "SRI-4 response"],
        therapeutic_area="Rheumatology",
        diseases=["Systemic Lupus Erythematosus", "SLE"],
        endpoint_type="efficacy",
        endpoint_category_typical="Primary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 52"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Systemic",
    ),
    "BICLA": EndpointDefinition(
        endpoint_name_canonical="BICLA",
        endpoint_name_full="British Isles Lupus Assessment Group-based Composite Lupus Assessment",
        aliases=["BICLA response"],
        therapeutic_area="Rheumatology",
        diseases=["Systemic Lupus Erythematosus", "SLE"],
        endpoint_type="efficacy",
        endpoint_category_typical="Primary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 52"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Systemic",
    ),
    "SLEDAI-2K": EndpointDefinition(
        endpoint_name_canonical="SLEDAI-2K",
        endpoint_name_full="SLE Disease Activity Index 2000",
        aliases=["SLEDAI", "SLEDAI-2K score", "SELENA-SLEDAI"],
        therapeutic_area="Rheumatology",
        diseases=["Systemic Lupus Erythematosus", "SLE"],
        endpoint_type="efficacy",
        endpoint_category_typical="Secondary",
        measurement_type="continuous",
        direction="lower_better",
        typical_timepoints=["Week 52"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="Systemic",
    ),
    # IBD endpoints
    "Clinical Remission": EndpointDefinition(
        endpoint_name_canonical="Clinical Remission",
        endpoint_name_full="Clinical Remission",
        aliases=["clinical remission rate", "remission"],
        therapeutic_area="Gastroenterology",
        diseases=["Ulcerative Colitis", "Crohn's Disease"],
        endpoint_type="efficacy",
        endpoint_category_typical="Primary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 8", "Week 52"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="GI",
    ),
    "Endoscopic Improvement": EndpointDefinition(
        endpoint_name_canonical="Endoscopic Improvement",
        endpoint_name_full="Endoscopic Improvement",
        aliases=["endoscopic response", "mucosal healing", "endoscopic remission"],
        therapeutic_area="Gastroenterology",
        diseases=["Ulcerative Colitis", "Crohn's Disease"],
        endpoint_type="efficacy",
        endpoint_category_typical="Primary",
        measurement_type="responder",
        direction="higher_better",
        typical_timepoints=["Week 8", "Week 52"],
        is_validated=True,
        regulatory_acceptance="FDA",
        quality_tier=1,
        organ_domain="GI",
    ),
}


class EndpointStandardizer:
    """
    Standardizes endpoint names to canonical forms.

    Methods:
    1. Exact match against library
    2. Alias matching
    3. Regex pattern matching
    4. LLM classification for unknown endpoints
    """

    def __init__(
        self,
        anthropic_client: Optional[anthropic.Anthropic] = None,
        use_llm_discovery: bool = True,
    ):
        """
        Initialize the standardizer.

        Args:
            anthropic_client: Optional Anthropic client for LLM discovery
            use_llm_discovery: Whether to use LLM for unknown endpoints
        """
        if anthropic_client:
            self.anthropic = anthropic_client
        else:
            settings = get_settings()
            self.anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.use_llm_discovery = use_llm_discovery

        # Build reverse lookup from aliases
        self._alias_lookup: Dict[str, str] = {}
        for canonical, defn in ENDPOINT_LIBRARY.items():
            for alias in defn.aliases:
                self._alias_lookup[alias.lower()] = canonical

        # Cache for discovered endpoints
        self._discovery_cache: Dict[str, str] = {}

    def standardize_endpoint(
        self,
        endpoint: EfficacyEndpoint,
        indication: str,
    ) -> EfficacyEndpoint:
        """
        Standardize an endpoint's name to canonical form.

        Args:
            endpoint: EfficacyEndpoint to standardize
            indication: Disease context for disambiguation

        Returns:
            EfficacyEndpoint with normalized name filled in
        """
        raw_name = endpoint.endpoint_name_raw
        if not raw_name:
            return endpoint

        # Try to find canonical name
        canonical = self._find_canonical_name(raw_name, indication)

        if canonical:
            endpoint.endpoint_name_normalized = canonical

            # Update category if not set and we have library info
            if not endpoint.endpoint_category and canonical in ENDPOINT_LIBRARY:
                defn = ENDPOINT_LIBRARY[canonical]
                cat_map = {
                    "Primary": EndpointCategory.PRIMARY,
                    "Secondary": EndpointCategory.SECONDARY,
                    "Exploratory": EndpointCategory.EXPLORATORY,
                }
                if defn.endpoint_category_typical:
                    endpoint.endpoint_category = cat_map.get(defn.endpoint_category_typical)

        return endpoint

    def standardize_endpoints(
        self,
        endpoints: List[EfficacyEndpoint],
        indication: str,
    ) -> List[EfficacyEndpoint]:
        """
        Standardize a list of endpoints.
        """
        return [self.standardize_endpoint(ep, indication) for ep in endpoints]

    def _find_canonical_name(
        self,
        raw_name: str,
        indication: str,
    ) -> Optional[str]:
        """
        Find canonical name for a raw endpoint name.
        """
        raw_lower = raw_name.lower().strip()

        # Method 1: Exact match
        for canonical in ENDPOINT_LIBRARY:
            if canonical.lower() == raw_lower:
                return canonical

        # Method 2: Alias lookup
        if raw_lower in self._alias_lookup:
            return self._alias_lookup[raw_lower]

        # Method 3: Partial alias match
        for alias, canonical in self._alias_lookup.items():
            if alias in raw_lower or raw_lower in alias:
                return canonical

        # Method 4: Pattern matching for common formats
        canonical = self._pattern_match(raw_name)
        if canonical:
            return canonical

        # Method 5: Check cache
        cache_key = f"{raw_lower}:{indication.lower()}"
        if cache_key in self._discovery_cache:
            return self._discovery_cache[cache_key]

        # Method 6: LLM discovery for unknown endpoints
        if self.use_llm_discovery:
            discovered = self._discover_endpoint(raw_name, indication)
            if discovered:
                self._discovery_cache[cache_key] = discovered
                return discovered

        # If all else fails, return None (will keep raw name)
        return None

    def _pattern_match(self, raw_name: str) -> Optional[str]:
        """
        Match common endpoint patterns.
        """
        raw_lower = raw_name.lower()

        # EASI patterns
        easi_match = re.search(r'easi[\s\-]?(\d+)', raw_lower)
        if easi_match:
            threshold = easi_match.group(1)
            return f"EASI-{threshold}"

        # PASI patterns
        pasi_match = re.search(r'pasi[\s\-]?(\d+)', raw_lower)
        if pasi_match:
            threshold = pasi_match.group(1)
            return f"PASI-{threshold}"

        # ACR patterns
        acr_match = re.search(r'acr[\s\-]?(\d+)', raw_lower)
        if acr_match:
            threshold = acr_match.group(1)
            return f"ACR{threshold}"

        # SRI patterns
        sri_match = re.search(r'sri[\s\-]?(\d+)', raw_lower)
        if sri_match:
            threshold = sri_match.group(1)
            return f"SRI-{threshold}"

        # IGA patterns
        if re.search(r'iga.*0.*1|iga.*success|iga.*response', raw_lower):
            return "IGA 0/1"

        # Pruritus NRS
        if re.search(r'pruritus|itch|pp[\s\-]?nrs', raw_lower):
            return "Pruritus NRS"

        return None

    def _discover_endpoint(
        self,
        raw_name: str,
        indication: str,
    ) -> Optional[str]:
        """
        Use LLM to classify an unknown endpoint.
        """
        try:
            prompt = build_endpoint_discovery_prompt(
                endpoint_name=raw_name,
                indication=indication,
            )

            response = self.anthropic.messages.create(
                model=CLASSIFICATION_MODEL,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text.strip()

            # Parse JSON
            if response_text.startswith("```"):
                response_text = re.sub(r"```json?\n?", "", response_text)
                response_text = response_text.rstrip("`")

            result = json.loads(response_text)
            canonical = result.get("endpoint_name_canonical")

            if canonical:
                logger.info(f"Discovered endpoint: {raw_name} -> {canonical}")
                return canonical

        except Exception as e:
            logger.warning(f"Endpoint discovery failed for '{raw_name}': {e}")

        return None

    def get_endpoint_definition(self, canonical_name: str) -> Optional[EndpointDefinition]:
        """
        Get full definition for a canonical endpoint name.
        """
        return ENDPOINT_LIBRARY.get(canonical_name)

    def get_expected_endpoints(self, indication: str) -> List[str]:
        """
        Get expected endpoint names for a disease.
        """
        indication_lower = indication.lower()
        endpoints = []

        for canonical, defn in ENDPOINT_LIBRARY.items():
            if defn.diseases:
                for disease in defn.diseases:
                    if disease.lower() in indication_lower or indication_lower in disease.lower():
                        endpoints.append(canonical)
                        break

        return list(set(endpoints))
