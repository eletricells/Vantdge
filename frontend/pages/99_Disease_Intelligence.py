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

from auth import check_password

st.set_page_config(
    page_title="Disease Intelligence",
    page_icon="🏥",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

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


def render_market_funnel(disease: DiseaseIntelligence):
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


def render_treatment_paradigm(disease: DiseaseIntelligence):
    """Render treatment paradigm."""
    st.subheader("Treatment Paradigm")

    tp = disease.treatment_paradigm
    if not tp:
        st.info("No treatment paradigm data available")
        return

    if tp.summary:
        st.markdown(f"**Summary:** {tp.summary}")

    # First line
    if tp.first_line:
        with st.expander("**1L: First-Line Therapy**", expanded=True):
            if tp.first_line.description:
                st.markdown(tp.first_line.description)

            if tp.first_line.drugs:
                drugs_data = []
                for drug in tp.first_line.drugs:
                    drugs_data.append({
                        "Drug": drug.drug_name,
                        "Generic": drug.generic_name or "",
                        "Class": drug.drug_class or "",
                        "SOC": "✓" if drug.is_standard_of_care else "",
                    })
                st.dataframe(pd.DataFrame(drugs_data), hide_index=True)

    # Second line
    if tp.second_line:
        with st.expander("**2L: Second-Line Therapy**", expanded=True):
            if tp.second_line.description:
                st.markdown(tp.second_line.description)

            if tp.second_line.drugs:
                drugs_data = []
                for drug in tp.second_line.drugs:
                    drugs_data.append({
                        "Drug": drug.drug_name,
                        "Generic": drug.generic_name or "",
                        "Class": drug.drug_class or "",
                        "WAC/mo": f"${drug.wac_monthly:,.0f}" if drug.wac_monthly else "",
                    })
                st.dataframe(pd.DataFrame(drugs_data), hide_index=True)


def render_disease_detail(disease: DiseaseIntelligence):
    """Render full disease detail view."""
    st.header(disease.disease_name)

    if disease.therapeutic_area:
        st.caption(f"Therapeutic Area: {disease.therapeutic_area}")

    # Data quality badge
    quality_colors = {"High": "green", "Medium": "orange", "Low": "red"}
    quality = disease.data_quality or "Unknown"
    st.markdown(f"Data Quality: :{quality_colors.get(quality, 'gray')}[{quality}]")

    st.divider()

    # Tabs for different sections
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Market Funnel",
        "Prevalence",
        "Treatment",
        "Failure Rates",
        "Sources"
    ])

    with tab1:
        render_market_funnel(disease)

    with tab2:
        st.subheader("Prevalence Data")
        prev = disease.prevalence

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Patients", format_number(prev.total_patients))
        with col2:
            st.metric("Adults", format_number(prev.adult_patients) if prev.adult_patients else "N/A")
        with col3:
            st.metric("Pediatric", format_number(prev.pediatric_patients) if prev.pediatric_patients else "N/A")

        if prev.prevalence_source:
            st.caption(f"Source: {prev.prevalence_source} ({prev.prevalence_year or 'N/A'})")

        # Segmentation
        st.subheader("Patient Segmentation")
        seg = disease.segmentation

        col1, col2 = st.columns(2)
        with col1:
            if seg.pct_diagnosed:
                st.metric("% Diagnosed", f"{seg.pct_diagnosed:.0f}%")
        with col2:
            if seg.pct_treated:
                st.metric("% Treated", f"{seg.pct_treated:.0f}%")

        if seg.severity:
            st.markdown("**Severity Breakdown:**")
            sev = seg.severity
            sev_data = []
            if sev.mild:
                sev_data.append({"Severity": "Mild", "%": f"{sev.mild:.0f}%"})
            if sev.moderate:
                sev_data.append({"Severity": "Moderate", "%": f"{sev.moderate:.0f}%"})
            if sev.severe:
                sev_data.append({"Severity": "Severe", "%": f"{sev.severe:.0f}%"})
            if sev_data:
                st.dataframe(pd.DataFrame(sev_data), hide_index=True)

    with tab3:
        render_treatment_paradigm(disease)

    with tab4:
        st.subheader("Treatment Failure Rates")
        fr = disease.failure_rates

        col1, col2 = st.columns(2)
        with col1:
            if fr.fail_1L_pct:
                st.metric("Fail 1L", f"{fr.fail_1L_pct:.0f}%")
                if fr.fail_1L_reason:
                    st.caption(f"Reason: {fr.fail_1L_reason}")
        with col2:
            if fr.fail_2L_pct:
                st.metric("Fail 2L", f"{fr.fail_2L_pct:.0f}%")
                if fr.fail_2L_reason:
                    st.caption(f"Reason: {fr.fail_2L_reason}")

        if fr.source:
            st.caption(f"Source: {fr.source}")

    with tab5:
        st.subheader("Data Sources")
        if disease.sources:
            for source in disease.sources:
                with st.expander(f"{source.title or 'Untitled'} ({source.source_type})"):
                    if source.journal:
                        st.caption(f"{source.journal} ({source.publication_year or 'N/A'})")
                    if source.pmid:
                        st.markdown(f"PMID: [{source.pmid}](https://pubmed.ncbi.nlm.nih.gov/{source.pmid})")
                    if source.url:
                        st.markdown(f"URL: [{source.url}]({source.url})")
                    if source.quality_tier:
                        st.caption(f"Quality: {source.quality_tier}")
        else:
            st.info("No sources recorded")


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
            render_disease_detail(disease)

            # Edit/Delete buttons
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("Edit", use_container_width=True):
                    st.session_state["show_form"] = True
                    st.rerun()
            with col2:
                if st.button("Delete", type="secondary", use_container_width=True):
                    if st.session_state.get("confirm_delete"):
                        repo.delete_disease(disease.disease_id)
                        st.success("Deleted")
                        st.session_state["confirm_delete"] = False
                        st.rerun()
                    else:
                        st.session_state["confirm_delete"] = True
                        st.warning("Click Delete again to confirm")
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
