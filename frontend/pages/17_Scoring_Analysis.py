"""
Scoring Analysis Dashboard

Provides transparent scoring breakdown with:
- Detailed component scores with rubrics
- Disease-level aggregation with N-weighting
- Manual score override capability
- Excel export with formulas
"""

import streamlit as st
import pandas as pd
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys
import io

# Add paths
frontend_dir = Path(__file__).parent.parent
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(project_root))

from auth import check_password

st.set_page_config(
    page_title="Scoring Analysis",
    page_icon="📊",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import after path setup
from src.case_series.scoring import (
    ScoringRubric,
    TransparentScorer,
    DiseaseAggregator,
    DetailedScoreBreakdown,
    DiseaseAggregateScore,
)
from src.case_series.taxonomy import get_default_taxonomy

st.title("📊 Scoring Analysis Dashboard")
st.markdown("""
Transparent scoring breakdown with detailed component scores, disease-level aggregation,
and manual override capability.
""")


# Initialize session state
if 'scoring_data' not in st.session_state:
    st.session_state.scoring_data = []
if 'aggregated_scores' not in st.session_state:
    st.session_state.aggregated_scores = []
if 'score_overrides' not in st.session_state:
    st.session_state.score_overrides = {}

taxonomy = get_default_taxonomy()
scorer = TransparentScorer()


# =============================================================================
# Tab 1: Scoring Rubrics
# =============================================================================

tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Scoring Rubrics",
    "🔢 Score Calculator",
    "📈 Disease Aggregation",
    "📥 Export"
])

with tab1:
    st.header("Scoring Rubrics")
    st.markdown("These are the explicit rules used to calculate each score component.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Sample Size")
        sample_data = []
        for t in ScoringRubric.SAMPLE_SIZE_RUBRIC["thresholds"]:
            sample_data.append({
                "N Patients": f"≥{t['n']}",
                "Score": t['score'],
                "Label": t['label']
            })
        st.dataframe(pd.DataFrame(sample_data), hide_index=True, use_container_width=True)

        st.subheader("Response Rate")
        response_data = []
        for t in ScoringRubric.RESPONSE_RATE_RUBRIC["thresholds"]:
            response_data.append({
                "Response %": f"≥{t['rate']}%",
                "Score": t['score'],
                "Label": t['label']
            })
        st.dataframe(pd.DataFrame(response_data), hide_index=True, use_container_width=True)

    with col2:
        st.subheader("Safety (SAE Rate)")
        safety_data = []
        for t in ScoringRubric.SAFETY_RUBRIC["thresholds"]:
            safety_data.append({
                "SAE %": f"≤{t['sae_pct']}%",
                "Score": t['score'],
                "Label": t['label']
            })
        st.dataframe(pd.DataFrame(safety_data), hide_index=True, use_container_width=True)

        st.subheader("Competitors")
        comp_data = []
        for t in ScoringRubric.COMPETITORS_RUBRIC["thresholds"]:
            comp_data.append({
                "# Drugs": f"≤{t['n_drugs']}",
                "Score": t['score'],
                "Label": t['label']
            })
        st.dataframe(pd.DataFrame(comp_data), hide_index=True, use_container_width=True)

    st.markdown("---")
    st.subheader("Category Weights")
    weight_data = [
        {"Category": "Clinical Signal", "Weight": "50%", "Components": "Response Rate (60%), Safety (30%), Endpoint Quality (10%)"},
        {"Category": "Evidence Quality", "Weight": "25%", "Components": "Sample Size (50%), Follow-up (25%), Publication Venue (25%)"},
        {"Category": "Market Opportunity", "Weight": "25%", "Components": "Unmet Need (40%), Market Size (30%), Competitors (30%)"},
    ]
    st.dataframe(pd.DataFrame(weight_data), hide_index=True, use_container_width=True)

    st.markdown("---")
    st.subheader("N-Confidence Multiplier")
    st.markdown("Scores are adjusted based on total sample size across all studies for a disease.")
    conf_data = [
        {"Total N": "<5", "Confidence": "0.50", "Effect": "50% penalty"},
        {"Total N": "5-9", "Confidence": "0.65", "Effect": "35% penalty"},
        {"Total N": "10-19", "Confidence": "0.75", "Effect": "25% penalty"},
        {"Total N": "20-34", "Confidence": "0.85", "Effect": "15% penalty"},
        {"Total N": "35-49", "Confidence": "0.90", "Effect": "10% penalty"},
        {"Total N": "50-74", "Confidence": "0.95", "Effect": "5% penalty"},
        {"Total N": "75+", "Confidence": "1.00", "Effect": "No penalty"},
    ]
    st.dataframe(pd.DataFrame(conf_data), hide_index=True, use_container_width=True)


