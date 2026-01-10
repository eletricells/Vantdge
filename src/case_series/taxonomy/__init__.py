"""
Disease Taxonomy System

Provides standardized disease names, hierarchies, and endpoint mappings
for autoimmune and rare diseases.
"""

from src.case_series.taxonomy.disease_taxonomy import (
    DiseaseTaxonomy,
    DiseaseEntry,
    EndpointDefinition,
    get_default_taxonomy,
)

__all__ = [
    "DiseaseTaxonomy",
    "DiseaseEntry",
    "EndpointDefinition",
    "get_default_taxonomy",
]
