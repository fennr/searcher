"""Compatibility facade for prompt core layer."""

from searcher.core.prompts import build_system_prompt as system_prompt
from searcher.core.prompts import format_capabilities_block

__all__ = ["format_capabilities_block", "system_prompt"]
