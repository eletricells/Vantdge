"""
Clinical Data Extractor - Extract structured clinical trial data from papers.

This page allows users to:
1. Select drugs from Literature Search (PaperScope v2) results
2. Filter by disease indication (optional)
3. View available papers from PaperScope
4. Select trials to extract
5. Run AI-powered extraction
6. View comparative tables (baseline, efficacy, safety)
7. Export to Excel
"""
import streamlit as st
import sys
from pathlib import Path
import logging
from datetime import datetime
import pandas as pd
import json

# Add paths
frontend_dir = Path(__file__).parent.parent
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(project_root))

from auth import check_password
from src.agents.clinical_data_extractor import ClinicalDataExtractorAgent
from src.tools.clinical_extraction_database import ClinicalExtractionDatabase
from src.utils.config import get_settings
from src.utils.name_standardizer import standardize_disease_name, standardize_drug_name
from anthropic import Anthropic
import psycopg2

st.set_page_config(
    page_title="Clinical Data Extractor",
    page_icon="📊",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Clinical Data Extractor",
    page_icon="🔬",
    layout="wide"
)

st.title("🔬 Clinical Data Extractor")
st.markdown("""
Extract structured clinical trial data from scientific papers collected by PaperScope.

**What this does:**
- Extracts baseline characteristics (demographics, prior medications, disease-specific biomarkers)
- Extracts efficacy endpoints (all timepoints, matched to standard endpoints)
- Extracts safety endpoints (AEs, SAEs, discontinuations)
- Creates comparative tables across multiple trials
- Exports to Excel for further analysis
""")

st.markdown("---")

# Initialize settings
if "settings" not in st.session_state:
    st.session_state.settings = get_settings()

settings = st.session_state.settings

# Initialize session state
if "selected_disease" not in st.session_state:
    st.session_state.selected_disease = None
if "selected_drugs" not in st.session_state:
    st.session_state.selected_drugs = []
if "selected_trials" not in st.session_state:
    st.session_state.selected_trials = []
if "extraction_results" not in st.session_state:
    st.session_state.extraction_results = []
if "show_results" not in st.session_state:
    st.session_state.show_results = False


# Configuration sidebar
with st.sidebar:
    st.markdown("## ⚙️ Configuration")

    st.markdown("### API Keys")
    if settings.anthropic_api_key:
        st.success("✓ Anthropic API key configured")
    else:
        st.error("✗ Anthropic API key missing")

    database_url = settings.drug_database_url or settings.paper_catalog_url
    if database_url:
        st.success("✓ Database configured")
    else:
        st.error("✗ Database not configured")

    st.markdown("---")

    st.markdown("### Extraction Settings")
    use_extended_thinking = st.checkbox(
        "Use Extended Thinking",
        value=True,
        help="Enable extended thinking for complex table interpretation (recommended)"
    )

    confidence_threshold = st.slider(
        "Confidence Threshold",
        min_value=0.0,
        max_value=1.0,
        value=0.7,
        step=0.1,
        help="Minimum confidence for valid extractions"
    )


# ============================================================================
# SECTION 1: DRUG SELECTION (Drug-First Approach)
# ============================================================================

st.markdown("## 1️⃣ Select Drug")
st.markdown("Choose a drug from Literature Search (PaperScope v2) results.")


@st.cache_data(ttl=600)
def get_all_drugs_from_paperscope_v2():
    """Get all drugs from PaperScope v2 database searches."""
    try:
        from src.tools.paperscope_v2_database import PaperScopeV2Database

        database_url = settings.drug_database_url or settings.paper_catalog_url
        if not database_url:
            return []

        db = PaperScopeV2Database(database_url)
        db.connect()

        searches = db.get_all_searches()
        db.close()

        # Extract unique drug names
        drugs = list(set([s.get('drug_name') for s in searches if s.get('drug_name')]))
        return sorted(drugs)

    except Exception as e:
        logger.error(f"Failed to get drugs from PaperScope v2: {e}")
        return []


def get_all_drugs():
    """Get all drugs from PaperScope v2 (Literature Search)."""
    return get_all_drugs_from_paperscope_v2()


drugs = get_all_drugs()

if not drugs:
    st.warning("No drugs found. Please run Literature Search (PaperScope v2) first.")
    st.stop()

selected_drug = st.selectbox(
    "Drug",
    options=drugs,
    index=0 if drugs else None,
    help="Select the drug to analyze"
)

st.info("📄 Source: Literature Search (PaperScope v2)")

st.markdown("---")


# ============================================================================
# SECTION 2: DISEASE FILTER (Optional)
# ============================================================================

st.markdown("## 2️⃣ Filter by Disease (Optional)")
st.markdown(f"Filter papers for **{selected_drug}** by disease indication.")


@st.cache_data(ttl=600)
def get_diseases_for_drug_from_paperscope_v2(drug: str):
    """Get all diseases for a drug from PaperScope v2 database."""
    try:
        from src.tools.paperscope_v2_database import PaperScopeV2Database

        database_url = settings.drug_database_url or settings.paper_catalog_url
        if not database_url:
            return []

        db = PaperScopeV2Database(database_url)
        db.connect()

        # Get all searches for this drug
        searches = db.get_all_searches()
        drug_lower = drug.lower()

        diseases = set()
        for search in searches:
            search_drug = search.get('drug_name', '').lower()
            if drug_lower in search_drug or search_drug in drug_lower:
                search_id = search.get('search_id')
                papers = db.get_papers_by_search_id(search_id)

                # Extract diseases from papers
                for paper in papers:
                    # Get indication from structured summary
                    structured = paper.get('structured_summary')
                    if structured:
                        if isinstance(structured, str):
                            try:
                                structured = json.loads(structured)
                            except:
                                structured = {}
                        if isinstance(structured, dict):
                            indication = structured.get('indication')
                            if indication and indication != 'Unknown':
                                diseases.add(indication)

        db.close()
        return sorted(list(diseases))

    except Exception as e:
        logger.error(f"Failed to get diseases for drug from PaperScope v2: {e}")
        return []


# Get diseases for selected drug
diseases_for_drug = get_diseases_for_drug_from_paperscope_v2(selected_drug)

if diseases_for_drug:
    st.markdown(f"**Found {len(diseases_for_drug)} disease indications for {selected_drug}:**")

    # Add "All Diseases" option
    disease_options = ["All Diseases"] + diseases_for_drug

    selected_disease = st.selectbox(
        "Disease Filter",
        options=disease_options,
        index=0,
        help="Filter papers by disease indication (or select 'All Diseases' to see all papers)"
    )

    # If "All Diseases" selected, set to None for no filtering
    if selected_disease == "All Diseases":
        selected_disease = None
        st.info("📊 Showing papers for all disease indications")
    else:
        st.info(f"📊 Filtering papers for: {selected_disease}")
else:
    st.warning(f"No disease indications found for {selected_drug} in PaperScope v2.")
    selected_disease = None

