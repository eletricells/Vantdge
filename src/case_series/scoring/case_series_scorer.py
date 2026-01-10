"""
Case Series Scorer

Implements the refined 6-dimension scoring system for case series studies.

Scoring Dimensions (weights):
1. Efficacy/Quantitative Rigor (35%) - How strong is the clinical response data?
2. Sample Size (15%) - Number of patients, calibrated for case series
3. Endpoint Quality (10%) - Are validated instruments used?
4. Biomarker Support (15%) - Biomarkers mentioned AND quantified with beneficial change
5. Response Definition (15%) - How rigorously is response defined?
6. Follow-up Duration (10%) - Length of follow-up period
"""

import logging
import re
from typing import Optional, List, Dict, Any, Tuple
from statistics import mean, stdev

from src.case_series.models import (
    CaseSeriesExtraction,
    DetailedEfficacyEndpoint,
    BiomarkerResult,
    IndividualStudyScore,
    AggregateScore,
    EfficacySignal,
)
from src.case_series.taxonomy import get_default_taxonomy, DiseaseTaxonomy

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Default weights for scoring dimensions
DEFAULT_WEIGHTS = {
    "efficacy": 0.35,
    "sample_size": 0.15,
    "endpoint_quality": 0.10,
    "biomarker": 0.15,
    "response_definition": 0.15,
    "followup": 0.10,
}

# Gold-standard validated endpoints (regulatory-accepted)
REGULATORY_ENDPOINTS = {
    # Rheumatology
    'acr20', 'acr50', 'acr70', 'acr90',
    'das28', 'das-28',
    # Dermatology
    'pasi', 'pasi50', 'pasi75', 'pasi90', 'pasi100',
    'easi', 'easi50', 'easi75', 'easi90',
    'iga 0/1', 'iga 0', 'iga 1',
    'salt', 'salt50', 'salt75', 'salt90',
    # Lupus
    'sledai', 'sledai-2k',
    'bilag', 'sri', 'sri-4',
    # Myositis
    'cdasi', 'mmt8', 'mmt-8',
    'imacs', 'acr/eular',
    # GI
    'mayo', 'mayo score',
    'cdai',
    # General
    'complete response', 'partial response',
    'remission',
}

# Disease-specific validated endpoints
DISEASE_SPECIFIC_ENDPOINTS = {
    'dlqi', 'scorad', 'haq', 'haq-di',
    'facit', 'facit-fatigue',
    'sf-36', 'sf36', 'eq-5d',
    'physician global', 'pga',
    'patient global',
}

# Biomarker keywords for detection
BIOMARKER_KEYWORDS = [
    'crp', 'c-reactive', 'esr', 'sed rate',
    'ldh', 'lactate dehydrogenase',
    'ck', 'creatine kinase', 'cpk',
    'complement', 'c3', 'c4', 'ch50',
    'cytokine', 'chemokine', 'cxcl', 'il-', 'tnf',
    'interferon', 'ifn', 'stat1',
    'autoantibody', 'anti-', 'ana', 'dsdna',
    'b-cell', 'cd19', 'cd20',
    'platelet', 'hemoglobin', 'wbc', 'anc',
    'ferritin', 'albumin', 'proteinuria',
    'egfr', 'creatinine',
]

