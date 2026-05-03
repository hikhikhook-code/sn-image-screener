"""Tests for the provider model registry."""

from __future__ import annotations

from sn_image_screener.services.ai.models import (
    PROVIDER_MODELS, default_model_for, is_supported, models_for,
)
from sn_image_screener.services.ai.types import ProviderName


def test_every_provider_has_at_least_one_model():
    for provider in ProviderName:
        models = models_for(provider)
        assert models, f"no models registered for {provider}"
        assert all(m.id for m in models)


def test_every_provider_has_exactly_one_recommended():
    for provider in ProviderName:
        models = models_for(provider)
        recs = [m for m in models if m.recommended]
        assert len(recs) == 1, (
            f"expected exactly one recommended model for {provider}, "
            f"found {[m.id for m in recs]}"
        )


def test_default_model_matches_recommended_flag():
    for provider in ProviderName:
        default = default_model_for(provider)
        rec = next(m for m in models_for(provider) if m.recommended)
        assert default == rec.id


def test_is_supported_recognises_registered_models():
    for provider in ProviderName:
        for opt in PROVIDER_MODELS[provider]:
            assert is_supported(provider, opt.id)


def test_is_supported_rejects_unknown_models():
    assert not is_supported(ProviderName.GEMINI, "totally-fake-model")
    assert not is_supported(ProviderName.OPENAI, "some-other-model")


def test_display_marks_recommended():
    rec = [m for m in models_for(ProviderName.GEMINI) if m.recommended][0]
    assert rec.display().endswith("(recommended)")
    other = [m for m in models_for(ProviderName.GEMINI) if not m.recommended][0]
    assert "(recommended)" not in other.display()


def test_display_marks_paid():
    """Paid-only models are tagged so users with free-tier keys avoid them."""
    paid = [
        m for m in models_for(ProviderName.GEMINI)
        if m.paid and not m.recommended
    ]
    assert paid, "expected at least one (paid) Gemini model"
    for opt in paid:
        assert opt.display().endswith("(paid)")


def test_recommended_takes_precedence_over_paid():
    """If a model is somehow both, the recommended tag wins on display."""
    from sn_image_screener.services.ai.models import ModelOption
    opt = ModelOption("foo", recommended=True, paid=True)
    assert opt.display().endswith("(recommended)")
    assert "(paid)" not in opt.display()
