"""
MeSH (Medical Subject Headings) API Client

Client for standardizing disease names using NLM's MeSH database.
"""

import logging
from typing import Dict, List, Optional, Any

from src.drug_extraction_system.api_clients.base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class MeSHClient(BaseAPIClient):
    """
    Client for NLM MeSH API.
    
    Free API with no authentication required.
    Rate limit: ~50 requests/minute (conservative estimate)
    """

    BASE_URL = "https://id.nlm.nih.gov/mesh"

    def __init__(self):
        """Initialize MeSH client."""
        super().__init__(
            base_url=self.BASE_URL,
            rate_limit=50,
            name="MeSH"
        )

    def search_term(self, term: str, limit: int = 10) -> Optional[List[Dict]]:
        """
        Search MeSH for a term.

        Args:
            term: Term to search (e.g., disease name)
            limit: Max results to return

        Returns:
            List of matching MeSH concepts or None
        """
        # Try the MeSH lookup API first (more reliable)
        lookup_result = self._search_via_lookup(term, limit)
        if lookup_result:
            return lookup_result

        # Fall back to SPARQL search
        # Escape special characters in term
        safe_term = term.replace('"', '\\"').replace("'", "\\'")

        sparql_query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>

        SELECT ?descriptor ?label ?scopeNote
        WHERE {{
            ?descriptor a meshv:Descriptor .
            ?descriptor rdfs:label ?label .
            OPTIONAL {{ ?descriptor meshv:scopeNote ?scopeNote }}
            FILTER(CONTAINS(LCASE(STR(?label)), LCASE("{safe_term}")))
        }}
        LIMIT {limit}
        """

        result = self.get("/sparql", params={
            "query": sparql_query,
            "format": "json"
        })

        if result and "results" in result:
            bindings = result["results"].get("bindings", [])
            concepts = []
            for binding in bindings:
                concepts.append({
                    "mesh_id": self._extract_mesh_id(binding.get("descriptor", {}).get("value")),
                    "label": binding.get("label", {}).get("value"),
                    "scope_note": binding.get("scopeNote", {}).get("value"),
                })
            return concepts if concepts else None

        return None

    def _search_via_lookup(self, term: str, limit: int = 10) -> Optional[List[Dict]]:
        """
        Search MeSH using the lookup API.

        The lookup API is more reliable for free-text searches.
        """
        import requests

        try:
            # Use the NLM MeSH lookup API
            url = "https://id.nlm.nih.gov/mesh/lookup/descriptor"
            params = {
                "label": term,
                "match": "contains",
                "limit": limit
            }

            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                return None

            data = response.json()
            if not data:
                return None

            concepts = []
            for item in data[:limit]:
                # Extract MeSH ID from resource URI
                resource = item.get("resource", "")
                mesh_id = resource.split("/")[-1] if resource else None

                concepts.append({
                    "mesh_id": mesh_id,
                    "label": item.get("label"),
                    "scope_note": None,
                })

            return concepts if concepts else None

        except Exception as e:
            logger.debug(f"MeSH lookup API error: {e}")
            return None

    def get_descriptor(self, mesh_id: str) -> Optional[Dict]:
        """
        Get MeSH descriptor by ID.

        Args:
            mesh_id: MeSH descriptor ID (e.g., "D003920" for Diabetes Mellitus)

        Returns:
            Descriptor data or None
        """
        # Normalize ID format
        if not mesh_id.startswith("D"):
            mesh_id = f"D{mesh_id}"

        result = self.get(f"/{mesh_id}.json")

        if result:
            return {
                "mesh_id": mesh_id,
                "label": result.get("label", {}).get("@value"),
                "scope_note": result.get("scopeNote", {}).get("@value") if result.get("scopeNote") else None,
                "tree_numbers": result.get("treeNumber", []),
            }

        return None

    def standardize_disease_name(self, disease_name: str) -> Optional[Dict[str, str]]:
        """
        Standardize a disease name using MeSH.

        Args:
            disease_name: Disease name to standardize

        Returns:
            Dictionary with mesh_id and standardized name, or None
        """
        results = self.search_term(disease_name, limit=5)

        if results:
            # Return best match (first result)
            best_match = results[0]
            return {
                "mesh_id": best_match["mesh_id"],
                "standardized_name": best_match["label"],
                "original_name": disease_name,
            }

        logger.debug(f"No MeSH match found for '{disease_name}'")
        return None

    def get_related_terms(self, mesh_id: str) -> List[Dict]:
        """
        Get related terms for a MeSH descriptor.

        Args:
            mesh_id: MeSH descriptor ID

        Returns:
            List of related terms
        """
        sparql_query = f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX meshv: <http://id.nlm.nih.gov/mesh/vocab#>

        SELECT ?related ?label
        WHERE {{
            <http://id.nlm.nih.gov/mesh/{mesh_id}> meshv:seeAlso ?related .
            ?related rdfs:label ?label .
        }}
        LIMIT 20
        """

        result = self.get("/sparql", params={
            "query": sparql_query,
            "format": "json"
        })

        if result and "results" in result:
            bindings = result["results"].get("bindings", [])
            related = []
            for binding in bindings:
                related.append({
                    "mesh_id": self._extract_mesh_id(binding.get("related", {}).get("value")),
                    "label": binding.get("label", {}).get("value"),
                })
            return related

        return []

    def get_synonyms(self, mesh_id: str) -> List[str]:
        """
        Get all synonyms (entry terms) for a MeSH descriptor.

        Entry terms are alternative names used to find this concept.
        For example, "Dermatitis, Atopic" has entry terms like
        "Atopic Dermatitis", "Atopic Eczema", "Eczema, Atopic", etc.

        Args:
            mesh_id: MeSH descriptor ID (e.g., "D003876")

        Returns:
            List of synonym strings including the preferred label
        """
        # Normalize ID format
        if not mesh_id.startswith("D"):
            mesh_id = f"D{mesh_id}"

        synonyms = set()

        # Try to get from JSON API which has complete term data
        try:
            result = self.get(f"/{mesh_id}.json")

            if result:
                # Add preferred label
                label = result.get("label", {})
                if isinstance(label, dict):
                    synonyms.add(label.get("@value", ""))
                elif isinstance(label, str):
                    synonyms.add(label)

                # Add entry terms from concepts
                concepts = result.get("concept", [])
                if not isinstance(concepts, list):
                    concepts = [concepts]

                for concept in concepts:
                    # Get terms from each concept
                    terms = concept.get("term", [])
                    if not isinstance(terms, list):
                        terms = [terms]

                    for term in terms:
                        if isinstance(term, dict):
                            term_label = term.get("label", {})
                            if isinstance(term_label, dict):
                                synonyms.add(term_label.get("@value", ""))
                            elif isinstance(term_label, str):
                                synonyms.add(term_label)
                        elif isinstance(term, str):
                            synonyms.add(term)

        except Exception as e:
            logger.debug(f"Error getting MeSH synonyms: {e}")

        # Remove empty strings
        synonyms.discard("")

        # Generate common variations (MeSH uses inverted form like "Dermatitis, Atopic")
        variations = set()
        for syn in list(synonyms):
            variations.add(syn)
            # If it's in "X, Y" format, also add "Y X" format
            if ", " in syn:
                parts = syn.split(", ", 1)
                if len(parts) == 2:
                    variations.add(f"{parts[1]} {parts[0]}")
            # If it's in "X Y" format, also add "Y, X" format
            elif " " in syn:
                words = syn.split(" ", 1)
                if len(words) == 2:
                    variations.add(f"{words[1]}, {words[0]}")

        return list(variations)

    def get_disease_search_terms(self, disease_name: str) -> Dict[str, Any]:
        """
        Get standardized name and all search terms for a disease.

        Returns the MeSH preferred term, synonyms, and original name
        for comprehensive searching.

        Args:
            disease_name: Disease name to standardize

        Returns:
            Dictionary with mesh_id, preferred_name, and search_terms list
        """
        # First try exact standardization
        standard = self.standardize_disease_name(disease_name)

        # If no match, try searching with individual words
        if not standard:
            words = disease_name.split()
            for word in words:
                if len(word) > 3:  # Skip short words
                    results = self.search_term(word, limit=5)
                    if results:
                        # Look for a result that matches the full disease name
                        for r in results:
                            label = r.get("label", "").lower()
                            if all(w.lower() in label for w in words):
                                standard = {
                                    "mesh_id": r["mesh_id"],
                                    "standardized_name": r["label"],
                                    "original_name": disease_name,
                                }
                                break
                    if standard:
                        break

        if not standard:
            # No MeSH match - return original as only search term
            logger.info(f"No MeSH match for '{disease_name}', using original term only")
            return {
                "mesh_id": None,
                "preferred_name": disease_name,
                "search_terms": [disease_name.lower()],
            }

        mesh_id = standard["mesh_id"]
        preferred_name = standard["standardized_name"]

        # Get all synonyms
        synonyms = self.get_synonyms(mesh_id)

        # Build comprehensive search term list
        search_terms = set()
        search_terms.add(disease_name.lower())
        search_terms.add(preferred_name.lower())
        for syn in synonyms:
            search_terms.add(syn.lower())

        logger.info(f"MeSH standardized '{disease_name}' -> '{preferred_name}' ({mesh_id}) with {len(search_terms)} search terms")

        return {
            "mesh_id": mesh_id,
            "preferred_name": preferred_name,
            "search_terms": list(search_terms),
        }

    def _extract_mesh_id(self, uri: Optional[str]) -> Optional[str]:
        """Extract MeSH ID from URI."""
        if not uri:
            return None
        # URI format: http://id.nlm.nih.gov/mesh/D003920
        parts = uri.split("/")
        return parts[-1] if parts else None

    def health_check(self) -> bool:
        """Check if MeSH API is accessible."""
        try:
            # Try to get a known descriptor
            result = self.get_descriptor("D003920")  # Diabetes Mellitus
            return result is not None
        except Exception:
            return False

