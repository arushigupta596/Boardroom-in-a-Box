"""
LLM Client - OpenRouter Integration
====================================
Provides LLM capabilities via OpenRouter API.
Supports multiple models with fallback.
"""

import os
import json
import httpx
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


class LLMModel(Enum):
    """Available models via OpenRouter."""
    CLAUDE_SONNET = "anthropic/claude-sonnet-4"
    CLAUDE_HAIKU = "anthropic/claude-3-5-haiku"
    GPT4O_MINI = "openai/gpt-4o-mini"
    LLAMA_70B = "meta-llama/llama-3.1-70b-instruct"
    LLAMA_8B_FREE = "meta-llama/llama-3.1-8b-instruct:free"


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str
    model: str
    usage: Dict[str, int]
    raw: Dict[str, Any]


class LLMClient:
    """
    OpenRouter LLM Client.

    Usage:
        client = LLMClient()
        response = client.complete("What is 2+2?")
        print(response.content)
    """

    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[LLMModel] = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key required. Set OPENROUTER_API_KEY environment variable "
                "or pass api_key parameter."
            )

        # Allow model to be set via environment variable
        if default_model is None:
            model_str = os.environ.get("OPENROUTER_MODEL")
            if model_str:
                # Try to find matching enum value
                for model_enum in LLMModel:
                    if model_enum.value == model_str:
                        default_model = model_enum
                        break
                else:
                    # Model string not found in enum, use CLAUDE_HAIKU as fallback
                    default_model = LLMModel.CLAUDE_HAIKU
            else:
                default_model = LLMModel.CLAUDE_HAIKU

        self.default_model = default_model
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[LLMModel] = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Send a completion request to OpenRouter.

        Args:
            prompt: User message/prompt
            system: Optional system message
            model: Model to use (defaults to default_model)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response
            json_mode: If True, request JSON response format

        Returns:
            LLMResponse with content and metadata
        """
        model = model or self.default_model

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model.value,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://boardroom-in-a-box.local",
            "X-Title": "Boardroom-in-a-Box",
        }

        response = self.client.post(
            self.OPENROUTER_URL,
            json=payload,
            headers=headers,
        )
        response.raise_for_status()

        data = response.json()

        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", model.value),
            usage=data.get("usage", {}),
            raw=data,
        )

    def complete_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[LLMModel] = None,
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Send a completion request expecting JSON response.

        Returns:
            Parsed JSON dictionary
        """
        response = self.complete(
            prompt=prompt,
            system=system,
            model=model,
            temperature=temperature,
            json_mode=True,
        )

        # Parse JSON from response
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content.strip())

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# Singleton instance for convenience
_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create the global LLM client."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def set_llm_client(client: LLMClient):
    """Set a custom LLM client."""
    global _client
    _client = client
