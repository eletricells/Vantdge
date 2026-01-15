"""
Disease-Based Drug Efficacy Benchmarking

Compare approved drug efficacy data across a disease area.
Extract efficacy data from publications and clinical trials,
display benchmarking comparison tables.
"""

import streamlit as st
import sys
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add paths
frontend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()
import os


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv('DATABASE_URL', '')

# Configure logging to write to logs.md
log_file = Path(__file__).parent.parent.parent / "logs.md"

# Force reconfigure logging (basicConfig won't work if already configured)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Remove existing handlers
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Add file and stream handlers
file_handler = logging.FileHandler(log_file, mode='a')
file_handler.setFormatter(logging.Formatter('%(name)s - %(message)s'))
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(name)s - %(message)s'))

root_logger.addHandler(file_handler)
root_logger.addHandler(stream_handler)

from auth import check_password, check_page_access, show_access_denied

st.set_page_config(
    page_title="Efficacy Benchmarking",
    page_icon="📊",
    layout="wide"
)

if not check_password():
    st.stop()

# Page access check
if not check_page_access("Efficacy_Benchmarking"):
    show_access_denied()

# Import after auth
from src.drug_extraction_system.database.connection import DatabaseConnection
from src.efficacy_benchmarking.agent import EfficacyBenchmarkingAgent
from src.efficacy_benchmarking.models import (
    ReviewStatus, AUTOIMMUNE_ENDPOINTS, BenchmarkSession, EfficacyDataPoint
)

# Initialize session state
if 'disease' not in st.session_state:
    st.session_state.disease = None
if 'drugs' not in st.session_state:
    st.session_state.drugs = []
if 'database_drugs' not in st.session_state:
    st.session_state.database_drugs = []
if 'openfda_drugs' not in st.session_state:
    st.session_state.openfda_drugs = []
if 'extracted_drugs' not in st.session_state:
    st.session_state.extracted_drugs = []
if 'session' not in st.session_state:
    st.session_state.session = None
if 'existing_data' not in st.session_state:
    st.session_state.existing_data = None
if 'auto_extract_triggered' not in st.session_state:
    st.session_state.auto_extract_triggered = False


# Endpoint direction mapping - determines how to interpret results
# "higher_better": Response rates, remission rates (drug > comparator = good)
# "lower_better": Exacerbation rates, event rates (drug < comparator = good)
# "reduction": Change from baseline where negative = improvement
ENDPOINT_DIRECTIONS = {
    # Higher is better (response/remission rates)
    "sri-4": "higher_better",
    "sri-5": "higher_better",
    "sri-6": "higher_better",
    "bicla": "higher_better",
    "acr20": "higher_better",
    "acr50": "higher_better",
    "acr70": "higher_better",
    "pasi 75": "higher_better",
    "pasi 90": "higher_better",
    "pasi 100": "higher_better",
    "easi-75": "higher_better",
    "iga 0/1": "higher_better",
    "complete renal response": "higher_better",
    "partial renal response": "higher_better",
    "perr": "higher_better",
    "crr": "higher_better",
    "lldas": "higher_better",
    "remission": "higher_better",

    # Lower is better (event rates, exacerbations)
    "aaer": "lower_better",
    "aer": "lower_better",
    "exacerbation rate": "lower_better",
    "annualized exacerbation rate": "lower_better",
    "severe exacerbation": "lower_better",
    "flare rate": "lower_better",
    "relapse rate": "lower_better",
    "mortality": "lower_better",
    "hospitalization": "lower_better",

    # Reduction from baseline (change scores)
    "das28": "reduction",
    "sledai": "reduction",
    "mayo score": "reduction",
    "cdai": "reduction",
    "haq-di": "reduction",
    "pain vas": "reduction",
    "fatigue": "reduction",
}


def get_endpoint_direction(endpoint_name: str) -> str:
    """Determine the direction for an endpoint (higher_better, lower_better, reduction)."""
    if not endpoint_name:
        return "higher_better"  # Default assumption

    endpoint_lower = endpoint_name.lower()

    # Check exact matches first
    for key, direction in ENDPOINT_DIRECTIONS.items():
        if key in endpoint_lower:
            return direction

    # Heuristics for unknown endpoints
    # IMPORTANT: Check for response rate patterns FIRST
    # "CLASI 50% reduction" = % of patients achieving reduction = response rate (higher_better)
    # "50% reduction", "75% improvement" patterns are response rates
    if any(term in endpoint_lower for term in [
        "response", "remission", "improvement", "success", "responder",
        "50%", "75%", "90%", "100%",  # Response rate thresholds
        "lldas", "low disease activity"
    ]):
        return "higher_better"

    # Event rates where lower is better
    if any(term in endpoint_lower for term in ["exacerbation", "flare", "event", "death", "mortality"]):
        return "lower_better"
    # "rate" alone - check if it's a response rate or event rate
    if "rate" in endpoint_lower and not any(term in endpoint_lower for term in ["response", "remission"]):
        return "lower_better"

    # Change from baseline scores (only if not a response rate)
    if any(term in endpoint_lower for term in ["change from", "decrease in", "score change"]):
        return "reduction"

    return "higher_better"  # Default - most endpoints are response rates


