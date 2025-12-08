"""
Tests for the v2 scoring improvements in the case series agent.

Tests:
- _response_pct_to_score() helper function
- _percent_change_to_score() helper function
- _is_decrease_good() helper function
- _calculate_evidence_confidence_case_series() helper function
- _score_sample_size_v2() method
- _aggregate_disease_evidence() method
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from agents.drug_repurposing_case_series_agent import (
    _response_pct_to_score,
    _percent_change_to_score,
    _is_decrease_good,
    _calculate_evidence_confidence_case_series,
    DrugRepurposingCaseSeriesAgent
)


class TestResponsePctToScore:
    """Tests for _response_pct_to_score helper function."""

    def test_excellent_response(self):
        """≥90% response should score 10."""
        assert _response_pct_to_score(95.0) == 10.0
        assert _response_pct_to_score(90.0) == 10.0
        assert _response_pct_to_score(100.0) == 10.0

    def test_very_good_response(self):
        """≥80% response should score 9."""
        assert _response_pct_to_score(85.0) == 9.0
        assert _response_pct_to_score(80.0) == 9.0

    def test_good_response(self):
        """≥70% response should score 8."""
        assert _response_pct_to_score(75.0) == 8.0
        assert _response_pct_to_score(70.0) == 8.0

    def test_moderate_response(self):
        """≥60% response should score 7, ≥50% should score 6."""
        assert _response_pct_to_score(60.0) == 7.0
        assert _response_pct_to_score(50.0) == 6.0
        assert _response_pct_to_score(59.0) == 6.0

    def test_fair_response(self):
        """10-19% response should score 2."""
        assert _response_pct_to_score(15.0) == 2.0
        assert _response_pct_to_score(10.0) == 2.0

    def test_minimal_response(self):
        """<10% response should score 1."""
        assert _response_pct_to_score(5.0) == 1.0
        assert _response_pct_to_score(0.0) == 1.0


class TestPercentChangeToScore:
    """Tests for _percent_change_to_score helper function.

    Actual implementation thresholds:
    >=60%: 10, >=50%: 9, >=40%: 8, >=30%: 7, >=20%: 6, >=10%: 5, >=0%: 4, >=-10%: 3, <-10%: 2
    """

    def test_excellent_improvement(self):
        """≥60% improvement should score 10."""
        assert _percent_change_to_score(60.0) == 10.0
        assert _percent_change_to_score(80.0) == 10.0
        assert _percent_change_to_score(100.0) == 10.0

    def test_very_good_improvement(self):
        """≥50% improvement should score 9."""
        assert _percent_change_to_score(50.0) == 9.0
        assert _percent_change_to_score(55.0) == 9.0

    def test_good_improvement(self):
        """≥40% improvement should score 8."""
        assert _percent_change_to_score(40.0) == 8.0
        assert _percent_change_to_score(45.0) == 8.0

    def test_moderate_improvement(self):
        """≥30% improvement should score 7."""
        assert _percent_change_to_score(30.0) == 7.0
        assert _percent_change_to_score(35.0) == 7.0

    def test_mild_improvement(self):
        """≥20% improvement should score 6."""
        assert _percent_change_to_score(20.0) == 6.0
        assert _percent_change_to_score(25.0) == 6.0

    def test_minimal_improvement(self):
        """≥10% improvement should score 5."""
        assert _percent_change_to_score(10.0) == 5.0
        assert _percent_change_to_score(15.0) == 5.0

    def test_no_improvement(self):
        """0-10% improvement should score 4."""
        assert _percent_change_to_score(0.0) == 4.0
        assert _percent_change_to_score(5.0) == 4.0

    def test_mild_worsening(self):
        """0 to -10% change should score 3."""
        assert _percent_change_to_score(-5.0) == 3.0
        assert _percent_change_to_score(-10.0) == 3.0

    def test_significant_worsening(self):
        """<-10% change should score 2."""
        assert _percent_change_to_score(-15.0) == 2.0
        assert _percent_change_to_score(-50.0) == 2.0


class TestIsDecreaseGood:
    """Tests for _is_decrease_good helper function."""

    def test_disease_activity_scores(self):
        """Disease activity scores (DAS28, CDAI, etc.) - decrease is good."""
        assert _is_decrease_good("DAS28") == True
        assert _is_decrease_good("DAS28-CRP") == True
        assert _is_decrease_good("CDAI") == True
        assert _is_decrease_good("SLEDAI") == True

    def test_pain_scores(self):
        """Pain scores (VAS, NRS) - decrease is good."""
        assert _is_decrease_good("VAS Pain") == True
        assert _is_decrease_good("Pain VAS") == True
        assert _is_decrease_good("NRS") == True

    def test_inflammatory_markers(self):
        """Inflammatory markers (CRP, ESR) - decrease is good."""
        assert _is_decrease_good("CRP levels") == True
        assert _is_decrease_good("ESR") == True

    def test_response_rates(self):
        """Response rates (ACR50, PASI75) - decrease is NOT good."""
        assert _is_decrease_good("ACR50") == False
        assert _is_decrease_good("PASI75 response") == False
        assert _is_decrease_good("ACR20 responders") == False

    def test_quality_of_life(self):
        """Quality of life improvements - decrease is NOT good."""
        assert _is_decrease_good("Quality of Life Score") == False


class TestEvidenceConfidenceCaseSeries:
    """Tests for _calculate_evidence_confidence_case_series helper function.

    Function signature: (n_studies, total_patients, consistency, extractions) -> str

    Levels:
    - Moderate: 3+ studies, 20+ patients, consistent, 2+ high-quality extractions
    - Low-Moderate: 3+ studies, 20+ patients, consistent (less high-quality)
    - Low: 2+ studies, 10+ patients
    - Very Low: Everything else
    """

    def _make_mock_extraction(self, method='multi_stage'):
        """Create mock extraction with specified method."""
        mock = MagicMock()
        mock.extraction_method = method
        return mock

    def test_moderate_confidence_with_high_quality(self):
        """3+ studies, 20+ patients, consistent, 2+ multi-stage should be Moderate."""
        extractions = [self._make_mock_extraction('multi_stage') for _ in range(3)]
        result = _calculate_evidence_confidence_case_series(
            n_studies=3, total_patients=25, consistency="High", extractions=extractions
        )
        assert result == "Moderate"

    def test_low_moderate_confidence(self):
        """3+ studies, 20+ patients, consistent, but no high-quality extractions."""
        extractions = [self._make_mock_extraction('abstract_only') for _ in range(3)]
        result = _calculate_evidence_confidence_case_series(
            n_studies=3, total_patients=25, consistency="High", extractions=extractions
        )
        assert result == "Low-Moderate"

    def test_low_confidence(self):
        """2+ studies, 10+ patients should be Low."""
        extractions = [self._make_mock_extraction('abstract_only') for _ in range(2)]
        result = _calculate_evidence_confidence_case_series(
            n_studies=2, total_patients=12, consistency="Low", extractions=extractions
        )
        assert result == "Low"

    def test_very_low_confidence_single_study(self):
        """Single study should be Very Low."""
        extractions = [self._make_mock_extraction('multi_stage')]
        result = _calculate_evidence_confidence_case_series(
            n_studies=1, total_patients=10, consistency="High", extractions=extractions
        )
        assert result == "Very Low"

    def test_very_low_small_sample(self):
        """Small sample (<10 patients, single study) should be Very Low."""
        extractions = [self._make_mock_extraction('abstract_only') for _ in range(2)]
        result = _calculate_evidence_confidence_case_series(
            n_studies=2, total_patients=5, consistency="High", extractions=extractions
        )
        assert result == "Very Low"


class TestSampleSizeV2:
    """Tests for _score_sample_size_v2 method.

    The method expects a CaseSeriesExtraction object with patient_population.
    We use mock objects to test the scoring logic.
    """

    @pytest.fixture
    def agent(self):
        """Create agent instance for testing (mock API key)."""
        return DrugRepurposingCaseSeriesAgent(
            anthropic_api_key="test-key"
        )

    def _make_mock_extraction(self, n_patients):
        """Create a mock extraction with specified patient count."""
        mock = MagicMock()
        mock.patient_population.n_patients = n_patients
        return mock

    def _make_mock_extraction_no_population(self):
        """Create a mock extraction with no patient_population."""
        mock = MagicMock()
        mock.patient_population = None
        return mock

    def test_large_case_series(self, agent):
        """N≥20 should score 10."""
        assert agent._score_sample_size_v2(self._make_mock_extraction(20)) == 10.0
        assert agent._score_sample_size_v2(self._make_mock_extraction(50)) == 10.0
        assert agent._score_sample_size_v2(self._make_mock_extraction(100)) == 10.0

    def test_substantial_case_series(self, agent):
        """N≥15 should score 9."""
        assert agent._score_sample_size_v2(self._make_mock_extraction(15)) == 9.0
        assert agent._score_sample_size_v2(self._make_mock_extraction(19)) == 9.0

    def test_solid_case_series(self, agent):
        """N≥10 should score 8."""
        assert agent._score_sample_size_v2(self._make_mock_extraction(10)) == 8.0
        assert agent._score_sample_size_v2(self._make_mock_extraction(14)) == 8.0

    def test_small_case_series(self, agent):
        """N≥5 should score 6."""
        assert agent._score_sample_size_v2(self._make_mock_extraction(5)) == 6.0
        assert agent._score_sample_size_v2(self._make_mock_extraction(9)) == 6.0

    def test_minimal_case_series(self, agent):
        """N≥3 should score 4."""
        assert agent._score_sample_size_v2(self._make_mock_extraction(3)) == 4.0
        assert agent._score_sample_size_v2(self._make_mock_extraction(4)) == 4.0

    def test_two_patient_report(self, agent):
        """N=2 should score 2."""
        assert agent._score_sample_size_v2(self._make_mock_extraction(2)) == 2.0

    def test_single_case_report(self, agent):
        """N=1 should score 1."""
        assert agent._score_sample_size_v2(self._make_mock_extraction(1)) == 1.0

    def test_no_patients(self, agent):
        """N=0 or no patient_population should score 1."""
        assert agent._score_sample_size_v2(self._make_mock_extraction(0)) == 1.0
        assert agent._score_sample_size_v2(self._make_mock_extraction_no_population()) == 1.0


class TestAggregateEvidence:
    """Tests for _aggregate_disease_evidence method.

    Note: The method doesn't include 'disease' key in returned dict.
    The actual returned keys are: n_studies, total_patients, total_responders,
    pooled_response_pct, response_range, heterogeneity_cv, consistency, evidence_confidence
    """

    @pytest.fixture
    def agent(self):
        """Create agent instance for testing (mock API key)."""
        return DrugRepurposingCaseSeriesAgent(
            anthropic_api_key="test-key"
        )

    def test_empty_extractions(self, agent):
        """Empty list should return zeros."""
        result = agent._aggregate_disease_evidence("Test Disease", [])
        assert result['n_studies'] == 0
        assert result['total_patients'] == 0
        assert result['pooled_response_pct'] is None

    def test_aggregation_returns_dict_keys(self, agent):
        """Result should have all expected keys."""
        result = agent._aggregate_disease_evidence("Test Disease", [])
        expected_keys = [
            'n_studies', 'total_patients', 'total_responders', 'pooled_response_pct',
            'response_range', 'heterogeneity_cv', 'consistency', 'evidence_confidence'
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"
