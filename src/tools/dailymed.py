"""
DailyMed API wrapper for FDA-approved drug information.

API Documentation: https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm
"""
import requests
import logging
from typing import Optional, Dict, List
import xml.etree.ElementTree as ET
from time import sleep
import json
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class DailyMedAPI:
    """
    Wrapper for DailyMed API to get FDA-approved drug information.

    Provides:
    - Route of administration
    - Dosing regimens
    - Approved indications
    - Manufacturer
    - Drug class/type
    """

    BASE_URL = "https://dailymed.nlm.nih.gov/dailymed"
    V1_BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v1"
    V2_BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2"

    def __init__(self):
        """Initialize DailyMed API client."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; ResearchBot/1.0)'
        })
        # Load preferred manufacturers from config
        self.preferred_manufacturers = self._load_preferred_manufacturers()

    def _load_preferred_manufacturers(self) -> List[str]:
        """
        Load preferred manufacturers from config file.

        Returns:
            List of manufacturer names (lowercase) to prefer over biosimilars
        """
        # Hardcoded fallback list (original 16 companies)
        fallback_manufacturers = [
            'abbvie', 'amgen', 'novartis', 'roche', 'genentech', 'pfizer',
            'bristol myers', 'bms', 'merck', 'eli lilly', 'janssen',
            'sanofi', 'regeneron', 'gilead', 'biogen', 'takeda'
        ]

        try:
            # Find config file - go up to project root
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent  # src/tools/dailymed.py -> project root
            config_path = project_root / 'config' / 'preferred_manufacturers.json'

            if not config_path.exists():
                logger.info(f"Config file not found at {config_path}, using fallback manufacturer list ({len(fallback_manufacturers)} companies)")
                return fallback_manufacturers

            # Load config file
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Flatten all categories into single list
            manufacturers = []
            for category, names in config.items():
                manufacturers.extend(names)

            # Remove duplicates (some manufacturers appear in multiple categories)
            manufacturers = list(set(manufacturers))

            logger.info(f"Loaded {len(manufacturers)} preferred manufacturers from config file")
            return manufacturers

        except Exception as e:
            logger.warning(f"Error loading manufacturer config: {e}, using fallback list")
            return fallback_manufacturers

    def search_drug(self, drug_name: str, prefer_original: bool = True) -> Optional[str]:
        """
        Search for a drug and get its SetID using v2 API (primary).

        The v2 API is preferred because:
        - Better coverage for newer drugs (e.g., rimegepant/Nurtec)
        - JSON format is easier to parse
        - More flexible query parameters
        - v1 API returns 404 for some drugs that exist in v2

        Args:
            drug_name: Drug name to search for
            prefer_original: If True, prefer original manufacturer over biosimilars

        Returns:
            SetID if found, None otherwise
        """
        # Use v2 API as primary (better coverage for newer drugs)
        setid = self._search_drug_v2(drug_name, prefer_original)
        if setid:
            return setid

        # Fallback to v1 API only if v2 fails
        logger.debug(f"v2 API failed for {drug_name}, trying v1 API as fallback")
        return self._search_drug_v1(drug_name, prefer_original)

    def get_official_brand_name(self, drug_name: str) -> Optional[str]:
        """
        Get the official brand name from DailyMed's drugnames API.

        This is useful for looking up drugs on other sites like Drugs.com,
        which may use the full official name (e.g., "NURTEC ODT" instead of "nurtec").

        Args:
            drug_name: User-provided drug name (partial or complete)

        Returns:
            Official brand name if found, None otherwise
        """
        try:
            url = f"{self.V2_BASE_URL}/drugnames.json"
            params = {
                "drug_name": drug_name,
                "name_type": "B"  # Brand names only
            }

            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                results = data.get('data', [])

                if results:
                    # Return the first matching brand name
                    brand_name = results[0].get('drug_name')
                    if brand_name:
                        logger.info(f"Found official brand name: {brand_name} (searched: {drug_name})")
                        return brand_name

            return None

        except Exception as e:
            logger.warning(f"Error getting official brand name for {drug_name}: {e}")
            return None

    def _search_drug_v1(self, drug_name: str, prefer_original: bool = True) -> Optional[str]:
        """Search using v1 API (XML-based)."""
        try:
            from urllib.parse import quote
            encoded_name = quote(drug_name)
            search_url = f"{self.V1_BASE_URL}/drugname/{encoded_name}/human/spls.xml"

            logger.debug(f"Searching DailyMed v1 for: {drug_name}")
            response = self.session.get(search_url, timeout=10)

            if response.status_code != 200:
                logger.debug(f"DailyMed v1 search failed with status {response.status_code}")
                return None

            root = ET.fromstring(response.content)
            spls = root.findall('.//spl')

            if not spls:
                return None

            return self._select_best_spl_v1(spls, drug_name, prefer_original)

        except Exception as e:
            logger.debug(f"DailyMed v1 search error for {drug_name}: {e}")
            return None

    def _search_drug_v2(self, drug_name: str, prefer_original: bool = True) -> Optional[str]:
        """Search using v2 API (JSON-based) - better coverage for newer drugs."""
        try:
            from urllib.parse import quote
            encoded_name = quote(drug_name)
            search_url = f"{self.V2_BASE_URL}/spls.json?drug_name={encoded_name}"

            logger.debug(f"Searching DailyMed v2 for: {drug_name}")
            response = self.session.get(search_url, timeout=10)

            if response.status_code != 200:
                logger.warning(f"DailyMed v2 search failed with status {response.status_code}")
                return None

            data = response.json()
            spls = data.get('data', [])

            if not spls:
                logger.debug(f"No results from v2 API for {drug_name}")
                return None

            return self._select_best_spl_v2(spls, drug_name, prefer_original)

        except Exception as e:
            logger.error(f"DailyMed v2 search error for {drug_name}: {e}")
            return None

    def _select_best_spl_v1(self, spls: List, drug_name: str, prefer_original: bool) -> Optional[str]:
        """Select best SPL from v1 XML results."""
        exclude_keywords = [
            'biosimilar', 'limited', 'a-s medication', 'repackager',
            'cardinal health', 'h-e-b', 'golden state', 'remedyrepack',
            'proficient rx', 'bryant ranch', 'pharma pac', 'physicians total care'
        ]

        if prefer_original and len(spls) > 1:
            # First pass: try to find preferred manufacturer
            for spl in spls:
                title = spl.find('title')
                if title is not None and title.text:
                    title_lower = title.text.lower()
                    if any(mfr in title_lower for mfr in self.preferred_manufacturers):
                        setid = spl.find('setid')
                        if setid is not None and setid.text:
                            logger.info(f"Found preferred manufacturer for {drug_name}: {title.text}")
                            return setid.text.strip()

            # Second pass: exclude biosimilars/repackagers
            for spl in spls:
                title = spl.find('title')
                if title is not None and title.text:
                    title_lower = title.text.lower()
                    if not any(keyword in title_lower for keyword in exclude_keywords):
                        setid = spl.find('setid')
                        if setid is not None and setid.text:
                            logger.info(f"Found original drug for {drug_name}: {title.text}")
                            return setid.text.strip()

        # Fallback: return first result
        setid_element = spls[0].find('setid')
        if setid_element is not None and setid_element.text:
            return setid_element.text.strip()
        return None

    def _select_best_spl_v2(self, spls: List[Dict], drug_name: str, prefer_original: bool) -> Optional[str]:
        """Select best SPL from v2 JSON results."""
        exclude_keywords = [
            'biosimilar', 'limited', 'a-s medication', 'repackager',
            'cardinal health', 'h-e-b', 'golden state', 'remedyrepack',
            'proficient rx', 'bryant ranch', 'pharma pac', 'physicians total care'
        ]

        if prefer_original and len(spls) > 1:
            # First pass: try to find preferred manufacturer
            for spl in spls:
                title = spl.get('title', '').lower()
                if any(mfr in title for mfr in self.preferred_manufacturers):
                    setid = spl.get('setid')
                    if setid:
                        logger.info(f"Found preferred manufacturer for {drug_name}: {spl.get('title')}")
                        return setid

            # Second pass: exclude biosimilars/repackagers
            for spl in spls:
                title = spl.get('title', '').lower()
                if not any(keyword in title for keyword in exclude_keywords):
                    setid = spl.get('setid')
                    if setid:
                        logger.info(f"Found original drug for {drug_name}: {spl.get('title')}")
                        return setid

        # Fallback: return first result
        if spls and spls[0].get('setid'):
            return spls[0]['setid']
        return None

    def get_drug_label(self, setid: str) -> Optional[str]:
        """
        Get full drug label XML for a SetID using v2 API.

        Args:
            setid: DailyMed SetID

        Returns:
            XML content as string
        """
        try:
            # v2 API endpoint for getting SPL by SETID
            label_url = f"{self.V2_BASE_URL}/spls/{setid}.xml"

            logger.debug(f"Fetching drug label for SetID: {setid}")
            response = self.session.get(label_url, timeout=10)

            if response.status_code == 200:
                return response.text
            else:
                logger.warning(f"Failed to fetch label: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error fetching drug label: {e}")
            return None

    def get_drug_info(self, drug_name: str) -> Optional[Dict]:
        """
        Get comprehensive drug information from DailyMed.

        Args:
            drug_name: Drug name to look up

        Returns:
            Dictionary with drug information:
            {
                "route_of_administration": [str],
                "dosing_frequency": [str],
                "manufacturer": str,
                "indications": [str],
                "active_ingredients": [str]
            }
        """
        # Search for drug
        setid = self.search_drug(drug_name)
        if not setid:
            return None

        # Small delay to be respectful to API
        sleep(0.5)

        # Get drug label
        label_xml = self.get_drug_label(setid)
        if not label_xml:
            return None

        # Parse the label
        return self._parse_drug_label(label_xml, drug_name)

    def _parse_drug_label(self, xml_content: str, drug_name: str) -> Dict:
        """
        Parse DailyMed XML label to extract key information.

        This is a simplified parser - DailyMed XML is very complex.
        May need enhancement for better coverage.
        """
        try:
            root = ET.fromstring(xml_content)

            info = {
                "route_of_administration": [],
                "dosing_frequency": [],
                "manufacturer": None,
                "indications": [],
                "active_ingredients": [],
                "drug_name": drug_name,
                "generic_name": None,
                "mechanism_of_action": None
            }

            # Extract generic name from genericMedicine or substanceAdministration
            # Look for genericMedicine element
            for generic in root.findall('.//{urn:hl7-org:v3}genericMedicine'):
                name_elem = generic.find('.//{urn:hl7-org:v3}name')
                if name_elem is not None and name_elem.text:
                    info["generic_name"] = name_elem.text.strip()
                    break

            # Fallback: extract from active ingredients if generic_name not found
            if not info["generic_name"]:
                for ingredient in root.findall('.//{urn:hl7-org:v3}ingredientSubstance'):
                    name_elem = ingredient.find('.//{urn:hl7-org:v3}name')
                    if name_elem is not None and name_elem.text:
                        info["generic_name"] = name_elem.text.strip()
                        break

            # Extract routes of administration
            # Look for routeCode elements
            for route in root.findall('.//{urn:hl7-org:v3}routeCode'):
                display_name = route.get('displayName')
                if display_name:
                    info["route_of_administration"].append(display_name)

            # Extract manufacturer
            # Look for representedOrganization
            for org in root.findall('.//{urn:hl7-org:v3}representedOrganization'):
                name_elem = org.find('.//{urn:hl7-org:v3}name')
                if name_elem is not None and name_elem.text:
                    info["manufacturer"] = name_elem.text
                    break

            # Extract active ingredients
            for ingredient in root.findall('.//{urn:hl7-org:v3}ingredient'):
                name_elem = ingredient.find('.//{urn:hl7-org:v3}name')
                if name_elem is not None and name_elem.text:
                    info["active_ingredients"].append(name_elem.text)

            # Extract indications (from indications section)
            for section in root.findall('.//{urn:hl7-org:v3}section'):
                code = section.find('.//{urn:hl7-org:v3}code')
                if code is not None and code.get('code') == '34067-9':  # Indications & Usage
                    text = section.find('.//{urn:hl7-org:v3}text')
                    if text is not None:
                        # Get text content (simplified)
                        indication_text = ''.join(text.itertext()).strip()
                        info["indications"].append(indication_text[:500])  # Limit length

            # Extract mechanism of action (section code 43679-0)
            for section in root.findall('.//{urn:hl7-org:v3}section'):
                code = section.find('.//{urn:hl7-org:v3}code')
                if code is not None and code.get('code') == '43679-0':  # Mechanism of Action
                    text = section.find('.//{urn:hl7-org:v3}text')
                    if text is not None:
                        moa_text = ''.join(text.itertext()).strip()
                        # Clean up and limit length
                        moa_text = ' '.join(moa_text.split())  # Normalize whitespace
                        info["mechanism_of_action"] = moa_text[:1000]
                        break

            # Also check for Clinical Pharmacology section (34090-1) which often contains MOA
            if not info["mechanism_of_action"]:
                for section in root.findall('.//{urn:hl7-org:v3}section'):
                    code = section.find('.//{urn:hl7-org:v3}code')
                    if code is not None and code.get('code') == '34090-1':  # Clinical Pharmacology
                        text = section.find('.//{urn:hl7-org:v3}text')
                        if text is not None:
                            pharma_text = ''.join(text.itertext()).strip()
                            pharma_text = ' '.join(pharma_text.split())
                            info["mechanism_of_action"] = pharma_text[:1000]
                            break

            # Dosing frequency is harder to extract from structured XML
            # Would need to parse dosage sections which vary greatly
            # For now, leave empty - will be filled by AI analysis

            logger.info(f"Parsed DailyMed data for {drug_name}")
            return info

        except Exception as e:
            logger.error(f"Error parsing drug label: {e}")
            return None

    def close(self):
        """Close session."""
        self.session.close()
