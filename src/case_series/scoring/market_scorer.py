"""
Market Opportunity Scorer

Scores market opportunity for drug repurposing opportunities.
Handles:
- Competitor analysis scoring
- Market size scoring
- Unmet need scoring
"""

from typing import Optional

from src.case_series.models import (
    RepurposingOpportunity,
    EfficacySignal,
)


class MarketScorer:
    """
    Scores market opportunity for repurposing opportunities.

    Provides scoring for:
    - Competitors (fewer approved drugs = higher score)
    - Market size (larger market = higher score)
    - Unmet need (better than current options = higher score)
    """

    def __init__(self):
        """Initialize the market scorer."""
        pass

    def score_competitors(self, opportunity: RepurposingOpportunity) -> float:
        """
        Score based on number of competitors.

        Fewer approved drugs = higher opportunity.

        Scoring:
        - No approved drugs: 10
        - 1-2 approved: 7
        - 3-5 approved: 5
        - 6-10 approved: 3
        - >10 approved: 1

        Returns:
            Score from 1-10
        """
        if not opportunity.market_intelligence:
            return 5.0

        mi = opportunity.market_intelligence
        num_drugs = mi.standard_of_care.num_approved_drugs or 0

        if num_drugs == 0:
            return 10.0
        elif num_drugs <= 2:
            return 7.0
        elif num_drugs <= 5:
            return 5.0
        elif num_drugs <= 10:
            return 3.0
        else:
            return 1.0

    def score_market_size(self, opportunity: RepurposingOpportunity) -> float:
        """
        Score market size.

        Market size = patient population × avg annual cost of top 3 branded drugs.
        If no approved drugs, use prevalence-based pricing:
        - Rare (<10K): ~$200K/year
        - Specialty (10K-100K): ~$75K/year
        - Standard (>100K): ~$20K/year

        Scoring:
        - >$10B: 10
        - $5-10B: 9
        - $1-5B: 8
        - $500M-1B: 7
        - $100-500M: 6
        - $50-100M: 5
        - $10-50M: 4
        - <$10M: 2

        Returns:
            Score from 1-10
        """
        if not opportunity.market_intelligence:
            return 5.0

        mi = opportunity.market_intelligence
        pop = mi.epidemiology.patient_population_size or 0

        # Use pre-calculated market size if available
        if mi.market_size_usd:
            market_size = mi.market_size_usd
        elif mi.standard_of_care.avg_annual_cost_usd and pop > 0:
            market_size = pop * mi.standard_of_care.avg_annual_cost_usd
        elif pop > 0:
            # Estimate based on prevalence
            if pop < 10000:
                # Rare disease pricing
                annual_cost = 200000
            elif pop < 100000:
                # Specialty pricing
                annual_cost = 75000
            else:
                # Standard pricing
                annual_cost = 20000
            market_size = pop * annual_cost
        else:
            return 5.0

        # Score based on market size
        if market_size >= 10_000_000_000:  # $10B+
            return 10.0
        elif market_size >= 5_000_000_000:  # $5-10B
            return 9.0
        elif market_size >= 1_000_000_000:  # $1-5B
            return 8.0
        elif market_size >= 500_000_000:  # $500M-1B
            return 7.0
        elif market_size >= 100_000_000:  # $100-500M
            return 6.0
        elif market_size >= 50_000_000:  # $50-100M
            return 5.0
        elif market_size >= 10_000_000:  # $10-50M
            return 4.0
        else:  # <$10M
            return 2.0

    def score_unmet_need(self, opportunity: RepurposingOpportunity) -> float:
        """
        Score unmet need.

        Compares efficacy signal from case series vs top 3 approved drugs.
        - Better efficacy than approved options = 10
        - Similar efficacy = 5
        - Worse efficacy = 2
        - No approved drugs for indication = 10

        Returns:
            Score from 1-10
        """
        if not opportunity.market_intelligence:
            return 5.0

        mi = opportunity.market_intelligence
        ext = opportunity.extraction

        # If no approved drugs, unmet need is maximum
        if (mi.standard_of_care.num_approved_drugs or 0) == 0:
            return 10.0

        # If unmet need is explicitly marked
        if mi.standard_of_care.unmet_need:
            return 10.0

        # Compare case series efficacy to SOC
        case_series_efficacy = ext.efficacy.responders_pct

        # Get average SOC efficacy
        soc_efficacies = []
        for treatment in mi.standard_of_care.top_treatments[:3]:
            if treatment.efficacy_pct:
                soc_efficacies.append(treatment.efficacy_pct)

        if case_series_efficacy and soc_efficacies:
            avg_soc = sum(soc_efficacies) / len(soc_efficacies)

            # Compare: significantly better (+10%) = 10, similar (±10%) = 5, worse = 2
            if case_series_efficacy > avg_soc + 10:
                return 10.0
            elif case_series_efficacy >= avg_soc - 10:
                return 5.0
            else:
                return 2.0

        # Fallback: use efficacy signal
        if ext.efficacy_signal == EfficacySignal.STRONG:
            return 8.0
        elif ext.efficacy_signal == EfficacySignal.MODERATE:
            return 5.0
        elif ext.efficacy_signal == EfficacySignal.WEAK:
            return 3.0

        return 5.0

    def estimate_market_size_usd(
        self,
        patient_population: int,
        avg_annual_cost: Optional[float] = None,
    ) -> float:
        """
        Estimate market size in USD.

        Args:
            patient_population: Number of patients
            avg_annual_cost: Average annual treatment cost (optional)

        Returns:
            Estimated market size in USD
        """
        if avg_annual_cost:
            return patient_population * avg_annual_cost

        # Estimate based on population size
        if patient_population < 10000:
            return patient_population * 200000  # Rare disease
        elif patient_population < 100000:
            return patient_population * 75000   # Specialty
        else:
            return patient_population * 20000   # Standard

    def format_market_size(self, market_size_usd: float) -> str:
        """
        Format market size as human-readable string.

        Args:
            market_size_usd: Market size in USD

        Returns:
            Formatted string (e.g., "$2.5B")
        """
        if market_size_usd >= 1_000_000_000:
            return f"${market_size_usd / 1_000_000_000:.1f}B"
        elif market_size_usd >= 1_000_000:
            return f"${market_size_usd / 1_000_000:.0f}M"
        elif market_size_usd >= 1_000:
            return f"${market_size_usd / 1_000:.0f}K"
        else:
            return f"${market_size_usd:.0f}"
