"""
PubChem API Client

Provides drug name resolution and synonym lookup using PubChem's PUG REST API.
Useful for mapping research codes to generic names and deduplicating drug entries.
"""

import logging
import re
import requests
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)


@dataclass
class PubChemCompound:
    """PubChem compound information."""
    cid: int
    name: str
    iupac_name: Optional[str] = None
    molecular_formula: Optional[str] = None
    synonyms: List[str] = None

    def __post_init__(self):
        if self.synonyms is None:
            self.synonyms = []


class PubChemClient:
    """
    Client for PubChem PUG REST API.

    Useful for:
    - Mapping research codes (e.g., PF-06823859) to generic names (e.g., dazukibart)
    - Getting all synonyms for a compound
    - Deduplicating drug entries
    """

    BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    # Pattern for INN (International Nonproprietary Name) - generic drug names
    # Most end in specific suffixes like -mab, -nib, -tinib, etc.
    INN_SUFFIXES = [
        'mab', 'umab', 'ximab', 'zumab', 'mumab',  # Monoclonal antibodies
        'nib', 'tinib', 'anib',  # Kinase inhibitors
        'lib', 'glib',  # Lipase inhibitors
        'prazole', 'razole',  # Proton pump inhibitors
        'sartan', 'artan',  # Angiotensin receptor blockers
        'statin', 'vastatin',  # HMG-CoA reductase inhibitors
        'pril', 'april',  # ACE inhibitors
        'olol', 'alol',  # Beta blockers
        'caine', 'cain',  # Local anesthetics
        'cillin', 'mycin', 'cycline',  # Antibiotics
        'vir', 'navir', 'gravir',  # Antivirals
        'ase',  # Enzymes
        'ept', 'cept',  # Receptor molecules
        'bart', 'ibart',  # Interferon inhibitors (like dazukibart)
        'kin', 'leukin',  # Interleukins
        'platin',  # Platinum compounds
        'taxel', 'xel',  # Taxanes
        'parin',  # Anticoagulants
        'lukast',  # Leukotriene antagonists
        'glitazone', 'gliflozin',  # Diabetes drugs
        'tide', 'tide',  # Peptides
        'ximab', 'zumab',  # Chimeric/humanized antibodies
        'citinib', 'metinib',  # More kinase inhibitors
    ]

    # Research code patterns (company prefixes)
    RESEARCH_CODE_PATTERN = re.compile(
        r'^[A-Z]{2,5}[-\s]?\d{3,7}[A-Z]?$',
        re.IGNORECASE
    )

    def __init__(self, timeout: int = 30):
        """
        Initialize PubChem client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json'
        })

    def search_by_name(self, name: str) -> Optional[PubChemCompound]:
        """
        Search for a compound by name.

        Args:
            name: Drug name (generic, brand, or research code)

        Returns:
            PubChemCompound if found, None otherwise
        """
        try:
            # First, try the compound database
            url = f"{self.BASE_URL}/compound/name/{requests.utils.quote(name)}/cids/JSON"
            response = self.session.get(url, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()
                cids = data.get('IdentifierList', {}).get('CID', [])
                if cids:
                    return self.get_compound_by_cid(cids[0])

            # If not found in compounds, try the substance database
            logger.debug(f"No compound found for '{name}', trying substance database...")
            substance_result = self.search_substance_by_name(name)
            if substance_result:
                return substance_result

            logger.debug(f"No PubChem compound or substance found for '{name}'")
            return None

        except requests.exceptions.RequestException as e:
            logger.warning(f"PubChem search failed for '{name}': {e}")
            return None

    def search_substance_by_name(self, name: str) -> Optional[PubChemCompound]:
        """
        Search for a substance by name (for newer drugs not yet in compound DB).

        Args:
            name: Drug name

        Returns:
            PubChemCompound-like object with substance info
        """
        try:
            # Search substance by name
            url = f"{self.BASE_URL}/substance/name/{requests.utils.quote(name)}/sids/JSON"
            response = self.session.get(url, timeout=self.timeout)

            if response.status_code != 200:
                return None

            data = response.json()
            sids = data.get('IdentifierList', {}).get('SID', [])

            if not sids:
                return None

            sid = sids[0]

            # Get substance synonyms
            synonyms = self.get_substance_synonyms(sid)

            # Try to get linked CID (if substance is linked to a compound)
            cid = self.get_substance_cid(sid)

            return PubChemCompound(
                cid=cid or -sid,  # Use negative SID if no CID
                name=name,
                synonyms=synonyms
            )

        except requests.exceptions.RequestException as e:
            logger.debug(f"Substance search failed for '{name}': {e}")
            return None

    def get_substance_synonyms(self, sid: int) -> List[str]:
        """Get synonyms for a substance."""
        try:
            url = f"{self.BASE_URL}/substance/sid/{sid}/synonyms/JSON"
            response = self.session.get(url, timeout=self.timeout)

            if response.status_code != 200:
                return []

            data = response.json()
            synonyms = data.get('InformationList', {}).get('Information', [{}])[0].get('Synonym', [])
            return synonyms[:100]

        except requests.exceptions.RequestException as e:
            logger.debug(f"Failed to get substance synonyms for SID {sid}: {e}")
            return []

    def get_substance_cid(self, sid: int) -> Optional[int]:
        """Get the CID linked to a substance (if any)."""
        try:
            url = f"{self.BASE_URL}/substance/sid/{sid}/cids/JSON"
            response = self.session.get(url, timeout=self.timeout)

            if response.status_code != 200:
                return None

            data = response.json()
            cids = data.get('InformationList', {}).get('Information', [{}])[0].get('CID', [])
            return cids[0] if cids else None

        except requests.exceptions.RequestException as e:
            logger.debug(f"Failed to get CID for SID {sid}: {e}")
            return None

    def get_compound_by_cid(self, cid: int) -> Optional[PubChemCompound]:
        """
        Get compound details by CID.

        Args:
            cid: PubChem Compound ID

        Returns:
            PubChemCompound with details
        """
        try:
            # Get basic properties
            url = f"{self.BASE_URL}/compound/cid/{cid}/property/Title,IUPACName,MolecularFormula/JSON"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            props = response.json().get('PropertyTable', {}).get('Properties', [{}])[0]

            # Get synonyms
            synonyms = self.get_synonyms(cid)

            return PubChemCompound(
                cid=cid,
                name=props.get('Title', ''),
                iupac_name=props.get('IUPACName'),
                molecular_formula=props.get('MolecularFormula'),
                synonyms=synonyms
            )

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get PubChem compound {cid}: {e}")
            return None

    @lru_cache(maxsize=500)
    def get_synonyms(self, cid: int) -> List[str]:
        """
        Get all synonyms for a compound.

        Args:
            cid: PubChem Compound ID

        Returns:
            List of synonyms
        """
        try:
            url = f"{self.BASE_URL}/compound/cid/{cid}/synonyms/JSON"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()
            synonyms = data.get('InformationList', {}).get('Information', [{}])[0].get('Synonym', [])

            return synonyms[:100]  # Limit to first 100

        except requests.exceptions.RequestException as e:
            logger.debug(f"Failed to get synonyms for CID {cid}: {e}")
            return []

    def find_generic_name(self, name: str) -> Optional[str]:
        """
        Find the generic (INN) name for a drug.

        This is the main method for mapping research codes to generic names.

        Args:
            name: Drug name (often a research code like PF-06823859)

        Returns:
            Generic name if found (e.g., 'dazukibart'), None otherwise
        """
        compound = self.search_by_name(name)
        if not compound:
            return None

        # Check if the compound's primary name is already a generic name
        if self._is_generic_name(compound.name):
            return compound.name.lower()

        # Search through synonyms for generic name
        for synonym in compound.synonyms:
            if self._is_generic_name(synonym):
                return synonym.lower()

        # If no clear generic name, return the primary name
        return compound.name.lower() if compound.name else None

    def _is_generic_name(self, name: str) -> bool:
        """
        Check if a name appears to be a generic (INN) drug name.

        Args:
            name: Drug name to check

        Returns:
            True if appears to be generic name
        """
        if not name:
            return False

        name_lower = name.lower().strip()

        # Skip if it's a research code
        if self.RESEARCH_CODE_PATTERN.match(name):
            return False

        # Skip if it contains numbers (likely research code or CAS number)
        if re.search(r'\d', name):
            return False

        # Skip if too short
        if len(name_lower) < 5:
            return False

        # Check for INN suffixes
        for suffix in self.INN_SUFFIXES:
            if name_lower.endswith(suffix):
                return True

        # Check if it's a single lowercase word (typical of generic names)
        if name_lower.isalpha() and name[0].islower():
            return True

        return False

    def find_research_codes(self, name: str) -> List[str]:
        """
        Find research codes for a drug given its generic name.

        Args:
            name: Generic drug name (e.g., 'dazukibart')

        Returns:
            List of research codes (e.g., ['PF-06823859'])
        """
        compound = self.search_by_name(name)
        if not compound:
            return []

        research_codes = []
        for synonym in compound.synonyms:
            if self.RESEARCH_CODE_PATTERN.match(synonym):
                research_codes.append(synonym.upper())

        return research_codes

    def are_same_compound(self, name1: str, name2: str) -> Tuple[bool, Optional[int]]:
        """
        Check if two drug names refer to the same compound.

        Args:
            name1: First drug name
            name2: Second drug name

        Returns:
            Tuple of (are_same, shared_cid)
        """
        compound1 = self.search_by_name(name1)
        compound2 = self.search_by_name(name2)

        if not compound1 or not compound2:
            return False, None

        if compound1.cid == compound2.cid:
            return True, compound1.cid

        return False, None

    def get_drug_info(self, name: str) -> Optional[Dict]:
        """
        Get comprehensive drug information for deduplication.

        Args:
            name: Drug name

        Returns:
            Dict with generic_name, research_codes, cid, synonyms
        """
        compound = self.search_by_name(name)
        if not compound:
            return None

        generic_name = self.find_generic_name(name)
        research_codes = [s for s in compound.synonyms if self.RESEARCH_CODE_PATTERN.match(s)]

        return {
            'cid': compound.cid,
            'generic_name': generic_name,
            'research_codes': research_codes[:10],
            'all_synonyms': compound.synonyms[:50],
            'molecular_formula': compound.molecular_formula,
        }


def find_duplicate_drugs(drug_names: List[str]) -> Dict[int, List[str]]:
    """
    Find groups of drug names that refer to the same compound.

    Args:
        drug_names: List of drug names to check

    Returns:
        Dict mapping CID to list of names that share that CID
    """
    client = PubChemClient()
    cid_to_names: Dict[int, List[str]] = {}

    for name in drug_names:
        compound = client.search_by_name(name)
        if compound:
            if compound.cid not in cid_to_names:
                cid_to_names[compound.cid] = []
            cid_to_names[compound.cid].append(name)

    # Return only groups with multiple names (actual duplicates)
    return {cid: names for cid, names in cid_to_names.items() if len(names) > 1}
