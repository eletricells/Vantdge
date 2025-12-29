"""
Drug Database Viewer - Visual display of extracted drug data

Displays drug information in a card format similar to the reference design.

Version: 2.5 - Updated 2025-12-27
- Added standardized condition grouping (from condition_standardizer)
- Trials now grouped by therapeutic area, then by standardized condition
- Enhanced debug panel with metrics and error display
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
    page_icon="🔬",
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
st.title("Drug Database Viewer")
st.markdown("View extracted drug data from the database")
st.info("Version 2.5 - Standardized conditions with therapeutic area grouping")
# Force page refresh indicator
import time
st.caption(f"Last loaded: {time.strftime('%Y-%m-%d %H:%M:%S')}")
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
        st.markdown("## Select Drug")
        selected_drug_label = st.selectbox(
            "Choose a drug to view",
            options=list(drug_options.keys()),
            index=0
        )
        selected_drug_id = drug_options[selected_drug_label]

        st.markdown("---")
        st.markdown("## Database Stats")
        st.metric("Total Drugs", len(drugs_list))

        # Count by status
        approved_count = sum(1 for d in drugs_list if (d.get('approval_status') or '').lower() == 'approved')
        pipeline_count = len(drugs_list) - approved_count
        st.metric("Approved", approved_count)
        st.metric("Pipeline", pipeline_count)

except Exception as e:
    st.error(f"Database connection error: {e}")
    st.stop()

# Initialize variables
trials = []
sources = []

# Get detailed drug data
try:
    with DatabaseConnection() as db:
        ops = DrugDatabaseOperations(db)
        drug = ops.get_drug_with_details(selected_drug_id)

        if not drug:
            st.error("Drug not found")
            st.stop()

        # Get clinical trials (industry-sponsored only)
        with db.cursor() as cur:
            cur.execute("""
                SELECT nct_id, trial_title, trial_phase, trial_status, conditions, sponsors
                FROM drug_clinical_trials
                WHERE drug_id = %s
                ORDER BY trial_phase DESC
                LIMIT 100
            """, (selected_drug_id,))
            all_trials = [dict(row) for row in cur.fetchall()]

            # Don't filter - just pass all trials through for now
            # We'll filter in display if needed
            trials = all_trials
            excluded_trials = []

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
with st.expander("Debug: Raw Data", expanded=False):
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
    st.markdown("### Core Information")

    # Get black box warning from drug_metadata
    black_box_warning = "N/A"
    try:
        with DatabaseConnection() as db_check:
            with db_check.cursor() as cur:
                cur.execute("""
                    SELECT has_black_box_warning
                    FROM drug_metadata
                    WHERE drug_id = %s
                """, (selected_drug_id,))
                result = cur.fetchone()
                if result:
                    black_box_warning = "Yes" if result['has_black_box_warning'] else "No"
    except Exception as e:
        pass  # If table doesn't exist or query fails, show N/A

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
        ("Black Box Warning", black_box_warning),
    ]

    for label, value in info_items:
        st.markdown(f"**{label}:** {value}")

with col2:
    st.markdown("### Mechanism of Action")
    moa = drug.get('mechanism_of_action', 'Not available')
    if moa and len(moa) > 500:
        with st.expander("View full mechanism", expanded=False):
            st.write(moa)
        st.write(moa[:500] + "...")
    else:
        st.write(moa or "Not available")

# Indications section
st.markdown("---")
st.markdown("### Indications")

indications = drug.get('indications', [])
if indications:
    # Limit columns to 4 max
    num_cols = min(len(indications), 4)
    ind_cols = st.columns(num_cols)
    for i, ind in enumerate(indications):
        with ind_cols[i % num_cols]:
            disease = ind.get('disease_name') or 'Unknown Indication'
            ind_status = ind.get('approval_status', 'unknown')
            population = ind.get('population', '')
            severity = ind.get('severity', '')
            line_therapy = ind.get('line_of_therapy', '')
            confidence = ind.get('confidence_score', 0) or 0
            approval_date = ind.get('approval_date')

            # Build subtitle from details
            subtitle_parts = []
            if population:
                subtitle_parts.append(population)
            if severity:
                subtitle_parts.append(severity)
            if line_therapy:
                subtitle_parts.append(line_therapy)
            subtitle = " | ".join(subtitle_parts) if subtitle_parts else ""

            # Format approval date
            approval_text = ""
            if approval_date:
                # Format date nicely
                if isinstance(approval_date, str):
                    approval_text = f'<div style="color: #64748b; font-size: 11px; margin-top: 4px;">Approved: {approval_date}</div>'
                else:
                    approval_text = f'<div style="color: #64748b; font-size: 11px; margin-top: 4px;">Approved: {approval_date.strftime("%Y-%m-%d")}</div>'

            # Determine status color
            if ind_status == 'approved':
                status_style = "background-color: #d1fae5; color: #065f46;"
            elif ind_status == 'investigational':
                status_style = "background-color: #fef3c7; color: #92400e;"
            else:
                status_style = "background-color: #e5e7eb; color: #374151;"

            st.markdown(f"""
            <div style="background-color: #f8fafc; border-radius: 8px; padding: 12px; margin-bottom: 10px; border: 1px solid #e2e8f0;">
                <div style="font-weight: 600; font-size: 14px; color: #1e293b; margin-bottom: 4px;">{disease}</div>
                <div style="{status_style} display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-bottom: 4px;">{ind_status.title()}</div>
                {f'<div style="color: #64748b; font-size: 12px;">{subtitle}</div>' if subtitle else ''}
                {approval_text}
            </div>
            """, unsafe_allow_html=True)
else:
    st.info("No indications extracted")

# Dosing section
st.markdown("---")
st.markdown("### Dosing Regimens")

dosing = drug.get('dosing_regimens', [])

# Debug dosing data
with st.expander("Debug: Dosing Data", expanded=False):
    st.write(f"**Total dosing records from database:** {len(dosing)}")

    # Get indication names for dosing regimens - map by indication_id
    indication_map_debug = {ind.get('indication_id'): ind.get('disease_name', 'General')
                     for ind in drug.get('indications', [])}
    st.write(f"**Indication map:** {indication_map_debug}")

    # Count how many dosing records map to each indication
    for d in dosing[:20]:  # Show first 20
        ind_id = d.get('indication_id')
        ind_name = indication_map_debug.get(ind_id, f"ORPHANED (ID={ind_id})")
        st.write(f"  Dosing ID {d.get('dosing_id')}: ind_id={ind_id} -> {ind_name}")

if dosing:
    import pandas as pd

    # Get indication names for dosing regimens - map by indication_id
    indication_map = {ind.get('indication_id'): ind.get('disease_name', 'General')
                     for ind in drug.get('indications', [])}
    all_indications = list(indication_map.values())

    is_approved = drug.get('approval_status') == 'approved'

    # Create one row per dosing regimen (no deduplication)
    dosing_data = []
    for d in dosing:
        indication_id = d.get('indication_id')

        # Get indication name - use map if available, otherwise use General
        if indication_id and indication_id in indication_map:
            indication_name = indication_map[indication_id]
        elif indication_id:
            # Indication ID exists but not in current indications - skip orphaned records
            continue
        else:
            indication_name = 'General'

        # Determine phase/status column value
        if is_approved:
            phase_value = "Approved"
        else:
            phase_value = d.get('regimen_phase', 'N/A').title()

        # Get population/age group
        population = d.get('population') or 'Adults'

        row = {
            "Indication": indication_name,
            "Population": population,
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

# Efficacy Results section
st.markdown("---")
st.markdown("### Efficacy Results")

efficacy_data = drug.get('efficacy_data', [])

with st.expander("Debug: Efficacy Data", expanded=False):
    st.write(f"**Total efficacy records:** {len(efficacy_data)}")
    if efficacy_data:
        st.write(f"**Sample:** {efficacy_data[0]}")

if efficacy_data:
    from collections import defaultdict

    # Group by indication
    by_indication = defaultdict(list)
    for e in efficacy_data:
        ind_name = e.get('indication_name') or 'General'
        by_indication[ind_name].append(e)

    for indication, results in by_indication.items():
        with st.expander(f"{indication} ({len(results)} endpoints)", expanded=True):
            eff_table_data = []
            sources_list = []  # Collect unique sources

            for r in results:
                drug_result = r.get('drug_arm_result')
                comp_result = r.get('comparator_arm_result')
                unit = r.get('drug_arm_result_unit', '%')

                # Format results
                drug_str = f"{drug_result}{unit}" if drug_result is not None else "N/A"
                comp_str = f"{comp_result}{unit}" if comp_result is not None else "N/A"

                # Handle source - for approved drugs show "Label", for web_search show numbered ref
                data_source = r.get('data_source', 'openfda')
                source_url = r.get('source_url')

                if data_source == 'web_search' and source_url:
                    # Add to sources list if not already there
                    if source_url not in sources_list:
                        sources_list.append(source_url)
                    source_num = sources_list.index(source_url) + 1
                    source_display = str(source_num)
                else:
                    source_display = "Label"

                eff_table_data.append({
                    "Trial": r.get('trial_name') or 'N/A',
                    "Endpoint": r.get('endpoint_name') or 'N/A',
                    "Drug": drug_str,
                    "Comparator": comp_str,
                    "vs": r.get('comparator_arm_name') or 'Placebo',
                    "Timepoint": r.get('timepoint') or 'N/A',
                    "Phase": r.get('trial_phase') or 'N/A',
                    "Source": source_display
                })

            st.dataframe(pd.DataFrame(eff_table_data), use_container_width=True, hide_index=True)

            # Show sources if any web search sources
            if sources_list:
                st.markdown("**Sources:**")
                for i, url in enumerate(sources_list, 1):
                    # Truncate URL for display
                    display_url = url[:60] + "..." if len(url) > 60 else url
                    st.markdown(f"{i}. [{display_url}]({url})")
else:
    st.info("No efficacy data extracted. Run: python extract_efficacy_safety.py --drug \"drug_name\"")

# Safety Profile section
st.markdown("---")
st.markdown("### Safety Profile")

safety_data = drug.get('safety_data', [])

with st.expander("Debug: Safety Data", expanded=False):
    st.write(f"**Total safety records:** {len(safety_data)}")
    if safety_data:
        st.write(f"**Sample:** {safety_data[0]}")

if safety_data:
    from collections import defaultdict

    # Check for boxed warnings
    boxed_warnings = [s for s in safety_data if s.get('is_boxed_warning')]
    if boxed_warnings:
        warning_cats = list(set(w.get('warning_category') or w.get('adverse_event') for w in boxed_warnings))
        st.warning(f"**Boxed Warnings:** {', '.join(warning_cats)}")

    # Check if we have multiple indications
    unique_indications = list(set(s.get('indication_name') or 'General' for s in safety_data))
    has_multiple_indications = len(unique_indications) > 1

    # Group by indication first, then by SOC
    by_indication = defaultdict(list)
    for s in safety_data:
        ind_name = s.get('indication_name') or 'General'
        by_indication[ind_name].append(s)

    for indication, ind_events in sorted(by_indication.items()):
        with st.expander(f"{indication} ({len(ind_events)} adverse events)", expanded=len(by_indication) == 1):
            safety_table_data = []
            safety_sources_list = []  # Collect unique sources

            # Group by SOC within indication
            by_soc = defaultdict(list)
            for s in ind_events:
                soc = s.get('system_organ_class') or 'Other'
                by_soc[soc].append(s)

            # Sort events by rate descending
            sorted_events = sorted(ind_events, key=lambda x: x.get('drug_arm_rate') or 0, reverse=True)

            for e in sorted_events:
                drug_rate = e.get('drug_arm_rate')
                comp_rate = e.get('comparator_arm_rate')
                unit = e.get('drug_arm_rate_unit', '%')

                drug_str = f"{drug_rate}{unit}" if drug_rate is not None else "N/A"
                comp_str = f"{comp_rate}{unit}" if comp_rate is not None else "N/A"

                # Handle source
                data_source = e.get('data_source', 'openfda')
                source_url = e.get('source_url')

                if data_source == 'web_search' and source_url:
                    if source_url not in safety_sources_list:
                        safety_sources_list.append(source_url)
                    source_num = safety_sources_list.index(source_url) + 1
                    source_display = str(source_num)
                else:
                    source_display = "Label"

                safety_table_data.append({
                    "Adverse Event": e.get('adverse_event') or 'N/A',
                    "SOC": e.get('system_organ_class') or 'Other',
                    "Drug": drug_str,
                    "Comparator": comp_str,
                    "vs": e.get('comparator_arm_name') or 'Placebo',
                    "Timepoint": e.get('timepoint') or 'N/A',
                    "Serious": "Yes" if e.get('is_serious') else "No",
                    "Source": source_display
                })

            st.dataframe(pd.DataFrame(safety_table_data), use_container_width=True, hide_index=True)

            # Show sources if any web search sources
            if safety_sources_list:
                st.markdown("**Sources:**")
                for i, url in enumerate(safety_sources_list, 1):
                    display_url = url[:60] + "..." if len(url) > 60 else url
                    st.markdown(f"{i}. [{display_url}]({url})")
else:
    st.info("No safety data extracted. Run: python extract_efficacy_safety.py --drug \"drug_name\"")

# Clinical Trials section
st.markdown("---")
st.markdown("### Clinical Trials")

# Filter to only show industry-sponsored trials
industry_trials = []
for t in trials:
    sponsors = t.get('sponsors', {})
    sponsor_class = sponsors.get('class', '') if isinstance(sponsors, dict) else ''
    if sponsor_class == 'INDUSTRY':
        industry_trials.append(t)

# Get standardized conditions for trials
trials_with_std_conditions = {}
std_conditions_error = None
try:
    with DatabaseConnection() as db:
        with db.cursor() as cur:
            cur.execute("""
                SELECT dct.trial_id, dct.nct_id,
                       sc.standard_name, sc.therapeutic_area
                FROM drug_clinical_trials dct
                JOIN trial_conditions tc ON dct.trial_id = tc.trial_id
                JOIN standardized_conditions sc ON tc.condition_id = sc.condition_id
                WHERE dct.drug_id = %s
            """, (selected_drug_id,))
            for row in cur.fetchall():
                trial_id = row['trial_id']
                if trial_id not in trials_with_std_conditions:
                    trials_with_std_conditions[trial_id] = []
                trials_with_std_conditions[trial_id].append({
                    'standard_name': row['standard_name'],
                    'therapeutic_area': row['therapeutic_area']
                })
except Exception as e:
    std_conditions_error = str(e)

# Debug trials data
with st.expander("Debug: Clinical Trials Data", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total trials in DB", len(trials))
        st.metric("Industry-sponsored", len(industry_trials))
    with col2:
        st.metric("With standardized conditions", len(trials_with_std_conditions))
        st.metric("Drug ID", selected_drug_id)

    if std_conditions_error:
        st.error(f"Standardized conditions error: {std_conditions_error}")

    if trials_with_std_conditions:
        st.success(f"✓ {len(trials_with_std_conditions)} trials have standardized conditions")
    else:
        st.warning("⚠ No standardized conditions found - using raw condition names")

if industry_trials:
    import re
    from collections import defaultdict

    # Helper function to extract trial acronym
    def extract_trial_acronym(title: str) -> str:
        """Extract trial acronym from title using regex patterns."""
        if not title:
            return None

        # Pattern 1: Acronym at start with colon - "ERASURE: A Phase 3 Study..."
        start_match = re.match(r'^([A-Z][A-Za-z0-9\-]{2,}):\s', title)
        if start_match:
            acronym = start_match.group(1)
            if acronym not in ['LTE', 'IMID', 'RCT', 'OLE', 'PHASE', 'STUDY']:
                return acronym

        # Pattern 2: Acronym in parentheses - "A Study (ERASURE) of..."
        paren_match = re.search(r'[\(\[]([A-Z][A-Za-z0-9\-]{2,})[\)\]]', title)
        if paren_match:
            acronym = paren_match.group(1)
            if acronym not in ['LTE', 'IMID', 'RCT', 'OLE'] and not re.match(r'^[A-Z]{2,5}-?\d{2,4}$', acronym):
                return acronym

        return None

    # Build trial_id -> trial mapping for quick lookup (nct_id to trial_id)
    trial_id_map = {}
    try:
        with DatabaseConnection() as db:
            with db.cursor() as cur:
                cur.execute("SELECT trial_id, nct_id FROM drug_clinical_trials WHERE drug_id = %s", (selected_drug_id,))
                for row in cur.fetchall():
                    trial_id_map[row['nct_id']] = row['trial_id']
    except:
        pass

    # Group trials by STANDARDIZED conditions (with therapeutic area)
    trials_by_condition = defaultdict(lambda: {'trials': [], 'therapeutic_area': None})

    for trial in industry_trials:
        nct_id = trial.get('nct_id')
        trial_id = trial_id_map.get(nct_id)

        # Check if we have standardized conditions for this trial
        if trial_id and trial_id in trials_with_std_conditions:
            std_conditions = trials_with_std_conditions[trial_id]
            # Use the first standardized condition as the primary grouping
            primary = std_conditions[0]
            condition_name = primary['standard_name']
            therapeutic_area = primary['therapeutic_area']

            trials_by_condition[condition_name]['trials'].append(trial)
            if not trials_by_condition[condition_name]['therapeutic_area']:
                trials_by_condition[condition_name]['therapeutic_area'] = therapeutic_area
        else:
            # Fallback to raw conditions if no standardized mapping
            raw_conditions = trial.get('conditions', [])
            if isinstance(raw_conditions, str):
                import json
                try:
                    raw_conditions = json.loads(raw_conditions)
                except:
                    raw_conditions = [raw_conditions] if raw_conditions else []

            if raw_conditions:
                trials_by_condition[raw_conditions[0]]['trials'].append(trial)
            else:
                trials_by_condition['Other/Unknown']['trials'].append(trial)

    # Get approved indications for highlighting
    approved_conditions = {ind.get('disease_name', '').lower()
                          for ind in drug.get('indications', [])
                          if ind.get('approval_status') == 'approved'}

    # Helper to check if condition is approved
    def is_approved_condition(condition_name):
        condition_lower = condition_name.lower()
        for approved in approved_conditions:
            if approved in condition_lower or condition_lower in approved:
                return True
        return False

    # Sort conditions: approved first, then by number of trials (descending), then alphabetically
    def sort_key(item):
        condition_name, condition_data = item
        is_approved = is_approved_condition(condition_name)
        trial_count = len(condition_data['trials'])
        return (not is_approved, -trial_count, condition_name.lower())

    sorted_conditions = sorted(trials_by_condition.items(), key=sort_key)

    # Group by therapeutic area
    therapeutic_areas = defaultdict(list)
    for condition_name, condition_data in sorted_conditions:
        area = condition_data.get('therapeutic_area') or 'Other'
        therapeutic_areas[area].append((condition_name, condition_data))

    # Display trials grouped by therapeutic area, then by condition
    for area, conditions_in_area in therapeutic_areas.items():
        # Count total trials in this therapeutic area
        total_trials_in_area = sum(len(cd['trials']) for _, cd in conditions_in_area)

        with st.expander(f"🏥 **{area}** ({len(conditions_in_area)} conditions, {total_trials_in_area} trials)", expanded=False):
            for condition_name, condition_data in conditions_in_area:
                condition_trials = condition_data['trials']

                # Group trials by phase within each condition
                trials_by_phase = defaultdict(list)
                for trial in condition_trials:
                    phase = trial.get('trial_phase', 'Unknown')
                    trials_by_phase[phase].append(trial)

                # Add approval badge if this is an approved indication
                is_approved = is_approved_condition(condition_name)
                approval_badge = " ✓ Approved" if is_approved else ""

                # Show condition header
                st.markdown(f"**{condition_name}**{approval_badge} ({len(condition_trials)} trials)")

                # Display trials grouped by phase
                phase_order = ['PHASE3', 'PHASE2', 'PHASE1', 'PHASE4', 'Unknown']

                for phase_key in phase_order:
                    if phase_key not in trials_by_phase:
                        continue

                    phase_trials = trials_by_phase[phase_key]
                    phase_display = phase_key.replace('PHASE', 'Phase ') if phase_key != 'Unknown' else 'Unknown Phase'

                    # Display phase header
                    st.markdown(f"*{phase_display}* ({len(phase_trials)} trials)")

                    for trial in phase_trials:
                        nct_id = trial.get('nct_id', 'Unknown')
                        title = trial.get('trial_title') or 'No title available'
                        trial_status = trial.get('trial_status') or 'Unknown'

                        # Extract acronym
                        acronym = extract_trial_acronym(title)

                        # Create display name - show full title
                        if acronym:
                            display_name = f"**{acronym}** - {title}"
                        else:
                            display_name = title

                        st.markdown(f"""
                        - [{nct_id}](https://clinicaltrials.gov/study/{nct_id}) - {display_name}
                          *Status: {trial_status}*
                        """)

                st.markdown("---")
else:
    st.info("No industry-sponsored clinical trials found")

# Data Sources section
st.markdown("---")
st.markdown("### Data Sources")

# Debug sources data
with st.expander("Debug: Data Sources", expanded=False):
    st.write(f"**Total sources found:** {len(sources)}")
    if sources:
        st.json(sources)

if sources:
    for s in sources:
        source_name = s.get('source_name', 'Unknown')
        # Use simple bullet point
        st.markdown(f"- **{source_name}**")
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
with st.expander("View Raw Data (JSON)"):
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