def format_delta(
    drug_result: Optional[float],
    comparator_result: Optional[float],
    endpoint_name: str = "",
    unit: str = "%"
) -> str:
    """Calculate and format the delta between drug and comparator.

    Always shows numeric difference with +/- sign.
    Positive = drug better for higher_better endpoints
    Negative = drug better for lower_better/reduction endpoints
    """
    if drug_result is None or comparator_result is None:
        return "N/A"

    direction = get_endpoint_direction(endpoint_name)
    delta = drug_result - comparator_result

    if direction == "higher_better":
        # Positive delta is good (drug > comparator)
        prefix = "+" if delta >= 0 else ""
        return f"{prefix}{delta:.1f}{unit}"

    elif direction == "lower_better":
        # For rates where lower is better, negative delta is good
        # Show as negative when drug is lower (good)
        prefix = "+" if delta <= 0 else ""
        return f"{prefix}{-delta:.1f}{unit}"

    else:  # reduction
        # For change from baseline, more negative score = better
        # If drug decreased more than comparator, delta is negative (good)
        prefix = "+" if delta <= 0 else ""
        return f"{prefix}{-delta:.1f}{unit}"


def format_nct_link(nct_id: Optional[str]) -> str:
    """Format NCT ID as a clickable link."""
    if not nct_id:
        return ""
    return f"https://clinicaltrials.gov/study/{nct_id}"


def build_results_dataframe(session: BenchmarkSession) -> pd.DataFrame:
    """Build a DataFrame from benchmark session results."""
    rows = []

    # Track unique sources for numbering
    source_map = {}
    source_counter = 1

    for result in session.results:
        drug = result.drug
        for dp in result.efficacy_data:
            if dp.review_status == ReviewStatus.USER_REJECTED:
                continue

            # Create source key from PMID or NCT ID
            source_key = dp.pmid or dp.nct_id or dp.source_url or "unknown"
            if source_key not in source_map:
                source_map[source_key] = source_counter
                source_counter += 1

            unit = dp.drug_arm_result_unit or "%"
            # Extract dose from drug_arm_name if available
            dose = dp.drug_arm_name if dp.drug_arm_name and dp.drug_arm_name != drug.generic_name else 'N/A'
            comp_name = dp.comparator_arm_name or 'Placebo'

            # Format results - show raw number without unit appended
            if dp.drug_arm_result is not None:
                drug_arm_display = f"{dp.drug_arm_result:.1f}"
            else:
                drug_arm_display = "N/A"

            if dp.comparator_arm_result is not None:
                comp_arm_display = f"{dp.comparator_arm_result:.1f}"
            else:
                comp_arm_display = "N/A"

            rows.append({
                'Drug': drug.brand_name or drug.generic_name,
                'Generic Name': drug.generic_name,
                'Trial': dp.trial_name if dp.trial_name and dp.trial_name != 'None' else 'N/A',
                'NCT ID': dp.nct_id or '',
                'Dose': dose,
                'Endpoint': dp.endpoint_name,
                'Type': dp.endpoint_type or 'N/A',
                'Units': unit,
                'Drug Arm': drug_arm_display,
                'Comp': comp_name,
                'Comparator': comp_arm_display,
                'Delta': format_delta(dp.drug_arm_result, dp.comparator_arm_result, dp.endpoint_name, unit),
                'p-value': f"{dp.p_value:.4f}" if dp.p_value is not None else "N/A",
                'Timepoint': dp.timepoint or "N/A",
                'Confidence': f"{dp.confidence_score:.0%}",
                'Source': dp.source_type.value,
                'Source URL': dp.source_url,
                'NCT Link': format_nct_link(dp.nct_id),
                'Review Status': dp.review_status.value,
                'Source #': source_map[source_key],
                '_drug_arm_result': dp.drug_arm_result,
                '_confidence_score': dp.confidence_score,
            })

    return pd.DataFrame(rows)


