"""
Case Study Analysis v2 - Drug Repurposing Case Series

A modular workflow for identifying drug repurposing opportunities through:
1. Approved Indication Identification (DailyMed, Drugs.com, Database)
2. Case Series Search (PubMed + Web Search)
3. Structured Data Extraction (Claude-powered extraction)
4. Scoring & Prioritization (Clinical 50%, Evidence 25%, Market 25%)
"""

import streamlit as st
import os
import sys
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add paths
frontend_dir = Path(__file__).parent.parent
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(project_root))

from auth import check_password
from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent
from src.utils.config import get_settings
from src.visualization.case_series_charts import render_priority_matrix, render_market_opportunity

st.set_page_config(
    page_title="Case Study Analysis v2",
    page_icon="📋",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Page config
st.set_page_config(
    page_title="Case Study Analysis v2",
    page_icon="🧬",
    layout="wide"
)

st.title("🧬 Case Study Analysis v2")
st.markdown("""
**Drug Repurposing Case Series Analysis** - Identify off-label development opportunities by mining
case series and case reports from the literature. Test each workflow step individually.
""")

# Initialize session state
if 'v2_drug_name' not in st.session_state:
    st.session_state.v2_drug_name = ''
if 'v2_drug_info' not in st.session_state:
    st.session_state.v2_drug_info = None
if 'v2_case_series' not in st.session_state:
    st.session_state.v2_case_series = []
if 'v2_extractions' not in st.session_state:
    st.session_state.v2_extractions = []
if 'v2_opportunities' not in st.session_state:
    st.session_state.v2_opportunities = []
if 'v2_agent' not in st.session_state:
    st.session_state.v2_agent = None

# Check configuration
if not settings.anthropic_api_key:
    st.error("❌ Anthropic API key not configured. Please set ANTHROPIC_API_KEY in your .env file.")
    st.stop()

# Initialize agent
@st.cache_resource
def get_agent():
    """Initialize Drug Repurposing Case Series Agent."""
    database_url = getattr(settings, 'drug_database_url', None) or getattr(settings, 'disease_landscape_url', None)
    return DrugRepurposingCaseSeriesAgent(
        anthropic_api_key=settings.anthropic_api_key,
        database_url=database_url,
        case_series_database_url=database_url,  # Use same DB for case series persistence
        tavily_api_key=getattr(settings, 'tavily_api_key', None),
        pubmed_email=getattr(settings, 'pubmed_email', None) or 'noreply@example.com',
        pubmed_api_key=getattr(settings, 'pubmed_api_key', None),
        semantic_scholar_api_key=getattr(settings, 'semantic_scholar_api_key', None),
        cache_max_age_days=30
    )

try:
    agent = get_agent()
    st.session_state.v2_agent = agent
except Exception as e:
    st.error(f"Failed to initialize agent: {e}")
    logger.error(f"Agent initialization error: {e}", exc_info=True)
    st.stop()

# Sidebar - Drug Input
with st.sidebar:
    st.header("🎯 Drug Selection")

    drug_name = st.text_input(
        "Drug Name",
        value=st.session_state.v2_drug_name,
        placeholder="e.g., Metformin, Rituximab",
        help="Enter a drug brand name or generic name"
    )

    if drug_name != st.session_state.v2_drug_name:
        st.session_state.v2_drug_name = drug_name
        # Reset downstream state when drug changes
        st.session_state.v2_drug_info = None
        st.session_state.v2_case_series = []
        st.session_state.v2_extractions = []
        st.session_state.v2_opportunities = []

    st.markdown("---")

    # Status indicators
    st.subheader("📊 Workflow Status")

    col1, col2 = st.columns(2)
    with col1:
        if st.session_state.v2_drug_info:
            st.success("✅ Drug Info")
        else:
            st.info("⬜ Drug Info")

        if st.session_state.v2_extractions:
            st.success("✅ Extracted")
        else:
            st.info("⬜ Extracted")

    with col2:
        if st.session_state.v2_case_series:
            st.success("✅ Case Series")
        else:
            st.info("⬜ Case Series")

        if st.session_state.v2_opportunities:
            st.success("✅ Scored")
        else:
            st.info("⬜ Scored")

    st.markdown("---")

    if st.button("🔄 Reset All", use_container_width=True):
        st.session_state.v2_drug_name = ''
        st.session_state.v2_drug_info = None
        st.session_state.v2_case_series = []
        st.session_state.v2_extractions = []
        st.session_state.v2_opportunities = []
        st.rerun()

    # Historical Runs Section
    st.markdown("---")
    st.subheader("📜 Historical Runs")

    if agent.database_available:
        historical_runs = agent.get_historical_runs(limit=10)
        if historical_runs:
            # Create a selectbox for historical runs
            run_options = ["-- Select a run to load --"]
            run_map = {}
            for run in historical_runs:
                started = run.get('started_at')
                if started:
                    date_str = started.strftime("%Y-%m-%d %H:%M") if hasattr(started, 'strftime') else str(started)[:16]
                else:
                    date_str = "Unknown"
                status = run.get('status', 'unknown')
                opps = run.get('opportunities_found', 0) or 0
                label = f"{run.get('drug_name', 'Unknown')} ({date_str}) - {opps} opps"
                run_options.append(label)
                run_map[label] = run.get('run_id')

            selected_run = st.selectbox(
                "Load Historical Run",
                options=run_options,
                key="historical_run_select"
            )

            if selected_run != "-- Select a run to load --":
                run_id = run_map.get(selected_run)
                if run_id and st.button("📥 Load Selected Run", use_container_width=True):
                    with st.spinner("Loading historical run..."):
                        result = agent.load_historical_run(run_id)
                        if result:
                            st.session_state.v2_drug_name = result.drug_name
                            st.session_state.v2_drug_info = {
                                'drug_name': result.drug_name,
                                'generic_name': result.generic_name,
                                'mechanism': result.mechanism,
                                'target': result.target,
                                'approved_indications': result.approved_indications or []
                            }
                            st.session_state.v2_opportunities = result.opportunities
                            st.session_state.v2_extractions = [opp.extraction for opp in result.opportunities]
                            st.success(f"✅ Loaded run with {len(result.opportunities)} opportunities")
                            st.rerun()
                        else:
                            st.error("Failed to load historical run")
        else:
            st.info("No historical runs found")
    else:
        st.info("Database not connected - historical runs unavailable")

# Main content - Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "💊 Approved Indications",
    "🔍 Case Series Search",
    "📋 Data Extraction",
    "📊 Scoring & Results",
    "📈 Full Analysis",
    "📚 Analysis Browser"
])

# =====================================================
# TAB 1: APPROVED INDICATION IDENTIFICATION
# =====================================================

