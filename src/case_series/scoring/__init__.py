"""
Scoring Engine for Case Series Opportunities

Provides modular, testable scoring components for:
- Clinical signal (response rate, safety, organ domain breadth)
- Evidence quality (sample size, publication venue, durability, completeness)
- Market opportunity (competitors, market size, unmet need)
- Transparent scoring with detailed breakdowns
- Disease-level aggregation with N-weighting
"""

from src.case_series.scoring.scoring_engine import ScoringEngine, ScoringWeights
from src.case_series.scoring.clinical_scorer import ClinicalScorer
from src.case_series.scoring.evidence_scorer import EvidenceScorer
from src.case_series.scoring.market_scorer import MarketScorer
from src.case_series.scoring.scoring_transparency import (
    ScoringRubric,
    ComponentScore,
    CategoryScore,
    DetailedScoreBreakdown,
    DiseaseAggregateScore,
    TransparentScorer,
    DiseaseAggregator,
)

__all__ = [
    "ScoringEngine",
    "ScoringWeights",
    "ClinicalScorer",
    "EvidenceScorer",
    "MarketScorer",
    # Transparency
    "ScoringRubric",
    "ComponentScore",
    "CategoryScore",
    "DetailedScoreBreakdown",
    "DiseaseAggregateScore",
    "TransparentScorer",
    "DiseaseAggregator",
]
