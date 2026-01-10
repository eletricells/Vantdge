"""
Clinical Signal Scorer

Scores clinical efficacy and safety signals from case series extractions.
Handles:
- Response rate scoring (quality-weighted multi-endpoint)
- Safety profile scoring
- Organ domain breadth scoring
"""

import re
from typing import Dict, Any, List, Tuple, Optional

from src.case_series.models import (
    CaseSeriesExtraction,
    EfficacySignal,
    SafetyProfile,
)
from src.case_series.protocols.database_protocol import CaseSeriesRepositoryProtocol


# =============================================================================
# Helper Functions for Efficacy Scoring
# =============================================================================

def _response_pct_to_score(pct: float) -> float:
    """
    Convert response percentage to 1-10 score.

    10 tiers for granularity:
    >=90%: 10, >=80%: 9, >=70%: 8, >=60%: 7, >=50%: 6,
    >=40%: 5, >=30%: 4, >=20%: 3, >=10%: 2, <10%: 1
    """
    if pct >= 90:
        return 10.0
    elif pct >= 80:
        return 9.0
    elif pct >= 70:
        return 8.0
    elif pct >= 60:
        return 7.0
    elif pct >= 50:
        return 6.0
    elif pct >= 40:
        return 5.0
    elif pct >= 30:
        return 4.0
    elif pct >= 20:
        return 3.0
    elif pct >= 10:
        return 2.0
    else:
        return 1.0


def _percent_change_to_score(effective_change: float) -> float:
    """
    Convert percent improvement to 1-10 score.

    effective_change is positive when improvement occurs
    (already adjusted for direction by caller).

    >=60% improvement: 10, >=50%: 9, >=40%: 8, >=30%: 7,
    >=20%: 6, >=10%: 5, 0-10%: 4, worsening: 2-3
    """
    if effective_change >= 60:
        return 10.0
    elif effective_change >= 50:
        return 9.0
    elif effective_change >= 40:
        return 8.0
    elif effective_change >= 30:
        return 7.0
    elif effective_change >= 20:
        return 6.0
    elif effective_change >= 10:
        return 5.0
    elif effective_change >= 0:
        return 4.0
    elif effective_change >= -10:
        return 3.0
    else:
        return 2.0


def _is_decrease_good(endpoint_name: str) -> bool:
    """
    Determine if a decrease in endpoint value indicates improvement.

    Most disease activity scores: decrease = improvement
    Quality of life / response rates: increase = improvement
    """
    endpoint_lower = endpoint_name.lower()

    # Endpoints where INCREASE is good (return False = decrease is NOT good)
    increase_good_patterns = [
        # Response rates
        'acr20', 'acr50', 'acr70', 'acr90',
        'pasi50', 'pasi75', 'pasi90', 'pasi100',
        'easi50', 'easi75', 'easi90',
        'salt50', 'salt75', 'salt90',
        'response', 'responder', 'remission',
        # Quality of life
        'quality of life', 'qol',
        'sf-36', 'sf36',
        'eq-5d', 'eq5d',
        'facit', 'well-being', 'wellbeing',
        # Function
        'function', 'improvement',
        # Clear/almost clear assessments
        'iga 0', 'iga 1', 'clear', 'almost clear',
        # Hair regrowth
        'regrowth', 'hair growth',
    ]

    for pattern in increase_good_patterns:
        if pattern in endpoint_lower:
            return False  # Increase is good, so decrease is NOT good

    # Default: most clinical scores decrease = improvement
    return True


