"""
Efficacy Metrics Browser

Browse and compare structured efficacy metrics extracted from case series papers.
Supports multiple metric types: response rates, hazard ratios, biomarker changes, etc.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
from pathlib import Path

# Path setup
frontend_dir = Path(__file__).parent.parent
project_root = frontend_dir.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(project_root))

from auth import check_password, check_page_access, show_access_denied

from dotenv import load_dotenv
load_dotenv()

import os
import psycopg2
from psycopg2.extras import RealDictCursor

st.set_page_config(
    page_title="Efficacy Metrics Browser",
    page_icon="📊",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

# Page access check
if not check_page_access("Efficacy_Metrics_Browser"):
    show_access_denied()

st.title("📊 Efficacy Metrics Browser")
st.markdown("Browse structured efficacy metrics extracted from case series papers.")


def get_connection():
    """Get database connection."""
    return psycopg2.connect(os.getenv('DATABASE_URL'))


@st.cache_data(ttl=300)
def get_drugs_with_metrics():
    """Get list of drugs that have efficacy metrics."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT e.drug_name, COUNT(m.metric_id) as metric_count
                FROM cs_extractions e
                JOIN cs_efficacy_metrics m ON e.id = m.extraction_id
                WHERE e.is_relevant = true
                GROUP BY e.drug_name
                ORDER BY metric_count DESC
            """)
            return [row['drug_name'] for row in cur.fetchall()]
    finally:
        conn.close()


@st.cache_data(ttl=300)
def get_diseases_for_drug(drug_name: str):
    """Get diseases for a specific drug."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT e.disease, COUNT(m.metric_id) as metric_count
                FROM cs_extractions e
                JOIN cs_efficacy_metrics m ON e.id = m.extraction_id
                WHERE LOWER(e.drug_name) = LOWER(%s) AND e.is_relevant = true
                GROUP BY e.disease
                ORDER BY metric_count DESC
            """, (drug_name,))
            return ["All Diseases"] + [row['disease'] for row in cur.fetchall()]
    finally:
        conn.close()


@st.cache_data(ttl=300)
def get_metrics_summary(drug_name: str, disease: str = None):
    """Get summary of metrics by category."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            disease_filter = ""
            params = [drug_name]
            if disease and disease != "All Diseases":
                disease_filter = "AND e.disease = %s"
                params.append(disease)

            cur.execute(f"""
                SELECT
                    m.metric_category,
                    COUNT(*) as count,
                    COUNT(DISTINCT e.pmid) as paper_count,
                    AVG(m.responders_pct) FILTER (WHERE m.responders_pct IS NOT NULL) as avg_response,
                    AVG(m.ratio_value) FILTER (WHERE m.ratio_value IS NOT NULL) as avg_ratio,
                    AVG(m.change_pct) FILTER (WHERE m.change_pct IS NOT NULL) as avg_change_pct,
                    COUNT(*) FILTER (WHERE m.is_statistically_significant = true) as significant_count
                FROM cs_extractions e
                JOIN cs_efficacy_metrics m ON e.id = m.extraction_id
                WHERE LOWER(e.drug_name) = LOWER(%s) AND e.is_relevant = true
                {disease_filter}
                GROUP BY m.metric_category
                ORDER BY count DESC
            """, params)
            return cur.fetchall()
    finally:
        conn.close()


