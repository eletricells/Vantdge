"""
Database Operations

CRUD operations for drugs with versioning, audit logging, and drug_key support.
"""

import json
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID
import psycopg2
from psycopg2.extras import RealDictCursor, Json

from src.drug_extraction_system.database.connection import DatabaseConnection
from src.drug_extraction_system.utils.drug_key_generator import DrugKeyGenerator

logger = logging.getLogger(__name__)


class DrugDatabaseOperations:
    """
    Database operations for drug extraction system.
    
    Provides CRUD with versioning, audit logging, and drug_key support.
    """

    def __init__(self, db: DatabaseConnection):
        """
        Initialize with database connection.

        Args:
            db: DatabaseConnection instance
        """
        self.db = db

    def upsert_drug(
        self,
        data: Dict[str, Any],
        batch_id: Optional[UUID] = None,
        force_update: bool = False
    ) -> Tuple[int, str]:
        """
        Insert new drug or update existing drug.

        Args:
            data: Drug data dictionary (must include 'generic_name')
            batch_id: Optional batch ID for audit logging
            force_update: If True, update even if drug exists and hasn't changed

        Returns:
            Tuple of (drug_id, drug_key)
        """
        self.db.ensure_connected()

        # Generate drug_key if not provided
        if "drug_key" not in data or not data["drug_key"]:
            data["drug_key"] = DrugKeyGenerator.generate(
                data["generic_name"],
                additional_data=data.get("cas_number")
            )

        try:
            with self.db.cursor() as cur:
                # Check if drug exists by drug_key or generic_name
                cur.execute("""
                    SELECT drug_id, drug_key, data_version, generic_name
                    FROM drugs 
                    WHERE drug_key = %(drug_key)s 
                       OR generic_name = %(generic_name)s
                    LIMIT 1
                """, data)

                existing = cur.fetchone()

                if existing:
                    drug_id = existing["drug_id"]
                    old_version = existing.get("data_version", 1) or 1

                    # Update existing drug
                    logger.info(f"Updating drug: {data['drug_key']} (ID: {drug_id})")

                    # Get old values for audit
                    cur.execute("SELECT * FROM drugs WHERE drug_id = %s", (drug_id,))
                    old_values = dict(cur.fetchone())

                    # Build update query dynamically based on provided fields
                    update_fields = []
                    update_values = {"drug_id": drug_id}

                    updatable_fields = [
                        "drug_key", "brand_name", "manufacturer", "development_code", "drug_type",
                        "mechanism_of_action", "target", "moa_category", "approval_status", "highest_phase",
                        "dailymed_setid", "first_approval_date", "rxcui", "chembl_id",
                        "inchi_key", "cas_number", "unii", "completeness_score",
                        "last_enrichment_at"
                    ]

                    for field in updatable_fields:
                        if field in data and data[field] is not None:
                            update_fields.append(f"{field} = %({field})s")
                            update_values[field] = data[field]

                    # Always increment version and update timestamp
                    update_fields.append("data_version = %(new_version)s")
                    update_fields.append("updated_at = CURRENT_TIMESTAMP")
                    update_values["new_version"] = old_version + 1

                    if update_fields:
                        query = f"""
                            UPDATE drugs SET {', '.join(update_fields)}
                            WHERE drug_id = %(drug_id)s
                        """
                        cur.execute(query, update_values)

                    # Log audit entry
                    self._log_audit(
                        cur, "drugs", drug_id, data["drug_key"],
                        "UPDATE", old_values, data, batch_id
                    )

                else:
                    # Insert new drug
                    logger.info(f"Inserting new drug: {data['drug_key']}")

                    cur.execute("""
                        INSERT INTO drugs (
                            drug_key, brand_name, generic_name, manufacturer, development_code,
                            drug_type, mechanism_of_action, target, moa_category, approval_status,
                            highest_phase, dailymed_setid, first_approval_date, rxcui, chembl_id,
                            inchi_key, cas_number, unii, completeness_score,
                            data_version
                        ) VALUES (
                            %(drug_key)s, %(brand_name)s, %(generic_name)s, %(manufacturer)s,
                            %(development_code)s, %(drug_type)s, %(mechanism_of_action)s, %(target)s,
                            %(moa_category)s, %(approval_status)s, %(highest_phase)s, %(dailymed_setid)s,
                            %(first_approval_date)s, %(rxcui)s, %(chembl_id)s, %(inchi_key)s,
                            %(cas_number)s, %(unii)s, %(completeness_score)s, 1
                        )
                        RETURNING drug_id
                    """, self._prepare_insert_data(data))

                    drug_id = cur.fetchone()["drug_id"]

                    # Log audit entry
                    self._log_audit(
                        cur, "drugs", drug_id, data["drug_key"],
                        "INSERT", None, data, batch_id
                    )

                # Store identifiers
                self._store_identifiers(cur, drug_id, data)

                self.db.commit()
                return (drug_id, data["drug_key"])

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to upsert drug: {e}")
            raise

    def _prepare_insert_data(self, data: Dict) -> Dict:
        """Prepare data dict with all fields (None for missing)."""
        fields = [
            "drug_key", "brand_name", "generic_name", "manufacturer", "development_code",
            "drug_type", "mechanism_of_action", "target", "moa_category", "approval_status",
            "highest_phase", "dailymed_setid", "first_approval_date", "rxcui", "chembl_id",
            "inchi_key", "cas_number", "unii", "completeness_score"
        ]
        return {f: data.get(f) for f in fields}

    def _log_audit(
        self, cur, table: str, record_id: int, drug_key: str,
        action: str, old_values: Optional[Dict], new_values: Dict,
        batch_id: Optional[UUID]
    ):
        """Log change to audit table."""
        # Determine changed fields
        changed_fields = []
        if old_values and action == "UPDATE":
            for key, new_val in new_values.items():
                if key in old_values and old_values[key] != new_val:
                    changed_fields.append(key)

        try:
            cur.execute("""
                INSERT INTO drug_audit_log (
                    table_name, record_id, drug_key, action,
                    old_values, new_values, changed_fields, batch_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                table, record_id, drug_key, action,
                Json(self._serialize_for_json(old_values)) if old_values else None,
                Json(self._serialize_for_json(new_values)),
                changed_fields or None,
                str(batch_id) if batch_id else None
            ))
        except Exception as e:
            # Don't fail the main operation if audit logging fails
            logger.warning(f"Failed to log audit entry: {e}")

    def _serialize_for_json(self, data: Dict) -> Dict:
        """Serialize data for JSON storage (handle dates, Decimals, etc.)."""
        if not data:
            return data
        result = {}
        for key, value in data.items():
            if isinstance(value, (datetime, date)):
                result[key] = value.isoformat()
            elif isinstance(value, Decimal):
                result[key] = float(value)
            elif hasattr(value, '__dict__'):
                result[key] = str(value)
            else:
                result[key] = value
        return result

    def _store_identifiers(self, cur, drug_id: int, data: Dict):
        """Store all known identifiers for cross-referencing."""
        identifiers = []

        # Map of data fields to identifier types
        id_mapping = [
            ("drug_key", "drug_key", "internal"),
            ("rxcui", "rxcui", "rxnorm"),
            ("chembl_id", "chembl_id", "chembl"),
            ("inchi_key", "inchi_key", "chemical"),
            ("cas_number", "cas_number", "cas"),
            ("unii", "unii", "fda"),
        ]

        for field, id_type, source in id_mapping:
            if data.get(field):
                identifiers.append((id_type, data[field], source))

        for id_type, id_value, source in identifiers:
            try:
                cur.execute("""
                    INSERT INTO drug_identifiers (drug_id, identifier_type, identifier_value, source)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (identifier_type, identifier_value)
                    DO UPDATE SET drug_id = EXCLUDED.drug_id
                """, (drug_id, id_type, id_value, source))
            except Exception as e:
                logger.warning(f"Failed to store identifier {id_type}={id_value}: {e}")

    def find_drug_by_identifier(self, identifier: str) -> Optional[Dict]:
        """
        Find drug by any known identifier.

        Args:
            identifier: Can be drug_key, RxCUI, ChEMBL ID, generic name, etc.

        Returns:
            Drug record or None
        """
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            # Try drug_key first (fastest)
            if identifier.startswith("DRG-"):
                cur.execute("SELECT * FROM drugs WHERE drug_key = %s", (identifier,))
                result = cur.fetchone()
                if result:
                    return dict(result)

            # Try other identifiers
            cur.execute("""
                SELECT d.*
                FROM drugs d
                LEFT JOIN drug_identifiers di ON d.drug_id = di.drug_id
                WHERE d.generic_name ILIKE %s
                   OR d.brand_name ILIKE %s
                   OR d.rxcui = %s
                   OR d.chembl_id = %s
                   OR di.identifier_value = %s
                LIMIT 1
            """, (identifier, identifier, identifier, identifier, identifier))

            result = cur.fetchone()
            return dict(result) if result else None

    def get_drug_with_details(self, drug_id: int) -> Optional[Dict]:
        """Get drug with all related data."""
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM drugs WHERE drug_id = %s", (drug_id,))
            drug = cur.fetchone()
            if not drug:
                return None

            drug = dict(drug)

            # Get indications (new schema - no join needed)
            cur.execute("""
                SELECT indication_id, disease_name, mesh_id, population, severity,
                       line_of_therapy, combination_therapy, approval_status, approval_date,
                       special_conditions, confidence_score
                FROM drug_indications
                WHERE drug_id = %s
            """, (drug_id,))
            drug["indications"] = [dict(r) for r in cur.fetchall()]

            # Get dosing
            cur.execute("""
                SELECT * FROM drug_dosing_regimens WHERE drug_id = %s
                ORDER BY dosing_id
            """, (drug_id,))
            drug["dosing_regimens"] = [dict(r) for r in cur.fetchall()]

            # Get identifiers
            cur.execute("""
                SELECT identifier_type, identifier_value, source
                FROM drug_identifiers WHERE drug_id = %s
            """, (drug_id,))
            drug["identifiers"] = {r["identifier_type"]: r["identifier_value"] for r in cur.fetchall()}

            # Get efficacy data
            cur.execute("""
                SELECT * FROM drug_efficacy_data WHERE drug_id = %s
                ORDER BY trial_name, endpoint_name
            """, (drug_id,))
            drug["efficacy_data"] = [dict(r) for r in cur.fetchall()]

            # Get safety data
            cur.execute("""
                SELECT * FROM drug_safety_data WHERE drug_id = %s
                ORDER BY drug_arm_rate DESC NULLS LAST
            """, (drug_id,))
            drug["safety_data"] = [dict(r) for r in cur.fetchall()]

            return drug

    def log_process_start(self, batch_id: UUID, csv_file: str, total_drugs: int) -> int:
        """Log batch processing start."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO drug_process_log (batch_id, csv_file, total_drugs, status)
                VALUES (%s, %s, %s, 'in_progress')
                RETURNING process_id
            """, (str(batch_id), csv_file, total_drugs))
            self.db.commit()
            return cur.fetchone()["process_id"]

    def log_process_end(
        self, batch_id: UUID, successful: int, partial: int,
        failed: int, error_summary: Optional[Dict] = None
    ):
        """Log batch processing completion."""
        self.db.ensure_connected()
        with self.db.cursor() as cur:
            cur.execute("""
                UPDATE drug_process_log
                SET status = 'completed', successful = %s, partial = %s,
                    failed = %s, completed_at = CURRENT_TIMESTAMP,
                    error_summary = %s
                WHERE batch_id = %s
            """, (successful, partial, failed, Json(error_summary) if error_summary else None, str(batch_id)))
            self.db.commit()

    def get_development_code(self, drug_name: str) -> Optional[str]:
        """
        Get development code for a drug by name.

        Args:
            drug_name: Generic or brand name of the drug

        Returns:
            Development code (e.g., "LNP023") or None if not set
        """
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("""
                SELECT development_code
                FROM drugs
                WHERE (generic_name ILIKE %s OR brand_name ILIKE %s)
                  AND development_code IS NOT NULL
                LIMIT 1
            """, (drug_name, drug_name))

            result = cur.fetchone()
            return result["development_code"] if result else None

    def set_development_code(self, drug_name: str, development_code: str) -> bool:
        """
        Set development code for a drug.

        Args:
            drug_name: Generic or brand name of the drug
            development_code: Development code to set (e.g., "LNP023")

        Returns:
            True if updated successfully, False if drug not found
        """
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("""
                UPDATE drugs
                SET development_code = %s, updated_at = CURRENT_TIMESTAMP
                WHERE generic_name ILIKE %s OR brand_name ILIKE %s
                RETURNING drug_id
            """, (development_code, drug_name, drug_name))

            result = cur.fetchone()
            self.db.commit()
            return result is not None

    def store_efficacy_data(self, drug_id: int, efficacy_results: List[Any]) -> int:
        """
        Store efficacy data for a drug.

        Args:
            drug_id: Drug ID
            efficacy_results: List of EfficacyResult dataclasses or dicts

        Returns:
            Number of records inserted
        """
        self.db.ensure_connected()
        inserted = 0

        with self.db.cursor() as cur:
            for result in efficacy_results:
                # Convert dataclass to dict if needed
                if hasattr(result, '__dict__') and hasattr(result, 'trial_name'):
                    data = {
                        'trial_name': result.trial_name,
                        'endpoint_name': result.endpoint_name,
                        'endpoint_type': result.endpoint_type,
                        'drug_arm_name': result.drug_arm_name,
                        'drug_arm_n': result.drug_arm_n,
                        'drug_arm_result': result.drug_arm_result,
                        'drug_arm_result_unit': result.drug_arm_result_unit,
                        'comparator_arm_name': result.comparator_arm_name,
                        'comparator_arm_n': result.comparator_arm_n,
                        'comparator_arm_result': result.comparator_arm_result,
                        'p_value': result.p_value,
                        'confidence_interval': result.confidence_interval,
                        'timepoint': result.timepoint,
                        'trial_phase': result.trial_phase,
                        'nct_id': result.nct_id,
                        'population': result.population,
                        'indication_name': result.indication_name,
                        'confidence_score': result.confidence_score,
                    }
                else:
                    data = result

                try:
                    cur.execute("""
                        INSERT INTO drug_efficacy_data (
                            drug_id, trial_name, endpoint_name, endpoint_type,
                            drug_arm_name, drug_arm_n, drug_arm_result, drug_arm_result_unit,
                            comparator_arm_name, comparator_arm_n, comparator_arm_result,
                            p_value, confidence_interval, timepoint, trial_phase, nct_id,
                            population, indication_name, confidence_score, data_source
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'openfda'
                        )
                    """, (
                        drug_id,
                        data.get('trial_name'),
                        data.get('endpoint_name'),
                        data.get('endpoint_type'),
                        data.get('drug_arm_name'),
                        data.get('drug_arm_n'),
                        data.get('drug_arm_result'),
                        data.get('drug_arm_result_unit'),
                        data.get('comparator_arm_name'),
                        data.get('comparator_arm_n'),
                        data.get('comparator_arm_result'),
                        data.get('p_value'),
                        data.get('confidence_interval'),
                        data.get('timepoint'),
                        data.get('trial_phase'),
                        data.get('nct_id'),
                        data.get('population'),
                        data.get('indication_name'),
                        data.get('confidence_score', 0.85),
                    ))
                    inserted += 1
                except Exception as e:
                    logger.warning(f"Failed to insert efficacy record: {e}")

            self.db.commit()

        logger.info(f"Stored {inserted} efficacy records for drug_id={drug_id}")
        return inserted

    def store_safety_data(self, drug_id: int, safety_results: List[Any]) -> int:
        """
        Store safety data for a drug.

        Args:
            drug_id: Drug ID
            safety_results: List of SafetyResult dataclasses or dicts

        Returns:
            Number of records inserted
        """
        self.db.ensure_connected()
        inserted = 0

        with self.db.cursor() as cur:
            for result in safety_results:
                # Convert dataclass to dict if needed
                if hasattr(result, '__dict__') and hasattr(result, 'adverse_event'):
                    data = {
                        'adverse_event': result.adverse_event,
                        'system_organ_class': result.system_organ_class,
                        'severity': result.severity,
                        'is_serious': result.is_serious,
                        'drug_arm_name': result.drug_arm_name,
                        'drug_arm_n': result.drug_arm_n,
                        'drug_arm_count': result.drug_arm_count,
                        'drug_arm_rate': result.drug_arm_rate,
                        'drug_arm_rate_unit': result.drug_arm_rate_unit,
                        'comparator_arm_name': result.comparator_arm_name,
                        'comparator_arm_n': result.comparator_arm_n,
                        'comparator_arm_count': result.comparator_arm_count,
                        'comparator_arm_rate': result.comparator_arm_rate,
                        'timepoint': result.timepoint,
                        'trial_context': result.trial_context,
                        'is_boxed_warning': result.is_boxed_warning,
                        'warning_category': result.warning_category,
                        'population': result.population,
                        'indication_name': result.indication_name,
                        'confidence_score': result.confidence_score,
                    }
                else:
                    data = result

                try:
                    cur.execute("""
                        INSERT INTO drug_safety_data (
                            drug_id, adverse_event, system_organ_class, severity, is_serious,
                            drug_arm_name, drug_arm_n, drug_arm_count, drug_arm_rate, drug_arm_rate_unit,
                            comparator_arm_name, comparator_arm_n, comparator_arm_count, comparator_arm_rate,
                            timepoint, trial_context, is_boxed_warning, warning_category,
                            population, indication_name, confidence_score, data_source
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'openfda'
                        )
                    """, (
                        drug_id,
                        data.get('adverse_event'),
                        data.get('system_organ_class'),
                        data.get('severity'),
                        data.get('is_serious', False),
                        data.get('drug_arm_name'),
                        data.get('drug_arm_n'),
                        data.get('drug_arm_count'),
                        data.get('drug_arm_rate'),
                        data.get('drug_arm_rate_unit', '%'),
                        data.get('comparator_arm_name'),
                        data.get('comparator_arm_n'),
                        data.get('comparator_arm_count'),
                        data.get('comparator_arm_rate'),
                        data.get('timepoint'),
                        data.get('trial_context'),
                        data.get('is_boxed_warning', False),
                        data.get('warning_category'),
                        data.get('population'),
                        data.get('indication_name'),
                        data.get('confidence_score', 0.85),
                    ))
                    inserted += 1
                except Exception as e:
                    logger.warning(f"Failed to insert safety record: {e}")

            self.db.commit()

        logger.info(f"Stored {inserted} safety records for drug_id={drug_id}")
        return inserted

    def clear_efficacy_safety_data(self, drug_id: int) -> None:
        """Clear existing efficacy and safety data for a drug before re-extraction."""
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("DELETE FROM drug_efficacy_data WHERE drug_id = %s", (drug_id,))
            cur.execute("DELETE FROM drug_safety_data WHERE drug_id = %s", (drug_id,))
            self.db.commit()

        logger.info(f"Cleared efficacy/safety data for drug_id={drug_id}")

