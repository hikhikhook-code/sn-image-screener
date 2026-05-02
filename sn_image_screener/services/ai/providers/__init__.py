"""Concrete AI vision providers."""

from .base import Provider, parse_json_loose
from .gemini_provider import GeminiProvider
from .groq_provider import GroqProvider
from .openai_provider import OpenAIProvider

from ..types import ProviderName


def provider_for(name: ProviderName) -> Provider:
    """Return a fresh provider instance for the given enum value."""
    return {
        ProviderName.GEMINI: GeminiProvider(),
        ProviderName.OPENAI: OpenAIProvider(),
        ProviderName.GROQ: GroqProvider(),
    }[name]


__all__ = [
    "Provider", "GeminiProvider", "OpenAIProvider", "GroqProvider",
    "parse_json_loose", "provider_for",
]
