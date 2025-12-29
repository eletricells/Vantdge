"""
Extract Efficacy and Safety Data

CLI script to extract efficacy and safety data for a drug.
Supports both approved drugs (via OpenFDA) and investigational drugs (via web search).

Usage:
    python extract_efficacy_safety.py --drug "secukinumab"
    python extract_efficacy_safety.py --drug "batoclimab" --investigational
"""

import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from src.drug_extraction_system.database.connection import DatabaseConnection
from src.drug_extraction_system.database.operations import DrugDatabaseOperations
from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
from src.drug_extraction_system.services.efficacy_safety_extractor import EfficacySafetyExtractor

logging.basicConfig(
    level=logging.INFO,
    format='%(name)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_approved_drug(drug_name: str, drug_id: int):
    """Extract efficacy/safety for an approved drug from OpenFDA."""
    logger.info(f"Extracting efficacy/safety for approved drug: {drug_name}")

    # Get OpenFDA label
    openfda = OpenFDAClient()
    labels = openfda.search_drug_labels(drug_name, limit=1)

    if not labels:
        logger.error(f"No FDA label found for {drug_name}")
        return False

    label = labels[0]
    logger.info(f"Found FDA label with {len(label.get('clinical_studies', [''])[0])} chars of clinical studies")

    # Extract using Claude
    extractor = EfficacySafetyExtractor()
    efficacy_results, safety_results = extractor.extract_from_label(drug_name, label)

    logger.info(f"Extracted {len(efficacy_results)} efficacy endpoints")
    logger.info(f"Extracted {len(safety_results)} adverse events")

    # Store in database
    with DatabaseConnection() as db:
        ops = DrugDatabaseOperations(db)

        # Clear existing data first
        ops.clear_efficacy_safety_data(drug_id)

        # Store new data
        efficacy_count = ops.store_efficacy_data(drug_id, efficacy_results)
        safety_count = ops.store_safety_data(drug_id, safety_results)

    logger.info(f"Stored {efficacy_count} efficacy records and {safety_count} safety records")
    return True


def extract_investigational_drug(drug_name: str, drug_id: int):
    """Extract efficacy/safety for an investigational drug via web search."""
    logger.info(f"Extracting efficacy/safety for investigational drug: {drug_name}")

    # TODO: Implement PipelineEfficacySafetyExtractor for web search
    # For now, just use the basic extractor with web search capability

    from anthropic import Anthropic
    import os
    import json

    anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Get indications for this drug
    with DatabaseConnection() as db:
        with db.cursor() as cur:
            cur.execute("""
                SELECT disease_name FROM drug_indications WHERE drug_id = %s
            """, (drug_id,))
            indications = [row['disease_name'] for row in cur.fetchall()]

    if not indications:
        logger.warning(f"No indications found for {drug_name}")
        return False

    all_efficacy = []
    all_safety = []

    for indication in indications:
        logger.info(f"Searching efficacy/safety for {drug_name} - {indication}")

        try:
            # Use Claude with web search for efficacy
            message = anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=3000,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search"
                }],
                messages=[{
                    "role": "user",
                    "content": f"""Search the web to find clinical trial efficacy and safety data for {drug_name}
used to treat {indication}.

Look for:
- Primary endpoint results (response rates, remission rates)
- Comparison to placebo or active comparator
- Adverse event rates
- Trial phase and timepoints

After searching, extract the data and return it as JSON with this structure:
{{
  "sources": ["url1", "url2"],
  "efficacy": [
    {{
      "trial_name": "trial name",
      "endpoint_name": "primary endpoint",
      "drug_arm_result": 65.5,
      "comparator_arm_result": 20.0,
      "comparator_arm_name": "Placebo",
      "timepoint": "Week 12",
      "trial_phase": "Phase 3",
      "source_index": 0
    }}
  ],
  "safety": [
    {{
      "adverse_event": "event name",
      "drug_arm_rate": 10.5,
      "comparator_arm_rate": 8.0,
      "is_serious": false,
      "source_index": 0
    }}
  ]
}}

IMPORTANT: Include a "sources" array with all URLs you found data from.
For each efficacy/safety entry, include "source_index" (0-based) pointing to the source URL.

Return ONLY the JSON, no additional text."""
                }]
            )

            # Extract source URLs from web search results
            search_urls = []
            for block in message.content:
                if hasattr(block, 'type') and block.type == 'web_search_tool_result':
                    # Extract URLs from search results
                    if hasattr(block, 'content'):
                        for result in block.content:
                            if hasattr(result, 'url'):
                                search_urls.append(result.url)

            # Parse response
            for block in message.content:
                if block.type == "text":
                    text = block.text.strip()
                    # Clean JSON
                    if "```" in text:
                        import re
                        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
                        if match:
                            text = match.group(1)

                    try:
                        data = json.loads(text)

                        # Get sources from response (or use search_urls as fallback)
                        sources = data.get('sources', []) or search_urls

                        # Add indication and source URL to each result
                        for e in data.get('efficacy', []):
                            e['indication_name'] = indication
                            # Get source URL from index
                            source_idx = e.get('source_index', 0)
                            if sources and 0 <= source_idx < len(sources):
                                e['source_url'] = sources[source_idx]
                            elif sources:
                                e['source_url'] = sources[0]  # Default to first source
                            all_efficacy.append(e)

                        for s in data.get('safety', []):
                            s['indication_name'] = indication
                            # Get source URL from index
                            source_idx = s.get('source_index', 0)
                            if sources and 0 <= source_idx < len(sources):
                                s['source_url'] = sources[source_idx]
                            elif sources:
                                s['source_url'] = sources[0]
                            all_safety.append(s)

                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse JSON for {indication}: {e}")

        except Exception as e:
            logger.error(f"Web search failed for {indication}: {e}")

    logger.info(f"Extracted {len(all_efficacy)} efficacy endpoints from web search")
    logger.info(f"Extracted {len(all_safety)} adverse events from web search")

    # Store in database
    with DatabaseConnection() as db:
        ops = DrugDatabaseOperations(db)

        # Clear existing data first
        ops.clear_efficacy_safety_data(drug_id)

        # Store new data (convert to expected format)
        efficacy_dicts = [{
            'trial_name': e.get('trial_name'),
            'endpoint_name': e.get('endpoint_name'),
            'drug_arm_result': e.get('drug_arm_result'),
            'drug_arm_result_unit': '%',
            'comparator_arm_name': e.get('comparator_arm_name'),
            'comparator_arm_result': e.get('comparator_arm_result'),
            'timepoint': e.get('timepoint'),
            'trial_phase': e.get('trial_phase'),
            'indication_name': e.get('indication_name'),
            'source_url': e.get('source_url'),
            'confidence_score': 0.7,  # Lower confidence for web search
        } for e in all_efficacy]

        safety_dicts = [{
            'adverse_event': s.get('adverse_event'),
            'drug_arm_rate': s.get('drug_arm_rate'),
            'comparator_arm_rate': s.get('comparator_arm_rate'),
            'is_serious': s.get('is_serious', False),
            'indication_name': s.get('indication_name'),
            'source_url': s.get('source_url'),
            'confidence_score': 0.7,
        } for s in all_safety]

        # Update data source to web_search
        with db.cursor() as cur:
            efficacy_count = 0
            for e in efficacy_dicts:
                cur.execute("""
                    INSERT INTO drug_efficacy_data (
                        drug_id, trial_name, endpoint_name, drug_arm_result, drug_arm_result_unit,
                        comparator_arm_name, comparator_arm_result, timepoint, trial_phase,
                        indication_name, confidence_score, data_source, source_url
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'web_search', %s)
                """, (
                    drug_id, e.get('trial_name'), e.get('endpoint_name'),
                    e.get('drug_arm_result'), e.get('drug_arm_result_unit'),
                    e.get('comparator_arm_name'), e.get('comparator_arm_result'),
                    e.get('timepoint'), e.get('trial_phase'),
                    e.get('indication_name'), e.get('confidence_score'),
                    e.get('source_url')
                ))
                efficacy_count += 1

            safety_count = 0
            for s in safety_dicts:
                cur.execute("""
                    INSERT INTO drug_safety_data (
                        drug_id, adverse_event, drug_arm_rate, comparator_arm_rate,
                        is_serious, indication_name, confidence_score, data_source, source_url
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'web_search', %s)
                """, (
                    drug_id, s.get('adverse_event'), s.get('drug_arm_rate'),
                    s.get('comparator_arm_rate'), s.get('is_serious'),
                    s.get('indication_name'), s.get('confidence_score'),
                    s.get('source_url')
                ))
                safety_count += 1

            db.commit()

    logger.info(f"Stored {efficacy_count} efficacy records and {safety_count} safety records")
    return True


