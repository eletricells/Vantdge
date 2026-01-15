"""
Disease Intelligence Database - View and populate disease market data.

Displays the treatment funnel for diseases:
- Prevalence → Treated → Fail 1L → Addressable market
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime
import asyncio
import pandas as pd

# Add paths
frontend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auth import check_password, check_page_access, show_access_denied

st.set_page_config(
    page_title="Disease Intelligence",
    page_icon="🏥",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

# Page access check
if not check_page_access("Disease_Intelligence"):
    show_access_denied()

# Import after auth check
from dotenv import load_dotenv
load_dotenv()

from src.drug_extraction_system.database.connection import DatabaseConnection
from src.disease_intelligence.repository import DiseaseIntelligenceRepository
from src.disease_intelligence.models import (
    DiseaseIntelligence,
    PrevalenceData,
    PatientSegmentation,
    TreatmentParadigm,
    TreatmentLine,
    TreatmentDrug,
    FailureRates,
    SeverityBreakdown,
)


def format_number(n: int) -> str:
    """Format large numbers with K/M suffix."""
    if n is None:
        return "N/A"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def format_currency(n: int) -> str:
    """Format currency with B/M suffix."""
    if n is None:
        return "N/A"
    if n >= 1_000_000_000:
        return f"${n / 1_000_000_000:.1f}B"
    elif n >= 1_000_000:
        return f"${n / 1_000_000:.0f}M"
    return f"${n:,}"


def superscript(n: int) -> str:
    """Convert number to superscript for citations."""
    superscript_map = {'0': '\u2070', '1': '\u00b9', '2': '\u00b2', '3': '\u00b3',
                       '4': '\u2074', '5': '\u2075', '6': '\u2076', '7': '\u2077',
                       '8': '\u2078', '9': '\u2079'}
    return ''.join(superscript_map.get(c, c) for c in str(n))


def format_with_citation(value: str, citation_nums: list) -> str:
    """Format a value with superscript citation numbers."""
    if not citation_nums:
        return value
    citations = ''.join(superscript(n) for n in citation_nums)
    return f"{value}{citations}"


def render_market_funnel(disease: DiseaseIntelligence, sources_map: dict = None):
    """Render the market funnel visualization."""
    st.subheader("Market Funnel")

    if not disease.market_funnel:
        disease.calculate_market_funnel()

    funnel = disease.market_funnel
    if not funnel:
        st.warning("Unable to calculate market funnel - missing data")
        return

    # Create funnel visualization
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Patients",
            format_number(funnel.total_patients),
            help="Total US patient population"
        )

    with col2:
        pct_treated = disease.segmentation.pct_treated or 0
        st.metric(
            "Treated",
            format_number(funnel.patients_treated),
            f"{pct_treated:.0f}% of total",
            help="Patients receiving any treatment"
        )

    with col3:
        fail_pct = disease.failure_rates.fail_1L_pct or 0
        st.metric(
            "Fail 1L",
            format_number(funnel.patients_fail_1L),
            f"{fail_pct:.0f}% of treated",
            help="Patients with inadequate response to 1L"
        )

    with col4:
        st.metric(
            "Market Size (2L)",
            format_currency(funnel.market_size_2L_usd),
            help="Total addressable market for 2L therapies"
        )

    # Show calculation
    if funnel.market_size_2L_usd:
        avg_cost = funnel.avg_annual_cost_2L or 0
        st.caption(
            f"Calculation: {format_number(funnel.patients_addressable_2L)} patients × "
            f"${avg_cost:,.0f}/year = {format_currency(funnel.market_size_2L_usd)}"
        )


def render_disease_detail(disease: DiseaseIntelligence, repo: DiseaseIntelligenceRepository):
    """Render full disease detail view on a single page with proper citations."""
    st.header(disease.disease_name)

    if disease.therapeutic_area:
        st.caption(f"Therapeutic Area: {disease.therapeutic_area}")

    # Data quality badge
    quality_colors = {"High": "green", "Medium": "orange", "Low": "red"}
    quality = disease.data_quality or "Unknown"
    st.markdown(f"Data Quality: :{quality_colors.get(quality, 'gray')}[{quality}]")

    st.divider()

    # Build sources map for citations
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

    # === MARKET FUNNEL ===
    render_market_funnel(disease)

    st.divider()

    # === PREVALENCE ===
    st.subheader("Prevalence")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        value = format_number(prev.total_patients)
        if prevalence_citations:
            st.markdown(f"**Total Patients**")
            st.markdown(f"### {value}" + ''.join(superscript(n) for n in prevalence_citations))
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

    # Show prevalence estimates table if we have multiple sources
    if prev.source_estimates and len(prev.source_estimates) > 0:
        with st.expander(f"Prevalence Methodology ({len(prev.source_estimates)} sources)", expanded=True):
            if prev.methodology_notes:
                st.info(prev.methodology_notes)
            else:
                st.info("Consensus derived from median of available estimates")

            # Build table of estimates
            est_data = []
            for i, est in enumerate(prev.source_estimates):
                short_title = (est.title[:50] + '...') if est.title and len(est.title) > 50 else (est.title or 'Unknown')
                # Format estimate type for display
                est_type = est.estimate_type or ''
                if est_type == 'incidence':
                    est_type = '⚠️ Incidence'  # Flag incidence to differentiate from prevalence
                elif est_type == 'prevalence':
                    est_type = 'Prevalence'
                elif est_type == 'point_prevalence':
                    est_type = 'Point Prev.'
                elif est_type == 'period_prevalence':
                    est_type = 'Period Prev.'
                # Use regular numbers for table (not superscript - too small)
                citation_num = f"[{prevalence_citations[i]}]" if i < len(prevalence_citations) else ''
                est_data.append({
                    'Ref': citation_num,
                    'Source': short_title,
                    'PMID': est.pmid or '',
                    'Type': est_type,
                    'Year': est.year or '',
                    'Patients': format_number(est.total_patients) if est.total_patients else '',
                    'Rate': est.prevalence_rate or '',
                    'Method': est.methodology or '',
                    'Quality': est.quality_tier or '',
                })

            st.dataframe(pd.DataFrame(est_data), hide_index=True, use_container_width=True)
            st.caption("⚠️ Note: Incidence estimates (new cases/year) are excluded from consensus prevalence calculation.")

            if prev.estimate_range:
                st.caption(f"Range of estimates: {prev.estimate_range}")
    elif prev.prevalence_source:
        st.caption(f"Source: {prev.prevalence_source} ({prev.prevalence_year or 'N/A'})")

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
                st.metric("% Treated", f"{seg.pct_treated:.0f}%")
                # Show source and confidence for treatment rate
                if hasattr(seg, 'pct_treated_source') and seg.pct_treated_source:
                    st.caption(f"Source: {seg.pct_treated_source[:50]}...")
                if hasattr(seg, 'treatment_rate_confidence') and seg.treatment_rate_confidence:
                    st.caption(f"Confidence: {seg.treatment_rate_confidence}")
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

        # Show treatment rate estimates if available
        if hasattr(seg, 'treatment_estimates') and seg.treatment_estimates and len(seg.treatment_estimates) > 0:
            with st.expander(f"Treatment Rate Sources ({len(seg.treatment_estimates)} sources)", expanded=False):
                if hasattr(seg, 'treatment_rate_confidence_rationale') and seg.treatment_rate_confidence_rationale:
                    st.info(seg.treatment_rate_confidence_rationale)
                est_data = []
                for est in seg.treatment_estimates:
                    short_title = (est.title[:40] + '...') if est.title and len(est.title) > 40 else (est.title or 'Unknown')
                    est_data.append({
                        'Source': short_title,
                        'PMID': est.pmid or '',
                        'Year': est.year or '',
                        '% Treated': f"{est.pct_treated:.0f}%" if est.pct_treated else '',
                        'Definition': (est.treatment_definition[:30] + '...') if est.treatment_definition and len(est.treatment_definition) > 30 else (est.treatment_definition or ''),
                        'Quality': est.quality_tier or '',
                    })
                st.dataframe(pd.DataFrame(est_data), hide_index=True, use_container_width=True)
                if hasattr(seg, 'treatment_rate_range') and seg.treatment_rate_range:
                    st.caption(f"Range of estimates: {seg.treatment_rate_range}")

    with col_right:
        st.subheader("Failure Rates")

        col1, col2 = st.columns(2)
        with col1:
            if fr.fail_1L_pct:
                value = f"{fr.fail_1L_pct:.0f}%"
                if failure_citations:
                    st.markdown("**Fail 1L**")
                    st.markdown(f"### {value}" + ''.join(superscript(n) for n in failure_citations))
                else:
                    st.metric("Fail 1L", value)
                if fr.fail_1L_reason:
                    st.caption(f"Reason: {fr.fail_1L_reason}")
                # Show source info for fail 1L
                if hasattr(fr, 'fail_1L_source') and fr.fail_1L_source:
                    source_count = getattr(fr, 'fail_1L_source_count', None)
                    if source_count and source_count > 1:
                        st.caption(f"Source: {fr.fail_1L_source[:40]}... ({source_count} sources)")
                    else:
                        st.caption(f"Source: {fr.fail_1L_source[:50]}...")
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

    # Show failure rate estimates if available
    if fr.source_estimates and len(fr.source_estimates) > 0:
        with st.expander(f"Failure Rate Methodology ({len(fr.source_estimates)} sources)", expanded=False):
            if fr.methodology_notes:
                st.info(fr.methodology_notes)

            est_data = []
            for i, est in enumerate(fr.source_estimates):
                short_title = (est.title[:40] + '...') if est.title and len(est.title) > 40 else (est.title or 'Unknown')
                # Format failure type for readability
                fail_type = est.failure_type or ''
                if fail_type == 'primary_nonresponse':
                    fail_type = 'Primary Non-resp'
                elif fail_type == 'secondary_loss_of_response':
                    fail_type = 'Secondary Loss'
                elif fail_type == 'discontinuation_any_reason':
                    fail_type = 'Discontinuation'
                # Use regular numbers for table (not superscript - too small)
                citation_num = f"[{failure_citations[i]}]" if i < len(failure_citations) else ''
                est_data.append({
                    'Ref': citation_num,
                    'Source': short_title,
                    'PMID': est.pmid or '',
                    'Line': est.line_of_therapy or '',
                    'Type': fail_type,
                    'Year': est.year or '',
                    'Rate': f"{est.fail_rate_pct:.0f}%" if est.fail_rate_pct else '',
                    'Endpoint': est.clinical_endpoint or '',
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
    with col2:
        if tp and tp.second_line and tp.second_line.drugs:
            st.markdown("**Second-Line (2L)**")
            for drug in tp.second_line.drugs[:5]:
                wac = f" - ${drug.wac_monthly:,.0f}/mo" if drug.wac_monthly else ""
                st.markdown(f"- {drug.drug_name}{wac}")

    if not tp or (not tp.first_line and not tp.second_line):
        st.caption("No treatment data available")

    st.divider()

    # === COMPETITIVE LANDSCAPE (DRUGS) ===
    st.subheader("Competitive Landscape")

    drugs = repo.get_drugs_for_disease(disease.disease_name)

    if drugs:
        phase_order = ["Approved", "Phase 3", "Phase 2", "Phase 1", "Preclinical"]
        drugs_by_phase = {}
        for drug in drugs:
            phase = drug.get("highest_phase") or "Unknown"
            if phase not in drugs_by_phase:
                drugs_by_phase[phase] = []
            drugs_by_phase[phase].append(drug)

        phase_counts = []
        for phase in phase_order:
            if phase in drugs_by_phase:
                phase_counts.append(f"{phase}: {len(drugs_by_phase[phase])}")
        if "Unknown" in drugs_by_phase:
            phase_counts.append(f"Unknown: {len(drugs_by_phase['Unknown'])}")

        st.caption(f"{len(drugs)} drugs total - " + " | ".join(phase_counts))

        phase_tabs = [p for p in phase_order if p in drugs_by_phase]
        if "Unknown" in drugs_by_phase:
            phase_tabs.append("Unknown")

        if phase_tabs:
            tabs = st.tabs([f"{p} ({len(drugs_by_phase[p])})" for p in phase_tabs])
            for i, phase in enumerate(phase_tabs):
                with tabs[i]:
                    table_data = []
                    for drug in drugs_by_phase[phase]:
                        table_data.append({
                            "Drug": drug.get('brand_name') or drug.get('generic_name') or 'Unknown',
                            "Generic": drug.get('generic_name') or '',
                            "Manufacturer": drug.get('manufacturer') or '',
                            "MOA": drug.get('mechanism_of_action') or '',
                            "Type": drug.get('drug_type') or '',
                        })
                    st.dataframe(pd.DataFrame(table_data), hide_index=True, use_container_width=True)
    else:
        st.info("No drugs found. Run Pipeline Intelligence to populate competitive landscape.")

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

            col1, col2, col3 = st.columns([0.5, 4, 1])
            with col1:
                st.markdown(f"**{superscript(num)}**")
            with col2:
                st.markdown(f"{citation_text} {link}")
            with col3:
                if value:
                    st.caption(f"{data_type}: {value}")
    elif disease.sources:
        for i, source in enumerate(disease.sources):
            col1, col2 = st.columns([4, 1])
            with col1:
                title = source.title or 'Untitled'
                if source.pmid:
                    st.markdown(f"{superscript(i+1)} [{title}](https://pubmed.ncbi.nlm.nih.gov/{source.pmid})")
                elif source.url:
                    st.markdown(f"{superscript(i+1)} [{title}]({source.url})")
                else:
                    st.markdown(f"{superscript(i+1)} {title}")
            with col2:
                st.caption(f"{source.source_type} | {source.quality_tier or 'N/A'}")
    else:
        st.info("No sources recorded - data needs proper citation")

    # === PIPELINE RUNS ===
    with st.expander("Pipeline Extraction History", expanded=False):
        runs = repo.get_pipeline_runs(disease.disease_id)

        if runs:
            # Summary
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Runs", len(runs))
            with col2:
                completed = sum(1 for r in runs if r.get("status") == "completed")
                st.metric("Completed", completed)
            with col3:
                total_trials = sum(r.get("clinicaltrials_searched") or 0 for r in runs)
                st.metric("Trials Searched", total_trials)

            # Runs table
            runs_df = pd.DataFrame(runs)
            if not runs_df.empty:
                display_cols = ["run_timestamp", "run_type", "status", "drugs_found_total", "drugs_new"]
                display_cols = [c for c in display_cols if c in runs_df.columns]
                rename_map = {
                    "run_timestamp": "Timestamp",
                    "run_type": "Type",
                    "status": "Status",
                    "drugs_found_total": "Found",
                    "drugs_new": "New"
                }
                df_display = runs_df[display_cols].copy()
                df_display.columns = [rename_map.get(c, c) for c in display_cols]
                if "Timestamp" in df_display.columns:
                    df_display["Timestamp"] = pd.to_datetime(df_display["Timestamp"]).dt.strftime("%Y-%m-%d %H:%M")
                st.dataframe(df_display, hide_index=True, use_container_width=True)
        else:
            st.info("No pipeline runs recorded")


def render_manual_entry_form(repo: DiseaseIntelligenceRepository):
    """Render form for manual data entry."""
    st.subheader("Manual Data Entry")

    with st.form("disease_form"):
        # Basic info
        disease_name = st.text_input("Disease Name*", placeholder="e.g., Systemic Lupus Erythematosus")
        therapeutic_area = st.selectbox(
            "Therapeutic Area",
            ["", "Autoimmune", "Oncology", "Neurology", "Cardiology", "Dermatology", "Rare Disease", "Other"]
        )

        st.divider()

        # Prevalence
        st.markdown("**Prevalence**")
        col1, col2 = st.columns(2)
        with col1:
            total_patients = st.number_input("Total US Patients", min_value=0, step=1000)
        with col2:
            prevalence_source = st.text_input("Source", placeholder="e.g., CDC, NIH GARD")

        st.divider()

        # Segmentation
        st.markdown("**Patient Segmentation**")
        col1, col2 = st.columns(2)
        with col1:
            pct_treated = st.number_input("% Treated", min_value=0.0, max_value=100.0, step=1.0)
        with col2:
            fail_1L_pct = st.number_input("% Fail 1L", min_value=0.0, max_value=100.0, step=1.0)

        st.divider()

        # 2L drugs
        st.markdown("**Second-Line Therapies**")
        drug_2L_1 = st.text_input("2L Drug 1", placeholder="e.g., Benlysta")
        drug_2L_1_wac = st.number_input("Monthly WAC ($)", min_value=0.0, step=100.0, key="wac1")

        submitted = st.form_submit_button("Save Disease")

        if submitted and disease_name:
            # Build disease object
            disease = DiseaseIntelligence(
                disease_name=disease_name,
                therapeutic_area=therapeutic_area if therapeutic_area else None,
                prevalence=PrevalenceData(
                    total_patients=int(total_patients) if total_patients else None,
                    prevalence_source=prevalence_source if prevalence_source else None,
                ),
                segmentation=PatientSegmentation(
                    pct_treated=pct_treated if pct_treated else None,
                ),
                failure_rates=FailureRates(
                    fail_1L_pct=fail_1L_pct if fail_1L_pct else None,
                ),
            )

            # Add 2L drug if provided
            if drug_2L_1:
                disease.treatment_paradigm = TreatmentParadigm(
                    second_line=TreatmentLine(
                        line="2L",
                        drugs=[TreatmentDrug(
                            drug_name=drug_2L_1,
                            wac_monthly=drug_2L_1_wac if drug_2L_1_wac else None,
                        )]
                    )
                )

            # Calculate funnel
            disease.calculate_market_funnel()

            # Save
            try:
                disease_id = repo.save_disease(disease)
                st.success(f"Saved {disease_name} (ID: {disease_id})")
                st.rerun()
            except Exception as e:
                st.error(f"Error saving: {e}")


def run_disease_population(disease_name: str, therapeutic_area: str, repo, db):
    """Run the disease intelligence extraction process."""
    import os
    from pathlib import Path
    import sys

    st.subheader("Populating Disease Data from Literature")

    # Progress placeholder
    progress_bar = st.progress(0)
    status_text = st.empty()
    log_container = st.container()

    try:
        # Import required modules
        status_text.text("Initializing extraction service...")
        progress_bar.progress(5)

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        from src.tools.pubmed import PubMedAPI
        from src.tools.web_search import create_web_searcher
        from src.disease_intelligence.service import DiseaseIntelligenceService

        # Create searchers
        pubmed = PubMedAPI()
        web_searcher = create_web_searcher()

        # Create LLM client
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            st.error("ANTHROPIC_API_KEY not set. Cannot run extraction.")
            st.session_state["populate_disease"] = None
            return

        from anthropic import Anthropic

        class AnthropicLLMClient:
            def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
                self._client = Anthropic(api_key=api_key)
                self._model = model

            async def complete(self, prompt: str, max_tokens: int = 4000, temperature: float = 0.0,
                             system: str = None, cache_system: bool = False, model: str = None) -> str:
                messages = [{"role": "user", "content": prompt}]
                kwargs = {
                    "model": model or self._model,
                    "max_tokens": max_tokens,
                    "messages": messages,
                }
                if system:
                    kwargs["system"] = system
                if temperature > 0:
                    kwargs["temperature"] = temperature

                response = self._client.messages.create(**kwargs)
                return response.content[0].text

        llm_client = AnthropicLLMClient(api_key)

        # Create service
        service = DiseaseIntelligenceService(
            pubmed_searcher=pubmed,
            semantic_scholar_searcher=None,  # Optional
            web_searcher=web_searcher,
            llm_client=llm_client,
            repository=repo,
        )

        status_text.text("Searching PubMed for prevalence data...")
        progress_bar.progress(10)
        with log_container:
            st.info("Phase 1: Multi-source literature search")

        # Run the population (async)
        import asyncio

        async def do_population():
            return await service.populate_disease(
                disease_name=disease_name,
                therapeutic_area=therapeutic_area,
                force_refresh=True,
            )

        # Update progress during execution
        status_text.text("Extracting prevalence, treatment, and failure rate data...")
        progress_bar.progress(30)

        # Run async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(do_population())
        finally:
            loop.close()

        progress_bar.progress(100)
        status_text.text("Extraction complete!")

        # Show results
        with log_container:
            st.success(f"Successfully populated {disease_name}")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Prevalence Estimates", len(result.prevalence.source_estimates))
            with col2:
                st.metric("Failure Rate Estimates", len(result.failure_rates.source_estimates))
            with col3:
                st.metric("Data Quality", result.data_quality or "Unknown")

            if result.prevalence.total_patients:
                st.info(f"Total Patients: {format_number(result.prevalence.total_patients)}")

            if result.prevalence.source_estimates:
                st.markdown("**Prevalence Sources Found:**")
                for est in result.prevalence.source_estimates[:5]:
                    st.caption(f"- {est.title} ({est.year}): {format_number(est.total_patients) if est.total_patients else 'N/A'}")

        # Clear the populate flag and refresh
        st.session_state["populate_disease"] = None
        if st.button("Refresh Page"):
            st.rerun()

    except Exception as e:
        progress_bar.progress(0)
        status_text.text("Extraction failed")
        st.error(f"Error during extraction: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
        st.session_state["populate_disease"] = None


def main():
    st.title("Disease Intelligence Database")
    st.caption("Treatment funnel data for market sizing")

    # Initialize database
    try:
        db = DatabaseConnection()
        repo = DiseaseIntelligenceRepository(db)
    except Exception as e:
        st.error(f"Database connection error: {e}")
        st.stop()

    # Sidebar - disease list
    with st.sidebar:
        st.header("Diseases")

        # Get all diseases
        diseases = repo.list_diseases()

        if diseases:
            # Filter by therapeutic area
            areas = list(set(d.get("therapeutic_area") or "Uncategorized" for d in diseases))
            areas.sort()
            selected_area = st.selectbox("Filter by Area", ["All"] + areas)

            if selected_area != "All":
                diseases = [d for d in diseases if (d.get("therapeutic_area") or "Uncategorized") == selected_area]

            # Disease selector
            disease_options = {d["disease_name"]: d["disease_id"] for d in diseases}
            selected_disease = st.selectbox(
                "Select Disease",
                options=list(disease_options.keys()),
            )
        else:
            selected_disease = None
            st.info("No diseases in database yet")

        st.divider()

        # Add new disease button
        if st.button("➕ Add New Disease", use_container_width=True):
            st.session_state["show_form"] = True

    # Main content
    if st.session_state.get("show_form"):
        render_manual_entry_form(repo)

        if st.button("Cancel"):
            st.session_state["show_form"] = False
            st.rerun()

    elif selected_disease:
        disease = repo.get_disease(selected_disease)
        if disease:
            render_disease_detail(disease, repo)

            st.divider()

            # Action buttons
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if st.button("Populate Data from Literature", use_container_width=True, type="primary"):
                    st.session_state["populate_disease"] = disease.disease_name
                    st.rerun()
            with col2:
                if st.button("Edit", use_container_width=True):
                    st.session_state["show_form"] = True
                    st.rerun()
            with col3:
                if st.button("Delete", type="secondary", use_container_width=True):
                    if st.session_state.get("confirm_delete"):
                        repo.delete_disease(disease.disease_id)
                        st.success("Deleted")
                        st.session_state["confirm_delete"] = False
                        st.rerun()
                    else:
                        st.session_state["confirm_delete"] = True
                        st.warning("Click Delete again to confirm")

            # Handle population request
            if st.session_state.get("populate_disease") == disease.disease_name:
                run_disease_population(disease.disease_name, disease.therapeutic_area, repo, db)
        else:
            st.error("Disease not found")
    else:
        st.info("Select a disease from the sidebar or add a new one")

        # Show summary if we have diseases
        if diseases:
            st.subheader("Database Summary")

            # Summary metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Diseases", len(diseases))
            with col2:
                with_funnel = sum(1 for d in diseases if d.get("market_size_2l_usd"))
                st.metric("With Market Data", with_funnel)
            with col3:
                high_quality = sum(1 for d in diseases if d.get("data_quality") == "High")
                st.metric("High Quality", high_quality)

            # Summary table (PostgreSQL lowercases column names)
            df = pd.DataFrame(diseases)
            df = df[["disease_name", "therapeutic_area", "total_patients", "market_size_2l_usd", "data_quality"]]
            df.columns = ["Disease", "Area", "Patients", "Market Size", "Quality"]
            df["Patients"] = df["Patients"].apply(lambda x: format_number(x) if x else "")
            df["Market Size"] = df["Market Size"].apply(lambda x: format_currency(x) if x else "")
            st.dataframe(df, hide_index=True, use_container_width=True)


if __name__ == "__main__":
    main()
