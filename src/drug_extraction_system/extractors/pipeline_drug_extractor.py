"""
Pipeline Drug Extractor

Extracts data for pipeline drugs (not yet FDA-approved) from:
- ClinicalTrials.gov (trial data)
- RxNorm (if available)
- MeSH (disease standardization)
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from src.drug_extraction_system.api_clients.clinicaltrials_client import ClinicalTrialsClient
from src.drug_extraction_system.api_clients.rxnorm_client import RxNormClient
from src.drug_extraction_system.api_clients.mesh_client import MeSHClient
from src.drug_extraction_system.utils.drug_key_generator import DrugKeyGenerator
from src.drug_extraction_system.extractors.approved_drug_extractor import ExtractedDrugData
from src.drug_extraction_system.services.drug_type_classifier import DrugTypeClassifier

logger = logging.getLogger(__name__)


class PipelineDrugExtractor:
    """
    Extracts data for pipeline drugs (in clinical trials).

    Data sources:
    - ClinicalTrials.gov: Trial data, phases, conditions
    - RxNorm: Name standardization (if available)
    - MeSH: Disease/condition standardization
    """

    def __init__(
        self,
        clinicaltrials_client: Optional[ClinicalTrialsClient] = None,
        rxnorm_client: Optional[RxNormClient] = None,
        mesh_client: Optional[MeSHClient] = None,
        drug_type_classifier: Optional[DrugTypeClassifier] = None
    ):
        """Initialize extractor with API clients."""
        self.clinicaltrials = clinicaltrials_client or ClinicalTrialsClient()
        self.rxnorm = rxnorm_client or RxNormClient()
        self.mesh = mesh_client or MeSHClient()
        self.drug_type_classifier = drug_type_classifier or DrugTypeClassifier()

    def extract(self, drug_name: str, development_code: Optional[str] = None) -> ExtractedDrugData:
        """
        Extract data for a pipeline drug.

        Args:
            drug_name: Drug name (generic or research code)
            development_code: Optional alternate development code to search

        Returns:
            ExtractedDrugData with all available information
        """
        result = ExtractedDrugData()
        result.approval_status = "investigational"  # Use DB-allowed value
        result.development_code = development_code  # Store for database
        logger.info(f"Extracting data for pipeline drug: '{drug_name}'" +
                   (f" (dev code: {development_code})" if development_code else ""))

        # Step 1: Search ALL industry-sponsored clinical trials
        # Build search terms from drug name and development code
        search_terms = [drug_name]
        if development_code:
            search_terms.append(development_code)
            # Handle hyphen variants
            if "-" in development_code:
                search_terms.append(development_code.replace("-", ""))
            else:
                import re
                match = re.match(r'^([A-Z]+)(\d+)$', development_code, re.IGNORECASE)
                if match:
                    search_terms.append(f"{match.group(1)}-{match.group(2)}")

        trials = self.clinicaltrials.search_trials_all(
            search_terms=search_terms,
            sponsor_class="INDUSTRY",  # Only industry-sponsored
            max_results=1000
        )
        if trials:
            self._populate_from_trials(result, trials, drug_name)
            result.data_sources.append("ClinicalTrials.gov")

        # Step 2: Try RxNorm normalization
        rxnorm_data = self.rxnorm.normalize_drug_name(drug_name)
        if rxnorm_data:
            result.rxcui = rxnorm_data["rxcui"]
            if not result.generic_name:
                result.generic_name = rxnorm_data["normalized_name"]
            result.data_sources.append("RxNorm")

        # Step 3: Set generic name if still missing
        if not result.generic_name:
            result.generic_name = drug_name

        # Step 4: Infer drug type from name
        result.drug_type = self._infer_drug_type(result.generic_name)

        # Step 5: Generate drug key
        result.drug_key = DrugKeyGenerator.generate(
            result.generic_name,
            additional_data=result.cas_number
        )

        # Step 5: Standardize indications with MeSH
        if result.indications:
            result.indications = self._standardize_indications(result.indications)

        # Step 6: Calculate completeness
        result.completeness_score = self._calculate_completeness(result)

        logger.info(f"Extracted '{result.drug_key}' with completeness {result.completeness_score:.2%}")
        return result

    def _populate_from_trials(self, result: ExtractedDrugData, trials: List[Dict], drug_name: str):
        """Populate result from clinical trial data."""
        # Phase mapping to DB-allowed values
        # DB constraint: 'Phase 1', 'Phase 2', 'Phase 3', 'Approved', 'Discontinued', 'Preclinical'
        phase_order = {
            "PHASE4": 5, "PHASE3": 4, "PHASE2": 3, "PHASE1": 2,
            "EARLY_PHASE1": 1, "NA": 0
        }
        phase_to_db = {
            "PHASE4": "Approved",  # Phase 4 means approved (post-marketing)
            "PHASE3": "Phase 3",
            "PHASE2": "Phase 2",
            "PHASE1": "Phase 1",
            "EARLY_PHASE1": "Phase 1",
            "NA": "Preclinical"
        }
        highest_phase = None
        highest_rank = -1

        # Collect conditions and sponsors
        all_conditions = set()
        sponsors = set()
        clinical_trials = []

        for study in trials:
            trial_data = self.clinicaltrials.extract_trial_data(study)

            # Track highest phase
            phase = trial_data.get("trial_phase") or ""
            for p in phase.split(", "):
                p_upper = p.upper().replace(" ", "")
                rank = phase_order.get(p_upper, 0)
                if rank > highest_rank:
                    highest_rank = rank
                    highest_phase = p_upper  # Store normalized phase key

            # Collect conditions
            conditions = trial_data.get("conditions", [])
            all_conditions.update(conditions)

            # Collect sponsors
            sponsor_info = trial_data.get("sponsors", {})
            if sponsor_info.get("lead"):
                sponsors.add(sponsor_info["lead"])

            # Store trial data (use correct field names from clinicaltrials_client)
            clinical_trials.append({
                "nct_id": trial_data.get("nct_id"),
                "title": trial_data.get("trial_title"),  # API returns trial_title
                "phase": trial_data.get("trial_phase"),
                "status": trial_data.get("trial_status"),  # API returns trial_status
                "conditions": conditions,
                "sponsors": sponsor_info,
                "interventions": trial_data.get("interventions", []),  # For dosing extraction
            })

        # Set highest phase (convert to DB-allowed value)
        result.highest_phase = phase_to_db.get(highest_phase, "Preclinical") if highest_phase else None

        # Set manufacturer from most common sponsor
        if sponsors:
            result.manufacturer = list(sponsors)[0]

        # Convert conditions to indications (mark as investigational for pipeline drugs)
        result.indications = [
            {
                "disease_name": cond,
                "source": "ClinicalTrials.gov",
                "approval_status": "investigational"  # Pipeline indications are investigational
            }
            for cond in list(all_conditions)[:10]  # Limit to 10
        ]

        # Store ALL clinical trials (no limit - industry-sponsored are already filtered)
        result.clinical_trials = clinical_trials

        # Store trial count in metadata
        result.data_sources.append(f"{len(clinical_trials)} industry-sponsored trials found")

    def _standardize_indications(self, indications: List[Dict]) -> List[Dict]:
        """Standardize indication names using MeSH."""
        standardized = []
        for ind in indications:
            disease_name = ind.get("disease_name")
            if disease_name:
                mesh_result = self.mesh.standardize_disease_name(disease_name)
                if mesh_result:
                    ind["mesh_id"] = mesh_result["mesh_id"]
                    ind["standardized_name"] = mesh_result["standardized_name"]
            standardized.append(ind)
        return standardized

    def _calculate_completeness(self, data: ExtractedDrugData) -> float:
        """Calculate data completeness score for pipeline drugs."""
        scores = {
            "core": 0.0,
            "indications": 0.0,
            "trials": 0.0,
            "identifiers": 0.0,
        }

        # Core fields (30%)
        core_fields = ["generic_name", "manufacturer", "highest_phase"]
        core_filled = sum(1 for f in core_fields if getattr(data, f))
        scores["core"] = core_filled / len(core_fields)

        # Indications (25%)
        scores["indications"] = min(1.0, len(data.indications) / 3)  # 3+ indications = 100%

        # Trials info (25%) - based on having trial data
        has_trials = "ClinicalTrials.gov" in data.data_sources
        scores["trials"] = 1.0 if has_trials else 0.0

        # Identifiers (20%)
        id_fields = ["rxcui", "unii", "chembl_id", "cas_number"]
        id_filled = sum(1 for f in id_fields if getattr(data, f))
        scores["identifiers"] = id_filled / len(id_fields)

        # Weighted average
        total = (scores["core"] * 0.30 + scores["indications"] * 0.25 +
                 scores["trials"] * 0.25 + scores["identifiers"] * 0.20)

        return round(total, 4)

    def extract_trials(self, drug_name: str, development_code: Optional[str] = None) -> List[Dict]:
        """
        Extract detailed trial data for a drug - industry-sponsored only.

        Args:
            drug_name: Drug name to search
            development_code: Optional development code to also search

        Returns:
            List of extracted trial data dictionaries (industry-sponsored only)
        """
        search_terms = [drug_name]
        if development_code:
            search_terms.append(development_code)

        trials = self.clinicaltrials.search_trials_all(
            search_terms=search_terms,
            sponsor_class="INDUSTRY",
            max_results=1000
        )
        if not trials:
            return []

        extracted = []
        for study in trials:
            trial_data = self.clinicaltrials.extract_trial_data(study)
            extracted.append(trial_data)

        return extracted

    def _infer_drug_type(self, drug_name: str, mechanism: str = None) -> Optional[str]:
        """
        Infer drug type using the DrugTypeClassifier.

        Uses a two-tier approach:
        1. INN suffix pattern matching (fast, no API calls)
        2. Claude API classification (fallback for unknown patterns)

        Args:
            drug_name: Drug name to analyze
            mechanism: Optional mechanism of action for context

        Returns:
            Inferred drug type or None
        """
        return self.drug_type_classifier.classify(drug_name, mechanism)