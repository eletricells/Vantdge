"""
Score Explanation Service

Generates Claude-powered narrative explanations of scores for transparency.
Pre-generates explanations during analysis for fast UI retrieval.
"""

import logging
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass

from src.case_series.protocols.llm_protocol import LLMClient

if TYPE_CHECKING:
    from src.case_series.services.aggregation_service import AggregatedEvidence
    from src.case_series.models import (
        RepurposingOpportunity,
        CaseSeriesExtraction,
        IndividualStudyScore,
    )

logger = logging.getLogger(__name__)


# =============================================================================
# Prompt Templates
# =============================================================================

AGGREGATE_EXPLANATION_SYSTEM = """You are a clinical research analyst explaining drug repurposing evidence.
Your explanations should be professional, data-driven, and accessible to both clinical and business audiences.
Use specific numbers from the provided data. Be honest about limitations while highlighting strengths."""

AGGREGATE_EXPLANATION_PROMPT = """Generate a 2-3 paragraph explanation for why {disease} scored {overall_score:.1f}/10 for repurposing potential with {drug_name}.

## Evidence Summary
- Number of studies: {n_studies}
- Total patients: {total_patients}
- Pooled response rate: {pooled_response}
- Response consistency: {consistency}
- Evidence confidence: {evidence_confidence}

## Score Breakdown
- Clinical Signal: {clinical_score:.1f}/10 (response rates, safety, organ involvement)
- Evidence Quality: {evidence_score:.1f}/10 (sample size, endpoints, follow-up)
- Market Opportunity: {market_score:.1f}/10 (unmet need, competition)

## Individual Paper Highlights
{paper_summaries}

---

Write your explanation covering:
1. **Opening paragraph:** Summarize the overall evidence strength and what the {overall_score:.1f}/10 score indicates. Highlight the most compelling data points.

2. **Middle paragraph:** Explain the key score drivers - what aspects were strongest (e.g., high response rates, validated endpoints, large samples) and what limitations exist (e.g., small samples, short follow-up, case reports only).

3. **Closing paragraph:** Briefly address clinical plausibility and what additional evidence would strengthen the case.

Keep paragraphs concise (3-4 sentences each). Use specific numbers."""


PAPER_EXPLANATION_PROMPT = """Explain in 2-3 sentences why this study scored {total_score:.1f}/10.

## Paper: PMID {pmid}
## Disease: {disease}
## Drug: {drug_name}

## Score Breakdown (each dimension 1-10):
- Efficacy (35% weight): {efficacy_score:.1f} - {efficacy_note}
- Sample Size (15% weight): {sample_size_score:.1f} - N={n_patients}
- Endpoint Quality (10% weight): {endpoint_score:.1f}
- Biomarker Support (15% weight): {biomarker_score:.1f}
- Response Definition (15% weight): {response_def_score:.1f}
- Follow-up (10% weight): {followup_score:.1f}

## Key Data:
- Response rate: {response_rate}
- Primary endpoint: {primary_endpoint}
- Follow-up duration: {follow_up_duration}

Write 2-3 sentences explaining what drove the score (mention the strongest and weakest dimensions)."""


# =============================================================================
# Service Class
# =============================================================================

@dataclass
class ExplanationResult:
    """Result from explanation generation."""
    disease: str
    explanation: str
    tokens_used: int
    model: str


