import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from searcher import cli
from searcher.core.command_policy import (
    check_tool_policy,
    coerce_command,
    looks_like_command,
)
from searcher.core.completion import zsh_completion_script
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
    return {
        "tools": tools,
        "modern_available": modern,
        "baseline_available": baseline,
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
                    f"/bin/{name}" if name in {"rg", "cat", "grep"} else None
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
            }
        )
        prompt = build_system_prompt(
            reasoning=False, capabilities=capabilities, tool_policy="prefer"
        )
        self.assertIn("Available modern tools: bat, rg", prompt)
        self.assertIn("Environment: OS=Darwin; shell=zsh", prompt)
        self.assertIn("Policy: Prefer modern tools", prompt)

    def test_zsh_completion_contains_flags(self) -> None:
        """Expose CLI flags in completion script."""
        script = zsh_completion_script()
        self.assertIn("#compdef searcher", script)
        self.assertIn("--dry-run", script)
        self.assertIn("--reasoning", script)
        self.assertIn("--prefer-modern", script)
        self.assertIn("--strict-modern", script)
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


class CliFlowTests(unittest.TestCase):
    """Validate user-facing CLI flow."""

    def test_main_normal_mode_executes_command_after_confirmation(self) -> None:
        """Run command after positive confirmation."""
        prompt_calls: list[str] = []

        def fake_input(prompt: str = "") -> str:
            prompt_calls.append(prompt)
            return "y"

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
                return_value='grep -R "TODO" .',
            ),
            patch(
                "searcher.use_cases.cli_runtime.coerce_command",
                return_value='grep -R "TODO" .',
            ),
            patch("builtins.input", side_effect=fake_input),
            patch(
                "searcher.core.execution.subprocess.run",
                return_value=SimpleNamespace(returncode=0),
            ) as run_mock,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main(["как найти todo"])
        self.assertEqual(exit_code, 0)
        self.assertIn('grep -R "TODO" .', stdout.getvalue())
        run_mock.assert_called_once_with('grep -R "TODO" .', shell=True)
        self.assertEqual(prompt_calls, ["[y/N]: "])
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
                return_value="rg TODO .",
            ),
            patch(
                "searcher.use_cases.cli_runtime.coerce_command",
                return_value="rg TODO .",
            ) as coerce_mock,
            patch("builtins.input", return_value="n"),
        ):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exit_code = cli.main(["--strict-modern", "todo"])
        self.assertEqual(exit_code, 1)
        self.assertEqual(coerce_mock.call_args.kwargs["tool_policy"], "strict")

    def test_main_reasoning_mode_skips_command_coercion(self) -> None:
        """Do not coerce command in reasoning mode."""
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
            patch("searcher.use_cases.cli_runtime.coerce_command") as coerce_mock,
            patch("builtins.input") as input_mock,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main(["-r", "как посмотреть лог"])
        self.assertEqual(exit_code, 0)
        self.assertIn("Предложенный ответ:", stdout.getvalue())
        coerce_mock.assert_not_called()
        input_mock.assert_not_called()
        self.assertEqual(stderr.getvalue(), "")

    def test_main_dry_run_does_not_execute_command(self) -> None:
        """Skip execution when dry-run is enabled."""
        prompt_calls: list[str] = []

        def fake_input(prompt: str = "") -> str:
            prompt_calls.append(prompt)
            return "y"

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
                return_value="tail -n 50 app.log",
            ),
            patch(
                "searcher.use_cases.cli_runtime.coerce_command",
                return_value="tail -n 50 app.log",
            ),
            patch("builtins.input", side_effect=fake_input),
            patch("searcher.core.execution.subprocess.run") as run_mock,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main(["--dry-run", "показать последние логи"])
        self.assertEqual(exit_code, 0)
        self.assertIn("tail -n 50 app.log", stdout.getvalue())
        self.assertEqual(prompt_calls, ["[y/N]: "])
        run_mock.assert_not_called()
        self.assertEqual(stderr.getvalue(), "")

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


if __name__ == "__main__":
    unittest.main()