with tab1:
    st.header("1️⃣ Approved Indication Identification")
    st.markdown("""
    Retrieve the drug's approved indications from multiple data sources in priority order:
    1. **DrugDatabase** (PostgreSQL) - Cached data from previous runs
    2. **DailyMed API** - Official FDA drug labeling
    3. **Drugs.com Scraping** - Approved indications from drug monographs
    4. **Web Search Fallback** - Tavily search with Claude extraction
    """)

    if not st.session_state.v2_drug_name:
        st.warning("⚠️ Please enter a drug name in the sidebar to begin.")
    else:
        drug_name = st.session_state.v2_drug_name

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader(f"Drug: {drug_name}")

            if st.button("🔍 Fetch Drug Information", type="primary", use_container_width=True):
                with st.spinner(f"Fetching information for {drug_name}..."):
                    try:
                        drug_info = agent._get_drug_info(drug_name)
                        st.session_state.v2_drug_info = drug_info
                        st.success("✅ Drug information retrieved!")
                    except Exception as e:
                        st.error(f"Error fetching drug info: {e}")
                        logger.error(f"Drug info error: {e}", exc_info=True)

        with col2:
            st.metric("Status", "✅ Loaded" if st.session_state.v2_drug_info else "⬜ Not loaded")

        # Display drug info
        if st.session_state.v2_drug_info:
            info = st.session_state.v2_drug_info

            st.markdown("---")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("**Drug Name**")
                st.write(info.get('drug_name', drug_name))
            with col2:
                st.markdown("**Generic Name**")
                st.write(info.get('generic_name', 'Not available'))
            with col3:
                st.markdown("**Mechanism**")
                st.write(info.get('mechanism', 'Not available'))

            st.markdown("---")

            # Approved indications
            indications = info.get('approved_indications', [])
            st.subheader(f"📋 Approved Indications ({len(indications)})")

            if indications:
                for i, indication in enumerate(indications, 1):
                    st.markdown(f"{i}. {indication}")
            else:
                st.info("No approved indications found. The drug may be investigational or data sources may be unavailable.")

            # Raw JSON expander
            with st.expander("🔧 View Raw JSON"):
                st.json(info)

# =====================================================
# TAB 2: CASE SERIES SEARCH
# =====================================================

# Initialize grouped papers in session state
if 'v2_grouped_papers' not in st.session_state:
    st.session_state.v2_grouped_papers = {}

with tab2:
    st.header("2️⃣ Case Series Search")
    st.markdown("""
    Search for case series and case reports describing off-label use of the drug.
    Uses dual-source search strategy:
    - **PubMed** - Medical literature database
    - **Web Search** - Tavily-powered web search for additional sources

    Papers are automatically **grouped by disease/indication** after search.
    """)

    if not st.session_state.v2_drug_name:
        st.warning("⚠️ Please enter a drug name in the sidebar to begin.")
    elif not st.session_state.v2_drug_info:
        st.warning("⚠️ Please fetch drug information first (Tab 1).")
    else:
        drug_name = st.session_state.v2_drug_name

        # Search configuration
        st.markdown("### Search Configuration")

        col1, col2, col3 = st.columns(3)
        with col1:
            use_llm_filter = st.checkbox("🤖 LLM Relevance Filtering", value=True,
                                         help="Use Claude to evaluate each paper's relevance (more accurate, uses API credits)")
        with col2:
            auto_group = st.checkbox("📊 Auto-group by Disease", value=True,
                                     help="Automatically organize papers by disease/indication")
        with col3:
            include_web = st.checkbox("🌐 Include Web Search", value=False,
                                      help="Also search grey literature (may include less reliable sources)")

        # Optional: target indication filter
        target_indication = st.text_input(
            "Target Indication (optional)",
            placeholder="e.g., vitiligo, alopecia, dermatomyositis",
            help="Filter results for a specific indication or leave blank for all off-label uses"
        )

        col1, col2 = st.columns(2)
        with col1:
            search_btn = st.button("🔍 Search for Case Series", type="primary", use_container_width=True)
        with col2:
            group_btn = st.button("📊 Re-group Papers by Disease", type="secondary", use_container_width=True,
                                  disabled=not st.session_state.v2_case_series)

        # Search action
        if search_btn:
            with st.spinner(f"Searching for case series on {drug_name}..." + (" (with LLM filtering)" if use_llm_filter else "")):
                try:
                    # Get approved indications to exclude
                    drug_info = st.session_state.v2_drug_info or {}
                    exclude_indications = drug_info.get('approved_indications', [])

                    # Use the agent's search method with LLM filtering
                    case_series = agent._search_case_series(
                        drug_name=drug_name,
                        exclude_indications=exclude_indications,
                        max_papers=200,  # Get all papers, LLM will filter
                        include_web_search=include_web,
                        use_llm_filtering=use_llm_filter
                    )
                    st.session_state.v2_case_series = case_series
                    st.session_state.v2_grouped_papers = {}  # Reset grouping

                    # Count papers with full text available
                    full_text_count = sum(1 for p in case_series if p.get('has_full_text'))
                    st.success(f"✅ Found {len(case_series)} relevant case series/reports! ({full_text_count} with full text available)")
                except Exception as e:
                    st.error(f"Error searching: {e}")
                    logger.error(f"Search error: {e}", exc_info=True)

            # Auto-group if enabled and papers found
            if auto_group and st.session_state.v2_case_series:
                with st.spinner("Grouping papers by disease..."):
                    try:
                        drug_info = st.session_state.v2_drug_info or {}
                        # If LLM filtering was used, papers already have extracted_disease
                        if use_llm_filter:
                            # Use pre-extracted diseases from LLM filtering
                            from collections import defaultdict
                            grouped = defaultdict(list)
                            for paper in st.session_state.v2_case_series:
                                disease = paper.get('extracted_disease') or 'Unknown/Unclassified'
                                grouped[disease].append(paper)
                            st.session_state.v2_grouped_papers = dict(sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True))
                        else:
                            # Use full grouping method
                            grouped = agent.group_papers_by_disease(
                                papers=st.session_state.v2_case_series,
                                drug_name=drug_name,
                                drug_info=drug_info
                            )
                            st.session_state.v2_grouped_papers = grouped
                        st.success(f"✅ Grouped papers into {len(st.session_state.v2_grouped_papers)} disease categories!")
                    except Exception as e:
                        st.error(f"Error grouping papers: {e}")
                        logger.error(f"Grouping error: {e}", exc_info=True)

        # Manual group action (for re-grouping)
        if group_btn and st.session_state.v2_case_series:
            with st.spinner("Grouping papers by disease using Claude..."):
                try:
                    drug_info = st.session_state.v2_drug_info or {}
                    grouped = agent.group_papers_by_disease(
                        papers=st.session_state.v2_case_series,
                        drug_name=drug_name,
                        drug_info=drug_info
                    )
                    st.session_state.v2_grouped_papers = grouped
                    st.success(f"✅ Grouped papers into {len(grouped)} disease categories!")
                except Exception as e:
                    st.error(f"Error grouping papers: {e}")
                    logger.error(f"Grouping error: {e}", exc_info=True)

        # Display results
        if st.session_state.v2_grouped_papers:
            # Display grouped view
            st.markdown("---")
            total_papers = sum(len(p) for p in st.session_state.v2_grouped_papers.values())
            full_text_count = sum(1 for papers in st.session_state.v2_grouped_papers.values()
                                  for p in papers if p.get('has_full_text'))
            st.subheader(f"📊 {total_papers} Papers in {len(st.session_state.v2_grouped_papers)} Disease Categories")
            if full_text_count > 0:
                st.caption(f"📄 {full_text_count} papers have full text available in PubMed Central")

            for disease, papers in st.session_state.v2_grouped_papers.items():
                with st.expander(f"**🏥 {disease}** ({len(papers)} papers)", expanded=len(papers) <= 3):
                    for i, paper in enumerate(papers, 1):
                        # Build title with indicators
                        title = paper.get('title', 'Untitled')
                        indicators = []
                        if paper.get('has_full_text'):
                            indicators.append("📄")  # Full text available
                        if paper.get('llm_relevance_reason'):
                            indicators.append("✓")  # LLM verified
                        indicator_str = " ".join(indicators)

                        st.markdown(f"**{i}. {title}** {indicator_str}")

                        col1, col2, col3, col4 = st.columns([2, 1, 2, 2])
                        with col1:
                            st.caption(f"Source: {paper.get('source', 'Unknown')}")
                        with col2:
                            st.caption(f"Year: {paper.get('year', 'Unknown')}")
                        with col3:
                            if paper.get('pmid'):
                                st.caption(f"[PMID: {paper['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/)")
                        with col4:
                            if paper.get('pmcid'):
                                st.caption(f"[📄 Full Text](https://www.ncbi.nlm.nih.gov/pmc/articles/{paper['pmcid']}/)")

                        # Show LLM relevance reason if available
                        if paper.get('llm_relevance_reason'):
                            st.caption(f"💡 *{paper['llm_relevance_reason']}*")

                        # Show truncated abstract
                        abstract = paper.get('abstract') or 'No abstract available'
                        if len(abstract) > 300:
                            st.caption(abstract[:300] + "...")
                        else:
                            st.caption(abstract)
                        st.markdown("---")

        elif st.session_state.v2_case_series:
            # Display flat list (ungrouped)
            st.markdown("---")
            full_text_count = sum(1 for p in st.session_state.v2_case_series if p.get('has_full_text'))
            st.subheader(f"📚 Found {len(st.session_state.v2_case_series)} Case Series/Reports")
            if full_text_count > 0:
                st.caption(f"📄 {full_text_count} papers have full text available in PubMed Central")
            st.info("💡 Enable **Auto-group by Disease** to organize papers by indication.")

            for i, paper in enumerate(st.session_state.v2_case_series, 1):
                title = paper.get('title', 'Untitled')
                indicators = []
                if paper.get('has_full_text'):
                    indicators.append("📄")
                if paper.get('llm_relevance_reason'):
                    indicators.append("✓")
                indicator_str = " ".join(indicators)

                with st.expander(f"**{i}. {title}** {indicator_str}"):
                    col1, col2, col3, col4 = st.columns([2, 1, 2, 2])
                    with col1:
                        st.markdown(f"**Source:** {paper.get('source', 'Unknown')}")
                    with col2:
                        st.markdown(f"**Year:** {paper.get('year', 'Unknown')}")
                    with col3:
                        if paper.get('pmid'):
                            st.markdown(f"[PMID: {paper['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/)")
                    with col4:
                        if paper.get('pmcid'):
                            st.markdown(f"[📄 Full Text](https://www.ncbi.nlm.nih.gov/pmc/articles/{paper['pmcid']}/)")

                    # Show LLM relevance reason
                    if paper.get('llm_relevance_reason'):
                        st.success(f"💡 *{paper['llm_relevance_reason']}*")

                    # Show disease if extracted
                    if paper.get('extracted_disease'):
                        st.caption(f"🏥 Disease: **{paper['extracted_disease']}**")

                    st.markdown("**Abstract:**")
                    abstract = paper.get('abstract') or 'No abstract available'
                    st.write(abstract[:500] + "..." if len(abstract) > 500 else abstract)

