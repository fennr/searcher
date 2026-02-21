"""Command selection and execution primitives."""

import re
import shutil
import subprocess

from searcher.core.command_policy import clean_single_line, has_minimum_usefulness
from searcher.core.command_policy import looks_like_command

_FENCE_RE = re.compile(r"^```(?P<lang>[A-Za-z0-9_-]+)?\s*$")


def extract_commands(answer: str) -> list[str]:
    """Extract unique shell commands only from fenced bash blocks."""
    commands: list[str] = []
    seen: set[str] = set()
    in_bash_block = False
    in_code_block = False
    for line in answer.splitlines():
        stripped = line.strip()
        fence = _FENCE_RE.match(stripped)
        if fence:
            if in_code_block:
                in_code_block = False
                in_bash_block = False
            else:
                in_code_block = True
                in_bash_block = (fence.group("lang") or "").lower() == "bash"
            continue
        if not (in_code_block and in_bash_block):
            continue
        candidate = clean_single_line(line)
        if not looks_like_command(candidate):
            continue
        if not has_minimum_usefulness(candidate):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        commands.append(candidate)
    return commands


def choose_command(commands: list[str]) -> str | None:
    """Prompt user to choose command index; return None on cancel."""
    if not commands:
        return None
    print("Выберите команду по номеру (Enter для отмены):")
    for index, command in enumerate(commands, start=1):
        print(f"{index}. {command}")
    while True:
        raw = input("> ").strip()
        if not raw:
            return None
        if not raw.isdigit():
            print(f"Введите число от 1 до {len(commands)}.")
            continue
        selected = int(raw)
        if 1 <= selected <= len(commands):
            return commands[selected - 1]
        print(f"Введите число от 1 до {len(commands)}.")


def render_with_system_cat(text: str) -> None:
    """Render text through system `cat`; fallback to plain print."""
    payload = text if text.endswith("\n") else f"{text}\n"
    try:
        subprocess.run(["cat"], input=payload, text=True, check=False)
    except OSError:
        print(text)


def render_markdown(text: str) -> None:
    """Render markdown in terminal when supported tools are available."""
    payload = text if text.endswith("\n") else f"{text}\n"
    renderers: list[list[str]] = [["glow", "-"], ["mdcat"]]
    for command in renderers:
        if shutil.which(command[0]) is None:
            continue
        try:
            completed = subprocess.run(command, input=payload, text=True, check=False)
        except OSError:
            continue
        if completed.returncode == 0:
            return
    render_with_system_cat(text)


def execute_command(command: str) -> int:
    """Execute command in user shell and return process code."""
    completed = subprocess.run(command, shell=True)
    return completed.returncode
