"""
Case Series Repository

Implements the CaseSeriesRepositoryProtocol by wrapping the existing
CaseSeriesDatabase. Provides a clean interface for data persistence.
"""

import logging
from typing import Optional, List, Dict, Any

from src.case_series.models import (
    CaseSeriesExtraction,
    MarketIntelligence,
    RepurposingOpportunity,
    DrugAnalysisResult,
)

logger = logging.getLogger(__name__)


class CaseSeriesRepository:
    """
    Repository for case series data persistence.

    Wraps the existing CaseSeriesDatabase to provide a clean interface
    that implements the CaseSeriesRepositoryProtocol.

    Can operate without a database (returns None/empty for reads, no-ops for writes).
    """

    # Default organ domain mappings
    DEFAULT_ORGAN_DOMAINS = {
        'musculoskeletal': ['joint', 'arthritis', 'das28', 'acr20', 'acr50', 'haq'],
        'mucocutaneous': ['skin', 'rash', 'pasi', 'easi', 'bsa'],
        'renal': ['kidney', 'renal', 'proteinuria', 'creatinine', 'gfr'],
        'neurological': ['neuro', 'cognitive', 'edss', 'relapse'],
        'hematological': ['anemia', 'platelet', 'neutropenia', 'cytopenia'],
        'cardiopulmonary': ['cardiac', 'lung', 'fvc', 'dlco'],
        'immunological': ['complement', 'autoantibody', 'crp', 'esr'],
        'systemic': ['sledai', 'bilag', 'bvas', 'disease activity'],
        'gastrointestinal': ['gi', 'bowel', 'mayo', 'cdai'],
        'ocular': ['eye', 'uveitis', 'visual acuity'],
        'constitutional': ['fatigue', 'fever', 'weight loss'],
    }

    # Default safety categories
    DEFAULT_SAFETY_CATEGORIES = {
        'serious_infection': {'keywords': ['serious infection', 'sepsis', 'pneumonia', 'tb'], 'severity_weight': 9, 'regulatory_flag': True},
        'malignancy': {'keywords': ['malignancy', 'cancer', 'lymphoma'], 'severity_weight': 10, 'regulatory_flag': True},
        'cardiovascular': {'keywords': ['mace', 'mi', 'stroke', 'heart failure'], 'severity_weight': 9, 'regulatory_flag': True},
        'thromboembolic': {'keywords': ['vte', 'dvt', 'pe', 'thrombosis'], 'severity_weight': 9, 'regulatory_flag': True},
        'hepatotoxicity': {'keywords': ['hepatotoxicity', 'liver injury', 'alt increased'], 'severity_weight': 8, 'regulatory_flag': True},
        'cytopenia': {'keywords': ['neutropenia', 'thrombocytopenia', 'anemia'], 'severity_weight': 7, 'regulatory_flag': True},
        'death': {'keywords': ['death', 'fatal', 'mortality'], 'severity_weight': 10, 'regulatory_flag': True},
    }

    # Default validated instruments
    DEFAULT_INSTRUMENTS = {
        'Physician Global': 7,
        'Patient Global': 7,
        'SF-36': 8,
        'EQ-5D': 8,
        'Pain VAS': 7,
        'FACIT-Fatigue': 8,
    }

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize the repository.

        Args:
            database_url: PostgreSQL database URL. If None, repository operates
                         in memory-only mode (no persistence).
        """
        self._db = None
        self._database_url = database_url

        if database_url:
            try:
                from src.tools.case_series_database import CaseSeriesDatabase
                self._db = CaseSeriesDatabase(database_url)
                if self._db.is_available:
                    logger.info("CaseSeriesRepository connected to database")
                else:
                    logger.warning("CaseSeriesRepository: database not available, operating in memory-only mode")
                    self._db = None
            except Exception as e:
                logger.warning(f"CaseSeriesRepository: failed to connect to database: {e}")
                self._db = None

    @property
    def is_available(self) -> bool:
        """Check if database is available."""
        return self._db is not None and self._db.is_available

    # -------------------------------------------------------------------------
    # Run Management
    # -------------------------------------------------------------------------

    def create_run(
        self,
        drug_name: str,
        parameters: Dict[str, Any],
    ) -> str:
        """Create a new analysis run."""
        if not self._db:
            import uuid
            return str(uuid.uuid4())
        return self._db.create_run(drug_name, parameters)

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
        """Update an existing run's status and metrics."""
        if not self._db:
            return

        # Update status
        self._db.update_run_status(run_id, status)

        # Update stats
        stats = {}
        if papers_found is not None:
            stats['papers_found'] = papers_found
        if papers_extracted is not None:
            stats['papers_extracted'] = papers_extracted
        if opportunities_found is not None:
            stats['opportunities_found'] = opportunities_found
        if total_tokens is not None:
            stats['total_input_tokens'] = total_tokens
        if estimated_cost_usd is not None:
            stats['estimated_cost_usd'] = estimated_cost_usd

        if stats:
            self._db.update_run_stats(run_id, **stats)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get run details by ID."""
        if not self._db:
            return None
        return self._db.get_run_details(run_id)

    def get_historical_runs(
        self,
        drug_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get historical runs."""
        if not self._db:
            return []
        # Note: current implementation doesn't filter by drug_name
        return self._db.get_historical_runs(limit)

    def load_historical_run(self, run_id: str) -> Optional[DrugAnalysisResult]:
        """Load a complete historical run as DrugAnalysisResult."""
        if not self._db:
            return None
        return self._db.load_run_as_result(run_id)

    # -------------------------------------------------------------------------
    # Extraction Cache
    # -------------------------------------------------------------------------

    def save_extraction(
        self,
        drug_name: str,
        pmid: str,
        extraction_data: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> None:
        """Save an extraction to the cache."""
        if not self._db:
            return

        # Convert dict to CaseSeriesExtraction if needed
        if isinstance(extraction_data, dict):
            try:
                extraction = CaseSeriesExtraction(**extraction_data)
            except Exception as e:
                logger.error(f"Failed to convert extraction data: {e}")
                return
        else:
            extraction = extraction_data

        if run_id:
            self._db.save_extraction(run_id, extraction, drug_name)

    def load_extraction(
        self,
        drug_name: str,
        pmid: str,
    ) -> Optional[Dict[str, Any]]:
        """Load a cached extraction."""
        if not self._db:
            return None

        extraction = self._db.load_extraction(drug_name, pmid)
        if extraction:
            return extraction.model_dump()
        return None

    def has_extraction(self, drug_name: str, pmid: str) -> bool:
        """Check if an extraction exists in cache."""
        if not self._db:
            return False

        result = self._db.check_extraction_exists(pmid, drug_name, "")
        return result is not None

    # -------------------------------------------------------------------------
    # Market Intelligence Cache
    # -------------------------------------------------------------------------

    def save_market_intel(
        self,
        disease: str,
        market_intel_data: Dict[str, Any],
    ) -> None:
        """Save market intelligence to the cache."""
        if not self._db:
            return

        # Convert dict to MarketIntelligence if needed
        if isinstance(market_intel_data, dict):
            try:
                mi = MarketIntelligence(**market_intel_data)
            except Exception as e:
                logger.error(f"Failed to convert market intel data: {e}")
                return
        else:
            mi = market_intel_data

        self._db.save_market_intelligence(mi)

    def load_market_intel(
        self,
        disease: str,
    ) -> Optional[Dict[str, Any]]:
        """Load cached market intelligence."""
        if not self._db:
            return None

        mi = self._db.check_market_intel_fresh(disease)
        if mi:
            return mi.model_dump()
        return None

    def is_market_intel_fresh(
        self,
        disease: str,
        max_age_days: int = 30,
    ) -> bool:
        """Check if market intelligence is fresh."""
        if not self._db:
            return False

        mi = self._db.check_market_intel_fresh(disease)
        return mi is not None

    # -------------------------------------------------------------------------
    # Drug Cache
    # -------------------------------------------------------------------------

    def save_drug(
        self,
        drug_name: str,
        drug_data: Dict[str, Any],
    ) -> None:
        """Save drug information to cache."""
        if not self._db:
            return

        self._db.save_drug(
            drug_name=drug_name,
            generic_name=drug_data.get('generic_name'),
            mechanism=drug_data.get('mechanism'),
            target=drug_data.get('target'),
            approved_indications=drug_data.get('approved_indications', []),
            data_sources=drug_data.get('data_sources', []),
        )

    def load_drug(
        self,
        drug_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Load cached drug information."""
        if not self._db:
            return None
        return self._db.check_drug_exists(drug_name)

    # -------------------------------------------------------------------------
    # Reference Data
    # -------------------------------------------------------------------------

    def get_organ_domains(self) -> Dict[str, List[str]]:
        """Get organ domain keyword mappings."""
        if self._db:
            try:
                domains = self._db.get_organ_domains()
                if domains:
                    return domains
            except Exception as e:
                logger.warning(f"Failed to load organ domains from database: {e}")

        return self.DEFAULT_ORGAN_DOMAINS.copy()

    def get_safety_categories(self) -> Dict[str, Dict[str, Any]]:
        """Get safety signal category definitions."""
        if self._db:
            try:
                categories = self._db.get_safety_categories()
                if categories:
                    return categories
            except Exception as e:
                logger.warning(f"Failed to load safety categories from database: {e}")

        return self.DEFAULT_SAFETY_CATEGORIES.copy()

    def find_instruments_for_disease(
        self,
        disease: str,
    ) -> Dict[str, int]:
        """Find validated instruments for a disease."""
        if self._db:
            try:
                instruments = self._db.find_instruments_for_disease(disease)
                if instruments:
                    return instruments
            except Exception as e:
                logger.warning(f"Failed to load instruments from database: {e}")

        return self.DEFAULT_INSTRUMENTS.copy()

    # -------------------------------------------------------------------------
    # Opportunity Tracking
    # -------------------------------------------------------------------------

    def save_opportunity(
        self,
        run_id: str,
        drug_name: str,
        opportunity: RepurposingOpportunity,
    ) -> None:
        """Save an opportunity to the database."""
        if not self._db:
            return

        try:
            # Use extraction_id if it exists on the extraction, otherwise use 0
            extraction_id = getattr(opportunity.extraction, 'extraction_id', 0) or 0
            self._db.save_opportunity(
                run_id=run_id,
                extraction_id=extraction_id,
                opportunity=opportunity,
                drug_name=drug_name,
            )
        except Exception as e:
            logger.error(f"Failed to save opportunity: {e}")

    def get_opportunities_for_run(
        self,
        run_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all opportunities for a run."""
        if not self._db:
            return []

        result = self.load_historical_run(run_id)
        if result:
            return [opp.model_dump() for opp in result.opportunities]
        return []

    # -------------------------------------------------------------------------
    # Disease Variants
    # -------------------------------------------------------------------------

    def get_disease_variants(self) -> Dict[str, List[str]]:
        """Get disease name variants for search expansion."""
        if self._db:
            try:
                return self._db.load_disease_name_variants()
            except Exception as e:
                logger.warning(f"Failed to load disease variants: {e}")

        return {}

    def get_disease_parent_mappings(self) -> Dict[str, str]:
        """Get disease-to-parent mappings for market intel grouping."""
        if self._db:
            try:
                return self._db.load_disease_parent_mappings()
            except Exception as e:
                logger.warning(f"Failed to load disease parent mappings: {e}")

        return {}

    def save_disease_mapping(
        self,
        raw_disease: str,
        canonical_disease: str,
        source: str = 'llm_standardization',
    ) -> bool:
        """
        Save a disease name mapping (variant -> canonical).

        Args:
            raw_disease: Raw disease name from extraction
            canonical_disease: Standardized/canonical disease name
            source: Source of the mapping

        Returns:
            True if saved successfully
        """
        if not self._db:
            return False

        try:
            # Save as both variant and parent mapping for comprehensive coverage
            self._db.save_disease_variant(
                canonical_name=canonical_disease,
                variant_name=raw_disease,
                variant_type='variant',
                source=source,
                confidence=0.85,
                created_by='llm'
            )
            self._db.save_disease_parent_mapping(
                specific_name=raw_disease,
                parent_name=canonical_disease,
                relationship_type='synonym',
                source=source,
                confidence=0.85,
                created_by='llm'
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to save disease mapping: {e}")
            return False

    # -------------------------------------------------------------------------
    # Paper Discovery Persistence
    # -------------------------------------------------------------------------

    def save_paper_discovery(
        self,
        drug_name: str,
        generic_name: Optional[str],
        papers: List[Dict[str, Any]],
        approved_indications: List[str],
        sources_searched: List[str],
        duplicates_removed: int = 0,
    ) -> Optional[str]:
        """
        Save a paper discovery session with all papers and filter status.

        Args:
            drug_name: Name of the drug
            generic_name: Generic name of the drug
            papers: List of paper dicts with metadata and filter evaluation
            approved_indications: List of approved indications
            sources_searched: List of sources searched
            duplicates_removed: Number of duplicates removed

        Returns:
            discovery_id if successful, None otherwise
        """
        if not self._db:
            return None

        try:
            return self._db.save_paper_discovery(
                drug_name=drug_name,
                generic_name=generic_name,
                papers=papers,
                approved_indications=approved_indications,
                sources_searched=sources_searched,
                duplicates_removed=duplicates_removed,
            )
        except Exception as e:
            logger.error(f"Failed to save paper discovery: {e}")
            return None

    def load_paper_discovery(
        self,
        drug_name: str,
        max_age_days: int = 7,
    ) -> Optional[Dict[str, Any]]:
        """
        Load the most recent paper discovery for a drug.

        Args:
            drug_name: Name of the drug
            max_age_days: Maximum age of discovery to consider fresh

        Returns:
            Dict with discovery metadata and papers, or None if not found
        """
        if not self._db:
            return None

        try:
            return self._db.load_paper_discovery(drug_name, max_age_days)
        except Exception as e:
            logger.error(f"Failed to load paper discovery: {e}")
            return None

    def get_discovery_history(
        self,
        drug_name: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get paper discovery history.

        Args:
            drug_name: Optional drug name to filter by
            limit: Maximum number of discoveries to return

        Returns:
            List of discovery summaries
        """
        if not self._db:
            return []

        try:
            return self._db.get_discovery_history(drug_name, limit)
        except Exception as e:
            logger.error(f"Failed to get discovery history: {e}")
            return []

    # -------------------------------------------------------------------------
    # Score Explanations
    # -------------------------------------------------------------------------

    def save_score_explanation(
        self,
        run_id: str,
        drug_name: str,
        disease: str,
        parent_disease: Optional[str],
        explanation: str,
        input_summary: Dict[str, Any],
        model: str,
        tokens: int,
    ) -> None:
        """
        Save a score explanation to the database.

        Args:
            run_id: Run ID
            drug_name: Drug name
            disease: Disease name
            parent_disease: Parent disease (None if this is the parent)
            explanation: Claude-generated explanation text
            input_summary: Input data used for generation
            model: Model used for generation
            tokens: Tokens used
        """
        if not self._db:
            return

        try:
            self._db.save_score_explanation(
                run_id=run_id,
                drug_name=drug_name,
                disease=disease,
                parent_disease=parent_disease,
                explanation=explanation,
                input_summary=input_summary,
                model=model,
                tokens=tokens,
            )
        except Exception as e:
            logger.error(f"Failed to save score explanation: {e}")

    def load_score_explanations(self, run_id: str) -> Dict[str, str]:
        """
        Load all score explanations for a run.

        Args:
            run_id: Run ID

        Returns:
            Dict mapping disease -> explanation
        """
        if not self._db:
            return {}

        try:
            return self._db.load_score_explanations(run_id)
        except Exception as e:
            logger.error(f"Failed to load score explanations: {e}")
            return {}

    def save_paper_explanation(
        self,
        run_id: str,
        pmid: str,
        explanation: str,
    ) -> None:
        """
        Save a per-paper score explanation.

        Args:
            run_id: Run ID
            pmid: Paper PMID
            explanation: Brief explanation text
        """
        if not self._db:
            return

        try:
            self._db.save_paper_explanation(
                run_id=run_id,
                pmid=pmid,
                explanation=explanation,
            )
        except Exception as e:
            logger.error(f"Failed to save paper explanation: {e}")

    def update_extraction_parent_disease(
        self,
        run_id: str,
        pmid: str,
        parent_disease: Optional[str],
    ) -> None:
        """
        Update parent disease on an extraction.

        Args:
            run_id: Run ID
            pmid: Paper PMID
            parent_disease: Parent disease name
        """
        if not self._db:
            return

        try:
            self._db.update_extraction_parent_disease(
                run_id=run_id,
                pmid=pmid,
                parent_disease=parent_disease,
            )
        except Exception as e:
            logger.debug(f"Failed to update extraction parent disease: {e}")

    def update_opportunity_parent_disease(
        self,
        run_id: str,
        drug_name: str,
        disease: str,
        parent_disease: Optional[str],
    ) -> None:
        """
        Update parent disease on an opportunity.

        Args:
            run_id: Run ID
            drug_name: Drug name
            disease: Disease name
            parent_disease: Parent disease name
        """
        if not self._db:
            return

        try:
            self._db.update_opportunity_parent_disease(
                run_id=run_id,
                drug_name=drug_name,
                disease=disease,
                parent_disease=parent_disease,
            )
        except Exception as e:
            logger.debug(f"Failed to update opportunity parent disease: {e}")

    def get_hierarchical_opportunities(self, run_id: str) -> List[Dict[str, Any]]:
        """
        Get opportunities with hierarchical structure for a run.

        Args:
            run_id: Run ID

        Returns:
            List of hierarchical opportunity dicts
        """
        if not self._db:
            return []

        try:
            return self._db.get_hierarchical_opportunities(run_id)
        except Exception as e:
            logger.error(f"Failed to get hierarchical opportunities: {e}")
            return []

    # -------------------------------------------------------------------------
    # Papers for Manual Review
    # -------------------------------------------------------------------------

    def save_papers_for_manual_review(
        self,
        run_id: str,
        drug_name: str,
        papers: List[Any],
    ) -> int:
        """
        Save papers requiring manual review to the database.

        Args:
            run_id: Analysis run ID
            drug_name: Drug being analyzed
            papers: List of PaperForManualReview objects or dicts

        Returns:
            Number of papers saved
        """
        if not self._db:
            return 0

        try:
            # Convert to dicts if needed
            paper_dicts = []
            for paper in papers:
                if hasattr(paper, 'model_dump'):
                    paper_dicts.append(paper.model_dump())
                elif isinstance(paper, dict):
                    paper_dicts.append(paper)
                else:
                    # Try to convert dataclass or similar
                    paper_dicts.append(vars(paper) if hasattr(paper, '__dict__') else {})

            return self._db.save_papers_for_manual_review(
                run_id=run_id,
                drug_name=drug_name,
                papers=paper_dicts,
            )
        except Exception as e:
            logger.error(f"Failed to save papers for manual review: {e}")
            return 0

    def load_papers_for_manual_review(self, run_id: str) -> List[Dict[str, Any]]:
        """
        Load papers requiring manual review for a run.

        Args:
            run_id: Analysis run ID

        Returns:
            List of paper dicts, sorted by n_patients descending
        """
        if not self._db:
            return []

        try:
            return self._db.load_papers_for_manual_review(run_id)
        except Exception as e:
            logger.error(f"Failed to load papers for manual review: {e}")
            return []

    def get_manual_review_count(self, run_id: str) -> int:
        """
        Get count of papers requiring manual review for a run.

        Args:
            run_id: Analysis run ID

        Returns:
            Count of papers
        """
        if not self._db:
            return 0

        try:
            return self._db.get_manual_review_count(run_id)
        except Exception as e:
            logger.error(f"Failed to get manual review count: {e}")
            return 0
