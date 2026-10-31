#!/usr/bin/env bash
# PostToolUse hook: run ruff on the Python or Markdown file that was just edited (ruff formats Python code blocks inside Markdown).
# Never blocks the edit: any failure to read the path exits 0.

file=$(jq -r '.tool_input.file_path // empty' 2>/dev/null) || exit 0

[[ "$file" == *.py || "$file" == *.md ]] || exit 0
[[ -f "$file" ]] || exit 0

# ruff check does not lint Markdown; only format it.
if [[ "$file" == *.py ]]; then
  uv run ruff check --fix --quiet "$file" || true
fi
uv run ruff format --quiet "$file" || true
exit 0
