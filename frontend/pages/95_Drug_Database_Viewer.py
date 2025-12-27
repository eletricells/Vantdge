"""
Drug Database Viewer - Visual display of extracted drug data

Displays drug information in a card format similar to the reference design.

Version: 2.2 - Updated 2025-12-26
- Fixed UTF-8 BOM encoding issue causing random characters
- Fixed approval dates display in indication cards
- Fixed clinical trials section to handle JSON string conditions
- Added debug sections for troubleshooting
"""
import streamlit as st
import sys
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal

# Add paths
frontend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auth import check_password

st.set_page_config(
    page_title="Drug Database Viewer",
    page_icon="",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

# Import after auth check
from dotenv import load_dotenv
load_dotenv()

from src.drug_extraction_system.database.connection import DatabaseConnection
from src.drug_extraction_system.database.operations import DrugDatabaseOperations


def get_status_color(status: str) -> str:
    """Get color based on approval status."""
    status_lower = (status or "").lower()
    if status_lower == "approved":
        return "#10b981"  # Green
    elif status_lower == "investigational":
        return "#f59e0b"  # Orange/Yellow
    else:
        return "#3b82f6"  # Blue


def get_status_badge_style(status: str) -> str:
    """Get badge CSS style based on status."""
    status_lower = (status or "").lower()
    if status_lower == "approved":
        return "background-color: #d1fae5; color: #065f46;"
    elif status_lower == "investigational":
        return "background-color: #fef3c7; color: #92400e;"
    else:
        return "background-color: #dbeafe; color: #1e40af;"


def format_value(val):
    """Format value for display."""
    if val is None:
        return "N/A"
    if isinstance(val, Decimal):
        return f"{float(val):.1%}"
    if isinstance(val, (date, datetime)):
        return val.strftime("%Y-%m-%d")
    return str(val)


# Page header
st.title(" Drug Database Viewer")
st.markdown("View extracted drug data from the database")
st.info(" Version 2.5 - All emojis and special characters removed")
st.markdown("---")

# Get all drugs for dropdown
try:
    with DatabaseConnection() as db:
        with db.cursor() as cur:
            cur.execute("""
                SELECT drug_id, drug_key, generic_name, brand_name, 
                       approval_status, highest_phase, completeness_score
                FROM drugs 
                WHERE drug_key IS NOT NULL
                ORDER BY generic_name
            """)
            drugs_list = [dict(row) for row in cur.fetchall()]

    if not drugs_list:
        st.warning("No drugs found in the database. Please extract some drugs first using the Drug Extraction System.")
        st.code("python -m src.drug_extraction_system.main --drug \"upadacitinib\"", language="bash")
        st.stop()

    # Create dropdown options
    drug_options = {
        f"{d['generic_name']} ({d['brand_name'] or 'No brand'}) - {d['approval_status'] or 'Unknown'}": d['drug_id']
        for d in drugs_list
    }

    # Sidebar with dropdown
    with st.sidebar:
        st.markdown("##  Select Drug")
        selected_drug_label = st.selectbox(
            "Choose a drug to view",
            options=list(drug_options.keys()),
            index=0
        )
        selected_drug_id = drug_options[selected_drug_label]

        st.markdown("---")
        st.markdown("##  Database Stats")
        st.metric("Total Drugs", len(drugs_list))

        # Count by status
        approved_count = sum(1 for d in drugs_list if (d.get('approval_status') or '').lower() == 'approved')
        pipeline_count = len(drugs_list) - approved_count
        st.metric("Approved", approved_count)
        st.metric("Pipeline", pipeline_count)

except Exception as e:
    st.error(f"Database connection error: {e}")
    st.stop()

# Get detailed drug data
trials = []
sources = []
try:
    with DatabaseConnection() as db:
        ops = DrugDatabaseOperations(db)
        drug = ops.get_drug_with_details(selected_drug_id)

        if not drug:
            st.error("Drug not found")
            st.stop()

        # Get clinical trials
        with db.cursor() as cur:
            cur.execute("""
                SELECT nct_id, trial_title, trial_phase, trial_status, conditions, sponsors
                FROM drug_clinical_trials 
                WHERE drug_id = %s 
                ORDER BY trial_phase DESC
                LIMIT 50
            """, (selected_drug_id,))

        # Get data sources
        with db.cursor() as cur:
            cur.execute("""
                SELECT source_name, source_url, data_retrieved_at
                FROM drug_data_sources
                WHERE drug_id = %s
            """, (selected_drug_id,))
            sources = [dict(row) for row in cur.fetchall()]

except Exception as e:
    st.error(f"Error loading drug data: {e}")
    st.stop()
# Debug: Show raw data
with st.expander(" Debug: Raw Data", expanded=False):
    st.write("**Target:**", drug.get('target'))
    st.write("**MoA Category:**", drug.get('moa_category'))
    st.write("**Indications count:**", len(drug.get('indications', [])))
    if drug.get('indications'):
        st.write("**First indication approval_date:**", drug['indications'][0].get('approval_date'))
    st.write("**Dosing regimens count:**", len(drug.get('dosing_regimens', [])))


# Display drug card
status = drug.get('approval_status', 'Unknown')
status_color = get_status_color(status)

# Custom CSS for card styling
st.markdown(f"""
<style>
    .drug-card {{
        background: #f7fafc;
        border-radius: 12px;
        padding: 25px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        border-top: 5px solid {status_color};
        margin-bottom: 20px;
    }}
    .drug-name {{
        font-size: 28px;
        font-weight: bold;
        color: #2d3748;
        margin-bottom: 5px;
    }}
    .drug-status {{
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        {get_status_badge_style(status)}
    }}
    .section-title {{
        font-size: 16px;
        font-weight: bold;
        color: #4c51bf;
        margin: 20px 0 10px 0;
        border-bottom: 2px solid #e2e8f0;
        padding-bottom: 5px;
    }}
    .info-row {{
        display: flex;
        padding: 8px 0;
        border-bottom: 1px solid #e2e8f0;
    }}
    .info-label {{
        font-weight: 600;
        color: #4a5568;
        min-width: 160px;
    }}
    .info-value {{
        color: #2d3748;
    }}
    .badge {{
        display: inline-block;
        padding: 3px 10px;
        margin: 3px;
        background: #edf2f7;
        border-radius: 12px;
        font-size: 12px;
        color: #4a5568;
    }}
    .highlight {{
        background: #fef5e7;
        padding: 2px 6px;
        border-radius: 3px;
        font-weight: 500;
    }}
    .completeness-bar {{
        height: 8px;
        background: #e2e8f0;
        border-radius: 4px;
        overflow: hidden;
    }}
    .completeness-fill {{
        height: 100%;
        background: linear-gradient(90deg, #10b981, #3b82f6);
        border-radius: 4px;
    }}
</style>
""", unsafe_allow_html=True)

# Drug Header
brand_name = drug.get('brand_name') or 'No Brand Name'
generic_name = drug.get('generic_name', 'Unknown')
completeness = float(drug.get('completeness_score') or 0)

st.markdown(f"""
<div class="drug-card">
    <div class="drug-name">{brand_name} ({generic_name})</div>
    <span class="drug-status">{status.upper() if status else 'UNKNOWN'}</span>
    <span style="margin-left: 10px; color: #718096;">Drug Key: {drug.get('drug_key', 'N/A')}</span>
    <div style="margin-top: 15px;">
        <span style="font-size: 12px; color: #718096;">Completeness: {completeness:.0%}</span>
        <div class="completeness-bar">
            <div class="completeness-fill" style="width: {completeness*100}%;"></div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Main content in columns
col1, col2 = st.columns(2)

with col1:
    st.markdown("###  Core Information")

    info_items = [
        ("Brand Name", brand_name),
        ("Generic Name", generic_name),
        ("Manufacturer", drug.get('manufacturer', 'N/A')),
        ("Drug Type", drug.get('drug_type', 'Not specified')),
        ("Target", drug.get('target', 'N/A')),
        ("MoA Category", drug.get('moa_category', 'N/A')),
        ("Highest Phase", drug.get('highest_phase', 'N/A')),
        ("First Approval", format_value(drug.get('first_approval_date'))),
        ("RxCUI", drug.get('rxcui') or drug.get('identifiers', {}).get('rxcui', 'N/A')),
        ("UNII", drug.get('unii') or drug.get('identifiers', {}).get('unii', 'N/A')),
    ]

    for label, value in info_items:
        st.markdown(f"**{label}:** {value}")

with col2:
    st.markdown("###  Mechanism of Action")
    moa = drug.get('mechanism_of_action', 'Not available')
    if moa and len(moa) > 500:
        with st.expander("View full mechanism", expanded=False):
            st.write(moa)
        st.write(moa[:500] + "...")
    else:
        st.write(moa or "Not available")

# Indications section
st.markdown("---")
st.markdown("###  Indications")

indications = drug.get('indications', [])
if indications:
    ind_cols = st.columns(min(len(indications), 4))
    for i, ind in enumerate(indications):
        with ind_cols[i % 4]:
            disease = ind.get('disease_name') or 'Unknown Indication'
            ind_status = ind.get('approval_status', 'unknown')
            approval_date = ind.get('approval_date')

            # Determine status color
            if ind_status == 'approved':
                status_style = "background-color: #d1fae5; color: #065f46;"
            elif ind_status == 'investigational':
                status_style = "background-color: #fef3c7; color: #92400e;"
            else:
                status_style = "background-color: #e5e7eb; color: #374151;"

            # Format approval date
            approval_text = ""
            if approval_date:
                if isinstance(approval_date, str):
                    approval_text = f'<div style="color: #64748b; font-size: 11px; margin-top: 4px;"> Approved: {approval_date}</div>'
                else:
                    approval_text = f'<div style="color: #64748b; font-size: 11px; margin-top: 4px;"> Approved: {approval_date.strftime("%Y-%m-%d")}</div>'

            st.markdown(f"""
            <div style="background-color: #f8fafc; border-radius: 8px; padding: 12px; margin-bottom: 10px; border: 1px solid #e2e8f0;">
                <div style="font-weight: 600; font-size: 14px; color: #1e293b; margin-bottom: 4px;">{disease}</div>
                <div style="{status_style} display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-bottom: 4px;">{ind_status.title()}</div>
                {approval_text}
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("No indications extracted")

# Dosing section
st.markdown("---")
st.markdown("###  Dosing Regimens")

dosing = drug.get('dosing_regimens', [])
if dosing:
    import pandas as pd
    
    # Get all indication names
    indication_map = {ind.get('indication_id'): ind.get('disease_name', 'General') 
                     for ind in drug.get('indications', [])}
    all_indications = list(indication_map.values())
    
    is_approved = drug.get('approval_status') == 'approved'

    # Check if we have only 1 unique dosing regimen
    unique_regimens = {}
    for d in dosing:
        key = (d.get('regimen_phase'), d.get('dose_amount'), d.get('dose_unit'),
               d.get('frequency_raw') or d.get('frequency_standard'),
               d.get('route_raw') or d.get('route_standard'))
        if key not in unique_regimens:
            unique_regimens[key] = d
    
    # If only 1 unique regimen and multiple indications, expand to all
    should_expand = (len(unique_regimens) == 1 and len(all_indications) > 1)

    dosing_data = []
    seen_regimens = set()
    
    for d in dosing:
        indication_id = d.get('indication_id')
        
        # Determine target indications
        if should_expand:
            target_indications = all_indications if all_indications else ['General']
        elif indication_id and indication_id in indication_map:
            target_indications = [indication_map[indication_id]]
        else:
            target_indications = ['General']
        
        # Create unique key for deduplication
        regimen_key = (d.get('regimen_phase'), d.get('dose_amount'), d.get('dose_unit'),
                      d.get('frequency_raw') or d.get('frequency_standard'),
                      d.get('route_raw') or d.get('route_standard'))
        
        # Skip if already seen
        if regimen_key in seen_regimens:
            continue
        seen_regimens.add(regimen_key)

        # Determine status
        phase_value = "Approved" if is_approved else (d.get('regimen_phase', 'N/A').title())

        # Create one row per target indication
        for indication_name in target_indications:
            row = {
                "Indication": indication_name,
                "Status": phase_value,
                "Dosing Type": (d.get('regimen_phase') or 'N/A').title(),
                "Dose": f"{d.get('dose_amount', 'N/A')} {d.get('dose_unit', '')}",
                "Frequency": d.get('frequency_raw') or d.get('frequency_standard', 'N/A'),
                "Route": d.get('route_raw') or d.get('route_standard', 'N/A')
            }
            dosing_data.append(row)

    st.dataframe(pd.DataFrame(dosing_data), use_container_width=True, hide_index=True)

else:
    st.info("No dosing regimens extracted")


# Clinical Trials section
st.markdown("---")
st.markdown("###  Clinical Trials")

# Debug trials data
with st.expander(" Debug: Clinical Trials Data", expanded=False):
    st.write(f"**Total trials found:** {len(trials)}")
    if trials:
        st.write("**First trial sample:**")
        st.json(trials[0])

if trials:
    import re
    
    # Helper function to extract trial acronym
    def extract_acronym(title):
        if not title:
            return None
        # Pattern 1: Acronym at start with colon - "SELECT-SLE: A Phase 3 Study..."
        start_match = re.match(r'^([A-Z][A-Za-z0-9\-]{2,}):\s', title)
        if start_match:
            acronym = start_match.group(1)
            if acronym not in ['LTE', 'IMID', 'RCT', 'OLE']:
                return acronym
        
        # Pattern 2: Acronym in parentheses/brackets - "A Study (FIXTURE) of..."
        paren_match = re.search(r'[\(\[]([A-Z][A-Za-z0-9\-]{2,})[\)\]]', title)
        if paren_match:
            acronym = paren_match.group(1)
            if acronym not in ['LTE', 'IMID', 'RCT', 'OLE']:
                return acronym
        
        return None
    
    # Group trials by indication
    indication_trials = {}
    other_trials = []

    for trial in trials:
        conditions = trial.get('conditions', [])

        # Handle conditions as either list, string, or None
        if isinstance(conditions, str):
            import json
            try:
                # Try to parse as JSON array
                conditions = json.loads(conditions)
            except:
                # If not JSON, treat as single condition
                conditions = [conditions] if conditions else []
        elif not isinstance(conditions, list):
            conditions = []

        if conditions:
            # Use first condition as primary indication
            primary_condition = conditions[0]
            if primary_condition not in indication_trials:
                indication_trials[primary_condition] = []
            indication_trials[primary_condition].append(trial)
        else:
            other_trials.append(trial)
    
    # Display trials grouped by indication
    for indication, indication_trial_list in sorted(indication_trials.items()):
        with st.expander(f"**{indication}** ({len(indication_trial_list)} trials)", expanded=False):
            # Sort by phase (Phase 3 > Phase 2 > Phase 1)
            phase_order = {'Phase 4': 4, 'Phase 3': 3, 'Phase 2': 2, 'Phase 1': 1, 'Phase 2/Phase 3': 2.5}
            sorted_trials = sorted(indication_trial_list, 
                                 key=lambda t: phase_order.get(t.get('trial_phase', ''), 0), 
                                 reverse=True)
            
            for trial in sorted_trials:
                nct_id = trial.get('nct_id', 'Unknown')
                title = trial.get('trial_title', 'No title')
                phase = trial.get('trial_phase', 'Unknown')
                trial_status = trial.get('trial_status', 'Unknown')
                
                # Extract acronym
                acronym = extract_acronym(title)
                
                # Create display title
                if acronym:
                    display_title = f"{acronym}: {title[:80]}{'...' if len(title) > 80 else ''}"
                else:
                    display_title = f"{title[:100]}{'...' if len(title) > 100 else ''}"
                
                st.markdown(f"""
                - **[{nct_id}](https://clinicaltrials.gov/study/{nct_id})** - {phase} - {trial_status}
                  - {display_title}
                """)
    
    # Display other trials
    if other_trials:
        with st.expander(f"**Other Trials** ({len(other_trials)} trials)", expanded=False):
            for trial in other_trials[:10]:
                nct_id = trial.get('nct_id', 'Unknown')
                title = trial.get('trial_title', 'No title')
                phase = trial.get('trial_phase', 'Unknown')
                trial_status = trial.get('trial_status', 'Unknown')
                
                acronym = extract_acronym(title)
                if acronym:
                    display_title = f"{acronym}: {title[:80]}{'...' if len(title) > 80 else ''}"
                else:
                    display_title = f"{title[:100]}{'...' if len(title) > 100 else ''}"
                
                st.markdown(f"""
                - **[{nct_id}](https://clinicaltrials.gov/study/{nct_id})** - {phase} - {trial_status}
                  - {display_title}
                """)
else:
    st.info("No clinical trials linked")

# Data Sources section
st.markdown("---")
st.markdown("###  Data Sources")

if sources:
    source_text = []
    for s in sources:
        source_text.append(f" {s.get('source_name', 'Unknown')}")
    st.markdown("  \n".join(source_text))
else:
    # Show identifiers as sources
    identifiers = drug.get('identifiers', {})
    if identifiers:
        st.markdown("**External Identifiers:**")
        for id_type, id_value in identifiers.items():
            st.markdown(f"- {id_type}: `{id_value}`")
    else:
        st.info("No data sources recorded")

# Raw JSON view
with st.expander(" View Raw Data (JSON)"):
    # Convert for JSON display
    import json
    from datetime import date, datetime
    from decimal import Decimal

    def json_serializer(obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return str(obj)

    st.json(json.loads(json.dumps(drug, default=json_serializer)))

# Footer
st.markdown("---")
st.caption("Data extracted using the Drug Extraction System from openFDA, RxNorm, ClinicalTrials.gov, and other sources.")

