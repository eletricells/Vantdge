"""
Batch Drug Extraction

Upload a CSV file with drug names to extract and store drug data in batch.
Supports both approved and investigational drugs with checkpoint saving.

Version: 1.0 - 2025-12-29
"""
import streamlit as st
import sys
import os
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from uuid import uuid4
import logging

# Add paths
frontend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from auth import check_password, check_page_access, show_access_denied

st.set_page_config(
    page_title="Batch Drug Extraction",
    page_icon="",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

# Page access check
if not check_page_access("Batch_Drug_Extraction"):
    show_access_denied()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(message)s')
logger = logging.getLogger(__name__)

# Import extraction modules
try:
    from src.drug_extraction_system.database.connection import DatabaseConnection
    from src.drug_extraction_system.database.operations import DrugDatabaseOperations
    from src.drug_extraction_system.extractors.approved_drug_extractor import ApprovedDrugExtractor
    from src.drug_extraction_system.extractors.pipeline_drug_extractor import PipelineDrugExtractor
    from src.drug_extraction_system.services.efficacy_safety_extractor import EfficacySafetyExtractor
    from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
    IMPORTS_OK = True
except ImportError as e:
    IMPORTS_OK = False
    IMPORT_ERROR = str(e)

def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv('DATABASE_URL', '')


# Checkpoint file location
CHECKPOINT_DIR = Path(__file__).parent.parent.parent / "data" / "batch_checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def get_checkpoint_file(batch_id: str) -> Path:
    """Get checkpoint file path for a batch."""
    return CHECKPOINT_DIR / f"batch_{batch_id}.json"


def save_checkpoint(batch_id: str, data: dict):
    """Save checkpoint data to file."""
    checkpoint_file = get_checkpoint_file(batch_id)
    with open(checkpoint_file, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def load_checkpoint(batch_id: str) -> dict:
    """Load checkpoint data from file."""
    checkpoint_file = get_checkpoint_file(batch_id)
    if checkpoint_file.exists():
        with open(checkpoint_file, 'r') as f:
            return json.load(f)
    return None


def list_checkpoints() -> list:
    """List all available checkpoints."""
    checkpoints = []
    for f in CHECKPOINT_DIR.glob("batch_*.json"):
        try:
            data = json.load(open(f))
            checkpoints.append({
                'batch_id': data.get('batch_id'),
                'filename': data.get('filename'),
                'total': data.get('total_drugs', 0),
                'processed': len(data.get('processed', [])),
                'started_at': data.get('started_at'),
                'file': f
            })
        except:
            pass
    return sorted(checkpoints, key=lambda x: x.get('started_at', ''), reverse=True)


def store_drug_data(ops: DrugDatabaseOperations, extracted_data, is_investigational: bool) -> tuple:
    """
    Store extracted drug data to database.

    Returns:
        Tuple of (drug_id, drug_key) or (None, error_message)
    """
    try:
        # Convert dataclass to dict
        drug_dict = {
            'drug_key': extracted_data.drug_key,
            'generic_name': extracted_data.generic_name,
            'brand_name': extracted_data.brand_name,
            'manufacturer': extracted_data.manufacturer,
            'development_code': extracted_data.development_code,
            'drug_type': extracted_data.drug_type,
            'mechanism_of_action': extracted_data.mechanism_of_action,
            'approval_status': extracted_data.approval_status,
            'highest_phase': extracted_data.highest_phase,
            'dailymed_setid': extracted_data.dailymed_setid,
            'first_approval_date': extracted_data.first_approval_date,
            'rxcui': extracted_data.rxcui,
            'chembl_id': extracted_data.chembl_id,
            'inchi_key': extracted_data.inchi_key,
            'cas_number': extracted_data.cas_number,
            'unii': extracted_data.unii,
            'completeness_score': extracted_data.completeness_score,
        }

        # Upsert drug
        drug_id, drug_key = ops.upsert_drug(drug_dict)

        # Store indications
        if extracted_data.indications:
            ops.store_indications(drug_id, extracted_data.indications)

        # Store clinical trials
        if extracted_data.clinical_trials:
            ops.store_clinical_trials(drug_id, extracted_data.clinical_trials)

        # Store dosing regimens (if available and method exists)
        if hasattr(extracted_data, 'dosing_regimens') and extracted_data.dosing_regimens:
            if hasattr(ops, 'store_dosing_regimens'):
                ops.store_dosing_regimens(drug_id, extracted_data.dosing_regimens)

        return (drug_id, drug_key)

    except Exception as e:
        logger.error(f"Failed to store drug data: {e}")
        return (None, str(e))


def extract_efficacy_safety(drug_id: int, drug_name: str, is_investigational: bool):
    """Extract and store efficacy/safety data for a drug."""
    import re
    try:
        if is_investigational:
            # Use web search for investigational drugs
            from anthropic import Anthropic
            anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

            # Get indications
            with DatabaseConnection(database_url=get_database_url()) as db:
                with db.cursor() as cur:
                    cur.execute("""
                        SELECT disease_name FROM drug_indications WHERE drug_id = %s
                    """, (drug_id,))
                    indications = [row['disease_name'] for row in cur.fetchall()]

            if not indications:
                return 0, 0

            # Search for first indication
            indication = indications[0]
            message = anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{
                    "role": "user",
                    "content": f"""Search for clinical trial efficacy and safety data for {drug_name} used to treat {indication}.

Look for Phase 2 or Phase 3 trial results including:
- Primary endpoint response rates
- Comparison to placebo or standard of care
- Common adverse events and rates

Return as JSON:
{{
  "sources": ["url1", "url2"],
  "efficacy": [
    {{"trial_name": "name", "endpoint_name": "endpoint", "drug_arm_result": 65.5, "comparator_arm_result": 20.0, "comparator_arm_name": "Placebo", "timepoint": "Week 12", "trial_phase": "Phase 3", "source_index": 0}}
  ],
  "safety": [
    {{"adverse_event": "event", "drug_arm_rate": 10.5, "comparator_arm_rate": 5.0, "is_serious": false, "source_index": 0}}
  ]
}}

Return ONLY valid JSON."""
                }]
            )

            # Extract sources from web search
            search_urls = []
            for block in message.content:
                if hasattr(block, 'type') and block.type == 'web_search_tool_result':
                    if hasattr(block, 'content'):
                        for result in block.content:
                            if hasattr(result, 'url'):
                                search_urls.append(result.url)

            # Parse response
            efficacy_data = []
            safety_data = []

            for block in message.content:
                if block.type == 'text':
                    text = block.text.strip()
                    # Clean JSON from markdown
                    if '```' in text:
                        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
                        if match:
                            text = match.group(1)

                    try:
                        data = json.loads(text)
                        sources = data.get('sources', []) or search_urls

                        for e in data.get('efficacy', []):
                            e['indication_name'] = indication
                            source_idx = e.get('source_index', 0)
                            if sources and 0 <= source_idx < len(sources):
                                e['source_url'] = sources[source_idx]
                            efficacy_data.append(e)

                        for s in data.get('safety', []):
                            s['indication_name'] = indication
                            source_idx = s.get('source_index', 0)
                            if sources and 0 <= source_idx < len(sources):
                                s['source_url'] = sources[source_idx]
                            safety_data.append(s)

                    except json.JSONDecodeError:
                        pass

            # Store in database
            if efficacy_data or safety_data:
                with DatabaseConnection(database_url=get_database_url()) as db:
                    with db.cursor() as cur:
                        cur.execute('DELETE FROM drug_efficacy_data WHERE drug_id = %s', (drug_id,))
                        cur.execute('DELETE FROM drug_safety_data WHERE drug_id = %s', (drug_id,))

                        eff_count = 0
                        for e in efficacy_data:
                            drug_result = e.get('drug_arm_result')
                            comp_result = e.get('comparator_arm_result')
                            try:
                                drug_result = float(drug_result) if drug_result is not None else None
                            except (ValueError, TypeError):
                                drug_result = None
                            try:
                                comp_result = float(comp_result) if comp_result is not None else None
                            except (ValueError, TypeError):
                                comp_result = None

                            cur.execute("""
                                INSERT INTO drug_efficacy_data (
                                    drug_id, trial_name, endpoint_name, drug_arm_result, drug_arm_result_unit,
                                    comparator_arm_name, comparator_arm_result, timepoint, trial_phase,
                                    indication_name, confidence_score, data_source, source_url
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'web_search', %s)
                            """, (
                                drug_id, e.get('trial_name'), e.get('endpoint_name'),
                                drug_result, '%',
                                e.get('comparator_arm_name'), comp_result,
                                e.get('timepoint'), e.get('trial_phase'),
                                e.get('indication_name'), 0.7, e.get('source_url')
                            ))
                            eff_count += 1

                        safety_count = 0
                        for s in safety_data:
                            drug_rate = s.get('drug_arm_rate')
                            comp_rate = s.get('comparator_arm_rate')
                            try:
                                drug_rate = float(drug_rate) if drug_rate is not None else None
                            except (ValueError, TypeError):
                                drug_rate = None
                            try:
                                comp_rate = float(comp_rate) if comp_rate is not None else None
                            except (ValueError, TypeError):
                                comp_rate = None

                            cur.execute("""
                                INSERT INTO drug_safety_data (
                                    drug_id, adverse_event, drug_arm_rate, comparator_arm_rate,
                                    is_serious, indication_name, confidence_score, data_source, source_url
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'web_search', %s)
                            """, (
                                drug_id, s.get('adverse_event'), drug_rate,
                                comp_rate, s.get('is_serious', False),
                                s.get('indication_name'), 0.7, s.get('source_url')
                            ))
                            safety_count += 1

                        db.commit()

                return eff_count, safety_count

            return 0, 0

        else:
            # Use OpenFDA for approved drugs
            openfda = OpenFDAClient()

            # Get brand name from database as fallback
            brand_name = None
            with DatabaseConnection(database_url=get_database_url()) as db:
                with db.cursor() as cur:
                    cur.execute("SELECT brand_name FROM drugs WHERE drug_id = %s", (drug_id,))
                    row = cur.fetchone()
                    if row:
                        brand_name = row['brand_name']

            # Try generic name first
            labels = openfda.search_drug_labels(drug_name, limit=1)

            # Check if label has required sections, try brand name if not
            if labels:
                label = labels[0]
                has_clinical = label.get('clinical_studies') or label.get('adverse_reactions')
                if not has_clinical and brand_name:
                    brand_labels = openfda.search_drug_labels(brand_name, limit=1)
                    if brand_labels:
                        labels = brand_labels
            elif brand_name:
                labels = openfda.search_drug_labels(brand_name, limit=1)

            if not labels:
                return 0, 0

            extractor = EfficacySafetyExtractor()
            efficacy_results, safety_results = extractor.extract_from_label(drug_name, labels[0])

            with DatabaseConnection(database_url=get_database_url()) as db:
                ops = DrugDatabaseOperations(db)
                ops.clear_efficacy_safety_data(drug_id)
                eff_count = ops.store_efficacy_data(drug_id, efficacy_results)
                safety_count = ops.store_safety_data(drug_id, safety_results)

            return eff_count, safety_count

    except Exception as e:
        logger.error(f"Failed to extract efficacy/safety: {e}")
        return 0, 0


