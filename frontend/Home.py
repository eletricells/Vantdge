"""
Vantdge - Biopharma Intelligence Platform - Main Entry Point
"""
import streamlit as st
import sys
from pathlib import Path

# Add frontend directory to path for imports
frontend_dir = Path(__file__).parent
if str(frontend_dir) not in sys.path:
    sys.path.insert(0, str(frontend_dir))

from auth import check_password

st.set_page_config(
    page_title="Vantdge",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Password protection
if not check_password():
    st.stop()  # Do not continue if check_password is not True

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
        text-align: center;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #555;
        margin-bottom: 2rem;
        text-align: center;
    }
    .feature-card {
        background-color: #f0f2f6;
        padding: 2rem;
        border-radius: 1rem;
        margin: 1rem 0;
        border-left: 4px solid #1f77b4;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<p class="main-header">🧬 Vantdge</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">AI-Powered Biopharma Intelligence Platform</p>', unsafe_allow_html=True)

st.markdown("---")

# Welcome message
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("""
    ## Welcome!

    **Case Study Analysis v2** identifies drug repurposing opportunities through:

    - 📋 **Approved Indication Discovery**: Extracts FDA-approved uses from DailyMed and Drugs.com
    - 🔍 **Case Series Search**: Finds off-label evidence via PubMed and web search
    - 🤖 **AI-Powered Extraction**: Structures clinical data with Claude
    - 📊 **Scoring & Prioritization**: Ranks opportunities by clinical strength (50%), evidence quality (25%), and market potential (25%)

    ### Getting Started

    Navigate to **Case Study Analysis v2** in the sidebar to discover repurposing opportunities.
    """)

with col2:
    st.markdown("""
    ### 📊 System Status

    **Active Agents:**
    - ✅ Case Study Analysis v2

    **WIP Agents:**
    - 🔨 Drug Extraction
    - 🔨 Drug Browser
    - 🔨 Clinical Data Extractor
    - 🔨 Literature Search
    - 🔨 Prompt Manager
    - 🔨 Case Study Analysis (v1)

    **Features:**
    - ✅ PubMed Integration
    - ✅ Web Search (Tavily)
    - ✅ DailyMed API
    - ✅ Drugs.com Scraping
    """)

# Sidebar navigation help
with st.sidebar:
    st.markdown("## 🧭 Navigation")
    st.markdown("""
    Use the pages above to navigate:

    **📄 Case Studies**
    - Case Study Analysis
    - Case Study Analysis v2

    **🔬 WIP (Work In Progress)**
    - Drug Extraction
    - Drug Browser
    - Clinical Data Extractor
    - Literature Search
    - Prompt Manager

    ---

    ### 💡 Note
    WIP pages are experimental features under development.
    """)
