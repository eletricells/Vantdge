"""
Database Repository Protocol

Defines the interface for data persistence operations.
"""

from typing import Protocol, Optional, List, Dict, Any
from datetime import datetime


class CaseSeriesRepositoryProtocol(Protocol):
    """Protocol for case series data persistence."""

    # --- Run Management ---

    def create_run(
        self,
        drug_name: str,
        parameters: Dict[str, Any],
    ) -> str:
        """
        Create a new analysis run.

        Args:
            drug_name: Name of the drug being analyzed
            parameters: Run parameters (search settings, etc.)

        Returns:
            Run ID (UUID string)
        """
        ...

    def update_run(
        self,
        run_id: str,
        status: str,
        papers_found: Optional[int] = None,
        papers_extracted: Optional[int] = None,
        opportunities_found: Optional[int] = None,
        total_tokens: Optional[int] = None,
        estimated_cost_usd: Optional[float] = None,
    ) -> None:
        """
        Update an existing run's status and metrics.

        Args:
            run_id: Run ID to update
            status: New status (running, completed, failed)
            papers_found: Number of papers found
            papers_extracted: Number of papers extracted
            opportunities_found: Number of opportunities found
            total_tokens: Total tokens used
            estimated_cost_usd: Estimated cost in USD
        """
        ...

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get run details by ID.

        Args:
            run_id: Run ID

        Returns:
            Run details dict, or None if not found
        """
        ...

    def get_historical_runs(
        self,
        drug_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get historical runs, optionally filtered by drug.

        Args:
            drug_name: Filter by drug name (optional)
            limit: Maximum runs to return

        Returns:
            List of run summary dicts
        """
        ...

    # --- Extraction Cache ---

    def save_extraction(
        self,
        drug_name: str,
        pmid: str,
        extraction_data: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> None:
        """
        Save an extraction to the cache.

        Args:
            drug_name: Drug name
            pmid: PubMed ID
            extraction_data: Full extraction data dict
            run_id: Associated run ID (optional)
        """
        ...

    def load_extraction(
        self,
        drug_name: str,
        pmid: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Load a cached extraction.

        Args:
            drug_name: Drug name
            pmid: PubMed ID

        Returns:
            Extraction data dict if cached, None otherwise
        """
        ...

    def has_extraction(self, drug_name: str, pmid: str) -> bool:
        """
        Check if an extraction exists in cache.

        Args:
            drug_name: Drug name
            pmid: PubMed ID

        Returns:
            True if extraction is cached
        """
        ...

    # --- Market Intelligence Cache ---

    def save_market_intel(
        self,
        disease: str,
        market_intel_data: Dict[str, Any],
    ) -> None:
        """
        Save market intelligence to the cache.

        Args:
            disease: Disease name
            market_intel_data: Market intelligence data dict
        """
        ...

    def load_market_intel(
        self,
        disease: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Load cached market intelligence.

        Args:
            disease: Disease name

        Returns:
            Market intelligence data if cached, None otherwise
        """
        ...

    def is_market_intel_fresh(
        self,
        disease: str,
        max_age_days: int = 30,
    ) -> bool:
        """
        Check if market intelligence is fresh (not stale).

        Args:
            disease: Disease name
            max_age_days: Maximum age in days before considered stale

        Returns:
            True if market intel exists and is fresh
        """
        ...

    # --- Drug Cache ---

    def save_drug(
        self,
        drug_name: str,
        drug_data: Dict[str, Any],
    ) -> None:
        """
        Save drug information to cache.

        Args:
            drug_name: Drug name
            drug_data: Drug data dict (mechanism, target, indications, etc.)
        """
        ...

    def load_drug(
        self,
        drug_name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Load cached drug information.

        Args:
            drug_name: Drug name

        Returns:
            Drug data dict if cached, None otherwise
        """
        ...

    # --- Reference Data ---

    def get_organ_domains(self) -> Dict[str, List[str]]:
        """
        Get organ domain keyword mappings.

        Returns:
            Dict mapping domain name to list of keywords
        """
        ...

    def get_safety_categories(self) -> Dict[str, Dict[str, Any]]:
        """
        Get safety signal category definitions.

        Returns:
            Dict mapping category name to config dict with:
            - keywords: List of trigger keywords
            - severity_weight: Severity score (1-10)
            - regulatory_flag: Whether this is a regulatory concern
        """
        ...

    def find_instruments_for_disease(
        self,
        disease: str,
    ) -> Dict[str, int]:
        """
        Find validated instruments for a disease.

        Args:
            disease: Disease name

        Returns:
            Dict mapping instrument name to quality score (1-10)
        """
        ...

    # --- Opportunity Tracking ---

    def save_opportunity(
        self,
        run_id: str,
        opportunity_data: Dict[str, Any],
    ) -> None:
        """
        Save an opportunity to the database.

        Args:
            run_id: Associated run ID
            opportunity_data: Opportunity data dict
        """
        ...

    def get_opportunities_for_run(
        self,
        run_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all opportunities for a run.

        Args:
            run_id: Run ID

        Returns:
            List of opportunity data dicts
        """
        ...
