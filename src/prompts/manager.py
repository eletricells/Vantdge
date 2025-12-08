"""
Prompt Manager for loading and rendering Jinja2 templates.

Simplified implementation focused on:
- Template loading from files
- Variable substitution with Jinja2
- Caching for performance
- Basic validation
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import json
import logging

try:
    from jinja2 import Environment, FileSystemLoader, TemplateNotFound
except ImportError:
    raise ImportError(
        "Jinja2 is required for prompt management. Install with: pip install jinja2"
    )

logger = logging.getLogger(__name__)


class PromptManager:
    """
    Manages prompt templates with Jinja2 rendering.

    Features:
    - Template loading from files
    - Variable substitution
    - Partial template inclusion
    - Caching for performance

    Example:
        manager = PromptManager()
        prompt = manager.render(
            "clinical_extraction/stage2_demographics",
            arm_name="Upadacitinib 30mg",
            n=180,
            tables=["Table 1", "Table 2"],
        )
    """

    def __init__(
        self,
        templates_dir: Optional[Path] = None,
        cache_enabled: bool = True,
    ):
        """
        Initialize the PromptManager.

        Args:
            templates_dir: Path to templates directory
            cache_enabled: Cache rendered templates
        """
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"

        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        self._register_filters()
        self._cache: Dict[str, str] = {} if cache_enabled else None

    def render(
        self,
        template_name: str,
        **variables
    ) -> str:
        """
        Render a prompt template with variables.

        Args:
            template_name: Template path relative to templates_dir (without .j2)
            **variables: Template variables

        Returns:
            Rendered prompt string

        Raises:
            TemplateNotFound: If template doesn't exist
        """
        if not template_name.endswith('.j2'):
            template_name = f"{template_name}.j2"

        # For caching, convert variables to a hashable representation
        # Use JSON serialization for complex nested structures
        try:
            import json
            cache_key = f"{template_name}:{hash(json.dumps(variables, sort_keys=True, default=str))}"
        except (TypeError, ValueError):
            # If serialization fails, skip caching for this call
            cache_key = None

        if cache_key and self._cache is not None and cache_key in self._cache:
            logger.debug(f"Using cached prompt: {template_name}")
            return self._cache[cache_key]

        try:
            template = self.env.get_template(template_name)
            rendered = template.render(**variables)

            if cache_key and self._cache is not None:
                self._cache[cache_key] = rendered

            logger.debug(f"Rendered prompt: {template_name}")
            return rendered

        except TemplateNotFound:
            logger.error(f"Template not found: {template_name}")
            raise
        except Exception as e:
            logger.error(f"Error rendering template {template_name}: {e}")
            raise

    def list_templates(self, category: Optional[str] = None) -> List[str]:
        """
        List available templates.

        Args:
            category: Optional category filter (e.g., "clinical_extraction")

        Returns:
            List of template names
        """
        templates = []

        search_path = self.templates_dir
        if category:
            search_path = search_path / category

        if not search_path.exists():
            return []

        for path in search_path.rglob("*.j2"):
            if "_partials" not in str(path):
                rel_path = path.relative_to(self.templates_dir)
                templates.append(str(rel_path).replace(".j2", "").replace("\\", "/"))

        return sorted(templates)

    def clear_cache(self):
        """Clear the template cache."""
        if self._cache is not None:
            self._cache.clear()
            logger.debug("Cleared prompt cache")

    def _register_filters(self):
        """Register custom Jinja2 filters."""

        def join_list(items: List[Any], separator: str = ", ") -> str:
            return separator.join(str(item) for item in items)

        def to_json(obj: Any, indent: int = 2) -> str:
            return json.dumps(obj, indent=indent)

        def truncate(text: str, length: int, suffix: str = "...") -> str:
            if len(text) <= length:
                return text
            return text[:length - len(suffix)] + suffix

        def format_tables(tables: List[Dict], max_length: int = 10000) -> str:
            formatted = []
            total_length = 0

            for table in tables:
                content = table.get('content', '')
                label = table.get('label', 'Unknown')

                table_text = f"\n{'='*80}\n{label.upper()}\n{'='*80}\n{content}\n"

                if total_length + len(table_text) > max_length:
                    formatted.append(f"\n... (truncated, {len(tables) - len(formatted)} more tables)")
                    break

                formatted.append(table_text)
                total_length += len(table_text)

            return "\n".join(formatted)

        self.env.filters['join_list'] = join_list
        self.env.filters['to_json'] = to_json
        self.env.filters['truncate'] = truncate
        self.env.filters['format_tables'] = format_tables


# Singleton instance for convenience
_default_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """Get the default PromptManager instance."""
    global _default_manager
    if _default_manager is None:
        _default_manager = PromptManager()
    return _default_manager

