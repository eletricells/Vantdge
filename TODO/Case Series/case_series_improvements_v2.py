"""
Drug Repurposing Case Series Agent - Recommended Improvements (v2)

This file contains consolidated improvements for:
1. Multi-endpoint efficacy scoring with quality weighting
   - Defaults to "secondary" weight when category unknown
   - LLM guidance for inferring category from context
2. Sample size penalties calibrated for case series (max N=20)
3. Cross-study aggregation with adjusted confidence thresholds
4. Consolidated Analysis Summary sheet with top 5 opportunities

To integrate: Replace or augment the corresponding methods in your main
drug_repurposing_case_series_agent.py file.

CHANGELOG from v1:
- Endpoint category defaults to "secondary" (0.6 weight) when not specified
- Sample size thresholds: 20/15/10/5/3/2/1 (was 100/50/30/20/10/5/1)
- Evidence confidence thresholds adjusted to match case series reality
- Executive summary shows top 5 opportunities (was top 3)
"""

from typing import Dict, List, Tuple, Any, Optional


# =============================================================================
# SECTION 1: MULTI-ENDPOINT EFFICACY SCORING WITH QUALITY WEIGHTING
# =============================================================================

def _score_response_rate_v2(self, ext) -> Tuple[float, Dict[str, Any]]:
    """
    Enhanced response rate scoring using totality of efficacy endpoints
    with quality weighting.
    
    Returns (score, breakdown_dict) where score is 1-10.
    
    Scoring approach:
    1. Score each endpoint individually (1-10 based on results)
    2. Get quality score for each endpoint (validated vs ad-hoc)
    3. Calculate weight = (category_weight) × (quality_weight)
    4. Compute weighted average across all endpoints
    5. Apply concordance multiplier (0.85-1.15)
    6. Blend with best single endpoint to prevent dilution
    
    Category weights: Primary=1.0, Secondary=0.6, Exploratory=0.3
                      Unknown defaults to Secondary (0.6)
    Quality weights: Scaled from 0.4 (ad-hoc) to 1.0 (validated gold-standard)
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
    if not ext.detailed_efficacy_endpoints:
        base_score = self._score_response_rate_fallback(ext)
        breakdown['method'] = 'fallback_no_detailed_endpoints'
        breakdown['final_score'] = base_score
        return base_score, breakdown
    
    # Get validated instruments for this disease
    disease = ext.disease or ext.disease_normalized or ""
    validated_instruments = self._get_validated_instruments_for_disease(disease)
    
    # Score each endpoint
    endpoint_scores = []
    primary_scores = []
    secondary_scores = []
    exploratory_scores = []
    
    for ep in ext.detailed_efficacy_endpoints:
        # Get efficacy score (how good were the results?)
        efficacy_score, efficacy_detail = self._score_single_endpoint(ep)
        
        # Get quality score (how good was the instrument?)
        quality_score = self._get_endpoint_quality_score(ep, validated_instruments)
        
        # Determine category (defaults to secondary if unknown)
        raw_category = getattr(ep, 'endpoint_category', '') if hasattr(ep, 'endpoint_category') else ''
        category, category_weight = self._get_category_and_weight(raw_category)
        
        # Calculate quality weight (scale 0.4 to 1.0)
        # quality_score is 1-10, map to 0.4-1.0
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


def _get_category_and_weight(self, raw_category: str) -> Tuple[str, float]:
    """
    Get normalized category and weight for an endpoint.
    
    Handles missing/unknown categories by defaulting to "secondary" (0.6 weight).
    This is conservative - not over-weighting or under-weighting when we don't know.
    
    The LLM extraction should try to infer category from context:
    - "Main outcome" / prominent in abstract/conclusion → primary
    - "Also measured" / mentioned in results → secondary  
    - "Additionally noted" / supplementary → exploratory
    - Can't tell → leave blank (defaults to secondary here)
    
    Returns: (normalized_category, weight)
    """
    category_lower = (raw_category or '').lower().strip()
    
    # Primary indicators
    if category_lower in ['primary', 'main', 'principal', 'primary endpoint', 
                          'primary outcome', 'main outcome']:
        return 'primary', 1.0
    
    # Exploratory indicators
    if category_lower in ['exploratory', 'tertiary', 'post-hoc', 'additional',
                          'exploratory endpoint', 'post hoc', 'supplementary']:
        return 'exploratory', 0.3
    
    # Secondary or unknown → default to secondary weight
    # This includes: 'secondary', '', None, or any unrecognized value
    return 'secondary', 0.6


def _score_single_endpoint(self, ep) -> Tuple[float, Dict[str, Any]]:
    """
    Score a single efficacy endpoint on 1-10 scale based on results.
    
    Priority order:
    1. Response rate percentage (most direct)
    2. Percent change from baseline
    3. Absolute change from baseline (calculate % if possible)
    4. Statistical significance (weak proxy)
    
    Returns (score, detail_dict)
    """
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
            
            # Flip sign so positive = improvement
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
            
            # Try to calculate percent change if we have baseline
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
            # Handle strings like "<0.001" or "0.03"
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


def _get_endpoint_quality_score(self, ep, validated_instruments: Dict[str, int]) -> float:
    """
    Get quality score for an endpoint based on whether it uses validated instruments.
    
    Returns score from 1-10:
    - 10: Gold-standard validated instrument (ACR50, DAS28, SLEDAI, etc.)
    - 7-9: Known validated instruments
    - 4-6: Generic or ad-hoc measures
    - 4: Completely ad-hoc
    """
    ep_name = getattr(ep, 'endpoint_name', '') or ''
    ep_name_lower = ep_name.lower()
    
    # Check against disease-specific validated instruments from database
    best_score = 0
    for instrument, score in validated_instruments.items():
        if instrument.lower() in ep_name_lower or ep_name_lower in instrument.lower():
            best_score = max(best_score, score)
    
    if best_score > 0:
        return float(best_score)
    
    # Check against gold-standard patterns (disease-agnostic)
    gold_standard_patterns = {
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
        'salt': 9, 'salt50': 9, 'salt75': 9, 'salt90': 9,  # Alopecia
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
    
    for pattern, score in gold_standard_patterns.items():
        if pattern in ep_name_lower:
            return float(score)
    
    # Check for generic positive indicators
    moderate_patterns = ['remission', 'response', 'responder', 'improvement']
    for pattern in moderate_patterns:
        if pattern in ep_name_lower:
            return 7.0
    
    # Ad-hoc endpoint
    return 4.0


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
    # (DAS28, SLEDAI, PASI score, SALT score, pain VAS, disease activity, etc.)
    return True


def _calculate_concordance_multiplier(self, endpoint_scores: List[Dict]) -> float:
    """
    Calculate concordance multiplier (0.85 to 1.15).
    
    High concordance (most endpoints agree on direction) = bonus
    Low concordance (mixed/contradictory results) = penalty
    """
    if len(endpoint_scores) < 2:
        return 1.0  # No adjustment for single endpoint
    
    scores = [ep['efficacy_score'] for ep in endpoint_scores]
    
    # Classify each endpoint result
    positive = sum(1 for s in scores if s > 5.5)   # Clearly positive
    negative = sum(1 for s in scores if s < 4.5)   # Clearly negative
    neutral = sum(1 for s in scores if 4.5 <= s <= 5.5)  # Neutral/unknown
    total = len(scores)
    
    # Calculate concordance - what fraction point in the same direction?
    if positive >= negative:
        # Majority positive
        concordance = (positive + neutral * 0.5) / total
    else:
        # Majority negative (still concordant, just concordantly bad)
        concordance = (negative + neutral * 0.5) / total
    
    # Map concordance to multiplier
    if concordance >= 0.9:
        return 1.15  # Very high agreement
    elif concordance >= 0.75:
        return 1.10  # Good agreement
    elif concordance >= 0.6:
        return 1.0   # Acceptable agreement
    elif concordance >= 0.4:
        return 0.90  # Mixed results
    else:
        return 0.85  # Contradictory results


def _score_response_rate_fallback(self, ext) -> float:
    """
    Fallback scoring when no detailed endpoints available.
    Uses summary efficacy data from extraction.
    """
    # Try responders_pct from summary
    if ext.efficacy.responders_pct is not None:
        return _response_pct_to_score(ext.efficacy.responders_pct)
    
    # Use efficacy signal enum
    from src.models.case_series_schemas import EfficacySignal
    
    if ext.efficacy_signal == EfficacySignal.STRONG:
        return 8.5
    elif ext.efficacy_signal == EfficacySignal.MODERATE:
        return 6.0
    elif ext.efficacy_signal == EfficacySignal.WEAK:
        return 3.5
    elif ext.efficacy_signal == EfficacySignal.NONE:
        return 1.5
    
    return 5.0  # Unknown


# =============================================================================
# SECTION 2: UPDATED CLINICAL SIGNAL SCORING
# =============================================================================

def _score_opportunity_v2(self, opp) -> 'OpportunityScores':
    """
    Score a single repurposing opportunity.
    
    UPDATED: Removed separate endpoint_quality_score since quality is now
    factored into the efficacy score. Redistributed weights.
    
    Clinical Signal (50%):
    - Response rate (quality-weighted): 40%
    - Safety profile: 40%
    - Organ domain breadth: 20%
    
    Evidence Quality (25%):
    - Sample size: 35%
    - Publication venue: 25%
    - Response durability: 25%
    - Extraction completeness: 15%
    
    Market Opportunity (25%):
    - Competitors: 33%
    - Market size: 33%
    - Unmet need: 33%
    """
    ext = opp.extraction
    
    # Clinical Signal Score (50% of overall)
    response_score, response_breakdown = self._score_response_rate_v2(ext)
    safety_score, safety_breakdown = self._score_safety_profile_detailed(ext)
    organ_domain_score = self._score_organ_domain_breadth(ext)
    
    clinical_score = (
        response_score * 0.40 +
        safety_score * 0.40 +
        organ_domain_score * 0.20
    )
    
    # Evidence Quality Score (25% of overall)
    sample_score = self._score_sample_size_v2(ext)
    venue_score = self._score_publication_venue(ext)
    durability_score = self._score_response_durability(ext)
    completeness_score = self._score_extraction_completeness(ext)
    
    evidence_score = (
        sample_score * 0.35 +
        venue_score * 0.25 +
        durability_score * 0.25 +
        completeness_score * 0.15
    )
    
    # Market Opportunity Score (25% of overall)
    competitors_score = self._score_competitors(opp)
    market_size_score = self._score_market_size(opp)
    unmet_need_score = self._score_unmet_need(opp)
    market_score = (competitors_score + market_size_score + unmet_need_score) / 3
    
    # Overall Priority
    overall = (
        clinical_score * 0.50 +
        evidence_score * 0.25 +
        market_score * 0.25
    )
    
    # Import here to avoid circular imports
    from src.models.case_series_schemas import OpportunityScores
    
    return OpportunityScores(
        clinical_signal=round(clinical_score, 1),
        evidence_quality=round(evidence_score, 1),
        market_opportunity=round(market_score, 1),
        overall_priority=round(overall, 1),
        # Clinical breakdown
        response_rate_score=round(response_score, 1),
        safety_profile_score=round(safety_score, 1),
        endpoint_quality_score=None,  # Now baked into response_rate_score
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
        },
        # Market breakdown
        competitors_score=round(competitors_score, 1),
        market_size_score=round(market_size_score, 1),
        unmet_need_score=round(unmet_need_score, 1),
        market_breakdown={
            "competitors": round(competitors_score, 1),
            "market_size": round(market_size_score, 1),
            "unmet_need": round(unmet_need_score, 1)
        }
    )


# =============================================================================
# SECTION 3: SAMPLE SIZE SCORING - CALIBRATED FOR CASE SERIES
# =============================================================================

def _score_sample_size_v2(self, ext) -> float:
    """
    Score sample size calibrated for case series (1-10).
    
    For case series, 20+ patients is considered substantial.
    100-patient case series are rare, so thresholds are adjusted accordingly.
    Single case reports get minimal weight.
    
    Scoring:
    N >= 20: 10 (large case series for this literature type)
    N >= 15: 9  (substantial case series)
    N >= 10: 8  (solid case series)
    N >= 5:  6  (small but acceptable series)
    N >= 3:  4  (minimal case series)
    N >= 2:  2  (two-patient case report)
    N = 1:   1  (single case report)
    N = 0:   1  (unknown, treat as single case)
    """
    n = ext.patient_population.n_patients if ext.patient_population else 0
    
    if n >= 20:
        return 10.0
    elif n >= 15:
        return 9.0
    elif n >= 10:
        return 8.0
    elif n >= 5:
        return 6.0
    elif n >= 3:
        return 4.0
    elif n >= 2:
        return 2.0
    else:
        return 1.0  # N=1 or unknown


# =============================================================================
# SECTION 4: CROSS-STUDY AGGREGATION
# =============================================================================

def _aggregate_disease_evidence(
    self,
    disease: str,
    extractions: List[Any]
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
        n = ext.patient_population.n_patients if ext.patient_population else 0
        total_patients += n
        
        resp_pct = ext.efficacy.responders_pct
        resp_n = ext.efficacy.responders_n
        
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
    
    # Determine evidence confidence (calibrated for case series)
    n_studies = len(extractions)
    evidence_confidence = _calculate_evidence_confidence_case_series(
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


def _calculate_evidence_confidence_case_series(
    n_studies: int,
    total_patients: int,
    consistency: str,
    extractions: List[Any]
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
    - Very Low: Everything else
    """
    # Count high-quality extractions (multi-stage with full text)
    high_quality = sum(
        1 for ext in extractions
        if getattr(ext, 'extraction_method', '') == 'multi_stage'
    )
    
    if n_studies >= 3 and total_patients >= 20 and consistency in ['High', 'Moderate']:
        if high_quality >= 2:
            return 'Moderate'
        return 'Low-Moderate'
    elif n_studies >= 2 and total_patients >= 10:
        return 'Low'
    elif n_studies >= 1 and total_patients >= 3:
        return 'Very Low'
    else:
        return 'Very Low'


