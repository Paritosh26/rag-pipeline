from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstraction for LLM providers so the answer layer remains provider-agnostic."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate a response from the provided prompt."""


class GeminiProvider(LLMProvider):
    """Gemini-backed LLM provider used by the default application configuration."""

    def __init__(self, model_name: str, api_key: str) -> None:
        from google import genai

        self.model_name = model_name
        self._client = genai.Client(api_key=api_key)

    def generate(self, prompt: str) -> str:
        response = self._client.models.generate_content(model=self.model_name, contents=prompt)
        text = response.text
        if not text:
            # A blocked/empty candidate yields text=None; raising lets the
            # answer layer fall back instead of returning a null answer.
            raise RuntimeError(f'Gemini model {self.model_name} returned no text for the prompt')
        return text
