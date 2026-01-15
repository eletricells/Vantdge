"""
Pipeline Intelligence - Competitive Landscape View.

Displays pipeline drugs for a disease sorted by phase:
- Approved
- Phase 3
- Phase 2
- Phase 1
- Preclinical
- Discontinued/Failed
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
    page_title="Pipeline Intelligence",
    page_icon="💊",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

# Page access check
if not check_page_access("Pipeline_Intelligence"):
    show_access_denied()

# Import after auth check
from dotenv import load_dotenv
load_dotenv()
import os


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv('DATABASE_URL', '')


from src.drug_extraction_system.database.connection import DatabaseConnection
from src.drug_extraction_system.api_clients.clinicaltrials_client import ClinicalTrialsClient
from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
from src.pipeline_intelligence.repository import PipelineIntelligenceRepository
from src.pipeline_intelligence.service import PipelineIntelligenceService
from src.pipeline_intelligence.models import PipelineDrug, CompetitiveLandscape
from src.disease_intelligence.repository import DiseaseIntelligenceRepository


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


def render_drug_card(drug: PipelineDrug, show_discontinued_info: bool = False):
    """Render a drug as an expandable card."""
    name = drug.brand_name or drug.generic_name
    with st.expander(f"**{name}** ({drug.generic_name})"):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**Manufacturer:** {drug.manufacturer or 'N/A'}")
            st.markdown(f"**MOA:** {drug.mechanism_of_action or 'N/A'}")
            if drug.drug_type:
                st.markdown(f"**Type:** {drug.drug_type}")
            if drug.target:
                st.markdown(f"**Target:** {drug.target}")

        with col2:
            if drug.dosing_summary:
                st.markdown(f"**Dosing:** {drug.dosing_summary}")
            if drug.recent_milestone:
                st.markdown(f"**Recent News:** {drug.recent_milestone}")
            if drug.source_nct_ids:
                trials_str = ", ".join(drug.source_nct_ids[:3])
                st.markdown(f"**Trials:** {trials_str}")

        if show_discontinued_info:
            st.divider()
            status_color = {"discontinued": "red", "failed": "red", "on_hold": "orange", "terminated": "red"}
            status = drug.development_status or "discontinued"
            st.markdown(f"**Status:** :{status_color.get(status, 'gray')}[{status.upper()}]")
            if drug.discontinuation_date:
                st.markdown(f"**Discontinued:** {drug.discontinuation_date}")
            if drug.discontinuation_reason:
                st.markdown(f"**Reason:** {drug.discontinuation_reason}")
            if drug.failure_stage:
                st.markdown(f"**Highest Phase Reached:** {drug.failure_stage}")

        # Data sources
        if drug.data_sources:
            st.caption(f"Sources: {', '.join(drug.data_sources)}")


def render_phase_section(drugs: list, phase_name: str, color: str = "blue"):
    """Render a phase section with drug cards."""
    if not drugs:
        return

    st.markdown(f"### :{color}[{phase_name}] ({len(drugs)})")

    for drug in drugs:
        render_drug_card(drug, show_discontinued_info=(phase_name == "DISCONTINUED/FAILED"))


def render_landscape(landscape: CompetitiveLandscape):
    """Render the full competitive landscape."""
    st.header(f"Pipeline: {landscape.disease_name}")

    # Summary metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Approved", landscape.approved_count)
    with col2:
        st.metric("Phase 3", landscape.phase3_count)
    with col3:
        st.metric("Phase 2", landscape.phase2_count)
    with col4:
        st.metric("Phase 1", landscape.phase1_count)
    with col5:
        st.metric("Discontinued", landscape.discontinued_count)

    st.divider()

    # Key MOA classes
    if landscape.key_moa_classes:
        st.markdown(f"**Key MOA Classes:** {', '.join(landscape.key_moa_classes[:8])}")

    st.divider()

    # Tabs for different phases
    tabs = st.tabs([
        f"Approved ({landscape.approved_count})",
        f"Phase 3 ({landscape.phase3_count})",
        f"Phase 2 ({landscape.phase2_count})",
        f"Phase 1 ({landscape.phase1_count})",
        f"Discontinued ({landscape.discontinued_count})",
    ])

    with tabs[0]:
        if landscape.approved_drugs:
            for drug in landscape.approved_drugs:
                render_drug_card(drug)
        else:
            st.info("No approved drugs for this indication")

    with tabs[1]:
        if landscape.phase3_drugs:
            for drug in landscape.phase3_drugs:
                render_drug_card(drug)
        else:
            st.info("No Phase 3 drugs")

    with tabs[2]:
        if landscape.phase2_drugs:
            for drug in landscape.phase2_drugs:
                render_drug_card(drug)
        else:
            st.info("No Phase 2 drugs")

    with tabs[3]:
        if landscape.phase1_drugs:
            for drug in landscape.phase1_drugs:
                render_drug_card(drug)
        else:
            st.info("No Phase 1 drugs")

    with tabs[4]:
        if landscape.discontinued_drugs:
            for drug in landscape.discontinued_drugs:
                render_drug_card(drug, show_discontinued_info=True)
        else:
            st.info("No discontinued drugs tracked")

    # Metadata
    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption(f"Trials Reviewed: {landscape.trials_reviewed}")
    with col2:
        st.caption(f"Sources: {', '.join(landscape.sources_searched)}")
    with col3:
        if landscape.search_timestamp:
            st.caption(f"Last Updated: {landscape.search_timestamp.strftime('%Y-%m-%d %H:%M')}")


def render_summary_table(landscape: CompetitiveLandscape):
    """Render a summary table of all drugs."""
    all_drugs = []

    for drug in landscape.approved_drugs:
        all_drugs.append({
            "Drug": drug.brand_name or drug.generic_name,
            "Generic Name": drug.generic_name,
            "Phase": "Approved",
            "Manufacturer": drug.manufacturer or "",
            "MOA": drug.mechanism_of_action or "",
            "Status": "Active"
        })

    for drug in landscape.phase3_drugs:
        all_drugs.append({
            "Drug": drug.brand_name or drug.generic_name,
            "Generic Name": drug.generic_name,
            "Phase": "Phase 3",
            "Manufacturer": drug.manufacturer or "",
            "MOA": drug.mechanism_of_action or "",
            "Status": "Active"
        })

    for drug in landscape.phase2_drugs:
        all_drugs.append({
            "Drug": drug.brand_name or drug.generic_name,
            "Generic Name": drug.generic_name,
            "Phase": "Phase 2",
            "Manufacturer": drug.manufacturer or "",
            "MOA": drug.mechanism_of_action or "",
            "Status": "Active"
        })

    for drug in landscape.phase1_drugs:
        all_drugs.append({
            "Drug": drug.brand_name or drug.generic_name,
            "Generic Name": drug.generic_name,
            "Phase": "Phase 1",
            "Manufacturer": drug.manufacturer or "",
            "MOA": drug.mechanism_of_action or "",
            "Status": "Active"
        })

    for drug in landscape.discontinued_drugs:
        all_drugs.append({
            "Drug": drug.brand_name or drug.generic_name,
            "Generic Name": drug.generic_name,
            "Phase": drug.failure_stage or drug.highest_phase or "N/A",
            "Manufacturer": drug.manufacturer or "",
            "MOA": drug.mechanism_of_action or "",
            "Status": f"Discontinued ({drug.discontinuation_date or 'N/A'})"
        })

    if all_drugs:
        df = pd.DataFrame(all_drugs)
        st.dataframe(df, hide_index=True, use_container_width=True)


def render_past_runs_view():
    """Render a view of all past pipeline runs."""
    st.header("Past Pipeline Runs")

    # Initialize database
    try:
        db = DatabaseConnection(database_url=get_database_url())
        repo = DiseaseIntelligenceRepository(db)
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return

    # Refresh button
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Refresh", key="refresh_all_runs"):
            st.rerun()

    # Get all runs
    runs = repo.get_all_pipeline_runs(limit=100)

    if not runs:
        st.info("No pipeline runs recorded yet. Run a pipeline analysis to get started.")
        return

    # Summary metrics
    st.subheader("Summary")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Total Runs", len(runs))
    with col2:
        unique_diseases = len(set(r.get("disease_name") for r in runs if r.get("disease_name")))
        st.metric("Diseases Analyzed", unique_diseases)
    with col3:
        completed = sum(1 for r in runs if r.get("status") == "completed")
        st.metric("Completed", completed)
    with col4:
        total_drugs = sum(r.get("drugs_found_total") or 0 for r in runs)
        st.metric("Total Drugs Found", total_drugs)
    with col5:
        total_trials = sum(r.get("clinicaltrials_searched") or 0 for r in runs)
        st.metric("Trials Searched", total_trials)

    st.divider()

    # Filter options
    col1, col2 = st.columns(2)
    with col1:
        disease_filter = st.selectbox(
            "Filter by Disease",
            ["All"] + list(set(r.get("disease_name") for r in runs if r.get("disease_name")))
        )
    with col2:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All", "completed", "running", "failed"]
        )

    # Apply filters
    filtered_runs = runs
    if disease_filter != "All":
        filtered_runs = [r for r in filtered_runs if r.get("disease_name") == disease_filter]
    if status_filter != "All":
        filtered_runs = [r for r in filtered_runs if r.get("status") == status_filter]

    # Runs table
    st.subheader(f"Runs ({len(filtered_runs)})")

    if filtered_runs:
        runs_df = pd.DataFrame(filtered_runs)

        # Select and rename columns for display
        display_cols = [
            "run_id", "disease_name", "therapeutic_area", "run_timestamp",
            "run_type", "status", "clinicaltrials_searched", "drugs_found_total",
            "drugs_new", "drugs_updated"
        ]
        display_cols = [c for c in display_cols if c in runs_df.columns]

        rename_map = {
            "run_id": "ID",
            "disease_name": "Disease",
            "therapeutic_area": "Area",
            "run_timestamp": "Timestamp",
            "run_type": "Type",
            "status": "Status",
            "clinicaltrials_searched": "Trials",
            "drugs_found_total": "Drugs",
            "drugs_new": "New",
            "drugs_updated": "Updated"
        }

        df_display = runs_df[display_cols].copy()
        df_display.columns = [rename_map.get(c, c) for c in display_cols]

        # Format timestamp
        if "Timestamp" in df_display.columns:
            df_display["Timestamp"] = pd.to_datetime(df_display["Timestamp"]).dt.strftime("%Y-%m-%d %H:%M")

        # Style status column
        def highlight_status(val):
            colors = {"completed": "background-color: #90EE90", "running": "background-color: #87CEEB", "failed": "background-color: #FFB6C1"}
            return colors.get(val, "")

        st.dataframe(
            df_display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Drugs": st.column_config.NumberColumn("Drugs", format="%d"),
                "Trials": st.column_config.NumberColumn("Trials", format="%d"),
            }
        )

        # Detailed view for selected run
        st.subheader("Run Details")

        # Select a run to view details
        run_ids = [r.get("run_id") for r in filtered_runs]
        selected_run_id = st.selectbox("Select Run to View Details", run_ids, format_func=lambda x: f"Run {x}")

        selected_run = next((r for r in filtered_runs if r.get("run_id") == selected_run_id), None)

        if selected_run:
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**Disease:** {selected_run.get('disease_name', 'N/A')}")
                st.markdown(f"**Therapeutic Area:** {selected_run.get('therapeutic_area', 'N/A')}")
                st.markdown(f"**Run Type:** {selected_run.get('run_type', 'N/A')}")
                st.markdown(f"**Status:** {selected_run.get('status', 'N/A')}")

            with col2:
                st.markdown(f"**ClinicalTrials Searched:** {selected_run.get('clinicaltrials_searched', 0)}")
                st.markdown(f"**Web Sources Searched:** {selected_run.get('web_sources_searched', 0)}")
                st.markdown(f"**Drugs Found:** {selected_run.get('drugs_found_total', 0)}")
                st.markdown(f"**New:** {selected_run.get('drugs_new', 0)} | **Updated:** {selected_run.get('drugs_updated', 0)}")

            if selected_run.get("error_message"):
                st.error(f"Error: {selected_run.get('error_message')}")

            # Get drugs for this disease
            disease_name = selected_run.get("disease_name")
            if disease_name:
                drugs = repo.get_drugs_for_disease(disease_name)
                if drugs:
                    st.subheader(f"Drugs Found ({len(drugs)})")

                    # Group by phase
                    phase_order = ["Approved", "Phase 3", "Phase 2", "Phase 1", "Preclinical"]
                    drugs_by_phase = {}
                    for drug in drugs:
                        phase = drug.get("highest_phase") or "Unknown"
                        if phase not in drugs_by_phase:
                            drugs_by_phase[phase] = []
                        drugs_by_phase[phase].append(drug)

                    # Display in tabs
                    phase_tabs = [p for p in phase_order if p in drugs_by_phase]
                    if "Unknown" in drugs_by_phase:
                        phase_tabs.append("Unknown")

                    if phase_tabs:
                        drug_tabs = st.tabs([f"{p} ({len(drugs_by_phase[p])})" for p in phase_tabs])
                        for i, phase in enumerate(phase_tabs):
                            with drug_tabs[i]:
                                for drug in drugs_by_phase[phase]:
                                    name = drug.get('brand_name') or drug.get('generic_name') or 'Unknown'
                                    generic = drug.get('generic_name') or ''
                                    with st.expander(f"**{name}** ({generic})"):
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.markdown(f"**Manufacturer:** {drug.get('manufacturer') or 'N/A'}")
                                            st.markdown(f"**Type:** {drug.get('drug_type') or 'N/A'}")
                                        with col2:
                                            st.markdown(f"**MOA:** {drug.get('mechanism_of_action') or 'N/A'}")
                                            if drug.get('first_approval_date'):
                                                st.markdown(f"**Approval Date:** {drug.get('first_approval_date')}")
                else:
                    st.info("No drugs found for this disease in the database")

            # Get pipeline sources for this disease
            disease_id = selected_run.get("disease_id")
            if disease_id:
                sources = repo.get_pipeline_sources(disease_id)
                if sources:
                    st.subheader(f"Sources ({len(sources)})")

                    # Group by type
                    source_types = {}
                    for src in sources:
                        stype = src.get("source_type", "unknown")
                        if stype not in source_types:
                            source_types[stype] = []
                        source_types[stype].append(src)

                    for stype, type_sources in source_types.items():
                        with st.expander(f"{stype.replace('_', ' ').title()} ({len(type_sources)})"):
                            for src in type_sources[:10]:
                                title = src.get("title") or src.get("nct_id") or "Untitled"
                                if src.get("nct_id"):
                                    st.markdown(f"- **{title}** ([NCT](https://clinicaltrials.gov/study/{src.get('nct_id')}))")
                                elif src.get("source_url"):
                                    st.markdown(f"- **{title}** ([Link]({src.get('source_url')}))")
                                else:
                                    st.markdown(f"- **{title}**")
    else:
        st.info("No runs match the selected filters")


async def run_pipeline_extraction(disease_name: str, therapeutic_area: str) -> CompetitiveLandscape:
    """Run pipeline extraction asynchronously."""
    db = DatabaseConnection(database_url=get_database_url())
    ct_client = ClinicalTrialsClient()
    openfda_client = OpenFDAClient()
    web_searcher = get_web_searcher()
    llm_client = get_llm_client()

    if not llm_client:
        st.error("LLM client required for extraction")
        return None

    repository = PipelineIntelligenceRepository(db)

    service = PipelineIntelligenceService(
        clinicaltrials_client=ct_client,
        web_searcher=web_searcher,
        llm_client=llm_client,
        repository=repository,
        openfda_client=openfda_client,
    )

    return await service.get_landscape(
        disease_name=disease_name,
        therapeutic_area=therapeutic_area,
        include_web_search=True,
        force_refresh=True,
    )


def main():
    st.title("Pipeline Intelligence")
    st.caption("Competitive landscape analysis by phase")

    # Input section
    with st.sidebar:
        st.header("View Mode")

        view_mode = st.radio(
            "Select View",
            ["Run Analysis", "Past Runs"],
            horizontal=True
        )

        st.divider()

        if view_mode == "Run Analysis":
            st.header("Search Parameters")

            disease_name = st.text_input(
                "Disease Name",
                value="Systemic Lupus Erythematosus",
                placeholder="e.g., Systemic Lupus Erythematosus"
            )

            therapeutic_area = st.selectbox(
                "Therapeutic Area",
                ["Autoimmune", "Oncology", "Neurology", "Cardiology", "Dermatology", "Rare Disease", "Other"]
            )

            run_extraction = st.button("Run Pipeline Analysis", type="primary", use_container_width=True)

            st.divider()

            st.caption("**Note:** Analysis includes:")
            st.caption("- ClinicalTrials.gov (active trials)")
            st.caption("- Web search for news/updates")
            st.caption("- Discontinued program tracking")
            st.caption("- FDA approval verification")
        else:
            disease_name = None
            therapeutic_area = None
            run_extraction = False
            st.caption("View historical pipeline analysis runs")

    # Main content
    if view_mode == "Past Runs":
        render_past_runs_view()
        return

    # Run Analysis mode
    if run_extraction:
        if not disease_name:
            st.error("Please enter a disease name")
            return

        with st.spinner(f"Analyzing pipeline for {disease_name}..."):
            try:
                landscape = asyncio.run(run_pipeline_extraction(disease_name, therapeutic_area))

                if landscape:
                    st.session_state["landscape"] = landscape
                    st.success(f"Found {landscape.total_drugs} active drugs + {landscape.discontinued_count} discontinued")
                else:
                    st.error("Extraction failed")
            except Exception as e:
                st.error(f"Error during extraction: {e}")
                import traceback
                st.code(traceback.format_exc())

    # Display results
    if "landscape" in st.session_state:
        landscape = st.session_state["landscape"]

        # View toggle
        result_view = st.radio(
            "Result View",
            ["Cards by Phase", "Summary Table"],
            horizontal=True
        )

        if result_view == "Cards by Phase":
            render_landscape(landscape)
        else:
            st.subheader(f"All Drugs for {landscape.disease_name}")
            render_summary_table(landscape)

    else:
        st.info("Enter a disease name and click 'Run Pipeline Analysis' to get started")

        # Example diseases
        st.subheader("Example Diseases")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**Autoimmune:**")
            st.markdown("- Systemic Lupus Erythematosus")
            st.markdown("- Rheumatoid Arthritis")
            st.markdown("- Psoriatic Arthritis")

        with col2:
            st.markdown("**Rare Disease:**")
            st.markdown("- Dermatomyositis")
            st.markdown("- Neuromyelitis Optica")
            st.markdown("- IgA Nephropathy")

        with col3:
            st.markdown("**Other:**")
            st.markdown("- Atopic Dermatitis")
            st.markdown("- Ulcerative Colitis")
            st.markdown("- Multiple Sclerosis")


if __name__ == "__main__":
    main()
