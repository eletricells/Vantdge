"""
Streamlit visualization components for drug repurposing case series analysis.

Usage:
    import streamlit as st
    from src.visualization.case_series_charts import render_priority_matrix, render_market_opportunity
    
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
    clinical_score_col: str = "Clinical Score (avg)",
    total_patients_col: str = "Total Patients",
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
    clinical_score_col : str
        Column name for clinical score (used for color gradient)
    total_patients_col : str
        Column name for total patients (used for bubble size)
    unmet_need_col : str
        Column name for unmet need (Yes/No)
    disease_col : str
        Column name for disease/indication name
    height : int
        Chart height in pixels
    show_sweet_spot : bool
        Whether to show the highlighted "sweet spot" zone
    """

    # Prepare data
    df_plot = df.copy()
    df_plot['disease_short'] = df_plot[disease_col].apply(shorten_disease)
    df_plot['n_patients'] = df_plot.get(total_patients_col, pd.Series([0] * len(df_plot))).fillna(0).astype(int)
    df_plot['bubble_size'] = df_plot['n_patients'].apply(lambda x: max(20, min(80, 10 + x * 2)))

    # Get clinical scores for color mapping
    clinical_scores = df_plot.get(clinical_score_col, pd.Series([5.0] * len(df_plot))).fillna(5.0)

    fig = go.Figure()

    # Add main scatter trace with clinical score color gradient
    fig.add_trace(go.Scatter(
        x=df_plot[competitors_col],
        y=df_plot[overall_score_col],
        mode='markers+text',
        marker=dict(
            size=df_plot['bubble_size'],
            color=clinical_scores,
            colorscale='Plasma',  # Purple to yellow/orange gradient
            cmin=clinical_scores.min(),
            cmax=clinical_scores.max(),
            line=dict(width=2, color='white'),
            opacity=0.8,
            showscale=True,
            colorbar=dict(
                title="Clinical<br>Score",
                thickness=15,
                len=0.7
            )
        ),
        text=df_plot['disease_short'],
        textposition='top center',
        textfont=dict(size=10, color='#333'),
        customdata=df_plot[[disease_col, clinical_score_col, 'n_patients', unmet_need_col]].values,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Overall Score: %{y:.1f}<br>"
            "Clinical Score: %{customdata[1]:.1f}<br>"
            "# Competitors: %{x}<br>"
            "Total Patients: %{customdata[2]}<br>"
            "Unmet Need: %{customdata[3]}<br>"
            "<extra></extra>"
        ),
        showlegend=False
    ))

    # Determine axis ranges from data
    max_competitors = df_plot[competitors_col].max() if competitors_col in df_plot.columns else 3
    min_score = df_plot[overall_score_col].min() if overall_score_col in df_plot.columns else 6
    max_score = df_plot[overall_score_col].max() if overall_score_col in df_plot.columns else 9

    layout_args = dict(
        title=dict(
            text=f'<b>{drug_name.upper()} Market Opportunity Analysis</b><br>'
                 f'<sup>Competitive Landscape vs Priority Score (Bubble Size = Total Patients)</sup>',
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
        showlegend=False
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

