"""
Streamlit visualization components for drug repurposing case series analysis.

Usage:
    import streamlit as st
    from visualizations import render_priority_matrix, render_market_opportunity
    
    # Assuming you have your analysis data in a DataFrame
    render_priority_matrix(analysis_df, drug_name="Iptacopan")
    render_market_opportunity(analysis_df, drug_name="Iptacopan")
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from typing import Optional


def shorten_disease(name: str, max_len: int = 30) -> str:
    """Shorten disease names for display."""
    if len(str(name)) <= max_len:
        return str(name)
    
    # Common abbreviations
    abbrevs = {
        'Transplantation-associated Thrombotic Microangiopathy': 'TA-TMA',
        'Membranoproliferative Glomerulonephritis': 'MPGN',
        'Autoimmune Hemolytic Anemia': 'AIHA',
        'C3 Glomerulopathy': 'C3G',
        'Cold Agglutinin Disease': 'CAD',
        'Atypical Hemolytic Uremic Syndrome': 'aHUS',
        'Paroxysmal Nocturnal Hemoglobinuria': 'PNH',
    }
    
    for full, short in abbrevs.items():
        if full.lower() in name.lower():
            return short
    
    return str(name)[:max_len-3] + '...'


def render_priority_matrix(
    df: pd.DataFrame,
    drug_name: str = "Drug",
    clinical_score_col: str = "Clinical Score (avg)",
    evidence_score_col: str = "Evidence Score (avg)",
    overall_score_col: str = "Overall Score (avg)",
    total_patients_col: str = "Total Patients",
    n_studies_col: str = "# Studies",
    disease_col: str = "Disease",
    height: int = 600,
    show_high_priority_zone: bool = True
) -> None:
    """
    Render an interactive priority matrix (Clinical vs Evidence score bubble chart).
    
    Parameters:
    -----------
    df : pd.DataFrame
        Analysis summary dataframe with one row per disease/indication
    drug_name : str
        Name of the drug being analyzed (for title)
    clinical_score_col : str
        Column name for clinical score
    evidence_score_col : str
        Column name for evidence score
    overall_score_col : str
        Column name for overall priority score (used for color)
    total_patients_col : str
        Column name for total patients (used for bubble size)
    n_studies_col : str
        Column name for number of studies
    disease_col : str
        Column name for disease/indication name
    height : int
        Chart height in pixels
    show_high_priority_zone : bool
        Whether to show the highlighted "high priority" zone
    """
    
    fig = go.Figure()
    
    # Add a trace for each disease
    for _, row in df.iterrows():
        disease_short = shorten_disease(row[disease_col])
        
        # Scale bubble size (min 15, max 60)
        n_patients = row.get(total_patients_col, 1) or 1
        bubble_size = max(15, min(60, n_patients * 5))
        
        fig.add_trace(go.Scatter(
            x=[row[clinical_score_col]],
            y=[row[evidence_score_col]],
            mode='markers+text',
            marker=dict(
                size=bubble_size,
                color=row[overall_score_col],
                colorscale='RdYlGn',
                cmin=5,
                cmax=9,
                line=dict(width=2, color='white'),
                opacity=0.8
            ),
            text=[disease_short],
            textposition='top center',
            textfont=dict(size=11, color='#333'),
            hovertemplate=(
                f"<b>{row[disease_col]}</b><br>"
                f"Clinical Score: {row[clinical_score_col]:.1f}<br>"
                f"Evidence Score: {row[evidence_score_col]:.1f}<br>"
                f"Overall Score: {row[overall_score_col]:.1f}<br>"
                f"Total Patients: {n_patients}<br>"
                f"# Studies: {row.get(n_studies_col, 'N/A')}<br>"
                "<extra></extra>"
            ),
            showlegend=False
        ))
    
    # Layout configuration
    layout_args = dict(
        title=dict(
            text=f'<b>{drug_name.upper()} Repurposing Opportunities</b><br>'
                 f'<sup>Priority Matrix: Clinical Signal vs Evidence Quality</sup>',
            x=0.5,
            font=dict(size=18)
        ),
        xaxis=dict(
            title='Clinical Score (Efficacy + Safety)',
            range=[4, 10],
            dtick=1,
            gridcolor='lightgray'
        ),
        yaxis=dict(
            title='Evidence Score (Sample Size + Quality)',
            range=[3, 8],
            dtick=1,
            gridcolor='lightgray'
        ),
        plot_bgcolor='white',
        height=height,
        annotations=[
            dict(
                text="Bubble size = Total patients<br>Color = Overall priority score",
                xref="paper", yref="paper",
                x=0.02, y=0.98,
                showarrow=False,
                font=dict(size=10, color='gray'),
                align='left'
            )
        ]
    )
    
    # Add high priority zone if requested
    if show_high_priority_zone:
        layout_args['annotations'].append(
            dict(
                text="HIGH PRIORITY<br>ZONE",
                x=8.5, y=6.5,
                showarrow=False,
                font=dict(size=12, color='green', family='Arial Black'),
                opacity=0.5
            )
        )
        layout_args['shapes'] = [
            dict(
                type='rect',
                x0=7, x1=10, y0=5, y1=8,
                fillcolor='rgba(0,255,0,0.05)',
                line=dict(color='green', width=1, dash='dash')
            )
        ]
    
    fig.update_layout(**layout_args)
    
    # Render in Streamlit
    st.plotly_chart(fig, use_container_width=True)


def render_market_opportunity(
    df: pd.DataFrame,
    drug_name: str = "Drug",
    competitors_col: str = "# Approved Competitors",
    overall_score_col: str = "Overall Score (avg)",
    tam_col: str = "TAM Estimate",
    unmet_need_col: str = "Unmet Need",
    disease_col: str = "Disease",
    height: int = 550,
    show_sweet_spot: bool = True
) -> None:
    """
    Render an interactive market opportunity bubble chart.
    
    Parameters:
    -----------
    df : pd.DataFrame
        Analysis summary dataframe with one row per disease/indication
    drug_name : str
        Name of the drug being analyzed (for title)
    competitors_col : str
        Column name for number of approved competitors
    overall_score_col : str
        Column name for overall priority score
    tam_col : str
        Column name for TAM (can be string like "$172.8M" or numeric)
    unmet_need_col : str
        Column name for unmet need (Yes/No)
    disease_col : str
        Column name for disease/indication name
    height : int
        Chart height in pixels
    show_sweet_spot : bool
        Whether to show the highlighted "sweet spot" zone
    """
    
    fig = go.Figure()
    
    for _, row in df.iterrows():
        disease_short = shorten_disease(row[disease_col])
        
        # Parse TAM - handle both string ("$172.8M") and numeric formats
        tam_value = row.get(tam_col, '$50M')
        if pd.isna(tam_value):
            tam_millions = 50
            tam_display = 'N/A'
        elif isinstance(tam_value, str):
            try:
                tam_millions = float(
                    tam_value.replace('$', '')
                    .replace('M', '')
                    .replace('B', '000')
                    .replace(',', '')
                )
                tam_display = tam_value
            except ValueError:
                tam_millions = 50
                tam_display = tam_value
        else:
            # Assume numeric in dollars
            tam_millions = tam_value / 1_000_000
            tam_display = f"${tam_millions:.0f}M"
        
        # Bubble size based on TAM (min 20, max 80)
        bubble_size = max(20, min(80, tam_millions / 2))
        
        # Color based on unmet need
        unmet_need = row.get(unmet_need_col, 'No')
        if unmet_need == 'Yes':
            color = '#e74c3c'  # Red for high unmet need
        else:
            color = '#3498db'  # Blue for lower unmet need
        
        fig.add_trace(go.Scatter(
            x=[row[competitors_col]],
            y=[row[overall_score_col]],
            mode='markers+text',
            marker=dict(
                size=bubble_size,
                color=color,
                opacity=0.7,
                line=dict(width=2, color='white')
            ),
            text=[disease_short],
            textposition='top center',
            textfont=dict(size=10),
            hovertemplate=(
                f"<b>{row[disease_col]}</b><br>"
                f"Approved Competitors: {row[competitors_col]}<br>"
                f"Overall Score: {row[overall_score_col]:.1f}<br>"
                f"TAM: {tam_display}<br>"
                f"Unmet Need: {unmet_need}<br>"
                "<extra></extra>"
            ),
            showlegend=False
        ))
    
    # Add legend markers for unmet need
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode='markers',
        marker=dict(size=15, color='#e74c3c'),
        name='Unmet Need: Yes'
    ))
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode='markers',
        marker=dict(size=15, color='#3498db'),
        name='Unmet Need: No'
    ))
    
    # Determine axis ranges from data
    max_competitors = df[competitors_col].max() if competitors_col in df.columns else 3
    min_score = df[overall_score_col].min() if overall_score_col in df.columns else 6
    max_score = df[overall_score_col].max() if overall_score_col in df.columns else 9
    
    layout_args = dict(
        title=dict(
            text=f'<b>{drug_name.upper()} - Market Opportunity Assessment</b><br>'
                 f'<sup>Competitive Landscape vs Priority Score (Bubble Size = TAM)</sup>',
            x=0.5,
            font=dict(size=16)
        ),
        xaxis=dict(
            title='Number of Approved Competitors',
            dtick=1,
            range=[-0.5, max(3, max_competitors + 0.5)],
            gridcolor='lightgray'
        ),
        yaxis=dict(
            title='Overall Priority Score',
            range=[min_score - 0.5, max_score + 0.5],
            gridcolor='lightgray'
        ),
        plot_bgcolor='white',
        height=height,
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=-0.15,
            xanchor='center',
            x=0.5
        )
    )
    
    # Add sweet spot zone if requested
    if show_sweet_spot:
        layout_args['annotations'] = [
            dict(
                text="SWEET SPOT:<br>High priority,<br>few competitors",
                x=0.2, y=max_score + 0.3,
                showarrow=False,
                font=dict(size=10, color='green'),
                align='center'
            )
        ]
        layout_args['shapes'] = [
            dict(
                type='rect',
                x0=-0.3, x1=0.8,
                y0=max_score - 1.0, y1=max_score + 0.5,
                fillcolor='rgba(0,255,0,0.05)',
                line=dict(color='green', width=1, dash='dash')
            )
        ]
    
    fig.update_layout(**layout_args)
    
    # Render in Streamlit
    st.plotly_chart(fig, use_container_width=True)


# =============================================================================
# EXAMPLE STREAMLIT APP
# =============================================================================

def example_app():
    """
    Example Streamlit app demonstrating the visualizations.
    
    Run with: streamlit run visualizations_streamlit.py
    """
    st.set_page_config(
        page_title="Drug Repurposing Analysis",
        page_icon="💊",
        layout="wide"
    )
    
    st.title("💊 Drug Repurposing Case Series Analysis")
    
    # File uploader
    uploaded_file = st.file_uploader(
        "Upload analysis Excel file",
        type=['xlsx'],
        help="Upload the Excel output from the case series analysis"
    )
    
    if uploaded_file is not None:
        # Load data
        try:
            analysis_df = pd.read_excel(uploaded_file, sheet_name='Analysis Summary')
            drug_df = pd.read_excel(uploaded_file, sheet_name='Drug Summary')
            drug_name = drug_df['Drug'].iloc[0] if len(drug_df) > 0 else "Drug"
        except Exception as e:
            st.error(f"Error loading file: {e}")
            return
        
        st.success(f"Loaded analysis for **{drug_name}** with {len(analysis_df)} indications")
        
        # Display visualizations in columns
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Priority Matrix")
            render_priority_matrix(analysis_df, drug_name=drug_name)
        
        with col2:
            st.subheader("Market Opportunity")
            render_market_opportunity(analysis_df, drug_name=drug_name)
        
        # Show data table
        st.subheader("Analysis Summary Data")
        st.dataframe(
            analysis_df,
            use_container_width=True,
            hide_index=True
        )
    
    else:
        # Demo with sample data
        st.info("Upload an analysis file, or view the demo below with sample data.")
        
        if st.button("Load Demo Data"):
            # Create sample data
            demo_data = pd.DataFrame({
                'Disease': [
                    'Transplantation-associated Thrombotic Microangiopathy',
                    'Membranoproliferative Glomerulonephritis',
                    'Autoimmune Hemolytic Anemia',
                    'Atypical Hemolytic Uremic Syndrome'
                ],
                '# Studies': [3, 1, 2, 3],
                'Total Patients': [5, 1, 2, 3],
                'Pooled Response (%)': [100, 100, 100, 100],
                'Clinical Score (avg)': [7.9, 8.5, 7.8, 6.9],
                'Evidence Score (avg)': [4.7, 4.9, 4.7, 4.8],
                'Market Score (avg)': [9.0, 7.7, 8.3, 6.7],
                'Overall Score (avg)': [7.4, 7.4, 7.2, 6.4],
                '# Approved Competitors': [0, 1, 1, 2],
                'Unmet Need': ['Yes', 'No', 'Yes', 'No'],
                'TAM Estimate': ['$172.8M', '$114.3M', '$42M', '$892M']
            })
            
            st.session_state['demo_data'] = demo_data
        
        if 'demo_data' in st.session_state:
            demo_data = st.session_state['demo_data']
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Priority Matrix")
                render_priority_matrix(demo_data, drug_name="Iptacopan")
            
            with col2:
                st.subheader("Market Opportunity")
                render_market_opportunity(demo_data, drug_name="Iptacopan")


# Run example app if executed directly
if __name__ == "__main__":
    example_app()
