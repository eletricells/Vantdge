"""
Drug Extraction from DailyMed

Extract FDA-approved drug information from DailyMed and populate drug database.
Supports single or batch drug extraction with autocomplete suggestions.
"""
import streamlit as st
import sys
from pathlib import Path
import logging

# Add paths
frontend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_dir))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auth import check_password, check_page_access, show_access_denied
from src.utils.config import get_settings
from src.tools.drug_database import DrugDatabase
from src.tools.enhanced_dailymed_extractor import EnhancedDailyMedExtractor

st.set_page_config(
    page_title="Drug Extraction",
    page_icon="💊",
    layout="wide"
)

# Password protection
if not check_password():
    st.stop()

# Page access check
if not check_page_access("WIP_Drug_Extraction"):
    show_access_denied()

# Common FDA-approved drugs for autocomplete
# This list can be expanded or loaded from a file
COMMON_DRUGS = [
    # mAbs - Autoimmune
    "Humira", "Enbrel", "Remicade", "Stelara", "Cosentyx", "Taltz",
    "Simponi", "Cimzia", "Orencia", "Actemra", "Kevzara",

    # mAbs - Oncology
    "Keytruda", "Opdivo", "Tecentriq", "Imfinzi", "Bavencio",
    "Yervoy", "Herceptin", "Perjeta", "Kadcyla", "Avastin",
    "Rituxan", "Gazyva", "Darzalex", "Kyprolis",

    # mAbs - Other
    "Dupixent", "Fasenra", "Nucala", "Cinqair", "Xolair",
    "Prolia", "Evenity", "Repatha", "Praluent",

    # Small molecules - Oncology
    "Ibrance", "Kisqali", "Verzenio", "Tagrisso", "Alecensa",
    "Zykadia", "Lorbrena", "Vitrakvi", "Rozlytrek",
    "Venclexta", "Calquence", "Imbruvica", "Brukinsa",

    # Small molecules - Autoimmune
    "Xeljanz", "Rinvoq", "Olumiant", "Otezla",

    # Small molecules - Other
    "Eliquis", "Xarelto", "Jardiance", "Farxiga", "Invokana",
    "Ozempic", "Trulicity", "Victoza", "Mounjaro",

    # Gene therapies
    "Zolgensma", "Luxturna", "Kymriah", "Yescarta",

    # Vaccines
    "Prevnar", "Gardasil", "Shingrix", "Fluzone",
]

# Sort alphabetically
COMMON_DRUGS = sorted(set(COMMON_DRUGS))

st.title("💊 Drug Extraction from DailyMed")
st.markdown("""
Extract FDA-approved drug information from DailyMed and populate the drug database.
Supports single or batch extraction with progress tracking.
""")

st.markdown("---")

# Sidebar - Configuration
with st.sidebar:
    st.markdown("## ⚙️ Configuration")

    # Check database configuration
    try:
        settings = get_settings()

        # Check if drug database URL is configured
        if hasattr(settings, 'drug_database_url') and settings.drug_database_url:
            st.success("✅ Drug database configured")
            database_url = settings.drug_database_url
        else:
            # Fall back to paper catalog URL
            database_url = settings.paper_catalog_url
            if not database_url:
                st.error("❌ No database URL configured. Please set DRUG_DATABASE_URL in your .env file.")
                st.stop()

    except Exception as e:
        st.error(f"❌ Configuration error: {e}")
        st.stop()

    st.markdown("---")
    st.markdown("## 📊 Database Stats")

    try:
        with DrugDatabase(database_url) as db:
            # Get table counts
            cursor = db.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM drugs")
            drug_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM diseases")
            disease_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM drug_indications")
            indication_count = cursor.fetchone()[0]
            cursor.close()

            st.metric("Total Drugs", drug_count)
            st.metric("Total Diseases", disease_count)
            st.metric("Total Indications", indication_count)
    except Exception as e:
        st.warning(f"Could not load stats: {e}")

# Main content
st.markdown("## 🔍 Select Drugs to Extract")

# Initialize session state for manual drugs
if 'manual_drugs' not in st.session_state:
    st.session_state.manual_drugs = []

# Drug selection
col1, col2 = st.columns([3, 1])

with col1:
    # Multi-select with search
    selected_drugs_from_list = st.multiselect(
        "Select drugs (start typing to search)",
        options=COMMON_DRUGS,
        help="Select one or more drugs to extract from DailyMed"
    )