st.session_state.selected_disease = selected_disease
st.session_state.selected_drugs = [selected_drug]  # Single drug selection

st.markdown("---")


# ============================================================================
# SECTION 3: PAPER AVAILABILITY CHECK
# ============================================================================

st.markdown("## 3️⃣ Check Paper Availability")
st.markdown("Review papers collected by PaperScope.")


@st.cache_data(ttl=600)
def check_paper_availability(disease: str, drugs: list):
    """Check which papers are available from PaperScope v2 database.

    Queries the paperscope_v2_papers table to find papers for each drug.
    """
    available_papers = {}

    try:
        # Connect to PaperScope v2 database
        from src.tools.paperscope_v2_database import PaperScopeV2Database

        database_url = settings.drug_database_url or settings.paper_catalog_url
        if not database_url:
            logger.error("Database URL not found")
            return {drug: 0 for drug in drugs}

        db = PaperScopeV2Database(database_url)
        db.connect()

        # Get all searches
        searches = db.get_all_searches()

        # For each drug, count papers from PaperScope v2
        for drug in drugs:
            paper_count = 0

            # Find searches for this drug (case-insensitive match)
            drug_lower = drug.lower()
            for search in searches:
                search_drug = search.get('drug_name', '').lower()

                # Match if drug name is in search drug name or vice versa
                if drug_lower in search_drug or search_drug in drug_lower:
                    search_id = search.get('search_id')
                    papers = db.get_papers_by_search_id(search_id)

                    # NOTE: We show ALL papers for the drug, not filtered by disease
                    # Reason: PaperScope v2 already categorizes papers by disease,
                    # and users may want to extract data from papers about different indications
                    # The disease selection is just for organizing the workflow, not filtering papers
                    paper_count += len(papers)

            available_papers[drug] = paper_count

        db.close()

    except Exception as e:
        logger.error(f"Failed to check paper availability from PaperScope v2: {e}")
        # Fallback to old file-based system
        available_papers = check_paper_availability_legacy(disease, drugs)

    return available_papers


@st.cache_data(ttl=600)
def check_paper_availability_legacy(disease: str, drugs: list):
    """Legacy: Check papers from file system (PaperScope v1).

    This is a fallback for papers stored in: data/clinical_papers/{drug}/{disease}/
    """
    available_papers = {}

    # Standardize disease name once
    disease_std = standardize_disease_name(disease)
    base_dir = project_root / "data" / "clinical_papers"

    for drug in drugs:
        paper_count = 0

        # Try standardized version of drug name
        drug_std = standardize_drug_name(drug)
        paper_dir = base_dir / drug_std / disease_std

        if paper_dir.exists():
            papers = list(paper_dir.glob("*.json"))
            paper_count = len(papers)
            if paper_count > 0:
                logger.info(f"Found {paper_count} papers for {drug} at {paper_dir}")

        available_papers[drug] = paper_count

    return available_papers


# Use the selected_drugs from session state (set in Section 2)
selected_drugs = st.session_state.selected_drugs

paper_availability = check_paper_availability(selected_disease, selected_drugs)

# Display availability
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.markdown("**Drug**")
with col2:
    st.markdown("**Papers Available**")
with col3:
    st.markdown("**Status**")

for drug in selected_drugs:
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.write(drug)
    with col2:
        st.write(paper_availability.get(drug, 0))
    with col3:
        if paper_availability.get(drug, 0) > 0:
            st.success("✓ Ready")
        else:
            st.error("✗ No papers")

if all(paper_availability.get(drug, 0) == 0 for drug in selected_drugs):
    st.warning("No papers available for selected drugs. Please run PaperScope first.")
    st.stop()

st.markdown("---")


# ============================================================================
# SECTION 4: TRIAL SELECTION (AI-SUGGESTED)
# ============================================================================

st.markdown("## 4️⃣ Select Trials to Extract")
st.markdown("AI will suggest priority trials based on relevance and completeness.")

# Ensure selected_drugs is defined (should be set in Section 2)
if 'selected_drugs' not in st.session_state or not st.session_state.selected_drugs:
    st.error("No drug selected. Please go back to Section 1 and select a drug.")
    st.stop()

selected_drugs = st.session_state.selected_drugs

# Add a button to clear cache and refresh
col1, col2 = st.columns([6, 1])
with col2:
    if st.button("🔄 Refresh", help="Clear cache and reload papers"):
        st.cache_data.clear()
        st.rerun()


@st.cache_data(ttl=600)
def get_available_trials(disease: str, drugs: list):
    """Get all available trials from PaperScope v2 database.

    Queries the paperscope_v2_papers table to find papers for each drug.
    """
    trials = []

    try:
        # Connect to PaperScope v2 database
        from src.tools.paperscope_v2_database import PaperScopeV2Database

        database_url = settings.drug_database_url or settings.paper_catalog_url
        if not database_url:
            logger.error("Database URL not found")
            st.error("Database URL not configured. Please check settings.")
            return get_available_trials_legacy(disease, drugs)

        db = PaperScopeV2Database(database_url)
        db.connect()

        # Get all searches
        searches = db.get_all_searches()
        if searches is None:
            searches = []
        logger.info(f"Found {len(searches)} searches in database")

        # For each drug, get papers from PaperScope v2
        for drug in drugs:
            # Find searches for this drug (case-insensitive match)
            drug_lower = drug.lower()
            logger.info(f"Looking for papers for drug: {drug}")

            for search in searches:
                search_drug = search.get('drug_name', '').lower()

                # Match if drug name is in search drug name or vice versa
                if drug_lower in search_drug or search_drug in drug_lower:
                    search_id = search.get('search_id')
                    papers = db.get_papers_by_search_id(search_id)
                    if papers is None:
                        papers = []
                    logger.info(f"Found {len(papers)} papers for search_id {search_id}")

                    # NOTE: We show ALL papers for the drug, not filtered by disease
                    # Reason: PaperScope v2 already categorizes papers by disease,
                    # and users may want to extract data from papers about different indications
                    # The disease selection is just for organizing the workflow, not filtering papers

                    # Convert papers to trial format
                    papers_processed = 0
                    papers_failed = 0

                    for paper in papers:
                        try:
                            import re

                            # Extract NCT ID from trial_name or search in paper content
                            nct_id = paper.get('trial_name')

                            # Validate that trial_name is actually an NCT ID (starts with NCT + 8 digits)
                            if nct_id and not re.match(r'^NCT\d{8}$', str(nct_id)):
                                nct_id = None  # Invalid format, will search in content

                            # If no valid NCT ID in trial_name, search in paper content
                            if not nct_id:
                                content = paper.get('content') or ''  # Handle None content
                                # Search for NCT ID in first 5000 characters
                                nct_matches = re.findall(r'NCT\d{8}', content[:5000])
                                if nct_matches:
                                    nct_id = nct_matches[0]  # Use first occurrence
                                else:
                                    # No NCT ID found - use PMID with prefix to indicate it's not an NCT ID
                                    pmid = paper.get('pmid')
                                    if pmid:
                                        nct_id = f"PMID_{pmid}"
                                    else:
                                        nct_id = f"PAPER_{paper.get('paper_id', 'unknown')}"

                            # Get title
                            title = paper.get('title', 'Unknown')
                            if not title or title == 'Unknown':
                                title = f"[Paper ID: {paper.get('paper_id', 'unknown')}]"

                            # Calculate priority with error handling
                            try:
                                priority = calculate_priority_v2(paper)
                            except Exception as priority_error:
                                logger.error(f"Error calculating priority for paper {paper.get('paper_id')}: {priority_error}")
                                priority = 0.5  # Default priority

                            trials.append({
                                'nct_id': str(nct_id),
                                'drug': drug,
                                'title': title,
                                'pmid': paper.get('pmid', 'Unknown'),
                                'paper_data': paper,  # Store full paper data for extraction
                                'priority': priority  # AI scoring
                            })
                            papers_processed += 1

                        except Exception as paper_error:
                            papers_failed += 1
                            logger.error(f"Error processing paper {paper.get('paper_id', 'unknown')}: {paper_error}")
                            import traceback
                            logger.error(traceback.format_exc())
                            continue

                    logger.info(f"Processed {papers_processed}/{len(papers)} papers for search_id {search_id} ({papers_failed} failed)")

        db.close()
        logger.info(f"Total trials found: {len(trials)}")

    except Exception as e:
        logger.error(f"Failed to get trials from PaperScope v2: {e}")
        import traceback
        logger.error(traceback.format_exc())
        st.error(f"Error loading papers from PaperScope v2: {e}")
        # Fallback to legacy file-based system
        trials = get_available_trials_legacy(disease, drugs)

    # Sort by priority (highest first)
    trials = sorted(trials, key=lambda x: x['priority'], reverse=True)

    return trials


