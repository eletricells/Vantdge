"""
Efficacy Comparison - Streamlit UI

Generate comprehensive efficacy comparison tables for approved drugs
in a given disease/indication.
"""

import asyncio
import logging
import pandas as pd
import streamlit as st
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional

# Add paths
frontend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auth import check_password, check_page_access, show_access_denied

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="Efficacy Comparison",
    page_icon="📊",
    layout="wide",
)

# Password protection
if not check_password():
    st.stop()

# Page access check
if not check_page_access("Efficacy_Comparison"):
    show_access_denied()

# Initialize session state
if "ec_results" not in st.session_state:
    st.session_state.ec_results = None
if "ec_drugs" not in st.session_state:
    st.session_state.ec_drugs = []
if "ec_progress" not in st.session_state:
    st.session_state.ec_progress = 0.0
if "ec_status" not in st.session_state:
    st.session_state.ec_status = ""


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def update_progress(message: str, progress: float):
    """Update progress in session state."""
    st.session_state.ec_progress = progress
    st.session_state.ec_status = message


# =============================================================================
# MAIN PAGE
# =============================================================================

st.title("📊 Efficacy Comparison")
st.markdown("""
Generate comprehensive efficacy comparison tables for approved drugs in a disease/indication.

**Features:**
- Finds innovative drugs only (excludes generics/biosimilars)
- Identifies pivotal Phase 2/3 trials
- Screens papers with AI to find primary results
- Extracts ALL endpoints at ALL timepoints
- Standardizes endpoint names
""")

# Sidebar
with st.sidebar:
    st.header("Settings")

    max_drugs = st.slider(
        "Max drugs to process",
        min_value=1,
        max_value=20,
        value=10,
        help="Maximum number of drugs to analyze",
    )

    max_trials = st.slider(
        "Max trials per drug",
        min_value=1,
        max_value=6,
        value=4,
        help="Maximum pivotal trials per drug",
    )

    st.markdown("---")
    st.markdown("**Data Sources (Priority)**")
    st.markdown("""
    1. PMC Full-Text
    2. PubMed Abstract
    3. ClinicalTrials.gov
    4. FDA Label
    """)

# =============================================================================
# TAB 1: NEW ANALYSIS
# =============================================================================

tab1, tab2, tab3 = st.tabs(["🔍 New Analysis", "📋 Results", "📈 Comparison View"])

with tab1:
    st.subheader("1. Enter Disease/Indication")

    col1, col2 = st.columns([3, 1])

    with col1:
        indication = st.text_input(
            "Disease Name",
            placeholder="e.g., Atopic Dermatitis, Systemic Lupus Erythematosus",
            help="Enter the disease or indication to analyze",
        )

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        search_drugs_btn = st.button("🔍 Find Drugs", type="secondary", use_container_width=True)

    # Quick disease buttons
    st.markdown("**Quick Select:**")
    quick_cols = st.columns(5)
    quick_diseases = [
        "Atopic Dermatitis",
        "Plaque Psoriasis",
        "Rheumatoid Arthritis",
        "Systemic Lupus Erythematosus",
        "Ulcerative Colitis",
    ]

    for i, disease in enumerate(quick_diseases):
        with quick_cols[i]:
            if st.button(disease, key=f"quick_{i}", use_container_width=True):
                indication = disease
                search_drugs_btn = True

    # Find drugs
    if search_drugs_btn and indication:
        with st.spinner(f"Finding innovative drugs for {indication}..."):
            try:
                from src.efficacy_comparison.services import InnovativeDrugFinder

                finder = InnovativeDrugFinder()
                drugs = run_async(finder.find_innovative_drugs(indication))
                st.session_state.ec_drugs = drugs

                if drugs:
                    st.success(f"Found {len(drugs)} innovative drugs for {indication}")
                else:
                    st.warning(f"No innovative drugs found for {indication}")

            except Exception as e:
                st.error(f"Error finding drugs: {e}")
                logger.exception("Error in drug finder")

    # Display found drugs
    if st.session_state.ec_drugs:
        st.subheader("2. Select Drugs to Analyze")

        drugs = st.session_state.ec_drugs

        # Create dataframe for display
        drug_df = pd.DataFrame([
            {
                "Select": True,
                "Brand Name": d.drug_name,
                "Generic Name": d.generic_name,
                "Manufacturer": d.manufacturer or "Unknown",
                "Type": d.drug_type or "Unknown",
            }
            for d in drugs[:max_drugs]
        ])

        # Editable dataframe for selection
        edited_df = st.data_editor(
            drug_df,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=True),
                "Brand Name": st.column_config.TextColumn("Brand Name", disabled=True),
                "Generic Name": st.column_config.TextColumn("Generic Name", disabled=True),
                "Manufacturer": st.column_config.TextColumn("Manufacturer", disabled=True),
                "Type": st.column_config.TextColumn("Type", disabled=True),
            },
            hide_index=True,
            use_container_width=True,
        )

        # Get selected drugs
        selected_mask = edited_df["Select"].tolist()
        selected_drugs = [d for d, selected in zip(drugs[:max_drugs], selected_mask) if selected]

        st.markdown(f"**Selected:** {len(selected_drugs)} drugs")

        # Run analysis button
        st.subheader("3. Run Analysis")

        if st.button("🚀 Run Efficacy Comparison", type="primary", use_container_width=True):
            if not selected_drugs:
                st.warning("Please select at least one drug")
            else:
                # Progress placeholder
                progress_bar = st.progress(0)
                status_text = st.empty()

                try:
                    from src.efficacy_comparison import EfficacyComparisonAgent

                    def progress_callback(message, progress):
                        progress_bar.progress(progress)
                        status_text.text(message)

                    agent = EfficacyComparisonAgent(
                        progress_callback=progress_callback
                    )

                    selected_names = [d.drug_name for d in selected_drugs]

                    result = run_async(
                        agent.run_comparison(
                            indication=indication,
                            selected_drug_names=selected_names,
                            max_drugs=max_drugs,
                            max_trials_per_drug=max_trials,
                        )
                    )

                    st.session_state.ec_results = result
                    progress_bar.progress(1.0)
                    status_text.text("Complete!")

                    st.success(f"""
                    Analysis complete!
                    - **Drugs:** {result.total_drugs}
                    - **Trials:** {result.total_trials}
                    - **Endpoints:** {result.total_endpoints}
                    """)

                    st.balloons()

                except Exception as e:
                    st.error(f"Error running analysis: {e}")
                    logger.exception("Error in efficacy comparison")

