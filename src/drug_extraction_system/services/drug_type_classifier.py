"""
Drug Type Classifier Service

Classifies drugs into standardized drug types using:
1. INN (International Nonproprietary Name) suffix patterns
2. Claude API fallback for unknown patterns
"""

import logging
from typing import Optional, Dict, List
from enum import Enum

logger = logging.getLogger(__name__)


class DrugType(Enum):
    """Standardized drug type classifications."""
    # Biologics - Large molecules
    MAB = "mAb"  # Monoclonal antibody
    BISPECIFIC = "bispecific"  # Bispecific antibody
    ADC = "ADC"  # Antibody-drug conjugate
    FUSION_PROTEIN = "fusion protein"  # Fc-fusion proteins (e.g., etanercept)
    
    # Small Molecules
    SMALL_MOLECULE = "small molecule"  # Traditional small molecule drugs
    
    # Cell & Gene Therapies
    CAR_T = "CAR-T"  # Chimeric antigen receptor T-cell therapy
    CAR_NK = "CAR-NK"  # CAR Natural Killer cell therapy
    TCR_T = "TCR-T"  # T-cell receptor therapy
    TIL = "TIL"  # Tumor-infiltrating lymphocyte therapy
    GENE_THERAPY = "gene therapy"  # AAV, lentiviral vectors
    CELL_THERAPY = "cell therapy"  # Other cell-based therapies
    
    # Nucleic Acid Therapies
    SIRNA = "siRNA"  # Small interfering RNA
    ANTISENSE = "antisense"  # Antisense oligonucleotides
    MRNA = "mRNA"  # mRNA therapeutics
    OLIGONUCLEOTIDE = "oligonucleotide"  # Other oligonucleotides
    
    # Peptides & Proteins
    PEPTIDE = "peptide"  # Therapeutic peptides
    PROTEIN = "protein"  # Recombinant proteins (non-antibody)
    ENZYME = "enzyme"  # Enzyme replacement therapies
    
    # Vaccines
    VACCINE = "vaccine"  # Preventive and therapeutic vaccines
    
    # Radiopharmaceuticals
    RADIOPHARMACEUTICAL = "radiopharmaceutical"  # Radioligand therapies
    
    # Other
    BIOSIMILAR = "biosimilar"  # Biosimilar products (reference originator separately)
    OTHER = "other"  # Unclassified


# Valid drug types for validation
VALID_DRUG_TYPES = [dt.value for dt in DrugType]

# INN suffix patterns for classification
INN_SUFFIX_PATTERNS = {
    # Monoclonal antibodies
    "mab": DrugType.MAB,
    "umab": DrugType.MAB,  # Human mAb
    "zumab": DrugType.MAB,  # Humanized mAb
    "ximab": DrugType.MAB,  # Chimeric mAb
    "momab": DrugType.MAB,  # Mouse mAb
    
    # Fusion proteins
    "cept": DrugType.FUSION_PROTEIN,
    
    # Small molecule kinase inhibitors
    "nib": DrugType.SMALL_MOLECULE,
    "tinib": DrugType.SMALL_MOLECULE,
    "fenib": DrugType.SMALL_MOLECULE,
    "ciclib": DrugType.SMALL_MOLECULE,  # CDK inhibitors
    
    # Other small molecules
    "vir": DrugType.SMALL_MOLECULE,  # Antivirals
    "navir": DrugType.SMALL_MOLECULE,  # Protease inhibitors
    "previr": DrugType.SMALL_MOLECULE,  # HCV protease inhibitors
    "buvir": DrugType.SMALL_MOLECULE,  # HCV NS5B inhibitors
    "asvir": DrugType.SMALL_MOLECULE,  # HCV NS5A inhibitors
    "stat": DrugType.SMALL_MOLECULE,  # Statins
    "prazole": DrugType.SMALL_MOLECULE,  # PPIs
    "sartan": DrugType.SMALL_MOLECULE,  # ARBs
    "pril": DrugType.SMALL_MOLECULE,  # ACE inhibitors
    "olol": DrugType.SMALL_MOLECULE,  # Beta blockers
    "dipine": DrugType.SMALL_MOLECULE,  # Calcium channel blockers
    "oxacin": DrugType.SMALL_MOLECULE,  # Fluoroquinolones
    "mycin": DrugType.SMALL_MOLECULE,  # Macrolides
    "cycline": DrugType.SMALL_MOLECULE,  # Tetracyclines
    "azole": DrugType.SMALL_MOLECULE,  # Antifungals
    "gliptin": DrugType.SMALL_MOLECULE,  # DPP-4 inhibitors
    "gliflozin": DrugType.SMALL_MOLECULE,  # SGLT2 inhibitors
    "glutide": DrugType.PEPTIDE,  # GLP-1 agonists (peptides)
    
    # Peptides
    "tide": DrugType.PEPTIDE,
    "relix": DrugType.PEPTIDE,  # GnRH antagonists
    "relin": DrugType.PEPTIDE,  # GnRH agonists
    
    # Enzymes
    "ase": DrugType.ENZYME,
    
    # Gene therapies
    "vec": DrugType.GENE_THERAPY,  # Vectors
    "gene": DrugType.GENE_THERAPY,
    
    # Cell therapies (CAR-T products often end in -cel)
    "cel": DrugType.CAR_T,
    
    # siRNA/antisense
    "siran": DrugType.SIRNA,
    "ersen": DrugType.ANTISENSE,
}

