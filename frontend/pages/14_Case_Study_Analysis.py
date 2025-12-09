"""
Off-Label Case Study Discovery

Discovers and analyzes clinical evidence of off-label drug use including:
case studies, case series, clinical trials, and real-world evidence.
"""

import streamlit as st
import os
import sys
import logging
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

# Add paths
frontend_dir = Path(__file__).parent.parent
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(project_root))

from auth import check_password
from src.agents.off_label_case_study_agent import OffLabelCaseStudyAgent
from src.tools.off_label_database import OffLabelDatabase
from src.utils.config import get_settings

st.set_page_config(
    page_title="Case Study Analysis",
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
    page_title="Case Study Analysis",
    page_icon="🔬",
    layout="wide"
)

st.title("🔬 Off-Label Case Study Analysis")
st.markdown("""
Discover and analyze clinical evidence of off-label drug use including case studies,
clinical trials, and real-world evidence. Identify development opportunities for non-approved indications.
""")

# Initialize session state
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None
if 'related_mechanisms' not in st.session_state:
    st.session_state.related_mechanisms = []
if 'selected_mechanisms' not in st.session_state:
    st.session_state.selected_mechanisms = []
if 'mechanism_analysis_results' not in st.session_state:
    st.session_state.mechanism_analysis_results = {}
if 'papers_found' not in st.session_state:
    st.session_state.papers_found = []
if 'drug_info' not in st.session_state:
    st.session_state.drug_info = None
if 'current_drug' not in st.session_state:
    st.session_state.current_drug = None
if 'discovered_papers' not in st.session_state:
    st.session_state.discovered_papers = []
if 'drug_name' not in st.session_state:
    st.session_state.drug_name = ''

# Check configuration
if not settings.anthropic_api_key:
    st.error("❌ Anthropic API key not configured. Please set ANTHROPIC_API_KEY in your .env file.")
    st.stop()

database_url = settings.drug_database_url or settings.paper_catalog_url
if not database_url:
    st.error("❌ Database not configured. Please set DRUG_DATABASE_URL in your .env file.")
    st.stop()

# Initialize agent
@st.cache_resource
def get_agent():
    """Initialize Off-Label Case Study Agent."""
    return OffLabelCaseStudyAgent(
        anthropic_api_key=settings.anthropic_api_key,
        database_url=database_url,
        pubmed_email='noreply@example.com',  # PubMed API default
        tavily_api_key=settings.tavily_api_key
    )

try:
    agent = get_agent()
    db = agent.db
except Exception as e:
    st.error(f"Failed to initialize agent: {e}")
    logger.error(f"Agent initialization error: {e}", exc_info=True)
    st.stop()

# Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🔍 Discover Papers",
    "📋 Analyze Papers",
    "📊 View Results",
    "🎯 Evidence Summary",
    "🔬 Advanced Analysis",
    "🧬 Mechanism Discovery"
])

# =====================================================
# TAB 1: DISCOVER PAPERS
# =====================================================

