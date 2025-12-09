"""
Literature Search - Comprehensive Drug Literature Discovery

Universal drug literature discovery with:
- Multi-indication support with disease-based categorization
- Web search integration (bioRxiv, medRxiv, conference abstracts)
- Detailed summaries with structured metadata extraction
- Complete stage categorization (preclinical → post-marketing)
- Ongoing trial discovery
- Direct links to papers
"""
import streamlit as st
import sys
from pathlib import Path
import logging
from datetime import datetime
import json
import pandas as pd
import time

# Add paths
frontend_dir = Path(__file__).parent.parent
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(project_root))

from auth import check_password
from src.agents.paperscope_v2 import PaperScopeV2Agent
from src.tools.pubmed import PubMedAPI
from src.tools.web_search import WebSearchTool
from src.tools.clinicaltrials import ClinicalTrialsAPI
from src.tools.paperscope_v2_database import PaperScopeV2Database
from src.utils.config import get_settings

st.set_page_config(
    page_title="Literature Search",
    page_icon="📚",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()
from anthropic import Anthropic

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Literature Search",
    page_icon="📚",
    layout="wide"
)

st.title("📚 Literature Search")
st.markdown("""
Comprehensive drug literature discovery with advanced features:

**Key Capabilities:**
- 🏥 **Multi-Indication Support**: Automatically discovers all indications and organizes papers by disease
- 🌐 **Web Search**: Finds papers beyond PubMed (bioRxiv, medRxiv, conference abstracts)
- 📝 **Detailed Summaries**: Structured metadata extraction with study design, endpoints, and results
- 🎯 **Complete Categorization**: 23 categories covering all stages (preclinical → post-marketing)
- 🔬 **Ongoing Trials**: Discovers recruiting/active trials from ClinicalTrials.gov
- 🔗 **Direct Links**: Multiple link options (PubMed, PMC, DOI, journal)
- 📊 **Source Tracking**: Understand where papers came from

**How it works:**
1. Enter a drug name (generic name)
2. System searches PubMed + web for ALL papers
3. Claude AI categorizes and summarizes papers
4. Results saved to dedicated database
5. Browse comprehensive paper catalog
""")

st.markdown("---")

# Initialize settings
if "settings" not in st.session_state:
    st.session_state.settings = get_settings()

settings = st.session_state.settings

# Configuration section
with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    
    st.markdown("### API Keys")
    if settings.anthropic_api_key:
        st.success("✓ Anthropic API key configured")
    else:
        st.error("✗ Anthropic API key missing")
    
    if settings.pubmed_api_key:
        st.success("✓ PubMed API key configured")
    else:
        st.warning("⚠ PubMed API key not configured")
    
    if settings.tavily_api_key:
        st.success("✓ Tavily API key configured (web search enabled)")
    else:
        st.warning("⚠ Tavily API key missing (web search disabled)")
    
    st.markdown("---")
    
    st.markdown("### Search Settings")
    max_results = st.number_input(
        "Max results per search",
        min_value=10,
        max_value=500,
        value=100,
        step=10,
        help="Maximum papers to retrieve per PubMed search"
    )
    
    enable_web_search = st.checkbox(
        "Enable web search (Required for trial name discovery)",
        value=True if settings.tavily_api_key else False,
        help="Search beyond PubMed for preprints, conference abstracts, etc. REQUIRED for discovering trial names (TULIP, PSOARING, etc.)",
        disabled=not settings.tavily_api_key
    )

    if not settings.tavily_api_key:
        st.warning("⚠️ Tavily API key not found. Web search disabled. Trial names will not be discovered.")
    elif not enable_web_search:
        st.info("ℹ️ Web search is disabled. Trial names will not be discovered.")
    
    st.markdown("---")
    
    st.markdown("### Cost Estimate")
    st.info(f"""
    **Estimated cost for 500 papers:**
    - Without web search: ~$0.50-0.70
    - With web search: ~$0.80-1.20
    
    **Coverage increase with web search:**
    - +25-30% more papers
    """)

