"""
Test script to verify supplemental run skip logic works correctly.
Tests that non-relevant extractions are saved and appear in skip list.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the database module
from src.tools.case_series_database import CaseSeriesDatabase
from src.models.case_series_schemas import (
    CaseSeriesExtraction,
    CaseSeriesSource,
    PatientPopulation,
    TreatmentDetails,
    EfficacyOutcome,
    SafetyOutcome,
    EvidenceLevel,
)

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set")

# Test data - simulating a non-relevant extraction
TEST_DRUG_NAME = "_TEST_SUPPLEMENTAL_SKIP_"
TEST_PMID = "TEST_12345678"
TEST_DOI_PAPER = "DOI:10.1016/j.jacc.2024.01.012"  # Realistic long DOI (now supported with VARCHAR(100))

def create_test_extraction(is_relevant: bool, pmid: str) -> CaseSeriesExtraction:
    """Create a test extraction object."""
    # Handle DOI-based identifiers
    actual_pmid = pmid if not pmid.startswith("DOI:") else None
    actual_doi = pmid.replace("DOI:", "") if pmid.startswith("DOI:") else "10.1234/test"

    return CaseSeriesExtraction(
        is_relevant=is_relevant,
        is_off_label=not is_relevant,
        disease="Not relevant - approved indication" if not is_relevant else "Test Disease",
        disease_normalized=None,
        disease_subtype=None,
        disease_category=None,
        source=CaseSeriesSource(
            pmid=actual_pmid,
            doi=actual_doi,
            title="Test Paper Title",
            authors="Test Author",
            journal="Test Journal",
            year=2024,
            abstract="Test abstract"
        ),
        patient_population=PatientPopulation(
            n_patients=10,
            description="Test patients",
            age_range=None,
            gender_distribution=None,
            disease_severity=None,
            prior_therapy_lines=None,
            inclusion_criteria=None,
            exclusion_criteria=None
        ),
        treatment=TreatmentDetails(
            drug_name=TEST_DRUG_NAME,
            dose="100mg",
            frequency="daily",
            duration="12 weeks",
            route="oral",
            concomitant_medications=None
        ),
        efficacy=EfficacyOutcome(
            primary_endpoint="Test endpoint",
            endpoint_result="Positive",
            response_rate="80%",
            responders_n=8,
            responders_pct=80.0,
            time_to_response=None,
            duration_of_response=None,
            efficacy_summary="Test summary"
        ),
        safety=SafetyOutcome(
            adverse_events=[],
            sae_count=None,
            discontinuations_n=None,
            discontinuations_due_to_ae=None,
            safety_summary=None
        ),
        biomarkers=[],
        study_design="case_series",
        evidence_level=EvidenceLevel.CASE_SERIES,
        follow_up_duration="12 weeks",
        key_findings="Test findings",
        limitations=None,
        individual_score=None,
        score_explanation=None,
        additional_diseases=[]
    )


def create_extraction_with_problematic_values(pmid: str) -> CaseSeriesExtraction:
    """Create extraction with values that previously caused issues."""
    # The Pydantic validators should handle these problematic values
    return CaseSeriesExtraction(
        is_relevant=False,
        is_off_label=True,
        disease="Not relevant - problematic values test",
        disease_normalized=None,
        disease_subtype=None,
        disease_category=None,
        source=CaseSeriesSource(
            pmid=pmid,
            doi="10.1234/problematic",
            title="Problematic Values Test",
            authors="Test Author",
            journal="Test Journal",
            year="Unknown",  # String instead of int - validator should convert to None
            abstract="Test abstract"
        ),
        patient_population=PatientPopulation(
            n_patients="Unknown",  # String instead of int - validator should convert to None
            description="Test patients",
            age_range=None,
            gender_distribution=None,
            disease_severity=None,
            prior_therapy_lines="Unknown",  # String - validator should handle
            inclusion_criteria=None,
            exclusion_criteria=None
        ),
        treatment=TreatmentDetails(
            drug_name=TEST_DRUG_NAME,
            dose="100mg",
            frequency="daily",
            duration="12 weeks",
            route="oral",
            concomitant_medications=None
        ),
        efficacy=EfficacyOutcome(
            primary_endpoint="Test endpoint",
            endpoint_result="Positive",
            response_rate="80%",
            responders_n="N/A",  # String - validator should convert to None
            responders_pct=80.0,
            time_to_response=None,
            duration_of_response=None,
            efficacy_summary="Test summary"
        ),
        safety=SafetyOutcome(
            adverse_events=[],
            sae_count="Not reported",  # String - validator should convert to None
            discontinuations_n=None,
            discontinuations_due_to_ae=None,
            safety_summary=None
        ),
        biomarkers=[],
        study_design="case_series",
        evidence_level=EvidenceLevel.CASE_SERIES,
        follow_up_duration="12 weeks",
        key_findings="Problematic values test",
        limitations=None,
        individual_score=None,
        score_explanation=None,
        additional_diseases=[]
    )


async def run_tests():
    """Run all tests."""
    db = CaseSeriesDatabase(DATABASE_URL)

    if not db.is_available:
        logger.error("Database not available - cannot run tests")
        return False

    logger.info("=" * 60)
    logger.info("Starting supplemental skip logic tests")
    logger.info("=" * 60)

    all_passed = True

    # Clean up any previous test data
    logger.info("\n1. Cleaning up previous test data...")
    try:
        conn = db._get_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cs_extractions WHERE drug_name = %s", (TEST_DRUG_NAME,))
            deleted = cur.rowcount
            cur.execute("DELETE FROM cs_analysis_runs WHERE drug_name = %s", (TEST_DRUG_NAME,))
            conn.commit()
        conn.close()
        logger.info(f"   Cleaned up {deleted} previous test extractions")
    except Exception as e:
        logger.error(f"   Failed to clean up: {e}")

    # Create a test analysis run for the foreign key
    logger.info("\n1b. Creating test analysis run...")
    test_run_id = str(uuid.uuid4())
    try:
        conn = db._get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO cs_analysis_runs (run_id, drug_name, status)
                VALUES (%s, %s, 'running')
            """, (test_run_id, TEST_DRUG_NAME))
            conn.commit()
        conn.close()
        logger.info(f"   Created test run: {test_run_id[:8]}...")
    except Exception as e:
        logger.error(f"   Failed to create test run: {e}")
        return False

    # Test 1: Save a non-relevant extraction
    logger.info("\n2. Testing: Save non-relevant extraction...")
    try:
        extraction = create_test_extraction(is_relevant=False, pmid=TEST_PMID)
        result = db.save_extraction(
            run_id=test_run_id,
            extraction=extraction,
            drug_name=TEST_DRUG_NAME
        )
        if result:
            logger.info(f"   ✓ Non-relevant extraction saved successfully (ID: {result})")
        else:
            logger.error("   ✗ save_extraction returned None")
            all_passed = False
    except Exception as e:
        logger.error(f"   ✗ Failed to save non-relevant extraction: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # Test 2: Save extraction with DOI-based identifier
    logger.info("\n3. Testing: Save extraction with DOI identifier...")
    try:
        extraction = create_test_extraction(is_relevant=False, pmid=TEST_DOI_PAPER)
        # For DOI-based papers, we need to set the pmid field in source to the DOI:xxx format
        # The extraction already has pmid=None and doi set, but the database uses pmid column
        # So we need to override the source.pmid to store the DOI:xxx identifier
        extraction.source.pmid = TEST_DOI_PAPER  # Store as "DOI:xxx"
        result = db.save_extraction(
            run_id=test_run_id,
            extraction=extraction,
            drug_name=TEST_DRUG_NAME
        )
        if result:
            logger.info(f"   ✓ DOI-based extraction saved successfully (ID: {result})")
        else:
            logger.error("   ✗ save_extraction returned None")
            all_passed = False
    except Exception as e:
        logger.error(f"   ✗ Failed to save DOI-based extraction: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # Test 3: Save extraction with problematic values
    logger.info("\n4. Testing: Save extraction with problematic values (Unknown, N/A, etc.)...")
    problematic_pmid = "TEST_PROBLEMATIC_001"
    try:
        extraction = create_extraction_with_problematic_values(problematic_pmid)
        logger.info(f"   Created extraction with: year={extraction.source.year}, n_patients={extraction.patient_population.n_patients}, responders_n={extraction.efficacy.responders_n}")
        result = db.save_extraction(
            run_id=test_run_id,
            extraction=extraction,
            drug_name=TEST_DRUG_NAME
        )
        if result:
            logger.info(f"   ✓ Extraction with problematic values saved successfully (ID: {result})")
        else:
            logger.error("   ✗ save_extraction returned None")
            all_passed = False
    except Exception as e:
        logger.error(f"   ✗ Failed to save extraction with problematic values: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # Test 4: Verify extractions appear in skip list
    logger.info("\n5. Testing: Verify papers appear in supplemental skip list...")
    try:
        skip_pmids = db.get_processed_pmids(TEST_DRUG_NAME)

        if TEST_PMID in skip_pmids:
            logger.info(f"   ✓ PMID {TEST_PMID} found in skip list")
        else:
            logger.error(f"   ✗ PMID {TEST_PMID} NOT found in skip list")
            all_passed = False

        if TEST_DOI_PAPER in skip_pmids:
            logger.info(f"   ✓ DOI paper {TEST_DOI_PAPER} found in skip list")
        else:
            logger.error(f"   ✗ DOI paper {TEST_DOI_PAPER} NOT found in skip list")
            all_passed = False

        if problematic_pmid in skip_pmids:
            logger.info(f"   ✓ Problematic paper {problematic_pmid} found in skip list")
        else:
            logger.error(f"   ✗ Problematic paper {problematic_pmid} NOT found in skip list")
            all_passed = False

        logger.info(f"   Total papers in skip list for {TEST_DRUG_NAME}: {len(skip_pmids)}")
    except Exception as e:
        logger.error(f"   ✗ Failed to get skip list: {e}")
        all_passed = False

    # Test 5: Verify extraction can be loaded (cache check)
    logger.info("\n6. Testing: Verify extraction can be loaded from cache...")
    try:
        cached = db.load_extraction(TEST_DRUG_NAME, TEST_PMID)
        if cached:
            logger.info(f"   ✓ Extraction loaded from cache")
            logger.info(f"   - is_relevant: {cached.is_relevant}")
            logger.info(f"   - disease: {cached.disease}")
        else:
            logger.error("   ✗ Failed to load extraction from cache")
            all_passed = False
    except Exception as e:
        logger.error(f"   ✗ Failed to load extraction: {e}")
        all_passed = False

    # Test 6: Verify non-relevant extraction is returned (not filtered out)
    logger.info("\n7. Testing: Verify non-relevant extraction is returned by load_extraction...")
    try:
        cached = db.load_extraction(TEST_DRUG_NAME, TEST_PMID)
        if cached and cached.is_relevant == False:
            logger.info("   ✓ Non-relevant extraction correctly returned (not filtered)")
        elif cached and cached.is_relevant == True:
            logger.error("   ✗ Extraction returned but is_relevant is True (unexpected)")
            all_passed = False
        else:
            logger.error("   ✗ Extraction not returned")
            all_passed = False
    except Exception as e:
        logger.error(f"   ✗ Failed: {e}")
        all_passed = False

    # Clean up test data
    logger.info("\n8. Cleaning up test data...")
    try:
        conn = db._get_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cs_extractions WHERE drug_name = %s", (TEST_DRUG_NAME,))
            deleted = cur.rowcount
            cur.execute("DELETE FROM cs_analysis_runs WHERE drug_name = %s", (TEST_DRUG_NAME,))
            conn.commit()
        conn.close()
        logger.info(f"   Cleaned up {deleted} test extractions and test run")
    except Exception as e:
        logger.error(f"   Failed to clean up: {e}")

    # Summary
    logger.info("\n" + "=" * 60)
    if all_passed:
        logger.info("✓ ALL TESTS PASSED")
    else:
        logger.error("✗ SOME TESTS FAILED")
    logger.info("=" * 60)

    return all_passed


if __name__ == "__main__":
    asyncio.run(run_tests())