# =============================================================================
# Tab 2: Score Calculator
# =============================================================================

with tab2:
    st.header("Score Calculator")
    st.markdown("Enter study data to calculate a detailed score breakdown.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Study Data")
        disease = st.selectbox(
            "Disease",
            options=["Custom..."] + taxonomy.get_all_diseases(),
            index=0
        )
        if disease == "Custom...":
            disease = st.text_input("Enter disease name", value="")

        pmid = st.text_input("PMID (optional)", value="")
        n_patients = st.number_input("Number of Patients", min_value=1, max_value=1000, value=10)
        response_rate = st.slider("Response Rate (%)", 0.0, 100.0, 70.0)

    with col2:
        st.subheader("Safety & Follow-up")
        sae_rate = st.slider("SAE Rate (%)", 0.0, 50.0, 5.0)
        followup_months = st.number_input("Follow-up (months)", min_value=0, max_value=60, value=6)
        publication_type = st.selectbox(
            "Publication Type",
            options=["peer_reviewed", "high_impact", "specialty_journal", "case_report", "conference", "preprint"]
        )

    with col3:
        st.subheader("Market Data")
        n_competitors = st.number_input("Approved Competitors", min_value=0, max_value=20, value=2)
        has_unmet_need = st.checkbox("High Unmet Need", value=False)
        market_size = st.selectbox(
            "Market Size",
            options=["Unknown", "<$100M", "$100M-500M", "$500M-1B", "$1B-2B", "$2B-5B", "$5B-10B", ">$10B"]
        )

    # Convert market size to USD
    market_size_map = {
        "Unknown": None,
        "<$100M": 50_000_000,
        "$100M-500M": 300_000_000,
        "$500M-1B": 750_000_000,
        "$1B-2B": 1_500_000_000,
        "$2B-5B": 3_500_000_000,
        "$5B-10B": 7_500_000_000,
        ">$10B": 15_000_000_000,
    }
    market_size_usd = market_size_map.get(market_size)

    if st.button("Calculate Score", type="primary", use_container_width=True):
        if disease:
            breakdown = scorer.calculate_detailed_breakdown(
                n_patients=n_patients,
                response_rate_pct=response_rate,
                sae_rate_pct=sae_rate,
                followup_months=followup_months,
                publication_type=publication_type,
                n_competitors=n_competitors,
                market_size_usd=market_size_usd,
                has_unmet_need=has_unmet_need,
                pmid=pmid,
                disease=disease,
            )

            # Store in session
            st.session_state.scoring_data.append(breakdown)

            st.success(f"Score calculated: {breakdown.overall_score:.2f}/10")
        else:
            st.error("Please enter a disease name")

    # Display scoring breakdown
    if st.session_state.scoring_data:
        st.markdown("---")
        st.subheader("Score Breakdowns")

        for i, breakdown in enumerate(st.session_state.scoring_data):
            with st.expander(f"**{breakdown.disease}** (n={breakdown.n_patients}) - Score: {breakdown.overall_score:.2f}", expanded=(i == len(st.session_state.scoring_data) - 1)):
                # Overall score
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Overall", f"{breakdown.overall_score:.2f}")
                with col2:
                    st.metric("Clinical", f"{breakdown.clinical_breakdown.category_score:.2f}")
                with col3:
                    st.metric("Evidence", f"{breakdown.evidence_breakdown.category_score:.2f}")
                with col4:
                    st.metric("Market", f"{breakdown.market_breakdown.category_score:.2f}")

                st.markdown("---")

                # Clinical breakdown
                st.markdown("**Clinical Signal (50%)**")
                clinical_df = pd.DataFrame([
                    {
                        "Component": c.component_name,
                        "Raw Value": c.raw_value,
                        "Score": c.score,
                        "Weight": f"{c.weight*100:.0f}%",
                        "Weighted": c.weighted_score,
                        "Explanation": c.explanation,
                    }
                    for c in breakdown.clinical_breakdown.components
                ])
                st.dataframe(clinical_df, hide_index=True, use_container_width=True)

                # Evidence breakdown
                st.markdown("**Evidence Quality (25%)**")
                evidence_df = pd.DataFrame([
                    {
                        "Component": c.component_name,
                        "Raw Value": c.raw_value,
                        "Score": c.score,
                        "Weight": f"{c.weight*100:.0f}%",
                        "Weighted": c.weighted_score,
                        "Explanation": c.explanation,
                    }
                    for c in breakdown.evidence_breakdown.components
                ])
                st.dataframe(evidence_df, hide_index=True, use_container_width=True)

                # Market breakdown
                st.markdown("**Market Opportunity (25%)**")
                market_df = pd.DataFrame([
                    {
                        "Component": c.component_name,
                        "Raw Value": c.raw_value,
                        "Score": c.score,
                        "Weight": f"{c.weight*100:.0f}%",
                        "Weighted": c.weighted_score,
                        "Explanation": c.explanation,
                    }
                    for c in breakdown.market_breakdown.components
                ])
                st.dataframe(market_df, hide_index=True, use_container_width=True)

                # Calculation explanation
                st.markdown("**Calculation:**")
                st.code(breakdown.overall_explanation)

        if st.button("Clear All Scores"):
            st.session_state.scoring_data = []
            st.rerun()


