"""Shell completion generation."""


def zsh_completion_script() -> str:
    """Return zsh completion script for searcher command."""
    return """#compdef searcher

_searcher() {
  _arguments -s \\
    '(-s --short)'{-s,--short}'[Короткий режим: выбрать и выполнить одну из предложенных команд]' \\
    '--prefer-modern[Приоритет modern-утилит с fallback на стандартные]' \\
    '--strict-modern[Строгий modern-режим без fallback на baseline]' \\
    '--llm-validate[Дополнительная LLM-валидация команды перед выполнением]' \\
    '--dry-run[Показать команду без выполнения]' \\
    '--print-zsh-completion[Печать zsh completion-скрипта]' \\
    '*:query:_message "текст запроса"'
}

_searcher "$@"
"""
