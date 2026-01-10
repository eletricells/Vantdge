"""Repository for Pipeline Intelligence database operations."""

import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from .models import PipelineSource, PipelineRun, PipelineDrug

logger = logging.getLogger(__name__)


class PipelineIntelligenceRepository:
    """Database operations for pipeline intelligence data."""

    def __init__(self, db):
        """
        Initialize repository.

        Args:
            db: Database connection (DatabaseConnection instance)
        """
        self.db = db

    def get_disease_key(self, disease_id: int) -> Optional[str]:
        """Get disease_key for a disease_id."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT disease_key FROM disease_intelligence WHERE disease_id = %s",
                (disease_id,)
            )
            result = cur.fetchone()
            return result["disease_key"] if result else None

    def get_disease_by_name(self, disease_name: str) -> Optional[Dict[str, Any]]:
        """Get disease intelligence record by name."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT disease_id, disease_name, disease_key, therapeutic_area
                FROM disease_intelligence
                WHERE LOWER(disease_name) = LOWER(%s)
                """,
                (disease_name,)
            )
            result = cur.fetchone()
            return dict(result) if result else None

    def ensure_disease(self, disease_name: str, therapeutic_area: Optional[str] = None) -> Dict[str, Any]:
        """Ensure disease exists in disease_intelligence table, creating if needed.

        Returns:
            Dict with disease_id, disease_name, disease_key
        """
        existing = self.get_disease_by_name(disease_name)
        if existing:
            return existing

        # Create new disease record
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO disease_intelligence (disease_name, therapeutic_area)
                VALUES (%s, %s)
                RETURNING disease_id, disease_name
                """,
                (disease_name, therapeutic_area)
            )
            result = cur.fetchone()
            self.db.commit()

            disease_id = result["disease_id"]

            # Generate and set disease_key
            clean_name = disease_name.upper().replace(' ', '-').replace("'", '')
            disease_key = f"DIS-{clean_name}-{disease_id:04d}"

            cur.execute(
                "UPDATE disease_intelligence SET disease_key = %s WHERE disease_id = %s",
                (disease_key, disease_id)
            )
            self.db.commit()

            logger.info(f"Created disease_intelligence record: {disease_name} (ID: {disease_id})")

            return {
                "disease_id": disease_id,
                "disease_name": disease_name,
                "disease_key": disease_key,
                "therapeutic_area": therapeutic_area
            }

    def ensure_disease_key(self, disease_id: int, disease_name: str) -> str:
        """Ensure disease has a disease_key, creating one if needed."""
        existing = self.get_disease_key(disease_id)
        if existing:
            return existing

        # Generate and set key
        clean_name = disease_name.upper().replace(' ', '-').replace("'", '')
        key = f"DIS-{clean_name}-{disease_id:04d}"
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute(
                "UPDATE disease_intelligence SET disease_key = %s WHERE disease_id = %s",
                (key, disease_id)
            )
            self.db.commit()
        return key

    # Pipeline Run operations

    def create_run(self, disease_id: int, disease_key: str, run_type: str = "full") -> int:
        """Create a new pipeline discovery run record."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO disease_pipeline_runs (disease_id, disease_key, run_type, status)
                VALUES (%s, %s, %s, 'running')
                RETURNING run_id
                """,
                (disease_id, disease_key, run_type)
            )
            result = cur.fetchone()
            self.db.commit()
            return result["run_id"]

    def update_run(
        self,
        run_id: int,
        status: str,
        clinicaltrials_searched: int = 0,
        web_sources_searched: int = 0,
        drugs_found_total: int = 0,
        drugs_new: int = 0,
        drugs_updated: int = 0,
        error_message: Optional[str] = None
    ):
        """Update a pipeline run with results."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute(
                """
                UPDATE disease_pipeline_runs
                SET status = %s,
                    clinicaltrials_searched = %s,
                    web_sources_searched = %s,
                    drugs_found_total = %s,
                    drugs_new = %s,
                    drugs_updated = %s,
                    error_message = %s
                WHERE run_id = %s
                """,
                (
                    status, clinicaltrials_searched, web_sources_searched,
                    drugs_found_total, drugs_new, drugs_updated, error_message, run_id
                )
            )
            self.db.commit()

    def get_latest_run(self, disease_id: int) -> Optional[PipelineRun]:
        """Get most recent pipeline run for a disease."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM disease_pipeline_runs
                WHERE disease_id = %s
                ORDER BY run_timestamp DESC
                LIMIT 1
                """,
                (disease_id,)
            )
            result = cur.fetchone()
            return PipelineRun(**dict(result)) if result else None

    # Pipeline Source operations

    def add_source(self, source: PipelineSource) -> int:
        """Add a pipeline source record."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            # Serialize extracted_data to JSON
            extracted_json = json.dumps(source.extracted_data) if source.extracted_data else None

            cur.execute(
                """
                INSERT INTO disease_pipeline_sources
                (disease_id, drug_id, nct_id, source_url, source_type, title,
                 publication_date, content_summary, extracted_data, confidence_score, verified)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING source_id
                """,
                (
                    source.disease_id, source.drug_id, source.nct_id, source.source_url,
                    source.source_type, source.title, source.publication_date,
                    source.content_summary, extracted_json, source.confidence_score,
                    source.verified
                )
            )
            result = cur.fetchone()
            self.db.commit()
            return result["source_id"] if result else 0

    def get_sources_for_disease(self, disease_id: int) -> List[PipelineSource]:
        """Get all pipeline sources for a disease."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM disease_pipeline_sources
                WHERE disease_id = %s
                ORDER BY publication_date DESC NULLS LAST
                """,
                (disease_id,)
            )
            results = cur.fetchall()
            return [PipelineSource(**dict(r)) for r in results]

    # Drug Database operations (links to existing drugs table)

    def find_drug_by_name(self, generic_name: str, brand_name: Optional[str] = None) -> Optional[Dict]:
        """Find existing drug in database."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            if brand_name:
                cur.execute(
                    """
                    SELECT * FROM drugs
                    WHERE LOWER(generic_name) = LOWER(%s) OR LOWER(brand_name) = LOWER(%s)
                    LIMIT 1
                    """,
                    (generic_name, brand_name)
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM drugs
                    WHERE LOWER(generic_name) = LOWER(%s)
                    LIMIT 1
                    """,
                    (generic_name,)
                )
            result = cur.fetchone()
            return dict(result) if result else None

    def upsert_drug(self, drug: PipelineDrug) -> int:
        """Insert or update a drug in the database."""
        existing = self.find_drug_by_name(drug.generic_name, drug.brand_name)

        self.db.ensure_connected()
        with self.db.cursor() as cur:
            if existing:
                # Update existing drug
                cur.execute(
                    """
                    UPDATE drugs
                    SET manufacturer = COALESCE(%s, manufacturer),
                        drug_type = COALESCE(%s, drug_type),
                        mechanism_of_action = COALESCE(%s, mechanism_of_action),
                        approval_status = %s,
                        highest_phase = COALESCE(%s, highest_phase),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE drug_id = %s
                    """,
                    (
                        drug.manufacturer, drug.drug_type, drug.mechanism_of_action,
                        drug.approval_status, drug.highest_phase, existing["drug_id"]
                    )
                )
                self.db.commit()
                return existing["drug_id"]
            else:
                # Insert new drug
                cur.execute(
                    """
                    INSERT INTO drugs
                    (brand_name, generic_name, manufacturer, drug_type, mechanism_of_action,
                     approval_status, highest_phase, first_approval_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING drug_id
                    """,
                    (
                        drug.brand_name, drug.generic_name, drug.manufacturer,
                        drug.drug_type, drug.mechanism_of_action,
                        drug.approval_status, drug.highest_phase, drug.first_approval_date
                    )
                )
                result = cur.fetchone()
                self.db.commit()
                return result["drug_id"]

    def ensure_disease_in_drug_db(self, disease_name: str, therapeutic_area: Optional[str] = None) -> int:
        """Ensure disease exists in the drugs database diseases table."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT disease_id FROM diseases
                WHERE LOWER(disease_name_standard) = LOWER(%s)
                """,
                (disease_name,)
            )
            existing = cur.fetchone()

            if existing:
                return existing["disease_id"]

            # Create new disease
            cur.execute(
                """
                INSERT INTO diseases (disease_name_standard, therapeutic_area)
                VALUES (%s, %s)
                RETURNING disease_id
                """,
                (disease_name, therapeutic_area)
            )
            result = cur.fetchone()
            self.db.commit()
            return result["disease_id"]

    def link_drug_to_disease(
        self,
        drug_id: int,
        disease_id: int,
        disease_name: str,
        approval_status: str = "investigational",
        line_of_therapy: Optional[str] = None,
        data_source: str = "ClinicalTrials.gov"
    ):
        """Create drug-disease indication link."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO drug_indications
                (drug_id, disease_id, disease_name, approval_status, line_of_therapy, data_source)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (drug_id, disease_id, line_of_therapy)
                DO UPDATE SET
                    approval_status = EXCLUDED.approval_status,
                    data_source = EXCLUDED.data_source,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (drug_id, disease_id, disease_name, approval_status, line_of_therapy or "any", data_source)
            )
            self.db.commit()

    def get_pipeline_for_disease(self, disease_name: str) -> List[Dict]:
        """Get all pipeline drugs for a disease from drug database."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    d.drug_id, d.brand_name, d.generic_name, d.manufacturer,
                    d.drug_type, d.mechanism_of_action, d.approval_status,
                    d.highest_phase, d.first_approval_date,
                    di.line_of_therapy, di.approval_status as indication_status
                FROM diseases dis
                JOIN drug_indications di ON dis.disease_id = di.disease_id
                JOIN drugs d ON di.drug_id = d.drug_id
                WHERE LOWER(dis.disease_name_standard) = LOWER(%s)
                ORDER BY
                    CASE d.highest_phase
                        WHEN 'Approved' THEN 1
                        WHEN 'Phase 3' THEN 2
                        WHEN 'Phase 2' THEN 3
                        WHEN 'Phase 1' THEN 4
                        WHEN 'Preclinical' THEN 5
                        ELSE 6
                    END
                """,
                (disease_name,)
            )
            results = cur.fetchall()
            return [dict(r) for r in results]