def main():
    parser = argparse.ArgumentParser(description="Extract efficacy and safety data for a drug")
    parser.add_argument("--drug", required=True, help="Drug name (generic or brand)")
    parser.add_argument("--investigational", action="store_true",
                        help="Use web search for investigational drugs (no FDA label)")

    args = parser.parse_args()

    # Find drug in database
    with DatabaseConnection() as db:
        with db.cursor() as cur:
            cur.execute("""
                SELECT drug_id, generic_name, approval_status
                FROM drugs
                WHERE generic_name ILIKE %s OR brand_name ILIKE %s
            """, (f"%{args.drug}%", f"%{args.drug}%"))
            drug = cur.fetchone()

    if not drug:
        logger.error(f"Drug '{args.drug}' not found in database")
        sys.exit(1)

    drug_id = drug['drug_id']
    drug_name = drug['generic_name']
    approval_status = drug['approval_status']

    logger.info(f"Found drug: {drug_name} (ID: {drug_id}, Status: {approval_status})")

    # Determine extraction method
    if args.investigational or approval_status == 'investigational':
        success = extract_investigational_drug(drug_name, drug_id)
    else:
        success = extract_approved_drug(drug_name, drug_id)

    if success:
        print(f"\nDone! Efficacy/safety data extracted for {drug_name}.")
        print("View in the Drug Database Viewer.")
    else:
        print(f"\nFailed to extract efficacy/safety data for {drug_name}.")
        sys.exit(1)


if __name__ == "__main__":
    main()
