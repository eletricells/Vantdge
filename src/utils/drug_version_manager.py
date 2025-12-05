"""
Drug Version Management and Comparison Utilities

Handles versioning, change tracking, and visual diff generation for drug data.
"""
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime, date
from decimal import Decimal
import json


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime, date, and Decimal objects."""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class DrugVersionManager:
    """Manages drug versions and tracks changes."""

    @staticmethod
    def compare_versions(old_data: Dict, new_data: Dict) -> Dict[str, Any]:
        """
        Compare two drug versions and identify changes.

        Args:
            old_data: Previous version drug data
            new_data: New version drug data

        Returns:
            Dictionary with:
                - changed_fields: List of field names that changed
                - added_fields: Fields that were added
                - removed_fields: Fields that were removed
                - modified_fields: Fields that were modified with old/new values
        """
        changed_fields = []
        added_fields = []
        removed_fields = []
        modified_fields = {}

        # Get all unique keys
        all_keys = set(old_data.keys()) | set(new_data.keys())

        for key in all_keys:
            old_value = old_data.get(key)
            new_value = new_data.get(key)

            # Field was added
            if key not in old_data and key in new_data:
                added_fields.append(key)
                changed_fields.append(key)

            # Field was removed
            elif key in old_data and key not in new_data:
                removed_fields.append(key)
                changed_fields.append(key)

            # Field was modified
            elif old_value != new_value:
                changed_fields.append(key)
                modified_fields[key] = {
                    'old': old_value,
                    'new': new_value
                }

        return {
            'changed_fields': changed_fields,
            'added_fields': added_fields,
            'removed_fields': removed_fields,
            'modified_fields': modified_fields,
            'has_changes': len(changed_fields) > 0
        }

    @staticmethod
    def format_change_summary(changes: Dict[str, Any]) -> str:
        """
        Format changes into human-readable summary.

        Args:
            changes: Output from compare_versions()

        Returns:
            Formatted string summary
        """
        if not changes['has_changes']:
            return "No changes detected"

        summary_parts = []

        if changes['added_fields']:
            summary_parts.append(f"Added: {', '.join(changes['added_fields'])}")

        if changes['removed_fields']:
            summary_parts.append(f"Removed: {', '.join(changes['removed_fields'])}")

        if changes['modified_fields']:
            modified_list = [
                f"{field} ({_format_value_change(old_val, new_val)})"
                for field, vals in changes['modified_fields'].items()
                for old_val, new_val in [(vals['old'], vals['new'])]
            ]
            summary_parts.append(f"Modified: {', '.join(modified_list)}")

        return " | ".join(summary_parts)

    @staticmethod
    def get_field_change_type(field_name: str, changes: Dict[str, Any]) -> Optional[str]:
        """
        Get the type of change for a specific field.

        Args:
            field_name: Name of the field
            changes: Output from compare_versions()

        Returns:
            'added', 'removed', 'modified', or None
        """
        if field_name in changes['added_fields']:
            return 'added'
        elif field_name in changes['removed_fields']:
            return 'removed'
        elif field_name in changes['modified_fields']:
            return 'modified'
        return None

    @staticmethod
    def get_visual_indicator(change_type: Optional[str]) -> str:
        """
        Get emoji/symbol for change type.

        Args:
            change_type: 'added', 'removed', 'modified', or None

        Returns:
            Visual indicator string
        """
        indicators = {
            'added': '🆕',
            'removed': '❌',
            'modified': '✏️',
            None: ''
        }
        return indicators.get(change_type, '')

    @staticmethod
    def get_streamlit_color(change_type: Optional[str]) -> str:
        """
        Get Streamlit color for change type.

        Args:
            change_type: 'added', 'removed', 'modified', or None

        Returns:
            Color name for Streamlit styling
        """
        colors = {
            'added': 'green',
            'removed': 'red',
            'modified': 'orange',
            None: 'gray'
        }
        return colors.get(change_type, 'gray')


def _format_value_change(old_value: Any, new_value: Any) -> str:
    """Format old/new value change for display."""
    def format_val(val):
        if val is None:
            return "null"
        elif isinstance(val, (list, dict)):
            return f"{type(val).__name__}[{len(val)}]"
        elif isinstance(val, str) and len(val) > 30:
            return f"{val[:30]}..."
        return str(val)

    return f"{format_val(old_value)} → {format_val(new_value)}"


class DrugVersionHistory:
    """Manages version history for a drug."""

    def __init__(self, database):
        """
        Initialize version history manager.

        Args:
            database: DrugDatabase instance
        """
        self.db = database

    def save_version(
        self,
        drug_id: int,
        drug_data: Dict,
        created_by: str = 'system'
    ) -> Tuple[int, Optional[Dict]]:
        """
        Save a new version of a drug.

        Automatically rotates old versions if already have 3.

        Args:
            drug_id: Drug ID
            drug_data: Full drug data dictionary
            created_by: Username or system identifier

        Returns:
            Tuple of (version_number, deleted_version_info)
            - version_number: The version number assigned (1-3)
            - deleted_version_info: Info about deleted version if rotation occurred, else None
        """
        cursor = self.db.conn.cursor()

        try:
            # Get current version count
            cursor.execute(
                "SELECT get_drug_version_count(%s)",
                (drug_id,)
            )
            version_count = cursor.fetchone()[0]

            # Get latest version for comparison
            cursor.execute("""
                SELECT version_number, drug_data
                FROM drug_versions
                WHERE drug_id = %s
                ORDER BY version_number DESC
                LIMIT 1
            """, (drug_id,))

            latest_version = cursor.fetchone()
            changed_fields = []

            if latest_version:
                # Compare with previous version
                _, old_data_json = latest_version
                old_data = json.loads(old_data_json) if isinstance(old_data_json, str) else old_data_json

                changes = DrugVersionManager.compare_versions(old_data, drug_data)
                changed_fields = changes['changed_fields']

            deleted_version_info = None

            # If already have 3 versions, rotate
            if version_count >= 3:
                cursor.execute(
                    "SELECT * FROM rotate_drug_versions(%s)",
                    (drug_id,)
                )
                deleted_info = cursor.fetchone()
                if deleted_info:
                    deleted_version_info = {
                        'version_number': deleted_info[0],
                        'created_at': deleted_info[1]
                    }

                # After rotation, insert as version 3
                new_version_number = 3
            else:
                # Insert as next version
                new_version_number = version_count + 1

            # Insert new version (use custom encoder for date/datetime objects)
            cursor.execute("""
                INSERT INTO drug_versions (drug_id, version_number, drug_data, changed_fields, created_by)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (drug_id, version_number)
                DO UPDATE SET
                    drug_data = EXCLUDED.drug_data,
                    changed_fields = EXCLUDED.changed_fields,
                    created_at = CURRENT_TIMESTAMP,
                    created_by = EXCLUDED.created_by
            """, (drug_id, new_version_number, json.dumps(drug_data, cls=DateTimeEncoder), changed_fields, created_by))

            self.db.conn.commit()

            return new_version_number, deleted_version_info

        except Exception as e:
            self.db.conn.rollback()
            raise Exception(f"Failed to save drug version: {e}")

    def get_versions(self, drug_id: int) -> List[Dict]:
        """
        Get all versions for a drug.

        Args:
            drug_id: Drug ID

        Returns:
            List of version dictionaries, ordered by version_number (oldest to newest)
        """
        cursor = self.db.conn.cursor()

        cursor.execute("""
            SELECT
                version_id,
                version_number,
                drug_data,
                changed_fields,
                created_at,
                created_by
            FROM drug_versions
            WHERE drug_id = %s
            ORDER BY version_number ASC
        """, (drug_id,))

        versions = []
        for row in cursor.fetchall():
            version_id, version_number, drug_data, changed_fields, created_at, created_by = row

            versions.append({
                'version_id': version_id,
                'version_number': version_number,
                'drug_data': drug_data,
                'changed_fields': changed_fields or [],
                'created_at': created_at,
                'created_by': created_by
            })

        return versions

    def get_version_comparison(
        self,
        drug_id: int,
        version_number: int
    ) -> Optional[Dict]:
        """
        Get version with comparison to previous version.

        Args:
            drug_id: Drug ID
            version_number: Version number to get

        Returns:
            Dictionary with version data and comparison to previous version
        """
        versions = self.get_versions(drug_id)

        if not versions:
            return None

        # Find requested version
        current_version = next(
            (v for v in versions if v['version_number'] == version_number),
            None
        )

        if not current_version:
            return None

        # Find previous version
        previous_version = next(
            (v for v in versions if v['version_number'] == version_number - 1),
            None
        )

        if previous_version:
            changes = DrugVersionManager.compare_versions(
                previous_version['drug_data'],
                current_version['drug_data']
            )
        else:
            changes = {'has_changes': False, 'changed_fields': []}

        return {
            **current_version,
            'comparison': changes,
            'has_previous_version': previous_version is not None
        }
