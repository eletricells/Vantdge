"""
Disease Taxonomy

Provides:
- Hierarchical disease structure (category → disease → subtype)
- Standard endpoint definitions per disease
- Disease name normalization/matching
- Alias resolution
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


@dataclass
class EndpointDefinition:
    """Standard endpoint definition for a disease."""
    name: str                           # Canonical name: "CDASI"
    full_name: str                      # Full name: "Cutaneous Dermatomyositis Disease Area and Severity Index"
    category: str                       # "efficacy", "safety", "biomarker", "PRO"
    aliases: List[str] = field(default_factory=list)  # Alternative names
    is_validated: bool = False          # Whether endpoint is clinically validated
    typical_responder_threshold: Optional[str] = None  # e.g., "50% improvement"


@dataclass
class DiseaseEntry:
    """Disease entry in the taxonomy."""
    canonical_name: str                 # Standardized name: "Dermatomyositis"
    category: str                       # Top-level category: "Inflammatory Myopathies"
    parent_disease: Optional[str]       # Parent if this is a subtype: None for main diseases
    subtypes: List[str] = field(default_factory=list)  # Child subtypes
    aliases: List[str] = field(default_factory=list)   # Alternative names/spellings
    icd10_codes: List[str] = field(default_factory=list)  # ICD-10 codes
    mesh_terms: List[str] = field(default_factory=list)   # MeSH terms
    standard_endpoints: List[EndpointDefinition] = field(default_factory=list)
    prevalence_per_100k: Optional[float] = None  # Prevalence estimate
    is_rare: bool = False               # Rare disease designation


class DiseaseTaxonomy:
    """
    Disease taxonomy for standardization and hierarchy management.

    Provides:
    - Disease name normalization
    - Subtype → parent disease mapping
    - Standard endpoint lookup
    - Fuzzy matching for unknown disease names
    """

    def __init__(self, diseases: Optional[Dict[str, DiseaseEntry]] = None):
        """
        Initialize taxonomy.

        Args:
            diseases: Dictionary of canonical_name → DiseaseEntry
        """
        self._diseases: Dict[str, DiseaseEntry] = diseases or {}
        self._alias_map: Dict[str, str] = {}  # alias → canonical_name
        self._subtype_to_parent: Dict[str, str] = {}  # subtype → parent
        self._category_diseases: Dict[str, List[str]] = {}  # category → [diseases]

        self._build_indexes()

    def _build_indexes(self) -> None:
        """Build lookup indexes from disease entries."""
        self._alias_map.clear()
        self._subtype_to_parent.clear()
        self._category_diseases.clear()

        for canonical, entry in self._diseases.items():
            # Build alias map
            canonical_lower = canonical.lower()
            self._alias_map[canonical_lower] = canonical

            for alias in entry.aliases:
                self._alias_map[alias.lower()] = canonical

            # Build subtype map
            if entry.parent_disease:
                self._subtype_to_parent[canonical_lower] = entry.parent_disease

            for subtype in entry.subtypes:
                self._subtype_to_parent[subtype.lower()] = canonical

            # Build category index
            if entry.category not in self._category_diseases:
                self._category_diseases[entry.category] = []
            self._category_diseases[entry.category].append(canonical)

    def add_disease(self, entry: DiseaseEntry) -> None:
        """Add or update a disease entry."""
        self._diseases[entry.canonical_name] = entry
        self._build_indexes()

    def get_disease(self, name: str) -> Optional[DiseaseEntry]:
        """Get disease entry by canonical name or alias."""
        canonical = self.normalize(name)
        if canonical:
            return self._diseases.get(canonical)
        return None

    def normalize(self, disease_name: str) -> Optional[str]:
        """
        Normalize disease name to canonical form.

        Args:
            disease_name: Raw disease name from extraction

        Returns:
            Canonical disease name or None if not found
        """
        if not disease_name:
            return None

        name_lower = disease_name.lower().strip()

        # Direct match
        if name_lower in self._alias_map:
            return self._alias_map[name_lower]

        # Check if it's a known subtype
        if name_lower in self._subtype_to_parent:
            return self._subtype_to_parent[name_lower]

        # Fuzzy match
        best_match, score = self._fuzzy_match(name_lower)
        if score >= 0.85:
            return best_match

        return None

    def extract_disease_and_subtype(self, raw_text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract disease and subtype from raw text.

        Args:
            raw_text: Raw disease text like "amyopathic dermatomyositis"

        Returns:
            Tuple of (canonical_disease, subtype) e.g., ("Dermatomyositis", "Amyopathic")
        """
        if not raw_text:
            return None, None

        text_lower = raw_text.lower().strip()

        # FIRST: Check if this is a known subtype entry with parent_disease
        canonical = self.normalize(text_lower)
        if canonical:
            entry = self._diseases.get(canonical)
            if entry and entry.parent_disease:
                # This is itself a subtype entry (e.g., Lupus Nephritis)
                return entry.parent_disease, canonical

        # SECOND: Check for subtype keywords in text BEFORE falling back to base disease
        # This handles "amyopathic dermatomyositis" → (Dermatomyositis, Amyopathic)
        for canonical_name, entry in self._diseases.items():
            for subtype in entry.subtypes:
                subtype_lower = subtype.lower()
                # Check if full subtype name is in text
                if subtype_lower in text_lower:
                    # Extract just the qualifier (e.g., "Amyopathic" from "Amyopathic Dermatomyositis")
                    qualifier = self._extract_subtype_qualifier(subtype, canonical_name)
                    return canonical_name, qualifier or subtype

                # Also check for partial match (e.g., "amyopathic" in "amyopathic dermatomyositis")
                subtype_parts = subtype_lower.split()
                if len(subtype_parts) > 1:
                    qualifier_part = subtype_parts[0]
                    if qualifier_part in text_lower and canonical_name.lower() in text_lower:
                        qualifier = self._extract_subtype_qualifier(subtype, canonical_name)
                        return canonical_name, qualifier or subtype

        # THIRD: Fall back to canonical match without subtype
        if canonical:
            return canonical, None

        # FOURTH: Try to find disease by checking if canonical name or alias is in text
        for canonical_name, entry in self._diseases.items():
            if canonical_name.lower() in text_lower:
                return canonical_name, None
            for alias in entry.aliases:
                if alias.lower() in text_lower:
                    return canonical_name, None

        return None, None

    def _extract_subtype_qualifier(self, subtype: str, disease_name: str) -> Optional[str]:
        """
        Extract the qualifier portion of a subtype name.

        E.g., "Amyopathic Dermatomyositis" → "Amyopathic"
              "Relapsing-Remitting MS" → "Relapsing-Remitting"
        """
        subtype_lower = subtype.lower()
        disease_lower = disease_name.lower()

        # Remove disease name variants from subtype
        for variant in [disease_lower, disease_lower.replace(' ', '-'), disease_lower[:2].upper()]:
            if variant in subtype_lower:
                qualifier = subtype.replace(disease_name, '').replace(variant.upper(), '').strip()
                if qualifier:
                    return qualifier.strip(' -')

        # Try splitting on common disease abbreviations
        for abbrev in ['MS', 'DM', 'PM', 'RA', 'SLE', 'SSc', 'JIA']:
            if abbrev in subtype:
                parts = subtype.split(abbrev)
                if parts[0].strip():
                    return parts[0].strip(' -')

        # Return first word(s) before last word if multi-word
        parts = subtype.split()
        if len(parts) > 1:
            return ' '.join(parts[:-1])

        return subtype

    def get_parent_disease(self, disease_name: str) -> Optional[str]:
        """Get parent disease if this is a subtype."""
        name_lower = disease_name.lower().strip()
        return self._subtype_to_parent.get(name_lower)

    def get_standard_endpoints(self, disease_name: str) -> List[EndpointDefinition]:
        """Get standard endpoints for a disease."""
        canonical = self.normalize(disease_name)
        if canonical and canonical in self._diseases:
            return self._diseases[canonical].standard_endpoints
        return []

    def normalize_endpoint(self, endpoint_name: str, disease_name: str) -> Optional[str]:
        """
        Normalize endpoint name to canonical form.

        Args:
            endpoint_name: Raw endpoint name
            disease_name: Disease context for endpoint lookup

        Returns:
            Canonical endpoint name or None
        """
        if not endpoint_name:
            return None

        endpoint_lower = endpoint_name.lower().strip()
        endpoints = self.get_standard_endpoints(disease_name)

        for ep in endpoints:
            # Direct match
            if ep.name.lower() == endpoint_lower:
                return ep.name

            # Full name match
            if ep.full_name.lower() == endpoint_lower:
                return ep.name

            # Alias match
            for alias in ep.aliases:
                if alias.lower() == endpoint_lower or alias.lower() in endpoint_lower:
                    return ep.name

        # Extract core endpoint (remove disease qualifiers)
        # e.g., "CDASI score - Amyopathic DM" → "CDASI"
        for ep in endpoints:
            if ep.name.lower() in endpoint_lower:
                return ep.name

        return None

    def get_diseases_by_category(self, category: str) -> List[str]:
        """Get all diseases in a category."""
        return self._category_diseases.get(category, [])

    def get_all_categories(self) -> List[str]:
        """Get all disease categories."""
        return list(self._category_diseases.keys())

    def get_all_diseases(self) -> List[str]:
        """Get all canonical disease names."""
        return list(self._diseases.keys())

    def _fuzzy_match(self, name: str) -> Tuple[Optional[str], float]:
        """Find best fuzzy match for a disease name."""
        best_match = None
        best_score = 0.0

        for canonical in self._diseases.keys():
            score = SequenceMatcher(None, name, canonical.lower()).ratio()
            if score > best_score:
                best_score = score
                best_match = canonical

        # Also check aliases
        for alias, canonical in self._alias_map.items():
            score = SequenceMatcher(None, name, alias).ratio()
            if score > best_score:
                best_score = score
                best_match = canonical

        return best_match, best_score

    def to_dict(self) -> Dict:
        """Export taxonomy to dictionary."""
        return {
            name: {
                'canonical_name': entry.canonical_name,
                'category': entry.category,
                'parent_disease': entry.parent_disease,
                'subtypes': entry.subtypes,
                'aliases': entry.aliases,
                'icd10_codes': entry.icd10_codes,
                'standard_endpoints': [
                    {
                        'name': ep.name,
                        'full_name': ep.full_name,
                        'category': ep.category,
                        'aliases': ep.aliases,
                    }
                    for ep in entry.standard_endpoints
                ],
                'prevalence_per_100k': entry.prevalence_per_100k,
                'is_rare': entry.is_rare,
            }
            for name, entry in self._diseases.items()
        }


