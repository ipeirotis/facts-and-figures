#!/usr/bin/env bash
# facts-and-figures write-boundary guard — a Claude Code PreToolUse hook.
#
# While a facts-and-figures run is active (the run marker
# <proposal-dir>/.active exists), deny Write/Edit/MultiEdit/NotebookEdit
# calls that target anything outside the proposal directory or the system
# temp directory. Without the marker the hook is inert, so it never
# interferes with ordinary editing sessions in the same repository.
#
# This is a guardrail, not a sandbox: writes made through shell commands
# (Bash redirects, `sed -i`, the pipeline itself) are not intercepted. The
# skill's master rule remains the primary control; this hook catches the
# most common violation vector and restates the protocol at the moment of
# violation.
#
# The proposal directory defaults to facts-and-figures-out/ under the
# project root; set FACTS_AND_FIGURES_OUT to the directory the author named
# if it differs. Registration instructions live in README.md.
#
# Fail-open by design: missing python3, unparseable input, or a call with
# no file path allows the tool call rather than breaking the session.

set -u

FNF_HOOK_INPUT="$(cat)"
export FNF_HOOK_INPUT

command -v python3 >/dev/null 2>&1 || exit 0

exec python3 - <<'PY'
import json, os, sys

try:
    payload = json.loads(os.environ.get("FNF_HOOK_INPUT") or "{}")
except Exception:
    sys.exit(0)

tool = payload.get("tool_name", "")
if tool not in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    sys.exit(0)

project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
out_dir = os.environ.get("FACTS_AND_FIGURES_OUT", "facts-and-figures-out")
proposal = os.path.realpath(os.path.join(project, out_dir))
marker = os.path.join(proposal, ".active")

if not os.path.exists(marker):
    sys.exit(0)

tool_input = payload.get("tool_input") or {}
target = tool_input.get("file_path") or tool_input.get("notebook_path")
if not target:
    sys.exit(0)

cwd = payload.get("cwd") or project
resolved = os.path.realpath(os.path.join(cwd, os.path.expanduser(target)))

allowed = [proposal, os.path.realpath("/tmp")]
tmpdir = os.environ.get("TMPDIR")
if tmpdir:
    allowed.append(os.path.realpath(tmpdir))

for root in allowed:
    if resolved == root or resolved.startswith(root + os.sep):
        sys.exit(0)

reason = (
    "facts-and-figures write boundary: a run is active (marker {m}) and {t} is outside "
    "the proposal directory {p}. The skill never edits the author's manuscript, data, "
    "figures, or analysis code; write generated work under the proposal directory instead. "
    "If no run is actually in progress, remove the marker file to disarm this guard."
).format(m=marker, t=resolved, p=proposal)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }
}))
sys.exit(0)
PY
