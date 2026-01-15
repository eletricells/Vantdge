"""
Disease Analysis - Consolidated workflow runner for multiple diseases.

Allows users to select diseases from Case Series Browser and run
Pipeline Intelligence and/or Disease Intelligence workflows in parallel.
Supports incremental updates based on last run timestamp.
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime
import asyncio
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd

# Add paths
frontend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auth import check_password, check_page_access, show_access_denied

st.set_page_config(
    page_title="Disease Analysis",
    page_icon="🔬",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

# Page access check
if not check_page_access("Disease_Analysis"):
    show_access_denied()

# Import after auth check
from dotenv import load_dotenv
load_dotenv()

import psycopg2
from psycopg2.extras import RealDictCursor
import os

from src.drug_extraction_system.database.connection import DatabaseConnection
from src.drug_extraction_system.api_clients.clinicaltrials_client import ClinicalTrialsClient
from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
from src.pipeline_intelligence.repository import PipelineIntelligenceRepository
from src.pipeline_intelligence.service import PipelineIntelligenceService
from src.disease_intelligence.repository import DiseaseIntelligenceRepository

# Import the unified orchestrator
try:
    from src.disease_analysis.orchestrator import DiseaseAnalysisOrchestrator
    from src.disease_analysis.models import UnifiedDiseaseAnalysis
    UNIFIED_ORCHESTRATOR_AVAILABLE = True
except ImportError:
    UNIFIED_ORCHESTRATOR_AVAILABLE = False


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv('DATABASE_URL', '')


async def refresh_pipeline_data(disease_name: str, therapeutic_area: str = "Autoimmune") -> Tuple[bool, str, Optional[Any]]:
    """
    Refresh pipeline data for a disease by running full Pipeline Intelligence flow.
    This includes web search for latest press releases and news.
    """
    try:
        database_url = get_database_url()
        if not database_url:
            return False, "Database URL not configured", None
        db = DatabaseConnection(database_url=database_url)
        ct_client = ClinicalTrialsClient()
        openfda_client = OpenFDAClient()

        # Get web searcher
        try:
            from src.tools.web_search import create_web_searcher
            web_searcher = create_web_searcher()
        except Exception:
            web_searcher = None

        # Get LLM client
        try:
            from anthropic import AsyncAnthropic

            class SimpleLLMClient:
                def __init__(self):
                    self.client = AsyncAnthropic()

                async def complete(self, prompt: str, model: str = "claude-sonnet-4-20250514", max_tokens: int = 8000) -> str:
                    response = await self.client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    return response.content[0].text

            llm_client = SimpleLLMClient()
        except Exception as e:
            return False, f"LLM client not available: {e}", None

        repository = PipelineIntelligenceRepository(db)

        service = PipelineIntelligenceService(
            clinicaltrials_client=ct_client,
            web_searcher=web_searcher,
            llm_client=llm_client,
            repository=repository,
            openfda_client=openfda_client,
        )

        # Run full pipeline with web search and force refresh
        landscape = await service.get_landscape(
            disease_name=disease_name,
            therapeutic_area=therapeutic_area,
            include_web_search=True,  # Include press release search
            force_refresh=True,  # Force refresh to get latest data
            filter_related_conditions=True,
            enrich_new_drugs=False,
        )

        if landscape:
            return True, f"Refreshed: {landscape.total_drugs} drugs ({landscape.approved_count} approved, {landscape.discontinued_count} discontinued)", landscape
        else:
            return False, "No results returned", None

    except Exception as e:
        import traceback
        return False, f"Error: {str(e)}\n{traceback.format_exc()}", None


def get_unique_diseases() -> List[Dict[str, Any]]:
    """Get unique diseases from case series extractions with counts."""
    database_url = get_database_url()
    if not database_url:
        return []

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    disease,
                    COUNT(DISTINCT drug_name) as drug_count,
                    COUNT(*) as paper_count,
                    SUM(n_patients) as total_patients,
                    MAX(extracted_at) as last_extraction
                FROM cs_extractions
                WHERE is_relevant = true AND disease IS NOT NULL AND disease != ''
                GROUP BY disease
                ORDER BY disease ASC
            """)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_last_workflow_run(disease_name: str, workflow_type: str) -> Optional[datetime]:
    """Get the last run timestamp for a disease/workflow combination."""
    database_url = get_database_url()
    if not database_url:
        return None

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if workflow_type == "pipeline":
                cur.execute("""
                    SELECT MAX(run_timestamp) as last_run
                    FROM pipeline_runs
                    WHERE disease_name = %s AND status = 'completed'
                """, (disease_name,))
            elif workflow_type == "disease":
                cur.execute("""
                    SELECT MAX(created_at) as last_run
                    FROM disease_intelligence
                    WHERE disease_name = %s
                """, (disease_name,))
            else:
                return None

            row = cur.fetchone()
            return row['last_run'] if row and row['last_run'] else None
    except Exception:
        return None
    finally:
        conn.close()


def get_all_disease_intelligence() -> List[Dict[str, Any]]:
    """Get all disease intelligence records."""
    database_url = get_database_url()
    if not database_url:
        return []

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    disease_id, disease_name, therapeutic_area,
                    total_patients, pct_treated, fail_1l_pct,
                    market_size_2l_usd, data_quality, updated_at,
                    created_at
                FROM disease_intelligence
                ORDER BY updated_at DESC NULLS LAST
            """)
            return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        st.error(f"Error fetching disease intelligence: {e}")
        return []
    finally:
        conn.close()


def get_all_pipeline_runs(limit: int = 100) -> List[Dict[str, Any]]:
    """Get all pipeline runs."""
    database_url = get_database_url()
    if not database_url:
        return []

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    r.run_id,
                    r.disease_id,
                    di.disease_name,
                    di.therapeutic_area,
                    r.run_timestamp,
                    r.run_type,
                    r.drugs_found_total,
                    r.drugs_new,
                    r.drugs_updated,
                    r.status,
                    r.error_message
                FROM disease_pipeline_runs r
                JOIN disease_intelligence di ON r.disease_id = di.disease_id
                ORDER BY r.run_timestamp DESC
                LIMIT %s
            """, (limit,))
            return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        # Table might not exist yet
        return []
    finally:
        conn.close()