# Main content
tab1, tab2 = st.tabs(["🔍 New Search", "📚 Browse Results"])

with tab1:
    st.markdown("## 🔍 New Search")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        drug_name = st.text_input(
            "Drug Name (Generic)",
            placeholder="e.g., Anifrolumab, Adalimumab, Tofacitinib",
            help="Enter the generic drug name"
        )
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        search_button = st.button("🚀 Start Search", type="primary", use_container_width=True)
    
    if search_button:
        if not drug_name:
            st.error("Please enter a drug name")
        elif not settings.anthropic_api_key:
            st.error("Anthropic API key is required")
        else:
            # Initialize database
            try:
                # Get database URL (try drug_database_url first, then paper_catalog_url)
                database_url = settings.drug_database_url or settings.paper_catalog_url
                if not database_url:
                    st.error("❌ Database URL not found in environment (DRUG_DATABASE_URL or PAPER_CATALOG_URL)")
                    st.stop()

                db = PaperScopeV2Database(database_url)
                db.connect()
                db.create_tables()
            except Exception as e:
                st.error(f"Database connection failed: {e}")
                st.stop()
            
            # Initialize APIs
            try:
                pubmed_api = PubMedAPI(
                    api_key=settings.pubmed_api_key,
                    email="noreply@example.com"
                )
                
                anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
                
                web_search_tool = None
                if enable_web_search and settings.tavily_api_key:
                    web_search_tool = WebSearchTool(api_key=settings.tavily_api_key)
                
                ct_api = ClinicalTrialsAPI()
                
                # Initialize agent
                agent = PaperScopeV2Agent(
                    pubmed_api=pubmed_api,
                    anthropic_client=anthropic_client,
                    web_search_tool=web_search_tool,
                    clinicaltrials_api=ct_api,
                    output_dir="data/paperscope_v2"
                )
                
            except Exception as e:
                st.error(f"Failed to initialize APIs: {e}")
                st.stop()
            
            # Run search
            st.markdown("---")
            st.markdown("### 🔄 Search Progress")
            
            progress_placeholder = st.empty()
            status_placeholder = st.empty()
            
            try:
                with st.spinner("Running comprehensive search..."):
                    start_time = time.time()
                    
                    # Run search
                    results = agent.search_and_categorize(
                        drug_name=drug_name,
                        max_results_per_search=max_results
                    )
                    
                    elapsed = time.time() - start_time
                    
                    # Save to database
                    search_id = db.save_search(drug_name, results)
                    
                    st.success(f"✅ Search completed in {elapsed:.1f} seconds!")
                    
                    # Display summary
                    metadata = results.get('metadata', {})
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Total Papers", metadata.get('total_unique_papers', 0))
                    
                    with col2:
                        st.metric("Ongoing Trials", metadata.get('ongoing_trials_count', 0))
                    
                    with col3:
                        st.metric("Searches Run", metadata.get('total_searches', 0))
                    
                    with col4:
                        st.metric("Time (sec)", f"{elapsed:.1f}")
                    
                    # Paper sources
                    if metadata.get('paper_sources'):
                        st.markdown("### 📊 Paper Sources")
                        sources_df = pd.DataFrame([
                            {"Source": k, "Count": v}
                            for k, v in metadata['paper_sources'].items()
                        ])
                        st.dataframe(sources_df, use_container_width=True)
                    
                    # Disease/Drug class
                    if metadata.get('disease_indication') or metadata.get('drug_class'):
                        st.markdown("### 🎯 Detected Context")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.info(f"**Disease:** {metadata.get('disease_indication', 'Unknown')}")
                        with col2:
                            st.info(f"**Drug Class:** {metadata.get('drug_class', 'Unknown')}")

                    # Discovered trial names
                    discovered_trials = results.get('discovered_trial_names', [])
                    if discovered_trials:
                        st.markdown("### 🔬 Discovered Clinical Trials")
                        st.info(f"**Trial Names:** {', '.join(sorted(discovered_trials))}")

                    # Filtering stats
                    filtered_count = metadata.get('filtered_papers_count', 0)
                    if filtered_count > 0:
                        st.markdown("### 🔍 Quality Filtering")
                        st.warning(f"**Filtered out {filtered_count} papers** not primarily about {drug_name}")

                    st.markdown("---")
                    st.info("💡 Switch to the 'Browse Results' tab to explore the papers!")
                    
            except Exception as e:
                st.error(f"Search failed: {e}")
                logger.exception("Search error")
            
            finally:
                db.close()

