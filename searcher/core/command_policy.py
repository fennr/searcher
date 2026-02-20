"""Command validation and policy enforcement."""

import os
import re
from typing import Protocol

from searcher.config import BASELINE_TOOLS, MODERN_TOOLS, PREFERRED_TOOL_MAP
from searcher.models.contracts import Capabilities, ToolPolicy

STRICT_MISSING_SENTINEL = "ERROR_STRICT_MISSING_TOOL"


class RepairCommandFn(Protocol):
    """Callable contract for command repair use case."""

    def __call__(
        self,
        *,
        query: str,
        model_id: str,
        capabilities: Capabilities,
        tool_policy: ToolPolicy,
        reason: str,
    ) -> str:
        """Return repaired command text."""


def clean_single_line(text: str) -> str:
    """Normalize model output to one command line."""
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()
    cleaned = cleaned.strip("`").strip()
    if "\n" in cleaned:
        cleaned = cleaned.splitlines()[0].strip()
    return cleaned


def looks_like_command(text: str) -> bool:
    """Check if text resembles a shell command."""
    if not text:
        return False
    if any(ord(ch) < 32 for ch in text):
        return False
    tool = extract_first_tool(text)
    if tool is None:
        return False
    return re.search(r"[A-Za-z0-9]", tool) is not None


def has_minimum_usefulness(command: str) -> bool:
    """Check that command is not a bare known utility without arguments."""
    stripped = command.strip()
    if " " in stripped or "\t" in stripped:
        return True
    tool = extract_first_tool(stripped)
    if tool is None:
        return False
    known_tools = set((*MODERN_TOOLS, *BASELINE_TOOLS))
    return tool not in known_tools


def extract_first_tool(command: str) -> str | None:
    """Extract executable token from command string."""
    match = re.match(
        r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]+\s+)*(?P<cmd>[A-Za-z0-9_./~-]+)", command
    )
    if match is None:
        return None
    return os.path.basename(match.group("cmd"))


def check_tool_policy(
    command: str, capabilities: Capabilities, tool_policy: ToolPolicy
) -> tuple[bool, str]:
    """Validate command against tool availability and selected policy."""
    tool = extract_first_tool(command)
    if tool is None:
        return False, "Команда не распознана: не найден основной исполняемый файл."
    known_tools = set((*MODERN_TOOLS, *BASELINE_TOOLS))
    if tool not in known_tools:
        return True, ""
    tools = capabilities["tools"]
    if tool in MODERN_TOOLS and not tools.get(tool, False):
        return False, f"Инструмент `{tool}` недоступен в системе."
    if tool_policy == "strict":
        for baseline, modern in PREFERRED_TOOL_MAP.items():
            if tool == baseline:
                if tools.get(modern, False):
                    return (
                        False,
                        f"В strict-режиме нужно использовать `{modern}` вместо `{baseline}`.",
                    )
                return (
                    False,
                    f"В strict-режиме требовался `{modern}`, но он не установлен.",
                )
    return True, ""


def _repair_if_needed(
    *,
    query: str,
    model_id: str,
    command: str,
    capabilities: Capabilities,
    tool_policy: ToolPolicy,
    reason: str,
    repair_fn: RepairCommandFn,
) -> str:
    """Call repair function and validate basic strict sentinel handling."""
    repaired = clean_single_line(
        repair_fn(
            query=query,
            model_id=model_id,
            capabilities=capabilities,
            tool_policy=tool_policy,
            reason=reason,
        )
    )
    if repaired == STRICT_MISSING_SENTINEL:
        raise RuntimeError(
            "Strict modern режим: для запроса требуется modern-инструмент, который не установлен."
        )
    if not looks_like_command(repaired):
        raise RuntimeError(
            "Модель не смогла вернуть корректную shell-команду. Попробуйте переформулировать запрос."
        )
    return repaired


def coerce_command(
    *,
    query: str,
    model_id: str,
    draft: str,
    capabilities: Capabilities,
    tool_policy: ToolPolicy,
    repair_command_fn: RepairCommandFn,
) -> str:
    """Coerce model output into command compatible with active policy."""
    command = clean_single_line(draft)
    if not looks_like_command(command):
        command = _repair_if_needed(
            query=query,
            model_id=model_id,
            command=command,
            capabilities=capabilities,
            tool_policy=tool_policy,
            reason="not a valid single-line shell command",
            repair_fn=repair_command_fn,
        )
    if not has_minimum_usefulness(command):
        command = _repair_if_needed(
            query=query,
            model_id=model_id,
            command=command,
            capabilities=capabilities,
            tool_policy=tool_policy,
            reason="command is too generic and lacks required arguments",
            repair_fn=repair_command_fn,
        )
    is_ok, reason = check_tool_policy(command, capabilities, tool_policy)
    if is_ok:
        return command
    command = _repair_if_needed(
        query=query,
        model_id=model_id,
        command=command,
        capabilities=capabilities,
        tool_policy=tool_policy,
        reason=reason,
        repair_fn=repair_command_fn,
    )
    is_ok, reason = check_tool_policy(command, capabilities, tool_policy)
    if is_ok:
        return command
    raise RuntimeError(
        reason or "Модель вернула команду, несовместимую с доступными утилитами."
    )