# =============================================================================
# Tab 3: Disease Aggregation
# =============================================================================

with tab3:
    st.header("Disease-Level Aggregation")
    st.markdown("""
    Aggregate scores across multiple studies for the same disease.
    Uses N-weighted averaging and confidence adjustment.
    """)

    if not st.session_state.scoring_data:
        st.info("Add some scores in the Score Calculator tab first.")
    else:
        # Group by disease
        disease_groups: Dict[str, List[DetailedScoreBreakdown]] = {}
        for breakdown in st.session_state.scoring_data:
            disease = breakdown.disease
            if disease not in disease_groups:
                disease_groups[disease] = []
            disease_groups[disease].append(breakdown)

        # Calculate aggregates
        aggregates = []
        for disease, breakdowns in disease_groups.items():
            agg = DiseaseAggregator.aggregate_disease_scores(breakdowns, disease)
            aggregates.append(agg)

        # Sort by adjusted score
        aggregates.sort(key=lambda x: x.adjusted_score, reverse=True)

        # Assign ranks
        for i, agg in enumerate(aggregates):
            agg.rank = i + 1

        st.session_state.aggregated_scores = aggregates

        # Display summary table
        st.subheader("Disease Rankings")

        summary_data = []
        for agg in aggregates:
            summary_data.append({
                "Rank": agg.rank,
                "Disease": agg.disease,
                "Total N": agg.total_patients,
                "Studies": agg.study_count,
                "Response %": f"{agg.weighted_response_rate:.1f}%" if agg.weighted_response_rate else "N/A",
                "SAE %": f"{agg.combined_sae_rate:.1f}%" if agg.combined_sae_rate else "N/A",
                "Clinical": f"{agg.clinical_score:.1f}",
                "Evidence": f"{agg.evidence_score:.1f}",
                "Market": f"{agg.market_score:.1f}",
                "Raw Score": f"{agg.overall_score:.2f}",
                "N-Conf": f"{agg.n_confidence:.2f}",
                "Adjusted": f"{agg.adjusted_score:.2f}",
            })

        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, hide_index=True, use_container_width=True)

        # Score override section
        st.markdown("---")
        st.subheader("Manual Score Override")
        st.markdown("Adjust scores based on domain expertise. Overrides are tracked.")

        override_disease = st.selectbox(
            "Select Disease to Override",
            options=[agg.disease for agg in aggregates]
        )

        if override_disease:
            current_agg = next((a for a in aggregates if a.disease == override_disease), None)
            if current_agg:
                col1, col2, col3 = st.columns(3)

                with col1:
                    new_clinical = st.slider(
                        "Clinical Score Override",
                        1.0, 10.0,
                        current_agg.clinical_score,
                        0.5
                    )
                with col2:
                    new_evidence = st.slider(
                        "Evidence Score Override",
                        1.0, 10.0,
                        current_agg.evidence_score,
                        0.5
                    )
                with col3:
                    new_market = st.slider(
                        "Market Score Override",
                        1.0, 10.0,
                        current_agg.market_score,
                        0.5
                    )

                override_reason = st.text_input("Override Reason", placeholder="e.g., Domain expert adjustment")

                if st.button("Apply Override"):
                    # Calculate new overall
                    new_overall = new_clinical * 0.5 + new_evidence * 0.25 + new_market * 0.25
                    new_adjusted = new_overall * current_agg.n_confidence

                    # Store override
                    st.session_state.score_overrides[override_disease] = {
                        "original_clinical": current_agg.clinical_score,
                        "original_evidence": current_agg.evidence_score,
                        "original_market": current_agg.market_score,
                        "original_overall": current_agg.overall_score,
                        "new_clinical": new_clinical,
                        "new_evidence": new_evidence,
                        "new_market": new_market,
                        "new_overall": new_overall,
                        "new_adjusted": new_adjusted,
                        "reason": override_reason,
                        "timestamp": datetime.now().isoformat(),
                    }

                    st.success(f"Override applied: {current_agg.adjusted_score:.2f} → {new_adjusted:.2f}")

        # Show overrides
        if st.session_state.score_overrides:
            st.markdown("---")
            st.subheader("Active Overrides")

            override_data = []
            for disease, override in st.session_state.score_overrides.items():
                override_data.append({
                    "Disease": disease,
                    "Original Score": f"{override['original_overall']:.2f}",
                    "New Score": f"{override['new_overall']:.2f}",
                    "Reason": override['reason'],
                    "Applied": override['timestamp'][:16],
                })

            st.dataframe(pd.DataFrame(override_data), hide_index=True, use_container_width=True)

            if st.button("Clear All Overrides"):
                st.session_state.score_overrides = {}
                st.rerun()