@st.cache_data(ttl=300)
def get_detailed_metrics(drug_name: str, disease: str = None, category: str = None):
    """Get detailed metrics for display."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            filters = ["LOWER(e.drug_name) = LOWER(%s)", "e.is_relevant = true"]
            params = [drug_name]

            if disease and disease != "All Diseases":
                filters.append("e.disease = %s")
                params.append(disease)

            if category and category != "All Categories":
                filters.append("m.metric_category = %s")
                params.append(category)

            cur.execute(f"""
                SELECT
                    e.pmid,
                    e.disease,
                    e.n_patients,
                    e.evidence_level,
                    m.metric_category,
                    m.metric_name,
                    m.endpoint_category,
                    m.responders_n,
                    m.responders_pct,
                    m.total_n,
                    m.ratio_type,
                    m.ratio_value,
                    m.ci_lower,
                    m.ci_upper,
                    m.comparator,
                    m.baseline_value,
                    m.final_value,
                    m.change_pct,
                    m.unit,
                    m.p_value,
                    m.is_statistically_significant,
                    m.timepoint,
                    m.is_biomarker,
                    m.is_primary_endpoint,
                    m.organ_domain
                FROM cs_extractions e
                JOIN cs_efficacy_metrics m ON e.id = m.extraction_id
                WHERE {' AND '.join(filters)}
                ORDER BY m.metric_category, e.n_patients DESC NULLS LAST
            """, params)
            return cur.fetchall()
    finally:
        conn.close()


def format_metric_value(row):
    """Format a metric value for display."""
    # Try response percentage first
    if row.get('responders_pct') is not None:
        n_info = f" ({row['responders_n']}/{row['total_n']})" if row.get('responders_n') and row.get('total_n') else ""
        return f"{row['responders_pct']:.1f}%{n_info}"

    # Try ratio value
    if row.get('ratio_value') is not None:
        ci = f" [{row['ci_lower']:.2f}-{row['ci_upper']:.2f}]" if row.get('ci_lower') and row.get('ci_upper') else ""
        ratio_type = row.get('ratio_type', 'Ratio')
        return f"{ratio_type}={row['ratio_value']:.2f}{ci}"

    # Try change percentage
    if row.get('change_pct') is not None:
        unit = f" {row['unit']}" if row.get('unit') else ""
        if row.get('baseline_value') is not None and row.get('final_value') is not None:
            return f"{row['baseline_value']:.1f} → {row['final_value']:.1f}{unit} ({row['change_pct']:+.1f}%)"
        return f"{row['change_pct']:+.1f}%"

    # Try baseline/final values without change
    if row.get('baseline_value') is not None and row.get('final_value') is not None:
        unit = f" {row['unit']}" if row.get('unit') else ""
        return f"{row['baseline_value']:.1f} → {row['final_value']:.1f}{unit}"

    # Try just final value
    if row.get('final_value') is not None:
        unit = f" {row['unit']}" if row.get('unit') else ""
        return f"{row['final_value']:.1f}{unit}"

    return "—"


def create_response_chart(metrics_df):
    """Create a chart for response rate metrics."""
    response_data = metrics_df[metrics_df['metric_category'] == 'response'].copy()
    if response_data.empty:
        return None

    response_data = response_data[response_data['responders_pct'].notna()]
    if response_data.empty:
        return None

    # Group by disease and endpoint
    grouped = response_data.groupby(['disease', 'metric_name']).agg({
        'responders_pct': 'mean',
        'pmid': 'count'
    }).reset_index()
    grouped.columns = ['Disease', 'Endpoint', 'Response Rate (%)', 'Paper Count']

    fig = px.bar(
        grouped.head(20),
        x='Endpoint',
        y='Response Rate (%)',
        color='Disease',
        title='Response Rates by Endpoint',
        hover_data=['Paper Count']
    )
    fig.update_layout(xaxis_tickangle=-45, height=400)
    return fig


def create_ratio_chart(metrics_df):
    """Create a forest plot style chart for HR/OR metrics."""
    ratio_data = metrics_df[metrics_df['metric_category'] == 'ratio'].copy()
    if ratio_data.empty:
        return None

    ratio_data = ratio_data[ratio_data['ratio_value'].notna()]
    if ratio_data.empty:
        return None

    # Create forest plot
    fig = go.Figure()

    for idx, row in ratio_data.iterrows():
        # Point estimate
        fig.add_trace(go.Scatter(
            x=[row['ratio_value']],
            y=[f"{row['metric_name'][:30]} ({row['disease'][:20]})"],
            mode='markers',
            marker=dict(size=10, color='blue'),
            name=row['pmid'],
            showlegend=False,
            hovertemplate=f"PMID: {row['pmid']}<br>{row['ratio_type']}: {row['ratio_value']:.2f}<br>p={row['p_value']}<extra></extra>"
        ))

        # CI if available
        if row['ci_lower'] and row['ci_upper']:
            fig.add_trace(go.Scatter(
                x=[row['ci_lower'], row['ci_upper']],
                y=[f"{row['metric_name'][:30]} ({row['disease'][:20]})"]*2,
                mode='lines',
                line=dict(color='blue', width=2),
                showlegend=False
            ))

    # Add reference line at 1
    fig.add_vline(x=1, line_dash="dash", line_color="red", annotation_text="No effect")

    fig.update_layout(
        title='Hazard Ratios / Odds Ratios (Forest Plot)',
        xaxis_title='Ratio Value (< 1 favors treatment)',
        height=max(300, len(ratio_data) * 30),
        xaxis_type='log'
    )
    return fig


def create_biomarker_chart(metrics_df):
    """Create a chart for biomarker changes."""
    bio_data = metrics_df[metrics_df['is_biomarker'] == True].copy()
    if bio_data.empty:
        return None

    bio_data = bio_data[bio_data['change_pct'].notna()]
    if bio_data.empty:
        return None

    # Group by biomarker
    grouped = bio_data.groupby('metric_name').agg({
        'change_pct': 'mean',
        'pmid': 'count'
    }).reset_index()
    grouped.columns = ['Biomarker', 'Avg Change (%)', 'Paper Count']
    grouped = grouped.sort_values('Avg Change (%)')

    fig = px.bar(
        grouped,
        x='Avg Change (%)',
        y='Biomarker',
        orientation='h',
        title='Biomarker Changes',
        hover_data=['Paper Count'],
        color='Avg Change (%)',
        color_continuous_scale='RdYlGn_r'
    )
    fig.update_layout(height=max(300, len(grouped) * 25))
    return fig


# Main UI
try:
    drugs = get_drugs_with_metrics()

    if not drugs:
        st.warning("No drugs with efficacy metrics found. Run case series extraction first.")
        st.stop()

    # Sidebar filters
    st.sidebar.header("Filters")
    selected_drug = st.sidebar.selectbox("Select Drug", drugs)

    diseases = get_diseases_for_drug(selected_drug)
    selected_disease = st.sidebar.selectbox("Select Disease", diseases)

    category_options = ["All Categories", "response", "ratio", "change", "biomarker", "survival"]
    selected_category = st.sidebar.selectbox("Metric Category", category_options)

    # Summary metrics
    st.header(f"Efficacy Metrics: {selected_drug}")
    if selected_disease != "All Diseases":
        st.subheader(f"Disease: {selected_disease}")

    summary = get_metrics_summary(selected_drug, selected_disease if selected_disease != "All Diseases" else None)

    if summary:
        # Display summary cards
        cols = st.columns(len(summary))
        for i, row in enumerate(summary):
            with cols[i]:
                cat_name = row['metric_category'].title()
                st.metric(
                    label=cat_name,
                    value=f"{row['count']} metrics",
                    delta=f"{row['paper_count']} papers"
                )

                if row['metric_category'] == 'response' and row['avg_response']:
                    st.caption(f"Avg: {row['avg_response']:.1f}%")
                elif row['metric_category'] == 'ratio' and row['avg_ratio']:
                    st.caption(f"Avg: {row['avg_ratio']:.2f}")
                elif row['avg_change_pct']:
                    st.caption(f"Avg: {row['avg_change_pct']:+.1f}%")

                if row['significant_count']:
                    st.caption(f"✓ {row['significant_count']} significant")

    # Get detailed metrics
    metrics = get_detailed_metrics(
        selected_drug,
        selected_disease if selected_disease != "All Diseases" else None,
        selected_category if selected_category != "All Categories" else None
    )

    if metrics:
        metrics_df = pd.DataFrame(metrics)

        # Tabs for different views
        tab1, tab2, tab3 = st.tabs(["📋 Data Table", "📈 Visualizations", "🔬 Biomarkers"])

        with tab1:
            st.subheader("Detailed Metrics")

            # Format for display
            display_df = metrics_df.copy()
            display_df['Value'] = display_df.apply(format_metric_value, axis=1)
            display_df['Significant'] = display_df['is_statistically_significant'].apply(
                lambda x: "✓" if x else ""
            )
            display_df['Primary'] = display_df['is_primary_endpoint'].apply(
                lambda x: "★" if x else ""
            )

            # Select columns for display
            display_cols = [
                'pmid', 'disease', 'metric_category', 'metric_name',
                'Value', 'p_value', 'Significant', 'Primary',
                'timepoint', 'comparator', 'evidence_level', 'n_patients'
            ]
            display_cols = [c for c in display_cols if c in display_df.columns]

            st.dataframe(
                display_df[display_cols].rename(columns={
                    'pmid': 'PMID',
                    'disease': 'Disease',
                    'metric_category': 'Category',
                    'metric_name': 'Endpoint',
                    'p_value': 'P-value',
                    'timepoint': 'Timepoint',
                    'comparator': 'Comparator',
                    'evidence_level': 'Evidence',
                    'n_patients': 'N'
                }),
                use_container_width=True,
                height=500
            )

            # Download button
            csv = display_df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"{selected_drug}_efficacy_metrics.csv",
                mime="text/csv"
            )

        with tab2:
            st.subheader("Visualizations")

            col1, col2 = st.columns(2)

            with col1:
                # Response rate chart
                response_fig = create_response_chart(metrics_df)
                if response_fig:
                    st.plotly_chart(response_fig, use_container_width=True)
                else:
                    st.info("No response rate data available")

            with col2:
                # Ratio chart (forest plot)
                ratio_fig = create_ratio_chart(metrics_df)
                if ratio_fig:
                    st.plotly_chart(ratio_fig, use_container_width=True)
                else:
                    st.info("No HR/OR data available")

            # Category distribution
            cat_counts = metrics_df['metric_category'].value_counts()
            fig_pie = px.pie(
                values=cat_counts.values,
                names=cat_counts.index,
                title='Metrics by Category'
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with tab3:
            st.subheader("Biomarker Analysis")

            bio_fig = create_biomarker_chart(metrics_df)
            if bio_fig:
                st.plotly_chart(bio_fig, use_container_width=True)
            else:
                st.info("No biomarker data available")

            # Biomarker details table
            bio_data = metrics_df[metrics_df['is_biomarker'] == True]
            if not bio_data.empty:
                st.subheader("Biomarker Details")
                bio_display = bio_data[['pmid', 'disease', 'metric_name', 'baseline_value',
                                        'final_value', 'change_pct', 'unit', 'p_value']].copy()
                bio_display.columns = ['PMID', 'Disease', 'Biomarker', 'Baseline', 'Final',
                                       'Change %', 'Unit', 'P-value']
                st.dataframe(bio_display, use_container_width=True)
    else:
        st.info("No metrics found for the selected filters.")

except Exception as e:
    st.error(f"Error loading data: {str(e)}")
    import traceback
    st.code(traceback.format_exc())
