"""
Drug Key Generator

Generates stable, deterministic drug keys for unique identification across systems.

Format: DRG-{NORMALIZED_GENERIC_NAME}-{CHECKSUM}
Example: DRG-UPADACITINIB-7A2F
"""

import hashlib
import re
from typing import Optional


class DrugKeyGenerator:
    """Generate stable, deterministic drug keys."""

    PREFIX = "DRG"
    CHECKSUM_LENGTH = 4

    @classmethod
    def generate(cls, generic_name: str, additional_data: Optional[str] = None) -> str:
        """
        Generate drug key from generic name.

        Args:
            generic_name: Generic drug name (e.g., "upadacitinib")
            additional_data: Optional data for collision resolution (e.g., CAS number)

        Returns:
            Drug key in format: DRG-UPADACITINIB-7A2F

        Examples:
            >>> DrugKeyGenerator.generate("upadacitinib")
            'DRG-UPADACITINIB-7A2F'

            >>> DrugKeyGenerator.generate("Upadacitinib")  # Case insensitive
            'DRG-UPADACITINIB-7A2F'
        """
        # Step 1: Normalize generic name
        normalized = cls._normalize_name(generic_name)

        # Step 2: Generate checksum
        checksum = cls._generate_checksum(normalized, additional_data)

        # Step 3: Construct key
        drug_key = f"{cls.PREFIX}-{normalized}-{checksum}"

        return drug_key

    @classmethod
    def _normalize_name(cls, name: str) -> str:
        """
        Normalize drug name to standard format.

        Rules:
        - Convert to uppercase
        - Remove special characters (keep letters and numbers)
        - Remove spaces
        - Trim to 50 characters max
        """
        # Convert to uppercase
        normalized = name.upper()

        # Remove special characters, keep only alphanumeric
        normalized = re.sub(r'[^A-Z0-9]', '', normalized)

        # Trim to max length
        normalized = normalized[:50]

        if not normalized:
            raise ValueError(f"Cannot normalize empty drug name: {name}")

        return normalized

    @classmethod
    def _generate_checksum(cls, normalized_name: str, additional_data: Optional[str] = None) -> str:
        """
        Generate checksum for collision detection.

        Uses SHA-256 hash, takes first N hex digits.
        """
        # Combine name with optional additional data
        data = normalized_name
        if additional_data:
            data = f"{normalized_name}:{additional_data}"

        # Generate hash
        hash_obj = hashlib.sha256(data.encode('utf-8'))
        hash_hex = hash_obj.hexdigest()

        # Take first N characters and convert to uppercase
        checksum = hash_hex[:cls.CHECKSUM_LENGTH].upper()

        return checksum

    @classmethod
    def validate(cls, drug_key: str) -> bool:
        """
        Validate drug key format.

        Format: DRG-{NAME}-{CHECKSUM}
        """
        pattern = r'^DRG-[A-Z0-9]{1,50}-[A-F0-9]{4}$'
        return bool(re.match(pattern, drug_key))

    @classmethod
    def extract_name(cls, drug_key: str) -> Optional[str]:
        """Extract normalized name from drug key."""
        if not cls.validate(drug_key):
            return None

        parts = drug_key.split('-')
        if len(parts) >= 2:
            return parts[1]

        return None

    @classmethod
    def regenerate_and_verify(cls, drug_key: str, generic_name: str, additional_data: Optional[str] = None) -> bool:
        """
        Verify that a drug key matches the expected value for a generic name.

        Useful for data integrity checks.
        """
        expected_key = cls.generate(generic_name, additional_data)
        return drug_key == expected_key

