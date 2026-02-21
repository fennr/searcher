"""Prompt assembly primitives."""

from searcher.config import PREFERRED_TOOL_MAP
from searcher.models.contracts import Capabilities, ToolPolicy


def format_capabilities_block(
    capabilities: Capabilities, tool_policy: ToolPolicy
) -> str:
    """Serialize environment capabilities into prompt-friendly text."""
    modern = capabilities["modern_available"] or ["none"]
    baseline = capabilities["baseline_available"] or ["none"]
    dev_tools = capabilities["dev_tools_available"] or ["none"]
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
        f"Available domain dev tools: {', '.join(dev_tools)}\n"
        f"Available modern tools: {', '.join(modern)}\n"
        f"Available baseline tools: {', '.join(baseline)}\n"
        f"Preferred mapping: {', '.join(mapping_parts)}\n"
        "Important: modern/baseline lists describe known replacement policy only; "
        "they do not limit which shell commands are allowed.\n"
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
            "Сначала выбери наиболее релевантный доменный инструмент по смыслу запроса "
            "(например: docker/podman для контейнеров, git для VCS, systemctl/journalctl для сервисов, "
            "kubectl для Kubernetes, npm/yarn/pnpm для Node.js). "
            "Не подменяй такие запросы общими файловыми командами (`cat`, `find`, `ls`), если доменный инструмент уместен. "
            "Если пользователь просит найти текст/строку/слово в файлах проекта, предлагай поиск по содержимому: "
            "в приоритете `rg`, иначе `grep`; по умолчанию по текущей директории `.` и от корня пользовательской папки. "
            "Нужны 1-3 наиболее вероятные и практичные команды для оболочки. "
            "Дай короткое объяснение (1-3 пункта), затем выведи ровно один блок ```bash``` "
            "с 1-3 командами, по одной на строку, без нумерации внутри блока. "
            "Не добавляй других блоков кода.\n\n"
            f"{block}"
        )
    return (
        "Ты помощник по терминалу macOS. Отвечай на русском языке. "
        "Верни только одну наиболее подходящую shell-команду без пояснений и без форматирования. "
        "Строго одна строка, без обратных кавычек, без префиксов и без русских слов.\n\n"
        f"{block}"
    )