# =====================================================
# TAB 3: STRUCTURED DATA EXTRACTION
# =====================================================

with tab3:
    st.header("3️⃣ Structured Data Extraction")
    st.markdown("""
    Extract structured clinical data from case series using Claude. Extracts:
    - **Patient Population** - Sample size, demographics, disease severity
    - **Efficacy Outcomes** - Response rates, primary/secondary endpoints
    - **Safety Outcomes** - Adverse events, SAEs, discontinuations
    - **Dosing Information** - Regimen, duration, modifications
    """)

    if not st.session_state.v2_case_series:
        st.warning("⚠️ Please search for case series first (Tab 2).")
    else:
        drug_name = st.session_state.v2_drug_name
        case_series = st.session_state.v2_case_series

        st.info(f"📚 {len(case_series)} case series available for extraction")

        # Show estimated cost for extracting all papers
        estimated_cost = len(case_series) * 0.05
        st.metric("Estimated Cost (all papers)", f"~${estimated_cost:.2f}")

        if st.button("📋 Extract Structured Data", type="primary", use_container_width=True):
            with st.spinner(f"Extracting data from {len(case_series)} papers..."):
                try:
                    extractions = []
                    progress_bar = st.progress(0)
                    drug_info = st.session_state.v2_drug_info or {}

                    total_papers = len(case_series)
                    for i, paper in enumerate(case_series):
                        # Extract using agent method with correct signature
                        extraction = agent._extract_case_series_data(
                            drug_name=drug_name,
                            drug_info=drug_info,
                            paper=paper
                        )
                        if extraction:
                            extractions.append({
                                'paper': paper,
                                'extraction': extraction
                            })
                        progress_bar.progress((i + 1) / total_papers)

                    st.session_state.v2_extractions = extractions
                    st.success(f"✅ Extracted data from {len(extractions)} papers!")
                except Exception as e:
                    st.error(f"Error extracting: {e}")
                    logger.error(f"Extraction error: {e}", exc_info=True)

        # Display extractions
        if st.session_state.v2_extractions:
            st.markdown("---")
            st.subheader(f"📊 Extracted Data ({len(st.session_state.v2_extractions)} papers)")

            for i, item in enumerate(st.session_state.v2_extractions, 1):
                paper = item['paper']
                ext = item['extraction']

                with st.expander(f"**{i}. {paper.get('title', 'Untitled')[:80]}...**"):
                    # Key metrics
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        n_patients = ext.patient_population.n_patients if hasattr(ext, 'patient_population') else 'N/A'
                        st.metric("Patients", n_patients)
                    with col2:
                        resp_pct = ext.efficacy.responders_pct if hasattr(ext, 'efficacy') and ext.efficacy else 'N/A'
                        st.metric("Response %", f"{resp_pct}%" if resp_pct != 'N/A' else 'N/A')
                    with col3:
                        signal = ext.efficacy_signal.value if hasattr(ext, 'efficacy_signal') else 'N/A'
                        st.metric("Efficacy Signal", signal)
                    with col4:
                        safety = ext.safety.safety_profile.value if hasattr(ext, 'safety') and ext.safety else 'N/A'
                        st.metric("Safety", safety)

                    # Indication
                    if hasattr(ext, 'indication_studied'):
                        st.markdown(f"**Indication:** {ext.indication_studied}")

                    # Efficacy details
                    if hasattr(ext, 'efficacy') and ext.efficacy:
                        st.markdown("**Efficacy Outcomes:**")
                        if ext.efficacy.primary_endpoint:
                            st.markdown(f"- Primary: {ext.efficacy.primary_endpoint}")
                        if ext.efficacy.efficacy_summary:
                            st.markdown(f"- Summary: {ext.efficacy.efficacy_summary}")

                    # Safety details
                    if hasattr(ext, 'safety') and ext.safety:
                        st.markdown("**Safety Outcomes:**")
                        if ext.safety.sae_percentage is not None:
                            st.markdown(f"- SAE Rate: {ext.safety.sae_percentage}%")
                        if ext.safety.safety_summary:
                            st.markdown(f"- Summary: {ext.safety.safety_summary}")

                    # Raw data
                    with st.expander("🔧 View Raw Extraction"):
                        st.json(ext.model_dump() if hasattr(ext, 'model_dump') else str(ext))



