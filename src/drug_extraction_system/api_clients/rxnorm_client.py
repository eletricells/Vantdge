"""
RxNorm API Client

Client for accessing RxNorm drug terminology data including:
- Drug name normalization
- RxCUI lookup
- Drug relationships
"""

import logging
from typing import Dict, List, Optional, Any

from src.drug_extraction_system.api_clients.base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class RxNormClient(BaseAPIClient):
    """
    Client for RxNorm REST API.
    
    Free API with no authentication required.
    Rate limit: ~20 requests/second (conservative estimate)
    """

    BASE_URL = "https://rxnav.nlm.nih.gov/REST"

    def __init__(self):
        """Initialize RxNorm client."""
        super().__init__(
            base_url=self.BASE_URL,
            rate_limit=1200,  # 20/sec = 1200/min
            name="RxNorm"
        )

    def get_rxcui_by_name(self, drug_name: str) -> Optional[str]:
        """
        Get RxCUI for a drug name.

        Args:
            drug_name: Drug name (brand or generic)

        Returns:
            RxCUI string or None
        """
        result = self.get("/rxcui.json", params={"name": drug_name})

        if result and "idGroup" in result:
            rxnorm_ids = result["idGroup"].get("rxnormId", [])
            if rxnorm_ids:
                rxcui = rxnorm_ids[0]
                logger.debug(f"Found RxCUI {rxcui} for '{drug_name}'")
                return rxcui

        logger.debug(f"No RxCUI found for '{drug_name}'")
        return None

    def get_rxcui_approximate(self, drug_name: str) -> Optional[str]:
        """
        Get RxCUI using approximate matching.

        Useful for misspellings or partial names.

        Args:
            drug_name: Drug name to search

        Returns:
            RxCUI string or None
        """
        result = self.get("/approximateTerm.json", params={"term": drug_name})

        if result and "approximateGroup" in result:
            candidates = result["approximateGroup"].get("candidate", [])
            if candidates:
                # Return highest ranked match
                rxcui = candidates[0].get("rxcui")
                logger.debug(f"Found approximate RxCUI {rxcui} for '{drug_name}'")
                return rxcui

        return None

    def get_drug_properties(self, rxcui: str) -> Optional[Dict[str, Any]]:
        """
        Get drug properties by RxCUI.

        Args:
            rxcui: RxNorm Concept Unique Identifier

        Returns:
            Dictionary of drug properties or None
        """
        result = self.get(f"/rxcui/{rxcui}/properties.json")

        if result and "properties" in result:
            props = result["properties"]
            return {
                "rxcui": props.get("rxcui"),
                "name": props.get("name"),
                "synonym": props.get("synonym"),
                "tty": props.get("tty"),  # Term type
                "language": props.get("language"),
                "suppress": props.get("suppress"),
                "umlscui": props.get("umlscui"),
            }

        return None

    def get_related_drugs(self, rxcui: str, relation_type: str = "SY") -> List[Dict]:
        """
        Get related drugs by RxCUI.

        Args:
            rxcui: RxNorm Concept Unique Identifier
            relation_type: Relationship type (SY=synonym, IN=ingredient, etc.)

        Returns:
            List of related drug concepts
        """
        result = self.get(f"/rxcui/{rxcui}/related.json", params={"tty": relation_type})

        if result and "relatedGroup" in result:
            concept_groups = result["relatedGroup"].get("conceptGroup", [])
            related = []
            for group in concept_groups:
                for concept in group.get("conceptProperties", []):
                    related.append({
                        "rxcui": concept.get("rxcui"),
                        "name": concept.get("name"),
                        "tty": concept.get("tty"),
                    })
            return related

        return []

    def get_all_related(self, rxcui: str) -> Dict[str, List[Dict]]:
        """
        Get all related concepts for a drug.

        Args:
            rxcui: RxNorm Concept Unique Identifier

        Returns:
            Dictionary mapping relation types to related concepts
        """
        result = self.get(f"/rxcui/{rxcui}/allrelated.json")

        if result and "allRelatedGroup" in result:
            concept_groups = result["allRelatedGroup"].get("conceptGroup", [])
            related = {}
            for group in concept_groups:
                tty = group.get("tty", "unknown")
                concepts = []
                for concept in group.get("conceptProperties", []):
                    concepts.append({
                        "rxcui": concept.get("rxcui"),
                        "name": concept.get("name"),
                    })
                if concepts:
                    related[tty] = concepts
            return related

        return {}

    def normalize_drug_name(self, drug_name: str) -> Optional[Dict[str, str]]:
        """
        Normalize drug name using RxNorm.

        Args:
            drug_name: Drug name to normalize

        Returns:
            Dictionary with rxcui and normalized name, or None
        """
        # Try exact match first
        rxcui = self.get_rxcui_by_name(drug_name)

        # Fall back to approximate match
        if not rxcui:
            rxcui = self.get_rxcui_approximate(drug_name)

        if rxcui:
            props = self.get_drug_properties(rxcui)
            if props:
                return {
                    "rxcui": rxcui,
                    "normalized_name": props.get("name"),
                    "original_name": drug_name,
                }

        return None

    def health_check(self) -> bool:
        """Check if RxNorm API is accessible."""
        try:
            result = self.get("/version.json")
            return result is not None and "version" in result
        except Exception:
            return False