@st.cache_data(ttl=600)
def get_available_trials_legacy(disease: str, drugs: list):
    """Legacy: Get trials from file system (PaperScope v1).

    This is a fallback for papers stored in: data/clinical_papers/{drug}/{disease}/
    """
    trials = []

    # Standardize disease name once
    disease_std = standardize_disease_name(disease)
    base_dir = project_root / "data" / "clinical_papers"

    for drug in drugs:
        # Try standardized version of drug name
        drug_std = standardize_drug_name(drug)
        paper_dir = base_dir / drug_std / disease_std

        if not paper_dir.exists():
            continue

        for paper_file in paper_dir.glob("*.json"):
            try:
                with open(paper_file, 'r', encoding='utf-8') as f:
                    paper = json.load(f)

                # Extract NCT ID from paper metadata, PMID as fallback, then filename
                nct_id = paper.get('nct_id') or paper.get('pmid') or paper_file.stem

                # Get title and handle incomplete titles
                title = paper.get('title', 'Unknown')
                if not title or title == 'Unknown':
                    # Use filename as fallback
                    title = f"[Paper: {paper_file.stem}]"
                elif len(title) < 20 and title.endswith(','):
                    # Likely incomplete title - add indicator
                    title = f"{title} [Incomplete - PMID: {paper.get('pmid', 'Unknown')}]"

                trials.append({
                    'nct_id': str(nct_id) if nct_id else paper_file.stem,
                    'drug': drug,  # Use the original drug name from UI
                    'title': title,
                    'pmid': paper.get('pmid', 'Unknown'),
                    'paper_file': str(paper_file),
                    'priority': calculate_priority(paper)  # AI scoring
                })
            except Exception as e:
                logger.warning(f"Failed to load paper {paper_file}: {e}")
                continue

    return trials


def calculate_priority_v2(paper: dict) -> float:
    """
    Calculate priority score for a PaperScope v2 paper.

    Heuristics:
    - Phase 3 trials: +0.3
    - Recent publications: +0.2
    - Has full-text content: +0.2
    - Has tables: +0.1
    - Long content: +0.1
    """
    score = 0.5  # Base score

    # Check categories for phase information
    categories = paper.get('categories', [])
    if categories is None:
        categories = []

    if isinstance(categories, list) and len(categories) > 0:
        category_text = ' '.join(str(c) for c in categories).lower()
        if 'phase 3' in category_text or 'phase iii' in category_text:
            score += 0.3
        elif 'phase 2' in category_text or 'phase ii' in category_text:
            score += 0.2
        elif 'phase 1' in category_text or 'phase i' in category_text:
            score += 0.1

    # Check year (convert to int if string)
    year = paper.get('year', 0)
    if isinstance(year, str):
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = 0

    if year >= 2020:
        score += 0.2
    elif year >= 2015:
        score += 0.1

    # Check has full-text content
    content = paper.get('content') or ''  # Handle None content
    if content:
        score += 0.2

    # Check has tables
    tables = paper.get('tables', [])
    if tables and len(tables) > 0:
        score += 0.1

    # Check content length (indicates completeness)
    if content and len(content) > 30000:  # Check content is not None before len()
        score += 0.1

    return min(score, 1.0)


def calculate_priority(paper: dict) -> float:
    """
    Calculate priority score for a legacy PaperScope v1 paper.

    Heuristics:
    - Phase 3 trials: +0.3
    - Recent publications: +0.2
    - Has tables: +0.2
    - Long content: +0.1
    """
    score = 0.5  # Base score

    # Check phase
    content = paper.get('content', '').lower()
    if 'phase 3' in content or 'phase iii' in content:
        score += 0.3
    elif 'phase 2' in content or 'phase ii' in content:
        score += 0.2

    # Check year (convert to int if string)
    year = paper.get('year', 0)
    if isinstance(year, str):
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = 0

    if year >= 2020:
        score += 0.2
    elif year >= 2015:
        score += 0.1

    # Check has tables
    if 'table' in content:
        score += 0.2

    # Check content length (indicates completeness)
    if len(content) > 30000:
        score += 0.1

    return min(score, 1.0)


trials = get_available_trials(selected_disease, selected_drugs)

if not trials:
    st.warning("No trials found in PaperScope papers.")
    st.stop()

st.markdown(f"**Found {len(trials)} papers. AI-suggested priorities shown below:**")
logger.info(f"Displaying {len(trials)} trials for {selected_drugs}")

# Add legend for content availability badges
st.info("**Legend:** 📄 Full Text = Complete paper content available | 📊 Tables = Extracted tables available | ⚠️ PDF Upload Required = Only abstract available, upload PDF for full extraction")

# Add Select All / Unselect All buttons
col_btn1, col_btn2, col_spacer = st.columns([1, 1, 4])
with col_btn1:
    if st.button("✓ Select All", use_container_width=True, key="btn_select_all_trials"):
        # Update all trial checkbox states directly
        for idx, trial in enumerate(trials):
            nct_id_safe = trial.get('nct_id') or f'unknown_{idx}'
            trial_key = f"trial_{idx}_{nct_id_safe}"
            st.session_state[trial_key] = True
