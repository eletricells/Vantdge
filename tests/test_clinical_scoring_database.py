"""
Tests for clinical scoring database methods.

Tests the database queries for organ domains, validated instruments,
and safety categories used in the case series scoring system.
"""

import os
import pytest
from dotenv import load_dotenv

from src.tools.case_series_database import CaseSeriesDatabase


# Load environment variables
load_dotenv()


@pytest.fixture
def db():
    """Create database connection for tests."""
    database_url = os.getenv("DRUG_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("No database URL configured")
    
    db = CaseSeriesDatabase(database_url)
    if not db.is_available:
        pytest.skip("Database not available")
    
    return db


class TestOrganDomains:
    """Tests for organ domain queries."""

    def test_get_organ_domains_returns_data(self, db):
        """Test that organ domains are returned from database."""
        domains = db.get_organ_domains()
        
        assert domains, "Should return organ domains"
        assert len(domains) == 11, f"Expected 11 domains, got {len(domains)}"
    
    def test_organ_domains_have_keywords(self, db):
        """Test that each domain has keywords."""
        domains = db.get_organ_domains()
        
        for domain_name, keywords in domains.items():
            assert keywords, f"Domain '{domain_name}' should have keywords"
            assert len(keywords) > 5, f"Domain '{domain_name}' should have >5 keywords"
    
    def test_expected_domains_present(self, db):
        """Test that expected domains are present."""
        domains = db.get_organ_domains()
        
        expected = ['musculoskeletal', 'mucocutaneous', 'renal', 'neurological',
                    'hematological', 'cardiopulmonary', 'immunological', 'systemic',
                    'gastrointestinal', 'ocular', 'constitutional']
        
        for domain in expected:
            assert domain in domains, f"Missing expected domain: {domain}"


class TestValidatedInstruments:
    """Tests for validated instruments queries."""

    def test_get_all_instruments(self, db):
        """Test that all instruments can be retrieved."""
        instruments = db.get_validated_instruments()
        
        assert instruments, "Should return instruments"
        assert len(instruments) >= 15, f"Expected >=15 diseases, got {len(instruments)}"
    
    def test_get_instruments_by_disease(self, db):
        """Test filtering instruments by disease."""
        instruments = db.get_validated_instruments("rheumatoid_arthritis")
        
        assert instruments, "Should return RA instruments"
        assert 'rheumatoid_arthritis' in instruments
        
        ra_instruments = instruments['rheumatoid_arthritis']
        assert 'ACR20' in ra_instruments, "RA should have ACR20"
        assert 'DAS28-CRP' in ra_instruments, "RA should have DAS28-CRP"
    
    def test_find_instruments_for_disease_exact(self, db):
        """Test finding instruments with exact disease match."""
        instruments = db.find_instruments_for_disease("rheumatoid_arthritis")
        
        assert instruments, "Should find RA instruments"
        assert 'ACR20' in instruments
        assert instruments['ACR20'] == 10, "ACR20 should have quality score 10"
    
    def test_find_instruments_for_disease_fuzzy(self, db):
        """Test finding instruments with fuzzy disease match."""
        # Test with natural language disease name
        instruments = db.find_instruments_for_disease("psoriatic arthritis")
        
        assert instruments, "Should find PsA instruments"
        assert 'MDA' in instruments or 'PASI' in instruments
    
    def test_find_instruments_for_unknown_disease(self, db):
        """Test that unknown diseases return empty dict."""
        instruments = db.find_instruments_for_disease("made_up_disease_xyz")
        
        assert instruments == {}, "Unknown disease should return empty dict"


class TestSafetyCategories:
    """Tests for safety category queries."""

    def test_get_safety_categories(self, db):
        """Test that safety categories are returned."""
        categories = db.get_safety_categories()
        
        assert categories, "Should return safety categories"
        assert len(categories) == 15, f"Expected 15 categories, got {len(categories)}"
    
    def test_safety_category_structure(self, db):
        """Test that categories have correct structure."""
        categories = db.get_safety_categories()
        
        for cat_name, config in categories.items():
            assert 'keywords' in config, f"'{cat_name}' missing keywords"
            assert 'severity_weight' in config, f"'{cat_name}' missing severity_weight"
            assert 'regulatory_flag' in config, f"'{cat_name}' missing regulatory_flag"
            assert isinstance(config['keywords'], list), f"'{cat_name}' keywords should be list"
    
    def test_high_severity_categories(self, db):
        """Test that high-severity categories exist."""
        categories = db.get_safety_categories()
        
        # Death and malignancy should have severity 10
        assert categories['death']['severity_weight'] == 10
        assert categories['malignancy']['severity_weight'] == 10
        
        # These should be regulatory flags
        assert categories['serious_infection']['regulatory_flag'] is True
        assert categories['cardiovascular']['regulatory_flag'] is True


class TestScoringWeights:
    """Tests for scoring weight queries."""

    def test_get_default_weights(self, db):
        """Test getting default scoring weights."""
        weights = db.get_scoring_weights('default')
        
        assert weights, "Should return weights"
        assert 'response_rate' in weights
        assert 'safety' in weights
        assert 'clinical' in weights
        
        # Check defaults
        assert weights['response_rate'] == 0.30
        assert weights['clinical'] == 0.50
    
    def test_weights_sum_to_one(self, db):
        """Test that dimension weights sum to 1.0."""
        weights = db.get_scoring_weights('default')
        
        dimension_sum = weights['clinical'] + weights['evidence'] + weights['market']
        assert abs(dimension_sum - 1.0) < 0.01, f"Dimension weights should sum to 1.0, got {dimension_sum}"
    
    def test_fallback_for_unknown_area(self, db):
        """Test that unknown therapeutic area returns defaults."""
        weights = db.get_scoring_weights('unknown_area_xyz')
        
        assert weights, "Should return default weights for unknown area"
        assert weights['clinical'] == 0.50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

