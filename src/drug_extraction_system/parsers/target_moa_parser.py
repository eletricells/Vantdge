"""
Target and MoA Category Parser

Extracts standardized molecular target and mechanism of action category from drug data.
"""
import logging
import anthropic
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TargetMoAParser:
    """Parse and extract standardized target and MoA category from drug information."""
    
    def __init__(self):
        """Initialize the parser with Claude API."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        self.client = anthropic.Anthropic(api_key=api_key)
    
    def parse(self, drug_name: str, mechanism_text: str, drug_type: str = None) -> Dict[str, Optional[str]]:
        """
        Extract standardized target and MoA category from mechanism text.
        
        Args:
            drug_name: Name of the drug
            mechanism_text: Full mechanism of action text from FDA label
            drug_type: Drug type (e.g., "mAb", "small molecule")
        
        Returns:
            Dictionary with 'target' and 'moa_category' keys
        """
        if not mechanism_text or len(mechanism_text.strip()) < 20:
            logger.warning(f"Insufficient mechanism text for {drug_name}")
            return {"target": None, "moa_category": None}
        
        prompt = f"""Extract the molecular target and mechanism of action category from this drug information.

Drug Name: {drug_name}
Drug Type: {drug_type or "Unknown"}

Mechanism of Action Text:
{mechanism_text[:2000]}

Please extract:
1. **Target**: The specific molecular target(s) the drug acts on. Use standard nomenclature.
   Examples: "IL-17A", "JAK1/JAK2", "C5", "PD-1", "KRAS G12C", "CD20"
   
2. **MoA Category**: A standardized mechanism of action category.
   Examples: "IL-17A inhibitor", "JAK inhibitor", "Complement inhibitor", "PD-1 inhibitor", "KRAS G12C inhibitor", "CD20 antagonist"

Return ONLY a JSON object with this exact format:
{{
    "target": "molecular target here",
    "moa_category": "mechanism category here"
}}

If you cannot determine either field, use null for that field.
Do not include any explanation, only the JSON object."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = response.content[0].text.strip()
            
            # Parse JSON response
            import json
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            result = json.loads(response_text)
            
            logger.info(f"Extracted target/MoA for {drug_name}: target={result.get('target')}, moa_category={result.get('moa_category')}")
            
            return {
                "target": result.get("target"),
                "moa_category": result.get("moa_category")
            }
            
        except Exception as e:
            logger.error(f"Error parsing target/MoA for {drug_name}: {e}")
            return {"target": None, "moa_category": None}