with col_btn2:
    if st.button("✗ Unselect All", use_container_width=True, key="btn_unselect_all_trials"):
        # Update all trial checkbox states directly
        for idx, trial in enumerate(trials):
            nct_id_safe = trial.get('nct_id') or f'unknown_{idx}'
            trial_key = f"trial_{idx}_{nct_id_safe}"
            st.session_state[trial_key] = False

# Organize papers by disease and category (like PaperScope v2)
disease_agnostic_categories = {
    'Mechanism of Action Studies',
    'Pharmacokinetics/Pharmacodynamics',
    'Drug-Drug Interaction Studies',
    'Biomarker Studies',
    'Systematic Reviews/Meta-analyses',
    'Economic/Cost-effectiveness Studies',
    'Other'
}

papers_by_disease = {}
disease_agnostic_papers = {}
trial_selection = {}

for idx, trial in enumerate(trials):
    paper = trial.get('paper_data', {})

    # Get indication from structured summary
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
    if categories is None:
        categories = []
    elif isinstance(categories, str):
        try:
            categories = json.loads(categories)
        except:
            categories = [categories]

    # Ensure categories is a list
    if not isinstance(categories, list):
        categories = []

    # Use ONLY the PRIMARY (first) category
    primary_category = categories[0] if categories and len(categories) > 0 else 'Other'

    # Organize by disease or disease-agnostic
    if primary_category in disease_agnostic_categories:
        if primary_category not in disease_agnostic_papers:
            disease_agnostic_papers[primary_category] = []
        disease_agnostic_papers[primary_category].append((idx, trial))
    else:
        if indication not in papers_by_disease:
            papers_by_disease[indication] = {}
        if primary_category not in papers_by_disease[indication]:
            papers_by_disease[indication][primary_category] = []
        papers_by_disease[indication][primary_category].append((idx, trial))

# Display papers organized by disease and category
st.markdown("---")

# Debug logging
logger.info(f"Papers by disease: {list(papers_by_disease.keys())}")
logger.info(f"Disease-agnostic papers: {list(disease_agnostic_papers.keys())}")
logger.info(f"Total papers organized: {sum(len(cats) for disease_cats in papers_by_disease.values() for cats in disease_cats.values())} disease-specific + {sum(len(papers) for papers in disease_agnostic_papers.values())} disease-agnostic")

# Display disease-specific papers
for disease in sorted(papers_by_disease.keys()):
    st.markdown(f"### 🏥 {disease}")

    for category in sorted(papers_by_disease[disease].keys()):
        papers_in_cat = papers_by_disease[disease][category]

        with st.expander(f"**{category}** ({len(papers_in_cat)} papers)", expanded=True):
            for idx, trial in papers_in_cat:
                col1, col2, col3, col4 = st.columns([0.5, 3, 1, 1])

                with col1:
                    nct_id_safe = trial.get('nct_id') or f'unknown_{idx}'
                    trial_key = f"trial_{idx}_{nct_id_safe}"
                    default_value = trial['priority'] > 0.7

                    trial_selection[idx] = st.checkbox(
                        "Select",
                        value=st.session_state.get(trial_key, default_value),
                        key=trial_key,
                        label_visibility="collapsed"
                    )

                with col2:
                    title = trial['title']

                    # Check content availability
                    paper = trial.get('paper_data', {})
                    has_content = bool(paper.get('content'))
                    has_tables = bool(paper.get('tables'))

                    # Add badges for content availability
                    badges = []
                    if has_content:
                        badges.append("📄 Full Text")
                    if has_tables:
                        badges.append("📊 Tables")
                    if not has_content and not has_tables:
                        badges.append("⚠️ PDF Upload Required")

                    badge_str = " ".join(badges)
                    st.markdown(f"**{title}** {badge_str}")

                    # Show metadata
                    meta_parts = []
                    if paper.get('authors'):
                        meta_parts.append(paper['authors'][:100])
                    if paper.get('journal'):
                        meta_parts.append(paper['journal'])
                    if paper.get('year'):
                        meta_parts.append(str(paper['year']))

                    if meta_parts:
                        st.markdown(f"*{' | '.join(meta_parts)}*")

                with col3:
                    nct_id_display = trial.get('nct_id', 'Unknown')
                    if nct_id_display.isdigit() and len(nct_id_display) == 8:
                        st.write(f"PMID:{nct_id_display}")
                    else:
                        st.write(nct_id_display)

                with col4:
                    if trial['priority'] > 0.7:
                        st.success(f"{trial['priority']:.2f}")
                    elif trial['priority'] > 0.5:
                        st.info(f"{trial['priority']:.2f}")
                    else:
                        st.warning(f"{trial['priority']:.2f}")

# Display disease-agnostic papers
if disease_agnostic_papers:
    st.markdown("### 📚 Disease-Agnostic Studies")

    for category in sorted(disease_agnostic_papers.keys()):
        papers_in_cat = disease_agnostic_papers[category]

        with st.expander(f"**{category}** ({len(papers_in_cat)} papers)", expanded=False):
            for idx, trial in papers_in_cat:
                col1, col2, col3, col4 = st.columns([0.5, 3, 1, 1])

                with col1:
                    nct_id_safe = trial.get('nct_id') or f'unknown_{idx}'
                    trial_key = f"trial_{idx}_{nct_id_safe}"
                    default_value = trial['priority'] > 0.7

                    trial_selection[idx] = st.checkbox(
                        "Select",
                        value=st.session_state.get(trial_key, default_value),
                        key=trial_key,
                        label_visibility="collapsed"
                    )

                with col2:
                    title = trial['title']

                    # Check content availability
                    paper = trial.get('paper_data', {})
                    has_content = bool(paper.get('content'))
                    has_tables = bool(paper.get('tables'))

                    # Add badges for content availability
                    badges = []
                    if has_content:
                        badges.append("📄 Full Text")
                    if has_tables:
                        badges.append("📊 Tables")
                    if not has_content and not has_tables:
                        badges.append("⚠️ PDF Upload Required")

                    badge_str = " ".join(badges)
                    st.markdown(f"**{title}** {badge_str}")

                    # Show metadata
                    meta_parts = []
                    if paper.get('authors'):
                        meta_parts.append(paper['authors'][:100])
                    if paper.get('journal'):
                        meta_parts.append(paper['journal'])
                    if paper.get('year'):
                        meta_parts.append(str(paper['year']))

                    if meta_parts:
                        st.markdown(f"*{' | '.join(meta_parts)}*")

                with col3:
                    nct_id_display = trial.get('nct_id', 'Unknown')
                    if nct_id_display.isdigit() and len(nct_id_display) == 8:
                        st.write(f"PMID:{nct_id_display}")
                    else:
                        st.write(nct_id_display)

                with col4:
                    if trial['priority'] > 0.7:
                        st.success(f"{trial['priority']:.2f}")
                    elif trial['priority'] > 0.5:
                        st.info(f"{trial['priority']:.2f}")
                    else:
                        st.warning(f"{trial['priority']:.2f}")

