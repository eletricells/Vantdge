"""
Database interface for Off-Label Case Study Agent.

Handles all database operations for storing and retrieving case study data.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor, Json

from src.models.off_label_schemas import (
    OffLabelCaseStudy,
    OffLabelBaseline,
    OffLabelOutcome,
    OffLabelSafetyEvent
)

logger = logging.getLogger(__name__)


class OffLabelDatabase:
    """
    Database interface for off-label case studies.
    
    Provides methods to save and retrieve case study data.
    """
    
    def __init__(self, database_url: str):
        """
        Initialize database connection.

        Args:
            database_url: PostgreSQL database URL
        """
        self.database_url = database_url
        self._conn = None

    @property
    def conn(self):
        """Get persistent database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.database_url)
        return self._conn

    def _get_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.database_url)
    
    # =====================================================
    # SAVE METHODS
    # =====================================================
    
    def save_case_study(self, case_study: OffLabelCaseStudy) -> int:
        """
        Save complete case study to database.
        
        Args:
            case_study: OffLabelCaseStudy object
            
        Returns:
            case_study_id: ID of saved case study
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Insert main case study record
                case_study_id = self._insert_case_study(cur, case_study)
                
                # Insert baseline characteristics
                if case_study.baseline_characteristics:
                    self._insert_baseline(cur, case_study_id, case_study.baseline_characteristics)
                
                # Insert outcomes
                for outcome in case_study.outcomes:
                    self._insert_outcome(cur, case_study_id, outcome)
                
                # Insert safety events
                for safety_event in case_study.safety_events:
                    self._insert_safety_event(cur, case_study_id, safety_event)
                
                conn.commit()
                logger.info(f"Saved case study {case_study_id}: {case_study.title}")
                return case_study_id
                
        except psycopg2.IntegrityError as e:
            conn.rollback()
            if "unique constraint" in str(e).lower():
                logger.warning(f"Case study already exists: {case_study.pmid} - {case_study.drug_name} - {case_study.indication_treated}")
                # Get existing ID
                case_study_id = self._get_existing_case_study_id(case_study)
                return case_study_id
            else:
                raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving case study: {e}")
            raise
        finally:
            conn.close()
    
    def _insert_case_study(self, cur, case_study: OffLabelCaseStudy) -> int:
        """Insert main case study record."""
        query = """
            INSERT INTO off_label_case_studies (
                pmid, doi, pmc, title, authors, journal, year, abstract,
                study_type, relevance_score,
                drug_id, drug_name, generic_name, mechanism, target,
                indication_treated, approved_indications, is_off_label,
                n_patients,
                dosing_regimen, treatment_duration, concomitant_medications,
                response_rate, responders_n, responders_pct, time_to_response, duration_of_response,
                adverse_events, serious_adverse_events_n, discontinuations_n,
                efficacy_signal, safety_profile, mechanism_rationale, development_potential, key_findings,
                paper_path, is_open_access, citation_count,
                extracted_by, extraction_timestamp, extraction_confidence, extraction_notes,
                evidence_quality, evidence_grade,
                extraction_method, extraction_stages_completed,
                detailed_efficacy_endpoints, detailed_safety_endpoints, standard_endpoints_matched,
                search_query, search_source
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s
            )
            RETURNING case_study_id
        """

        # Serialize detailed endpoints to JSON
        detailed_efficacy_json = None
        if case_study.detailed_efficacy_endpoints:
            detailed_efficacy_json = Json([ep.model_dump() for ep in case_study.detailed_efficacy_endpoints])

        detailed_safety_json = None
        if case_study.detailed_safety_endpoints:
            detailed_safety_json = Json([ep.model_dump() for ep in case_study.detailed_safety_endpoints])

        cur.execute(query, (
            case_study.pmid, case_study.doi, case_study.pmc, case_study.title,
            case_study.authors, case_study.journal, case_study.year, case_study.abstract,
            case_study.study_type, case_study.relevance_score,
            case_study.drug_id, case_study.drug_name, case_study.generic_name,
            case_study.mechanism, case_study.target,
            case_study.indication_treated,
            Json(case_study.approved_indications) if case_study.approved_indications else None,
            case_study.is_off_label,
            case_study.n_patients,
            case_study.dosing_regimen, case_study.treatment_duration,
            Json(case_study.concomitant_medications) if case_study.concomitant_medications else None,
            case_study.response_rate, case_study.responders_n, case_study.responders_pct,
            case_study.time_to_response, case_study.duration_of_response,
            Json(case_study.adverse_events) if case_study.adverse_events else None,
            case_study.serious_adverse_events_n, case_study.discontinuations_n,
            case_study.efficacy_signal, case_study.safety_profile,
            case_study.mechanism_rationale, case_study.development_potential, case_study.key_findings,
            case_study.paper_path, case_study.is_open_access, case_study.citation_count,
            case_study.extracted_by, case_study.extraction_timestamp,
            case_study.extraction_confidence, case_study.extraction_notes,
            Json(case_study.evidence_quality) if case_study.evidence_quality else None,
            case_study.evidence_grade,
            case_study.extraction_method,
            Json(case_study.extraction_stages_completed) if case_study.extraction_stages_completed else None,
            detailed_efficacy_json,
            detailed_safety_json,
            Json(case_study.standard_endpoints_matched) if case_study.standard_endpoints_matched else None,
            case_study.search_query, case_study.search_source
        ))

        return cur.fetchone()[0]
    
    def _insert_baseline(self, cur, case_study_id: int, baseline: OffLabelBaseline):
        """Insert baseline characteristics."""
        query = """
            INSERT INTO off_label_baseline_characteristics (
                case_study_id, n,
                median_age, mean_age, age_range, age_sd,
                male_n, male_pct, female_n, female_pct,
                race_ethnicity,
                median_disease_duration, mean_disease_duration, disease_duration_unit, disease_duration_range,
                disease_severity, baseline_severity_scores,
                prior_medications_detail, prior_lines_median, prior_lines_mean,
                treatment_naive_n, treatment_naive_pct,
                prior_steroid_use_n, prior_steroid_use_pct,
                prior_biologic_use_n, prior_biologic_use_pct,
                prior_immunosuppressant_use_n, prior_immunosuppressant_use_pct,
                comorbidities, biomarkers,
                notes, source_table
            ) VALUES (
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s
            )
        """
        
        cur.execute(query, (
            case_study_id, baseline.n,
            baseline.median_age, baseline.mean_age, baseline.age_range, baseline.age_sd,
            baseline.male_n, baseline.male_pct, baseline.female_n, baseline.female_pct,
            Json(baseline.race_ethnicity) if baseline.race_ethnicity else None,
            baseline.median_disease_duration, baseline.mean_disease_duration,
            baseline.disease_duration_unit, baseline.disease_duration_range,
            baseline.disease_severity,
            Json(baseline.baseline_severity_scores) if baseline.baseline_severity_scores else None,
            Json(baseline.prior_medications_detail) if baseline.prior_medications_detail else None,
            baseline.prior_lines_median, baseline.prior_lines_mean,
            baseline.treatment_naive_n, baseline.treatment_naive_pct,
            baseline.prior_steroid_use_n, baseline.prior_steroid_use_pct,
            baseline.prior_biologic_use_n, baseline.prior_biologic_use_pct,
            baseline.prior_immunosuppressant_use_n, baseline.prior_immunosuppressant_use_pct,
            Json(baseline.comorbidities) if baseline.comorbidities else None,
            Json(baseline.biomarkers) if baseline.biomarkers else None,
            baseline.notes, baseline.source_table
        ))
    
    def _insert_outcome(self, cur, case_study_id: int, outcome: OffLabelOutcome):
        """Insert outcome record."""
        query = """
            INSERT INTO off_label_outcomes (
                case_study_id,
                outcome_category, outcome_name, outcome_description, outcome_unit,
                timepoint, timepoint_weeks,
                measurement_type,
                responders_n, responders_pct, non_responders_n,
                mean_value, median_value, sd, range_min, range_max,
                mean_change, median_change, pct_change,
                sustained_response, duration_of_response,
                p_value, ci_lower, ci_upper,
                notes, source_table
            ) VALUES (
                %s,
                %s, %s, %s, %s,
                %s, %s,
                %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s
            )
        """
        
        cur.execute(query, (
            case_study_id,
            outcome.outcome_category, outcome.outcome_name, outcome.outcome_description, outcome.outcome_unit,
            outcome.timepoint, outcome.timepoint_weeks,
            outcome.measurement_type,
            outcome.responders_n, outcome.responders_pct, outcome.non_responders_n,
            outcome.mean_value, outcome.median_value, outcome.sd, outcome.range_min, outcome.range_max,
            outcome.mean_change, outcome.median_change, outcome.pct_change,
            outcome.sustained_response, outcome.duration_of_response,
            outcome.p_value, outcome.ci_lower, outcome.ci_upper,
            outcome.notes, outcome.source_table
        ))
    
    def _insert_safety_event(self, cur, case_study_id: int, safety_event: OffLabelSafetyEvent):
        """Insert safety event record."""
        query = """
            INSERT INTO off_label_safety_events (
                case_study_id,
                event_category, event_name, event_description,
                severity,
                n_events, n_patients, incidence_pct,
                time_to_onset,
                event_outcome,
                causality_assessment,
                action_taken,
                notes, source_table
            ) VALUES (
                %s,
                %s, %s, %s,
                %s,
                %s, %s, %s,
                %s,
                %s,
                %s,
                %s,
                %s, %s
            )
        """
        
        cur.execute(query, (
            case_study_id,
            safety_event.event_category, safety_event.event_name, safety_event.event_description,
            safety_event.severity,
            safety_event.n_events, safety_event.n_patients, safety_event.incidence_pct,
            safety_event.time_to_onset,
            safety_event.event_outcome,
            safety_event.causality_assessment,
            safety_event.action_taken,
            safety_event.notes, safety_event.source_table
        ))
    
    # =====================================================
    # QUERY METHODS
    # =====================================================
    
    def get_case_studies_by_drug(self, drug_name: str) -> List[Dict[str, Any]]:
        """Get all case studies for a drug."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT * FROM off_label_case_studies
                    WHERE drug_name ILIKE %s
                    ORDER BY year DESC, relevance_score DESC
                """
                cur.execute(query, (f"%{drug_name}%",))
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()
    
    def get_case_studies_by_mechanism(self, mechanism: str) -> List[Dict[str, Any]]:
        """Get all case studies for a mechanism."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT * FROM off_label_case_studies
                    WHERE mechanism ILIKE %s
                    ORDER BY year DESC, relevance_score DESC
                """
                cur.execute(query, (f"%{mechanism}%",))
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()
    
    def get_last_search_date(self, drug_name: str) -> Optional[datetime]:
        """Get last search date for a drug."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT MAX(extraction_timestamp)
                    FROM off_label_case_studies
                    WHERE drug_name = %s
                """
                cur.execute(query, (drug_name,))
                result = cur.fetchone()
                return result[0] if result and result[0] else None
        finally:
            conn.close()
    
    def _get_existing_case_study_id(self, case_study: OffLabelCaseStudy) -> Optional[int]:
        """Get ID of existing case study."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT case_study_id FROM off_label_case_studies
                    WHERE pmid = %s AND drug_name = %s AND indication_treated = %s
                """
                cur.execute(query, (case_study.pmid, case_study.drug_name, case_study.indication_treated))
                result = cur.fetchone()
                return result[0] if result else None
        finally:
            conn.close()
    
    def check_paper_exists(self, pmid: str, drug_name: str, indication: str) -> bool:
        """Check if paper already extracted."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                query = """
                    SELECT 1 FROM off_label_case_studies
                    WHERE pmid = %s AND drug_name = %s AND indication_treated = %s
                """
                cur.execute(query, (pmid, drug_name, indication))
                return cur.fetchone() is not None
        finally:
            conn.close()

    def get_case_studies_by_drug_and_indication(
        self,
        drug_name: str,
        indication: str
    ) -> List[OffLabelCaseStudy]:
        """
        Get all case studies for a specific drug and indication.

        Args:
            drug_name: Drug name
            indication: Indication name

        Returns:
            List of OffLabelCaseStudy objects
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT * FROM off_label_case_studies
                    WHERE drug_name ILIKE %s
                    AND indication_treated ILIKE %s
                    ORDER BY year DESC, relevance_score DESC
                """
                cur.execute(query, (f"%{drug_name}%", f"%{indication}%"))
                rows = cur.fetchall()

                # Convert to OffLabelCaseStudy objects
                case_studies = []
                for row in rows:
                    # Get related data
                    case_study_id = row['case_study_id']

                    # Get baseline
                    baseline = self._get_baseline(cur, case_study_id)

                    # Get outcomes
                    outcomes = self._get_outcomes(cur, case_study_id)

                    # Get safety events
                    safety_events = self._get_safety_events(cur, case_study_id)

                    # Create OffLabelCaseStudy object
                    case_study_dict = dict(row)
                    case_study_dict['baseline_characteristics'] = baseline
                    case_study_dict['outcomes'] = outcomes
                    case_study_dict['safety_events'] = safety_events

                    case_studies.append(OffLabelCaseStudy(**case_study_dict))

                return case_studies
        finally:
            conn.close()

    def get_clinical_data_for_drug_indication(
        self,
        drug_id: int,
        indication: str
    ) -> Dict[str, Any]:
        """
        Get clinical trial data for a drug-indication pair.

        This queries the clinical_papers and related tables.

        Args:
            drug_id: Drug ID
            indication: Indication name

        Returns:
            Dict with clinical data summary
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Query clinical papers
                query = """
                    SELECT
                        cp.paper_id,
                        cp.title,
                        cp.year,
                        cp.trial_name,
                        cp.trial_phase,
                        cp.n_patients,
                        cp.primary_endpoint,
                        cp.primary_endpoint_met
                    FROM clinical_papers cp
                    WHERE cp.drug_id = %s
                    AND cp.indication ILIKE %s
                    ORDER BY cp.year DESC
                """
                cur.execute(query, (drug_id, f"%{indication}%"))
                papers = [dict(row) for row in cur.fetchall()]

                # Get efficacy data for these papers
                efficacy_data = []
                for paper in papers:
                    paper_id = paper['paper_id']

                    # Get efficacy endpoints
                    efficacy_query = """
                        SELECT * FROM efficacy_endpoints
                        WHERE paper_id = %s
                        ORDER BY is_primary DESC, endpoint_name
                    """
                    cur.execute(efficacy_query, (paper_id,))
                    endpoints = [dict(row) for row in cur.fetchall()]

                    efficacy_data.append({
                        'paper': paper,
                        'endpoints': endpoints
                    })

                return {
                    'n_trials': len(papers),
                    'trials': efficacy_data
                }
        finally:
            conn.close()

    def _get_baseline(self, cur, case_study_id: int) -> Optional[OffLabelBaseline]:
        """Get baseline characteristics for a case study."""
        query = """
            SELECT * FROM off_label_baseline_characteristics
            WHERE case_study_id = %s
        """
        cur.execute(query, (case_study_id,))
        row = cur.fetchone()

        if row:
            baseline_dict = dict(row)
            del baseline_dict['baseline_id']
            del baseline_dict['case_study_id']
            return OffLabelBaseline(**baseline_dict)
        return None

    def _get_outcomes(self, cur, case_study_id: int) -> List[OffLabelOutcome]:
        """Get outcomes for a case study."""
        query = """
            SELECT * FROM off_label_outcomes
            WHERE case_study_id = %s
            ORDER BY outcome_id
        """
        cur.execute(query, (case_study_id,))
        rows = cur.fetchall()

        outcomes = []
        for row in rows:
            outcome_dict = dict(row)
            del outcome_dict['outcome_id']
            del outcome_dict['case_study_id']
            outcomes.append(OffLabelOutcome(**outcome_dict))

        return outcomes

    def _get_safety_events(self, cur, case_study_id: int) -> List[OffLabelSafetyEvent]:
        """Get safety events for a case study."""
        query = """
            SELECT * FROM off_label_safety_events
            WHERE case_study_id = %s
            ORDER BY safety_event_id
        """
        cur.execute(query, (case_study_id,))
        rows = cur.fetchall()

        safety_events = []
        for row in rows:
            event_dict = dict(row)
            del event_dict['safety_event_id']
            del event_dict['case_study_id']
            safety_events.append(OffLabelSafetyEvent(**event_dict))

        return safety_events

