"""Output clean-up that does not depend on the provider."""
from __future__ import annotations

import re

_CLOSED = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove the visible reasoning that some models (for example Qwen3) put in <think> tags.

    Handles a closed block, a closing tag with no opening tag (some servers split the template) and an opening
    tag that was never closed (the reply ran out of tokens while still thinking).
    """
    text = _CLOSED.sub("", text)
    lowered = text.lower()
    if "</think>" in lowered:
        text = text[lowered.rfind("</think>") + len("</think>"):]
        lowered = text.lower()
    opening = lowered.find("<think>")
    if opening != -1:
        text = text[:opening]
    return text.strip()