# Get selected trials by index
selected_trial_indices = [idx for idx, selected in trial_selection.items() if selected]
st.session_state.selected_trials = [trials[idx] for idx in selected_trial_indices]

if not selected_trial_indices:
    st.info("Please select at least one trial to extract.")
    st.stop()

st.success(f"✓ Selected {len(selected_trial_indices)} trials for extraction")

st.markdown("---")


# ============================================================================
# SECTION 4.5: PDF UPLOAD FOR PAPERS WITHOUT FULL TEXT
# ============================================================================

st.markdown("## 📤 Upload PDFs (Optional)")
st.markdown("Upload PDFs for papers that don't have full-text content available.")

# Check which selected papers need PDFs
selected_trials = [trials[idx] for idx in selected_trial_indices]
papers_needing_pdf = []
papers_with_content = []

for trial in selected_trials:
    paper = trial.get('paper_data', {})
    has_content = bool(paper.get('content'))
    has_tables = bool(paper.get('tables'))

    if not has_content and not has_tables:
        papers_needing_pdf.append(trial)
    else:
        papers_with_content.append(trial)

if papers_needing_pdf:
    st.warning(f"⚠️ {len(papers_needing_pdf)} of your selected papers need PDF uploads for full extraction:")

    with st.expander(f"📋 Papers Needing PDFs ({len(papers_needing_pdf)})", expanded=True):
        for i, trial in enumerate(papers_needing_pdf, 1):
            paper = trial.get('paper_data', {})
            st.markdown(f"**{i}. {trial['title']}**")

            # Show metadata
            meta_parts = []
            if paper.get('pmid'):
                meta_parts.append(f"PMID: {paper['pmid']}")
            if paper.get('journal'):
                meta_parts.append(paper['journal'])
            if paper.get('year'):
                meta_parts.append(str(paper['year']))

            if meta_parts:
                st.caption(" | ".join(meta_parts))

            # PDF uploader for this specific paper
            pmid = paper.get('pmid', f'paper_{i}')
            uploaded_file = st.file_uploader(
                f"Upload PDF for: {trial['title'][:50]}...",
                type=['pdf'],
                key=f"pdf_upload_{pmid}_{i}",
                help=f"Upload the full-text PDF for this paper"
            )

            if uploaded_file:
                # Save uploaded PDF and process it
                import tempfile
                from pathlib import Path

                # Create temp file
                temp_dir = Path("data/uploaded_papers")
                temp_dir.mkdir(parents=True, exist_ok=True)

                temp_path = temp_dir / f"{pmid}_{uploaded_file.name}"
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                st.success(f"✓ PDF uploaded: {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")

                # Store the uploaded PDF path in the trial data
                trial['uploaded_pdf_path'] = str(temp_path)

                # Use full PaperScope extraction pipeline (text + sections + tables + header recovery)
                try:
                    from src.agents.clinical_data_collector import ClinicalDataCollectorAgent
                    from src.tools.clinicaltrials import ClinicalTrialsAPI
                    from src.tools.pubmed import PubMedAPI
                    from src.tools.web_search import WebSearchTool
                    from anthropic import Anthropic

                    # Initialize collector with full extraction pipeline
                    ct_api = ClinicalTrialsAPI()
                    pubmed_api = PubMedAPI(api_key=settings.pubmed_api_key)
                    web_search = WebSearchTool(api_key=settings.tavily_api_key)
                    client = Anthropic(api_key=settings.anthropic_api_key)

                    collector = ClinicalDataCollectorAgent(
                        clinicaltrials_tool=ct_api,
                        pubmed_tool=pubmed_api,
                        web_search_tool=web_search,
                        client=client,
                        enable_header_recovery=True  # Enable AI-powered header recovery
                    )

                    # Prepare metadata for extraction
                    extraction_metadata = {
                        'pmid': paper.get('pmid'),
                        'title': trial['title'],
                        'authors': paper.get('authors', []),
                        'journal': paper.get('journal', 'Unknown'),
                        'publication_date': str(paper.get('year', 'Unknown')),
                        'doi': paper.get('doi'),
                        'drug': selected_drug,
                        'indication': selected_disease if selected_disease != "All Diseases" else "Unknown"
                    }

                    # Process PDF using full PaperScope pipeline
                    with st.spinner("🔄 Processing PDF (extracting text, sections, tables, and recovering headers)..."):
                        json_path = collector._pdf_to_json(str(temp_path), extraction_metadata)

                        # Load processed data
                        with open(json_path, 'r', encoding='utf-8') as f:
                            processed_data = json.load(f)

                        # Update paper data with full structured extraction
                        paper['content'] = processed_data.get('content', '')
                        paper['sections'] = processed_data.get('sections', {})
                        paper['tables'] = processed_data.get('tables', [])
                        paper['metadata'] = processed_data.get('metadata', {})
                        paper['source'] = 'pdf_upload'

                        # Add PDF path to metadata
                        if 'metadata' not in paper or paper['metadata'] is None:
                            paper['metadata'] = {}
                        paper['metadata']['uploaded_pdf_path'] = str(temp_path)
                        paper['metadata']['pdf_filename'] = uploaded_file.name

                        # Save extracted content to database for persistence
                        from src.tools.paperscope_v2_database import PaperScopeV2Database
                        database_url = settings.drug_database_url or settings.paper_catalog_url
                        db = PaperScopeV2Database(database_url)
                        db.connect()
                        try:
                            paper_id = paper.get('paper_id')
                            if paper_id:
                                success = db.update_paper_content(
                                    paper_id=paper_id,
                                    content=paper['content'],
                                    tables=paper['tables'],
                                    sections=paper['sections'],
                                    metadata=paper['metadata']
                                )
                                if success:
                                    logger.info(f"✓ Saved extracted content to database for paper_id {paper_id}")
                                    st.success("💾 Content saved to database - will persist across sessions!")

                                    # Clear cache so UI reflects the updated paper
                                    st.cache_data.clear()
                                else:
                                    logger.warning(f"⚠ Failed to save content to database for paper_id {paper_id}")
                                    st.warning("⚠️ Content extracted but not saved to database")
                            else:
                                logger.warning("⚠ No paper_id found, cannot save to database")
                                st.warning("⚠️ No paper_id found - content will not persist")
                        except Exception as db_error:
                            logger.error(f"Error saving to database: {db_error}")
                            st.error(f"❌ Error saving to database: {db_error}")
                        finally:
                            db.close()

                        # Clean up temp JSON (with retry for Windows file locking)
                        import time
                        for attempt in range(3):
                            try:
                                Path(json_path).unlink(missing_ok=True)
                                break
                            except PermissionError:
                                if attempt < 2:
                                    time.sleep(0.5)  # Wait 500ms before retry
                                else:
                                    # If still locked after 3 attempts, just log it
                                    logger.warning(f"Could not delete temp file {json_path} (file locked)")

                    # Show extraction results
                    st.success(f"✓ Extraction complete!")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Text", f"{len(paper['content']):,} chars")
                    with col2:
                        st.metric("Sections", len(paper.get('sections', {})))
                    with col3:
                        st.metric("Tables", len(paper.get('tables', [])))

                    # Show extraction method
                    extraction_method = paper.get('metadata', {}).get('extraction_method', 'Unknown')
                    st.caption(f"📋 Extraction: {extraction_method}")

                except Exception as e:
                    st.error(f"Failed to process PDF: {e}")
                    import traceback
                    st.error(traceback.format_exc())

            st.markdown("---")

    if len(papers_needing_pdf) > 0:
        st.info("💡 **Tip:** You can proceed without uploading PDFs, but extraction will be limited to abstract data only.")
