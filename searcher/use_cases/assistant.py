"""Use cases that communicate with language model API."""

import json
import urllib.error

from searcher.config import BASE_URL, CHAT_PATH, MODELS_PATH
from searcher.core.http_client import request_json
from searcher.core.prompts import build_system_prompt, format_capabilities_block
from searcher.models.contracts import (
    Capabilities,
    ChatCompletionsResponse,
    ChatMessage,
    ChoiceItem,
    ModelItem,
    ModelsResponse,
    ToolPolicy,
    ValidationResult,
)


def _build_chat_payload(
    query: str,
    model_id: str,
    reasoning: bool,
    capabilities: Capabilities,
    tool_policy: ToolPolicy,
    preferred_tools: list[str] | None = None,
) -> dict[str, object]:
    """Build chat completion payload."""
    messages: list[ChatMessage] = [
        {
            "role": "system",
            "content": build_system_prompt(
                reasoning, capabilities, tool_policy, preferred_tools
            ),
        },
        {"role": "user", "content": query},
    ]
    return {"model": model_id, "messages": messages, "temperature": 0.2}


def _extract_model_id(response: ModelsResponse) -> str:
    """Extract first model id from models response."""
    data = response.get("data")
    if not data:
        raise RuntimeError(
            "Сервер запущен, но список моделей пуст.\n"
            "Загрузите модель в LM Studio и включите Local Server."
        )
    model_id = data[0].get("id")
    if not model_id:
        raise RuntimeError("Не удалось определить id модели из /v1/models.")
    return model_id


def _parse_models_response(payload: dict[str, object]) -> ModelsResponse:
    """Convert raw payload to typed models response."""
    raw_data = payload.get("data")
    if isinstance(raw_data, list):
        models: list[ModelItem] = []
        for item in raw_data:
            if isinstance(item, dict):
                model_id = item.get("id")
                if isinstance(model_id, str):
                    models.append({"id": model_id})
                else:
                    models.append({})
            else:
                models.append({})
        return {"data": models}
    return {}


def _parse_chat_response(payload: dict[str, object]) -> ChatCompletionsResponse:
    """Convert raw payload to typed chat response."""
    raw_choices = payload.get("choices")
    if not isinstance(raw_choices, list):
        return {}
    choices: list[ChoiceItem] = []
    for raw_choice in raw_choices:
        if not isinstance(raw_choice, dict):
            choices.append({})
            continue
        raw_message = raw_choice.get("message")
        if not isinstance(raw_message, dict):
            choices.append({})
            continue
        raw_content = raw_message.get("content")
        if isinstance(raw_content, str):
            choices.append({"message": {"content": raw_content}})
        else:
            choices.append({"message": {}})
    return {"choices": choices}


def _extract_content(response: ChatCompletionsResponse) -> str:
    """Extract assistant content from chat completion response."""
    choices = response.get("choices")
    if not choices:
        raise RuntimeError("API вернул пустой ответ (нет choices).")
    message = choices[0].get("message")
    if not message:
        raise RuntimeError("API вернул пустой текст ответа.")
    content = (message.get("content") or "").strip()
    if not content:
        raise RuntimeError("API вернул пустой текст ответа.")
    return content


def get_model_id() -> str:
    """Fetch selected model id from local API."""
    try:
        response = request_json("GET", f"{BASE_URL}{MODELS_PATH}", timeout=2.5)
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError(
            "Локальный API недоступен на http://127.0.0.1:1234.\n"
            "Запустите сервер LM Studio и повторите попытку."
        ) from exc
    return _extract_model_id(_parse_models_response(response))


def generate_answer(
    *,
    query: str,
    model_id: str,
    reasoning: bool,
    capabilities: Capabilities,
    tool_policy: ToolPolicy,
    preferred_tools: list[str] | None = None,
) -> str:
    """Generate command or reasoning answer from chat completions."""
    payload = _build_chat_payload(
        query, model_id, reasoning, capabilities, tool_policy, preferred_tools
    )
    try:
        response = request_json(
            "POST", f"{BASE_URL}{CHAT_PATH}", payload=payload, timeout=30.0
        )
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError(
            "Ошибка запроса к /v1/chat/completions.\n"
            "Проверьте, что LM Studio Local Server запущен и доступен."
        ) from exc
    return _extract_content(_parse_chat_response(response))


def repair_command(
    *,
    query: str,
    model_id: str,
    capabilities: Capabilities,
    tool_policy: ToolPolicy,
    reason: str,
    preferred_tools: list[str] | None = None,
) -> str:
    """Request repaired command constrained by capabilities and policy."""
    policy_instruction = (
        "Prefer modern tools when available; fallback to baseline tools when modern tools are unavailable."
        if tool_policy == "prefer"
        else "Strict modern mode: for mapped commands use modern tools only. If required modern tool is missing, output exactly: ERROR_STRICT_MISSING_TOOL"
    )
    messages: list[ChatMessage] = [
        {
            "role": "system",
            "content": (
                "Return exactly one macOS shell command in one line. "
                "ASCII only. No explanations, no markdown.\n\n"
                f"{format_capabilities_block(capabilities, tool_policy, preferred_tools)}\n"
                f"{policy_instruction}"
            ),
        },
        {"role": "user", "content": f"User request: {query}\nFix reason: {reason}"},
    ]
    payload: dict[str, object] = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 120,
    }
    response = request_json(
        "POST", f"{BASE_URL}{CHAT_PATH}", payload=payload, timeout=20.0
    )
    return _extract_content(_parse_chat_response(response))


def _parse_validation_text(text: str) -> ValidationResult:
    """Parse validator response to typed ValidationResult."""
    normalized = text.strip()
    if normalized == "VALID":
        return {"is_valid": True, "reason": ""}
    if normalized.startswith("INVALID:"):
        reason = normalized.removeprefix("INVALID:").strip()
        return {"is_valid": False, "reason": reason}
    return {"is_valid": False, "reason": "Валидатор вернул неожиданный формат ответа."}


def validate_terminal_command(
    *,
    query: str,
    command: str,
    model_id: str,
    capabilities: Capabilities,
    tool_policy: ToolPolicy,
) -> ValidationResult:
    """Validate command with an additional LLM request."""
    messages: list[ChatMessage] = [
        {
            "role": "system",
            "content": (
                "You validate shell commands for macOS terminal usage. "
                "Respond with exactly one line in one of two formats: "
                "VALID or INVALID: <reason>.\n\n"
                f"{format_capabilities_block(capabilities, tool_policy)}"
            ),
        },
        {"role": "user", "content": f"User request: {query}\nCommand: {command}"},
    ]
    payload: dict[str, object] = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 40,
    }
    response = request_json(
        "POST", f"{BASE_URL}{CHAT_PATH}", payload=payload, timeout=20.0
    )
    raw = _extract_content(_parse_chat_response(response))
    return _parse_validation_text(raw)