# =============================================================================
# Tab 4: Export
# =============================================================================

with tab4:
    st.header("Export Scoring Data")

    if not st.session_state.scoring_data:
        st.info("Add some scores first to enable export.")
    else:
        st.subheader("Export Options")

        col1, col2 = st.columns(2)

        with col1:
            # Excel export
            if st.button("Export to Excel", type="primary", use_container_width=True):
                try:
                    output = io.BytesIO()

                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        # Sheet 1: Summary
                        summary_data = []
                        for b in st.session_state.scoring_data:
                            summary_data.append({
                                "PMID": b.pmid or "",
                                "Disease": b.disease,
                                "N Patients": b.n_patients,
                                "Response %": b.response_rate_pct,
                                "SAE %": b.sae_rate_pct,
                                "Follow-up (mo)": b.followup_months,
                                "Clinical Score": b.clinical_breakdown.category_score,
                                "Evidence Score": b.evidence_breakdown.category_score,
                                "Market Score": b.market_breakdown.category_score,
                                "Overall Score": b.overall_score,
                            })
                        pd.DataFrame(summary_data).to_excel(writer, sheet_name="Summary", index=False)

                        # Sheet 2: Detailed Components
                        detail_data = []
                        for b in st.session_state.scoring_data:
                            for comp in b.clinical_breakdown.components:
                                detail_data.append({
                                    "Disease": b.disease,
                                    "Category": "Clinical",
                                    "Component": comp.component_name,
                                    "Raw Value": comp.raw_value,
                                    "Score": comp.score,
                                    "Weight": comp.weight,
                                    "Weighted Score": comp.weighted_score,
                                    "Explanation": comp.explanation,
                                })
                            for comp in b.evidence_breakdown.components:
                                detail_data.append({
                                    "Disease": b.disease,
                                    "Category": "Evidence",
                                    "Component": comp.component_name,
                                    "Raw Value": comp.raw_value,
                                    "Score": comp.score,
                                    "Weight": comp.weight,
                                    "Weighted Score": comp.weighted_score,
                                    "Explanation": comp.explanation,
                                })
                            for comp in b.market_breakdown.components:
                                detail_data.append({
                                    "Disease": b.disease,
                                    "Category": "Market",
                                    "Component": comp.component_name,
                                    "Raw Value": comp.raw_value,
                                    "Score": comp.score,
                                    "Weight": comp.weight,
                                    "Weighted Score": comp.weighted_score,
                                    "Explanation": comp.explanation,
                                })
                        pd.DataFrame(detail_data).to_excel(writer, sheet_name="Components", index=False)

                        # Sheet 3: Aggregated (if available)
                        if st.session_state.aggregated_scores:
                            agg_data = []
                            for agg in st.session_state.aggregated_scores:
                                agg_data.append({
                                    "Rank": agg.rank,
                                    "Disease": agg.disease,
                                    "Total N": agg.total_patients,
                                    "Study Count": agg.study_count,
                                    "Weighted Response %": agg.weighted_response_rate,
                                    "Combined SAE %": agg.combined_sae_rate,
                                    "Clinical Score": agg.clinical_score,
                                    "Evidence Score": agg.evidence_score,
                                    "Market Score": agg.market_score,
                                    "Raw Overall": agg.overall_score,
                                    "N-Confidence": agg.n_confidence,
                                    "Adjusted Score": agg.adjusted_score,
                                })
                            pd.DataFrame(agg_data).to_excel(writer, sheet_name="Aggregated", index=False)

                        # Sheet 4: Rubrics
                        rubric_data = []
                        for t in ScoringRubric.SAMPLE_SIZE_RUBRIC["thresholds"]:
                            rubric_data.append({"Rubric": "Sample Size", "Threshold": f"n≥{t['n']}", "Score": t['score'], "Label": t['label']})
                        for t in ScoringRubric.RESPONSE_RATE_RUBRIC["thresholds"]:
                            rubric_data.append({"Rubric": "Response Rate", "Threshold": f"≥{t['rate']}%", "Score": t['score'], "Label": t['label']})
                        for t in ScoringRubric.SAFETY_RUBRIC["thresholds"]:
                            rubric_data.append({"Rubric": "Safety (SAE)", "Threshold": f"≤{t['sae_pct']}%", "Score": t['score'], "Label": t['label']})
                        pd.DataFrame(rubric_data).to_excel(writer, sheet_name="Rubrics", index=False)

                    output.seek(0)

                    st.download_button(
                        label="Download Excel File",
                        data=output,
                        file_name=f"scoring_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                except Exception as e:
                    st.error(f"Export error: {e}")

        with col2:
            # JSON export
            if st.button("Export to JSON", use_container_width=True):
                import json

                export_data = {
                    "generated_at": datetime.now().isoformat(),
                    "studies": [b.model_dump() for b in st.session_state.scoring_data],
                    "aggregated": [a.model_dump() for a in st.session_state.aggregated_scores],
                    "overrides": st.session_state.score_overrides,
                }

                st.download_button(
                    label="Download JSON File",
                    data=json.dumps(export_data, indent=2, default=str),
                    file_name=f"scoring_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
