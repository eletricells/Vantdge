"""
Aggregation Service

Aggregates evidence across multiple papers for the same disease,
providing pooled estimates with confidence metrics (like V2 agent).
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

from src.case_series.models import (
    CaseSeriesExtraction,
    RepurposingOpportunity,
    OpportunityScores,
)

logger = logging.getLogger(__name__)


@dataclass
class AggregatedEvidence:
    """Aggregated evidence across multiple studies for a disease."""
    disease: str
    n_studies: int
    total_patients: int
    total_responders: int
    pooled_response_pct: Optional[float]
    response_range: Optional[Tuple[float, float]]
    heterogeneity_cv: Optional[float]
    consistency: str  # High, Moderate, Low, Single study, N/A
    evidence_confidence: str  # Moderate, Low-Moderate, Low, Very Low, None

    # Aggregated scores
    avg_clinical_score: float
    avg_evidence_score: float
    avg_market_score: float
    avg_overall_score: float
    best_overall_score: float

    # Source data
    opportunities: List[RepurposingOpportunity]
    pmids: List[str]


def calculate_evidence_confidence(
    n_studies: int,
    total_patients: int,
    consistency: str,
    extractions: List[CaseSeriesExtraction]
) -> str:
    """
    Calculate overall confidence in aggregated evidence.

    Calibrated for case series literature where:
    - 20+ patients is substantial
    - 10+ patients is reasonable
    - <5 patients is very limited

    Levels:
    - Moderate: 3+ studies, 20+ patients, consistent results, some full text
    - Low-Moderate: 3+ studies, 20+ patients, consistent results
    - Low: 2+ studies, 10+ patients
    - Very Low: 1 study or <10 patients
    - None: No valid data
    """
    if n_studies == 0 or total_patients == 0:
        return "None"

    # Check for full text sources (better quality) - use is_open_access as proxy
    has_fulltext = any(
        ext.source and ext.source.is_open_access
        for ext in extractions
        if ext.source
    )

    if n_studies >= 3 and total_patients >= 20:
        if consistency in ['High', 'Moderate'] and has_fulltext:
            return "Moderate"
        elif consistency in ['High', 'Moderate']:
            return "Low-Moderate"
        else:
            return "Low"
    elif n_studies >= 2 and total_patients >= 10:
        return "Low"
    else:
        return "Very Low"


def aggregate_disease_evidence(
    disease: str,
    extractions: List[CaseSeriesExtraction]
) -> Dict[str, Any]:
    """
    Aggregate evidence across multiple papers for the same disease.

    Returns pooled estimates with confidence metrics:
    - Weighted response rate (by sample size)
    - Response range
    - Heterogeneity assessment
    - Evidence confidence level
    """
    if not extractions:
        return {
            'n_studies': 0,
            'total_patients': 0,
            'total_responders': 0,
            'pooled_response_pct': None,
            'response_range': None,
            'heterogeneity_cv': None,
            'consistency': 'N/A',
            'evidence_confidence': 'None'
        }

    # Collect response rates and sample sizes
    response_data = []
    total_patients = 0
    total_responders = 0

    for ext in extractions:
        # Handle None values for n_patients
        n = 0
        if ext.patient_population and ext.patient_population.n_patients is not None:
            n = ext.patient_population.n_patients
        total_patients += n

        resp_pct = ext.efficacy.responders_pct if ext.efficacy else None
        resp_n = ext.efficacy.responders_n if ext.efficacy else None

        if resp_n:
            total_responders += resp_n

        if n > 0 and resp_pct is not None:
            response_data.append({
                'n': n,
                'response_pct': resp_pct
            })

    # Calculate pooled estimate (weighted by sample size)
    pooled_response = None
    response_range = None
    heterogeneity_cv = None
    consistency = 'N/A'

    if response_data:
        # Weighted average
        total_weight = sum(d['n'] for d in response_data)
        if total_weight > 0:
            pooled_response = sum(
                d['response_pct'] * d['n'] for d in response_data
            ) / total_weight

        # Range
        rates = [d['response_pct'] for d in response_data]
        response_range = (min(rates), max(rates))

        # Heterogeneity (coefficient of variation)
        if len(rates) >= 2:
            mean_rate = sum(rates) / len(rates)
            if mean_rate > 0:
                variance = sum((r - mean_rate) ** 2 for r in rates) / len(rates)
                heterogeneity_cv = (variance ** 0.5) / mean_rate

                # Classify consistency
                if heterogeneity_cv < 0.25:
                    consistency = 'High'
                elif heterogeneity_cv < 0.50:
                    consistency = 'Moderate'
                else:
                    consistency = 'Low'
        elif len(rates) == 1:
            consistency = 'Single study'

    # Determine evidence confidence
    n_studies = len(extractions)
    evidence_confidence = calculate_evidence_confidence(
        n_studies, total_patients, consistency, extractions
    )

    return {
        'n_studies': n_studies,
        'total_patients': total_patients,
        'total_responders': total_responders,
        'pooled_response_pct': round(pooled_response, 1) if pooled_response else None,
        'response_range': response_range,
        'heterogeneity_cv': round(heterogeneity_cv, 2) if heterogeneity_cv else None,
        'consistency': consistency,
        'evidence_confidence': evidence_confidence
    }


def aggregate_opportunities_by_disease(
    opportunities: List[RepurposingOpportunity]
) -> List[AggregatedEvidence]:
    """
    Aggregate opportunities by disease, combining evidence from multiple papers.

    Args:
        opportunities: List of individual opportunities (one per paper)

    Returns:
        List of AggregatedEvidence objects, sorted by avg_overall_score descending
    """
    if not opportunities:
        return []

    # Group by disease
    disease_groups: Dict[str, List[RepurposingOpportunity]] = {}
    for opp in opportunities:
        disease = opp.extraction.disease_normalized or opp.extraction.disease or 'Unknown'
        if disease not in disease_groups:
            disease_groups[disease] = []
        disease_groups[disease].append(opp)

    # Aggregate each disease
    aggregated = []
    for disease, opps in disease_groups.items():
        extractions = [opp.extraction for opp in opps]

        # Get evidence aggregation
        evidence = aggregate_disease_evidence(disease, extractions)

        # Calculate aggregated scores
        valid_opps = [o for o in opps if o.scores]
        if valid_opps:
            avg_clinical = sum(o.scores.clinical_signal for o in valid_opps) / len(valid_opps)
            avg_evidence = sum(o.scores.evidence_quality for o in valid_opps) / len(valid_opps)
            avg_market = sum(o.scores.market_opportunity for o in valid_opps) / len(valid_opps)
            avg_overall = sum(o.scores.overall_priority for o in valid_opps) / len(valid_opps)
            best_overall = max(o.scores.overall_priority for o in valid_opps)
        else:
            avg_clinical = avg_evidence = avg_market = avg_overall = best_overall = 0.0

        # Collect paper identifiers (PMIDs or DOI-based IDs as fallback)
        pmids = []
        for opp in opps:
            if opp.extraction.source:
                if opp.extraction.source.pmid:
                    pmids.append(opp.extraction.source.pmid)
                elif opp.extraction.source.doi:
                    # Use DOI as fallback identifier
                    pmids.append(f"DOI:{opp.extraction.source.doi}")

        aggregated.append(AggregatedEvidence(
            disease=disease,
            n_studies=evidence['n_studies'],
            total_patients=evidence['total_patients'],
            total_responders=evidence['total_responders'],
            pooled_response_pct=evidence['pooled_response_pct'],
            response_range=evidence['response_range'],
            heterogeneity_cv=evidence['heterogeneity_cv'],
            consistency=evidence['consistency'],
            evidence_confidence=evidence['evidence_confidence'],
            avg_clinical_score=round(avg_clinical, 1),
            avg_evidence_score=round(avg_evidence, 1),
            avg_market_score=round(avg_market, 1),
            avg_overall_score=round(avg_overall, 1),
            best_overall_score=round(best_overall, 1),
            opportunities=opps,
            pmids=pmids,
        ))

    # Sort by average overall score
    aggregated.sort(key=lambda x: x.avg_overall_score, reverse=True)

    # Assign ranks
    for i, agg in enumerate(aggregated, 1):
        agg.rank = i

    logger.info(f"Aggregated {len(opportunities)} opportunities into {len(aggregated)} disease groups")
    return aggregated


# =============================================================================
# Hierarchical Aggregation (for UI drill-down)
# =============================================================================

@dataclass
class HierarchicalAggregation:
    """
    Aggregated evidence with parent-child disease hierarchy.

    Used for UI display where diseases are grouped under parent categories.
    """
    parent_disease: str
    parent_evidence: AggregatedEvidence  # Aggregate across all children
    children: List[AggregatedEvidence]   # Per-child disease aggregations
    child_count: int
    total_papers: int
    total_patients: int

    # For display
    is_single_disease: bool = False  # True if parent has no distinct children


def aggregate_with_hierarchy(
    opportunities: List[RepurposingOpportunity],
    disease_standardizer: Any,  # DiseaseStandardizer - avoid circular import
) -> List[HierarchicalAggregation]:
    """
    Aggregate opportunities with parent-child disease hierarchy.

    Groups diseases by parent, then aggregates children under parents.
    Each parent gets a combined AggregatedEvidence from all children.

    Args:
        opportunities: List of opportunities
        disease_standardizer: DiseaseStandardizer for parent lookup

    Returns:
        List of HierarchicalAggregation sorted by parent score descending
    """
    if not opportunities:
        return []

    # Step 1: Group opportunities by normalized disease
    disease_opps: Dict[str, List[RepurposingOpportunity]] = {}
    for opp in opportunities:
        disease = opp.extraction.disease_normalized or opp.extraction.disease or 'Unknown'
        if disease not in disease_opps:
            disease_opps[disease] = []
        disease_opps[disease].append(opp)

    # Step 2: Get child aggregations for each disease
    child_aggregations: Dict[str, AggregatedEvidence] = {}
    for disease, opps in disease_opps.items():
        agg_list = aggregate_opportunities_by_disease(opps)
        if agg_list:
            child_aggregations[disease] = agg_list[0]

    # Step 3: Group by parent disease
    parent_children: Dict[str, List[str]] = {}
    disease_to_parent: Dict[str, str] = {}

    for disease in child_aggregations.keys():
        parent = disease_standardizer.get_parent_disease(disease)
        disease_to_parent[disease] = parent

        if parent not in parent_children:
            parent_children[parent] = []
        if disease not in parent_children[parent]:
            parent_children[parent].append(disease)

    # Step 4: Build hierarchical aggregations
    hierarchical: List[HierarchicalAggregation] = []

    for parent, child_diseases in parent_children.items():
        children = [child_aggregations[d] for d in child_diseases if d in child_aggregations]

        if not children:
            continue

        # Create parent-level aggregate by combining all child opportunities
        all_opps = []
        for d in child_diseases:
            if d in disease_opps:
                all_opps.extend(disease_opps[d])

        parent_agg_list = aggregate_opportunities_by_disease(all_opps)
        if not parent_agg_list:
            continue

        parent_evidence = parent_agg_list[0]
        # Override disease name to be the parent
        parent_evidence.disease = parent

        # Determine if this is effectively a single disease
        # (parent equals child or only one unique child that matches parent)
        unique_children = set(d.lower() for d in child_diseases)
        is_single = len(unique_children) == 1 and (
            parent.lower() in unique_children or
            list(unique_children)[0] == parent.lower()
        )

        hierarchical.append(HierarchicalAggregation(
            parent_disease=parent,
            parent_evidence=parent_evidence,
            children=children,
            child_count=len(children),
            total_papers=sum(c.n_studies for c in children),
            total_patients=sum(c.total_patients for c in children),
            is_single_disease=is_single,
        ))

    # Sort by parent avg_overall_score descending
    hierarchical.sort(key=lambda x: x.parent_evidence.avg_overall_score, reverse=True)

    # Assign ranks
    for i, h in enumerate(hierarchical, 1):
        h.parent_evidence.rank = i

    logger.info(
        f"Built hierarchical aggregation: {len(hierarchical)} parent groups "
        f"from {len(child_aggregations)} diseases"
    )

    return hierarchical


def get_disease_aggregations_dict(
    opportunities: List[RepurposingOpportunity],
) -> Dict[str, AggregatedEvidence]:
    """
    Get disease aggregations as a dictionary.

    Convenience method for score explanation service.

    Args:
        opportunities: List of opportunities

    Returns:
        Dict mapping disease -> AggregatedEvidence
    """
    aggregated = aggregate_opportunities_by_disease(opportunities)
    return {agg.disease: agg for agg in aggregated}


def get_opportunities_by_disease(
    opportunities: List[RepurposingOpportunity],
) -> Dict[str, List[RepurposingOpportunity]]:
    """
    Group opportunities by disease.

    Convenience method for score explanation service.

    Args:
        opportunities: List of opportunities

    Returns:
        Dict mapping disease -> list of opportunities
    """
    result: Dict[str, List[RepurposingOpportunity]] = {}
    for opp in opportunities:
        disease = opp.extraction.disease_normalized or opp.extraction.disease or 'Unknown'
        if disease not in result:
            result[disease] = []
        result[disease].append(opp)
    return result