# =============================================================================
# Default Taxonomy Data
# =============================================================================

def get_default_taxonomy() -> DiseaseTaxonomy:
    """
    Create taxonomy with comprehensive autoimmune and rare disease entries.

    Uses expanded disease entries covering 295+ indications from Trial Matrix.
    """
    from src.case_series.taxonomy.expanded_diseases import get_expanded_disease_entries

    diseases = get_expanded_disease_entries()
    return DiseaseTaxonomy(diseases)


def get_legacy_taxonomy() -> DiseaseTaxonomy:
    """
    Create taxonomy with original curated entries (legacy).

    Kept for reference - use get_default_taxonomy() for production.
    """
    diseases = {}

    # =========================================================================
    # INFLAMMATORY MYOPATHIES
    # =========================================================================

    diseases["Dermatomyositis"] = DiseaseEntry(
        canonical_name="Dermatomyositis",
        category="Inflammatory Myopathies",
        parent_disease=None,
        subtypes=[
            "Amyopathic Dermatomyositis",
            "Hypomyopathic Dermatomyositis",
            "Classic Dermatomyositis",
            "Juvenile Dermatomyositis",
            "Clinically Amyopathic Dermatomyositis",
            "Anti-MDA5 Dermatomyositis",
        ],
        aliases=[
            "DM",
            "dermatomyositis",
            "adult dermatomyositis",
        ],
        icd10_codes=["M33.1", "M33.10", "M33.11", "M33.12"],
        standard_endpoints=[
            EndpointDefinition(
                name="CDASI",
                full_name="Cutaneous Dermatomyositis Disease Area and Severity Index",
                category="efficacy",
                aliases=["cdasi score", "cutaneous disease activity"],
                is_validated=True,
                typical_responder_threshold="50% improvement",
            ),
            EndpointDefinition(
                name="MMT8",
                full_name="Manual Muscle Testing 8",
                category="efficacy",
                aliases=["mmt-8", "manual muscle test", "muscle strength"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="Physician Global",
                full_name="Physician Global Assessment",
                category="efficacy",
                aliases=["physician global activity", "PGA", "physician VAS"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="Patient Global",
                full_name="Patient Global Assessment",
                category="PRO",
                aliases=["patient global activity", "patient VAS"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="CK",
                full_name="Creatine Kinase",
                category="biomarker",
                aliases=["creatine kinase", "CPK", "muscle enzymes"],
            ),
            EndpointDefinition(
                name="HAQ-DI",
                full_name="Health Assessment Questionnaire Disability Index",
                category="PRO",
                aliases=["HAQ", "disability index"],
                is_validated=True,
            ),
        ],
        prevalence_per_100k=1.0,
        is_rare=True,
    )

    diseases["Polymyositis"] = DiseaseEntry(
        canonical_name="Polymyositis",
        category="Inflammatory Myopathies",
        parent_disease=None,
        subtypes=[],
        aliases=["PM", "polymyositis"],
        icd10_codes=["M33.2", "M33.20", "M33.21", "M33.22"],
        standard_endpoints=[
            EndpointDefinition(
                name="MMT8",
                full_name="Manual Muscle Testing 8",
                category="efficacy",
                aliases=["mmt-8", "manual muscle test"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="CK",
                full_name="Creatine Kinase",
                category="biomarker",
                aliases=["creatine kinase", "CPK"],
            ),
        ],
        prevalence_per_100k=0.5,
        is_rare=True,
    )

    diseases["Inclusion Body Myositis"] = DiseaseEntry(
        canonical_name="Inclusion Body Myositis",
        category="Inflammatory Myopathies",
        parent_disease=None,
        subtypes=[],
        aliases=["IBM", "sporadic inclusion body myositis", "sIBM"],
        icd10_codes=["G72.41"],
        standard_endpoints=[
            EndpointDefinition(
                name="6MWD",
                full_name="6-Minute Walk Distance",
                category="efficacy",
                aliases=["6 minute walk", "6MWT"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="IBM-FRS",
                full_name="IBM Functional Rating Scale",
                category="PRO",
                aliases=["functional rating scale"],
                is_validated=True,
            ),
        ],
        prevalence_per_100k=0.5,
        is_rare=True,
    )

    # =========================================================================
    # ALOPECIA
    # =========================================================================

    diseases["Alopecia Areata"] = DiseaseEntry(
        canonical_name="Alopecia Areata",
        category="Alopecia",
        parent_disease=None,
        subtypes=[
            "Alopecia Totalis",
            "Alopecia Universalis",
            "Patchy Alopecia Areata",
            "Ophiasis",
        ],
        aliases=[
            "AA",
            "alopecia areata",
            "patchy alopecia",
            "spot baldness",
        ],
        icd10_codes=["L63.0", "L63.1", "L63.2", "L63.8", "L63.9"],
        standard_endpoints=[
            EndpointDefinition(
                name="SALT",
                full_name="Severity of Alopecia Tool",
                category="efficacy",
                aliases=["salt score", "alopecia severity"],
                is_validated=True,
                typical_responder_threshold="SALT ≤20 or 50% improvement",
            ),
            EndpointDefinition(
                name="Regrowth",
                full_name="Hair Regrowth Assessment",
                category="efficacy",
                aliases=["hair regrowth", "regrowth percentage"],
            ),
            EndpointDefinition(
                name="AASIS",
                full_name="Alopecia Areata Symptom Impact Scale",
                category="PRO",
                aliases=["symptom impact"],
            ),
        ],
        prevalence_per_100k=200.0,
        is_rare=False,
    )

    # =========================================================================
    # RHEUMATOID ARTHRITIS
    # =========================================================================

    diseases["Rheumatoid Arthritis"] = DiseaseEntry(
        canonical_name="Rheumatoid Arthritis",
        category="Rheumatic Diseases",
        parent_disease=None,
        subtypes=[
            "Seropositive Rheumatoid Arthritis",
            "Seronegative Rheumatoid Arthritis",
            "Juvenile Idiopathic Arthritis",
        ],
        aliases=[
            "RA",
            "rheumatoid arthritis",
            "rheumatoid",
        ],
        icd10_codes=["M05", "M06"],
        standard_endpoints=[
            EndpointDefinition(
                name="ACR20",
                full_name="American College of Rheumatology 20% Response",
                category="efficacy",
                aliases=["ACR 20", "acr20 response"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="ACR50",
                full_name="American College of Rheumatology 50% Response",
                category="efficacy",
                aliases=["ACR 50", "acr50 response"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="ACR70",
                full_name="American College of Rheumatology 70% Response",
                category="efficacy",
                aliases=["ACR 70", "acr70 response"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="DAS28",
                full_name="Disease Activity Score 28",
                category="efficacy",
                aliases=["DAS28-CRP", "DAS28-ESR", "disease activity score"],
                is_validated=True,
                typical_responder_threshold="DAS28 <2.6 (remission)",
            ),
            EndpointDefinition(
                name="HAQ-DI",
                full_name="Health Assessment Questionnaire Disability Index",
                category="PRO",
                aliases=["HAQ", "disability index"],
                is_validated=True,
            ),
        ],
        prevalence_per_100k=500.0,
        is_rare=False,
    )

    # =========================================================================
    # PSORIASIS / PSORIATIC ARTHRITIS
    # =========================================================================

    diseases["Psoriasis"] = DiseaseEntry(
        canonical_name="Psoriasis",
        category="Psoriatic Diseases",
        parent_disease=None,
        subtypes=[
            "Plaque Psoriasis",
            "Guttate Psoriasis",
            "Pustular Psoriasis",
            "Erythrodermic Psoriasis",
            "Inverse Psoriasis",
            "Palmoplantar Psoriasis",
            "Scalp Psoriasis",
            "Nail Psoriasis",
        ],
        aliases=["psoriasis vulgaris", "chronic plaque psoriasis"],
        icd10_codes=["L40.0", "L40.1", "L40.2", "L40.3", "L40.4"],
        standard_endpoints=[
            EndpointDefinition(
                name="PASI",
                full_name="Psoriasis Area and Severity Index",
                category="efficacy",
                aliases=["pasi score", "psoriasis severity"],
                is_validated=True,
                typical_responder_threshold="PASI 75 or PASI 90",
            ),
            EndpointDefinition(
                name="IGA",
                full_name="Investigator Global Assessment",
                category="efficacy",
                aliases=["IGA 0/1", "clear/almost clear"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="BSA",
                full_name="Body Surface Area",
                category="efficacy",
                aliases=["body surface area affected"],
            ),
            EndpointDefinition(
                name="DLQI",
                full_name="Dermatology Life Quality Index",
                category="PRO",
                aliases=["quality of life"],
                is_validated=True,
            ),
        ],
        prevalence_per_100k=2000.0,
        is_rare=False,
    )

    diseases["Psoriatic Arthritis"] = DiseaseEntry(
        canonical_name="Psoriatic Arthritis",
        category="Psoriatic Diseases",
        parent_disease=None,
        subtypes=[
            "Peripheral Psoriatic Arthritis",
            "Axial Psoriatic Arthritis",
        ],
        aliases=["PsA", "psoriatic arthritis"],
        icd10_codes=["L40.5", "M07.0", "M07.1", "M07.2", "M07.3"],
        standard_endpoints=[
            EndpointDefinition(
                name="ACR20",
                full_name="American College of Rheumatology 20% Response",
                category="efficacy",
                aliases=["ACR 20"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="MDA",
                full_name="Minimal Disease Activity",
                category="efficacy",
                aliases=["minimal disease activity"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="DAPSA",
                full_name="Disease Activity in Psoriatic Arthritis",
                category="efficacy",
                aliases=["dapsa score"],
                is_validated=True,
            ),
        ],
        prevalence_per_100k=100.0,
        is_rare=False,
    )

    # =========================================================================
    # LUPUS
    # =========================================================================

    diseases["Systemic Lupus Erythematosus"] = DiseaseEntry(
        canonical_name="Systemic Lupus Erythematosus",
        category="Lupus",
        parent_disease=None,
        subtypes=[
            "Lupus Nephritis",
            "Cutaneous Lupus",
            "Neuropsychiatric Lupus",
        ],
        aliases=[
            "SLE",
            "lupus",
            "systemic lupus",
        ],
        icd10_codes=["M32.0", "M32.1", "M32.8", "M32.9"],
        standard_endpoints=[
            EndpointDefinition(
                name="SRI-4",
                full_name="SLE Responder Index 4",
                category="efficacy",
                aliases=["SRI", "responder index"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="SLEDAI",
                full_name="SLE Disease Activity Index",
                category="efficacy",
                aliases=["sledai score", "disease activity"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="BILAG",
                full_name="British Isles Lupus Assessment Group",
                category="efficacy",
                aliases=["bilag score"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="CLASI",
                full_name="Cutaneous Lupus Erythematosus Disease Area and Severity Index",
                category="efficacy",
                aliases=["clasi score", "cutaneous lupus activity"],
                is_validated=True,
            ),
        ],
        prevalence_per_100k=50.0,
        is_rare=False,
    )

    # =========================================================================
    # ATOPIC DERMATITIS
    # =========================================================================

    diseases["Atopic Dermatitis"] = DiseaseEntry(
        canonical_name="Atopic Dermatitis",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=[
            "Moderate Atopic Dermatitis",
            "Severe Atopic Dermatitis",
        ],
        aliases=[
            "AD",
            "eczema",
            "atopic eczema",
        ],
        icd10_codes=["L20.0", "L20.8", "L20.9"],
        standard_endpoints=[
            EndpointDefinition(
                name="EASI",
                full_name="Eczema Area and Severity Index",
                category="efficacy",
                aliases=["easi score", "eczema severity"],
                is_validated=True,
                typical_responder_threshold="EASI 75 or EASI 90",
            ),
            EndpointDefinition(
                name="IGA",
                full_name="Investigator Global Assessment",
                category="efficacy",
                aliases=["IGA 0/1", "clear/almost clear"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="SCORAD",
                full_name="Scoring Atopic Dermatitis",
                category="efficacy",
                aliases=["scorad index"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="Pruritus NRS",
                full_name="Pruritus Numerical Rating Scale",
                category="PRO",
                aliases=["itch NRS", "pruritus score"],
                is_validated=True,
            ),
        ],
        prevalence_per_100k=1000.0,
        is_rare=False,
    )

    # =========================================================================
    # VITILIGO
    # =========================================================================

    diseases["Vitiligo"] = DiseaseEntry(
        canonical_name="Vitiligo",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=[
            "Non-segmental Vitiligo",
            "Segmental Vitiligo",
            "Universal Vitiligo",
        ],
        aliases=["vitiligo vulgaris"],
        icd10_codes=["L80"],
        standard_endpoints=[
            EndpointDefinition(
                name="F-VASI",
                full_name="Facial Vitiligo Area Scoring Index",
                category="efficacy",
                aliases=["facial VASI", "f-vasi score"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="T-VASI",
                full_name="Total Vitiligo Area Scoring Index",
                category="efficacy",
                aliases=["total VASI", "t-vasi score"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="Repigmentation",
                full_name="Repigmentation Assessment",
                category="efficacy",
                aliases=["repigmentation rate", "pigment return"],
            ),
        ],
        prevalence_per_100k=100.0,
        is_rare=False,
    )

    # =========================================================================
    # SJOGREN'S SYNDROME
    # =========================================================================

    diseases["Sjogren's Syndrome"] = DiseaseEntry(
        canonical_name="Sjogren's Syndrome",
        category="Autoimmune Diseases",
        parent_disease=None,
        subtypes=[
            "Primary Sjogren's Syndrome",
            "Secondary Sjogren's Syndrome",
        ],
        aliases=[
            "Sjogren syndrome",
            "Sjögren's syndrome",
            "sicca syndrome",
        ],
        icd10_codes=["M35.0"],
        standard_endpoints=[
            EndpointDefinition(
                name="ESSDAI",
                full_name="EULAR Sjogren's Syndrome Disease Activity Index",
                category="efficacy",
                aliases=["essdai score", "disease activity"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="ESSPRI",
                full_name="EULAR Sjogren's Syndrome Patient Reported Index",
                category="PRO",
                aliases=["esspri score", "patient reported"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="Schirmer Test",
                full_name="Schirmer's Test",
                category="efficacy",
                aliases=["schirmer score", "tear production"],
            ),
        ],
        prevalence_per_100k=50.0,
        is_rare=False,
    )

    # =========================================================================
    # SYSTEMIC SCLEROSIS
    # =========================================================================

    diseases["Systemic Sclerosis"] = DiseaseEntry(
        canonical_name="Systemic Sclerosis",
        category="Autoimmune Diseases",
        parent_disease=None,
        subtypes=[
            "Limited Cutaneous Systemic Sclerosis",
            "Diffuse Cutaneous Systemic Sclerosis",
        ],
        aliases=[
            "scleroderma",
            "SSc",
            "systemic scleroderma",
        ],
        icd10_codes=["M34.0", "M34.1", "M34.8", "M34.9"],
        standard_endpoints=[
            EndpointDefinition(
                name="mRSS",
                full_name="Modified Rodnan Skin Score",
                category="efficacy",
                aliases=["rodnan skin score", "skin thickness"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="FVC",
                full_name="Forced Vital Capacity",
                category="efficacy",
                aliases=["lung function", "pulmonary function"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="HAQ-DI",
                full_name="Health Assessment Questionnaire Disability Index",
                category="PRO",
                aliases=["HAQ", "disability index"],
                is_validated=True,
            ),
        ],
        prevalence_per_100k=20.0,
        is_rare=True,
    )

    # =========================================================================
    # VASCULITIS
    # =========================================================================

    diseases["ANCA-Associated Vasculitis"] = DiseaseEntry(
        canonical_name="ANCA-Associated Vasculitis",
        category="Vasculitis",
        parent_disease=None,
        subtypes=[
            "Granulomatosis with Polyangiitis",
            "Microscopic Polyangiitis",
            "Eosinophilic Granulomatosis with Polyangiitis",
        ],
        aliases=[
            "AAV",
            "ANCA vasculitis",
            "GPA",
            "Wegener's granulomatosis",
            "MPA",
            "EGPA",
            "Churg-Strauss syndrome",
        ],
        icd10_codes=["M31.3", "M31.7"],
        standard_endpoints=[
            EndpointDefinition(
                name="BVAS",
                full_name="Birmingham Vasculitis Activity Score",
                category="efficacy",
                aliases=["bvas score", "vasculitis activity"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="Remission",
                full_name="Complete Remission",
                category="efficacy",
                aliases=["clinical remission", "disease remission"],
            ),
            EndpointDefinition(
                name="GC Tapering",
                full_name="Glucocorticoid Tapering",
                category="efficacy",
                aliases=["steroid sparing", "prednisone tapering"],
            ),
        ],
        prevalence_per_100k=2.0,
        is_rare=True,
    )

    # =========================================================================
    # MYASTHENIA GRAVIS
    # =========================================================================

    diseases["Myasthenia Gravis"] = DiseaseEntry(
        canonical_name="Myasthenia Gravis",
        category="Neuromuscular Diseases",
        parent_disease=None,
        subtypes=[
            "Generalized Myasthenia Gravis",
            "Ocular Myasthenia Gravis",
            "Anti-AChR Myasthenia Gravis",
            "Anti-MuSK Myasthenia Gravis",
        ],
        aliases=[
            "MG",
            "myasthenia",
        ],
        icd10_codes=["G70.0", "G70.00", "G70.01"],
        standard_endpoints=[
            EndpointDefinition(
                name="MG-ADL",
                full_name="Myasthenia Gravis Activities of Daily Living",
                category="PRO",
                aliases=["mg-adl score", "adl score"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="QMG",
                full_name="Quantitative Myasthenia Gravis Score",
                category="efficacy",
                aliases=["qmg score"],
                is_validated=True,
            ),
            EndpointDefinition(
                name="MGC",
                full_name="Myasthenia Gravis Composite",
                category="efficacy",
                aliases=["mg composite"],
                is_validated=True,
            ),
        ],
        prevalence_per_100k=20.0,
        is_rare=True,
    )

    return DiseaseTaxonomy(diseases)
