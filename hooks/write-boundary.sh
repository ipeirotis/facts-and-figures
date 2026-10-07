#!/usr/bin/env bash
# facts-and-figures write-boundary guard — a Claude Code PreToolUse hook.
#
# The run marker always lives at <project>/facts-and-figures-out/.active,
# so the hook can find it without environment coordination. While it
# exists, Write/Edit/MultiEdit/NotebookEdit calls targeting anything
# outside the proposal directory or a scratch root are denied; without it
# the hook is inert and never interferes with ordinary editing sessions.
#
# When the author named a different proposal directory, the marker file's
# single line carries that directory's path (relative to the project), and
# the hook guards it; the FACTS_AND_FIGURES_OUT environment variable is
# honored as a fallback for launches configured that way. A proposal
# directory that equals or contains the project is rejected — it would
# whitelist the author's tree — as is a scratch root that is not fully
# disjoint from the project.
#
# The payload is parsed straight from stdin: a Write payload carries the
# whole file content, and routing it through an environment variable or an
# argument would fail with E2BIG on large writes, making the hook fail
# open exactly when it matters.
#
# This is a guardrail, not a sandbox: writes made through shell commands
# (Bash redirects, `sed -i`, the pipeline itself) are not intercepted. The
# skill's master rule remains the primary control; this hook catches the
# most common violation vector and restates the protocol at the moment of
# violation.
#
# Fail-open by design: missing python3, unparseable input, or a call with
# no file path allows the tool call rather than breaking the session.

set -u

command -v python3 >/dev/null 2>&1 || exit 0

exec python3 -c '
import json, os, sys

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool = payload.get("tool_name", "")
if tool not in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    sys.exit(0)

project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
project = os.path.realpath(project)
default_dir = os.path.realpath(os.path.join(project, "facts-and-figures-out"))
marker = os.path.join(default_dir, ".active")

if not os.path.exists(marker):
    sys.exit(0)

try:
    with open(marker) as f:
        named = f.readline().strip()
except Exception:
    named = ""
out_dir = named or os.environ.get("FACTS_AND_FIGURES_OUT", "") or "facts-and-figures-out"
proposal = os.path.realpath(os.path.join(project, out_dir))

tool_input = payload.get("tool_input") or {}
target = tool_input.get("file_path") or tool_input.get("notebook_path")
if not target:
    sys.exit(0)

cwd = payload.get("cwd") or project
lexical = os.path.normpath(os.path.join(cwd, os.path.expanduser(target)))
resolved = os.path.realpath(lexical)


def under(path, root):
    return path == root or path.startswith(root + os.sep)


# a directory is a safe allowance only if it neither equals nor contains
# the project, where a path like ".." would whitelist the whole tree
def safe_root(cand):
    return cand != project and not under(project, cand)


scratch_roots = []
for scratch in ("/tmp", os.environ.get("TMPDIR") or ""):
    if not scratch:
        continue
    root = os.path.realpath(scratch)
    # a scratch root must be disjoint from the project: one containing the
    # project would whitelist the checkout, one inside it (TMPDIR pointed
    # at data/) would whitelist author files
    if (project == root or under(project, root) or under(root, project)):
        continue
    scratch_roots.append(root)

if resolved == os.path.realpath(marker) or lexical == marker:
    sys.exit(0)

if under(lexical, project):
    # a path addressed inside the repository is judged as addressed: a
    # symlink leading into /tmp must not let the scratch exemption rewrite
    # author data through its repository path
    lexical_proposal = os.path.normpath(os.path.join(project, out_dir))
    if safe_root(lexical_proposal) and under(lexical, lexical_proposal):
        sys.exit(0)
    if safe_root(proposal) and under(resolved, proposal):
        sys.exit(0)
else:
    allowed = ([proposal] if safe_root(proposal) else []) + scratch_roots
    for root in allowed:
        if under(resolved, root):
            sys.exit(0)

reason = (
    "facts-and-figures write boundary: a run is active (marker {m}) and {t} is outside "
    "the proposal directory {p}. The skill never edits the manuscript, data, figures, or "
    "analysis code; write generated work under the proposal directory instead. If no run "
    "is actually in progress, remove the marker file to disarm this guard."
).format(m=marker, t=resolved, p=proposal)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }
}))
sys.exit(0)
'
