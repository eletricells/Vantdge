"""
LLM Client Protocol

Defines the interface for LLM interactions, allowing different
implementations (Anthropic, OpenAI, etc.) to be swapped easily.
"""

from typing import Protocol, Optional, Dict, Any, List


class LLMClient(Protocol):
    """Protocol for LLM client implementations."""

    async def complete(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.0,
        system: Optional[str] = None,
        cache_system: bool = False,
    ) -> str:
        """
        Generate a completion for the given prompt.

        Args:
            prompt: The user prompt to complete
            max_tokens: Maximum tokens in the response
            temperature: Sampling temperature (0.0 = deterministic)
            system: Optional system prompt
            cache_system: If True, enable prompt caching for system prompt

        Returns:
            The generated text response
        """
        ...

    async def complete_with_thinking(
        self,
        prompt: str,
        thinking_budget: int = 3000,
        max_tokens: int = 8000,
        temperature: float = 1.0,
        system: Optional[str] = None,
        cache_system: bool = False,
    ) -> tuple[str, Optional[str]]:
        """
        Generate a completion with extended thinking enabled.

        Args:
            prompt: The user prompt to complete
            thinking_budget: Token budget for thinking
            max_tokens: Maximum tokens in the response (must be > thinking_budget)
            temperature: Must be 1.0 for extended thinking
            system: Optional system prompt
            cache_system: If True, enable prompt caching for system prompt

        Returns:
            Tuple of (response_text, thinking_text)
        """
        ...

    def count_tokens(self, text: str) -> int:
        """
        Count the number of tokens in the given text.

        Args:
            text: The text to count tokens for

        Returns:
            The token count
        """
        ...

    def get_usage_stats(self) -> Dict[str, int]:
        """
        Get cumulative token usage statistics.

        Returns:
            Dict with keys: input_tokens, output_tokens, thinking_tokens,
            cache_creation_tokens, cache_read_tokens
        """
        ...

    def reset_usage_stats(self) -> None:
        """Reset the token usage statistics."""
        ...
