"""
Enhanced DailyMed Extractor

Improved extraction that actually populates all database tables:
- Infers drug type from drug name
- Extracts mechanism from label
- Normalizes manufacturer names
- Extracts and saves dosing regimens
- Saves formulation data
"""
import logging
import re
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET

from src.tools.dailymed import DailyMedAPI
from src.tools.drug_database import DrugDatabase
from src.utils.drug_standardization import (
    standardize_frequency,
    standardize_route,
    standardize_drug_type,
    clean_indication_name
)
from src.utils.drug_version_manager import DrugVersionHistory

logger = logging.getLogger(__name__)


class EnhancedDailyMedExtractor:
    """
    Enhanced extractor that fully populates drug database.
    """

    def __init__(self, drug_database: DrugDatabase):
        self.dailymed = DailyMedAPI()
        self.drug_db = drug_database
        self.drugs_com_scraper = None  # Lazy initialization

    def extract_and_store_drug(
        self,
        drug_name: str,
        save_to_database: bool = True,
        overwrite: bool = False
    ) -> Optional[Dict]:
        """
        Extract drug with full data extraction.

        NEW FLOW (improved):
        1. Try Drugs.com FIRST for indications + approval dates (more reliable)
        2. Get DailyMed label for dosing + other metadata
        3. Match dosing to Drugs.com indications
        4. Fallback to DailyMed Section 1 if Drugs.com unavailable

        Args:
            drug_name: Drug brand name to extract
            save_to_database: Whether to save to database
            overwrite: If True, delete and recreate existing drug data
        """
        logger.info(f"Extracting (enhanced) DailyMed data for: {drug_name}")

        # Step 1: Try Drugs.com FIRST for indications + approval dates
        drugs_com_indications = self._get_indications_from_drugs_com(drug_name)

        if drugs_com_indications:
            logger.info(f"✓ Using Drugs.com as PRIMARY source for {len(drugs_com_indications)} indications")
            indication_source = "Drugs.com"
        else:
            logger.info("⚠ Drugs.com unavailable - will use DailyMed Section 1 as fallback")
            indication_source = "DailyMed"

        # Step 2: Get DailyMed SetID and label (needed for dosing + metadata)
        setid = self.dailymed.search_drug(drug_name)
        if not setid:
            logger.warning(f"No DailyMed data found for {drug_name}")
            return None

        # Get full label XML
        label_xml = self.dailymed.get_drug_label(setid)
        if not label_xml:
            logger.warning(f"Could not retrieve label for {drug_name}")
            return None

        # Step 3: Parse label (will use Drugs.com indications if available, otherwise DailyMed Section 1)
        structured_data = self._parse_full_label(
            label_xml,
            drug_name,
            setid,
            drugs_com_indications=drugs_com_indications
        )

        # Save to database
        if save_to_database:
            try:
                drug_id = self._save_complete_drug_data(structured_data, label_xml, overwrite=overwrite)
                structured_data["drug_id"] = drug_id
                action = "Overwrote" if overwrite else "Saved"
                logger.info(f"✓ {action} {drug_name} to database (ID: {drug_id})")
            except Exception as e:
                logger.error(f"Failed to save {drug_name}: {e}")
                import traceback
                traceback.print_exc()
                return None

        return structured_data

    def _parse_full_label(
        self,
        label_xml: str,
        drug_name: str,
        setid: str,
        drugs_com_indications: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Comprehensive label parsing.

        Args:
            label_xml: DailyMed label XML
            drug_name: Drug name
            setid: DailyMed SetID
            drugs_com_indications: Indications from Drugs.com (if available)

        Returns:
            Structured drug data
        """
        try:
            root = ET.fromstring(label_xml)

            # Extract basic info
            brand_name = drug_name
            generic_name = None
            manufacturer = None
            active_ingredients = []
            routes = []
            indications = []
            indications_with_approval = []  # NEW: Track approval data
            dosing_regimens = []
            mechanism = None

            # Extract active ingredients (generic name)
            # The SPL XML distinguishes active vs inactive ingredients via classCode:
            # - classCode="ACTIM" or "ACTIB" = Active ingredient
            # - classCode="IACT" = Inactive ingredient
            # We should only use active ingredients for the generic name

            # Method 1: Look for ingredients with classCode="ACTIM" or "ACTIB" (active moiety/base)
            for ingredient in root.findall('.//{urn:hl7-org:v3}ingredient'):
                class_code = ingredient.get('classCode', '')
                if class_code in ('ACTIM', 'ACTIB'):  # Active moiety or active base
                    # Look for the name within ingredientSubstance
                    substance = ingredient.find('.//{urn:hl7-org:v3}ingredientSubstance')
                    if substance is not None:
                        name_elem = substance.find('.//{urn:hl7-org:v3}name')
                        if name_elem is not None and name_elem.text:
                            active_ingredients.append(name_elem.text.strip())

            # Method 2: Fallback to activeMoiety elements (the actual drug molecule name)
            if not active_ingredients:
                for moiety in root.findall('.//{urn:hl7-org:v3}activeMoiety'):
                    inner_moiety = moiety.find('.//{urn:hl7-org:v3}activeMoiety')
                    if inner_moiety is not None:
                        name_elem = inner_moiety.find('.//{urn:hl7-org:v3}name')
                        if name_elem is not None and name_elem.text:
                            active_ingredients.append(name_elem.text.strip())

            # Method 3: Fallback to genericMedicine element
            if not active_ingredients:
                for med in root.findall('.//{urn:hl7-org:v3}genericMedicine'):
                    name_elem = med.find('.//{urn:hl7-org:v3}name')
                    if name_elem is not None and name_elem.text:
                        active_ingredients.append(name_elem.text.strip())

            # Method 4: Last resort - use first ingredient (old behavior, may include inactive)
            if not active_ingredients:
                for ingredient in root.findall('.//{urn:hl7-org:v3}ingredient'):
                    substance = ingredient.find('.//{urn:hl7-org:v3}ingredientSubstance')
                    if substance is not None:
                        name_elem = substance.find('.//{urn:hl7-org:v3}name')
                        if name_elem is not None and name_elem.text:
                            active_ingredients.append(name_elem.text.strip())
                            break  # Only take first as last resort

            if active_ingredients:
                generic_name = active_ingredients[0].lower()
                logger.info(f"Extracted generic name: {generic_name} (from {len(active_ingredients)} active ingredients)")

            # Extract manufacturer
            for org in root.findall('.//{urn:hl7-org:v3}representedOrganization'):
                name_elem = org.find('.//{urn:hl7-org:v3}name')
                if name_elem is not None and name_elem.text:
                    manufacturer = self._normalize_manufacturer(name_elem.text.strip())
                    break

            # Extract routes
            for route in root.findall('.//{urn:hl7-org:v3}routeCode'):
                display_name = route.get('displayName')
                if display_name:
                    route_std, _ = standardize_route(display_name)
                    if route_std and route_std not in routes:
                        routes.append(route_std)

            # NEW APPROACH: Use Drugs.com as PRIMARY source when available (has approval dates)
            # Fallback to DailyMed Section 1 only if Drugs.com unavailable
            if drugs_com_indications:
                logger.info(f"Using Drugs.com as PRIMARY source for {len(drugs_com_indications)} indications")
                for dc_ind in drugs_com_indications:
                    indication_name = dc_ind.get("indication", "")
                    indication_cleaned = clean_indication_name(indication_name, brand_name, generic_name)
                    indications.append(indication_cleaned)

                    indications_with_approval.append({
                        "indication": indication_cleaned,
                        "indication_raw": indication_name,  # Store original Drugs.com text
                        "approval_year": dc_ind.get("approval_year"),
                        "approval_date": dc_ind.get("approval_date"),
                        "source": "Drugs.com",
                        "severity_mild": dc_ind.get("severity_mild", False),
                        "severity_moderate": dc_ind.get("severity_moderate", False),
                        "severity_severe": dc_ind.get("severity_severe", False)
                    })
            else:
                # FALLBACK: Extract from DailyMed Section 1 if Drugs.com unavailable
                logger.info("Drugs.com unavailable - extracting from DailyMed Section 1 (FDA label)")

                for section in root.findall('.//{urn:hl7-org:v3}section'):
                    code = section.find('.//{urn:hl7-org:v3}code')
                    if code is not None and code.get('code') == '34067-9':  # Indications
                        # Check if section has subsections (typical structure)
                        subsections = section.findall('.//{urn:hl7-org:v3}section')

                        if subsections:
                            # Each subsection is typically one indication
                            for subsec in subsections:
                                text_elem = subsec.find('.//{urn:hl7-org:v3}text')
                                if text_elem is not None:
                                    subsec_text = ''.join(text_elem.itertext()).strip()

                                    # Extract disease from this subsection
                                    diseases = self._extract_diseases_from_text(subsec_text)

                                    # Extract severity from subsection text
                                    severity = self._extract_severity_from_text(subsec_text)

                                    # Clean each disease name before adding
                                    for disease in diseases:
                                        disease_cleaned = clean_indication_name(disease, brand_name, generic_name)
                                        indications.append(disease_cleaned)

                                        # Store with severity data (no approval data from DailyMed fallback)
                                        indications_with_approval.append({
                                            "indication": disease_cleaned,
                                            "approval_year": None,
                                            "approval_date": None,
                                            "source": "DailyMed",
                                            "severity_mild": severity.get("severity_mild", False),
                                            "severity_moderate": severity.get("severity_moderate", False),
                                            "severity_severe": severity.get("severity_severe", False)
                                        })
                        else:
                            # No subsections, extract from main section text
                            text_elem = section.find('.//{urn:hl7-org:v3}text')
                            if text_elem is not None:
                                ind_text = ''.join(text_elem.itertext()).strip()
                                diseases = self._extract_diseases_from_text(ind_text)

                                # Extract severity from main section text
                                severity = self._extract_severity_from_text(ind_text)

                                # Clean each disease name before adding
                                for disease in diseases:
                                    disease_cleaned = clean_indication_name(disease, brand_name, generic_name)
                                    indications.append(disease_cleaned)

                                    # Store with severity data (no approval data from DailyMed fallback)
                                    indications_with_approval.append({
                                        "indication": disease_cleaned,
                                        "approval_year": None,
                                        "approval_date": None,
                                        "source": "DailyMed",
                                        "severity_mild": severity.get("severity_mild", False),
                                        "severity_moderate": severity.get("severity_moderate", False),
                                        "severity_severe": severity.get("severity_severe", False)
                                    })

                        break  # Only process first indications section

            # Extract dosing (simplified pattern matching)
            dosing_regimens = self._extract_dosing_patterns(label_xml, brand_name, generic_name)

            # Infer drug type
            drug_type = self._infer_drug_type(brand_name, generic_name or "", active_ingredients)

            # Extract/infer mechanism
            mechanism = self._extract_mechanism(label_xml, brand_name, drug_type)

            return {
                "brand_name": brand_name,
                "generic_name": generic_name or brand_name.lower(),
                "manufacturer": manufacturer,
                "drug_type": drug_type,
                "mechanism_of_action": mechanism,
                "approval_status": "approved",
                "highest_phase": "Approved",
                "dailymed_setid": setid,
                "routes": routes,
                "active_ingredients": active_ingredients,
                "indications": indications,
                "indications_with_approval": indications_with_approval,  # NEW: Includes approval data
                "dosing_regimens": dosing_regimens
            }

        except Exception as e:
            logger.error(f"Error parsing label: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _normalize_manufacturer(self, manufacturer: str) -> str:
        """
        Normalize manufacturer names.
        """
        # Remove common suffixes
        normalized = manufacturer
        suffixes = [
            " Pharmaceuticals Corporation",
            " Pharmaceutical Corporation",
            " Pharmaceuticals",
            " Pharmaceutical",
            " Corporation",
            " Corp.",
            ", Inc.",
            " Inc.",
            " LLC",
            " Ltd.",
            " Limited"
        ]

        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]

        return normalized.strip()

    def _normalize_indication(self, indication: str) -> str:
        """
        Normalize indication names for better matching.

        Removes common modifiers and prefixes to create a canonical form.

        Args:
            indication: Raw indication name

        Returns:
            Normalized indication name
        """
        normalized = indication.lower().strip()

        # Remove common prefixes (order matters - longer prefixes first)
        prefixes = [
            "pediatric patients living with to ",
            "adult patients living with to ",
            "pediatric patients living with ",
            "adult patients living with ",
            "adult patients with ",
            "pediatric patients with ",
            "patients living with to ",
            "patients living with ",
            "patients with ",
            "adults with ",
            "children with ",
            "treatment of ",
        ]

        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break  # Only remove one prefix

        # Remove leading "to" after prefix removal
        normalized = re.sub(r'^\s*to\s+', '', normalized)

        # Remove common modifiers
        modifiers = r'\b(active|chronic|acute|severe|moderate|moderately|severely|mild)\s+'
        normalized = re.sub(modifiers, '', normalized).strip()

        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', normalized)

        return normalized

    def _match_indication_to_drugs_com(
        self,
        dailymed_indication: str,
        drugs_com_indications: List[Dict]
    ) -> Optional[Dict]:
        """
        Match a DailyMed indication name to Drugs.com approval data using fuzzy matching.

        This allows us to use DailyMed Section 1 as the PRIMARY source for indication names
        while still getting approval dates from Drugs.com.

        Args:
            dailymed_indication: Indication name from DailyMed Section 1
            drugs_com_indications: List of indications from Drugs.com with approval data

        Returns:
            Matched Drugs.com indication dict with approval_year and approval_date, or None
        """
        dailymed_norm = self._normalize_indication(dailymed_indication)

        # Try direct match first
        for drugs_com_ind in drugs_com_indications:
            drugs_com_norm = drugs_com_ind.get("indication_normalized", "")
            if dailymed_norm == drugs_com_norm:
                logger.debug(f"Direct match: '{dailymed_indication}' → '{drugs_com_ind['indication']}'")
                return drugs_com_ind

        # Try substring match
        for drugs_com_ind in drugs_com_indications:
            drugs_com_norm = drugs_com_ind.get("indication_normalized", "")
            # Check if one is a substring of the other
            if dailymed_norm in drugs_com_norm or drugs_com_norm in dailymed_norm:
                logger.debug(f"Substring match: '{dailymed_indication}' → '{drugs_com_ind['indication']}'")
                return drugs_com_ind

        # No match found
        logger.debug(f"No Drugs.com match for: '{dailymed_indication}'")
        return None

    def _extract_severity_from_text(self, text: str) -> Dict[str, bool]:
        """
        Extract severity flags (mild, moderate, severe) from indication text.

        Args:
            text: Raw indication text

        Returns:
            Dictionary with severity flags:
            {
                "severity_mild": bool,
                "severity_moderate": bool,
                "severity_severe": bool
            }

        Logic:
        - If "moderate to severe" or "moderately to severely" → moderate + severe
        - If "mild to moderate" → mild + moderate
        - If individual severity mentions → set those flags
        - If NO severity mentioned (e.g., "active psoriatic arthritis") → ALL severities (default)
        """
        text_lower = text.lower()

        severity = {
            "severity_mild": False,
            "severity_moderate": False,
            "severity_severe": False
        }

        has_severity_mention = False

        # Pattern 1: "moderate to severe" or "moderately to severely"
        if "moderate to severe" in text_lower or "moderately to severely" in text_lower:
            severity["severity_moderate"] = True
            severity["severity_severe"] = True
            has_severity_mention = True
            return severity

        # Pattern 2: "moderate-to-severe" or "moderately-to-severely"
        if "moderate-to-severe" in text_lower or "moderately-to-severely" in text_lower:
            severity["severity_moderate"] = True
            severity["severity_severe"] = True
            has_severity_mention = True
            return severity

        # Pattern 3: "mild to moderate"
        if "mild to moderate" in text_lower:
            severity["severity_mild"] = True
            severity["severity_moderate"] = True
            has_severity_mention = True
            return severity

        # Pattern 4: Individual severity mentions
        if re.search(r'\b(severe|severely)\b', text_lower):
            severity["severity_severe"] = True
            has_severity_mention = True

        if re.search(r'\b(moderate|moderately)\b', text_lower):
            severity["severity_moderate"] = True
            has_severity_mention = True

        if re.search(r'\bmild\b', text_lower):
            severity["severity_mild"] = True
            has_severity_mention = True

        # NEW: If no severity mentioned, default to ALL severities
        # Example: "active psoriatic arthritis" (no severity) → all severities
        if not has_severity_mention:
            severity["severity_mild"] = True
            severity["severity_moderate"] = True
            severity["severity_severe"] = True

        return severity

    def _extract_severity_from_dailymed_section1(self, label_xml: str, brand_name: str, generic_name: str) -> Dict[str, Dict]:
        """
        Extract severity information from DailyMed Section 1 for all indications.

        Returns a mapping of indication_name → severity dict.
        This is used to supplement Drugs.com data which often lacks severity markers.

        Args:
            label_xml: DailyMed label XML
            brand_name: Brand name for cleaning indication names
            generic_name: Generic name for cleaning indication names

        Returns:
            Dict mapping indication_name (cleaned, lowercase) to severity dict:
            {
                "rheumatoid arthritis": {
                    "severity_mild": False,
                    "severity_moderate": True,
                    "severity_severe": True
                },
                ...
            }
        """
        severity_mapping = {}

        try:
            root = ET.fromstring(label_xml)

            # Find Section 1 - Indications and Usage (code 34067-9)
            for section in root.findall('.//{urn:hl7-org:v3}section'):
                code = section.find('.//{urn:hl7-org:v3}code')
                if code is not None and code.get('code') == '34067-9':  # Indications
                    # Check if section has subsections (typical structure)
                    subsections = section.findall('.//{urn:hl7-org:v3}section')

                    if subsections:
                        # Each subsection is typically one indication
                        for subsec in subsections:
                            text_elem = subsec.find('.//{urn:hl7-org:v3}text')
                            if text_elem is not None:
                                subsec_text = ''.join(text_elem.itertext()).strip()

                                # Extract disease names from this subsection
                                diseases = self._extract_diseases_from_text(subsec_text)

                                # Extract severity from subsection text
                                severity = self._extract_severity_from_text(subsec_text)

                                # Map each disease to its severity
                                for disease in diseases:
                                    disease_cleaned = clean_indication_name(disease, brand_name, generic_name)
                                    disease_key = disease_cleaned.lower().strip()
                                    severity_mapping[disease_key] = severity

                    break  # Only process first indications section

        except Exception as e:
            logger.warning(f"Failed to extract severity from DailyMed Section 1: {e}")

        return severity_mapping

    def _get_indications_from_drugs_com(self, drug_name: str) -> Optional[List[Dict]]:
        """
        Get indications and approval dates from Drugs.com.

        This is the PRIMARY source for indications + approval data.

        Args:
            drug_name: Drug brand name

        Returns:
            List of indications with approval data:
            [
                {
                    "indication": "rheumatoid arthritis",
                    "indication_normalized": "rheumatoid arthritis",
                    "approval_year": 2002,
                    "approval_date": "2002-12-31",
                    "source": "Drugs.com"
                },
                ...
            ]
            Returns None if Drugs.com is unavailable
        """
        try:
            # Lazy init scraper
            if not self.drugs_com_scraper:
                from src.tools.drugs_com_scraper import DrugsComScraper
                self.drugs_com_scraper = DrugsComScraper()

            # Try the user-provided name first
            approval_events = self.drugs_com_scraper.get_approval_timeline(drug_name)

            # If not found, try the official brand name from DailyMed
            # (e.g., "nurtec" -> "NURTEC ODT")
            if not approval_events:
                official_name = self.dailymed.get_official_brand_name(drug_name)
                if official_name and official_name.lower() != drug_name.lower():
                    logger.info(f"Trying official brand name from DailyMed: {official_name}")
                    approval_events = self.drugs_com_scraper.get_approval_timeline(official_name)

            if not approval_events:
                logger.info(f"Drugs.com: no approval data for {drug_name}")
                return None

            logger.info(f"Drugs.com: found {len(approval_events)} indications for {drug_name}")

            # Convert to indication format
            indications = []
            seen = set()

            for event in approval_events:
                indication = event["indication"]
                indication_normalized = self._normalize_indication(indication)

                # Deduplicate by normalized name
                if indication_normalized in seen:
                    continue

                seen.add(indication_normalized)

                # Extract severity flags from indication text
                severity = self._extract_severity_from_text(indication)

                indications.append({
                    "indication": indication,  # Original from Drugs.com
                    "indication_normalized": indication_normalized,
                    "approval_year": event.get("year"),
                    "approval_date": event.get("approval_date"),
                    "source": "Drugs.com",
                    **severity  # Add severity flags
                })

            return indications

        except Exception as e:
            logger.warning(f"Failed to get indications from Drugs.com: {e}")
            return None

    def _infer_drug_type(
        self,
        brand_name: str,
        generic_name: str,
        active_ingredients: List[str]
    ) -> Optional[str]:
        """
        Infer drug type from naming patterns.
        """
        name_lower = (brand_name + " " + generic_name).lower()

        # mAb patterns (check for -mab suffix, 'mab ' with space, or ending with 'mab')
        is_mab = any(pattern in name_lower for pattern in ['-mab', 'mab ']) or name_lower.endswith('mab')

        if is_mab:
            # Check for specific mAb subtypes
            if 'bispecific' in name_lower:
                return "bispecific"
            elif any(x in name_lower for x in ['vedotin', 'deruxtecan', 'ozogamicin']):
                return "ADC"
            else:
                return "mAb"

        # Small molecule patterns
        if any(pattern in name_lower for pattern in ['-ib', '-inib', '-tinib']):
            return "small molecule"

        # Gene therapy
        if 'gene therapy' in name_lower or any(x in brand_name.lower() for x in ['zolgensma', 'luxturna']):
            return "gene therapy"

        # CAR-T
        if any(x in brand_name.lower() for x in ['kymriah', 'yescarta', 'tecartus', 'breyanzi']):
            return "CAR-T"

        # Vaccine
        if 'vaccine' in name_lower:
            return "vaccine"

        # Peptide
        if 'tide' in generic_name:
            return "peptide"

        # Default to small molecule for now
        return "small molecule"

    def _extract_mechanism(
        self,
        label_xml: str,
        brand_name: str,
        drug_type: str
    ) -> Optional[str]:
        """
        Extract or infer mechanism of action.

        Uses drug-clarity's improved approach:
        1. Look in DESCRIPTION section first (most reliable)
        2. Look in CLINICAL PHARMACOLOGY section
        3. Use multiple regex patterns
        4. Fallback to name-based inference
        """
        try:
            root = ET.fromstring(label_xml)

            # Priority 1: Look in DESCRIPTION section (drug-clarity approach)
            for section in root.findall('.//{urn:hl7-org:v3}section'):
                title = section.find('.//{urn:hl7-org:v3}title')
                if title is not None and title.text and 'description' in title.text.lower():
                    text_elem = section.find('.//{urn:hl7-org:v3}text')
                    if text_elem is not None:
                        desc_text = ''.join(text_elem.itertext()).strip().lower()

                        # Try multiple patterns (from drug-clarity)
                        patterns = [
                            r'is\s+an?\s+([^.]*?)\s+(?:inhibitor|agonist|antagonist|modulator|blocker)',
                            r'works\s+by\s+([^.]*?)(?:\.|,)',
                            r'mechanism\s+of\s+action[:\s]+([^.]*?)(?:\.|,)',
                            r'acts\s+as\s+an?\s+([^.]*?)(?:\.|,)',
                            r'(?:inhibitor|agonist|antagonist|blocker)\s+of\s+([^.]*?)(?:\.|,)'
                        ]

                        for pattern in patterns:
                            match = re.search(pattern, desc_text, re.IGNORECASE)
                            if match and match.group(1):
                                mechanism = match.group(1).strip()
                                # Clean up and return if reasonable length
                                if 5 < len(mechanism) < 200:
                                    return mechanism

            # Priority 2: Look for "Mechanism of Action" or "Clinical Pharmacology" sections
            for section in root.findall('.//{urn:hl7-org:v3}section'):
                title = section.find('.//{urn:hl7-org:v3}title')
                if title is not None and title.text and ('mechanism' in title.text.lower() or 'clinical pharmacology' in title.text.lower()):
                    text_elem = section.find('.//{urn:hl7-org:v3}text')
                    if text_elem is not None:
                        mech_text = ''.join(text_elem.itertext()).strip()
                        # Extract first sentence
                        first_sentence = mech_text.split('.')[0][:200]
                        if len(first_sentence) > 10:
                            return first_sentence.strip()

            # Priority 3: Fallback to name-based inference
            return self._infer_mechanism_from_name(brand_name, drug_type)

        except Exception as e:
            logger.warning(f"Mechanism extraction failed: {e}")
            return self._infer_mechanism_from_name(brand_name, drug_type)

    def _infer_mechanism_from_name(self, brand_name: str, drug_type: str) -> Optional[str]:
        """
        Infer mechanism from drug name patterns.
        """
        name_lower = brand_name.lower()

        # Common mAb patterns
        mab_mechanisms = {
            'adalimumab': 'TNF-alpha inhibitor',
            'humira': 'TNF-alpha inhibitor',
            'infliximab': 'TNF-alpha inhibitor',
            'remicade': 'TNF-alpha inhibitor',
            'etanercept': 'TNF-alpha inhibitor',
            'enbrel': 'TNF-alpha inhibitor',
            'secukinumab': 'IL-17A inhibitor',
            'cosentyx': 'IL-17A inhibitor',
            'ixekizumab': 'IL-17A inhibitor',
            'taltz': 'IL-17A inhibitor',
            'ustekinumab': 'IL-12/IL-23 inhibitor',
            'stelara': 'IL-12/IL-23 inhibitor',
            'pembrolizumab': 'PD-1 inhibitor',
            'keytruda': 'PD-1 inhibitor',
            'nivolumab': 'PD-1 inhibitor',
            'opdivo': 'PD-1 inhibitor',
        }

        for key, mechanism in mab_mechanisms.items():
            if key in name_lower:
                return mechanism

        # Generic fallback
        if drug_type == "mAb":
            return "monoclonal antibody therapy"
        elif drug_type == "small molecule":
            return "small molecule inhibitor"

        return None

    def _extract_diseases_from_text(self, text: str) -> List[str]:
        """
        Extract disease names from indication text.

        Generic extraction based on common DailyMed phrasing patterns.
        Works for any drug, not just specific hardcoded diseases.
        """
        diseases = []

        # Normalize text: fix encoding issues with apostrophes and special characters
        # Replace replacement character (�) and other Unicode apostrophe variants with standard apostrophe
        text = text.replace('\ufffd', "'")  # Replacement character
        text = text.replace('\u2019', "'")  # Right single quotation mark
        text = text.replace('\u2018', "'")  # Left single quotation mark
        text = text.replace('\u201c', '"')  # Left double quotation mark
        text = text.replace('\u201d', '"')  # Right double quotation mark

        # Clean up whitespace and newlines
        text = re.sub(r'\s+', ' ', text)

        # Pattern 1: "treatment of [disease]"
        # Captures: "treatment of Crohn's disease", "treatment of moderate to severe plaque psoriasis"
        pattern1 = r"treatment of\s+(?:moderately to severely active\s+|moderate to severe\s+|active\s+|chronic\s+|acute\s+)?([a-zA-Z'\s-]+?)(?:\s+in\s+(?:adult|pediatric|patients)|\.|\(|;|$)"
        matches = re.findall(pattern1, text, re.IGNORECASE)
        for match in matches:
            disease = match.strip()
            if len(disease) > 4 and not any(skip in disease.lower() for skip in ['indicated', 'treatment', 'reducing']):
                diseases.append(disease)

        # Pattern 2: "reducing signs and symptoms... in patients with [disease]"
        # Captures the disease after "with", "in patients with", etc.
        pattern2 = r"(?:in (?:adult|pediatric)? ?patients with|signs and symptoms[^.]{0,50}?\s+with)\s+(?:moderately to severely active\s+|moderate to severe\s+|active\s+)?([a-zA-Z'\s-]+?)(?:\.|\(|$)"
        matches = re.findall(pattern2, text, re.IGNORECASE)
        for match in matches:
            disease = match.strip()
            if len(disease) > 4:
                diseases.append(disease)

        # Pattern 3: "indicated for [disease]"
        pattern3 = r"indicated for\s+(?:the\s+)?(?:treatment of\s+)?(?:reducing[^.]{0,30}?\s+)?(?:moderately to severely active\s+|moderate to severe\s+|active\s+)?([a-zA-Z'\s-]+?)(?:\s+in\s+(?:adult|pediatric|patients)|\.|\(|;|$)"
        matches = re.findall(pattern3, text, re.IGNORECASE)
        for match in matches:
            disease = match.strip()
            if len(disease) > 4:
                diseases.append(disease)

        # Pattern 4: Look for capitalized multi-word disease names
        # This catches "Crohn's Disease", "Rheumatoid Arthritis", etc.
        # Only keep if they contain disease-related keywords
        capitalized_pattern = r'\b([A-Z][a-z]+(?:\'s)?\s+(?:[a-z]+\s+)?(?:disease|arthritis|colitis|psoriasis|spondylitis|uveitis|syndrome|disorder))\b'
        matches = re.findall(capitalized_pattern, text, re.IGNORECASE)
        for match in matches:
            diseases.append(match)

        # Pattern 5: Look for common disease name structures with apostrophes
        # e.g., "Crohn's", "Grave's", "Parkinson's" (when followed by context)
        apostrophe_pattern = r"\b([A-Z][a-z]+\'s)\b"
        matches = re.findall(apostrophe_pattern, text)
        for match in matches:
            # Add "disease" if it seems to be referring to a disease
            if match.lower() not in ['patient\'s', 'doctor\'s', 'physician\'s']:
                diseases.append(f"{match} disease")

        # Clean up extracted diseases
        cleaned_diseases = []
        for disease in diseases:
            disease = disease.strip()

            # Remove trailing articles and prepositions
            disease = re.sub(r'\s+(and|or|with|the|a|an)$', '', disease, flags=re.IGNORECASE).strip()

            # Remove "in adult" / "in pediatric" suffixes
            disease = re.sub(r'\s+in\s+(adult|pediatric).*$', '', disease, flags=re.IGNORECASE).strip()

            # Skip if contains unwanted words or phrases
            skip_words = ['indicated', 'reducing', 'improving', 'inhibiting', 'inducing', 'progression',
                         'signs and symptoms', 'biologic', 'major clinical', 'physical function']
            if any(skip in disease.lower() for skip in skip_words):
                continue

            # Skip if too short or too generic
            if len(disease) < 5:
                continue

            # Skip if it's just descriptive text (no disease keywords)
            # Valid diseases should have at least one of these keywords or be capitalized
            has_disease_keyword = any(kw in disease.lower() for kw in [
                'disease', 'arthritis', 'colitis', 'psoriasis', 'spondylitis', 'uveitis',
                'syndrome', 'disorder', 'infection', 'cancer', 'diabetes', 'asthma',
                'dermatitis', 'hepatitis', 'nephritis', 'lupus', 'sclerosis',
                'suppurativa',  # hidradenitis suppurativa
                'myeloma', 'lymphoma', 'leukemia', 'sarcoma', 'carcinoma',  # cancer types
                # Neurological conditions
                'migraine', 'headache', 'epilepsy', 'seizure', 'neuropathy', 'neuralgia',
                'parkinson', 'alzheimer', 'dementia', 'stroke', 'tremor',
                # Cardiovascular
                'hypertension', 'heart failure', 'arrhythmia', 'angina', 'thrombosis',
                # Respiratory
                'copd', 'bronchitis', 'pneumonia', 'fibrosis',
                # Gastrointestinal
                'crohn', 'ibd', 'gerd', 'reflux', 'ulcer',
                # Autoimmune/Inflammatory
                'eczema', 'alopecia', 'vitiligo', 'myasthenia',
                # Metabolic
                'obesity', 'hyperlipidemia', 'gout',
                # Pain/Musculoskeletal
                'fibromyalgia', 'osteoporosis',
                # Psychiatric
                'depression', 'anxiety', 'schizophrenia', 'bipolar',
                # Other common indications
                'anemia', 'hiv', 'aids', 'malaria', 'tuberculosis'
            ])

            # Or starts with capital letter (proper noun, likely a disease name)
            is_capitalized = disease[0].isupper() if disease else False

            if not (has_disease_keyword or is_capitalized):
                continue

            cleaned_diseases.append(disease)

        # Deduplicate using normalized form (strips modifiers like "active", "chronic", etc.)
        # But keep the PREFERRED form (shortest/cleanest version) in the output
        unique_diseases = []
        seen_normalized = {}  # Maps normalized → preferred original form

        for disease in cleaned_diseases:
            # Normalize to create deduplication key (removes "active", "chronic", etc.)
            disease_normalized = self._normalize_indication(disease)

            if disease_normalized not in seen_normalized:
                # First time seeing this disease - add it
                seen_normalized[disease_normalized] = disease.strip()
            else:
                # Already seen this disease - keep the shorter/cleaner version
                # Prefer "ulcerative colitis" over "active ulcerative colitis"
                existing = seen_normalized[disease_normalized]
                current = disease.strip()

                # Prefer the version with fewer words (usually the one without modifiers)
                if len(current.split()) < len(existing.split()):
                    seen_normalized[disease_normalized] = current

        # Return the preferred forms
        unique_diseases = list(seen_normalized.values())
        return unique_diseases

    def _extract_dosing_patterns(self, label_xml: str, brand_name: str = None, generic_name: str = None) -> List[Dict]:
        """
        Extract dosing regimens from Section 2 (Dosage and Administration).

        Parses XML structure to find subsections for each indication,
        then extracts dosing information per indication.

        Args:
            label_xml: DailyMed label XML
            brand_name: Brand name for cleaning indication names (optional)
            generic_name: Generic name for cleaning indication names (optional)

        Returns list of dicts with: dose_amount, dose_unit, frequency_raw,
        frequency_standard, regimen_phase, indication_name (for matching later)
        """
        try:
            root = ET.fromstring(label_xml)
            dosing_regimens = []

            # Find Section 2 - Dosage and Administration (code 34068-7)
            for section in root.findall('.//{urn:hl7-org:v3}section'):
                code = section.find('.//{urn:hl7-org:v3}code')
                if code is not None and code.get('code') == '34068-7':  # Dosage section

                    # Check for subsections (typically organized by indication)
                    # Use .// to find all descendant sections, not just direct children
                    subsections = section.findall('.//{urn:hl7-org:v3}section')

                    if subsections:
                        # Process each subsection (usually one per indication)
                        for subsec in subsections:
                            title_elem = subsec.find('./{urn:hl7-org:v3}title')
                            text_elem = subsec.find('./{urn:hl7-org:v3}text')

                            if text_elem is not None:
                                subsec_text = ''.join(text_elem.itertext())
                                subsec_text_clean = re.sub(r'\s+', ' ', subsec_text)

                                # Extract indication from title if available
                                indication_name = None
                                if title_elem is not None:
                                    # Use itertext() to get all text including from child elements
                                    title_text = ''.join(title_elem.itertext()).strip()
                                    if title_text:
                                        # Parse titles like "2.2 Recommended Dosage in Rheumatoid Arthritis"
                                        indication_match = re.search(r'(?:in|for)\s+(.+?)(?:\s*$)', title_text, re.IGNORECASE)
                                        if indication_match:
                                            indication_name = indication_match.group(1).strip()
                                            # Clean up common prefixes
                                            indication_name = re.sub(r'^(adult|pediatric|patients with|adults with|children with)\s+', '', indication_name, flags=re.IGNORECASE).strip()
                                            # Clean indication name (same cleaning as Section 1) to ensure proper matching
                                            indication_name = clean_indication_name(indication_name, brand_name, generic_name)

                                # Extract dosing patterns from this subsection
                                subsec_dosing = self._extract_dosing_from_text(subsec_text_clean)

                                # Add indication name to each dosing entry
                                for dosing in subsec_dosing:
                                    dosing['indication_name'] = indication_name
                                    dosing_regimens.append(dosing)
                    else:
                        # No subsections - extract from main section text
                        # FIX: Use .// to search all descendants, not just direct children
                        text_elem = section.find('.//{urn:hl7-org:v3}text')
                        if text_elem is not None:
                            section_text = ''.join(text_elem.itertext())
                            section_text_clean = re.sub(r'\s+', ' ', section_text)
                            dosing_regimens.extend(self._extract_dosing_from_text(section_text_clean))

                    break  # Only process first dosage section

            # Deduplicate while preserving indication association
            unique_dosing = []
            seen = set()
            for d in dosing_regimens:
                key = (d['dose_amount'], d['frequency_raw'], d['regimen_phase'], d.get('indication_name'))
                if key not in seen:
                    seen.add(key)
                    unique_dosing.append(d)

            return unique_dosing

        except Exception as e:
            logger.error(f"Could not extract dosing: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _extract_week_based_loading(self, text: str) -> List[Dict]:
        """
        Extract week-based loading doses.

        Examples:
        - "160 mg at Week 0"
        - "80 mg at Weeks 2, 4, 6, 8, 10, and 12"
        - "160 mg (two 80 mg injections) at Week 0, followed by 80 mg at Weeks 2, 4..."

        Returns list of dosing dicts with regimen_phase="loading"
        """
        dosing = []

        # Pattern 1: Single week - "N mg at Week X"
        pattern_single = r'(\d+)\s*mg[^,]*?\s+at\s+Week\s+(\d+)'
        matches = re.findall(pattern_single, text, re.IGNORECASE)

        for dose, week in matches:
            dosing.append({
                "dose_amount": float(dose),
                "dose_unit": "mg",
                "frequency_raw": f"Week {week}",
                "frequency_standard": None,
                "regimen_phase": "loading",
                "indication_name": None
            })

        # Pattern 2: Multiple weeks - "N mg at Weeks X, Y, Z"
        # e.g., "80 mg at Weeks 2, 4, 6, 8, 10, and 12"
        pattern_multiple = r'(\d+)\s*mg[^,]*?\s+at\s+Weeks?\s+([\d,\s]+(?:and\s+\d+)?)'
        matches = re.findall(pattern_multiple, text, re.IGNORECASE)

        for dose, weeks_str in matches:
            # Parse comma-separated week numbers
            # Remove "and" and split by comma
            weeks_str = weeks_str.replace('and', ',')
            week_numbers = re.findall(r'\d+', weeks_str)

            for week in week_numbers:
                # Avoid duplicates from Pattern 1
                if not any(d['frequency_raw'] == f"Week {week}" and d['dose_amount'] == float(dose) for d in dosing):
                    dosing.append({
                        "dose_amount": float(dose),
                        "dose_unit": "mg",
                        "frequency_raw": f"Week {week}",
                        "frequency_standard": None,
                        "regimen_phase": "loading",
                        "indication_name": None
                    })

        return dosing

    def _extract_transition_pattern(self, text: str) -> List[Dict]:
        """
        Extract dosing with transition from loading to maintenance.

        Examples:
        - "50 mg at Weeks 0, 4, then 50 mg every 8 weeks"
        - "160 mg on Day 1, followed by 80 mg every 2 weeks"

        Returns list of dosing dicts with appropriate regimen_phase
        """
        dosing = []

        # Pattern: "... then/followed by N mg every X weeks/months"
        # Captures both the loading portion and maintenance portion
        pattern = r'([\d\s,mgweek]+?)\s+(?:then|followed by)\s+(\d+)\s*mg\s+every\s+(\d+)\s+(weeks?|months?)'
        matches = re.findall(pattern, text, re.IGNORECASE)

        for loading_portion, maintenance_dose, interval, unit in matches:
            # The loading portion is already captured by week-based or day-based patterns
            # Here we just capture the maintenance dose after "then"/"followed by"

            # Standardize maintenance frequency
            if 'month' in unit.lower():
                freq_raw = f"every {interval} months" if int(interval) > 1 else "monthly"
            else:
                freq_raw = f"every {interval} weeks" if int(interval) > 1 else "weekly"

            freq_std, _ = standardize_frequency(freq_raw)

            dosing.append({
                "dose_amount": float(maintenance_dose),
                "dose_unit": "mg",
                "frequency_raw": freq_raw,
                "frequency_standard": freq_std,
                "regimen_phase": "maintenance",
                "indication_name": None
            })

        return dosing

    def _extract_two_dose_initial(self, text: str) -> List[Dict]:
        """
        Extract two-dose initial loading patterns.

        Examples:
        - "300 mg IV, followed 2 weeks later by second 300 mg IV"
        - "600 mg, then 300 mg 14 days later"

        Returns list of dosing dicts with regimen_phase="loading"
        """
        dosing = []

        # Pattern 1: "N mg, followed X weeks/days later by (second) N mg"
        pattern1 = r'(\d+)\s*mg[^,]*?,\s*followed\s+(\d+)\s+(weeks?|days?)\s+later\s+by\s+(?:second\s+)?(\d+)\s*mg'
        matches = re.findall(pattern1, text, re.IGNORECASE)

        for initial_dose, interval, unit, second_dose in matches:
            # First dose (Initial)
            dosing.append({
                "dose_amount": float(initial_dose),
                "dose_unit": "mg",
                "frequency_raw": "Initial dose",
                "frequency_standard": None,
                "regimen_phase": "loading",
                "indication_name": None
            })

            # Second dose (after interval)
            unit_label = "weeks" if "week" in unit.lower() else "days"
            dosing.append({
                "dose_amount": float(second_dose),
                "dose_unit": "mg",
                "frequency_raw": f"+{interval} {unit_label}",
                "frequency_standard": None,
                "regimen_phase": "loading",
                "indication_name": None
            })

        # Pattern 2: "N mg, then N mg X days later"
        pattern2 = r'(\d+)\s*mg[^,]*?,\s*then\s+(\d+)\s*mg\s+(\d+)\s+(weeks?|days?)\s+later'
        matches = re.findall(pattern2, text, re.IGNORECASE)

        for first_dose, second_dose, interval, unit in matches:
            dosing.append({
                "dose_amount": float(first_dose),
                "dose_unit": "mg",
                "frequency_raw": "Initial dose",
                "frequency_standard": None,
                "regimen_phase": "loading",
                "indication_name": None
            })

            unit_label = "weeks" if "week" in unit.lower() else "days"
            dosing.append({
                "dose_amount": float(second_dose),
                "dose_unit": "mg",
                "frequency_raw": f"+{interval} {unit_label}",
                "frequency_standard": None,
                "regimen_phase": "loading",
                "indication_name": None
            })

        return dosing

    def _infer_loading_phase(self, dosing_list: List[Dict]) -> List[Dict]:
        """
        Infer loading vs maintenance phase for doses that don't have it explicitly set.

        Rules:
        1. Week 0, Day 0, Day 1 → loading
        2. Sequential time-specific doses (before "every" regimens) → loading
        3. "every N weeks/months" → maintenance
        4. If phase already set, leave it

        Args:
            dosing_list: List of dosing dicts

        Returns:
            Same list with regimen_phase inferred where needed
        """
        for dosing in dosing_list:
            # Skip if phase already set
            if dosing.get("regimen_phase"):
                continue

            freq_raw = dosing.get("frequency_raw", "").lower()

            # Rule 1: Week 0 or Day 0/1 → loading
            if "week 0" in freq_raw or "day 0" in freq_raw or "day 1" in freq_raw:
                dosing["regimen_phase"] = "loading"
                continue

            # Rule 2: "every" pattern → maintenance
            if "every" in freq_raw or "monthly" in freq_raw or "weekly" in freq_raw:
                dosing["regimen_phase"] = "maintenance"
                continue

            # Rule 3: Specific week/day numbers → likely loading
            # e.g., "Week 2", "Week 4", "Day 15"
            if re.match(r'(week|day)\s+\d+', freq_raw):
                dosing["regimen_phase"] = "loading"
                continue

            # Default to maintenance if unclear
            dosing["regimen_phase"] = "maintenance"

        return dosing_list

    def _extract_dosing_from_text(self, text: str) -> List[Dict]:
        """
        Extract dosing patterns from a text block.

        Helper method that extracts doses using regex patterns.
        Now uses enhanced pattern detection for loading doses.
        """
        dosing = []

        # NEW: Week-based loading doses (Task 1.1)
        # e.g., "160 mg at Week 0, followed by 80 mg at Weeks 2, 4, 6, 8, 10, 12"
        dosing.extend(self._extract_week_based_loading(text))

        # NEW: Transition patterns (Task 1.2)
        # e.g., "50 mg at Weeks 0, 4, then 50 mg every 8 weeks"
        dosing.extend(self._extract_transition_pattern(text))

        # NEW: Two-dose initial (Task 1.3)
        # e.g., "300 mg IV, followed 2 weeks later by second 300 mg IV"
        dosing.extend(self._extract_two_dose_initial(text))

        # Pattern 1: Loading doses with specific days (EXISTING)
        # e.g., "160 mg on Day 1", "80 mg on Day 15"
        loading_pattern = r'(\d+)\s*mg\s+on\s+Day\s+(\d+)'
        loading_matches = re.findall(loading_pattern, text, re.IGNORECASE)

        for dose, day in loading_matches:
            dosing.append({
                "dose_amount": float(dose),
                "dose_unit": "mg",
                "frequency_raw": f"Day {day}",
                "frequency_standard": None,  # One-time doses
                "regimen_phase": "loading",
                "indication_name": None  # Will be filled in by caller
            })

        # Pattern 2: "every other week"
        pattern_q2w = r'(\d+)\s*mg\s+every\s+other\s+week'
        matches = re.findall(pattern_q2w, text, re.IGNORECASE)
        for dose in matches:
            freq_std, _ = standardize_frequency("every other week")
            dosing.append({
                "dose_amount": float(dose),
                "dose_unit": "mg",
                "frequency_raw": "every other week",
                "frequency_standard": freq_std,
                "regimen_phase": "maintenance",
                "indication_name": None
            })

        # Pattern 3: "every N weeks"
        pattern_qnw = r'(\d+)\s*mg\s+every\s+(\d+)\s+weeks?'
        matches = re.findall(pattern_qnw, text, re.IGNORECASE)
        for dose, interval in matches:
            frequency_raw = f"every {interval} weeks"
            freq_std, _ = standardize_frequency(frequency_raw)
            dosing.append({
                "dose_amount": float(dose),
                "dose_unit": "mg",
                "frequency_raw": frequency_raw,
                "frequency_standard": freq_std,
                "regimen_phase": "maintenance",
                "indication_name": None
            })

        # Pattern 4: "once weekly" / "every week"
        pattern_qw = r'(\d+)\s*mg\s+(?:once\s+weekly|every\s+week)'
        matches = re.findall(pattern_qw, text, re.IGNORECASE)
        for dose in matches:
            freq_std, _ = standardize_frequency("every week")
            dosing.append({
                "dose_amount": float(dose),
                "dose_unit": "mg",
                "frequency_raw": "every week",
                "frequency_standard": freq_std,
                "regimen_phase": "maintenance",
                "indication_name": None
            })

        # Pattern 5: "once monthly" / "every month"
        pattern_qm = r'(\d+)\s*mg\s+(?:once\s+monthly|every\s+month)'
        matches = re.findall(pattern_qm, text, re.IGNORECASE)
        for dose in matches:
            freq_std, _ = standardize_frequency("monthly")
            dosing.append({
                "dose_amount": float(dose),
                "dose_unit": "mg",
                "frequency_raw": "monthly",
                "frequency_standard": freq_std,
                "regimen_phase": "maintenance",
                "indication_name": None
            })

        # NEW: Infer loading phase for any doses without explicit phase (Task 1.4)
        dosing = self._infer_loading_phase(dosing)

        return dosing

    def _save_complete_drug_data(self, data: Dict, label_xml: str, overwrite: bool = False) -> int:
        """
        Save all extracted data to database.

        Args:
            data: Extracted drug data
            label_xml: Full DailyMed label XML (for gap filling)
            overwrite: If True, delete and recreate existing drug data

        Flow:
        1. Add diseases first (needed for gap filling to identify indications)
        2. Fill data gaps (mechanism + approval years) using unified approach
        3. Add drug with filled mechanism
        4. Add indications with approval years
        5. Add dosing, formulations, metadata
        """
        # 1. Add diseases first, build mapping
        disease_name_to_id = {}
        for disease_name in data.get("indications", []):
            disease_id = self.drug_db.add_disease(disease_name=disease_name)
            # Store mapping for dosing linkage
            disease_name_to_id[disease_name.lower().strip()] = disease_id

        # 2. Fill data gaps using unified approach (mechanism + approval years)
        logger.info(f"Filling data gaps for {data['brand_name']} using unified approach")
        try:
            # Step 1: Use approval data from indications_with_approval (already scraped from Drugs.com)
            scraped_approval_data = None

            if data.get("indications_with_approval"):
                logger.info(f"Using pre-fetched approval data from Drugs.com")

                # Convert to the format gap filler expects
                scraped_approval_data = {}
                for ind_data in data["indications_with_approval"]:
                    indication_lower = ind_data["indication"].lower()
                    scraped_approval_data[indication_lower] = {
                        "year": ind_data.get("approval_year"),
                        "approval_date": ind_data.get("approval_date")
                    }
            else:
                logger.info("No Drugs.com approval data available")

            # Step 2: Use unified gap filler to fill ALL gaps (mechanism + approval years) in ONE AI call
            from src.tools.drug_data_gap_filler import DrugDataGapFiller

            gap_filler = DrugDataGapFiller()
            filled_gaps = gap_filler.fill_all_gaps(
                drug_data=data,
                label_xml=label_xml,
                scraped_approval_data=scraped_approval_data
            )

            # Extract filled data
            approval_years = filled_gaps.get("approval_years", {})
            filled_mechanism = filled_gaps.get("mechanism_of_action")
            filled_dosing = filled_gaps.get("dosing_regimens", [])

            # Update mechanism if it was filled by AI
            if filled_mechanism and not data.get("mechanism_of_action"):
                data["mechanism_of_action"] = filled_mechanism
                logger.info(f"Mechanism filled by AI: {filled_mechanism}")

            # Update dosing regimens if AI extracted better indication-specific data
            if filled_dosing:
                logger.info(f"AI extracted {len(filled_dosing)} indication-specific dosing regimens")
                # Merge AI dosing with regex-extracted dosing
                # AI dosing takes precedence for indication linkage
                ai_dosing_dict = {
                    (d['dose_amount'], d['frequency_raw'], d.get('indication_name', '').lower()): d
                    for d in filled_dosing
                }
                regex_dosing_dict = {
                    (d['dose_amount'], d['frequency_raw'], d.get('indication_name', '').lower()): d
                    for d in data.get("dosing_regimens", [])
                }

                # Use AI dosing for entries with indication names, keep regex dosing for others
                merged_dosing = list(ai_dosing_dict.values())
                for key, dosing in regex_dosing_dict.items():
                    if key not in ai_dosing_dict:
                        merged_dosing.append(dosing)

                data["dosing_regimens"] = merged_dosing
                logger.info(f"Merged dosing: {len(merged_dosing)} total regimens")

            # Convert approval_years to the format we need for database insertion
            approval_dates = {}
            for indication in data.get("indications", []):
                indication_lower = indication.lower()

                # Check if we have data from gap filler
                if indication_lower in approval_years:
                    gap_data = approval_years[indication_lower]
                    approval_dates[indication_lower] = {
                        "year": gap_data.get("year"),
                        "date": gap_data.get("date"),
                        "source": gap_data.get("source", "AI Agent")
                    }
                # Check if we have data from Drugs.com scraper
                elif scraped_approval_data and indication_lower in scraped_approval_data:
                    scraped_data = scraped_approval_data[indication_lower]
                    approval_dates[indication_lower] = {
                        "year": scraped_data.get("year"),
                        "date": scraped_data.get("approval_date"),
                        "source": "Drugs.com"
                    }
                else:
                    # No data found
                    approval_dates[indication_lower] = {
                        "year": None,
                        "date": None,
                        "source": "Not found"
                    }

            # Log coverage statistics
            total = len(data.get("indications", []))
            with_year = sum(1 for d in approval_dates.values() if d.get("year"))
            coverage = (with_year / total * 100) if total > 0 else 0

            logger.info(
                f"Gap filling complete: {with_year}/{total} indications with approval years "
                f"({coverage:.1f}% coverage)"
            )

            if filled_gaps.get("gaps_filled"):
                logger.info(
                    f"AI filled {filled_gaps['gaps_filled_count']} gaps: "
                    f"{', '.join(filled_gaps['gaps_filled_types'])}"
                )

        except Exception as e:
            logger.warning(f"Data gap filling failed: {e}")
            import traceback
            traceback.print_exc()
            # Create empty results - will proceed without dates
            approval_dates = {
                ind.lower(): {"year": None, "date": None, "source": "Extraction failed"}
                for ind in data.get("indications", [])
            }

        # 3. Calculate first approval date (earliest approval date from all indications)
        first_approval_date = None
        approval_dates_with_values = [
            ad.get("date") for ad in approval_dates.values()
            if ad.get("date") is not None
        ]
        if approval_dates_with_values:
            # Sort and get earliest
            first_approval_date = sorted(approval_dates_with_values)[0]
            logger.info(f"First approval date calculated: {first_approval_date}")

        # 4. Add drug with filled mechanism and first approval date
        drug_id = self.drug_db.add_drug(
            generic_name=data["generic_name"],
            brand_name=data["brand_name"],
            manufacturer=data["manufacturer"],
            drug_type=data["drug_type"],
            mechanism=data["mechanism_of_action"],  # Now includes AI-filled mechanism
            approval_status=data["approval_status"],
            highest_phase=data["highest_phase"],
            dailymed_setid=data["dailymed_setid"],
            first_approval_date=first_approval_date,  # NEW: Pass calculated first approval date
            overwrite=overwrite  # Pass overwrite flag
        )

        # 5. Add indications with approval dates + severity
        disease_id_to_indication_id = {}  # NEW: Track disease_id → indication_id mapping

        for disease_name in data.get("indications", []):
            disease_id = disease_name_to_id[disease_name.lower().strip()]

            # Get approval data for this indication
            approval_data = approval_dates.get(disease_name.lower(), {})

            # Get severity data and indication_raw from indications_with_approval
            severity_mild = False
            severity_moderate = False
            severity_severe = False
            indication_raw = None

            if data.get("indications_with_approval"):
                for ind_data in data["indications_with_approval"]:
                    if ind_data["indication"].lower() == disease_name.lower():
                        severity_mild = ind_data.get("severity_mild", False)
                        severity_moderate = ind_data.get("severity_moderate", False)
                        severity_severe = ind_data.get("severity_severe", False)
                        indication_raw = ind_data.get("indication_raw") or ind_data.get("indication")
                        break

            indication_id = self.drug_db.add_indication(
                drug_id=drug_id,
                disease_id=disease_id,
                indication_raw=indication_raw,  # Pass the raw indication text
                approval_status="approved",
                approval_year=approval_data.get("year"),
                approval_date=approval_data.get("date"),
                approval_source=approval_data.get("source"),
                data_source="DailyMed",
                severity_mild=severity_mild,
                severity_moderate=severity_moderate,
                severity_severe=severity_severe
            )

            # NEW: Store mapping for dosing linkage
            disease_id_to_indication_id[disease_id] = indication_id

        # 5. Add dosing regimens with indication linkage
        primary_route = data.get("routes", [None])[0] if data.get("routes") else None

        dosing_regimens = data.get("dosing_regimens", [])

        # Separate loading and maintenance
        loading_doses = [d for d in dosing_regimens if d.get("regimen_phase") == "loading"]
        maintenance_doses = [d for d in dosing_regimens if d.get("regimen_phase") == "maintenance"]

        # Sort loading doses by day number (with safe parsing)
        def get_day_number(dosing_dict):
            """Safely extract day number from frequency_raw"""
            freq_raw = dosing_dict.get("frequency_raw", "Day 0")
            if "Day" in freq_raw:
                day_str = freq_raw.replace("Day ", "").split()[0]
                # Try to convert to int, return 0 if it fails
                try:
                    return int(day_str)
                except ValueError:
                    return 0
            return 0

        loading_doses.sort(key=get_day_number)

        # Add in sequence
        sequence = 1
        for dosing in loading_doses + maintenance_doses:
            # Try to match indication_name to a disease_id, then convert to indication_id
            indication_id = None
            if dosing.get("indication_name"):
                # Step 1: Match indication name from Section 2 to disease_id from Section 1
                disease_id = self._match_indication_to_disease(
                    dosing["indication_name"],
                    disease_name_to_id
                )

                # Step 2: Convert disease_id to indication_id for this specific drug
                if disease_id and disease_id in disease_id_to_indication_id:
                    indication_id = disease_id_to_indication_id[disease_id]
                    logger.debug(f"Matched indication '{dosing['indication_name']}' to indication_id={indication_id}")
                else:
                    logger.debug(f"Could not find indication_id for disease_id={disease_id}")

            try:
                self.drug_db.add_dosing_regimen(
                    drug_id=drug_id,
                    dose_amount=dosing.get("dose_amount"),
                    dose_unit=dosing.get("dose_unit"),
                    frequency_raw=dosing.get("frequency_raw"),
                    route_raw=primary_route,
                    regimen_phase=dosing.get("regimen_phase", "maintenance"),
                    sequence_order=sequence,
                    indication_id=indication_id,  # Link to specific indication
                    weight_based=dosing.get("weight_based", False),  # Weight-based dosing flag
                    dosing_notes=dosing.get("dosing_notes"),  # Weight range or patient population
                    data_source="DailyMed"
                )
                sequence += 1
            except Exception as e:
                # If foreign key constraint fails, try without indication_id
                logger.warning(f"Failed to add dosing with indication_id {indication_id}: {e}")
                logger.warning("Retrying without indication_id")
                self.drug_db.add_dosing_regimen(
                    drug_id=drug_id,
                    dose_amount=dosing.get("dose_amount"),
                    dose_unit=dosing.get("dose_unit"),
                    frequency_raw=dosing.get("frequency_raw"),
                    route_raw=primary_route,
                    regimen_phase=dosing.get("regimen_phase", "maintenance"),
                    sequence_order=sequence,
                    indication_id=None,  # Will show as "General"
                    weight_based=dosing.get("weight_based", False),  # Weight-based dosing flag
                    dosing_notes=dosing.get("dosing_notes"),  # Weight range or patient population
                    data_source="DailyMed"
                )
                sequence += 1

        # 6. Add formulations (one per route)
        for route in data.get("routes", []):
            try:
                cursor = self.drug_db.connection.cursor()
                cursor.execute("""
                    INSERT INTO drug_formulations (drug_id, route)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                """, (drug_id, route))
                self.drug_db.connection.commit()
                cursor.close()
            except Exception as e:
                logger.debug(f"Could not add formulation: {e}")

        # 7. Add metadata
        # Check if biosimilars are available (check if multiple manufacturers exist in DailyMed)
        biosimilar_available = self._check_biosimilars_available(data.get("generic_name"))

        # Check for black box warning in label
        has_black_box = self._check_black_box_warning(label_xml)
        if has_black_box:
            logger.info(f"Black box warning detected for {data['brand_name']}")

        self.drug_db.add_drug_metadata(
            drug_id=drug_id,
            orphan_designation=False,
            breakthrough_therapy=False,
            fast_track=False,
            biosimilar_available=biosimilar_available,
            has_black_box_warning=has_black_box
        )

        # 8. Save version snapshot (capture complete state for versioning)
        logger.info(f"Creating version snapshot for {data['brand_name']}")
        try:
            # Get complete drug data including related tables
            drug_overview = self.drug_db.get_drug_overview(drug_id)

            if drug_overview:
                # Create complete snapshot for versioning
                version_snapshot = {
                    **data,  # Original extracted data
                    'drug_id': drug_id,
                    'indications': drug_overview.get('indications', []),
                    'dosing_regimens': drug_overview.get('dosing_regimens', []),
                    'approval_dates': approval_dates,
                    'biosimilar_available': biosimilar_available
                }

                # Create version history manager directly
                version_manager = DrugVersionHistory(self.drug_db)

                # Save version
                version_number, deleted_version = version_manager.save_version(
                    drug_id=drug_id,
                    drug_data=version_snapshot,
                    created_by='DailyMed Extractor'
                )

                logger.info(
                    f"Saved as version {version_number}/3"
                    + (f" (deleted oldest version {deleted_version['version_number']})" if deleted_version else "")
                )
        except Exception as e:
            logger.warning(f"Failed to save version snapshot: {e}")
            # Don't fail the entire extraction if versioning fails
            import traceback
            traceback.print_exc()

        return drug_id

    def _match_indication_to_disease(self, indication_name: str, disease_name_to_id: Dict[str, int]) -> Optional[int]:
        """
        Match an indication name from Section 2 to a disease_id from Section 1.

        Uses fuzzy matching since Section 2 titles may not exactly match Section 1 disease names.
        E.g., Section 1: "plaque psoriasis", Section 2: "Plaque Psoriasis"

        Handles multi-disease titles like "Rheumatoid Arthritis, Psoriatic Arthritis, and Ankylosing Spondylitis"
        by extracting the first disease mentioned.
        """
        if not indication_name:
            return None

        indication_lower = indication_name.lower().strip()

        # Handle multi-disease indications (comma-separated or "and"-separated)
        # E.g., "rheumatoid arthritis, psoriatic arthritis, and ankylosing spondylitis"
        # Take the first disease mentioned
        if ',' in indication_lower or ' and ' in indication_lower:
            # Split by comma or "and"
            first_disease = re.split(r',|\sand\s', indication_lower)[0].strip()
            logger.debug(f"Multi-disease indication '{indication_name}' - using first disease: '{first_disease}'")
            indication_lower = first_disease

        # Direct match
        if indication_lower in disease_name_to_id:
            return disease_name_to_id[indication_lower]

        # Fuzzy match: check if indication name is contained in any disease name or vice versa
        # "plaque psoriasis" should match "chronic plaque psoriasis"
        for disease_name, disease_id in disease_name_to_id.items():
            if indication_lower in disease_name or disease_name in indication_lower:
                return disease_id

        # Check for common variations
        # E.g., "psoriatic arthritis" vs "active psoriatic arthritis"
        # Strip common modifiers
        indication_stripped = re.sub(r'\b(active|chronic|acute|severe|moderate|moderately|severely)\s+', '', indication_lower).strip()
        for disease_name, disease_id in disease_name_to_id.items():
            disease_stripped = re.sub(r'\b(active|chronic|acute|severe|moderate|moderately|severely)\s+', '', disease_name).strip()
            if indication_stripped == disease_stripped:
                return disease_id

        # No match found
        logger.debug(f"Could not match indication '{indication_name}' to any disease")
        return None

    def _check_biosimilars_available(self, generic_name: str) -> bool:
        """
        Check if biosimilars are available for this drug.
        Looks for multiple manufacturers for the same generic name in DailyMed.
        """
        try:
            if not generic_name:
                return False

            # Search DailyMed for the generic name
            from urllib.parse import quote
            import requests
            import xml.etree.ElementTree as ET

            encoded_name = quote(generic_name)
            search_url = f"{self.dailymed.V1_BASE_URL}/drugname/{encoded_name}/human/spls.xml"

            response = requests.get(search_url, timeout=10)
            if response.status_code != 200:
                return False

            root = ET.fromstring(response.content)
            spls = root.findall('.//spl')

            # Check if there are multiple entries (indicating biosimilars/generics)
            if len(spls) >= 2:
                # Check for biosimilar keywords in titles
                biosimilar_keywords = ['biosimilar', 'limited', 'teva', 'sandoz', 'mylan', 'fresenius']
                for spl in spls:
                    title = spl.find('title')
                    if title is not None and title.text:
                        title_lower = title.text.lower()
                        if any(keyword in title_lower for keyword in biosimilar_keywords):
                            logger.info(f"Biosimilar detected for {generic_name}")
                            return True

            return False

        except Exception as e:
            logger.debug(f"Error checking biosimilars: {e}")
            return False

    def _check_black_box_warning(self, label_xml: str) -> bool:
        """
        Check if drug has a black box warning (boxed warning).

        DailyMed section code for boxed warnings: 34066-1

        Args:
            label_xml: DailyMed label XML

        Returns:
            True if black box warning exists, False otherwise
        """
        try:
            root = ET.fromstring(label_xml)

            # Look for boxed warning section (code 34066-1)
            for section in root.findall('.//{urn:hl7-org:v3}section'):
                code = section.find('.//{urn:hl7-org:v3}code')
                if code is not None and code.get('code') == '34066-1':
                    logger.info("Black box warning section found in label")
                    return True

            return False

        except Exception as e:
            logger.debug(f"Error checking black box warning: {e}")
            return False

    def close(self):
        self.dailymed.close()
