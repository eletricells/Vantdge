"""
Drug data standardization utilities.

Standardizes dosing frequencies, routes of administration, and other drug data
into machine-readable formats for database storage.
"""
import re
from typing import Optional, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# FREQUENCY STANDARDIZATION
# =============================================================================

# Standard frequency codes
FREQUENCY_CODES = {
    # Daily
    "QD": "once daily",
    "BID": "twice daily",
    "TID": "three times daily",
    "QID": "four times daily",

    # Weekly
    "QW": "once weekly",
    "BIW": "twice weekly",
    "TIW": "three times weekly",

    # Multi-week
    "Q2W": "every 2 weeks",
    "Q3W": "every 3 weeks",
    "Q4W": "every 4 weeks",
    "Q6W": "every 6 weeks",
    "Q8W": "every 8 weeks",
    "Q12W": "every 12 weeks",

    # Monthly
    "QM": "monthly",
    "Q2M": "every 2 months",
    "Q3M": "every 3 months",
    "Q6M": "every 6 months",

    # As needed
    "PRN": "as needed",
    "HS": "at bedtime",
    "AC": "before meals",
    "PC": "after meals",
}

# Mapping from natural language to standard codes
FREQUENCY_MAPPING = {
    # Daily patterns
    "once daily": "QD",
    "once a day": "QD",
    "once per day": "QD",
    "every day": "QD",
    "daily": "QD",
    "qd": "QD",
    "od": "QD",

    "twice daily": "BID",
    "twice a day": "BID",
    "two times daily": "BID",
    "two times a day": "BID",
    "bid": "BID",

    "three times daily": "TID",
    "three times a day": "TID",
    "tid": "TID",

    "four times daily": "QID",
    "four times a day": "QID",
    "qid": "QID",

    # Weekly patterns
    "once weekly": "QW",
    "once a week": "QW",
    "once per week": "QW",
    "every week": "QW",
    "weekly": "QW",
    "qw": "QW",

    "twice weekly": "BIW",
    "twice a week": "BIW",
    "two times weekly": "BIW",
    "biw": "BIW",

    "three times weekly": "TIW",
    "three times a week": "TIW",
    "tiw": "TIW",

    # Multi-week patterns
    "every 2 weeks": "Q2W",
    "every two weeks": "Q2W",
    "every other week": "Q2W",
    "biweekly": "Q2W",
    "q2w": "Q2W",

    "every 3 weeks": "Q3W",
    "every three weeks": "Q3W",
    "q3w": "Q3W",

    "every 4 weeks": "Q4W",
    "every four weeks": "Q4W",
    "q4w": "Q4W",

    "every 6 weeks": "Q6W",
    "every six weeks": "Q6W",
    "q6w": "Q6W",

    "every 8 weeks": "Q8W",
    "every eight weeks": "Q8W",
    "q8w": "Q8W",

    "every 12 weeks": "Q12W",
    "every twelve weeks": "Q12W",
    "q12w": "Q12W",

    # Monthly patterns
    "monthly": "QM",
    "once monthly": "QM",
    "once a month": "QM",
    "every month": "QM",
    "qm": "QM",

    "every 2 months": "Q2M",
    "every two months": "Q2M",
    "q2m": "Q2M",

    "every 3 months": "Q3M",
    "every three months": "Q3M",
    "quarterly": "Q3M",
    "q3m": "Q3M",

    "every 6 months": "Q6M",
    "every six months": "Q6M",
    "q6m": "Q6M",

    # Special patterns
    "as needed": "PRN",
    "prn": "PRN",
    "at bedtime": "HS",
    "before sleep": "HS",
    "hs": "HS",
    "before meals": "AC",
    "ac": "AC",
    "after meals": "PC",
    "pc": "PC",
}


