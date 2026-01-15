"""
EfficacyComparisonAgent

Main orchestrator for the efficacy comparison pipeline.
Coordinates all services to generate comprehensive efficacy comparison data.
"""

import logging
from datetime import datetime
from typing import Callable, Dict, List, Optional

from src.efficacy_comparison.models import (
    ApprovedDrug,
    DrugEfficacyProfile,
    EfficacyComparisonResult,
    PivotalTrial,
    TrialExtraction,
)
from src.efficacy_comparison.repository import EfficacyComparisonRepository
from src.efficacy_comparison.services import (
    ComprehensiveExtractor,
    DataSourceResolver,
    InnovativeDrugFinder,
    PivotalTrialIdentifier,
    PrimaryPaperIdentifier,
)

logger = logging.getLogger(__name__)


# Expected endpoints by disease (common endpoints to look for)
DISEASE_EXPECTED_ENDPOINTS = {
    "atopic dermatitis": [
        "IGA 0/1", "IGA response", "EASI-50", "EASI-75", "EASI-90",
        "Pruritus NRS", "DLQI", "POEM", "SCORAD", "BSA",
    ],
    "psoriasis": [
        "PASI-50", "PASI-75", "PASI-90", "PASI-100", "IGA 0/1",
        "BSA", "DLQI", "Nail Psoriasis",
    ],
    "rheumatoid arthritis": [
        "ACR20", "ACR50", "ACR70", "DAS28-CRP", "DAS28-ESR",
        "HAQ-DI", "CDAI", "SDAI", "Boolean remission",
    ],
    "systemic lupus erythematosus": [
        "SRI-4", "SRI-5", "SRI-6", "BICLA", "SLEDAI-2K",
        "Flare rate", "OCS reduction", "CLASI", "Renal response",
    ],
    "ulcerative colitis": [
        "Clinical remission", "Clinical response", "Endoscopic improvement",
        "Mayo score", "Partial Mayo score", "Mucosal healing",
    ],
    "crohn's disease": [
        "Clinical remission", "Clinical response", "CDAI",
        "Endoscopic response", "Mucosal healing", "Fistula closure",
    ],
}


