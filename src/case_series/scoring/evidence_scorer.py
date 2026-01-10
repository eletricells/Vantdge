"""
Evidence Quality Scorer

Scores the quality of clinical evidence from case series extractions.
Handles:
- Sample size scoring
- Publication venue scoring
- Follow-up duration/durability scoring
- Extraction completeness scoring
"""

import re
from typing import Optional

from src.case_series.models import CaseSeriesExtraction


class EvidenceScorer:
    """
    Scores evidence quality from case series extractions.

    Provides scoring for:
    - Sample size (calibrated for case series literature)
    - Publication venue (peer-reviewed vs preprint vs conference)
    - Follow-up duration (longer = more durable evidence)
    - Extraction completeness (data quality)
    """

    def __init__(self):
        """Initialize the evidence scorer."""
        pass

    def score_sample_size(self, extraction: CaseSeriesExtraction) -> float:
        """
        Score sample size calibrated for case series literature.

        For case series, 20+ patients is considered substantial.
        100-patient case series are rare, so thresholds are adjusted.
        Single case reports get minimal weight.

        Scoring:
        - N >= 20: 10 (large case series)
        - N >= 15: 9  (substantial case series)
        - N >= 10: 8  (solid case series)
        - N >= 5:  6  (small but acceptable)
        - N >= 3:  4  (minimal case series)
        - N >= 2:  2  (two-patient report)
        - N = 1:   1  (single case report)

        Returns:
            Score from 1-10
        """
        n = 0
        if extraction.patient_population and extraction.patient_population.n_patients is not None:
            n = extraction.patient_population.n_patients

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
            return 1.0

    def score_publication_venue(self, extraction: CaseSeriesExtraction) -> float:
        """
        Score publication venue quality.

        - Peer-reviewed journal: 10
        - Preprint: 6
        - Conference abstract: 4
        - Unknown with journal: 8
        - Unknown: 5

        Returns:
            Score from 1-10
        """
        venue = (extraction.source.publication_venue or "").lower()

        if 'peer-reviewed' in venue or 'journal' in venue:
            return 10.0
        elif 'preprint' in venue:
            return 6.0
        elif 'conference' in venue or 'abstract' in venue:
            return 4.0
        elif venue and venue != 'unknown':
            return 2.0

        # Try to infer from journal name
        if extraction.source.journal:
            return 8.0

        return 5.0

    def score_followup_duration(self, extraction: CaseSeriesExtraction) -> float:
        """
        Score follow-up duration.

        Longer follow-up = more durable evidence.

        Scoring:
        - > 1 year: 10
        - 6-12 months: 7
        - 3-6 months: 5
        - 1-3 months: 3
        - < 1 month: 1
        - Unknown: 5

        Returns:
            Score from 1-10
        """
        follow_up = (extraction.follow_up_duration or "").lower()

        # Check for years
        if 'year' in follow_up:
            match = re.search(r'(\d+)\s*year', follow_up)
            if match and int(match.group(1)) >= 1:
                return 10.0
            return 10.0

        # Check for months
        if 'month' in follow_up:
            match = re.search(r'(\d+)\s*month', follow_up)
            if match:
                months = int(match.group(1))
                if months >= 12:
                    return 10.0
                elif months >= 6:
                    return 7.0
                elif months >= 3:
                    return 5.0
                elif months >= 1:
                    return 3.0
            return 5.0

        # Check for weeks
        if 'week' in follow_up:
            match = re.search(r'(\d+)\s*week', follow_up)
            if match:
                weeks = int(match.group(1))
                if weeks >= 4:
                    return 3.0
                else:
                    return 1.0
            return 2.0

        return 5.0

    def score_response_durability(self, extraction: CaseSeriesExtraction) -> float:
        """
        Score response durability based on follow-up and sustained response mentions.

        Similar to followup_duration but also checks for durability keywords.

        Returns:
            Score from 1-10
        """
        follow_up = (extraction.follow_up_duration or "").lower()

        # Parse follow-up duration
        months = 0

        year_match = re.search(r'(\d+(?:\.\d+)?)\s*year', follow_up)
        if year_match:
            months = float(year_match.group(1)) * 12

        month_match = re.search(r'(\d+(?:\.\d+)?)\s*month', follow_up)
        if month_match:
            months = max(months, float(month_match.group(1)))

        week_match = re.search(r'(\d+(?:\.\d+)?)\s*week', follow_up)
        if week_match:
            months = max(months, float(week_match.group(1)) / 4.33)

        # Score based on duration
        if months >= 24:
            duration_score = 10.0
        elif months >= 12:
            duration_score = 9.0
        elif months >= 6:
            duration_score = 7.0
        elif months >= 3:
            duration_score = 5.0
        elif months >= 1:
            duration_score = 3.0
        elif months > 0:
            duration_score = 2.0
        else:
            duration_score = 4.0

        # Bonus for sustained response mentioned
        if extraction.detailed_efficacy_endpoints:
            for ep in extraction.detailed_efficacy_endpoints:
                ep_name = (getattr(ep, 'endpoint_name', '') or '').lower()
                if any(term in ep_name for term in ['sustained', 'durable', 'maintained', 'long-term']):
                    duration_score = min(10.0, duration_score + 1.0)
                    break

        return duration_score

    def score_extraction_completeness(self, extraction: CaseSeriesExtraction) -> float:
        """
        Score data extraction completeness.

        Checks for presence of key data fields.

        Returns:
            Score from 1-10
        """
        completeness_checks = [
            # Source information
            extraction.source.pmid is not None,
            extraction.source.title is not None and len(extraction.source.title) > 10,
            extraction.source.journal is not None,
            extraction.source.year is not None,

            # Patient population
            extraction.patient_population.n_patients is not None and extraction.patient_population.n_patients > 0,
            extraction.disease is not None,
            extraction.patient_population.age_description is not None,

            # Treatment details
            extraction.treatment.drug_name is not None,
            extraction.treatment.dose is not None,
            extraction.treatment.duration is not None,

            # Efficacy data
            extraction.efficacy.primary_endpoint is not None,
            extraction.efficacy.responders_pct is not None or extraction.efficacy.responders_n is not None,
            len(extraction.detailed_efficacy_endpoints or []) > 0,

            # Safety data
            len(extraction.safety.adverse_events or []) > 0,
            extraction.safety.sae_count is not None or extraction.safety.sae_percentage is not None,

            # Follow-up
            extraction.follow_up_duration is not None,
        ]

        completeness_pct = sum(completeness_checks) / len(completeness_checks)

        # Convert to 1-10 scale
        score = 1.0 + (completeness_pct * 9.0)
        return round(score, 1)

    def calculate_evidence_confidence(
        self,
        n_studies: int,
        total_patients: int,
        consistency: str,
        high_quality_count: int,
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

        Returns:
            Confidence level string
        """
        if n_studies >= 3 and total_patients >= 20 and consistency in ['High', 'Moderate']:
            if high_quality_count >= 2:
                return 'Moderate'
            return 'Low-Moderate'
        elif n_studies >= 2 and total_patients >= 10:
            return 'Low'
        elif n_studies >= 1 and total_patients >= 3:
            return 'Very Low'
        else:
            return 'Very Low'
