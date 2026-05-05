"""Core translation logic: one call per (image, language) pair."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openai import OpenAI


DEFAULT_MODEL = "gpt-image-2"
DEFAULT_QUALITY = "high"
DEFAULT_SIZE = "auto"

PROMPT_TEMPLATE = (
    "Translate every piece of visible text in this screenshot into {language}. "
    "Preserve the original layout, fonts, font sizes, colors, alignment, "
    "spacing, icons, backgrounds, and all non-text visual elements exactly. "
    "Do not add, remove, or rearrange any UI elements. Do not change colors "
    "or styling. Only the text strings change to natural, idiomatic {language}. "
    "Keep brand names, code identifiers, file paths, URLs, and numeric values "
    "unchanged. If a string would not fit in its original space after "
    "translation, keep the visual layout intact and shorten the translation "
    "naturally rather than overflowing."
)


@dataclass
class TranslateResult:
    source: Path
    language: str
    output: Path
    bytes_written: int


def build_prompt(language: str, extra: Optional[str] = None) -> str:
    prompt = PROMPT_TEMPLATE.format(language=language)
    if extra:
        prompt = f"{prompt}\n\nAdditional instructions: {extra.strip()}"
    return prompt


def translate_screenshot(
    source: Path,
    language: str,
    output: Path,
    *,
    client: Optional[OpenAI] = None,
    model: str = DEFAULT_MODEL,
    quality: str = DEFAULT_QUALITY,
    size: str = DEFAULT_SIZE,
    prompt_extra: Optional[str] = None,
) -> TranslateResult:
    """Translate one screenshot to one language and write the result to `output`.

    The OpenAI client is created lazily if not supplied. `OPENAI_API_KEY` from
    the environment is used by default; set it before calling.
    """
    if client is None:
        client = OpenAI()

    prompt = build_prompt(language, prompt_extra)

    edit_kwargs = {
        "model": model,
        "image": open(source, "rb"),
        "prompt": prompt,
    }
    if quality and quality != "auto":
        edit_kwargs["quality"] = quality
    if size and size != "auto":
        edit_kwargs["size"] = size

    try:
        response = client.images.edit(**edit_kwargs)
    finally:
        edit_kwargs["image"].close()

    b64 = response.data[0].b64_json
    if not b64:
        raise RuntimeError(
            "OpenAI returned no b64_json payload. "
            "The model may have refused the edit; try a different image."
        )

    image_bytes = base64.b64decode(b64)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image_bytes)

    return TranslateResult(
        source=source,
        language=language,
        output=output,
        bytes_written=len(image_bytes),
    )
