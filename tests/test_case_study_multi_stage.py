"""
Test multi-stage extraction for Off-Label Case Study Agent.

Tests:
1. CaseStudyDataExtractor class methods
2. Integration with extract_case_study_data
3. Export to Excel functionality
4. Schema validation
"""
import os
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.models.off_label_schemas import (
    OffLabelCaseStudy,
    OffLabelOutcome,
    StudyClassification
)
from src.models.clinical_extraction_schemas import (
    EfficacyEndpoint,
    SafetyEndpoint,
    DataSectionIdentification
)

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =====================================================
# TEST 1: Schema Validation
# =====================================================

def test_schema_new_fields():
    """Test that new fields are properly added to OffLabelCaseStudy."""
    logger.info("Test 1: Schema new fields validation")
    
    # Create case study with new fields
    cs = OffLabelCaseStudy(
        pmid="12345678",
        title="Test Case Study",
        drug_name="Tofacitinib",
        study_type="Case Series",
        relevance_score=0.95,
        indication_treated="Dermatomyositis",
        extraction_method="multi_stage",
        extraction_stages_completed=["section_id", "efficacy", "safety"],
        detailed_efficacy_endpoints=[
            EfficacyEndpoint(
                endpoint_name="Complete Response",
                timepoint="Week 12",
                responders_n=8,
                n_evaluated=10,
                responders_pct=80.0,
                is_standard_endpoint=True
            )
        ],
        detailed_safety_endpoints=[
            SafetyEndpoint(
                event_category="TEAE",
                event_name="Nasopharyngitis",
                n_events=3,
                incidence_pct=30.0
            )
        ],
        standard_endpoints_matched=["Complete Response", "Partial Response"]
    )
    
    # Verify fields
    assert cs.extraction_method == "multi_stage"
    assert len(cs.extraction_stages_completed) == 3
    assert len(cs.detailed_efficacy_endpoints) == 1
    assert len(cs.detailed_safety_endpoints) == 1
    assert len(cs.standard_endpoints_matched) == 2
    assert cs.detailed_efficacy_endpoints[0].endpoint_name == "Complete Response"
    assert cs.detailed_efficacy_endpoints[0].responders_pct == 80.0
    
    logger.info("✅ Schema validation passed")
    return True


def test_schema_backward_compatibility():
    """Test that existing fields still work (backward compatibility)."""
    logger.info("Test 2: Schema backward compatibility")
    
    # Create with only required fields (old style)
    cs = OffLabelCaseStudy(
        pmid="12345678",
        title="Test Case Study",
        drug_name="Tofacitinib",
        study_type="Case Report",
        relevance_score=0.9,
        indication_treated="Vitiligo",
        # Old-style outcome
        outcomes=[
            OffLabelOutcome(
                outcome_name="Repigmentation",
                outcome_category="Primary",
                responders_n=1,
                responders_pct=100.0
            )
        ]
    )
    
    # New fields should have defaults
    assert cs.extraction_method == "single_pass"
    assert cs.extraction_stages_completed == []
    assert cs.detailed_efficacy_endpoints == []
    assert cs.detailed_safety_endpoints == []
    assert cs.standard_endpoints_matched == []
    
    # Old fields should work
    assert len(cs.outcomes) == 1
    assert cs.outcomes[0].outcome_name == "Repigmentation"
    
    logger.info("✅ Backward compatibility passed")
    return True


# =====================================================
# TEST 2: CaseStudyDataExtractor Class
# =====================================================

def test_extractor_initialization():
    """Test CaseStudyDataExtractor initialization."""
    logger.info("Test 3: CaseStudyDataExtractor initialization")
    
    from src.agents.off_label_case_study_agent import CaseStudyDataExtractor
    
    # Mock Anthropic client
    mock_client = Mock()
    
    extractor = CaseStudyDataExtractor(
        client=mock_client,
        model="claude-sonnet-4-20250514",
        max_tokens=16000,
        database_url=None
    )
    
    assert extractor.client == mock_client
    assert extractor.model == "claude-sonnet-4-20250514"
    assert extractor.max_tokens == 16000
    assert extractor._clinical_db is None
    
    logger.info("✅ Extractor initialization passed")
    return True


