import sys
sys.path.insert(0, '.')

import requests
import xml.etree.ElementTree as ET

from src.tools.enhanced_dailymed_extractor import EnhancedDailyMedExtractor
from src.tools.drug_database import DrugDatabase
from src.utils.config import get_settings

settings = get_settings()
db = DrugDatabase(settings.drug_database_url)
extractor = EnhancedDailyMedExtractor(db)

# Test the _extract_diseases_from_text method directly
test_texts = [
    "NURTEC ODT is indicated for the acute treatment of migraine with or without aura in adults.",
    "NURTEC ODT is indicated for the preventive treatment of episodic migraine in adults.",
    "treatment of moderate to severe plaque psoriasis in adult patients",  # Known to work (Cosentyx-like)
]

print("=== Testing _extract_diseases_from_text ===")
for text in test_texts:
    diseases = extractor._extract_diseases_from_text(text)
    print(f"Input: {text}")
    print(f"Extracted: {diseases}")
    print()

# Get the Nurtec label XML
setid = '9ef08e09-1098-35cc-e053-2a95a90a3e1d'  # Pfizer Nurtec
url = f'https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}.xml'
resp = requests.get(url, timeout=30)
label_xml = resp.text

print(f"Got XML, length: {len(label_xml)}")

root = ET.fromstring(label_xml)
ns = 'urn:hl7-org:v3'

# Look for Section 1 - Indications and Usage
print("\n=== Looking for Section 1 (Indications and Usage) ===")

# Method 1: Look for code with displayName containing "INDICATIONS"
for section in root.findall(f'.//{{{ns}}}section'):
    code_elem = section.find(f'{{{ns}}}code')
    if code_elem is not None:
        display_name = code_elem.get('displayName', '')
        code_val = code_elem.get('code', '')
        if code_val == '34067-9':  # Only INDICATIONS section
            print(f"Found section: code={code_val}, displayName={display_name}")
            # Get the text content
            text_elem = section.find(f'{{{ns}}}text')
            print(f"text_elem found: {text_elem is not None}")
            if text_elem is not None:
                # Get all text content including nested elements
                all_text = ''.join(text_elem.itertext())
                print(f"\nSection text (first 2000 chars):\n{all_text[:2000]}")
            else:
                print("No text element found directly. Looking for nested sections...")
                # Maybe text is in nested subsections
                for subsection in section.findall(f'.//{{{ns}}}section'):
                    sub_code = subsection.find(f'{{{ns}}}code')
                    if sub_code is not None:
                        print(f"  Subsection: {sub_code.get('code')}, {sub_code.get('displayName')}")
                    sub_text = subsection.find(f'{{{ns}}}text')
                    if sub_text is not None:
                        all_text = ''.join(sub_text.itertext())
                        print(f"  Subsection text: {all_text[:1000]}")
                # Also try to get component sections
                for comp in section.findall(f'{{{ns}}}component'):
                    comp_section = comp.find(f'{{{ns}}}section')
                    if comp_section is not None:
                        comp_code = comp_section.find(f'{{{ns}}}code')
                        comp_text = comp_section.find(f'{{{ns}}}text')
                        if comp_code is not None:
                            print(f"  Component section: {comp_code.get('code')}, {comp_code.get('displayName')}")
                        if comp_text is not None:
                            all_text = ''.join(comp_text.itertext())
                            print(f"  Component text: {all_text[:1000]}")

# Method 2: Look for SPL section code 34067-9 (Indications & Usage)
print("\n=== Looking for LOINC code 34067-9 ===")
for section in root.findall(f'.//{{{ns}}}section'):
    code_elem = section.find(f'{{{ns}}}code')
    if code_elem is not None:
        if code_elem.get('code') == '34067-9':
            print("Found 34067-9 section!")
            text_elem = section.find(f'{{{ns}}}text')
            if text_elem is not None:
                all_text = ''.join(text_elem.itertext())
                print(f"Text: {all_text[:2000]}")

# Also look for Section 2 - Dosage and Administration
print("\n=== Looking for Section 2 (Dosage and Administration) ===")
for section in root.findall(f'.//{{{ns}}}section'):
    code_elem = section.find(f'{{{ns}}}code')
    if code_elem is not None:
        display_name = code_elem.get('displayName', '')
        code_val = code_elem.get('code', '')
        if 'DOSAGE' in display_name.upper() or code_val == '34068-7':
            print(f"Found section: code={code_val}, displayName={display_name}")
            text_elem = section.find(f'{{{ns}}}text')
            if text_elem is not None:
                all_text = ''.join(text_elem.itertext())
                print(f"\nSection text (first 2000 chars):\n{all_text[:2000]}")