# =============================================================================
# SECTION 5: CONSOLIDATED ANALYSIS SUMMARY SHEET
# =============================================================================

def _generate_analysis_summary_sheet(
    self,
    result,  # DrugAnalysisResult
    writer   # pd.ExcelWriter
) -> None:
    """
    Generate consolidated Analysis Summary sheet with:
    - Executive summary at top (with TOP 5 opportunities)
    - Disease-level aggregation with pooled estimates
    - Cross-study synthesis
    - Confidence flags
    
    This should be the FIRST sheet in the workbook for easy access.
    """
    import pandas as pd
    
    # =========================================================================
    # STEP 1: AGGREGATE DATA BY DISEASE
    # =========================================================================
    disease_data = {}
    
    for opp in result.opportunities:
        disease = opp.extraction.disease_normalized or opp.extraction.disease or 'Unknown'
        
        if disease not in disease_data:
            disease_data[disease] = {
                'extractions': [],
                'opportunities': [],
                'response_rates': [],
                'sample_sizes': [],
                'efficacy_scores': [],
                'safety_scores': [],
                'overall_scores': [],
                'pmids': [],
                'has_full_text': [],
            }
        
        ext = opp.extraction
        dd = disease_data[disease]
        
        dd['extractions'].append(ext)
        dd['opportunities'].append(opp)
        dd['pmids'].append(ext.source.pmid if ext.source else None)
        dd['has_full_text'].append(
            getattr(ext, 'extraction_method', '') == 'multi_stage'
        )
        
        # Collect numeric data
        n_patients = ext.patient_population.n_patients if ext.patient_population else 0
        dd['sample_sizes'].append(n_patients)
        
        if ext.efficacy.responders_pct is not None:
            dd['response_rates'].append(ext.efficacy.responders_pct)
        
        if opp.scores:
            dd['efficacy_scores'].append(opp.scores.response_rate_score)
            dd['safety_scores'].append(opp.scores.safety_profile_score)
            dd['overall_scores'].append(opp.scores.overall_priority)
    
    # =========================================================================
    # STEP 2: CALCULATE AGGREGATED METRICS PER DISEASE
    # =========================================================================
    summary_rows = []
    
    for disease, dd in disease_data.items():
        # Use aggregation function
        aggregated = self._aggregate_disease_evidence(disease, dd['extractions'])
        
        n_studies = aggregated['n_studies']
        total_patients = aggregated['total_patients']
        pooled_response = aggregated['pooled_response_pct']
        response_range = aggregated['response_range']
        consistency = aggregated['consistency']
        evidence_confidence = aggregated['evidence_confidence']
        
        # Format response range
        range_str = None
        if response_range and len(dd['response_rates']) > 1:
            range_str = f"{response_range[0]:.0f}-{response_range[1]:.0f}%"
        elif pooled_response:
            range_str = f"{pooled_response:.0f}%"
        
        # Best and average scores
        best_efficacy = max(dd['efficacy_scores']) if dd['efficacy_scores'] else None
        best_safety = max(dd['safety_scores']) if dd['safety_scores'] else None
        best_overall = max(dd['overall_scores']) if dd['overall_scores'] else None
        avg_overall = (
            sum(dd['overall_scores']) / len(dd['overall_scores'])
            if dd['overall_scores'] else None
        )
        
        # Build confidence flags
        flags = []
        if total_patients < 5:
            flags.append('⚠️ Very small N (<5)')
        elif total_patients < 10:
            flags.append('⚠️ Small N (<10)')
        
        if n_studies == 1:
            flags.append('Single study')
        
        if consistency == 'Low':
            flags.append('High heterogeneity')
        
        full_text_count = sum(1 for ft in dd['has_full_text'] if ft)
        if full_text_count == 0:
            flags.append('Abstract-only')
        
        # Market data (from first opportunity with market intel)
        market_size = None
        unmet_need = None
        for opp in dd['opportunities']:
            if opp.market_intelligence:
                mi = opp.market_intelligence
                if mi.market_size_estimate:
                    market_size = mi.market_size_estimate
                if mi.standard_of_care and mi.standard_of_care.unmet_need:
                    unmet_need = 'Yes'
                break
        
        summary_rows.append({
            # Disease identification
            'Disease': disease,
            
            # Evidence volume
            'N Studies': n_studies,
            'Total Patients': total_patients,
            'PMIDs': ', '.join(str(p) for p in dd['pmids'] if p),
            
            # Efficacy synthesis
            'Pooled Response (%)': pooled_response,
            'Response Range': range_str,
            'Consistency': consistency,
            
            # Scores
            'Best Efficacy Score': best_efficacy,
            'Best Safety Score': best_safety,
            'Best Overall Score': best_overall,
            'Avg Overall Score': round(avg_overall, 1) if avg_overall else None,
            
            # Confidence assessment
            'Evidence Confidence': evidence_confidence,
            'Flags': '; '.join(flags) if flags else '✓ None',
            
            # Market context
            'Market Size': market_size,
            'Unmet Need': unmet_need,
            
            # Data quality
            'Full Text Available': f"{full_text_count}/{n_studies}",
        })
    
    # Sort by best overall score descending
    summary_rows.sort(key=lambda x: x['Best Overall Score'] or 0, reverse=True)
    
    # =========================================================================
    # STEP 3: BUILD EXECUTIVE SUMMARY
    # =========================================================================
    exec_rows = []
    
    # Header
    exec_rows.append({
        'Section': '═══════════════════════════════════════',
        'Value': 'EXECUTIVE SUMMARY',
        'Detail': '═══════════════════════════════════════'
    })
    exec_rows.append({'Section': '', 'Value': '', 'Detail': ''})
    
    # Basic info
    exec_rows.append({
        'Section': 'Drug Analyzed',
        'Value': result.drug_name,
        'Detail': f"Generic: {result.generic_name or 'N/A'}"
    })
    exec_rows.append({
        'Section': 'Mechanism',
        'Value': (result.mechanism or 'Unknown')[:60],
        'Detail': ''
    })
    exec_rows.append({
        'Section': 'Analysis Date',
        'Value': result.analysis_date.strftime("%Y-%m-%d"),
        'Detail': ''
    })
    exec_rows.append({
        'Section': 'Total Indications Found',
        'Value': len(disease_data),
        'Detail': f"from {len(result.opportunities)} publication(s)"
    })
    exec_rows.append({'Section': '', 'Value': '', 'Detail': ''})
    
    # Top 5 opportunities
    exec_rows.append({
        'Section': '─── TOP 5 OPPORTUNITIES ───',
        'Value': '',
        'Detail': ''
    })
    
    top_5 = summary_rows[:5]
    for i, row in enumerate(top_5, 1):
        response_str = f"{row['Pooled Response (%)']}%" if row['Pooled Response (%)'] else 'N/A'
        exec_rows.append({
            'Section': f'#{i}',
            'Value': row['Disease'],
            'Detail': f"Score: {row['Best Overall Score']}, N={row['Total Patients']}, Response: {response_str}"
        })
    
    # Pad if fewer than 5
    if len(top_5) < 5:
        for i in range(len(top_5) + 1, 6):
            exec_rows.append({
                'Section': f'#{i}',
                'Value': '—',
                'Detail': ''
            })
    
    exec_rows.append({'Section': '', 'Value': '', 'Detail': ''})
    
    # Key statistics
    exec_rows.append({
        'Section': '─── KEY STATISTICS ───',
        'Value': '',
        'Detail': ''
    })
    
    high_priority = sum(
        1 for row in summary_rows
        if row['Best Overall Score'] and row['Best Overall Score'] >= 7
    )
    exec_rows.append({
        'Section': 'High Priority (Score ≥7)',
        'Value': high_priority,
        'Detail': 'indication(s)'
    })
    
    moderate_confidence = sum(
        1 for row in summary_rows
        if 'Moderate' in (row['Evidence Confidence'] or '')
    )
    exec_rows.append({
        'Section': 'Moderate+ Confidence',
        'Value': moderate_confidence,
        'Detail': 'indication(s)'
    })
    
    flagged = sum(1 for row in summary_rows if '⚠️' in (row['Flags'] or ''))
    exec_rows.append({
        'Section': 'With Data Limitations',
        'Value': flagged,
        'Detail': 'indication(s) - see Flags column'
    })
    
    exec_rows.append({'Section': '', 'Value': '', 'Detail': ''})
    
    # Limitations disclaimer
    exec_rows.append({
        'Section': '─── LIMITATIONS ───',
        'Value': '',
        'Detail': ''
    })
    exec_rows.append({
        'Section': 'Note',
        'Value': 'Case series evidence only',
        'Detail': 'Not RCT-level; publication bias likely'
    })
    
    exec_rows.append({'Section': '', 'Value': '', 'Detail': ''})
    exec_rows.append({
        'Section': '═══════════════════════════════════════',
        'Value': 'DISEASE-LEVEL SUMMARY',
        'Detail': '═══════════════════════════════════════'
    })
    exec_rows.append({'Section': '', 'Value': '', 'Detail': ''})
    
    # =========================================================================
    # STEP 4: WRITE TO EXCEL
    # =========================================================================
    
    # Create dataframes
    exec_df = pd.DataFrame(exec_rows)
    summary_df = pd.DataFrame(summary_rows)
    
    # Write executive summary first
    exec_df.to_excel(writer, sheet_name='Analysis Summary', index=False, startrow=0)
    
    # Write disease summary below (with 1 row gap)
    start_row = len(exec_rows) + 1
    summary_df.to_excel(writer, sheet_name='Analysis Summary', index=False, startrow=start_row)
    
    # Try to auto-adjust column widths
    try:
        worksheet = writer.sheets['Analysis Summary']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    cell_len = len(str(cell.value)) if cell.value else 0
                    if cell_len > max_length:
                        max_length = cell_len
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    except Exception:
        pass  # Column width adjustment is optional


