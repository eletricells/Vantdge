"""
Drug Name Resolver

Resolves drug names (brand, generic, research codes) to standardized identifiers.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from src.drug_extraction_system.api_clients.rxnorm_client import RxNormClient
from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient

logger = logging.getLogger(__name__)

# Try to import PubChem client
try:
    from src.drug_extraction_system.api_clients.pubchem_client import PubChemClient
    PUBCHEM_AVAILABLE = True
except ImportError:
    PUBCHEM_AVAILABLE = False
    logger.debug("PubChem client not available")


@dataclass
class ResolvedDrug:
    """Resolved drug information."""
    original_name: str
    generic_name: Optional[str] = None
    brand_name: Optional[str] = None
    rxcui: Optional[str] = None
    pubchem_cid: Optional[int] = None
    development_code: Optional[str] = None
    synonyms: List[str] = field(default_factory=list)
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

    Uses multiple data sources:
    - PubChem (compounds + substances) - best for investigational drugs
    - RxNorm - best for approved drugs
    - OpenFDA - approval status verification
    """

    # Pattern for research codes (e.g., ABT-494, BMS-986165, PF-06823859)
    RESEARCH_CODE_PATTERN = re.compile(r'^[A-Z]{2,5}[-\s]?\d{3,8}[A-Z]?$', re.IGNORECASE)

    def __init__(
        self,
        rxnorm_client: Optional[RxNormClient] = None,
        openfda_client: Optional[OpenFDAClient] = None,
        pubchem_client: Optional['PubChemClient'] = None,
        use_pubchem: bool = True
    ):
        """
        Initialize resolver with API clients.

        Args:
            rxnorm_client: RxNorm client (created if not provided)
            openfda_client: OpenFDA client (created if not provided)
            pubchem_client: PubChem client (created if not provided and use_pubchem=True)
            use_pubchem: Whether to use PubChem for resolution (recommended for pipeline drugs)
        """
        self.rxnorm = rxnorm_client or RxNormClient()
        self.openfda = openfda_client or OpenFDAClient()

        # Initialize PubChem client for research code resolution
        self.pubchem = None
        if use_pubchem and PUBCHEM_AVAILABLE:
            self.pubchem = pubchem_client or PubChemClient()
            logger.debug("PubChem client initialized for drug name resolution")

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

        # For research codes, try PubChem first (best source for investigational drugs)
        if self.pubchem and result.name_type == "research_code":
            pubchem_result = self._resolve_via_pubchem(drug_name)
            if pubchem_result:
                result.generic_name = pubchem_result.get('generic_name')
                result.pubchem_cid = pubchem_result.get('cid')
                result.development_code = drug_name  # Original was research code
                result.synonyms = pubchem_result.get('synonyms', [])
                result.confidence = "high"
                logger.info(f"PubChem resolved '{drug_name}' -> '{result.generic_name}'")

        # Try RxNorm for normalization (best for approved drugs)
        if not result.generic_name or result.confidence != "high":
            rxnorm_result = self.rxnorm.normalize_drug_name(drug_name)
            if rxnorm_result:
                result.rxcui = rxnorm_result["rxcui"]
                if not result.generic_name:
                    result.generic_name = rxnorm_result["normalized_name"]
                result.confidence = "high"
                logger.debug(f"RxNorm resolved: {result.generic_name} (RxCUI: {result.rxcui})")

        # Try OpenFDA for approval status and additional info
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

        # For non-research-code names, also try PubChem for synonyms
        if self.pubchem and result.name_type != "research_code" and not result.pubchem_cid:
            pubchem_result = self._resolve_via_pubchem(drug_name)
            if pubchem_result:
                result.pubchem_cid = pubchem_result.get('cid')
                result.synonyms = pubchem_result.get('synonyms', [])
                # Extract development code from synonyms
                if not result.development_code:
                    for syn in result.synonyms:
                        if self.RESEARCH_CODE_PATTERN.match(syn):
                            result.development_code = syn.upper()
                            break

        # If still no generic name, use original
        if not result.generic_name:
            result.generic_name = drug_name
            result.confidence = "low"
            logger.warning(f"Could not resolve '{drug_name}' - using original name")

        return result

    def _resolve_via_pubchem(self, name: str) -> Optional[Dict]:
        """
        Resolve drug name via PubChem.

        Args:
            name: Drug name to look up

        Returns:
            Dict with cid, generic_name, synonyms, research_codes
        """
        if not self.pubchem:
            return None

        try:
            info = self.pubchem.get_drug_info(name)
            if info:
                return {
                    'cid': info['cid'],
                    'generic_name': info['generic_name'],
                    'synonyms': info['all_synonyms'],
                    'research_codes': info['research_codes'],
                }
        except Exception as e:
            logger.debug(f"PubChem lookup failed for '{name}': {e}")

        return None

    def _detect_name_type(self, name: str) -> str:
        """Detect if name is brand, generic, or research code."""
        # Research codes have specific patterns (e.g., ABT-494, PF-06823859, BMS-986165)
        if self.RESEARCH_CODE_PATTERN.match(name):
            return "research_code"

        # Also check for codes with numbers anywhere
        if re.search(r'^[A-Z]{2,5}\d', name, re.IGNORECASE):
            return "research_code"

        # Brand names typically start with capital letter
        # Generic names are typically all lowercase
        if name and name[0].isupper() and not name.isupper():
            return "brand"

        return "generic"

    def find_existing_drug_by_pubchem(self, pubchem_cid: int, db_connection) -> Optional[Dict]:
        """
        Check if a drug with this PubChem CID already exists in the database.

        This prevents creating duplicate entries for the same compound.

        Args:
            pubchem_cid: PubChem CID to search for
            db_connection: Database connection

        Returns:
            Existing drug record if found, None otherwise
        """
        if not pubchem_cid:  # Allow negative values (SIDs from substance DB)
            return None

        try:
            from psycopg2.extras import RealDictCursor
            with db_connection.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT drug_id, generic_name, brand_name, development_code
                    FROM drugs
                    WHERE pubchem_cid = %s
                    LIMIT 1
                """, (pubchem_cid,))
                result = cur.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.debug(f"Error checking for existing drug by PubChem CID: {e}")
            return None

    def check_for_duplicate(self, resolved: ResolvedDrug, db_connection) -> Optional[Dict]:
        """
        Check if a resolved drug already exists in the database.

        Checks by:
        1. PubChem CID (if available)
        2. Generic name match
        3. Development code match

        Args:
            resolved: Resolved drug information
            db_connection: Database connection

        Returns:
            Existing drug record if found, None otherwise
        """
        try:
            from psycopg2.extras import RealDictCursor
            with db_connection.cursor(cursor_factory=RealDictCursor) as cur:
                # Check by PubChem CID first (most reliable)
                if resolved.pubchem_cid and resolved.pubchem_cid > 0:
                    cur.execute("""
                        SELECT drug_id, generic_name, brand_name, development_code
                        FROM drugs
                        WHERE pubchem_cid = %s
                        LIMIT 1
                    """, (resolved.pubchem_cid,))
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Found existing drug by PubChem CID: {result['generic_name']}")
                        return dict(result)

                # Check by generic name
                if resolved.generic_name:
                    cur.execute("""
                        SELECT drug_id, generic_name, brand_name, development_code
                        FROM drugs
                        WHERE LOWER(generic_name) = LOWER(%s)
                        LIMIT 1
                    """, (resolved.generic_name,))
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Found existing drug by generic name: {result['generic_name']}")
                        return dict(result)

                # Check by development code
                if resolved.development_code:
                    cur.execute("""
                        SELECT drug_id, generic_name, brand_name, development_code
                        FROM drugs
                        WHERE LOWER(development_code) = LOWER(%s)
                           OR LOWER(generic_name) = LOWER(%s)
                        LIMIT 1
                    """, (resolved.development_code, resolved.development_code))
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Found existing drug by development code: {result['generic_name']}")
                        return dict(result)

                # Check synonyms against generic_name and development_code
                for synonym in resolved.synonyms[:20]:  # Limit to first 20
                    cur.execute("""
                        SELECT drug_id, generic_name, brand_name, development_code
                        FROM drugs
                        WHERE LOWER(generic_name) = LOWER(%s)
                           OR LOWER(development_code) = LOWER(%s)
                        LIMIT 1
                    """, (synonym, synonym))
                    result = cur.fetchone()
                    if result:
                        logger.info(f"Found existing drug by synonym '{synonym}': {result['generic_name']}")
                        return dict(result)

                return None

        except Exception as e:
            logger.warning(f"Error checking for duplicate drug: {e}")
            return None

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

