import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

import main


class CommandValidationTests(unittest.TestCase):
    def test_standard_utilities_are_valid_commands(self) -> None:
        commands = [
            "cat README.md",
            "sort -hr sizes.txt | head -n 5",
            "awk '{print $1}' access.log",
            "grep -R \"TODO\" .",
            "head -n 20 /var/log/system.log",
            "tail -f /var/log/system.log",
        ]
        for cmd in commands:
            with self.subTest(command=cmd):
                self.assertTrue(main._looks_like_command(cmd))

    def test_command_with_cyrillic_is_rejected(self) -> None:
        self.assertFalse(main._looks_like_command("показать файлы"))


class PromptTests(unittest.TestCase):
    def _make_capabilities(self, tools: dict[str, bool]) -> dict:
        return {
            "tools": tools,
            "modern_available": [name for name in main.MODERN_TOOLS if tools.get(name)],
            "baseline_available": [name for name in main.BASELINE_TOOLS if tools.get(name)],
            "os_name": "Darwin",
            "shell_name": "zsh",
        }

    def test_detect_tools_uses_cache(self) -> None:
        main._TOOLS_CACHE = None
        with patch("main.shutil.which", side_effect=lambda name: f"/bin/{name}"):
            first = main._detect_tools()
            second = main._detect_tools()
        self.assertEqual(first, second)
        self.assertTrue(all(first.values()))

    def test_build_capabilities_uses_environment_context(self) -> None:
        main._TOOLS_CACHE = None
        with (
            patch("main.shutil.which", side_effect=lambda name: f"/bin/{name}" if name in {"rg", "cat", "grep"} else None),
            patch("main.platform.system", return_value="Darwin"),
            patch.dict("main.os.environ", {"SHELL": "/bin/zsh"}, clear=True),
        ):
            capabilities = main._build_capabilities()

        self.assertEqual(capabilities["os_name"], "Darwin")
        self.assertEqual(capabilities["shell_name"], "zsh")
        self.assertIn("rg", capabilities["modern_available"])
        self.assertIn("cat", capabilities["baseline_available"])

    def test_system_prompt_includes_dynamic_capabilities(self) -> None:
        capabilities = self._make_capabilities(
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
        prompt = main._system_prompt(reasoning=False, capabilities=capabilities, tool_policy="prefer")
        self.assertIn("Available modern tools: bat, rg", prompt)
        self.assertIn("Environment: OS=Darwin; shell=zsh", prompt)
        self.assertIn("Policy: Prefer modern tools", prompt)

    def test_zsh_completion_contains_flags(self) -> None:
        script = main._zsh_completion_script()
        self.assertIn("#compdef searcher", script)
        self.assertIn("--dry-run", script)
        self.assertIn("--reasoning", script)
        self.assertIn("--prefer-modern", script)
        self.assertIn("--strict-modern", script)
        self.assertIn("--print-zsh-completion", script)

    def test_check_tool_policy_strict_requires_modern(self) -> None:
        capabilities = self._make_capabilities(
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
        ok, reason = main._check_tool_policy("grep TODO .", capabilities, "strict")
        self.assertFalse(ok)
        self.assertIn("использовать `rg`", reason)

    def test_coerce_command_repairs_after_policy_violation(self) -> None:
        capabilities = self._make_capabilities(
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
        with patch("main._repair_command", return_value="rg TODO ."):
            result = main._coerce_command(
                query="find todo",
                model_id="model",
                draft="grep TODO .",
                capabilities=capabilities,
                tool_policy="strict",
            )
        self.assertEqual(result, "rg TODO .")


class CliFlowTests(unittest.TestCase):
    def test_main_normal_mode_executes_command_after_confirmation(self) -> None:
        prompt_calls = []

        def fake_input(prompt: str = "") -> str:
            prompt_calls.append(prompt)
            return "y"

        with (
            patch("main._get_model_id", return_value="local-model"),
            patch("main._generate_answer", return_value="grep -R \"TODO\" ."),
            patch("main._coerce_command", return_value="grep -R \"TODO\" ."),
            patch("builtins.input", side_effect=fake_input),
            patch("main.subprocess.run", return_value=SimpleNamespace(returncode=0)) as run_mock,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main.main(["как найти todo"])

        self.assertEqual(exit_code, 0)
        self.assertIn("grep -R \"TODO\" .", stdout.getvalue())
        self.assertNotIn("Предложенная команда:", stdout.getvalue())
        run_mock.assert_called_once_with("grep -R \"TODO\" .", shell=True)
        self.assertEqual(prompt_calls, ["[y/N]: "])
        self.assertEqual(stderr.getvalue(), "")

    def test_main_strict_modern_passes_policy_to_coerce(self) -> None:
        with (
            patch("main._build_capabilities", return_value={"tools": {}, "modern_available": [], "baseline_available": [], "os_name": "Darwin", "shell_name": "zsh"}),
            patch("main._get_model_id", return_value="local-model"),
            patch("main._generate_answer", return_value="rg TODO ."),
            patch("main._coerce_command", return_value="rg TODO .") as coerce_mock,
            patch("builtins.input", return_value="n"),
        ):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                exit_code = main.main(["--strict-modern", "todo"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(coerce_mock.call_args.kwargs["tool_policy"], "strict")

    def test_main_reasoning_mode_skips_command_coercion(self) -> None:
        with (
            patch("main._get_model_id", return_value="local-model"),
            patch(
                "main._generate_answer",
                return_value="Можно использовать cat и grep для первичной фильтрации.",
            ),
            patch("main._coerce_command") as coerce_mock,
            patch("builtins.input") as input_mock,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main.main(["-r", "как посмотреть лог"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Предложенный ответ:", stdout.getvalue())
        coerce_mock.assert_not_called()
        input_mock.assert_not_called()
        self.assertEqual(stderr.getvalue(), "")

    def test_main_dry_run_does_not_execute_command(self) -> None:
        prompt_calls = []

        def fake_input(prompt: str = "") -> str:
            prompt_calls.append(prompt)
            return "y"

        with (
            patch("main._get_model_id", return_value="local-model"),
            patch("main._generate_answer", return_value="tail -n 50 app.log"),
            patch("main._coerce_command", return_value="tail -n 50 app.log"),
            patch("builtins.input", side_effect=fake_input),
            patch("main.subprocess.run") as run_mock,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main.main(["--dry-run", "показать последние логи"])

        self.assertEqual(exit_code, 0)
        self.assertIn("tail -n 50 app.log", stdout.getvalue())
        self.assertNotIn("Dry-run:", stdout.getvalue())
        self.assertEqual(prompt_calls, ["[y/N]: "])
        run_mock.assert_not_called()
        self.assertEqual(stderr.getvalue(), "")

    def test_main_returns_error_when_api_unavailable(self) -> None:
        with patch("main._get_model_id", side_effect=RuntimeError("API недоступен")):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main.main(["любой запрос"])

        self.assertEqual(exit_code, 1)
        self.assertIn("API недоступен", stderr.getvalue())

    def test_main_prints_zsh_completion_and_exits(self) -> None:
        with (
            patch("main._get_model_id") as get_model_mock,
            patch("main._generate_answer") as generate_mock,
        ):
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main.main(["--print-zsh-completion"])

        self.assertEqual(exit_code, 0)
        self.assertIn("#compdef searcher", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        get_model_mock.assert_not_called()
        generate_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
