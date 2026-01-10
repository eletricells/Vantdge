"""
Extract efficacy data from ClinicalTrials.gov.

Fallback data source when publication data is insufficient.
"""

import logging
import re
from typing import List, Optional, Dict, Any

from src.tools.clinicaltrials import ClinicalTrialsAPI
from ..models import (
    EfficacyDataPoint, DataSource, ReviewStatus, ApprovedDrug, DiseaseMatch
)

logger = logging.getLogger(__name__)


def clean_generic_name(name: str) -> str:
    """
    Clean generic name for better search results.

    Removes suffixes like -FNIA, -XXXX (antibody designations).
    """
    if not name:
        return name
    # Remove antibody suffix patterns like -FNIA, -ADCC, -XXXX
    cleaned = re.sub(r'-[A-Z]{3,4}$', '', name, flags=re.IGNORECASE)
    return cleaned.strip()


class ClinicalTrialsEfficacyExtractor:
    """
    Extract efficacy data from ClinicalTrials.gov trial results.

    This is a fallback source when publication data is insufficient.
    Note: ClinicalTrials.gov results data is often limited compared to publications.
    """

    def __init__(self, api: Optional[ClinicalTrialsAPI] = None):
        """
        Initialize the extractor.

        Args:
            api: Optional ClinicalTrialsAPI instance
        """
        self.api = api or ClinicalTrialsAPI()

    def search_completed_trials(
        self,
        drug: ApprovedDrug,
        disease: DiseaseMatch,
        max_results: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search for completed Phase 2/3 trials with results.

        Args:
            drug: Approved drug to search for
            disease: Disease context
            max_results: Maximum number of trials to return

        Returns:
            List of trial dictionaries
        """
        trials = []
        seen_nct_ids = set()

        # Clean the generic name (remove -FNIA, -XXXX suffixes)
        clean_name = clean_generic_name(drug.generic_name)
        logger.info(f"Searching ClinicalTrials.gov for '{clean_name}' (original: '{drug.generic_name}')")

        # Search with cleaned drug generic name
        try:
            results = self.api.search_trials(
                drug_name=clean_name,
                condition=disease.standard_name,
                max_results=max_results,
                use_fuzzy_search=True
            )

            for trial in results:
                nct_id = trial.get('nct_id')
                if nct_id and nct_id not in seen_nct_ids:
                    seen_nct_ids.add(nct_id)
                    trials.append(trial)
        except Exception as e:
            logger.warning(f"CT.gov search failed for {clean_name}: {e}")

        # Also search with brand name if available
        if drug.brand_name:
            try:
                results = self.api.search_trials(
                    drug_name=drug.brand_name,
                    condition=disease.standard_name,
                    max_results=max_results // 2,
                    use_fuzzy_search=True
                )

                for trial in results:
                    nct_id = trial.get('nct_id')
                    if nct_id and nct_id not in seen_nct_ids:
                        seen_nct_ids.add(nct_id)
                        trials.append(trial)
            except Exception as e:
                logger.debug(f"CT.gov brand search failed: {e}")

        # Filter to completed Phase 2/3 trials
        completed_trials = []
        for trial in trials:
            status = trial.get('status', '').lower()
            phase = trial.get('phase', '')

            if status in ['completed', 'terminated'] and (
                'Phase 2' in phase or 'Phase 3' in phase or
                'phase 2' in phase.lower() or 'phase 3' in phase.lower()
            ):
                completed_trials.append(trial)

        logger.info(
            f"Found {len(completed_trials)} completed Phase 2/3 trials for "
            f"{drug.generic_name} in {disease.standard_name}"
        )
        return completed_trials[:max_results]

    def extract_from_trials(
        self,
        trials: List[Dict[str, Any]],
        drug: ApprovedDrug,
        disease: DiseaseMatch,
        expected_endpoints: List[str]
    ) -> List[EfficacyDataPoint]:
        """
        Extract efficacy data from trial results.

        Note: ClinicalTrials.gov API v2 provides outcome metadata but
        often lacks actual numeric results. Data points are marked for review.

        Args:
            trials: List of trial dictionaries
            drug: Drug context
            disease: Disease context
            expected_endpoints: Expected endpoint names

        Returns:
            List of EfficacyDataPoint objects
        """
        all_data_points = []

        for trial in trials:
            nct_id = trial.get('nct_id')
            if not nct_id:
                continue

            try:
                data_points = self._extract_from_single_trial(
                    trial, drug, disease, expected_endpoints
                )
                all_data_points.extend(data_points)
            except Exception as e:
                logger.warning(f"Failed to extract from trial {nct_id}: {e}")
                continue

        return all_data_points

    def _extract_from_single_trial(
        self,
        trial: Dict[str, Any],
        drug: ApprovedDrug,
        disease: DiseaseMatch,
        expected_endpoints: List[str]
    ) -> List[EfficacyDataPoint]:
        """
        Extract efficacy data from a single trial.
        """
        nct_id = trial.get('nct_id', '')
        data_points = []

        # Get detailed trial info
        try:
            details = self.api.get_parsed_trial_details(nct_id)
        except Exception as e:
            logger.debug(f"Could not get trial details for {nct_id}: {e}")
            details = trial  # Use basic info

        # Extract primary outcomes
        primary_outcomes = details.get('primary_outcomes', [])
        if not primary_outcomes and 'primaryOutcome' in str(trial):
            # Try alternative structure
            primary_outcomes = trial.get('primaryOutcome', [])

        for outcome in primary_outcomes:
            measure = outcome.get('measure', '') if isinstance(outcome, dict) else str(outcome)
            timeframe = outcome.get('timeframe', '') if isinstance(outcome, dict) else ''

            if not measure:
                continue

            data_point = EfficacyDataPoint(
                source_type=DataSource.CLINICALTRIALS,
                source_url=f"https://clinicaltrials.gov/study/{nct_id}",
                nct_id=nct_id,
                trial_name=trial.get('title', nct_id)[:100],
                trial_phase=trial.get('phase'),
                endpoint_name=self._normalize_outcome_name(measure, expected_endpoints),
                endpoint_type='primary',
                timepoint=timeframe or None,
                drug_arm_name=drug.generic_name,
                disease_mesh_id=disease.mesh_id,
                indication_name=disease.standard_name,
                # CT.gov often lacks numeric results - mark for review
                confidence_score=0.6,  # Lower confidence
                review_status=ReviewStatus.PENDING_REVIEW,
            )
            data_points.append(data_point)

        # Extract secondary outcomes (limit to relevant ones)
        secondary_outcomes = details.get('secondary_outcomes', [])[:5]
        for outcome in secondary_outcomes:
            measure = outcome.get('measure', '') if isinstance(outcome, dict) else str(outcome)
            timeframe = outcome.get('timeframe', '') if isinstance(outcome, dict) else ''

            if not measure:
                continue

            # Check if this matches an expected endpoint
            normalized = self._normalize_outcome_name(measure, expected_endpoints)
            if not any(ep.lower() in normalized.lower() for ep in expected_endpoints):
                continue  # Skip non-matching secondary outcomes

            data_point = EfficacyDataPoint(
                source_type=DataSource.CLINICALTRIALS,
                source_url=f"https://clinicaltrials.gov/study/{nct_id}",
                nct_id=nct_id,
                trial_name=trial.get('title', nct_id)[:100],
                trial_phase=trial.get('phase'),
                endpoint_name=normalized,
                endpoint_type='secondary',
                timepoint=timeframe or None,
                drug_arm_name=drug.generic_name,
                disease_mesh_id=disease.mesh_id,
                indication_name=disease.standard_name,
                confidence_score=0.5,  # Even lower for secondary without data
                review_status=ReviewStatus.PENDING_REVIEW,
            )
            data_points.append(data_point)

        logger.debug(f"Extracted {len(data_points)} outcomes from trial {nct_id}")
        return data_points

    def _normalize_outcome_name(
        self,
        measure: str,
        expected_endpoints: List[str]
    ) -> str:
        """
        Normalize outcome measure name to match expected endpoints.

        Args:
            measure: Raw outcome measure text
            expected_endpoints: List of expected endpoint names

        Returns:
            Normalized endpoint name
        """
        measure_lower = measure.lower()

        # Check for exact/partial matches with expected endpoints
        for endpoint in expected_endpoints:
            if endpoint.lower() in measure_lower:
                return endpoint

        # Common normalizations
        normalizations = {
            'systemic lupus erythematosus responder index': 'SRI-4',
            'sri-4': 'SRI-4',
            'sri4': 'SRI-4',
            'bicla': 'BICLA',
            'sledai': 'SLEDAI',
            'acr20': 'ACR20',
            'acr50': 'ACR50',
            'acr70': 'ACR70',
            'pasi 75': 'PASI 75',
            'pasi75': 'PASI 75',
            'pasi 90': 'PASI 90',
            'pasi90': 'PASI 90',
            'easi 75': 'EASI 75',
            'easi75': 'EASI 75',
        }

        for pattern, normalized in normalizations.items():
            if pattern in measure_lower:
                return normalized

        # Return truncated original if no match
        return measure[:100] if len(measure) > 100 else measure