def process_drug(drug_name: str, is_investigational: bool, development_code: str = None,
                 extract_efficacy: bool = True) -> dict:
    """
    Process a single drug through the extraction pipeline.

    Returns:
        Dict with status, drug_id, drug_key, and any errors
    """
    result = {
        'drug_name': drug_name,
        'status': 'pending',
        'drug_id': None,
        'drug_key': None,
        'error': None,
        'efficacy_count': 0,
        'safety_count': 0,
    }

    try:
        # Step 1: Extract drug data
        if is_investigational:
            extractor = PipelineDrugExtractor()
            extracted_data = extractor.extract(drug_name, development_code=development_code)
        else:
            extractor = ApprovedDrugExtractor()
            extracted_data = extractor.extract(drug_name, development_code=development_code)

        if not extracted_data or not extracted_data.generic_name:
            result['status'] = 'failed'
            result['error'] = 'No data extracted'
            return result

        # Step 2: Store to database
        with DatabaseConnection(database_url=get_database_url()) as db:
            ops = DrugDatabaseOperations(db)
            store_result = store_drug_data(ops, extracted_data, is_investigational)

            if store_result[0] is None:
                result['status'] = 'failed'
                result['error'] = store_result[1]
                return result

            result['drug_id'] = store_result[0]
            result['drug_key'] = store_result[1]

        # Step 3: Extract efficacy/safety (optional)
        if extract_efficacy:
            eff_count, safety_count = extract_efficacy_safety(
                result['drug_id'],
                extracted_data.generic_name,
                bool(is_investigational)  # Ensure Python bool
            )
            result['efficacy_count'] = eff_count
            result['safety_count'] = safety_count

        result['status'] = 'success'
        return result

    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)
        logger.exception(f"Error processing {drug_name}: {e}")
        import traceback
        traceback.print_exc()
        return result


