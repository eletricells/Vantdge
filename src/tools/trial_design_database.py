"""
Trial Design Database Interface

Service class for saving and retrieving trial design metadata.
Stores in main MCP database (alongside landscape_discovery_results, drugs, diseases).
"""
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime

from src.models.clinical_extraction_schemas import TrialDesignMetadata


logger = logging.getLogger(__name__)


class TrialDesignDatabase:
    """
    Database interface for trial design metadata.

    Handles CRUD operations for:
    - Trial design metadata (study design, enrollment criteria, parameters)
    """

    def __init__(self, database_url: str):
        """
        Initialize trial design database connection.

        Args:
            database_url: PostgreSQL connection string (main MCP database)
        """
        self.database_url = database_url
        self.connection = None

    @property
    def conn(self):
        """Alias for connection."""
        return self.connection

    def connect(self):
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(self.database_url)
            logger.info("Connected to trial design database")
        except Exception as e:
            logger.error(f"Failed to connect to trial design database: {e}")
            raise

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Closed trial design database connection")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # =========================================================================
    # SAVE TRIAL DESIGN
    # =========================================================================

    def save_trial_design(self, trial_design: TrialDesignMetadata) -> int:
        """
        Save trial design metadata to the database.

        Args:
            trial_design: TrialDesignMetadata object

        Returns:
            trial_design_id (primary key)
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            # Check if trial design already exists
            existing_id = self.check_trial_design_exists(trial_design.nct_id)

            if existing_id:
                logger.info(
                    f"Trial design already exists for {trial_design.nct_id} "
                    f"(ID: {existing_id}). Updating."
                )
                # Update existing record
                return self._update_trial_design(trial_design, existing_id, cursor)

            # Insert new trial design
            query = """
                INSERT INTO trial_design_metadata (
                    nct_id, indication, study_design, trial_design_summary, enrollment_summary,
                    inclusion_criteria, exclusion_criteria, primary_endpoint_description,
                    secondary_endpoints_summary, sample_size_planned, sample_size_enrolled,
                    duration_weeks, randomization_ratio, stratification_factors, blinding,
                    paper_pmid, paper_doi, paper_title, extraction_timestamp,
                    extraction_confidence, extraction_notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING trial_design_id
            """

            cursor.execute(query, (
                trial_design.nct_id,
                trial_design.indication,
                trial_design.study_design,
                trial_design.trial_design_summary,
                trial_design.enrollment_summary,
                Json(trial_design.inclusion_criteria) if trial_design.inclusion_criteria else None,
                Json(trial_design.exclusion_criteria) if trial_design.exclusion_criteria else None,
                trial_design.primary_endpoint_description,
                trial_design.secondary_endpoints_summary,
                trial_design.sample_size_planned,
                trial_design.sample_size_enrolled,
                trial_design.duration_weeks,
                trial_design.randomization_ratio,
                trial_design.stratification_factors,
                trial_design.blinding,
                trial_design.paper_pmid,
                trial_design.paper_doi,
                trial_design.paper_title,
                trial_design.extraction_timestamp,
                trial_design.extraction_confidence,
                trial_design.extraction_notes
            ))

            trial_design_id = cursor.fetchone()[0]
            self.connection.commit()
            cursor.close()

            logger.info(f"Saved trial design {trial_design_id} for {trial_design.nct_id}")
            return trial_design_id

        except Exception as e:
            logger.error(f"Failed to save trial design: {e}")
            if self.connection:
                self.connection.rollback()
            raise

    def _update_trial_design(
        self,
        trial_design: TrialDesignMetadata,
        trial_design_id: int,
        cursor
    ) -> int:
        """Update existing trial design record."""
        query = """
            UPDATE trial_design_metadata
            SET
                indication = %s,
                study_design = %s,
                trial_design_summary = %s,
                enrollment_summary = %s,
                inclusion_criteria = %s,
                exclusion_criteria = %s,
                primary_endpoint_description = %s,
                secondary_endpoints_summary = %s,
                sample_size_planned = %s,
                sample_size_enrolled = %s,
                duration_weeks = %s,
                randomization_ratio = %s,
                stratification_factors = %s,
                blinding = %s,
                paper_pmid = %s,
                paper_doi = %s,
                paper_title = %s,
                extraction_timestamp = %s,
                extraction_confidence = %s,
                extraction_notes = %s
            WHERE trial_design_id = %s
        """

        cursor.execute(query, (
            trial_design.indication,
            trial_design.study_design,
            trial_design.trial_design_summary,
            trial_design.enrollment_summary,
            Json(trial_design.inclusion_criteria) if trial_design.inclusion_criteria else None,
            Json(trial_design.exclusion_criteria) if trial_design.exclusion_criteria else None,
            trial_design.primary_endpoint_description,
            trial_design.secondary_endpoints_summary,
            trial_design.sample_size_planned,
            trial_design.sample_size_enrolled,
            trial_design.duration_weeks,
            trial_design.randomization_ratio,
            trial_design.stratification_factors,
            trial_design.blinding,
            trial_design.paper_pmid,
            trial_design.paper_doi,
            trial_design.paper_title,
            trial_design.extraction_timestamp,
            trial_design.extraction_confidence,
            trial_design.extraction_notes,
            trial_design_id
        ))

        self.connection.commit()
        logger.debug(f"Updated trial design {trial_design_id}")
        return trial_design_id

    # =========================================================================
    # CHECK EXISTENCE
    # =========================================================================

    def check_trial_design_exists(self, nct_id: str) -> Optional[int]:
        """
        Check if trial design already exists.

        Args:
            nct_id: ClinicalTrials.gov NCT ID

        Returns:
            trial_design_id if exists, None otherwise
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            cursor.execute(
                "SELECT trial_design_id FROM trial_design_metadata WHERE nct_id = %s",
                (nct_id,)
            )

            result = cursor.fetchone()
            cursor.close()

            if result:
                return result[0]
            return None

        except Exception as e:
            logger.error(f"Failed to check trial design existence: {e}")
            return None

    # =========================================================================
    # RETRIEVE TRIAL DESIGNS
    # =========================================================================

    def get_trial_design(self, nct_id: str) -> Optional[Dict[str, Any]]:
        """
        Get trial design by NCT ID.

        Args:
            nct_id: ClinicalTrials.gov NCT ID

        Returns:
            Trial design dictionary or None
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)

            cursor.execute(
                "SELECT * FROM trial_design_metadata WHERE nct_id = %s",
                (nct_id,)
            )

            result = cursor.fetchone()
            cursor.close()

            if result:
                return dict(result)
            return None

        except Exception as e:
            logger.error(f"Failed to get trial design: {e}")
            return None

    def get_trial_designs_by_indication(
        self,
        indication: str
    ) -> List[Dict[str, Any]]:
        """
        Get all trial designs for an indication.

        Args:
            indication: Disease indication

        Returns:
            List of trial design dictionaries
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)

            cursor.execute(
                "SELECT * FROM trial_design_metadata WHERE indication = %s ORDER BY extraction_timestamp DESC",
                (indication,)
            )

            results = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get trial designs by indication: {e}")
            return []

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_trial_design_stats(self) -> Dict[str, Any]:
        """
        Get trial design statistics.

        Returns:
            Dictionary with statistics
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            cursor.execute("SELECT get_trial_design_stats()")
            result = cursor.fetchone()
            cursor.close()

            if result and result[0]:
                return {
                    'total_trials': result[0],
                    'unique_indications': result[1],
                    'avg_sample_size': float(result[2]) if result[2] else None,
                    'avg_duration_weeks': float(result[3]) if result[3] else None
                }

            return {}

        except Exception as e:
            logger.error(f"Failed to get trial design stats: {e}")
            return {}
