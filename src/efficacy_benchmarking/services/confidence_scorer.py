"""
Confidence scoring for extracted efficacy data.

Multi-factor confidence calculation based on:
- Data completeness (required fields present)
- Source reliability (publication > CT.gov > web search)
- Statistical significance (p-value present and significant)
- Data quality indicators
"""

import logging
from typing import List

from ..models import EfficacyDataPoint, DataSource, ReviewStatus

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """
    Calculate and validate confidence scores for efficacy data.
    """

    # Source reliability weights
    SOURCE_WEIGHTS = {
        DataSource.PUBLICATION: 1.0,
        DataSource.OPENFDA: 0.9,
        DataSource.CLINICALTRIALS: 0.75,
        DataSource.WEB_SEARCH: 0.6,
    }

    def __init__(self, confidence_threshold: float = 0.7):
        """
        Initialize the confidence scorer.

        Args:
            confidence_threshold: Minimum confidence for auto-acceptance
        """
        self.confidence_threshold = confidence_threshold

    def calculate_confidence(self, data_point: EfficacyDataPoint) -> float:
        """
        Calculate overall confidence score for a data point.

        Score breakdown:
        - Data completeness: 40%
        - Source reliability: 30%
        - Statistical significance: 20%
        - Data quality indicators: 10%

        Returns:
            Confidence score between 0.0 and 1.0
        """
        scores = []

        # 1. Data completeness (40%)
        completeness_score = self._calculate_completeness(data_point)
        scores.append(completeness_score * 0.4)

        # 2. Source reliability (30%)
        source_score = self.SOURCE_WEIGHTS.get(data_point.source_type, 0.5)
        scores.append(source_score * 0.3)

        # 3. Statistical significance (20%)
        stat_score = self._calculate_statistical_score(data_point)
        scores.append(stat_score * 0.2)

        # 4. Data quality indicators (10%)
        quality_score = self._calculate_quality_score(data_point)
        scores.append(quality_score * 0.1)

        total_score = sum(scores)
        return min(total_score, 1.0)

    def _calculate_completeness(self, dp: EfficacyDataPoint) -> float:
        """
        Score based on required and optional fields present.
        """
        # Required fields (must have for basic validity)
        required_fields = [
            bool(dp.endpoint_name),
            dp.drug_arm_result is not None,
            bool(dp.source_url),
        ]

        # Optional but valuable fields
        optional_fields = [
            dp.comparator_arm_result is not None,
            dp.p_value is not None,
            bool(dp.timepoint),
            bool(dp.trial_name),
            bool(dp.drug_arm_name),
            dp.drug_arm_n is not None,
        ]

        required_score = sum(1 for f in required_fields if f) / len(required_fields) if required_fields else 0
        optional_score = sum(1 for f in optional_fields if f) / len(optional_fields) if optional_fields else 0

        # Weight required fields more heavily
        return required_score * 0.7 + optional_score * 0.3

    def _calculate_statistical_score(self, dp: EfficacyDataPoint) -> float:
        """
        Score based on statistical significance.
        """
        if dp.p_value is None:
            return 0.5  # Unknown significance

        if dp.p_value <= 0.001:
            return 1.0  # Highly significant
        elif dp.p_value <= 0.01:
            return 0.9  # Very significant
        elif dp.p_value <= 0.05:
            return 0.8  # Significant
        elif dp.p_value <= 0.1:
            return 0.6  # Marginally significant
        else:
            return 0.4  # Not significant

    def _calculate_quality_score(self, dp: EfficacyDataPoint) -> float:
        """
        Score based on data quality indicators.
        """
        score = 0.5  # Base score

        # Has sample sizes
        if dp.drug_arm_n and dp.drug_arm_n > 0:
            score += 0.1
            if dp.comparator_arm_n and dp.comparator_arm_n > 0:
                score += 0.1

        # Has confidence interval
        if dp.confidence_interval:
            score += 0.1

        # Has identifiers (PMID or NCT ID)
        if dp.pmid or dp.nct_id:
            score += 0.1

        # Has raw source text (for verification)
        if dp.raw_source_text:
            score += 0.1

        return min(score, 1.0)

    def determine_review_status(self, data_point: EfficacyDataPoint) -> ReviewStatus:
        """
        Determine if data point needs manual review based on confidence score.
        """
        if data_point.confidence_score >= self.confidence_threshold:
            return ReviewStatus.AUTO_ACCEPTED
        return ReviewStatus.PENDING_REVIEW

    def score_and_flag(self, data_points: List[EfficacyDataPoint]) -> List[EfficacyDataPoint]:
        """
        Calculate confidence scores and set review status for all data points.

        Args:
            data_points: List of efficacy data points to score

        Returns:
            Same list with updated confidence_score and review_status
        """
        for dp in data_points:
            dp.confidence_score = self.calculate_confidence(dp)
            dp.review_status = self.determine_review_status(dp)

            if dp.review_status == ReviewStatus.PENDING_REVIEW:
                logger.debug(
                    f"Flagged for review: {dp.endpoint_name} "
                    f"(confidence: {dp.confidence_score:.2f})"
                )

        return data_points

    def get_statistics(self, data_points: List[EfficacyDataPoint]) -> dict:
        """
        Get summary statistics for a list of data points.
        """
        if not data_points:
            return {
                "total": 0,
                "auto_accepted": 0,
                "pending_review": 0,
                "avg_confidence": 0.0,
                "min_confidence": 0.0,
                "max_confidence": 0.0,
            }

        confidences = [dp.confidence_score for dp in data_points]

        return {
            "total": len(data_points),
            "auto_accepted": sum(1 for dp in data_points if dp.review_status == ReviewStatus.AUTO_ACCEPTED),
            "pending_review": sum(1 for dp in data_points if dp.review_status == ReviewStatus.PENDING_REVIEW),
            "avg_confidence": sum(confidences) / len(confidences),
            "min_confidence": min(confidences),
            "max_confidence": max(confidences),
        }
