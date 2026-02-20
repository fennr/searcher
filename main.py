import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request


BASE_URL = "http://127.0.0.1:1234"
MODELS_PATH = "/v1/models"
CHAT_PATH = "/v1/chat/completions"
MODERN_TOOLS = ("bat", "rg", "fd", "eza", "dust", "zoxide")
BASELINE_TOOLS = ("cat", "grep", "find", "ls", "du", "awk", "sed", "head", "tail", "sort")
PREFERRED_TOOL_MAP = {
    "cat": "bat",
    "grep": "rg",
    "find": "fd",
    "ls": "eza",
    "du": "dust",
}

_TOOLS_CACHE: dict[str, bool] | None = None


def _request_json(method: str, path: str, payload: dict | None = None, timeout: float = 4.0) -> dict:
    url = f"{BASE_URL}{path}"
    data = None
    headers = {"Accept": "application/json"}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _get_model_id() -> str:
    try:
        response = _request_json("GET", MODELS_PATH, timeout=2.5)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Локальный API недоступен на http://127.0.0.1:1234.\n"
            "Запустите сервер LM Studio и повторите попытку."
        ) from exc

    models = response.get("data", [])
    if not models:
        raise RuntimeError(
            "Сервер запущен, но список моделей пуст.\n"
            "Загрузите модель в LM Studio и включите Local Server."
        )

    model_id = models[0].get("id")
    if not model_id:
        raise RuntimeError("Не удалось определить id модели из /v1/models.")
    return model_id


def _detect_tools(force_refresh: bool = False) -> dict[str, bool]:
    global _TOOLS_CACHE
    if _TOOLS_CACHE is not None and not force_refresh:
        return dict(_TOOLS_CACHE)

    tools = {}
    for name in (*MODERN_TOOLS, *BASELINE_TOOLS):
        tools[name] = shutil.which(name) is not None
    _TOOLS_CACHE = tools
    return dict(tools)


def _build_capabilities() -> dict:
    tools = _detect_tools()
    modern_available = [name for name in MODERN_TOOLS if tools.get(name)]
    baseline_available = [name for name in BASELINE_TOOLS if tools.get(name)]

    shell_raw = os.environ.get("SHELL", "").strip()
    shell_name = os.path.basename(shell_raw) if shell_raw else "unknown"

    return {
        "tools": tools,
        "modern_available": modern_available,
        "baseline_available": baseline_available,
        "os_name": platform.system(),
        "shell_name": shell_name,
    }


def _format_capabilities_block(capabilities: dict, tool_policy: str) -> str:
    modern = capabilities["modern_available"] or ["none"]
    baseline = capabilities["baseline_available"] or ["none"]

    mapping_parts = []
    for base, modern_tool in PREFERRED_TOOL_MAP.items():
        if capabilities["tools"].get(modern_tool):
            mapping_parts.append(f"{base}->{modern_tool}")
        else:
            mapping_parts.append(f"{base}->{modern_tool}(missing)")

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


def _system_prompt(reasoning: bool, capabilities: dict, tool_policy: str) -> str:
    capabilities_block = _format_capabilities_block(capabilities, tool_policy)
    if reasoning:
        return (
            "Ты помощник по терминалу macOS. Отвечай на русском языке. "
            "Дай краткое объяснение и предложи несколько подходящих команд с комментариями.\n\n"
            f"{capabilities_block}"
        )
    return (
        "Ты помощник по терминалу macOS. Отвечай на русском языке. "
        "Верни только одну наиболее подходящую shell-команду без пояснений и без форматирования. "
        "Строго одна строка, без обратных кавычек, без префиксов и без русских слов.\n\n"
        f"{capabilities_block}"
    )


def _generate_answer(query: str, model_id: str, reasoning: bool, capabilities: dict, tool_policy: str) -> str:
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": _system_prompt(reasoning, capabilities, tool_policy)},
            {"role": "user", "content": query},
        ],
        "temperature": 0.2,
    }

    try:
        response = _request_json("POST", CHAT_PATH, payload=payload, timeout=30.0)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Ошибка запроса к /v1/chat/completions.\n"
            "Проверьте, что LM Studio Local Server запущен и доступен."
        ) from exc

    choices = response.get("choices", [])
    if not choices:
        raise RuntimeError("API вернул пустой ответ (нет choices).")

    message = choices[0].get("message", {})
    content = (message.get("content") or "").strip()
    if not content:
        raise RuntimeError("API вернул пустой текст ответа.")
    return content


def _clean_single_line(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()
    cleaned = cleaned.strip("`").strip()
    if "\n" in cleaned:
        cleaned = cleaned.splitlines()[0].strip()
    return cleaned


def _looks_like_command(text: str) -> bool:
    if not text:
        return False
    if re.search(r"[А-Яа-яЁё]", text):
        return False
    if not text.isascii():
        return False
    # Разрешаем любые печатные ASCII-символы shell (включая |, ", ', *, >, <, && и т.п.).
    if not re.match(r"^[ -~]+$", text):
        return False
    # Минимальная защита от "пустых" спецсимволов: в строке должна быть хотя бы одна буква/цифра.
    return bool(re.search(r"[A-Za-z0-9]", text))


def _extract_first_tool(command: str) -> str | None:
    match = re.match(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]+\s+)*(?P<cmd>[A-Za-z0-9_./~-]+)", command)
    if not match:
        return None
    cmd = match.group("cmd")
    return os.path.basename(cmd)