def build_existing_data_dataframe(data: List[Dict[str, Any]]) -> pd.DataFrame:
    """Build a DataFrame from existing database records."""
    rows = []

    # Track unique sources for numbering
    source_map = {}
    source_counter = 1

    for record in data:
        endpoint_name = record.get('endpoint_name', 'N/A')
        unit = record.get('drug_arm_result_unit', '%') or '%'
        nct_id = record.get('nct_id', '')

        # Create source key from PMID or NCT ID
        source_key = record.get('pmid') or nct_id or record.get('source_url', '') or "unknown"
        if source_key not in source_map:
            source_map[source_key] = source_counter
            source_counter += 1

        # Extract dose from drug_arm_name if available
        drug_arm_name = record.get('drug_arm_name', '')
        generic_name = record.get('generic_name', 'Unknown')
        dose = drug_arm_name if drug_arm_name and drug_arm_name != generic_name else 'N/A'
        comp_name = record.get('comparator_arm_name', 'Placebo') or 'Placebo'

        # Format results - show raw number without unit appended
        if record.get('drug_arm_result') is not None:
            drug_arm_display = f"{record['drug_arm_result']:.1f}"
        else:
            drug_arm_display = "N/A"

        if record.get('comparator_arm_result') is not None:
            comp_arm_display = f"{record['comparator_arm_result']:.1f}"
        else:
            comp_arm_display = "N/A"

        rows.append({
            'Drug': record.get('brand_name') or generic_name,
            'Generic Name': generic_name,
            'Trial': record.get('trial_name') if record.get('trial_name') and record.get('trial_name') != 'None' else 'N/A',
            'NCT ID': nct_id,
            'Dose': dose,
            'Endpoint': endpoint_name,
            'Type': record.get('endpoint_type', 'N/A'),
            'Units': unit,
            'Drug Arm': drug_arm_display,
            'Comp': comp_name,
            'Comparator': comp_arm_display,
            'Delta': format_delta(record.get('drug_arm_result'), record.get('comparator_arm_result'), endpoint_name, unit),
            'p-value': f"{record['p_value']:.4f}" if record.get('p_value') is not None else "N/A",
            'Timepoint': record.get('timepoint', 'N/A'),
            'Confidence': f"{record.get('confidence_score', 0.85):.0%}",
            'Source': record.get('data_source', 'N/A'),
            'Source URL': record.get('source_url', ''),
            'NCT Link': format_nct_link(nct_id),
            'Review Status': record.get('review_status', 'auto_accepted'),
            'Source #': source_map[source_key],
            '_drug_arm_result': record.get('drug_arm_result'),
            '_confidence_score': record.get('confidence_score', 0.85),
        })

    return pd.DataFrame(rows)


# Page header
st.title("📊 Drug Efficacy Benchmarking")
st.markdown("Compare efficacy data across approved drugs for a disease area")
st.markdown("---")

# Sidebar configuration
with st.sidebar:
    st.markdown("## Configuration")

    min_confidence = st.slider(
        "Minimum Confidence Score",
        min_value=0.0,
        max_value=1.0,
        value=0.7,
        step=0.05,
        help="Data below this threshold will be flagged for review"
    )

    max_papers = st.slider(
        "Max Papers per Drug",
        min_value=1,
        max_value=10,
        value=5,
        help="Maximum number of publications to search per drug"
    )

    st.markdown("---")
    st.markdown("## Data Sources")
    st.markdown("""
    Priority order:
    1. 📚 PubMed publications
    2. 🏥 ClinicalTrials.gov

    All data includes source URLs for verification.
    """)

    st.markdown("---")
    st.markdown("## Supported Diseases")
    for disease in list(AUTOIMMUNE_ENDPOINTS.keys())[:8]:
        st.markdown(f"- {disease}")
    if len(AUTOIMMUNE_ENDPOINTS) > 8:
        st.markdown(f"- *...and {len(AUTOIMMUNE_ENDPOINTS) - 8} more*")

# Main content tabs
tab1, tab2, tab3 = st.tabs(["🔍 New Analysis", "📋 Review Queue", "📈 Results"])