def get_pipeline_drugs(disease_name: str) -> List[Dict[str, Any]]:
    """Get pipeline drugs for a disease with per-indication phase and discontinuation status."""
    database_url = get_database_url()
    if not database_url:
        st.warning("No database URL configured")
        return []

    try:
        conn = psycopg2.connect(database_url)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get drugs with clinical trial info for this specific indication
            # Use DISTINCT ON to deduplicate by drug_id
            cur.execute("""
                WITH indication_trials AS (
                    -- Get the highest phase trial and status for each drug for this indication
                    SELECT
                        d.drug_id,
                        MAX(CASE ct.trial_phase
                            WHEN 'PHASE4' THEN 5
                            WHEN 'PHASE3' THEN 4
                            WHEN 'PHASE2_3' THEN 4
                            WHEN 'PHASE2' THEN 3
                            WHEN 'PHASE1_2' THEN 2
                            WHEN 'PHASE1' THEN 1
                            ELSE 0
                        END) as max_phase_num,
                        -- Check if any trials are terminated/withdrawn (discontinued)
                        bool_or(ct.trial_status IN ('TERMINATED', 'WITHDRAWN', 'SUSPENDED')) as has_discontinued_trial,
                        -- Check if any trials are active
                        bool_or(ct.trial_status IN ('RECRUITING', 'ACTIVE_NOT_RECRUITING', 'ENROLLING_BY_INVITATION', 'NOT_YET_RECRUITING')) as has_active_trial,
                        -- Check if Phase 3 trial is completed (NDA/BLA pending)
                        bool_or(ct.trial_phase IN ('PHASE3', 'PHASE2_3') AND ct.trial_status = 'COMPLETED') as has_completed_phase3,
                        array_agg(DISTINCT ct.trial_status) FILTER (WHERE ct.trial_status IS NOT NULL) as trial_statuses,
                        array_agg(DISTINCT ct.nct_id) FILTER (WHERE ct.nct_id IS NOT NULL) as nct_ids
                    FROM drugs d
                    JOIN drug_clinical_trials ct ON d.drug_id = ct.drug_id
                    WHERE ct.conditions::text ILIKE %s
                    GROUP BY d.drug_id
                ),
                ranked_drugs AS (
                    SELECT DISTINCT ON (d.drug_id)
                        d.drug_id, d.generic_name, d.brand_name,
                        d.manufacturer, d.drug_type, d.mechanism_of_action,
                        d.target, d.highest_phase,
                        d.first_approval_date as approval_date,
                        di.approval_status as indication_status,
                        di.disease_name as matched_indication,
                        -- Use indication-specific phase from trials if available
                        -- Prioritize NDA Filed/Planned from press releases
                        CASE
                            WHEN d.highest_phase IN ('NDA Filed', 'NDA Planned', 'BLA Filed', 'BLA Planned') THEN d.highest_phase
                            WHEN it.max_phase_num = 5 THEN 'Phase 4'
                            WHEN it.max_phase_num = 4 THEN 'Phase 3'
                            WHEN it.max_phase_num = 3 THEN 'Phase 2'
                            WHEN it.max_phase_num = 2 THEN 'Phase 1/2'
                            WHEN it.max_phase_num = 1 THEN 'Phase 1'
                            ELSE d.highest_phase
                        END as indication_phase,
                        -- Determine if drug is discontinued for this indication
                        -- Check di.approval_status FIRST for manually validated discontinuations
                        CASE
                            WHEN di.approval_status = 'approved' THEN 'approved'
                            WHEN di.approval_status = 'discontinued' THEN 'discontinued'
                            WHEN d.highest_phase IN ('NDA Filed', 'NDA Planned', 'BLA Filed', 'BLA Planned') THEN 'nda_pending'
                            WHEN it.has_completed_phase3 AND NOT COALESCE(it.has_active_trial, false) THEN 'nda_pending'
                            WHEN it.has_discontinued_trial AND NOT COALESCE(it.has_active_trial, false) THEN 'discontinued'
                            WHEN it.has_active_trial THEN 'active'
                            ELSE 'unknown'
                        END as development_status,
                        it.trial_statuses,
                        it.nct_ids,
                        COALESCE(it.has_completed_phase3, false) as has_completed_phase3,
                        -- For ordering
                        CASE
                            WHEN di.approval_status = 'approved' THEN 1
                            WHEN di.approval_status = 'discontinued' THEN 10
                            WHEN d.highest_phase IN ('NDA Filed', 'NDA Planned', 'BLA Filed', 'BLA Planned') THEN 2
                            WHEN it.has_completed_phase3 AND NOT COALESCE(it.has_active_trial, false) THEN 2
                            WHEN it.has_discontinued_trial AND NOT COALESCE(it.has_active_trial, false) THEN 10
                            ELSE 3
                        END as sort_priority,
                        COALESCE(it.max_phase_num, 0) as phase_num
                    FROM drugs d
                    JOIN drug_indications di ON d.drug_id = di.drug_id
                    LEFT JOIN indication_trials it ON d.drug_id = it.drug_id
                    WHERE LOWER(di.disease_name) = LOWER(%s)
                       OR LOWER(di.disease_name) LIKE LOWER(%s)
                    ORDER BY d.drug_id,
                        CASE WHEN di.approval_status = 'approved' THEN 0 ELSE 1 END,
                        di.disease_name
                )
                SELECT * FROM ranked_drugs
                ORDER BY
                    sort_priority,
                    CASE phase_num
                        WHEN 5 THEN 1
                        WHEN 4 THEN 2
                        WHEN 3 THEN 3
                        WHEN 2 THEN 4
                        WHEN 1 THEN 5
                        ELSE 6
                    END,
                    brand_name
            """, (f'%{disease_name}%', disease_name, f'%{disease_name}%'))
            results = [dict(row) for row in cur.fetchall()]
            conn.close()
            return results
    except Exception as e:
        st.error(f"Error fetching pipeline drugs: {e}")
        import traceback
        st.code(traceback.format_exc())
        return []


def format_number(n) -> str:
    """Format large numbers with K/M suffix."""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "N/A"
    try:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        elif n >= 1_000:
            return f"{n / 1_000:.0f}K"
        return str(int(n))
    except (ValueError, TypeError):
        return "N/A"


def format_currency(n) -> str:
    """Format currency with B/M suffix."""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "N/A"
    try:
        if n >= 1_000_000_000:
            return f"${n / 1_000_000_000:.1f}B"
        elif n >= 1_000_000:
            return f"${n / 1_000_000:.0f}M"
        return f"${int(n):,}"
    except (ValueError, TypeError):
        return "N/A"


def superscript(n: int) -> str:
    """Convert number to superscript for citations."""
    superscript_map = {'0': '\u2070', '1': '\u00b9', '2': '\u00b2', '3': '\u00b3',
                       '4': '\u2074', '5': '\u2075', '6': '\u2076', '7': '\u2077',
                       '8': '\u2078', '9': '\u2079'}
    return ''.join(superscript_map.get(c, c) for c in str(n))


def format_citations(citation_nums: list) -> str:
    """Format citation numbers as superscripts with raised separator."""
    if not citation_nums:
        return ""
    # Use middle dot as separator - visually balanced with superscript numbers
    separator = '\u00b7'  # middle dot ·
    return separator.join(superscript(n) for n in citation_nums)


def get_disease_intelligence_model(disease_name: str):
    """Get disease intelligence as proper model with source estimates."""
    try:
        database_url = get_database_url()
        if not database_url:
            st.error("Database URL required. Set DATABASE_URL environment variable.")
            return None
        db = DatabaseConnection(database_url=database_url)
        repo = DiseaseIntelligenceRepository(db)
        return repo.get_disease(disease_name)
    except Exception as e:
        st.error(f"Error loading disease: {e}")
        return None


