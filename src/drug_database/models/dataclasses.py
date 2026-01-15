"""
Data models for drug database.

Provides type-safe dataclasses for all drug-related entities.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any


@dataclass
class Drug:
    """Drug entity."""
    drug_id: int
    generic_name: str
    brand_name: Optional[str] = None
    manufacturer: Optional[str] = None
    drug_key: Optional[str] = None
    development_code: Optional[str] = None
    drug_type: Optional[str] = None
    mechanism_of_action: Optional[str] = None
    target: Optional[str] = None
    moa_category: Optional[str] = None
    approval_status: str = "investigational"
    highest_phase: Optional[str] = None
    dailymed_setid: Optional[str] = None
    first_approval_date: Optional[date] = None
    rxcui: Optional[str] = None
    chembl_id: Optional[str] = None
    inchi_key: Optional[str] = None
    cas_number: Optional[str] = None
    unii: Optional[str] = None
    is_combination: bool = False
    combination_components: Optional[List[int]] = None
    completeness_score: Optional[float] = None
    data_version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Disease:
    """Disease/indication entity."""
    disease_id: int
    disease_name_standard: str
    disease_aliases: List[str] = field(default_factory=list)
    icd10_codes: List[str] = field(default_factory=list)
    therapeutic_area: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class Indication:
    """Drug-disease indication relationship.

    Note: Schema stores disease_name directly, not as FK to diseases table.
    """
    indication_id: int
    drug_id: int
    disease_name: Optional[str] = None
    mesh_id: Optional[str] = None
    icd10_code: Optional[str] = None
    population: Optional[str] = None
    severity: Optional[str] = None
    line_of_therapy: Optional[str] = None
    combination_therapy: Optional[str] = None
    approval_status: str = "investigational"
    approval_date: Optional[date] = None
    regulatory_region: Optional[str] = None
    special_conditions: Optional[str] = None
    raw_source_text: Optional[str] = None
    confidence_score: Optional[float] = None
    data_source: str = "Manual"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class DosingRegimen:
    """Drug dosing regimen."""
    dosing_id: int
    drug_id: int
    indication_id: Optional[int] = None
    regimen_phase: Optional[str] = "single"
    dose_amount: Optional[float] = None
    dose_unit: Optional[str] = None
    frequency_standard: Optional[str] = None
    frequency_raw: Optional[str] = None
    route_standard: Optional[str] = None
    route_raw: Optional[str] = None
    duration_weeks: Optional[int] = None
    weight_based: bool = False
    sequence_order: int = 1
    dosing_notes: Optional[str] = None
    data_source: Optional[str] = "Manual"
    population: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class DrugMetadata:
    """Drug regulatory and safety metadata.

    Note: drug_id is the primary key (no separate metadata_id).
    """
    drug_id: int
    patent_expiry: Optional[date] = None
    exclusivity_end: Optional[date] = None
    orphan_designation: bool = False
    breakthrough_therapy: bool = False
    fast_track: bool = False
    accelerated_approval: bool = False
    first_in_class: bool = False
    biosimilar_available: bool = False
    has_black_box_warning: bool = False
    contraindications_summary: Optional[str] = None
    safety_notes: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class DrugOverview:
    """Complete drug overview with all related data."""
    drug: Drug
    indications: List[Indication] = field(default_factory=list)
    dosing_regimens: List[DosingRegimen] = field(default_factory=list)
    metadata: Optional[DrugMetadata] = None
    identifiers: Dict[str, str] = field(default_factory=dict)


# Type aliases for create/update operations
DrugCreateData = Dict[str, Any]
DrugUpdateData = Dict[str, Any]
IndicationCreateData = Dict[str, Any]
DosingCreateData = Dict[str, Any]

