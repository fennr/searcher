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
DEV_TOOLS = (
    # Rust
    "cargo",
    "rustc",
    "rustup",
    "cargo-clippy",
    "cargo-nextest",
    "cargo-watch",
    "cargo-audit",
    "rustfmt",
    # Python
    "python3",
    "pip",
    "uv",
    "poetry",
    "pytest",
    "ruff",
    "mypy",
    "black",
    # Go
    "go",
    "gofmt",
    "golangci-lint",
    "dlv",
    # Common dev/devops
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
PREFERRED_TOOL_MAP = {
    "cat": "bat",
    "grep": "rg",
    "find": "fd",
    "ls": "eza",
    "du": "dust",
}
