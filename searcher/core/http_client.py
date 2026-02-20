"""HTTP client primitives based on Python stdlib."""

import json
import urllib.request


def request_json(
    method: str,
    url: str,
    payload: dict[str, object] | None = None,
    timeout: float = 4.0,
) -> dict[str, object]:
    """Send HTTP request and parse JSON response body."""
    data: bytes | None = None
    headers: dict[str, str] = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    if not raw:
        return {}
    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        return parsed
    return {}
