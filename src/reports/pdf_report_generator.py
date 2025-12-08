"""
PDF Report Generator for Drug Repurposing Analysis

Generates professional PDF reports with LLM-generated scoring rationale
for each disease opportunity.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, ListFlowable, ListItem, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

from src.models.case_series_schemas import (
    DrugAnalysisResult, RepurposingOpportunity, CaseSeriesExtraction
)

logger = logging.getLogger(__name__)


class PDFReportGenerator:
    """
    Generates comprehensive PDF reports for drug repurposing analysis.
    
    Includes LLM-generated scoring rationale explanations for each disease.
    """
    
    def __init__(self, client=None, model: str = "claude-sonnet-4-20250514"):
        """
        Initialize PDF report generator.
        
        Args:
            client: Anthropic client for generating rationale text
            model: Model to use for rationale generation
        """
        self.client = client
        self.model = model
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
        
    def _setup_custom_styles(self):
        """Set up custom paragraph styles for the report."""
        # Title style
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#1a365d')
        ))
        
        # Section header
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceBefore=20,
            spaceAfter=10,
            textColor=colors.HexColor('#2c5282')
        ))
        
        # Disease header
        self.styles.add(ParagraphStyle(
            name='DiseaseHeader',
            parent=self.styles['Heading3'],
            fontSize=14,
            spaceBefore=15,
            spaceAfter=8,
            textColor=colors.HexColor('#2b6cb0')
        ))
        
        # Body text
        self.styles.add(ParagraphStyle(
            name='BodyText',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceBefore=6,
            spaceAfter=6,
            alignment=TA_JUSTIFY,
            leading=14
        ))
        
        # Rationale text (slightly indented, italic)
        self.styles.add(ParagraphStyle(
            name='RationaleText',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceBefore=4,
            spaceAfter=8,
            leftIndent=20,
            alignment=TA_JUSTIFY,
            leading=13,
            textColor=colors.HexColor('#4a5568')
        ))
        
        # Score label
        self.styles.add(ParagraphStyle(
            name='ScoreLabel',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#2d3748')
        ))

    def generate_report(
        self,
        result: DrugAnalysisResult,
        output_path: str,
        include_rationale: bool = True,
        analysis_provider: Optional[Any] = None
    ) -> str:
        """
        Generate a comprehensive PDF report.

        Args:
            result: DrugAnalysisResult with all opportunities
            output_path: Path to save the PDF
            include_rationale: Whether to generate LLM rationale for each disease
            analysis_provider: Optional object with _analyze_efficacy_totality and
                             _analyze_safety_totality methods for detailed analysis

        Returns:
            Path to generated PDF file
        """
        logger.info(f"Generating PDF report for {result.drug_name}")

        # Create output directory if needed
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create document
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch
        )

        # Build story (content)
        story = []

        # Title page
        story.extend(self._build_title_page(result))
        story.append(PageBreak())

        # Executive summary
        story.extend(self._build_executive_summary(result))
        story.append(PageBreak())

        # Scoring methodology
        story.extend(self._build_methodology_section())
        story.append(PageBreak())

        # Disease sections with rationale
        for i, opp in enumerate(result.opportunities, 1):
            rationale = None
            if include_rationale and self.client:
                # Get detailed analysis if provider available
                efficacy_analysis = None
                safety_analysis = None
                if analysis_provider:
                    try:
                        efficacy_analysis = analysis_provider._analyze_efficacy_totality(opp.extraction)
                        safety_analysis = analysis_provider._analyze_safety_totality(opp.extraction)
                    except Exception as e:
                        logger.warning(f"Could not get analysis for {opp.extraction.disease}: {e}")

                rationale = self._generate_scoring_rationale(
                    opp, result.drug_name, efficacy_analysis, safety_analysis
                )

            story.extend(self._build_disease_section(opp, i, rationale))

            # Page break every 2 diseases (adjust as needed)
            if i % 2 == 0 and i < len(result.opportunities):
                story.append(PageBreak())

        # Build PDF
        doc.build(story)
        logger.info(f"PDF report saved to: {output_path}")

        return output_path

    def _build_title_page(self, result: DrugAnalysisResult) -> List:
        """Build the title page content."""
        story = []

        story.append(Spacer(1, 2*inch))
        story.append(Paragraph(
            f"Drug Repurposing Analysis Report",
            self.styles['ReportTitle']
        ))
        story.append(Spacer(1, 0.5*inch))
        story.append(Paragraph(
            f"<b>{result.drug_name}</b>",
            ParagraphStyle(
                'DrugName',
                parent=self.styles['Heading1'],
                fontSize=20,
                alignment=TA_CENTER,
                textColor=colors.HexColor('#2c5282')
            )
        ))
        story.append(Spacer(1, 0.3*inch))
        if result.mechanism:
            story.append(Paragraph(
                f"Mechanism: {result.mechanism}",
                ParagraphStyle('Mechanism', parent=self.styles['Normal'],
                              alignment=TA_CENTER, fontSize=12)
            ))
        story.append(Spacer(1, inch))

        # Summary stats
        summary_data = [
            ['Analysis Date', result.analysis_date.strftime("%B %d, %Y")],
            ['Papers Screened', str(result.papers_screened or len(result.opportunities))],
            ['Opportunities Identified', str(len(result.opportunities))],
            ['Estimated Cost', f"${result.estimated_cost_usd:.2f}" if result.estimated_cost_usd else "N/A"]
        ]

        summary_table = Table(summary_data, colWidths=[2.5*inch, 2.5*inch])
        summary_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(summary_table)

        return story

    def _build_executive_summary(self, result: DrugAnalysisResult) -> List:
        """Build executive summary section."""
        story = []

        story.append(Paragraph("Executive Summary", self.styles['SectionHeader']))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e2e8f0')))
        story.append(Spacer(1, 0.2*inch))

        # Drug overview
        story.append(Paragraph(
            f"This report presents the drug repurposing analysis for <b>{result.drug_name}</b> "
            f"({result.generic_name or 'generic name not available'}). "
            f"The analysis identified <b>{len(result.opportunities)} potential repurposing opportunities</b> "
            f"across various therapeutic areas.",
            self.styles['BodyText']
        ))

        if result.approved_indications:
            story.append(Paragraph(
                f"<b>Current Approved Indications:</b> {', '.join(result.approved_indications)}",
                self.styles['BodyText']
            ))

        story.append(Spacer(1, 0.2*inch))

        # Top opportunities table
        story.append(Paragraph("Top Repurposing Opportunities", self.styles['DiseaseHeader']))

        top_opps = result.opportunities[:10]  # Top 10
        table_data = [['Rank', 'Disease', 'Score', 'Evidence', 'N Patients']]

        for opp in top_opps:
            ext = opp.extraction
            table_data.append([
                str(opp.rank),
                (ext.disease_normalized or ext.disease)[:40],
                f"{opp.scores.overall_priority:.1f}" if opp.scores else "N/A",
                ext.evidence_level.value,
                str(ext.patient_population.n_patients) if ext.patient_population.n_patients else "N/A"
            ])

        top_table = Table(table_data, colWidths=[0.6*inch, 2.8*inch, 0.8*inch, 1.2*inch, 0.9*inch])
        top_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
        ]))
        story.append(top_table)

        return story

    def _build_methodology_section(self) -> List:
        """Build scoring methodology explanation section."""
        story = []

        story.append(Paragraph("Scoring Methodology", self.styles['SectionHeader']))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e2e8f0')))
        story.append(Spacer(1, 0.2*inch))

        story.append(Paragraph(
            "Each repurposing opportunity is scored on a 1-10 scale across three dimensions:",
            self.styles['BodyText']
        ))

        # Scoring breakdown
        methodology_text = """
        <b>Clinical Signal (50% weight)</b><br/>
        • Response Rate (30%): Percentage of patients achieving clinical response<br/>
        • Safety Profile (30%): Tolerability and adverse event profile<br/>
        • Endpoint Quality (25%): Use of validated clinical instruments<br/>
        • Organ Domain Breadth (15%): Multi-organ system response<br/><br/>

        <b>Evidence Quality (25% weight)</b><br/>
        • Sample Size (30%): Number of patients studied<br/>
        • Publication Venue (25%): Journal impact and peer review quality<br/>
        • Response Durability (25%): Sustained clinical benefit over time<br/>
        • Data Completeness (20%): Completeness of extracted data<br/><br/>

        <b>Market Opportunity (25% weight)</b><br/>
        • Competitive Landscape (33%): Existing approved treatments<br/>
        • Market Size (33%): Patient population and revenue potential<br/>
        • Unmet Need (33%): Gap in current treatment options
        """
        story.append(Paragraph(methodology_text, self.styles['BodyText']))

        return story

    def _build_disease_section(
        self,
        opp: RepurposingOpportunity,
        index: int,
        rationale: Optional[str] = None
    ) -> List:
        """Build section for a single disease opportunity."""
        story = []
        ext = opp.extraction
        disease = ext.disease_normalized or ext.disease

        # Disease header
        story.append(Paragraph(
            f"{index}. {disease}",
            self.styles['DiseaseHeader']
        ))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#e2e8f0')))

        # Score summary table
        if opp.scores:
            scores_data = [
                ['Overall', 'Clinical', 'Evidence', 'Market'],
                [
                    f"{opp.scores.overall_priority:.1f}",
                    f"{opp.scores.clinical_signal:.1f}",
                    f"{opp.scores.evidence_quality:.1f}",
                    f"{opp.scores.market_opportunity:.1f}"
                ]
            ]
            scores_table = Table(scores_data, colWidths=[1.5*inch]*4)
            scores_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#edf2f7')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
            ]))
            story.append(scores_table)
            story.append(Spacer(1, 0.1*inch))

        # Key information
        info_items = []
        if ext.evidence_level:
            info_items.append(f"<b>Evidence Level:</b> {ext.evidence_level.value}")
        if ext.patient_population and ext.patient_population.n_patients:
            info_items.append(f"<b>N Patients:</b> {ext.patient_population.n_patients}")
        if ext.efficacy.primary_endpoint:
            info_items.append(f"<b>Primary Endpoint:</b> {ext.efficacy.primary_endpoint}")
        if ext.efficacy.responders_pct:
            info_items.append(f"<b>Response Rate:</b> {ext.efficacy.responders_pct:.1f}%")
        if ext.source and ext.source.pmid:
            info_items.append(f"<b>PMID:</b> {ext.source.pmid}")

        if info_items:
            story.append(Paragraph("<br/>".join(info_items), self.styles['BodyText']))

        # Key findings
        if ext.key_findings:
            story.append(Paragraph(
                f"<b>Key Findings:</b> {ext.key_findings[:500]}",
                self.styles['BodyText']
            ))

        # LLM-generated rationale
        if rationale:
            story.append(Spacer(1, 0.1*inch))
            story.append(Paragraph("<b>Scoring Rationale:</b>", self.styles['ScoreLabel']))
            story.append(Paragraph(rationale, self.styles['RationaleText']))

        story.append(Spacer(1, 0.2*inch))

        return story

    def _generate_scoring_rationale(
        self,
        opp: RepurposingOpportunity,
        drug_name: str,
        efficacy_analysis: Optional[Dict[str, Any]] = None,
        safety_analysis: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Generate LLM-based scoring rationale for an opportunity.

        Explains why the opportunity received its scores with detailed
        commentary on efficacy totality and safety profile.
        """
        if not self.client or not opp.scores:
            return None

        ext = opp.extraction
        disease = ext.disease_normalized or ext.disease

        # Build efficacy totality context
        efficacy_context = ""
        if efficacy_analysis:
            efficacy_context = f"""
EFFICACY TOTALITY ANALYSIS:
- Total Endpoints Evaluated: {efficacy_analysis.get('total_endpoints', 0)}
- Positive Endpoints: {efficacy_analysis.get('positive_endpoints', 0)} ({efficacy_analysis.get('positive_rate', 0)*100:.0f}%)
- Statistically Significant: {efficacy_analysis.get('significant_endpoints', 0)} ({efficacy_analysis.get('significance_rate', 0)*100:.0f}%)
- Primary Endpoints: {efficacy_analysis.get('primary_count', 0)} ({efficacy_analysis.get('primary_positive', 0)} positive)
- Secondary Endpoints: {efficacy_analysis.get('secondary_count', 0)} ({efficacy_analysis.get('secondary_positive', 0)} positive)
- Response Rate Range: {f"{efficacy_analysis.get('min_response_rate', 'N/A')}% - {efficacy_analysis.get('max_response_rate', 'N/A')}%" if efficacy_analysis.get('max_response_rate') else 'N/A'}
- Concordance Assessment: {efficacy_analysis.get('concordance_assessment', 'Not assessed')}
"""

        # Build safety totality context
        safety_context = ""
        if safety_analysis:
            safety_context = f"""
SAFETY TOTALITY ANALYSIS:
- Overall Safety Profile: {safety_analysis.get('safety_profile', 'Unknown')}
- Serious Adverse Events: {safety_analysis.get('sae_count', 0)} ({f"{safety_analysis.get('sae_percentage', 0):.1f}%" if safety_analysis.get('sae_percentage') else 'N/A'})
- Total AE Types Reported: {safety_analysis.get('total_ae_types', 0)}
- Discontinuations: {safety_analysis.get('discontinuations_n', 0)} ({f"{safety_analysis.get('discontinuation_rate', 0):.1f}%" if safety_analysis.get('discontinuation_rate') else 'N/A'})
- Safety Assessment: {safety_analysis.get('safety_assessment', 'Not assessed')}
"""

        # Build main context
        context = f"""
Drug: {drug_name}
Disease: {disease}
Evidence Level: {ext.evidence_level.value}
N Patients: {ext.patient_population.n_patients if ext.patient_population else 'Not reported'}
Primary Endpoint: {ext.efficacy.primary_endpoint or 'Not specified'}
Primary Response Rate: {f'{ext.efficacy.responders_pct:.1f}%' if ext.efficacy.responders_pct else 'Not reported'}
Key Findings: {ext.key_findings or 'Not available'}
{efficacy_context}
{safety_context}
SCORES:
- Overall Priority: {opp.scores.overall_priority:.1f}/10
- Clinical Signal: {opp.scores.clinical_signal:.1f}/10
  - Response Rate Score: {opp.scores.response_rate_score:.1f}/10
  - Safety Score: {opp.scores.safety_profile_score:.1f}/10
  - Endpoint Quality Score: {opp.scores.endpoint_quality_score:.1f}/10
  - Organ Domain Score: {opp.scores.organ_domain_score:.1f}/10
- Evidence Quality: {opp.scores.evidence_quality:.1f}/10
- Market Opportunity: {opp.scores.market_opportunity:.1f}/10
"""

        prompt = f"""You are a clinical development strategist analyzing drug repurposing opportunities.

Based on the following comprehensive data, provide a detailed rationale (4-6 sentences) explaining why this opportunity received its scores.

Your rationale MUST address:
1. EFFICACY TOTALITY: Comment on the consistency/concordance across all endpoints measured. How many endpoints showed improvement? Were results statistically significant across multiple measures?
2. SAFETY PROFILE: Summarize the safety data including SAEs, discontinuations, and overall tolerability assessment.
3. EVIDENCE STRENGTH: Comment on sample size, study design limitations, and confidence in the data.
4. COMMERCIAL/STRATEGIC: Note any market factors (unmet need, competition) that affect the opportunity.

{context}

Write a professional, objective rationale. Be specific about the data. Use actual numbers from the analysis."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"Error generating rationale for {disease}: {e}")
            return None

    def generate_report_sync(
        self,
        result: DrugAnalysisResult,
        output_dir: str,
        include_rationale: bool = True
    ) -> str:
        """
        Convenience method to generate report with automatic filename.

        Args:
            result: DrugAnalysisResult
            output_dir: Directory to save PDF
            include_rationale: Whether to generate LLM rationale

        Returns:
            Path to generated PDF
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{result.drug_name.lower()}_report_{timestamp}.pdf"
        output_path = str(Path(output_dir) / filename)

        return self.generate_report(result, output_path, include_rationale)

