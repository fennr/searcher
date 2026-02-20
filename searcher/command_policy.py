"""Compatibility facade for command policy core layer."""

from searcher.core.command_policy import (
    STRICT_MISSING_SENTINEL,
    check_tool_policy,
    clean_single_line,
    coerce_command,
    extract_first_tool,
    looks_like_command,
)

__all__ = [
    "STRICT_MISSING_SENTINEL",
    "check_tool_policy",
    "clean_single_line",
    "coerce_command",
    "extract_first_tool",
    "looks_like_command",
]
