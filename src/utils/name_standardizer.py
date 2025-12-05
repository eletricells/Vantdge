"""
Disease and drug name standardization utilities.

Provides consistent naming across:
- File system folders (data/clinical_papers/)
- Database storage (landscape_discovery_results)
- UI display

Standard format rules:
- Remove apostrophes, quotes, and special characters
- Replace spaces with underscores
- Lowercase everything
- Remove extra whitespace
- Replace multiple underscores with single underscore
"""
import re
from typing import Dict, List


def standardize_disease_name(disease: str) -> str:
    """
    Standardize a disease name for consistent file/folder naming.

    Args:
        disease: Original disease name (e.g., "Graves' Disease", "C3 Glomerulopathy")

    Returns:
        Standardized name (e.g., "graves_disease", "c3_glomerulopathy")

    Examples:
        >>> standardize_disease_name("Graves' Disease")
        'graves_disease'
        >>> standardize_disease_name("C3 Glomerulopathy")
        'c3_glomerulopathy'
        >>> standardize_disease_name("Crohn's Disease")
        'crohns_disease'
        >>> standardize_disease_name("Atopic Dermatitis")
        'atopic_dermatitis'
    """
    if not disease:
        return ""

    # Remove apostrophes and quotes
    name = disease.replace("'", "").replace('"', "")

    # Remove other special characters (keep letters, numbers, spaces, underscores, hyphens)
    name = re.sub(r'[^a-zA-Z0-9\s\_\-]', '', name)

    # Replace spaces and hyphens with underscores
    name = name.replace(' ', '_').replace('-', '_')

    # Replace multiple underscores with single underscore
    name = re.sub(r'_+', '_', name)

    # Lowercase
    name = name.lower()

    # Strip leading/trailing underscores
    name = name.strip('_')

    return name


def standardize_drug_name(drug: str) -> str:
    """
    Standardize a drug name for consistent file/folder naming.

    Args:
        drug: Original drug name (e.g., "APL-2", "K1-70", "Adalimumab")

    Returns:
        Standardized name (e.g., "apl_2", "k1_70", "adalimumab")

    Examples:
        >>> standardize_drug_name("APL-2")
        'apl_2'
        >>> standardize_drug_name("K1-70")
        'k1_70'
        >>> standardize_drug_name("Dupilumab")
        'dupilumab'
    """
    if not drug:
        return ""

    # Remove special characters except hyphens and underscores
    name = re.sub(r'[^a-zA-Z0-9\-_]', '', drug)

    # Replace hyphens with underscores
    name = name.replace('-', '_')

    # Replace multiple underscores with single underscore
    name = re.sub(r'_+', '_', name)

    # Lowercase
    name = name.lower()

    # Strip leading/trailing underscores
    name = name.strip('_')

    return name


def get_display_name(standardized_name: str) -> str:
    """
    Convert a standardized name back to a display-friendly format.

    Args:
        standardized_name: Standardized name (e.g., "graves_disease")

    Returns:
        Display name (e.g., "Graves Disease")

    Examples:
        >>> get_display_name("graves_disease")
        'Graves Disease'
        >>> get_display_name("c3_glomerulopathy")
        'C3 Glomerulopathy'
    """
    if not standardized_name:
        return ""

    # Replace underscores with spaces
    name = standardized_name.replace('_', ' ')

    # Title case
    name = name.title()

    return name


def create_name_mapping(original_names: List[str]) -> Dict[str, str]:
    """
    Create a mapping from original names to standardized names.

    Args:
        original_names: List of original names

    Returns:
        Dictionary mapping original -> standardized

    Example:
        >>> create_name_mapping(["Graves' Disease", "C3 Glomerulopathy"])
        {"Graves' Disease": "graves_disease", "C3 Glomerulopathy": "c3_glomerulopathy"}
    """
    return {name: standardize_disease_name(name) for name in original_names}


def reverse_mapping(name_mapping: Dict[str, str]) -> Dict[str, str]:
    """
    Create reverse mapping from standardized -> original.

    Args:
        name_mapping: Dictionary mapping original -> standardized

    Returns:
        Dictionary mapping standardized -> original
    """
    return {v: k for k, v in name_mapping.items()}


# Common disease name variations that should map to the same standardized name
DISEASE_ALIASES = {
    "graves_disease": ["Graves' Disease", "Graves Disease", "graves disease"],
    "crohns_disease": ["Crohn's Disease", "Crohns Disease", "crohns disease"],
    "atopic_dermatitis": ["Atopic Dermatitis", "atopic dermatitis", "AD"],
    "c3_glomerulopathy": ["C3 Glomerulopathy", "c3 glomerulopathy", "C3G"],
    "rheumatoid_arthritis": ["Rheumatoid Arthritis", "rheumatoid arthritis", "RA"],
    "psoriatic_arthritis": ["Psoriatic Arthritis", "psoriatic arthritis", "PsA"],
}


def normalize_disease_name(disease: str) -> str:
    """
    Normalize a disease name by standardizing and checking aliases.

    This handles common variations and aliases.

    Args:
        disease: Disease name in any format

    Returns:
        Standardized name

    Examples:
        >>> normalize_disease_name("Graves' Disease")
        'graves_disease'
        >>> normalize_disease_name("AD")
        'atopic_dermatitis'
    """
    # First try standardization
    standardized = standardize_disease_name(disease)

    # Check if it's in our standardized names
    if standardized in DISEASE_ALIASES:
        return standardized

    # Check if it matches any alias
    for standard_name, aliases in DISEASE_ALIASES.items():
        if disease in aliases:
            return standard_name

    # Return standardized version
    return standardized


if __name__ == "__main__":
    # Test the standardization
    test_cases = [
        "Graves' Disease",
        "C3 Glomerulopathy",
        "Crohn's Disease",
        "Atopic Dermatitis",
        "Rheumatoid Arthritis",
        "Psoriatic Arthritis",
    ]

    print("Disease Name Standardization Tests:\n")
    for disease in test_cases:
        standardized = standardize_disease_name(disease)
        display = get_display_name(standardized)
        print(f"{disease:25} -> {standardized:25} -> {display}")

    print("\n" + "="*70 + "\n")

    drug_tests = [
        "APL-2",
        "K1-70",
        "Adalimumab",
        "Pegcetacoplan",
        "IL-17A inhibitor",
    ]

    print("Drug Name Standardization Tests:\n")
    for drug in drug_tests:
        standardized = standardize_drug_name(drug)
        print(f"{drug:25} -> {standardized}")
