"""
JSON Exporter for Case Series Analysis Results
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

from src.case_series.models import DrugAnalysisResult

logger = logging.getLogger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def export_to_json(
    result: DrugAnalysisResult,
    output_path: str,
    indent: int = 2,
) -> str:
    """
    Export analysis results to JSON file.

    Args:
        result: DrugAnalysisResult to export
        output_path: Output file path
        indent: JSON indentation level

    Returns:
        Path to created file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict
    data = result.model_dump()

    # Write JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, cls=DateTimeEncoder)

    logger.info(f"Exported results to {output_path}")
    return str(output_path)


def export_opportunities_summary(
    result: DrugAnalysisResult,
    output_path: str,
) -> str:
    """
    Export a summary of opportunities to JSON.

    Includes only key fields for each opportunity.

    Args:
        result: DrugAnalysisResult to export
        output_path: Output file path

    Returns:
        Path to created file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        'drug_name': result.drug_name,
        'analysis_date': result.analysis_date.isoformat(),
        'total_opportunities': len(result.opportunities),
        'opportunities': []
    }

    for opp in result.opportunities:
        ext = opp.extraction
        opp_summary = {
            'rank': opp.rank,
            'disease': ext.disease_normalized or ext.disease,
            'scores': {
                'overall': opp.scores.overall_priority,
                'clinical': opp.scores.clinical_signal,
                'evidence': opp.scores.evidence_quality,
                'market': opp.scores.market_opportunity,
            },
            'evidence': {
                'n_patients': ext.patient_population.n_patients,
                'response_rate': ext.efficacy.responders_pct,
                'efficacy_signal': ext.efficacy_signal.value if ext.efficacy_signal else None,
            },
            'source': {
                'pmid': ext.source.pmid,
                'year': ext.source.year,
            }
        }

        if opp.market_intelligence:
            mi = opp.market_intelligence
            opp_summary['market'] = {
                'patient_population': mi.epidemiology.patient_population_size,
                'tam': mi.tam_estimate,
                'approved_drugs': mi.standard_of_care.num_approved_drugs,
                'unmet_need': mi.standard_of_care.unmet_need,
            }

        summary['opportunities'].append(opp_summary)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Exported summary to {output_path}")
    return str(output_path)
