"""
Trial Discovery Service for Efficacy Benchmarking.

Discovers Phase 2/3 trial names for approved drugs using:
1. ClinicalTrials.gov API (acronym field)
2. Claude + web search as fallback
"""

import os
import re
import logging
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field

import anthropic

from src.tools.clinicaltrials import ClinicalTrialsAPI

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredTrial:
    """A discovered clinical trial."""
    name: str  # Trial name/acronym (e.g., "TULIP-1", "BLISS-52")
    nct_id: Optional[str] = None
    phase: Optional[str] = None
    indication: Optional[str] = None
    status: Optional[str] = None
    source: str = "unknown"  # "clinicaltrials.gov", "web_search", "claude"


@dataclass
class DrugTrialInfo:
    """Trial information for a drug."""
    drug_name: str
    generic_name: str
    trials: List[DiscoveredTrial] = field(default_factory=list)

    @property
    def trial_names(self) -> List[str]:
        """Get list of trial names."""
        return [t.name for t in self.trials]


class TrialDiscoveryService:
    """
    Discovers Phase 2/3 trial names for approved drugs.

    Uses multiple sources:
    1. ClinicalTrials.gov API - official acronym field
    2. Claude + web search - for trials without acronyms
    """

    def __init__(self):
        self.ct_api = ClinicalTrialsAPI()
        self.anthropic = anthropic.Anthropic()

    def discover_trials(
        self,
        drug_name: str,
        generic_name: str,
        indication: str,
        use_web_search: bool = True
    ) -> DrugTrialInfo:
        """
        Discover Phase 2/3 trial names for a drug.

        Args:
            drug_name: Brand name or generic name
            generic_name: Generic drug name
            indication: Disease/indication to search for
            use_web_search: Whether to use Claude + web search as fallback

        Returns:
            DrugTrialInfo with discovered trials
        """
        result = DrugTrialInfo(drug_name=drug_name, generic_name=generic_name)

        # Clean the generic name (remove -FNIA, -XXXX suffixes)
        clean_name = self._clean_generic_name(generic_name)
        logger.info(f"Discovering trials for {clean_name} in {indication}")

        # Step 1: Get trials from ClinicalTrials.gov
        ct_trials = self._discover_from_clinicaltrials(clean_name, indication)
        result.trials.extend(ct_trials)
        logger.info(f"Found {len(ct_trials)} trials from ClinicalTrials.gov")

        # Step 2: For trials with only NCT IDs, use Claude to find proper names
        unnamed_trials = [t for t in result.trials if t.name and t.name.startswith("NCT")]
        if unnamed_trials:
            logger.info(f"Found {len(unnamed_trials)} trials without acronyms, looking up names...")
            self._lookup_names_for_nct_ids(unnamed_trials, clean_name, drug_name, indication)

        # Step 3: Use Claude + web search if we still don't have enough named trials
        named_trials = [t for t in result.trials if t.name and not t.name.startswith("NCT")]
        if use_web_search and len(named_trials) < 2:
            logger.info("Few named trials found, using Claude + web search...")
            web_trials = self._discover_from_web_search(clean_name, drug_name, indication)

            # Add trials that aren't duplicates
            existing_names = {t.name.upper() for t in result.trials}
            for trial in web_trials:
                if trial.name.upper() not in existing_names:
                    result.trials.append(trial)
                    existing_names.add(trial.name.upper())

            logger.info(f"Added {len(web_trials)} trials from web search")

        # Deduplicate trials by name, preferring CT.gov official acronyms over Claude lookups
        # First, collect all trials by name
        trials_by_name = {}
        for trial in result.trials:
            name_upper = trial.name.upper() if trial.name else ""
            if not name_upper or name_upper.startswith("NCT"):
                continue

            if name_upper not in trials_by_name:
                trials_by_name[name_upper] = trial
            else:
                # Prefer clinicaltrials.gov source over claude lookups
                existing = trials_by_name[name_upper]
                if trial.source == "clinicaltrials.gov" and existing.source != "clinicaltrials.gov":
                    trials_by_name[name_upper] = trial
                # Prefer Phase 3 over Phase 2
                elif trial.phase and "PHASE3" in trial.phase.upper() and existing.phase and "PHASE2" in existing.phase.upper():
                    trials_by_name[name_upper] = trial

        # Keep unnamed trials (NCT IDs) as well
        unique_trials = list(trials_by_name.values())
        for trial in result.trials:
            if trial.name and trial.name.startswith("NCT"):
                unique_trials.append(trial)

        result.trials = unique_trials

        # Log final result
        logger.info(f"Discovered {len(result.trials)} total trials: {result.trial_names}")
        return result

    def _clean_generic_name(self, name: str) -> str:
        """Remove suffixes like -FNIA from generic names."""
        # Remove common suffixes
        cleaned = re.sub(r'-[A-Z]{3,4}$', '', name)
        return cleaned

    def _is_drug_code(self, name: str) -> bool:
        """Check if a name is a drug code rather than a trial name."""
        if not name:
            return False
        # Drug codes: MEDI-546, CNTO1959, GSK123456, etc.
        drug_code_patterns = [
            r'^[A-Z]{2,4}-?\d{3,6}$',  # MEDI-546, GSK-123456
            r'^[A-Z]{3,5}\d{4,6}$',    # CNTO1959, ABT12345
        ]
        for pattern in drug_code_patterns:
            if re.match(pattern, name.upper()):
                return True
        return False

    def _discover_from_clinicaltrials(
        self,
        drug_name: str,
        indication: str
    ) -> List[DiscoveredTrial]:
        """
        Discover trials from ClinicalTrials.gov API.

        Uses the official 'acronym' field when available.
        """
        trials = []
        seen_ncts = set()

        # Search for Phase 2/3 industry-sponsored trials
        try:
            ct_results = self.ct_api.search_pivotal_trials(
                drug_name=drug_name,
                conditions=[indication],
                max_results=20,
                phase_filter="PHASE2|PHASE3",
                sponsor_filter="INDUSTRY"
            )

            for ct_trial in ct_results:
                nct_id = ct_trial.get('nct_id')
                if nct_id in seen_ncts:
                    continue
                seen_ncts.add(nct_id)

                # Get the acronym (official trial name)
                acronym = ct_trial.get('acronym')
                title = ct_trial.get('title', '')

                # Use acronym if available, otherwise extract from title or use NCT ID
                if acronym and not self._is_drug_code(acronym):
                    trial_name = acronym
                else:
                    # Try to extract from title
                    trial_name = self._extract_trial_name_from_title(title) or nct_id

                trials.append(DiscoveredTrial(
                    name=trial_name,
                    nct_id=nct_id,
                    phase=ct_trial.get('phase'),
                    indication=indication,
                    status=ct_trial.get('status'),
                    source="clinicaltrials.gov"
                ))

        except Exception as e:
            logger.error(f"Error searching ClinicalTrials.gov: {e}")

        return trials

    def _extract_trial_name_from_title(self, title: str) -> Optional[str]:
        """Extract trial name from CT.gov title if present."""
        if not title:
            return None

        # Look for common trial name patterns
        # e.g., "TULIP-1: A Study of..." or "The BLISS-52 Trial"
        patterns = [
            r'\b([A-Z]{3,}-\d+[A-Z]?)\b',  # TULIP-1, BLISS-52
            r'\b([A-Z]{4,}\d+)\b',  # MUSE2
        ]

        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                name = match.group(1)
                # Exclude false positives and drug codes
                if name not in {'PHASE', 'STUDY', 'TRIAL', 'PART'} and not self._is_drug_code(name):
                    return name

        return None

    # Known trial name -> drug mappings to prevent cross-drug confusion
    # BRAVE = baricitinib, TULIP = anifrolumab, BLISS = belimumab, etc.
    TRIAL_DRUG_MAPPINGS = {
        "BRAVE": "baricitinib",
        "TULIP": "anifrolumab",
        "BLISS": "belimumab",
        "MUSE": "anifrolumab",
        "AURA": "voclosporin",
        "AURORA": "voclosporin",
        "EXPLORER": "rituximab",
        "LUNAR": "obinutuzumab",
        "NOBILITY": "obinutuzumab",
        "CARIBOU": "dapirolizumab",
    }

    def _validate_trial_name_for_drug(self, trial_name: str, drug_name: str) -> bool:
        """
        Validate that a trial name is appropriate for the given drug.

        Prevents cross-drug confusion (e.g., BRAVE is for baricitinib, not anifrolumab).
        """
        if not trial_name:
            return False

        trial_prefix = trial_name.upper().split("-")[0].split(" ")[0]
        drug_lower = drug_name.lower()

        # Check if this trial prefix is known to belong to a different drug
        if trial_prefix in self.TRIAL_DRUG_MAPPINGS:
            expected_drug = self.TRIAL_DRUG_MAPPINGS[trial_prefix].lower()
            if expected_drug not in drug_lower:
                logger.warning(
                    f"Trial name '{trial_name}' rejected - belongs to {expected_drug}, not {drug_name}"
                )
                return False

        return True

    def _lookup_names_for_nct_ids(
        self,
        trials: List[DiscoveredTrial],
        generic_name: str,
        brand_name: str,
        indication: str
    ) -> None:
        """
        Use Claude to find proper trial names for NCT IDs without acronyms.

        Updates trials in place with discovered names.
        Validates that trial names actually belong to this drug.
        """
        if not trials:
            return

        nct_ids = [t.nct_id for t in trials if t.nct_id]
        if not nct_ids:
            return

        nct_list = ", ".join(nct_ids)

        prompt = f"""I need to find the official trial names/acronyms for these clinical trials:

NCT IDs: {nct_list}
Drug: {generic_name} ({brand_name})
Indication: {indication}

CRITICAL: Only return trial names that are CONFIRMED to be for {generic_name}.
Do NOT guess or infer trial names from other drugs.
For example, BRAVE is a baricitinib trial, TULIP is an anifrolumab trial, BLISS is a belimumab trial.

For each NCT ID, find its official trial name/acronym (like "TULIP-1", "TULIP-2", "MUSE", "BLISS-52", etc.).
These are typically 3-8 character acronyms, sometimes with a number suffix.

Return ONLY a JSON object mapping NCT IDs to trial names. Example:
{{"NCT02446899": "TULIP-1", "NCT02446912": "TULIP-2"}}

If you cannot find a confirmed name for an NCT ID for THIS SPECIFIC DRUG, omit it from the result.
It's better to return an empty object than to guess incorrectly.

Return ONLY the JSON object, no explanation:"""

        try:
            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            result_text = response.content[0].text.strip()

            # Parse JSON response
            import json
            # Clean up response (remove markdown if present)
            if result_text.startswith("```"):
                result_text = re.sub(r'^```json?\s*', '', result_text)
                result_text = re.sub(r'\s*```$', '', result_text)

            nct_to_name = json.loads(result_text)

            if isinstance(nct_to_name, dict):
                for trial in trials:
                    if trial.nct_id in nct_to_name:
                        new_name = nct_to_name[trial.nct_id]
                        if isinstance(new_name, str) and len(new_name) >= 3:
                            # Validate that this trial name belongs to this drug
                            if self._validate_trial_name_for_drug(new_name, generic_name):
                                logger.info(f"Found name for {trial.nct_id}: {new_name}")
                                trial.name = new_name
                                trial.source = "claude_nct_lookup"
                            else:
                                logger.warning(f"Rejected name '{new_name}' for {trial.nct_id} - wrong drug")

        except Exception as e:
            logger.error(f"Error looking up NCT names with Claude: {e}")

    def _discover_from_web_search(
        self,
        generic_name: str,
        brand_name: str,
        indication: str
    ) -> List[DiscoveredTrial]:
        """
        Discover trial names using Claude with web search.

        Claude will search for Phase 2/3 trial names for the drug.
        """
        trials = []

        prompt = f"""Find the names of Phase 2 and Phase 3 clinical trials for {generic_name} ({brand_name})
in {indication}.

I need the official trial names/acronyms like "TULIP-1", "BLISS-52", "MUSE", etc.
These are typically 3-8 character acronyms, sometimes with a number suffix.

Search for "{generic_name} phase 3 trial name" and "{brand_name} pivotal trials".

Return ONLY a JSON array of trial names. Example format:
["TULIP-1", "TULIP-2", "MUSE"]

If you cannot find specific trial names, return an empty array: []

Return ONLY the JSON array, no explanation:"""

        try:
            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            result_text = response.content[0].text.strip()

            # Parse JSON response
            import json
            # Clean up response (remove markdown if present)
            if result_text.startswith("```"):
                result_text = re.sub(r'^```json?\s*', '', result_text)
                result_text = re.sub(r'\s*```$', '', result_text)

            trial_names = json.loads(result_text)

            if isinstance(trial_names, list):
                for name in trial_names:
                    if isinstance(name, str) and len(name) >= 3:
                        trials.append(DiscoveredTrial(
                            name=name,
                            indication=indication,
                            source="claude_web_search"
                        ))

        except Exception as e:
            logger.error(f"Error in Claude web search: {e}")

        return trials

    def match_trials_to_nct(
        self,
        trials: List[DiscoveredTrial],
        drug_name: str,
        indication: str
    ) -> List[DiscoveredTrial]:
        """
        Match discovered trial names to NCT IDs.

        For trials discovered via web search, find their NCT IDs on CT.gov.
        """
        for trial in trials:
            if trial.nct_id:
                continue  # Already has NCT ID

            # Search CT.gov for this trial name
            try:
                results = self.ct_api.search_pivotal_trials(
                    drug_name=drug_name,
                    conditions=[indication],
                    max_results=10
                )

                # Find trial with matching acronym or title containing the name
                for ct_trial in results:
                    acronym = ct_trial.get('acronym', '')
                    title = ct_trial.get('title', '')

                    if (trial.name.upper() == acronym.upper() or
                        trial.name.upper() in title.upper()):
                        trial.nct_id = ct_trial.get('nct_id')
                        trial.phase = ct_trial.get('phase')
                        trial.status = ct_trial.get('status')
                        logger.info(f"Matched {trial.name} to {trial.nct_id}")
                        break

            except Exception as e:
                logger.error(f"Error matching trial {trial.name}: {e}")

        return trials
