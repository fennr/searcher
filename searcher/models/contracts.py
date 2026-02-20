"""Typed model contracts used across layers."""

from typing import Literal, TypedDict


ToolPolicy = Literal["prefer", "strict"]


class Capabilities(TypedDict):
    """Describes discovered environment capabilities."""

    tools: dict[str, bool]
    modern_available: list[str]
    baseline_available: list[str]
    os_name: str
    shell_name: str


class CliOptions(TypedDict):
    """CLI options normalized from argparse namespace."""

    query: str
    reasoning: bool
    dry_run: bool
    llm_validate: bool
    tool_policy: ToolPolicy
    print_zsh_completion: bool


class ChatMessage(TypedDict):
    """OpenAI-compatible message shape."""

    role: str
    content: str


class ModelItem(TypedDict, total=False):
    """Model descriptor returned by /v1/models."""

    id: str


class ModelsResponse(TypedDict, total=False):
    """Response shape for /v1/models."""

    data: list[ModelItem]


class AssistantMessage(TypedDict, total=False):
    """Assistant message shape in chat completion."""

    content: str


class ChoiceItem(TypedDict, total=False):
    """Choice item in chat completion."""

    message: AssistantMessage


class ChatCompletionsResponse(TypedDict, total=False):
    """Response shape for /v1/chat/completions."""

    choices: list[ChoiceItem]


class ValidationResult(TypedDict):
    """Validation result returned by command validation use case."""

    is_valid: bool
    reason: str