def standardize_frequency(frequency_text: str) -> Tuple[Optional[str], str]:
    """
    Standardize dosing frequency to standard code.

    Args:
        frequency_text: Natural language frequency description

    Returns:
        Tuple of (standard_code, original_text)

    Examples:
        >>> standardize_frequency("once every 4 weeks")
        ('Q4W', 'once every 4 weeks')
        >>> standardize_frequency("twice daily")
        ('BID', 'twice daily')
    """
    if not frequency_text:
        return None, ""

    original = frequency_text.strip()
    normalized = original.lower().strip()

    # Direct lookup
    if normalized in FREQUENCY_MAPPING:
        return FREQUENCY_MAPPING[normalized], original

    # Pattern matching for "X times per week/month"
    # "2 times per week" -> "BIW"
    match = re.search(r'(\d+)\s*times?\s*(?:per|a)\s*(week|day)', normalized)
    if match:
        count = int(match.group(1))
        period = match.group(2)

        if period == "day":
            mapping = {1: "QD", 2: "BID", 3: "TID", 4: "QID"}
            if count in mapping:
                return mapping[count], original
        elif period == "week":
            mapping = {1: "QW", 2: "BIW", 3: "TIW"}
            if count in mapping:
                return mapping[count], original

    # Pattern matching for "every X weeks/months"
    # "every 4 weeks" -> "Q4W"
    match = re.search(r'every\s+(\d+)\s+(week|month)', normalized)
    if match:
        count = int(match.group(1))
        period = match.group(2)

        if period == "week":
            return f"Q{count}W", original
        elif period == "month":
            return f"Q{count}M", original

    # Pattern matching for loading dose time points
    # "Week 0", "Week 1", "Day 1", "Day 15" - these are one-time doses, not recurring
    # Don't standardize these - keep them as-is since they represent specific time points
    if re.match(r'^week\s+\d+$', normalized):
        # "Week 0", "Week 1", etc. - return as-is (no standard code)
        return None, original

    if re.match(r'^day\s+\d+$', normalized):
        # "Day 1", "Day 15", etc. - return as-is (no standard code)
        return None, original

    # Pattern for "X weeks later", "X days later" - part of loading sequence
    if re.search(r'(week|day)s?\s+later', normalized):
        return None, original

    # Pattern for "initial dose" - loading dose
    if 'initial' in normalized and 'dose' in normalized:
        return None, original

    # If no match found, log warning and return None
    logger.warning(f"Could not standardize frequency: '{original}'")
    return None, original


# =============================================================================
# ROUTE STANDARDIZATION
# =============================================================================

# Standard route codes
ROUTE_CODES = {
    "SC": "subcutaneous",
    "IV": "intravenous",
    "PO": "oral",
    "IM": "intramuscular",
    "IT": "intrathecal",
    "ICV": "intracerebroventricular",
    "topical": "topical",
    "ophthalmic": "ophthalmic",
    "otic": "otic",
    "nasal": "nasal",
    "inhaled": "inhaled",
    "rectal": "rectal",
    "transdermal": "transdermal",
}

# Mapping from natural language to standard codes
ROUTE_MAPPING = {
    # Subcutaneous
    "subcutaneous": "SC",
    "subcutaneous injection": "SC",
    "sc": "SC",
    "subq": "SC",
    "sq": "SC",
    "under the skin": "SC",

    # Intravenous
    "intravenous": "IV",
    "intravenous infusion": "IV",
    "intravenous injection": "IV",
    "iv": "IV",
    "into the vein": "IV",

    # Oral
    "oral": "PO",
    "by mouth": "PO",
    "po": "PO",
    "orally": "PO",

    # Intramuscular
    "intramuscular": "IM",
    "intramuscular injection": "IM",
    "im": "IM",
    "into the muscle": "IM",

    # Intrathecal
    "intrathecal": "IT",
    "intrathecal injection": "IT",
    "it": "IT",
    "into the spinal canal": "IT",

    # Intracerebroventricular
    "intracerebroventricular": "ICV",
    "icv": "ICV",

    # Topical
    "topical": "topical",
    "applied to skin": "topical",
    "skin application": "topical",

    # Ophthalmic
    "ophthalmic": "ophthalmic",
    "eye drops": "ophthalmic",
    "into the eye": "ophthalmic",

    # Otic
    "otic": "otic",
    "ear drops": "otic",
    "into the ear": "otic",

    # Nasal
    "nasal": "nasal",
    "nasal spray": "nasal",
    "into the nose": "nasal",

    # Inhaled
    "inhaled": "inhaled",
    "inhalation": "inhaled",
    "by inhalation": "inhaled",

    # Rectal
    "rectal": "rectal",
    "rectally": "rectal",
    "into the rectum": "rectal",

    # Transdermal
    "transdermal": "transdermal",
    "transdermal patch": "transdermal",
    "patch": "transdermal",
}


