"""
Case Series Browser

Drug-centric view of case series extractions with dynamic scoring.
Browse all case series data by drug, with auto-refresh for stale scores.
"""

import os
import sys
from pathlib import Path

# Add paths for imports
frontend_dir = Path(__file__).parent.parent
project_root = frontend_dir.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO

# Page config
st.set_page_config(
    page_title="Case Series Browser",
    page_icon="📚",
    layout="wide"
)

st.title("Case Series Browser")
st.markdown("Browse case series extractions by drug with dynamic scoring")


def get_service():
    """Get the browser scoring service."""
    from src.case_series.services.browser_scoring_service import BrowserScoringService
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        st.error("DATABASE_URL not configured")
        st.stop()
    return BrowserScoringService(database_url)


def format_score(score: float) -> str:
    """Format score with color indicator."""
    if score >= 7.0:
        return f"🟢 {score:.1f}"
    elif score >= 5.0:
        return f"🟡 {score:.1f}"
    else:
        return f"🔴 {score:.1f}"


def export_to_excel(data: dict) -> BytesIO:
    """Export drug data to Excel file."""
    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Summary sheet
        if data['summaries']:
            df_summary = pd.DataFrame(data['summaries'])
            df_summary.to_excel(writer, sheet_name='Disease Summaries', index=False)

        # Papers sheet
        if data['papers']:
            df_papers = pd.DataFrame(data['papers'])
            df_papers.to_excel(writer, sheet_name='Individual Papers', index=False)

    output.seek(0)
    return output


# Initialize service
service = get_service()

# Get list of drugs
drugs = service.get_drugs_with_extractions()

if not drugs:
    st.warning("No case series extractions found in the database.")
    st.stop()

# Drug selector
drug_options = {d.drug_name: d for d in drugs}
col1, col2 = st.columns([3, 1])

with col1:
    selected_drug_name = st.selectbox(
        "Select Drug",
        options=list(drug_options.keys()),
        format_func=lambda x: f"{x} ({drug_options[x].total_papers} papers, {drug_options[x].disease_count} diseases)"
    )

selected_drug = drug_options[selected_drug_name]

with col2:
    # Refresh button
    needs_refresh = selected_drug.needs_refresh
    refresh_label = "🔄 Refresh Scores" if not needs_refresh else "⚠️ Refresh Scores (Stale)"

    if st.button(refresh_label, type="primary" if needs_refresh else "secondary"):
        with st.spinner(f"Refreshing scores for {selected_drug_name}..."):
            result = service.refresh_scores(selected_drug_name, force=True)
            if result.papers_changed > 0:
                st.success(f"Updated {result.papers_changed} of {result.papers_scored} papers in {result.duration_seconds:.1f}s")
            else:
                st.info(f"All {result.papers_scored} scores are current")
            if result.errors:
                st.warning(f"{len(result.errors)} errors occurred")
            st.rerun()

# Auto-refresh if stale
if needs_refresh:
    st.info("⚠️ Scores may be out of date. Click 'Refresh Scores' to update.")

# Summary metrics
st.markdown("---")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Total Papers", selected_drug.total_papers)
with col2:
    st.metric("Diseases", selected_drug.disease_count)
with col3:
    st.metric("Total Patients", f"{selected_drug.total_patients:,}")
with col4:
    st.metric("Avg Score", f"{selected_drug.avg_disease_score:.1f}/10")
with col5:
    last_scored = selected_drug.last_scored_at
    if last_scored:
        age = datetime.now() - last_scored
        if age.days > 0:
            age_str = f"{age.days}d ago"
        elif age.seconds > 3600:
            age_str = f"{age.seconds // 3600}h ago"
        else:
            age_str = f"{age.seconds // 60}m ago"
    else:
        age_str = "Never"
    st.metric("Last Scored", age_str)

# Filters
st.markdown("---")
col1, col2, col3, col4 = st.columns(4)

with col1:
    min_patients = st.number_input("Min Patients", min_value=0, value=0, step=5)

with col2:
    evidence_options = ['Any', 'RCT', 'Controlled Trial', 'Prospective Cohort', 'Retrospective Study', 'Case Series', 'Case Report']
    evidence_filter = st.selectbox("Evidence Level", options=evidence_options)