class ScoreExplanationService:
    """
    Generates Claude-powered narrative explanations of scores.

    Uses Claude 3 Haiku for cost efficiency while maintaining quality.
    Explanations are generated during analysis and cached in the database.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        model: str = "claude-3-haiku-20240307",
    ):
        """
        Initialize the explanation service.

        Args:
            llm_client: LLM client for Claude API calls
            model: Model to use (default: Haiku for cost efficiency)
        """
        self._llm = llm_client
        self._model = model

    async def generate_aggregate_explanation(
        self,
        disease: str,
        drug_name: str,
        aggregated_evidence: "AggregatedEvidence",
        opportunities: List["RepurposingOpportunity"],
    ) -> ExplanationResult:
        """
        Generate 2-3 paragraph explanation for aggregate disease scores.

        Args:
            disease: Disease name
            drug_name: Drug being analyzed
            aggregated_evidence: Aggregated evidence data
            opportunities: Individual paper opportunities for this disease

        Returns:
            ExplanationResult with narrative explanation
        """
        # Build paper summaries
        paper_summaries = self._build_paper_summaries(opportunities)

        # Format pooled response
        if aggregated_evidence.pooled_response_pct is not None:
            pooled_response = f"{aggregated_evidence.pooled_response_pct:.0f}%"
            if aggregated_evidence.response_range:
                low, high = aggregated_evidence.response_range
                pooled_response += f" (range: {low:.0f}%-{high:.0f}%)"
        else:
            pooled_response = "Not quantified"

        # Build prompt
        prompt = AGGREGATE_EXPLANATION_PROMPT.format(
            disease=disease,
            drug_name=drug_name,
            overall_score=aggregated_evidence.avg_overall_score,
            n_studies=aggregated_evidence.n_studies,
            total_patients=aggregated_evidence.total_patients,
            pooled_response=pooled_response,
            consistency=aggregated_evidence.consistency,
            evidence_confidence=aggregated_evidence.evidence_confidence,
            clinical_score=aggregated_evidence.avg_clinical_score,
            evidence_score=aggregated_evidence.avg_evidence_score,
            market_score=aggregated_evidence.avg_market_score,
            paper_summaries=paper_summaries,
        )

        try:
            response = await self._llm.complete(
                prompt=prompt,
                system=AGGREGATE_EXPLANATION_SYSTEM,
                max_tokens=500,
                temperature=0.3,  # Slight creativity but mostly deterministic
            )

            tokens_used = self._llm.count_tokens(prompt) + self._llm.count_tokens(response)

            return ExplanationResult(
                disease=disease,
                explanation=response.strip(),
                tokens_used=tokens_used,
                model=self._model,
            )

        except Exception as e:
            logger.error(f"Failed to generate explanation for {disease}: {e}")
            # Return fallback explanation
            return ExplanationResult(
                disease=disease,
                explanation=self._build_fallback_explanation(aggregated_evidence),
                tokens_used=0,
                model="fallback",
            )

    async def generate_paper_explanation(
        self,
        extraction: "CaseSeriesExtraction",
        drug_name: str,
    ) -> str:
        """
        Generate brief 2-3 sentence explanation for individual paper score.

        Args:
            extraction: Paper extraction data
            drug_name: Drug being analyzed

        Returns:
            Brief explanation string
        """
        score = extraction.individual_score
        if not score:
            return "Score not available for this paper."

        # Get basic data
        pmid = extraction.source.pmid if extraction.source else "N/A"
        disease = extraction.disease_normalized or extraction.disease or "Unknown"
        n_patients = extraction.patient_population.n_patients if extraction.patient_population else 0

        # Response rate
        resp_pct = extraction.efficacy.responders_pct if extraction.efficacy else None
        response_rate = f"{resp_pct:.0f}%" if resp_pct is not None else "Not reported"

        # Primary endpoint
        primary_endpoint = extraction.efficacy.primary_endpoint if extraction.efficacy else "Not specified"
        if primary_endpoint and len(primary_endpoint) > 100:
            primary_endpoint = primary_endpoint[:100] + "..."

        # Follow-up
        follow_up = extraction.follow_up_duration or "Not specified"

        # Efficacy note
        if resp_pct is not None and resp_pct >= 80:
            efficacy_note = "Strong response"
        elif resp_pct is not None and resp_pct >= 50:
            efficacy_note = "Moderate response"
        elif resp_pct is not None:
            efficacy_note = "Limited response"
        else:
            efficacy_note = "Qualitative data only"

        prompt = PAPER_EXPLANATION_PROMPT.format(
            pmid=pmid,
            disease=disease,
            drug_name=drug_name,
            total_score=score.total_score,
            efficacy_score=score.efficacy_score,
            efficacy_note=efficacy_note,
            sample_size_score=score.sample_size_score,
            n_patients=n_patients,
            endpoint_score=score.endpoint_quality_score,
            biomarker_score=score.biomarker_score,
            response_def_score=score.response_definition_score,
            followup_score=score.followup_score,
            response_rate=response_rate,
            primary_endpoint=primary_endpoint,
            follow_up_duration=follow_up,
        )

        try:
            response = await self._llm.complete(
                prompt=prompt,
                max_tokens=150,
                temperature=0.2,
            )
            return response.strip()

        except Exception as e:
            logger.error(f"Failed to generate paper explanation for PMID {pmid}: {e}")
            return score.scoring_notes or f"Score: {score.total_score:.1f}/10"

    async def generate_all_explanations(
        self,
        drug_name: str,
        disease_aggregations: Dict[str, "AggregatedEvidence"],
        opportunities_by_disease: Dict[str, List["RepurposingOpportunity"]],
        include_paper_explanations: bool = True,
    ) -> Dict[str, ExplanationResult]:
        """
        Generate all explanations for a run (batch).

        Args:
            drug_name: Drug being analyzed
            disease_aggregations: Dict of disease -> AggregatedEvidence
            opportunities_by_disease: Dict of disease -> list of opportunities
            include_paper_explanations: Whether to generate per-paper explanations

        Returns:
            Dict mapping disease -> ExplanationResult
        """
        results: Dict[str, ExplanationResult] = {}

        for disease, evidence in disease_aggregations.items():
            opportunities = opportunities_by_disease.get(disease, [])

            logger.info(f"Generating explanation for {disease}...")
            result = await self.generate_aggregate_explanation(
                disease=disease,
                drug_name=drug_name,
                aggregated_evidence=evidence,
                opportunities=opportunities,
            )
            results[disease] = result

            # Generate per-paper explanations if requested
            if include_paper_explanations:
                for opp in opportunities:
                    if opp.extraction and not opp.extraction.score_explanation:
                        paper_explanation = await self.generate_paper_explanation(
                            extraction=opp.extraction,
                            drug_name=drug_name,
                        )
                        opp.extraction.score_explanation = paper_explanation

        logger.info(f"Generated {len(results)} disease explanations")
        return results

    def _build_paper_summaries(
        self,
        opportunities: List["RepurposingOpportunity"],
    ) -> str:
        """Build formatted paper summaries for the prompt."""
        if not opportunities:
            return "No individual papers available."

        summaries = []
        for i, opp in enumerate(opportunities[:5], 1):  # Limit to 5 papers
            ext = opp.extraction
            pmid = ext.source.pmid if ext.source else "N/A"
            n = ext.patient_population.n_patients if ext.patient_population else 0
            resp = ext.efficacy.responders_pct if ext.efficacy else None
            score = ext.individual_score.total_score if ext.individual_score else 0

            resp_str = f"{resp:.0f}% response" if resp is not None else "response not quantified"
            summaries.append(f"{i}. PMID {pmid}: N={n} patients, {resp_str}, score {score:.1f}/10")

        if len(opportunities) > 5:
            summaries.append(f"... and {len(opportunities) - 5} more papers")

        return "\n".join(summaries)

    def _build_fallback_explanation(
        self,
        evidence: "AggregatedEvidence",
    ) -> str:
        """Build a simple fallback explanation without LLM."""
        score = evidence.avg_overall_score

        if score >= 8:
            strength = "strong"
        elif score >= 6:
            strength = "moderate"
        elif score >= 4:
            strength = "limited"
        else:
            strength = "weak"

        parts = [
            f"This disease shows {strength} repurposing potential with a score of {score:.1f}/10.",
            f"Evidence comes from {evidence.n_studies} studies involving {evidence.total_patients} patients.",
        ]

        if evidence.pooled_response_pct is not None:
            parts.append(f"The pooled response rate is {evidence.pooled_response_pct:.0f}%.")

        if evidence.consistency and evidence.consistency != "N/A":
            parts.append(f"Response consistency across studies is {evidence.consistency.lower()}.")

        return " ".join(parts)
