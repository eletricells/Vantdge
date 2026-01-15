"""
Excel Exporter for Case Series Analysis Results
"""

import logging
from pathlib import Path
from typing import List, Dict, Any

from src.case_series.models import DrugAnalysisResult, RepurposingOpportunity

logger = logging.getLogger(__name__)


def export_to_excel(
    result: DrugAnalysisResult,
    output_path: str,
) -> str:
    """
    Export analysis results to Excel file.

    Creates a multi-sheet workbook with:
    - Drug Summary
    - Analysis Summary
    - Opportunities (ranked)
    - Efficacy Endpoints
    - Safety Endpoints
    - Market Intelligence

    Args:
        result: DrugAnalysisResult to export
        output_path: Output file path

    Returns:
        Path to created file
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas is required for Excel export")

    try:
        import openpyxl
    except ImportError:
        raise ImportError("openpyxl is required for Excel export")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Sheet 1: Drug Summary
        drug_summary = pd.DataFrame([{
            'Drug Name': result.drug_name,
            'Generic Name': result.generic_name,
            'Mechanism': result.mechanism,
            'Target': result.target,
            'Approved Indications': '; '.join(result.approved_indications),
            'Analysis Date': result.analysis_date.strftime('%Y-%m-%d'),
        }])
        drug_summary.to_excel(writer, sheet_name='Drug Summary', index=False)

        # Sheet 2: Analysis Summary
        analysis_summary = pd.DataFrame([{
            'Papers Screened': result.papers_screened,
            'Papers Extracted': result.papers_extracted,
            'Opportunities Found': len(result.opportunities),
            'Total Input Tokens': result.total_input_tokens,
            'Total Output Tokens': result.total_output_tokens,
            'Estimated Cost (USD)': result.estimated_cost_usd,
        }])
        analysis_summary.to_excel(writer, sheet_name='Analysis Summary', index=False)

        # Sheet 3: Opportunities
        opportunities_data = []
        for opp in result.opportunities:
            ext = opp.extraction
            opportunities_data.append({
                'Rank': opp.rank,
                'Disease': ext.disease_normalized or ext.disease,
                'Overall Score': opp.scores.overall_priority,
                'Clinical Score': opp.scores.clinical_signal,
                'Evidence Score': opp.scores.evidence_quality,
                'Market Score': opp.scores.market_opportunity,
                'N Patients': ext.patient_population.n_patients,
                'Response Rate': ext.efficacy.response_rate,
                'Primary Endpoint': ext.efficacy.primary_endpoint,
                'Population Type': ext.patient_population.population_type,
                'Refractory': ext.patient_population.is_refractory,
                'Prior Lines': ext.patient_population.prior_therapy_lines,
                'Disease Severity': ext.patient_population.disease_severity,
                'Follow-up': ext.follow_up_duration,
                'PMID': ext.source.pmid,
                'Title': ext.source.title,
                'Year': ext.source.year,
            })

        if opportunities_data:
            opportunities_df = pd.DataFrame(opportunities_data)
            opportunities_df.to_excel(writer, sheet_name='Opportunities', index=False)

        # Sheet 4: Efficacy Endpoints
        efficacy_data = []
        for opp in result.opportunities:
            for ep in opp.extraction.detailed_efficacy_endpoints:
                efficacy_data.append({
                    'Disease': opp.extraction.disease_normalized or opp.extraction.disease,
                    'PMID': opp.extraction.source.pmid,
                    'Endpoint Name': ep.endpoint_name,
                    'Category': ep.endpoint_category,
                    'Responders %': ep.responders_pct,
                    'Change %': ep.change_pct,
                    'Baseline': ep.baseline_value,
                    'Final': ep.final_value,
                    'P-value': ep.p_value,
                    'Organ Domain': ep.organ_domain,
                })

        if efficacy_data:
            efficacy_df = pd.DataFrame(efficacy_data)
            efficacy_df.to_excel(writer, sheet_name='Efficacy Endpoints', index=False)

        # Sheet 5: Safety Endpoints
        safety_data = []
        for opp in result.opportunities:
            for ep in opp.extraction.detailed_safety_endpoints:
                safety_data.append({
                    'Disease': opp.extraction.disease_normalized or opp.extraction.disease,
                    'PMID': opp.extraction.source.pmid,
                    'Event Name': ep.event_name,
                    'Category': ep.event_category,
                    'Patients Affected': ep.patients_affected_n,
                    'Patients Affected %': ep.patients_affected_pct,
                    'Severity': ep.severity_grade,
                    'Outcome': ep.outcome,
                    'SOC Category': ep.category_soc,
                })

        if safety_data:
            safety_df = pd.DataFrame(safety_data)
            safety_df.to_excel(writer, sheet_name='Safety Endpoints', index=False)

        # Sheet 6: Market Intelligence
        market_data = []
        seen_diseases = set()
        for opp in result.opportunities:
            disease = opp.extraction.disease_normalized or opp.extraction.disease
            if disease in seen_diseases or not opp.market_intelligence:
                continue
            seen_diseases.add(disease)

            mi = opp.market_intelligence
            market_data.append({
                'Disease': disease,
                'Patient Population': mi.epidemiology.patient_population_size,
                'US Prevalence': mi.epidemiology.us_prevalence_estimate,
                'Approved Drugs': mi.standard_of_care.num_approved_drugs,
                'Pipeline Drugs': mi.standard_of_care.num_pipeline_therapies,
                'TAM Estimate': mi.tam_estimate,
                'Unmet Need': mi.standard_of_care.unmet_need,
                'Treatment Paradigm': mi.standard_of_care.treatment_paradigm,
            })

        if market_data:
            market_df = pd.DataFrame(market_data)
            market_df.to_excel(writer, sheet_name='Market Intelligence', index=False)

    logger.info(f"Exported results to {output_path}")
    return str(output_path)
