"""
Case Series Report Generator

Generates comprehensive analytical reports from drug repurposing case series analyses.
Based on report_prompt_v2.py with enhancements for robustness and integration.
"""

import pandas as pd
from typing import Dict, Any, Optional
from pathlib import Path
from anthropic import Anthropic
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class CaseSeriesReportGenerator:
    """
    Generates analytical reports from case series analysis data.
    
    Features:
    - Loads data from Excel or AnalysisResult objects
    - Generates comprehensive LLM prompts
    - Calls Claude API to generate reports
    - Saves reports to markdown/text files
    """
    
    def __init__(self, client: Optional[Anthropic] = None, model: str = "claude-sonnet-4-20250514"):
        """
        Initialize report generator.
        
        Parameters:
        -----------
        client : Anthropic, optional
            Anthropic client instance. If None, will create from env vars.
        model : str
            Claude model to use for report generation
        """
        self.client = client
        self.model = model
        self.logger = logger
    
    def format_data_from_excel(self, excel_path: str) -> Dict[str, Any]:
        """
        Load and format Excel analysis data for the report prompt.
        
        Parameters:
        -----------
        excel_path : str
            Path to the analysis Excel file
        
        Returns:
        --------
        dict
            Formatted data ready for prompt generation
        """
        try:
            xlsx = pd.ExcelFile(excel_path)
            
            # Load all sheets
            analysis_df = pd.read_excel(xlsx, sheet_name='Analysis Summary')
            drug_df = pd.read_excel(xlsx, sheet_name='Drug Summary')
            opportunities_df = pd.read_excel(xlsx, sheet_name='Opportunities')
            market_df = pd.read_excel(xlsx, sheet_name='Market Intelligence')
            efficacy_df = pd.read_excel(xlsx, sheet_name='Efficacy Endpoints')
            safety_df = pd.read_excel(xlsx, sheet_name='Safety Endpoints')
            
            # Extract drug info
            drug_info = drug_df.iloc[0].to_dict() if len(drug_df) > 0 else {}
            
            # Format efficacy data
            efficacy_detail = efficacy_df[[
                'Disease', 'PMID', 'Endpoint Name', 'Endpoint Category',
                'Baseline Value', 'Final Value', 'Change from Baseline', 'Percent Change',
                'Response Rate (%)', 'Timepoint', 'Notes'
            ]].copy()
            efficacy_detail = efficacy_detail.fillna('')
            
            # Format safety data
            safety_detail = safety_df[[
                'Disease', 'PMID', 'Event Name', 'Event Category', 'Is Serious (SAE)',
                'Patients Affected (n)', 'Incidence (%)', 'Related to Drug', 'Outcome', 'Notes'
            ]].copy()
            safety_detail = safety_detail.fillna('')
            
            # Build data dictionary
            data = {
                'drug_name': drug_info.get('Drug', 'Unknown'),
                'generic_name': drug_info.get('Generic Name', ''),
                'mechanism': drug_info.get('Mechanism', ''),
                'approved_indications': drug_info.get('Approved Indications', ''),
                'papers_screened': drug_info.get('Papers Screened', 0),
                'opportunities_found': drug_info.get('Opportunities Found', 0),
                'analysis_date': str(drug_info.get('Analysis Date', '')),
                
                # Summary statistics
                'n_indications': len(analysis_df),
                'total_patients': int(analysis_df['Total Patients'].sum()),
                'total_studies': int(analysis_df['# Studies'].sum()),
                
                # Top opportunities
                'top_opportunities': analysis_df.nlargest(5, 'Overall Score (avg)').to_dict('records'),
                
                # Full data as formatted strings
                'analysis_summary_table': analysis_df.to_markdown(index=False),
                
                # Detailed opportunities with scores breakdown
                'opportunities_table': opportunities_df[[
                    'Disease (Standardized)', 'N Patients', 'Primary Endpoint', 'Endpoint Result',
                    'Responders (%)', 'Time to Response', 'Duration of Response',
                    'Clinical Score', 'Evidence Score', 'Market Score', 'Overall Priority',
                    'Response Rate Score (Quality-Weighted)', 'Safety Score', 'Organ Domain Score',
                    '# Efficacy Endpoints Scored', 'Efficacy Concordance',
                    'Safety Summary', 'Key Findings', 'PMID'
                ]].to_markdown(index=False),
                
                'market_intelligence_table': market_df[[
                    'Disease', 'US Prevalence', 'US Incidence', 'Patient Population',
                    'Approved Treatments (Count)', 'Approved Drug Names',
                    'Pipeline Therapies (Count)', 'Pipeline Details',
                    'Unmet Need', 'Unmet Need Description',
                    'TAM (Total Addressable Market)', 'Competitive Landscape'
                ]].to_markdown(index=False),
                
                # Detailed efficacy endpoints
                'efficacy_endpoints_table': efficacy_detail.to_markdown(index=False),
                
                # Detailed safety data
                'safety_endpoints_table': safety_detail.to_markdown(index=False),
            }
            
            return data

        except Exception as e:
            self.logger.error(f"Error formatting data from Excel: {e}", exc_info=True)
            raise

    def format_data_from_result(self, result) -> Dict[str, Any]:
        """
        Format data from an AnalysisResult object.

        Parameters:
        -----------
        result : AnalysisResult
            Analysis result object from the agent

        Returns:
        --------
        dict
            Formatted data ready for prompt generation
        """
        try:
            opps = result.opportunities

            # Build summary statistics
            total_patients = sum(o.extraction.sample_size for o in opps if o.extraction)
            unique_diseases = set(o.extraction.disease for o in opps if o.extraction)

            # Create analysis summary data
            disease_groups = {}
            for opp in opps:
                if not opp.extraction:
                    continue
                disease = opp.extraction.disease
                if disease not in disease_groups:
                    disease_groups[disease] = {
                        'studies': [],
                        'patients': 0,
                        'scores': []
                    }
                disease_groups[disease]['studies'].append(opp)
                disease_groups[disease]['patients'] += opp.extraction.sample_size or 0
                disease_groups[disease]['scores'].append(opp.scores.overall_priority)

            # Format as markdown tables
            analysis_rows = []
            for disease, data in sorted(disease_groups.items(),
                                       key=lambda x: sum(x[1]['scores'])/len(x[1]['scores']),
                                       reverse=True):
                avg_score = sum(data['scores']) / len(data['scores'])
                analysis_rows.append({
                    'Disease': disease,
                    '# Studies': len(data['studies']),
                    'Total Patients': data['patients'],
                    'Overall Score (avg)': f"{avg_score:.1f}"
                })

            analysis_summary_table = pd.DataFrame(analysis_rows).to_markdown(index=False)

            # Format opportunities table
            opp_rows = []
            for opp in sorted(opps, key=lambda x: x.scores.overall_priority, reverse=True):
                ext = opp.extraction
                if not ext:
                    continue

                # Get primary endpoint
                primary_endpoint = "N/A"
                endpoint_result = "N/A"
                response_rate = "N/A"
                if ext.efficacy_endpoints:
                    primary = [e for e in ext.efficacy_endpoints if e.endpoint_category == 'primary']
                    if primary:
                        primary_endpoint = primary[0].endpoint_name
                        if primary[0].response_rate:
                            response_rate = f"{primary[0].response_rate:.1f}%"
                        if primary[0].change_from_baseline:
                            endpoint_result = f"{primary[0].change_from_baseline:+.1f}"

                opp_rows.append({
                    'Disease (Standardized)': ext.disease,
                    'N Patients': ext.sample_size or 0,
                    'Primary Endpoint': primary_endpoint,
                    'Endpoint Result': endpoint_result,
                    'Responders (%)': response_rate,
                    'Clinical Score': f"{opp.scores.clinical_signal:.1f}",
                    'Evidence Score': f"{opp.scores.evidence_quality:.1f}",
                    'Market Score': f"{opp.scores.market_opportunity:.1f}",
                    'Overall Priority': f"{opp.scores.overall_priority:.1f}",
                    'PMID': ext.pmid or 'N/A'
                })

            opportunities_table = pd.DataFrame(opp_rows).to_markdown(index=False)

            # Format efficacy endpoints table
            efficacy_rows = []
            for opp in opps:
                ext = opp.extraction
                if not ext or not ext.efficacy_endpoints:
                    continue
                for endpoint in ext.efficacy_endpoints:
                    efficacy_rows.append({
                        'Disease': ext.disease,
                        'PMID': ext.pmid or 'N/A',
                        'Endpoint Name': endpoint.endpoint_name,
                        'Endpoint Category': endpoint.endpoint_category,
                        'Baseline Value': endpoint.baseline_value or '',
                        'Final Value': endpoint.final_value or '',
                        'Change from Baseline': endpoint.change_from_baseline or '',
                        'Percent Change': endpoint.percent_change or '',
                        'Response Rate (%)': endpoint.response_rate or '',
                        'Timepoint': endpoint.timepoint or '',
                        'Notes': endpoint.notes or ''
                    })

            efficacy_endpoints_table = pd.DataFrame(efficacy_rows).to_markdown(index=False) if efficacy_rows else "No efficacy data available"

            # Format safety endpoints table
            safety_rows = []
            for opp in opps:
                ext = opp.extraction
                if not ext or not ext.safety_events:
                    continue
                for event in ext.safety_events:
                    safety_rows.append({
                        'Disease': ext.disease,
                        'PMID': ext.pmid or 'N/A',
                        'Event Name': event.event_name,
                        'Event Category': event.event_category,
                        'Is Serious (SAE)': 'Yes' if event.is_serious else 'No',
                        'Patients Affected (n)': event.patients_affected or '',
                        'Incidence (%)': event.incidence_percent or '',
                        'Related to Drug': event.relationship_to_drug or '',
                        'Outcome': event.outcome or '',
                        'Notes': event.notes or ''
                    })

            safety_endpoints_table = pd.DataFrame(safety_rows).to_markdown(index=False) if safety_rows else "No safety data available"

            # Format market intelligence table
            market_rows = []
            for opp in opps:
                if not opp.market_intelligence:
                    continue
                mi = opp.market_intelligence
                market_rows.append({
                    'Disease': opp.extraction.disease if opp.extraction else 'Unknown',
                    'US Prevalence': mi.prevalence_us or 'N/A',
                    'US Incidence': mi.incidence_us or 'N/A',
                    'Patient Population': mi.patient_population or 'N/A',
                    'Approved Treatments (Count)': mi.approved_competitors or 0,
                    'Approved Drug Names': mi.approved_drug_names or 'N/A',
                    'Pipeline Therapies (Count)': mi.pipeline_therapies or 0,
                    'Pipeline Details': mi.pipeline_details or 'N/A',
                    'Unmet Need': 'Yes' if mi.unmet_need_score >= 7 else 'No',
                    'Unmet Need Description': mi.unmet_need_description or 'N/A',
                    'TAM (Total Addressable Market)': mi.tam_estimate or 'N/A',
                    'Competitive Landscape': mi.competitive_landscape or 'N/A'
                })

            market_intelligence_table = pd.DataFrame(market_rows).to_markdown(index=False) if market_rows else "No market intelligence available"

            # Build final data dictionary
            data = {
                'drug_name': result.drug_name,
                'generic_name': result.generic_name or '',
                'mechanism': result.mechanism or '',
                'approved_indications': ', '.join(result.approved_indications) if result.approved_indications else 'N/A',
                'papers_screened': len(result.opportunities),  # Approximate
                'opportunities_found': len(result.opportunities),
                'analysis_date': datetime.now().strftime("%Y-%m-%d"),

                # Summary statistics
                'n_indications': len(unique_diseases),
                'total_patients': total_patients,
                'total_studies': len(opps),

                # Top opportunities
                'top_opportunities': analysis_rows[:5],

                # Formatted tables
                'analysis_summary_table': analysis_summary_table,
                'opportunities_table': opportunities_table,
                'efficacy_endpoints_table': efficacy_endpoints_table,
                'safety_endpoints_table': safety_endpoints_table,
                'market_intelligence_table': market_intelligence_table
            }

            return data

        except Exception as e:
            self.logger.error(f"Error formatting data from result: {e}", exc_info=True)
            raise

    def generate_prompt(self, data: Dict[str, Any]) -> str:
        """
        Generate the complete report prompt with data filled in.

        Parameters:
        -----------
        data : dict
            Output from format_data_from_excel() or format_data_from_result()

        Returns:
        --------
        str
            Complete prompt ready to send to an LLM
        """
        try:
            # Load template
            template_path = Path(__file__).parent.parent / 'prompts' / 'templates' / 'case_series_report_template.txt'
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()

            # Truncate mechanism if too long
            mechanism = str(data.get('mechanism', ''))
            if len(mechanism) > 800:
                mechanism = mechanism[:800] + '...'

            # Format the template
            prompt = template.format(
                drug_name=data['drug_name'],
                generic_name=data['generic_name'],
                mechanism=mechanism,
                approved_indications=data['approved_indications'],
                analysis_date=data['analysis_date'],
                papers_screened=data['papers_screened'],
                opportunities_found=data['opportunities_found'],
                n_indications=data['n_indications'],
                total_patients=data['total_patients'],
                total_studies=data['total_studies'],
                analysis_summary_table=data['analysis_summary_table'],
                opportunities_table=data['opportunities_table'],
                efficacy_endpoints_table=data['efficacy_endpoints_table'],
                safety_endpoints_table=data['safety_endpoints_table'],
                market_intelligence_table=data['market_intelligence_table']
            )

            return prompt

        except Exception as e:
            self.logger.error(f"Error generating prompt: {e}", exc_info=True)
            raise

    def generate_report(
        self,
        data: Dict[str, Any],
        max_tokens: int = 8000,
        temperature: float = 0.0
    ) -> str:
        """
        Generate report by calling Claude API.

        Parameters:
        -----------
        data : dict
            Formatted data from format_data_from_excel() or format_data_from_result()
        max_tokens : int
            Maximum tokens for the response
        temperature : float
            Temperature for generation (0.0 = deterministic)

        Returns:
        --------
        str
            Generated report text
        """
        try:
            # Ensure we have a client
            if self.client is None:
                import os
                api_key = os.environ.get('ANTHROPIC_API_KEY')
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY not set. Cannot generate report.")
                self.client = Anthropic(api_key=api_key)

            # Generate prompt
            prompt = self.generate_prompt(data)

            self.logger.info(f"Generating report for {data['drug_name']} using {self.model}")

            # Call API
            message = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            report_text = message.content[0].text

            self.logger.info(f"Report generated successfully ({len(report_text)} characters)")

            return report_text

        except Exception as e:
            self.logger.error(f"Error generating report: {e}", exc_info=True)
            raise

    def save_report(
        self,
        report_text: str,
        output_path: str,
        drug_name: str = None
    ) -> str:
        """
        Save report to a file.

        Parameters:
        -----------
        report_text : str
            Generated report text
        output_path : str
            Path to save the report (can be .md or .txt)
        drug_name : str, optional
            Drug name for auto-generating filename

        Returns:
        --------
        str
            Path where report was saved
        """
        try:
            output_path = Path(output_path)

            # Auto-generate filename if directory provided
            if output_path.is_dir():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                drug_slug = drug_name.lower().replace(' ', '_') if drug_name else 'report'
                filename = f"{drug_slug}_report_{timestamp}.md"
                output_path = output_path / filename

            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Save report
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_text)

            self.logger.info(f"Report saved to: {output_path}")

            return str(output_path)

        except Exception as e:
            self.logger.error(f"Error saving report: {e}", exc_info=True)
            raise

    def generate_and_save_report(
        self,
        excel_path: str = None,
        result = None,
        output_path: str = None,
        max_tokens: int = 8000
    ) -> tuple[str, str]:
        """
        Complete workflow: format data, generate report, save to file.

        Parameters:
        -----------
        excel_path : str, optional
            Path to Excel file (if using Excel as source)
        result : AnalysisResult, optional
            Analysis result object (if using result as source)
        output_path : str, optional
            Where to save the report. If None, saves to data/reports/
        max_tokens : int
            Maximum tokens for generation

        Returns:
        --------
        tuple[str, str]
            (report_text, saved_path)
        """
        try:
            # Format data
            if excel_path:
                self.logger.info(f"Loading data from Excel: {excel_path}")
                data = self.format_data_from_excel(excel_path)
            elif result:
                self.logger.info(f"Loading data from AnalysisResult")
                data = self.format_data_from_result(result)
            else:
                raise ValueError("Must provide either excel_path or result")

            # Generate report
            report_text = self.generate_report(data, max_tokens=max_tokens)

            # Save report
            if output_path is None:
                output_path = Path('data') / 'reports'

            saved_path = self.save_report(
                report_text,
                output_path,
                drug_name=data['drug_name']
            )

            return report_text, saved_path

        except Exception as e:
            self.logger.error(f"Error in generate_and_save_report: {e}", exc_info=True)
            raise

