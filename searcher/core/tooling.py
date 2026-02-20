"""Tool detection and capability-building logic."""

import os
import platform
import shutil

from searcher.config import BASELINE_TOOLS, MODERN_TOOLS
from searcher.models.contracts import Capabilities

_tools_cache: dict[str, bool] | None = None


def reset_tools_cache() -> None:
    """Reset in-process cache for tool detection."""
    global _tools_cache
    _tools_cache = None


def detect_tools(force_refresh: bool = False) -> dict[str, bool]:
    """Detect available tools via PATH lookup."""
    global _tools_cache
    if _tools_cache is not None and not force_refresh:
        return dict(_tools_cache)
    detected: dict[str, bool] = {}
    for name in (*MODERN_TOOLS, *BASELINE_TOOLS):
        detected[name] = shutil.which(name) is not None
    _tools_cache = detected
    return dict(detected)


def build_capabilities() -> Capabilities:
    """Build full capabilities object from environment."""
    tools = detect_tools()
    modern_available = [name for name in MODERN_TOOLS if tools.get(name, False)]
    baseline_available = [name for name in BASELINE_TOOLS if tools.get(name, False)]
    shell_raw = os.environ.get("SHELL", "").strip()
    shell_name = os.path.basename(shell_raw) if shell_raw else "unknown"
    return {
        "tools": tools,
        "modern_available": modern_available,
        "baseline_available": baseline_available,
        "os_name": platform.system(),
        "shell_name": shell_name,
    }