def render_market_sizing_detail(disease_name: str):
    """Render detailed market sizing view for a disease with proper citations."""
    # Load disease model to get source estimates
    disease = get_disease_intelligence_model(disease_name)
    if not disease:
        st.warning(f"Could not load detailed data for {disease_name}")
        return

    st.markdown(f"### Market Sizing: {disease.disease_name}")

    # Data quality badge
    quality_colors = {"High": "green", "Medium": "orange", "Low": "red"}
    quality = disease.data_quality or "Unknown"
    st.markdown(f"Data Quality: :{quality_colors.get(quality, 'gray')}[{quality}]")

    st.divider()

    # Build sources list for citations
    sources_list = []
    citation_num = 1

    # Add prevalence estimates as sources
    prev = disease.prevalence
    prevalence_citations = []
    if prev.source_estimates:
        for est in prev.source_estimates:
            sources_list.append({
                'num': citation_num,
                'title': est.title or 'Unknown',
                'authors': est.authors,
                'journal': est.journal,
                'year': est.year,
                'pmid': est.pmid,
                'url': est.url,
                'type': 'Prevalence',
                'value': format_number(est.total_patients) if est.total_patients else est.prevalence_rate,
            })
            prevalence_citations.append(citation_num)
            citation_num += 1

    # Add failure rate estimates as sources
    fr = disease.failure_rates
    failure_citations = []
    if fr.source_estimates:
        for est in fr.source_estimates:
            sources_list.append({
                'num': citation_num,
                'title': est.title or 'Unknown',
                'authors': est.authors,
                'journal': est.journal,
                'year': est.year,
                'pmid': est.pmid,
                'url': est.url,
                'type': 'Failure Rate',
                'value': f"{est.fail_rate_pct:.0f}%" if est.fail_rate_pct else None,
            })
            failure_citations.append(citation_num)
            citation_num += 1

    # Add treatment rate estimates as sources
    seg = disease.segmentation
    treatment_citations = []
    if seg.treatment_estimates:
        for est in seg.treatment_estimates:
            sources_list.append({
                'num': citation_num,
                'title': est.title or 'Unknown',
                'authors': est.authors,
                'journal': est.journal,
                'year': est.year,
                'pmid': est.pmid,
                'url': est.url,
                'type': 'Treatment Rate',
                'value': f"{est.pct_treated:.0f}%" if est.pct_treated else None,
            })
            treatment_citations.append(citation_num)
            citation_num += 1

    # === MARKET FUNNEL ===
    st.subheader("Market Funnel")

    # Always recalculate market funnel to use current tiered pricing logic
    # This ensures consistency with the prevalence-based tiers:
    # - Rare (<10K): $200K/year
    # - Specialty (10K-100K): $75K/year
    # - Standard (>100K): $20K/year
    disease.calculate_market_funnel()

    funnel = disease.market_funnel

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Patients",
            format_number(funnel.total_patients) if funnel else "N/A",
            help="Total US patient population"
        )

    with col2:
        pct_treated = disease.segmentation.pct_treated or 0
        st.metric(
            "Treated",
            format_number(funnel.patients_treated) if funnel else "N/A",
            f"{pct_treated:.0f}% of total" if pct_treated else None,
            help="Patients receiving any treatment"
        )

    with col3:
        fail_pct = disease.failure_rates.fail_1L_pct or 0
        st.metric(
            "Fail 1L",
            format_number(funnel.patients_fail_1L) if funnel else "N/A",
            f"{fail_pct:.0f}% of treated" if fail_pct else None,
            help="Patients with inadequate response to 1L"
        )

    with col4:
        st.metric(
            "Market Size (2L)",
            format_currency(funnel.market_size_2L_usd) if funnel else "N/A",
            help="Total addressable market for 2L therapies"
        )

    # Show calculation with pricing tier explanation
    if funnel and funnel.market_size_2L_usd:
        avg_cost = funnel.avg_annual_cost_2L or 0
        total_patients = funnel.total_patients or 0

        # Determine which pricing tier is being used
        if total_patients < 10000:
            tier_name = "Rare Disease"
            tier_price = "$200,000"
        elif total_patients < 100000:
            tier_name = "Specialty"
            tier_price = "$75,000"
        else:
            tier_name = "Standard"
            tier_price = "$20,000"

        # Create columns for calculation and help icon
        calc_col, help_col = st.columns([10, 1])
        with calc_col:
            st.caption(
                f"Calculation: {format_number(funnel.patients_addressable_2L)} patients × "
                f"${avg_cost:,.0f}/year ({tier_name} tier) = {format_currency(funnel.market_size_2L_usd)}"
            )
        with help_col:
            with st.popover("ⓘ"):
                st.markdown("**Pricing Tiers by Patient Population**")
                st.markdown("""
| Tier | Patient Count | Annual Cost |
|------|---------------|-------------|
| Rare Disease | < 10,000 | $200,000/yr |
| Specialty | 10,000 - 100,000 | $75,000/yr |
| Standard | > 100,000 | $20,000/yr |
""")
                st.caption(f"**This disease:** {format_number(total_patients)} patients → {tier_name} tier ({tier_price}/yr)")

    st.divider()

    # === PREVALENCE ===
    st.subheader("Prevalence")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        value = format_number(prev.total_patients)
        if prevalence_citations:
            st.markdown(f"**Total Patients**")
            st.markdown(f"### {value}" + format_citations(prevalence_citations))
        else:
            st.metric("Total Patients", value)
    with col2:
        st.metric("Adults", format_number(prev.adult_patients) if prev.adult_patients else "N/A")
    with col3:
        st.metric("Pediatric", format_number(prev.pediatric_patients) if prev.pediatric_patients else "N/A")
    with col4:
        if prev.confidence:
            st.metric("Confidence", prev.confidence)
        elif prev.estimate_range:
            st.metric("Range", prev.estimate_range)

    # Show prevalence estimates table
    if prev.source_estimates and len(prev.source_estimates) > 0:
        with st.expander(f"Prevalence Methodology ({len(prev.source_estimates)} sources)", expanded=False):
            if prev.methodology_notes:
                st.info(prev.methodology_notes)
            else:
                st.info("Consensus derived from median of available estimates")

            est_data = []
            for i, est in enumerate(prev.source_estimates):
                short_title = (est.title[:50] + '...') if est.title and len(est.title) > 50 else (est.title or 'Unknown')
                est_type = est.estimate_type or ''
                if est_type == 'incidence':
                    est_type = '⚠️ Incidence'
                elif est_type == 'prevalence':
                    est_type = 'Prevalence'
                citation_ref = f"[{prevalence_citations[i]}]" if i < len(prevalence_citations) else ''
                est_data.append({
                    'Ref': citation_ref,
                    'Source': short_title,
                    'PMID': est.pmid or '',
                    'Type': est_type,
                    'Year': est.year or '',
                    'Patients': format_number(est.total_patients) if est.total_patients else '',
                    'Rate': est.prevalence_rate or '',
                    'Quality': est.quality_tier or '',
                })

            st.dataframe(pd.DataFrame(est_data), hide_index=True, use_container_width=True)
            if prev.estimate_range:
                st.caption(f"Range of estimates: {prev.estimate_range}")

    st.divider()

    # === SEGMENTATION & FAILURE RATES ===
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Segmentation")
        seg = disease.segmentation

        col1, col2 = st.columns(2)
        with col1:
            if seg.pct_diagnosed:
                st.metric("% Diagnosed", f"{seg.pct_diagnosed:.0f}%")
            else:
                st.metric("% Diagnosed", "N/A")
        with col2:
            if seg.pct_treated:
                value = f"{seg.pct_treated:.0f}%"
                if treatment_citations:
                    st.markdown("**% Treated**")
                    st.markdown(f"### {value}" + format_citations(treatment_citations))
                else:
                    st.metric("% Treated", value)
                    if seg.pct_treated_source:
                        st.caption(f"Source: {seg.pct_treated_source[:50]}...")
            else:
                st.metric("% Treated", "N/A")

        if seg.severity:
            sev = seg.severity
            sev_parts = []
            if sev.mild:
                sev_parts.append(f"Mild: {sev.mild:.0f}%")
            if sev.moderate:
                sev_parts.append(f"Moderate: {sev.moderate:.0f}%")
            if sev.severe:
                sev_parts.append(f"Severe: {sev.severe:.0f}%")
            if sev_parts:
                st.caption("Severity: " + " | ".join(sev_parts))

    with col_right:
        st.subheader("Failure Rates")

        col1, col2 = st.columns(2)
        with col1:
            if fr.fail_1L_pct:
                value = f"{fr.fail_1L_pct:.0f}%"
                if failure_citations:
                    st.markdown("**Fail 1L**")
                    st.markdown(f"### {value}" + format_citations(failure_citations))
                else:
                    st.metric("Fail 1L", value)
                if fr.fail_1L_reason:
                    st.caption(f"Reason: {fr.fail_1L_reason}")
                if fr.confidence:
                    st.caption(f"Confidence: {fr.confidence}")
            else:
                st.metric("Fail 1L", "N/A")
        with col2:
            if fr.fail_2L_pct:
                st.metric("Fail 2L", f"{fr.fail_2L_pct:.0f}%")
                if fr.fail_2L_reason:
                    st.caption(f"Reason: {fr.fail_2L_reason}")
            else:
                st.metric("Fail 2L", "N/A")

    # Show failure rate estimates table
    if fr.source_estimates and len(fr.source_estimates) > 0:
        with st.expander(f"Failure Rate Methodology ({len(fr.source_estimates)} sources)", expanded=False):
            if fr.methodology_notes:
                st.info(fr.methodology_notes)

            est_data = []
            for i, est in enumerate(fr.source_estimates):
                short_title = (est.title[:40] + '...') if est.title and len(est.title) > 40 else (est.title or 'Unknown')
                fail_type = est.failure_type or ''
                if fail_type == 'primary_nonresponse':
                    fail_type = 'Primary Non-resp'
                elif fail_type == 'secondary_loss_of_response':
                    fail_type = 'Secondary Loss'
                elif fail_type == 'discontinuation_any_reason':
                    fail_type = 'Discontinuation'
                citation_ref = f"[{failure_citations[i]}]" if i < len(failure_citations) else ''
                est_data.append({
                    'Ref': citation_ref,
                    'Source': short_title,
                    'PMID': est.pmid or '',
                    'Line': est.line_of_therapy or '',
                    'Type': fail_type,
                    'Year': est.year or '',
                    'Rate': f"{est.fail_rate_pct:.0f}%" if est.fail_rate_pct else '',
                    'Quality': est.quality_tier or '',
                })

            st.dataframe(pd.DataFrame(est_data), hide_index=True, use_container_width=True)
            if fr.estimate_range:
                st.caption(f"Range of estimates: {fr.estimate_range}")

    st.divider()

    # === TREATMENT PARADIGM ===
    st.subheader("Treatment Paradigm")
    tp = disease.treatment_paradigm

    if tp and tp.summary:
        st.markdown(tp.summary)

    col1, col2 = st.columns(2)
    with col1:
        if tp and tp.first_line and tp.first_line.drugs:
            st.markdown("**First-Line (1L)**")
            for drug in tp.first_line.drugs[:5]:
                soc = " (SOC)" if drug.is_standard_of_care else ""
                st.markdown(f"- {drug.drug_name}{soc}")
        else:
            st.caption("No 1L treatment data available")
    with col2:
        if tp and tp.second_line and tp.second_line.drugs:
            st.markdown("**Second-Line (2L)**")
            for drug in tp.second_line.drugs[:5]:
                wac = f" - ${drug.wac_monthly:,.0f}/mo" if drug.wac_monthly else ""
                st.markdown(f"- {drug.drug_name}{wac}")
        else:
            st.caption("No 2L treatment data available")

    st.divider()

    # === PIPELINE DRUGS ===
    st.subheader("Pipeline Drugs")
    pipeline_drugs = get_pipeline_drugs(disease.disease_name)

    if pipeline_drugs:
        # Group by development status
        approved = [d for d in pipeline_drugs if d.get('indication_status', '').lower() == 'approved']
        nda_pending = [d for d in pipeline_drugs if d.get('development_status') == 'nda_pending' and d not in approved]
        phase3 = [d for d in pipeline_drugs if d.get('indication_phase', '') in ['Phase 3', 'Phase 2/3'] and d not in approved + nda_pending]
        phase2 = [d for d in pipeline_drugs if d.get('indication_phase', '') in ['Phase 2', 'Phase 1/2'] and d not in approved + nda_pending + phase3]
        phase1 = [d for d in pipeline_drugs if d.get('indication_phase', '') == 'Phase 1' and d not in approved + nda_pending + phase3 + phase2]
        discontinued = [d for d in pipeline_drugs if d.get('development_status') == 'discontinued']
        other = [d for d in pipeline_drugs if d not in approved + nda_pending + phase3 + phase2 + phase1 + discontinued]

        # Summary metrics
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Approved", len(approved))
        with col2:
            st.metric("NDA/BLA", len(nda_pending))
        with col3:
            st.metric("Phase 3", len(phase3))
        with col4:
            st.metric("Phase 2", len(phase2))
        with col5:
            st.metric("Discontinued", len(discontinued))

        # Tabs for different phases
        tab_approved, tab_nda, tab_phase3, tab_phase2, tab_phase1, tab_disc = st.tabs([
            f"Approved ({len(approved)})",
            f"NDA/BLA ({len(nda_pending)})",
            f"Phase 3 ({len(phase3)})",
            f"Phase 2 ({len(phase2)})",
            f"Phase 1 ({len(phase1)})",
            f"Discontinued ({len(discontinued)})"
        ])

        def render_drug_table(drugs, show_status=False):
            """Render drugs as a table."""
            if not drugs:
                st.info("No drugs in this category")
                return

            # Show count if many drugs
            if len(drugs) > 20:
                st.caption(f"Showing all {len(drugs)} drugs")

            table_data = []
            for d in drugs:  # Removed [:20] limit - show all drugs
                # Format NCT IDs as clickable links (markdown format)
                # Filter out None, NaN, and "nan" strings
                raw_nct_ids = d.get('nct_ids') or []
                nct_ids = [nct for nct in raw_nct_ids if nct and str(nct).lower() != 'nan' and str(nct).strip()]
                nct_links = []
                for nct in nct_ids[:3]:
                    nct_links.append(f"[{nct}](https://clinicaltrials.gov/study/{nct})")
                nct_str = ' '.join(nct_links)
                if len(nct_ids) > 3:
                    nct_str += f' +{len(nct_ids)-3}'

                row = {
                    'Drug': d.get('brand_name') or d.get('generic_name') or 'Unknown',
                    'Generic': d.get('generic_name') or '',
                    'Mechanism': (d.get('mechanism_of_action') or '')[:50],  # Truncate for table
                    'Company': d.get('manufacturer') or '',
                }
                if nct_str:
                    row['Trials'] = nct_str
                if show_status:
                    row['Status'] = d.get('indication_phase') or d.get('highest_phase') or ''
                table_data.append(row)

            df = pd.DataFrame(table_data)

            # Render as markdown table for clickable links
            if 'Trials' in df.columns and len(df) <= 50:
                # Use markdown table for clickable NCT links (up to 50 rows)
                md_table = df.to_markdown(index=False)
                st.markdown(md_table, unsafe_allow_html=False)
            else:
                # Fall back to dataframe for large tables (faster rendering)
                st.dataframe(
                    df,
                    hide_index=True,
                    use_container_width=True,
                    height=min(600, 35 + len(drugs) * 35)
                )

        def render_discontinued_table(drugs):
            """Render discontinued drugs as a table."""
            if not drugs:
                st.info("No discontinued drugs")
                return

            # Show count if many drugs
            if len(drugs) > 20:
                st.caption(f"Showing all {len(drugs)} discontinued drugs")

            table_data = []
            for d in drugs:  # Removed [:20] limit
                statuses = d.get('trial_statuses') or []
                # Filter out None, NaN, and "nan" strings from statuses
                valid_statuses = [s for s in statuses if s and str(s).lower() != 'nan' and str(s).strip()]
                status_str = ', '.join(str(s) for s in valid_statuses) if valid_statuses else 'Discontinued'

                # Format NCT IDs as clickable links (markdown format)
                # Filter out None, NaN, and "nan" strings
                raw_nct_ids = d.get('nct_ids') or []
                nct_ids = [nct for nct in raw_nct_ids if nct and str(nct).lower() != 'nan' and str(nct).strip()]
                nct_links = []
                for nct in nct_ids[:3]:
                    nct_links.append(f"[{nct}](https://clinicaltrials.gov/study/{nct})")
                nct_str = ' '.join(nct_links)
                if len(nct_ids) > 3:
                    nct_str += f' +{len(nct_ids)-3}'

                row = {
                    'Drug': d.get('brand_name') or d.get('generic_name') or 'Unknown',
                    'Generic': d.get('generic_name') or '',
                    'Mechanism': d.get('mechanism_of_action') or '',
                    'Company': d.get('manufacturer') or '',
                    'Trial Status': status_str,
                }
                if nct_str:
                    row['Trials'] = nct_str
                table_data.append(row)

            df = pd.DataFrame(table_data)

            # Render as markdown table for clickable links
            if 'Trials' in df.columns and len(df) <= 50:
                # Use markdown table for clickable NCT links (up to 50 rows)
                md_table = df.to_markdown(index=False)
                st.markdown(md_table, unsafe_allow_html=False)
            else:
                # Fall back to dataframe for large tables (faster rendering)
                st.dataframe(
                    df,
                    hide_index=True,
                    use_container_width=True,
                    height=min(600, 35 + len(drugs) * 35)
                )

        with tab_approved:
            render_drug_table(approved)

        with tab_nda:
            render_drug_table(nda_pending, show_status=True)

        with tab_phase3:
            render_drug_table(phase3)

        with tab_phase2:
            render_drug_table(phase2)

        with tab_phase1:
            render_drug_table(phase1)

        with tab_disc:
            render_discontinued_table(discontinued)
    else:
        st.info("No pipeline drugs found. Run Pipeline Intelligence to populate.")

    st.divider()

    # === REFERENCES ===
    st.subheader("References")

    if sources_list:
        for src in sources_list:
            num = src['num']
            title = src['title']
            authors = src.get('authors') or ''
            journal = src.get('journal') or ''
            year = src.get('year') or ''
            pmid = src.get('pmid')
            url = src.get('url')
            data_type = src.get('type', '')
            value = src.get('value', '')

            # Format citation
            citation_parts = []
            if authors:
                citation_parts.append(authors)
            if title:
                citation_parts.append(f"*{title}*")
            if journal:
                citation_parts.append(journal)
            if year:
                citation_parts.append(f"({year})")

            citation_text = ". ".join(citation_parts) if citation_parts else title

            # Add link
            if pmid:
                link = f"[PMID: {pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid})"
            elif url:
                link = f"[Link]({url})"
            else:
                link = ""

            # Use larger reference numbers (not superscript)
            col1, col2, col3 = st.columns([0.4, 4, 1])
            with col1:
                st.markdown(f"**[{num}]**")
            with col2:
                st.markdown(f"{citation_text} {link}")
            with col3:
                if value:
                    st.caption(f"{data_type}: {value}")
    else:
        st.info("No sources recorded - run analysis to populate citations")