with col2:
    # Manual entry option
    manual_drug = st.text_input(
        "Or enter drug name manually",
        help="For drugs not in the list"
    )

    if manual_drug and st.button("Add Manual Entry"):
        # Add to session state (persists across reruns)
        if manual_drug not in st.session_state.manual_drugs and manual_drug not in selected_drugs_from_list:
            st.session_state.manual_drugs.append(manual_drug)
            st.success(f"Added '{manual_drug}'")
            st.rerun()  # Rerun to show the added drug
        elif manual_drug in st.session_state.manual_drugs or manual_drug in selected_drugs_from_list:
            st.info(f"'{manual_drug}' already selected")

# Combine selected drugs from multiselect and manual entries
selected_drugs = list(selected_drugs_from_list) + st.session_state.manual_drugs

# Add button to clear manual entries
if st.session_state.manual_drugs:
    if st.button("Clear Manual Entries"):
        st.session_state.manual_drugs = []
        st.rerun()

# Show selected drugs
if selected_drugs:
    st.markdown(f"### Selected Drugs ({len(selected_drugs)})")

    # Display as pills
    pills_html = " ".join([
        f'<span style="background-color: #e3f2fd; color: #1976d2; padding: 5px 10px; margin: 2px; border-radius: 15px; display: inline-block;">{drug}</span>'
        for drug in selected_drugs
    ])
    st.markdown(pills_html, unsafe_allow_html=True)

    st.markdown("---")

    # Extraction options
    st.markdown("## ⚙️ Extraction Options")

    col1, col2 = st.columns(2)

    with col1:
        overwrite_existing = st.checkbox(
            "Overwrite existing drugs",
            value=False,
            help="If checked, will update existing drugs in database"
        )

    with col2:
        show_debug = st.checkbox(
            "Show debug information",
            value=False,
            help="Show detailed extraction logs"
        )

    # Extract button
    st.markdown("---")

    if st.button("🚀 Extract Drug Data", type="primary", use_container_width=True):
        # Initialize extractor
        try:
            with DrugDatabase(database_url) as db:
                extractor = EnhancedDailyMedExtractor(db)

                # Create progress containers
                progress_bar = st.progress(0)
                status_text = st.empty()

                # Results tracking
                successful = []
                failed = []
                skipped = []

                # Extract each drug
                for i, drug_name in enumerate(selected_drugs):
                    # Update progress
                    progress = (i + 1) / len(selected_drugs)
                    progress_bar.progress(progress)
                    status_text.markdown(f"**Processing {i+1}/{len(selected_drugs)}:** {drug_name}")

                    # Check if drug already exists (if not overwriting)
                    if not overwrite_existing:
                        results = db.search_drugs(drug_name, limit=1)
                        if results and results[0]['brand_name'].lower() == drug_name.lower():
                            skipped.append(drug_name)
                            st.info(f"⏭️ Skipped '{drug_name}' (already exists)")
                            continue

                    # Extract drug
                    with st.spinner(f"Extracting {drug_name}..."):
                        try:
                            # Configure logging for debug mode
                            if show_debug:
                                logging.basicConfig(level=logging.DEBUG)

                            data = extractor.extract_and_store_drug(
                                drug_name=drug_name,
                                save_to_database=True,
                                overwrite=overwrite_existing  # Pass overwrite flag
                            )

                            if data:
                                successful.append(drug_name)
                                st.success(f"✅ Extracted '{drug_name}' (ID: {data.get('drug_id')})")
                            else:
                                failed.append(drug_name)
                                st.error(f"❌ Failed to extract '{drug_name}' - Not found in DailyMed")

                        except Exception as e:
                            failed.append(drug_name)
                            st.error(f"❌ Error extracting '{drug_name}': {str(e)}")
                            if show_debug:
                                st.exception(e)

                # Clean up
                extractor.close()

                # Final summary
                progress_bar.progress(1.0)
                status_text.markdown("**✓ Extraction Complete**")

                st.markdown("---")
                st.markdown("## 📊 Extraction Summary")

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric(
                        "✅ Successful",
                        len(successful),
                        delta=f"{len(successful)}/{len(selected_drugs)}"
                    )

                with col2:
                    st.metric(
                        "❌ Failed",
                        len(failed),
                        delta=f"-{len(failed)}" if failed else None,
                        delta_color="inverse"
                    )

                with col3:
                    st.metric(
                        "⏭️ Skipped",
                        len(skipped),
                        delta=f"{len(skipped)} already exist" if skipped else None
                    )

                # Detailed results
                if successful:
                    with st.expander(f"✅ Successfully Extracted ({len(successful)})", expanded=True):
                        for drug in successful:
                            st.markdown(f"- **{drug}**")

                if failed:
                    with st.expander(f"❌ Failed Extractions ({len(failed)})", expanded=True):
                        st.warning("These drugs may not be in DailyMed or have different names.")
                        for drug in failed:
                            st.markdown(f"- **{drug}**")

                if skipped:
                    with st.expander(f"⏭️ Skipped ({len(skipped)})", expanded=False):
                        for drug in skipped:
                            st.markdown(f"- **{drug}** (already in database)")

        except Exception as e:
            st.error(f"❌ Extraction failed: {str(e)}")
            st.exception(e)

