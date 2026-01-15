"""
Scoring Engine

Main orchestrator for opportunity scoring, combining clinical, evidence,
and market scores into an overall priority score.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from src.case_series.models import (
    RepurposingOpportunity,
    OpportunityScores,
)
from src.case_series.scoring.clinical_scorer import ClinicalScorer
from src.case_series.scoring.evidence_scorer import EvidenceScorer
from src.case_series.scoring.market_scorer import MarketScorer
from src.case_series.protocols.database_protocol import CaseSeriesRepositoryProtocol


@dataclass
class ScoringWeights:
    """
    Weights for scoring dimensions.

    Default weights:
    - Clinical Signal: 50%
    - Evidence Quality: 25%
    - Market Opportunity: 25%
    """
    # Dimension weights (must sum to 1.0)
    clinical_weight: float = 0.50
    evidence_weight: float = 0.25
    market_weight: float = 0.25

    # Clinical sub-weights (must sum to 1.0)
    response_rate_weight: float = 0.40
    safety_profile_weight: float = 0.40
    organ_domain_weight: float = 0.20

    # Evidence sub-weights (must sum to 1.0)
    sample_size_weight: float = 0.35
    publication_venue_weight: float = 0.25
    durability_weight: float = 0.25
    completeness_weight: float = 0.15

    # Market sub-weights (equal weights)
    competitors_weight: float = 0.333
    market_size_weight: float = 0.333
    unmet_need_weight: float = 0.334

    def validate(self) -> bool:
        """Validate that weights sum to 1.0."""
        dim_sum = self.clinical_weight + self.evidence_weight + self.market_weight
        clinical_sum = self.response_rate_weight + self.safety_profile_weight + self.organ_domain_weight
        evidence_sum = self.sample_size_weight + self.publication_venue_weight + self.durability_weight + self.completeness_weight
        market_sum = self.competitors_weight + self.market_size_weight + self.unmet_need_weight

        return all([
            abs(dim_sum - 1.0) < 0.001,
            abs(clinical_sum - 1.0) < 0.001,
            abs(evidence_sum - 1.0) < 0.001,
            abs(market_sum - 1.0) < 0.001,
        ])


# Default weights instance
DEFAULT_WEIGHTS = ScoringWeights()


class ScoringEngine:
    """
    Main scoring engine that combines all scoring components.

    Orchestrates:
    - ClinicalScorer: Response rate, safety, organ domain
    - EvidenceScorer: Sample size, venue, durability, completeness
    - MarketScorer: Competitors, market size, unmet need

    Produces weighted overall priority scores.
    """

    def __init__(
        self,
        clinical_scorer: Optional[ClinicalScorer] = None,
        evidence_scorer: Optional[EvidenceScorer] = None,
        market_scorer: Optional[MarketScorer] = None,
        weights: ScoringWeights = DEFAULT_WEIGHTS,
        repository: Optional[CaseSeriesRepositoryProtocol] = None,
    ):
        """
        Initialize the scoring engine.

        Args:
            clinical_scorer: Clinical signal scorer (created if not provided)
            evidence_scorer: Evidence quality scorer (created if not provided)
            market_scorer: Market opportunity scorer (created if not provided)
            weights: Scoring weights configuration
            repository: Optional repository for reference data
        """
        self._clinical_scorer = clinical_scorer or ClinicalScorer(repository=repository)
        self._evidence_scorer = evidence_scorer or EvidenceScorer()
        self._market_scorer = market_scorer or MarketScorer()
        self._weights = weights

        if not weights.validate():
            raise ValueError("Scoring weights must sum to 1.0 within each category")

    @property
    def weights(self) -> ScoringWeights:
        """Get current scoring weights."""
        return self._weights

    @weights.setter
    def weights(self, value: ScoringWeights) -> None:
        """Set scoring weights."""
        if not value.validate():
            raise ValueError("Scoring weights must sum to 1.0 within each category")
        self._weights = value

    def score(self, opportunity: RepurposingOpportunity) -> OpportunityScores:
        """
        Score a single repurposing opportunity.

        Args:
            opportunity: The opportunity to score

        Returns:
            OpportunityScores with all component and overall scores
        """
        ext = opportunity.extraction
        w = self._weights

        # Clinical Signal Score (50% of overall by default)
        response_score, response_breakdown = self._clinical_scorer.score_response_rate(ext)
        safety_score, safety_breakdown = self._clinical_scorer.score_safety_profile(ext)
        organ_domain_score = self._clinical_scorer.score_organ_domain_breadth(ext)

        clinical_score = (
            response_score * w.response_rate_weight +
            safety_score * w.safety_profile_weight +
            organ_domain_score * w.organ_domain_weight
        )

        # Evidence Quality Score (25% of overall by default)
        sample_score = self._evidence_scorer.score_sample_size(ext)
        venue_score = self._evidence_scorer.score_publication_venue(ext)
        durability_score = self._evidence_scorer.score_response_durability(ext)
        completeness_score = self._evidence_scorer.score_extraction_completeness(ext)

        evidence_score = (
            sample_score * w.sample_size_weight +
            venue_score * w.publication_venue_weight +
            durability_score * w.durability_weight +
            completeness_score * w.completeness_weight
        )

        # Apply preprint penalty (30% reduction for lack of peer review)
        preprint_penalty_applied = False
        if ext.is_preprint:
            evidence_score *= 0.7
            preprint_penalty_applied = True

        # Market Opportunity Score (25% of overall by default)
        competitors_score = self._market_scorer.score_competitors(opportunity)
        market_size_score = self._market_scorer.score_market_size(opportunity)
        unmet_need_score = self._market_scorer.score_unmet_need(opportunity)

        market_score = (
            competitors_score * w.competitors_weight +
            market_size_score * w.market_size_weight +
            unmet_need_score * w.unmet_need_weight
        )

        # Overall Priority
        overall = (
            clinical_score * w.clinical_weight +
            evidence_score * w.evidence_weight +
            market_score * w.market_weight
        )

        # Build market breakdown data
        market_breakdown_data = {
            "competitors": round(competitors_score, 1),
            "market_size": round(market_size_score, 1),
            "unmet_need": round(unmet_need_score, 1)
        }

        # Add actual market intelligence data if available
        if opportunity.market_intelligence:
            mi = opportunity.market_intelligence
            if mi.standard_of_care:
                market_breakdown_data["num_approved_drugs"] = mi.standard_of_care.num_approved_drugs
                market_breakdown_data["unmet_need_flag"] = mi.standard_of_care.unmet_need
            if mi.tam_estimate:
                market_breakdown_data["tam_estimate"] = mi.tam_estimate

        return OpportunityScores(
            clinical_signal=round(clinical_score, 1),
            evidence_quality=round(evidence_score, 1),
            market_opportunity=round(market_score, 1),
            overall_priority=round(overall, 1),
            # Clinical breakdown
            response_rate_score=round(response_score, 1),
            safety_profile_score=round(safety_score, 1),
            endpoint_quality_score=None,  # Baked into response_rate_score
            organ_domain_score=round(organ_domain_score, 1),
            clinical_breakdown={
                "response_rate_quality_weighted": round(response_score, 1),
                "safety_profile": round(safety_score, 1),
                "organ_domain_breadth": round(organ_domain_score, 1),
                "safety_categories": safety_breakdown.get('categories_detected', []),
                "regulatory_flags": safety_breakdown.get('regulatory_flags', []),
                "efficacy_endpoint_count": response_breakdown.get('n_endpoints_scored', 0),
                "efficacy_concordance": response_breakdown.get('concordance_multiplier', 1.0),
            },
            # Evidence breakdown
            sample_size_score=round(sample_score, 1),
            publication_venue_score=round(venue_score, 1),
            followup_duration_score=round(durability_score, 1),
            extraction_completeness_score=round(completeness_score, 1),
            evidence_breakdown={
                "sample_size": round(sample_score, 1),
                "publication_venue": round(venue_score, 1),
                "response_durability": round(durability_score, 1),
                "extraction_completeness": round(completeness_score, 1),
                "is_preprint": ext.is_preprint,
                "preprint_penalty_applied": preprint_penalty_applied,
                "preprint_server": ext.preprint_server if ext.is_preprint else None,
            },
            # Market breakdown
            competitors_score=round(competitors_score, 1),
            market_size_score=round(market_size_score, 1),
            unmet_need_score=round(unmet_need_score, 1),
            market_breakdown=market_breakdown_data
        )

    def score_all(
        self,
        opportunities: List[RepurposingOpportunity],
    ) -> List[RepurposingOpportunity]:
        """
        Score all opportunities and update their scores in place.

        Args:
            opportunities: List of opportunities to score

        Returns:
            The same list with scores updated
        """
        for opp in opportunities:
            opp.scores = self.score(opp)
        return opportunities

    def rank(
        self,
        opportunities: List[RepurposingOpportunity],
        score_if_needed: bool = True,
    ) -> List[RepurposingOpportunity]:
        """
        Rank opportunities by overall priority score.

        Args:
            opportunities: List of opportunities to rank
            score_if_needed: If True, score opportunities that don't have scores

        Returns:
            Sorted list with ranks assigned
        """
        # Score if needed
        if score_if_needed:
            for opp in opportunities:
                if opp.scores.overall_priority == 5.0:  # Default score
                    opp.scores = self.score(opp)

        # Sort by overall priority (descending)
        sorted_opps = sorted(
            opportunities,
            key=lambda x: x.scores.overall_priority,
            reverse=True
        )

        # Assign ranks
        for i, opp in enumerate(sorted_opps, 1):
            opp.rank = i

        return sorted_opps

    def get_score_explanation(
        self,
        scores: OpportunityScores,
    ) -> Dict[str, Any]:
        """
        Get a human-readable explanation of scores.

        Args:
            scores: The scores to explain

        Returns:
            Dict with explanation text for each component
        """
        def interpret_score(score: float, context: str) -> str:
            if score >= 8:
                return f"Excellent {context}"
            elif score >= 6:
                return f"Good {context}"
            elif score >= 4:
                return f"Moderate {context}"
            else:
                return f"Limited {context}"

        return {
            "overall": interpret_score(scores.overall_priority, "opportunity"),
            "clinical_signal": interpret_score(scores.clinical_signal, "clinical signal"),
            "evidence_quality": interpret_score(scores.evidence_quality, "evidence quality"),
            "market_opportunity": interpret_score(scores.market_opportunity, "market opportunity"),
            "details": {
                "response_rate": interpret_score(scores.response_rate_score, "response rate"),
                "safety": interpret_score(scores.safety_profile_score, "safety profile"),
                "sample_size": interpret_score(scores.sample_size_score, "sample size"),
                "competitors": interpret_score(scores.competitors_score, "competitive landscape"),
            }
        }
