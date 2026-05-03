"""Provider-supported model registry.

The Settings UI reads this to populate the model dropdown for each
provider — users pick from a known-good list rather than typing
arbitrary model names. The recommended/default model per provider is
marked so the dropdown can render it as ``"<id> (recommended)"``.

Keep this list conservative — only multi-modal (vision) capable models
that the existing provider HTTP wrappers know how to call. New options
can be added freely; users with old keys that reference a removed
model will still load (the saved value is appended back into the
dropdown so they can re-select or change it).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .types import ProviderName


@dataclass(frozen=True)
class ModelOption:
    """A single supported model for a provider."""

    id: str
    label: str = ""           # optional friendly label; falls back to ``id``
    recommended: bool = False

    def display(self) -> str:
        base = self.label or self.id
        return f"{base} (recommended)" if self.recommended else base


# ---------------------------------------------------------------------------
# Per-provider supported model lists. The order is the order the
# Settings dropdown will render. Exactly one option per provider is
# tagged ``recommended=True`` and will be picked as the default for new
# keys.
# ---------------------------------------------------------------------------

PROVIDER_MODELS: Dict[ProviderName, Tuple[ModelOption, ...]] = {
    ProviderName.GEMINI: (
        ModelOption("gemini-1.5-flash", recommended=True),
        ModelOption("gemini-1.5-flash-8b"),
        ModelOption("gemini-1.5-pro"),
        ModelOption("gemini-2.0-flash"),
        ModelOption("gemini-2.0-flash-exp"),
        ModelOption("gemini-2.5-flash"),
        ModelOption("gemini-2.5-pro"),
    ),
    ProviderName.OPENAI: (
        ModelOption("gpt-4o-mini", recommended=True),
        ModelOption("gpt-4o"),
        ModelOption("gpt-4.1-mini"),
        ModelOption("gpt-4.1"),
    ),
    ProviderName.GROQ: (
        ModelOption(
            "meta-llama/llama-4-scout-17b-16e-instruct", recommended=True,
        ),
        ModelOption("meta-llama/llama-4-maverick-17b-128e-instruct"),
        ModelOption("llama-3.2-11b-vision-preview"),
        ModelOption("llama-3.2-90b-vision-preview"),
    ),
}


def models_for(provider: ProviderName) -> List[ModelOption]:
    """Return the supported model list for ``provider`` (never empty)."""
    return list(PROVIDER_MODELS[provider])


def default_model_for(provider: ProviderName) -> str:
    """Return the recommended model id for ``provider``."""
    for opt in PROVIDER_MODELS[provider]:
        if opt.recommended:
            return opt.id
    # Fallback — first option if no recommended flag is set.
    return PROVIDER_MODELS[provider][0].id


def is_supported(provider: ProviderName, model: str) -> bool:
    """True iff ``model`` is one of the registered options for ``provider``."""
    return any(opt.id == model for opt in PROVIDER_MODELS[provider])


__all__ = [
    "ModelOption",
    "PROVIDER_MODELS",
    "models_for",
    "default_model_for",
    "is_supported",
]
