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

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent
from src.utils.config import get_settings

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
        tavily_api_key=getattr(settings, 'tavily_api_key', None),
        pubmed_email='noreply@example.com'
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

# Main content - Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "💊 Approved Indications",
    "🔍 Case Series Search",
    "📋 Data Extraction",
    "📊 Scoring & Results",
    "📈 Full Analysis"
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
                        abstract = paper.get('abstract', 'No abstract available')
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
                    abstract = paper.get('abstract', 'No abstract available')
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

        # Select papers to extract
        col1, col2 = st.columns(2)
        with col1:
            max_extract = st.slider("Max papers to extract", 1, min(20, len(case_series)), min(5, len(case_series)))
        with col2:
            st.metric("Estimated Cost", f"~${max_extract * 0.05:.2f}")

        if st.button("📋 Extract Structured Data", type="primary", use_container_width=True):
            with st.spinner(f"Extracting data from {max_extract} papers..."):
                try:
                    extractions = []
                    progress_bar = st.progress(0)
                    drug_info = st.session_state.v2_drug_info or {}

                    for i, paper in enumerate(case_series[:max_extract]):
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
                        progress_bar.progress((i + 1) / max_extract)

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

        # Configuration
        col1, col2, col3 = st.columns(3)
        with col1:
            max_papers = st.number_input("Max papers", 5, 50, 15, key="full_max_papers")
        with col2:
            max_extract = st.number_input("Max extractions", 3, 20, 10, key="full_max_extract")
        with col3:
            include_market = st.checkbox("Include market intel", value=True, key="full_market")

        estimated_cost = max_extract * 0.08  # Rough estimate
        st.caption(f"💰 Estimated cost: ~${estimated_cost:.2f}")

        if st.button("🚀 Run Full Analysis", type="primary", use_container_width=True):
            progress_container = st.container()

            with progress_container:
                progress_bar = st.progress(0)
                status_text = st.empty()

                try:
                    # Step 1: Drug info
                    status_text.text("Step 1/5: Fetching drug information...")
                    progress_bar.progress(10)
                    drug_info = agent._get_drug_info(drug_name)
                    st.session_state.v2_drug_info = drug_info

                    # Step 2: Search
                    status_text.text("Step 2/5: Searching for case series...")
                    progress_bar.progress(25)
                    exclude_indications = drug_info.get('approved_indications', [])
                    case_series = agent._search_case_series(
                        drug_name=drug_name,
                        exclude_indications=exclude_indications,
                        max_papers=max_papers,
                        include_web_search=True
                    )
                    st.session_state.v2_case_series = case_series

                    # Step 3: Extract
                    status_text.text("Step 3/5: Extracting structured data...")
                    progress_bar.progress(40)
                    extractions = []
                    for i, paper in enumerate(case_series[:max_extract]):
                        extraction = agent._extract_case_series_data(
                            drug_name=drug_name,
                            drug_info=drug_info,
                            paper=paper
                        )
                        if extraction:
                            extractions.append({'paper': paper, 'extraction': extraction})
                        progress_bar.progress(40 + int(30 * (i + 1) / max_extract))
                    st.session_state.v2_extractions = extractions

                    # Step 4: Score
                    status_text.text("Step 4/5: Scoring opportunities...")
                    progress_bar.progress(75)
                    from src.models.case_series_schemas import RepurposingOpportunity

                    opportunities = []
                    for item in extractions:
                        ext = item['extraction']
                        opp = RepurposingOpportunity(extraction=ext)
                        scores = agent._score_opportunity(opp)
                        opp.scores = scores
                        opportunities.append(opp)

                    opportunities.sort(key=lambda x: x.scores.overall_priority, reverse=True)
                    st.session_state.v2_opportunities = opportunities

                    # Step 5: Complete
                    status_text.text("Step 5/5: Analysis complete!")
                    progress_bar.progress(100)

                    st.success(f"✅ Analysis complete! Found {len(opportunities)} repurposing opportunities.")

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

            import pandas as pd
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
                    use_container_width=True
                )

            with col2:
                # CSV export
                csv_data = df.to_csv(index=False)
                st.download_button(
                    "📥 Download CSV",
                    csv_data,
                    file_name=f"{drug_name}_case_series_analysis.csv",
                    mime="text/csv",
                    use_container_width=True
                )
