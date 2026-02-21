import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from searcher import cli
from searcher.core.command_policy import (
    check_tool_policy,
    coerce_command,
    has_minimum_usefulness,
    looks_like_command,
)
from searcher.core.completion import zsh_completion_script
from searcher.core.execution import choose_command, extract_commands, render_markdown
from searcher.core.execution import render_with_system_cat
from searcher.core.prompts import build_system_prompt
from searcher.core.tooling import build_capabilities, detect_tools, reset_tools_cache
from searcher.models.contracts import Capabilities


def make_capabilities(tools: dict[str, bool]) -> Capabilities:
    """Build capabilities fixture for tests."""
    modern = [
        name
        for name in ("bat", "rg", "fd", "eza", "dust", "zoxide")
        if tools.get(name, False)
    ]
    baseline = [
        name
        for name in (
            "cat",
            "grep",
            "find",
            "ls",
            "du",
            "awk",
            "sed",
            "head",
            "tail",
            "sort",
        )
        if tools.get(name, False)
    ]
    dev_tools = [
        name
        for name in (
            "docker",
            "git",
            "systemctl",
            "journalctl",
            "kubectl",
            "npm",
            "yarn",
            "pnpm",
            "make",
            "ssh",
            "curl",
        )
        if tools.get(name, False)
    ]
    return {
        "tools": tools,
        "modern_available": modern,
        "baseline_available": baseline,
        "dev_tools_available": dev_tools,
        "os_name": "Darwin",
        "shell_name": "zsh",
    }


class CommandValidationTests(unittest.TestCase):
    """Validate command-shape heuristics."""

    def test_standard_utilities_are_valid_commands(self) -> None:
        """Accept common shell command forms."""
        commands = [
            "cat README.md",
            "sort -hr sizes.txt | head -n 5",
            "awk '{print $1}' access.log",
            'grep -R "TODO" .',
            "head -n 20 /var/log/system.log",
            "tail -f /var/log/system.log",
        ]
        for cmd in commands:
            with self.subTest(command=cmd):
                self.assertTrue(looks_like_command(cmd))

    def test_command_with_cyrillic_is_rejected(self) -> None:
        """Reject plain russian text as shell command."""
        self.assertFalse(looks_like_command("показать файлы"))

    def test_command_with_unicode_argument_is_accepted(self) -> None:
        """Accept command with unicode argument value."""
        self.assertTrue(looks_like_command('grep -i "требования" README.md'))


class ToolingAndPromptTests(unittest.TestCase):
    """Validate environment detection and prompt composition."""

    def test_detect_tools_uses_cache(self) -> None:
        """Reuse detection cache in same process."""
        reset_tools_cache()
        with patch(
            "searcher.core.tooling.shutil.which",
            side_effect=lambda name: f"/bin/{name}",
        ):
            first = detect_tools()
            second = detect_tools()
        self.assertEqual(first, second)
        self.assertTrue(all(first.values()))

    def test_build_capabilities_uses_environment_context(self) -> None:
        """Read os and shell context for capabilities."""
        reset_tools_cache()
        with (
            patch(
                "searcher.core.tooling.shutil.which",
                side_effect=lambda name: (
                    f"/bin/{name}" if name in {"rg", "cat", "grep", "docker"} else None
                ),
            ),
            patch("searcher.core.tooling.platform.system", return_value="Darwin"),
            patch.dict(
                "searcher.core.tooling.os.environ", {"SHELL": "/bin/zsh"}, clear=True
            ),
        ):
            capabilities = build_capabilities()
        self.assertEqual(capabilities["os_name"], "Darwin")
        self.assertEqual(capabilities["shell_name"], "zsh")
        self.assertIn("rg", capabilities["modern_available"])
        self.assertIn("cat", capabilities["baseline_available"])
        self.assertIn("docker", capabilities["dev_tools_available"])

    def test_system_prompt_includes_dynamic_capabilities(self) -> None:
        """Embed capabilities in system prompt."""
        capabilities = make_capabilities(
            {
                "bat": True,
                "rg": True,
                "fd": False,
                "eza": False,
                "dust": False,
                "zoxide": False,
                "cat": True,
                "grep": True,
                "find": True,
                "ls": True,
                "du": True,
                "awk": True,
                "sed": True,
                "head": True,
                "tail": True,
                "sort": True,
                "docker": True,
                "git": True,
            }
        )
        prompt = build_system_prompt(
            reasoning=False, capabilities=capabilities, tool_policy="prefer"
        )
        self.assertIn("Available modern tools: bat, rg", prompt)
        self.assertIn("Available domain dev tools: docker, git", prompt)
        self.assertIn("Environment: OS=Darwin; shell=zsh", prompt)
        self.assertIn("Policy: Prefer modern tools", prompt)
        reasoning_prompt = build_system_prompt(
            reasoning=True, capabilities=capabilities, tool_policy="prefer"
        )
        self.assertIn("в приоритете `rg`, иначе `grep`", reasoning_prompt)

    def test_zsh_completion_contains_flags(self) -> None:
        """Expose CLI flags in completion script."""
        script = zsh_completion_script()
        self.assertIn("#compdef searcher", script)
        self.assertIn("--dry-run", script)
        self.assertIn("--short", script)
        self.assertIn("--prefer-modern", script)
        self.assertIn("--strict-modern", script)
        self.assertIn("--llm-validate", script)
        self.assertIn("--print-zsh-completion", script)


