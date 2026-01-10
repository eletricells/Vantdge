"""
Main Efficacy Benchmarking Agent.

Orchestrates the disease-based drug efficacy benchmarking workflow:
1. Standardize disease name
2. Find approved drugs for the disease
3. For each drug, extract efficacy data (publications first, then CT.gov)
4. Score confidence and flag low-confidence for review
5. Store results and return benchmarking table
"""

import logging
from typing import List, Optional, Callable, Dict, Any
from uuid import uuid4
from datetime import datetime

from src.drug_extraction_system.database.connection import DatabaseConnection
from .models import (
    BenchmarkSession, DiseaseMatch, ApprovedDrug, DrugBenchmarkResult,
    EfficacyDataPoint, ReviewStatus, DataSource, get_endpoints_for_disease
)
from .services.disease_drug_finder import DiseaseDrugFinder
from .services.publication_extractor import PublicationEfficacyExtractor
from .services.clinical_trials_extractor import ClinicalTrialsEfficacyExtractor
from .services.confidence_scorer import ConfidenceScorer

logger = logging.getLogger(__name__)


class EfficacyBenchmarkingAgent:
    """
    Disease-Based Drug Efficacy Benchmarking Agent.
    """

    def __init__(
        self,
        db: DatabaseConnection,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        confidence_threshold: float = 0.7
    ):
        """
        Initialize the agent.

        Args:
            db: Database connection
            progress_callback: Optional callback(message, progress) for UI updates
            confidence_threshold: Minimum confidence for auto-acceptance
        """
        self.db = db
        self.progress_callback = progress_callback or (lambda msg, pct: None)
        self.confidence_threshold = confidence_threshold

        # Initialize services
        self.disease_finder = DiseaseDrugFinder(db)
        self.publication_extractor = PublicationEfficacyExtractor()
        self.ct_extractor = ClinicalTrialsEfficacyExtractor()
        self.confidence_scorer = ConfidenceScorer(confidence_threshold)

    def run_benchmark(
        self,
        disease_input: str,
        selected_drug_ids: Optional[List[int]] = None,
        max_papers_per_drug: int = 5,
        min_confidence: Optional[float] = None
    ) -> BenchmarkSession:
        """
        Run full benchmarking workflow.

        Args:
            disease_input: User-provided disease name
            selected_drug_ids: Optional list of drug IDs to benchmark (None = all found)
            max_papers_per_drug: Maximum papers to search per drug
            min_confidence: Override default confidence threshold

        Returns:
            BenchmarkSession with all results
        """
        if min_confidence is not None:
            self.confidence_scorer.confidence_threshold = min_confidence

        session = BenchmarkSession(
            session_id=str(uuid4())[:8],
            disease=None,
            status="initializing"
        )

        try:
            # Step 1: Standardize disease
            self.progress_callback("Standardizing disease name...", 0.05)
            disease = self.disease_finder.standardize_disease(disease_input)

            if not disease:
                logger.error(f"Could not standardize disease: {disease_input}")
                session.status = "failed"
                return session

            session.disease = disease
            logger.info(f"Disease standardized: {disease.standard_name} (MeSH: {disease.mesh_id})")

            # Step 2: Find approved drugs
            self.progress_callback(f"Finding approved drugs for {disease.standard_name}...", 0.10)
            drugs = self.disease_finder.find_approved_drugs(disease)

            # Filter to selected drugs if specified
            if selected_drug_ids:
                drugs = [d for d in drugs if d.drug_id in selected_drug_ids]

            session.drugs = drugs

            if not drugs:
                logger.warning(f"No approved drugs found for {disease.standard_name}")
                session.status = "complete"
                return session

            logger.info(f"Found {len(drugs)} drugs to benchmark")

            # Get expected endpoints for this disease
            endpoints_config = get_endpoints_for_disease(disease.standard_name)
            all_endpoints = (
                endpoints_config.get('primary', []) +
                endpoints_config.get('secondary', [])
            )

            # Step 3: Extract efficacy for each drug
            session.status = "extracting"
            total_drugs = len(drugs)

            for i, drug in enumerate(drugs):
                # Add delay between drugs to avoid rate limits (except for first drug)
                if i > 0:
                    import time
                    logger.info("Waiting 3 seconds before next drug to avoid rate limits...")
                    time.sleep(3.0)

                progress = 0.15 + (i / total_drugs) * 0.75
                self.progress_callback(
                    f"Extracting efficacy for {drug.generic_name} ({i+1}/{total_drugs})...",
                    progress
                )

                result = self._extract_drug_efficacy(
                    drug=drug,
                    disease=disease,
                    expected_endpoints=all_endpoints,
                    max_papers=max_papers_per_drug
                )
                session.results.append(result)

            # Step 4: Determine session status
            self.progress_callback("Finalizing results...", 0.95)

            pending_review = session.pending_review_count
            if pending_review > 0:
                session.status = "review_needed"
                logger.info(f"Benchmark complete with {pending_review} items pending review")
            else:
                session.status = "complete"
                logger.info("Benchmark complete - all items auto-accepted")

            # Store results in database
            self._store_results(session)

            self.progress_callback("Benchmark complete!", 1.0)
            return session

        except Exception as e:
            logger.error(f"Benchmark failed: {e}", exc_info=True)
            session.status = "failed"
            return session

    def _extract_drug_efficacy(
        self,
        drug: ApprovedDrug,
        disease: DiseaseMatch,
        expected_endpoints: List[str],
        max_papers: int = 12  # Increased from 5 to ensure coverage of all discovered trials
    ) -> DrugBenchmarkResult:
        """
        Extract efficacy data for a single drug.
        """
        result = DrugBenchmarkResult(drug=drug)

        try:
            # Priority 1: Publications (PubMed)
            logger.info(f"Searching publications for {drug.generic_name}...")
            papers = self.publication_extractor.search_pivotal_trials(
                drug=drug,
                disease=disease,
                max_results=max_papers
            )

            if papers:
                logger.info(f"Found {len(papers)} papers, extracting data...")
                pub_data = self.publication_extractor.extract_from_papers(
                    papers=papers,
                    drug=drug,
                    disease=disease,
                    expected_endpoints=expected_endpoints
                )
                result.efficacy_data.extend(pub_data)
                logger.info(f"Extracted {len(pub_data)} data points from publications")

            # Fallback: ClinicalTrials.gov if insufficient publication data
            min_data_points = 3
            if len(result.efficacy_data) < min_data_points:
                logger.info(
                    f"Insufficient publication data ({len(result.efficacy_data)} points), "
                    f"trying ClinicalTrials.gov..."
                )

                trials = self.ct_extractor.search_completed_trials(
                    drug=drug,
                    disease=disease,
                    max_results=10
                )

                if trials:
                    ct_data = self.ct_extractor.extract_from_trials(
                        trials=trials,
                        drug=drug,
                        disease=disease,
                        expected_endpoints=expected_endpoints
                    )
                    result.efficacy_data.extend(ct_data)
                    logger.info(f"Added {len(ct_data)} data points from CT.gov")

            # Score confidence for all data points
            result.efficacy_data = self.confidence_scorer.score_and_flag(result.efficacy_data)

            # Set extraction status
            if result.efficacy_data:
                if result.has_primary_endpoints:
                    result.extraction_status = "success"
                else:
                    result.extraction_status = "partial"
            else:
                result.extraction_status = "failed"
                result.errors.append("No efficacy data found")

        except Exception as e:
            logger.error(f"Extraction failed for {drug.generic_name}: {e}", exc_info=True)
            result.extraction_status = "failed"
            result.errors.append(str(e))

        return result

    def _store_results(self, session: BenchmarkSession) -> None:
        """
        Store benchmark results in database.
        """
        self.db.ensure_connected()

        for result in session.results:
            if not result.efficacy_data:
                continue

            drug_id = result.drug.drug_id

            with self.db.cursor() as cur:
                for dp in result.efficacy_data:
                    try:
                        # Truncate fields to fit varchar limits
                        nct_id = dp.nct_id[:20] if dp.nct_id and len(dp.nct_id) > 20 else dp.nct_id
                        pmid = dp.pmid[:20] if dp.pmid and len(dp.pmid) > 20 else dp.pmid
                        endpoint_type = dp.endpoint_type[:50] if dp.endpoint_type and len(dp.endpoint_type) > 50 else dp.endpoint_type
                        trial_phase = dp.trial_phase[:50] if dp.trial_phase and len(dp.trial_phase) > 50 else dp.trial_phase
                        result_unit = dp.drug_arm_result_unit[:50] if dp.drug_arm_result_unit and len(dp.drug_arm_result_unit) > 50 else dp.drug_arm_result_unit

                        # Use INSERT with all fields including new benchmark fields
                        cur.execute("""
                            INSERT INTO drug_efficacy_data (
                                drug_id, trial_name, endpoint_name, endpoint_type,
                                drug_arm_name, drug_arm_n, drug_arm_result, drug_arm_result_unit,
                                comparator_arm_name, comparator_arm_n, comparator_arm_result,
                                p_value, confidence_interval, timepoint, trial_phase, nct_id,
                                population, indication_name, confidence_score, data_source,
                                source_url, pmid, review_status, raw_source_text
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s
                            )
                        """, (
                            drug_id,
                            dp.trial_name,
                            dp.endpoint_name,
                            endpoint_type,
                            dp.drug_arm_name,
                            dp.drug_arm_n,
                            dp.drug_arm_result,
                            result_unit,
                            dp.comparator_arm_name,
                            dp.comparator_arm_n,
                            dp.comparator_arm_result,
                            dp.p_value,
                            dp.confidence_interval,
                            dp.timepoint,
                            trial_phase,
                            nct_id,
                            dp.population,
                            dp.indication_name,
                            dp.confidence_score,
                            dp.source_type.value,
                            dp.source_url,
                            pmid,
                            dp.review_status.value,
                            dp.raw_source_text,
                        ))
                    except Exception as e:
                        logger.error(f"Failed to store efficacy data point: {e}")
                        # Rollback this transaction to prevent blocking
                        self.db.conn.rollback()

                self.db.commit()

        logger.info(f"Stored {session.total_data_points} efficacy data points")

    def update_review_status(
        self,
        efficacy_id: int,
        new_status: ReviewStatus,
        note: Optional[str] = None
    ) -> bool:
        """
        Update review status for a data point (user override).

        Args:
            efficacy_id: Database ID of the efficacy data point
            new_status: New review status
            note: Optional user note

        Returns:
            True if update succeeded
        """
        try:
            self.db.ensure_connected()
            with self.db.cursor() as cur:
                cur.execute("""
                    UPDATE drug_efficacy_data
                    SET review_status = %s, user_override_note = %s, updated_at = NOW()
                    WHERE efficacy_id = %s
                """, (new_status.value, note, efficacy_id))
                self.db.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to update review status: {e}")
            return False

    def get_existing_efficacy_data(
        self,
        disease_name: str,
        drug_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get existing efficacy data for a disease from the database.

        Args:
            disease_name: Disease name to filter by
            drug_ids: Optional list of drug IDs to filter

        Returns:
            List of efficacy data records
        """
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            if drug_ids:
                cur.execute("""
                    SELECT ed.*, d.generic_name, d.brand_name
                    FROM drug_efficacy_data ed
                    JOIN drugs d ON ed.drug_id = d.drug_id
                    WHERE ed.indication_name ILIKE %s
                      AND ed.drug_id = ANY(%s)
                      AND ed.review_status != 'user_rejected'
                    ORDER BY d.generic_name, ed.endpoint_name
                """, (f"%{disease_name}%", drug_ids))
            else:
                cur.execute("""
                    SELECT ed.*, d.generic_name, d.brand_name
                    FROM drug_efficacy_data ed
                    JOIN drugs d ON ed.drug_id = d.drug_id
                    WHERE ed.indication_name ILIKE %s
                      AND ed.review_status != 'user_rejected'
                    ORDER BY d.generic_name, ed.endpoint_name
                """, (f"%{disease_name}%",))

            return [dict(row) for row in cur.fetchall()]

    def clear_disease_efficacy_data(
        self,
        disease_name: str,
        drug_ids: Optional[List[int]] = None
    ) -> int:
        """
        Clear efficacy data for a disease (for re-extraction).

        Args:
            disease_name: Disease name to match
            drug_ids: Optional list of specific drug IDs to clear

        Returns:
            Number of records deleted
        """
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            if drug_ids:
                cur.execute("""
                    DELETE FROM drug_efficacy_data
                    WHERE indication_name ILIKE %s
                      AND drug_id = ANY(%s)
                """, (f"%{disease_name}%", drug_ids))
            else:
                cur.execute("""
                    DELETE FROM drug_efficacy_data
                    WHERE indication_name ILIKE %s
                """, (f"%{disease_name}%",))

            deleted = cur.rowcount
            self.db.commit()

        logger.info(f"Cleared {deleted} efficacy records for {disease_name}")
        return deleted