# ADC payload indicators
ADC_PAYLOADS = [
    "vedotin", "deruxtecan", "ozogamicin", "emtansine",
    "ravtansine", "mafodotin", "govitecan", "tesirine",
    "calicheamicin", "duocarmycin", "pyrrolobenzodiazepine"
]


class DrugTypeClassifier:
    """
    Classifies drugs into standardized drug types.

    Uses a two-tier approach:
    1. INN suffix pattern matching (fast, no API calls)
    2. Claude API classification (fallback for unknown patterns)
    """

    def __init__(self, anthropic_client=None):
        """
        Initialize classifier.

        Args:
            anthropic_client: Optional Anthropic client for Claude API calls
        """
        self.anthropic = anthropic_client
        self._init_anthropic_if_needed()

    def _init_anthropic_if_needed(self):
        """Initialize Anthropic client if not provided."""
        if self.anthropic is None:
            try:
                import anthropic
                self.anthropic = anthropic.Anthropic()
                logger.info("Anthropic client initialized for drug type classification")
            except Exception as e:
                logger.warning(f"Could not initialize Anthropic client: {e}")
                self.anthropic = None

    def classify(self, drug_name: str, mechanism_of_action: str = None) -> Optional[str]:
        """
        Classify a drug into a standardized drug type.

        Args:
            drug_name: Drug name (generic/INN preferred)
            mechanism_of_action: Optional mechanism text for context

        Returns:
            Standardized drug type string, or None if classification fails
        """
        if not drug_name:
            return None

        name_lower = drug_name.lower().strip()

        # Step 1: Check for ADC patterns first (before mAb check)
        for payload in ADC_PAYLOADS:
            if payload in name_lower:
                logger.info(f"Classified '{drug_name}' as ADC (payload: {payload})")
                return DrugType.ADC.value

        # Step 2: Check INN suffix patterns
        drug_type = self._classify_by_suffix(name_lower)
        if drug_type:
            logger.info(f"Classified '{drug_name}' as {drug_type} (INN suffix)")
            return drug_type

        # Step 3: Fallback to Claude API
        if self.anthropic:
            drug_type = self._classify_with_claude(drug_name, mechanism_of_action)
            if drug_type:
                logger.info(f"Classified '{drug_name}' as {drug_type} (Claude API)")
                return drug_type

        logger.warning(f"Could not classify drug type for '{drug_name}'")
        return None

    def _classify_by_suffix(self, name_lower: str) -> Optional[str]:
        """Classify based on INN suffix patterns."""
        # Check suffixes in order of specificity (longer suffixes first)
        sorted_patterns = sorted(INN_SUFFIX_PATTERNS.keys(), key=len, reverse=True)

        for suffix in sorted_patterns:
            if name_lower.endswith(suffix):
                return INN_SUFFIX_PATTERNS[suffix].value

        # Special case: -cel for CAR-T but need to check it's not just ending in 'cel'
        if name_lower.endswith('cel') or '-cel' in name_lower:
            return DrugType.CAR_T.value

        return None

    def _classify_with_claude(self, drug_name: str, mechanism: str = None) -> Optional[str]:
        """Use Claude API to classify drug type."""
        try:
            # Build the prompt
            valid_types = ", ".join(VALID_DRUG_TYPES)

            context = f"Drug name: {drug_name}"
            if mechanism:
                context += f"\nMechanism of action: {mechanism}"

            prompt = f"""Classify the following drug into exactly ONE of these drug types:
{valid_types}

{context}

Instructions:
1. Use your knowledge of the drug to determine its type
2. If it's a monoclonal antibody, answer "mAb"
3. If it's an antibody-drug conjugate, answer "ADC"
4. If it's a bispecific antibody, answer "bispecific"
5. If it's a small molecule (oral pill, kinase inhibitor, etc.), answer "small molecule"
6. If it's a CAR-T cell therapy, answer "CAR-T"
7. If it's a gene therapy (AAV vector, etc.), answer "gene therapy"
8. If it's an siRNA or antisense oligonucleotide, answer appropriately
9. If you're unsure, answer "other"

Respond with ONLY the drug type, nothing else. No explanation needed."""

            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}]
            )

            result = response.content[0].text.strip().lower()

            # Validate the response
            for valid_type in VALID_DRUG_TYPES:
                if result == valid_type.lower():
                    return valid_type

            # Try to match partial responses
            result_normalized = result.replace("-", "").replace(" ", "")
            for valid_type in VALID_DRUG_TYPES:
                if valid_type.lower().replace("-", "").replace(" ", "") == result_normalized:
                    return valid_type

            logger.warning(f"Claude returned invalid drug type: '{result}'")
            return None

        except Exception as e:
            logger.error(f"Claude classification failed: {e}")
            return None

    def get_valid_types(self) -> List[str]:
        """Return list of valid drug types."""
        return VALID_DRUG_TYPES.copy()

