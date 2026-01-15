"""
Case Series Browser Scoring Service

Provides dynamic scoring for the drug-centric case series browser.
- Refresh scores at drug level
- Auto-detect stale data
- Aggregate scores computed from cached individual scores
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from decimal import Decimal

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


@dataclass
class PaperScore:
    """Individual paper scoring result."""
    extraction_id: int
    pmid: str
    disease: str
    n_patients: int
    old_score: Optional[float]
    new_score: float
    changed: bool


@dataclass
class RefreshResult:
    """Result of a scoring refresh operation."""
    drug_name: str
    papers_scored: int
    papers_changed: int
    duration_seconds: float
    errors: List[str]


@dataclass
class DiseaseSummary:
    """Aggregated stats for a drug/disease combination."""
    disease: str
    disease_normalized: Optional[str]
    parent_disease: Optional[str]
    paper_count: int
    total_patients: int
    aggregate_score: float
    best_paper_score: float
    best_paper_pmid: Optional[str]
    avg_response_rate: Optional[float]
    efficacy_signal: Optional[str]
    best_evidence_level: str
    consistency_level: Optional[str]
    explanation: Optional[str] = None  # AI-generated scientific explanation
    papers: List[Dict[str, Any]] = None


@dataclass
class DrugSummary:
    """Drug-level summary for the browser."""
    drug_name: str
    drug_id: Optional[int]
    disease_count: int
    total_papers: int
    total_patients: int
    avg_disease_score: float
    top_paper_score: float
    last_scored_at: Optional[datetime]
    last_extracted_at: Optional[datetime]
    needs_refresh: bool


class BrowserScoringService:
    """
    Service for case series browser scoring operations.

    Handles:
    - Checking if scores are stale
    - Refreshing individual paper scores
    - Providing aggregated drug/disease summaries
    """

    # Staleness threshold in days
    STALE_THRESHOLD_DAYS = 7

    def __init__(self, database_url: str):
        """Initialize with database connection."""
        self.database_url = database_url
        self._scorer = None

    def _get_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.database_url)

    def _get_scorer(self):
        """Lazy-load the scorer to avoid circular imports."""
        if self._scorer is None:
            from src.case_series.scoring.case_series_scorer import CaseSeriesScorer
            self._scorer = CaseSeriesScorer()
        return self._scorer

    def get_drugs_with_extractions(self) -> List[DrugSummary]:
        """Get list of all drugs that have case series extractions."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        drug_name,
                        drug_id,
                        disease_count,
                        total_papers,
                        total_patients,
                        avg_disease_score,
                        top_paper_score,
                        last_scored_at,
                        last_extracted_at
                    FROM v_cs_drug_summary
                    ORDER BY total_papers DESC
                """)

                results = []
                now = datetime.now()

                for row in cur.fetchall():
                    last_scored = row['last_scored_at']
                    last_extracted = row['last_extracted_at']

                    # Determine if refresh needed
                    needs_refresh = False
                    if last_scored is None:
                        needs_refresh = True
                    elif last_extracted and last_extracted > last_scored:
                        needs_refresh = True
                    elif (now - last_scored).days > self.STALE_THRESHOLD_DAYS:
                        needs_refresh = True

                    results.append(DrugSummary(
                        drug_name=row['drug_name'],
                        drug_id=row['drug_id'],
                        disease_count=row['disease_count'],
                        total_papers=row['total_papers'],
                        total_patients=row['total_patients'],
                        avg_disease_score=float(row['avg_disease_score'] or 0),
                        top_paper_score=float(row['top_paper_score'] or 0),
                        last_scored_at=last_scored,
                        last_extracted_at=last_extracted,
                        needs_refresh=needs_refresh
                    ))

                return results
        finally:
            conn.close()

    def needs_refresh(self, drug_name: str) -> bool:
        """Check if a drug's scores need refreshing."""
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        MAX(scored_at) as last_scored,
                        MAX(extracted_at) as last_extracted,
                        COUNT(*) FILTER (WHERE scored_at IS NULL) as unscored_count
                    FROM cs_extractions
                    WHERE LOWER(drug_name) = LOWER(%s) AND is_relevant = true
                """, (drug_name,))

                row = cur.fetchone()
                if not row or row['last_scored'] is None:
                    return True

                if row['unscored_count'] > 0:
                    return True

                if row['last_extracted'] and row['last_extracted'] > row['last_scored']:
                    return True

                if (datetime.now() - row['last_scored']).days > self.STALE_THRESHOLD_DAYS:
                    return True

                return False
        finally:
            conn.close()

    def refresh_scores(self, drug_name: str, force: bool = False) -> RefreshResult:
        """
        Refresh all individual paper scores for a drug.

        Args:
            drug_name: Drug to refresh scores for
            force: If True, refresh even if not stale

        Returns:
            RefreshResult with stats about the refresh
        """
        from src.models.case_series_schemas import (
            CaseSeriesExtraction, CaseSeriesSource, PatientPopulation,
            TreatmentDetails, EfficacyOutcome, SafetyOutcome, BiomarkerResult
        )

        start_time = datetime.now()
        errors = []
        papers_scored = 0
        papers_changed = 0

        if not force and not self.needs_refresh(drug_name):
            logger.info(f"Scores for {drug_name} are up to date, skipping refresh")
            return RefreshResult(
                drug_name=drug_name,
                papers_scored=0,
                papers_changed=0,
                duration_seconds=0,
                errors=[]
            )

        scorer = self._get_scorer()
        conn = self._get_connection()

        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Fetch all extractions for this drug
                cur.execute("""
                    SELECT id, pmid, drug_name, disease, n_patients,
                           efficacy_signal, efficacy_summary, response_rate, responders_pct,
                           evidence_level, study_design, follow_up_duration, follow_up_weeks,
                           primary_endpoint, response_definition_quality, biomarkers_data,
                           paper_title, paper_year, individual_score
                    FROM cs_extractions
                    WHERE LOWER(drug_name) = LOWER(%s) AND is_relevant = true
                    ORDER BY n_patients DESC NULLS LAST
                """, (drug_name,))

                rows = cur.fetchall()
                logger.info(f"Refreshing scores for {len(rows)} papers ({drug_name})")

                for row in rows:
                    try:
                        # Build extraction object for scoring
                        extraction = CaseSeriesExtraction(
                            source=CaseSeriesSource(
                                pmid=row['pmid'],
                                title=row['paper_title'] or '',
                                year=row['paper_year'],
                            ),
                            disease=row['disease'] or 'Unknown',
                            evidence_level=row['evidence_level'] or 'Case Report',
                            patient_population=PatientPopulation(
                                n_patients=row['n_patients'],
                            ),
                            treatment=TreatmentDetails(
                                drug_name=drug_name,
                            ),
                            efficacy=EfficacyOutcome(
                                response_rate=row['response_rate'],
                                responders_pct=row['responders_pct'],
                                efficacy_summary=row['efficacy_summary'],
                                primary_endpoint=row['primary_endpoint'],
                            ),
                            safety=SafetyOutcome(),
                            efficacy_signal=row['efficacy_signal'] or 'Unknown',
                            study_design=row['study_design'],
                            follow_up_duration=row['follow_up_duration'],
                            follow_up_weeks=row['follow_up_weeks'],
                            response_definition_quality=row['response_definition_quality'],
                        )

                        # Parse biomarkers if present
                        if row['biomarkers_data']:
                            try:
                                biomarkers = json.loads(row['biomarkers_data']) if isinstance(row['biomarkers_data'], str) else row['biomarkers_data']
                                extraction.biomarkers = [BiomarkerResult(**b) for b in biomarkers]
                            except Exception:
                                pass

                        # Calculate score
                        score_result = scorer.score_extraction(extraction)
                        new_score = score_result.total_score
                        old_score = float(row['individual_score']) if row['individual_score'] else None

                        papers_scored += 1

                        # Update if changed
                        if old_score is None or abs(new_score - old_score) > 0.01:
                            cur.execute("""
                                UPDATE cs_extractions
                                SET individual_score = %s,
                                    score_breakdown = %s,
                                    scored_at = NOW()
                                WHERE id = %s
                            """, (
                                new_score,
                                json.dumps(score_result.model_dump()),
                                row['id']
                            ))
                            papers_changed += 1
                        else:
                            # Update scored_at even if score unchanged
                            cur.execute("""
                                UPDATE cs_extractions
                                SET scored_at = NOW()
                                WHERE id = %s
                            """, (row['id'],))

                    except Exception as e:
                        errors.append(f"PMID {row['pmid']}: {str(e)}")
                        logger.error(f"Error scoring PMID {row['pmid']}: {e}")

                conn.commit()

        finally:
            conn.close()

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Refresh complete: {papers_scored} scored, {papers_changed} changed, {duration:.1f}s")

        return RefreshResult(
            drug_name=drug_name,
            papers_scored=papers_scored,
            papers_changed=papers_changed,
            duration_seconds=duration,
            errors=errors
        )

    def get_disease_summaries(
        self,
        drug_name: str,
        min_patients: int = 0,
        evidence_filter: Optional[str] = None,
        sort_by: str = 'aggregate_score'
    ) -> List[DiseaseSummary]:
        """
        Get disease-level summaries for a drug.

        Args:
            drug_name: Drug to get summaries for
            min_patients: Minimum total patients filter
            evidence_filter: Filter by evidence level
            sort_by: Column to sort by (aggregate_score, total_patients, paper_count)

        Returns:
            List of DiseaseSummary objects
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Build query with filters
                where_clauses = ["LOWER(drug_name) = LOWER(%s)"]
                params = [drug_name]

                if min_patients > 0:
                    where_clauses.append("total_patients >= %s")
                    params.append(min_patients)

                if evidence_filter and evidence_filter != 'Any':
                    where_clauses.append("best_evidence_level = %s")
                    params.append(evidence_filter)

                # Validate sort column
                valid_sorts = ['aggregate_score', 'total_patients', 'paper_count', 'best_paper_score']
                if sort_by not in valid_sorts:
                    sort_by = 'aggregate_score'

                query = f"""
                    SELECT
                        disease,
                        disease_normalized,
                        parent_disease,
                        paper_count,
                        total_patients,
                        aggregate_score,
                        best_paper_score,
                        avg_response_rate,
                        efficacy_signal,
                        best_evidence_level
                    FROM v_cs_drug_disease_summary
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY {sort_by} DESC NULLS LAST
                """

                cur.execute(query, params)
                rows = cur.fetchall()

                results = []
                for row in rows:
                    # Get best paper PMID
                    cur.execute("""
                        SELECT pmid FROM cs_extractions
                        WHERE LOWER(drug_name) = LOWER(%s)
                          AND disease = %s
                          AND is_relevant = true
                        ORDER BY individual_score DESC NULLS LAST
                        LIMIT 1
                    """, (drug_name, row['disease']))
                    best = cur.fetchone()
                    best_pmid = best['pmid'] if best else None

                    # Get explanation from cs_opportunities
                    cur.execute("""
                        SELECT key_findings FROM cs_opportunities
                        WHERE LOWER(drug_name) = LOWER(%s)
                          AND LOWER(disease) = LOWER(%s)
                        LIMIT 1
                    """, (drug_name, row['disease']))
                    opp = cur.fetchone()
                    explanation = opp['key_findings'] if opp else None

                    results.append(DiseaseSummary(
                        disease=row['disease'],
                        disease_normalized=row['disease_normalized'],
                        parent_disease=row['parent_disease'],
                        paper_count=row['paper_count'],
                        total_patients=row['total_patients'],
                        aggregate_score=float(row['aggregate_score'] or 0),
                        best_paper_score=float(row['best_paper_score'] or 0),
                        best_paper_pmid=best_pmid,
                        avg_response_rate=float(row['avg_response_rate']) if row['avg_response_rate'] else None,
                        efficacy_signal=row['efficacy_signal'],
                        best_evidence_level=row['best_evidence_level'],
                        consistency_level=None,  # Calculated if needed
                        explanation=explanation,
                    ))

                return results
        finally:
            conn.close()

    def get_disease_papers(
        self,
        drug_name: str,
        disease: str
    ) -> List[Dict[str, Any]]:
        """
        Get individual papers for a drug/disease combination.

        Returns:
            List of paper dicts with extraction data including detailed endpoints
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        pmid,
                        paper_title,
                        paper_year,
                        n_patients,
                        responders_pct,
                        response_rate,
                        efficacy_signal,
                        efficacy_summary,
                        safety_profile,
                        safety_summary,
                        evidence_level,
                        study_design,
                        follow_up_duration,
                        individual_score,
                        scored_at,
                        full_extraction->>'extraction_method' as extraction_method,
                        full_extraction->'detailed_efficacy_endpoints' as detailed_endpoints,
                        biomarkers_data
                    FROM cs_extractions
                    WHERE LOWER(drug_name) = LOWER(%s)
                      AND disease = %s
                      AND is_relevant = true
                    ORDER BY individual_score DESC NULLS LAST
                """, (drug_name, disease))

                results = []
                for row in cur.fetchall():
                    paper = dict(row)
                    # Parse detailed endpoints if present
                    if paper.get('detailed_endpoints'):
                        endpoints = paper['detailed_endpoints']
                        if isinstance(endpoints, str):
                            paper['detailed_endpoints'] = json.loads(endpoints)
                    # Parse biomarkers if present
                    if paper.get('biomarkers_data'):
                        biomarkers = paper['biomarkers_data']
                        if isinstance(biomarkers, str):
                            paper['biomarkers_data'] = json.loads(biomarkers)
                    results.append(paper)
                return results
        finally:
            conn.close()

    def export_drug_data(self, drug_name: str) -> Dict[str, Any]:
        """
        Export all case series data for a drug (for Excel/CSV export).

        Returns:
            Dict with 'summaries' and 'papers' lists
        """
        summaries = self.get_disease_summaries(drug_name)

        all_papers = []
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        disease,
                        pmid,
                        paper_title,
                        paper_year,
                        n_patients,
                        responders_pct,
                        response_rate,
                        efficacy_signal,
                        efficacy_summary,
                        safety_profile,
                        evidence_level,
                        study_design,
                        individual_score
                    FROM cs_extractions
                    WHERE LOWER(drug_name) = LOWER(%s) AND is_relevant = true
                    ORDER BY disease, individual_score DESC NULLS LAST
                """, (drug_name,))

                all_papers = [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

        return {
            'drug_name': drug_name,
            'summaries': [
                {
                    'disease': s.disease,
                    'paper_count': s.paper_count,
                    'total_patients': s.total_patients,
                    'aggregate_score': s.aggregate_score,
                    'best_paper_score': s.best_paper_score,
                    'best_paper_pmid': s.best_paper_pmid,
                    'avg_response_rate': s.avg_response_rate,
                    'efficacy_signal': s.efficacy_signal,
                    'best_evidence_level': s.best_evidence_level,
                }
                for s in summaries
            ],
            'papers': all_papers
        }

    def get_papers_for_manual_review(self, drug_name: str) -> List[Dict[str, Any]]:
        """
        Get papers that need manual review for a drug.

        These are papers that passed filters but were extracted from abstract only
        (no full text available), ranked by patient count.

        Args:
            drug_name: Drug to get papers for

        Returns:
            List of paper dicts needing manual review
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        pmid,
                        doi,
                        title,
                        authors,
                        journal,
                        year,
                        disease,
                        n_patients,
                        n_confidence,
                        response_rate,
                        primary_endpoint,
                        efficacy_mention,
                        reason,
                        has_full_text,
                        extraction_method,
                        created_at
                    FROM cs_papers_for_manual_review
                    WHERE LOWER(drug_name) = LOWER(%s)
                    ORDER BY n_patients DESC NULLS LAST, year DESC NULLS LAST
                """, (drug_name,))

                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def get_manual_review_count(self, drug_name: str) -> int:
        """Get count of papers needing manual review for a drug."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*)
                    FROM cs_papers_for_manual_review
                    WHERE LOWER(drug_name) = LOWER(%s)
                """, (drug_name,))
                return cur.fetchone()[0]
        finally:
            conn.close()
