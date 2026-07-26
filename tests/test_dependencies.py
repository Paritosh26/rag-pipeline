from app.config_util import Settings
from app.infrastructure.dependencies import _build_llm_provider
from app.llm.gemini_provider import GeminiProvider


def test_build_llm_provider_returns_none_when_llm_disabled() -> None:
    settings = Settings(llm_enabled=False, gemini_api_key='fake-key')

    provider = _build_llm_provider(settings)

    assert provider is None


def test_build_llm_provider_returns_none_without_api_key() -> None:
    settings = Settings(llm_enabled=True, gemini_api_key=None)

    provider = _build_llm_provider(settings)

    assert provider is None


def test_build_llm_provider_returns_gemini_when_enabled_with_key() -> None:
    settings = Settings(llm_enabled=True, gemini_api_key='fake-key', llm_provider='gemini')

    provider = _build_llm_provider(settings)

    assert isinstance(provider, GeminiProvider)
