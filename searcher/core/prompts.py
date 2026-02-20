"""Prompt assembly primitives."""

from searcher.config import PREFERRED_TOOL_MAP
from searcher.models.contracts import Capabilities, ToolPolicy


def format_capabilities_block(
    capabilities: Capabilities, tool_policy: ToolPolicy
) -> str:
    """Serialize environment capabilities into prompt-friendly text."""
    modern = capabilities["modern_available"] or ["none"]
    baseline = capabilities["baseline_available"] or ["none"]
    mapping_parts: list[str] = []
    for base, modern_tool in PREFERRED_TOOL_MAP.items():
        suffix = (
            modern_tool
            if capabilities["tools"].get(modern_tool, False)
            else f"{modern_tool}(missing)"
        )
        mapping_parts.append(f"{base}->{suffix}")
    policy_text = (
        "Prefer modern tools if available; fallback to baseline tools when modern tools are missing."
        if tool_policy == "prefer"
        else "Strict modern policy: use modern tools for mapped commands; if modern tool is missing, do not invent replacements."
    )
    return (
        f"Environment: OS={capabilities['os_name']}; shell={capabilities['shell_name']}\n"
        f"Available modern tools: {', '.join(modern)}\n"
        f"Available baseline tools: {', '.join(baseline)}\n"
        f"Preferred mapping: {', '.join(mapping_parts)}\n"
        f"Policy: {policy_text}"
    )


def build_system_prompt(
    reasoning: bool, capabilities: Capabilities, tool_policy: ToolPolicy
) -> str:
    """Build system prompt for command or reasoning mode."""
    block = format_capabilities_block(capabilities, tool_policy)
    if reasoning:
        return (
            "Ты помощник по терминалу macOS. Отвечай на русском языке. "
            "Дай краткое объяснение и предложи несколько подходящих команд с комментариями.\n\n"
            f"{block}"
        )
    return (
        "Ты помощник по терминалу macOS. Отвечай на русском языке. "
        "Верни только одну наиболее подходящую shell-команду без пояснений и без форматирования. "
        "Строго одна строка, без обратных кавычек, без префиксов и без русских слов.\n\n"
        f"{block}"
    )