def render_results_browser():
    """Render the past results browser."""
    st.subheader("Disease Intelligence Data")

    disease_data = get_all_disease_intelligence()

    if not disease_data:
        st.info("No disease intelligence data yet. Run an analysis to populate.")
        return

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Diseases Analyzed", len(disease_data))
    with col2:
        with_prevalence = sum(1 for d in disease_data if d.get('total_patients'))
        st.metric("With Prevalence Data", with_prevalence)
    with col3:
        with_market = sum(1 for d in disease_data if d.get('market_size_2l_usd'))
        st.metric("With Market Size", with_market)

    st.divider()

    # Disease intelligence table
    df = pd.DataFrame(disease_data)

    # Format columns for display - use available columns
    available_cols = df.columns.tolist()
    display_cols = ['disease_name', 'therapeutic_area', 'total_patients', 'pct_treated']

    # Add optional columns if they exist
    if 'fail_1l_pct' in available_cols:
        display_cols.append('fail_1l_pct')
    if 'market_size_2l_usd' in available_cols:
        display_cols.append('market_size_2l_usd')
    if 'data_quality' in available_cols:
        display_cols.append('data_quality')
    if 'updated_at' in available_cols:
        display_cols.append('updated_at')

    display_df = df[[c for c in display_cols if c in available_cols]].copy()

    # Rename columns for display
    col_renames = {
        'disease_name': 'Disease',
        'therapeutic_area': 'Therapeutic Area',
        'total_patients': 'Total Patients',
        'pct_treated': '% Treated',
        'fail_1l_pct': 'Fail 1L %',
        'market_size_2l_usd': 'Market Size (2L)',
        'data_quality': 'Data Quality',
        'updated_at': 'Last Updated'
    }
    display_df.rename(columns=col_renames, inplace=True)

    # Format numbers
    if 'Total Patients' in display_df.columns:
        display_df['Total Patients'] = display_df['Total Patients'].apply(format_number)
    if '% Treated' in display_df.columns:
        display_df['% Treated'] = display_df['% Treated'].apply(lambda x: f"{x:.1f}%" if x else "N/A")
    if 'Fail 1L %' in display_df.columns:
        display_df['Fail 1L %'] = display_df['Fail 1L %'].apply(lambda x: f"{x:.1f}%" if x else "N/A")
    if 'Market Size (2L)' in display_df.columns:
        display_df['Market Size (2L)'] = display_df['Market Size (2L)'].apply(format_currency)
    if 'Last Updated' in display_df.columns:
        display_df['Last Updated'] = display_df['Last Updated'].apply(
            lambda x: x.strftime('%Y-%m-%d %H:%M') if x else "N/A"
        )

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.divider()

    # Disease selector for detailed view
    disease_names = [d['disease_name'] for d in disease_data]
    selected_for_detail = st.selectbox(
        "Select disease for detailed market sizing view",
        ["(Select a disease)"] + disease_names,
        key="market_detail_selector"
    )

    if selected_for_detail and selected_for_detail != "(Select a disease)":
        render_market_sizing_detail(selected_for_detail)