def standardize_route(route_text: str) -> Tuple[Optional[str], str]:
    """
    Standardize route of administration to standard code.

    Args:
        route_text: Natural language route description

    Returns:
        Tuple of (standard_code, original_text)

    Examples:
        >>> standardize_route("subcutaneous injection")
        ('SC', 'subcutaneous injection')
        >>> standardize_route("by mouth")
        ('PO', 'by mouth')
    """
    if not route_text:
        return None, ""

    original = route_text.strip()
    normalized = original.lower().strip()

    # Direct lookup
    if normalized in ROUTE_MAPPING:
        return ROUTE_MAPPING[normalized], original

    # Partial matching for common patterns
    if "subcutaneous" in normalized or "subq" in normalized or " sc " in normalized:
        return "SC", original
    if "intravenous" in normalized or " iv " in normalized:
        return "IV", original
    if "oral" in normalized or "by mouth" in normalized:
        return "PO", original
    if "intramuscular" in normalized or " im " in normalized:
        return "IM", original
    if "intrathecal" in normalized or " it " in normalized:
        return "IT", original

    # If no match found, log warning and return None
    logger.warning(f"Could not standardize route: '{original}'")
    return None, original


# =============================================================================
# DOSE UNIT STANDARDIZATION
# =============================================================================

# Standard dose units
DOSE_UNIT_MAPPING = {
    # Mass
    "mg": "mg",
    "milligram": "mg",
    "milligrams": "mg",
    "g": "g",
    "gram": "g",
    "grams": "g",
    "mcg": "mcg",
    "microgram": "mcg",
    "micrograms": "mcg",
    "μg": "mcg",

    # Weight-based
    "mg/kg": "mg/kg",
    "mg per kg": "mg/kg",
    "mg/m2": "mg/m2",
    "mg per m2": "mg/m2",

    # Volume
    "ml": "mL",
    "milliliter": "mL",
    "milliliters": "mL",

    # Concentration
    "mg/ml": "mg/mL",
    "mg per ml": "mg/mL",

    # Units
    "units": "units",
    "unit": "units",
    "iu": "IU",
    "international units": "IU",

    # Percentage
    "%": "%",
    "percent": "%",
}


def standardize_dose_unit(unit_text: str) -> Optional[str]:
    """
    Standardize dose unit.

    Args:
        unit_text: Unit text to standardize

    Returns:
        Standardized unit or None if not recognized

    Examples:
        >>> standardize_dose_unit("milligrams")
        'mg'
        >>> standardize_dose_unit("mg/kg")
        'mg/kg'
    """
    if not unit_text:
        return None

    normalized = unit_text.lower().strip()

    if normalized in DOSE_UNIT_MAPPING:
        return DOSE_UNIT_MAPPING[normalized]

    logger.warning(f"Could not standardize dose unit: '{unit_text}'")
    return None


# =============================================================================
# DRUG TYPE STANDARDIZATION
# =============================================================================