with tab1:
    st.markdown("### Step 1: Enter Disease Name")

    col1, col2 = st.columns([3, 1])
    with col1:
        disease_input = st.text_input(
            "Disease",
            placeholder="e.g., SLE, lupus, rheumatoid arthritis, psoriasis",
            help="Enter disease name or common abbreviation"
        )

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        search_clicked = st.button("Find Drugs", type="primary", use_container_width=True)

    # Step 1: Find drugs when search clicked
    if search_clicked and disease_input:
        progress_container = st.empty()
        status_container = st.empty()

        def update_progress(msg: str, pct: float):
            progress_container.progress(pct, text=msg)
            status_container.text(msg)

        try:
            with DatabaseConnection(database_url=get_database_url()) as db:
                agent = EfficacyBenchmarkingAgent(db)

                # Standardize disease first
                update_progress("Standardizing disease name...", 0.1)
                disease = agent.disease_finder.standardize_disease(disease_input)

                if disease:
                    st.session_state.disease = disease
                    st.session_state.auto_extract_triggered = False

                    # Search database and OpenFDA (without auto-extraction yet)
                    update_progress(f"Searching database for {disease.standard_name}...", 0.2)
                    db_drugs = agent.disease_finder.find_approved_drugs_from_database(disease)
                    st.session_state.database_drugs = db_drugs

                    update_progress("Searching OpenFDA for approved drugs...", 0.4)
                    openfda_drugs = agent.disease_finder.search_openfda_by_indication(disease)

                    # Filter to drugs not in database
                    db_drug_names = {d.generic_name.lower() for d in db_drugs}
                    missing_drugs = [
                        d for d in openfda_drugs
                        if d["generic_name"].lower() not in db_drug_names
                    ]
                    st.session_state.openfda_drugs = missing_drugs

                    # Clear previously extracted drugs
                    st.session_state.extracted_drugs = []

                    # Combine for display
                    st.session_state.drugs = db_drugs

                    # Check for existing efficacy data
                    update_progress("Checking for existing efficacy data...", 0.8)
                    st.session_state.existing_data = agent.get_existing_efficacy_data(
                        disease.standard_name
                    )

                    progress_container.empty()
                    status_container.empty()

                    st.success(
                        f"✓ Matched to: **{disease.standard_name}** "
                        f"(MeSH: {disease.mesh_id or 'N/A'}, "
                        f"Area: {disease.therapeutic_area or 'N/A'})"
                    )
                else:
                    st.error("Could not standardize disease name. Try a different term.")
                    st.session_state.disease = None
                    st.session_state.drugs = []
                    st.session_state.database_drugs = []
                    st.session_state.openfda_drugs = []
        except Exception as e:
            progress_container.empty()
            status_container.empty()
            st.error(f"Error: {e}")
            import traceback
            with st.expander("Error details"):
                st.code(traceback.format_exc())

    # Show existing data summary if available
    if st.session_state.existing_data:
        st.info(
            f"📁 Found **{len(st.session_state.existing_data)}** existing efficacy records "
            f"for this disease. View them in the Results tab."
        )

    # Step 2: Show found drugs for selection
    if st.session_state.disease:
        disease = st.session_state.disease
        db_drugs = st.session_state.database_drugs
        openfda_drugs = st.session_state.openfda_drugs
        extracted_drugs = st.session_state.extracted_drugs

        # Combine database and extracted drugs
        all_available_drugs = db_drugs + extracted_drugs

        st.markdown("---")

        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("In Database", len(db_drugs))
        with col2:
            st.metric("Found in OpenFDA (Not in DB)", len(openfda_drugs))
        with col3:
            st.metric("Newly Extracted", len(extracted_drugs))

        # Show OpenFDA drugs not in database with option to extract
        if openfda_drugs:
            st.markdown("### New Drugs Found in OpenFDA")

            # Common generic drug names to filter out
            GENERIC_DRUG_PATTERNS = {
                'prednisone', 'prednisolone', 'dexamethasone', 'methylprednisolone',
                'hydrocortisone', 'betamethasone', 'triamcinolone', 'cortisone',
                'budesonide', 'fluticasone', 'beclomethasone',  # Steroids
                'methotrexate', 'azathioprine', 'cyclophosphamide', 'mycophenolate',
                'cyclosporine', 'tacrolimus', 'sirolimus',  # Immunosuppressants
                'hydroxychloroquine', 'chloroquine',  # Antimalarials
                'aspirin', 'ibuprofen', 'naproxen', 'diclofenac',  # NSAIDs
                'acetaminophen', 'lidocaine', 'bupivacaine',  # Others
            }

            def is_branded_drug(drug_info: dict) -> bool:
                """Check if drug is a branded/targeted therapy vs generic."""
                generic = drug_info.get('generic_name', '').lower()
                brand = drug_info.get('brand_name', '')

                # Check if generic name matches common generics
                for pattern in GENERIC_DRUG_PATTERNS:
                    if pattern in generic:
                        return False

                # Check if it's a kit/combination with generic steroids
                if 'kit' in generic or 'kit' in (brand or '').lower():
                    return False

                # Has a distinct brand name
                if brand and brand.upper() != generic.upper():
                    return True

                return False

            # Filter options
            filter_col1, filter_col2 = st.columns([1, 2])
            with filter_col1:
                show_branded_only = st.checkbox(
                    "Show branded drugs only",
                    value=True,
                    help="Filter out common generics (steroids, immunosuppressants)"
                )

            # Apply filter
            if show_branded_only:
                filtered_drugs = [d for d in openfda_drugs if is_branded_drug(d)]
            else:
                filtered_drugs = openfda_drugs

            st.info(
                f"Found **{len(filtered_drugs)}** {'branded ' if show_branded_only else ''}drugs "
                f"in OpenFDA not in your database. Select which drugs to add."
            )

            # Drug selection with checkboxes
            if filtered_drugs:
                st.markdown("**Select drugs to add to database:**")

                # Initialize selection state
                if 'openfda_selection' not in st.session_state:
                    st.session_state.openfda_selection = {}

                # Create checkbox grid
                cols = st.columns(min(2, len(filtered_drugs)))
                selected_for_extraction = []

                for i, drug_info in enumerate(filtered_drugs):
                    with cols[i % 2]:
                        brand = drug_info.get('brand_name') or drug_info['generic_name']
                        generic = drug_info['generic_name']
                        manufacturer = drug_info.get('manufacturer', 'Unknown')

                        # Use generic name as key for checkbox
                        key = f"extract_{generic.lower().replace(' ', '_')}"
                        is_selected = st.checkbox(
                            f"**{brand}**",
                            value=True,  # Default to selected
                            key=key
                        )
                        st.caption(f"{generic}")
                        st.caption(f"*{manufacturer}*")

                        if is_selected:
                            selected_for_extraction.append(drug_info)

                st.markdown("---")

                # Extract button
                if selected_for_extraction:
                    if st.button(
                        f"🔄 Extract {len(selected_for_extraction)} Selected Drug(s)",
                        type="primary",
                        use_container_width=True
                    ):
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        def extraction_progress(msg: str, pct: float):
                            progress_bar.progress(pct)
                            status_text.text(msg)

                        try:
                            with DatabaseConnection(database_url=get_database_url()) as db:
                                agent = EfficacyBenchmarkingAgent(db)
                                extracted = agent.disease_finder.extract_missing_drugs(
                                    selected_for_extraction,
                                    disease,
                                    progress_callback=extraction_progress
                                )

                                # Add to existing extracted drugs
                                existing_extracted = st.session_state.extracted_drugs or []
                                st.session_state.extracted_drugs = existing_extracted + extracted
                                st.session_state.auto_extract_triggered = True

                                # Remove extracted drugs from openfda list
                                extracted_names = {d.generic_name.lower() for d in extracted}
                                remaining = [
                                    d for d in openfda_drugs
                                    if d["generic_name"].lower() not in extracted_names
                                ]
                                st.session_state.openfda_drugs = remaining

                            progress_bar.empty()
                            status_text.empty()
                            st.success(f"✓ Successfully extracted {len(extracted)} drugs!")
                            st.rerun()

                        except Exception as e:
                            progress_bar.empty()
                            status_text.empty()
                            st.error(f"Extraction failed: {e}")
                            import traceback
                            with st.expander("Error details"):
                                st.code(traceback.format_exc())
                else:
                    st.warning("Select at least one drug to extract")
            else:
                st.info("No branded drugs found. Uncheck 'Show branded drugs only' to see all drugs.")

        # Drug selection section
        if all_available_drugs:
            st.markdown(f"### Step 2: Select Drugs ({len(all_available_drugs)} available)")

            # Create checkbox selection
            drug_selection = {}

            # Show database drugs
            if db_drugs:
                st.markdown("**Drugs in Database:**")
                cols = st.columns(min(3, max(len(db_drugs), 1)))
                for i, drug in enumerate(db_drugs):
                    with cols[i % 3]:
                        display_name = drug.brand_name or drug.generic_name
                        drug_selection[drug.drug_id] = st.checkbox(
                            f"**{display_name}**",
                            value=True,
                            key=f"drug_{drug.drug_id}"
                        )
                        st.caption(f"{drug.generic_name}")
                        if drug.manufacturer:
                            st.caption(f"*{drug.manufacturer}*")

            # Show newly extracted drugs
            if extracted_drugs:
                st.markdown("**Newly Extracted Drugs:**")
                cols = st.columns(min(3, max(len(extracted_drugs), 1)))
                for i, drug in enumerate(extracted_drugs):
                    with cols[i % 3]:
                        display_name = drug.brand_name or drug.generic_name
                        drug_selection[drug.drug_id] = st.checkbox(
                            f"**{display_name}** 🆕",
                            value=True,
                            key=f"extracted_drug_{drug.drug_id}"
                        )
                        st.caption(f"{drug.generic_name}")
                        if drug.indication_details:
                            st.caption(f"*{drug.indication_details}*")

            selected_drug_ids = [did for did, selected in drug_selection.items() if selected]
        else:
            selected_drug_ids = []
            if not openfda_drugs:
                st.warning(f"No approved drugs found for {disease.standard_name}")
            else:
                st.info("Extract the OpenFDA drugs above to add them to the database for analysis.")

        # Manual drug search
        with st.expander("🔎 Search for additional drugs manually"):
            search_drug = st.text_input("Drug name", key="manual_drug_search")
            if search_drug:
                try:
                    with DatabaseConnection(database_url=get_database_url()) as db:
                        agent = EfficacyBenchmarkingAgent(db)
                        found_drugs = agent.disease_finder.search_drugs_by_name(search_drug)
                        if found_drugs:
                            st.markdown("**Found drugs:**")
                            for fd in found_drugs:
                                st.markdown(
                                    f"- {fd.brand_name or fd.generic_name} ({fd.generic_name}) - "
                                    f"ID: {fd.drug_id}"
                                )
                        else:
                            st.info("No drugs found matching that name")
                except Exception as e:
                    st.error(f"Search error: {e}")

        # Step 3: Extract Efficacy Data (only if drugs are available)
        if all_available_drugs:
            st.markdown("---")
            st.markdown("### Step 3: Extract Efficacy Data")

            # Show expected endpoints
            from src.efficacy_benchmarking.models import get_endpoints_for_disease
            endpoints = get_endpoints_for_disease(disease.standard_name)
            with st.expander("Expected endpoints for this disease"):
                st.markdown(f"**Primary:** {', '.join(endpoints.get('primary', []))}")
                st.markdown(f"**Secondary:** {', '.join(endpoints.get('secondary', []))}")
                st.markdown(f"**Timepoints:** {', '.join(endpoints.get('timepoints', []))}")

            if st.button("🚀 Extract Efficacy Data", type="primary", use_container_width=True):
                if not selected_drug_ids:
                    st.warning("Please select at least one drug")
                else:
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    def update_progress(message: str, progress: float):
                        progress_bar.progress(progress)
                        status_text.text(message)

                    try:
                        with DatabaseConnection(database_url=get_database_url()) as db:
                            agent = EfficacyBenchmarkingAgent(
                                db,
                                progress_callback=update_progress,
                                confidence_threshold=min_confidence
                            )
                            session = agent.run_benchmark(
                                disease_input=disease.raw_input,
                                selected_drug_ids=selected_drug_ids,
                                max_papers_per_drug=max_papers,
                                min_confidence=min_confidence
                            )
                            st.session_state.session = session

                            # Refresh existing data from database (inside db connection)
                            st.session_state.existing_data = agent.get_existing_efficacy_data(
                                disease.standard_name
                            )

                        status_text.empty()
                        st.success("✓ Extraction complete!")

                        # Show summary
                        total_datapoints = session.total_data_points
                        pending_review = session.pending_review_count

                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Data Points", total_datapoints)
                        with col2:
                            st.metric("Pending Review", pending_review)
                        with col3:
                            st.metric("Drugs Processed", len(session.results))
                        with col4:
                            success_count = sum(1 for r in session.results if r.extraction_status == "success")
                            st.metric("Successful", success_count)

                        if pending_review > 0:
                            st.warning(
                                f"⚠️ {pending_review} data points need manual review "
                                f"(confidence < {min_confidence:.0%}). Check the Review Queue tab."
                            )

                    except Exception as e:
                        st.error(f"Extraction failed: {e}")
                        import traceback
                        with st.expander("Error details"):
                            st.code(traceback.format_exc())