# Page header
st.title("Batch Drug Extraction")
st.markdown("Upload a CSV file with drug names to extract and store drug data in batch.")

if not IMPORTS_OK:
    st.error(f"Failed to import required modules: {IMPORT_ERROR}")
    st.stop()

st.markdown("---")

# Sidebar - Configuration and stats
with st.sidebar:
    st.markdown("## Configuration")

    # Check database connection
    try:
        with DatabaseConnection(database_url=get_database_url()) as db:
            with db.cursor() as cur:
                cur.execute("SELECT COUNT(*) as count FROM drugs")
                drug_count = cur.fetchone()['count']
        st.success("Database connected")
        st.metric("Drugs in Database", drug_count)
    except Exception as e:
        st.error(f"Database error: {e}")
        st.stop()

    st.markdown("---")
    st.markdown("## Resume Previous Batch")

    # Show available checkpoints
    checkpoints = list_checkpoints()
    if checkpoints:
        for cp in checkpoints[:5]:
            remaining = cp['total'] - cp['processed']
            if remaining > 0:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.text(f"{cp['filename'][:20]}...")
                    st.caption(f"{cp['processed']}/{cp['total']} processed")
                with col2:
                    if st.button("Resume", key=f"resume_{cp['batch_id']}"):
                        st.session_state['resume_batch_id'] = cp['batch_id']
                        st.rerun()
    else:
        st.info("No pending batches")