# Biomarker/endpoint direction mapping: which direction indicates improvement
# "lower" = decrease is beneficial, "higher" = increase is beneficial
BIOMARKER_DIRECTION = {
    # Disease activity scores (lower is better)
    'sledai': 'lower', 'sledai-2k': 'lower',
    'das28': 'lower', 'das-28': 'lower',
    'cdai': 'lower',  # Crohn's Disease Activity Index
    'mayo': 'lower', 'mayo score': 'lower',
    'pasi': 'lower',  # Psoriasis Area Severity Index
    'easi': 'lower',  # Eczema Area Severity Index
    'scorad': 'lower',
    'cdasi': 'lower',  # Cutaneous Dermatomyositis Activity
    'bilag': 'lower',
    'haq': 'lower', 'haq-di': 'lower',  # Health Assessment Questionnaire
    'dlqi': 'lower',  # Dermatology Life Quality Index
    'vas pain': 'lower', 'pain score': 'lower', 'pain vas': 'lower',

    # Inflammatory markers (lower is better)
    'crp': 'lower', 'c-reactive': 'lower', 'c-reactive protein': 'lower',
    'esr': 'lower', 'sed rate': 'lower', 'sedimentation rate': 'lower',
    'ferritin': 'lower',  # In inflammatory conditions
    'il-6': 'lower', 'il-1': 'lower', 'tnf': 'lower',
    'ifn': 'lower', 'interferon': 'lower',

    # Kidney function markers (lower is better for damage markers)
    'creatinine': 'lower', 'serum creatinine': 'lower',
    'urea': 'lower', 'blood urea': 'lower', 'bun': 'lower',
    'proteinuria': 'lower', 'protein/creatinine': 'lower',
    'albumin-creatinine ratio': 'lower', 'acr': 'lower', 'uacr': 'lower',
    'urine protein': 'lower',

    # Liver enzymes (lower is better when elevated)
    'alt': 'lower', 'alanine': 'lower',
    'ast': 'lower', 'aspartate': 'lower',
    'alkaline phosphatase': 'lower', 'alp': 'lower',
    'bilirubin': 'lower',
    'ggt': 'lower', 'gamma-glutamyl': 'lower',

    # Muscle enzymes (lower is better in myositis)
    'ck': 'lower', 'creatine kinase': 'lower', 'cpk': 'lower',
    'ldh': 'lower', 'lactate dehydrogenase': 'lower',
    'aldolase': 'lower',

    # Autoantibodies (lower/negative is better)
    'anti-dsdna': 'lower', 'dsdna': 'lower',
    'ana titer': 'lower',
    'anca': 'lower',
    'rf': 'lower', 'rheumatoid factor': 'lower',
    'anti-ccp': 'lower',

    # Blood counts - context dependent, but in autoimmune usually:
    'wbc': 'lower',  # Often elevated in inflammation
    'neutrophil': 'lower',  # In inflammatory states

    # Beneficial markers (higher is better)
    'hemoglobin': 'higher', 'hgb': 'higher', 'hb': 'higher',
    'albumin': 'higher', 'serum albumin': 'higher',
    'complement': 'higher', 'c3': 'higher', 'c4': 'higher', 'ch50': 'higher',
    'platelet': 'higher',  # When low due to disease
    'lymphocyte': 'higher',  # When depleted
    'egfr': 'higher',  # Kidney function
    'fvc': 'higher', 'dlco': 'higher',  # Lung function
    'mmt': 'higher', 'mmt8': 'higher', 'mmt-8': 'higher',  # Muscle strength

    # Quality of life (higher is better)
    'sf-36': 'higher', 'sf36': 'higher',
    'eq-5d': 'higher',
    'facit': 'higher', 'facit-fatigue': 'higher',

    # Response rates (higher is better) - these use responders_pct anyway
    'acr20': 'higher', 'acr50': 'higher', 'acr70': 'higher',
    'pasi75': 'higher', 'pasi90': 'higher', 'pasi100': 'higher',
    'easi75': 'higher', 'easi90': 'higher',
}