DRUG_TYPE_MAPPING = {
    # Biologics
    "monoclonal antibody": "mAb",
    "monoclonal": "mAb",
    "mab": "mAb",
    "antibody": "mAb",

    "bispecific antibody": "bispecific",
    "bispecific": "bispecific",

    "antibody-drug conjugate": "ADC",
    "adc": "ADC",

    "fusion protein": "fusion protein",
    "fc fusion": "fusion protein",

    # Small molecules
    "small molecule": "small molecule",
    "small molecule inhibitor": "small molecule",

    # Cell/gene therapies
    "car-t": "CAR-T",
    "car t": "CAR-T",
    "chimeric antigen receptor": "CAR-T",

    "gene therapy": "gene therapy",
    "aav": "gene therapy",
    "adeno-associated virus": "gene therapy",

    # Others
    "peptide": "peptide",
    "protein": "protein",
    "vaccine": "vaccine",
    "oligonucleotide": "oligonucleotide",
    "antisense": "oligonucleotide",
    "sirna": "siRNA",
    "rna interference": "siRNA",
}


def standardize_drug_type(drug_type_text: str) -> Optional[str]:
    """
    Standardize drug type classification.

    Args:
        drug_type_text: Drug type description

    Returns:
        Standardized drug type or None

    Examples:
        >>> standardize_drug_type("monoclonal antibody")
        'mAb'
        >>> standardize_drug_type("antibody-drug conjugate")
        'ADC'
    """
    if not drug_type_text:
        return None

    normalized = drug_type_text.lower().strip()

    if normalized in DRUG_TYPE_MAPPING:
        return DRUG_TYPE_MAPPING[normalized]

    # Partial matching
    if "monoclonal" in normalized or "antibody" in normalized:
        if "bispecific" in normalized:
            return "bispecific"
        elif "conjugate" in normalized or "adc" in normalized:
            return "ADC"
        else:
            return "mAb"

    if "small molecule" in normalized:
        return "small molecule"

    if "car" in normalized and "t" in normalized:
        return "CAR-T"

    logger.warning(f"Could not standardize drug type: '{drug_type_text}'")
    return None


# =============================================================================
# BATCH STANDARDIZATION
# =============================================================================

def standardize_dosing_data(dosing_dict: Dict) -> Dict:
    """
    Standardize all dosing-related fields in a dictionary.

    Args:
        dosing_dict: Dictionary with fields like frequency_raw, route_raw, dose_unit

    Returns:
        Dictionary with added standardized fields

    Example:
        >>> data = {
        ...     "frequency_raw": "once every 4 weeks",
        ...     "route_raw": "subcutaneous injection",
        ...     "dose_unit": "milligrams"
        ... }
        >>> standardize_dosing_data(data)
        {
            'frequency_raw': 'once every 4 weeks',
            'frequency_standard': 'Q4W',
            'route_raw': 'subcutaneous injection',
            'route_standard': 'SC',
            'dose_unit': 'mg'
        }
    """
    result = dosing_dict.copy()

    # Standardize frequency
    if "frequency_raw" in result:
        freq_std, _ = standardize_frequency(result["frequency_raw"])
        result["frequency_standard"] = freq_std

    # Standardize route
    if "route_raw" in result:
        route_std, _ = standardize_route(result["route_raw"])
        result["route_standard"] = route_std

    # Standardize dose unit
    if "dose_unit" in result:
        result["dose_unit"] = standardize_dose_unit(result["dose_unit"])

    return result


# =============================================================================
# VALIDATION
# =============================================================================

def validate_frequency_code(code: str) -> bool:
    """Check if frequency code is valid."""
    return code in FREQUENCY_CODES


def validate_route_code(code: str) -> bool:
    """Check if route code is valid."""
    return code in ROUTE_CODES


def get_frequency_description(code: str) -> Optional[str]:
    """Get human-readable description for frequency code."""
    return FREQUENCY_CODES.get(code)


def get_route_description(code: str) -> Optional[str]:
    """Get human-readable description for route code."""
    return ROUTE_CODES.get(code)


# =============================================================================
# INDICATION NAME CLEANING
# =============================================================================