def get_llm_client():
    """Create LLM client."""
    try:
        from anthropic import AsyncAnthropic

        class SimpleLLMClient:
            def __init__(self):
                self.client = AsyncAnthropic()

            async def complete(self, prompt: str, model: str = "claude-sonnet-4-20250514", max_tokens: int = 8000) -> str:
                response = await self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text

        return SimpleLLMClient()
    except Exception as e:
        st.error(f"Failed to initialize LLM client: {e}")
        return None


def get_web_searcher():
    """Create web searcher."""
    try:
        from src.tools.web_search import create_web_searcher
        return create_web_searcher()
    except Exception as e:
        st.warning(f"Web searcher not available: {e}")
        return None


async def run_pipeline_intelligence(
    disease_name: str,
    therapeutic_area: str,
    force_refresh: bool = False
) -> Tuple[bool, str, Optional[Any]]:
    """Run Pipeline Intelligence workflow for a disease."""
    try:
        database_url = get_database_url()
        if not database_url:
            return False, "Database URL not configured", None
        db = DatabaseConnection(database_url=database_url)
        ct_client = ClinicalTrialsClient()
        openfda_client = OpenFDAClient()
        web_searcher = get_web_searcher()
        llm_client = get_llm_client()

        if not llm_client:
            return False, "LLM client not available", None

        repository = PipelineIntelligenceRepository(db)

        service = PipelineIntelligenceService(
            clinicaltrials_client=ct_client,
            web_searcher=web_searcher,
            llm_client=llm_client,
            repository=repository,
            openfda_client=openfda_client,
        )

        landscape = await service.get_landscape(
            disease_name=disease_name,
            therapeutic_area=therapeutic_area,
            include_web_search=True,
            force_refresh=force_refresh,
        )

        if landscape:
            return True, f"Found {landscape.total_drugs} drugs ({landscape.approved_count} approved)", landscape
        else:
            return False, "No results returned", None

    except Exception as e:
        return False, f"Error: {str(e)}", None


