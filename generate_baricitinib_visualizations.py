"""
Generate visualizations for the baricitinib analysis.
Creates interactive charts and saves them as HTML files.
"""
import sys
import os
from pathlib import Path
import pandas as pd
import logging
import glob

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

import plotly.graph_objects as go

def shorten_disease(name: str, max_len: int = 30) -> str:
    """Shorten disease names for display."""
    if len(str(name)) <= max_len:
        return str(name)
    return str(name)[:max_len-3] + '...'

def create_priority_matrix(df: pd.DataFrame, drug_name: str = "Drug", height: int = 600):
    """Create priority matrix figure."""
    fig = go.Figure()

    for _, row in df.iterrows():
        disease_short = shorten_disease(row['Disease'], max_len=25)
        n_patients = int(row['Total Patients']) if pd.notna(row['Total Patients']) else 0
        bubble_size = max(10, min(50, 10 + n_patients * 2))

        fig.add_trace(go.Scatter(
            x=[row['Clinical Score (avg)']],
            y=[row['Evidence Score (avg)']],
            mode='markers+text',
            marker=dict(
                size=bubble_size,
                color=row['Overall Score (avg)'],
                colorscale='RdYlGn',
                cmin=5,
                cmax=9,
                line=dict(width=2, color='white'),
                opacity=0.8,
                showscale=True,
                colorbar=dict(title="Overall<br>Score")
            ),
            text=[disease_short],
            textposition='top center',
            textfont=dict(size=11, color='#333'),
            hovertemplate=(
                f"<b>{row['Disease']}</b><br>"
                f"Clinical Score: {row['Clinical Score (avg)']:.1f}<br>"
                f"Evidence Score: {row['Evidence Score (avg)']:.1f}<br>"
                f"Overall Score: {row['Overall Score (avg)']:.1f}<br>"
                f"Total Patients: {n_patients}<br>"
                f"# Studies: {row.get('# Studies', 'N/A')}<br>"
                "<extra></extra>"
            ),
            showlegend=False
        ))

    fig.update_layout(
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
            range=[3, 10],
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

    return fig

def create_market_opportunity(df: pd.DataFrame, drug_name: str = "Drug", height: int = 600):
    """Create market opportunity figure."""
    fig = go.Figure()

    for _, row in df.iterrows():
        disease_short = shorten_disease(row['Disease'], max_len=25)
        n_patients = int(row['Total Patients']) if pd.notna(row['Total Patients']) else 0
        bubble_size = max(10, min(50, 10 + n_patients * 2))

        # Use number of approved competitors if available, otherwise default to 0
        competitors = row.get('# Approved Competitors', 0)

        fig.add_trace(go.Scatter(
            x=[competitors],
            y=[row['Overall Score (avg)']],
            mode='markers+text',
            marker=dict(
                size=bubble_size,
                color=row['Clinical Score (avg)'],
                colorscale='Viridis',
                cmin=5,
                cmax=10,
                line=dict(width=2, color='white'),
                opacity=0.8,
                showscale=True,
                colorbar=dict(title="Clinical<br>Score")
            ),
            text=[disease_short],
            textposition='top center',
            textfont=dict(size=11, color='#333'),
            hovertemplate=(
                f"<b>{row['Disease']}</b><br>"
                f"Overall Score: {row['Overall Score (avg)']:.1f}<br>"
                f"Clinical Score: {row['Clinical Score (avg)']:.1f}<br>"
                f"# Competitors: {competitors}<br>"
                f"Total Patients: {n_patients}<br>"
                f"Unmet Need: {row.get('Unmet Need', 'Unknown')}<br>"
                "<extra></extra>"
            ),
            showlegend=False
        ))

    fig.update_layout(
        title=dict(
            text=f'<b>{drug_name.upper()} Market Opportunity</b><br>'
                 f'<sup>Competitive Landscape vs Priority Score</sup>',
            x=0.5,
            font=dict(size=18)
        ),
        xaxis=dict(
            title='Number of Approved Competitors',
            gridcolor='lightgray'
        ),
        yaxis=dict(
            title='Overall Priority Score',
            range=[5, 10],
            dtick=1,
            gridcolor='lightgray'
        ),
        plot_bgcolor='white',
        height=height,
        annotations=[
            dict(
                text="Bubble size = Total patients<br>Color = Clinical score<br>Left side = Less competition",
                xref="paper", yref="paper",
                x=0.02, y=0.98,
                showarrow=False,
                font=dict(size=10, color='gray'),
                align='left'
            )
        ]
    )

    return fig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Generate visualizations for baricitinib analysis from Excel file."""

    # Find the most recent baricitinib Excel file
    excel_files = glob.glob('data/case_series/baricitinib_*.xlsx')
    if not excel_files:
        logger.error("No baricitinib Excel files found!")
        return

    # Get the most recent file
    excel_path = max(excel_files, key=os.path.getctime)
    logger.info(f"Loading data from: {excel_path}")

    # Load the Analysis Summary sheet
    try:
        analysis_df = pd.read_excel(excel_path, sheet_name='Analysis Summary')
        logger.info(f"Loaded {len(analysis_df)} diseases from Analysis Summary")
    except Exception as e:
        logger.error(f"Error loading Excel file: {e}")
        return

    # Check if we have the required columns
    required_cols = ['Disease', '# Studies', 'Total Patients', 'Clinical Score (avg)',
                     'Evidence Score (avg)', 'Overall Score (avg)']
    missing_cols = [col for col in required_cols if col not in analysis_df.columns]
    if missing_cols:
        logger.error(f"Missing required columns: {missing_cols}")
        logger.info(f"Available columns: {list(analysis_df.columns)}")
        return

    # Add missing columns with defaults
    if 'Market Score (avg)' not in analysis_df.columns:
        analysis_df['Market Score (avg)'] = 5.0
    if '# Approved Competitors' not in analysis_df.columns:
        analysis_df['# Approved Competitors'] = 0
    if 'Unmet Need' not in analysis_df.columns:
        analysis_df['Unmet Need'] = 'Unknown'
    if 'TAM Estimate' not in analysis_df.columns:
        analysis_df['TAM Estimate'] = 'N/A'

    logger.info(f"Prepared data for {len(analysis_df)} diseases")


    # Create output directory
    output_dir = Path('data/case_series/visualizations')
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate Priority Matrix
    logger.info("Generating Priority Matrix...")
    try:
        fig1 = create_priority_matrix(
            analysis_df,
            drug_name='Baricitinib',
            height=600
        )
        output_path1 = output_dir / 'baricitinib_priority_matrix.html'
        fig1.write_html(str(output_path1))
        logger.info(f"✅ Saved Priority Matrix: {output_path1}")
    except Exception as e:
        logger.error(f"Error generating priority matrix: {e}")
        import traceback
        traceback.print_exc()

    # Generate Market Opportunity Chart
    logger.info("Generating Market Opportunity Chart...")
    try:
        fig2 = create_market_opportunity(
            analysis_df,
            drug_name='Baricitinib',
            height=600
        )
        output_path2 = output_dir / 'baricitinib_market_opportunity.html'
        fig2.write_html(str(output_path2))
        logger.info(f"✅ Saved Market Opportunity Chart: {output_path2}")
    except Exception as e:
        logger.error(f"Error generating market opportunity chart: {e}")
        import traceback
        traceback.print_exc()
    
    logger.info("\n" + "="*80)
    logger.info("VISUALIZATION FILES GENERATED:")
    logger.info("="*80)
    logger.info(f"📊 Priority Matrix: {output_dir / 'baricitinib_priority_matrix.html'}")
    logger.info(f"📊 Market Opportunity: {output_dir / 'baricitinib_market_opportunity.html'}")
    logger.info("="*80)
    logger.info("\nOpen these HTML files in your browser to view the interactive charts!")

if __name__ == "__main__":
    main()