class CaseSeriesScorer:
    """
    Scores individual case series studies using 6 dimensions.

    Also provides aggregate scoring across multiple studies for a disease.
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        taxonomy: Optional[DiseaseTaxonomy] = None,
    ):
        """
        Initialize the scorer.

        Args:
            weights: Custom weights for scoring dimensions (must sum to 1.0)
            taxonomy: Disease taxonomy for endpoint validation
        """
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self._taxonomy = taxonomy or get_default_taxonomy()

        # Validate weights sum to 1.0
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Weights sum to {total}, normalizing to 1.0")
            for k in self.weights:
                self.weights[k] /= total

    def score_extraction(
        self,
        extraction: CaseSeriesExtraction,
    ) -> IndividualStudyScore:
        """
        Score an individual case series extraction.

        Args:
            extraction: The extraction to score

        Returns:
            IndividualStudyScore with breakdown by dimension
        """
        # Score each dimension
        efficacy = self._score_efficacy(extraction)
        sample_size = self._score_sample_size(extraction)
        endpoint_quality = self._score_endpoint_quality(extraction)
        biomarker = self._score_biomarker(extraction)
        response_def = self._score_response_definition(extraction)
        followup = self._score_followup(extraction)

        # Calculate weighted total
        total = (
            efficacy * self.weights["efficacy"] +
            sample_size * self.weights["sample_size"] +
            endpoint_quality * self.weights["endpoint_quality"] +
            biomarker * self.weights["biomarker"] +
            response_def * self.weights["response_definition"] +
            followup * self.weights["followup"]
        )

        # Build notes
        notes = self._build_scoring_notes(
            extraction, efficacy, sample_size, endpoint_quality,
            biomarker, response_def, followup
        )

        return IndividualStudyScore(
            total_score=round(total, 1),
            efficacy_score=efficacy,
            sample_size_score=sample_size,
            endpoint_quality_score=endpoint_quality,
            biomarker_score=biomarker,
            response_definition_score=response_def,
            followup_score=followup,
            weights=self.weights.copy(),
            scoring_notes=notes,
        )

    def score_aggregate(
        self,
        extractions: List[CaseSeriesExtraction],
    ) -> AggregateScore:
        """
        Calculate aggregate score across multiple extractions for a disease.

        Uses N-weighted average of individual scores.

        Args:
            extractions: List of extractions for same disease

        Returns:
            AggregateScore with breakdown
        """
        if not extractions:
            return AggregateScore(
                aggregate_score=0.0,
                study_count=0,
                total_patients=0,
            )

        individual_scores = []
        response_rates = []

        for ext in extractions:
            # Score if not already scored
            if ext.individual_score is None:
                score = self.score_extraction(ext)
            else:
                score = ext.individual_score

            n = ext.patient_population.n_patients or 1
            pmid = ext.source.pmid if ext.source else None

            individual_scores.append({
                "pmid": pmid,
                "n_patients": n,
                "score": score.total_score,
            })

            # Collect response rates for consistency calculation
            if ext.efficacy.responders_pct is not None:
                response_rates.append(ext.efficacy.responders_pct)

        # Calculate N-weighted average
        total_n = sum(s["n_patients"] for s in individual_scores)
        weighted_sum = sum(s["score"] * s["n_patients"] for s in individual_scores)
        aggregate_score = weighted_sum / total_n if total_n > 0 else 0

        # Find best paper
        best = max(individual_scores, key=lambda x: x["score"])

        # Calculate consistency
        consistency_level = None
        cv = None
        if len(response_rates) >= 2:
            avg_rate = mean(response_rates)
            if avg_rate > 0:
                cv = stdev(response_rates) / avg_rate
                if cv < 0.25:
                    consistency_level = "High"
                elif cv < 0.50:
                    consistency_level = "Moderate"
                else:
                    consistency_level = "Low"

        return AggregateScore(
            aggregate_score=round(aggregate_score, 1),
            study_count=len(extractions),
            total_patients=total_n,
            best_paper_pmid=best["pmid"],
            best_paper_score=best["score"],
            consistency_level=consistency_level,
            response_rate_cv=round(cv, 2) if cv is not None else None,
            individual_scores=individual_scores,
        )

    # =========================================================================
    # Dimension Scoring Methods
    # =========================================================================

    def _score_efficacy(self, extraction: CaseSeriesExtraction) -> float:
        """
        Score efficacy/quantitative rigor (35% weight).

        1-3: Qualitative only ("patient improved")
        4-5: Direction only ("scores decreased")
        6-7: Quantified (% change, counts)
        8-9: Statistical tests reported
        10:  P-values + effect sizes + multiple endpoints concordant
        """
        score = 5.0  # Default neutral

        # Check detailed endpoints first
        endpoints = extraction.detailed_efficacy_endpoints
        if endpoints:
            return self._score_efficacy_from_endpoints(endpoints)

        # Fallback to summary fields
        efficacy = extraction.efficacy

        # Check for quantitative data
        has_response_pct = efficacy.responders_pct is not None
        has_response_rate = efficacy.response_rate is not None

        if has_response_pct:
            pct = efficacy.responders_pct
            if pct >= 80:
                score = 9.0
            elif pct >= 60:
                score = 8.0
            elif pct >= 40:
                score = 7.0
            elif pct >= 20:
                score = 6.0
            else:
                score = 5.0
        elif has_response_rate:
            # Has response rate text but maybe not parsed
            score = 6.0

        # Adjust based on efficacy signal
        if extraction.efficacy_signal == EfficacySignal.STRONG:
            score = max(score, 8.0)
        elif extraction.efficacy_signal == EfficacySignal.MODERATE:
            score = max(score, 6.0)
        elif extraction.efficacy_signal == EfficacySignal.WEAK:
            score = min(score, 4.0)
        elif extraction.efficacy_signal == EfficacySignal.NONE:
            score = min(score, 2.0)

        return score

    def _score_efficacy_from_endpoints(
        self,
        endpoints: List[DetailedEfficacyEndpoint],
    ) -> float:
        """
        Score efficacy from detailed endpoints.

        Uses a hybrid approach:
        1. Response percentages scored directly (higher = better)
        2. Change from baseline with directionality awareness
        3. Statistical significance bonus
        """
        if not endpoints:
            return 5.0

        scores = []
        has_p_values = False
        has_quantitative = False

        for ep in endpoints:
            ep_score = 5.0

            # Priority 1: Check for response percentage (already a "good outcome" metric)
            if ep.responders_pct is not None:
                has_quantitative = True
                pct = ep.responders_pct
                if pct >= 80:
                    ep_score = 9.0
                elif pct >= 60:
                    ep_score = 8.0
                elif pct >= 40:
                    ep_score = 7.0
                elif pct >= 20:
                    ep_score = 6.0

            # Priority 2: Check for change_pct (if explicitly provided)
            elif ep.change_pct is not None:
                has_quantitative = True
                # Check if change is in beneficial direction
                if self._is_beneficial_change(ep):
                    change = abs(ep.change_pct)
                    if change >= 50:
                        ep_score = 8.0
                    elif change >= 30:
                        ep_score = 7.0
                    elif change >= 10:
                        ep_score = 6.0
                else:
                    # Non-beneficial change - penalize
                    ep_score = 3.0

            # Priority 3: Calculate change_pct from baseline and change_from_baseline
            elif ep.change_from_baseline is not None and ep.baseline_value is not None and ep.baseline_value != 0:
                has_quantitative = True
                calculated_change_pct = abs(ep.change_from_baseline / ep.baseline_value) * 100

                # Check if change is in beneficial direction
                if self._is_beneficial_change(ep):
                    if calculated_change_pct >= 50:
                        ep_score = 8.0
                    elif calculated_change_pct >= 30:
                        ep_score = 7.0
                    elif calculated_change_pct >= 10:
                        ep_score = 6.0
                    else:
                        ep_score = 5.5  # Small but beneficial change
                else:
                    # Non-beneficial change or unknown direction
                    ep_score = 4.0

            # Check for statistical significance - add bonus
            if ep.statistical_significance or ep.p_value:
                has_p_values = True
                ep_score = min(10.0, ep_score + 1.0)

            scores.append(ep_score)

        if not scores:
            return 5.0

        avg_score = mean(scores)

        # Bonus for multiple concordant endpoints
        if len(scores) >= 3 and has_p_values and has_quantitative:
            avg_score = min(10.0, avg_score + 0.5)

        return round(avg_score, 1)

    def _is_beneficial_change(self, ep: DetailedEfficacyEndpoint) -> bool:
        """
        Determine if the change direction for an endpoint is beneficial.

        Uses a lookup table of known biomarkers/endpoints and their expected
        beneficial direction. Falls back to statistical significance as a proxy.

        Args:
            ep: The endpoint to evaluate

        Returns:
            True if the change appears beneficial, False otherwise
        """
        endpoint_name = (ep.endpoint_name or "").lower()
        change = ep.change_from_baseline

        if change is None:
            # If we have change_pct, assume it's already a positive/beneficial representation
            return True

        # Look up expected direction in the biomarker table
        for marker, direction in BIOMARKER_DIRECTION.items():
            if marker in endpoint_name:
                if direction == 'lower':
                    # Decrease is beneficial
                    return change < 0
                else:
                    # Increase is beneficial
                    return change > 0

        # Check notes field for hints about improvement
        notes = (ep.notes or "").lower()
        if any(word in notes for word in ['improvement', 'improved', 'better', 'reduction', 'decreased', 'resolved']):
            return True
        if any(word in notes for word in ['worsening', 'worsened', 'worse', 'increased risk', 'deterioration']):
            return False

        # Fallback: if statistically significant, assume beneficial
        # (papers typically report improvements, not worsening, as efficacy endpoints)
        if ep.statistical_significance or ep.p_value:
            return True

        # Unknown - assume neutral (return True to not penalize)
        return True

    def _score_sample_size(self, extraction: CaseSeriesExtraction) -> float:
        """
        Score sample size (15% weight).

        Calibrated for case series:
        1:  N = 1
        2:  N = 2
        4:  N = 3-4
        6:  N = 5-9
        8:  N = 10-14
        9:  N = 15-19
        10: N >= 20
        """
        n = extraction.patient_population.n_patients

        if n is None or n < 1:
            return 1.0
        elif n == 1:
            return 1.0
        elif n == 2:
            return 2.0
        elif n <= 4:
            return 4.0
        elif n <= 9:
            return 6.0
        elif n <= 14:
            return 8.0
        elif n <= 19:
            return 9.0
        else:
            return 10.0

    def _score_endpoint_quality(self, extraction: CaseSeriesExtraction) -> float:
        """
        Score endpoint quality (10% weight).

        1-4: Ad-hoc endpoints only
        5-6: Some validated endpoints
        7-8: Disease-specific validated endpoints
        9-10: Gold-standard regulatory endpoints
        """
        # Check detailed endpoints
        endpoints = extraction.detailed_efficacy_endpoints
        if endpoints:
            return self._score_endpoint_quality_from_endpoints(endpoints, extraction.disease)

        # Fallback to primary endpoint text
        primary_ep = extraction.efficacy.primary_endpoint
        if not primary_ep:
            return 4.0  # Ad-hoc / no endpoint specified

        return self._score_single_endpoint_quality(primary_ep)

    def _score_endpoint_quality_from_endpoints(
        self,
        endpoints: List[DetailedEfficacyEndpoint],
        disease: str,
    ) -> float:
        """Score endpoint quality from detailed endpoints."""
        if not endpoints:
            return 4.0

        scores = []
        for ep in endpoints:
            ep_name = (ep.endpoint_name or "").lower()

            # Check if validated instrument
            if ep.is_validated_instrument:
                if ep.instrument_quality_tier == 1:
                    scores.append(10.0)
                elif ep.instrument_quality_tier == 2:
                    scores.append(8.0)
                else:
                    scores.append(6.0)
            else:
                scores.append(self._score_single_endpoint_quality(ep_name))

        return max(scores) if scores else 4.0

    def _score_single_endpoint_quality(self, endpoint_name: str) -> float:
        """Score a single endpoint name."""
        ep_lower = endpoint_name.lower()

        # Check regulatory endpoints (gold standard)
        for pattern in REGULATORY_ENDPOINTS:
            if pattern in ep_lower:
                return 10.0

        # Check disease-specific validated
        for pattern in DISEASE_SPECIFIC_ENDPOINTS:
            if pattern in ep_lower:
                return 8.0

        # Check for common validated terms
        if any(term in ep_lower for term in ['response', 'remission', 'improvement']):
            return 6.0

        # Ad-hoc endpoint
        return 4.0

    def _score_biomarker(self, extraction: CaseSeriesExtraction) -> float:
        """
        Score biomarker support (15% weight).

        0-2: No biomarkers mentioned
        3-4: Biomarkers mentioned but not quantified
        5-6: Biomarkers quantified (before/after values)
        7-8: Biomarkers show beneficial change with stats
        9-10: Biomarkers support mechanism AND show beneficial change
        """
        # Check explicit biomarker field first
        biomarkers = extraction.biomarkers
        if biomarkers:
            return self._score_explicit_biomarkers(biomarkers)

        # Detect biomarkers from detailed endpoints
        return self._detect_and_score_biomarkers(extraction)

    def _score_explicit_biomarkers(self, biomarkers: List[BiomarkerResult]) -> float:
        """Score from explicit biomarker results."""
        if not biomarkers:
            return 2.0

        best_score = 3.0  # At least mentioned
        for bm in biomarkers:
            score = 3.0

            # Quantified?
            if bm.baseline_value is not None or bm.final_value is not None:
                score = 5.0

                # Beneficial change?
                if bm.is_beneficial:
                    score = 7.0

                    # With statistics?
                    if bm.p_value:
                        score = 8.0

                    # Supports mechanism?
                    if bm.supports_mechanism:
                        score = 10.0

            best_score = max(best_score, score)

        return best_score

    def _detect_and_score_biomarkers(self, extraction: CaseSeriesExtraction) -> float:
        """Detect biomarkers from endpoints and score."""
        biomarker_endpoints = []

        for ep in extraction.detailed_efficacy_endpoints:
            ep_name = (ep.endpoint_name or "").lower()
            organ = (ep.organ_domain or "").lower()

            # Check explicit is_biomarker field first (from extraction prompt)
            if ep.is_biomarker is True:
                biomarker_endpoints.append(ep)
                continue

            # Skip if explicitly marked as not a biomarker
            if ep.is_biomarker is False:
                continue

            # Fallback: Check if biomarker by organ domain
            is_biomarker = organ in ['immunological', 'hematological']

            # Check if biomarker by name
            if not is_biomarker:
                for kw in BIOMARKER_KEYWORDS:
                    if kw in ep_name:
                        is_biomarker = True
                        break

            if is_biomarker:
                biomarker_endpoints.append(ep)

        if not biomarker_endpoints:
            return 2.0  # No biomarkers

        best_score = 3.0
        for ep in biomarker_endpoints:
            score = 3.0

            # Quantified?
            has_values = (
                ep.baseline_value is not None or
                ep.final_value is not None or
                ep.change_pct is not None or
                ep.responders_pct is not None
            )
            if has_values:
                score = 5.0

                # Beneficial change? (assume decrease in biomarker is good unless known otherwise)
                if ep.change_pct is not None and ep.change_pct < 0:
                    score = 7.0
                elif ep.responders_pct is not None and ep.responders_pct > 50:
                    score = 7.0

                # With statistics?
                if ep.statistical_significance or ep.p_value:
                    score = 8.0

            best_score = max(best_score, score)

        return best_score

    def _score_response_definition(self, extraction: CaseSeriesExtraction) -> float:
        """
        Score response definition quality (15% weight).

        1-3: Implicit/subjective ("patient felt better")
        4-5: Author-defined criteria
        6-7: Disease-specific criteria (but not regulatory)
        8-9: Established clinical trial criteria
        10:  Regulatory-accepted endpoints (ACR20/50/70, PASI75, EASI-75)
        """
        # Check explicit field first
        if extraction.response_definition_quality:
            quality = extraction.response_definition_quality.lower()
            if 'regulatory' in quality:
                return 10.0
            elif 'disease' in quality:
                return 7.0
            elif 'author' in quality:
                return 5.0
            else:
                return 3.0

        # Infer from endpoints
        endpoints = extraction.detailed_efficacy_endpoints
        primary_ep = extraction.efficacy.primary_endpoint

        # Check for regulatory criteria
        all_text = " ".join([
            (ep.endpoint_name or "") for ep in endpoints
        ] + [primary_ep or ""])
        all_text_lower = all_text.lower()

        for pattern in REGULATORY_ENDPOINTS:
            if pattern in all_text_lower:
                return 10.0

        for pattern in DISEASE_SPECIFIC_ENDPOINTS:
            if pattern in all_text_lower:
                return 7.0

        # Check for some structure
        if any(term in all_text_lower for term in ['response', 'remission', 'criteria']):
            return 5.0

        # Implicit
        return 3.0

    def _score_followup(self, extraction: CaseSeriesExtraction) -> float:
        """
        Score follow-up duration (10% weight).

        1-3: Acute only / single timepoint
        4-5: < 1 month
        6-7: 1-3 months
        8-9: 3-6 months
        10:  > 6 months
        """
        # Check numeric field first
        if extraction.follow_up_weeks is not None:
            weeks = extraction.follow_up_weeks
            if weeks >= 26:  # > 6 months
                return 10.0
            elif weeks >= 12:  # 3-6 months
                return 8.0
            elif weeks >= 4:  # 1-3 months
                return 7.0
            elif weeks >= 1:  # < 1 month
                return 5.0
            else:
                return 3.0

        # Parse from text
        duration_text = extraction.follow_up_duration
        if not duration_text:
            return 5.0  # Unknown

        return self._parse_duration_to_score(duration_text)

    def _parse_duration_to_score(self, duration_text: str) -> float:
        """Parse duration text and return score."""
        text = duration_text.lower()

        # Look for week patterns
        week_match = re.search(r'(\d+)\s*(?:week|wk)', text)
        if week_match:
            weeks = int(week_match.group(1))
            if weeks >= 26:
                return 10.0
            elif weeks >= 12:
                return 8.0
            elif weeks >= 4:
                return 7.0
            else:
                return 5.0

        # Look for month patterns
        month_match = re.search(r'(\d+)\s*(?:month|mo)', text)
        if month_match:
            months = int(month_match.group(1))
            if months >= 6:
                return 10.0
            elif months >= 3:
                return 8.0
            elif months >= 1:
                return 7.0
            else:
                return 5.0

        # Look for year patterns
        year_match = re.search(r'(\d+)\s*(?:year|yr)', text)
        if year_match:
            return 10.0

        # Keywords
        if any(term in text for term in ['long-term', 'long term', 'extended']):
            return 9.0
        if any(term in text for term in ['short', 'acute', 'single']):
            return 3.0

        return 5.0  # Unknown

    def _build_scoring_notes(
        self,
        extraction: CaseSeriesExtraction,
        efficacy: float,
        sample_size: float,
        endpoint_quality: float,
        biomarker: float,
        response_def: float,
        followup: float,
    ) -> str:
        """Build human-readable scoring notes."""
        notes = []

        n = extraction.patient_population.n_patients or 0
        notes.append(f"N={n}")

        if efficacy >= 8:
            notes.append("strong efficacy data")
        elif efficacy <= 4:
            notes.append("weak efficacy data")

        if endpoint_quality >= 9:
            notes.append("gold-standard endpoints")
        elif endpoint_quality <= 4:
            notes.append("ad-hoc endpoints")

        if biomarker >= 7:
            notes.append("biomarker support")
        elif biomarker <= 3:
            notes.append("no biomarkers")

        return "; ".join(notes)