def test_extractor_json_parsing():
    """Test JSON extraction from text."""
    logger.info("Test 4: JSON extraction from text")

    from src.agents.off_label_case_study_agent import CaseStudyDataExtractor

    mock_client = Mock()
    extractor = CaseStudyDataExtractor(client=mock_client)

    # Test with markdown code block
    text1 = """Here's the JSON:
```json
[{"endpoint_name": "Response Rate", "responders_pct": 75.0}]
```
"""
    result1 = extractor._extract_json_from_text(text1)
    assert '"endpoint_name"' in result1

    # Test with plain JSON
    text2 = '[{"event_name": "Headache", "incidence_pct": 10.0}]'
    result2 = extractor._extract_json_from_text(text2)
    assert '"event_name"' in result2

    logger.info("✅ JSON parsing passed")
    return True


# =====================================================
# TEST 3: Export to Excel
# =====================================================

def test_export_to_excel():
    """Test export_to_excel method."""
    logger.info("Test 5: Export to Excel")

    try:
        import pandas as pd
    except ImportError:
        logger.warning("pandas not installed, skipping Excel test")
        return True

    from src.agents.off_label_case_study_agent import OffLabelCaseStudyAgent

    # Create mock agent
    with patch.object(OffLabelCaseStudyAgent, '__init__', lambda x, *args, **kwargs: None):
        agent = OffLabelCaseStudyAgent.__new__(OffLabelCaseStudyAgent)

    # Create test case studies
    case_studies = [
        OffLabelCaseStudy(
            pmid="12345678",
            title="Test Study 1",
            drug_name="Tofacitinib",
            study_type="Case Series",
            relevance_score=0.95,
            indication_treated="Dermatomyositis",
            n_patients=10,
            response_rate="80% (8/10)",
            responders_n=8,
            responders_pct=80.0,
            efficacy_signal="Strong",
            extraction_method="multi_stage",
            extraction_stages_completed=["section_id", "efficacy", "safety"],
            detailed_efficacy_endpoints=[
                EfficacyEndpoint(
                    endpoint_name="Complete Response",
                    timepoint="Week 12",
                    responders_n=8,
                    n_evaluated=10,
                    responders_pct=80.0,
                    is_standard_endpoint=True
                ),
                EfficacyEndpoint(
                    endpoint_name="Partial Response",
                    timepoint="Week 12",
                    responders_n=2,
                    n_evaluated=10,
                    responders_pct=20.0,
                    is_standard_endpoint=True
                )
            ],
            detailed_safety_endpoints=[
                SafetyEndpoint(
                    event_category="TEAE",
                    event_name="Nasopharyngitis",
                    n_events=3,
                    incidence_pct=30.0
                )
            ],
            standard_endpoints_matched=["Complete Response", "Partial Response"]
        ),
        OffLabelCaseStudy(
            pmid="87654321",
            title="Test Study 2",
            drug_name="Tofacitinib",
            study_type="Case Report",
            relevance_score=0.85,
            indication_treated="Vitiligo",
            n_patients=1,
            response_rate="Complete repigmentation",
            extraction_method="single_pass"
        )
    ]

    # Test export
    output_path = "data/exports/test_export.xlsx"
    Path("data/exports").mkdir(parents=True, exist_ok=True)

    result_path = agent.export_to_excel(case_studies, "Tofacitinib", output_path)

    # Verify file was created
    assert Path(result_path).exists(), f"Excel file not created at {result_path}"

    # Read and verify sheets
    xl = pd.ExcelFile(result_path)
    sheets = xl.sheet_names

    assert "Summary" in sheets, "Missing Summary sheet"
    assert "Case Studies" in sheets, "Missing Case Studies sheet"
    assert "Efficacy Endpoints" in sheets, "Missing Efficacy Endpoints sheet"
    assert "Safety Endpoints" in sheets, "Missing Safety Endpoints sheet"

    # Verify Summary data
    summary_df = pd.read_excel(result_path, sheet_name="Summary")
    assert summary_df["Total Case Studies"].iloc[0] == 2
    assert summary_df["Multi-Stage Extractions"].iloc[0] == 1
    assert summary_df["Single-Pass Extractions"].iloc[0] == 1

    # Verify Efficacy data
    efficacy_df = pd.read_excel(result_path, sheet_name="Efficacy Endpoints")
    assert len(efficacy_df) == 2, f"Expected 2 efficacy endpoints, got {len(efficacy_df)}"

    # Close the Excel file explicitly
    xl.close()

    # Clean up (with retry for Windows file locking)
    import time
    for _ in range(3):
        try:
            Path(result_path).unlink()
            break
        except PermissionError:
            time.sleep(0.5)

    logger.info("✅ Export to Excel passed")
    return True


