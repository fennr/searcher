"""CLI argument parsing adapter."""

import argparse
import sys

from searcher.models.contracts import CliOptions, ToolPolicy
from searcher.use_cases.cli_runtime import run_cli


def _to_tool_policy(value: str) -> ToolPolicy:
    """Validate and narrow argparse string to ToolPolicy."""
    if value == "strict":
        return "strict"
    return "prefer"


def parse_args(argv: list[str]) -> CliOptions:
    """Parse argv into typed CLI options."""
    parser = argparse.ArgumentParser(
        prog="searcher",
        description="Подсказки по консольным командам macOS через локальный LM Studio/OpenAI API.",
    )
    parser.add_argument(
        "query", nargs="*", help="Текст запроса, например: как найти большой файл"
    )
    parser.add_argument(
        "-s",
        "--short",
        action="store_true",
        help="Короткий командный режим: выбрать и выполнить одну из предложенных команд.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Не выполнять выбранную команду, только показать её.",
    )
    parser.add_argument(
        "--llm-validate",
        action="store_true",
        help="Дополнительно валидировать команду через модель перед выполнением.",
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
    namespace = parser.parse_args(argv)
    query_parts = list(namespace.query) if isinstance(namespace.query, list) else []
    return {
        "query": " ".join(query_parts).strip(),
        "short": bool(namespace.short),
        "dry_run": bool(namespace.dry_run),
        "llm_validate": bool(namespace.llm_validate),
        "tool_policy": _to_tool_policy(str(namespace.tool_policy)),
        "print_zsh_completion": bool(namespace.print_zsh_completion),
    }


def main(argv: list[str] | None = None) -> int:
    """Run CLI from argv and return process exit code."""
    options = parse_args(argv if argv is not None else sys.argv[1:])
    return run_cli(options)