def _check_tool_policy(command: str, capabilities: dict, tool_policy: str) -> tuple[bool, str]:
    tool = _extract_first_tool(command)
    if not tool:
        return False, "Команда не распознана: не найден основной исполняемый файл."

    known_tools = set((*MODERN_TOOLS, *BASELINE_TOOLS))
    if tool not in known_tools:
        return True, ""

    tools = capabilities["tools"]
    if tool in MODERN_TOOLS and not tools.get(tool, False):
        return False, f"Инструмент `{tool}` недоступен в системе."

    if tool_policy == "strict":
        for base, modern in PREFERRED_TOOL_MAP.items():
            if tool == base:
                if tools.get(modern, False):
                    return False, f"В strict-режиме нужно использовать `{modern}` вместо `{base}`."
                return False, f"В strict-режиме требовался `{modern}`, но он не установлен."

    return True, ""


def _repair_command(query: str, model_id: str, capabilities: dict, tool_policy: str, reason: str) -> str:
    policy_instruction = (
        "Prefer modern tools when available; fallback to baseline tools when modern tools are unavailable."
        if tool_policy == "prefer"
        else "Strict modern mode: for mapped commands use modern tools only. If required modern tool is missing, output exactly: ERROR_STRICT_MISSING_TOOL"
    )

    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return exactly one macOS shell command in one line. "
                    "ASCII only. No explanations, no markdown.\n\n"
                    f"{_format_capabilities_block(capabilities, tool_policy)}\n"
                    f"{policy_instruction}"
                ),
            },
            {"role": "user", "content": f"User request: {query}\nFix reason: {reason}"},
        ],
        "temperature": 0.0,
        "max_tokens": 120,
    }
    response = _request_json("POST", CHAT_PATH, payload=payload, timeout=20.0)
    choices = response.get("choices", [])
    if not choices:
        raise RuntimeError("Не удалось получить команду: API вернул пустой ответ.")
    repaired = _clean_single_line((choices[0].get("message", {}).get("content") or ""))
    if repaired == "ERROR_STRICT_MISSING_TOOL":
        raise RuntimeError("Strict modern режим: для запроса требуется modern-инструмент, который не установлен.")
    return repaired


def _coerce_command(query: str, model_id: str, draft: str, capabilities: dict, tool_policy: str) -> str:
    command = _clean_single_line(draft)

    if not _looks_like_command(command):
        command = _repair_command(
            query=query,
            model_id=model_id,
            capabilities=capabilities,
            tool_policy=tool_policy,
            reason="not a valid single-line shell command",
        )
        command = _clean_single_line(command)
        if not _looks_like_command(command):
            raise RuntimeError("Модель не смогла вернуть корректную shell-команду. Попробуйте переформулировать запрос.")

    ok, reason = _check_tool_policy(command, capabilities, tool_policy)
    if ok:
        return command

    command = _repair_command(
        query=query,
        model_id=model_id,
        capabilities=capabilities,
        tool_policy=tool_policy,
        reason=reason,
    )
    command = _clean_single_line(command)
    if not _looks_like_command(command):
        raise RuntimeError("Модель не смогла вернуть корректную shell-команду. Попробуйте переформулировать запрос.")

    ok, reason = _check_tool_policy(command, capabilities, tool_policy)
    if ok:
        return command
    raise RuntimeError(reason or "Модель вернула команду, несовместимую с доступными утилитами.")


def _confirm_output() -> bool:
    answer = input("[y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _execute_command(command: str) -> int:
    completed = subprocess.run(command, shell=True)
    return completed.returncode


def _zsh_completion_script() -> str:
    return """#compdef searcher

_searcher() {
  _arguments -s \
    '(-r --reasoning)'{-r,--reasoning}'[Режим рассуждения: текстовый ответ без выполнения команды]' \
    '--prefer-modern[Приоритет modern-утилит с fallback на стандартные]' \
    '--strict-modern[Строгий modern-режим без fallback на baseline]' \
    '--dry-run[Показать команду без выполнения]' \
    '--print-zsh-completion[Печать zsh completion-скрипта]' \
    '*:query:_message "текст запроса"'
}

_searcher "$@"
"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="searcher",
        description="Подсказки по консольным командам macOS через локальный LM Studio/OpenAI API.",
    )
    parser.add_argument("query", nargs="*", help="Текст запроса, например: как найти большой файл")
    parser.add_argument(
        "-r",
        "--reasoning",
        action="store_true",
        help="Режим пояснений: вывести свободный текст и несколько возможных команд.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Не выполнять команду после подтверждения, только показать её.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--prefer-modern",
        action="store_const",
        const="prefer",
        dest="tool_policy",
        help="Приоритет modern-утилит с fallback на стандартные.",
    )
    group.add_argument(
        "--strict-modern",
        action="store_const",
        const="strict",
        dest="tool_policy",
        help="Строгий modern-режим: требовать modern-утилиты для известных замен.",
    )
    parser.set_defaults(tool_policy="prefer")
    parser.add_argument(
        "--print-zsh-completion",
        action="store_true",
        help="Напечатать скрипт автодополнения zsh для команды searcher.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if args.print_zsh_completion:
        print(_zsh_completion_script(), end="")
        return 0

    query = " ".join(args.query).strip()
    if not query:
        print("Запрос не должен быть пустым.", file=sys.stderr)
        return 1

    try:
        capabilities = _build_capabilities()
        model_id = _get_model_id()
        result = _generate_answer(
            query=query,
            model_id=model_id,
            reasoning=args.reasoning,
            capabilities=capabilities,
            tool_policy=args.tool_policy,
        )
        if not args.reasoning:
            result = _coerce_command(
                query=query,
                model_id=model_id,
                draft=result,
                capabilities=capabilities,
                tool_policy=args.tool_policy,
            )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.reasoning:
        print("\nПредложенный ответ:\n")
        print(result)
        return 0

    print(result)

    if not _confirm_output():
        return 1

    if args.dry_run:
        return 0

    return _execute_command(result)


if __name__ == "__main__":
    raise SystemExit(main())