# =============================================================================
# SECTION 6: INTEGRATION GUIDE
# =============================================================================

"""
INTEGRATION CHECKLIST
=====================

1. REPLACE these methods in your main file:
   - _score_response_rate      → _score_response_rate_v2
   - _score_opportunity        → _score_opportunity_v2
   - _score_sample_size        → _score_sample_size_v2

2. ADD these new methods to your class:
   - _get_category_and_weight
   - _score_single_endpoint
   - _get_endpoint_quality_score
   - _calculate_concordance_multiplier
   - _score_response_rate_fallback
   - _aggregate_disease_evidence
   - _generate_analysis_summary_sheet

3. ADD these standalone helper functions (or convert to methods):
   - _response_pct_to_score
   - _percent_change_to_score
   - _is_decrease_good
   - _calculate_evidence_confidence_case_series

4. MODIFY export_to_excel:
   - Add call to _generate_analysis_summary_sheet as FIRST sheet
   - Keep all other sheets as-is

   Example:
   ```python
   def export_to_excel(self, result, filename=None):
       # ... setup code ...
       
       with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
           # NEW: Analysis Summary as first sheet
           self._generate_analysis_summary_sheet(result, writer)
           
           # Existing sheets follow...
           # Summary sheet
           # Opportunities sheet
           # Market Intelligence sheet
           # etc.
   ```

5. OPTIONAL: Update LLM extraction prompt to infer endpoint category
   
   Add to your extraction prompt something like:
   
   ```
   For each efficacy endpoint, classify as:
   - "primary": Main outcome discussed prominently in abstract/conclusions
   - "secondary": Additional outcomes measured and reported
   - "exploratory": Supplementary findings mentioned briefly
   
   If you cannot determine the category, leave endpoint_category blank.
   ```

6. UPDATE OpportunityScores usage:
   - endpoint_quality_score is now None (quality baked into efficacy)
   - clinical_breakdown has new keys for efficacy details:
     - efficacy_endpoint_count
     - efficacy_concordance

7. SAMPLE SIZE THRESHOLDS (for reference):
   N >= 20: 10 (large for case series)
   N >= 15: 9
   N >= 10: 8
   N >= 5:  6
   N >= 3:  4
   N >= 2:  2
   N = 1:   1

8. EVIDENCE CONFIDENCE THRESHOLDS (for reference):
   - Moderate: 3+ studies, 20+ patients, consistent, 2+ full text
   - Low-Moderate: 3+ studies, 20+ patients, consistent
   - Low: 2+ studies, 10+ patients
   - Very Low: Everything else

9. FLAGS (shown in Analysis Summary):
   - ⚠️ Very small N (<5)
   - ⚠️ Small N (<10)
   - Single study
   - High heterogeneity
   - Abstract-only
"""