else:
    st.info("👆 Select one or more drugs to extract")

st.markdown("---")

# Recently extracted drugs section
st.markdown("## 📋 Recently Extracted Drugs")

try:
    with DrugDatabase(database_url) as db:
        # Get recent drugs
        cursor = db.connection.cursor()
        cursor.execute("""
            SELECT
                brand_name,
                generic_name,
                manufacturer,
                drug_type,
                mechanism_of_action,
                approval_status,
                created_at
            FROM drugs
            ORDER BY created_at DESC
            LIMIT 10
        """)

        recent_drugs = cursor.fetchall()
        cursor.close()

        if recent_drugs:
            for drug in recent_drugs:
                with st.expander(f"**{drug[0] or drug[1]}** ({drug[5]})"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Brand Name:** {drug[0] or 'N/A'}")
                        st.markdown(f"**Generic Name:** {drug[1]}")
                        st.markdown(f"**Manufacturer:** {drug[2] or 'N/A'}")

                    with col2:
                        st.markdown(f"**Drug Type:** {drug[3] or 'N/A'}")
                        st.markdown(f"**Mechanism:** {drug[4] or 'N/A'}")
                        st.markdown(f"**Added:** {drug[6].strftime('%Y-%m-%d %H:%M')}")
        else:
            st.info("No drugs extracted yet. Select drugs above to get started!")

except Exception as e:
    st.warning(f"Could not load recent drugs: {e}")

# Footer
st.markdown("---")

with st.expander("ℹ️ How This Works"):
    st.markdown("""
    ### DailyMed Extraction Process

    1. **Search DailyMed**: Searches for drug by name in DailyMed database
    2. **Retrieve Label**: Downloads FDA-approved drug label (SPL XML format)
    3. **Parse Data**: Extracts structured information:
       - Drug names (brand/generic)
       - Manufacturer
       - Routes of administration
       - Active ingredients
       - Indications
    4. **Standardize**: Converts to machine-readable formats:
       - Routes: "subcutaneous" → "SC", "intravenous" → "IV"
       - Frequencies: "once weekly" → "QW", "every 4 weeks" → "Q4W"
    5. **Save to Database**: Stores in normalized drug database schema

    ### What's Extracted

    ✅ **Currently Extracted:**
    - Drug names (brand and generic)
    - Manufacturer
    - Routes of administration
    - Active ingredients
    - Indications (FDA-approved uses)

    🔨 **Future Enhancements:**
    - Detailed dosing regimens (loading/maintenance)
    - Formulation details (strengths, packaging)
    - Safety information (black box warnings)
    - Label version history

    ### Troubleshooting

    **Drug Not Found:**
    - Drug may not be FDA-approved
    - Try alternative spelling or brand name
    - Check if using correct drug name

    **Extraction Failed:**
    - DailyMed API may be temporarily unavailable
    - Check database connection
    - Enable debug mode for detailed logs
    """)

with st.expander("🔧 Manual Database Management"):
    st.markdown("""
    ### Command-Line Tools

    ```bash
    # Setup drug database
    python scripts/setup_drug_database.py

    # Batch extract from Python
    from src.tools.dailymed_extractor import batch_extract_from_list

    drugs = ["Humira", "Enbrel", "Remicade"]
    results = batch_extract_from_list(drugs, "postgresql://...")

    # Search drugs in database
    from src.tools.drug_database import DrugDatabase

    with DrugDatabase("postgresql://...") as db:
        results = db.search_drugs("humira")
        drug = db.get_drug_overview(drug_id=1)
    ```

    See `DRUG_DATABASE_GUIDE.md` for complete documentation.
    """)
