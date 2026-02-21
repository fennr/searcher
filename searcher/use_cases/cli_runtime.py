"""CLI orchestration use case."""

import sys

from searcher.core.command_policy import coerce_command
from searcher.core.completion import zsh_completion_script
from searcher.core.execution import choose_command, execute_command, extract_commands
from searcher.core.execution import render_markdown
from searcher.core.tooling import build_capabilities
from searcher.models.contracts import CliOptions
from searcher.use_cases.assistant import generate_answer, get_model_id, repair_command
from searcher.use_cases.assistant import validate_terminal_command


def run_cli(options: CliOptions) -> int:
    """Execute full CLI flow from validated options."""
    if options["print_zsh_completion"]:
        print(zsh_completion_script(), end="")
        return 0
    query = options["query"].strip()
    if not query:
        print("Запрос не должен быть пустым.", file=sys.stderr)
        return 1
    try:
        capabilities = build_capabilities()
        model_id = get_model_id()
        result = generate_answer(
            query=query,
            model_id=model_id,
            reasoning=True,
            capabilities=capabilities,
            tool_policy=options["tool_policy"],
        )
        if options["reasoning"]:
            render_markdown(result)
            return 0
        candidates = extract_commands(result)
        if not candidates:
            raise RuntimeError(
                "Не удалось извлечь подходящие команды из ответа модели. "
                "Попробуйте уточнить запрос."
            )
        selected = choose_command(candidates)
        if selected is None:
            return 1
        result = coerce_command(
            query=query,
            model_id=model_id,
            draft=selected,
            capabilities=capabilities,
            tool_policy=options["tool_policy"],
            repair_command_fn=repair_command,
        )
        if options["llm_validate"]:
            validation = validate_terminal_command(
                query=query,
                command=result,
                model_id=model_id,
                capabilities=capabilities,
                tool_policy=options["tool_policy"],
            )
            if not validation["is_valid"]:
                repaired = repair_command(
                    query=query,
                    model_id=model_id,
                    capabilities=capabilities,
                    tool_policy=options["tool_policy"],
                    reason=f"llm validation failed: {validation['reason']}",
                )
                result = coerce_command(
                    query=query,
                    model_id=model_id,
                    draft=repaired,
                    capabilities=capabilities,
                    tool_policy=options["tool_policy"],
                    repair_command_fn=repair_command,
                )
                validation = validate_terminal_command(
                    query=query,
                    command=result,
                    model_id=model_id,
                    capabilities=capabilities,
                    tool_policy=options["tool_policy"],
                )
                if not validation["is_valid"]:
                    raise RuntimeError(
                        "LLM-валидация не подтвердила команду: "
                        f"{validation['reason'] or 'неизвестная причина'}"
                    )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if options["dry_run"]:
        print(result)
        return 0
    return execute_command(result)
