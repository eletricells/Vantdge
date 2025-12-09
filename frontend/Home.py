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

    This AI-powered system helps BigPharma BD teams evaluate drug development opportunities by:

    - 🔬 **Clinical Analysis**: Evaluates trial data, probability of success, and clinical risks
    - 💼 **Investment Synthesis**: Generates actionable ACQUIRE/MONITOR/PASS recommendations
    - 📊 **Executive Summaries**: Creates board-ready investment theses
    - 🎯 **Custom Prompts**: Fine-tune agent behavior for your specific needs

    ### Getting Started

    Navigate using the sidebar:
    - **Analysis** → Run investment analyses
    - **Agent Prompts** → Customize AI agent behavior
    """)

with col2:
    st.markdown("""
    ### 📊 System Status

    **Active Agents:**
    - ✅ Clinical Agent
    - ✅ Manager Agent
    - 🔨 Commercial Agent (Coming)
    - 🔨 Preclinical Agent (Coming)

    **Features:**
    - ✅ ClinicalTrials.gov API
    - ✅ Web Search (Tavily)
    - ✅ PubMed Integration
    - ✅ Custom Prompts
    - ✅ Multi-iteration Refinement
    """)

st.markdown("---")

# Feature cards
st.markdown("## 🎯 Key Features")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    <div class="feature-card">
        <h3>🔬 Clinical Analysis</h3>
        <ul>
            <li>Trial design assessment</li>
            <li>Probability of success</li>
            <li>Risk/opportunity identification</li>
            <li>Competitive benchmarking</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="feature-card">
        <h3>💼 Investment Thesis</h3>
        <ul>
            <li>ACQUIRE/MONITOR/PASS recommendations</li>
            <li>Deal structure suggestions</li>
            <li>Peak sales forecasts</li>
            <li>Executive summaries</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="feature-card">
        <h3>⚙️ Customizable</h3>
        <ul>
            <li>Edit agent prompts</li>
            <li>Adjust confidence thresholds</li>
            <li>Control iteration depth</li>
            <li>Fine-tune analysis rigor</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# Quick examples
st.markdown("## 📚 Example Analyses")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    ### KRAS Inhibitor
    **Target:** Amgen - Sotorasib
    **Indication:** KRAS G12C-mutated NSCLC
    **Phase:** Phase 2

    *Example of successful precision oncology program*
    """)

    st.markdown("""
    ### RET Inhibitor
    **Target:** Blueprint Medicines - Pralsetinib
    **Indication:** RET-altered cancer
    **Phase:** Phase 2

    *Example of targeted therapy in rare mutations*
    """)

with col2:
    st.markdown("""
    ### Cancer Immunotherapy
    **Target:** BioNTech - BNT111
    **Indication:** Melanoma
    **Phase:** Phase 2

    *Example of novel immunotherapy approach*
    """)

    st.markdown("""
    ### Custom Analysis
    Use the Analysis page to evaluate any drug program with:
    - Custom target and indication
    - Adjustable parameters
    - Iterative refinement
    """)

st.markdown("---")

# Footer
st.markdown("""
### 🚀 Ready to Start?

1. **Go to the Analysis page** (sidebar) to run your first analysis
2. **Customize prompts** (Agent Prompts page) to fine-tune behavior
3. **Iterate and refine** to get the best insights

---

*Phase 2 MVP - Clinical Agent + Manager Agent + Custom Prompts*
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
