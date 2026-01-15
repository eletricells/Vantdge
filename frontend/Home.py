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

from auth import check_password, render_sidebar_nav, get_user_role

st.set_page_config(
    page_title="Vantdge",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Hide sidebar before login
if not st.session_state.get("password_correct"):
    st.markdown("""<style>[data-testid="stSidebar"]{display:none}</style>""", unsafe_allow_html=True)

# Password protection
if not check_password():
    st.stop()

# Render custom sidebar navigation for restricted users
render_sidebar_nav()

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

# Get user role for conditional content
user_role = get_user_role()

# Header
st.markdown('<p class="main-header">🧬 Vantdge</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">AI-Powered Biopharma Intelligence Platform</p>', unsafe_allow_html=True)

st.markdown("---")

# Different content based on user role
if user_role == "case_series":
    # RH_TEST1 - Case Series focused view
    st.markdown("## Welcome!")
    st.markdown("""
    Explore drug repurposing opportunities through AI-powered case series analysis.
    """)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div class="feature-card">
        <h3>🧬 Case Study Analysis</h3>
        <p>Run new drug repurposing analyses:</p>
        <ul>
            <li>Search PubMed & preprints</li>
            <li>Extract clinical evidence</li>
            <li>Score disease opportunities</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="feature-card">
        <h3>📚 Case Series Browser</h3>
        <p>Browse existing analyses:</p>
        <ul>
            <li>View extracted papers by drug</li>
            <li>Filter by disease & evidence</li>
            <li>Export to Excel</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Getting Started")
    st.markdown("Use the sidebar to navigate to Case Study Analysis or Case Series Browser.")

else:
    # JCL_TEST - Full access view
    st.markdown("## Welcome!")
    st.markdown("""
    Vantdge is an AI-powered platform for biopharma competitive intelligence and drug repurposing analysis.
    """)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        <div class="feature-card">
        <h3>🧬 Case Study Analysis</h3>
        <p>Identify drug repurposing opportunities through AI-powered literature analysis.</p>
        <ul>
            <li>PubMed & preprint search</li>
            <li>Full-text extraction</li>
            <li>Clinical evidence scoring</li>
            <li>Disease opportunity ranking</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="feature-card">
        <h3>🏥 Disease Intelligence</h3>
        <p>Comprehensive disease landscape analysis for strategic planning.</p>
        <ul>
            <li>Prevalence & incidence data</li>
            <li>Current treatment options</li>
            <li>Clinical trial failure rates</li>
            <li>Unmet medical needs</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="feature-card">
        <h3>💊 Pipeline Intelligence</h3>
        <p>Track competitive drug development pipelines.</p>
        <ul>
            <li>Clinical trial monitoring</li>
            <li>Competitor drug tracking</li>
            <li>Development stage analysis</li>
            <li>Market opportunity assessment</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Getting Started")
    st.markdown("Use the sidebar to navigate to the available tools.")
