import sys
import types
from dataclasses import dataclass
from typing import Any

import pytest

from app.llm.gemini_provider import GeminiProvider, LLMProvider


@dataclass
class FakeResponse:
    text: str


class FakeModels:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, model: str, contents: str) -> FakeResponse:
        self.calls.append({'model': model, 'contents': contents})
        return FakeResponse(text='generated answer')


class FakeClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.models = FakeModels()


@pytest.fixture
def fake_genai(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    genai = types.ModuleType('google.genai')
    genai.Client = FakeClient  # type: ignore[attr-defined]
    google = types.ModuleType('google')
    google.genai = genai  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, 'google', google)
    monkeypatch.setitem(sys.modules, 'google.genai', genai)
    return genai


def test_provider_builds_a_client_with_the_api_key(fake_genai: types.ModuleType) -> None:
    provider = GeminiProvider(model_name='gemini-2.0-flash', api_key='fake-key')

    assert provider.model_name == 'gemini-2.0-flash'
    assert provider._client.api_key == 'fake-key'


def test_generate_returns_the_response_text(fake_genai: types.ModuleType) -> None:
    provider = GeminiProvider(model_name='gemini-2.0-flash', api_key='fake-key')

    answer = provider.generate('Why?')

    assert answer == 'generated answer'
    assert provider._client.models.calls == [{'model': 'gemini-2.0-flash', 'contents': 'Why?'}]


def test_llm_provider_cannot_be_instantiated_without_generate() -> None:
    with pytest.raises(TypeError):
        LLMProvider()  # type: ignore[abstract]