with tab1:
    st.header("1️⃣ Discover Off-Label Literature")
    st.markdown("Search PubMed and web sources for off-label case studies. Papers are cached for re-use.")

    # Show previously searched drugs
    from pathlib import Path
    off_label_papers_dir = Path("data/off_label_papers")

    if off_label_papers_dir.exists():
        previous_drugs = []
        for drug_dir in off_label_papers_dir.iterdir():
            if drug_dir.is_dir():
                papers_file = drug_dir / "discovered_papers.json"
                if papers_file.exists():
                    try:
                        import json
                        with open(papers_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            previous_drugs.append({
                                'drug_name': data.get('drug_name', drug_dir.name),
                                'search_date': data.get('search_date', 'Unknown'),
                                'total_papers': data.get('total_papers', 0),
                                'path': str(drug_dir)
                            })
                    except Exception as e:
                        pass

        if previous_drugs:
            st.info(f"📚 Found {len(previous_drugs)} previously searched drugs. Select one to load cached papers.")

            # Sort by search date (most recent first)
            previous_drugs.sort(key=lambda x: x['search_date'], reverse=True)

            # Create dropdown
            drug_options = [f"{d['drug_name']} ({d['total_papers']} papers, {d['search_date'][:10]})" for d in previous_drugs]
            selected_previous = st.selectbox(
                "Load Previous Search",
                options=["-- Select a drug --"] + drug_options,
                key="previous_drug_select"
            )

            if selected_previous != "-- Select a drug --":
                # Extract drug name from selection
                selected_drug_name = selected_previous.split(" (")[0]

                if st.button("📂 Load Cached Papers", type="primary", use_container_width=True, key="load_previous"):
                    with st.spinner(f"Loading cached papers for {selected_drug_name}..."):
                        try:
                            # Load papers
                            storage_path = agent._get_storage_path(selected_drug_name)
                            existing_papers = agent._load_existing_papers(storage_path)

                            # Load drug info
                            drug_info = agent.extract_mechanism(selected_drug_name)

                            # Store in session state
                            st.session_state.current_drug = selected_drug_name
                            st.session_state.drug_name = selected_drug_name
                            st.session_state.drug_info = drug_info
                            st.session_state.papers_found = existing_papers
                            st.session_state.discovered_papers = existing_papers

                            st.success(f"✅ Loaded {len(existing_papers)} cached papers for {selected_drug_name}! Go to 'Analyze Papers' tab.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error loading cached papers: {e}")

            st.markdown("---")

    st.subheader("Search for New Drug")

    col1, col2 = st.columns([3, 1])

    with col1:
        drug_name = st.text_input(
            "Drug Name",
            placeholder="e.g., Tofacitinib, Baricitinib, Rituximab",
            help="Enter the drug name to search for off-label case studies"
        )

    with col2:
        max_papers = st.number_input(
            "Max Papers",
            min_value=10,
            max_value=200,
            value=50,
            step=10,
            help="Maximum number of papers to search"
        )

    # Check if papers already exist for this drug
    if drug_name:
        storage_path = agent._get_storage_path(drug_name)
        existing_papers = agent._load_existing_papers(storage_path)

        if existing_papers:
            st.info(f"📚 Found {len(existing_papers)} cached papers for {drug_name}. Click 'Load Cached Papers' to use them, or 'Force Re-search' to search again.")

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("📚 Load Cached Papers", type="primary", use_container_width=True):
                    # Load drug info
                    drug_info = agent.extract_mechanism(drug_name)

                    # Store in session state
                    st.session_state.current_drug = drug_name
                    st.session_state.drug_info = drug_info
                    st.session_state.papers_found = existing_papers

                    st.success(f"✅ Loaded {len(existing_papers)} cached papers! Go to 'Analyze Papers' tab.")
                    st.rerun()

            with col_btn2:
                force_search = st.button("🔄 Force Re-search", use_container_width=True)
        else:
            force_search = False
    else:
        force_search = False

    # Search button
    search_button = st.button("🔍 Discover Papers", type="primary", use_container_width=True, disabled=bool(existing_papers) if drug_name else False)

    if search_button or force_search:
        if not drug_name:
            st.error("Please enter a drug name")
        else:
            with st.spinner(f"Discovering off-label literature for {drug_name}..."):
                try:
                    # Delete cached papers if force search
                    if force_search:
                        storage_path = agent._get_storage_path(drug_name)
                        papers_file = storage_path / "discovered_papers.json"
                        if papers_file.exists():
                            papers_file.unlink()
                            st.info("🗑️ Cleared cached papers")

                    # Step 1: Extract mechanism
                    st.info("Step 1: Extracting drug mechanism...")
                    drug_info = agent.extract_mechanism(drug_name)

                    # Step 2: Discover papers (will auto-download open access)
                    st.info("Step 2: Searching PubMed and web sources...")
                    st.info("Step 3: Auto-downloading open access papers...")
                    papers = agent.search_off_label_literature(drug_name, max_results=max_papers, save_to_disk=True)

                    # Store in session state
                    st.session_state.current_drug = drug_name
                    st.session_state.drug_name = drug_name
                    st.session_state.drug_info = drug_info
                    st.session_state.papers_found = papers
                    st.session_state.discovered_papers = papers

                    # Count open access papers
                    open_access_count = sum(1 for p in papers if p.get('is_open_access'))

                    st.success(f"✅ Found {len(papers)} papers ({open_access_count} with full text)! Go to 'Analyze Papers' tab.")

                except Exception as e:
                    st.error(f"Error during discovery: {e}")
                    logger.error(f"Discovery error: {e}", exc_info=True)

# =====================================================
# TAB 2: ANALYZE PAPERS
# =====================================================

with tab2:
    st.header("2️⃣ Analyze Selected Papers")

    if not st.session_state.papers_found:
        st.info("No papers yet. Discover papers in the 'Discover Papers' tab first.")
    else:
        papers = st.session_state.papers_found
        drug_name = st.session_state.current_drug

        if not papers:
            st.warning(f"No papers found for {drug_name}. Try adjusting your search.")
            st.stop()

        st.markdown(f"**Found {len(papers)} papers for {drug_name}**")

        # Group papers by indication (auto-classified during discovery)
        papers_by_disease = {}
        papers_without_indication = []

        for paper in papers:
            indication = paper.get('indication')
            if indication:
                if indication not in papers_by_disease:
                    papers_by_disease[indication] = []
                papers_by_disease[indication].append(paper)
            else:
                papers_without_indication.append(paper)

        # Show grouping options
        if papers_by_disease:
            view_mode = st.radio(
                "View Mode",
                options=["Group by Disease", "Show All"],
                horizontal=True,
                key="view_mode"
            )
        else:
            view_mode = "Show All"
            if papers_without_indication:
                st.info("💡 Papers are being classified during discovery. Newly discovered papers will be automatically grouped by disease.")
        
        # Add Select All / Unselect All buttons
        col_btn1, col_btn2, col_spacer = st.columns([1, 1, 4])
        with col_btn1:
            if st.button("✓ Select All", use_container_width=True, key="btn_select_all_papers"):
                for idx in range(len(papers)):
                    paper_key = f"paper_{idx}"
                    st.session_state[paper_key] = True
                st.rerun()
        with col_btn2:
            if st.button("✗ Unselect All", use_container_width=True, key="btn_unselect_all_papers"):
                for idx in range(len(papers)):
                    paper_key = f"paper_{idx}"
                    st.session_state[paper_key] = False
                st.rerun()

        # Display papers with checkboxes
        paper_selection = {}

        # Show papers grouped by disease or all together
        if view_mode == "Group by Disease" and papers_by_disease:
            # Display by disease
            for disease in sorted(papers_by_disease.keys()):
                st.markdown(f"## 🏥 {disease}")
                disease_papers = papers_by_disease[disease]
                st.caption(f"{len(disease_papers)} papers")

                # Header row
                header_col1, header_col2, header_col3, header_col4, header_col5 = st.columns([0.5, 3.5, 1, 1, 1])
                with header_col1:
                    st.markdown("**Select**")
                with header_col2:
                    st.markdown("**Paper Title**")
                with header_col3:
                    st.markdown("**Year**")
                with header_col4:
                    st.markdown("**Source**")
                with header_col5:
                    st.markdown("**Content**")

                st.markdown("---")

                for paper in disease_papers:
                    # Find original index
                    idx = papers.index(paper)

                    col1, col2, col3, col4, col5 = st.columns([0.5, 3.5, 1, 1, 1])

                    with col1:
                        paper_key = f"paper_{idx}"
                        default_value = idx < 20

                        paper_selection[idx] = st.checkbox(
                            "Select paper",
                            value=st.session_state.get(paper_key, default_value),
                            key=paper_key,
                            label_visibility="collapsed"
                        )

                    with col2:
                        title = paper.get('title', 'No title')
                        pmid = paper.get('pmid', '')
                        if pmid:
                            st.markdown(f"[{title}](https://pubmed.ncbi.nlm.nih.gov/{pmid})")
                        else:
                            st.markdown(title)

                    with col3:
                        year = paper.get('year', 'N/A')
                        st.write(year)

                    with col4:
                        source = paper.get('search_source', 'Unknown')
                        if source == 'PubMed':
                            st.success("PubMed")
                        elif source == 'Web Search':
                            st.info("Web")
                        else:
                            st.write(source)

                    with col5:
                        # Check if full text is available
                        has_full_text = False

                        if paper.get('full_text'):
                            has_full_text = True
                        elif paper.get('is_open_access'):
                            has_full_text = True
                        elif paper.get('pmid'):
                            existing = agent._find_existing_paper(paper['pmid'])
                            if existing:
                                has_full_text = True

                        if has_full_text:
                            st.success("📄 Full")
                        else:
                            st.warning("📝 Abstract")

                st.markdown("---")

            # Show unclassified papers
            if papers_without_indication:
                st.markdown(f"## ❓ Unclassified Papers")
                st.caption(f"{len(papers_without_indication)} papers - These may be older cached papers from before auto-classification was added")

                for paper in papers_without_indication[:5]:  # Show first 5 only
                    idx = papers.index(paper)
                    title = paper.get('title', 'No title')
                    st.markdown(f"- {title}")

        else:
            # Show all papers in one list
            # Header row
            header_col1, header_col2, header_col3, header_col4, header_col5 = st.columns([0.5, 3.5, 1, 1, 1])
            with header_col1:
                st.markdown("**Select**")
            with header_col2:
                st.markdown("**Paper Title**")
            with header_col3:
                st.markdown("**Year**")
            with header_col4:
                st.markdown("**Source**")
            with header_col5:
                st.markdown("**Content**")

            st.markdown("---")

            for idx, paper in enumerate(papers):
                col1, col2, col3, col4, col5 = st.columns([0.5, 3.5, 1, 1, 1])

                with col1:
                    paper_key = f"paper_{idx}"
                    # Default: select first 20 papers
                    default_value = idx < 20

                    paper_selection[idx] = st.checkbox(
                        "Select paper",
                        value=st.session_state.get(paper_key, default_value),
                        key=paper_key,
                        label_visibility="collapsed"
                    )

                with col2:
                    title = paper.get('title', 'No title')
                    pmid = paper.get('pmid', '')
                    if pmid:
                        st.markdown(f"[{title}](https://pubmed.ncbi.nlm.nih.gov/{pmid})")
                    else:
                        st.markdown(title)

                with col3:
                    year = paper.get('year', 'N/A')
                    st.write(year)

                with col4:
                    source = paper.get('search_source', 'Unknown')
                    if source == 'PubMed':
                        st.success("PubMed")
                    elif source == 'Web Search':
                        st.info("Web")
                    else:
                        st.write(source)

                with col5:
                    # Check if full text is available
                    # Priority: cached full_text > is_open_access flag > Clinical Data Collector > PMC
                    has_full_text = False

                    if paper.get('full_text'):
                        has_full_text = True
                    elif paper.get('is_open_access'):
                        has_full_text = True
                    elif paper.get('pmid'):
                        # Check Clinical Data Collector
                        existing = agent._find_existing_paper(paper['pmid'])
                        if existing:
                            has_full_text = True

                    if has_full_text:
                        st.success("📄 Full")
                    else:
                        st.warning("📝 Abstract")
        
        # Get selected papers
        selected_paper_indices = [idx for idx, selected in paper_selection.items() if selected]

        # Show summary of selected papers
        if selected_paper_indices:
            st.success(f"✓ Selected {len(selected_paper_indices)} papers for analysis")

            # Check which papers need PDFs
            selected_papers = [papers[idx] for idx in selected_paper_indices]
            papers_needing_pdf = []

            for paper in selected_papers:
                pmid = paper.get('pmid')
                pmc = paper.get('pmc')
                has_full_text = False

                # Check if full text is available (same logic as display)
                if paper.get('full_text'):
                    has_full_text = True
                elif paper.get('is_open_access'):
                    has_full_text = True
                elif pmid:
                    existing = agent._find_existing_paper(pmid)
                    if existing:
                        has_full_text = True

                if not has_full_text:
                    papers_needing_pdf.append(paper)

            # Show PDF upload section if needed
            if papers_needing_pdf:
                st.markdown("---")
                st.warning(f"⚠️ {len(papers_needing_pdf)} selected papers only have abstracts. Upload PDFs for better extraction quality.")

                with st.expander(f"📤 Upload PDFs ({len(papers_needing_pdf)} papers need full text)", expanded=True):
                    st.info("**Optional:** Upload PDFs to extract comprehensive data. Without PDFs, only abstract data will be extracted (limited detail).")

                    for paper in papers_needing_pdf:
                        st.markdown(f"**{paper.get('title', 'No title')}**")
                        pmid = paper.get('pmid', 'N/A')
                        st.caption(f"PMID: {pmid}")

                        # PDF upload
                        uploaded_file = st.file_uploader(
                            f"Upload PDF for PMID {pmid}",
                            type=['pdf'],
                            key=f"pdf_upload_{pmid}",
                            label_visibility="collapsed"
                        )

                        if uploaded_file:
                            # Save uploaded PDF temporarily
                            import tempfile
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                                tmp_file.write(uploaded_file.read())
                                paper['uploaded_pdf_path'] = tmp_file.name
                                st.success(f"✓ PDF uploaded: {uploaded_file.name}")

                        st.markdown("---")

            st.markdown("---")
        else:
            st.info("👆 Select papers above to analyze. Papers marked '📝 Abstract' will need PDF uploads for comprehensive extraction.")

        # Analyze button (only show if papers are selected)
        if selected_paper_indices:
            if st.button("🚀 Analyze Selected Papers", type="primary", use_container_width=True):
                # Get drug info from session state
                drug_info = st.session_state.get('drug_info', {})

                with st.spinner(f"Analyzing {len(selected_papers)} papers..."):
                    try:
                        # Classify and extract from selected papers
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        case_studies = []
                        errors = []

                        for i, paper in enumerate(selected_papers):
                            status_text.text(f"Processing paper {i+1}/{len(selected_papers)}...")
                            progress_bar.progress((i) / len(selected_papers))

                            try:
                                # Check if PDF was uploaded
                                if paper.get('uploaded_pdf_path'):
                                    # Extract from PDF
                                    case_study = agent.extract_from_pdf(
                                        pdf_path=paper['uploaded_pdf_path'],
                                        drug_name=drug_name,
                                        drug_info=drug_info,
                                        pmid=paper.get('pmid')
                                    )
                                else:
                                    # Extract from abstract/existing content
                                    # Classify paper
                                    classification = agent.classify_paper(paper, drug_name)

                                    if classification:  # classify_paper already filters by relevance_score >= 0.5
                                        # Extract data
                                        case_study = agent.extract_case_study_data(paper, drug_name, drug_info, classification)
                                    else:
                                        case_study = None

                                if case_study:
                                    # Save to database
                                    case_study_id = agent.db.save_case_study(case_study)
                                    case_studies.append({
                                        'case_study_id': case_study_id,
                                        'title': case_study.title,
                                        'indication': case_study.indication_treated,
                                        'n_patients': case_study.n_patients,
                                        'study_type': case_study.study_type,
                                        'efficacy_signal': case_study.efficacy_signal,
                                        'safety_profile': case_study.safety_profile,
                                        'development_potential': case_study.development_potential,
                                        'key_findings': case_study.key_findings,
                                        'pmid': case_study.pmid
                                    })
                            except Exception as e:
                                errors.append(f"Error processing {paper.get('title', 'Unknown')}: {str(e)}")

                        progress_bar.progress(1.0)
                        status_text.text("Analysis complete!")

                        # Store results
                        st.session_state.analysis_results = {
                            'case_studies': case_studies,
                            'errors': errors,
                            'papers_found': len(papers),
                            'papers_classified': len(selected_papers),
                            'case_studies_extracted': len(case_studies)
                        }

                        st.success(f"✅ Extracted {len(case_studies)} case studies! Go to 'View Results' tab.")

                    except Exception as e:
                        st.error(f"Error during analysis: {e}")
                        logger.error(f"Analysis error: {e}", exc_info=True)

# =====================================================
# TAB 3: VIEW RESULTS
# =====================================================

with tab3:
    st.header("3️⃣ Analysis Results")

    # Display results
    if st.session_state.analysis_results:
        results = st.session_state.analysis_results

        st.divider()
        st.subheader("📊 Analysis Summary")

        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Papers Found", results['papers_found'])
        with col2:
            st.metric("Papers Analyzed", results['papers_classified'])
        with col3:
            st.metric("Case Studies Extracted", results['case_studies_extracted'])

        # Case studies
        if results.get('case_studies'):
            st.divider()
            st.subheader("📄 Case Studies")

            for cs in results['case_studies']:
                with st.expander(f"📄 {cs['title'][:100]}..."):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(f"**Indication:** {cs['indication']}")
                        st.write(f"**N Patients:** {cs['n_patients']}")
                    with col2:
                        st.write(f"**Efficacy Signal:** {cs['efficacy_signal']}")
                        st.write(f"**Development Potential:** {cs['development_potential']}")
                    with col3:
                        if cs.get('pmid'):
                            st.markdown(f"[View on PubMed](https://pubmed.ncbi.nlm.nih.gov/{cs['pmid']})")
                        st.write(f"**Case Study ID:** {cs['case_study_id']}")

                    if cs.get('key_findings'):
                        st.markdown("**Key Findings:**")
                        st.write(cs['key_findings'])

        # Errors
        if results.get('errors'):
            st.divider()
            st.subheader("⚠️ Errors")
            for error in results['errors']:
                st.warning(error)
    else:
        st.info("No results yet. Search for papers and analyze them in the previous tabs.")

# =====================================================
# TAB 4: EVIDENCE SUMMARY (AGGREGATE ANALYSIS)
# =====================================================

with tab4:
    st.header("4️⃣ Evidence Summary")
    st.markdown("""
    Aggregate and rank all indications by evidence strength across all case studies for a drug.
    This provides a prioritized view of repurposing opportunities.
    """)

    # Drug selection
    drug_name_for_summary = st.text_input(
        "Drug Name",
        placeholder="e.g., Baricitinib, Tofacitinib",
        help="Enter drug name to aggregate evidence",
        key="evidence_summary_drug"
    )

    if st.button("📊 Generate Evidence Summary", type="primary", use_container_width=True):
        if not drug_name_for_summary:
            st.error("Please enter a drug name")
        else:
            with st.spinner(f"Aggregating evidence for {drug_name_for_summary}..."):
                try:
                    # Get aggregate evidence
                    indications = agent.aggregate_indication_evidence(drug_name_for_summary)

                    if not indications:
                        st.warning(f"No case studies found for {drug_name_for_summary}. Please analyze papers first in Tab 2.")
                    else:
                        st.success(f"Found {len(indications)} indications with evidence")

                        # Display summary metrics
                        st.markdown("### 📈 Summary Metrics")
                        col1, col2, col3, col4 = st.columns(4)

                        total_studies = sum(ind['n_studies'] for ind in indications)
                        total_patients = sum(ind['total_patients'] for ind in indications)
                        high_potential = sum(1 for ind in indications if ind['development_potential'] == 'High')

                        with col1:
                            st.metric("Total Indications", len(indications))
                        with col2:
                            st.metric("Total Studies", total_studies)
                        with col3:
                            st.metric("Total Patients", total_patients)
                        with col4:
                            st.metric("High Potential", high_potential)

                        st.divider()

                        # Display ranked indications
                        st.markdown("### 🎯 Ranked Indications by Evidence Strength")

                        for i, ind in enumerate(indications, 1):
                            # Color code by evidence score
                            score = ind['evidence_score']
                            if score >= 70:
                                score_color = "🟢"
                            elif score >= 50:
                                score_color = "🟡"
                            else:
                                score_color = "🔴"

                            with st.expander(
                                f"{score_color} **#{i}. {ind['indication']}** - Evidence Score: {score:.1f}/100",
                                expanded=(i <= 3)  # Expand top 3
                            ):
                                # Overview metrics
                                col1, col2, col3, col4 = st.columns(4)

                                with col1:
                                    st.metric("Studies", ind['n_studies'])
                                with col2:
                                    st.metric("Total Patients", ind['total_patients'])
                                with col3:
                                    st.metric("Avg Response Rate", f"{ind['avg_response_rate']:.1f}%")
                                with col4:
                                    st.metric("Development Potential", ind['development_potential'])

                                # Score breakdown
                                st.markdown("#### 📊 Evidence Score Breakdown")
                                breakdown = ind['score_breakdown']

                                score_data = {
                                    "Replication (max 30)": breakdown['replication_score'],
                                    "Sample Size (max 25)": breakdown['sample_size_score'],
                                    "Efficacy (max 30)": breakdown['efficacy_score'],
                                    "Quality (max 10)": breakdown['quality_score'],
                                    "Potential (max 5)": breakdown['potential_score']
                                }

                                for label, value in score_data.items():
                                    st.progress(value / float(label.split('max ')[1].rstrip(')')), text=f"{label}: {value:.1f}")

                                # Safety profile
                                safety = ind['safety_profile']
                                safety_emoji = "✅" if safety == "Acceptable" else "⚠️" if safety == "Concerning" else "❓"
                                st.markdown(f"**Safety Profile:** {safety_emoji} {safety}")

                                # Individual studies
                                st.markdown("#### 📄 Individual Studies")
                                for study in ind['studies']:
                                    st.markdown(f"""
                                    - **{study['title']}** ({study['year']})
                                      - PMID: [{study['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{study['pmid']})
                                      - N={study['n_patients']}, Response: {study['response_rate']}
                                      - Efficacy: {study['efficacy_signal']}
                                    """)

                        # Export option
                        st.divider()
                        st.markdown("### 💾 Export Evidence Summary")

                        import json
                        summary_json = json.dumps(indications, indent=2, default=str)
                        st.download_button(
                            label="📥 Download as JSON",
                            data=summary_json,
                            file_name=f"{drug_name_for_summary}_evidence_summary.json",
                            mime="application/json"
                        )

                except Exception as e:
                    st.error(f"Error generating evidence summary: {e}")
                    logger.error(f"Evidence summary error: {e}", exc_info=True)

# =====================================================
# TAB 5: ADVANCED ANALYSIS
# =====================================================

with tab5:
    st.header("5️⃣ Advanced Analysis")
    st.markdown("""
    Advanced features for expanding your search and comparing to approved therapies.
    """)

    # Sub-tabs for different advanced features
    subtab1, subtab2 = st.tabs([
        "🔗 Citation Network Analysis",
        "⚖️ Comparative Analysis"
    ])

    # =====================================================
    # CITATION NETWORK ANALYSIS
    # =====================================================

    with subtab1:
        st.subheader("Citation Network Analysis")
        st.markdown("""
        Expand your search by following citation networks from seed papers.
        This finds related papers that may not appear in keyword searches.
        """)

        # Select seed papers
        if st.session_state.discovered_papers:
            papers = st.session_state.discovered_papers
            drug_name = st.session_state.get('drug_name', '')

            st.markdown("### Select Seed Papers")
            st.caption("Choose papers to use as starting points for citation network expansion")

            seed_selection = {}
            for idx, paper in enumerate(papers[:10]):  # Show first 10
                title = paper.get('title', 'No title')
                pmid = paper.get('pmid', '')

                if pmid:
                    seed_selection[idx] = st.checkbox(
                        f"{title} (PMID: {pmid})",
                        key=f"seed_{idx}"
                    )

            selected_seeds = [papers[idx] for idx, selected in seed_selection.items() if selected]

            if selected_seeds:
                st.success(f"✓ Selected {len(selected_seeds)} seed papers")

                max_related = st.slider(
                    "Max related papers per seed",
                    min_value=5,
                    max_value=50,
                    value=10,
                    help="Number of related papers to fetch for each seed paper"
                )

                if st.button("🔗 Expand via Citations", type="primary", use_container_width=True):
                    with st.spinner(f"Following citation networks from {len(selected_seeds)} seed papers..."):
                        try:
                            # Expand search via citations
                            new_papers = agent.expand_search_via_citations(
                                drug_name=drug_name,
                                seed_papers=selected_seeds,
                                max_related_per_paper=max_related
                            )

                            if new_papers:
                                st.success(f"✅ Found {len(new_papers)} new papers via citation network!")

                                # Display new papers
                                st.markdown("### 📄 Newly Discovered Papers")

                                for paper in new_papers[:20]:  # Show first 20
                                    title = paper.get('title', 'No title')
                                    pmid = paper.get('pmid', '')
                                    year = paper.get('year', 'N/A')
                                    relationships = paper.get('relationship_to_seed', [])

                                    rel_text = ", ".join(relationships) if relationships else "similar"

                                    st.markdown(f"""
                                    - **{title}** ({year})
                                      - PMID: [{pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid})
                                      - Relationship: {rel_text}
                                    """)

                                # Option to add to discovered papers
                                if st.button("➕ Add to Discovered Papers", key="add_citation_papers"):
                                    st.session_state.discovered_papers.extend(new_papers)
                                    st.success(f"Added {len(new_papers)} papers to discovered papers!")
                                    st.rerun()
                            else:
                                st.warning("No new papers found via citation network")

                        except Exception as e:
                            st.error(f"Error expanding via citations: {e}")
                            logger.error(f"Citation expansion error: {e}", exc_info=True)
            else:
                st.info("👆 Select seed papers above to expand via citation network")
        else:
            st.info("👈 Discover papers first in Tab 1 to use citation network analysis")

    # =====================================================
    # COMPARATIVE ANALYSIS
    # =====================================================

    with subtab2:
        st.subheader("Comparative Analysis")
        st.markdown("""
        Compare your off-label candidate to approved drugs for the same indication.
        This helps assess competitive landscape and unmet need.
        """)

        # Input fields
        col1, col2 = st.columns(2)

        with col1:
            comp_drug_name = st.text_input(
                "Off-Label Drug",
                value=st.session_state.get('drug_name', ''),
                help="Drug being evaluated for off-label use"
            )

        with col2:
            comp_indication = st.text_input(
                "Target Indication",
                placeholder="e.g., Systemic Lupus Erythematosus",
                help="Indication to compare against"
            )

        if st.button("⚖️ Compare to Approved Drugs", type="primary", use_container_width=True):
            if not comp_drug_name or not comp_indication:
                st.error("Please enter both drug name and indication")
            else:
                with st.spinner(f"Comparing {comp_drug_name} to approved drugs for {comp_indication}..."):
                    try:
                        comparison = agent.compare_to_approved_drugs(comp_drug_name, comp_indication)

                        if comparison.get('error'):
                            st.error(f"Error: {comparison['error']}")
                        else:
                            # Display off-label data
                            st.markdown("### 📊 Off-Label Drug Data")

                            off_label_data = comparison.get('off_label_data')
                            if off_label_data:
                                col1, col2, col3, col4 = st.columns(4)

                                with col1:
                                    st.metric("Studies", off_label_data['n_studies'])
                                with col2:
                                    st.metric("Total Patients", off_label_data['total_patients'])
                                with col3:
                                    st.metric("Avg Response Rate", f"{off_label_data['avg_response_rate']:.1f}%")
                                with col4:
                                    st.metric("Development Potential", off_label_data['development_potential'])
                            else:
                                st.warning("No off-label case study data found. Analyze papers first in Tab 2.")

                            # Display approved drugs
                            st.markdown("### 💊 Approved Drugs for This Indication")

                            approved_drugs = comparison.get('approved_drugs', [])
                            if approved_drugs:
                                st.info(f"Found {len(approved_drugs)} approved drugs")

                                for drug in approved_drugs:
                                    with st.expander(f"**{drug['drug_name']}** ({drug['mechanism']})"):
                                        st.markdown(f"**Status:** {drug['approval_status']}")

                                        clinical_data = drug.get('clinical_data', {})
                                        n_trials = clinical_data.get('n_trials', 0)

                                        if n_trials > 0:
                                            st.markdown(f"**Clinical Trials:** {n_trials}")

                                            # Show trial summaries
                                            for trial in clinical_data.get('trials', [])[:3]:  # Show first 3
                                                paper = trial['paper']
                                                st.markdown(f"""
                                                - **{paper['title']}** ({paper['year']})
                                                  - Phase: {paper['trial_phase']}
                                                  - N={paper['n_patients']}
                                                  - Primary endpoint: {paper['primary_endpoint']}
                                                  - Met: {'✅' if paper['primary_endpoint_met'] else '❌'}
                                                """)
                                        else:
                                            st.caption("No clinical trial data available")
                            else:
                                st.success("✨ No approved drugs found - High unmet need!")

                            # Display comparative summary
                            st.markdown("### 📝 Comparative Summary")

                            summary = comparison.get('comparative_summary')
                            if summary:
                                st.info(summary)

                            # Display unmet need assessment
                            st.markdown("### 🎯 Unmet Need Assessment")

                            unmet_need = comparison.get('unmet_need_assessment', 'Unknown')

                            if 'High' in unmet_need:
                                st.success(f"**{unmet_need}**")
                            elif 'Moderate' in unmet_need:
                                st.warning(f"**{unmet_need}**")
                            else:
                                st.error(f"**{unmet_need}**")

                    except Exception as e:
                        st.error(f"Error in comparative analysis: {e}")
                        logger.error(f"Comparative analysis error: {e}", exc_info=True)

# =====================================================
# TAB 6: MECHANISM-BASED DISCOVERY
# =====================================================

with tab6:
    st.header("6️⃣ Mechanism-Based Discovery")
    st.markdown("Search for off-label case studies across all drugs with a specific mechanism.")

    col1, col2 = st.columns([2, 1])

    with col1:
        mechanism_input = st.text_input(
            "Mechanism of Action",
            placeholder="e.g., JAK inhibition, TNF-alpha inhibition",
            help="Enter the mechanism to search for drugs and their off-label uses"
        )

    with col2:
        max_drugs = st.number_input(
            "Max Drugs",
            min_value=5,
            max_value=50,
            value=10,
            step=5,
            help="Maximum number of drugs to analyze"
        )

    if st.button("🔬 Search by Mechanism", type="primary", use_container_width=True):
        if not mechanism_input:
            st.error("Please enter a mechanism")
        else:
            st.info("🚧 Mechanism-based discovery coming soon!")
            st.markdown("""
            This feature will:
            1. Find all drugs with the specified mechanism
            2. Search for off-label case studies for each drug
            3. Aggregate findings across all drugs
            4. Identify common off-label indications
            """)