class PolicyTests(unittest.TestCase):
    """Validate strict/prefer policy behavior."""

    def test_check_tool_policy_strict_requires_modern(self) -> None:
        """Reject baseline tool when strict modern has replacement."""
        capabilities = make_capabilities(
            {
                "bat": True,
                "rg": True,
                "fd": False,
                "eza": False,
                "dust": False,
                "zoxide": False,
                "cat": True,
                "grep": True,
                "find": True,
                "ls": True,
                "du": True,
                "awk": True,
                "sed": True,
                "head": True,
                "tail": True,
                "sort": True,
            }
        )
        ok, reason = check_tool_policy("grep TODO .", capabilities, "strict")
        self.assertFalse(ok)
        self.assertIn("использовать `rg`", reason)

    def test_coerce_command_repairs_after_policy_violation(self) -> None:
        """Repair output when first command violates strict policy."""
        capabilities = make_capabilities(
            {
                "bat": True,
                "rg": True,
                "fd": False,
                "eza": False,
                "dust": False,
                "zoxide": False,
                "cat": True,
                "grep": True,
                "find": True,
                "ls": True,
                "du": True,
                "awk": True,
                "sed": True,
                "head": True,
                "tail": True,
                "sort": True,
            }
        )
        result = coerce_command(
            query="find todo",
            model_id="model",
            draft="grep TODO .",
            capabilities=capabilities,
            tool_policy="strict",
            repair_command_fn=lambda **_: "rg TODO .",
        )
        self.assertEqual(result, "rg TODO .")

    def test_has_minimum_usefulness_rejects_bare_known_tool(self) -> None:
        """Reject single-token known utility as non-useful command."""
        self.assertFalse(has_minimum_usefulness("bat"))
        self.assertFalse(has_minimum_usefulness("rg"))
        self.assertTrue(has_minimum_usefulness('rg "needle" .'))

    def test_coerce_command_repairs_bare_tool(self) -> None:
        """Repair bare tool output into actionable command."""
        capabilities = make_capabilities(
            {
                "bat": True,
                "rg": True,
                "fd": True,
                "eza": False,
                "dust": False,
                "zoxide": False,
                "cat": True,
                "grep": True,
                "find": True,
                "ls": True,
                "du": True,
                "awk": True,
                "sed": True,
                "head": True,
                "tail": True,
                "sort": True,
            }
        )
        result = coerce_command(
            query="Найти py файл с текстом Требования",
            model_id="model",
            draft="bat",
            capabilities=capabilities,
            tool_policy="prefer",
            repair_command_fn=lambda **_: 'rg -l "Requirements" -g "*.py" .',
        )
        self.assertEqual(result, 'rg -l "Requirements" -g "*.py" .')