else:
    st.success(f"✓ All {len(papers_with_content)} selected papers have full-text content available!")

st.markdown("---")


# ============================================================================
# SECTION 5: RUN EXTRACTION
# ============================================================================

st.markdown("## 5️⃣ Extract Clinical Data")

if st.button("🚀 Run Extraction", type="primary"):
    if not settings.anthropic_api_key:
        st.error("Anthropic API key required for extraction")
        st.stop()

    database_url = settings.drug_database_url or settings.paper_catalog_url
    if not database_url:
        st.error("Database connection required")
        st.stop()

    # Initialize agent and database
    client = Anthropic(api_key=settings.anthropic_api_key)
    agent = ClinicalDataExtractorAgent(client, strict_validation=True)

    try:
        db = ClinicalExtractionDatabase(database_url)
        db.connect()

        # Get standard endpoints for this indication
        # If "All Diseases" is selected (None), try to infer disease from paper categories
        disease_for_endpoints = selected_disease
        if selected_disease is None:  # "All Diseases" was selected
            # Try to get disease from first selected trial's paper structured_summary
            if st.session_state.selected_trials:
                first_trial = st.session_state.selected_trials[0]
                paper = first_trial.get('paper_data', {})

                # Get indication from structured_summary
                structured = paper.get('structured_summary')
                if structured:
                    if isinstance(structured, str):
                        try:
                            structured = json.loads(structured)
                        except:
                            structured = {}
                    if isinstance(structured, dict):
                        indication = structured.get('indication')
                        if indication and indication != 'Unknown':
                            disease_for_endpoints = indication
                            st.info(f"ℹ️ Using disease '{disease_for_endpoints}' from paper indication for endpoint matching")

                # If still no disease found, set to Unknown
                if not disease_for_endpoints:
                    disease_for_endpoints = "Unknown"
                    st.warning("⚠️ No disease indication found in papers. Extraction will proceed without disease-specific endpoints.")

        standard_endpoints = db.get_standard_endpoints(disease_for_endpoints) if disease_for_endpoints != "Unknown" else []

        st.info(f"Found {len(standard_endpoints)} standard clinical endpoints for {disease_for_endpoints}")

        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()

        all_extractions = []

        # Extract each selected trial
        for i, trial in enumerate(st.session_state.selected_trials):
            status_text.text(f"Extracting {trial['nct_id']} ({i+1}/{len(st.session_state.selected_trials)})...")
            progress_bar.progress((i) / len(st.session_state.selected_trials))

            # Load paper (from database or file)
            if 'paper_data' in trial:
                # PaperScope v2: paper data is already in the trial dict
                paper = trial['paper_data']
            elif 'paper_file' in trial:
                # Legacy PaperScope v1: load from file
                with open(trial['paper_file'], 'r', encoding='utf-8') as f:
                    paper = json.load(f)
            else:
                st.error(f"No paper data found for trial {trial['nct_id']}")
                continue

            # Extract data
            try:
                # Use disease_for_endpoints (which was inferred from paper if needed) instead of selected_disease
                trial_design, extractions = agent.extract_trial_data(
                    paper=paper,
                    nct_id=trial['nct_id'],
                    drug_name=trial['drug'],
                    indication=disease_for_endpoints if disease_for_endpoints != "Unknown" else selected_disease,
                    standard_endpoints=standard_endpoints
                )


                # Save trial design to MCP database
                try:
                    from src.tools.trial_design_database import TrialDesignDatabase
                    trial_design_db = TrialDesignDatabase(database_url)
                    trial_design_db.connect()
                    trial_design_db.save_trial_design(trial_design)
                    trial_design_db.close()
                    logger.info(f"Saved trial design for {trial['nct_id']}")
                except Exception as e:
                    logger.warning(f"Failed to save trial design: {e}")

                # Save to database with graceful error handling
                for extraction in extractions:
                    result = db.save_extraction_gracefully(extraction)
                    all_extractions.append((extraction, result))

                    # Display detailed results for this arm
                    with st.expander(f"📊 {extraction.arm_name} - Extraction Details"):
                        col1, col2, col3, col4 = st.columns(4)

                        with col1:
                            if result['trial_metadata']['success']:
                                st.success("✓ Metadata")
                                st.caption(f"ID: {result['trial_metadata']['extraction_id']}")
                            else:
                                st.error("✗ Metadata")

                        with col2:
                            if result['baseline']['success']:
                                st.success("✓ Baseline")
                                st.caption(f"{result['baseline']['fields_saved']} fields")
                            elif result['baseline']['error']:
                                st.error("✗ Baseline")
                                with st.popover("Error"):
                                    st.code(result['baseline']['error'], language="text")

                        with col3:
                            if result['efficacy']['success']:
                                st.success("✓ Efficacy")
                                st.caption(f"{result['efficacy']['count']} endpoints")
                            elif result['efficacy']['error']:
                                st.error("✗ Efficacy")
                                with st.popover("Error"):
                                    st.code(result['efficacy']['error'], language="text")

                        with col4:
                            if result['safety']['success']:
                                st.success("✓ Safety")
                                st.caption(f"{result['safety']['count']} endpoints")
                            elif result['safety']['error']:
                                st.error("✗ Safety")
                                with st.popover("Error"):
                                    st.code(result['safety']['error'], language="text")

                        # Show overall status
                        if result['overall_success']:
                            st.info(f"✓ Overall: Successfully saved {len([s for s in ['trial_metadata', 'baseline', 'efficacy', 'safety'] if result[s]['success']])}/4 sections")
                        else:
                            st.warning("⚠ Partial save - some sections failed")

                st.success(f"✓ Processed {len(extractions)} arms from {trial['nct_id']}")

            except Exception as e:
                logger.error(f"Failed to extract {trial['nct_id']}: {e}")
                st.error(f"✗ Failed to extract {trial['nct_id']}: {str(e)}")
                continue

        progress_bar.progress(1.0)
        status_text.text("✓ Extraction complete!")

        # Show comprehensive error summary
        all_errors = []
        total_sections_saved = 0
        total_sections_attempted = 0

        for extraction, result in all_extractions:
            for section in ['trial_metadata', 'baseline', 'efficacy', 'safety']:
                total_sections_attempted += 1
                if result[section]['success']:
                    total_sections_saved += 1

            if result.get('errors'):
                all_errors.extend(result['errors'])

        # Display overall statistics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Trial Arms", len(all_extractions))
        with col2:
            st.metric("Sections Saved", f"{total_sections_saved}/{total_sections_attempted}")
        with col3:
            success_rate = (total_sections_saved / total_sections_attempted * 100) if total_sections_attempted > 0 else 0
            st.metric("Success Rate", f"{success_rate:.1f}%")

        # Show error summary if there were any errors
        if all_errors:
            with st.expander(f"⚠ Error Summary ({len(all_errors)} errors)", expanded=False):
                # Group errors by missing column
                missing_columns = {}
                for error in all_errors:
                    if error.get('missing_column'):
                        col = error['missing_column']
                        if col not in missing_columns:
                            missing_columns[col] = {
                                'count': 0,
                                'sections': set(),
                                'trials': set()
                            }
                        missing_columns[col]['count'] += 1
                        missing_columns[col]['sections'].add(error['section'])
                        missing_columns[col]['trials'].add(error['nct_id'])

                if missing_columns:
                    st.subheader("Missing Database Columns")
                    st.info("These columns need to be added to the database schema:")

                    for col, info in sorted(missing_columns.items(), key=lambda x: x[1]['count'], reverse=True):
                        sections_str = ", ".join(info['sections'])
                        trials_str = ", ".join(info['trials'])

                        st.code(f"# Column: {col}\n"
                               f"# Affected sections: {sections_str}\n"
                               f"# Trials affected: {trials_str}\n"
                               f"# Occurrences: {info['count']}\n\n"
                               f"# Migration command:\n"
                               f"ALTER TABLE trial_{list(info['sections'])[0]} ADD COLUMN {col} VARCHAR(100);",
                               language="sql")

                # Show all errors
                st.subheader("All Errors")
                for idx, error in enumerate(all_errors, 1):
                    with st.container():
                        st.markdown(f"**Error {idx}**: {error['section']} - {error['nct_id']}")
                        st.code(error['error_message'], language="text")

        st.session_state.extraction_results = all_extractions
        st.session_state.show_results = True

        if all_errors:
            st.warning(f"⚠ Extraction completed with {len(all_errors)} errors. Check summary above.")
        else:
            st.success(f"✓ Successfully extracted {len(all_extractions)} trial arms with no errors!")

        db.close()

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        st.error(f"Extraction failed: {str(e)}")
        if db:
            db.close()