# Main content
tab1, tab2 = st.tabs(["New Batch", "Processing Status"])

with tab1:
    # Input method selection
    input_method = st.radio(
        "Input Method",
        ["Type Drug Names", "Upload CSV File"],
        horizontal=True,
        help="Choose how to enter drug names"
    )

    df = None
    source_name = "manual_input"

    if input_method == "Type Drug Names":
        st.markdown("### Enter Drug Names")
        st.markdown("Enter drug names separated by commas, or one per line.")

        # Text area for drug names
        drug_text = st.text_area(
            "Drug Names",
            placeholder="brepocitinib, baricitinib, tofacitinib\n\nOR\n\nbrepocitinib\nbaricitinib\ntofacitinib",
            height=150,
            help="Enter generic or brand names, separated by commas or newlines"
        )

        # Option to mark all as investigational
        all_investigational = st.checkbox(
            "All drugs are investigational",
            value=False,
            help="Check if all drugs in the list are investigational (not FDA-approved)"
        )

        if drug_text.strip():
            # Parse drug names - split by comma or newline
            import re
            # Split by comma or newline, strip whitespace
            drug_names = re.split(r'[,\n]+', drug_text)
            drug_names = [name.strip() for name in drug_names if name.strip()]

            if drug_names:
                # Create dataframe
                df = pd.DataFrame({
                    'drug_name': drug_names,
                    'is_investigational': all_investigational,
                    'development_code': ''
                })
                source_name = "manual_input"

                st.success(f"Parsed {len(df)} drug names")

    else:  # Upload CSV File
        st.markdown("### Upload CSV File")

        st.markdown("""
        **CSV Format Requirements:**
        - Required column: `drug_name` (generic or brand name)
        - Optional columns:
          - `is_investigational` (true/false) - defaults to false
          - `development_code` (e.g., LNP023, BMS-986165)
        """)

        # Example CSV
        with st.expander("Example CSV Format"):
            example_df = pd.DataFrame({
                'drug_name': ['secukinumab', 'batoclimab', 'upadacitinib'],
                'is_investigational': [False, True, False],
                'development_code': ['', 'HBM9161', '']
            })
            st.dataframe(example_df, hide_index=True)

            # Download example
            csv = example_df.to_csv(index=False)
            st.download_button(
                "Download Example CSV",
                csv,
                "drug_list_example.csv",
                "text/csv"
            )

        # File upload
        uploaded_file = st.file_uploader(
            "Choose a CSV file",
            type=['csv'],
            help="Upload a CSV with drug_name column"
        )

        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                source_name = uploaded_file.name

                # Validate required column
                if 'drug_name' not in df.columns:
                    st.error("CSV must contain a 'drug_name' column")
                    df = None

            except Exception as e:
                st.error(f"Error reading CSV: {e}")
                df = None

    # Process dataframe if we have one
    if df is not None and len(df) > 0:
        # Clean data
        df['drug_name'] = df['drug_name'].astype(str).str.strip()
        df = df[df['drug_name'].notna() & (df['drug_name'] != '') & (df['drug_name'] != 'nan')]

        # Add optional columns if missing
        if 'is_investigational' not in df.columns:
            df['is_investigational'] = False
        else:
            df['is_investigational'] = df['is_investigational'].fillna(False).astype(bool)

        if 'development_code' not in df.columns:
            df['development_code'] = ''
        else:
            df['development_code'] = df['development_code'].fillna('').astype(str)

        if len(df) == 0:
            st.warning("No valid drug names found")
        else:
            # Preview
            st.markdown("### Preview")
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Options
            st.markdown("### Extraction Options")

            col1, col2 = st.columns(2)
            with col1:
                should_extract_efficacy = st.checkbox(
                    "Extract efficacy/safety data",
                    value=True,
                    help="Extract clinical trial efficacy and safety data (takes longer)"
                )

            with col2:
                skip_existing = st.checkbox(
                    "Skip existing drugs",
                    value=True,
                    help="Skip drugs already in database"
                )

            st.markdown("---")

            # Start extraction button
            if st.button("Start Batch Extraction", type="primary", use_container_width=True):
                # Initialize batch
                batch_id = str(uuid4())[:8]

                # Create checkpoint
                checkpoint_data = {
                    'batch_id': batch_id,
                    'filename': source_name,
                    'started_at': datetime.now().isoformat(),
                    'total_drugs': len(df),
                    'drugs': df.to_dict('records'),
                    'processed': [],
                    'successful': [],
                    'failed': [],
                    'skipped': [],
                    'options': {
                        'extract_efficacy_safety': should_extract_efficacy,
                        'skip_existing': skip_existing
                    }
                }
                save_checkpoint(batch_id, checkpoint_data)

                st.session_state['current_batch_id'] = batch_id
                st.session_state['batch_started'] = True
                st.rerun()

    # Show help message if no input yet
    if df is None or len(df) == 0:
        if input_method == "Type Drug Names":
            if 'drug_text' not in dir() or not drug_text.strip():
                st.info("Enter drug names above to get started")
        else:
            if 'uploaded_file' not in dir() or uploaded_file is None:
                st.info("Upload a CSV file to get started")

