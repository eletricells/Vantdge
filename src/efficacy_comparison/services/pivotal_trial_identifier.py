"""
PivotalTrialIdentifier Service

Identifies pivotal clinical trials that supported FDA approval for a drug+indication.
Uses multiple methods: FDA label parsing, ClinicalTrials.gov filtering, web validation.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
from src.drug_extraction_system.api_clients.clinicaltrials_client import ClinicalTrialsClient
from src.efficacy_comparison.models import ApprovedDrug, PivotalTrial

logger = logging.getLogger(__name__)


# Patterns to extract trial names from FDA labels
TRIAL_NAME_PATTERNS = [
    # "Study 1 (TULIP-2)" or "the TULIP-2 study"
    r'\b(?:study|trial)\s*(?:\d+\s*)?\(([A-Z][A-Z0-9\-]+(?:\s*\d+)?)\)',
    r'\bthe\s+([A-Z][A-Z0-9\-]+(?:\s*\d+)?)\s+(?:study|trial)',
    # "TULIP-2, a Phase 3 trial"
    r'\b([A-Z][A-Z0-9\-]+(?:\s*\d+)?),?\s+a\s+(?:phase|Phase)\s*[23]',
    # "In TULIP-2,"
    r'\bIn\s+([A-Z][A-Z0-9\-]+(?:\s*\d+)?),',
    # "NCT12345678"
    r'\b(NCT\d{8})\b',
]

# Common trial name patterns (acronyms)
COMMON_TRIAL_ACRONYM_PATTERN = re.compile(
    r'\b([A-Z]{2,}[\-\s]?(?:AD|SC|LTE|OLE)?\d*)\b'
)

# Phase patterns
PHASE_PATTERNS = {
    'PHASE3': ['phase 3', 'phase iii', 'phase-3', 'pivotal'],
    'PHASE2': ['phase 2', 'phase ii', 'phase-2', 'phase 2b', 'phase 2/3'],
}

# Curated list of known pivotal trials for major drugs
# Key format: (drug_generic_name, indication_lower)
KNOWN_PIVOTAL_TRIALS = {
    ("dupilumab", "atopic dermatitis"): [
        {"name": "SOLO 1", "nct": "NCT02277743", "phase": "Phase 3", "enrollment": 671},
        {"name": "SOLO 2", "nct": "NCT02277769", "phase": "Phase 3", "enrollment": 708},
        {"name": "CHRONOS", "nct": "NCT02260986", "phase": "Phase 3", "enrollment": 740},
        {"name": "CAFE", "nct": "NCT02755649", "phase": "Phase 3", "enrollment": 325},
    ],
    ("tralokinumab", "atopic dermatitis"): [
        {"name": "ECZTRA 1", "nct": "NCT03131648", "phase": "Phase 3", "enrollment": 802},
        {"name": "ECZTRA 2", "nct": "NCT03160885", "phase": "Phase 3", "enrollment": 794},
        {"name": "ECZTRA 3", "nct": "NCT03363854", "phase": "Phase 3", "enrollment": 380},
    ],
    ("upadacitinib", "atopic dermatitis"): [
        {"name": "Measure Up 1", "nct": "NCT03569293", "phase": "Phase 3", "enrollment": 847},
        {"name": "Measure Up 2", "nct": "NCT03607422", "phase": "Phase 3", "enrollment": 836},
        {"name": "AD Up", "nct": "NCT03568318", "phase": "Phase 3", "enrollment": 901},
    ],
    ("abrocitinib", "atopic dermatitis"): [
        {"name": "JADE MONO-1", "nct": "NCT03349060", "phase": "Phase 3", "enrollment": 387},
        {"name": "JADE MONO-2", "nct": "NCT03575871", "phase": "Phase 3", "enrollment": 391},
        {"name": "JADE COMPARE", "nct": "NCT03720470", "phase": "Phase 3", "enrollment": 838},
    ],
    ("ruxolitinib", "atopic dermatitis"): [
        {"name": "TRuE-AD1", "nct": "NCT03745638", "phase": "Phase 3", "enrollment": 631},
        {"name": "TRuE-AD2", "nct": "NCT03745651", "phase": "Phase 3", "enrollment": 618},
    ],
    ("anifrolumab", "systemic lupus erythematosus"): [
        {"name": "TULIP-1", "nct": "NCT02446899", "phase": "Phase 3", "enrollment": 457},
        {"name": "TULIP-2", "nct": "NCT02446912", "phase": "Phase 3", "enrollment": 362},
    ],
    ("belimumab", "systemic lupus erythematosus"): [
        {"name": "BLISS-52", "nct": "NCT00424476", "phase": "Phase 3", "enrollment": 865},
        {"name": "BLISS-76", "nct": "NCT00410384", "phase": "Phase 3", "enrollment": 819},
    ],
}


class PivotalTrialIdentifier:
    """
    Identifies pivotal trials that supported FDA approval for a drug+indication.

    Uses multiple methods in priority order:
    1. Parse FDA label "Clinical Studies" section for trial names
    2. Search ClinicalTrials.gov with strict filters
    3. Validate findings via cross-referencing

    Returns the 3-4 most likely pivotal trials for extraction.
    """

    def __init__(
        self,
        openfda_client: Optional[OpenFDAClient] = None,
        clinicaltrials_client: Optional[ClinicalTrialsClient] = None,
    ):
        """
        Initialize the service.

        Args:
            openfda_client: Optional OpenFDA client
            clinicaltrials_client: Optional ClinicalTrials.gov client
        """
        self.openfda = openfda_client or OpenFDAClient()
        self.ctgov = clinicaltrials_client or ClinicalTrialsClient()

    async def identify_pivotal_trials(
        self,
        drug: ApprovedDrug,
        indication: str,
        max_trials: int = 4,
    ) -> List[PivotalTrial]:
        """
        Identify pivotal trials for a drug+indication.

        Args:
            drug: ApprovedDrug object with drug information
            indication: Disease/condition name
            max_trials: Maximum number of trials to return

        Returns:
            List of PivotalTrial objects, sorted by confidence
        """
        logger.info(f"Identifying pivotal trials for {drug.drug_name} in {indication}")

        all_trials: List[PivotalTrial] = []

        # Method 0: Check curated list of known pivotal trials (most reliable)
        curated_trials = self._get_curated_trials(drug, indication)
        if curated_trials:
            logger.info(f"Using curated trial list for {drug.generic_name} ({len(curated_trials)} trials)")
            return curated_trials[:max_trials]

        # Method 1: Parse FDA label for trial names
        fda_trials = await self._extract_trials_from_fda_label(drug, indication)
        if fda_trials:
            logger.info(f"Found {len(fda_trials)} trials from FDA label")
            all_trials.extend(fda_trials)

        # Method 2: Search ClinicalTrials.gov with strict filters
        ctgov_trials = await self._search_clinicaltrials_gov(drug, indication)
        if ctgov_trials:
            logger.info(f"Found {len(ctgov_trials)} trials from ClinicalTrials.gov")
            # Add trials not already found
            existing_ncts = {t.nct_id for t in all_trials if t.nct_id}
            for trial in ctgov_trials:
                if trial.nct_id not in existing_ncts:
                    all_trials.append(trial)
                else:
                    # Merge info if we have the same trial from both sources
                    self._merge_trial_info(all_trials, trial)

        # Method 3: Enrich with CT.gov data for trials found in FDA label
        await self._enrich_trials_from_ctgov(all_trials, drug)

        # Score and rank trials
        scored_trials = self._score_and_rank_trials(all_trials, indication)

        # Return top N trials
        result = scored_trials[:max_trials]
        logger.info(f"Returning {len(result)} pivotal trials for {drug.drug_name}")

        return result

    def _get_curated_trials(
        self,
        drug: ApprovedDrug,
        indication: str,
    ) -> List[PivotalTrial]:
        """
        Get pivotal trials from curated list if available.

        Args:
            drug: ApprovedDrug object
            indication: Disease/condition name

        Returns:
            List of PivotalTrial objects from curated list, or empty list
        """
        generic_lower = drug.generic_name.lower() if drug.generic_name else ""
        indication_lower = indication.strip().lower()

        key = (generic_lower, indication_lower)
        curated = KNOWN_PIVOTAL_TRIALS.get(key, [])

        if not curated:
            return []

        trials = []
        for trial_info in curated:
            trial = PivotalTrial(
                nct_id=trial_info["nct"],
                trial_name=trial_info["name"],
                phase=trial_info.get("phase"),
                enrollment=trial_info.get("enrollment"),
                confidence=1.0,  # High confidence for curated trials
                identification_source="curated",
            )
            trials.append(trial)

        return trials

    async def _extract_trials_from_fda_label(
        self,
        drug: ApprovedDrug,
        indication: str,
    ) -> List[PivotalTrial]:
        """
        Extract trial information from FDA label Clinical Studies section.

        Only extracts trials that are relevant to the specified indication.
        """
        trials = []

        # Fetch drug label
        labels = self.openfda.search_drug_labels(drug.drug_name, limit=5)
        if not labels:
            labels = self.openfda.search_drug_labels(drug.generic_name, limit=5)

        if not labels:
            logger.debug(f"No FDA label found for {drug.drug_name}")
            return trials

        # Find the most relevant label (for this indication)
        label = self._find_relevant_label(labels, indication)
        if not label:
            label = labels[0]

        # Extract clinical studies section
        clinical_studies = label.get("clinical_studies", [""])[0]
        if not clinical_studies:
            # Try other sections that might contain trial info
            clinical_studies = label.get("indications_and_usage", [""])[0]

        if not clinical_studies:
            return trials

        # Filter clinical studies text to only include sections about the target indication
        clinical_studies = self._filter_clinical_studies_by_indication(
            clinical_studies, indication
        )

        # Extract trial names using patterns
        found_names = set()
        found_ncts = set()

        for pattern in TRIAL_NAME_PATTERNS:
            matches = re.findall(pattern, clinical_studies, re.IGNORECASE)
            for match in matches:
                if match.upper().startswith("NCT"):
                    found_ncts.add(match.upper())
                else:
                    # Clean up trial name
                    name = match.strip().upper()
                    if len(name) >= 3 and not name.isdigit():
                        found_names.add(name)

        # Also look for common acronym patterns
        acronym_matches = COMMON_TRIAL_ACRONYM_PATTERN.findall(clinical_studies)
        for match in acronym_matches:
            name = match.strip().upper()
            # Filter out common false positives and FDA label section headers
            EXCLUDED_WORDS = {
                # Common words
                'THE', 'AND', 'FOR', 'WITH', 'FROM', 'WERE', 'THAT', 'THIS',
                'HAVE', 'BEEN', 'THEY', 'WILL', 'ALSO', 'SOME', 'MORE', 'WHEN',
                # Common abbreviations
                'FDA', 'USA', 'HIV', 'DNA', 'RNA', 'MRI', 'BMI', 'ITT', 'AUC',
                # FDA label section headers
                'INDICATIONS', 'USAGE', 'DOSAGE', 'ADMINISTRATION', 'CONTRAINDICATIONS',
                'WARNINGS', 'PRECAUTIONS', 'ADVERSE', 'REACTIONS', 'OVERDOSAGE',
                'DESCRIPTION', 'PHARMACOLOGY', 'CLINICAL', 'STUDIES', 'REFERENCES',
                'SUPPLIED', 'STORAGE', 'HANDLING', 'INFORMATION', 'PATIENTS',
                'CARCINOGENESIS', 'MUTAGENESIS', 'IMPAIRMENT', 'FERTILITY',
                'PREGNANCY', 'NURSING', 'MOTHERS', 'PEDIATRIC', 'GERIATRIC',
                'THREE', 'FOUR', 'FIVE', 'ADULT', 'CHILDREN', 'TREATMENT',
                'THERAPY', 'DRUG', 'INTERACTIONS', 'MECHANISM', 'ACTION',
                'METABOLISM', 'EXCRETION', 'DISTRIBUTION', 'ABSORPTION',
                # Other false positives
                'RESULTS', 'BASELINE', 'ENDPOINT', 'PRIMARY',
                'SECONDARY', 'EFFICACY', 'SAFETY', 'PLACEBO', 'ACTIVE',
            }
            if (len(name) >= 4 and
                not name.isdigit() and
                name not in EXCLUDED_WORDS):
                found_names.add(name)

        # Create PivotalTrial objects
        for name in found_names:
            trial = PivotalTrial(
                nct_id=None,
                trial_name=name,
                confidence=0.8,  # High confidence from FDA label
                identification_source="fda_label",
            )
            trials.append(trial)

        for nct_id in found_ncts:
            trial = PivotalTrial(
                nct_id=nct_id,
                confidence=0.9,  # Very high confidence with NCT ID
                identification_source="fda_label",
            )
            trials.append(trial)

        # Try to extract phase information
        self._extract_phase_info(trials, clinical_studies)

        return trials

    async def _search_clinicaltrials_gov(
        self,
        drug: ApprovedDrug,
        indication: str,
    ) -> List[PivotalTrial]:
        """
        Search ClinicalTrials.gov for pivotal trials.

        Filters:
        - Phase 2/3 only
        - Completed status
        - Industry-sponsored (usually)
        - Has results (preferably)
        """
        trials = []

        # Build search terms
        search_terms = [drug.generic_name]
        if drug.drug_name and drug.drug_name.lower() != drug.generic_name.lower():
            search_terms.append(drug.drug_name)

        # Search with filters for completed Phase 2/3 trials
        # Include condition filter to only find trials for this indication
        studies = self.ctgov.search_trials(
            drug_name=drug.generic_name,
            status=["COMPLETED"],
            phase=["PHASE2", "PHASE3"],
            limit=50,
            condition=indication,  # Filter by indication
        )

        if not studies:
            # Try without condition filter as fallback
            studies = self.ctgov.search_trials(
                drug_name=drug.generic_name,
                status=["COMPLETED"],
                phase=["PHASE2", "PHASE3"],
                limit=50,
            )

        if not studies:
            return trials

        # Filter for the specific indication
        indication_lower = indication.lower()
        indication_keywords = set(indication_lower.split())

        for study in studies:
            protocol = study.get("protocolSection", {})
            id_module = protocol.get("identificationModule", {})
            status_module = protocol.get("statusModule", {})
            design_module = protocol.get("designModule", {})
            conditions_module = protocol.get("conditionsModule", {})

            # Check if indication matches
            conditions = conditions_module.get("conditions", [])
            conditions_text = " ".join(conditions).lower()

            # Check for indication match (fuzzy)
            indication_match = (
                indication_lower in conditions_text or
                any(kw in conditions_text for kw in indication_keywords if len(kw) > 3)
            )

            if not indication_match:
                continue

            # Extract trial info
            nct_id = id_module.get("nctId")
            trial_name = id_module.get("acronym")  # Official trial acronym
            brief_title = id_module.get("briefTitle", "")

            # If no acronym, try to extract from title
            if not trial_name:
                title_match = COMMON_TRIAL_ACRONYM_PATTERN.search(brief_title)
                if title_match:
                    potential_name = title_match.group(1)
                    if len(potential_name) >= 4:
                        trial_name = potential_name

            # Get phase
            phases = design_module.get("phases", [])
            phase = ", ".join(phases) if phases else None

            # Get enrollment
            enrollment = design_module.get("enrollmentInfo", {}).get("count")

            # Check if has results
            has_results = protocol.get("hasResults", False)

            # Calculate confidence
            confidence = 0.5  # Base confidence
            if phases and any("PHASE3" in p for p in phases):
                confidence += 0.2
            if has_results:
                confidence += 0.15
            if enrollment and enrollment > 100:
                confidence += 0.1
            if trial_name:  # Has official acronym
                confidence += 0.05

            trial = PivotalTrial(
                nct_id=nct_id,
                trial_name=trial_name,
                phase=phase,
                enrollment=enrollment,
                status=status_module.get("overallStatus"),
                confidence=min(confidence, 0.95),
                identification_source="ctgov_search",
            )

            # Extract primary endpoint if available
            outcomes_module = protocol.get("outcomesModule", {})
            primary_outcomes = outcomes_module.get("primaryOutcomes", [])
            if primary_outcomes:
                trial.primary_endpoint = primary_outcomes[0].get("measure")

            trials.append(trial)

        return trials

    async def _enrich_trials_from_ctgov(
        self,
        trials: List[PivotalTrial],
        drug: ApprovedDrug,
    ) -> None:
        """
        Enrich trials found from FDA label with CT.gov data.

        For trials with only a name (no NCT ID), search CT.gov to find the NCT ID.
        For trials with NCT ID but missing info, fetch full details.
        """
        for trial in trials:
            # If we have NCT ID but missing details, fetch them
            if trial.nct_id and (not trial.phase or not trial.enrollment):
                study = self.ctgov.get_trial_by_nct(trial.nct_id)
                if study:
                    data = self.ctgov.extract_trial_data(study)
                    if not trial.phase:
                        trial.phase = data.get("trial_phase")
                    if not trial.enrollment:
                        trial.enrollment = data.get("enrollment")
                    if not trial.primary_endpoint:
                        trial.primary_endpoint = data.get("primary_outcome")
                    if not trial.trial_name:
                        # Try to get acronym
                        protocol = study.get("protocolSection", {})
                        id_module = protocol.get("identificationModule", {})
                        trial.trial_name = id_module.get("acronym")

            # If we only have trial name, search for NCT ID
            elif trial.trial_name and not trial.nct_id:
                # Search CT.gov by trial name
                search_query = f"{drug.generic_name} {trial.trial_name}"
                studies = self.ctgov.search_trials(
                    drug_name=search_query,
                    status=["COMPLETED"],
                    limit=10,
                )

                if studies:
                    # Find the matching study
                    for study in studies:
                        protocol = study.get("protocolSection", {})
                        id_module = protocol.get("identificationModule", {})
                        acronym = id_module.get("acronym", "").upper()
                        title = id_module.get("briefTitle", "").upper()

                        if (trial.trial_name.upper() in acronym or
                            trial.trial_name.upper() in title):
                            trial.nct_id = id_module.get("nctId")
                            data = self.ctgov.extract_trial_data(study)
                            trial.phase = data.get("trial_phase")
                            trial.enrollment = data.get("enrollment")
                            trial.primary_endpoint = data.get("primary_outcome")
                            trial.confidence = min(trial.confidence + 0.1, 0.95)
                            break

    def _find_relevant_label(
        self,
        labels: List[Dict],
        indication: str,
    ) -> Optional[Dict]:
        """Find the label most relevant to the indication."""
        indication_lower = indication.lower()

        for label in labels:
            indications_text = label.get("indications_and_usage", [""])[0].lower()
            if indication_lower in indications_text:
                return label

        return None

    def _filter_clinical_studies_by_indication(
        self,
        clinical_studies_text: str,
        indication: str,
    ) -> str:
        """
        Filter clinical studies text to only include sections about the target indication.

        FDA labels for drugs approved for multiple indications (e.g., tocilizumab for
        RA and COVID-19) have separate sections. This method extracts only the section
        relevant to the target indication.

        Args:
            clinical_studies_text: Full clinical studies section from FDA label
            indication: Target indication to filter for

        Returns:
            Filtered text containing only trials for the target indication
        """
        indication_lower = indication.lower()

        # Common section headers that indicate indication-specific content
        indication_patterns = self._get_indication_section_patterns(indication_lower)

        # Try to find indication-specific section
        text_lower = clinical_studies_text.lower()

        for pattern in indication_patterns:
            # Look for section starting with indication name/pattern
            idx = text_lower.find(pattern)
            if idx != -1:
                # Found a section for this indication
                # Find the end of this section (next major indication header or end)
                end_idx = self._find_next_indication_section(text_lower, idx + len(pattern))
                if end_idx > idx:
                    return clinical_studies_text[idx:end_idx]
                else:
                    return clinical_studies_text[idx:]

        # If no specific section found, check if the entire text is about the indication
        # or if it mentions other indications that we should exclude

        # List of indications to exclude (other common indications for multi-use drugs)
        exclude_indications = [
            "covid-19", "coronavirus", "sars-cov-2",
            "cytokine release syndrome", "crs",
            "giant cell arteritis", "gca",
            "juvenile idiopathic arthritis", "jia",
            "polyarticular juvenile", "systemic juvenile",
            "castleman disease", "castleman's disease",
        ]

        # For RA, also add specific exclusions
        if "rheumatoid" in indication_lower:
            # Keep RA-specific content
            pass
        else:
            # For other indications, exclude RA trials
            exclude_indications.append("rheumatoid arthritis")

        # Check if text contains excluded indication sections
        has_excluded_content = any(
            excl in text_lower for excl in exclude_indications
        )

        if not has_excluded_content:
            # Text doesn't contain excluded indications, return as-is
            return clinical_studies_text

        # Try to extract only the portion relevant to our indication
        # Split by common section markers
        section_markers = [
            f"{indication_lower}",
            "clinical studies",
            "clinical trials",
            "pivotal studies",
        ]

        best_section = clinical_studies_text
        best_score = 0

        # Split text into paragraphs and score relevance
        paragraphs = clinical_studies_text.split("\n\n")
        relevant_paragraphs = []

        for para in paragraphs:
            para_lower = para.lower()
            # Check if paragraph is about excluded indication
            is_excluded = any(excl in para_lower for excl in exclude_indications)
            # Check if paragraph is about target indication
            is_relevant = indication_lower in para_lower or any(
                marker in para_lower for marker in section_markers
            )

            if not is_excluded or is_relevant:
                relevant_paragraphs.append(para)

        if relevant_paragraphs:
            return "\n\n".join(relevant_paragraphs)

        return clinical_studies_text

    def _get_indication_section_patterns(self, indication: str) -> List[str]:
        """Get patterns to identify indication-specific sections in FDA labels."""
        patterns = [
            f"14.1 {indication}",
            f"14.2 {indication}",
            f"14.3 {indication}",
            f"14.4 {indication}",
            f"{indication}",
        ]

        # Add disease-specific patterns
        if "rheumatoid arthritis" in indication:
            patterns.extend([
                "rheumatoid arthritis",
                "14.1 rheumatoid",
                "moderately to severely active rheumatoid",
                "adult patients with moderately to severely active ra",
            ])
        elif "atopic dermatitis" in indication:
            patterns.extend([
                "atopic dermatitis",
                "14.1 atopic",
                "moderate-to-severe atopic dermatitis",
            ])

        return patterns

    def _find_next_indication_section(self, text: str, start_idx: int) -> int:
        """Find the start of the next indication section."""
        # Look for patterns that indicate a new indication section
        next_section_patterns = [
            "14.2 ", "14.3 ", "14.4 ", "14.5 ", "14.6 ",
            "covid-19", "coronavirus",
            "cytokine release syndrome",
            "giant cell arteritis",
            "juvenile idiopathic",
            "castleman",
        ]

        min_idx = len(text)
        for pattern in next_section_patterns:
            idx = text.find(pattern, start_idx)
            if idx != -1 and idx < min_idx:
                min_idx = idx

        return min_idx if min_idx < len(text) else -1

    def _extract_phase_info(
        self,
        trials: List[PivotalTrial],
        text: str,
    ) -> None:
        """Extract phase information from text and assign to trials."""
        text_lower = text.lower()

        for trial in trials:
            if trial.trial_name and not trial.phase:
                # Look for phase mention near trial name
                trial_name_lower = trial.trial_name.lower()
                pattern = rf'{trial_name_lower}[^.]*?(phase\s*[23]|phase\s*ii|phase\s*iii)'
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    phase_text = match.group(1).lower()
                    if '3' in phase_text or 'iii' in phase_text:
                        trial.phase = "Phase 3"
                    elif '2' in phase_text or 'ii' in phase_text:
                        trial.phase = "Phase 2"

    def _merge_trial_info(
        self,
        existing_trials: List[PivotalTrial],
        new_trial: PivotalTrial,
    ) -> None:
        """Merge info from new_trial into matching existing trial."""
        for trial in existing_trials:
            if trial.nct_id and trial.nct_id == new_trial.nct_id:
                # Merge missing info
                if not trial.trial_name and new_trial.trial_name:
                    trial.trial_name = new_trial.trial_name
                if not trial.phase and new_trial.phase:
                    trial.phase = new_trial.phase
                if not trial.enrollment and new_trial.enrollment:
                    trial.enrollment = new_trial.enrollment
                if not trial.primary_endpoint and new_trial.primary_endpoint:
                    trial.primary_endpoint = new_trial.primary_endpoint
                # Boost confidence if found in multiple sources
                trial.confidence = min(trial.confidence + 0.1, 0.95)
                break

    def _score_and_rank_trials(
        self,
        trials: List[PivotalTrial],
        indication: str,
    ) -> List[PivotalTrial]:
        """
        Score and rank trials by likelihood of being pivotal.

        Scoring factors:
        - Phase 3 > Phase 2
        - Has NCT ID
        - Has trial name
        - Larger enrollment
        - Found in FDA label (high confidence)
        - Has results in CT.gov
        """
        for trial in trials:
            score = trial.confidence

            # Phase boost
            if trial.phase:
                phase_lower = trial.phase.lower()
                if 'phase 3' in phase_lower or 'phase3' in phase_lower:
                    score += 0.15
                elif 'phase 2' in phase_lower or 'phase2' in phase_lower:
                    score += 0.05

            # NCT ID boost
            if trial.nct_id:
                score += 0.1

            # Trial name boost
            if trial.trial_name:
                score += 0.05

            # Enrollment boost (larger = more likely pivotal)
            if trial.enrollment:
                if trial.enrollment > 500:
                    score += 0.1
                elif trial.enrollment > 200:
                    score += 0.05

            # Source boost
            if trial.identification_source == "fda_label":
                score += 0.1

            trial.confidence = min(score, 1.0)

        # Deduplicate by NCT ID (keep highest confidence)
        seen_nct_ids = {}
        deduplicated = []
        for trial in trials:
            nct = trial.nct_id
            if nct:
                if nct not in seen_nct_ids or trial.confidence > seen_nct_ids[nct].confidence:
                    seen_nct_ids[nct] = trial
            else:
                deduplicated.append(trial)

        deduplicated.extend(seen_nct_ids.values())

        # Sort by confidence (highest first)
        deduplicated.sort(key=lambda t: t.confidence, reverse=True)

        return deduplicated

    def get_trial_identifiers(self, trial: PivotalTrial) -> Tuple[Optional[str], Optional[str]]:
        """
        Get the best identifiers for a trial.

        Returns:
            Tuple of (nct_id, trial_name)
        """
        return (trial.nct_id, trial.trial_name)
