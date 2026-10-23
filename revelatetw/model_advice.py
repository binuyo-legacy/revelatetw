"""Whisper model choice and Yoruba advisory logic. Pure functions, headless-safe (no Qt).

Large models need a powerful PC; choosing one shows a warning the operator can cancel.
The Yoruba advisory is shown once per install; dismissal is saved in settings.
"""
from __future__ import annotations

LARGE_MODELS = ("large", "large-v3")
MODEL_CHOICES = ("tiny", "base", "small", "medium", "large", "large-v3")

LARGE_MODEL_WARNING = (
    "The large model needs a powerful PC (16GB+ RAM recommended). "
    "If your PC struggles, switch back to the smaller model."
)
YORUBA_ADVISORY = (
    "Yoruba live detection is experimental. For best results use the large-v3 model in "
    "Settings > Transcription, or use manual verse mode."
)


def is_large_model(model_size: str) -> bool:
    return str(model_size or "").strip().lower() in LARGE_MODELS


def needs_large_model_warning(previous: str, chosen: str) -> bool:
    """True when the operator picks a large model (and it is not already the one in use)."""
    return is_large_model(chosen) and str(chosen).strip().lower() != str(previous or "").strip().lower()


def is_yoruba(translation_id: str) -> bool:
    return str(translation_id or "").strip().lower() in ("yo", "yoruba")


def should_show_yoruba_advisory(translation_id: str, live_detection_on: bool, dismissed: bool) -> bool:
    return bool(live_detection_on) and is_yoruba(translation_id) and not dismissed