# =====================================================
# TAB 4: SCORING & RESULTS
# =====================================================

with tab4:
    st.header("4️⃣ Scoring & Prioritization")
    st.markdown("""
    Score and rank repurposing opportunities using the weighted scoring system:
    - **Clinical Signal (50%)** - Response rate + Safety profile (SAE %)
    - **Evidence Quality (25%)** - Sample size + Publication venue + Follow-up duration
    - **Market Opportunity (25%)** - Competitors + Market size + Unmet need
    """)

    if not st.session_state.v2_extractions:
        st.warning("⚠️ Please extract data first (Tab 3).")
    else:
        drug_name = st.session_state.v2_drug_name
        extractions = st.session_state.v2_extractions

        st.info(f"📊 {len(extractions)} extractions ready for scoring")

        if st.button("📈 Score Opportunities", type="primary", use_container_width=True):
            with st.spinner("Scoring opportunities..."):
                try:
                    from src.models.case_series_schemas import RepurposingOpportunity

                    opportunities = []
                    for item in extractions:
                        ext = item['extraction']

                        # Create opportunity object
                        opp = RepurposingOpportunity(extraction=ext)

                        # Score it
                        scores = agent._score_opportunity(opp)
                        opp.scores = scores
                        opportunities.append(opp)

                    # Sort by overall priority
                    opportunities.sort(key=lambda x: x.scores.overall_priority, reverse=True)
                    st.session_state.v2_opportunities = opportunities
                    st.success(f"✅ Scored {len(opportunities)} opportunities!")
                except Exception as e:
                    st.error(f"Error scoring: {e}")
                    logger.error(f"Scoring error: {e}", exc_info=True)

        # Display scored opportunities
        if st.session_state.v2_opportunities:
            st.markdown("---")

            # Create DataFrame for visualizations
            import pandas as pd

            viz_data = []
            for opp in st.session_state.v2_opportunities:
                scores = opp.scores
                ext = opp.extraction
                market_intel = opp.market_intelligence

                viz_data.append({
                    'Disease': ext.disease if ext else 'Unknown',
                    '# Studies': 1,  # Each extraction is from one paper
                    'Total Patients': ext.patient_population.n_patients if ext and ext.patient_population and ext.patient_population.n_patients else 0,
                    'Clinical Score (avg)': scores.clinical_signal,
                    'Evidence Score (avg)': scores.evidence_quality,
                    'Market Score (avg)': scores.market_opportunity,
                    'Overall Score (avg)': scores.overall_priority,
                    '# Approved Competitors': market_intel.standard_of_care.num_approved_drugs if market_intel and market_intel.standard_of_care else 0,
                    'Unmet Need': 'Yes' if market_intel and market_intel.standard_of_care and market_intel.standard_of_care.unmet_need else 'No',
                    'TAM Estimate': market_intel.tam_estimate if market_intel else 'N/A'
                })

            viz_df = pd.DataFrame(viz_data)

            # Aggregate by disease (in case multiple papers for same disease)
            agg_df = viz_df.groupby('Disease').agg({
                '# Studies': 'sum',
                'Total Patients': 'sum',
                'Clinical Score (avg)': 'mean',
                'Evidence Score (avg)': 'mean',
                'Market Score (avg)': 'mean',
                'Overall Score (avg)': 'mean',
                '# Approved Competitors': 'first',
                'Unmet Need': 'first',
                'TAM Estimate': 'first'
            }).reset_index()

            # Display visualizations
            st.subheader("📊 Visual Analysis")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Priority Matrix")
                st.caption("Clinical Signal vs Evidence Quality")
                try:
                    render_priority_matrix(
                        agg_df,
                        drug_name=st.session_state.v2_drug_name,
                        height=500
                    )
                except Exception as e:
                    st.error(f"Error rendering priority matrix: {e}")
                    logger.error(f"Priority matrix error: {e}", exc_info=True)

            with col2:
                st.markdown("#### Market Opportunity")
                st.caption("Competitive Landscape vs Priority Score")
                try:
                    render_market_opportunity(
                        agg_df,
                        drug_name=st.session_state.v2_drug_name,
                        height=500
                    )
                except Exception as e:
                    st.error(f"Error rendering market opportunity: {e}")
                    logger.error(f"Market opportunity error: {e}", exc_info=True)

            st.markdown("---")
            st.subheader("🏆 Ranked Opportunities")

            for i, opp in enumerate(st.session_state.v2_opportunities, 1):
                scores = opp.scores
                indication = opp.extraction.disease if opp.extraction else "Unknown"

                # Color-code by priority
                if scores.overall_priority >= 7:
                    priority_color = "🟢"
                elif scores.overall_priority >= 5:
                    priority_color = "🟡"
                else:
                    priority_color = "🔴"

                with st.expander(f"{priority_color} **#{i}: {indication}** (Score: {scores.overall_priority}/10)"):
                    # Overall scores
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Overall", f"{scores.overall_priority}/10")
                    with col2:
                        st.metric("Clinical (50%)", f"{scores.clinical_signal}/10")
                    with col3:
                        st.metric("Evidence (25%)", f"{scores.evidence_quality}/10")
                    with col4:
                        st.metric("Market (25%)", f"{scores.market_opportunity}/10")

                    st.markdown("---")

                    # Detailed breakdowns
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.markdown("**Clinical Breakdown**")
                        st.markdown(f"- Response Rate: {scores.response_rate_score}/10")
                        st.markdown(f"- Safety Profile: {scores.safety_profile_score}/10")

                    with col2:
                        st.markdown("**Evidence Breakdown**")
                        st.markdown(f"- Sample Size: {scores.sample_size_score}/10")
                        st.markdown(f"- Publication: {scores.publication_venue_score}/10")
                        st.markdown(f"- Follow-up: {scores.followup_duration_score}/10")

                    with col3:
                        st.markdown("**Market Breakdown**")
                        st.markdown(f"- Competitors: {scores.competitors_score}/10")
                        st.markdown(f"- Market Size: {scores.market_size_score}/10")
                        st.markdown(f"- Unmet Need: {scores.unmet_need_score}/10")



# =====================================================
# TAB 5: FULL ANALYSIS
# =====================================================