async def run_disease_intelligence(
    disease_name: str,
    therapeutic_area: str,
    force_refresh: bool = False
) -> Tuple[bool, str, Optional[Any]]:
    """Run Disease Intelligence workflow for a disease."""
    try:
        from src.tools.pubmed import PubMedAPI
        from src.disease_intelligence.service import DiseaseIntelligenceService
        from anthropic import Anthropic

        database_url = get_database_url()
        if not database_url:
            return False, "Database URL not configured", None
        db = DatabaseConnection(database_url=database_url)
        pubmed = PubMedAPI()
        web_searcher = get_web_searcher()

        # Create LLM client for disease intelligence
        anthropic_client = Anthropic()

        class LLMWrapper:
            def __init__(self, client):
                self.client = client

            async def complete(self, prompt: str, model: str = "claude-sonnet-4-20250514", max_tokens: int = 8000) -> str:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text

        llm_client = LLMWrapper(anthropic_client)

        repository = DiseaseIntelligenceRepository(db)

        service = DiseaseIntelligenceService(
            pubmed_searcher=pubmed,
            semantic_scholar_searcher=None,
            web_searcher=web_searcher,
            llm_client=llm_client,
            repository=repository,
        )

        result = await service.populate_disease(
            disease_name=disease_name,
            therapeutic_area=therapeutic_area,
            force_refresh=force_refresh,
        )

        if result:
            patients = result.prevalence.total_patients if result.prevalence else 0
            return True, f"Populated data (prevalence: {patients:,} patients)", result
        else:
            return False, "No results returned", None

    except Exception as e:
        return False, f"Error: {str(e)}", None


async def run_unified_analysis(
    disease_name: str,
    therapeutic_area: str,
    force_refresh: bool = False
) -> Tuple[bool, str, Optional[Any]]:
    """
    Run unified analysis using the DiseaseAnalysisOrchestrator.

    This combines Pipeline Intelligence and Disease Intelligence into a single
    coordinated workflow, sharing data between them to avoid duplication.
    """
    if not UNIFIED_ORCHESTRATOR_AVAILABLE:
        return False, "Unified orchestrator not available", None

    try:
        from src.tools.pubmed import PubMedAPI
        from src.disease_intelligence.service import DiseaseIntelligenceService
        from anthropic import Anthropic

        database_url = get_database_url()
        if not database_url:
            return False, "Database URL not configured", None
        db = DatabaseConnection(database_url=database_url)
        ct_client = ClinicalTrialsClient()
        openfda_client = OpenFDAClient()
        pubmed = PubMedAPI()
        web_searcher = get_web_searcher()

        # Create LLM client
        anthropic_client = Anthropic()

        class LLMWrapper:
            def __init__(self, client):
                self.client = client

            async def complete(self, prompt: str, model: str = "claude-sonnet-4-20250514", max_tokens: int = 8000) -> str:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text

        llm_client = LLMWrapper(anthropic_client)

        # Create Pipeline Intelligence service
        pipeline_repo = PipelineIntelligenceRepository(db)
        pipeline_service = PipelineIntelligenceService(
            clinicaltrials_client=ct_client,
            web_searcher=web_searcher,
            llm_client=llm_client,
            repository=pipeline_repo,
            openfda_client=openfda_client,
        )

        # Create Disease Intelligence service
        disease_repo = DiseaseIntelligenceRepository(db)
        disease_service = DiseaseIntelligenceService(
            pubmed_searcher=pubmed,
            semantic_scholar_searcher=None,
            web_searcher=web_searcher,
            llm_client=llm_client,
            repository=disease_repo,
        )

        # Create orchestrator
        orchestrator = DiseaseAnalysisOrchestrator(
            pipeline_service=pipeline_service,
            disease_service=disease_service,
        )

        # Run unified analysis
        result = await orchestrator.analyze_disease(
            disease_name=disease_name,
            therapeutic_area=therapeutic_area,
            include_pipeline=True,
            include_market_sizing=True,
            force_refresh=force_refresh,
        )

        if result:
            # Build summary message
            summary_parts = []
            if result.landscape:
                summary_parts.append(f"{result.landscape.total_drugs} drugs")
            if result.disease_intel and result.disease_intel.prevalence.total_patients:
                summary_parts.append(f"{result.disease_intel.prevalence.total_patients:,} patients")
            if result.market_opportunity and result.market_opportunity.market_size_2L_formatted:
                summary_parts.append(f"Market: {result.market_opportunity.market_size_2L_formatted}")

            message = " | ".join(summary_parts) if summary_parts else "Analysis complete"
            return True, message, result
        else:
            return False, "No results returned", None

    except Exception as e:
        import traceback
        return False, f"Error: {str(e)}\n{traceback.format_exc()}", None


