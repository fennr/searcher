BASE_URL = "http://127.0.0.1:1234"
MODELS_PATH = "/v1/models"
CHAT_PATH = "/v1/chat/completions"

MODERN_TOOLS = ("bat", "rg", "fd", "eza", "dust", "zoxide")
BASELINE_TOOLS = (
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
PREFERRED_TOOL_MAP = {
    "cat": "bat",
    "grep": "rg",
    "find": "fd",
    "ls": "eza",
    "du": "dust",
}
