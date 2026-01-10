"""
ClinicalTrials.gov API wrapper for querying clinical trial data.

NOTE: This uses the 'requests' library instead of 'httpx' because ClinicalTrials.gov
blocks httpx requests (likely due to HTTP/2 or TLS fingerprinting).
"""
import requests
from typing import List, Dict, Optional, Any
import logging
from datetime import datetime


logger = logging.getLogger(__name__)


class ClinicalTrialsAPI:
    """
    Wrapper for ClinicalTrials.gov API v2.

    Documentation: https://clinicaltrials.gov/data-api/api
    """

    BASE_URL = "https://clinicaltrials.gov/api/v2"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 30):
        """
        Initialize ClinicalTrials.gov API client.

        Args:
            api_key: Optional API key (for higher rate limits)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        # Use requests library instead of httpx (ClinicalTrials.gov blocks httpx)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9'
        })
        # Global rate limiter: 50 req/min = 1.2s minimum, we use 2s to be safe
        self._last_request_time = None
        self._min_request_interval = 2.0  # seconds between requests

    def _ensure_rate_limit(self):
        """Enforce global rate limit by waiting if needed."""
        import time
        if self._last_request_time is not None:
            time_since_last = time.time() - self._last_request_time
            if time_since_last < self._min_request_interval:
                wait_time = self._min_request_interval - time_since_last
                logger.debug(f"Rate limit: waiting {wait_time:.2f}s")
                time.sleep(wait_time)
        self._last_request_time = time.time()

    def search_studies(
        self,
        query: str,
        max_results: int = 10,
        filter_advanced: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for clinical trials.

        Args:
            query: Search query (drug name, condition, etc.)
            max_results: Maximum number of results to return
            filter_advanced: Advanced filter expression

        Returns:
            List of study records
        """
        try:
            params = {
                "query.term": query,
                "pageSize": max_results,
                "format": "json"
            }

            if filter_advanced:
                params["filter.advanced"] = filter_advanced

            if self.api_key:
                params["api_key"] = self.api_key

            # Enforce global rate limit
            self._ensure_rate_limit()

            response = self.session.get(
                f"{self.BASE_URL}/studies",
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            studies = data.get("studies", [])

            logger.info(f"Found {len(studies)} studies for query: {query}")
            return studies

        except requests.exceptions.RequestException as e:
            logger.error(f"ClinicalTrials.gov API error: {str(e)}")
            return []

    def get_study_details(self, nct_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information for a specific study.

        Args:
            nct_id: NCT identifier (e.g., "NCT12345678")

        Returns:
            Study details or None if not found
        """
        try:
            params = {"format": "json"}
            if self.api_key:
                params["api_key"] = self.api_key

            # Enforce global rate limit
            self._ensure_rate_limit()

            response = self.session.get(
                f"{self.BASE_URL}/studies/{nct_id}",
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            logger.info(f"Retrieved details for {nct_id}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching study {nct_id}: {str(e)}")
            return None

    def extract_study_summary(self, study: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract key information from a study record.

        Args:
            study: Raw study data from API

        Returns:
            Simplified study summary
        """
        protocol_section = study.get("protocolSection", {})
        identification = protocol_section.get("identificationModule", {})
        status = protocol_section.get("statusModule", {})
        design = protocol_section.get("designModule", {})
        eligibility = protocol_section.get("eligibilityModule", {})
        conditions = protocol_section.get("conditionsModule", {})
        interventions = protocol_section.get("armsInterventionsModule", {})

        # Extract phase and study_type
        phase = design.get("phases", ["Unknown"])[0] if design.get("phases") else "Unknown"
        study_type = design.get("studyType", "")

        # Debug logging
        nct_id = identification.get("nctId", "")
        logger.debug(f"Trial {nct_id}: phase={phase}, study_type={study_type}")

        # If phase is Unknown, fall back to study_type
        if phase == "Unknown" and study_type:
            logger.info(f"Trial {nct_id}: Using study_type '{study_type}' as phase (no phase found)")
            phase = study_type

        return {
            "nct_id": identification.get("nctId", ""),
            "title": identification.get("briefTitle", ""),
            "official_title": identification.get("officialTitle", ""),
            "status": status.get("overallStatus", ""),
            "phase": phase,
            "study_type": study_type,
            "enrollment": status.get("enrollmentInfo", {}).get("count"),
            "conditions": conditions.get("conditions", []),
            "interventions": [
                {
                    "type": i.get("type"),
                    "name": i.get("name")
                }
                for i in interventions.get("interventions", [])
            ],
            "primary_outcomes": self._extract_outcomes(
                protocol_section.get("outcomesModule", {}).get("primaryOutcomes", [])
            ),
            "eligibility_criteria": eligibility.get("eligibilityCriteria", ""),
            "start_date": status.get("startDateStruct", {}).get("date"),
            "completion_date": status.get("completionDateStruct", {}).get("date"),
        }

    def _extract_outcomes(self, outcomes: List[Dict]) -> List[Dict[str, str]]:
        """Extract outcome measures"""
        return [
            {
                "measure": outcome.get("measure", ""),
                "description": outcome.get("description", ""),
                "timeframe": outcome.get("timeFrame", "")
            }
            for outcome in outcomes
        ]

    def format_for_llm(self, studies: List[Dict[str, Any]]) -> str:
        """
        Format study data for LLM consumption.

        Args:
            studies: List of study records

        Returns:
            Formatted text description
        """
        if not studies:
            return "No clinical trials found."

        output = []
        for study in studies:
            summary = self.extract_study_summary(study)

            output.append(f"""
NCT ID: {summary['nct_id']}
Title: {summary['title']}
Status: {summary['status']}
Phase: {summary['phase']}
Enrollment: {summary['enrollment']} participants
Conditions: {', '.join(summary['conditions'])}
Interventions: {', '.join([i['name'] for i in summary['interventions']])}
Start Date: {summary['start_date']}
Primary Outcomes: {len(summary['primary_outcomes'])} defined
---""")

        return "\n".join(output)

    def search_trials(
        self,
        drug_name: str,
        condition: Optional[str] = None,
        max_results: int = 50,
        max_retries: int = 3,
        use_fuzzy_search: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search trials by drug/intervention name with fuzzy matching.

        Uses general term search by default (searches all fields) which is more forgiving
        than structured field search. Falls back to structured search if needed.

        Args:
            drug_name: Name of drug or intervention
            condition: Optional condition filter
            max_results: Maximum number of results
            max_retries: Maximum number of retry attempts for rate limits
            use_fuzzy_search: If True, use general term search (recommended). If False, use structured field search.

        Returns:
            List of trial summaries with parsed data
        """
        import time

        if use_fuzzy_search:
            # Use general term search (fuzzy) - searches all fields
            query = f"{drug_name} {condition}" if condition else drug_name
            params = {
                "query.term": query,
                "pageSize": max_results,
                "format": "json"
            }
        else:
            # Use structured field search (restrictive) - exact field matching
            params = {
                "query.intr": drug_name,
                "pageSize": max_results,
                "format": "json"
            }
            if condition:
                params["query.cond"] = condition

        if self.api_key:
            params["api_key"] = self.api_key

        for attempt in range(max_retries):
            try:
                # Enforce global rate limit
                self._ensure_rate_limit()

                response = self.session.get(
                    f"{self.BASE_URL}/studies",
                    params=params,
                    timeout=self.timeout
                )
                response.raise_for_status()

                data = response.json()
                studies = data.get("studies", [])

                search_type = "fuzzy term search" if use_fuzzy_search else "structured field search"
                logger.info(f"Found {len(studies)} trials for {drug_name} using {search_type}")

                # Parse studies into simplified format
                return self._parse_studies_for_landscape(studies)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    # 403 typically means access forbidden (not rate limit) - skip drug instead of retrying
                    logger.warning(f"Access forbidden (403) for {drug_name} - skipping")
                    return []
                elif e.response.status_code == 429:
                    # 429 is actual rate limiting - wait and retry
                    wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                    logger.warning(f"Rate limited (429), waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"ClinicalTrials.gov search failed with status {e.response.status_code}: {e}")
                    return []
            except requests.exceptions.RequestException as e:
                logger.error(f"ClinicalTrials.gov search failed: {e}")
                return []

        # All retries exhausted
        logger.error(f"All {max_retries} retries exhausted for {drug_name}")
        return []

    def search_pivotal_trials(
        self,
        drug_name: str,
        conditions: List[str],
        max_results: int = 50,
        max_retries: int = 3,
        phase_filter: str = "PHASE2|PHASE3",
        sponsor_filter: str = "INDUSTRY",
        status_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for pivotal trials using proper CT.gov API filters.

        Uses structured field search with:
        - Intervention field for drug name
        - Condition field for disease (searches all provided condition terms)
        - Phase filter for Phase 2/3
        - Sponsor filter for industry-sponsored trials

        Args:
            drug_name: Generic name of drug (searched in intervention field)
            conditions: List of condition terms to search (disease name + synonyms)
            max_results: Maximum number of results
            max_retries: Maximum number of retry attempts
            phase_filter: Phase filter (default: "PHASE2|PHASE3")
            sponsor_filter: Sponsor type filter (default: "INDUSTRY", use None for all)
            status_filter: Optional status filter (e.g., "COMPLETED")

        Returns:
            List of trial summaries with parsed data
        """
        import time

        all_trials = []
        seen_ncts = set()

        # Build the advanced filter for phase and sponsor
        filter_parts = []

        if phase_filter:
            # Format: AREA[Phase](PHASE2 OR PHASE3)
            phases = phase_filter.split("|")
            phase_expr = " OR ".join(phases)
            filter_parts.append(f"AREA[Phase]({phase_expr})")

        if sponsor_filter:
            # Format: AREA[LeadSponsorClass]INDUSTRY
            filter_parts.append(f"AREA[LeadSponsorClass]{sponsor_filter}")

        if status_filter:
            # Format: AREA[OverallStatus]COMPLETED
            filter_parts.append(f"AREA[OverallStatus]{status_filter}")

        advanced_filter = " AND ".join(filter_parts) if filter_parts else None

        # Search for each condition term
        for condition in conditions:
            if len(all_trials) >= max_results:
                break

            params = {
                "query.intr": drug_name,
                "query.cond": condition,
                "pageSize": max_results,
                "format": "json"
            }

            if advanced_filter:
                params["filter.advanced"] = advanced_filter

            if self.api_key:
                params["api_key"] = self.api_key

            for attempt in range(max_retries):
                try:
                    self._ensure_rate_limit()

                    response = self.session.get(
                        f"{self.BASE_URL}/studies",
                        params=params,
                        timeout=self.timeout
                    )
                    response.raise_for_status()

                    data = response.json()
                    studies = data.get("studies", [])

                    logger.info(
                        f"CT.gov structured search: intr='{drug_name}' cond='{condition}' "
                        f"filter='{advanced_filter}' -> {len(studies)} trials"
                    )

                    # Parse and deduplicate
                    parsed = self._parse_studies_for_landscape(studies)
                    for trial in parsed:
                        nct_id = trial.get('nct_id')
                        if nct_id and nct_id not in seen_ncts:
                            seen_ncts.add(nct_id)
                            all_trials.append(trial)

                    break  # Success

                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:
                        wait_time = (attempt + 1) * 2
                        logger.warning(f"Rate limited, waiting {wait_time}s")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.warning(f"Search failed for condition '{condition}': {e}")
                        break
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Search failed for condition '{condition}': {e}")
                    break

        logger.info(f"Total unique pivotal trials found: {len(all_trials)}")
        return all_trials[:max_results]

    def search_by_intervention(
        self,
        drug_name: str,
        condition: Optional[str] = None,
        max_results: int = 50,
        max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Search trials by drug/intervention name with retry logic.

        DEPRECATED: Use search_trials() or search_pivotal_trials() instead.

        Args:
            drug_name: Name of drug or intervention
            condition: Optional condition filter
            max_results: Maximum number of results
            max_retries: Maximum number of retry attempts for rate limits

        Returns:
            List of trial summaries with parsed data
        """
        # Call new search_trials method with fuzzy search enabled
        return self.search_trials(drug_name, condition, max_results, max_retries, use_fuzzy_search=True)

    def search_by_condition(
        self,
        condition: str,
        sponsor_type: Optional[str] = "INDUSTRY",
        min_phase: Optional[str] = None,
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search trials by medical condition.

        Args:
            condition: Disease or condition
            sponsor_type: "INDUSTRY", "NIH", or None for all
            min_phase: Minimum phase (e.g., "Phase 2")
            max_results: Maximum number of results

        Returns:
            List of trial summaries
        """
        try:
            params = {
                "query.cond": condition,
                "pageSize": max_results,
                "format": "json"
            }

            if sponsor_type:
                params["filter.advanced"] = f"AREA[LeadSponsorClass]{sponsor_type}"

            if self.api_key:
                params["api_key"] = self.api_key

            # Enforce global rate limit
            self._ensure_rate_limit()

            response = self.session.get(
                f"{self.BASE_URL}/studies",
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()
            studies = data.get("studies", [])

            logger.info(f"Found {len(studies)} trials for condition: {condition}")

            # Parse and optionally filter by phase
            parsed = self._parse_studies_for_landscape(studies)

            if min_phase:
                parsed = [s for s in parsed if self._meets_phase_requirement(s.get("phase"), min_phase)]

            return parsed

        except requests.exceptions.RequestException as e:
            logger.error(f"ClinicalTrials.gov search by condition failed: {e}")
            return []

    def get_trial_details(self, nct_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full details for a specific trial including outcomes.

        Args:
            nct_id: NCT identifier (e.g., "NCT01234567")

        Returns:
            Detailed trial information
        """
        try:
            params = {"format": "json"}
            if self.api_key:
                params["api_key"] = self.api_key

            # Enforce global rate limit
            self._ensure_rate_limit()

            response = self.session.get(
                f"{self.BASE_URL}/studies/{nct_id}",
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()

            data = response.json()

            # Return the full study data including protocolSection for downstream parsing
            # The enrichment script needs access to the raw structure for date/enrollment extraction
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get trial details for {nct_id}: {e}")
            return None

    def get_parsed_trial_details(self, nct_id: str) -> Optional[Dict[str, Any]]:
        """
        Get parsed trial details in structured format for database storage.

        Args:
            nct_id: NCT identifier (e.g., "NCT01234567")

        Returns:
            Parsed trial details with all fields populated, or None if fetch fails
        """
        try:
            raw_data = self.get_trial_details(nct_id)
            if not raw_data:
                return None

            # Parse using existing extract_study_summary method
            parsed = self.extract_study_summary(raw_data)

            # Add secondary outcomes
            protocol = raw_data.get("protocolSection", {})
            outcomes_module = protocol.get("outcomesModule", {})
            parsed["secondary_outcomes"] = self._extract_outcomes(
                outcomes_module.get("secondaryOutcomes", [])
            )

            # Extract sponsor info
            sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
            lead_sponsor = sponsor_module.get("leadSponsor", {})
            parsed["sponsor"] = lead_sponsor.get("name")
            parsed["sponsor_class"] = lead_sponsor.get("class")

            # Get intervention names as simple list
            parsed["intervention_names"] = [i["name"] for i in parsed["interventions"] if i.get("name")]

            logger.debug(f"Successfully parsed trial details for {nct_id}")
            return parsed

        except Exception as e:
            logger.error(f"Failed to parse trial details for {nct_id}: {e}")
            return None

    def _parse_studies_for_landscape(self, studies: List[Dict]) -> List[Dict[str, Any]]:
        """
        Parse raw API response into simplified study list for landscape agent.

        Args:
            studies: Raw studies from API

        Returns:
            List of simplified study dictionaries
        """
        parsed = []

        for study in studies:
            protocol = study.get("protocolSection", {})
            identification = protocol.get("identificationModule", {})

            # Extract phases
            phases = protocol.get("designModule", {}).get("phases", [])
            phase_str = ", ".join(phases) if phases else "Unknown"

            # Extract study type
            study_type = protocol.get("designModule", {}).get("studyType", "")

            # Debug logging
            nct_id = identification.get("nctId")
            logger.debug(f"Trial {nct_id}: phases={phases}, study_type={study_type}")

            # If phase is Unknown, fall back to study_type
            if phase_str == "Unknown" and study_type:
                logger.info(f"Trial {nct_id}: Using study_type '{study_type}' as phase (no phases found)")
                phase_str = study_type

            # Extract interventions
            interventions_raw = protocol.get("armsInterventionsModule", {}).get("interventions", [])
            intervention_names = [i.get("name") for i in interventions_raw if i.get("name")]

            # Extract enrollment (from designModule per API docs)
            enrollment = protocol.get("designModule", {}).get("enrollmentInfo", {}).get("count")

            # Extract dates
            start_date = protocol.get("statusModule", {}).get("startDateStruct", {}).get("date")
            completion_date = protocol.get("statusModule", {}).get("completionDateStruct", {}).get("date")

            # Extract acronym from API (NEW!)
            acronym = identification.get("acronym")

            parsed.append({
                "nct_id": identification.get("nctId"),
                "title": identification.get("briefTitle"),
                "acronym": acronym,  # NEW: Include acronym from API
                "phase": phase_str,
                "status": protocol.get("statusModule", {}).get("overallStatus"),
                "sponsor": protocol.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name"),
                "conditions": protocol.get("conditionsModule", {}).get("conditions", []),
                "interventions": intervention_names,
                "enrollment": enrollment,
                "start_date": start_date,
                "completion_date": completion_date
            })

        return parsed

    def _meets_phase_requirement(self, phase_str: str, min_phase: str) -> bool:
        """
        Check if phase meets minimum requirement.

        Args:
            phase_str: Phase string from trial (e.g., "Phase 2, Phase 3")
            min_phase: Minimum required phase (e.g., "Phase 2")

        Returns:
            True if meets requirement
        """
        phase_order = {
            "Early Phase 1": 0,
            "Phase 1": 1,
            "Phase 2": 2,
            "Phase 3": 3,
            "Phase 4": 4
        }

        if not phase_str or phase_str == "Unknown":
            return False

        # Extract highest phase from string
        phases_in_str = [p.strip() for p in phase_str.split(",")]
        max_phase_value = max([phase_order.get(p, -1) for p in phases_in_str])
        min_phase_value = phase_order.get(min_phase, -1)

        return max_phase_value >= min_phase_value

    @staticmethod
    def most_advanced_phase(phases: List[str]) -> str:
        """
        Determine most advanced phase from list.

        Args:
            phases: List of phase strings

        Returns:
            Most advanced phase string
        """
        phase_order = {
            "Phase 4": 4,
            "Phase 3": 3,
            "Phase 2": 2,
            "Phase 1": 1,
            "Early Phase 1": 0
        }

        sorted_phases = sorted(phases, key=lambda p: phase_order.get(p, -1), reverse=True)
        return sorted_phases[0] if sorted_phases else "Unknown"

    @staticmethod
    def overall_status(statuses: List[str]) -> str:
        """
        Determine overall status from list of trial statuses.

        Args:
            statuses: List of status strings

        Returns:
            Overall status (priority: Recruiting > Active > Completed > Terminated)
        """
        if "Recruiting" in statuses:
            return "Recruiting"
        elif "Active, not recruiting" in statuses:
            return "Active"
        elif "Completed" in statuses:
            return "Completed"
        elif "Terminated" in statuses:
            return "Terminated"
        elif statuses:
            return statuses[0]
        else:
            return "Unknown"

    def get_trial_publications(self, nct_id: str) -> List[Dict[str, Any]]:
        """
        Get publications linked to a trial, prioritizing original trial results.

        Prioritization order:
        1. RESULT type publications
        2. Publications with trial name/acronym in citation (e.g., "BLISS-52")
        3. Publications with primary results keywords
        4. Older publications (lower PMID = older = original results)

        Args:
            nct_id: NCT identifier

        Returns:
            List of publication references with pmid, type, citation, is_original
        """
        try:
            data = self.get_study_details(nct_id)
            if not data:
                return []

            protocol = data.get('protocolSection', {})
            refs_module = protocol.get('referencesModule', {})
            refs = refs_module.get('references', [])

            # Get trial title for acronym extraction
            id_module = protocol.get('identificationModule', {})
            brief_title = id_module.get('briefTitle', '')
            official_title = id_module.get('officialTitle', '')

            # Extract trial acronyms (e.g., BLISS-52, TULIP-1, MUSE)
            import re
            trial_acronyms = set()
            for title in [brief_title, official_title]:
                # Match patterns like BLISS-52, TULIP-1, MUSE, BEL114333
                matches = re.findall(r'\b([A-Z]{3,}[-]?\d*)\b', title.upper())
                trial_acronyms.update(matches)
                # Also match study IDs like BEL114333
                matches = re.findall(r'\b([A-Z]{2,3}\d{5,})\b', title.upper())
                trial_acronyms.update(matches)

            publications = []
            for ref in refs:
                pmid = ref.get('pmid')
                if pmid:
                    citation = ref.get('citation', '')
                    pub_type = ref.get('type', 'UNKNOWN')
                    citation_upper = citation.upper()

                    # Determine if this is likely an original results paper
                    is_original = False

                    # Check for trial acronym in citation
                    for acronym in trial_acronyms:
                        if acronym in citation_upper:
                            is_original = True
                            break

                    # Check for primary results keywords
                    primary_keywords = [
                        'efficacy and safety', 'phase 3', 'phase iii', 'phase 2', 'phase ii',
                        'randomised', 'randomized', 'double-blind', 'placebo-controlled',
                        'primary endpoint', 'primary outcome', 'pivotal trial'
                    ]
                    citation_lower = citation.lower()
                    if any(kw in citation_lower for kw in primary_keywords):
                        is_original = True

                    publications.append({
                        'pmid': str(pmid),
                        'type': pub_type,
                        'citation': citation,
                        'nct_id': nct_id,
                        'is_original': is_original
                    })

            # Sort: RESULT type first, then original papers, then by PMID (older first)
            def sort_key(pub):
                type_score = 0 if pub['type'] == 'RESULT' else 1
                original_score = 0 if pub.get('is_original') else 1
                try:
                    pmid_score = int(pub['pmid'])
                except:
                    pmid_score = 99999999
                return (type_score, original_score, pmid_score)

            publications.sort(key=sort_key)

            logger.info(f"Found {len(publications)} publications for {nct_id}")
            originals = sum(1 for p in publications if p.get('is_original'))
            if originals:
                logger.debug(f"  {originals} identified as likely original results")

            return publications

        except Exception as e:
            logger.error(f"Error getting publications for {nct_id}: {e}")
            return []

    def get_primary_result_publications(self, nct_id: str, trial_name: str = None) -> List[str]:
        """
        Get PMIDs of primary results publications for a trial.

        Filters publications to find the most likely primary results papers.

        Args:
            nct_id: NCT identifier
            trial_name: Optional trial name (e.g., "BLISS-52") to match

        Returns:
            List of PMIDs likely to be primary results papers
        """
        pubs = self.get_trial_publications(nct_id)
        if not pubs:
            return []

        primary_pmids = []
        keywords = ['efficacy', 'safety', 'phase 3', 'phase iii', 'randomized', 'randomised',
                    'double-blind', 'placebo-controlled', 'primary endpoint', 'results']

        for pub in pubs:
            citation = pub.get('citation', '').lower()

            # Check if citation contains keywords indicating primary results
            matches = sum(1 for kw in keywords if kw in citation)

            # Also check if trial name matches
            if trial_name and trial_name.lower() in citation:
                matches += 3

            # Check for NCT ID in citation
            if nct_id.lower() in citation:
                matches += 2

            if matches >= 2:
                primary_pmids.append(pub['pmid'])

        logger.info(f"Found {len(primary_pmids)} primary result publications for {nct_id}")
        return primary_pmids

    def close(self):
        """Close the HTTP session"""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_tool_definition() -> dict:
    """
    Get tool definition for Claude tool use.

    Returns:
        Tool definition dictionary
    """
    return {
        "name": "search_clinical_trials",
        "description": "Search ClinicalTrials.gov for clinical trial information by drug name, condition, or company. Returns trial details including phase, status, enrollment, and outcomes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (drug name, condition, company, or NCT ID)"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    }
