"""
ClinicalTrials.gov API Client (v2)

Client for accessing clinical trial data for pipeline drugs.
Uses the new v2 API (https://clinicaltrials.gov/api/v2/).
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.drug_extraction_system.api_clients.base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class ClinicalTrialsClient(BaseAPIClient):
    """
    Client for ClinicalTrials.gov v2 API.
    
    Free API with no authentication required.
    Rate limit: ~50 requests/minute (conservative estimate)
    """

    BASE_URL = "https://clinicaltrials.gov/api/v2"

    def __init__(self):
        """Initialize ClinicalTrials.gov client."""
        super().__init__(
            base_url=self.BASE_URL,
            rate_limit=50,
            name="ClinicalTrials"
        )

    def search_trials(
        self,
        drug_name: str,
        status: Optional[List[str]] = None,
        phase: Optional[List[str]] = None,
        limit: int = 50,
        sponsor_class: Optional[str] = None
    ) -> Optional[List[Dict]]:
        """
        Search clinical trials by drug name.

        Args:
            drug_name: Drug/intervention name to search
            status: Filter by status (e.g., ["RECRUITING", "COMPLETED"])
            phase: Filter by phase (e.g., ["PHASE1", "PHASE2"])
            limit: Max results to return
            sponsor_class: Filter by sponsor class (e.g., "INDUSTRY", "NIH", "OTHER")

        Returns:
            List of trial data or None
        """
        params = {
            "query.intr": drug_name,  # Search in interventions
            "pageSize": min(limit, 100),
            "format": "json"
        }

        # Add status filter
        if status:
            params["filter.overallStatus"] = ",".join(status)

        # Add phase filter
        if phase:
            params["filter.phase"] = ",".join(phase)

        # Add sponsor class filter (INDUSTRY, NIH, OTHER, etc.)
        if sponsor_class:
            params["filter.advanced"] = f"AREA[LeadSponsorClass]{sponsor_class}"

        result = self.get("/studies", params=params)

        if result and "studies" in result:
            studies = result["studies"]
            logger.info(f"Found {len(studies)} trials for '{drug_name}'")
            return studies

        logger.debug(f"No trials found for '{drug_name}'")
        return None

    def search_trials_all(
        self,
        search_terms: List[str],
        sponsor_class: Optional[str] = None,
        max_results: int = 1000
    ) -> List[Dict]:
        """
        Search clinical trials using multiple search terms with pagination.

        Fetches ALL matching trials (up to max_results) across multiple search terms,
        deduplicating by NCT ID.

        Args:
            search_terms: List of drug names/codes to search (e.g., ["iptacopan", "LNP023"])
            sponsor_class: Filter by sponsor class (e.g., "INDUSTRY")
            max_results: Maximum total results to return

        Returns:
            List of unique trial data (deduplicated by NCT ID)
        """
        all_trials = {}  # Use dict with NCT ID as key for deduplication

        for term in search_terms:
            if not term:
                continue

            page_token = None
            term_count = 0

            while True:
                params = {
                    "query.intr": term,
                    "pageSize": 100,  # Max allowed per page
                    "format": "json"
                }

                if sponsor_class:
                    params["filter.advanced"] = f"AREA[LeadSponsorClass]{sponsor_class}"

                if page_token:
                    params["pageToken"] = page_token

                result = self.get("/studies", params=params)

                if not result or "studies" not in result:
                    break

                studies = result["studies"]
                for study in studies:
                    nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
                    if nct_id and nct_id not in all_trials:
                        all_trials[nct_id] = study
                        term_count += 1

                # Check if there are more pages
                page_token = result.get("nextPageToken")
                if not page_token or len(all_trials) >= max_results:
                    break

            logger.info(f"Found {term_count} trials for search term '{term}'")

        trials_list = list(all_trials.values())
        logger.info(f"Total unique trials found: {len(trials_list)}")
        return trials_list

    def get_trial_by_nct(self, nct_id: str) -> Optional[Dict]:
        """
        Get trial details by NCT ID.

        Args:
            nct_id: NCT identifier (e.g., "NCT04869137")

        Returns:
            Trial data or None
        """
        result = self.get(f"/studies/{nct_id}", params={"format": "json"})

        if result:
            return result

        logger.debug(f"No trial found for NCT ID '{nct_id}'")
        return None

    def extract_trial_data(self, study: Dict) -> Dict[str, Any]:
        """
        Extract structured trial data from API response.

        Args:
            study: Raw study data from API

        Returns:
            Structured trial data dictionary
        """
        protocol = study.get("protocolSection", {})
        id_module = protocol.get("identificationModule", {})
        status_module = protocol.get("statusModule", {})
        design_module = protocol.get("designModule", {})
        arms_module = protocol.get("armsInterventionsModule", {})
        outcomes_module = protocol.get("outcomesModule", {})
        contacts_module = protocol.get("contactsLocationsModule", {})
        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
        conditions_module = protocol.get("conditionsModule", {})
        eligibility_module = protocol.get("eligibilityModule", {})

        # Extract phases
        phases = design_module.get("phases", [])
        phase_str = ", ".join(phases) if phases else None

        # Extract interventions
        interventions = []
        for arm in arms_module.get("interventions", []):
            interventions.append({
                "type": arm.get("type"),
                "name": arm.get("name"),
                "description": arm.get("description"),
            })

        # Extract sponsors (including class for filtering by INDUSTRY, NIH, etc.)
        lead_sponsor = sponsor_module.get("leadSponsor", {})
        sponsors = {
            "lead": lead_sponsor.get("name"),
            "class": lead_sponsor.get("class"),  # INDUSTRY, NIH, FED, OTHER, etc.
            "collaborators": [
                c.get("name") for c in sponsor_module.get("collaborators", [])
            ]
        }

        # Extract locations
        locations = []
        for loc in contacts_module.get("locations", []):
            locations.append({
                "facility": loc.get("facility"),
                "city": loc.get("city"),
                "state": loc.get("state"),
                "country": loc.get("country"),
            })

        # Extract primary outcome
        primary_outcomes = outcomes_module.get("primaryOutcomes", [])
        primary_outcome = primary_outcomes[0].get("measure") if primary_outcomes else None

        # Extract secondary outcomes
        secondary_outcomes = [
            o.get("measure") for o in outcomes_module.get("secondaryOutcomes", [])
        ]

        return {
            "nct_id": id_module.get("nctId"),
            "trial_title": id_module.get("officialTitle") or id_module.get("briefTitle"),
            "trial_phase": phase_str,
            "trial_status": status_module.get("overallStatus"),
            "start_date": self._parse_date(status_module.get("startDateStruct")),
            "completion_date": self._parse_date(status_module.get("completionDateStruct")),
            "enrollment": design_module.get("enrollmentInfo", {}).get("count"),
            "conditions": conditions_module.get("conditions", []),
            "interventions": interventions,
            "sponsors": sponsors,
            "locations": locations[:10],  # Limit to first 10 locations
            "primary_outcome": primary_outcome,
            "secondary_outcomes": secondary_outcomes[:5],  # Limit to first 5
            "eligibility_criteria": eligibility_module.get("eligibilityCriteria"),
        }

    def _parse_date(self, date_struct: Optional[Dict]) -> Optional[str]:
        """Parse date from API date structure.

        Handles both full dates (YYYY-MM-DD) and partial dates (YYYY-MM)
        by adding -01 to partial dates for database compatibility.
        """
        if not date_struct:
            return None
        date_str = date_struct.get("date")
        if not date_str:
            return None
        # Handle YYYY-MM format by adding -01 for day
        if len(date_str) == 7 and date_str[4] == '-':
            return date_str + '-01'
        return date_str

    def get_highest_phase(self, drug_name: str) -> Optional[str]:
        """
        Get highest clinical trial phase for a drug.

        Args:
            drug_name: Drug name to search

        Returns:
            Highest phase string (e.g., "Phase 3") or None
        """
        trials = self.search_trials(drug_name, limit=100)
        if not trials:
            return None

        phase_order = ["PHASE4", "PHASE3", "PHASE2", "PHASE1", "EARLY_PHASE1", "NA"]
        highest = None

        for study in trials:
            protocol = study.get("protocolSection", {})
            phases = protocol.get("designModule", {}).get("phases", [])
            for phase in phases:
                if highest is None or phase_order.index(phase) < phase_order.index(highest):
                    highest = phase

        return highest.replace("_", " ").title() if highest else None

    def health_check(self) -> bool:
        """Check if ClinicalTrials.gov API is accessible."""
        try:
            result = self.get("/studies", params={"pageSize": 1, "format": "json"})
            return result is not None and "studies" in result
        except Exception:
            return False