with tab5:
    st.header("5️⃣ Full Analysis Pipeline")
    st.markdown("""
    Run the complete drug repurposing analysis workflow end-to-end:
    1. Fetch drug information and approved indications
    2. Search for case series and case reports
    3. Extract structured clinical data
    4. Enrich with market intelligence
    5. Score and rank opportunities
    6. Export results
    """)

    if not st.session_state.v2_drug_name:
        st.warning("⚠️ Please enter a drug name in the sidebar to begin.")
    else:
        drug_name = st.session_state.v2_drug_name

        st.subheader(f"🎯 Analyze: {drug_name}")

        # Configuration - simplified, extract ALL papers
        include_market = st.checkbox("Include market intelligence", value=True, key="full_market")

        st.caption("💡 This will search for all case series/reports and extract data from ALL relevant papers found.")
        st.caption("💰 Estimated cost: ~$1-3 depending on number of papers (typically 30-60 minutes)")

        if st.button("🚀 Run Full Analysis", type="primary", use_container_width=True):
            progress_container = st.container()

            with progress_container:
                progress_bar = st.progress(0)
                status_text = st.empty()

                try:
                    # Use the main analyze_drug method which saves to database
                    status_text.text("Running full analysis pipeline (this may take 30-60 minutes)...")
                    progress_bar.progress(10)

                    # Call the main analyze_drug method - this saves to database!
                    # max_papers=500 effectively means "no limit" - LLM filtering will reduce to relevant papers
                    result = agent.analyze_drug(
                        drug_name=drug_name,
                        max_papers=500,
                        include_web_search=True,
                        enrich_market_data=include_market
                    )

                    progress_bar.progress(90)
                    status_text.text("Saving results...")

                    # Update session state with results
                    st.session_state.v2_drug_info = {
                        'drug_name': result.drug_name,
                        'generic_name': result.generic_name,
                        'mechanism': result.mechanism,
                        'target': result.target,
                        'approved_indications': result.approved_indications or []
                    }
                    st.session_state.v2_opportunities = result.opportunities
                    st.session_state.v2_extractions = [{'paper': {}, 'extraction': opp.extraction} for opp in result.opportunities]

                    # Auto-export to Excel
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    excel_filename = f"{drug_name.lower().replace(' ', '_')}_report_{timestamp}.xlsx"
                    json_filename = f"{drug_name.lower().replace(' ', '_')}_full_{timestamp}.json"

                    excel_path = agent.export_to_excel(result, excel_filename)
                    json_path = agent.export_to_json(result, json_filename)

                    progress_bar.progress(100)
                    status_text.text("Analysis complete!")

                    st.success(f"✅ Analysis complete! Found {len(result.opportunities)} repurposing opportunities.")

                    # Download buttons for output files
                    col1, col2 = st.columns(2)

                    with col1:
                        st.info(f"📊 Excel report: `{excel_filename}`")
                        try:
                            with open(excel_path, 'rb') as f:
                                excel_data = f.read()
                            st.download_button(
                                label="⬇️ Download Excel Report",
                                data=excel_data,
                                file_name=excel_filename,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                        except Exception as e:
                            st.error(f"Could not load Excel file: {e}")

                    with col2:
                        st.info(f"📄 JSON data: `{json_filename}`")
                        try:
                            with open(json_path, 'rb') as f:
                                json_data = f.read()
                            st.download_button(
                                label="⬇️ Download JSON Data",
                                data=json_data,
                                file_name=json_filename,
                                mime="application/json",
                                use_container_width=True
                            )
                        except Exception as e:
                            st.error(f"Could not load JSON file: {e}")

                    # Show cost info
                    if result.total_input_tokens or result.total_output_tokens:
                        input_cost = (result.total_input_tokens or 0) * 0.003 / 1000
                        output_cost = (result.total_output_tokens or 0) * 0.015 / 1000
                        total_cost = input_cost + output_cost
                        st.caption(f"💰 Estimated API cost: ${total_cost:.2f}")

                except Exception as e:
                    st.error(f"Error during analysis: {e}")
                    logger.error(f"Full analysis error: {e}", exc_info=True)

        # Show summary if we have results
        if st.session_state.v2_opportunities:
            st.markdown("---")
            st.subheader("📊 Analysis Summary")

            opps = st.session_state.v2_opportunities

            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Opportunities", len(opps))
            with col2:
                high_priority = len([o for o in opps if o.scores.overall_priority >= 7])
                st.metric("High Priority (≥7)", high_priority)
            with col3:
                avg_score = sum(o.scores.overall_priority for o in opps) / len(opps) if opps else 0
                st.metric("Avg Score", f"{avg_score:.1f}")
            with col4:
                unique_indications = len(set(o.extraction.disease for o in opps))
                st.metric("Unique Indications", unique_indications)

            # Visual Analysis
            st.markdown("### 📊 Visual Analysis")

            # Create DataFrame for visualizations
            import pandas as pd

            viz_data = []
            for opp in opps:
                scores = opp.scores
                ext = opp.extraction
                market_intel = opp.market_intelligence

                viz_data.append({
                    'Disease': ext.disease if ext else 'Unknown',
                    '# Studies': 1,
                    'Total Patients': ext.patient_population.n_patients if ext and ext.patient_population and ext.patient_population.n_patients else 0,
                    'Clinical Score (avg)': scores.clinical_signal,
                    'Evidence Score (avg)': scores.evidence_quality,
                    'Market Score (avg)': scores.market_opportunity,
                    'Overall Score (avg)': scores.overall_priority,
                    '# Approved Competitors': market_intel.standard_of_care.num_approved_drugs if market_intel and market_intel.standard_of_care else 0,
                    'Unmet Need': 'Yes' if market_intel and market_intel.standard_of_care and market_intel.standard_of_care.unmet_need else 'No',
                    'TAM Estimate': market_intel.tam_estimate if market_intel else 'N/A'
                })

            viz_df = pd.DataFrame(viz_data)

            # Aggregate by disease
            agg_df = viz_df.groupby('Disease').agg({
                '# Studies': 'sum',
                'Total Patients': 'sum',
                'Clinical Score (avg)': 'mean',
                'Evidence Score (avg)': 'mean',
                'Market Score (avg)': 'mean',
                'Overall Score (avg)': 'mean',
                '# Approved Competitors': 'first',
                'Unmet Need': 'first',
                'TAM Estimate': 'first'
            }).reset_index()

            col1, col2 = st.columns(2)

            with col1:
                try:
                    render_priority_matrix(
                        agg_df,
                        drug_name=drug_name,
                        height=500
                    )
                except Exception as e:
                    st.error(f"Error rendering priority matrix: {e}")

            with col2:
                try:
                    render_market_opportunity(
                        agg_df,
                        drug_name=drug_name,
                        height=500
                    )
                except Exception as e:
                    st.error(f"Error rendering market opportunity: {e}")

            st.markdown("---")

            # Top opportunities table
            st.markdown("### 🏆 Top Opportunities")

            table_data = []
            for opp in opps[:10]:
                indication = opp.extraction.disease if opp.extraction else "Unknown"
                table_data.append({
                    "Indication": indication[:50] + "..." if len(indication) > 50 else indication,
                    "Overall": opp.scores.overall_priority,
                    "Clinical": opp.scores.clinical_signal,
                    "Evidence": opp.scores.evidence_quality,
                    "Market": opp.scores.market_opportunity
                })

            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Export options
            st.markdown("### 💾 Export Results")
            col1, col2 = st.columns(2)

            with col1:
                # JSON export
                export_data = {
                    "drug_name": drug_name,
                    "analysis_date": datetime.now().isoformat(),
                    "opportunities": [
                        {
                            "indication": o.extraction.disease if o.extraction else "Unknown",
                            "scores": o.scores.model_dump() if hasattr(o.scores, 'model_dump') else str(o.scores)
                        }
                        for o in opps
                    ]
                }
                json_str = json.dumps(export_data, indent=2)
                st.download_button(
                    "📥 Download JSON",
                    json_str,
                    file_name=f"{drug_name}_case_series_analysis.json",
                    mime="application/json",
                    width='stretch'
                )

            with col2:
                # CSV export
                csv_data = df.to_csv(index=False)
                st.download_button(
                    "📥 Download CSV",
                    csv_data,
                    file_name=f"{drug_name}_case_series_analysis.csv",
                    mime="text/csv",
                    width='stretch'
                )

            # Report Generation Section
            st.markdown("---")
            st.markdown("### 📄 Generate Analytical Report")
            st.markdown("""
            Generate a comprehensive analytical report using Claude. The report provides:
            - **Objective analysis** of findings without strategic recommendations
            - **Score derivation** with specific data citations
            - **Concordance analysis** across studies and endpoints
            - **Cross-indication patterns** and mechanistic insights
            - **Evidence quality assessment** and limitations
            - **Competitive landscape** context
            """)

            col1, col2, col3 = st.columns([2, 1, 1])

            with col1:
                if st.button("🤖 Generate Report with Claude", type="primary", use_container_width=True):
                    with st.spinner("Generating analytical report... This may take 1-2 minutes."):
                        try:
                            # Find the most recent Excel export for this drug
                            import glob
                            excel_pattern = f"data/case_series/{drug_name.lower().replace(' ', '_')}_report_*.xlsx"
                            excel_files = glob.glob(excel_pattern)

                            if excel_files:
                                # Use most recent Excel file
                                excel_path = max(excel_files, key=os.path.getctime)

                                # Generate report
                                report_text, report_path = agent.generate_analytical_report(
                                    excel_path=excel_path,
                                    auto_save=True
                                )

                                # Store in session state
                                st.session_state.v2_generated_report = report_text
                                st.session_state.v2_report_path = report_path

                                st.success(f"✅ Report generated! Saved to: `{report_path}`")
                                st.info("📖 Scroll down to view the report")

                            else:
                                st.error("❌ No Excel export found. Please run the full analysis first.")

                        except Exception as e:
                            st.error(f"Error generating report: {e}")
                            logger.error(f"Report generation error: {e}", exc_info=True)

            with col2:
                # Show cost estimate
                st.caption("💰 Cost: ~$0.10-0.20")
                st.caption("⏱️ Time: 1-2 min")

            with col3:
                # Download button if report exists
                if 'v2_generated_report' in st.session_state and st.session_state.v2_generated_report:
                    st.download_button(
                        "📥 Download Report",
                        st.session_state.v2_generated_report,
                        file_name=f"{drug_name}_analytical_report.md",
                        mime="text/markdown",
                        use_container_width=True
                    )

            # Display generated report
            if 'v2_generated_report' in st.session_state and st.session_state.v2_generated_report:
                st.markdown("---")
                st.markdown("### 📖 Generated Analytical Report")

                # Show report in expandable section
                with st.expander("📄 View Full Report", expanded=True):
                    st.markdown(st.session_state.v2_generated_report)

                # Show report metadata
                if 'v2_report_path' in st.session_state:
                    st.caption(f"💾 Saved to: `{st.session_state.v2_report_path}`")

            # Full Excel export with detailed endpoints
            st.markdown("---")
            st.markdown("### 📊 Full Excel Export (with detailed endpoints)")
            st.caption("Exports comprehensive Excel with Summary, Opportunities, Efficacy Endpoints, Safety Endpoints, and Market Intelligence sheets")

            if st.button("📥 Export Full Excel Report", type="primary", use_container_width=True):
                with st.spinner("Generating comprehensive Excel report..."):
                    try:
                        # Build full result object for export
                        from src.models.case_series_schemas import DrugAnalysisResult

                        full_result = DrugAnalysisResult(
                            drug_name=drug_name,
                            generic_name=st.session_state.v2_drug_info.get('generic_name') if st.session_state.v2_drug_info else None,
                            mechanism=st.session_state.v2_drug_info.get('mechanism') if st.session_state.v2_drug_info else None,
                            approved_indications=st.session_state.v2_drug_info.get('approved_indications', []) if st.session_state.v2_drug_info else [],
                            opportunities=opps,
                            papers_screened=len(st.session_state.v2_case_series) if st.session_state.v2_case_series else len(opps),
                            analysis_date=datetime.now()
                        )

                        # Use agent's export method
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"{drug_name.lower().replace(' ', '_')}_report_{timestamp}.xlsx"
                        filepath = agent.export_to_excel(full_result, filename)

                        st.success(f"✅ Excel report saved to: `{filepath}`")

                        # Also provide download button
                        with open(filepath, 'rb') as f:
                            st.download_button(
                                "📥 Download Excel Report",
                                f.read(),
                                file_name=filename,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                width='stretch'
                            )
                    except Exception as e:
                        st.error(f"Error exporting: {e}")
                        logger.error(f"Excel export error: {e}", exc_info=True)

# =====================================================
# TAB 6: ANALYSIS BROWSER
# =====================================================

with tab6:
    st.header("📚 Analysis Browser")
    st.markdown("""
    Browse and explore all historical drug repurposing analyses. View complete reports with
    visualizations, tables, and export options.
    """)

    if not agent.database_available:
        st.warning("⚠️ Database not connected. Historical runs feature requires a PostgreSQL database.")
        st.info("""
        To enable historical runs:
        1. Set `DATABASE_URL` or `DRUG_DATABASE_URL` in your `.env` file
        2. Run the case series schema migration: `psql -f mcp_server/case_series_schema.sql`
        """)
    else:
        # Fetch historical runs
        runs = agent.get_historical_runs(limit=50)

        if runs:
            st.success(f"✅ Database connected - Found {len(runs)} historical runs")

            # Display as a table
            import pandas as pd

            runs_data = []
            for run in runs:
                started = run.get('started_at')
                completed = run.get('completed_at')
                duration = run.get('duration_seconds')

                if started:
                    date_str = started.strftime("%Y-%m-%d %H:%M") if hasattr(started, 'strftime') else str(started)[:16]
                else:
                    date_str = "Unknown"

                if duration:
                    duration_str = f"{duration:.1f}s"
                elif completed and started:
                    try:
                        dur = (completed - started).total_seconds()
                        duration_str = f"{dur:.1f}s"
                    except:
                        duration_str = "N/A"
                else:
                    duration_str = "N/A"

                runs_data.append({
                    "Run ID": run.get('run_id', '')[:8] + "...",
                    "Drug": run.get('drug_name', 'Unknown'),
                    "Date": date_str,
                    "Status": run.get('status', 'unknown'),
                    "Papers Found": run.get('papers_found', 0) or 0,
                    "Extracted": run.get('papers_extracted', 0) or 0,
                    "Opportunities": run.get('opportunities_found', 0) or 0,
                    "Cost": f"${run.get('estimated_cost_usd', 0) or 0:.2f}",
                    "Duration": duration_str,
                    "Cache Hits": f"{run.get('papers_from_cache', 0) or 0}P/{run.get('market_intel_from_cache', 0) or 0}M",
                    "_full_run_id": run.get('run_id', '')
                })

            df = pd.DataFrame(runs_data)

            # Display table (without the hidden column)
            st.dataframe(
                df.drop(columns=['_full_run_id']),
                use_container_width=True,
                hide_index=True
            )

            # Allow loading a specific run
            st.markdown("---")
            st.subheader("🔍 Select Analysis to View")

            # Group runs by drug for easier selection
            drug_runs = {}
            for run in runs:
                drug_name = run.get('drug_name', 'Unknown')
                if drug_name not in drug_runs:
                    drug_runs[drug_name] = []
                drug_runs[drug_name].append(run)

            # Create dropdown options
            col1, col2 = st.columns([2, 1])

            with col1:
                # Drug selection dropdown
                drug_names = sorted(drug_runs.keys())
                selected_drug = st.selectbox(
                    "📊 Select Drug",
                    options=drug_names,
                    help="Choose a drug to view its analysis runs"
                )

            with col2:
                # Run selection dropdown for the selected drug
                if selected_drug and selected_drug in drug_runs:
                    drug_specific_runs = drug_runs[selected_drug]

                    # Format run labels with date, opportunities, and status
                    run_options = []
                    for run in drug_specific_runs:
                        started = run.get('started_at')
                        if started:
                            date_str = started.strftime("%Y-%m-%d %H:%M") if hasattr(started, 'strftime') else str(started)[:16]
                        else:
                            date_str = "Unknown date"

                        opps = run.get('opportunities_found', 0) or 0
                        status = run.get('status', 'unknown')
                        status_emoji = "✅" if status == 'completed' else "⚠️" if status == 'failed' else "🔄"

                        label = f"{status_emoji} {date_str} ({opps} opps)"
                        run_options.append((label, run))

                    selected_run_idx = st.selectbox(
                        "📅 Select Run",
                        options=range(len(run_options)),
                        format_func=lambda i: run_options[i][0],
                        help="Choose a specific analysis run to view"
                    )

                    selected_run = run_options[selected_run_idx][1]
                else:
                    selected_run = None

            # Action buttons
            st.markdown("---")
            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("📋 View Details (JSON)", use_container_width=True):
                    if selected_run:
                        run_id = selected_run.get('run_id')
                        if run_id:
                            details = agent.get_run_details(run_id)
                            if details:
                                st.json(details)
                            else:
                                st.error("Run not found")
                    else:
                        st.warning("Please select a run first")

            with col2:
                if st.button("📊 View Full Report", type="primary", use_container_width=True):
                    if selected_run:
                        run_id = selected_run.get('run_id')
                        if run_id:
                            st.session_state.v2_viewing_run_id = run_id
                            st.rerun()
                    else:
                        st.warning("Please select a run first")

            with col3:
                if st.button("📥 Quick Load to Session", use_container_width=True):
                    if selected_run:
                        run_id = selected_run.get('run_id')
                        if run_id:
                            with st.spinner("Loading run..."):
                                result = agent.load_historical_run(run_id)
                                if result:
                                    st.session_state.v2_drug_name = result.drug_name
                                    st.session_state.v2_drug_info = {
                                        'drug_name': result.drug_name,
                                        'generic_name': result.generic_name,
                                        'mechanism': result.mechanism,
                                        'target': result.target,
                                        'approved_indications': result.approved_indications or []
                                    }
                                    st.session_state.v2_opportunities = result.opportunities
                                    st.session_state.v2_extractions = [opp.extraction for opp in result.opportunities]
                                    st.success(f"✅ Loaded {len(result.opportunities)} opportunities! Navigate to other tabs to explore.")
                                else:
                                    st.error("Failed to load run")
                    else:
                        st.warning("Please select a run first")

            # Show full report if a run is selected
            if 'v2_viewing_run_id' in st.session_state and st.session_state.v2_viewing_run_id:
                st.markdown("---")

                with st.spinner("Loading run details..."):
                    result = agent.load_historical_run(st.session_state.v2_viewing_run_id)

                    if result and result.opportunities:
                        # Header with drug info
                        st.markdown(f"## 📊 Full Report: {result.drug_name}")

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.markdown(f"**Generic Name:** {result.generic_name or 'N/A'}")
                        with col2:
                            st.markdown(f"**Mechanism:** {result.mechanism or 'N/A'}")
                        with col3:
                            st.markdown(f"**Target:** {result.target or 'N/A'}")

                        # Summary metrics
                        st.markdown("### 📈 Summary Metrics")
                        col1, col2, col3, col4 = st.columns(4)

                        opps = result.opportunities
                        with col1:
                            st.metric("Total Opportunities", len(opps))
                        with col2:
                            high_priority = len([o for o in opps if o.scores.overall_priority >= 7])
                            st.metric("High Priority (≥7)", high_priority)
                        with col3:
                            avg_score = sum(o.scores.overall_priority for o in opps) / len(opps) if opps else 0
                            st.metric("Avg Score", f"{avg_score:.1f}")
                        with col4:
                            unique_indications = len(set(o.extraction.disease for o in opps if o.extraction))
                            st.metric("Unique Indications", unique_indications)

                        # Visualizations
                        st.markdown("### 📊 Visual Analysis")

                        # Create DataFrame for visualizations
                        viz_data = []
                        for opp in opps:
                            scores = opp.scores
                            ext = opp.extraction
                            market_intel = opp.market_intelligence

                            viz_data.append({
                                'Disease': ext.disease if ext else 'Unknown',
                                '# Studies': 1,
                                'Total Patients': ext.patient_population.n_patients if ext and ext.patient_population and ext.patient_population.n_patients else 0,
                                'Clinical Score (avg)': scores.clinical_signal,
                                'Evidence Score (avg)': scores.evidence_quality,
                                'Market Score (avg)': scores.market_opportunity,
                                'Overall Score (avg)': scores.overall_priority,
                                '# Approved Competitors': market_intel.standard_of_care.num_approved_drugs if market_intel and market_intel.standard_of_care else 0,
                                'Unmet Need': 'Yes' if market_intel and market_intel.standard_of_care and market_intel.standard_of_care.unmet_need else 'No',
                                'TAM Estimate': market_intel.tam_estimate if market_intel else 'N/A'
                            })

                        viz_df = pd.DataFrame(viz_data)

                        # Aggregate by disease
                        agg_df = viz_df.groupby('Disease').agg({
                            '# Studies': 'sum',
                            'Total Patients': 'sum',
                            'Clinical Score (avg)': 'mean',
                            'Evidence Score (avg)': 'mean',
                            'Market Score (avg)': 'mean',
                            'Overall Score (avg)': 'mean',
                            '# Approved Competitors': 'first',
                            'Unmet Need': 'first',
                            'TAM Estimate': 'first'
                        }).reset_index()

                        col1, col2 = st.columns(2)

                        with col1:
                            try:
                                render_priority_matrix(
                                    agg_df,
                                    drug_name=result.drug_name,
                                    height=500
                                )
                            except Exception as e:
                                st.error(f"Error rendering priority matrix: {e}")
                                logger.error(f"Priority matrix error: {e}", exc_info=True)

                        with col2:
                            try:
                                render_market_opportunity(
                                    agg_df,
                                    drug_name=result.drug_name,
                                    height=500
                                )
                            except Exception as e:
                                st.error(f"Error rendering market opportunity: {e}")
                                logger.error(f"Market opportunity error: {e}", exc_info=True)

                        st.markdown("---")

                        # Top opportunities table
                        st.markdown("### 🏆 Top Opportunities")

                        table_data = []
                        for opp in sorted(opps, key=lambda x: x.scores.overall_priority, reverse=True)[:10]:
                            ext = opp.extraction
                            indication = ext.disease if ext else "Unknown"

                            # Get response rate
                            response_rate = "N/A"
                            if ext and ext.detailed_efficacy_endpoints:
                                primary_endpoints = [e for e in ext.detailed_efficacy_endpoints if e.endpoint_category == 'primary']
                                if primary_endpoints and primary_endpoints[0].response_rate:
                                    response_rate = f"{primary_endpoints[0].response_rate:.1f}%"

                            table_data.append({
                                "Indication": indication[:50] + "..." if len(indication) > 50 else indication,
                                "Overall": f"{opp.scores.overall_priority:.1f}",
                                "Clinical": f"{opp.scores.clinical_signal:.1f}",
                                "Evidence": f"{opp.scores.evidence_quality:.1f}",
                                "Market": f"{opp.scores.market_opportunity:.1f}",
                                "Response Rate": response_rate,
                                "Sample Size": ext.patient_population.n_patients if ext and ext.patient_population and ext.patient_population.n_patients else 0
                            })

                        df_table = pd.DataFrame(table_data)
                        st.dataframe(df_table, use_container_width=True, hide_index=True)

                        st.markdown("---")

                        # Export options
                        st.markdown("### 💾 Export Options")

                        col1, col2, col3 = st.columns(3)

                        with col1:
                            # Excel export
                            try:
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                excel_filename = f"{result.drug_name.lower().replace(' ', '_')}_report_{timestamp}.xlsx"
                                excel_path = agent.export_to_excel(result, excel_filename)

                                # Read the file for download
                                with open(excel_path, 'rb') as f:
                                    excel_bytes = f.read()

                                st.download_button(
                                    "📥 Download Excel Report",
                                    excel_bytes,
                                    file_name=excel_filename,
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True
                                )
                            except Exception as e:
                                st.error(f"Error generating Excel: {e}")
                                logger.error(f"Excel export error: {e}", exc_info=True)

                        with col2:
                            # JSON export
                            try:
                                export_data = {
                                    "drug_name": result.drug_name,
                                    "generic_name": result.generic_name,
                                    "mechanism": result.mechanism,
                                    "target": result.target,
                                    "analysis_date": datetime.now().isoformat(),
                                    "opportunities": [
                                        {
                                            "indication": o.extraction.disease if o.extraction else "Unknown",
                                            "scores": o.scores.model_dump() if hasattr(o.scores, 'model_dump') else str(o.scores),
                                            "sample_size": o.extraction.patient_population.n_patients if o.extraction and o.extraction.patient_population and o.extraction.patient_population.n_patients else 0
                                        }
                                        for o in opps
                                    ]
                                }
                                json_str = json.dumps(export_data, indent=2)
                                st.download_button(
                                    "📥 Download JSON",
                                    json_str,
                                    file_name=f"{result.drug_name}_analysis.json",
                                    mime="application/json",
                                    use_container_width=True
                                )
                            except Exception as e:
                                st.error(f"Error generating JSON: {e}")

                        with col3:
                            # CSV export
                            try:
                                csv_data = df_table.to_csv(index=False)
                                st.download_button(
                                    "📥 Download CSV",
                                    csv_data,
                                    file_name=f"{result.drug_name}_opportunities.csv",
                                    mime="text/csv",
                                    use_container_width=True
                                )
                            except Exception as e:
                                st.error(f"Error generating CSV: {e}")

                        # Report Generation Section
                        st.markdown("---")
                        st.markdown("### 📄 Generate Analytical Report")
                        st.markdown("""
                        Generate a comprehensive analytical report using Claude. The report provides objective
                        analysis of findings, score derivations, concordance analysis, and competitive context.
                        """)

                        col1, col2, col3 = st.columns([2, 1, 1])

                        with col1:
                            # Generate report button
                            report_key = f"generate_report_{st.session_state.v2_viewing_run_id}"
                            if st.button("🤖 Generate Report with Claude", type="primary", use_container_width=True, key=report_key):
                                with st.spinner("Generating analytical report... This may take 1-2 minutes."):
                                    try:
                                        # Generate report from result object
                                        report_text, report_path = agent.generate_analytical_report(
                                            result=result,
                                            auto_save=True
                                        )

                                        # Store in session state with run-specific key
                                        st.session_state[f'report_{st.session_state.v2_viewing_run_id}'] = report_text
                                        st.session_state[f'report_path_{st.session_state.v2_viewing_run_id}'] = report_path

                                        st.success(f"✅ Report generated! Saved to: `{report_path}`")
                                        st.info("📖 Scroll down to view the report")

                                    except Exception as e:
                                        st.error(f"Error generating report: {e}")
                                        logger.error(f"Report generation error: {e}", exc_info=True)

                        with col2:
                            # Show cost estimate
                            st.caption("💰 Cost: ~$0.10-0.20")
                            st.caption("⏱️ Time: 1-2 min")

                        with col3:
                            # Download button if report exists
                            report_key_check = f'report_{st.session_state.v2_viewing_run_id}'
                            if report_key_check in st.session_state and st.session_state[report_key_check]:
                                st.download_button(
                                    "📥 Download Report",
                                    st.session_state[report_key_check],
                                    file_name=f"{result.drug_name}_analytical_report.md",
                                    mime="text/markdown",
                                    use_container_width=True,
                                    key=f"download_report_{st.session_state.v2_viewing_run_id}"
                                )

                        # Display generated report
                        report_key_display = f'report_{st.session_state.v2_viewing_run_id}'
                        if report_key_display in st.session_state and st.session_state[report_key_display]:
                            st.markdown("---")
                            st.markdown("### 📖 Generated Analytical Report")

                            # Show report in expandable section
                            with st.expander("📄 View Full Report", expanded=True):
                                st.markdown(st.session_state[report_key_display])

                            # Show report metadata
                            report_path_key = f'report_path_{st.session_state.v2_viewing_run_id}'
                            if report_path_key in st.session_state:
                                st.caption(f"💾 Saved to: `{st.session_state[report_path_key]}`")

                        # Load into session button
                        st.markdown("---")
                        if st.button("📥 Load into Current Session", use_container_width=True):
                            st.session_state.v2_drug_name = result.drug_name
                            st.session_state.v2_drug_info = {
                                'drug_name': result.drug_name,
                                'generic_name': result.generic_name,
                                'mechanism': result.mechanism,
                                'target': result.target,
                                'approved_indications': result.approved_indications or []
                            }
                            st.session_state.v2_opportunities = result.opportunities
                            st.session_state.v2_extractions = [opp.extraction for opp in result.opportunities]
                            st.success(f"✅ Loaded! {len(result.opportunities)} opportunities. Navigate to other tabs to explore.")

                        # Close button
                        if st.button("❌ Close Report", use_container_width=True):
                            del st.session_state.v2_viewing_run_id
                            st.rerun()

                    else:
                        st.error("Failed to load run or no opportunities found")
                        if st.button("❌ Close"):
                            del st.session_state.v2_viewing_run_id
                            st.rerun()

        else:
            st.info("📭 No historical runs found. Run an analysis to see it here!")