with tab2:
    st.markdown("## 📚 Browse Results")

    # Initialize database
    try:
        # Get database URL (try drug_database_url first, then paper_catalog_url)
        database_url = settings.drug_database_url or settings.paper_catalog_url
        if not database_url:
            st.error("❌ Database URL not found in environment (DRUG_DATABASE_URL or PAPER_CATALOG_URL)")
            st.stop()

        db = PaperScopeV2Database(database_url)
        db.connect()
        db.create_tables()
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        st.stop()
    
    try:
        # Get all searches
        searches = db.get_all_searches()
        
        if not searches:
            st.info("No searches found. Run a search in the 'New Search' tab first.")
        else:
            # Select search
            search_options = {
                f"{s['drug_name']} ({s['search_date'].strftime('%Y-%m-%d %H:%M')})": s['search_id']
                for s in searches
            }
            
            selected_search = st.selectbox(
                "Select a search",
                options=list(search_options.keys())
            )
            
            if selected_search:
                search_id = search_options[selected_search]
                search = next(s for s in searches if s['search_id'] == search_id)
                
                # Display search metadata
                st.markdown("### 📊 Search Summary")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Papers", search['total_papers'])
                
                with col2:
                    st.metric("Ongoing Trials", search['total_ongoing_trials'])
                
                with col3:
                    st.metric("Disease", search.get('disease_indication', 'Unknown'))
                
                with col4:
                    st.metric("Drug Class", search.get('drug_class', 'Unknown'))
                
                st.markdown("---")
                
                # Get papers and ongoing trials
                papers = db.get_papers_by_search_id(search_id)
                ongoing_trials = db.get_ongoing_trials_by_search_id(search_id)
                
                # Create tabs for different views
                paper_tab, trial_tab, export_tab = st.tabs(["📄 Papers", "🔬 Ongoing Trials", "💾 Export"])
                
                with paper_tab:
                    if not papers:
                        st.info("No papers found for this search.")
                    else:
                        # Group by disease first, then by category
                        disease_agnostic_categories = {
                            'Preclinical/Mechanistic Studies',
                            'Pharmacokinetics/Pharmacodynamics',
                            'Drug Interactions',
                            'Systematic Reviews/Meta-analyses',
                            'Economic/Cost-effectiveness Studies',
                            'Other'
                        }

                        papers_by_disease = {}
                        disease_agnostic_papers = {}
                        seen_papers = set()  # Track papers by PMID to avoid duplicates

                        for paper in papers:
                            # Skip if already processed (deduplication)
                            pmid = paper.get('pmid')
                            if pmid and pmid in seen_papers:
                                continue
                            if pmid:
                                seen_papers.add(pmid)

                            # Get indication
                            indication = None
                            structured = paper.get('structured_summary')
                            if structured:
                                if isinstance(structured, str):
                                    try:
                                        structured = json.loads(structured)
                                    except:
                                        structured = {}
                                if isinstance(structured, dict):
                                    indication = structured.get('indication')

                            if not indication or indication == 'Unknown':
                                indication = 'Unknown Indication'

                            # Get categories
                            categories = paper.get('categories', [])
                            if isinstance(categories, str):
                                try:
                                    categories = json.loads(categories)
                                except:
                                    categories = [categories]

                            # Use ONLY the PRIMARY (first) category to avoid duplicates
                            primary_category = categories[0] if categories else 'Other'

                            if primary_category in disease_agnostic_categories:
                                # Disease-agnostic
                                if primary_category not in disease_agnostic_papers:
                                    disease_agnostic_papers[primary_category] = []
                                disease_agnostic_papers[primary_category].append(paper)
                            else:
                                # Disease-specific
                                if indication not in papers_by_disease:
                                    papers_by_disease[indication] = {}
                                if primary_category not in papers_by_disease[indication]:
                                    papers_by_disease[indication][primary_category] = []
                                papers_by_disease[indication][primary_category].append(paper)

                        # Display disease-specific papers
                        for disease in sorted(papers_by_disease.keys()):
                            st.markdown(f"## 🏥 {disease}")

                            for category in sorted(papers_by_disease[disease].keys()):
                                papers_in_cat = papers_by_disease[disease][category]
                                with st.expander(f"**{category}** ({len(papers_in_cat)} papers)", expanded=False):
                                    for paper in papers_in_cat:
                                        st.markdown(f"### {paper['title']}")

                                        # Metadata
                                        meta_parts = []
                                        if paper.get('authors'):
                                            meta_parts.append(paper['authors'][:100])
                                        if paper.get('journal'):
                                            meta_parts.append(paper['journal'])
                                        if paper.get('year'):
                                            meta_parts.append(str(paper['year']))

                                        if meta_parts:
                                            st.markdown(f"*{' | '.join(meta_parts)}*")

                                        # Structured summary (if available)
                                        structured = paper.get('structured_summary')
                                        if structured:
                                            if isinstance(structured, str):
                                                try:
                                                    structured = json.loads(structured)
                                                except:
                                                    structured = None

                                            if structured:
                                                # Trial name and indication prominently displayed
                                                trial_indication_parts = []
                                                if structured.get('trial_name'):
                                                    trial_indication_parts.append(f"🔬 **Trial:** {structured['trial_name']}")
                                                elif paper.get('trial_name'):
                                                    trial_indication_parts.append(f"🔬 **Trial:** {paper['trial_name']}")

                                                if structured.get('indication'):
                                                    trial_indication_parts.append(f"🏥 **Indication:** {structured['indication']}")

                                                if trial_indication_parts:
                                                    st.markdown(" | ".join(trial_indication_parts))

                                                # Study details
                                                st.markdown("**📊 Study Details:**")
                                                col1, col2 = st.columns(2)

                                                with col1:
                                                    if structured.get('phase'):
                                                        st.markdown(f"- **Phase:** {structured['phase']}")
                                                    if structured.get('study_design'):
                                                        st.markdown(f"- **Design:** {structured['study_design']}")
                                                    if structured.get('patient_population'):
                                                        st.markdown(f"- **Population:** {structured['patient_population']}")

                                                with col2:
                                                    if structured.get('safety'):
                                                        st.markdown(f"- **Safety:** {structured['safety']}")

                                                # Key results
                                                if structured.get('key_results'):
                                                    results = structured['key_results']
                                                    st.markdown("**📈 Key Results:**")
                                                    if isinstance(results, dict):
                                                        if results.get('primary_endpoint'):
                                                            st.markdown(f"- **Primary:** {results['primary_endpoint']}")
                                                        if results.get('secondary_endpoints'):
                                                            for endpoint in results['secondary_endpoints']:
                                                                st.markdown(f"- **Secondary:** {endpoint}")
                                                    else:
                                                        st.markdown(f"- {results}")

                                                # Narrative summary
                                                if structured.get('narrative_summary'):
                                                    st.markdown(f"**Summary:** {structured['narrative_summary']}")

                                                # Key takeaways from structured summary
                                                if structured.get('takeaways'):
                                                    takeaways = structured['takeaways']
                                                    if isinstance(takeaways, list) and takeaways:
                                                        st.markdown("**Key Takeaways:**")
                                                        for takeaway in takeaways:
                                                            st.markdown(f"- {takeaway}")

                                        else:
                                            # Fallback: Show trial name if no structured summary
                                            if paper.get('trial_name'):
                                                st.markdown(f"🔬 **Trial:** {paper['trial_name']}")

                                            # Fallback: Old detailed summary
                                            if paper.get('detailed_summary'):
                                                st.markdown(f"**Summary:** {paper['detailed_summary']}")

                                            # Fallback: Old key takeaways
                                            if paper.get('key_takeaways'):
                                                takeaways = paper['key_takeaways']
                                                if isinstance(takeaways, str):
                                                    try:
                                                        takeaways = json.loads(takeaways)
                                                    except:
                                                        takeaways = []

                                                if isinstance(takeaways, list) and takeaways:
                                                    st.markdown("**Key Takeaways:**")
                                                    for takeaway in takeaways:
                                                        st.markdown(f"- {takeaway}")

                                        # Links
                                        if paper.get('links'):
                                            links = paper['links']
                                            if isinstance(links, str):
                                                links = json.loads(links)

                                            link_buttons = " | ".join([f"[Link {i+1}]({link})" for i, link in enumerate(links)])
                                            st.markdown(f"**Access:** {link_buttons}")

                                        st.markdown("---")

                        # Display disease-agnostic papers
                        if disease_agnostic_papers:
                            st.markdown("## 📚 Disease-Agnostic Studies")

                            for category in sorted(disease_agnostic_papers.keys()):
                                papers_in_cat = disease_agnostic_papers[category]
                                with st.expander(f"**{category}** ({len(papers_in_cat)} papers)", expanded=False):
                                    for paper in papers_in_cat:
                                        st.markdown(f"### {paper['title']}")

                                        # Metadata
                                        meta_parts = []
                                        if paper.get('authors'):
                                            meta_parts.append(paper['authors'][:100])
                                        if paper.get('journal'):
                                            meta_parts.append(paper['journal'])
                                        if paper.get('year'):
                                            meta_parts.append(str(paper['year']))

                                        if meta_parts:
                                            st.markdown(f"*{' | '.join(meta_parts)}*")

                                        # Structured summary (if available)
                                        structured = paper.get('structured_summary')
                                        if structured:
                                            if isinstance(structured, str):
                                                try:
                                                    structured = json.loads(structured)
                                                except:
                                                    structured = None

                                            if structured:
                                                # Trial name and indication prominently displayed
                                                trial_indication_parts = []
                                                if structured.get('trial_name'):
                                                    trial_indication_parts.append(f"🔬 **Trial:** {structured['trial_name']}")
                                                elif paper.get('trial_name'):
                                                    trial_indication_parts.append(f"🔬 **Trial:** {paper['trial_name']}")

                                                if structured.get('indication'):
                                                    trial_indication_parts.append(f"🏥 **Indication:** {structured['indication']}")

                                                if trial_indication_parts:
                                                    st.markdown(" | ".join(trial_indication_parts))

                                                # Study details
                                                st.markdown("**📊 Study Details:**")
                                                col1, col2 = st.columns(2)

                                                with col1:
                                                    if structured.get('phase'):
                                                        st.markdown(f"- **Phase:** {structured['phase']}")
                                                    if structured.get('study_design'):
                                                        st.markdown(f"- **Design:** {structured['study_design']}")
                                                    if structured.get('patient_population'):
                                                        st.markdown(f"- **Population:** {structured['patient_population']}")

                                                with col2:
                                                    if structured.get('safety'):
                                                        st.markdown(f"- **Safety:** {structured['safety']}")

                                                # Key results
                                                if structured.get('key_results'):
                                                    results = structured['key_results']
                                                    st.markdown("**📈 Key Results:**")
                                                    if isinstance(results, dict):
                                                        if results.get('primary_endpoint'):
                                                            st.markdown(f"- **Primary:** {results['primary_endpoint']}")
                                                        if results.get('secondary_endpoints'):
                                                            for endpoint in results['secondary_endpoints']:
                                                                st.markdown(f"- **Secondary:** {endpoint}")
                                                    else:
                                                        st.markdown(f"- {results}")

                                                # Narrative summary
                                                if structured.get('narrative_summary'):
                                                    st.markdown(f"**Summary:** {structured['narrative_summary']}")

                                                # Key takeaways from structured summary
                                                if structured.get('takeaways'):
                                                    takeaways = structured['takeaways']
                                                    if isinstance(takeaways, list) and takeaways:
                                                        st.markdown("**Key Takeaways:**")
                                                        for takeaway in takeaways:
                                                            st.markdown(f"- {takeaway}")

                                        else:
                                            # Fallback: Show trial name if no structured summary
                                            if paper.get('trial_name'):
                                                st.markdown(f"🔬 **Trial:** {paper['trial_name']}")

                                            # Fallback: Old detailed summary
                                            if paper.get('detailed_summary'):
                                                st.markdown(f"**Summary:** {paper['detailed_summary']}")

                                            # Fallback: Old key takeaways
                                            if paper.get('key_takeaways'):
                                                takeaways = paper['key_takeaways']
                                                if isinstance(takeaways, str):
                                                    try:
                                                        takeaways = json.loads(takeaways)
                                                    except:
                                                        takeaways = []

                                                if isinstance(takeaways, list) and takeaways:
                                                    st.markdown("**Key Takeaways:**")
                                                    for takeaway in takeaways:
                                                        st.markdown(f"- {takeaway}")

                                        # Links
                                        if paper.get('links'):
                                            links = paper['links']
                                            if isinstance(links, str):
                                                links = json.loads(links)

                                            link_buttons = " | ".join([f"[Link {i+1}]({link})" for i, link in enumerate(links)])
                                            st.markdown(f"**Access:** {link_buttons}")

                                        st.markdown("---")

                with trial_tab:
                    if not ongoing_trials:
                        st.info("No ongoing trials found for this search.")
                    else:
                        for trial in ongoing_trials:
                            st.markdown(f"### {trial['title']}")
                            
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                st.markdown(f"**NCT ID:** {trial['nct_id']}")
                                st.markdown(f"**Phase:** {trial.get('phase', 'Unknown')}")
                            
                            with col2:
                                st.markdown(f"**Status:** {trial.get('status', 'Unknown')}")
                                st.markdown(f"**Enrollment:** {trial.get('enrollment', 'N/A')}")
                            
                            with col3:
                                if trial.get('start_date'):
                                    st.markdown(f"**Start:** {trial['start_date']}")
                                if trial.get('completion_date'):
                                    st.markdown(f"**Completion:** {trial['completion_date']}")
                            
                            if trial.get('url'):
                                st.markdown(f"[View on ClinicalTrials.gov]({trial['url']})")
                            
                            st.markdown("---")
                
                with export_tab:
                    st.markdown("### 💾 Export Options")
                    
                    # Export papers as JSON
                    if st.button("Download Papers (JSON)"):
                        papers_json = json.dumps(papers, indent=2, default=str)
                        st.download_button(
                            label="Download JSON",
                            data=papers_json,
                            file_name=f"paperscope_v2_{search['drug_name']}_{datetime.now().strftime('%Y%m%d')}.json",
                            mime="application/json"
                        )
                    
                    # Export as CSV
                    if st.button("Download Papers (CSV)"):
                        papers_df = pd.DataFrame(papers)
                        csv = papers_df.to_csv(index=False)
                        st.download_button(
                            label="Download CSV",
                            data=csv,
                            file_name=f"paperscope_v2_{search['drug_name']}_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )
    
    finally:
        db.close()