async def run_workflows_parallel(
    diseases: List[str],
    therapeutic_area: str,
    run_unified: bool,
    run_pipeline: bool,
    run_disease_intel: bool,
    force_refresh: bool,
    progress_callback=None
) -> Dict[str, Dict[str, Any]]:
    """Run selected workflows in parallel for all diseases."""
    results = {}

    # Calculate total tasks
    if run_unified:
        total_tasks = len(diseases)  # Unified analysis counts as one task per disease
    else:
        total_tasks = len(diseases) * (int(run_pipeline) + int(run_disease_intel))

    completed = 0

    for disease in diseases:
        results[disease] = {
            "unified": None,
            "pipeline": None,
            "disease_intel": None,
            "conflicts": [],
        }

        if run_unified:
            # Run unified analysis (combines both workflows)
            try:
                success, message, data = await run_unified_analysis(
                    disease, therapeutic_area, force_refresh
                )
                results[disease]["unified"] = {
                    "success": success,
                    "message": message,
                    "data": data,
                }
                # Also populate pipeline and disease_intel from unified result
                if success and data:
                    if data.landscape:
                        results[disease]["pipeline"] = {
                            "success": True,
                            "message": f"Found {data.landscape.total_drugs} drugs",
                            "data": data.landscape,
                        }
                    if data.disease_intel:
                        patients = data.disease_intel.prevalence.total_patients if data.disease_intel.prevalence else 0
                        results[disease]["disease_intel"] = {
                            "success": True,
                            "message": f"Prevalence: {patients:,} patients" if patients else "Data populated",
                            "data": data.disease_intel,
                        }
            except Exception as e:
                results[disease]["unified"] = {
                    "success": False,
                    "message": f"Exception: {str(e)}",
                    "data": None,
                }

            completed += 1
            if progress_callback:
                progress_callback(completed / total_tasks)
        else:
            # Run individual workflows
            tasks = []
            task_types = []

            if run_pipeline:
                tasks.append(run_pipeline_intelligence(disease, therapeutic_area, force_refresh))
                task_types.append("pipeline")

            if run_disease_intel:
                tasks.append(run_disease_intelligence(disease, therapeutic_area, force_refresh))
                task_types.append("disease_intel")

            if tasks:
                task_results = await asyncio.gather(*tasks, return_exceptions=True)

                for i, result in enumerate(task_results):
                    task_type = task_types[i]

                    if isinstance(result, Exception):
                        results[disease][task_type] = {
                            "success": False,
                            "message": f"Exception: {str(result)}",
                            "data": None,
                        }
                    else:
                        success, message, data = result
                        results[disease][task_type] = {
                            "success": success,
                            "message": message,
                            "data": data,
                        }

                    completed += 1
                    if progress_callback:
                        progress_callback(completed / total_tasks)

    return results