with col3:
    sort_options = {
        'Aggregate Score': 'aggregate_score',
        'Total Patients': 'total_patients',
        'Paper Count': 'paper_count',
        'Best Paper Score': 'best_paper_score'
    }
    sort_label = st.selectbox("Sort By", options=list(sort_options.keys()))
    sort_by = sort_options[sort_label]

with col4:
    # Export button
    st.markdown("<br>", unsafe_allow_html=True)
    export_data = service.export_drug_data(selected_drug_name)
    excel_file = export_to_excel(export_data)
    st.download_button(
        "📥 Export to Excel",
        data=excel_file,
        file_name=f"{selected_drug_name}_case_series.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Get disease summaries
summaries = service.get_disease_summaries(
    selected_drug_name,
    min_patients=min_patients,
    evidence_filter=evidence_filter if evidence_filter != 'Any' else None,
    sort_by=sort_by
)

st.markdown("---")
st.subheader(f"Disease Opportunities ({len(summaries)} found)")

if not summaries:
    st.info("No diseases match the current filters.")
else:
    for i, summary in enumerate(summaries):
        # Disease header
        header_col1, header_col2, header_col3 = st.columns([3, 1, 1])

        with header_col1:
            disease_label = summary.disease
            if summary.parent_disease and summary.parent_disease != summary.disease:
                disease_label += f" ({summary.parent_disease})"

        with header_col2:
            score_display = format_score(summary.aggregate_score)

        with header_col3:
            evidence_badge = summary.best_evidence_level

        with st.expander(
            f"**{disease_label}** | {summary.paper_count} papers, N={summary.total_patients:,} | "
            f"Score: {score_display} | {evidence_badge}"
        ):
            # Summary metrics row
            mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)

            with mcol1:
                st.markdown(f"**Aggregate Score:** {summary.aggregate_score:.2f}/10")
            with mcol2:
                st.markdown(f"**Best Paper:** {summary.best_paper_score:.2f}/10")
                if summary.best_paper_pmid:
                    st.markdown(f"[PMID {summary.best_paper_pmid}](https://pubmed.ncbi.nlm.nih.gov/{summary.best_paper_pmid}/)")
            with mcol3:
                resp = f"{summary.avg_response_rate:.1f}%" if summary.avg_response_rate else "N/A"
                st.markdown(f"**Avg Response:** {resp}")
            with mcol4:
                signal = summary.efficacy_signal or "Unknown"
                st.markdown(f"**Efficacy Signal:** {signal}")
            with mcol5:
                st.markdown(f"**Evidence Level:** {summary.best_evidence_level}")

            st.markdown("---")

            # Individual papers
            papers = service.get_disease_papers(selected_drug_name, summary.disease)

            if papers:
                st.markdown("**Individual Papers:**")

                for paper in papers:
                    pcol1, pcol2 = st.columns([4, 1])

                    with pcol1:
                        title = paper['paper_title'][:100] + "..." if paper['paper_title'] and len(paper['paper_title']) > 100 else (paper['paper_title'] or "No title")
                        pmid = paper['pmid']
                        year = paper['paper_year'] or "N/A"
                        n = paper['n_patients'] or "N/A"
                        evidence = paper['evidence_level'] or "N/A"

                        st.markdown(
                            f"**[PMID {pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)** ({year}) - N={n} | {evidence}"
                        )
                        st.markdown(f"*{title}*")

                        # Efficacy summary (truncated)
                        if paper['efficacy_summary']:
                            eff = paper['efficacy_summary'][:300]
                            if len(paper['efficacy_summary']) > 300:
                                eff += "..."
                            st.markdown(f"📊 {eff}")

                    with pcol2:
                        score = paper['individual_score']
                        if score:
                            st.markdown(f"**Score:** {format_score(float(score))}")
                        resp = paper['responders_pct']
                        if resp:
                            st.markdown(f"**Response:** {float(resp):.1f}%")
                        signal = paper['efficacy_signal']
                        if signal:
                            st.markdown(f"**Signal:** {signal}")

                    st.markdown("---")
            else:
                st.info("No papers found for this disease.")

# Footer
st.markdown("---")
st.caption(
    f"Data from {selected_drug.total_papers} case series extractions. "
    f"Scores are N-weighted aggregates. "
    f"Last scored: {selected_drug.last_scored_at.strftime('%Y-%m-%d %H:%M') if selected_drug.last_scored_at else 'Never'}."
)
