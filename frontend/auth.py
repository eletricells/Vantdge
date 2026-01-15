"""
Authentication module for Vantdge platform with role-based access control
"""
import streamlit as st

# Define access levels and their allowed pages
ACCESS_LEVELS = {
    "RH_TEST1": {
        "role": "case_series",
        "allowed_pages": [
            "Case_Study_Analysis_v3",
            "Case_Series_Browser",
            "Home",
        ]
    },
    "JCL_TEST": {
        "role": "full_access",
        "allowed_pages": None  # None means all pages allowed
    }
}

# Map page filenames to display names for CSS hiding
PAGE_DISPLAY_NAMES = {
    "16_Case_Study_Analysis_v3": "Case Study Analysis v3",
    "17_Scoring_Analysis": "Scoring Analysis",
    "18_Case_Series_Browser": "Case Series Browser",
    "19_Efficacy_Metrics_Browser": "Efficacy Metrics Browser",
    "20_Disease_Analysis": "Disease Analysis",
    "90_WIP_Drug_Extraction": "WIP Drug Extraction",
    "91_WIP_Drug_Browser": "WIP Drug Browser",
    "92_WIP_Clinical_Data_Extractor": "WIP Clinical Data Extractor",
    "93_WIP_Literature_Search": "WIP Literature Search",
    "94_WIP_Prompt_Manager": "WIP Prompt Manager",
    "95_Drug_Database_Viewer": "Drug Database Viewer",
    "96_Batch_Drug_Extraction": "Batch Drug Extraction",
    "97_Efficacy_Benchmarking": "Efficacy Benchmarking",
    "98_Pipeline_Intelligence": "Pipeline Intelligence",
    "98_Efficacy_Comparison": "Efficacy Comparison",
    "99_Disease_Intelligence": "Disease Intelligence",
}


def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        entered_password = st.session_state.get("password", "")
        if entered_password in ACCESS_LEVELS:
            st.session_state["password_correct"] = True
            st.session_state["user_role"] = ACCESS_LEVELS[entered_password]["role"]
            st.session_state["allowed_pages"] = ACCESS_LEVELS[entered_password]["allowed_pages"]
            if "password" in st.session_state:
                del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    # First run, show input for password
    if "password_correct" not in st.session_state:
        st.markdown("## Authentication Required")
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.info("Please enter the password to access the platform.")
        return False
    # Password not correct, show input + error
    elif not st.session_state["password_correct"]:
        st.markdown("## Authentication Required")
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("Password incorrect")
        return False
    else:
        # Password correct - apply page hiding CSS
        _apply_page_visibility_css()
        return True


def check_page_access(page_name: str) -> bool:
    """
    Check if the current user has access to a specific page.

    Args:
        page_name: The name of the page (e.g., "Case_Study_Analysis_v3")

    Returns:
        True if user has access, False otherwise
    """
    if not st.session_state.get("password_correct", False):
        return False

    # Refresh allowed_pages from ACCESS_LEVELS based on role
    # This ensures config changes take effect without re-login
    user_role = st.session_state.get("user_role", "")
    for password, config in ACCESS_LEVELS.items():
        if config["role"] == user_role:
            st.session_state["allowed_pages"] = config["allowed_pages"]
            break

    allowed_pages = st.session_state.get("allowed_pages")

    # None means all pages allowed (full access)
    if allowed_pages is None:
        return True

    return page_name in allowed_pages


def get_user_role() -> str:
    """Get the current user's role."""
    return st.session_state.get("user_role", "")


def _apply_page_visibility_css():
    """Hide default navigation for restricted users."""
    allowed_pages = st.session_state.get("allowed_pages")
    if allowed_pages is None:
        return
    # Hide default nav for restricted users
    st.markdown("""<style>[data-testid="stSidebarNav"]{display:none}</style>""", unsafe_allow_html=True)


def render_sidebar_nav():
    """Render custom sidebar navigation based on user's allowed pages."""
    allowed_pages = st.session_state.get("allowed_pages")
    if allowed_pages is None:
        return

    # Simple page links for restricted users
    if "Home" in allowed_pages:
        st.sidebar.page_link("Home.py", label="🏠 Home")
    if "Case_Study_Analysis_v3" in allowed_pages:
        st.sidebar.page_link("pages/16_Case_Study_Analysis_v3.py", label="🧬 Case Study Analysis v3")
    if "Case_Series_Browser" in allowed_pages:
        st.sidebar.page_link("pages/18_Case_Series_Browser.py", label="📚 Case Series Browser")


def show_access_denied():
    """Silently redirect to home if user doesn't have access."""
    st.switch_page("Home.py")
    st.stop()  # Prevent further rendering while redirecting