# =============================================================================
# TAB 2: RESULTS
# =============================================================================

with tab2:
    st.subheader("Extraction Results")

    if st.session_state.ec_results is None:
        st.info("Run an analysis to see results here.")
    else:
        result = st.session_state.ec_results

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Indication", result.indication_name)
        with col2:
            st.metric("Drugs", result.total_drugs)
        with col3:
            st.metric("Trials", result.total_trials)
        with col4:
            st.metric("Endpoints", result.total_endpoints)

        st.markdown("---")

        # Drug selector
        drug_names = [p.drug.drug_name for p in result.drug_profiles]
        selected_drug = st.selectbox("Select Drug", drug_names)

        # Find selected profile
        profile = None
        for p in result.drug_profiles:
            if p.drug.drug_name == selected_drug:
                profile = p
                break

        if profile:
            st.markdown(f"### {profile.drug.drug_name} ({profile.drug.generic_name})")

            # Trials
            st.markdown("#### Pivotal Trials")
            if profile.pivotal_trials:
                trial_data = []
                for t in profile.pivotal_trials:
                    trial_data.append({
                        "Trial Name": t.trial_name or "N/A",
                        "NCT ID": t.nct_id or "N/A",
                        "Phase": t.phase or "N/A",
                        "Enrollment": t.enrollment or "N/A",
                        "Confidence": f"{t.confidence:.0%}",
                    })
                st.dataframe(pd.DataFrame(trial_data), hide_index=True, use_container_width=True)
            else:
                st.warning("No pivotal trials identified")

            # Extractions
            st.markdown("#### Extracted Data")
            if profile.extractions:
                for ext in profile.extractions:
                    trial_name = ext.metadata.trial_name or ext.metadata.nct_id or "Unknown"

                    with st.expander(f"📄 {trial_name}", expanded=True):
                        # Metadata
                        st.markdown("**Trial Info**")
                        meta_cols = st.columns(4)
                        with meta_cols[0]:
                            st.text(f"NCT: {ext.metadata.nct_id or 'N/A'}")
                        with meta_cols[1]:
                            st.text(f"Phase: {ext.metadata.phase or 'N/A'}")
                        with meta_cols[2]:
                            st.text(f"N: {ext.metadata.total_enrollment or 'N/A'}")
                        with meta_cols[3]:
                            st.text(f"Source: {ext.data_source.source_type.value if ext.data_source else 'N/A'}")

                        # Arms
                        if ext.metadata.arms:
                            st.markdown("**Treatment Arms**")
                            arm_data = [{
                                "Arm": a.name,
                                "N": a.n or "N/A",
                                "Dose": a.dose or "N/A",
                                "Frequency": a.frequency or "N/A",
                            } for a in ext.metadata.arms]
                            st.dataframe(pd.DataFrame(arm_data), hide_index=True)

                        # Endpoints
                        if ext.endpoints:
                            st.markdown("**Efficacy Endpoints**")

                            # Group by endpoint
                            endpoint_data = []
                            for ep in ext.endpoints:
                                endpoint_data.append({
                                    "Endpoint": ep.endpoint_name_normalized or ep.endpoint_name_raw,
                                    "Category": ep.endpoint_category.value if ep.endpoint_category else "N/A",
                                    "Arm": ep.arm_name or "N/A",
                                    "Timepoint": ep.timepoint or "N/A",
                                    "Responders %": f"{ep.responders_pct:.1%}" if ep.responders_pct else "N/A",
                                    "Change": ep.change_from_baseline if ep.change_from_baseline else "N/A",
                                    "P-value": ep.p_value or "N/A",
                                })

                            ep_df = pd.DataFrame(endpoint_data)
                            st.dataframe(ep_df, hide_index=True, use_container_width=True)

                        # Baseline
                        if ext.baseline:
                            st.markdown("**Baseline Characteristics**")
                            baseline_data = []
                            for b in ext.baseline:
                                baseline_data.append({
                                    "Arm": b.arm_name,
                                    "N": b.n or "N/A",
                                    "Age (mean)": b.age_mean or "N/A",
                                    "Male %": f"{b.male_pct:.0%}" if b.male_pct else "N/A",
                                    "Disease Duration": b.disease_duration_mean or "N/A",
                                })
                            st.dataframe(pd.DataFrame(baseline_data), hide_index=True)
            else:
                st.warning("No data extracted for this drug")