def clean_indication_name(indication_raw: str, brand_name: Optional[str] = None, generic_name: Optional[str] = None) -> str:
    """
    Clean indication name by removing drug names, patient population prefixes, and severity modifiers.

    Removes:
    - Drug names (brand/generic)
    - Patient population prefixes ("adult patients with", "pediatric patients with", etc.)
    - Severity modifiers ("active", "severe", "moderate", "chronic", etc.)
    - Leading/trailing prepositions

    Args:
        indication_raw: Raw indication text from label
        brand_name: Brand name to remove (optional)
        generic_name: Generic name to remove (optional)

    Returns:
        Cleaned indication name (just the core disease name)

    Examples:
        >>> clean_indication_name("Adult Patients With Active Non-Radiographic Axial Spondyloarthritis")
        'non-radiographic axial spondyloarthritis'
        >>> clean_indication_name("Severe Plaque Psoriasis")
        'plaque psoriasis'
        >>> clean_indication_name("Active Rheumatoid Arthritis")
        'rheumatoid arthritis'
    """
    if not indication_raw:
        return ""

    cleaned = indication_raw.strip()

    # Fix apostrophe spacing issues (e.g., "crohn'sdisease" → "crohn's disease")
    cleaned = re.sub(r"'s([a-z])", r"'s \1", cleaned)

    # Remove drug name prefixes (case-insensitive)
    if brand_name:
        # Remove "BrandName (generic) for"
        pattern = rf'\b{re.escape(brand_name)}\s*\([^)]+\)\s+for\s+'
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        # Remove "BrandName for"
        pattern = rf'\b{re.escape(brand_name)}\s+for\s+'
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    if generic_name:
        # Remove "generic for"
        pattern = rf'\b{re.escape(generic_name)}\s+for\s+'
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # Remove generic drug name pattern "(drugname) for"
    cleaned = re.sub(r'\([^)]+\)\s+for\s+', '', cleaned, flags=re.IGNORECASE)

    # Remove patient population prefixes (order matters - longer first)
    population_prefixes = [
        r'adult\s+patients\s+living\s+with\s+to\s+',
        r'pediatric\s+patients\s+living\s+with\s+to\s+',
        r'adult\s+patients\s+living\s+with\s+',
        r'pediatric\s+patients\s+living\s+with\s+',
        r'adult\s+patients\s+with\s+',
        r'pediatric\s+patients\s+with\s+',
        r'patients\s+living\s+with\s+to\s+',
        r'patients\s+living\s+with\s+',
        r'patients\s+with\s+',
        r'adults\s+with\s+',
        r'children\s+with\s+',
        r'adult\s+',
        r'pediatric\s+',
    ]
    for prefix in population_prefixes:
        cleaned = re.sub(rf'^\s*{prefix}', '', cleaned, flags=re.IGNORECASE)

    # Remove severity/temporal modifiers (comprehensive list)
    # These should be stripped to get the core disease name
    modifiers = [
        r'\bactive\s+',
        r'\bseverely\s+active\s+',
        r'\bmoderately\s+active\s+',
        r'\bmildly\s+active\s+',
        r'\bsevere\s+',
        r'\bmoderate\s+to\s+severe\s+',
        r'\bmild\s+to\s+moderate\s+',
        r'\bmoderate\s+',
        r'\bmild\s+',
        r'\bchronic\s+',
        r'\bacute\s+',
        r'\brecurrent\s+',
        r'\bpersistent\s+',
    ]
    for modifier in modifiers:
        cleaned = re.sub(modifier, '', cleaned, flags=re.IGNORECASE)

    # Remove leading prepositions
    cleaned = re.sub(r'^\s*to\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*for\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*in\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*of\s+', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^\s*with\s+', '', cleaned, flags=re.IGNORECASE)

    # Remove trailing prepositions/articles
    cleaned = re.sub(r'\s+(the|a|an|with|in|of)\s*$', '', cleaned, flags=re.IGNORECASE)

    # Remove "treatment of"
    cleaned = re.sub(r'^\s*treatment\s+of\s+', '', cleaned, flags=re.IGNORECASE)

    # Clean up whitespace (multiple spaces → single space)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # Lowercase the result (disease names should be lowercase in database)
    cleaned = cleaned.lower()

    return cleaned
