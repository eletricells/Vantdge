"""
Base agent class for all specialist agents in the Vantdge platform.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from anthropic import Anthropic
import logging
import time


class BaseAgent(ABC):
    """
    Abstract base class for all specialist agents.

    Each agent specializes in a specific domain (clinical, commercial, etc.)
    and provides structured analysis with confidence scores and citations.
    """

    def __init__(
        self,
        client: Anthropic,
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 4000
    ):
        """
        Initialize the base agent.

        Args:
            client: Anthropic API client
            model: Claude model to use
            max_tokens: Maximum tokens for responses
        """
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main analysis method - must be implemented by each specialist agent.

        Args:
            state: Current workflow state containing target, indication, etc.

        Returns:
            Dictionary containing analysis results with confidence scores and citations
        """
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Return agent-specific system prompt.

        Returns:
            System prompt string defining agent's role and instructions
        """
        pass

    def _call_claude(
        self,
        prompt: str,
        system: Optional[str] = None,
        tools: Optional[list] = None,
        max_retries: int = 3,
        enable_caching: bool = False
    ) -> Any:
        """
        Shared Claude API call logic with retry on transient errors.

        Args:
            prompt: User prompt/question
            system: System prompt (uses get_system_prompt() if not provided)
            tools: Optional list of tool definitions for tool use
            max_retries: Maximum number of retries for transient errors
            enable_caching: Whether to enable prompt caching for system message

        Returns:
            Claude API response
        """
        if system is None:
            system = self.get_system_prompt()

        last_error = None
        for attempt in range(max_retries):
            try:
                api_params = {
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                    "tools": tools or []
                }

                if system:
                    if enable_caching:
                        api_params["system"] = [
                            {
                                "type": "text",
                                "text": system,
                                "cache_control": {"type": "ephemeral"}
                            }
                        ]
                    else:
                        api_params["system"] = system

                response = self.client.messages.create(**api_params)
                return response
            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                is_transient = any(keyword in error_str for keyword in [
                    'overloaded', 'rate limit', 'timeout', '429', '500', '502', '503', '504'
                ])

                if is_transient and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 2
                    self.logger.warning(
                        f"Transient API error (attempt {attempt + 1}/{max_retries}): {str(e)}. "
                        f"Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"Claude API call failed: {str(e)}")
                    raise

        self.logger.error(f"Claude API call failed after {max_retries} retries: {str(last_error)}")
        raise last_error

    def _extract_text_response(self, response: Any) -> str:
        """
        Extract text content from Claude response.

        Args:
            response: Claude API response

        Returns:
            Text content from response
        """
        if hasattr(response, 'content') and len(response.content) > 0:
            text_blocks = [
                block.text for block in response.content
                if hasattr(block, 'text')
            ]
            return '\n'.join(text_blocks)
        return ""

    def _handle_tool_use(
        self,
        response: Any,
        tool_executor: callable,
        prompt: str,
        max_iterations: int = 5
    ) -> Any:
        """
        Handle tool use in agentic loop.

        Args:
            response: Initial Claude response
            tool_executor: Function to execute tools (takes tool name and input)
            prompt: Original prompt
            max_iterations: Maximum tool use iterations

        Returns:
            Final Claude response after all tool uses
        """
        messages = [{"role": "user", "content": prompt}]
        current_response = response
        iteration = 0

        while (
            hasattr(current_response, 'stop_reason') and
            current_response.stop_reason == "tool_use" and
            iteration < max_iterations
        ):
            iteration += 1
            self.logger.info(f"Tool use iteration {iteration}")

            messages.append({
                "role": "assistant",
                "content": current_response.content
            })

            tool_results = []
            for block in current_response.content:
                if hasattr(block, 'type') and block.type == "tool_use":
                    self.logger.info(f"Executing tool: {block.name}")
                    try:
                        result = tool_executor(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })
                    except Exception as e:
                        self.logger.error(f"Tool execution failed: {str(e)}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {str(e)}",
                            "is_error": True
                        })

            messages.append({
                "role": "user",
                "content": tool_results
            })

            current_response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.get_system_prompt(),
                messages=messages
            )

        return current_response

