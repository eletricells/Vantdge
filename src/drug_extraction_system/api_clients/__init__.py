"""
API Clients module for drug extraction system.

Provides rate-limited clients for various drug data APIs.
"""

from src.drug_extraction_system.api_clients.base_client import BaseAPIClient
from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
from src.drug_extraction_system.api_clients.rxnorm_client import RxNormClient
from src.drug_extraction_system.api_clients.clinicaltrials_client import ClinicalTrialsClient
from src.drug_extraction_system.api_clients.mesh_client import MeSHClient

__all__ = [
    "BaseAPIClient",
    "OpenFDAClient",
    "RxNormClient",
    "ClinicalTrialsClient",
    "MeSHClient",
]

