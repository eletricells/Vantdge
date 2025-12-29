"""
Drug Name Resolver

Resolves drug names (brand, generic, research codes) to standardized identifiers.
"""

import re
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from src.drug_extraction_system.api_clients.rxnorm_client import RxNormClient
from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient

logger = logging.getLogger(__name__)


@dataclass
class ResolvedDrug:
    """Resolved drug information."""
    original_name: str
    generic_name: Optional[str] = None
    brand_name: Optional[str] = None
    rxcui: Optional[str] = None
    is_approved: bool = False
    name_type: str = "unknown"  # "brand", "generic", "research_code"
    confidence: str = "low"  # "high", "medium", "low"


class DrugNameResolver:
    """
    Resolves drug names to standardized identifiers.
    
    Handles:
    - Brand names (e.g., "Rinvoq")
    - Generic names (e.g., "upadacitinib")
    - Research codes (e.g., "ABT-494")
    """

    # Pattern for research codes (e.g., ABT-494, BMS-986165)
    RESEARCH_CODE_PATTERN = re.compile(r'^[A-Z]{2,4}[-\s]?\d{3,6}$', re.IGNORECASE)

    def __init__(
        self,
        rxnorm_client: Optional[RxNormClient] = None,
        openfda_client: Optional[OpenFDAClient] = None
    ):
        """
        Initialize resolver with API clients.

        Args:
            rxnorm_client: RxNorm client (created if not provided)
            openfda_client: OpenFDA client (created if not provided)
        """
        self.rxnorm = rxnorm_client or RxNormClient()
        self.openfda = openfda_client or OpenFDAClient()

    def resolve(self, drug_name: str) -> ResolvedDrug:
        """
        Resolve a drug name to standardized identifiers.

        Args:
            drug_name: Drug name (brand, generic, or research code)

        Returns:
            ResolvedDrug with standardized information
        """
        drug_name = drug_name.strip()
        result = ResolvedDrug(original_name=drug_name)

        # Detect name type
        result.name_type = self._detect_name_type(drug_name)
        logger.info(f"Resolving '{drug_name}' (detected type: {result.name_type})")

        # Try RxNorm first for normalization
        rxnorm_result = self.rxnorm.normalize_drug_name(drug_name)
        if rxnorm_result:
            result.rxcui = rxnorm_result["rxcui"]
            result.generic_name = rxnorm_result["normalized_name"]
            result.confidence = "high"
            logger.debug(f"RxNorm resolved: {result.generic_name} (RxCUI: {result.rxcui})")

        # Try OpenFDA for additional info and approval status
        labels = self.openfda.search_drug_labels(drug_name, limit=1)
        if labels:
            label_data = self.openfda.extract_drug_data(labels[0])
            result.is_approved = True

            # Fill in missing data from OpenFDA
            if not result.generic_name:
                result.generic_name = label_data.get("generic_name")
            if not result.brand_name:
                result.brand_name = label_data.get("brand_name")
            if not result.rxcui:
                result.rxcui = label_data.get("rxcui")

            result.confidence = "high"
            logger.debug(f"OpenFDA found approved drug: {result.brand_name}/{result.generic_name}")

        # If still no generic name, use original
        if not result.generic_name:
            result.generic_name = drug_name
            result.confidence = "low"
            logger.warning(f"Could not resolve '{drug_name}' - using original name")

        return result

    def _detect_name_type(self, name: str) -> str:
        """Detect if name is brand, generic, or research code."""
        # Research codes have specific patterns
        if self.RESEARCH_CODE_PATTERN.match(name):
            return "research_code"

        # Brand names typically start with capital letter
        # Generic names are typically all lowercase
        if name[0].isupper() and not name.isupper():
            return "brand"

        return "generic"

    def resolve_batch(self, drug_names: list) -> Dict[str, ResolvedDrug]:
        """
        Resolve multiple drug names.

        Args:
            drug_names: List of drug names

        Returns:
            Dictionary mapping original names to ResolvedDrug objects
        """
        results = {}
        for name in drug_names:
            try:
                results[name] = self.resolve(name)
            except Exception as e:
                logger.error(f"Failed to resolve '{name}': {e}")
                results[name] = ResolvedDrug(
                    original_name=name,
                    generic_name=name,
                    confidence="low"
                )
        return results

    def get_generic_name(self, drug_name: str) -> str:
        """
        Get generic name for a drug.

        Convenience method that returns just the generic name.

        Args:
            drug_name: Drug name (any type)

        Returns:
            Generic name (or original if not resolved)
        """
        resolved = self.resolve(drug_name)
        return resolved.generic_name or drug_name

