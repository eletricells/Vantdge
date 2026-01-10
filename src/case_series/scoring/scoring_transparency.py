"""
Scoring Transparency Module

Provides detailed breakdown of all scoring components with:
- Explicit rubrics and formulas
- Component-level scores with explanations
- Disease-level aggregation
- Support for manual overrides
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# Scoring Rubrics (Explicit Rules)
# =============================================================================

class ScoringRubric:
    """
    Explicit scoring rubrics for all components.

    All scores are on a 1-10 scale.
    These rules are shown to users for transparency.
    """

    # Sample Size Rubric
    SAMPLE_SIZE_RUBRIC = {
        "description": "Score based on total number of patients",
        "formula": "Logarithmic scale with thresholds",
        "thresholds": [
            {"n": 1, "score": 3.0, "label": "Single case report"},
            {"n": 2, "score": 4.0, "label": "2 patients"},
            {"n": 3, "score": 5.0, "label": "3-4 patients"},
            {"n": 5, "score": 6.0, "label": "5-7 patients"},
            {"n": 8, "score": 7.0, "label": "8-10 patients"},
            {"n": 11, "score": 8.0, "label": "11-15 patients"},
            {"n": 16, "score": 9.0, "label": "16-24 patients"},
            {"n": 25, "score": 10.0, "label": "25+ patients"},
        ],
    }

    # Response Rate Rubric
    RESPONSE_RATE_RUBRIC = {
        "description": "Score based on percentage of responders",
        "formula": "Linear mapping with bonus for high rates",
        "thresholds": [
            {"rate": 0, "score": 1.0, "label": "No responders"},
            {"rate": 20, "score": 3.0, "label": "<20% response"},
            {"rate": 30, "score": 4.0, "label": "20-30% response"},
            {"rate": 40, "score": 5.0, "label": "30-40% response"},
            {"rate": 50, "score": 6.0, "label": "40-50% response"},
            {"rate": 60, "score": 7.0, "label": "50-60% response"},
            {"rate": 70, "score": 8.0, "label": "60-70% response"},
            {"rate": 80, "score": 9.0, "label": "70-80% response"},
            {"rate": 90, "score": 10.0, "label": "80%+ response"},
        ],
    }

    # Safety (SAE Rate) Rubric
    SAFETY_RUBRIC = {
        "description": "Score based on serious adverse event rate (lower is better)",
        "formula": "Inverse linear scale",
        "thresholds": [
            {"sae_pct": 0, "score": 10.0, "label": "No SAEs"},
            {"sae_pct": 2, "score": 9.0, "label": "<2% SAE"},
            {"sae_pct": 5, "score": 8.0, "label": "2-5% SAE"},
            {"sae_pct": 10, "score": 6.0, "label": "5-10% SAE"},
            {"sae_pct": 15, "score": 4.0, "label": "10-15% SAE"},
            {"sae_pct": 20, "score": 3.0, "label": "15-20% SAE"},
            {"sae_pct": 30, "score": 2.0, "label": "20-30% SAE"},
            {"sae_pct": 50, "score": 1.0, "label": ">30% SAE"},
        ],
    }

    # Follow-up Duration Rubric
    FOLLOWUP_RUBRIC = {
        "description": "Score based on follow-up duration",
        "formula": "Threshold-based",
        "thresholds": [
            {"months": 0, "score": 3.0, "label": "No follow-up"},
            {"months": 1, "score": 5.0, "label": "1 month"},
            {"months": 3, "score": 6.0, "label": "3 months"},
            {"months": 6, "score": 7.0, "label": "6 months"},
            {"months": 12, "score": 9.0, "label": "12 months"},
            {"months": 24, "score": 10.0, "label": "24+ months"},
        ],
    }

    # Publication Venue Rubric
    VENUE_RUBRIC = {
        "description": "Score based on publication type and journal quality",
        "formula": "Categorical",
        "categories": [
            {"type": "preprint", "score": 4.0, "label": "Preprint"},
            {"type": "conference", "score": 5.0, "label": "Conference abstract"},
            {"type": "case_report", "score": 6.0, "label": "Case report journal"},
            {"type": "specialty_journal", "score": 7.0, "label": "Specialty journal"},
            {"type": "peer_reviewed", "score": 8.0, "label": "Peer-reviewed journal"},
            {"type": "high_impact", "score": 10.0, "label": "High-impact journal"},
        ],
    }

    # Market Size Rubric
    MARKET_SIZE_RUBRIC = {
        "description": "Score based on estimated market size (TAM)",
        "formula": "Logarithmic scale",
        "thresholds": [
            {"tam_usd": 0, "score": 1.0, "label": "Unknown"},
            {"tam_usd": 100_000_000, "score": 4.0, "label": "<$100M"},
            {"tam_usd": 500_000_000, "score": 5.0, "label": "$100M-500M"},
            {"tam_usd": 1_000_000_000, "score": 6.0, "label": "$500M-1B"},
            {"tam_usd": 2_000_000_000, "score": 7.0, "label": "$1B-2B"},
            {"tam_usd": 5_000_000_000, "score": 8.0, "label": "$2B-5B"},
            {"tam_usd": 10_000_000_000, "score": 9.0, "label": "$5B-10B"},
            {"tam_usd": 20_000_000_000, "score": 10.0, "label": ">$10B"},
        ],
    }

    # Competitors Rubric
    COMPETITORS_RUBRIC = {
        "description": "Score based on number of approved competitors (fewer is better)",
        "formula": "Inverse scale",
        "thresholds": [
            {"n_drugs": 0, "score": 10.0, "label": "No approved drugs"},
            {"n_drugs": 1, "score": 9.0, "label": "1 approved drug"},
            {"n_drugs": 2, "score": 7.0, "label": "2 approved drugs"},
            {"n_drugs": 3, "score": 6.0, "label": "3 approved drugs"},
            {"n_drugs": 5, "score": 5.0, "label": "4-5 approved drugs"},
            {"n_drugs": 8, "score": 3.0, "label": "6-8 approved drugs"},
            {"n_drugs": 10, "score": 2.0, "label": "8+ approved drugs"},
        ],
    }

    @classmethod
    def get_sample_size_score(cls, n_patients: int) -> Tuple[float, str]:
        """Calculate sample size score with explanation."""
        for threshold in reversed(cls.SAMPLE_SIZE_RUBRIC["thresholds"]):
            if n_patients >= threshold["n"]:
                return threshold["score"], threshold["label"]
        return 1.0, "No data"

    @classmethod
    def get_response_rate_score(cls, response_pct: float) -> Tuple[float, str]:
        """Calculate response rate score with explanation."""
        if response_pct is None:
            return 5.0, "No response data"
        for threshold in reversed(cls.RESPONSE_RATE_RUBRIC["thresholds"]):
            if response_pct >= threshold["rate"]:
                return threshold["score"], threshold["label"]
        return 1.0, "No responders"

    @classmethod
    def get_safety_score(cls, sae_pct: float) -> Tuple[float, str]:
        """Calculate safety score with explanation."""
        if sae_pct is None:
            return 5.0, "No safety data"
        for threshold in cls.SAFETY_RUBRIC["thresholds"]:
            if sae_pct <= threshold["sae_pct"]:
                return threshold["score"], threshold["label"]
        return 1.0, "High SAE rate"

    @classmethod
    def get_followup_score(cls, months: int) -> Tuple[float, str]:
        """Calculate follow-up duration score with explanation."""
        if months is None or months == 0:
            return 3.0, "No follow-up data"
        for threshold in reversed(cls.FOLLOWUP_RUBRIC["thresholds"]):
            if months >= threshold["months"]:
                return threshold["score"], threshold["label"]
        return 3.0, "Unknown follow-up"

    @classmethod
    def get_competitors_score(cls, n_drugs: int) -> Tuple[float, str]:
        """Calculate competitors score with explanation."""
        if n_drugs is None:
            return 5.0, "Unknown competition"
        for threshold in cls.COMPETITORS_RUBRIC["thresholds"]:
            if n_drugs <= threshold["n_drugs"]:
                return threshold["score"], threshold["label"]
        return 2.0, "Many competitors"


# =============================================================================
# Detailed Score Breakdown Models
# =============================================================================

class ComponentScore(BaseModel):
    """Individual component score with explanation."""
    component_name: str = Field(..., description="Name of scoring component")
    raw_value: Optional[Any] = Field(None, description="Raw input value")
    score: float = Field(..., description="Score (1-10)")
    weight: float = Field(1.0, description="Weight applied to this component")
    weighted_score: float = Field(..., description="Score * weight")
    explanation: str = Field("", description="Human-readable explanation")
    rubric_used: str = Field("", description="Name of rubric applied")
    is_overridden: bool = Field(False, description="Whether manually overridden")
    override_reason: Optional[str] = Field(None, description="Reason for override")


class CategoryScore(BaseModel):
    """Category-level score aggregating multiple components."""
    category_name: str = Field(..., description="Category name (Clinical/Evidence/Market)")
    components: List[ComponentScore] = Field(default_factory=list)
    category_score: float = Field(..., description="Aggregated category score")
    category_weight: float = Field(..., description="Weight in overall score")
    weighted_category_score: float = Field(..., description="Category score * weight")


class DetailedScoreBreakdown(BaseModel):
    """Complete scoring breakdown for transparency."""
    # Identification
    pmid: Optional[str] = Field(None)
    disease: str = Field(...)
    disease_normalized: Optional[str] = Field(None)

    # Raw inputs
    n_patients: int = Field(0)
    response_rate_pct: Optional[float] = Field(None)
    sae_rate_pct: Optional[float] = Field(None)
    followup_months: Optional[int] = Field(None)
    n_competitors: Optional[int] = Field(None)
    market_size_usd: Optional[float] = Field(None)

    # Category breakdowns
    clinical_breakdown: CategoryScore
    evidence_breakdown: CategoryScore
    market_breakdown: CategoryScore

    # Overall
    overall_score: float = Field(...)
    overall_explanation: str = Field("")

    # Override tracking
    has_overrides: bool = Field(False)
    override_history: List[Dict[str, Any]] = Field(default_factory=list)


class DiseaseAggregateScore(BaseModel):
    """
    Aggregated score at the disease level.

    Combines multiple extractions for the same disease.
    """
    disease: str = Field(...)
    disease_normalized: str = Field(...)
    disease_category: Optional[str] = Field(None)

    # Aggregation metrics
    total_patients: int = Field(0, description="Sum of patients across all studies")
    study_count: int = Field(0, description="Number of studies/extractions")
    weighted_response_rate: Optional[float] = Field(None, description="N-weighted response rate")
    combined_sae_rate: Optional[float] = Field(None, description="N-weighted SAE rate")

    # Individual study breakdowns
    study_breakdowns: List[DetailedScoreBreakdown] = Field(default_factory=list)

    # Aggregated scores
    clinical_score: float = Field(5.0)
    evidence_score: float = Field(5.0)
    market_score: float = Field(5.0)
    overall_score: float = Field(5.0)

    # Confidence adjustment
    n_confidence: float = Field(1.0, description="Confidence multiplier based on total N")
    adjusted_score: float = Field(5.0, description="Overall score * n_confidence")

    # Rank
    rank: int = Field(0)

    # Override tracking
    has_overrides: bool = Field(False)


# =============================================================================
# Score Calculator with Transparency
# =============================================================================

class TransparentScorer:
    """
    Scorer that produces detailed breakdowns for transparency.

    All calculations are explicit and explainable.
    """

    # Default weights
    CLINICAL_WEIGHT = 0.50
    EVIDENCE_WEIGHT = 0.25
    MARKET_WEIGHT = 0.25

    # Clinical sub-weights
    RESPONSE_RATE_WEIGHT = 0.60
    SAFETY_WEIGHT = 0.30
    ENDPOINT_QUALITY_WEIGHT = 0.10

    # Evidence sub-weights
    SAMPLE_SIZE_WEIGHT = 0.50
    FOLLOWUP_WEIGHT = 0.25
    VENUE_WEIGHT = 0.25

    # Market sub-weights
    UNMET_NEED_WEIGHT = 0.40
    MARKET_SIZE_WEIGHT = 0.30
    COMPETITORS_WEIGHT = 0.30

    def __init__(
        self,
        clinical_weight: float = CLINICAL_WEIGHT,
        evidence_weight: float = EVIDENCE_WEIGHT,
        market_weight: float = MARKET_WEIGHT,
    ):
        """Initialize with custom weights."""
        self.clinical_weight = clinical_weight
        self.evidence_weight = evidence_weight
        self.market_weight = market_weight

    def calculate_detailed_breakdown(
        self,
        n_patients: int,
        response_rate_pct: Optional[float],
        sae_rate_pct: Optional[float],
        followup_months: Optional[int],
        publication_type: str = "peer_reviewed",
        n_competitors: Optional[int] = None,
        market_size_usd: Optional[float] = None,
        has_unmet_need: bool = False,
        pmid: Optional[str] = None,
        disease: str = "",
    ) -> DetailedScoreBreakdown:
        """
        Calculate detailed score breakdown with all components.

        Returns complete breakdown showing how final score was calculated.
        """

        # Clinical components
        response_score, response_expl = ScoringRubric.get_response_rate_score(response_rate_pct)
        safety_score, safety_expl = ScoringRubric.get_safety_score(sae_rate_pct)

        clinical_components = [
            ComponentScore(
                component_name="Response Rate",
                raw_value=response_rate_pct,
                score=response_score,
                weight=self.RESPONSE_RATE_WEIGHT,
                weighted_score=response_score * self.RESPONSE_RATE_WEIGHT,
                explanation=f"{response_rate_pct:.0f}% response rate → {response_expl}" if response_rate_pct else "No response data",
                rubric_used="RESPONSE_RATE_RUBRIC",
            ),
            ComponentScore(
                component_name="Safety Profile",
                raw_value=sae_rate_pct,
                score=safety_score,
                weight=self.SAFETY_WEIGHT,
                weighted_score=safety_score * self.SAFETY_WEIGHT,
                explanation=f"{sae_rate_pct:.1f}% SAE rate → {safety_expl}" if sae_rate_pct is not None else "No safety data",
                rubric_used="SAFETY_RUBRIC",
            ),
        ]

        clinical_score = sum(c.weighted_score for c in clinical_components) / sum(c.weight for c in clinical_components)
        clinical_breakdown = CategoryScore(
            category_name="Clinical Signal",
            components=clinical_components,
            category_score=clinical_score,
            category_weight=self.clinical_weight,
            weighted_category_score=clinical_score * self.clinical_weight,
        )

        # Evidence components
        sample_score, sample_expl = ScoringRubric.get_sample_size_score(n_patients)
        followup_score, followup_expl = ScoringRubric.get_followup_score(followup_months)
        venue_score = 8.0  # Default for peer-reviewed

        evidence_components = [
            ComponentScore(
                component_name="Sample Size",
                raw_value=n_patients,
                score=sample_score,
                weight=self.SAMPLE_SIZE_WEIGHT,
                weighted_score=sample_score * self.SAMPLE_SIZE_WEIGHT,
                explanation=f"n={n_patients} → {sample_expl}",
                rubric_used="SAMPLE_SIZE_RUBRIC",
            ),
            ComponentScore(
                component_name="Follow-up Duration",
                raw_value=followup_months,
                score=followup_score,
                weight=self.FOLLOWUP_WEIGHT,
                weighted_score=followup_score * self.FOLLOWUP_WEIGHT,
                explanation=f"{followup_months} months → {followup_expl}" if followup_months else "Unknown follow-up",
                rubric_used="FOLLOWUP_RUBRIC",
            ),
            ComponentScore(
                component_name="Publication Venue",
                raw_value=publication_type,
                score=venue_score,
                weight=self.VENUE_WEIGHT,
                weighted_score=venue_score * self.VENUE_WEIGHT,
                explanation=f"{publication_type}",
                rubric_used="VENUE_RUBRIC",
            ),
        ]

        evidence_score = sum(c.weighted_score for c in evidence_components) / sum(c.weight for c in evidence_components)
        evidence_breakdown = CategoryScore(
            category_name="Evidence Quality",
            components=evidence_components,
            category_score=evidence_score,
            category_weight=self.evidence_weight,
            weighted_category_score=evidence_score * self.evidence_weight,
        )

        # Market components
        competitors_score, competitors_expl = ScoringRubric.get_competitors_score(n_competitors)
        unmet_need_score = 10.0 if has_unmet_need else 5.0
        market_size_score = 5.0  # Default

        if market_size_usd:
            for threshold in reversed(ScoringRubric.MARKET_SIZE_RUBRIC["thresholds"]):
                if market_size_usd >= threshold["tam_usd"]:
                    market_size_score = threshold["score"]
                    break

        market_components = [
            ComponentScore(
                component_name="Unmet Need",
                raw_value=has_unmet_need,
                score=unmet_need_score,
                weight=self.UNMET_NEED_WEIGHT,
                weighted_score=unmet_need_score * self.UNMET_NEED_WEIGHT,
                explanation="High unmet need" if has_unmet_need else "Existing treatments available",
                rubric_used="UNMET_NEED",
            ),
            ComponentScore(
                component_name="Competitors",
                raw_value=n_competitors,
                score=competitors_score,
                weight=self.COMPETITORS_WEIGHT,
                weighted_score=competitors_score * self.COMPETITORS_WEIGHT,
                explanation=f"{n_competitors} approved drugs → {competitors_expl}" if n_competitors is not None else "Unknown",
                rubric_used="COMPETITORS_RUBRIC",
            ),
            ComponentScore(
                component_name="Market Size",
                raw_value=market_size_usd,
                score=market_size_score,
                weight=self.MARKET_SIZE_WEIGHT,
                weighted_score=market_size_score * self.MARKET_SIZE_WEIGHT,
                explanation=f"${market_size_usd/1e9:.1f}B TAM" if market_size_usd else "Unknown market size",
                rubric_used="MARKET_SIZE_RUBRIC",
            ),
        ]

        market_score = sum(c.weighted_score for c in market_components) / sum(c.weight for c in market_components)
        market_breakdown = CategoryScore(
            category_name="Market Opportunity",
            components=market_components,
            category_score=market_score,
            category_weight=self.market_weight,
            weighted_category_score=market_score * self.market_weight,
        )

        # Overall score
        overall = (
            clinical_breakdown.weighted_category_score +
            evidence_breakdown.weighted_category_score +
            market_breakdown.weighted_category_score
        )

        overall_explanation = (
            f"Clinical ({self.clinical_weight*100:.0f}%): {clinical_score:.1f} × {self.clinical_weight} = {clinical_breakdown.weighted_category_score:.2f}\n"
            f"Evidence ({self.evidence_weight*100:.0f}%): {evidence_score:.1f} × {self.evidence_weight} = {evidence_breakdown.weighted_category_score:.2f}\n"
            f"Market ({self.market_weight*100:.0f}%): {market_score:.1f} × {self.market_weight} = {market_breakdown.weighted_category_score:.2f}\n"
            f"Overall: {overall:.2f}"
        )

        return DetailedScoreBreakdown(
            pmid=pmid,
            disease=disease,
            n_patients=n_patients,
            response_rate_pct=response_rate_pct,
            sae_rate_pct=sae_rate_pct,
            followup_months=followup_months,
            n_competitors=n_competitors,
            market_size_usd=market_size_usd,
            clinical_breakdown=clinical_breakdown,
            evidence_breakdown=evidence_breakdown,
            market_breakdown=market_breakdown,
            overall_score=overall,
            overall_explanation=overall_explanation,
        )


# =============================================================================
# Disease-Level Aggregator
# =============================================================================

class DiseaseAggregator:
    """
    Aggregates scores at the disease level.

    Combines multiple extractions for the same disease
    with N-weighting and confidence adjustment.
    """

    @staticmethod
    def calculate_n_confidence(total_n: int) -> float:
        """
        Calculate confidence multiplier based on total patients.

        Returns value between 0.5 and 1.0.
        """
        if total_n < 5:
            return 0.5   # Heavy penalty for very small samples
        elif total_n < 10:
            return 0.65
        elif total_n < 20:
            return 0.75
        elif total_n < 35:
            return 0.85
        elif total_n < 50:
            return 0.90
        elif total_n < 75:
            return 0.95
        else:
            return 1.0

    @classmethod
    def aggregate_disease_scores(
        cls,
        breakdowns: List[DetailedScoreBreakdown],
        disease: str,
    ) -> DiseaseAggregateScore:
        """
        Aggregate multiple study breakdowns for a single disease.

        Uses N-weighted averaging for response and safety rates.
        """
        if not breakdowns:
            return DiseaseAggregateScore(
                disease=disease,
                disease_normalized=disease,
            )

        # Calculate aggregates
        total_n = sum(b.n_patients for b in breakdowns)
        study_count = len(breakdowns)

        # N-weighted response rate
        weighted_response_sum = 0.0
        response_n = 0
        for b in breakdowns:
            if b.response_rate_pct is not None:
                weighted_response_sum += b.response_rate_pct * b.n_patients
                response_n += b.n_patients

        weighted_response = weighted_response_sum / response_n if response_n > 0 else None

        # N-weighted SAE rate
        weighted_sae_sum = 0.0
        sae_n = 0
        for b in breakdowns:
            if b.sae_rate_pct is not None:
                weighted_sae_sum += b.sae_rate_pct * b.n_patients
                sae_n += b.n_patients

        weighted_sae = weighted_sae_sum / sae_n if sae_n > 0 else None

        # Aggregate category scores (N-weighted)
        clinical_scores = []
        evidence_scores = []
        market_scores = []

        for b in breakdowns:
            clinical_scores.append((b.clinical_breakdown.category_score, b.n_patients))
            evidence_scores.append((b.evidence_breakdown.category_score, b.n_patients))
            market_scores.append((b.market_breakdown.category_score, b.n_patients))

        def weighted_avg(scores_with_n):
            total_weight = sum(n for _, n in scores_with_n)
            if total_weight == 0:
                return 5.0
            return sum(score * n for score, n in scores_with_n) / total_weight

        agg_clinical = weighted_avg(clinical_scores)
        agg_evidence = weighted_avg(evidence_scores)
        agg_market = weighted_avg(market_scores)

        # Overall aggregated score
        overall = (
            agg_clinical * 0.50 +
            agg_evidence * 0.25 +
            agg_market * 0.25
        )

        # N-confidence adjustment
        n_confidence = cls.calculate_n_confidence(total_n)
        adjusted = overall * n_confidence

        return DiseaseAggregateScore(
            disease=disease,
            disease_normalized=breakdowns[0].disease_normalized or disease,
            total_patients=total_n,
            study_count=study_count,
            weighted_response_rate=weighted_response,
            combined_sae_rate=weighted_sae,
            study_breakdowns=breakdowns,
            clinical_score=agg_clinical,
            evidence_score=agg_evidence,
            market_score=agg_market,
            overall_score=overall,
            n_confidence=n_confidence,
            adjusted_score=adjusted,
        )
