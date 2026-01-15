"""
Case Study Analysis v3 - Using Refactored Architecture

Uses the new orchestrator-based architecture with:
- Isolated, testable services
- Dependency injection
- Clear separation of concerns
"""

import streamlit as st
import asyncio
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path
import sys

# Add paths
frontend_dir = Path(__file__).parent.parent
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(project_root))

from auth import check_password, check_page_access, show_access_denied, render_sidebar_nav
from src.case_series import CaseSeriesOrchestrator, create_orchestrator
from src.case_series.services.mechanism_discovery_service import MechanismDiscoveryService
from src.utils.config import get_settings

st.set_page_config(
    page_title="Case Study Analysis v3",
    page_icon="🧬",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

# Page access check
if not check_page_access("Case_Study_Analysis_v3"):
    show_access_denied()

# Render custom sidebar navigation for restricted users
render_sidebar_nav()

# Configure logging with file output to logs.md
LOG_FILE = project_root / "logs.md"

class MarkdownFileHandler(logging.Handler):
    """Custom handler that writes logs to a markdown file in real-time."""
    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath
        # Write header on first run of session
        self._write_header()

    def _write_header(self):
        """Write a session header to the log file."""
        with open(self.filepath, 'a', encoding='utf-8') as f:
            f.write(f"\n\n---\n## Analysis Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.flush()

    def emit(self, record):
        try:
            msg = self.format(record)
            with open(self.filepath, 'a', encoding='utf-8') as f:
                # Format as markdown with code block for each log line
                f.write(f"- `{msg}`\n")
                f.flush()  # Flush immediately for real-time updates
        except Exception:
            self.handleError(record)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add file handler for logs.md
file_handler = MarkdownFileHandler(LOG_FILE)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Add handler to root logger so all modules log to file
root_logger = logging.getLogger()
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)
logger.info("Case Study Analysis v3 started")

# Get settings
settings = get_settings()

st.title("🧬 Case Study Analysis v3")
st.markdown("""
**Drug Repurposing Analysis** using the new modular architecture.
Each component is independently testable and maintainable.
""")

# Add cache clear button in sidebar
with st.sidebar:
    if st.button("🔄 Clear Cache & Reload", help="Click if settings aren't taking effect"):
        st.cache_resource.clear()
        st.rerun()

# Check configuration
if not settings.anthropic_api_key:
    st.error("Anthropic API key not configured. Please set ANTHROPIC_API_KEY in your .env file.")
    st.stop()


# Initialize orchestrator
@st.cache_resource
def get_orchestrator() -> CaseSeriesOrchestrator:
    """Create orchestrator with all dependencies."""
    database_url = getattr(settings, 'drug_database_url', None) or getattr(settings, 'disease_landscape_url', None)
    return create_orchestrator(
        anthropic_api_key=settings.anthropic_api_key,
        tavily_api_key=getattr(settings, 'tavily_api_key', None),
        database_url=database_url,
        semantic_scholar_api_key=getattr(settings, 'semantic_scholar_api_key', None),
    )


# Initialize mechanism discovery service
@st.cache_resource
def get_mechanism_discovery_service() -> MechanismDiscoveryService:
    """Create mechanism discovery service."""
    database_url = getattr(settings, 'drug_database_url', None) or getattr(settings, 'disease_landscape_url', None)
    return MechanismDiscoveryService(
        database_url=database_url,
    )


# Helper to run async functions
def run_async(coro):
    """Run async coroutine in sync context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


try:
    orchestrator = get_orchestrator()
    mechanism_service = get_mechanism_discovery_service()
except Exception as e:
    st.error(f"Failed to initialize services: {e}")
    logger.error(f"Service initialization error: {e}", exc_info=True)
    st.stop()


# =============================================================================
# Hierarchical Display Helper Functions
# =============================================================================

def render_score_breakdown(score, show_weights: bool = True):
    """Render 6-dimension score breakdown in columns."""
    dimensions = [
        ("Efficacy", score.efficacy_score, "35%"),
        ("Sample Size", score.sample_size_score, "15%"),
        ("Endpoint Quality", score.endpoint_quality_score, "10%"),
        ("Biomarker", score.biomarker_score, "15%"),
        ("Response Def", score.response_definition_score, "15%"),
        ("Follow-up", score.followup_score, "10%"),
    ]

    cols = st.columns(6)
    for col, (name, val, weight) in zip(cols, dimensions):
        with col:
            help_text = f"{weight} weight" if show_weights else None
            st.metric(name, f"{val:.1f}", help=help_text)


def render_paper_card(opp, drug_name: str = None, show_explanation: bool = True):
    """Render an expandable paper card with score breakdown and AI explanation."""
    ext = opp.extraction
    score = ext.individual_score
    pmid = ext.source.pmid if ext.source else 'N/A'
    title = ext.source.title if ext.source else 'Unknown Title'
    if len(title) > 80:
        title = title[:80] + "..."

    n_patients = ext.patient_population.n_patients if ext.patient_population else 'N/A'
    resp_pct = ext.efficacy.responders_pct if ext.efficacy else None
    resp_str = f"{resp_pct:.0f}%" if resp_pct is not None else 'N/A'

    # Header with key metrics
    total_score = score.total_score if score else (opp.scores.overall_priority if opp.scores else 0)
    header = f"PMID {pmid}: {title} (N={n_patients}, {resp_str} response, Score: {total_score:.1f})"

    with st.expander(header):
        # Metadata row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.write(f"**Patients:** {n_patients}")
        with col2:
            st.write(f"**Response:** {resp_str}")
        with col3:
            st.write(f"**Year:** {ext.source.year if ext.source else 'N/A'}")
        with col4:
            if drug_name:
                st.write(f"**Drug:** {drug_name}")

        # 6-dimension score breakdown
        if score:
            st.markdown("**Score Breakdown (6 dimensions):**")
            render_score_breakdown(score)

            # Scoring notes/justification
            if score.scoring_notes:
                st.caption(f"**Rationale:** {score.scoring_notes}")

        # AI explanation
        if show_explanation and hasattr(ext, 'score_explanation') and ext.score_explanation:
            st.info(f"**AI Analysis:** {ext.score_explanation}")

        # Additional details
        if ext.efficacy and ext.efficacy.primary_endpoint:
            st.caption(f"**Primary Endpoint:** {ext.efficacy.primary_endpoint}")


def render_papers_for_manual_review(papers_for_review: list, title: str = "Papers Requiring Manual Review"):
    """
    Render an expandable section showing papers that need manual review.

    These are papers that passed filters but were extracted from abstract only
    (no full text available), ranked by patient count (N).

    Args:
        papers_for_review: List of PaperForManualReview objects
        title: Title for the section
    """
    if not papers_for_review:
        return

    st.markdown("---")
    with st.expander(f"📋 {title} ({len(papers_for_review)} papers)", expanded=False):
        st.markdown("""
        **These papers passed all relevant filters but were extracted from abstract only.**
        Full text was not available, so important indication details may be missing.
        Review these papers manually for potentially missed opportunities.

        Papers are ranked by patient count (N) - highest first.
        """)

        # Summary metrics
        papers_with_n = [p for p in papers_for_review if p.n_patients is not None]
        total_patients = sum(p.n_patients for p in papers_with_n)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Papers for Review", len(papers_for_review))
        with col2:
            st.metric("Papers with N", len(papers_with_n))
        with col3:
            st.metric("Total Patients", total_patients if total_patients > 0 else "Unknown")

        st.markdown("---")

        # Display each paper
        for i, paper in enumerate(papers_for_review, 1):
            # Build confidence badge for N
            n_badge = ""
            if paper.n_patients is not None:
                confidence_color = {
                    "High": "🟢",
                    "Medium": "🟡",
                    "Low": "🟠",
                    "Unknown": "⚪"
                }.get(paper.n_confidence, "⚪")
                n_badge = f"N={paper.n_patients} {confidence_color}"
            else:
                n_badge = "N=Unknown ⚪"

            # Build header
            pmid_str = paper.pmid or paper.doi or "N/A"
            year_str = f"({paper.year})" if paper.year else ""
            disease_str = f"| {paper.disease}" if paper.disease else ""

            with st.expander(f"**{i}. {n_badge}** | PMID: {pmid_str} {year_str} {disease_str}"):
                # Title and metadata
                st.markdown(f"**{paper.title}**")

                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Journal:** {paper.journal or 'N/A'}")
                    st.write(f"**Year:** {paper.year or 'N/A'}")
                    if paper.authors:
                        authors_display = paper.authors[:100] + "..." if len(paper.authors or "") > 100 else paper.authors
                        st.write(f"**Authors:** {authors_display}")

                with col2:
                    st.write(f"**PMID:** {paper.pmid or 'N/A'}")
                    st.write(f"**DOI:** {paper.doi or 'N/A'}")
                    st.write(f"**Disease:** {paper.disease or 'Not extracted'}")

                st.markdown("---")

                # Key efficacy information
                st.markdown("**Key Information (from abstract):**")
                eff_col1, eff_col2, eff_col3 = st.columns(3)
                with eff_col1:
                    n_display = f"{paper.n_patients} ({paper.n_confidence} confidence)" if paper.n_patients else "Not found"
                    st.write(f"**N (patients):** {n_display}")
                with eff_col2:
                    st.write(f"**Response Rate:** {paper.response_rate or 'Not found'}")
                with eff_col3:
                    st.write(f"**Primary Endpoint:** {paper.primary_endpoint or 'Not found'}")

                # Efficacy mention/summary
                if paper.efficacy_mention:
                    st.info(f"**Efficacy Summary:** {paper.efficacy_mention}")

                # Reason for manual review
                st.caption(f"⚠️ **Reason for review:** {paper.reason}")

                # PubMed link
                if paper.pmid:
                    st.markdown(f"[View on PubMed](https://pubmed.ncbi.nlm.nih.gov/{paper.pmid}/)")


def render_hierarchical_disease_card(
    agg,
    explanation: str = None,
    parent_disease: str = None,
    is_child: bool = False,
    drug_name: str = None,
):
    """
    Render a disease card with hierarchical indentation.

    Args:
        agg: AggregatedEvidence for this disease
        explanation: AI-generated explanation (optional)
        parent_disease: Parent disease name (for subtypes)
        is_child: Whether this is a child disease (indent)
        drug_name: Drug being analyzed
    """
    # Build header
    indent = "→ " if is_child else ""
    range_str = ""
    if agg.response_range and agg.response_range[0] != agg.response_range[1]:
        range_str = f" (range: {agg.response_range[0]:.0f}%-{agg.response_range[1]:.0f}%)"
    pooled_str = f"{agg.pooled_response_pct:.0f}%{range_str}" if agg.pooled_response_pct else "N/A"

    rank_str = f"#{agg.rank}. " if hasattr(agg, 'rank') and agg.rank else ""
    header = f"{indent}{rank_str}**{agg.disease}** - Score: {agg.avg_overall_score:.1f}/10 ({agg.n_studies} studies, {agg.total_patients} patients)"

    with st.expander(header, expanded=not is_child):
        # Aggregate metrics
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Studies", agg.n_studies)
        with col2:
            st.metric("Patients", agg.total_patients)
        with col3:
            st.metric("Pooled Response", pooled_str)
        with col4:
            st.metric("Consistency", agg.consistency)
        with col5:
            st.metric("Evidence", agg.evidence_confidence)

        # Score breakdown
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Avg Clinical", f"{agg.avg_clinical_score:.1f}")
        with col2:
            st.metric("Avg Evidence", f"{agg.avg_evidence_score:.1f}")
        with col3:
            st.metric("Avg Market", f"{agg.avg_market_score:.1f}")
        with col4:
            st.metric("Best Score", f"{agg.best_overall_score:.1f}")

        # AI Explanation
        if explanation:
            st.markdown("**AI Score Explanation:**")
            st.markdown(explanation)

        # Individual papers
        st.markdown("---")
        st.markdown(f"**Individual Papers ({len(agg.opportunities)}):**")
        for opp in agg.opportunities:
            render_paper_card(opp, drug_name=drug_name, show_explanation=True)


# Session state - Mechanism search
if 'v3_target_query' not in st.session_state:
    st.session_state.v3_target_query = ''
if 'v3_discovered_drugs' not in st.session_state:
    st.session_state.v3_discovered_drugs = []
if 'v3_selected_drugs' not in st.session_state:
    st.session_state.v3_selected_drugs = []
if 'v3_mechanism_result' not in st.session_state:
    st.session_state.v3_mechanism_result = None
if 'v3_mechanism_progress' not in st.session_state:
    st.session_state.v3_mechanism_progress = {}
if 'v3_checkbox_key' not in st.session_state:
    st.session_state.v3_checkbox_key = 0  # Used to reset checkbox states
if 'v3_paper_discovery' not in st.session_state:
    st.session_state.v3_paper_discovery = {}  # Dict of drug_name -> PaperDiscoveryResult
if 'v3_selected_papers' not in st.session_state:
    st.session_state.v3_selected_papers = {}  # Dict of drug_name -> set of PMIDs selected by user
if 'v3_paper_checkbox_key' not in st.session_state:
    st.session_state.v3_paper_checkbox_key = {}  # Dict of drug_name -> int for resetting checkbox state

# Session state - Single drug analysis
if 'v3_drug_name' not in st.session_state:
    st.session_state.v3_drug_name = ''
if 'v3_drug_info' not in st.session_state:
    st.session_state.v3_drug_info = None
if 'v3_search_result' not in st.session_state:
    st.session_state.v3_search_result = None
if 'v3_extractions' not in st.session_state:
    st.session_state.v3_extractions = []
if 'v3_opportunities' not in st.session_state:
    st.session_state.v3_opportunities = []
if 'v3_result' not in st.session_state:
    st.session_state.v3_result = None

# Session state - Preprint search
if 'v3_preprint_search_result' not in st.session_state:
    st.session_state.v3_preprint_search_result = None
if 'v3_preprint_extractions' not in st.session_state:
    st.session_state.v3_preprint_extractions = []
if 'v3_preprint_opportunities' not in st.session_state:
    st.session_state.v3_preprint_opportunities = []


# Sidebar
with st.sidebar:
    st.header("Drug Selection")

    drug_name = st.text_input(
        "Drug Name",
        value=st.session_state.v3_drug_name,
        placeholder="e.g., Upadacitinib, Rituximab",
        help="Enter a drug brand name or generic name"
    )

    if drug_name != st.session_state.v3_drug_name:
        st.session_state.v3_drug_name = drug_name
        # Reset state on drug change
        st.session_state.v3_drug_info = None
        st.session_state.v3_search_result = None
        st.session_state.v3_extractions = []
        st.session_state.v3_opportunities = []
        st.session_state.v3_result = None
        # Reset preprint state
        st.session_state.v3_preprint_search_result = None
        st.session_state.v3_preprint_extractions = []
        st.session_state.v3_preprint_opportunities = []

    st.markdown("---")
    st.subheader("Workflow Status")

    status_items = [
        ("Drug Info", st.session_state.v3_drug_info is not None),
        ("Search", st.session_state.v3_search_result is not None),
        ("Extraction", len(st.session_state.v3_extractions) > 0),
        ("Scoring", len(st.session_state.v3_opportunities) > 0),
    ]

    for name, done in status_items:
        if done:
            st.success(f"✅ {name}")
        else:
            st.info(f"⬜ {name}")

    st.markdown("---")
    if st.button("Reset All", use_container_width=True):
        for key in ['v3_drug_name', 'v3_drug_info', 'v3_search_result',
                    'v3_extractions', 'v3_opportunities', 'v3_result']:
            st.session_state[key] = None if 'name' not in key else ''
        st.session_state.v3_extractions = []
        st.session_state.v3_opportunities = []
        st.rerun()


# Main content - Tabs
tab0, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🎯 Mechanism Search",
    "1. Drug Info",
    "2. Literature Search",
    "3. Data Extraction",
    "4. Scoring & Results",
    "5. Full Analysis",
    "📊 History"
])


# Tab 0: Mechanism Search (NEW)
with tab0:
    st.header("Mechanism-Based Drug Discovery")
    st.markdown("""
    Search for drugs by **molecular target** (e.g., JAK1, IL-6, TNF-alpha).

    This workflow will:
    1. Find all approved drugs with the specified target in our database
    2. Search external sources (OpenFDA, ClinicalTrials.gov) for additional drugs
    3. Add any missing drugs to the database
    4. Let you select which drugs to analyze
    5. Run case study analysis in parallel for all selected drugs
    6. Aggregate and rank opportunities across the entire mechanism
    """)

    st.markdown("---")

    # Target input
    col1, col2 = st.columns([3, 1])
    with col1:
        target_query = st.text_input(
            "Molecular Target",
            value=st.session_state.v3_target_query,
            placeholder="e.g., JAK1, IL-6, TNF-alpha, C5",
            help="Enter a molecular target to find all drugs acting on it"
        )
    with col2:
        search_external = st.checkbox("Search external sources", value=True)

    if target_query != st.session_state.v3_target_query:
        st.session_state.v3_target_query = target_query
        st.session_state.v3_discovered_drugs = []
        st.session_state.v3_selected_drugs = []
        st.session_state.v3_mechanism_result = None

    # Step 1: Discover drugs
    st.subheader("Step 1: Discover Drugs")

    if st.button("🔍 Search for Drugs", type="primary", disabled=not target_query):
        with st.spinner(f"Searching for drugs targeting {target_query}..."):
            try:
                result = run_async(
                    mechanism_service.discover_drugs_by_target(
                        target=target_query,
                        search_external=search_external,
                        add_missing_to_database=True,
                        approval_status_filter="approved",  # Only approved for case studies
                    )
                )
                st.session_state.v3_discovered_drugs = result.all_drugs
                st.session_state.v3_selected_drugs = [d.generic_name for d in result.all_drugs]

                st.success(f"Found {len(result.all_drugs)} drugs targeting {target_query}")
                if result.drugs_added_to_database:
                    st.info(f"Added {len(result.drugs_added_to_database)} new drugs to database")

            except Exception as e:
                st.error(f"Search failed: {e}")
                logger.error(f"Mechanism search error: {e}", exc_info=True)

    # Display discovered drugs
    if st.session_state.v3_discovered_drugs:
        st.markdown("---")
        st.subheader(f"Step 2: Select Drugs ({len(st.session_state.v3_discovered_drugs)} found)")

        # Drug selection
        st.markdown("**Select drugs to include in case study analysis:**")

        # Select all / deselect all
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("Select All"):
                st.session_state.v3_selected_drugs = [d.generic_name for d in st.session_state.v3_discovered_drugs]
                st.session_state.v3_checkbox_key += 1  # Force checkbox refresh
                st.rerun()
        with col2:
            if st.button("Deselect All"):
                st.session_state.v3_selected_drugs = []
                st.session_state.v3_checkbox_key += 1  # Force checkbox refresh
                st.rerun()

        # Drug list with checkboxes and info
        # Use checkbox_key in the key to force reset when Select All/Deselect All is clicked
        checkbox_key_prefix = st.session_state.v3_checkbox_key
        for drug in st.session_state.v3_discovered_drugs:
            col1, col2 = st.columns([1, 4])
            with col1:
                is_selected = st.checkbox(
                    drug.generic_name,
                    value=drug.generic_name in st.session_state.v3_selected_drugs,
                    key=f"drug_select_{checkbox_key_prefix}_{drug.generic_name}"
                )
                if is_selected and drug.generic_name not in st.session_state.v3_selected_drugs:
                    st.session_state.v3_selected_drugs.append(drug.generic_name)
                elif not is_selected and drug.generic_name in st.session_state.v3_selected_drugs:
                    st.session_state.v3_selected_drugs.remove(drug.generic_name)

            with col2:
                with st.expander(f"📋 {drug.brand_name or drug.generic_name} - {drug.manufacturer or 'Unknown'}"):
                    info_col1, info_col2 = st.columns(2)
                    with info_col1:
                        st.write(f"**Generic:** {drug.generic_name}")
                        st.write(f"**Brand:** {drug.brand_name or 'N/A'}")
                        st.write(f"**Manufacturer:** {drug.manufacturer or 'N/A'}")
                        st.write(f"**Drug Type:** {drug.drug_type or 'N/A'}")
                    with info_col2:
                        st.write(f"**Target:** {drug.target or 'N/A'}")
                        st.write(f"**MoA Category:** {drug.moa_category or 'N/A'}")
                        st.write(f"**Status:** {drug.approval_status or 'N/A'}")
                        st.write(f"**Source:** {drug.source}")

                    if drug.approved_indications:
                        st.write(f"**Approved Indications:** {', '.join(drug.approved_indications[:5])}")
                        if len(drug.approved_indications) > 5:
                            st.write(f"  ... and {len(drug.approved_indications) - 5} more")

        # Paper Discovery Section
        st.markdown("---")
        st.subheader("📚 Paper Discovery & Selection")
        st.markdown("""
        **Explore and select papers for analysis.** Shows ALL papers organized by disease with filter evaluation.
        - ✅ = Would pass automatic filter | ❌ = Would be filtered out
        - Use checkboxes to manually include/exclude papers
        - Papers are saved to database and can be reloaded
        """)

        selected_drugs_for_discovery = st.session_state.v3_selected_drugs
        if selected_drugs_for_discovery:
            col1, col2 = st.columns([3, 1])
            with col1:
                discovery_drug = st.selectbox(
                    "Select drug to discover papers",
                    options=selected_drugs_for_discovery,
                    key="discovery_drug_select"
                )
            with col2:
                max_papers_discovery = st.number_input(
                    "Max papers/source",
                    min_value=20,
                    max_value=200,
                    value=50,
                    key="max_papers_discovery"
                )

            # Check for existing discovery in database
            existing_discovery = None
            try:
                existing_discovery = orchestrator.load_paper_discovery(discovery_drug, max_age_days=7)
                if existing_discovery and discovery_drug not in st.session_state.v3_paper_discovery:
                    st.info(f"📂 Found previous discovery for **{discovery_drug}** with {existing_discovery.total_papers} papers ({existing_discovery.papers_passing_filter} pass filter)")
            except Exception as e:
                logger.error(f"Error checking for existing discovery: {e}")
                st.warning(f"Could not check for existing discovery: {e}")

            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                # Include drug name in key to prevent stale state when switching drugs
                discover_new = st.button("🔍 Discover & Evaluate Papers", key=f"discover_papers_btn_{discovery_drug}")
            with btn_col2:
                load_existing = st.button(
                    "📂 Load Previous Discovery",
                    key=f"load_discovery_btn_{discovery_drug}",
                    disabled=existing_discovery is None
                )

            if load_existing:
                if existing_discovery is None:
                    st.error("No previous discovery found to load. Please run 'Discover & Evaluate Papers' first.")
                else:
                    try:
                        # Load from database - already have the data
                        st.session_state.v3_paper_discovery[discovery_drug] = existing_discovery

                        # Initialize selections with papers that pass filter
                        if discovery_drug not in st.session_state.v3_selected_papers:
                            st.session_state.v3_selected_papers[discovery_drug] = set()

                        # Initialize checkbox key for this drug
                        if discovery_drug not in st.session_state.v3_paper_checkbox_key:
                            st.session_state.v3_paper_checkbox_key[discovery_drug] = 0

                        # Auto-select papers that pass filter
                        for disease, papers in existing_discovery.papers_by_disease.items():
                            for p in papers:
                                paper_id = p.paper.pmid or p.paper.doi or p.paper.title[:50]
                                if p.would_pass_filter:
                                    st.session_state.v3_selected_papers[discovery_drug].add(paper_id)

                        st.success(f"Loaded {existing_discovery.total_papers} papers from database, {existing_discovery.papers_passing_filter} pass filter")
                        st.rerun()
                    except Exception as e:
                        logger.error(f"Error loading discovery: {e}", exc_info=True)
                        st.error(f"Failed to load discovery: {e}")

            if discover_new:
                with st.spinner(f"Discovering and evaluating papers for {discovery_drug}..."):
                    try:
                        discovery_result = run_async(
                            orchestrator.discover_papers(
                                drug_name=discovery_drug,
                                max_per_source=max_papers_discovery,
                                evaluate_filter=True,
                            )
                        )
                        st.session_state.v3_paper_discovery[discovery_drug] = discovery_result

                        # Initialize selections with papers that pass filter
                        if discovery_drug not in st.session_state.v3_selected_papers:
                            st.session_state.v3_selected_papers[discovery_drug] = set()

                        # Auto-select papers that pass filter
                        for disease, papers in discovery_result.papers_by_disease.items():
                            for p in papers:
                                paper_id = p.paper.pmid or p.paper.doi or p.paper.title[:50]
                                if p.would_pass_filter:
                                    st.session_state.v3_selected_papers[discovery_drug].add(paper_id)

                        st.success(f"Found {discovery_result.total_papers} papers, {discovery_result.papers_passing_filter} would pass filter (saved to database)")
                    except Exception as e:
                        st.error(f"Discovery failed: {e}")
                        logger.error(f"Paper discovery error: {e}", exc_info=True)

            # Display discovery results
            if selected_drugs_for_discovery:
                for drug_name in selected_drugs_for_discovery:
                    if drug_name in st.session_state.v3_paper_discovery:
                        discovery = st.session_state.v3_paper_discovery[drug_name]

                        # Ensure selection set exists
                        if drug_name not in st.session_state.v3_selected_papers:
                            st.session_state.v3_selected_papers[drug_name] = set()

                        selected_count = len(st.session_state.v3_selected_papers[drug_name])

                        with st.expander(
                            f"📄 {drug_name}: {discovery.total_papers} papers | "
                            f"✅ {discovery.papers_passing_filter} pass filter | "
                            f"🔘 {selected_count} selected",
                            expanded=(drug_name == discovery_drug if 'discovery_drug' in dir() else False)
                        ):
                            # Summary metrics
                            metric_cols = st.columns(5)
                            with metric_cols[0]:
                                st.metric("Total Papers", discovery.total_papers)
                            with metric_cols[1]:
                                st.metric("Duplicates Removed", discovery.duplicates_removed)
                            with metric_cols[2]:
                                st.metric("Would Pass Filter", discovery.papers_passing_filter)
                            with metric_cols[3]:
                                st.metric("User Selected", selected_count)
                            with metric_cols[4]:
                                st.metric("Diseases Found", len(discovery.papers_by_disease))

                            if discovery.approved_indications:
                                st.info(f"**Approved indications (excluded):** {', '.join(discovery.approved_indications[:5])}")

                            # Quick selection buttons
                            btn_cols = st.columns(4)
                            with btn_cols[0]:
                                if st.button("Select All Passing", key=f"select_passing_{drug_name}"):
                                    for disease, papers in discovery.papers_by_disease.items():
                                        for p in papers:
                                            if p.would_pass_filter:
                                                paper_id = p.paper.pmid or p.paper.doi or p.paper.title[:50]
                                                st.session_state.v3_selected_papers[drug_name].add(paper_id)
                                    # Increment checkbox key to sync UI
                                    if drug_name not in st.session_state.v3_paper_checkbox_key:
                                        st.session_state.v3_paper_checkbox_key[drug_name] = 0
                                    st.session_state.v3_paper_checkbox_key[drug_name] += 1
                                    st.rerun()
                            with btn_cols[1]:
                                if st.button("Select All", key=f"select_all_{drug_name}"):
                                    for disease, papers in discovery.papers_by_disease.items():
                                        for p in papers:
                                            paper_id = p.paper.pmid or p.paper.doi or p.paper.title[:50]
                                            st.session_state.v3_selected_papers[drug_name].add(paper_id)
                                    for p in discovery.unclassified_papers:
                                        paper_id = p.paper.pmid or p.paper.doi or p.paper.title[:50]
                                        st.session_state.v3_selected_papers[drug_name].add(paper_id)
                                    # Increment checkbox key to sync UI
                                    if drug_name not in st.session_state.v3_paper_checkbox_key:
                                        st.session_state.v3_paper_checkbox_key[drug_name] = 0
                                    st.session_state.v3_paper_checkbox_key[drug_name] += 1
                                    st.rerun()
                            with btn_cols[2]:
                                if st.button("Clear Selection", key=f"clear_sel_{drug_name}"):
                                    st.session_state.v3_selected_papers[drug_name] = set()
                                    # Increment checkbox key to force checkbox reset
                                    if drug_name not in st.session_state.v3_paper_checkbox_key:
                                        st.session_state.v3_paper_checkbox_key[drug_name] = 0
                                    st.session_state.v3_paper_checkbox_key[drug_name] += 1
                                    st.rerun()

                            # Papers by disease
                            st.markdown("#### Papers by Disease")
                            st.caption("Click the checkbox next to a disease name to select/deselect all papers for that disease.")

                            # Sort diseases by paper count (descending)
                            sorted_diseases = sorted(
                                discovery.papers_by_disease.items(),
                                key=lambda x: len(x[1]),
                                reverse=True
                            )

                            # Get checkbox key for this drug (for resetting checkboxes)
                            paper_cb_key = st.session_state.v3_paper_checkbox_key.get(drug_name, 0)

                            for disease, papers in sorted_diseases:
                                is_approved = any(
                                    disease.lower() in ind.lower() or ind.lower() in disease.lower()
                                    for ind in discovery.approved_indications
                                )
                                approved_badge = " 🏷️" if is_approved else ""
                                passing_count = sum(1 for p in papers if p.would_pass_filter)

                                # Get paper IDs for this disease
                                disease_paper_ids = [
                                    p.paper.pmid or p.paper.doi or p.paper.title[:50]
                                    for p in papers
                                ]

                                # Count how many are selected
                                selected_in_disease = sum(
                                    1 for pid in disease_paper_ids
                                    if pid in st.session_state.v3_selected_papers[drug_name]
                                )
                                all_selected = selected_in_disease == len(papers)

                                # Disease row with checkbox and expander
                                disease_col1, disease_col2 = st.columns([0.05, 0.95])

                                with disease_col1:
                                    # Store previous checkbox state in session to detect actual clicks
                                    checkbox_key = f"disease_{drug_name}_{disease}_{paper_cb_key}"
                                    prev_state_key = f"prev_{checkbox_key}"

                                    disease_checked = st.checkbox(
                                        "",
                                        value=all_selected,
                                        key=checkbox_key,
                                        label_visibility="collapsed",
                                        help=f"Select/deselect all {len(papers)} papers for {disease}"
                                    )

                                    # Get previous checkbox state (default to current if not stored)
                                    prev_checked = st.session_state.get(prev_state_key, disease_checked)

                                    # Only act if checkbox state actually changed (user clicked)
                                    if disease_checked != prev_checked:
                                        st.session_state[prev_state_key] = disease_checked
                                        if disease_checked:
                                            # Select all papers in this disease
                                            for pid in disease_paper_ids:
                                                st.session_state.v3_selected_papers[drug_name].add(pid)
                                        else:
                                            # Deselect all papers in this disease
                                            for pid in disease_paper_ids:
                                                st.session_state.v3_selected_papers[drug_name].discard(pid)
                                        st.rerun()

                                with disease_col2:
                                    with st.expander(f"**{disease}**{approved_badge} ({len(papers)} papers, {passing_count} ✅, {selected_in_disease} selected)"):
                                        for i, paper_status in enumerate(papers, 1):
                                            paper = paper_status.paper
                                            paper_id = paper.pmid or paper.doi or paper.title[:50]
                                            title = paper.title or "No title"
                                            pmid_display = paper.pmid or paper.doi or "N/A"
                                            year = paper.year or "N/A"
                                            source = paper.source or "Unknown"

                                            # Filter status indicator
                                            if paper_status.would_pass_filter:
                                                filter_icon = "✅"
                                            else:
                                                filter_icon = "❌"

                                            # Checkbox for selection - use paper_cb_key to reset on Clear
                                            is_selected = paper_id in st.session_state.v3_selected_papers[drug_name]
                                            col_check, col_content = st.columns([0.05, 0.95])

                                            with col_check:
                                                checkbox_key = f"paper_{drug_name}_{disease}_{i}_{paper_cb_key}"
                                                checked = st.checkbox(
                                                    "",
                                                    value=is_selected,
                                                    key=checkbox_key,
                                                    label_visibility="collapsed"
                                                )
                                                # Only update if state actually changed (prevents clearing on re-render)
                                                if checked and not is_selected:
                                                    st.session_state.v3_selected_papers[drug_name].add(paper_id)
                                                elif not checked and is_selected:
                                                    st.session_state.v3_selected_papers[drug_name].discard(paper_id)

                                            with col_content:
                                                n_patients = f"n={paper_status.patient_count}" if paper_status.patient_count else ""
                                                st.markdown(f"""
                                                {filter_icon} **{title}** {n_patients}
                                                - PMID: `{pmid_display}` | Year: {year} | Source: {source}
                                                """)

                                                if paper_status.filter_reason:
                                                    st.caption(f"💬 {paper_status.filter_reason[:200]}")

                                            st.markdown("---")

                            # Unclassified papers
                            if discovery.unclassified_papers:
                                # Get paper IDs for unclassified
                                unclass_paper_ids = [
                                    p.paper.pmid or p.paper.doi or p.paper.title[:50]
                                    for p in discovery.unclassified_papers
                                ]
                                selected_unclass = sum(
                                    1 for pid in unclass_paper_ids
                                    if pid in st.session_state.v3_selected_papers[drug_name]
                                )

                                unclass_col1, unclass_col2 = st.columns([0.05, 0.95])
                                with unclass_col1:
                                    all_unclass_selected = selected_unclass == len(discovery.unclassified_papers)
                                    unclass_checkbox_key = f"disease_{drug_name}_unclassified_{paper_cb_key}"
                                    unclass_prev_state_key = f"prev_{unclass_checkbox_key}"

                                    unclass_checked = st.checkbox(
                                        "",
                                        value=all_unclass_selected,
                                        key=unclass_checkbox_key,
                                        label_visibility="collapsed",
                                        help=f"Select/deselect all {len(discovery.unclassified_papers)} unclassified papers"
                                    )

                                    # Get previous checkbox state (default to current if not stored)
                                    unclass_prev_checked = st.session_state.get(unclass_prev_state_key, unclass_checked)

                                    # Only act if checkbox state actually changed (user clicked)
                                    if unclass_checked != unclass_prev_checked:
                                        st.session_state[unclass_prev_state_key] = unclass_checked
                                        if unclass_checked:
                                            for pid in unclass_paper_ids:
                                                st.session_state.v3_selected_papers[drug_name].add(pid)
                                        else:
                                            for pid in unclass_paper_ids:
                                                st.session_state.v3_selected_papers[drug_name].discard(pid)
                                        st.rerun()

                                with unclass_col2:
                                    with st.expander(f"**Unclassified** ({len(discovery.unclassified_papers)} papers, {selected_unclass} selected)"):
                                        for i, paper_status in enumerate(discovery.unclassified_papers[:30], 1):
                                            paper = paper_status.paper
                                            paper_id = paper.pmid or paper.doi or paper.title[:50]
                                            title = paper.title or "No title"
                                            pmid_display = paper.pmid or paper.doi or "N/A"

                                            filter_icon = "✅" if paper_status.would_pass_filter else "❌"

                                            col_check, col_content = st.columns([0.05, 0.95])
                                            with col_check:
                                                is_selected = paper_id in st.session_state.v3_selected_papers[drug_name]
                                                checked = st.checkbox(
                                                    "",
                                                    value=is_selected,
                                                    key=f"paper_{drug_name}_unclass_{i}_{paper_cb_key}",
                                                    label_visibility="collapsed"
                                                )
                                                # Only update if state actually changed (prevents clearing on re-render)
                                                if checked and not is_selected:
                                                    st.session_state.v3_selected_papers[drug_name].add(paper_id)
                                                elif not checked and is_selected:
                                                    st.session_state.v3_selected_papers[drug_name].discard(paper_id)

                                            with col_content:
                                                st.markdown(f"{filter_icon} **{i}.** {title} (PMID: `{pmid_display}`)")
                                                if paper_status.filter_reason:
                                                    st.caption(f"💬 {paper_status.filter_reason[:150]}")

                                        if len(discovery.unclassified_papers) > 30:
                                            st.caption(f"... and {len(discovery.unclassified_papers) - 30} more")
        else:
            st.info("Select drugs above to discover papers.")

        # Step 3: Run analysis
        st.markdown("---")
        st.subheader("Step 3: Run Analysis")

        selected_count = len(st.session_state.v3_selected_drugs)
        st.write(f"**{selected_count} drugs selected** for case study analysis")

        # Check if we have user-selected papers
        drugs_with_selections = []
        total_selected_papers = 0

        # Debug: Show what's in session state
        with st.expander("🔍 Debug: Session State", expanded=False):
            st.write("**v3_selected_drugs:**", list(st.session_state.v3_selected_drugs))
            st.write("**v3_selected_papers keys:**", list(st.session_state.v3_selected_papers.keys()))
            for drug, papers in st.session_state.v3_selected_papers.items():
                st.write(f"  - {drug}: {len(papers)} papers selected")
            st.write("**v3_paper_discovery keys:**", list(st.session_state.v3_paper_discovery.keys()))

        # Build a case-insensitive lookup for selected papers
        selected_papers_lower = {k.lower(): k for k in st.session_state.v3_selected_papers.keys()}

        for drug_name in st.session_state.v3_selected_drugs:
            # Try exact match first, then case-insensitive
            matched_key = None
            if drug_name in st.session_state.v3_selected_papers:
                matched_key = drug_name
            elif drug_name.lower() in selected_papers_lower:
                matched_key = selected_papers_lower[drug_name.lower()]
                logger.warning(f"Case mismatch: '{drug_name}' in v3_selected_drugs, '{matched_key}' in v3_selected_papers")

            if matched_key:
                paper_count = len(st.session_state.v3_selected_papers[matched_key])
                if paper_count > 0:
                    drugs_with_selections.append((drug_name, matched_key))  # Store both for later use
                    total_selected_papers += paper_count

        use_user_selections = len(drugs_with_selections) > 0

        if use_user_selections:
            st.info(f"📋 **Using user-selected papers:** {total_selected_papers} papers across {len(drugs_with_selections)} drugs")
            st.caption("Papers were selected from Paper Discovery. Only these papers will be analyzed.")
        else:
            st.caption("No papers selected. Will run full search and automatic filtering.")

        if st.button(
            f"🚀 Run Analysis for {selected_count} Drugs",
            type="primary",
            disabled=selected_count == 0,
            use_container_width=True
        ):
            progress_bar = st.progress(0)
            status_text = st.empty()
            drug_status_container = st.container()

            st.session_state.v3_mechanism_progress = {drug: "pending" for drug in st.session_state.v3_selected_drugs}

            def progress_callback(drug_name, status, result_or_error):
                st.session_state.v3_mechanism_progress[drug_name] = status

            try:
                from src.case_series.orchestrator import AnalysisConfig

                # Use sensible defaults - no need for user configuration
                config = AnalysisConfig(
                    max_papers_per_source=100,  # High enough to get all relevant papers
                    filter_with_llm=not use_user_selections,  # Skip filter if user selected papers
                    enrich_market_data=True,
                    max_concurrent_extractions=3,
                )
                max_concurrent = 3  # Default concurrent drug analyses

                if use_user_selections:
                    # Build dict of drug_name -> List[Paper] from user selections
                    drug_papers = {}
                    for drug_name, matched_key in drugs_with_selections:
                        # Use matched_key to look up discovery and selected papers (handles case mismatch)
                        discovery_key = matched_key if matched_key in st.session_state.v3_paper_discovery else drug_name
                        if discovery_key in st.session_state.v3_paper_discovery:
                            discovery = st.session_state.v3_paper_discovery[discovery_key]
                            selected_ids = st.session_state.v3_selected_papers[matched_key]

                            # Collect selected papers from discovery result
                            papers = []
                            # Check papers by disease
                            for disease, paper_list in discovery.papers_by_disease.items():
                                for p in paper_list:
                                    paper_id = p.paper.pmid or p.paper.doi or p.paper.title[:50]
                                    if paper_id in selected_ids:
                                        papers.append(p.paper)
                            # Check unclassified papers
                            for p in discovery.unclassified_papers:
                                paper_id = p.paper.pmid or p.paper.doi or p.paper.title[:50]
                                if paper_id in selected_ids:
                                    papers.append(p.paper)

                            if papers:
                                drug_papers[drug_name] = papers
                                logger.info(f"Found {len(papers)} selected papers for {drug_name} (key: {matched_key})")

                    status_text.write(f"Running analysis with {total_selected_papers} user-selected papers...")

                    result = run_async(
                        orchestrator.analyze_mechanism_with_selections(
                            target=st.session_state.v3_target_query,
                            drug_papers=drug_papers,
                            config=config,
                            max_concurrent_drugs=max_concurrent,
                            progress_callback=progress_callback,
                        )
                    )
                else:
                    # Fall back to normal mechanism analysis
                    status_text.write(f"Running analysis for {selected_count} drugs in parallel...")

                    result = run_async(
                        orchestrator.analyze_mechanism(
                            target=st.session_state.v3_target_query,
                            drug_names=st.session_state.v3_selected_drugs,
                            config=config,
                            max_concurrent_drugs=max_concurrent,
                            progress_callback=progress_callback,
                        )
                    )

                progress_bar.progress(100)
                st.session_state.v3_mechanism_result = result

                st.success(f"Analysis complete! Found {result.total_opportunities} opportunities across {result.successful_drugs} drugs.")

                if result.drugs_failed:
                    st.warning(f"{result.failed_drug_count} drugs failed analysis")
                    with st.expander("View failed drugs"):
                        for drug, error in result.drugs_failed.items():
                            st.write(f"**{drug}:** {error}")

            except Exception as e:
                st.error(f"Analysis failed: {e}")
                logger.error(f"Mechanism analysis error: {e}", exc_info=True)

        # Display mechanism analysis results
        if st.session_state.v3_mechanism_result:
            result = st.session_state.v3_mechanism_result

            st.markdown("---")
            st.subheader("Results: Mechanism-Wide Analysis")

            # Summary metrics
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Drugs Analyzed", result.successful_drugs)
            with col2:
                st.metric("Papers Screened", result.papers_screened)
            with col3:
                st.metric("Papers Extracted", result.papers_extracted)
            with col4:
                st.metric("Opportunities", result.total_opportunities)
            with col5:
                st.metric("Est. Cost", f"${result.estimated_cost_usd:.2f}")

            # Aggregated Disease Summary with Hierarchical Display
            st.markdown("---")
            st.subheader("🏆 Disease-Level Summary (with Score Explanations)")

            from src.case_series.services.aggregation_service import aggregate_opportunities_by_disease

            aggregated = aggregate_opportunities_by_disease(result.opportunities)

            st.write(f"**{len(aggregated)} unique diseases** across {result.total_opportunities} papers from {len(result.drug_results)} drugs")
            st.caption("Click on a disease to see individual papers with 6-dimension score breakdown and AI explanations.")

            for agg in aggregated:
                # Get drugs for this disease (for multi-drug display)
                drugs_in_disease = set()
                for opp in agg.opportunities:
                    if opp.extraction.treatment and opp.extraction.treatment.drug_name:
                        drugs_in_disease.add(opp.extraction.treatment.drug_name)
                drugs_str = ", ".join(sorted(drugs_in_disease)) if drugs_in_disease else "Unknown"

                # Use the new hierarchical card helper (pass drugs info via header modification)
                render_hierarchical_disease_card(
                    agg=agg,
                    explanation=None,  # Mechanism analysis doesn't have per-disease explanations yet
                    drug_name=drugs_str,  # Show all drugs for this disease
                )

            st.success(f"Showing all {len(aggregated)} disease groups ({result.total_opportunities} total papers)")

            # Individual papers view (collapsible)
            st.markdown("---")
            with st.expander("View All Individual Papers"):
                st.subheader("All Opportunities (Individual Papers)")
                for opp in result.opportunities:
                    ext = opp.extraction
                    scores = opp.scores
                    drug_name = ext.treatment.drug_name if ext.treatment else "Unknown"
                    n_patients = ext.patient_population.n_patients if ext.patient_population else 'N/A'
                    resp_pct = ext.efficacy.responders_pct if ext.efficacy else None
                    resp_str = f"{resp_pct}%" if resp_pct is not None else 'N/A'

                    with st.expander(
                        f"#{opp.rank}: {ext.disease} ({drug_name}) - Score: {scores.overall_priority:.1f}/10"
                    ):
                        st.metric("Overall Score", f"{scores.overall_priority:.1f}/10")

                        st.markdown("---")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Drug:** {drug_name}")
                            st.write(f"**Disease:** {ext.disease}")
                            st.write(f"**Patients:** {n_patients}")
                            st.write(f"**Response Rate:** {resp_str}")
                        with col2:
                            st.write(f"**PMID:** {ext.source.pmid if ext.source else 'N/A'}")
                            st.write(f"**Year:** {ext.source.year if ext.source else 'N/A'}")
                            st.write(f"**Journal:** {ext.source.journal if ext.source else 'N/A'}")

            # Results by drug
            st.markdown("---")
            st.subheader("📊 Results by Drug")

            for drug_name, drug_result in result.drug_results.items():
                with st.expander(f"{drug_name}: {len(drug_result.opportunities)} opportunities"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(f"**Papers Screened:** {drug_result.papers_screened}")
                    with col2:
                        st.write(f"**Papers Extracted:** {drug_result.papers_extracted}")
                    with col3:
                        st.write(f"**Opportunities:** {len(drug_result.opportunities)}")

                    if drug_result.opportunities:
                        st.write("**Top diseases:**")
                        for i, opp in enumerate(drug_result.opportunities[:5], 1):
                            disease = opp.extraction.disease
                            score = opp.scores.overall_priority
                            st.write(f"  {i}. {disease} (Score: {score:.1f})")

            # Papers Requiring Manual Review (aggregated from all drugs)
            # Collect papers for manual review from all drug results
            all_papers_for_review = []
            if hasattr(result, 'papers_for_manual_review') and result.papers_for_manual_review:
                all_papers_for_review = result.papers_for_manual_review
            else:
                # Fallback: aggregate from individual drug results
                for drug_name, drug_result in result.drug_results.items():
                    if hasattr(drug_result, 'papers_for_manual_review') and drug_result.papers_for_manual_review:
                        all_papers_for_review.extend(drug_result.papers_for_manual_review)

            if all_papers_for_review:
                render_papers_for_manual_review(
                    papers_for_review=all_papers_for_review,
                    title="Papers Requiring Manual Review (Abstract-Only Extractions)"
                )


# Tab 1: Drug Information
with tab1:
    st.header("Step 1: Drug Information")
    st.markdown("""
    Retrieve approved indications from DailyMed, Drugs.com, and OpenFDA.
    Uses the `DrugInfoService` component.
    """)

    if not st.session_state.v3_drug_name:
        st.warning("Enter a drug name in the sidebar to begin.")
    else:
        col1, col2 = st.columns([3, 1])

        with col1:
            if st.button("Fetch Drug Information", type="primary", use_container_width=True):
                with st.spinner(f"Fetching info for {st.session_state.v3_drug_name}..."):
                    try:
                        drug_info = run_async(
                            orchestrator.get_drug_info(st.session_state.v3_drug_name)
                        )
                        st.session_state.v3_drug_info = drug_info
                        st.success("Drug information retrieved!")
                    except Exception as e:
                        st.error(f"Error: {e}")
                        logger.error(f"Drug info error: {e}", exc_info=True)

        with col2:
            st.metric("Status", "Loaded" if st.session_state.v3_drug_info else "Not loaded")

        # Display drug info
        if st.session_state.v3_drug_info:
            info = st.session_state.v3_drug_info

            st.markdown("---")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**Drug Name**")
                st.write(info.drug_name)
            with col2:
                st.markdown("**Generic Name**")
                st.write(info.generic_name or "N/A")
            with col3:
                st.markdown("**Mechanism**")
                st.write(info.mechanism or "N/A")

            st.markdown("---")
            st.subheader(f"Approved Indications ({len(info.approved_indications)})")

            if info.approved_indications:
                for i, ind in enumerate(info.approved_indications, 1):
                    st.markdown(f"{i}. {ind}")
            else:
                st.info("No approved indications found.")


# Tab 2: Literature Search
with tab2:
    st.header("Step 2: Literature Search")

    if not st.session_state.v3_drug_info:
        st.warning("Complete Step 1 (Drug Information) first.")
    else:
        # Sub-tabs for Standard and Preprint searches
        search_tab1, search_tab2 = st.tabs([
            "📚 Standard Sources (PubMed, Semantic Scholar, Web)",
            "🔬 Preprint Servers (bioRxiv, medRxiv)"
        ])

        # Standard Sources Tab
        with search_tab1:
            st.markdown("""
            Search for case series using `LiteratureSearchService`.
            Multi-source: PubMed, Semantic Scholar, Web Search.
            """)

            col1, col2 = st.columns(2)

            with col1:
                use_llm_filter = st.checkbox("LLM Relevance Filtering", value=True, key="standard_llm_filter")
            with col2:
                max_per_source = st.slider("Max results per source", 10, 200, 50, key="standard_max_source")

            if st.button("Search Standard Sources", type="primary", use_container_width=True, key="search_standard"):
                with st.spinner("Searching literature..."):
                    try:
                        drug_info = st.session_state.v3_drug_info
                        search_result = run_async(
                            orchestrator.search_literature(
                                drug_name=drug_info.drug_name,
                                exclude_indications=drug_info.approved_indications,
                                max_per_source=max_per_source,
                                filter_with_llm=use_llm_filter,
                                generic_name=drug_info.generic_name,
                            )
                        )
                        st.session_state.v3_search_result = search_result
                        st.success(f"Found {len(search_result.papers)} papers!")
                    except Exception as e:
                        st.error(f"Error: {e}")
                        logger.error(f"Search error: {e}", exc_info=True)

            # Display standard results
            if st.session_state.v3_search_result:
                result = st.session_state.v3_search_result

                st.markdown("---")
                st.subheader(f"Found {len(result.papers)} Papers")

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Found", result.total_found)
                with col2:
                    st.metric("Duplicates Removed", result.duplicates_removed)
                with col3:
                    st.metric("Sources", len(result.sources_searched))

                # Paper list
                for i, paper in enumerate(result.papers[:20], 1):
                    title = paper.title or "No title"
                    display_title = f"{title[:80]}..." if len(title) > 80 else title
                    with st.expander(f"{i}. {display_title}"):
                        st.write(f"**PMID:** {paper.pmid or 'N/A'}")
                        st.write(f"**Journal:** {paper.journal or 'N/A'}")
                        st.write(f"**Year:** {paper.year or 'N/A'}")
                        st.write(f"**Source:** {paper.source}")
                        abstract_text = paper.abstract[:500] + "..." if paper.abstract and len(paper.abstract) > 500 else (paper.abstract or "No abstract")
                        st.write(f"**Abstract:** {abstract_text}")

                if len(result.papers) > 20:
                    st.info(f"Showing 20 of {len(result.papers)} papers")

        # Preprint Sources Tab
        with search_tab2:
            st.warning("""
            **Preprint papers are not peer-reviewed.**
            Evidence scores are reduced by 30% to reflect this.
            Always verify findings in peer-reviewed literature before clinical application.
            """)

            st.markdown("""
            Search bioRxiv and medRxiv for preprints from the **last 2 years**.
            Results are kept separate from standard sources.
            """)

            col1, col2, col3 = st.columns(3)

            with col1:
                preprint_server = st.selectbox(
                    "Server",
                    options=["both", "biorxiv", "medrxiv"],
                    format_func=lambda x: {"both": "Both", "biorxiv": "bioRxiv only", "medrxiv": "medRxiv only"}[x],
                    key="preprint_server"
                )
            with col2:
                preprint_llm_filter = st.checkbox("LLM Relevance Filtering", value=True, key="preprint_llm_filter")
            with col3:
                max_preprints = st.slider("Max results", 50, 300, 100, key="preprint_max")

            if st.button("Search Preprint Servers", type="primary", use_container_width=True, key="search_preprints"):
                with st.spinner("Searching preprint servers..."):
                    try:
                        drug_info = st.session_state.v3_drug_info

                        # Get standard papers for deduplication (if available)
                        standard_papers = None
                        if st.session_state.v3_search_result:
                            standard_papers = st.session_state.v3_search_result.papers

                        preprint_result = run_async(
                            orchestrator.search_preprint_literature(
                                drug_name=drug_info.drug_name,
                                generic_name=drug_info.generic_name,
                                approved_indications=drug_info.approved_indications,
                                max_results=max_preprints,
                                server=preprint_server,
                                years_back=2,
                                apply_llm_filter=preprint_llm_filter,
                                standard_papers=standard_papers,
                            )
                        )
                        st.session_state.v3_preprint_search_result = preprint_result
                        st.success(f"Found {len(preprint_result.papers)} preprints!")
                    except Exception as e:
                        st.error(f"Error: {e}")
                        logger.error(f"Preprint search error: {e}", exc_info=True)

            # Display preprint results
            if st.session_state.v3_preprint_search_result:
                result = st.session_state.v3_preprint_search_result

                st.markdown("---")
                st.subheader(f"Found {len(result.papers)} Preprints")

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Found", result.total_found)
                with col2:
                    st.metric("Duplicates Removed", result.duplicates_removed)
                with col3:
                    st.metric("Sources", ", ".join(result.sources_searched))

                # Paper list with preprint badges
                for i, paper in enumerate(result.papers[:20], 1):
                    title = paper.title or "No title"
                    display_title = f"{title[:80]}..." if len(title) > 80 else title

                    # Add preprint server badge
                    server_badge = f"🔬 {paper.source}" if paper.source else "🔬 Preprint"
                    pub_status = "✅ Published" if paper.published_doi else "📝 Preprint"

                    with st.expander(f"{i}. [{server_badge}] {display_title}"):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"**DOI:** {paper.doi or 'N/A'}")
                            st.write(f"**Year:** {paper.year or 'N/A'}")
                            st.write(f"**Server:** {paper.preprint_server or paper.source}")
                        with col2:
                            if paper.published_doi:
                                st.success(pub_status)
                                st.write(f"Published: {paper.published_doi}")
                            else:
                                st.warning(pub_status)

                        abstract_text = paper.abstract[:500] + "..." if paper.abstract and len(paper.abstract) > 500 else (paper.abstract or "No abstract")
                        st.write(f"**Abstract:** {abstract_text}")

                        if paper.url:
                            st.markdown(f"[View on {paper.source}]({paper.url})")

                if len(result.papers) > 20:
                    st.info(f"Showing 20 of {len(result.papers)} preprints")


# Tab 3: Data Extraction
with tab3:
    st.header("Step 3: Data Extraction")
    st.markdown("""
    Extract structured data using `ExtractionService`.
    Uses Claude with extended thinking for accuracy.
    """)

    if not st.session_state.v3_search_result:
        st.warning("Complete Step 2 (Literature Search) first.")
    else:
        papers = st.session_state.v3_search_result.papers
        st.write(f"**{len(papers)} papers available for extraction**")

        max_extract = st.slider("Max papers to extract", 1, min(50, len(papers)), min(10, len(papers)))

        if st.button("Extract Data", type="primary", use_container_width=True):
            progress = st.progress(0)
            status = st.empty()

            try:
                drug_info = st.session_state.v3_drug_info
                papers_to_extract = papers[:max_extract]

                status.write("Extracting data from papers...")
                extractions = run_async(
                    orchestrator.extract_data(
                        papers=papers_to_extract,
                        drug_info=drug_info,
                    )
                )
                progress.progress(100)

                st.session_state.v3_extractions = extractions
                st.success(f"Extracted data from {len(extractions)} papers!")

            except Exception as e:
                st.error(f"Error: {e}")
                logger.error(f"Extraction error: {e}", exc_info=True)

        # Display extractions
        if st.session_state.v3_extractions:
            st.markdown("---")
            st.subheader(f"Extracted {len(st.session_state.v3_extractions)} Case Series")

            for i, ext in enumerate(st.session_state.v3_extractions, 1):
                n_patients = ext.patient_population.n_patients if ext.patient_population else None
                # Get individual score if available
                ind_score = ext.individual_score.total_score if ext.individual_score else None
                score_str = f" - Score: {ind_score:.1f}/10" if ind_score else ""

                with st.expander(f"{i}. {ext.disease} (n={n_patients or 'N/A'}){score_str}"):
                    # Show individual study score breakdown if available
                    if ext.individual_score:
                        st.markdown("**Study Quality Score**")
                        score = ext.individual_score
                        cols = st.columns(6)
                        with cols[0]:
                            st.metric("Total", f"{score.total_score:.1f}")
                        with cols[1]:
                            st.metric("Efficacy", f"{score.efficacy_score:.1f}", help="35% weight")
                        with cols[2]:
                            st.metric("Sample Size", f"{score.sample_size_score:.1f}", help="15% weight")
                        with cols[3]:
                            st.metric("Endpoints", f"{score.endpoint_quality_score:.1f}", help="10% weight")
                        with cols[4]:
                            st.metric("Biomarkers", f"{score.biomarker_score:.1f}", help="15% weight")
                        with cols[5]:
                            st.metric("Response Def", f"{score.response_definition_score:.1f}", help="15% weight + 10% follow-up")
                        st.markdown("---")

                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Disease:** {ext.disease}")
                        st.write(f"**Patients:** {n_patients or 'N/A'}")
                        resp_pct = ext.efficacy.responders_pct if ext.efficacy else None
                        st.write(f"**Response Rate:** {resp_pct if resp_pct is not None else 'N/A'}{'%' if resp_pct is not None else ''}")
                    with col2:
                        st.write(f"**PMID:** {ext.source.pmid if ext.source else 'N/A'}")
                        st.write(f"**Year:** {ext.source.year if ext.source else 'N/A'}")
                        sae_pct = ext.safety.sae_percentage if ext.safety else None
                        st.write(f"**SAE Rate:** {sae_pct if sae_pct is not None else 'N/A'}{'%' if sae_pct is not None else ''}")


# Tab 4: Scoring & Results
with tab4:
    st.header("Step 4: Scoring & Results")
    st.markdown("""
    Score and rank opportunities using the **6-Dimension Scoring System**:

    | Dimension | Weight | Description |
    |-----------|--------|-------------|
    | Efficacy | 35% | Quantitative clinical response data |
    | Sample Size | 15% | Number of patients (calibrated for case series) |
    | Endpoint Quality | 10% | Validated vs ad-hoc instruments |
    | Biomarker Support | 15% | Biomarkers quantified with beneficial change |
    | Response Definition | 15% | Regulatory/disease-specific vs implicit |
    | Follow-up Duration | 10% | Length of follow-up period |

    **Aggregate scores** show N-weighted average across all studies for each disease.
    """)

    if not st.session_state.v3_extractions:
        st.warning("Complete Step 3 (Data Extraction) first.")
    else:
        enrich_market = st.checkbox("Add Market Intelligence", value=True)

        if st.button("Score & Rank Opportunities", type="primary", use_container_width=True):
            with st.spinner("Scoring opportunities..."):
                try:
                    from src.case_series.models import RepurposingOpportunity

                    # Create opportunities from extractions
                    opportunities = [
                        RepurposingOpportunity(extraction=ext)
                        for ext in st.session_state.v3_extractions
                    ]

                    # Enrich with market data if requested
                    if enrich_market:
                        opportunities = run_async(
                            orchestrator.enrich_with_market_data(opportunities)
                        )

                    # Score and rank
                    ranked = orchestrator.score_and_rank(opportunities)
                    st.session_state.v3_opportunities = ranked
                    st.success(f"Ranked {len(ranked)} opportunities!")

                except Exception as e:
                    st.error(f"Error: {e}")
                    logger.error(f"Scoring error: {e}", exc_info=True)

        # Display ranked opportunities
        if st.session_state.v3_opportunities:
            st.markdown("---")
            st.subheader("Ranked Opportunities")

            for opp in st.session_state.v3_opportunities:
                ext = opp.extraction
                scores = opp.scores
                agg = opp.aggregate_score

                # Build display string with aggregate info
                agg_info = ""
                if agg:
                    agg_info = f" (Aggregate: {agg.aggregate_score:.1f}/10, {agg.study_count} studies, N={agg.total_patients})"

                with st.expander(f"#{opp.rank}: {ext.disease} - Score: {scores.overall_priority:.1f}/10{agg_info}"):
                    # Show aggregate scores if available
                    if agg:
                        st.markdown("**Aggregate Disease Scores** (across all studies)")
                        cols = st.columns(5)
                        with cols[0]:
                            st.metric("Aggregate Score", f"{agg.aggregate_score:.1f}")
                        with cols[1]:
                            st.metric("Studies", agg.study_count)
                        with cols[2]:
                            st.metric("Total N", agg.total_patients)
                        with cols[3]:
                            st.metric("Best Paper Score", f"{agg.best_paper_score:.1f}" if agg.best_paper_score else "N/A")
                        with cols[4]:
                            st.metric("Consistency", agg.consistency_level or "N/A")

                        if agg.best_paper_pmid:
                            st.caption(f"Best paper: PMID {agg.best_paper_pmid}")
                        st.markdown("---")

                    # Show individual study score if available
                    if ext.individual_score:
                        st.markdown("**Individual Study Score**")
                        score = ext.individual_score
                        cols = st.columns(6)
                        with cols[0]:
                            st.metric("Total", f"{score.total_score:.1f}")
                        with cols[1]:
                            st.metric("Efficacy", f"{score.efficacy_score:.1f}")
                        with cols[2]:
                            st.metric("Sample Size", f"{score.sample_size_score:.1f}")
                        with cols[3]:
                            st.metric("Endpoints", f"{score.endpoint_quality_score:.1f}")
                        with cols[4]:
                            st.metric("Biomarkers", f"{score.biomarker_score:.1f}")
                        with cols[5]:
                            st.metric("Response Def", f"{score.response_definition_score:.1f}")
                        st.markdown("---")

                    col1, col2 = st.columns(2)

                    with col1:
                        n_patients = ext.patient_population.n_patients if ext.patient_population else None
                        resp_pct = ext.efficacy.responders_pct if ext.efficacy else None
                        sae_pct = ext.safety.sae_percentage if ext.safety else None
                        pop_type = ext.patient_population.population_type if ext.patient_population else None
                        is_refractory = ext.patient_population.is_refractory if ext.patient_population else None
                        severity = ext.patient_population.disease_severity if ext.patient_population else None
                        st.write(f"**Patients:** {n_patients or 'N/A'}")
                        st.write(f"**Response Rate:** {resp_pct if resp_pct is not None else 'N/A'}{'%' if resp_pct is not None else ''}")
                        st.write(f"**SAE Rate:** {sae_pct if sae_pct is not None else 'N/A'}{'%' if sae_pct is not None else ''}")
                        if pop_type or is_refractory is not None or severity:
                            pop_info = []
                            if pop_type:
                                pop_info.append(pop_type)
                            elif is_refractory:
                                pop_info.append("refractory")
                            if severity:
                                pop_info.append(f"{severity} severity")
                            st.write(f"**Population:** {', '.join(pop_info)}" if pop_info else "")

                    with col2:
                        st.write(f"**PMID:** {ext.source.pmid if ext.source else 'N/A'}")
                        st.write(f"**Year:** {ext.source.year if ext.source else 'N/A'}")
                        if opp.market_intelligence:
                            mi = opp.market_intelligence
                            pop_size = mi.epidemiology.patient_population_size if mi.epidemiology else None
                            st.write(f"**Market Size:** {pop_size:,} patients" if pop_size else "**Market Size:** N/A")


# Tab 5: Full Analysis
with tab5:
    st.header("Step 5: Full Analysis")
    st.markdown("""
    Run complete analysis pipeline using `CaseSeriesOrchestrator.analyze()`.
    Executes all steps automatically.
    """)

    if not st.session_state.v3_drug_name:
        st.warning("Enter a drug name in the sidebar to begin.")
    else:
        st.write(f"**Drug:** {st.session_state.v3_drug_name}")

        # Test mode toggle
        test_mode = st.checkbox("Test Mode (limit papers for faster testing)", value=True)

        if test_mode:
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                max_papers_to_find = st.number_input(
                    "Max papers to find",
                    min_value=5,
                    max_value=100,
                    value=30,
                    help="Max papers to retrieve per source (PubMed, Semantic Scholar)"
                )
            with col2:
                max_papers_to_extract = st.number_input(
                    "Max papers to extract",
                    min_value=1,
                    max_value=100,
                    value=10,
                    help="Limit number of papers to actually extract data from"
                )
            with col3:
                with_market = st.checkbox("Include market intelligence", value=False)
            with col4:
                supplemental_mode = st.checkbox(
                    "Supplemental search",
                    value=False,
                    help="Skip papers already processed in previous runs."
                )
            with col5:
                max_concurrent = st.number_input(
                    "Concurrent extractions",
                    min_value=1,
                    max_value=10,
                    value=3,
                    help="Number of papers to extract in parallel"
                )
        else:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                max_papers_to_find = 500  # High limit to get all available papers
                max_papers_to_extract = None  # No limit
                st.info("Full analysis: retrieves all papers, extracts all")
            with col2:
                with_market = st.checkbox("Include market intelligence", value=True)
            with col3:
                supplemental_mode = st.checkbox(
                    "Supplemental search",
                    value=False,
                    help="Skip papers already processed in previous runs. Use this to add new papers without re-processing existing ones."
                )
            with col4:
                max_concurrent = st.number_input(
                    "Concurrent extractions",
                    min_value=1,
                    max_value=10,
                    value=5,
                    help="Number of papers to extract in parallel"
                )

        if st.button("Run Full Analysis", type="primary", use_container_width=True):
            progress = st.progress(0)
            status = st.empty()

            try:
                from src.case_series.orchestrator import AnalysisConfig

                # Debug: Show what values we're passing
                logger.info(f"Creating AnalysisConfig with supplemental={supplemental_mode}")
                st.write(f"Debug: supplemental_mode = {supplemental_mode}")

                config = AnalysisConfig(
                    max_papers_per_source=max_papers_to_find,
                    max_papers_to_extract=max_papers_to_extract if test_mode else None,
                    enrich_market_data=with_market,
                    max_concurrent_extractions=max_concurrent,
                    supplemental=supplemental_mode,
                )

                extract_msg = f"max {max_papers_to_extract}" if test_mode else "all"
                supp_msg = " [SUPPLEMENTAL MODE]" if supplemental_mode else ""
                status.write(f"Running analysis (find up to {max_papers_to_find}, extract {extract_msg}){supp_msg}...")

                result = run_async(
                    orchestrator.analyze(st.session_state.v3_drug_name, config=config)
                )

                progress.progress(100)
                st.session_state.v3_result = result

                # Also update individual state
                st.session_state.v3_opportunities = result.opportunities

                st.success(f"Analysis complete! Found {len(result.opportunities)} opportunities.")

            except Exception as e:
                st.error(f"Error: {e}")
                logger.error(f"Analysis error: {e}", exc_info=True)

        # Display result
        if st.session_state.v3_result:
            result = st.session_state.v3_result

            st.markdown("---")
            st.subheader("Analysis Summary")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Papers Screened", result.papers_screened)
            with col2:
                st.metric("Papers Extracted", result.papers_extracted)
            with col3:
                st.metric("Opportunities", len(result.opportunities))
            with col4:
                st.metric("Est. Cost", f"${result.estimated_cost_usd:.2f}")

            # Aggregated Disease Summary with Hierarchical Display
            st.markdown("---")
            st.subheader("🏥 Disease-Level Summary (with Score Explanations)")

            from src.case_series.services.aggregation_service import aggregate_opportunities_by_disease

            aggregated = aggregate_opportunities_by_disease(result.opportunities)

            # Try to load explanations from database (if available)
            explanations = {}
            try:
                if orchestrator._repository and orchestrator._run_id:
                    explanations = orchestrator._repository.load_score_explanations(orchestrator._run_id)
                    if explanations:
                        st.info(f"📝 Loaded {len(explanations)} AI-generated score explanations")
            except Exception as e:
                logger.debug(f"Could not load explanations: {e}")

            st.write(f"**{len(aggregated)} unique diseases** across {len(result.opportunities)} papers")
            st.caption("Click on a disease to see individual papers with 6-dimension score breakdown and AI explanations.")

            for agg in aggregated:
                # Get explanation for this disease
                explanation = explanations.get(agg.disease)

                # Use the new hierarchical card helper
                render_hierarchical_disease_card(
                    agg=agg,
                    explanation=explanation,
                    drug_name=result.drug_name,
                )

            # Individual papers view (collapsible)
            st.markdown("---")
            with st.expander("View All Individual Papers"):
                st.subheader("All Opportunities (Individual Papers)")

                for opp in result.opportunities:
                    ext = opp.extraction
                    scores = opp.scores
                    n_patients = ext.patient_population.n_patients if ext.patient_population else 'N/A'
                    resp_pct = ext.efficacy.responders_pct if ext.efficacy else None
                    resp_str = f"{resp_pct}%" if resp_pct is not None else 'N/A'

                    st.markdown(f"""
                    **#{opp.rank}. {ext.disease}** - Score: {scores.overall_priority:.1f}/10
                    - Patients: {n_patients} | Response: {resp_str}
                    """)

            # Papers Requiring Manual Review
            if hasattr(result, 'papers_for_manual_review') and result.papers_for_manual_review:
                render_papers_for_manual_review(
                    papers_for_review=result.papers_for_manual_review,
                    title="Papers Requiring Manual Review (Abstract-Only Extractions)"
                )


# Tab 6: History
with tab6:
    st.header("Analysis History")
    st.markdown("""
    View historical analysis runs, extractions, and opportunities from the database.
    """)

    # Database connection check
    database_url = getattr(settings, 'drug_database_url', None) or getattr(settings, 'disease_landscape_url', None)
    if not database_url:
        st.warning("No database URL configured. History is only available when connected to a database.")
    else:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        try:
            conn = psycopg2.connect(database_url)

            # Section 1: Historical Runs
            st.subheader("Historical Runs")
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT run_id, drug_name, status, papers_found, papers_extracted,
                           opportunities_found, estimated_cost_usd, started_at, completed_at
                    FROM cs_analysis_runs
                    WHERE status NOT IN ('in_progress', 'running')
                    ORDER BY started_at DESC
                    LIMIT 20
                """)
                runs = cur.fetchall()

            if runs:
                selected_run = st.selectbox(
                    "Select a run to view details",
                    options=runs,
                    format_func=lambda r: f"{r['drug_name']} - {r['started_at'].strftime('%Y-%m-%d %H:%M')} ({r['status']})"
                )

                if selected_run:
                    run_id = selected_run['run_id']

                    # Run Summary
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.metric("Status", selected_run['status'])
                    with col2:
                        st.metric("Papers Found", selected_run['papers_found'] or 0)
                    with col3:
                        st.metric("Extracted", selected_run['papers_extracted'] or 0)
                    with col4:
                        st.metric("Opportunities", selected_run['opportunities_found'] or 0)
                    with col5:
                        cost = selected_run['estimated_cost_usd'] or 0
                        st.metric("Cost", f"${cost:.2f}")

                    # Extractions for this run
                    st.markdown("---")
                    st.subheader("Extractions")

                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute("""
                            SELECT disease, pmid, paper_title, paper_year, n_patients,
                                   responders_pct, efficacy_signal, safety_profile,
                                   evidence_level, is_off_label, extracted_at
                            FROM cs_extractions
                            WHERE run_id = %s
                            ORDER BY disease, extracted_at
                        """, (run_id,))
                        extractions = cur.fetchall()

                    if extractions:
                        # Group by disease
                        diseases = {}
                        for ext in extractions:
                            d = ext['disease'] or 'Unclassified'
                            if d not in diseases:
                                diseases[d] = []
                            diseases[d].append(ext)

                        st.write(f"**{len(extractions)} extractions across {len(diseases)} diseases**")

                        for disease, exts in sorted(diseases.items(), key=lambda x: -len(x[1])):
                            with st.expander(f"{disease} ({len(exts)} papers)"):
                                for ext in exts:
                                    patients = ext['n_patients'] if ext['n_patients'] else 'N/A'
                                    resp = f"{ext['responders_pct']}%" if ext['responders_pct'] else 'N/A'
                                    efficacy = ext['efficacy_signal'] or 'N/A'
                                    safety = ext['safety_profile'] or 'N/A'
                                    evidence = ext['evidence_level'] or 'N/A'

                                    st.markdown(f"""
                                    **PMID {ext['pmid']}** ({ext['paper_year'] or 'N/A'})
                                    - Title: {ext['paper_title'][:100] if ext['paper_title'] else 'N/A'}...
                                    - Patients: {patients} | Response: {resp}
                                    - Efficacy: {efficacy} | Safety: {safety} | Evidence: {evidence}
                                    """)
                    else:
                        st.info("No extractions found for this run.")

                    # Opportunities for this run
                    st.markdown("---")
                    st.subheader("Opportunities & Scores")

                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute("""
                            SELECT rank, disease, paper_count, total_patients,
                                   aggregate_score, best_paper_score, best_paper_pmid,
                                   study_count, avg_response_rate, consistency_level, response_rate_cv,
                                   efficacy_signal, safety_profile, evidence_level,
                                   recommendation, key_findings
                            FROM cs_opportunities
                            WHERE run_id = %s
                            ORDER BY aggregate_score DESC NULLS LAST
                        """, (run_id,))
                        opportunities = cur.fetchall()

                    if opportunities:
                        st.write(f"**{len(opportunities)} scored opportunities** (sorted by aggregate paper score)")

                        for i, opp in enumerate(opportunities, 1):
                            agg_score = float(opp['aggregate_score']) if opp['aggregate_score'] else 0
                            best_score = float(opp['best_paper_score']) if opp['best_paper_score'] else 0
                            best_pmid = opp['best_paper_pmid'] or 'N/A'
                            studies = opp['study_count'] or opp['paper_count'] or 0
                            patients = opp['total_patients'] or 0
                            avg_response = opp['avg_response_rate']
                            consistency = opp['consistency_level'] or 'N/A'
                            response_cv = opp['response_rate_cv']

                            with st.expander(f"#{i}. {opp['disease']} - Aggregate: {agg_score:.1f}/10 ({studies} studies, N={patients})"):
                                # Primary metrics: Aggregate scores (matching full analysis section)
                                st.markdown("**Aggregate Evidence Summary:**")
                                col1, col2, col3, col4, col5 = st.columns(5)
                                with col1:
                                    st.metric("Aggregate Score", f"{agg_score:.1f}/10", help="N-weighted avg of individual paper scores")
                                with col2:
                                    st.metric("Studies", studies)
                                with col3:
                                    st.metric("Total Patients", patients)
                                with col4:
                                    response_str = f"{avg_response:.0f}%" if avg_response else "N/A"
                                    st.metric("Pooled Response", response_str)
                                with col5:
                                    st.metric("Consistency", consistency)

                                # Best paper info
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Best Paper Score", f"{best_score:.1f}/10")
                                with col2:
                                    st.markdown(f"**Best Paper PMID:** {best_pmid}")
                                with col3:
                                    if response_cv:
                                        st.markdown(f"**Response CV:** {response_cv:.2f}")

                                # AI Score Explanation
                                with conn.cursor(cursor_factory=RealDictCursor) as expl_cur:
                                    expl_cur.execute("""
                                        SELECT aggregate_explanation
                                        FROM cs_score_explanations
                                        WHERE run_id = %s AND disease = %s
                                        LIMIT 1
                                    """, (run_id, opp['disease']))
                                    expl_row = expl_cur.fetchone()

                                if expl_row and expl_row['aggregate_explanation']:
                                    with st.expander("AI Score Explanation", expanded=False):
                                        st.markdown(expl_row['aggregate_explanation'])

                                st.markdown(f"""
                                - Efficacy Signal: {opp['efficacy_signal'] or 'N/A'}
                                - Safety Profile: {opp['safety_profile'] or 'N/A'}
                                - Evidence Level: {opp['evidence_level'] or 'N/A'}
                                """)

                                if opp['key_findings']:
                                    st.markdown(f"**Key Findings:** {opp['key_findings'][:500]}...")

                                # Show individual papers for this disease
                                st.markdown("---")
                                st.markdown("**Individual Papers:**")
                                with conn.cursor(cursor_factory=RealDictCursor) as paper_cur:
                                    paper_cur.execute("""
                                        SELECT pmid, paper_title, n_patients, individual_score,
                                               score_breakdown, responders_pct, efficacy_summary,
                                               primary_endpoint, primary_endpoint_result, full_extraction
                                        FROM cs_extractions
                                        WHERE run_id = %s AND disease = %s
                                        ORDER BY individual_score DESC NULLS LAST
                                    """, (run_id, opp['disease']))
                                    disease_papers = paper_cur.fetchall()

                                if disease_papers:
                                    for paper in disease_papers:
                                        pmid = paper['pmid'] or 'N/A'
                                        title = (paper['paper_title'] or 'No title')[:60]
                                        n_pts = paper['n_patients'] or 'N/A'
                                        total_score = float(paper['individual_score']) if paper['individual_score'] else 0
                                        resp_pct = paper['responders_pct']

                                        # Get score breakdown
                                        breakdown = paper['score_breakdown'] or {}
                                        eff_score = breakdown.get('efficacy_score', 'N/A')
                                        ss_score = breakdown.get('sample_size_score', 'N/A')
                                        eq_score = breakdown.get('endpoint_quality_score', 'N/A')
                                        bio_score = breakdown.get('biomarker_score', 'N/A')
                                        rd_score = breakdown.get('response_definition_score', 'N/A')
                                        fu_score = breakdown.get('followup_score', 'N/A')

                                        with st.expander(f"PMID {pmid}: {title}... (Score: {total_score:.1f}, N={n_pts})"):
                                            # 6-dimension score breakdown
                                            st.markdown("**6-Dimension Score Breakdown:**")
                                            score_cols = st.columns(6)
                                            dims = [
                                                ("Efficacy", eff_score, "35%"),
                                                ("Sample", ss_score, "15%"),
                                                ("Endpoint", eq_score, "10%"),
                                                ("Biomarker", bio_score, "15%"),
                                                ("Response", rd_score, "15%"),
                                                ("Follow-up", fu_score, "10%"),
                                            ]
                                            for col, (name, score, weight) in zip(score_cols, dims):
                                                with col:
                                                    score_str = f"{float(score):.1f}" if score and score != 'N/A' else 'N/A'
                                                    st.metric(f"{name} ({weight})", score_str)

                                            # Primary endpoint and response
                                            st.markdown("---")
                                            st.markdown("**Primary Endpoint:**")
                                            primary_ep = paper.get('primary_endpoint') or 'Not specified'
                                            primary_result = paper.get('primary_endpoint_result') or ''
                                            if resp_pct:
                                                st.markdown(f"- **{primary_ep}**: {resp_pct:.1f}% response rate")
                                            elif primary_result:
                                                st.markdown(f"- **{primary_ep}**: {primary_result[:150]}")
                                            else:
                                                st.markdown(f"- {primary_ep}")

                                            # Detailed endpoints from full_extraction
                                            full_ext = paper.get('full_extraction') or {}
                                            detailed_eps = full_ext.get('detailed_efficacy_endpoints', [])

                                            if detailed_eps:
                                                # Separate by category
                                                primary_eps = [e for e in detailed_eps if e.get('endpoint_category') == 'Primary']
                                                secondary_eps = [e for e in detailed_eps if e.get('endpoint_category') == 'Secondary']
                                                biomarker_eps = [e for e in detailed_eps if e.get('is_biomarker')]

                                                st.markdown("**Detailed Endpoints Used for Scoring:**")

                                                # Primary endpoints
                                                if primary_eps:
                                                    for ep in primary_eps[:3]:
                                                        ep_name = ep.get('endpoint_name', 'Unknown')
                                                        ep_value = ""
                                                        if ep.get('responders_pct'):
                                                            ep_value = f"{ep['responders_pct']:.1f}% response"
                                                        elif ep.get('change_pct'):
                                                            ep_value = f"{ep['change_pct']:.1f}% change"
                                                        elif ep.get('change_from_baseline') is not None and ep.get('baseline_value'):
                                                            pct = abs(ep['change_from_baseline'] / ep['baseline_value']) * 100
                                                            direction = "↓" if ep['change_from_baseline'] < 0 else "↑"
                                                            ep_value = f"{direction}{pct:.0f}% from baseline"
                                                        elif ep.get('value') is not None:
                                                            ep_value = f"value: {ep['value']}"
                                                        p_val = f" (p={ep['p_value']})" if ep.get('p_value') else ""
                                                        st.markdown(f"  - 🎯 **{ep_name}**: {ep_value}{p_val}")

                                                # Secondary endpoints (limit to 3)
                                                non_biomarker_secondary = [e for e in secondary_eps if not e.get('is_biomarker')]
                                                if non_biomarker_secondary:
                                                    for ep in non_biomarker_secondary[:3]:
                                                        ep_name = ep.get('endpoint_name', 'Unknown')
                                                        ep_value = ""
                                                        if ep.get('responders_pct'):
                                                            ep_value = f"{ep['responders_pct']:.1f}% response"
                                                        elif ep.get('change_pct'):
                                                            ep_value = f"{ep['change_pct']:.1f}% change"
                                                        elif ep.get('change_from_baseline') is not None and ep.get('baseline_value'):
                                                            pct = abs(ep['change_from_baseline'] / ep['baseline_value']) * 100
                                                            direction = "↓" if ep['change_from_baseline'] < 0 else "↑"
                                                            ep_value = f"{direction}{pct:.0f}% from baseline"
                                                        elif ep.get('value') is not None:
                                                            ep_value = f"value: {ep['value']}"
                                                        p_val = f" (p={ep['p_value']})" if ep.get('p_value') else ""
                                                        st.markdown(f"  - 📊 {ep_name}: {ep_value}{p_val}")

                                                # Biomarker endpoints (limit to 3)
                                                if biomarker_eps:
                                                    for ep in biomarker_eps[:3]:
                                                        ep_name = ep.get('endpoint_name', 'Unknown')
                                                        ep_value = ""
                                                        if ep.get('change_pct'):
                                                            ep_value = f"{ep['change_pct']:.1f}% change"
                                                        elif ep.get('change_from_baseline') is not None and ep.get('baseline_value'):
                                                            pct = abs(ep['change_from_baseline'] / ep['baseline_value']) * 100
                                                            direction = "↓" if ep['change_from_baseline'] < 0 else "↑"
                                                            ep_value = f"{direction}{pct:.0f}% from baseline"
                                                        elif ep.get('value') is not None:
                                                            unit = ep.get('unit', '')
                                                            ep_value = f"{ep['value']} {unit}".strip()
                                                        p_val = f" (p={ep['p_value']})" if ep.get('p_value') else ""
                                                        st.markdown(f"  - 🧬 {ep_name}: {ep_value}{p_val}")

                                                # Show count if more endpoints exist
                                                total_eps = len(detailed_eps)
                                                shown = min(3, len(primary_eps)) + min(3, len(non_biomarker_secondary)) + min(3, len(biomarker_eps))
                                                if total_eps > shown:
                                                    st.caption(f"... and {total_eps - shown} more endpoints")

                                            # Efficacy summary
                                            st.markdown("---")
                                            if paper['efficacy_summary']:
                                                st.markdown(f"**Summary:** {paper['efficacy_summary'][:400]}...")

                                            # Scoring notes
                                            if breakdown.get('scoring_notes'):
                                                st.caption(f"Scoring Notes: {breakdown['scoring_notes']}")
                                else:
                                    st.info("No individual paper data available for this disease.")
                    else:
                        st.info("No opportunities found for this run. (Opportunities may not have been saved - try running a new analysis)")

                    # Papers Requiring Manual Review (from database)
                    st.markdown("---")
                    st.subheader("Papers Requiring Manual Review")

                    # Check if we need to backfill
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute("""
                            SELECT COUNT(*) as count FROM cs_papers_for_manual_review
                            WHERE run_id = %s
                        """, (run_id,))
                        existing_count = cur.fetchone()['count']

                    # Backfill button
                    if existing_count == 0:
                        st.info("No papers for manual review found. Click below to generate from existing extractions.")

                    col1, col2 = st.columns([1, 3])
                    with col1:
                        if st.button("Generate/Refresh Manual Review List", key=f"backfill_{run_id}"):
                            with st.spinner("Analyzing abstracts with Haiku..."):
                                try:
                                    # Get abstract-only extractions
                                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                                        cur.execute("""
                                            SELECT
                                                e.pmid, e.drug_name, e.disease, e.paper_title as title, e.paper_year as year,
                                                e.n_patients, e.response_rate, e.primary_endpoint,
                                                e.efficacy_summary as efficacy_mention, e.full_extraction,
                                                p.abstract, p.doi, p.authors, p.journal, p.has_full_text
                                            FROM cs_extractions e
                                            LEFT JOIN cs_papers p ON e.pmid = p.pmid AND p.relevance_drug = e.drug_name
                                            WHERE e.run_id = %s
                                            AND (
                                                e.full_extraction->>'extraction_method' = 'single_pass'
                                                OR e.full_extraction->>'extraction_method' IS NULL
                                                OR NOT COALESCE(p.has_full_text, false)
                                            )
                                        """, (run_id,))
                                        abstract_only_papers = cur.fetchall()

                                    if abstract_only_papers:
                                        # Use Haiku to extract N from abstracts
                                        import anthropic
                                        from src.utils.config import get_settings
                                        settings = get_settings()
                                        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

                                        papers_to_save = []
                                        progress_bar = st.progress(0)

                                        for i, paper in enumerate(abstract_only_papers):
                                            progress_bar.progress((i + 1) / len(abstract_only_papers))

                                            # Try to extract N from abstract using Haiku
                                            n_patients = paper.get('n_patients')
                                            n_confidence = "Medium" if n_patients else "Unknown"
                                            response_rate = paper.get('response_rate')
                                            primary_endpoint = paper.get('primary_endpoint')
                                            efficacy_mention = paper.get('efficacy_mention')

                                            abstract = paper.get('abstract')
                                            if abstract and (not n_patients or not response_rate):
                                                try:
                                                    prompt = f"""Extract key clinical information from this abstract about {paper['drug_name']}.

Abstract:
{abstract[:2000]}

Extract ONLY what is explicitly stated. Return JSON:
{{
    "n_patients": <integer or null if not stated>,
    "n_confidence": "High" if exact number stated, "Medium" if range/approximate, "Low" if inferred,
    "response_rate": "<X/Y>" or "<X%>" format if stated, null otherwise,
    "primary_endpoint": "endpoint name" if stated, null otherwise,
    "efficacy_mention": "One sentence summary of efficacy findings" or null
}}

JSON only:"""

                                                    response = client.messages.create(
                                                        model="claude-3-5-haiku-latest",
                                                        max_tokens=300,
                                                        messages=[{"role": "user", "content": prompt}]
                                                    )

                                                    import json
                                                    try:
                                                        result = json.loads(response.content[0].text)
                                                        if result.get('n_patients') and not n_patients:
                                                            n_patients = result['n_patients']
                                                            n_confidence = result.get('n_confidence', 'Medium')
                                                        if result.get('response_rate') and not response_rate:
                                                            response_rate = result['response_rate']
                                                        if result.get('primary_endpoint') and not primary_endpoint:
                                                            primary_endpoint = result['primary_endpoint']
                                                        if result.get('efficacy_mention') and not efficacy_mention:
                                                            efficacy_mention = result['efficacy_mention']
                                                    except json.JSONDecodeError:
                                                        pass
                                                except Exception as e:
                                                    st.warning(f"Haiku extraction failed for {paper.get('pmid')}: {e}")

                                            # Determine reason
                                            has_full_text = paper.get('has_full_text', False)
                                            if has_full_text:
                                                reason = "Full text fetch failed - had PMCID but couldn't retrieve content"
                                            else:
                                                reason = "Abstract only - full text not available in PMC"

                                            papers_to_save.append({
                                                'pmid': paper.get('pmid'),
                                                'doi': paper.get('doi'),
                                                'title': paper.get('title', ''),
                                                'authors': paper.get('authors'),
                                                'journal': paper.get('journal'),
                                                'year': paper.get('year'),
                                                'abstract': abstract,
                                                'disease': paper.get('disease'),
                                                'n_patients': n_patients,
                                                'n_confidence': n_confidence,
                                                'response_rate': response_rate,
                                                'primary_endpoint': primary_endpoint,
                                                'efficacy_mention': efficacy_mention,
                                                'reason': reason,
                                                'has_full_text': has_full_text,
                                                'extraction_method': 'single_pass',
                                            })

                                        progress_bar.empty()

                                        # Save to database
                                        if papers_to_save:
                                            from src.tools.case_series_database import CaseSeriesDatabase
                                            db = CaseSeriesDatabase(database_url)

                                            # Delete existing entries first for refresh
                                            with conn.cursor() as cur:
                                                cur.execute("DELETE FROM cs_papers_for_manual_review WHERE run_id = %s", (run_id,))
                                                conn.commit()

                                            saved = db.save_papers_for_manual_review(
                                                run_id=str(run_id),
                                                drug_name=selected_run['drug_name'],
                                                papers=papers_to_save,
                                            )
                                            st.success(f"Generated {saved} papers for manual review!")
                                            st.rerun()
                                    else:
                                        st.info("No abstract-only extractions found for this run.")
                                except Exception as e:
                                    st.error(f"Error generating manual review list: {e}")
                                    import traceback
                                    st.code(traceback.format_exc())

                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute("""
                            SELECT pmid, doi, title, authors, journal, year, disease,
                                   n_patients, n_confidence, response_rate, primary_endpoint,
                                   efficacy_mention, reason, has_full_text, extraction_method
                            FROM cs_papers_for_manual_review
                            WHERE run_id = %s
                            ORDER BY n_patients DESC NULLS LAST, title
                        """, (run_id,))
                        manual_review_papers = cur.fetchall()

                    if manual_review_papers:
                        st.markdown("""
                        **These papers passed all relevant filters but were extracted from abstract only.**
                        Full text was not available, so important indication details may be missing.
                        Review these papers manually for potentially missed opportunities.
                        """)

                        # Summary metrics
                        papers_with_n = [p for p in manual_review_papers if p['n_patients'] is not None]
                        total_patients = sum(p['n_patients'] or 0 for p in papers_with_n)
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Papers for Review", len(manual_review_papers))
                        with col2:
                            st.metric("Papers with N", len(papers_with_n))
                        with col3:
                            st.metric("Total Patients", total_patients if total_patients > 0 else "Unknown")

                        # Display each paper
                        for i, paper in enumerate(manual_review_papers, 1):
                            # Build confidence badge for N
                            n_badge = ""
                            if paper['n_patients'] is not None:
                                confidence_color = {
                                    "High": "High",
                                    "Medium": "Med",
                                    "Low": "Low",
                                    "Unknown": "?"
                                }.get(paper['n_confidence'] or 'Unknown', '?')
                                n_badge = f"N={paper['n_patients']} ({confidence_color})"
                            else:
                                n_badge = "N=Unknown"

                            pmid_str = paper['pmid'] or paper['doi'] or "N/A"
                            year_str = f"({paper['year']})" if paper['year'] else ""
                            disease_str = f"| {paper['disease']}" if paper['disease'] else ""

                            with st.expander(f"{i}. {n_badge} | PMID: {pmid_str} {year_str} {disease_str}"):
                                st.markdown(f"**{paper['title']}**")

                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write(f"**Journal:** {paper['journal'] or 'N/A'}")
                                    st.write(f"**Year:** {paper['year'] or 'N/A'}")
                                with col2:
                                    st.write(f"**PMID:** {paper['pmid'] or 'N/A'}")
                                    st.write(f"**Disease:** {paper['disease'] or 'Not extracted'}")

                                st.markdown("---")
                                st.markdown("**Key Information (from abstract):**")
                                eff_col1, eff_col2, eff_col3 = st.columns(3)
                                with eff_col1:
                                    n_display = f"{paper['n_patients']} ({paper['n_confidence']} confidence)" if paper['n_patients'] else "Not found"
                                    st.write(f"**N (patients):** {n_display}")
                                with eff_col2:
                                    st.write(f"**Response Rate:** {paper['response_rate'] or 'Not found'}")
                                with eff_col3:
                                    st.write(f"**Primary Endpoint:** {paper['primary_endpoint'] or 'Not found'}")

                                if paper['efficacy_mention']:
                                    st.info(f"**Efficacy Summary:** {paper['efficacy_mention']}")

                                st.caption(f"Reason for review: {paper['reason']}")

                                if paper['pmid']:
                                    st.markdown(f"[View on PubMed](https://pubmed.ncbi.nlm.nih.gov/{paper['pmid']}/)")
                    else:
                        st.info("No papers requiring manual review for this run.")

            else:
                st.info("No historical runs found in the database.")

            # Section 2: Paper Discoveries
            st.markdown("---")
            st.subheader("Paper Discoveries")

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT discovery_id, drug_name, total_papers, papers_passing_filter,
                           duplicates_removed, discovered_at
                    FROM cs_paper_discoveries
                    ORDER BY discovered_at DESC
                    LIMIT 10
                """)
                discoveries = cur.fetchall()

            if discoveries:
                for disc in discoveries:
                    passing_pct = (disc['papers_passing_filter'] / disc['total_papers'] * 100) if disc['total_papers'] else 0
                    with st.expander(f"{disc['drug_name']} - {disc['discovered_at'].strftime('%Y-%m-%d %H:%M')} ({disc['total_papers']} papers)"):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Papers", disc['total_papers'])
                        with col2:
                            st.metric("Passing Filter", f"{disc['papers_passing_filter']} ({passing_pct:.0f}%)")
                        with col3:
                            st.metric("Duplicates Removed", disc['duplicates_removed'])

                        # Show papers in this discovery
                        with conn.cursor(cursor_factory=RealDictCursor) as cur:
                            cur.execute("""
                                SELECT pmid, title, disease, year, would_pass_filter, filter_reason
                                FROM cs_discovery_papers
                                WHERE discovery_id = %s
                                ORDER BY would_pass_filter DESC, disease
                                LIMIT 50
                            """, (disc['discovery_id'],))
                            papers = cur.fetchall()

                        if papers:
                            passing = [p for p in papers if p['would_pass_filter']]
                            failing = [p for p in papers if not p['would_pass_filter']]

                            st.markdown(f"**Passing filter ({len(passing)}):**")
                            for p in passing[:10]:
                                st.markdown(f"- PMID {p['pmid']}: {p['disease'] or 'N/A'} - {(p['title'] or '')[:80]}...")

                            if failing:
                                st.markdown(f"**Filtered out ({len(failing)}):**")
                                for p in failing[:5]:
                                    reason = p['filter_reason'] or 'No reason given'
                                    st.markdown(f"- PMID {p['pmid']}: {reason[:80]}...")
            else:
                st.info("No paper discoveries found in the database.")

            conn.close()

        except Exception as e:
            st.error(f"Database error: {e}")
            logger.error(f"Database error in History tab: {e}", exc_info=True)