# =============================================================================
# SECTION 7: QUICK REFERENCE - SCORING SUMMARY
# =============================================================================

"""
SCORING QUICK REFERENCE
=======================

EFFICACY SCORE (per endpoint, 1-10)
-----------------------------------
Response %:  >=90%→10, >=80%→9, >=70%→8, >=60%→7, >=50%→6, >=40%→5, >=30%→4, >=20%→3, >=10%→2, <10%→1
% Change:    >=60%→10, >=50%→9, >=40%→8, >=30%→7, >=20%→6, >=10%→5, >=0%→4, >=-10%→3, <-10%→2
Significance only: 6.0
Direction only: 6.5 (improved) or 3.5 (worsened)
Unknown: 5.0

CATEGORY WEIGHTS
----------------
Primary: 1.0
Secondary: 0.6
Exploratory: 0.3
Unknown: 0.6 (defaults to secondary)

QUALITY WEIGHTS
---------------
Gold standard (ACR50, DAS28, etc.): quality_score 10 → weight 1.0
Good validated: quality_score 8 → weight 0.88
Generic validated: quality_score 7 → weight 0.82
Ad-hoc: quality_score 4 → weight 0.64

Formula: quality_weight = 0.4 + (quality_score / 10) * 0.6

CONCORDANCE MULTIPLIER
----------------------
>=90% agreement: 1.15
>=75% agreement: 1.10
>=60% agreement: 1.00
>=40% agreement: 0.90
<40% agreement: 0.85

FINAL EFFICACY SCORE
--------------------
final = (weighted_avg * concordance * 0.70) + (best_endpoint * 0.30)

SAMPLE SIZE (case series calibrated)
------------------------------------
N >= 20: 10
N >= 15: 9
N >= 10: 8
N >= 5:  6
N >= 3:  4
N >= 2:  2
N = 1:   1

CLINICAL SIGNAL (50% of overall)
--------------------------------
Response rate (quality-weighted): 40%
Safety profile: 40%
Organ domain breadth: 20%

EVIDENCE QUALITY (25% of overall)
---------------------------------
Sample size: 35%
Publication venue: 25%
Response durability: 25%
Extraction completeness: 15%

MARKET OPPORTUNITY (25% of overall)
-----------------------------------
Competitors: 33%
Market size: 33%
Unmet need: 33%
"""
