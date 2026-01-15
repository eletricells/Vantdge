"""
Repository for storing and retrieving efficacy comparison data.

Provides incremental database saving during analysis to prevent data loss.
Uses psycopg2 (synchronous) to match the codebase patterns.
"""

import json
import logging
import os
from datetime import datetime
from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from src.efficacy_comparison.models import (
    ApprovedDrug,
    BaselineCharacteristics,
    DrugEfficacyProfile,
    EfficacyEndpoint,
    PivotalTrial,
    TrialExtraction,
    TrialMetadata,
)

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)


class EfficacyComparisonRepository:
    """
    Repository for saving efficacy comparison results to the database.

    Provides incremental saving after each trial extraction to prevent data loss.
    """

    def __init__(self, database_url: Optional[str] = None):
        """Initialize repository with database connection."""
        self.database_url = database_url or os.getenv("DRUG_DATABASE_URL")
        if not self.database_url:
            logger.warning(
                "DRUG_DATABASE_URL not set. Database operations will be disabled."
            )
        self.conn = None

    def _get_connection(self):
        """Get or create database connection."""
        if not self.database_url:
            raise ValueError("Database URL not configured")

        if not self.conn or self.conn.closed:
            self.conn = psycopg2.connect(self.database_url)
        return self.conn

    async def save_trial_extraction(
        self,
        drug: ApprovedDrug,
        trial: PivotalTrial,
        extraction: TrialExtraction,
        indication: str,
    ) -> int:
        """
        Save a single trial extraction to the database.

        Called after each trial is processed to ensure incremental saving.

        Args:
            drug: The drug being analyzed
            trial: The pivotal trial
            extraction: The extracted data
            indication: The indication name

        Returns:
            The trial_id of the saved record
        """
        if not self.database_url:
            logger.warning("Database not configured - skipping save")
            return -1

        conn = self._get_connection()

        try:
            # Insert or update trial record
            trial_id = self._upsert_trial(
                conn, drug, trial, extraction.metadata, indication
            )

            # Delete existing endpoints and baseline for this trial
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM efficacy_comparison_endpoints WHERE trial_id = %s",
                    (trial_id,)
                )
                cur.execute(
                    "DELETE FROM efficacy_comparison_baseline WHERE trial_id = %s",
                    (trial_id,)
                )

            # Insert baseline characteristics
            for baseline in extraction.baseline:
                self._insert_baseline(conn, trial_id, baseline)

            # Insert endpoints
            for endpoint in extraction.endpoints:
                self._insert_endpoint(conn, trial_id, endpoint)

            conn.commit()

            logger.info(
                f"Saved trial {trial.trial_name or trial.nct_id}: "
                f"{len(extraction.baseline)} arms, {len(extraction.endpoints)} endpoints"
            )

            return trial_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving trial extraction: {e}")
            raise

    def _upsert_trial(
        self,
        conn,
        drug: ApprovedDrug,
        trial: PivotalTrial,
        metadata: TrialMetadata,
        indication: str,
    ) -> int:
        """Insert or update trial record."""

        # Convert arms to JSONB
        arms_json = None
        if metadata.arms:
            arms_json = json.dumps([
                {
                    "name": a.name,
                    "n": a.n,
                    "is_active": a.is_active,
                    "dose": a.dose,
                    "frequency": a.frequency,
                }
                for a in metadata.arms
            ])

        # Convert concomitant therapies to JSONB
        concomitant_json = None
        if metadata.concomitant_therapies:
            concomitant_json = json.dumps([
                {
                    "therapy_name": t.therapy_name,
                    "is_required": t.is_required,
                    "dose_requirement": t.dose_requirement,
                    "percentage_on_therapy": t.percentage_on_therapy,
                }
                for t in metadata.concomitant_therapies
            ])

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # First try to find existing trial
            cur.execute("""
                SELECT trial_id FROM efficacy_comparison_trials
                WHERE nct_id = %s AND drug_name ILIKE %s
            """, (trial.nct_id, f"%{drug.drug_name}%"))

            existing = cur.fetchone()

            if existing:
                # Update existing
                cur.execute("""
                    UPDATE efficacy_comparison_trials SET
                        trial_name = %s,
                        trial_phase = %s,
                        total_enrollment = %s,
                        patient_population = %s,
                        patient_population_description = %s,
                        line_of_therapy = %s,
                        prior_treatment_failures_required = %s,
                        prior_treatment_failures_description = %s,
                        disease_subtype = %s,
                        disease_activity_requirement = %s,
                        arms = %s,
                        background_therapy = %s,
                        background_therapy_required = %s,
                        concomitant_therapies = %s,
                        rescue_therapy_allowed = %s,
                        rescue_therapy_description = %s,
                        primary_source_type = %s,
                        primary_source_url = %s,
                        pmid = %s,
                        pmc_id = %s,
                        extraction_confidence = %s,
                        extraction_notes = %s,
                        updated_at = NOW()
                    WHERE trial_id = %s
                    RETURNING trial_id
                """, (
                    metadata.trial_name or trial.trial_name,
                    metadata.phase or trial.phase,
                    metadata.total_enrollment or trial.enrollment,
                    metadata.patient_population,
                    metadata.patient_population_description,
                    metadata.line_of_therapy,
                    metadata.prior_treatment_failures_required,
                    metadata.prior_treatment_failures_description,
                    metadata.disease_subtype,
                    metadata.disease_activity_requirement,
                    arms_json,
                    metadata.background_therapy,
                    metadata.background_therapy_required,
                    concomitant_json,
                    metadata.rescue_therapy_allowed,
                    metadata.rescue_therapy_description,
                    metadata.source_type.value if metadata.source_type else None,
                    metadata.source_url,
                    metadata.pmid,
                    metadata.pmc_id,
                    metadata.extraction_confidence,
                    metadata.extraction_notes,
                    existing['trial_id'],
                ))
                result = cur.fetchone()
                return result['trial_id']
            else:
                # Insert new
                cur.execute("""
                    INSERT INTO efficacy_comparison_trials (
                        drug_name, generic_name, manufacturer,
                        nct_id, trial_name, trial_phase, total_enrollment,
                        indication_name,
                        patient_population, patient_population_description, line_of_therapy,
                        prior_treatment_failures_required, prior_treatment_failures_description,
                        disease_subtype, disease_activity_requirement,
                        arms, background_therapy, background_therapy_required,
                        concomitant_therapies, rescue_therapy_allowed, rescue_therapy_description,
                        primary_source_type, primary_source_url, pmid, pmc_id,
                        extraction_confidence, extraction_notes
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING trial_id
                """, (
                    drug.drug_name,
                    drug.generic_name,
                    drug.manufacturer,
                    trial.nct_id,
                    metadata.trial_name or trial.trial_name,
                    metadata.phase or trial.phase,
                    metadata.total_enrollment or trial.enrollment,
                    indication,
                    metadata.patient_population,
                    metadata.patient_population_description,
                    metadata.line_of_therapy,
                    metadata.prior_treatment_failures_required,
                    metadata.prior_treatment_failures_description,
                    metadata.disease_subtype,
                    metadata.disease_activity_requirement,
                    arms_json,
                    metadata.background_therapy,
                    metadata.background_therapy_required,
                    concomitant_json,
                    metadata.rescue_therapy_allowed,
                    metadata.rescue_therapy_description,
                    metadata.source_type.value if metadata.source_type else None,
                    metadata.source_url,
                    metadata.pmid,
                    metadata.pmc_id,
                    metadata.extraction_confidence,
                    metadata.extraction_notes,
                ))
                result = cur.fetchone()
                return result['trial_id']

    def _insert_baseline(
        self,
        conn,
        trial_id: int,
        baseline: BaselineCharacteristics,
    ):
        """Insert baseline characteristics record."""

        # Convert severity scores to JSONB
        severity_json = None
        if baseline.severity_scores:
            severity_json = json.dumps([
                {
                    "name": s.name,
                    "mean": s.mean,
                    "median": s.median,
                    "sd": s.sd,
                    "range_min": s.range_min,
                    "range_max": s.range_max,
                    "distribution": s.distribution,
                }
                for s in baseline.severity_scores
            ])

        # Convert race breakdown to JSONB (field is 'race' not 'race_breakdown')
        race_json = None
        if baseline.race:
            race_json = json.dumps(baseline.race.to_dict())

        # Convert prior treatments to JSONB (field is 'prior_treatments' not 'prior_treatments_detail')
        prior_json = None
        if baseline.prior_treatments:
            prior_json = json.dumps([
                {
                    "treatment": p.treatment,
                    "percentage": p.percentage,
                    "category": p.category,
                }
                for p in baseline.prior_treatments
            ])

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO efficacy_comparison_baseline (
                    trial_id, arm_name, n,
                    age_mean, age_median, age_sd, age_range_min, age_range_max,
                    male_pct, female_pct, race_breakdown,
                    weight_mean, weight_unit, bmi_mean,
                    disease_duration_mean, disease_duration_median, disease_duration_unit,
                    severity_scores,
                    rf_positive_pct, anti_ccp_positive_pct, seropositive_pct,
                    ana_positive_pct, anti_dsdna_positive_pct,
                    crp_mean, esr_mean,
                    prior_systemic_pct, prior_biologic_pct, prior_topical_pct,
                    prior_treatments_detail, prior_biologic_failures_mean, prior_dmard_failures_mean,
                    on_mtx_pct, on_steroids_pct, steroid_dose_mean,
                    source_table
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                trial_id,
                baseline.arm_name,
                baseline.n,
                baseline.age_mean,
                baseline.age_median,
                baseline.age_sd,
                baseline.age_range_min,
                baseline.age_range_max,
                baseline.male_pct,
                baseline.female_pct,
                race_json,
                baseline.weight_mean,
                baseline.weight_unit,
                baseline.bmi_mean,
                baseline.disease_duration_mean,
                baseline.disease_duration_median,
                baseline.disease_duration_unit,
                severity_json,
                baseline.rf_positive_pct,
                baseline.anti_ccp_positive_pct,
                baseline.seropositive_pct,
                baseline.ana_positive_pct,
                baseline.anti_dsdna_positive_pct,
                baseline.crp_mean,
                baseline.esr_mean,
                baseline.prior_systemic_pct,
                baseline.prior_biologic_pct,
                baseline.prior_topical_pct,
                prior_json,
                baseline.prior_biologic_failures_mean,
                baseline.prior_dmard_failures_mean,
                baseline.on_mtx_pct,
                baseline.on_steroids_pct,
                baseline.steroid_dose_mean,
                baseline.source_table,
            ))

    def _insert_endpoint(
        self,
        conn,
        trial_id: int,
        endpoint: EfficacyEndpoint,
    ):
        """Insert endpoint record."""

        # Parse p-value to numeric if possible
        p_value_numeric = None
        if endpoint.p_value:
            try:
                p_str = endpoint.p_value.replace('<', '').replace('>', '').strip()
                p_value_numeric = float(p_str)
            except (ValueError, AttributeError):
                pass

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO efficacy_comparison_endpoints (
                    trial_id, arm_name,
                    endpoint_name_raw, endpoint_name_normalized, endpoint_category,
                    timepoint, timepoint_weeks,
                    n_evaluated, responders_n, responders_pct,
                    mean_value, median_value, change_from_baseline, change_from_baseline_pct,
                    se, sd, ci_lower, ci_upper,
                    vs_comparator, p_value, p_value_numeric, is_statistically_significant,
                    source_table, source_text, extraction_confidence
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                trial_id,
                endpoint.arm_name,
                endpoint.endpoint_name_raw,
                endpoint.endpoint_name_normalized,
                endpoint.endpoint_category.value if endpoint.endpoint_category else None,
                endpoint.timepoint,
                endpoint.timepoint_weeks,
                endpoint.n_evaluated,
                endpoint.responders_n,
                endpoint.responders_pct,
                endpoint.mean_value,
                endpoint.median_value,
                endpoint.change_from_baseline,
                endpoint.change_from_baseline_pct,
                endpoint.se,
                endpoint.sd,
                endpoint.ci_lower,
                endpoint.ci_upper,
                endpoint.vs_comparator,
                endpoint.p_value,
                p_value_numeric,
                endpoint.is_statistically_significant,
                endpoint.source_table,
                endpoint.source_text,
                endpoint.extraction_confidence,
            ))

    async def trial_exists(
        self,
        nct_id: str,
        drug_name: str,
    ) -> bool:
        """
        Check if a trial has already been extracted.

        Useful for skip logic when resuming extraction.

        Args:
            nct_id: NCT ID of the trial
            drug_name: Drug name

        Returns:
            True if trial exists in database
        """
        if not nct_id or not self.database_url:
            return False

        conn = self._get_connection()

        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS(
                    SELECT 1 FROM efficacy_comparison_trials
                    WHERE nct_id = %s AND drug_name ILIKE %s
                )
            """, (nct_id, f"%{drug_name}%"))
            result = cur.fetchone()
            return result[0] if result else False

    async def get_existing_trials(
        self,
        indication: str,
        drug_name: Optional[str] = None,
    ) -> List[dict]:
        """
        Get existing trials for an indication from the database.

        Useful for checking what's already been extracted.

        Args:
            indication: The indication to filter by
            drug_name: Optional drug name to filter by

        Returns:
            List of trial records
        """
        if not self.database_url:
            return []

        conn = self._get_connection()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if drug_name:
                cur.execute("""
                    SELECT trial_id, drug_name, nct_id, trial_name, trial_phase,
                           patient_population, extraction_timestamp,
                           (SELECT COUNT(*) FROM efficacy_comparison_endpoints e WHERE e.trial_id = t.trial_id) as endpoint_count
                    FROM efficacy_comparison_trials t
                    WHERE indication_name ILIKE %s AND drug_name ILIKE %s
                    ORDER BY drug_name, trial_name
                """, (f"%{indication}%", f"%{drug_name}%"))
            else:
                cur.execute("""
                    SELECT trial_id, drug_name, nct_id, trial_name, trial_phase,
                           patient_population, extraction_timestamp,
                           (SELECT COUNT(*) FROM efficacy_comparison_endpoints e WHERE e.trial_id = t.trial_id) as endpoint_count
                    FROM efficacy_comparison_trials t
                    WHERE indication_name ILIKE %s
                    ORDER BY drug_name, trial_name
                """, (f"%{indication}%",))

            return [dict(row) for row in cur.fetchall()]

    async def get_endpoint_summary(
        self,
        indication: str,
        endpoint_name: Optional[str] = None,
        patient_population: Optional[str] = None,
    ) -> List[dict]:
        """
        Get summary of endpoints across drugs for comparison.

        Args:
            indication: Filter by indication
            endpoint_name: Optional filter by endpoint name
            patient_population: Optional filter by patient population

        Returns:
            List of endpoint summaries grouped by drug
        """
        if not self.database_url:
            return []

        conn = self._get_connection()

        query = """
            SELECT
                t.drug_name,
                t.trial_name,
                t.patient_population,
                e.endpoint_name_normalized,
                e.timepoint,
                e.arm_name,
                e.responders_pct,
                e.change_from_baseline,
                e.p_value
            FROM efficacy_comparison_endpoints e
            JOIN efficacy_comparison_trials t ON e.trial_id = t.trial_id
            WHERE t.indication_name ILIKE %s
        """
        params = [f"%{indication}%"]

        if endpoint_name:
            query += " AND e.endpoint_name_normalized ILIKE %s"
            params.append(f"%{endpoint_name}%")

        if patient_population:
            query += " AND t.patient_population ILIKE %s"
            params.append(f"%{patient_population}%")

        query += " ORDER BY t.drug_name, e.endpoint_name_normalized, e.timepoint"

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, tuple(params))
            return [dict(row) for row in cur.fetchall()]

    async def close(self):
        """Close database connection."""
        if self.conn and not self.conn.closed:
            self.conn.close()
            self.conn = None