class EfficacyComparisonAgent:
    """
    Main orchestrator for efficacy comparison analysis.

    Pipeline:
    1. Find innovative drugs for indication
    2. For each drug, identify pivotal trials
    3. For each trial, find primary results papers
    4. Resolve best data source
    5. Extract comprehensive efficacy data
    6. Store results

    Usage:
        agent = EfficacyComparisonAgent()
        result = await agent.run_comparison("atopic dermatitis")
    """

    def __init__(
        self,
        drug_finder: Optional[InnovativeDrugFinder] = None,
        trial_identifier: Optional[PivotalTrialIdentifier] = None,
        paper_identifier: Optional[PrimaryPaperIdentifier] = None,
        data_resolver: Optional[DataSourceResolver] = None,
        extractor: Optional[ComprehensiveExtractor] = None,
        repository: Optional[EfficacyComparisonRepository] = None,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        save_to_db: bool = True,
        skip_existing: bool = True,
    ):
        """
        Initialize the agent with optional service overrides.

        Args:
            drug_finder: Optional InnovativeDrugFinder instance
            trial_identifier: Optional PivotalTrialIdentifier instance
            paper_identifier: Optional PrimaryPaperIdentifier instance
            data_resolver: Optional DataSourceResolver instance
            extractor: Optional ComprehensiveExtractor instance
            repository: Optional EfficacyComparisonRepository for database persistence
            progress_callback: Optional callback for progress updates (message, progress 0-1)
            save_to_db: If True, save each trial extraction to database incrementally
            skip_existing: If True, skip trials that already exist in the database
        """
        self.drug_finder = drug_finder or InnovativeDrugFinder()
        self.trial_identifier = trial_identifier or PivotalTrialIdentifier()
        self.paper_identifier = paper_identifier or PrimaryPaperIdentifier()
        self.data_resolver = data_resolver or DataSourceResolver()
        self.extractor = extractor or ComprehensiveExtractor()
        self.repository = repository or EfficacyComparisonRepository()
        self.progress_callback = progress_callback
        self.save_to_db = save_to_db
        self.skip_existing = skip_existing

    def _report_progress(self, message: str, progress: float):
        """Report progress if callback is set."""
        logger.info(f"[{progress:.0%}] {message}")
        if self.progress_callback:
            self.progress_callback(message, progress)

    async def run_comparison(
        self,
        indication: str,
        selected_drug_names: Optional[List[str]] = None,
        max_drugs: int = 20,
        max_trials_per_drug: int = 4,
    ) -> EfficacyComparisonResult:
        """
        Run full efficacy comparison for an indication.

        Args:
            indication: Disease/condition name (e.g., "atopic dermatitis")
            selected_drug_names: Optional list of specific drugs to analyze (None = all)
            max_drugs: Maximum number of drugs to process
            max_trials_per_drug: Maximum trials per drug

        Returns:
            EfficacyComparisonResult with all extracted data
        """
        self._report_progress(f"Starting efficacy comparison for: {indication}", 0.0)

        # Get expected endpoints for this disease
        expected_endpoints = self._get_expected_endpoints(indication)

        # Step 1: Find innovative drugs
        self._report_progress("Finding innovative drugs...", 0.05)
        all_drugs = await self.drug_finder.find_innovative_drugs(indication)

        if not all_drugs:
            logger.warning(f"No innovative drugs found for: {indication}")
            return EfficacyComparisonResult(
                indication_name=indication,
                drug_profiles=[],
                analysis_timestamp=datetime.now(),
                analysis_notes="No innovative drugs found",
            )

        # Filter to selected drugs if specified
        if selected_drug_names:
            selected_lower = [n.lower() for n in selected_drug_names]
            drugs = [d for d in all_drugs
                    if d.drug_name.lower() in selected_lower or
                       d.generic_name.lower() in selected_lower]
        else:
            drugs = all_drugs[:max_drugs]

        logger.info(f"Processing {len(drugs)} drugs for {indication}")

        # Process each drug
        drug_profiles = []
        total_drugs = len(drugs)

        for i, drug in enumerate(drugs):
            drug_progress_base = 0.1 + (0.85 * i / total_drugs)

            try:
                profile = await self._process_drug(
                    drug=drug,
                    indication=indication,
                    expected_endpoints=expected_endpoints,
                    max_trials=max_trials_per_drug,
                    progress_base=drug_progress_base,
                    progress_range=0.85 / total_drugs,
                )
                drug_profiles.append(profile)

            except Exception as e:
                logger.error(f"Error processing drug {drug.drug_name}: {e}")
                # Create empty profile to track the failure
                drug_profiles.append(DrugEfficacyProfile(
                    drug=drug,
                    indication_name=indication,
                    pivotal_trials=[],
                    extractions=[],
                ))

        # Calculate totals
        total_trials = sum(len(p.pivotal_trials) for p in drug_profiles)
        total_endpoints = sum(
            sum(len(e.endpoints) for e in p.extractions)
            for p in drug_profiles
        )

        self._report_progress("Efficacy comparison complete!", 1.0)

        return EfficacyComparisonResult(
            indication_name=indication,
            drug_profiles=drug_profiles,
            total_drugs=len(drug_profiles),
            total_trials=total_trials,
            total_endpoints=total_endpoints,
            analysis_timestamp=datetime.now(),
        )

    async def _process_drug(
        self,
        drug: ApprovedDrug,
        indication: str,
        expected_endpoints: List[str],
        max_trials: int,
        progress_base: float,
        progress_range: float,
    ) -> DrugEfficacyProfile:
        """
        Process a single drug: find trials, papers, and extract data.
        """
        self._report_progress(f"Processing {drug.drug_name}...", progress_base)

        # Step 2: Identify pivotal trials
        self._report_progress(
            f"Identifying pivotal trials for {drug.drug_name}...",
            progress_base + progress_range * 0.1
        )

        pivotal_trials = await self.trial_identifier.identify_pivotal_trials(
            drug=drug,
            indication=indication,
            max_trials=max_trials,
        )

        if not pivotal_trials:
            logger.warning(f"No pivotal trials found for {drug.drug_name}")
            return DrugEfficacyProfile(
                drug=drug,
                indication_name=indication,
                pivotal_trials=[],
                extractions=[],
            )

        logger.info(f"Found {len(pivotal_trials)} pivotal trials for {drug.drug_name}")

        # Process each trial
        extractions = []
        total_trials = len(pivotal_trials)

        for j, trial in enumerate(pivotal_trials):
            trial_progress = progress_base + progress_range * (0.2 + 0.8 * j / total_trials)

            try:
                extraction = await self._process_trial(
                    trial=trial,
                    drug=drug,
                    indication=indication,
                    expected_endpoints=expected_endpoints,
                    progress=trial_progress,
                )
                if extraction:
                    extractions.append(extraction)

            except Exception as e:
                logger.error(
                    f"Error processing trial {trial.trial_name or trial.nct_id}: {e}"
                )

        return DrugEfficacyProfile(
            drug=drug,
            indication_name=indication,
            pivotal_trials=pivotal_trials,
            extractions=extractions,
            extraction_timestamp=datetime.now(),
        )

    async def _process_trial(
        self,
        trial: PivotalTrial,
        drug: ApprovedDrug,
        indication: str,
        expected_endpoints: List[str],
        progress: float,
    ) -> Optional[TrialExtraction]:
        """
        Process a single trial: find paper, resolve source, extract data, save to DB.
        """
        trial_id = trial.trial_name or trial.nct_id
        self._report_progress(f"Processing trial {trial_id}...", progress)

        # Check if trial already exists in database (skip if requested)
        if self.skip_existing and trial.nct_id:
            try:
                exists = await self.repository.trial_exists(trial.nct_id, drug.drug_name)
                if exists:
                    logger.info(f"Skipping {trial_id} - already exists in database")
                    self._report_progress(f"Skipping {trial_id} (already extracted)...", progress)
                    return None
            except Exception as e:
                logger.warning(f"Could not check if trial exists: {e}")

        # Step 3: Find primary papers
        papers = await self.paper_identifier.find_primary_papers(
            trial=trial,
            drug=drug,
            max_papers=2,
        )

        # Get the best paper (first one that passed screening)
        paper = papers[0] if papers else None

        # Step 4: Resolve data source
        self._report_progress(
            f"Resolving data source for {trial_id}...",
            progress + 0.02
        )

        data_source = await self.data_resolver.resolve_data_source(
            paper=paper,
            trial=trial,
            drug=drug,
        )

        logger.info(
            f"Using {data_source.source_type} for {trial_id} "
            f"(completeness: {data_source.completeness})"
        )

        # Step 5: Extract data
        self._report_progress(
            f"Extracting data from {trial_id}...",
            progress + 0.05
        )

        extraction = await self.extractor.extract_trial_data(
            data_source=data_source,
            trial=trial,
            drug=drug,
            indication=indication,
            expected_endpoints=expected_endpoints,
        )

        logger.info(
            f"Extracted {len(extraction.endpoints)} endpoints from {trial_id}"
        )

        # Step 6: Save to database (incremental save)
        if self.save_to_db and extraction and len(extraction.endpoints) > 0:
            try:
                db_trial_id = await self.repository.save_trial_extraction(
                    drug=drug,
                    trial=trial,
                    extraction=extraction,
                    indication=indication,
                )
                logger.info(f"Saved trial {trial_id} to database (trial_id={db_trial_id})")
            except Exception as e:
                logger.error(f"Failed to save trial {trial_id} to database: {e}")
                # Continue even if save fails - data is still in memory

        return extraction

    def _get_expected_endpoints(self, indication: str) -> List[str]:
        """Get expected endpoints for a disease."""
        indication_lower = indication.lower()

        for disease, endpoints in DISEASE_EXPECTED_ENDPOINTS.items():
            if disease in indication_lower or indication_lower in disease:
                return endpoints

        # Default endpoints
        return ["Primary endpoint", "Key secondary endpoint"]

    async def run_comparison_for_drug(
        self,
        drug_name: str,
        indication: str,
        max_trials: int = 4,
    ) -> DrugEfficacyProfile:
        """
        Run efficacy extraction for a single drug.

        Useful for targeted extraction when you already know the drug.

        Args:
            drug_name: Drug name (brand or generic)
            indication: Disease/condition name
            max_trials: Maximum trials to process

        Returns:
            DrugEfficacyProfile with extracted data
        """
        self._report_progress(f"Processing {drug_name} for {indication}...", 0.0)

        # Find the drug
        all_drugs = await self.drug_finder.find_innovative_drugs(indication)

        drug = None
        for d in all_drugs:
            if (d.drug_name.lower() == drug_name.lower() or
                d.generic_name.lower() == drug_name.lower()):
                drug = d
                break

        if not drug:
            # Create a minimal drug object
            drug = ApprovedDrug(
                drug_name=drug_name,
                generic_name=drug_name,
            )

        expected_endpoints = self._get_expected_endpoints(indication)

        return await self._process_drug(
            drug=drug,
            indication=indication,
            expected_endpoints=expected_endpoints,
            max_trials=max_trials,
            progress_base=0.1,
            progress_range=0.9,
        )

    async def close(self):
        """Clean up resources."""
        await self.data_resolver.close()
        if self.repository:
            await self.repository.close()