# =====================================================
# TEST 4: Integration Test (with mocked API)
# =====================================================

def test_multi_stage_extraction_flow():
    """Test the multi-stage extraction flow with mocked API responses."""
    logger.info("Test 6: Multi-stage extraction flow")

    from src.agents.off_label_case_study_agent import CaseStudyDataExtractor

    # Create mock Anthropic client with realistic responses
    mock_client = Mock()

    # Mock response for section identification
    mock_section_response = Mock()
    mock_section_response.content = [Mock(text='''
{
    "efficacy_tables": ["Table 1", "Table 2"],
    "safety_tables": ["Table 3"],
    "efficacy_sections": ["Results"],
    "safety_sections": ["Safety"],
    "confidence": 0.85,
    "notes": "Tables clearly labeled"
}
''')]

    # Mock response for efficacy extraction
    mock_efficacy_response = Mock()
    mock_efficacy_response.content = [Mock(text='''
[
    {
        "endpoint_name": "Complete Response",
        "endpoint_category": "Primary",
        "timepoint": "Week 12",
        "timepoint_weeks": 12,
        "responders_n": 8,
        "n_evaluated": 10,
        "responders_pct": 80.0,
        "is_standard_endpoint": true,
        "source_table": "Table 1"
    }
]
''')]

    # Mock response for safety extraction
    mock_safety_response = Mock()
    mock_safety_response.content = [Mock(text='''
[
    {
        "event_category": "TEAE",
        "event_name": "Nasopharyngitis",
        "n_events": 3,
        "n_patients": 2,
        "incidence_pct": 20.0,
        "source_table": "Table 3"
    }
]
''')]

    # Configure mock to return different responses
    mock_client.messages.create.side_effect = [
        mock_section_response,
        mock_efficacy_response,
        mock_safety_response
    ]

    extractor = CaseStudyDataExtractor(
        client=mock_client,
        model="claude-sonnet-4-20250514"
    )

    # Test paper data
    paper = {
        'content': 'A' * 5000,  # Long enough for multi-stage
        'tables': [
            {'label': 'Table 1', 'content': 'Efficacy data...'},
            {'label': 'Table 3', 'content': 'Safety data...'}
        ],
        'pmid': '12345678',
        'title': 'Test Study'
    }

    # Run extraction
    result = extractor.extract_multi_stage(
        paper=paper,
        drug_name="Tofacitinib",
        indication="Dermatomyositis",
        n_patients=10
    )

    # Verify results
    assert result['extraction_method'] == 'multi_stage'
    assert 'section_id' in result['stages_completed']
    assert 'efficacy' in result['stages_completed']
    assert 'safety' in result['stages_completed']
    assert len(result['efficacy_endpoints']) == 1
    assert len(result['safety_endpoints']) == 1
    assert result['efficacy_endpoints'][0].endpoint_name == "Complete Response"
    assert result['efficacy_endpoints'][0].responders_pct == 80.0
    assert result['safety_endpoints'][0].event_name == "Nasopharyngitis"

    logger.info("✅ Multi-stage extraction flow passed")
    return True


# =====================================================
# MAIN
# =====================================================

def main():
    """Run all tests."""
    logger.info("=" * 80)
    logger.info("MULTI-STAGE EXTRACTION TESTS")
    logger.info("=" * 80)

    results = []

    # Run tests
    results.append(("Schema new fields", test_schema_new_fields()))
    results.append(("Schema backward compatibility", test_schema_backward_compatibility()))
    results.append(("Extractor initialization", test_extractor_initialization()))
    results.append(("JSON parsing", test_extractor_json_parsing()))
    results.append(("Export to Excel", test_export_to_excel()))
    results.append(("Multi-stage extraction flow", test_multi_stage_extraction_flow()))

    # Summary
    logger.info("=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for test_name, passed_test in results:
        status = "✅ PASSED" if passed_test else "❌ FAILED"
        logger.info(f"{status}: {test_name}")

    logger.info(f"\nTotal: {passed}/{total} tests passed")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

