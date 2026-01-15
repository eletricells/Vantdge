"""
OpenFDA API Client

Client for accessing FDA drug data including:
- Drug labels
- Drug NDC directory
- Drug approval information
"""

import os
import logging
from typing import Dict, List, Optional, Any

from src.drug_extraction_system.api_clients.base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class OpenFDAClient(BaseAPIClient):
    """
    Client for OpenFDA API.
    
    Rate limits:
    - With API key: 240 requests/minute, 120,000 requests/day
    - Without API key: 40 requests/minute, 1,000 requests/day
    """

    BASE_URL = "https://api.fda.gov"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize OpenFDA client.

        Args:
            api_key: OpenFDA API key (optional but recommended)
        """
        self.api_key = api_key or os.getenv("OPEN_FDA_API_KEY")

        # Set rate limits based on whether we have an API key
        if self.api_key:
            rate_limit = 240
            daily_limit = 120000
            logger.info("OpenFDA client initialized with API key (240 req/min)")
        else:
            rate_limit = 40
            daily_limit = 1000
            logger.warning("OpenFDA client initialized WITHOUT API key (40 req/min)")

        super().__init__(
            base_url=self.BASE_URL,
            rate_limit=rate_limit,
            daily_limit=daily_limit,
            name="OpenFDA"
        )

    def _add_api_key(self, params: Dict) -> Dict:
        """Add API key to request parameters if available."""
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def search_drug_labels(
        self,
        drug_name: str,
        limit: int = 10
    ) -> Optional[List[Dict]]:
        """
        Search drug labels by name.

        Args:
            drug_name: Drug name (brand or generic)
            limit: Max results to return

        Returns:
            List of drug label results or None
        """
        # Build search query - search both brand and generic names
        # Use quotes for exact phrase matching to avoid incorrect results
        # OpenFDA stores names in uppercase, but search is case-insensitive
        clean_name = drug_name.strip().replace('"', '').replace("'", "")

        # Try exact match first with quotes
        search_query = f'(openfda.brand_name:"{clean_name}" OR openfda.generic_name:"{clean_name}")'

        params = self._add_api_key({
            "search": search_query,
            "limit": limit
        })

        result = self.get("/drug/label.json", params=params)

        if result and "results" in result:
            logger.info(f"Found {len(result['results'])} labels for '{drug_name}'")
            return result["results"]

        # If exact match fails, try without quotes for partial matching
        # but validate results afterwards
        search_query_loose = f'(openfda.brand_name:{clean_name} OR openfda.generic_name:{clean_name})'
        params_loose = self._add_api_key({
            "search": search_query_loose,
            "limit": limit
        })

        result = self.get("/drug/label.json", params=params_loose)

        if result and "results" in result:
            # Filter results to only include those where the drug name actually matches
            clean_lower = clean_name.lower()
            filtered = []
            for label in result["results"]:
                openfda = label.get("openfda", {})
                brand_names = [n.lower() for n in (openfda.get("brand_name") or [])]
                generic_names = [n.lower() for n in (openfda.get("generic_name") or [])]

                # Check if any brand or generic name contains our search term
                name_match = any(clean_lower in bn for bn in brand_names) or \
                             any(clean_lower in gn for gn in generic_names)

                if name_match:
                    filtered.append(label)

            if filtered:
                logger.info(f"Found {len(filtered)} labels for '{drug_name}' (filtered from {len(result['results'])})")
                return filtered

        logger.debug(f"No labels found for '{drug_name}'")
        return None

    def get_drug_label_by_setid(self, setid: str) -> Optional[Dict]:
        """
        Get drug label by DailyMed Set ID.

        Args:
            setid: DailyMed Set ID

        Returns:
            Drug label data or None
        """
        params = self._add_api_key({
            "search": f'set_id:"{setid}"',
            "limit": 1
        })

        result = self.get("/drug/label.json", params=params)

        if result and "results" in result and result["results"]:
            return result["results"][0]

        logger.debug(f"No label found for SetID '{setid}'")
        return None

    def search_ndc(self, drug_name: str, limit: int = 10) -> Optional[List[Dict]]:
        """
        Search NDC directory for drug.

        Args:
            drug_name: Drug name to search
            limit: Max results

        Returns:
            List of NDC entries or None
        """
        # Don't use quotes for case-insensitive matching
        clean_name = drug_name.strip().replace('"', '').replace("'", "")
        search_query = f'(brand_name:{clean_name}+generic_name:{clean_name})'

        params = self._add_api_key({
            "search": search_query,
            "limit": limit
        })

        result = self.get("/drug/ndc.json", params=params)

        if result and "results" in result:
            return result["results"]

        return None

    def is_drug_approved(self, drug_name: str) -> bool:
        """
        Check if drug has FDA approval (i.e., has a label).

        Args:
            drug_name: Drug name to check

        Returns:
            True if drug has FDA label, False otherwise
        """
        results = self.search_drug_labels(drug_name, limit=1)
        return results is not None and len(results) > 0

    def is_approved_for_indication(
        self,
        drug_name: str,
        indication: str,
        fuzzy_threshold: float = 0.8
    ) -> tuple[bool, str, list[str]]:
        """
        Check if a drug is FDA-approved for a specific indication.

        Searches OpenFDA drug labels and checks if the indication appears
        in the approved indications_and_usage text.

        Args:
            drug_name: Drug name (brand or generic)
            indication: Disease/indication to check (e.g., "pemphigus vulgaris")
            fuzzy_threshold: Minimum similarity score for fuzzy matching (0-1)

        Returns:
            Tuple of (is_approved, indications_text, matched_terms)
            - is_approved: True if indication found in approved uses
            - indications_text: Full indications_and_usage text from label
            - matched_terms: List of matching terms found
        """
        labels = self.search_drug_labels(drug_name, limit=3)
        if not labels:
            logger.debug(f"No FDA labels found for '{drug_name}'")
            return False, "", []

        # Check each label (may have multiple formulations)
        for label in labels:
            indications_text = ""
            indications_raw = label.get("indications_and_usage", [])
            if indications_raw:
                indications_text = indications_raw[0] if isinstance(indications_raw, list) else indications_raw

            if not indications_text:
                continue

            # Check if indication is mentioned in the approved uses
            is_match, matched_terms = self._check_indication_match(
                indication, indications_text, fuzzy_threshold
            )

            if is_match:
                logger.info(f"'{drug_name}' IS approved for '{indication}' - matched: {matched_terms}")
                return True, indications_text, matched_terms

        logger.debug(f"'{drug_name}' not approved for '{indication}'")
        return False, indications_text if labels else "", []

    def _check_indication_match(
        self,
        indication: str,
        indications_text: str,
        threshold: float = 0.8
    ) -> tuple[bool, list[str]]:
        """
        Check if an indication matches the approved indications text.

        Uses multiple matching strategies:
        1. Exact substring match (case-insensitive)
        2. Word-based matching for multi-word indications
        3. Common synonyms/variations

        Args:
            indication: The indication to search for
            indications_text: The FDA label indications_and_usage text
            threshold: Minimum match threshold

        Returns:
            Tuple of (is_match, matched_terms)
        """
        indication_lower = indication.lower().strip()
        text_lower = indications_text.lower()
        matched_terms = []

        # Strategy 1: Exact substring match
        if indication_lower in text_lower:
            matched_terms.append(f"exact: '{indication}'")
            return True, matched_terms

        # Strategy 2: Check key terms from indication
        # Split indication into significant words (skip common words)
        skip_words = {"disease", "syndrome", "disorder", "chronic", "acute", "severe",
                      "moderate", "mild", "adult", "pediatric", "patients", "with", "the", "of", "and"}
        indication_words = [w for w in indication_lower.split() if w not in skip_words and len(w) > 2]

        # Check if all significant words appear in text
        if indication_words:
            words_found = [w for w in indication_words if w in text_lower]
            if len(words_found) == len(indication_words):
                matched_terms.append(f"all_words: {words_found}")
                return True, matched_terms
            # Allow partial match if most words found (for long indication names)
            if len(indication_words) >= 3 and len(words_found) >= len(indication_words) * threshold:
                matched_terms.append(f"partial_words: {words_found}")
                return True, matched_terms

        # Strategy 3: Common medical synonyms and variations
        synonyms = self._get_indication_synonyms(indication_lower)
        for synonym in synonyms:
            if synonym in text_lower:
                matched_terms.append(f"synonym: '{synonym}'")
                return True, matched_terms

        return False, matched_terms

    def _get_indication_synonyms(self, indication: str) -> list[str]:
        """
        Get common synonyms and variations for an indication.

        This handles common cases where FDA labels may use different terminology.
        """
        synonyms = []

        # Map common variations
        # NOTE: Be careful with synonyms - they should be specific enough
        # to avoid false positives. For example, "lupus" alone would match
        # both "systemic lupus erythematosus" AND "lupus nephritis" which
        # are distinct FDA indications.
        synonym_map = {
            # Autoimmune conditions
            "pemphigus vulgaris": ["pemphigus", "pv"],
            # Don't use "lupus" alone - it would match lupus nephritis
            "systemic lupus erythematosus": ["sle", "systemic lupus"],
            "lupus nephritis": ["ln", "lupus nephritis"],
            "rheumatoid arthritis": ["ra"],  # "rheumatoid" alone could be ambiguous
            "psoriatic arthritis": ["psa"],
            "ankylosing spondylitis": ["as", "ankylosing"],
            "ulcerative colitis": ["uc"],
            "crohn's disease": ["crohn", "crohns", "crohn disease"],
            "multiple sclerosis": ["ms", "relapsing multiple sclerosis", "relapsing-remitting multiple sclerosis"],
            "myasthenia gravis": ["mg", "myasthenia"],
            "neuromyelitis optica": ["nmo", "nmosd", "devic", "neuromyelitis optica spectrum disorder"],
            "atopic dermatitis": ["atopic eczema"],  # "eczema" alone is too broad
            "plaque psoriasis": ["chronic plaque psoriasis"],  # "psoriasis" alone is too broad
            "giant cell arteritis": ["gca", "temporal arteritis"],
            "polymyalgia rheumatica": ["pmr"],
            "graves disease": ["graves", "graves' disease"],  # "hyperthyroidism" is too broad
            "hashimoto": ["hashimoto's thyroiditis", "hashimoto thyroiditis", "autoimmune thyroiditis"],
            # Oncology
            "non-hodgkin lymphoma": ["nhl", "non-hodgkin's lymphoma"],  # "b-cell lymphoma" is a subtype
            "chronic lymphocytic leukemia": ["cll"],
            "diffuse large b-cell lymphoma": ["dlbcl"],
            "follicular lymphoma": ["fl"],
        }

        # Check if indication has known synonyms
        for key, values in synonym_map.items():
            if key in indication or indication in key:
                synonyms.extend(values)
            # Also check if any synonym matches the input
            for v in values:
                if v in indication:
                    synonyms.append(key)
                    synonyms.extend([x for x in values if x != v])

        return list(set(synonyms))

    def extract_drug_data(self, label: Dict) -> Dict[str, Any]:
        """
        Extract structured drug data from OpenFDA label.

        Args:
            label: Raw OpenFDA label data

        Returns:
            Structured drug data dictionary
        """
        openfda = label.get("openfda", {})

        return {
            "brand_name": self._get_first(openfda.get("brand_name")),
            "generic_name": self._get_first(openfda.get("generic_name")),
            "manufacturer": self._get_first(openfda.get("manufacturer_name")),
            "rxcui": self._get_first(openfda.get("rxcui")),
            "unii": self._get_first(openfda.get("unii")),
            "nui": self._get_first(openfda.get("nui")),
            "route": self._get_first(openfda.get("route")),
            "product_type": self._get_first(openfda.get("product_type")),
            "substance_name": self._get_first(openfda.get("substance_name")),
            "indications_and_usage": self._get_first(label.get("indications_and_usage")),
            "dosage_and_administration": self._get_first(label.get("dosage_and_administration")),
            "warnings": self._get_first(label.get("warnings")),
            "boxed_warning": self._get_first(label.get("boxed_warning")),
            "contraindications": self._get_first(label.get("contraindications")),
            "mechanism_of_action": self._get_first(label.get("mechanism_of_action")),
            "clinical_pharmacology": self._get_first(label.get("clinical_pharmacology")),
            "set_id": label.get("set_id"),
            "effective_time": label.get("effective_time"),
        }

    def _get_first(self, value: Any) -> Optional[str]:
        """Get first element from list or return value as-is."""
        if isinstance(value, list) and value:
            return value[0]
        return value if value else None

    def get_approval_info(self, drug_name: str) -> Dict:
        """
        Fetch approval information from the drugsfda endpoint.

        Returns:
            {
                'first_approval_date': '2019-08-16',
                'application_number': 'NDA211675',
                'sponsor_name': 'AbbVie Inc.',
            }
        """
        # Try brand name first, then generic
        search_queries = [
            f'products.brand_name:"{drug_name}"',
            f'openfda.generic_name:"{drug_name}"',
            f'openfda.substance_name:"{drug_name}"'
        ]

        for search_query in search_queries:
            params = self._add_api_key({
                "search": search_query,
                "limit": 1
            })

            try:
                result = self.get("/drug/drugsfda.json", params=params)

                if result and result.get("results"):
                    fda_result = result["results"][0]

                    # Find original approval (submission_type = 'ORIG')
                    submissions = fda_result.get("submissions", [])
                    approval_date = None

                    for sub in submissions:
                        if sub.get("submission_type") == "ORIG":
                            approval_date = sub.get("submission_status_date")
                            break

                    # If no ORIG found, use earliest submission
                    if not approval_date and submissions:
                        sorted_subs = sorted(
                            submissions,
                            key=lambda x: x.get("submission_status_date", "9999")
                        )
                        approval_date = sorted_subs[0].get("submission_status_date")

                    return {
                        "first_approval_date": approval_date,
                        "application_number": fda_result.get("application_number"),
                        "sponsor_name": fda_result.get("sponsor_name"),
                    }

            except Exception as e:
                logger.debug(f"drugsfda search failed for '{search_query}': {e}")
                continue

        return {}

    def infer_drug_type(self, openfda_data: Dict, drug_name: str) -> str:
        """
        Infer drug type (small molecule, biologic, etc.) from available data.

        Returns one of:
        - 'small_molecule'
        - 'biologic'
        - 'vaccine'
        - 'unknown'
        """
        # Check pharmacologic class for biologic indicators
        pharm_class_moa = openfda_data.get("pharm_class_moa", []) or []
        pharm_class_epc = openfda_data.get("pharm_class_epc", []) or []
        all_classes = " ".join(pharm_class_moa + pharm_class_epc).lower()

        # Biologic indicators
        biologic_patterns = [
            "monoclonal antibody", "mab]", "fusion protein",
            "recombinant", "pegylated", "interleukin",
            "interferon", "colony-stimulating factor",
            "erythropoietin", "growth factor", "immunoglobulin"
        ]

        for pattern in biologic_patterns:
            if pattern in all_classes:
                return "biologic"

        # Check drug name patterns (common suffixes)
        name_lower = drug_name.lower()

        # Monoclonal antibody suffixes
        mab_suffixes = ["mab", "umab", "zumab", "ximab", "mumab"]
        for suffix in mab_suffixes:
            if name_lower.endswith(suffix):
                return "biologic"

        # Fusion protein suffix
        if name_lower.endswith("cept"):
            return "biologic"

        # Kinase inhibitor suffix (small molecule)
        if name_lower.endswith("nib") or name_lower.endswith("tinib"):
            return "small_molecule"

        # Check application number for BLA (Biologic License Application)
        application_number = openfda_data.get("application_number", [""])[0] if openfda_data.get("application_number") else ""
        if application_number.upper().startswith("BLA"):
            return "biologic"

        # Check product type if available
        product_type = (openfda_data.get("product_type", [""])[0] or "").lower()
        if "vaccine" in product_type:
            return "vaccine"

        # Default to small molecule (most common)
        return "small_molecule"

    def health_check(self) -> bool:
        """Check if OpenFDA API is accessible."""
        try:
            params = self._add_api_key({"limit": 1})
            result = self.get("/drug/label.json", params=params)
            return result is not None
        except Exception:
            return False