# =============================================================================
# TAB 3: COMPARISON VIEW
# =============================================================================

with tab3:
    st.subheader("Cross-Drug Comparison")

    if st.session_state.ec_results is None:
        st.info("Run an analysis to see comparison view here.")
    else:
        result = st.session_state.ec_results

        # Collect all endpoints across all drugs
        all_endpoints = []
        for profile in result.drug_profiles:
            for ext in profile.extractions:
                for ep in ext.endpoints:
                    all_endpoints.append({
                        "Drug": profile.drug.drug_name,
                        "Trial": ext.metadata.trial_name or ext.metadata.nct_id,
                        "Arm": ep.arm_name,
                        "Endpoint": ep.endpoint_name_normalized or ep.endpoint_name_raw,
                        "Category": ep.endpoint_category.value if ep.endpoint_category else "N/A",
                        "Timepoint": ep.timepoint,
                        "Timepoint (weeks)": ep.timepoint_weeks,
                        "N": ep.n_evaluated,
                        "Responders": ep.responders_n,
                        "Responders %": ep.responders_pct,
                        "Change": ep.change_from_baseline,
                        "P-value": ep.p_value,
                        "Significant": ep.is_statistically_significant,
                    })

        if all_endpoints:
            df = pd.DataFrame(all_endpoints)

            # Filters
            filter_cols = st.columns(4)

            with filter_cols[0]:
                endpoint_filter = st.multiselect(
                    "Filter by Endpoint",
                    options=df["Endpoint"].unique().tolist(),
                    default=[],
                )

            with filter_cols[1]:
                drug_filter = st.multiselect(
                    "Filter by Drug",
                    options=df["Drug"].unique().tolist(),
                    default=[],
                )

            with filter_cols[2]:
                timepoint_filter = st.multiselect(
                    "Filter by Timepoint",
                    options=sorted([t for t in df["Timepoint"].unique() if t], key=lambda x: str(x)),
                    default=[],
                )

            with filter_cols[3]:
                category_filter = st.multiselect(
                    "Filter by Category",
                    options=df["Category"].unique().tolist(),
                    default=[],
                )

            # Apply filters
            filtered_df = df.copy()
            if endpoint_filter:
                filtered_df = filtered_df[filtered_df["Endpoint"].isin(endpoint_filter)]
            if drug_filter:
                filtered_df = filtered_df[filtered_df["Drug"].isin(drug_filter)]
            if timepoint_filter:
                filtered_df = filtered_df[filtered_df["Timepoint"].isin(timepoint_filter)]
            if category_filter:
                filtered_df = filtered_df[filtered_df["Category"].isin(category_filter)]

            # Display
            st.markdown(f"**Showing {len(filtered_df)} of {len(df)} endpoints**")

            # Format percentages
            display_df = filtered_df.copy()
            display_df["Responders %"] = display_df["Responders %"].apply(
                lambda x: f"{x:.1%}" if pd.notna(x) else "N/A"
            )

            st.dataframe(
                display_df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Responders %": st.column_config.TextColumn("Responders %"),
                    "Significant": st.column_config.CheckboxColumn("Significant"),
                },
            )

            # Download button
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"efficacy_comparison_{result.indication_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.warning("No endpoint data available for comparison")

# Footer
st.markdown("---")
st.caption("Efficacy Comparison Module | Data sources: OpenFDA, ClinicalTrials.gov, PubMed, PMC")
