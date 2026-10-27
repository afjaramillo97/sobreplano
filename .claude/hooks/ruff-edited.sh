#!/usr/bin/env bash
# PostToolUse hook: run ruff on the Python file that was just edited.
# Never blocks the edit: any failure to read the path exits 0.

file=$(jq -r '.tool_input.file_path // empty' 2>/dev/null) || exit 0

[[ "$file" == *.py ]] || exit 0
[[ -f "$file" ]] || exit 0

uv run ruff check --fix --quiet "$file" || true
uv run ruff format --quiet "$file" || true
exit 0
