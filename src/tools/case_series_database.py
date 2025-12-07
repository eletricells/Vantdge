"""
Database interface for Case Series Workflow.

Handles progressive saving, caching, and historical run management.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor, Json

from src.models.case_series_schemas import (
    CaseSeriesExtraction,
    MarketIntelligence,
    RepurposingOpportunity,
    DrugAnalysisResult,
    AttributedSource,
    EpidemiologyData,
    StandardOfCareData,
    StandardOfCareTreatment,
    PipelineTherapy,
    OpportunityScores
)

logger = logging.getLogger(__name__)


class CaseSeriesDatabase:
    """
    Database interface for case series workflow.

    Provides methods to:
    - Save data progressively as each stage completes
    - Check cache before making API calls
    - Load historical runs
    - Track token usage and costs
    """

    def __init__(self, database_url: str, cache_max_age_days: int = 30):
        """
        Initialize database connection.

        Args:
            database_url: PostgreSQL database URL
            cache_max_age_days: Days before cached market intelligence expires
        """
        self.database_url = database_url
        self.cache_max_age_days = cache_max_age_days
        self._conn = None
        self._available = None

    @property
    def is_available(self) -> bool:
        """Check if database is available."""
        if self._available is not None:
            return self._available
        try:
            conn = self._get_connection()
            conn.close()
            self._available = True
        except Exception as e:
            logger.warning(f"Database not available: {e}")
            self._available = False
        return self._available

    def _get_connection(self):
        """Get a new database connection."""
        return psycopg2.connect(self.database_url)

    def _get_persistent_connection(self):
        """Get persistent database connection (reuses connection)."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.database_url)
        return self._conn

    # =====================================================
    # RUN MANAGEMENT
    # =====================================================

    def create_run(self, drug_name: str, parameters: Dict[str, Any]) -> str:
        """Create a new analysis run and return run_id."""
        if not self.is_available:
            return str(uuid.uuid4())  # Return fake UUID if DB unavailable

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO cs_analysis_runs (drug_name, parameters, status)
                    VALUES (%s, %s, 'in_progress')
                    RETURNING run_id
                """, (drug_name, Json(parameters)))
                run_id = str(cur.fetchone()[0])
                conn.commit()
                logger.info(f"Created analysis run {run_id} for {drug_name}")
                return run_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creating run: {e}")
            return str(uuid.uuid4())
        finally:
            conn.close()

    def update_run_status(self, run_id: str, status: str,
                          error_message: Optional[str] = None) -> None:
        """Update run status (in_progress, completed, failed)."""
        if not self.is_available:
            return

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                if status == 'completed':
                    cur.execute("""
                        UPDATE cs_analysis_runs
                        SET status = %s, completed_at = CURRENT_TIMESTAMP
                        WHERE run_id = %s
                    """, (status, run_id))
                elif status == 'failed':
                    cur.execute("""
                        UPDATE cs_analysis_runs
                        SET status = %s, completed_at = CURRENT_TIMESTAMP, error_message = %s
                        WHERE run_id = %s
                    """, (status, error_message, run_id))
                else:
                    cur.execute("""
                        UPDATE cs_analysis_runs SET status = %s WHERE run_id = %s
                    """, (status, run_id))
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating run status: {e}")
        finally:
            conn.close()

    def update_run_stats(self, run_id: str, **kwargs) -> None:
        """Update run statistics (papers_found, tokens, etc.)."""
        if not self.is_available:
            return

        valid_fields = {
            'papers_found', 'papers_extracted', 'opportunities_found',
            'total_input_tokens', 'total_output_tokens', 'estimated_cost_usd',
            'papers_from_cache', 'market_intel_from_cache', 'tokens_saved_by_cache'
        }
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        if not updates:
            return

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                set_clause = ", ".join(f"{k} = %s" for k in updates.keys())
                values = list(updates.values()) + [run_id]
                cur.execute(f"""
                    UPDATE cs_analysis_runs SET {set_clause} WHERE run_id = %s
                """, values)
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error updating run stats: {e}")
        finally:
            conn.close()

    # =====================================================
    # DRUG CACHING
    # =====================================================

    def check_drug_exists(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Check if drug info is cached. Returns drug data or None."""
        if not self.is_available:
            return None

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT drug_name, generic_name, mechanism, target,
                           approved_indications, data_sources, fetched_at
                    FROM cs_drugs WHERE LOWER(drug_name) = LOWER(%s)
                """, (drug_name,))
                row = cur.fetchone()
                if row:
                    logger.info(f"Found cached drug info for {drug_name}")
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Error checking drug cache: {e}")
            return None
        finally:
            conn.close()

    def save_drug(self, drug_name: str, generic_name: Optional[str],
                  mechanism: Optional[str], target: Optional[str],
                  approved_indications: List[str], data_sources: List[str]) -> None:
        """Save or update drug info in cache."""
        if not self.is_available:
            return

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO cs_drugs (drug_name, generic_name, mechanism, target,
                                          approved_indications, data_sources)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (drug_name) DO UPDATE SET
                        generic_name = EXCLUDED.generic_name,
                        mechanism = EXCLUDED.mechanism,
                        target = EXCLUDED.target,
                        approved_indications = EXCLUDED.approved_indications,
                        data_sources = EXCLUDED.data_sources,
                        updated_at = CURRENT_TIMESTAMP
                """, (drug_name, generic_name, mechanism, target,
                      Json(approved_indications), Json(data_sources)))
                conn.commit()
                logger.info(f"Saved drug info for {drug_name}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving drug: {e}")
        finally:
            conn.close()

    # =====================================================
    # PAPER CACHING (with relevance filtering)
    # =====================================================

    def check_paper_relevance(self, pmid: str, drug_name: str) -> Optional[Dict[str, Any]]:
        """Check if paper relevance has been assessed for this drug."""
        if not self.is_available or not pmid:
            return None

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT pmid, is_relevant, relevance_score, relevance_reason,
                           extracted_disease, title, abstract
                    FROM cs_papers
                    WHERE pmid = %s AND relevance_drug = %s
                """, (pmid, drug_name))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error checking paper relevance: {e}")
            return None
        finally:
            conn.close()

    def save_paper(self, pmid: str, drug_name: str, title: str,
                   abstract: Optional[str] = None, year: Optional[int] = None,
                   is_relevant: Optional[bool] = None, relevance_score: Optional[float] = None,
                   relevance_reason: Optional[str] = None, extracted_disease: Optional[str] = None,
                   **kwargs) -> None:
        """Save paper with relevance assessment."""
        if not self.is_available or not pmid:
            return

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO cs_papers (pmid, relevance_drug, title, abstract, year,
                                           is_relevant, relevance_score, relevance_reason,
                                           extracted_disease, source, journal, authors)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (pmid, relevance_drug) DO UPDATE SET
                        is_relevant = EXCLUDED.is_relevant,
                        relevance_score = EXCLUDED.relevance_score,
                        relevance_reason = EXCLUDED.relevance_reason,
                        extracted_disease = EXCLUDED.extracted_disease
                """, (pmid, drug_name, title, abstract, year,
                      is_relevant, relevance_score, relevance_reason, extracted_disease,
                      kwargs.get('source'), kwargs.get('journal'), kwargs.get('authors')))
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving paper: {e}")
        finally:
            conn.close()


    # =====================================================
    # EXTRACTION CACHING
    # =====================================================

    def check_extraction_exists(self, pmid: str, drug_name: str, disease: str) -> Optional[Dict[str, Any]]:
        """Check if extraction exists for this paper/drug/disease combo."""
        if not self.is_available or not pmid:
            return None

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, full_extraction, extracted_at
                    FROM cs_extractions
                    WHERE pmid = %s AND drug_name = %s AND disease = %s
                """, (pmid, drug_name, disease))
                row = cur.fetchone()
                if row and row.get('full_extraction'):
                    logger.info(f"Found cached extraction for PMID {pmid}, {disease}")
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Error checking extraction cache: {e}")
            return None
        finally:
            conn.close()

    def save_extraction(self, run_id: str, extraction: CaseSeriesExtraction,
                        drug_name: str) -> Optional[int]:
        """Save case series extraction to database. Returns extraction ID."""
        if not self.is_available:
            return None

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Extract nested data safely
                source = extraction.source
                patient_pop = extraction.patient_population
                treatment = extraction.treatment
                efficacy = extraction.efficacy
                safety = extraction.safety

                # Handle prior_treatments - can be list or string
                prior_treatments = None
                if hasattr(patient_pop, 'prior_treatments_failed') and patient_pop.prior_treatments_failed:
                    prior_treatments = ', '.join(patient_pop.prior_treatments_failed)
                elif hasattr(patient_pop, 'prior_treatments') and patient_pop.prior_treatments:
                    prior_treatments = patient_pop.prior_treatments if isinstance(patient_pop.prior_treatments, str) else ', '.join(patient_pop.prior_treatments)

                cur.execute("""
                    INSERT INTO cs_extractions (
                        run_id, pmid, paper_title, paper_year, drug_name, disease, is_off_label,
                        n_patients, age_description, gender_distribution, disease_severity, prior_treatments,
                        dosing_regimen, treatment_duration, concomitant_medications,
                        response_rate, responders_n, responders_pct, time_to_response, duration_of_response,
                        primary_endpoint, primary_endpoint_result, efficacy_summary, efficacy_signal,
                        adverse_events, serious_adverse_events, sae_count, sae_percentage, discontinuations_n,
                        safety_summary, safety_profile, evidence_level, study_design, follow_up_duration,
                        key_findings, full_extraction
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s
                    )
                    ON CONFLICT (pmid, drug_name, disease) DO UPDATE SET
                        run_id = EXCLUDED.run_id,
                        full_extraction = EXCLUDED.full_extraction,
                        extracted_at = CURRENT_TIMESTAMP
                    RETURNING id
                """, (
                    run_id, source.pmid, source.title, source.year, drug_name,
                    extraction.disease, extraction.is_off_label,
                    patient_pop.n_patients if patient_pop else None,
                    patient_pop.age_description if patient_pop else None,
                    patient_pop.sex_distribution if patient_pop else None,  # Model uses sex_distribution
                    patient_pop.disease_severity if patient_pop else None,
                    prior_treatments,
                    treatment.dosing_regimen if treatment else None,
                    treatment.treatment_duration if treatment else None,
                    Json(treatment.concomitant_medications) if treatment and treatment.concomitant_medications else None,
                    efficacy.response_rate if efficacy else None,
                    efficacy.responders_n if efficacy else None,
                    efficacy.responders_pct if efficacy else None,
                    efficacy.time_to_response if efficacy else None,
                    efficacy.duration_of_response if efficacy else None,
                    efficacy.primary_endpoint if efficacy else None,
                    efficacy.primary_endpoint_result if efficacy else None,
                    efficacy.efficacy_summary if efficacy else None,
                    efficacy.efficacy_signal.value if efficacy and efficacy.efficacy_signal else None,
                    Json([ae.model_dump() for ae in safety.adverse_events]) if safety and safety.adverse_events else None,
                    Json([sae.model_dump() for sae in safety.serious_adverse_events]) if safety and safety.serious_adverse_events else None,
                    safety.sae_count if safety else None,
                    safety.sae_percentage if safety else None,
                    safety.discontinuations_n if safety else None,
                    safety.safety_summary if safety else None,
                    safety.safety_profile.value if safety and safety.safety_profile else None,
                    extraction.evidence_level.value if extraction.evidence_level else None,
                    source.study_type if source else None,
                    extraction.follow_up_duration,
                    extraction.key_findings,
                    Json(extraction.model_dump())
                ))
                extraction_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"Saved extraction {extraction_id} for {extraction.disease}")
                return extraction_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving extraction: {e}")
            return None
        finally:
            conn.close()

    def load_extraction(self, drug_name: str, pmid: str) -> Optional[CaseSeriesExtraction]:
        """Load extraction from database by drug name and PMID."""
        if not self.is_available or not pmid:
            return None

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT full_extraction FROM cs_extractions
                    WHERE drug_name = %s AND pmid = %s
                """, (drug_name, pmid))
                row = cur.fetchone()
                if row and row.get('full_extraction'):
                    return CaseSeriesExtraction.model_validate(row['full_extraction'])
                return None
        except Exception as e:
            logger.error(f"Error loading extraction: {e}")
            return None
        finally:
            conn.close()

    def load_extraction_by_id(self, extraction_id: int) -> Optional[CaseSeriesExtraction]:
        """Load extraction from database by ID."""
        if not self.is_available:
            return None

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT full_extraction FROM cs_extractions WHERE id = %s
                """, (extraction_id,))
                row = cur.fetchone()
                if row and row.get('full_extraction'):
                    return CaseSeriesExtraction.model_validate(row['full_extraction'])
                return None
        except Exception as e:
            logger.error(f"Error loading extraction by ID: {e}")
            return None
        finally:
            conn.close()


    # =====================================================
    # MARKET INTELLIGENCE CACHING
    # =====================================================

    def check_market_intel_fresh(self, disease: str) -> Optional[MarketIntelligence]:
        """Check if market intelligence is cached and not expired."""
        if not self.is_available:
            return None

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Query using the actual schema columns
                cur.execute("""
                    SELECT disease, prevalence, incidence, approved_drugs,
                           treatment_paradigm, unmet_needs, pipeline_drugs,
                           tam_estimate, tam_growth_rate, market_dynamics,
                           sources_epidemiology, sources_approved_drugs, sources_treatment,
                           sources_pipeline, sources_tam, fetched_at, expires_at
                    FROM cs_market_intelligence
                    WHERE LOWER(disease) = LOWER(%s) AND expires_at > CURRENT_TIMESTAMP
                """, (disease,))
                row = cur.fetchone()
                if row:
                    logger.info(f"Found fresh cached market intel for {disease}")
                    # Reconstruct MarketIntelligence from stored columns
                    from src.models.case_series_schemas import Epidemiology, StandardOfCare, AttributedSource

                    epi = Epidemiology(
                        prevalence=row.get('prevalence'),
                        us_prevalence_estimate=row.get('prevalence')
                    ) if row.get('prevalence') else None

                    soc = StandardOfCare(
                        approved_drug_names=row.get('approved_drugs') or [],
                        treatment_paradigm=row.get('treatment_paradigm'),
                        unmet_need=bool(row.get('unmet_needs')),
                        unmet_need_description=row.get('unmet_needs'),
                        pipeline_therapies=[]
                    ) if row.get('approved_drugs') or row.get('treatment_paradigm') else None

                    # Build attributed sources from stored source arrays
                    attributed = []
                    for url in (row.get('sources_epidemiology') or []):
                        attributed.append(AttributedSource(url=url, attribution='Epidemiology'))
                    for url in (row.get('sources_approved_drugs') or []):
                        attributed.append(AttributedSource(url=url, attribution='Approved Treatments'))
                    for url in (row.get('sources_pipeline') or []):
                        attributed.append(AttributedSource(url=url, attribution='Pipeline/Clinical Trials'))
                    for url in (row.get('sources_tam') or []):
                        attributed.append(AttributedSource(url=url, attribution='TAM/Market Analysis'))

                    return MarketIntelligence(
                        disease=row.get('disease'),
                        epidemiology=epi,
                        standard_of_care=soc,
                        tam_estimate=row.get('tam_estimate'),
                        growth_rate=row.get('tam_growth_rate'),
                        unmet_needs=row.get('unmet_needs'),
                        attributed_sources=attributed,
                        pipeline_sources=row.get('sources_pipeline') or [],
                        tam_sources=row.get('sources_tam') or []
                    )
                return None
        except Exception as e:
            logger.error(f"Error checking market intel cache: {e}")
            return None
        finally:
            conn.close()

    def save_market_intelligence(self, mi: MarketIntelligence) -> None:
        """Save market intelligence to cache with expiration."""
        if not self.is_available:
            return

        expires_at = datetime.now() + timedelta(days=self.cache_max_age_days)

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Extract source URLs by category
                sources_epi = []
                sources_drugs = []
                sources_treatment = []
                sources_pipeline = []
                sources_tam = []

                for src in mi.attributed_sources or []:
                    if src.attribution == 'Epidemiology':
                        sources_epi.append(src.url or src.title)
                    elif src.attribution == 'Approved Treatments':
                        sources_drugs.append(src.url or src.title)
                    elif src.attribution == 'Treatment Paradigm':
                        sources_treatment.append(src.url or src.title)
                    elif src.attribution == 'Pipeline/Clinical Trials':
                        sources_pipeline.append(src.url or src.title)
                    elif src.attribution == 'TAM/Market Analysis':
                        sources_tam.append(src.url or src.title)

                # Also include direct source lists
                sources_pipeline.extend(mi.pipeline_sources or [])
                sources_tam.extend(mi.tam_sources or [])

                # Get values from nested objects safely
                prevalence = mi.epidemiology.prevalence if mi.epidemiology else None
                incidence = mi.epidemiology.us_incidence_estimate if mi.epidemiology else None
                approved_drugs = mi.standard_of_care.approved_drug_names if mi.standard_of_care else []
                treatment_paradigm = mi.standard_of_care.treatment_paradigm if mi.standard_of_care else None
                pipeline_drugs = []
                if mi.standard_of_care and mi.standard_of_care.pipeline_therapies:
                    pipeline_drugs = [p.model_dump() for p in mi.standard_of_care.pipeline_therapies]

                cur.execute("""
                    INSERT INTO cs_market_intelligence (
                        disease, prevalence, incidence, approved_drugs,
                        treatment_paradigm, unmet_needs, pipeline_drugs,
                        tam_estimate, tam_growth_rate, market_dynamics,
                        sources_epidemiology, sources_approved_drugs, sources_treatment,
                        sources_pipeline, sources_tam, expires_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (disease) DO UPDATE SET
                        prevalence = EXCLUDED.prevalence,
                        approved_drugs = EXCLUDED.approved_drugs,
                        tam_estimate = EXCLUDED.tam_estimate,
                        sources_epidemiology = EXCLUDED.sources_epidemiology,
                        sources_tam = EXCLUDED.sources_tam,
                        fetched_at = CURRENT_TIMESTAMP,
                        expires_at = EXCLUDED.expires_at
                """, (
                    mi.disease,
                    prevalence, incidence, Json(approved_drugs),
                    treatment_paradigm, mi.unmet_needs, Json(pipeline_drugs),
                    mi.tam_estimate, mi.growth_rate, None,  # market_dynamics
                    Json(sources_epi), Json(sources_drugs), Json(sources_treatment),
                    Json(sources_pipeline), Json(sources_tam), expires_at
                ))
                conn.commit()
                logger.info(f"Saved market intel for {mi.disease}, expires {expires_at}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving market intel: {e}")
        finally:
            conn.close()


    # =====================================================
    # OPPORTUNITIES
    # =====================================================

    def save_opportunity(self, run_id: str, extraction_id: int,
                         opportunity: RepurposingOpportunity, drug_name: str) -> None:
        """Save scored opportunity to database."""
        if not self.is_available:
            return

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                scores = opportunity.scores
                extraction = opportunity.extraction

                # Get market intel if available
                market_tam = None
                market_prevalence = None
                market_unmet_needs = None
                if opportunity.market_intelligence:
                    mi = opportunity.market_intelligence
                    market_tam = mi.tam_estimate
                    market_prevalence = mi.epidemiology.prevalence if mi.epidemiology else None
                    market_unmet_needs = mi.unmet_needs

                # Use correct attribute names (patient_population, efficacy instead of baseline, outcomes)
                n_patients = None
                if hasattr(extraction, 'patient_population') and extraction.patient_population:
                    n_patients = extraction.patient_population.n_patients

                response_rate = None
                efficacy_signal_val = None
                if hasattr(extraction, 'efficacy') and extraction.efficacy:
                    response_rate = extraction.efficacy.responders_pct
                    if extraction.efficacy.efficacy_signal:
                        efficacy_signal_val = extraction.efficacy.efficacy_signal.value

                safety_profile_val = None
                if hasattr(extraction, 'safety') and extraction.safety and extraction.safety.safety_profile:
                    safety_profile_val = extraction.safety.safety_profile.value

                cur.execute("""
                    INSERT INTO cs_opportunities (
                        run_id, drug_name, disease,
                        total_patients, paper_count, avg_response_rate,
                        efficacy_signal, safety_profile, evidence_level,
                        score_efficacy, score_safety, score_evidence, score_market, score_feasibility,
                        score_total, rank,
                        market_tam, market_prevalence, market_unmet_needs,
                        recommendation, key_findings, pmids
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id, drug_name, disease) DO UPDATE SET
                        score_total = EXCLUDED.score_total,
                        rank = EXCLUDED.rank
                """, (
                    run_id, drug_name, extraction.disease,
                    n_patients,
                    1,  # paper_count - single paper per extraction
                    response_rate,
                    efficacy_signal_val,
                    safety_profile_val,
                    extraction.evidence_level.value if extraction.evidence_level else None,
                    scores.clinical_signal,
                    scores.response_rate_score,  # Using as safety proxy
                    scores.evidence_quality,
                    scores.market_opportunity,
                    scores.sample_size_score,  # Using as feasibility proxy
                    scores.overall_priority,
                    opportunity.rank,
                    market_tam, market_prevalence, market_unmet_needs,
                    None,  # recommendation
                    extraction.key_findings,
                    Json([extraction.source.pmid] if extraction.source and extraction.source.pmid else [])
                ))
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving opportunity: {e}")
        finally:
            conn.close()

    # =====================================================
    # HISTORICAL RUNS
    # =====================================================

    def get_historical_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get list of historical analysis runs."""
        if not self.is_available:
            return []

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT run_id, drug_name, started_at, completed_at, status,
                           papers_found, papers_extracted, opportunities_found,
                           estimated_cost_usd, papers_from_cache, market_intel_from_cache,
                           tokens_saved_by_cache,
                           EXTRACT(EPOCH FROM (completed_at - started_at)) as duration_seconds
                    FROM cs_analysis_runs
                    ORDER BY started_at DESC
                    LIMIT %s
                """, (limit,))
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error getting historical runs: {e}")
            return []
        finally:
            conn.close()

    def get_run_details(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get full details of a specific run including extractions and opportunities."""
        if not self.is_available:
            return None

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get run info
                cur.execute("""
                    SELECT * FROM cs_analysis_runs WHERE run_id = %s
                """, (run_id,))
                run = cur.fetchone()
                if not run:
                    return None

                result = dict(run)

                # Get extractions
                cur.execute("""
                    SELECT id, pmid, paper_title, disease, n_patients,
                           response_rate, efficacy_signal, safety_profile,
                           full_extraction
                    FROM cs_extractions WHERE run_id = %s
                """, (run_id,))
                result['extractions'] = [dict(row) for row in cur.fetchall()]

                # Get opportunities (join on disease since we don't have extraction_id)
                cur.execute("""
                    SELECT * FROM cs_opportunities
                    WHERE run_id = %s
                    ORDER BY score_total DESC NULLS LAST
                """, (run_id,))
                result['opportunities'] = [dict(row) for row in cur.fetchall()]

                return result
        except Exception as e:
            logger.error(f"Error getting run details: {e}")
            return None
        finally:
            conn.close()

    def load_run_as_result(self, run_id: str) -> Optional[DrugAnalysisResult]:
        """Load a historical run as a DrugAnalysisResult object."""
        if not self.is_available:
            return None

        details = self.get_run_details(run_id)
        if not details:
            return None

        try:
            # Reconstruct opportunities from stored data
            opportunities = []
            for ext_row in details.get('extractions', []):
                if ext_row.get('full_extraction'):
                    extraction = CaseSeriesExtraction.model_validate(ext_row['full_extraction'])

                    # Find matching opportunity scores by disease
                    opp_row = next(
                        (o for o in details.get('opportunities', [])
                         if o.get('disease') == extraction.disease),
                        None
                    )

                    scores = OpportunityScores()
                    rank = None
                    if opp_row:
                        scores = OpportunityScores(
                            clinical_signal=float(opp_row.get('score_efficacy') or 5),
                            evidence_quality=float(opp_row.get('score_evidence') or 5),
                            market_opportunity=float(opp_row.get('score_market') or 5),
                            overall_priority=float(opp_row.get('score_total') or 5)
                        )
                        rank = opp_row.get('rank')

                    opportunities.append(RepurposingOpportunity(
                        extraction=extraction,
                        scores=scores,
                        rank=rank
                    ))

            return DrugAnalysisResult(
                drug_name=details['drug_name'],
                opportunities=opportunities,
                papers_screened=details.get('papers_found', 0),
                papers_extracted=details.get('papers_extracted', 0),
                total_input_tokens=details.get('total_input_tokens', 0),
                total_output_tokens=details.get('total_output_tokens', 0),
                estimated_cost_usd=float(details.get('estimated_cost_usd') or 0)
            )
        except Exception as e:
            logger.error(f"Error loading run as result: {e}")
            return None