class CliFlowTests(unittest.TestCase):
    """Validate user-facing CLI flow."""

    def test_main_normal_mode_executes_selected_command(self) -> None:
        """Execute selected command from numbered list."""

        with (
            patch(
                "searcher.use_cases.cli_runtime.build_capabilities",
                return_value=make_capabilities({}),
            ),
            patch(
                "searcher.use_cases.cli_runtime.get_model_id",
                return_value="local-model",
            ),
            patch(
                "searcher.use_cases.cli_runtime.generate_answer",
                return_value="1) rg -n TODO .\n2) fd TODO .",
            ),
            patch(
                "searcher.use_cases.cli_runtime.extract_commands",
                return_value=["rg -n TODO .", "fd TODO ."],
            ),
            patch(
                "searcher.use_cases.cli_runtime.choose_command",
                return_value="rg -n TODO .",
            ),
            patch(
                "searcher.use_cases.cli_runtime.execute_command",
                return_value=0,
            ) as execute_mock,
            patch(
                "searcher.use_cases.cli_runtime.coerce_command",
                return_value="rg -n TODO .",
            ) as coerce_mock,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main(["--short", "как найти todo"])
        self.assertEqual(exit_code, 0)
        execute_mock.assert_called_once_with("rg -n TODO .")
        self.assertEqual(coerce_mock.call_args.kwargs["draft"], "rg -n TODO .")
        self.assertEqual(stderr.getvalue(), "")

    def test_main_strict_modern_passes_policy_to_coerce(self) -> None:
        """Forward strict policy to command coercion."""
        with (
            patch(
                "searcher.use_cases.cli_runtime.build_capabilities",
                return_value=make_capabilities({}),
            ),
            patch(
                "searcher.use_cases.cli_runtime.get_model_id",
                return_value="local-model",
            ),
            patch(
                "searcher.use_cases.cli_runtime.generate_answer",
                return_value="1) rg TODO .",
            ),
            patch(
                "searcher.use_cases.cli_runtime.extract_commands",
                return_value=["rg TODO ."],
            ),
            patch(
                "searcher.use_cases.cli_runtime.choose_command",
                return_value="rg TODO .",
            ),
            patch(
                "searcher.use_cases.cli_runtime.coerce_command",
                return_value="rg TODO .",
            ) as coerce_mock,
            patch("searcher.use_cases.cli_runtime.execute_command", return_value=0),
        ):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exit_code = cli.main(["--short", "--strict-modern", "todo"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(coerce_mock.call_args.kwargs["tool_policy"], "strict")

    def test_main_llm_validate_calls_validator(self) -> None:
        """Run additional validator when llm validation is enabled."""
        with (
            patch(
                "searcher.use_cases.cli_runtime.build_capabilities",
                return_value=make_capabilities({}),
            ),
            patch(
                "searcher.use_cases.cli_runtime.get_model_id",
                return_value="local-model",
            ),
            patch(
                "searcher.use_cases.cli_runtime.generate_answer",
                return_value="1) rg TODO .",
            ),
            patch(
                "searcher.use_cases.cli_runtime.extract_commands",
                return_value=["rg TODO ."],
            ),
            patch(
                "searcher.use_cases.cli_runtime.choose_command",
                return_value="rg TODO .",
            ),
            patch(
                "searcher.use_cases.cli_runtime.coerce_command",
                return_value="rg TODO .",
            ),
            patch(
                "searcher.use_cases.cli_runtime.validate_terminal_command",
                return_value={"is_valid": True, "reason": ""},
            ) as validate_mock,
            patch("searcher.use_cases.cli_runtime.execute_command", return_value=0),
        ):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exit_code = cli.main(["--short", "--llm-validate", "todo"])
        self.assertEqual(exit_code, 0)
        validate_mock.assert_called()

    def test_main_default_mode_skips_command_coercion(self) -> None:
        """Do not coerce command in default reasoning mode."""
        with (
            patch(
                "searcher.use_cases.cli_runtime.build_capabilities",
                return_value=make_capabilities({}),
            ),
            patch(
                "searcher.use_cases.cli_runtime.get_model_id",
                return_value="local-model",
            ),
            patch(
                "searcher.use_cases.cli_runtime.generate_answer",
                return_value="Можно использовать cat и grep для первичной фильтрации.",
            ),
            patch("searcher.use_cases.cli_runtime.render_markdown") as render_mock,
            patch("searcher.use_cases.cli_runtime.coerce_command") as coerce_mock,
            patch("builtins.input") as input_mock,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main(["как посмотреть лог"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "")
        render_mock.assert_called_once_with(
            "Можно использовать cat и grep для первичной фильтрации."
        )
        coerce_mock.assert_not_called()
        input_mock.assert_not_called()
        self.assertEqual(stderr.getvalue(), "")

    def test_main_dry_run_prints_and_does_not_execute(self) -> None:
        """Skip command execution when dry-run is enabled."""

        with (
            patch(
                "searcher.use_cases.cli_runtime.build_capabilities",
                return_value=make_capabilities({}),
            ),
            patch(
                "searcher.use_cases.cli_runtime.get_model_id",
                return_value="local-model",
            ),
            patch(
                "searcher.use_cases.cli_runtime.generate_answer",
                return_value="1) tail -n 50 app.log",
            ),
            patch(
                "searcher.use_cases.cli_runtime.extract_commands",
                return_value=["tail -n 50 app.log"],
            ),
            patch(
                "searcher.use_cases.cli_runtime.choose_command",
                return_value="tail -n 50 app.log",
            ),
            patch(
                "searcher.use_cases.cli_runtime.coerce_command",
                return_value="tail -n 50 app.log",
            ),
            patch(
                "searcher.use_cases.cli_runtime.execute_command"
            ) as execute_mock,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main(["--short", "--dry-run", "показать последние логи"])
        self.assertEqual(exit_code, 0)
        self.assertIn("tail -n 50 app.log", stdout.getvalue())
        execute_mock.assert_not_called()
        self.assertEqual(stderr.getvalue(), "")

    def test_main_returns_error_when_no_commands_extracted(self) -> None:
        """Fail gracefully when reasoning answer has no command lines."""
        with (
            patch(
                "searcher.use_cases.cli_runtime.build_capabilities",
                return_value=make_capabilities({}),
            ),
            patch(
                "searcher.use_cases.cli_runtime.get_model_id",
                return_value="local-model",
            ),
            patch(
                "searcher.use_cases.cli_runtime.generate_answer",
                return_value="Попробуйте проверить README и логи.",
            ),
            patch("searcher.use_cases.cli_runtime.extract_commands", return_value=[]),
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main(["--short", "как найти configs"])
        self.assertEqual(exit_code, 1)
        self.assertIn("Не удалось извлечь подходящие команды", stderr.getvalue())

    def test_main_returns_error_when_api_unavailable(self) -> None:
        """Print runtime error from API layer."""
        with (
            patch(
                "searcher.use_cases.cli_runtime.build_capabilities",
                return_value=make_capabilities({}),
            ),
            patch(
                "searcher.use_cases.cli_runtime.get_model_id",
                side_effect=RuntimeError("API недоступен"),
            ),
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main(["любой запрос"])
        self.assertEqual(exit_code, 1)
        self.assertIn("API недоступен", stderr.getvalue())

    def test_main_prints_zsh_completion_and_exits(self) -> None:
        """Print completion without starting API flow."""
        with (
            patch("searcher.use_cases.cli_runtime.get_model_id") as get_model_mock,
            patch("searcher.use_cases.cli_runtime.generate_answer") as generate_mock,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main(["--print-zsh-completion"])
        self.assertEqual(exit_code, 0)
        self.assertIn("#compdef searcher", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        get_model_mock.assert_not_called()
        generate_mock.assert_not_called()


class ExecutionTests(unittest.TestCase):
    """Validate command extraction and interactive selection."""

    def test_extract_commands_reads_only_bash_fences(self) -> None:
        """Extract shell commands only from fenced bash blocks."""
        answer = (
            "Сделайте так:\n"
            "```bash\n"
            "ls -l ~/configs\n"
            "rg -n configs .\n"
            "```\n"
            "И еще можно `find . -name \"*.py\"`.\n"
            "```text\n"
            "cat README.md\n"
            "```"
        )
        self.assertEqual(extract_commands(answer), ["ls -l ~/configs", "rg -n configs ."])

    def test_choose_command_returns_selected_item(self) -> None:
        """Return selected command by number."""
        with patch("builtins.input", return_value="2"):
            selected = choose_command(["ls -la", "rg TODO ."])
        self.assertEqual(selected, "rg TODO .")

    def test_choose_command_empty_input_cancels(self) -> None:
        """Cancel selection when user presses Enter."""
        with patch("builtins.input", return_value=""):
            selected = choose_command(["ls -la", "rg TODO ."])
        self.assertIsNone(selected)

    def test_choose_command_zero_cancels(self) -> None:
        """Cancel selection when user enters 0."""
        with patch("builtins.input", return_value="0"):
            selected = choose_command(["ls -la", "rg TODO ."])
        self.assertIsNone(selected)

    def test_render_with_system_cat_falls_back_to_print(self) -> None:
        """Fallback to print when `cat` execution fails."""
        with (
            patch("searcher.core.execution.subprocess.run", side_effect=OSError),
            patch("builtins.print") as print_mock,
        ):
            render_with_system_cat("пример")
        print_mock.assert_called_once_with("пример")

    def test_render_markdown_prefers_glow_when_available(self) -> None:
        """Use glow renderer when it is available."""
        with (
            patch(
                "searcher.core.execution.shutil.which",
                side_effect=lambda name: "/bin/glow" if name == "glow" else None,
            ),
            patch("searcher.core.execution.subprocess.run") as run_mock,
            patch("searcher.core.execution.render_with_system_cat") as cat_mock,
        ):
            run_mock.return_value.returncode = 0
            render_markdown("# Заголовок")
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.args[0], ["glow", "-"])
        cat_mock.assert_not_called()

    def test_render_markdown_falls_back_to_cat_without_renderers(self) -> None:
        """Fallback to plain cat when markdown renderer is unavailable."""
        with (
            patch("searcher.core.execution.shutil.which", return_value=None),
            patch("searcher.core.execution.render_with_system_cat") as cat_mock,
        ):
            render_markdown("**text**")
        cat_mock.assert_called_once_with("**text**")


if __name__ == "__main__":
    unittest.main()
