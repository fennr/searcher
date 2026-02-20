"""Command execution primitives."""

import subprocess


def confirm_output() -> bool:
    """Prompt user for command confirmation."""
    answer = input("[y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def execute_command(command: str) -> int:
    """Execute command in user shell and return process code."""
    completed = subprocess.run(command, shell=True)
    return completed.returncode
