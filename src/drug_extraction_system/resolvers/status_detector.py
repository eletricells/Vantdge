"""
Drug Status Detector

Determines if a drug is approved (FDA-approved) or pipeline (in clinical trials).
"""

import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
from src.drug_extraction_system.api_clients.clinicaltrials_client import ClinicalTrialsClient

logger = logging.getLogger(__name__)


class DrugStatus(Enum):
    """Drug approval status."""
    APPROVED = "approved"
    PIPELINE = "pipeline"
    UNKNOWN = "unknown"


@dataclass
class StatusResult:
    """Result of status detection."""
    status: DrugStatus
    highest_phase: Optional[str] = None
    has_fda_label: bool = False
    has_clinical_trials: bool = False
    trial_count: int = 0
    confidence: str = "low"  # "high", "medium", "low"


class DrugStatusDetector:
    """
    Detects whether a drug is approved or in pipeline.
    
    Logic:
    1. Check OpenFDA for FDA label → Approved
    2. Check ClinicalTrials.gov for trials → Pipeline
    3. Neither → Unknown
    """

    def __init__(
        self,
        openfda_client: Optional[OpenFDAClient] = None,
        clinicaltrials_client: Optional[ClinicalTrialsClient] = None
    ):
        """
        Initialize detector with API clients.

        Args:
            openfda_client: OpenFDA client (created if not provided)
            clinicaltrials_client: ClinicalTrials client (created if not provided)
        """
        self.openfda = openfda_client or OpenFDAClient()
        self.clinicaltrials = clinicaltrials_client or ClinicalTrialsClient()

    def detect(self, drug_name: str) -> StatusResult:
        """
        Detect drug approval status.

        Args:
            drug_name: Drug name to check

        Returns:
            StatusResult with status and supporting information
        """
        result = StatusResult(status=DrugStatus.UNKNOWN)
        logger.info(f"Detecting status for '{drug_name}'")

        # Check OpenFDA first
        has_label = self.openfda.is_drug_approved(drug_name)
        result.has_fda_label = has_label

        if has_label:
            result.status = DrugStatus.APPROVED
            result.confidence = "high"
            logger.info(f"'{drug_name}' is APPROVED (has FDA label)")

            # Still check trials for additional context
            trials = self.clinicaltrials.search_trials(drug_name, limit=10)
            if trials:
                result.has_clinical_trials = True
                result.trial_count = len(trials)
                result.highest_phase = self._get_highest_phase(trials)

            return result

        # Check ClinicalTrials.gov
        trials = self.clinicaltrials.search_trials(drug_name, limit=50)
        if trials:
            result.has_clinical_trials = True
            result.trial_count = len(trials)
            result.highest_phase = self._get_highest_phase(trials)
            result.status = DrugStatus.PIPELINE
            result.confidence = "high"
            logger.info(f"'{drug_name}' is PIPELINE (highest phase: {result.highest_phase})")
            return result

        # Neither found
        result.status = DrugStatus.UNKNOWN
        result.confidence = "low"
        logger.warning(f"'{drug_name}' status UNKNOWN (no FDA label or trials found)")
        return result

    def _get_highest_phase(self, trials: list) -> Optional[str]:
        """Extract highest phase from trial list."""
        phase_order = {
            "PHASE4": 5,
            "PHASE3": 4,
            "PHASE2": 3,
            "PHASE1": 2,
            "EARLY_PHASE1": 1,
            "NA": 0,
        }

        highest_phase = None
        highest_rank = -1

        for study in trials:
            protocol = study.get("protocolSection", {})
            phases = protocol.get("designModule", {}).get("phases", [])
            for phase in phases:
                rank = phase_order.get(phase, 0)
                if rank > highest_rank:
                    highest_rank = rank
                    highest_phase = phase

        if highest_phase:
            return highest_phase.replace("_", " ").title()
        return None

    def is_approved(self, drug_name: str) -> bool:
        """
        Quick check if drug is approved.

        Args:
            drug_name: Drug name to check

        Returns:
            True if approved, False otherwise
        """
        return self.openfda.is_drug_approved(drug_name)

    def is_pipeline(self, drug_name: str) -> bool:
        """
        Quick check if drug is in pipeline.

        Args:
            drug_name: Drug name to check

        Returns:
            True if in pipeline (has trials but no FDA label), False otherwise
        """
        result = self.detect(drug_name)
        return result.status == DrugStatus.PIPELINE

