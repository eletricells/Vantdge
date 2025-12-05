"""
Clinical Extraction Database Interface

Service class for saving and retrieving clinical trial extractions.
"""
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime
import pandas as pd
import traceback
import re

from src.models.clinical_extraction_schemas import (
    ClinicalTrialExtraction,
    BaselineCharacteristics,
    EfficacyEndpoint,
    SafetyEndpoint,
)


logger = logging.getLogger(__name__)


class ClinicalExtractionDatabase:
    """
    Database interface for clinical trial extractions.

    Handles CRUD operations for:
    - Clinical trial extractions (main table)
    - Baseline characteristics
    - Efficacy endpoints
    - Safety endpoints
    - Standard clinical endpoints (library)
    """

    def __init__(self, database_url: str):
        """
        Initialize clinical extraction database connection.

        Args:
            database_url: PostgreSQL connection string
        """
        self.database_url = database_url
        self.connection = None

    @property
    def conn(self):
        """Alias for connection."""
        return self.connection

    def connect(self):
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(self.database_url)
            logger.info("Connected to clinical extraction database")
        except Exception as e:
            logger.error(f"Failed to connect to clinical extraction database: {e}")
            raise

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Closed clinical extraction database connection")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # =========================================================================
    # SAVE EXTRACTION
    # =========================================================================

    def save_extraction(self, extraction: ClinicalTrialExtraction) -> int:
        """
        Save a complete clinical trial extraction to the database.

        Saves to 4 tables:
        1. clinical_trial_extractions (main)
        2. trial_baseline_characteristics
        3. trial_efficacy_endpoints
        4. trial_safety_endpoints

        Args:
            extraction: ClinicalTrialExtraction object

        Returns:
            extraction_id (primary key)
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            # Check if extraction already exists
            existing_id = self.check_extraction_exists(
                extraction.nct_id,
                extraction.arm_name,
                extraction.dosing_regimen
            )

            if existing_id:
                logger.info(
                    f"Extraction already exists for {extraction.nct_id} / {extraction.arm_name} "
                    f"(ID: {existing_id}). Updating."
                )
                # Delete old extraction and re-insert
                self._delete_extraction(existing_id, cursor)

            # 1. Insert into clinical_trial_extractions
            query = """
                INSERT INTO clinical_trial_extractions (
                    nct_id, trial_name, drug_name, generic_name, indication,
                    arm_name, dosing_regimen, background_therapy, n, phase,
                    paper_pmid, paper_doi, paper_title,
                    extraction_timestamp, extraction_confidence, extraction_notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING extraction_id
            """

            cursor.execute(query, (
                extraction.nct_id,
                extraction.trial_name,
                extraction.drug_name,
                extraction.generic_name,
                extraction.indication,
                extraction.arm_name,
                extraction.dosing_regimen,
                extraction.background_therapy,
                extraction.n,
                extraction.phase,
                extraction.paper_pmid,
                extraction.paper_doi,
                extraction.paper_title,
                extraction.extraction_timestamp,
                extraction.extraction_confidence,
                extraction.extraction_notes
            ))

            extraction_id = cursor.fetchone()[0]
            logger.info(f"Saved extraction {extraction_id} for {extraction.nct_id} / {extraction.arm_name}")

            # 2. Insert baseline characteristics
            if extraction.baseline:
                self._save_baseline(extraction_id, extraction.baseline, cursor)

            # 2b. Insert baseline characteristics detail
            if extraction.baseline_characteristics_detail:
                self._save_baseline_characteristics_detail(extraction_id, extraction.baseline_characteristics_detail, cursor)

            # 3. Insert efficacy endpoints
            if extraction.efficacy_endpoints:
                self._save_efficacy_endpoints(extraction_id, extraction.efficacy_endpoints, cursor)

            # 4. Insert safety endpoints
            if extraction.safety_endpoints:
                self._save_safety_endpoints(extraction_id, extraction.safety_endpoints, cursor)

            self.connection.commit()
            cursor.close()

            logger.info(f"Successfully saved extraction {extraction_id} with all related data")
            return extraction_id

        except Exception as e:
            logger.error(f"Failed to save extraction: {e}")
            if self.connection:
                self.connection.rollback()
            raise

    def save_extraction_gracefully(self, extraction: ClinicalTrialExtraction) -> Dict[str, Any]:
        """
        Save extraction with graceful error handling.

        Continues saving even if individual sections fail, tracking detailed results.

        Returns:
            Dict with keys:
                - nct_id: str
                - drug_name: str
                - indication: str
                - arm_name: str
                - trial_metadata: dict (success, error, extraction_id)
                - baseline: dict (success, error, fields_saved)
                - efficacy: dict (success, error, count)
                - safety: dict (success, error, count)
                - overall_success: bool (True if metadata + at least one data section saved)
                - errors: list of error dicts
        """
        if not self.connection:
            self.connect()

        results = {
            'nct_id': extraction.nct_id,
            'drug_name': extraction.drug_name,
            'indication': extraction.indication,
            'arm_name': extraction.arm_name,
            'trial_metadata': {'success': False, 'error': None, 'extraction_id': None},
            'baseline': {'success': False, 'error': None, 'fields_saved': 0},
            'efficacy': {'success': False, 'error': None, 'count': 0},
            'safety': {'success': False, 'error': None, 'count': 0},
            'overall_success': False,
            'errors': []
        }

        cursor = None
        extraction_id = None

        try:
            cursor = self.connection.cursor()

            # SECTION 1: Trial Metadata (REQUIRED)
            try:
                # Check if extraction already exists
                existing_id = self.check_extraction_exists(
                    extraction.nct_id,
                    extraction.arm_name,
                    extraction.dosing_regimen
                )

                if existing_id:
                    logger.info(
                        f"Extraction already exists for {extraction.nct_id} / {extraction.arm_name} "
                        f"(ID: {existing_id}). Updating."
                    )
                    self._delete_extraction(existing_id, cursor)

                # Insert trial metadata
                query = """
                    INSERT INTO clinical_trial_extractions (
                        nct_id, trial_name, drug_name, generic_name, indication,
                        arm_name, dosing_regimen, background_therapy, n, phase,
                        paper_pmid, paper_doi, paper_title,
                        extraction_timestamp, extraction_confidence, extraction_notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING extraction_id
                """

                cursor.execute(query, (
                    extraction.nct_id,
                    extraction.trial_name,
                    extraction.drug_name,
                    extraction.generic_name,
                    extraction.indication,
                    extraction.arm_name,
                    extraction.dosing_regimen,
                    extraction.background_therapy,
                    extraction.n,
                    extraction.phase,
                    extraction.paper_pmid,
                    extraction.paper_doi,
                    extraction.paper_title,
                    extraction.extraction_timestamp,
                    extraction.extraction_confidence,
                    extraction.extraction_notes
                ))

                extraction_id = cursor.fetchone()[0]
                self.connection.commit()  # Commit metadata immediately

                results['trial_metadata'] = {
                    'success': True,
                    'error': None,
                    'extraction_id': extraction_id
                }
                logger.info(f"✓ Trial metadata saved (ID: {extraction_id})")

                # Save quality issues and warnings if present
                if extraction.extraction_notes:
                    try:
                        # Parse issues and warnings from extraction_notes
                        issues = []
                        warnings = []

                        # extraction_notes contains the validation summary with ISSUES and WARNINGS sections
                        if 'ISSUES' in extraction.extraction_notes:
                            # Extract issues section
                            issues_section = extraction.extraction_notes.split('ISSUES')[1].split('WARNINGS')[0] if 'WARNINGS' in extraction.extraction_notes else extraction.extraction_notes.split('ISSUES')[1]
                            for line in issues_section.split('\n'):
                                line = line.strip()
                                if line.startswith('- '):
                                    issues.append(line[2:])

                        if 'WARNINGS' in extraction.extraction_notes:
                            # Extract warnings section
                            warnings_section = extraction.extraction_notes.split('WARNINGS')[1]
                            for line in warnings_section.split('\n'):
                                line = line.strip()
                                if line.startswith('- '):
                                    warnings.append(line[2:])

                        if issues or warnings:
                            logger.info(f"Saving {len(issues)} issues and {len(warnings)} warnings for extraction {extraction_id}")
                            self.save_quality_issues(extraction_id, issues, warnings)
                    except Exception as e:
                        logger.error(f"Failed to parse or save quality issues for extraction {extraction_id}: {e}")
                        import traceback
                        logger.error(traceback.format_exc())

            except Exception as e:
                error_info = self._create_error_info(extraction, 'trial_metadata', e)
                results['trial_metadata'] = {
                    'success': False,
                    'error': str(e),
                    'extraction_id': None
                }
                results['errors'].append(error_info)
                self._log_extraction_error(error_info)

                logger.error(f"✗ Trial metadata FAILED: {e}")
                if self.connection:
                    self.connection.rollback()

                # Cannot continue without metadata
                if cursor:
                    cursor.close()
                return results

            # SECTION 2: Baseline (OPTIONAL)
            if extraction.baseline:
                try:
                    self._save_baseline(extraction_id, extraction.baseline, cursor)
                    self.connection.commit()

                    # Count non-null fields
                    baseline_dict = extraction.baseline.model_dump()
                    fields_saved = sum(1 for v in baseline_dict.values() if v is not None)

                    results['baseline'] = {
                        'success': True,
                        'error': None,
                        'fields_saved': fields_saved
                    }
                    logger.info(f"✓ Baseline saved ({fields_saved} fields)")

                except Exception as e:
                    error_info = self._create_error_info(extraction, 'baseline', e, 1)
                    results['baseline'] = {
                        'success': False,
                        'error': str(e),
                        'fields_saved': 0
                    }
                    results['errors'].append(error_info)
                    self._log_extraction_error(error_info)

                    logger.error(f"✗ Baseline FAILED: {e}")
                    if self.connection:
                        self.connection.rollback()

            # SECTION 2b: Baseline Characteristics Detail (OPTIONAL)
            if extraction.baseline_characteristics_detail:
                try:
                    self._save_baseline_characteristics_detail(extraction_id, extraction.baseline_characteristics_detail, cursor)
                    self.connection.commit()

                    results['baseline_characteristics_detail'] = {
                        'success': True,
                        'error': None,
                        'count': len(extraction.baseline_characteristics_detail)
                    }
                    logger.info(f"✓ Baseline characteristics detail saved ({len(extraction.baseline_characteristics_detail)} characteristics)")

                except Exception as e:
                    error_info = self._create_error_info(extraction, 'baseline_characteristics_detail', e, len(extraction.baseline_characteristics_detail))
                    results['baseline_characteristics_detail'] = {
                        'success': False,
                        'error': str(e),
                        'count': 0
                    }
                    results['errors'].append(error_info)
                    self._log_extraction_error(error_info)

                    logger.error(f"✗ Baseline characteristics detail FAILED: {e}")
                    if self.connection:
                        self.connection.rollback()

            # SECTION 3: Efficacy Endpoints (OPTIONAL)
            if extraction.efficacy_endpoints:
                try:
                    self._save_efficacy_endpoints(extraction_id, extraction.efficacy_endpoints, cursor)
                    self.connection.commit()

                    results['efficacy'] = {
                        'success': True,
                        'error': None,
                        'count': len(extraction.efficacy_endpoints)
                    }
                    logger.info(f"✓ Efficacy saved ({len(extraction.efficacy_endpoints)} endpoints)")

                except Exception as e:
                    error_info = self._create_error_info(
                        extraction, 'efficacy', e, len(extraction.efficacy_endpoints)
                    )
                    results['efficacy'] = {
                        'success': False,
                        'error': str(e),
                        'count': 0
                    }
                    results['errors'].append(error_info)
                    self._log_extraction_error(error_info)

                    logger.error(f"✗ Efficacy FAILED: {e}")
                    logger.error(f"  → {len(extraction.efficacy_endpoints)} endpoints attempted")
                    if self.connection:
                        self.connection.rollback()

            # SECTION 4: Safety Endpoints (OPTIONAL)
            if extraction.safety_endpoints:
                try:
                    self._save_safety_endpoints(extraction_id, extraction.safety_endpoints, cursor)
                    self.connection.commit()

                    results['safety'] = {
                        'success': True,
                        'error': None,
                        'count': len(extraction.safety_endpoints)
                    }
                    logger.info(f"✓ Safety saved ({len(extraction.safety_endpoints)} endpoints)")

                except Exception as e:
                    error_info = self._create_error_info(
                        extraction, 'safety', e, len(extraction.safety_endpoints)
                    )
                    results['safety'] = {
                        'success': False,
                        'error': str(e),
                        'count': 0
                    }
                    results['errors'].append(error_info)
                    self._log_extraction_error(error_info)

                    logger.error(f"✗ Safety FAILED: {e}")
                    logger.error(f"  → {len(extraction.safety_endpoints)} endpoints attempted")
                    if self.connection:
                        self.connection.rollback()

            # Calculate overall success
            sections_saved = sum([
                results['trial_metadata']['success'],
                results['baseline']['success'],
                results['efficacy']['success'],
                results['safety']['success']
            ])

            # Success if metadata + at least one data section saved
            results['overall_success'] = (
                results['trial_metadata']['success'] and sections_saved >= 2
            )

            # Log summary
            self._log_extraction_summary(results)

        finally:
            if cursor:
                cursor.close()

        return results

    def _create_error_info(
        self,
        extraction: ClinicalTrialExtraction,
        section: str,
        exception: Exception,
        affected_count: int = 0
    ) -> Dict[str, Any]:
        """Create detailed error information dict."""
        error_message = str(exception)
        error_type = type(exception).__name__

        # Parse missing column from error if UndefinedColumn
        missing_column = None
        if 'column' in error_message.lower() and 'does not exist' in error_message.lower():
            # Extract column name from error like: column "value_unit" of relation...
            match = re.search(r'column "([^"]+)"', error_message)
            if match:
                missing_column = match.group(1)

        return {
            'nct_id': extraction.nct_id,
            'drug_name': extraction.drug_name,
            'indication': extraction.indication,
            'section': section,
            'error_type': error_type,
            'error_message': error_message,
            'missing_column': missing_column,
            'affected_count': affected_count,
            'stack_trace': traceback.format_exc()
        }

    def save_quality_issues(
        self,
        extraction_id: int,
        issues: List[str],
        warnings: List[str],
        validation_result: Optional[Dict[str, Any]] = None
    ):
        """
        Save extraction quality issues and warnings to database.

        Args:
            extraction_id: ID of the extraction
            issues: List of critical issues found
            warnings: List of warnings found
            validation_result: Optional validation result dict with additional context
        """
        if not extraction_id or (not issues and not warnings):
            return

        quality_conn = None
        try:
            quality_conn = psycopg2.connect(self.database_url)
            cursor = quality_conn.cursor()

            # Save issues
            for i, issue in enumerate(issues, 1):
                # Skip if issue is None or empty
                if not issue:
                    logger.debug(f"Skipping empty issue {i}")
                    continue

                # Ensure issue is a string - handle all types
                try:
                    logger.debug(f"Processing issue {i}/{len(issues)}, type: {type(issue).__name__}")
                    if isinstance(issue, str):
                        issue_str = issue
                    elif isinstance(issue, (int, float, bool)):
                        issue_str = str(issue)
                    elif isinstance(issue, type):
                        # Skip type objects (e.g., <class 'str'>)
                        logger.warning(f"Skipping type object in issues: {issue}")
                        continue
                    else:
                        issue_str = str(issue)
                    logger.debug(f"Issue {i} converted to string, length: {len(issue_str)}")
                except Exception as e:
                    logger.error(f"Failed to convert issue {i} to string: {e}, type: {type(issue)}, skipping")
                    continue

                query = """
                    INSERT INTO extraction_quality_issues (
                        extraction_id, issue_type, category, title, description,
                        severity, affected_section, suggested_action
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    extraction_id,
                    'error',
                    'data_quality',
                    issue_str[:255],  # title (truncate to 255 chars)
                    issue_str,  # description
                    'high',
                    'general',
                    'Review extracted data for accuracy'
                ))

            # Save warnings
            for warning in warnings:
                # Skip if warning is None or empty
                if not warning:
                    continue

                # Ensure warning is a string - handle all types
                try:
                    if isinstance(warning, str):
                        warning_str = warning
                    elif isinstance(warning, (int, float, bool)):
                        warning_str = str(warning)
                    elif isinstance(warning, type):
                        # Skip type objects (e.g., <class 'str'>)
                        logger.warning(f"Skipping type object in warnings: {warning}")
                        continue
                    else:
                        warning_str = str(warning)
                except Exception as e:
                    logger.warning(f"Failed to convert warning to string: {e}, skipping")
                    continue

                query = """
                    INSERT INTO extraction_quality_issues (
                        extraction_id, issue_type, category, title, description,
                        severity, affected_section, suggested_action
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (
                    extraction_id,
                    'warning',
                    'data_quality',
                    warning_str[:255],  # title (truncate to 255 chars)
                    warning_str,  # description
                    'medium',
                    'general',
                    'Review data for potential issues'
                ))

            quality_conn.commit()
            logger.info(f"✓ Saved {len(issues)} issues and {len(warnings)} warnings for extraction {extraction_id}")

        except Exception as e:
            logger.error(f"Failed to save quality issues: {e}")
        finally:
            if quality_conn:
                quality_conn.close()

    def get_quality_issues(self, extraction_id: int) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get quality issues and warnings for an extraction.

        Args:
            extraction_id: ID of the extraction

        Returns:
            Dict with 'issues' and 'warnings' lists
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)

            query = """
                SELECT issue_id, issue_type, category, title, description, severity,
                       affected_section, suggested_action, created_at
                FROM extraction_quality_issues
                WHERE extraction_id = %s
                ORDER BY severity DESC, created_at DESC
            """

            logger.debug(f"Executing query for extraction_id={extraction_id}")
            cursor.execute(query, (extraction_id,))
            logger.debug("Query executed, fetching rows...")
            rows = cursor.fetchall()
            logger.debug(f"Fetched {len(rows)} rows")
            cursor.close()

            issues = []
            warnings = []

            for i, row in enumerate(rows, 1):
                try:
                    logger.debug(f"Processing row {i}/{len(rows)}")
                    # Convert row to dict and ensure all values are JSON-serializable
                    item = {}
                    for key, value in dict(row).items():
                        logger.debug(f"  Processing key={key}, value type={type(value)}")
                        # Convert datetime objects to strings
                        if hasattr(value, 'isoformat'):
                            item[key] = value.isoformat()
                        else:
                            item[key] = value

                    if row['issue_type'] == 'error':
                        issues.append(item)
                    else:
                        warnings.append(item)
                except Exception as e:
                    logger.error(f"Failed to process row {i}: {e}")
                    logger.error(f"Row data: {dict(row)}")
                    raise

            logger.debug(f"Returning {len(issues)} issues and {len(warnings)} warnings")
            return {'issues': issues, 'warnings': warnings}

        except Exception as e:
            logger.error(f"Failed to get quality issues: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {'issues': [], 'warnings': []}

    def _log_extraction_error(self, error_info: Dict[str, Any]):
        """
        Log error to extraction_errors table.

        Creates a new connection to avoid transaction conflicts.
        """
        error_conn = None
        try:
            # Create a NEW connection for error logging to avoid transaction conflicts
            error_conn = psycopg2.connect(self.database_url)
            cursor = error_conn.cursor()

            query = """
                INSERT INTO extraction_errors (
                    nct_id, drug_name, indication, section, error_type,
                    error_message, missing_column, affected_count, stack_trace
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            cursor.execute(query, (
                error_info['nct_id'],
                error_info['drug_name'],
                error_info['indication'],
                error_info['section'],
                error_info['error_type'],
                error_info['error_message'],
                error_info['missing_column'],
                error_info['affected_count'],
                error_info['stack_trace']
            ))

            error_conn.commit()
            cursor.close()

        except Exception as e:
            logger.warning(f"Failed to log extraction error: {e}")
        finally:
            if error_conn:
                error_conn.close()

    def _log_extraction_summary(self, results: Dict[str, Any]):
        """Log comprehensive extraction summary."""
        logger.info("=" * 70)
        logger.info(f"EXTRACTION COMPLETE: {results['nct_id']} / {results['arm_name']}")
        logger.info("=" * 70)

        sections = ['trial_metadata', 'baseline', 'efficacy', 'safety']
        success_count = sum(1 for s in sections if results.get(s, {}).get('success'))

        logger.info(f"Overall: {success_count}/{len(sections)} sections saved")
        logger.info("")

        # Trial metadata
        if results['trial_metadata']['success']:
            logger.info(f"  ✓ Trial Metadata (ID: {results['trial_metadata']['extraction_id']})")
        else:
            logger.error(f"  ✗ Trial Metadata")
            logger.error(f"    → {results['trial_metadata']['error']}")

        # Baseline
        if results['baseline']['success']:
            logger.info(f"  ✓ Baseline ({results['baseline']['fields_saved']} fields)")
        elif results['baseline']['error']:
            logger.error(f"  ✗ Baseline")
            logger.error(f"    → {results['baseline']['error']}")

        # Efficacy
        if results['efficacy']['success']:
            logger.info(f"  ✓ Efficacy ({results['efficacy']['count']} endpoints)")
        elif results['efficacy']['error']:
            logger.error(f"  ✗ Efficacy")
            logger.error(f"    → {results['efficacy']['error']}")

        # Safety
        if results['safety']['success']:
            logger.info(f"  ✓ Safety ({results['safety']['count']} endpoints)")
        elif results['safety']['error']:
            logger.error(f"  ✗ Safety")
            logger.error(f"    → {results['safety']['error']}")

        logger.info("=" * 70)

        if results['overall_success']:
            logger.info("✓ EXTRACTION SUCCESSFUL (partial data saved)")
        else:
            logger.error("✗ EXTRACTION FAILED (minimal/no data saved)")

    def _save_baseline(
        self,
        extraction_id: int,
        baseline: BaselineCharacteristics,
        cursor
    ):
        """Save baseline characteristics."""
        query = """
            INSERT INTO trial_baseline_characteristics (
                extraction_id, n, median_age, mean_age, age_range,
                male_pct, female_pct,
                race_white_pct, race_black_african_american_pct, race_asian_pct,
                race_hispanic_latino_pct, race_native_american_pct, race_pacific_islander_pct,
                race_mixed_pct, race_other_pct, race_unknown_pct, race_additional_detail,
                median_disease_duration, mean_disease_duration, disease_duration_unit,
                prior_steroid_use_pct, prior_biologic_use_pct, prior_tnf_inhibitor_use_pct,
                prior_immunosuppressant_use_pct, prior_topical_therapy_pct,
                treatment_naive_pct, prior_lines_median,
                prior_medications_detail, disease_specific_baseline, baseline_severity_scores,
                source_table
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        cursor.execute(query, (
            extraction_id,
            baseline.n,
            baseline.median_age,
            baseline.mean_age,
            baseline.age_range,
            baseline.male_pct,
            baseline.female_pct,
            baseline.race_white_pct,
            baseline.race_black_african_american_pct,
            baseline.race_asian_pct,
            baseline.race_hispanic_latino_pct,
            baseline.race_native_american_pct,
            baseline.race_pacific_islander_pct,
            baseline.race_mixed_pct,
            baseline.race_other_pct,
            baseline.race_unknown_pct,
            Json(baseline.race_additional_detail) if baseline.race_additional_detail else None,
            baseline.median_disease_duration,
            baseline.mean_disease_duration,
            baseline.disease_duration_unit,
            baseline.prior_steroid_use_pct,
            baseline.prior_biologic_use_pct,
            baseline.prior_tnf_inhibitor_use_pct,
            baseline.prior_immunosuppressant_use_pct,
            baseline.prior_topical_therapy_pct,
            baseline.treatment_naive_pct,
            baseline.prior_lines_median,
            Json(baseline.prior_medications_detail) if baseline.prior_medications_detail else None,
            Json(baseline.disease_specific_baseline) if baseline.disease_specific_baseline else None,
            Json(baseline.baseline_severity_scores) if baseline.baseline_severity_scores else None,
            baseline.source_table
        ))

        logger.debug(f"Saved baseline characteristics for extraction {extraction_id}")

    def _save_baseline_characteristics_detail(
        self,
        extraction_id: int,
        characteristics: List,
        cursor
    ):
        """Save individual baseline characteristics (demographics, biomarkers, etc.)."""
        from src.models.clinical_extraction_schemas import BaselineCharacteristicDetail

        query = """
            INSERT INTO trial_baseline_characteristics_detail (
                extraction_id, characteristic_name, characteristic_category, characteristic_description,
                cohort, value_numeric, value_text, unit,
                n_patients, percentage, mean_value, median_value, sd_value, range_min, range_max,
                source_table
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        for char in characteristics:
            # Handle both dict and BaselineCharacteristicDetail objects
            if isinstance(char, dict):
                char_obj = BaselineCharacteristicDetail(**char)
            else:
                char_obj = char

            cursor.execute(query, (
                extraction_id,
                char_obj.characteristic_name,
                char_obj.characteristic_category,
                char_obj.characteristic_description,
                char_obj.cohort,
                char_obj.value_numeric,
                char_obj.value_text,
                char_obj.unit,
                char_obj.n_patients,
                char_obj.percentage,
                char_obj.mean_value,
                char_obj.median_value,
                char_obj.sd_value,
                char_obj.range_min,
                char_obj.range_max,
                char_obj.source_table
            ))

        logger.debug(f"Saved {len(characteristics)} baseline characteristics for extraction {extraction_id}")

    def _deduplicate_and_clean_endpoints(self, endpoints: List[EfficacyEndpoint]) -> List[EfficacyEndpoint]:
        """
        Deduplicate and clean efficacy endpoints by:
        1. Extracting analysis type from endpoint name
        2. Merging duplicate endpoints from different sources (figures + tables)

        Handles cases where Claude didn't properly separate analysis type from endpoint name.
        Examples:
        - "24-hour UPCR (ITT population)" → name: "24-hour UPCR", analysis_type: "ITT"
        - "Mean eGFR - ITT" → name: "Mean eGFR", analysis_type: "ITT"

        Also merges duplicates where same endpoint appears in both figures and tables:
        - Figure: SRI-4 Week 48 with p-value=<0.10
        - Table: SRI-4 Week 48 with responders_pct=51.5
        → Merged: SRI-4 Week 48 with both p-value AND responders_pct
        """
        import re
        from collections import defaultdict

        cleaned_endpoints = []

        # Step 1: Clean endpoint names and extract analysis types
        for endpoint in endpoints:
            # Skip if already has analysis_type
            if not endpoint.analysis_type:
                # Try to extract analysis type from endpoint name
                name = endpoint.endpoint_name
                analysis_type = None

                # Pattern 1: "(ITT population)", "(PP population)", etc.
                match = re.search(r'\((ITT|PP|Safety|Per-protocol|Intent-to-treat|Per Protocol|Intention-to-treat)\s+population\)', name, re.IGNORECASE)
                if match:
                    analysis_type = match.group(1).upper() if match.group(1).upper() in ['ITT', 'PP'] else match.group(1)
                    name = re.sub(r'\s*\((ITT|PP|Safety|Per-protocol|Intent-to-treat|Per Protocol|Intention-to-treat)\s+population\)', '', name, flags=re.IGNORECASE).strip()

                # Pattern 2: "(ITT)", "(PP)", etc.
                if not analysis_type:
                    match = re.search(r'\((ITT|PP|Safety|Per-protocol|Intent-to-treat|Per Protocol|Intention-to-treat)\)', name, re.IGNORECASE)
                    if match:
                        analysis_type = match.group(1).upper() if match.group(1).upper() in ['ITT', 'PP'] else match.group(1)
                        name = re.sub(r'\s*\((ITT|PP|Safety|Per-protocol|Intent-to-treat|Per Protocol|Intention-to-treat)\)', '', name, flags=re.IGNORECASE).strip()

                # Pattern 3: "- ITT", "- PP", etc.
                if not analysis_type:
                    match = re.search(r'\s*-\s*(ITT|PP|Safety|Per-protocol|Intent-to-treat|Per Protocol|Intention-to-treat)$', name, re.IGNORECASE)
                    if match:
                        analysis_type = match.group(1).upper() if match.group(1).upper() in ['ITT', 'PP'] else match.group(1)
                        name = re.sub(r'\s*-\s*(ITT|PP|Safety|Per-protocol|Intent-to-treat|Per Protocol|Intention-to-treat)$', '', name, flags=re.IGNORECASE).strip()

                # Normalize analysis_type
                if analysis_type:
                    if analysis_type.upper() in ['ITT', 'INTENTION-TO-TREAT', 'INTENT-TO-TREAT']:
                        analysis_type = 'ITT'
                    elif analysis_type.upper() in ['PP', 'PER-PROTOCOL', 'PER PROTOCOL']:
                        analysis_type = 'PP'

                # Update endpoint with cleaned name and extracted analysis_type
                endpoint.endpoint_name = name
                if analysis_type:
                    endpoint.analysis_type = analysis_type

            cleaned_endpoints.append(endpoint)

        # Step 2: Merge duplicate endpoints from different sources
        # Group by (endpoint_name, timepoint) - these should be unique
        endpoint_groups = defaultdict(list)
        for endpoint in cleaned_endpoints:
            key = (endpoint.endpoint_name.strip().lower(), endpoint.timepoint.strip().lower() if endpoint.timepoint else '')
            endpoint_groups[key].append(endpoint)

        # Merge duplicates
        merged_endpoints = []
        for key, group in endpoint_groups.items():
            if len(group) == 1:
                # No duplicates
                merged_endpoints.append(group[0])
            else:
                # Merge duplicates - combine data from all sources
                merged = group[0]  # Start with first endpoint
                sources = [merged.source_table] if merged.source_table else []

                for dup in group[1:]:
                    # Merge responders_pct (prefer non-None)
                    if dup.responders_pct is not None and merged.responders_pct is None:
                        merged.responders_pct = dup.responders_pct

                    # Merge responders_n (prefer non-None)
                    if dup.responders_n is not None and merged.responders_n is None:
                        merged.responders_n = dup.responders_n

                    # Merge n_evaluated (prefer non-None)
                    if dup.n_evaluated is not None and merged.n_evaluated is None:
                        merged.n_evaluated = dup.n_evaluated

                    # Merge p_value (prefer non-None)
                    if dup.p_value is not None and merged.p_value is None:
                        merged.p_value = dup.p_value

                    # Merge stat_sig (prefer True if any source has it)
                    if dup.stat_sig is True:
                        merged.stat_sig = True

                    # Merge mean_value (prefer non-None)
                    if dup.mean_value is not None and merged.mean_value is None:
                        merged.mean_value = dup.mean_value

                    # Merge change_from_baseline_mean (prefer non-None)
                    if dup.change_from_baseline_mean is not None and merged.change_from_baseline_mean is None:
                        merged.change_from_baseline_mean = dup.change_from_baseline_mean

                    # Collect all sources
                    if dup.source_table and dup.source_table not in sources:
                        sources.append(dup.source_table)

                # Update source_table to show all sources
                merged.source_table = ', '.join(sources) if sources else None

                merged_endpoints.append(merged)

                logger.debug(f"Merged {len(group)} duplicate endpoints for {key[0]} at {key[1]}")

        logger.info(f"Deduplicated {len(cleaned_endpoints)} endpoints to {len(merged_endpoints)} (removed {len(cleaned_endpoints) - len(merged_endpoints)} duplicates)")

        return merged_endpoints

    def _save_efficacy_endpoints(
        self,
        extraction_id: int,
        endpoints: List[EfficacyEndpoint],
        cursor
    ):
        """Save efficacy endpoints."""
        # Clean and deduplicate endpoints
        endpoints = self._deduplicate_and_clean_endpoints(endpoints)

        query = """
            INSERT INTO trial_efficacy_endpoints (
                extraction_id, endpoint_category, endpoint_name, endpoint_unit, is_standard_endpoint,
                timepoint, timepoint_weeks, analysis_type, n_evaluated, responders_n, responders_pct,
                mean_value, median_value, change_from_baseline_mean, pct_change_from_baseline,
                stat_sig, p_value, confidence_interval, comparator_arm, source_table
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        for endpoint in endpoints:
            cursor.execute(query, (
                extraction_id,
                endpoint.endpoint_category,
                endpoint.endpoint_name,
                endpoint.endpoint_unit,
                endpoint.is_standard_endpoint,
                endpoint.timepoint,
                endpoint.timepoint_weeks,
                endpoint.analysis_type,
                endpoint.n_evaluated,
                endpoint.responders_n,
                endpoint.responders_pct,
                endpoint.mean_value,
                endpoint.median_value,
                endpoint.change_from_baseline_mean,
                endpoint.pct_change_from_baseline,
                endpoint.stat_sig,
                endpoint.p_value,
                endpoint.confidence_interval,
                endpoint.comparator_arm,
                endpoint.source_table
            ))

        logger.debug(f"Saved {len(endpoints)} efficacy endpoints for extraction {extraction_id}")

    def _save_safety_endpoints(
        self,
        extraction_id: int,
        endpoints: List[SafetyEndpoint],
        cursor
    ):
        """Save safety endpoints."""
        query = """
            INSERT INTO trial_safety_endpoints (
                extraction_id, event_category, event_name, severity,
                n_events, n_patients, incidence_pct, cohort, timepoint, source_table
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        for endpoint in endpoints:
            cursor.execute(query, (
                extraction_id,
                endpoint.event_category,
                endpoint.event_name,
                endpoint.severity,
                endpoint.n_events,
                endpoint.n_patients,
                endpoint.incidence_pct,
                endpoint.cohort,
                endpoint.timepoint,
                endpoint.source_table
            ))

        logger.debug(f"Saved {len(endpoints)} safety endpoints for extraction {extraction_id}")

    def _delete_extraction(self, extraction_id: int, cursor):
        """Delete existing extraction and all related data."""
        # Delete in reverse order (respecting foreign keys)
        cursor.execute("DELETE FROM trial_safety_endpoints WHERE extraction_id = %s", (extraction_id,))
        cursor.execute("DELETE FROM trial_efficacy_endpoints WHERE extraction_id = %s", (extraction_id,))
        cursor.execute("DELETE FROM trial_baseline_characteristics WHERE extraction_id = %s", (extraction_id,))
        cursor.execute("DELETE FROM clinical_trial_extractions WHERE extraction_id = %s", (extraction_id,))
        logger.debug(f"Deleted existing extraction {extraction_id}")

    # =========================================================================
    # CHECK EXISTENCE
    # =========================================================================

    def check_extraction_exists(
        self,
        nct_id: str,
        arm_name: str,
        dosing_regimen: Optional[str] = None
    ) -> Optional[int]:
        """
        Check if an extraction already exists for this trial arm.

        Args:
            nct_id: ClinicalTrials.gov NCT ID
            arm_name: Arm name
            dosing_regimen: Dosing regimen (optional)

        Returns:
            extraction_id if exists, None otherwise
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            query = """
                SELECT extraction_id
                FROM clinical_trial_extractions
                WHERE nct_id = %s AND arm_name = %s
            """
            params = [nct_id, arm_name]

            if dosing_regimen:
                query += " AND dosing_regimen = %s"
                params.append(dosing_regimen)

            cursor.execute(query, params)
            result = cursor.fetchone()
            cursor.close()

            if result:
                return result[0]
            return None

        except Exception as e:
            logger.error(f"Failed to check extraction existence: {e}")
            return None

    # =========================================================================
    # RETRIEVE EXTRACTIONS
    # =========================================================================

    def get_extractions_by_indication(
        self,
        indication: str,
        drug_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all extractions for an indication (optionally filtered by drugs).

        Uses the vw_complete_trial_data view for denormalized output.

        Args:
            indication: Disease indication
            drug_names: Optional list of drug names to filter

        Returns:
            List of extraction dictionaries
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)

            query = """
                SELECT *
                FROM vw_complete_trial_data
                WHERE indication = %s
            """
            params = [indication]

            if drug_names:
                placeholders = ','.join(['%s'] * len(drug_names))
                query += f" AND drug_name IN ({placeholders})"
                params.extend(drug_names)

            query += " ORDER BY nct_id, arm_name"

            cursor.execute(query, params)
            results = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get extractions by indication: {e}")
            return []

    def get_extractions_by_drug(
        self,
        drug_name: str,
        indication: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all extractions for a drug (optionally filtered by indication).

        Args:
            drug_name: Drug brand name
            indication: Optional disease indication

        Returns:
            List of extraction dictionaries
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)

            query = """
                SELECT *
                FROM vw_complete_trial_data
                WHERE drug_name = %s
            """
            params = [drug_name]

            if indication:
                query += " AND indication = %s"
                params.append(indication)

            query += " ORDER BY nct_id, arm_name"

            cursor.execute(query, params)
            results = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get extractions by drug: {e}")
            return []

    def get_baseline_comparison(
        self,
        indication: str,
        drug_names: Optional[List[str]] = None,
        characteristic_name: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get baseline characteristics comparison across trials.

        Uses vw_baseline_comparison view.

        Args:
            indication: Disease indication
            drug_names: Optional list of drug names
            characteristic_name: Optional specific characteristic to filter

        Returns:
            DataFrame with baseline characteristics comparison
        """
        if not self.connection:
            self.connect()

        try:
            query = """
                SELECT *
                FROM vw_baseline_comparison
                WHERE indication = %s
            """
            params = [indication]

            if drug_names:
                placeholders = ','.join(['%s'] * len(drug_names))
                query += f" AND drug_name IN ({placeholders})"
                params.extend(drug_names)

            if characteristic_name:
                query += " AND characteristic_name ILIKE %s"
                params.append(f"%{characteristic_name}%")

            query += " ORDER BY drug_name, characteristic_category, characteristic_name"

            df = pd.read_sql_query(query, self.connection, params=params)
            return df

        except Exception as e:
            logger.error(f"Failed to get baseline comparison: {e}")
            return pd.DataFrame()

    def get_efficacy_comparison(
        self,
        indication: str,
        drug_names: Optional[List[str]] = None,
        endpoint_name: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get efficacy comparison across trials.

        Uses vw_efficacy_comparison view.

        Args:
            indication: Disease indication
            drug_names: Optional list of drug names
            endpoint_name: Optional specific endpoint to filter

        Returns:
            DataFrame with efficacy comparison
        """
        if not self.connection:
            self.connect()

        try:
            query = """
                SELECT *
                FROM vw_efficacy_comparison
                WHERE indication = %s
            """
            params = [indication]

            if drug_names:
                placeholders = ','.join(['%s'] * len(drug_names))
                query += f" AND drug_name IN ({placeholders})"
                params.extend(drug_names)

            if endpoint_name:
                query += " AND endpoint_name ILIKE %s"
                params.append(f"%{endpoint_name}%")

            query += " ORDER BY drug_name, timepoint_weeks, endpoint_name"

            df = pd.read_sql_query(query, self.connection, params=params)
            return df

        except Exception as e:
            logger.error(f"Failed to get efficacy comparison: {e}")
            return pd.DataFrame()

    def get_safety_comparison(
        self,
        indication: str,
        drug_names: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Get safety comparison across trials.

        Uses vw_safety_comparison view.

        Args:
            indication: Disease indication
            drug_names: Optional list of drug names

        Returns:
            DataFrame with safety comparison
        """
        if not self.connection:
            self.connect()

        try:
            query = """
                SELECT *
                FROM vw_safety_comparison
                WHERE indication = %s
            """
            params = [indication]

            if drug_names:
                placeholders = ','.join(['%s'] * len(drug_names))
                query += f" AND drug_name IN ({placeholders})"
                params.extend(drug_names)

            query += " ORDER BY drug_name, event_category, event_name"

            df = pd.read_sql_query(query, self.connection, params=params)
            return df

        except Exception as e:
            logger.error(f"Failed to get safety comparison: {e}")
            return pd.DataFrame()

    # =========================================================================
    # EXCEL EXPORT
    # =========================================================================

    def export_to_excel(
        self,
        indication: str,
        drug_names: List[str],
        output_path: str
    ):
        """
        Export comparative data to Excel with multiple sheets.

        Args:
            indication: Disease indication
            drug_names: List of drug names
            output_path: Path to save Excel file
        """
        try:
            # Get data from views
            baseline_df = self.get_baseline_comparison(indication, drug_names)
            efficacy_df = self.get_efficacy_comparison(indication, drug_names)
            safety_df = self.get_safety_comparison(indication, drug_names)

            # Write to Excel
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                baseline_df.to_excel(writer, sheet_name='Baseline', index=False)
                efficacy_df.to_excel(writer, sheet_name='Efficacy', index=False)
                safety_df.to_excel(writer, sheet_name='Safety', index=False)

            logger.info(f"Exported data to {output_path}")

        except Exception as e:
            logger.error(f"Failed to export to Excel: {e}")
            raise

    # =========================================================================
    # STANDARD ENDPOINTS
    # =========================================================================

    def get_standard_endpoints(self, indication: str) -> List[str]:
        """
        Get standard clinical endpoints for an indication.

        Args:
            indication: Disease indication

        Returns:
            List of standard endpoint names
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            query = """
                SELECT endpoint_name
                FROM standard_clinical_endpoints
                WHERE indication = %s
                ORDER BY endpoint_name
            """

            cursor.execute(query, (indication,))
            results = cursor.fetchall()
            cursor.close()

            return [row[0] for row in results]

        except Exception as e:
            logger.error(f"Failed to get standard endpoints: {e}")
            return []
