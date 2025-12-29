"""
Approved Drug Extractor

Extracts comprehensive data for FDA-approved drugs from:
- DailyMed (primary source for MOA, indications, dosing)
- OpenFDA (labels, NDC, fallback)
- RxNorm (standardization)
- MeSH (disease standardization)
- ClinicalTrials.gov (completed trials)
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
from src.drug_extraction_system.api_clients.rxnorm_client import RxNormClient
from src.drug_extraction_system.api_clients.mesh_client import MeSHClient
from src.drug_extraction_system.api_clients.clinicaltrials_client import ClinicalTrialsClient
from src.drug_extraction_system.utils.drug_key_generator import DrugKeyGenerator
from src.drug_extraction_system.services.drug_type_classifier import DrugTypeClassifier
from src.tools.dailymed import DailyMedAPI

logger = logging.getLogger(__name__)


@dataclass
class ExtractedDrugData:
    """Container for extracted drug data."""
    # Core identifiers
    drug_key: str = ""
    generic_name: str = ""
    brand_name: Optional[str] = None
    manufacturer: Optional[str] = None
    development_code: Optional[str] = None  # e.g., LNP023, BMS-986165

    # External identifiers
    rxcui: Optional[str] = None
    unii: Optional[str] = None
    chembl_id: Optional[str] = None
    cas_number: Optional[str] = None
    inchi_key: Optional[str] = None

    # Drug properties
    drug_type: Optional[str] = None
    mechanism_of_action: Optional[str] = None
    approval_status: str = "approved"
    highest_phase: str = "Approved"
    dailymed_setid: Optional[str] = None
    first_approval_date: Optional[str] = None

    # Related data
    indications: List[Dict] = field(default_factory=list)
    dosing_regimens: List[Dict] = field(default_factory=list)
    clinical_trials: List[Dict] = field(default_factory=list)
    formulations: List[Dict] = field(default_factory=list)
    warnings: Optional[str] = None
    boxed_warning: Optional[str] = None
    contraindications: Optional[str] = None

    # Metadata
    data_sources: List[str] = field(default_factory=list)
    completeness_score: float = 0.0


class ApprovedDrugExtractor:
    """
    Extracts data for FDA-approved drugs.

    Data sources (priority order):
    - DailyMed: Primary source for MOA, indications, dosing
    - OpenFDA: Labels, NDC, approval info (fallback)
    - RxNorm: Name standardization, RxCUI
    - MeSH: Disease/indication standardization
    - ClinicalTrials.gov: Completed clinical trials
    """

    def __init__(
        self,
        openfda_client: Optional[OpenFDAClient] = None,
        rxnorm_client: Optional[RxNormClient] = None,
        mesh_client: Optional[MeSHClient] = None,
        clinicaltrials_client: Optional[ClinicalTrialsClient] = None,
        dailymed_client: Optional[DailyMedAPI] = None,
        drug_type_classifier: Optional[DrugTypeClassifier] = None
    ):
        """Initialize extractor with API clients."""
        self.openfda = openfda_client or OpenFDAClient()
        self.rxnorm = rxnorm_client or RxNormClient()
        self.mesh = mesh_client or MeSHClient()
        self.clinicaltrials = clinicaltrials_client or ClinicalTrialsClient()
        self.dailymed = dailymed_client or DailyMedAPI()
        self.drug_type_classifier = drug_type_classifier or DrugTypeClassifier()

    def extract(self, drug_name: str, development_code: Optional[str] = None) -> ExtractedDrugData:
        """
        Extract comprehensive data for an approved drug.

        Data source priority:
        1. DailyMed (primary for MOA, indications, dosing)
        2. OpenFDA (fallback and additional data)
        3. RxNorm (standardization)
        4. ClinicalTrials.gov (trial data)

        Args:
            drug_name: Drug name (brand or generic)
            development_code: Optional development code (e.g., "LNP023") for trial search

        Returns:
            ExtractedDrugData with all available information
        """
        result = ExtractedDrugData()
        result.development_code = development_code  # Store for database
        logger.info(f"Extracting data for approved drug: '{drug_name}'" +
                   (f" (dev code: {development_code})" if development_code else ""))

        # Step 1: Get OpenFDA label data (PRIMARY source for indications and dosing)
        labels = self.openfda.search_drug_labels(drug_name, limit=1)
        openfda_data = {}
        if labels:
            label_data = self.openfda.extract_drug_data(labels[0])
            openfda_data = labels[0].get("openfda", {})
            self._populate_from_openfda(result, label_data, is_primary=True)
            result.data_sources.append("openFDA")
            logger.info(f"✓ OpenFDA: Found Indications={bool(label_data.get('indications_and_usage'))}, "
                       f"Dosing={bool(label_data.get('dosage_and_administration'))}")

        # Step 2: Get DailyMed data (PRIMARY source for MOA, fallback for other fields)
        dailymed_data = self._extract_from_dailymed(drug_name)
        if dailymed_data:
            self._populate_from_dailymed(result, dailymed_data, is_primary=False)
            result.data_sources.append("DailyMed")
            logger.info(f"✓ DailyMed: Found MOA={bool(result.mechanism_of_action)}")

        # Step 3: Get approval info (first_approval_date)
        approval_info = self.openfda.get_approval_info(drug_name)
        if approval_info:
            result.first_approval_date = approval_info.get("first_approval_date")
            if not result.manufacturer and approval_info.get("sponsor_name"):
                result.manufacturer = approval_info["sponsor_name"]

        # Step 4: Infer drug type using DrugTypeClassifier (with Claude fallback)
        # Get the generic name for classification (more reliable than brand name)
        classify_name = result.generic_name or drug_name
        result.drug_type = self.drug_type_classifier.classify(
            classify_name,
            mechanism_of_action=result.mechanism_of_action
        )

        # Step 5: Normalize with RxNorm
        rxnorm_data = self.rxnorm.normalize_drug_name(drug_name)
        if rxnorm_data:
            if not result.rxcui:
                result.rxcui = rxnorm_data["rxcui"]
            if not result.generic_name:
                result.generic_name = rxnorm_data["normalized_name"]
            result.data_sources.append("RxNorm")

        # Step 6: Generate drug key
        if result.generic_name:
            result.drug_key = DrugKeyGenerator.generate(
                result.generic_name,
                additional_data=result.cas_number
            )
        else:
            result.generic_name = drug_name
            result.drug_key = DrugKeyGenerator.generate(drug_name)

        # Step 7: Fetch ALL industry-sponsored clinical trials
        clinical_trials = self._fetch_clinical_trials(
            drug_name=result.generic_name or drug_name,
            rxcui=result.rxcui,
            development_code=development_code,
            brand_name=result.brand_name
        )
        if clinical_trials:
            result.clinical_trials = clinical_trials
            result.data_sources.append("ClinicalTrials.gov")
            logger.info(f"Found {len(clinical_trials)} industry-sponsored clinical trials")

        # Step 8: Standardize indications with MeSH
        if result.indications:
            result.indications = self._standardize_indications(result.indications)

        # Step 9: Calculate completeness
        result.completeness_score = self._calculate_completeness(result)

        logger.info(f"Extracted '{result.drug_key}' with completeness {result.completeness_score:.2%}")
        return result

    def _extract_from_dailymed(self, drug_name: str) -> Optional[Dict]:
        """
        Extract data from DailyMed API.

        Returns:
            Dict with mechanism_of_action, indications, dosing, manufacturer, etc.
            None if drug not found
        """
        try:
            # Get drug info (this internally searches for SetID and parses label)
            drug_info = self.dailymed.get_drug_info(drug_name)
            if not drug_info:
                logger.info(f"DailyMed: Drug '{drug_name}' not found")
                return None

            logger.info(f"DailyMed: Successfully extracted data for '{drug_name}'")
            return drug_info

        except Exception as e:
            logger.warning(f"DailyMed extraction failed for '{drug_name}': {e}")
            return None

    def _populate_from_dailymed(self, result: ExtractedDrugData, dailymed_data: Dict, is_primary: bool = True):
        """
        Populate result from DailyMed data.

        Args:
            result: ExtractedDrugData to populate
            dailymed_data: DailyMed data
            is_primary: If True, DailyMed is primary source (populate all fields)
                       If False, DailyMed is fallback (only populate if empty)

        Note: As of current architecture, DailyMed is used as FALLBACK (is_primary=False)
              OpenFDA is the primary source for label data.
        """
        # Core fields - only populate if empty (fallback behavior)
        if not result.mechanism_of_action and dailymed_data.get("mechanism_of_action"):
            result.mechanism_of_action = dailymed_data["mechanism_of_action"]

        if not result.manufacturer and dailymed_data.get("manufacturer"):
            result.manufacturer = dailymed_data["manufacturer"]

        # SetID - always populate (DailyMed-specific field)
        if not result.dailymed_setid and dailymed_data.get("setid"):
            result.dailymed_setid = dailymed_data["setid"]

        # Indications - only populate if primary source (or if empty and fallback)
        if is_primary and dailymed_data.get("indications"):
            for indication_text in dailymed_data["indications"]:
                # Skip empty or whitespace-only indications
                if indication_text and indication_text.strip():
                    result.indications.append({
                        "raw_text": indication_text,
                        "source": "DailyMed"
                    })
        elif not is_primary and not result.indications and dailymed_data.get("indications"):
            # Fallback: populate if OpenFDA didn't provide indications
            for indication_text in dailymed_data["indications"]:
                if indication_text and indication_text.strip():
                    result.indications.append({
                        "raw_text": indication_text,
                        "source": "DailyMed"
                    })

        # Route of administration - always populate if available
        if dailymed_data.get("route"):
            # Store route info for later use in dosing
            result.formulations.append({
                "route": dailymed_data["route"],
                "source": "DailyMed"
            })

    def _populate_from_openfda(self, result: ExtractedDrugData, label_data: Dict, is_primary: bool = False):
        """
        Populate result from OpenFDA label data.

        Args:
            result: ExtractedDrugData to populate
            label_data: OpenFDA label data
            is_primary: If True, OpenFDA is primary source (always populate all fields)
                       If False, OpenFDA is fallback (only populate if empty)
        """
        # Core identifiers - always populate if empty
        if not result.generic_name:
            result.generic_name = label_data.get("generic_name") or ""
        if not result.brand_name:
            result.brand_name = label_data.get("brand_name")
        if not result.manufacturer:
            result.manufacturer = label_data.get("manufacturer")
        if not result.rxcui:
            result.rxcui = label_data.get("rxcui")
        if not result.unii:
            result.unii = label_data.get("unii")
        if not result.dailymed_setid:
            result.dailymed_setid = label_data.get("set_id")

        # Label content fields - populate based on is_primary
        # If primary: always populate (OpenFDA is authoritative)
        # If fallback: only populate if empty

        if is_primary or not result.mechanism_of_action:
            moa = label_data.get("mechanism_of_action")
            if moa:
                result.mechanism_of_action = moa

        if is_primary or not result.warnings:
            warnings = label_data.get("warnings")
            if warnings:
                result.warnings = warnings

        if is_primary or not result.boxed_warning:
            boxed = label_data.get("boxed_warning")
            if boxed:
                result.boxed_warning = boxed

        if is_primary or not result.contraindications:
            contra = label_data.get("contraindications")
            if contra:
                result.contraindications = contra

        # Indications: Always populate if primary source, otherwise only if empty
        if is_primary or not result.indications:
            indications_text = label_data.get("indications_and_usage")
            if indications_text:
                result.indications = [{"raw_text": indications_text, "source": "openFDA"}]

        # Dosing: Always populate if primary source, otherwise only if empty
        if is_primary or not result.dosing_regimens:
            dosing_text = label_data.get("dosage_and_administration")
            if dosing_text:
                result.dosing_regimens = [{"raw_text": dosing_text, "source": "openFDA"}]

    def _fetch_clinical_trials(
        self,
        drug_name: str,
        rxcui: Optional[str] = None,
        development_code: Optional[str] = None,
        brand_name: Optional[str] = None
    ) -> List[Dict]:
        """
        Fetch ALL industry-sponsored clinical trials for a drug.

        Searches by generic name, brand name, and development code (if provided).
        Only returns trials sponsored by pharmaceutical industry.

        Args:
            drug_name: Generic name of the drug (e.g., "iptacopan")
            rxcui: Optional RxNorm CUI (not currently used)
            development_code: Optional development code (e.g., "LNP023", "LNP-023")
            brand_name: Optional brand name (e.g., "Kadcyla", "Fabhalta")

        Returns:
            List of trial dictionaries with NCT ID, phase, status, conditions, sponsors
        """
        try:
            # Build search terms list - generic name, brand name, and development code
            search_terms = [drug_name]

            # Handle combination products (e.g., "DRUG A AND DRUG B")
            # Extract main active ingredient for trial search
            if " AND " in drug_name.upper():
                # Split on " AND " and take the first component (main active ingredient)
                components = drug_name.split(" AND ", 1)
                main_component = components[0].strip()
                if main_component and main_component.lower() != drug_name.lower():
                    search_terms.append(main_component)
                    logger.info(f"Detected combination product, adding main component: {main_component}")

            # Add brand name if provided and different from generic name
            if brand_name and brand_name.lower() != drug_name.lower():
                search_terms.append(brand_name)
                # Also handle combination brand names (e.g., "BRAND X / BRAND Y")
                if "/" in brand_name:
                    brand_components = brand_name.split("/", 1)
                    main_brand = brand_components[0].strip()
                    if main_brand and main_brand.lower() != brand_name.lower():
                        search_terms.append(main_brand)

            if development_code:
                search_terms.append(development_code)
                # Also try without hyphen if it has one, or with hyphen if it doesn't
                if "-" in development_code:
                    search_terms.append(development_code.replace("-", ""))
                else:
                    # Try to insert hyphen at common positions (letters-numbers pattern)
                    import re
                    match = re.match(r'^([A-Z]+)(\d+)$', development_code, re.IGNORECASE)
                    if match:
                        search_terms.append(f"{match.group(1)}-{match.group(2)}")

            logger.info(f"Searching trials with terms: {search_terms}")

            # Fetch ALL industry-sponsored trials (paginated)
            trials = self.clinicaltrials.search_trials_all(
                search_terms=search_terms,
                sponsor_class="INDUSTRY",  # Only industry-sponsored trials
                max_results=1000  # Get up to 1000 trials
            )

            if not trials:
                return []

            # Extract structured data from all trials (no status filtering)
            extracted_trials = []
            for study in trials:
                trial_data = self.clinicaltrials.extract_trial_data(study)
                extracted_trials.append({
                    "nct_id": trial_data.get("nct_id"),
                    "title": trial_data.get("trial_title"),
                    "phase": trial_data.get("trial_phase"),
                    "status": trial_data.get("trial_status"),
                    "conditions": trial_data.get("conditions", []),
                    "sponsors": trial_data.get("sponsors", {}),
                    "start_date": trial_data.get("start_date"),
                    "completion_date": trial_data.get("completion_date"),
                    "enrollment": trial_data.get("enrollment"),
                })

            logger.info(f"Extracted {len(extracted_trials)} industry-sponsored trials for {drug_name}")
            return extracted_trials

        except Exception as e:
            logger.warning(f"Failed to fetch trials for {drug_name}: {e}")
            return []

    def _standardize_indications(self, indications: List[Dict]) -> List[Dict]:
        """Standardize indication names using MeSH."""
        standardized = []
        for ind in indications:
            if "disease_name" in ind:
                mesh_result = self.mesh.standardize_disease_name(ind["disease_name"])
                if mesh_result:
                    ind["mesh_id"] = mesh_result["mesh_id"]
                    ind["standardized_name"] = mesh_result["standardized_name"]
            standardized.append(ind)
        return standardized

    def _calculate_completeness(self, data: ExtractedDrugData) -> float:
        """Calculate data completeness score."""
        scores = {
            "core": 0.0,
            "indications": 0.0,
            "dosing": 0.0,
            "identifiers": 0.0,
        }

        # Core fields (30%)
        core_fields = ["generic_name", "brand_name", "manufacturer", "mechanism_of_action"]
        core_filled = sum(1 for f in core_fields if getattr(data, f))
        scores["core"] = core_filled / len(core_fields)

        # Indications (25%)
        scores["indications"] = 1.0 if data.indications else 0.0

        # Dosing (25%)
        scores["dosing"] = 1.0 if data.dosing_regimens else 0.0

        # Identifiers (20%)
        id_fields = ["rxcui", "unii", "chembl_id", "cas_number"]
        id_filled = sum(1 for f in id_fields if getattr(data, f))
        scores["identifiers"] = id_filled / len(id_fields)

        # Weighted average
        total = (scores["core"] * 0.30 + scores["indications"] * 0.25 +
                 scores["dosing"] * 0.25 + scores["identifiers"] * 0.20)

        return round(total, 4)