with tab2:
    st.markdown("### Pending Review Queue")

    session = st.session_state.session

    if session and session.results:
        pending_items = []
        for result in session.results:
            for i, dp in enumerate(result.efficacy_data):
                if dp.review_status == ReviewStatus.PENDING_REVIEW:
                    pending_items.append({
                        'drug': result.drug.generic_name,
                        'brand': result.drug.brand_name,
                        'endpoint': dp.endpoint_name,
                        'result': f"{dp.drug_arm_result:.1f}{dp.drug_arm_result_unit}" if dp.drug_arm_result else "N/A",
                        'comparator': f"{dp.comparator_arm_result:.1f}{dp.drug_arm_result_unit}" if dp.comparator_arm_result else "N/A",
                        'confidence': f"{dp.confidence_score:.0%}",
                        'source': dp.source_url,
                        'source_type': dp.source_type.value,
                        'data_point': dp,
                        'result_idx': session.results.index(result),
                        'dp_idx': i
                    })

        if pending_items:
            st.info(f"**{len(pending_items)}** items need review")

            for idx, item in enumerate(pending_items):
                with st.expander(
                    f"⚠️ {item['brand'] or item['drug']} - {item['endpoint']} "
                    f"(Conf: {item['confidence']})"
                ):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**Drug:** {item['drug']}")
                        st.markdown(f"**Endpoint:** {item['endpoint']}")
                        st.markdown(f"**Result:** {item['result']}")
                        st.markdown(f"**Comparator:** {item['comparator']}")
                    with col2:
                        st.markdown(f"**Source:** {item['source_type']}")
                        st.markdown(f"**Confidence:** {item['confidence']}")

                    if item['source']:
                        st.markdown(f"[View Source]({item['source']})")

                    if item['data_point'].raw_source_text:
                        st.markdown("**Source text:**")
                        st.text(item['data_point'].raw_source_text[:500])

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button("✓ Confirm", key=f"confirm_{idx}", type="primary"):
                            item['data_point'].review_status = ReviewStatus.USER_CONFIRMED
                            st.success("Confirmed!")
                            st.rerun()
                    with col2:
                        if st.button("✗ Reject", key=f"reject_{idx}"):
                            item['data_point'].review_status = ReviewStatus.USER_REJECTED
                            st.success("Rejected!")
                            st.rerun()
                    with col3:
                        if st.button("⏭️ Skip", key=f"skip_{idx}"):
                            pass  # Do nothing, just continue
        else:
            st.success("✓ No items pending review")
    else:
        st.info("Run an analysis first to see review items")

