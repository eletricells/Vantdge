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