with tab2:
    # Check if we have an active batch
    batch_id = st.session_state.get('current_batch_id') or st.session_state.get('resume_batch_id')

    if batch_id:
        checkpoint = load_checkpoint(batch_id)

        if checkpoint:
            st.markdown(f"### Batch: {checkpoint['filename']}")
            st.caption(f"Batch ID: {batch_id} | Started: {checkpoint.get('started_at', 'Unknown')}")

            # Progress metrics
            total = checkpoint['total_drugs']
            processed = len(checkpoint.get('processed', []))
            successful = len(checkpoint.get('successful', []))
            failed = len(checkpoint.get('failed', []))
            skipped = len(checkpoint.get('skipped', []))
            remaining = total - processed

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total", total)
            with col2:
                st.metric("Successful", successful)
            with col3:
                st.metric("Failed", failed)
            with col4:
                st.metric("Remaining", remaining)

            # Progress bar
            progress = processed / total if total > 0 else 0
            st.progress(progress, text=f"{processed}/{total} processed ({progress*100:.1f}%)")

            # Process remaining drugs
            if remaining > 0 and (st.session_state.get('batch_started') or st.session_state.get('resume_batch_id')):
                st.markdown("---")
                st.markdown("### Processing...")

                options = checkpoint.get('options', {})
                extract_eff = options.get('extract_efficacy_safety', True)
                skip_existing = options.get('skip_existing', True)

                # Status containers
                status_container = st.empty()
                log_container = st.container()

                # Process each remaining drug
                drugs = checkpoint['drugs']
                processed_names = set(checkpoint.get('processed', []))

                for i, drug_row in enumerate(drugs):
                    drug_name = drug_row['drug_name']

                    # Skip already processed
                    if drug_name in processed_names:
                        continue

                    # Update status
                    with status_container:
                        st.info(f"Processing: **{drug_name}** ({processed + 1}/{total})")

                    # Check if drug exists (if skip_existing)
                    if skip_existing:
                        try:
                            with DatabaseConnection(database_url=get_database_url()) as db:
                                with db.cursor() as cur:
                                    cur.execute("""
                                        SELECT drug_id FROM drugs
                                        WHERE generic_name ILIKE %s OR brand_name ILIKE %s
                                    """, (drug_name, drug_name))
                                    existing = cur.fetchone()

                                    if existing:
                                        checkpoint['skipped'].append(drug_name)
                                        checkpoint['processed'].append(drug_name)
                                        save_checkpoint(batch_id, checkpoint)

                                        with log_container:
                                            st.info(f"Skipped: {drug_name} (already exists)")
                                        continue
                        except Exception as e:
                            logger.warning(f"Error checking existing drug: {e}")

                    # Process drug
                    is_investigational = drug_row.get('is_investigational', False)
                    # Ensure is_investigational is a Python bool (not numpy.bool_)
                    is_investigational = bool(is_investigational) if is_investigational else False
                    dev_code = drug_row.get('development_code', '') or None

                    result = process_drug(
                        drug_name,
                        is_investigational=is_investigational,
                        development_code=dev_code,
                        extract_efficacy=extract_eff
                    )

                    # Update checkpoint
                    checkpoint['processed'].append(drug_name)

                    if result['status'] == 'success':
                        checkpoint['successful'].append({
                            'drug_name': drug_name,
                            'drug_id': result['drug_id'],
                            'drug_key': result['drug_key'],
                            'efficacy_count': result['efficacy_count'],
                            'safety_count': result['safety_count']
                        })
                        with log_container:
                            st.success(f"Success: {drug_name} (ID: {result['drug_id']})")
                    else:
                        checkpoint['failed'].append({
                            'drug_name': drug_name,
                            'error': result['error']
                        })
                        with log_container:
                            st.error(f"Failed: {drug_name} - {result['error']}")

                    # Save checkpoint after each drug
                    save_checkpoint(batch_id, checkpoint)

                    # Update progress
                    processed = len(checkpoint['processed'])
                    progress = processed / total
                    st.progress(progress, text=f"{processed}/{total} processed ({progress*100:.1f}%)")

                # Complete
                with status_container:
                    st.success("Batch processing complete!")

                # Clear session state
                st.session_state.pop('batch_started', None)
                st.session_state.pop('resume_batch_id', None)

                # Final summary
                st.markdown("---")
                st.markdown("### Final Summary")

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Successful", len(checkpoint['successful']))
                with col2:
                    st.metric("Failed", len(checkpoint['failed']))
                with col3:
                    st.metric("Skipped", len(checkpoint['skipped']))

                # Details
                if checkpoint['successful']:
                    with st.expander(f"Successful ({len(checkpoint['successful'])})", expanded=True):
                        for s in checkpoint['successful']:
                            st.markdown(f"- **{s['drug_name']}** (ID: {s['drug_id']})")

                if checkpoint['failed']:
                    with st.expander(f"Failed ({len(checkpoint['failed'])})", expanded=True):
                        for f in checkpoint['failed']:
                            st.markdown(f"- **{f['drug_name']}**: {f['error']}")

                if checkpoint['skipped']:
                    with st.expander(f"Skipped ({len(checkpoint['skipped'])})", expanded=False):
                        for s in checkpoint['skipped']:
                            st.markdown(f"- {s}")

            elif remaining == 0:
                st.success("Batch complete!")

                # Show final summary
                if checkpoint['successful']:
                    with st.expander(f"Successful ({len(checkpoint['successful'])})", expanded=True):
                        for s in checkpoint['successful']:
                            st.markdown(f"- **{s['drug_name']}** (ID: {s['drug_id']})")

                if checkpoint['failed']:
                    with st.expander(f"Failed ({len(checkpoint['failed'])})", expanded=True):
                        for f in checkpoint['failed']:
                            st.markdown(f"- **{f['drug_name']}**: {f['error']}")

            else:
                # Not started yet - show resume button
                if st.button("Start Processing", type="primary"):
                    st.session_state['batch_started'] = True
                    st.rerun()
        else:
            st.info("No active batch. Upload a CSV file to start.")
    else:
        st.info("No active batch. Upload a CSV file to start.")

# Footer
st.markdown("---")
with st.expander("How Batch Processing Works"):
    st.markdown("""
    ### Batch Extraction Process

    1. **Upload CSV**: Provide a list of drug names (generic or brand)
    2. **Validation**: System validates the CSV format and drug names
    3. **Extraction**: For each drug:
       - **Approved drugs**: Extract from OpenFDA + DailyMed + RxNorm + ClinicalTrials.gov
       - **Investigational drugs**: Extract from ClinicalTrials.gov + RxNorm
    4. **Storage**: Data is saved to database after each drug (checkpoint)
    5. **Efficacy/Safety**: Optionally extract clinical trial efficacy and safety data

    ### Checkpoint System

    - Progress is saved after each drug is processed
    - If the process is interrupted, you can resume from where it left off
    - Checkpoints are stored in `data/batch_checkpoints/`

    ### Tips

    - Use "Skip existing drugs" to avoid reprocessing drugs already in database
    - For large batches (50+ drugs), consider running in smaller batches
    - Investigational drugs take longer due to clinical trial data extraction
    """)
