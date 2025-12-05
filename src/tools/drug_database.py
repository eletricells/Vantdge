"""
Drug Database Interface

Service class for interacting with the drug database (drugs, indications, dosing, etc.)
"""
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime

from src.utils.drug_standardization import (
    standardize_frequency,
    standardize_route,
    standardize_dose_unit,
    standardize_drug_type
)

logger = logging.getLogger(__name__)


class DrugDatabase:
    """
    Database interface for drug information.

    Handles CRUD operations for:
    - Drugs (approved and investigational)
    - Diseases (indications)
    - Drug-disease relationships
    - Dosing regimens
    - Formulations
    - Label versions
    - Metadata
    """

    def __init__(self, database_url: str):
        """
        Initialize drug database connection.

        Args:
            database_url: PostgreSQL connection string
        """
        self.database_url = database_url
        self.connection = None

    @property
    def conn(self):
        """Alias for connection (used by version manager)."""
        return self.connection

    def connect(self):
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(self.database_url)
            logger.info("Connected to drug database")
        except Exception as e:
            logger.error(f"Failed to connect to drug database: {e}")
            raise

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Closed drug database connection")

    # =========================================================================
    # DISEASE METHODS
    # =========================================================================

    def add_disease(
        self,
        disease_name: str,
        aliases: Optional[List[str]] = None,
        icd10_codes: Optional[List[str]] = None,
        therapeutic_area: Optional[str] = None
    ) -> int:
        """
        Add a disease to the database (or get existing ID).

        Args:
            disease_name: Standardized disease name
            aliases: Alternative names/spellings
            icd10_codes: ICD-10 diagnostic codes
            therapeutic_area: Therapeutic area category

        Returns:
            disease_id
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            # Check if disease already exists
            cursor.execute(
                "SELECT disease_id FROM diseases WHERE disease_name_standard = %s",
                (disease_name,)
            )
            result = cursor.fetchone()

            if result:
                disease_id = result[0]
                logger.debug(f"Disease '{disease_name}' already exists (ID: {disease_id})")
                cursor.close()
                return disease_id

            # Insert new disease
            query = """
                INSERT INTO diseases (disease_name_standard, disease_aliases, icd10_codes, therapeutic_area)
                VALUES (%s, %s, %s, %s)
                RETURNING disease_id
            """

            cursor.execute(
                query,
                (disease_name, Json(aliases or []), Json(icd10_codes or []), therapeutic_area)
            )

            disease_id = cursor.fetchone()[0]
            self.connection.commit()
            cursor.close()

            logger.info(f"Added disease '{disease_name}' (ID: {disease_id})")
            return disease_id

        except Exception as e:
            logger.error(f"Failed to add disease: {e}")
            if self.connection:
                self.connection.rollback()
            raise

    def get_disease_by_name(self, disease_name: str) -> Optional[Dict]:
        """
        Get disease by name (exact or alias match).

        Args:
            disease_name: Disease name to search for

        Returns:
            Disease dictionary or None
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)

            # Try exact match first
            cursor.execute(
                "SELECT * FROM diseases WHERE disease_name_standard = %s",
                (disease_name,)
            )
            result = cursor.fetchone()

            if result:
                cursor.close()
                return dict(result)

            # Try alias match
            cursor.execute(
                """
                SELECT * FROM diseases
                WHERE disease_aliases @> %s::jsonb
                """,
                (Json([disease_name]),)
            )
            result = cursor.fetchone()
            cursor.close()

            return dict(result) if result else None

        except Exception as e:
            logger.error(f"Failed to get disease: {e}")
            return None

    # =========================================================================
    # DRUG METHODS
    # =========================================================================

    def add_drug(
        self,
        generic_name: str,
        brand_name: Optional[str] = None,
        manufacturer: Optional[str] = None,
        drug_type: Optional[str] = None,
        mechanism: Optional[str] = None,
        approval_status: str = "investigational",
        highest_phase: Optional[str] = None,
        dailymed_setid: Optional[str] = None,
        first_approval_date: Optional[str] = None,
        is_combination: bool = False,
        combination_components: Optional[List[int]] = None,
        overwrite: bool = False
    ) -> int:
        """
        Add a drug to the database (or update existing).

        Args:
            generic_name: Generic/INN name (required)
            brand_name: Brand name
            manufacturer: Manufacturer name ("generic" for generics)
            drug_type: Drug type (will be standardized)
            mechanism: Mechanism of action
            approval_status: "approved", "investigational", "discontinued"
            highest_phase: Highest development phase
            dailymed_setid: DailyMed Set ID for approved drugs
            is_combination: True if combination therapy
            combination_components: List of drug_ids for combination
            overwrite: If True, delete existing drug data and recreate

        Returns:
            drug_id
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            # Standardize drug type
            if drug_type:
                drug_type = standardize_drug_type(drug_type) or drug_type

            # Check if drug already exists (by brand_name alone for overwrite mode)
            existing_drug_id = None
            if brand_name:
                if overwrite:
                    # When overwriting, check by brand_name only
                    cursor.execute(
                        "SELECT drug_id FROM drugs WHERE brand_name = %s",
                        (brand_name,)
                    )
                    result = cursor.fetchone()
                    if result:
                        existing_drug_id = result[0]
                        logger.info(f"Drug '{brand_name}' exists (ID: {existing_drug_id}) - will overwrite")
                else:
                    # When not overwriting, check by brand + manufacturer
                    if manufacturer:
                        cursor.execute(
                            "SELECT drug_id FROM drugs WHERE brand_name = %s AND manufacturer = %s",
                            (brand_name, manufacturer)
                        )
                        result = cursor.fetchone()

                        if result:
                            drug_id = result[0]
                            logger.debug(f"Drug '{brand_name}' ({manufacturer}) already exists (ID: {drug_id})")
                            cursor.close()
                            return drug_id

            # If overwriting and drug exists, UPDATE drug + delete related data
            if overwrite and existing_drug_id:
                logger.info(f"Overwriting existing drug ID {existing_drug_id} (preserving version history)")

                # Delete related data (but NOT the drug record itself)
                # This preserves drug_id and version history
                cursor.execute("DELETE FROM drug_metadata WHERE drug_id = %s", (existing_drug_id,))
                cursor.execute("DELETE FROM drug_dosing_regimens WHERE drug_id = %s", (existing_drug_id,))
                cursor.execute("DELETE FROM drug_indications WHERE drug_id = %s", (existing_drug_id,))
                cursor.execute("DELETE FROM drug_formulations WHERE drug_id = %s", (existing_drug_id,))

                # UPDATE the drug record (preserves drug_id and version history)
                update_query = """
                    UPDATE drugs SET
                        brand_name = %s,
                        generic_name = %s,
                        manufacturer = %s,
                        drug_type = %s,
                        mechanism_of_action = %s,
                        approval_status = %s,
                        highest_phase = %s,
                        dailymed_setid = %s,
                        first_approval_date = %s,
                        is_combination = %s,
                        combination_components = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE drug_id = %s
                """

                cursor.execute(
                    update_query,
                    (
                        brand_name, generic_name, manufacturer, drug_type,
                        mechanism, approval_status, highest_phase,
                        dailymed_setid, first_approval_date, is_combination, combination_components,
                        existing_drug_id
                    )
                )

                drug_id = existing_drug_id
                self.connection.commit()
                cursor.close()

                logger.info(f"Overwrote drug '{brand_name or generic_name}' (ID: {drug_id}, version history preserved)")
                return drug_id

            # Insert new drug (when not overwriting or drug doesn't exist)
            query = """
                INSERT INTO drugs (
                    brand_name, generic_name, manufacturer, drug_type,
                    mechanism_of_action, approval_status, highest_phase,
                    dailymed_setid, first_approval_date, is_combination, combination_components
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING drug_id
            """

            cursor.execute(
                query,
                (
                    brand_name, generic_name, manufacturer, drug_type,
                    mechanism, approval_status, highest_phase,
                    dailymed_setid, first_approval_date, is_combination, combination_components
                )
            )

            drug_id = cursor.fetchone()[0]
            self.connection.commit()
            cursor.close()

            logger.info(f"Added drug '{brand_name or generic_name}' (ID: {drug_id})")
            return drug_id

        except Exception as e:
            logger.error(f"Failed to add drug: {e}")
            if self.connection:
                self.connection.rollback()
            raise

    def get_drug(self, drug_id: int) -> Optional[Dict]:
        """Get drug by ID."""
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM drugs WHERE drug_id = %s", (drug_id,))
            result = cursor.fetchone()
            cursor.close()

            return dict(result) if result else None

        except Exception as e:
            logger.error(f"Failed to get drug: {e}")
            return None

    def search_drugs(
        self,
        query: str,
        approval_status: Optional[str] = None,
        manufacturer: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """
        Search drugs by name (brand or generic).

        Args:
            query: Search term (matches brand or generic name)
            approval_status: Filter by approval status
            manufacturer: Filter by manufacturer
            limit: Max results

        Returns:
            List of drug dictionaries
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)

            where_clauses = ["(brand_name ILIKE %s OR generic_name ILIKE %s)"]
            params = [f"%{query}%", f"%{query}%"]

            if approval_status:
                where_clauses.append("approval_status = %s")
                params.append(approval_status)

            if manufacturer:
                where_clauses.append("manufacturer = %s")
                params.append(manufacturer)

            params.append(limit)

            query_sql = f"""
                SELECT * FROM drugs
                WHERE {' AND '.join(where_clauses)}
                LIMIT %s
            """

            cursor.execute(query_sql, params)
            results = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to search drugs: {e}")
            return []

    # =========================================================================
    # INDICATION METHODS
    # =========================================================================

    def add_indication(
        self,
        drug_id: int,
        disease_id: int,
        indication_raw: Optional[str] = None,
        approval_status: str = "investigational",
        approval_date: Optional[str] = None,
        approval_year: Optional[int] = None,
        approval_source: Optional[str] = None,
        line_of_therapy: str = "any",
        population_restrictions: Optional[str] = None,
        data_source: str = "Manual",
        severity_mild: bool = False,
        severity_moderate: bool = False,
        severity_severe: bool = False
    ) -> int:
        """
        Add drug-disease indication relationship.

        Args:
            drug_id: Drug ID
            disease_id: Disease ID
            indication_raw: Raw indication text from source
            approval_status: Status of this indication
            approval_date: Date indication was approved
            approval_year: Year indication was approved (for quick filtering)
            approval_source: Source of approval date ("Drugs.com", "AI Agent", "DailyMed", etc.)
            line_of_therapy: Treatment line
            population_restrictions: Population restrictions
            data_source: Data source
            severity_mild: TRUE if approved for mild disease
            severity_moderate: TRUE if approved for moderate disease
            severity_severe: TRUE if approved for severe disease

        Returns:
            indication_id
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            query = """
                INSERT INTO drug_indications (
                    drug_id, disease_id, indication_raw, approval_status,
                    approval_date, approval_year, approval_source,
                    line_of_therapy, population_restrictions, data_source,
                    severity_mild, severity_moderate, severity_severe
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (drug_id, disease_id, line_of_therapy)
                DO UPDATE SET
                    indication_raw = EXCLUDED.indication_raw,
                    approval_status = EXCLUDED.approval_status,
                    approval_date = EXCLUDED.approval_date,
                    approval_year = EXCLUDED.approval_year,
                    approval_source = EXCLUDED.approval_source,
                    population_restrictions = EXCLUDED.population_restrictions,
                    data_source = EXCLUDED.data_source,
                    severity_mild = EXCLUDED.severity_mild,
                    severity_moderate = EXCLUDED.severity_moderate,
                    severity_severe = EXCLUDED.severity_severe,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING indication_id
            """

            cursor.execute(
                query,
                (
                    drug_id, disease_id, indication_raw, approval_status,
                    approval_date, approval_year, approval_source,
                    line_of_therapy, population_restrictions, data_source,
                    severity_mild, severity_moderate, severity_severe
                )
            )

            indication_id = cursor.fetchone()[0]
            self.connection.commit()
            cursor.close()

            logger.info(f"Added indication for drug {drug_id} + disease {disease_id}")
            return indication_id

        except Exception as e:
            logger.error(f"Failed to add indication: {e}")
            if self.connection:
                self.connection.rollback()
            raise

    def get_drug_indications(self, drug_id: int) -> List[Dict]:
        """Get all indications for a drug."""
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)

            query = """
                SELECT
                    di.*,
                    d.disease_name_standard,
                    d.therapeutic_area
                FROM drug_indications di
                JOIN diseases d ON di.disease_id = d.disease_id
                WHERE di.drug_id = %s
                ORDER BY di.approval_date DESC
            """

            cursor.execute(query, (drug_id,))
            results = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get drug indications: {e}")
            return []

    # =========================================================================
    # DOSING METHODS
    # =========================================================================

    def add_dosing_regimen(
        self,
        drug_id: int,
        indication_id: Optional[int] = None,
        regimen_phase: str = "single",
        dose_amount: Optional[float] = None,
        dose_unit: Optional[str] = None,
        frequency_raw: Optional[str] = None,
        route_raw: Optional[str] = None,
        duration_weeks: Optional[int] = None,
        weight_based: bool = False,
        sequence_order: int = 1,
        dosing_notes: Optional[str] = None,
        data_source: str = "Manual"
    ) -> int:
        """
        Add dosing regimen for a drug.

        Args:
            drug_id: Drug ID
            indication_id: Indication ID (optional, for indication-specific dosing)
            regimen_phase: Phase of dosing (loading, maintenance, single, induction)
            dose_amount: Dose amount (numeric)
            dose_unit: Dose unit (will be standardized)
            frequency_raw: Raw frequency text (will be standardized)
            route_raw: Raw route text (will be standardized)
            duration_weeks: Duration in weeks (for loading/induction)
            weight_based: True if dose is weight-based
            sequence_order: Order in sequence (1 for loading, 2 for maintenance)
            dosing_notes: Additional notes
            data_source: Data source

        Returns:
            dosing_id
        """
        if not self.connection:
            self.connect()

        try:
            # Standardize fields
            frequency_std, _ = standardize_frequency(frequency_raw) if frequency_raw else (None, "")
            route_std, _ = standardize_route(route_raw) if route_raw else (None, "")
            dose_unit_std = standardize_dose_unit(dose_unit) if dose_unit else None

            cursor = self.connection.cursor()

            query = """
                INSERT INTO drug_dosing_regimens (
                    drug_id, indication_id, regimen_phase, dose_amount, dose_unit,
                    frequency_standard, frequency_raw, route_standard, route_raw,
                    duration_weeks, weight_based, sequence_order, dosing_notes, data_source
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING dosing_id
            """

            cursor.execute(
                query,
                (
                    drug_id, indication_id, regimen_phase, dose_amount, dose_unit_std,
                    frequency_std, frequency_raw, route_std, route_raw,
                    duration_weeks, weight_based, sequence_order, dosing_notes, data_source
                )
            )

            dosing_id = cursor.fetchone()[0]
            self.connection.commit()
            cursor.close()

            logger.info(f"Added dosing regimen for drug {drug_id}")
            return dosing_id

        except Exception as e:
            logger.error(f"Failed to add dosing regimen: {e}")
            if self.connection:
                self.connection.rollback()
            raise

    def get_dosing_regimens(
        self,
        drug_id: int,
        indication_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Get dosing regimens for a drug.

        Args:
            drug_id: Drug ID
            indication_id: Filter by indication (optional)

        Returns:
            List of dosing regimen dictionaries (includes disease_name_standard if linked)
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)

            if indication_id:
                query = """
                    SELECT
                        dr.*,
                        d.disease_name_standard
                    FROM drug_dosing_regimens dr
                    LEFT JOIN drug_indications di ON dr.indication_id = di.indication_id
                    LEFT JOIN diseases d ON di.disease_id = d.disease_id
                    WHERE dr.drug_id = %s AND dr.indication_id = %s
                    ORDER BY dr.sequence_order
                """
                cursor.execute(query, (drug_id, indication_id))
            else:
                query = """
                    SELECT
                        dr.*,
                        d.disease_name_standard
                    FROM drug_dosing_regimens dr
                    LEFT JOIN drug_indications di ON dr.indication_id = di.indication_id
                    LEFT JOIN diseases d ON di.disease_id = d.disease_id
                    WHERE dr.drug_id = %s
                    ORDER BY dr.sequence_order
                """
                cursor.execute(query, (drug_id,))

            results = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get dosing regimens: {e}")
            return []

    # =========================================================================
    # METADATA METHODS
    # =========================================================================

    def add_drug_metadata(
        self,
        drug_id: int,
        orphan_designation: bool = False,
        breakthrough_therapy: bool = False,
        fast_track: bool = False,
        has_black_box_warning: bool = False,
        safety_notes: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        Add or update drug metadata.

        Args:
            drug_id: Drug ID
            orphan_designation: Has orphan designation
            breakthrough_therapy: Has breakthrough therapy designation
            fast_track: Has fast track designation
            has_black_box_warning: Has black box warning
            safety_notes: Safety notes
            **kwargs: Additional fields

        Returns:
            True if successful
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            query = """
                INSERT INTO drug_metadata (
                    drug_id, orphan_designation, breakthrough_therapy, fast_track,
                    has_black_box_warning, safety_notes
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (drug_id)
                DO UPDATE SET
                    orphan_designation = EXCLUDED.orphan_designation,
                    breakthrough_therapy = EXCLUDED.breakthrough_therapy,
                    fast_track = EXCLUDED.fast_track,
                    has_black_box_warning = EXCLUDED.has_black_box_warning,
                    safety_notes = EXCLUDED.safety_notes,
                    updated_at = CURRENT_TIMESTAMP
            """

            cursor.execute(
                query,
                (drug_id, orphan_designation, breakthrough_therapy, fast_track,
                 has_black_box_warning, safety_notes)
            )

            self.connection.commit()
            cursor.close()

            logger.info(f"Added/updated metadata for drug {drug_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to add drug metadata: {e}")
            if self.connection:
                self.connection.rollback()
            return False

    # =========================================================================
    # QUERY METHODS
    # =========================================================================

    def get_drug_overview(self, drug_id: int) -> Optional[Dict]:
        """
        Get complete drug overview (drug + metadata + indications).

        Args:
            drug_id: Drug ID

        Returns:
            Comprehensive drug dictionary
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)

            query = """
                SELECT * FROM vw_drug_overview
                WHERE drug_id = %s
            """

            cursor.execute(query, (drug_id,))
            result = cursor.fetchone()
            cursor.close()

            if not result:
                return None

            overview = dict(result)

            # Add indications
            overview["indications"] = self.get_drug_indications(drug_id)

            # Add dosing regimens
            overview["dosing_regimens"] = self.get_dosing_regimens(drug_id)

            return overview

        except Exception as e:
            logger.error(f"Failed to get drug overview: {e}")
            return None

    def get_drugs_by_disease(self, disease_id: int) -> List[Dict]:
        """Get all drugs for a specific disease/indication."""
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)

            query = """
                SELECT
                    d.*,
                    di.approval_status as indication_status,
                    di.line_of_therapy
                FROM drugs d
                JOIN drug_indications di ON d.drug_id = di.drug_id
                WHERE di.disease_id = %s
                ORDER BY d.approval_status, d.brand_name
            """

            cursor.execute(query, (disease_id,))
            results = cursor.fetchall()
            cursor.close()

            return [dict(row) for row in results]

        except Exception as e:
            logger.error(f"Failed to get drugs by disease: {e}")
            return []

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