def detect_conflicts(results: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect conflicts between old and new data that need review."""
    conflicts = []

    # For now, we flag any successful runs for review
    # In future, this could compare specific fields
    for disease, disease_results in results.items():
        # Check unified analysis results
        if disease_results.get("unified", {}).get("success"):
            unified = disease_results["unified"].get("data")
            if unified:
                summary_parts = []
                if unified.landscape:
                    summary_parts.append(f"{unified.landscape.total_drugs} drugs")
                if unified.market_opportunity and unified.market_opportunity.market_size_2L_formatted:
                    summary_parts.append(f"Market: {unified.market_opportunity.market_size_2L_formatted}")
                conflicts.append({
                    "disease": disease,
                    "workflow": "Unified Analysis",
                    "type": "new_data",
                    "message": " | ".join(summary_parts) if summary_parts else "Analysis complete",
                    "severity": "info",
                })
        else:
            # Check individual workflow results
            if disease_results.get("pipeline", {}).get("success"):
                landscape = disease_results["pipeline"].get("data")
                if landscape:
                    conflicts.append({
                        "disease": disease,
                        "workflow": "Pipeline Intelligence",
                        "type": "new_data",
                        "message": f"New landscape data: {landscape.total_drugs} drugs",
                        "severity": "info",
                    })

            if disease_results.get("disease_intel", {}).get("success"):
                intel = disease_results["disease_intel"].get("data")
                if intel:
                    conflicts.append({
                        "disease": disease,
                        "workflow": "Disease Intelligence",
                        "type": "new_data",
                        "message": f"Updated disease data",
                        "severity": "info",
                    })

    return conflicts


def render_disease_selector(diseases: List[Dict[str, Any]]) -> List[str]:
    """Render multi-select disease selector with info."""
    st.subheader("Select Diseases")

    # Create display options
    disease_options = {}
    for d in diseases:
        label = f"{d['disease']} ({d['drug_count']} drugs, {d['paper_count']} papers)"
        disease_options[label] = d['disease']

    selected_labels = st.multiselect(
        "Choose up to 5 diseases to analyze",
        options=list(disease_options.keys()),
        max_selections=5,
        help="Select diseases from your Case Series Browser data"
    )

    selected_diseases = [disease_options[label] for label in selected_labels]

    if selected_diseases:
        st.info(f"Selected {len(selected_diseases)} disease(s)")

        # Show last run info for selected diseases
        with st.expander("Last Run Info"):
            for disease in selected_diseases:
                col1, col2, col3 = st.columns([3, 2, 2])
                with col1:
                    st.write(f"**{disease}**")
                with col2:
                    last_pipeline = get_last_workflow_run(disease, "pipeline")
                    if last_pipeline:
                        st.caption(f"Pipeline: {last_pipeline.strftime('%Y-%m-%d %H:%M')}")
                    else:
                        st.caption("Pipeline: Never")
                with col3:
                    last_disease = get_last_workflow_run(disease, "disease")
                    if last_disease:
                        st.caption(f"Disease Intel: {last_disease.strftime('%Y-%m-%d %H:%M')}")
                    else:
                        st.caption("Disease Intel: Never")

    return selected_diseases


def render_workflow_options() -> Tuple[bool, bool, bool, bool, str]:
    """Render workflow selection options."""
    st.subheader("Workflow Options")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Select Workflows**")

        # Unified analysis option (recommended)
        if UNIFIED_ORCHESTRATOR_AVAILABLE:
            run_unified = st.checkbox(
                "Unified Analysis (Recommended)",
                value=True,
                help="Runs Pipeline + Disease Intelligence in a coordinated workflow. "
                     "Shares data between them to avoid duplication and build hybrid treatment paradigm."
            )
        else:
            run_unified = False
            st.info("Unified orchestrator not available")

        # Individual workflow options (disabled if unified is selected)
        st.markdown("*Or run individually:*")
        run_pipeline = st.checkbox(
            "Pipeline Intelligence",
            value=False,
            disabled=run_unified,
            help="Extract competitive landscape: approved drugs, clinical trials, discontinued programs"
        )
        run_disease_intel = st.checkbox(
            "Disease Intelligence",
            value=False,
            disabled=run_unified,
            help="Extract market data: prevalence, treatment paradigms, failure rates"
        )

    with col2:
        st.markdown("**Run Mode**")
        run_mode = st.radio(
            "Select mode",
            ["Update (Incremental)", "Full Refresh"],
            help="Update uses cached data where available; Full Refresh re-extracts everything"
        )
        force_refresh = run_mode == "Full Refresh"

        st.markdown("**Therapeutic Area**")
        therapeutic_area = st.selectbox(
            "Area",
            ["Autoimmune", "Oncology", "Neurology", "Cardiology", "Dermatology", "Rare Disease", "Other"],
            label_visibility="collapsed"
        )

    return run_unified, run_pipeline, run_disease_intel, force_refresh, therapeutic_area


def render_results(results: Dict[str, Dict[str, Any]], conflicts: List[Dict[str, Any]]):
    """Render workflow results."""
    st.subheader("Results")

    # Summary metrics
    total_diseases = len(results)
    unified_success = sum(1 for r in results.values() if r.get("unified", {}).get("success"))
    pipeline_success = sum(1 for r in results.values() if r.get("pipeline", {}).get("success"))
    disease_success = sum(1 for r in results.values() if r.get("disease_intel", {}).get("success"))

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Diseases Processed", total_diseases)
    with col2:
        if unified_success > 0:
            st.metric("Unified Success", f"{unified_success}/{total_diseases}")
        else:
            st.metric("Pipeline Success", f"{pipeline_success}/{total_diseases}")
    with col3:
        if unified_success > 0:
            st.metric("Market Data", f"{disease_success}/{total_diseases}")
        else:
            st.metric("Disease Intel Success", f"{disease_success}/{total_diseases}")
    with col4:
        st.metric("Items for Review", len(conflicts))

    st.divider()

    # Results by disease
    for disease, disease_results in results.items():
        unified = disease_results.get("unified")

        with st.expander(f"**{disease}**", expanded=True):
            # Check if unified analysis was run
            if unified and unified.get("success"):
                # Display unified analysis results
                st.success(f"**Unified Analysis:** {unified['message']}")

                unified_data = unified.get("data")
                if unified_data:
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.markdown("**Competitive Landscape**")
                        if unified_data.landscape:
                            landscape = unified_data.landscape
                            st.caption(f"Approved: {landscape.approved_count}")
                            st.caption(f"Phase 3: {landscape.phase3_count}")
                            st.caption(f"Phase 2: {landscape.phase2_count}")
                            st.caption(f"Total Pipeline: {landscape.total_drugs}")

                    with col2:
                        st.markdown("**Market Sizing**")
                        if unified_data.disease_intel and unified_data.disease_intel.prevalence:
                            intel = unified_data.disease_intel
                            if intel.prevalence.total_patients:
                                st.caption(f"Prevalence: {intel.prevalence.total_patients:,}")
                            if intel.segmentation.pct_treated:
                                st.caption(f"Treated: {intel.segmentation.pct_treated:.1f}%")
                            if intel.failure_rates.fail_1L_pct:
                                st.caption(f"Fail 1L: {intel.failure_rates.fail_1L_pct:.1f}%")

                    with col3:
                        st.markdown("**Market Opportunity**")
                        if unified_data.market_opportunity:
                            mo = unified_data.market_opportunity
                            if mo.addressable_2L:
                                st.caption(f"Addressable 2L: {mo.addressable_2L:,}")
                            if mo.market_size_2L_formatted:
                                st.caption(f"Market Size: {mo.market_size_2L_formatted}")
                            if mo.data_quality:
                                st.caption(f"Data Quality: {mo.data_quality}")

                    # Show errors if any
                    if unified_data.errors:
                        st.warning(f"Errors: {', '.join(unified_data.errors)}")
            else:
                # Display individual workflow results
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**Pipeline Intelligence**")
                    pipeline = disease_results.get("pipeline")
                    if pipeline:
                        if pipeline["success"]:
                            st.success(pipeline["message"])
                            if pipeline["data"]:
                                landscape = pipeline["data"]
                                st.caption(f"Approved: {landscape.approved_count} | Phase 3: {landscape.phase3_count} | Phase 2: {landscape.phase2_count}")
                        else:
                            st.error(pipeline["message"])
                    else:
                        st.info("Not run")

                with col2:
                    st.markdown("**Disease Intelligence**")
                    disease_intel = disease_results.get("disease_intel")
                    if disease_intel:
                        if disease_intel["success"]:
                            st.success(disease_intel["message"])
                            if disease_intel["data"]:
                                intel = disease_intel["data"]
                                if intel.prevalence and intel.prevalence.total_patients:
                                    st.caption(f"Prevalence: {intel.prevalence.total_patients:,} patients")
                        else:
                            st.error(disease_intel["message"])
                    else:
                        st.info("Not run")

    # Conflicts/Review items
    if conflicts:
        st.divider()
        st.subheader("Items for Review")

        for conflict in conflicts:
            severity_icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(conflict["severity"], "ℹ️")
            st.markdown(f"{severity_icon} **{conflict['disease']}** - {conflict['workflow']}: {conflict['message']}")


def main():
    st.title("Disease Analysis")
    st.caption("Run Pipeline and Disease Intelligence workflows, and browse past results")

    # Create tabs
    tab1, tab2 = st.tabs(["Browse Results", "Run New Analysis"])

    with tab1:
        render_results_browser()

    with tab2:
        # Get diseases from case series
        diseases = get_unique_diseases()

        if not diseases:
            st.warning("No diseases found in Case Series Browser. Please run case series analysis first.")
            st.stop()

        st.info(f"Found {len(diseases)} diseases in Case Series Browser")

        # Disease selector
        selected_diseases = render_disease_selector(diseases)

        st.divider()

        # Workflow options
        run_unified, run_pipeline, run_disease_intel, force_refresh, therapeutic_area = render_workflow_options()

        st.divider()

        # Run button
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            run_button = st.button(
                "Run Analysis",
                type="primary",
                use_container_width=True,
                disabled=not selected_diseases or (not run_unified and not run_pipeline and not run_disease_intel)
            )

        # Run workflows
        if run_button:
            if not selected_diseases:
                st.error("Please select at least one disease")
                return

            if not run_unified and not run_pipeline and not run_disease_intel:
                st.error("Please select at least one workflow")
                return

            workflow_names = []
            if run_unified:
                workflow_names.append("Unified Analysis (Pipeline + Disease Intelligence)")
            else:
                if run_pipeline:
                    workflow_names.append("Pipeline Intelligence")
                if run_disease_intel:
                    workflow_names.append("Disease Intelligence")

            st.markdown(f"**Running:** {', '.join(workflow_names)} for {len(selected_diseases)} disease(s)")

            progress_bar = st.progress(0)
            status_text = st.empty()

            def update_progress(pct):
                progress_bar.progress(pct)
                status_text.text(f"Progress: {int(pct * 100)}%")

            with st.spinner("Running workflows..."):
                try:
                    results = asyncio.run(run_workflows_parallel(
                        diseases=selected_diseases,
                        therapeutic_area=therapeutic_area,
                        run_unified=run_unified,
                        run_pipeline=run_pipeline,
                        run_disease_intel=run_disease_intel,
                        force_refresh=force_refresh,
                        progress_callback=update_progress,
                    ))

                    progress_bar.progress(1.0)
                    status_text.text("Complete!")

                    # Detect conflicts
                    conflicts = detect_conflicts(results)

                    # Store results in session state
                    st.session_state["analysis_results"] = results
                    st.session_state["analysis_conflicts"] = conflicts

                    st.success("Analysis complete!")

                except Exception as e:
                    st.error(f"Error during analysis: {e}")
                    import traceback
                    st.code(traceback.format_exc())

        # Show results if available
        if "analysis_results" in st.session_state:
            st.divider()
            render_results(
                st.session_state["analysis_results"],
                st.session_state.get("analysis_conflicts", [])
            )


if __name__ == "__main__":
    main()
