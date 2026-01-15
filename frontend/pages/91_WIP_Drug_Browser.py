"""
Drug Browser - View and explore extracted drug data
"""
import streamlit as st
import sys
from pathlib import Path
import pandas as pd

# Add paths
frontend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auth import check_password, check_page_access, show_access_denied
from src.utils.config import get_settings
from src.tools.drug_database import DrugDatabase
from src.utils.drug_version_manager import DrugVersionHistory, DrugVersionManager

st.set_page_config(
    page_title="Drug Browser",
    page_icon="🔍",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

# Page access check
if not check_page_access("WIP_Drug_Browser"):
    show_access_denied()


def smart_title_case(text: str) -> str:
    """
    Title case that handles apostrophes correctly.

    Python's .title() incorrectly capitalizes after apostrophes:
    "crohn's disease" -> "Crohn'S Disease" (wrong)

    This function preserves lowercase after apostrophes:
    "crohn's disease" -> "Crohn's Disease" (correct)
    """
    # First apply standard title case
    result = text.title()

    # Fix apostrophe capitalization issues
    # Pattern: apostrophe followed by uppercase letter
    import re
    result = re.sub(r"'([A-Z])", lambda m: f"'{m.group(1).lower()}", result)

    return result


st.set_page_config(
    page_title="Drug Browser",
    page_icon="🔬",
    layout="wide"
)

st.title("🔬 Drug Browser")
st.markdown("Browse and explore extracted drug data from the database")

st.markdown("---")

# Get database connection
try:
    settings = get_settings()
    if hasattr(settings, 'drug_database_url') and settings.drug_database_url:
        database_url = settings.drug_database_url
    else:
        database_url = settings.paper_catalog_url
except Exception as e:
    st.error(f"Configuration error: {e}")
    st.stop()

# Sidebar - Filters
with st.sidebar:
    st.markdown("## 🔍 Filters")

    # Search
    search_query = st.text_input("Search drug name", "")

    # Approval status filter
    approval_filter = st.selectbox(
        "Approval Status",
        ["All", "Approved", "Investigational", "Discontinued"]
    )

    # Drug type filter
    drug_type_filter = st.selectbox(
        "Drug Type",
        ["All", "mAb", "Small Molecule", "ADC", "Bispecific", "CAR-T", "Gene Therapy", "Other"]
    )

    st.markdown("---")
    st.markdown("## 📊 Database Stats")

    try:
        with DrugDatabase(database_url) as db:
            cursor = db.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM drugs")
            total_drugs = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM diseases")
            total_diseases = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM drug_indications")
            total_indications = cursor.fetchone()[0]
            cursor.close()

            st.metric("Total Drugs", total_drugs)
            st.metric("Total Diseases", total_diseases)
            st.metric("Total Indications", total_indications)
    except Exception as e:
        st.error(f"Database error: {e}")

# Main content
try:
    with DrugDatabase(database_url) as db:
        # Get all drugs
        cursor = db.connection.cursor()

        # Build query with filters
        where_clauses = []
        params = []

        if search_query:
            where_clauses.append("(brand_name ILIKE %s OR generic_name ILIKE %s)")
            params.extend([f"%{search_query}%", f"%{search_query}%"])

        if approval_filter != "All":
            where_clauses.append("approval_status = %s")
            params.append(approval_filter.lower())

        if drug_type_filter != "All":
            if drug_type_filter == "Other":
                where_clauses.append("(drug_type IS NULL OR drug_type NOT IN ('mAb', 'Small Molecule', 'ADC', 'Bispecific', 'CAR-T', 'Gene Therapy'))")
            else:
                where_clauses.append("drug_type = %s")
                params.append(drug_type_filter)

        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

        query = f"""
            SELECT
                drug_id,
                brand_name,
                generic_name,
                manufacturer,
                drug_type,
                mechanism_of_action,
                approval_status,
                highest_phase,
                first_approval_date,
                created_at
            FROM drugs
            WHERE {where_clause}
            ORDER BY created_at DESC
        """

        cursor.execute(query, params)
        drugs = cursor.fetchall()
        cursor.close()

        if not drugs:
            st.info("No drugs found. Try adjusting filters or extract some drugs first!")
        else:
            st.markdown(f"### Found {len(drugs)} drugs")

            # Display as cards
            for drug in drugs:
                drug_id, brand_name, generic_name, manufacturer, drug_type, mechanism, approval_status, highest_phase, first_approval_date, created_at = drug

                with st.expander(f"**{brand_name or generic_name}** ({approval_status})", expanded=False):
                    # Get metadata first to check black box warning
                    cursor_meta = db.connection.cursor()
                    cursor_meta.execute("SELECT * FROM drug_metadata WHERE drug_id = %s", (drug_id,))
                    metadata = cursor_meta.fetchone()
                    cursor_meta.close()

                    # Column 10 in table = index 9 (0-based)
                    # See check_humira_blackbox.py for column positions
                    has_black_box = metadata[9] if metadata and len(metadata) > 9 else False

                    # Basic Information - split into 2 columns
                    st.markdown("### Basic Information")
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Brand Name:** {brand_name or 'N/A'}")
                        st.markdown(f"**Generic Name:** {generic_name}")
                        st.markdown(f"**Manufacturer:** {manufacturer or 'N/A'}")
                        st.markdown(f"**Drug Type:** {drug_type or 'Not specified'}")
                        st.markdown(f"**Mechanism:** {mechanism or 'Not specified'}")

                    with col2:
                        st.markdown(f"**Status:** {approval_status}")
                        st.markdown(f"**Highest Phase:** {highest_phase or 'N/A'}")
                        if first_approval_date:
                            st.markdown(f"**First Approved:** {first_approval_date}")
                        if has_black_box:
                            st.markdown("**Blackbox Warning:** :red[Yes]")
                        st.markdown(f"**Added:** {created_at.strftime('%Y-%m-%d %H:%M')}")

                    # Version Selector
                    st.markdown("---")
                    st.markdown("### Version History")

                    # Get versions for this drug
                    version_manager = DrugVersionHistory(db)
                    versions = version_manager.get_versions(drug_id)

                    if versions:
                        # Version selector
                        col_version, col_compare = st.columns([1, 2])

                        with col_version:
                            version_options = {
                                f"Version {v['version_number']}/3": v['version_number']
                                for v in versions
                            }
                            selected_version_label = st.selectbox(
                                "Select version to view",
                                list(version_options.keys()),
                                index=len(versions) - 1,  # Default to latest (highest number)
                                key=f"version_selector_{drug_id}"
                            )
                            selected_version_num = version_options[selected_version_label]

                        # Get the selected version with comparison
                        version_comparison = version_manager.get_version_comparison(drug_id, selected_version_num)

                        if version_comparison:
                            with col_compare:
                                # Version metadata
                                st.caption(
                                    f"**Created:** {version_comparison['created_at'].strftime('%Y-%m-%d %H:%M')}  "
                                    f"| **By:** {version_comparison['created_by']}"
                                )

                                # Show changes summary
                                if version_comparison.get('has_previous_version') and version_comparison['comparison']['has_changes']:
                                    changes = version_comparison['comparison']
                                    change_summary = []

                                    if changes['added_fields']:
                                        change_summary.append(f":green[+{len(changes['added_fields'])} added]")
                                    if changes['removed_fields']:
                                        change_summary.append(f":red[-{len(changes['removed_fields'])} removed]")
                                    if changes['modified_fields']:
                                        change_summary.append(f":orange[~{len(changes['modified_fields'])} modified]")

                                    st.caption(f"**Changes:** {' | '.join(change_summary)}")
                                elif version_comparison.get('has_previous_version'):
                                    st.caption("**No changes from previous version**")
                                else:
                                    st.caption("**Initial version** (no previous version to compare)")

                            # Show detailed changes in expandable section
                            if version_comparison.get('has_previous_version') and version_comparison['comparison']['has_changes']:
                                with st.expander("View detailed changes"):
                                    changes = version_comparison['comparison']

                                    if changes['added_fields']:
                                        st.markdown("**Added Fields:**")
                                        for field in changes['added_fields']:
                                            st.markdown(f"- :green[🆕 {field}]")

                                    if changes['removed_fields']:
                                        st.markdown("**Removed Fields:**")
                                        for field in changes['removed_fields']:
                                            st.markdown(f"- :red[❌ {field}]")

                                    if changes['modified_fields']:
                                        st.markdown("**Modified Fields:**")
                                        for field, vals in changes['modified_fields'].items():
                                            st.markdown(f"- :orange[✏️ {field}]")
                                            st.caption(f"  Old: {vals['old']}")
                                            st.caption(f"  New: {vals['new']}")
                    else:
                        st.info("No version history available for this drug")

                    st.markdown("---")

                    # Indications - full width table below basic info
                    st.markdown("### Indications")

                    # Get indications
                    indications = db.get_drug_indications(drug_id)

                    if indications:
                        # Build dataframe for table display
                        indication_data = []
                        for ind in indications:
                            # Properly capitalize disease name for display
                            disease_name = ind['disease_name_standard']
                            # Title case with special handling for apostrophes and common abbreviations
                            disease_display = smart_title_case(disease_name)

                            row = {
                                "Disease": disease_display,
                                "Approved": str(ind.get('approval_year')) if ind.get('approval_year') else 'N/A',
                                "Status": ind.get('approval_status', 'N/A'),
                                "Line": ind.get('line_of_therapy', 'any'),
                                "Mild": "✓" if ind.get('severity_mild') else "",
                                "Moderate": "✓" if ind.get('severity_moderate') else "",
                                "Severe": "✓" if ind.get('severity_severe') else "",
                            }
                            indication_data.append(row)

                        indications_df = pd.DataFrame(indication_data)
                        st.dataframe(indications_df, width='stretch', hide_index=True)

                        # Show approval sources as expandable section
                        with st.expander("View approval data sources"):
                            for ind in indications:
                                if ind.get('approval_source'):
                                    st.markdown(f"**{ind['disease_name_standard']}**")
                                    st.caption(f"Source: {ind['approval_source']}")
                                    if ind.get('approval_date'):
                                        st.caption(f"Full date: {ind['approval_date']}")
                    else:
                        st.info("No indications extracted")

                    # Dosing regimens
                    st.markdown("### Dosing Regimens")
                    dosing = db.get_dosing_regimens(drug_id)

                    if dosing:
                        # Group dosing regimens by (indication, dose, frequency, route)
                        # to consolidate loading and maintenance phases into single rows
                        grouped_dosing = {}

                        for d in dosing:
                            # Properly capitalize indication name for display
                            indication_name = d.get('disease_name_standard') or "General"
                            if indication_name != "General":
                                indication_name = smart_title_case(indication_name)

                            # Create grouping key
                            dose_str = f"{d.get('dose_amount', 'N/A')} {d.get('dose_unit', '')}"
                            freq_str = d.get('frequency_standard', d.get('frequency_raw', 'N/A'))
                            route_str = d.get('route_standard', d.get('route_raw', 'N/A'))

                            key = (indication_name, dose_str, freq_str, route_str)

                            # Track if this dose has a loading phase
                            if key not in grouped_dosing:
                                grouped_dosing[key] = {
                                    "indication": indication_name,
                                    "dose": dose_str,
                                    "frequency": freq_str,
                                    "route": route_str,
                                    "has_loading": False,
                                    "has_maintenance": False,
                                    "order": d.get('sequence_order', 0)
                                }

                            # Mark if this is loading or maintenance
                            phase = d.get('regimen_phase', 'maintenance').lower()
                            if phase == 'loading':
                                grouped_dosing[key]["has_loading"] = True
                            else:
                                grouped_dosing[key]["has_maintenance"] = True

                        # Build dataframe from grouped data
                        dosing_data = []
                        for key, data in grouped_dosing.items():
                            row = {
                                "Indication": data["indication"],
                                "Dose": data["dose"],
                                "Frequency": data["frequency"],
                                "Route": data["route"],
                                "Loading Dose?": "✓" if data["has_loading"] else "",
                                "Order": data["order"]
                            }
                            dosing_data.append(row)

                        dosing_df = pd.DataFrame(dosing_data)
                        # Sort by Order
                        dosing_df = dosing_df.sort_values('Order')
                        st.dataframe(dosing_df.drop(columns=['Order']), width='stretch', hide_index=True)
                    else:
                        st.info("No dosing regimens extracted")

                    # Additional Information (metadata already fetched above)
                    if metadata:
                        st.markdown("### Additional Information")
                        col1, col2 = st.columns(2)

                        with col1:
                            if metadata[1]:  # patent_expiry
                                st.markdown(f"**Patent Expiry:** {metadata[1]}")
                            if metadata[3]:  # orphan_designation
                                st.markdown("🏅 **Orphan Designation**")

                        with col2:
                            if metadata[4]:  # breakthrough_therapy
                                st.markdown("⚡ **Breakthrough Therapy**")
                            if metadata[5]:  # fast_track
                                st.markdown("🚀 **Fast Track**")

                    # Raw data view
                    with st.expander("View Raw Data (JSON)"):
                        drug_overview = db.get_drug_overview(drug_id)
                        st.json(drug_overview)

except Exception as e:
    st.error(f"Error loading drugs: {e}")
    st.exception(e)

# Footer
st.markdown("---")
st.markdown("""
**Tip:** Use the sidebar filters to narrow down your search. Click on a drug to see full details including indications, dosing, and metadata.
""")