class ClinicalScorer:
    """
    Scores clinical signals from case series extractions.

    Provides scoring for:
    - Response rate (quality-weighted across multiple endpoints)
    - Safety profile (SAE rates, regulatory flags)
    - Organ domain breadth (multi-organ response)
    """

    # Gold-standard validated instruments (disease-agnostic)
    GOLD_STANDARD_PATTERNS = {
        # Rheumatology
        'acr20': 10, 'acr50': 10, 'acr70': 10, 'acr90': 10,
        'das28': 10, 'das-28': 10,
        'sdai': 9, 'cdai': 9,
        'haq': 9, 'haq-di': 9,
        # Lupus
        'sledai': 10, 'sledai-2k': 10,
        'bilag': 10,
        'sri': 9, 'sri-4': 9, 'sri-5': 9,
        'clasi': 9,
        # Dermatology
        'pasi': 10, 'pasi50': 10, 'pasi75': 10, 'pasi90': 10, 'pasi100': 10,
        'easi': 10, 'easi50': 10, 'easi75': 10, 'easi90': 10,
        'iga': 9, 'iga 0/1': 9,
        'dlqi': 9,
        'scorad': 9,
        'salt': 9, 'salt50': 9, 'salt75': 9, 'salt90': 9,
        # GI
        'mayo': 9, 'mayo score': 9,
        'ses-cd': 9,
        # Neurology
        'edss': 9,
        # General
        'sf-36': 8, 'sf36': 8,
        'eq-5d': 8, 'eq5d': 8,
        'facit': 8, 'facit-fatigue': 8,
        'pain vas': 7, 'vas pain': 7,
        'physician global': 7, 'pga': 7,
        'patient global': 7,
    }

    # Fallback organ domains
    DEFAULT_ORGAN_DOMAINS = {
        'musculoskeletal': ['joint', 'arthritis', 'das28', 'acr20', 'acr50', 'haq'],
        'mucocutaneous': ['skin', 'rash', 'pasi', 'easi', 'bsa'],
        'renal': ['kidney', 'renal', 'proteinuria', 'creatinine', 'gfr'],
        'neurological': ['neuro', 'cognitive', 'edss', 'relapse'],
        'hematological': ['anemia', 'platelet', 'neutropenia', 'cytopenia'],
        'cardiopulmonary': ['cardiac', 'lung', 'fvc', 'dlco'],
        'immunological': ['complement', 'autoantibody', 'crp', 'esr'],
        'systemic': ['sledai', 'bilag', 'bvas', 'disease activity'],
        'gastrointestinal': ['gi', 'bowel', 'mayo', 'cdai'],
        'ocular': ['eye', 'uveitis', 'visual acuity'],
        'constitutional': ['fatigue', 'fever', 'weight loss'],
    }

    # Fallback safety categories
    DEFAULT_SAFETY_CATEGORIES = {
        'serious_infection': {'keywords': ['serious infection', 'sepsis', 'pneumonia', 'tb'], 'severity_weight': 9, 'regulatory_flag': True},
        'malignancy': {'keywords': ['malignancy', 'cancer', 'lymphoma'], 'severity_weight': 10, 'regulatory_flag': True},
        'cardiovascular': {'keywords': ['mace', 'mi', 'stroke', 'heart failure'], 'severity_weight': 9, 'regulatory_flag': True},
        'thromboembolic': {'keywords': ['vte', 'dvt', 'pe', 'thrombosis'], 'severity_weight': 9, 'regulatory_flag': True},
        'hepatotoxicity': {'keywords': ['hepatotoxicity', 'liver injury', 'alt increased'], 'severity_weight': 8, 'regulatory_flag': True},
        'cytopenia': {'keywords': ['neutropenia', 'thrombocytopenia', 'anemia'], 'severity_weight': 7, 'regulatory_flag': True},
        'death': {'keywords': ['death', 'fatal', 'mortality'], 'severity_weight': 10, 'regulatory_flag': True},
    }

    # Generic validated instruments
    GENERIC_INSTRUMENTS = {
        'Physician Global': 7,
        'Patient Global': 7,
        'SF-36': 8,
        'EQ-5D': 8,
        'Pain VAS': 7,
        'FACIT-Fatigue': 8,
    }

    def __init__(self, repository: Optional[CaseSeriesRepositoryProtocol] = None):
        """
        Initialize the clinical scorer.

        Args:
            repository: Optional repository for loading reference data
        """
        self._repository = repository
        self._organ_domains: Optional[Dict[str, List[str]]] = None
        self._safety_categories: Optional[Dict[str, Dict[str, Any]]] = None

    def score_response_rate(
        self,
        extraction: CaseSeriesExtraction,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Score response rate using quality-weighted multi-endpoint approach.

        Returns:
            Tuple of (score, breakdown_dict)
        """
        breakdown = {
            'method': 'multi_endpoint_quality_weighted',
            'n_endpoints_scored': 0,
            'primary_score': None,
            'secondary_avg_score': None,
            'weighted_avg_score': None,
            'concordance_multiplier': 1.0,
            'best_endpoint_score': None,
            'final_score': None,
            'endpoint_details': []
        }

        # Fallback if no detailed endpoints available
        if not extraction.detailed_efficacy_endpoints:
            base_score = self._score_response_rate_fallback(extraction)
            breakdown['method'] = 'fallback_no_detailed_endpoints'
            breakdown['final_score'] = base_score
            return base_score, breakdown

        # Get validated instruments for this disease
        disease = extraction.disease or extraction.disease_normalized or ""
        validated_instruments = self._get_validated_instruments_for_disease(disease)

        # Score each endpoint
        endpoint_scores = []
        primary_scores = []
        secondary_scores = []
        exploratory_scores = []

        for ep in extraction.detailed_efficacy_endpoints:
            # Get efficacy score (how good were the results?)
            efficacy_score, efficacy_detail = self._score_single_endpoint(ep)

            # Get quality score (how good was the instrument?)
            quality_score = self._get_endpoint_quality_score(ep, validated_instruments)

            # Determine category (defaults to secondary if unknown)
            raw_category = getattr(ep, 'endpoint_category', '') if hasattr(ep, 'endpoint_category') else ''
            category, category_weight = self._get_category_and_weight(raw_category)

            # Calculate quality weight (scale 0.4 to 1.0)
            quality_weight = 0.4 + (quality_score / 10) * 0.6

            # Combined weight
            combined_weight = category_weight * quality_weight

            endpoint_info = {
                'name': getattr(ep, 'endpoint_name', 'Unknown'),
                'category': category,
                'category_inferred': raw_category == '' or raw_category is None,
                'efficacy_score': efficacy_score,
                'quality_score': quality_score,
                'category_weight': category_weight,
                'quality_weight': round(quality_weight, 2),
                'combined_weight': round(combined_weight, 2),
                'efficacy_detail': efficacy_detail
            }
            endpoint_scores.append(endpoint_info)

            # Track by category for reporting
            if category == 'primary':
                primary_scores.append(efficacy_score)
            elif category == 'secondary':
                secondary_scores.append(efficacy_score)
            else:
                exploratory_scores.append(efficacy_score)

        breakdown['endpoint_details'] = endpoint_scores
        breakdown['n_endpoints_scored'] = len(endpoint_scores)

        # Calculate weighted average
        weighted_sum = 0.0
        total_weight = 0.0

        for ep_info in endpoint_scores:
            weighted_sum += ep_info['efficacy_score'] * ep_info['combined_weight']
            total_weight += ep_info['combined_weight']

        weighted_avg = weighted_sum / total_weight if total_weight > 0 else 5.0
        breakdown['weighted_avg_score'] = round(weighted_avg, 2)

        # Track category averages for reporting
        if primary_scores:
            breakdown['primary_score'] = round(sum(primary_scores) / len(primary_scores), 2)
        if secondary_scores:
            breakdown['secondary_avg_score'] = round(sum(secondary_scores) / len(secondary_scores), 2)

        # Calculate concordance multiplier
        concordance_mult = self._calculate_concordance_multiplier(endpoint_scores)
        breakdown['concordance_multiplier'] = concordance_mult

        # Find best single endpoint (prevents dilution of strong signals)
        all_efficacy_scores = [ep['efficacy_score'] for ep in endpoint_scores]
        best_score = max(all_efficacy_scores) if all_efficacy_scores else 5.0
        breakdown['best_endpoint_score'] = best_score

        # Final score calculation:
        # 70% weighted average (with concordance) + 30% best endpoint
        adjusted_avg = weighted_avg * concordance_mult
        final_score = (adjusted_avg * 0.70) + (best_score * 0.30)

        # Clamp to 1-10
        final_score = max(1.0, min(10.0, final_score))
        breakdown['final_score'] = round(final_score, 1)

        return round(final_score, 1), breakdown

    def score_safety_profile(
        self,
        extraction: CaseSeriesExtraction,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Score safety profile with detailed breakdown by category.

        Returns:
            Tuple of (score, breakdown_dict)
        """
        breakdown = {
            'categories_detected': [],
            'serious_signals': [],
            'regulatory_flags': [],
            'sae_percentage': None,
            'discontinuation_rate': None,
        }

        # Collect all safety text
        safety_texts = []

        # From detailed safety endpoints
        if extraction.detailed_safety_endpoints:
            for ep in extraction.detailed_safety_endpoints:
                if hasattr(ep, 'event_name') and ep.event_name:
                    safety_texts.append(ep.event_name.lower())
                if hasattr(ep, 'event_category') and ep.event_category:
                    safety_texts.append(ep.event_category.lower())

        # From SAE list
        if extraction.safety.serious_adverse_events:
            for sae in extraction.safety.serious_adverse_events:
                safety_texts.append(sae.lower())

        # From AE list
        if extraction.safety.adverse_events:
            for ae in extraction.safety.adverse_events:
                safety_texts.append(ae.lower())

        combined_text = ' '.join(safety_texts)

        # Classify safety signals using categories
        safety_categories = self._get_safety_categories()
        category_scores = []
        for category, config in safety_categories.items():
            for keyword in config['keywords']:
                if keyword.lower() in combined_text:
                    breakdown['categories_detected'].append(category)
                    category_scores.append(config['severity_weight'])

                    if config['severity_weight'] >= 8:
                        breakdown['serious_signals'].append(category)
                    if config.get('regulatory_flag', False):
                        breakdown['regulatory_flags'].append(category)
                    break  # One match per category

        # Calculate base score from SAE percentage
        base_score = 5.0
        if extraction.safety.sae_percentage is not None:
            breakdown['sae_percentage'] = extraction.safety.sae_percentage
            sae_pct = extraction.safety.sae_percentage
            if sae_pct == 0:
                base_score = 10.0
            elif sae_pct < 5:
                base_score = 8.0
            elif sae_pct < 10:
                base_score = 6.0
            elif sae_pct < 20:
                base_score = 4.0
            else:
                base_score = 2.0
        elif extraction.safety.safety_profile == SafetyProfile.FAVORABLE:
            base_score = 9.0
        elif extraction.safety.safety_profile == SafetyProfile.ACCEPTABLE:
            base_score = 7.0
        elif extraction.safety.safety_profile == SafetyProfile.CONCERNING:
            base_score = 3.0

        # Adjust based on detected categories
        if category_scores:
            avg_severity = sum(category_scores) / len(category_scores)
            severity_penalty = (avg_severity - 5) * 0.3
            base_score = max(1.0, min(10.0, base_score - severity_penalty))

        # Extra penalty for regulatory flags
        n_regulatory = len(set(breakdown['regulatory_flags']))
        if n_regulatory >= 3:
            base_score = max(1.0, base_score - 2.0)
        elif n_regulatory >= 1:
            base_score = max(1.0, base_score - 1.0)

        # Deduplicate lists
        breakdown['categories_detected'] = list(set(breakdown['categories_detected']))
        breakdown['serious_signals'] = list(set(breakdown['serious_signals']))
        breakdown['regulatory_flags'] = list(set(breakdown['regulatory_flags']))

        return round(base_score, 1), breakdown

    def score_organ_domain_breadth(
        self,
        extraction: CaseSeriesExtraction,
    ) -> float:
        """
        Score the breadth of organ domain response.

        Multi-organ response indicates broader therapeutic effect.
        1 domain=4, 2 domains=6, 3 domains=8, 4+ domains=10

        Returns:
            Score from 1-10
        """
        # Collect all endpoint text for matching
        endpoint_texts = []

        # From detailed efficacy endpoints
        if extraction.detailed_efficacy_endpoints:
            for ep in extraction.detailed_efficacy_endpoints:
                if hasattr(ep, 'endpoint_name') and ep.endpoint_name:
                    endpoint_texts.append(ep.endpoint_name.lower())
                if hasattr(ep, 'endpoint_category') and ep.endpoint_category:
                    endpoint_texts.append(ep.endpoint_category.lower())
                if hasattr(ep, 'notes') and ep.notes:
                    endpoint_texts.append(ep.notes.lower())

        # From efficacy summary
        if extraction.efficacy.primary_endpoint:
            endpoint_texts.append(extraction.efficacy.primary_endpoint.lower())
        if extraction.efficacy.efficacy_summary:
            endpoint_texts.append(extraction.efficacy.efficacy_summary.lower())

        # Combine all text for matching
        combined_text = ' '.join(endpoint_texts)

        # Find matching domains
        organ_domains = self._get_organ_domains()
        matched_domains = set()
        for domain, keywords in organ_domains.items():
            for keyword in keywords:
                if keyword.lower() in combined_text:
                    matched_domains.add(domain)
                    break

        # Score based on number of domains
        n_domains = len(matched_domains)
        if n_domains >= 4:
            return 10.0
        elif n_domains == 3:
            return 8.0
        elif n_domains == 2:
            return 6.0
        elif n_domains == 1:
            return 4.0
        else:
            return 3.0

    def get_matched_organ_domains(
        self,
        extraction: CaseSeriesExtraction,
    ) -> List[str]:
        """
        Get list of organ domains matched for an extraction.

        Used for reporting which organ systems showed response.
        """
        endpoint_texts = []

        if extraction.detailed_efficacy_endpoints:
            for ep in extraction.detailed_efficacy_endpoints:
                if hasattr(ep, 'endpoint_name') and ep.endpoint_name:
                    endpoint_texts.append(ep.endpoint_name.lower())
                if hasattr(ep, 'notes') and ep.notes:
                    endpoint_texts.append(ep.notes.lower())

        if extraction.efficacy.primary_endpoint:
            endpoint_texts.append(extraction.efficacy.primary_endpoint.lower())
        if extraction.efficacy.efficacy_summary:
            endpoint_texts.append(extraction.efficacy.efficacy_summary.lower())

        combined_text = ' '.join(endpoint_texts)
        organ_domains = self._get_organ_domains()

        matched_domains = []
        for domain, keywords in organ_domains.items():
            for keyword in keywords:
                if keyword.lower() in combined_text:
                    matched_domains.append(domain)
                    break

        return sorted(matched_domains)

    # -------------------------------------------------------------------------
    # Private Helper Methods
    # -------------------------------------------------------------------------

    def _score_response_rate_fallback(self, extraction: CaseSeriesExtraction) -> float:
        """Fallback scoring when no detailed endpoints available."""
        if extraction.efficacy.responders_pct is not None:
            return _response_pct_to_score(extraction.efficacy.responders_pct)

        if extraction.efficacy_signal == EfficacySignal.STRONG:
            return 8.5
        elif extraction.efficacy_signal == EfficacySignal.MODERATE:
            return 6.0
        elif extraction.efficacy_signal == EfficacySignal.WEAK:
            return 3.5
        elif extraction.efficacy_signal == EfficacySignal.NONE:
            return 1.5

        return 5.0

    def _score_single_endpoint(self, ep) -> Tuple[float, Dict[str, Any]]:
        """Score a single efficacy endpoint on 1-10 scale."""
        detail = {
            'scoring_basis': None,
            'raw_value': None,
            'interpretation': None
        }

        # Priority 1: Response rate percentage
        responders_pct = getattr(ep, 'responders_pct', None)
        if responders_pct is not None:
            try:
                pct = float(responders_pct)
                score = _response_pct_to_score(pct)
                detail['scoring_basis'] = 'responders_pct'
                detail['raw_value'] = pct
                detail['interpretation'] = f"{pct:.0f}% responders"
                return score, detail
            except (ValueError, TypeError):
                pass

        # Priority 2: Percent change from baseline
        change_pct = getattr(ep, 'change_pct', None)
        if change_pct is not None:
            try:
                pct = float(change_pct)
                ep_name = getattr(ep, 'endpoint_name', '').lower()
                decrease_is_good = _is_decrease_good(ep_name)
                effective_change = -pct if decrease_is_good else pct
                score = _percent_change_to_score(effective_change)
                detail['scoring_basis'] = 'change_pct'
                detail['raw_value'] = pct
                direction = 'improvement' if effective_change > 0 else 'worsening'
                detail['interpretation'] = f"{pct:.1f}% change ({direction})"
                return score, detail
            except (ValueError, TypeError):
                pass

        # Priority 3: Absolute change from baseline
        change = getattr(ep, 'change_from_baseline', None)
        baseline = getattr(ep, 'baseline_value', None)
        if change is not None:
            try:
                change_val = float(change)
                ep_name = getattr(ep, 'endpoint_name', '').lower()
                decrease_is_good = _is_decrease_good(ep_name)

                if baseline is not None:
                    try:
                        baseline_val = float(baseline)
                        if baseline_val != 0:
                            calc_pct = (change_val / baseline_val) * 100
                            effective_change = -calc_pct if decrease_is_good else calc_pct
                            score = _percent_change_to_score(effective_change)
                            detail['scoring_basis'] = 'calculated_pct_change'
                            detail['raw_value'] = round(calc_pct, 1)
                            detail['interpretation'] = f"Calculated {calc_pct:.1f}% change from baseline"
                            return score, detail
                    except (ValueError, TypeError):
                        pass

                # Can't calculate %, use direction only
                is_improved = (change_val < 0) if decrease_is_good else (change_val > 0)
                score = 6.5 if is_improved else 3.5
                detail['scoring_basis'] = 'direction_only'
                detail['raw_value'] = change_val
                detail['interpretation'] = f"Change of {change_val} ({'improved' if is_improved else 'worsened'})"
                return score, detail
            except (ValueError, TypeError):
                pass

        # Priority 4: Statistical significance as weak proxy
        if getattr(ep, 'statistical_significance', False):
            detail['scoring_basis'] = 'statistical_significance'
            detail['raw_value'] = True
            detail['interpretation'] = 'Statistically significant (p<0.05), direction assumed positive'
            return 6.0, detail

        # Check p-value directly
        p_value = getattr(ep, 'p_value', None)
        if p_value is not None:
            try:
                p_str = str(p_value).replace('<', '').replace('>', '').strip()
                p = float(p_str)
                if p < 0.05:
                    detail['scoring_basis'] = 'p_value'
                    detail['raw_value'] = p_value
                    detail['interpretation'] = f'p={p_value}, assumed positive direction'
                    return 6.0, detail
            except (ValueError, TypeError):
                pass

        # Unable to score - return neutral
        detail['scoring_basis'] = 'insufficient_data'
        detail['interpretation'] = 'Could not determine efficacy from available data'
        return 5.0, detail

    def _get_category_and_weight(self, raw_category: str) -> Tuple[str, float]:
        """Get normalized category and weight for an endpoint."""
        category_lower = (raw_category or '').lower().strip()

        if category_lower in ['primary', 'main', 'principal', 'primary endpoint',
                              'primary outcome', 'main outcome']:
            return 'primary', 1.0

        if category_lower in ['exploratory', 'tertiary', 'post-hoc', 'additional',
                              'exploratory endpoint', 'post hoc', 'supplementary']:
            return 'exploratory', 0.3

        return 'secondary', 0.6

    def _get_endpoint_quality_score(
        self,
        ep,
        validated_instruments: Dict[str, int],
    ) -> float:
        """Get quality score for an endpoint based on validated instruments."""
        ep_name = getattr(ep, 'endpoint_name', '') or ''
        ep_name_lower = ep_name.lower()

        # Check against disease-specific validated instruments
        best_score = 0
        for instrument, score in validated_instruments.items():
            if instrument.lower() in ep_name_lower or ep_name_lower in instrument.lower():
                best_score = max(best_score, score)

        if best_score > 0:
            return float(best_score)

        # Check against gold-standard patterns
        for pattern, score in self.GOLD_STANDARD_PATTERNS.items():
            if pattern in ep_name_lower:
                return float(score)

        # Check for generic positive indicators
        moderate_patterns = ['remission', 'response', 'responder', 'improvement']
        for pattern in moderate_patterns:
            if pattern in ep_name_lower:
                return 7.0

        # Ad-hoc endpoint
        return 4.0

    def _calculate_concordance_multiplier(
        self,
        endpoint_scores: List[Dict],
    ) -> float:
        """Calculate concordance multiplier (0.85 to 1.15)."""
        if len(endpoint_scores) < 2:
            return 1.0

        scores = [ep['efficacy_score'] for ep in endpoint_scores]

        positive = sum(1 for s in scores if s > 5.5)
        negative = sum(1 for s in scores if s < 4.5)
        neutral = sum(1 for s in scores if 4.5 <= s <= 5.5)
        total = len(scores)

        if positive >= negative:
            concordance = (positive + neutral * 0.5) / total
        else:
            concordance = (negative + neutral * 0.5) / total

        if concordance >= 0.9:
            return 1.15
        elif concordance >= 0.75:
            return 1.10
        elif concordance >= 0.6:
            return 1.0
        elif concordance >= 0.4:
            return 0.90
        else:
            return 0.85

    def _get_validated_instruments_for_disease(self, disease: str) -> Dict[str, int]:
        """Get validated instruments for a disease."""
        if not disease:
            return self.GENERIC_INSTRUMENTS.copy()

        if self._repository:
            instruments = self._repository.find_instruments_for_disease(disease)
            if instruments:
                return instruments

        return self.GENERIC_INSTRUMENTS.copy()

    def _get_organ_domains(self) -> Dict[str, List[str]]:
        """Get organ domain keyword mappings."""
        if self._organ_domains is not None:
            return self._organ_domains

        if self._repository:
            domains = self._repository.get_organ_domains()
            if domains:
                self._organ_domains = domains
                return self._organ_domains

        self._organ_domains = self.DEFAULT_ORGAN_DOMAINS.copy()
        return self._organ_domains

    def _get_safety_categories(self) -> Dict[str, Dict[str, Any]]:
        """Get safety signal category definitions."""
        if self._safety_categories is not None:
            return self._safety_categories

        if self._repository:
            categories = self._repository.get_safety_categories()
            if categories:
                self._safety_categories = categories
                return self._safety_categories

        self._safety_categories = self.DEFAULT_SAFETY_CATEGORIES.copy()
        return self._safety_categories