st.markdown("---")


# ============================================================================
# SECTION 6: VIEW COMPARATIVE TABLES
# ============================================================================

if st.button("📊 Load Existing Data"):
    st.session_state.show_results = True

if st.session_state.show_results:
    st.markdown("## 6️⃣ Comparative Analysis")

    # Ensure selected_drugs is defined
    if 'selected_drugs' not in st.session_state or not st.session_state.selected_drugs:
        st.error("No drug selected. Please go back to Section 1 and select a drug.")
        st.stop()

    selected_drugs = st.session_state.selected_drugs
    selected_disease = st.session_state.selected_disease

    database_url = settings.drug_database_url or settings.paper_catalog_url
    try:
        db = ClinicalExtractionDatabase(database_url)
        db.connect()

        # Get data from database
        baseline_df = db.get_baseline_comparison(selected_disease, selected_drugs)
        efficacy_df = db.get_efficacy_comparison(selected_disease, selected_drugs)
        safety_df = db.get_safety_comparison(selected_disease, selected_drugs)
        extractions = db.get_extractions_by_indication(selected_disease, selected_drugs)

        # Clean extraction data to remove JSON columns that can't be serialized
        cleaned_extractions = []
        for ext in extractions:
            cleaned_ext = {}
            for key, value in ext.items():
                # Skip JSON columns and other non-serializable types
                if key in ['primary_efficacy', 'safety_summary']:
                    continue
                # Convert datetime objects to strings
                if hasattr(value, 'isoformat'):
                    cleaned_ext[key] = value.isoformat()
                else:
                    cleaned_ext[key] = value
            cleaned_extractions.append(cleaned_ext)

        extractions = cleaned_extractions

        # Display tabs
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 Baseline", "📈 Efficacy", "⚠️ Safety", "📐 Trial Design", "🔍 Data Quality"])

        with tab1:
            st.markdown("### Baseline Characteristics Comparison")
            if not baseline_df.empty:
                # Add filters
                col1, col2 = st.columns(2)
                with col1:
                    characteristic_filter = st.multiselect(
                        "Filter by Characteristic",
                        options=baseline_df['characteristic_name'].unique() if not baseline_df.empty else [],
                        default=[]
                    )
                with col2:
                    category_filter = st.multiselect(
                        "Filter by Category",
                        options=baseline_df['characteristic_category'].unique() if not baseline_df.empty else [],
                        default=[]
                    )

                # Apply filters
                filtered_baseline_df = baseline_df.copy()
                if characteristic_filter:
                    filtered_baseline_df = filtered_baseline_df[filtered_baseline_df['characteristic_name'].isin(characteristic_filter)]
                if category_filter:
                    filtered_baseline_df = filtered_baseline_df[filtered_baseline_df['characteristic_category'].isin(category_filter)]

                st.dataframe(filtered_baseline_df, use_container_width=True)
            else:
                st.info("No baseline data available")

        with tab2:
            st.markdown("### Efficacy Endpoints Comparison")
            if not efficacy_df.empty:
                # Add filters
                col1, col2 = st.columns(2)
                with col1:
                    endpoint_filter = st.multiselect(
                        "Filter by Endpoint",
                        options=efficacy_df['endpoint_name'].unique() if not efficacy_df.empty else [],
                        default=[]
                    )
                with col2:
                    timepoint_filter = st.multiselect(
                        "Filter by Timepoint",
                        options=efficacy_df['timepoint'].unique() if not efficacy_df.empty else [],
                        default=[]
                    )

                # Apply filters
                filtered_df = efficacy_df.copy()
                if endpoint_filter:
                    filtered_df = filtered_df[filtered_df['endpoint_name'].isin(endpoint_filter)]
                if timepoint_filter:
                    filtered_df = filtered_df[filtered_df['timepoint'].isin(timepoint_filter)]

                st.dataframe(filtered_df, use_container_width=True)
            else:
                st.info("No efficacy data available")

        with tab3:
            st.markdown("### Safety Endpoints Comparison")
            if not safety_df.empty:
                # Add filter
                event_filter = st.multiselect(
                    "Filter by Event Category",
                    options=safety_df['event_category'].unique() if not safety_df.empty else [],
                    default=[]
                )

                # Apply filter
                filtered_df = safety_df.copy()
                if event_filter:
                    filtered_df = filtered_df[filtered_df['event_category'].isin(event_filter)]

                st.dataframe(filtered_df, use_container_width=True)
            else:
                st.info("No safety data available")


        with tab4:
            st.markdown("### Trial Design Metadata")

            # Get trial design data from database
            from src.tools.trial_design_database import TrialDesignDatabase

            try:
                trial_design_db = TrialDesignDatabase(database_url)
                trial_design_db.connect()

                trial_designs = trial_design_db.get_trial_designs_by_indication(selected_disease)
                trial_design_db.close()

                if trial_designs:
                    for td in trial_designs:
                        with st.expander(f"**{td['nct_id']}** - {td.get('study_design', 'N/A')}"):
                            col1, col2 = st.columns(2)

                            with col1:
                                st.markdown("**Trial Design Summary:**")
                                st.write(td.get('trial_design_summary', 'N/A'))

                                st.markdown("**Enrollment Summary:**")
                                st.write(td.get('enrollment_summary', 'N/A'))

                                st.markdown("**Primary Endpoint:**")
                                st.write(td.get('primary_endpoint_description', 'N/A'))

                            with col2:
                                st.markdown("**Trial Parameters:**")
                                st.write(f"Sample Size: {td.get('sample_size_enrolled', 'N/A')}")
                                st.write(f"Duration: {td.get('duration_weeks', 'N/A')} weeks")
                                st.write(f"Randomization: {td.get('randomization_ratio', 'N/A')}")
                                st.write(f"Blinding: {td.get('blinding', 'N/A')}")

                            if td.get('inclusion_criteria'):
                                st.markdown("**Inclusion Criteria:**")
                                for criterion in td['inclusion_criteria']:
                                    st.write(f"✓ {criterion}")

                            if td.get('exclusion_criteria'):
                                st.markdown("**Exclusion Criteria:**")
                                for criterion in td['exclusion_criteria']:
                                    st.write(f"✗ {criterion}")
                else:
                    st.info("No trial design data available")

            except Exception as e:
                logger.error(f"Failed to load trial design data: {e}")
                st.error(f"Failed to load trial design data: {str(e)}")

        with tab5:
            st.markdown("### Data Quality Issues & Warnings")
            st.info("💡 This section shows validation issues and warnings identified during extraction. Review these to understand potential data quality concerns.")

            try:
                # Get all quality issues for all extractions
                all_issues = []
                all_warnings = []

                for ext in extractions:
                    extraction_id = ext.get('extraction_id')
                    if extraction_id:
                        quality_data = db.get_quality_issues(extraction_id)

                        for issue in quality_data.get('issues', []):
                            issue['nct_id'] = ext['nct_id']
                            issue['trial_name'] = ext['trial_name']
                            issue['drug_name'] = ext['drug_name']
                            all_issues.append(issue)

                        for warning in quality_data.get('warnings', []):
                            warning['nct_id'] = ext['nct_id']
                            warning['trial_name'] = ext['trial_name']
                            warning['drug_name'] = ext['drug_name']
                            all_warnings.append(warning)

                # Display issues
                if all_issues:
                    st.subheader(f"🔴 Critical Issues ({len(all_issues)})")
                    for issue in all_issues:
                        with st.container():
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.markdown(f"**{issue['title']}**")
                                st.write(f"*{issue['description']}*")
                                st.caption(f"Trial: {issue['trial_name']} ({issue['nct_id']}) | Drug: {issue['drug_name']}")
                            with col2:
                                st.write(f"Severity: **{issue['severity'].upper()}**")
                                if issue.get('suggested_action'):
                                    st.caption(f"Action: {issue['suggested_action']}")
                            st.divider()
                else:
                    st.success("✓ No critical issues found")

                # Display warnings
                if all_warnings:
                    st.subheader(f"🟡 Warnings ({len(all_warnings)})")
                    for warning in all_warnings:
                        with st.container():
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.markdown(f"**{warning['title']}**")
                                st.write(f"*{warning['description']}*")
                                st.caption(f"Trial: {warning['trial_name']} ({warning['nct_id']}) | Drug: {warning['drug_name']}")
                            with col2:
                                st.write(f"Severity: **{warning['severity'].upper()}**")
                                if warning.get('suggested_action'):
                                    st.caption(f"Action: {warning['suggested_action']}")
                            st.divider()
                else:
                    st.success("✓ No warnings found")

            except Exception as e:
                logger.error(f"Failed to load quality issues: {e}")
                st.error(f"Failed to load quality issues: {str(e)}")

        db.close()

    except Exception as e:
        logger.error(f"Failed to load results: {e}")
        st.error(f"Failed to load results: {str(e)}")


    # ========================================================================
    # SECTION 7: EXCEL EXPORT
    # ========================================================================

    st.markdown("---")
    st.markdown("## 7️⃣ Export to Excel")

    col1, col2 = st.columns([3, 1])

    with col1:
        # Generate unique filename with disease, drugs, and timestamp
        if selected_disease:
            disease_slug = selected_disease.replace(' ', '_').lower()
        else:
            disease_slug = "all_diseases"

        # Include up to 3 drug names in filename, or use "multi_drug" if more
        if len(selected_drugs) == 1:
            drug_slug = selected_drugs[0].replace(' ', '_').lower()
        elif len(selected_drugs) <= 3:
            drug_slug = "_".join([d.replace(' ', '_').lower() for d in selected_drugs])
        else:
            drug_slug = f"{len(selected_drugs)}_drugs"

        # Add timestamp for uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"{disease_slug}_{drug_slug}_{timestamp}.xlsx"

        export_filename = st.text_input(
            "Export Filename",
            value=default_filename,
            help="Excel file will be saved to reports/ directory. Filename includes disease, drugs, and timestamp for uniqueness."
        )

    with col2:
        st.write("")  # Spacing
        st.write("")  # Spacing

        if st.button("📥 Export to Excel", type="primary"):
            try:
                output_path = project_root / "reports" / export_filename

                # Create reports directory if needed
                output_path.parent.mkdir(parents=True, exist_ok=True)

                # Export
                export_db_url = settings.drug_database_url or settings.paper_catalog_url
                db = ClinicalExtractionDatabase(export_db_url)
                db.connect()
                db.export_to_excel(selected_disease, selected_drugs, str(output_path))
                db.close()

                st.success(f"✓ Exported to {output_path}")
                st.info(f"File location: {output_path}")

            except Exception as e:
                logger.error(f"Export failed: {e}")
                st.error(f"Export failed: {str(e)}")