with tab3:
    st.markdown("### Efficacy Benchmarking Results")

    # Source selector
    data_source = st.radio(
        "Data Source",
        ["Existing Database", "New Extraction"],  # Database first (most common)
        horizontal=True,
        help="'Existing Database' shows all stored data. 'New Extraction' shows only the current session's results."
    )

    df = None

    if data_source == "Existing Database":
        # Refresh data from database (may have been updated by extraction)
        if st.session_state.disease:
            col_refresh, col_clear = st.columns([1, 1])
            with col_refresh:
                if st.button("🔄 Refresh from Database"):
                    with DatabaseConnection(database_url=get_database_url()) as db:
                        agent = EfficacyBenchmarkingAgent(db)
                        st.session_state.existing_data = agent.get_existing_efficacy_data(
                            st.session_state.disease.standard_name
                        )
                    st.rerun()

            with col_clear:
                if st.button("🗑️ Clear Disease Data", type="secondary"):
                    st.session_state.confirm_clear = True

                if st.session_state.get('confirm_clear', False):
                    st.warning("⚠️ This will delete all efficacy data for this disease!")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Yes, Clear All", type="primary"):
                            with DatabaseConnection(database_url=get_database_url()) as db:
                                agent = EfficacyBenchmarkingAgent(db)
                                deleted = agent.clear_disease_efficacy_data(
                                    st.session_state.disease.standard_name
                                )
                                st.success(f"✓ Cleared {deleted} records")
                                st.session_state.existing_data = None
                                st.session_state.confirm_clear = False
                            st.rerun()
                    with c2:
                        if st.button("Cancel"):
                            st.session_state.confirm_clear = False
                            st.rerun()

        existing_data = st.session_state.existing_data
        if existing_data:
            df = build_existing_data_dataframe(existing_data)
            if st.session_state.disease:
                st.caption(f"Disease: **{st.session_state.disease.standard_name}** | Records: {len(existing_data)}")
        else:
            st.info("Search for a disease to view existing data, or click 'Refresh from Database' after extraction")

    else:  # New Extraction
        session = st.session_state.session
        if session and session.results:
            df = build_results_dataframe(session)
            st.caption(f"Disease: **{session.disease.standard_name}** | Status: {session.status} | This session only")
        else:
            st.info("Run an analysis to see new extraction results")

    if df is not None and not df.empty:
        # Filters
        col1, col2, col3 = st.columns(3)

        with col1:
            endpoints = df['Endpoint'].unique().tolist()
            selected_endpoints = st.multiselect(
                "Filter by Endpoint",
                options=endpoints,
                default=endpoints  # Show all endpoints by default
            )

        with col2:
            drugs = df['Drug'].unique().tolist()
            selected_drugs = st.multiselect(
                "Filter by Drug",
                options=drugs,
                default=drugs
            )

        with col3:
            sources = df['Source'].unique().tolist()
            selected_sources = st.multiselect(
                "Filter by Source",
                options=sources,
                default=sources
            )

        # Additional filter row for trials
        col4, col5 = st.columns(2)
        with col4:
            trials = df['Trial'].unique().tolist()
            selected_trials = st.multiselect(
                "Filter by Trial",
                options=trials,
                default=trials
            )

        # Apply filters
        filtered_df = df.copy()
        if selected_endpoints:
            filtered_df = filtered_df[filtered_df['Endpoint'].isin(selected_endpoints)]
        if selected_drugs:
            filtered_df = filtered_df[filtered_df['Drug'].isin(selected_drugs)]
        if selected_sources:
            filtered_df = filtered_df[filtered_df['Source'].isin(selected_sources)]
        if selected_trials:
            filtered_df = filtered_df[filtered_df['Trial'].isin(selected_trials)]

        # Display columns (include Trial, Dose, Units, and Comp)
        display_cols = [
            'Drug', 'Trial', 'Dose', 'Endpoint', 'Type', 'Units', 'Drug Arm', 'Comp', 'Comparator',
            'Delta', 'p-value', 'Timepoint', 'Confidence', 'Source #'
        ]

        st.markdown(f"**Showing {len(filtered_df)} records**")

        # Style the dataframe with clickable NCT links
        st.dataframe(
            filtered_df[display_cols],
            use_container_width=True,
            hide_index=True,
            height=min(400, 35 * len(filtered_df) + 38),  # Dynamic height based on row count
            column_config={
                'Drug': st.column_config.TextColumn('Drug', width='medium'),
                'Trial': st.column_config.TextColumn('Trial', width='small'),
                'Dose': st.column_config.TextColumn('Dose', width='medium'),
                'Endpoint': st.column_config.TextColumn('Endpoint', width='medium'),
                'Type': st.column_config.TextColumn('Type', width='small'),
                'Units': st.column_config.TextColumn('Units', width='small'),
                'Drug Arm': st.column_config.TextColumn('Drug', width='small'),
                'Comp': st.column_config.TextColumn('Comp', width='small'),
                'Comparator': st.column_config.TextColumn('Comp', width='small'),
                'Delta': st.column_config.TextColumn('Delta', width='small'),
                'p-value': st.column_config.TextColumn('p-value', width='small'),
                'Confidence': st.column_config.TextColumn('Conf', width='small'),
                'Source #': st.column_config.NumberColumn('Src', width='small'),
            }
        )

        # Build and display source legend
        source_legend = filtered_df[['Source #', 'Source URL', 'NCT ID', 'Trial']].drop_duplicates()
        source_legend = source_legend.sort_values('Source #')

        with st.expander(f"📚 Source Legend ({len(source_legend)} unique sources)"):
            for _, row in source_legend.iterrows():
                src_num = row['Source #']
                source_url = row.get('Source URL', '')
                nct_id = row.get('NCT ID', '')
                trial = row.get('Trial', 'N/A')

                if source_url:
                    st.markdown(f"**[{src_num}]** [{trial}]({source_url})")
                elif nct_id:
                    st.markdown(f"**[{src_num}]** [{trial}](https://clinicaltrials.gov/study/{nct_id})")
                else:
                    st.markdown(f"**[{src_num}]** {trial}")

        # Export section
        st.markdown("---")
        col1, col2 = st.columns([1, 3])
        with col1:
            disease_name = ""
            if st.session_state.disease:
                disease_name = st.session_state.disease.standard_name.replace(' ', '_')

            export_df = filtered_df[display_cols + ['Source URL', 'NCT ID']].copy()
            csv_data = export_df.to_csv(index=False)

            st.download_button(
                "📥 Export to CSV",
                csv_data,
                f"efficacy_benchmark_{disease_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                "text/csv",
                use_container_width=True
            )

        # Source links table
        with st.expander("📎 Source URLs"):
            source_df = filtered_df[['Drug', 'Endpoint', 'Source URL']].copy()
            source_df = source_df[source_df['Source URL'].notna() & (source_df['Source URL'] != '')]
            if not source_df.empty:
                st.dataframe(source_df, use_container_width=True, hide_index=True)
            else:
                st.info("No source URLs available")

    elif df is not None:
        st.info("No data to display")

# Footer
st.markdown("---")
st.caption(
    "Data sources include PubMed publications and ClinicalTrials.gov. "
    "All data points include source URLs for verification. "
    "Low-confidence data is flagged for manual review."
)
