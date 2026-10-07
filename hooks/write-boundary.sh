#!/usr/bin/env bash
# facts-and-figures write-boundary guard — a Claude Code PreToolUse hook.
#
# The run marker always lives at <project>/facts-and-figures-out/.active,
# so the hook can find it without environment coordination. While it
# exists, Write/Edit/MultiEdit/NotebookEdit calls targeting anything
# outside the proposal directory are denied; without it the hook is inert
# and never interferes with ordinary editing sessions. There is no
# scratch allowance: the protocol authors new files only in the proposal
# directory, shell-level temp files are not intercepted anyway, and a
# pipeline input living under /tmp is still an author file.
#
# When the author named a different proposal directory, the marker file's
# single line carries that directory's path (relative to the project), and
# the hook guards it; the FACTS_AND_FIGURES_OUT environment variable is
# honored as a fallback for launches configured that way. A proposal
# directory that equals or contains the project is rejected — it would
# whitelist the author's tree — as is one reached through a symlink.
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
import json, os, stat, sys

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool = payload.get("tool_name", "")
if tool not in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    sys.exit(0)

# prefer the root whose marker exists: in a linked worktree the
# CLAUDE_PROJECT_DIR environment variable stays at the original checkout
# while the session works in — and creates its marker in — the worktree
# the payload cwd names; judging only the original root would leave the
# worktree manuscript unguarded
candidates = []
for c in (os.environ.get("CLAUDE_PROJECT_DIR") or "", payload.get("cwd") or ""):
    if not c:
        continue
    c = os.path.realpath(c)
    if c not in candidates:
        candidates.append(c)
if not candidates:
    candidates.append(os.path.realpath(os.getcwd()))
project = candidates[0]
for c in candidates:
    if os.path.lexists(os.path.join(c, "facts-and-figures-out", ".active")):
        project = c
        break
marker = os.path.join(project, "facts-and-figures-out", ".active")

tool_input = payload.get("tool_input") or {}
target = tool_input.get("file_path") or tool_input.get("notebook_path")
if not target:
    sys.exit(0)

cwd = payload.get("cwd") or project
lexical = os.path.normpath(os.path.join(cwd, os.path.expanduser(target)))
resolved = os.path.realpath(lexical)


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


# lexists: a marker that is a broken symlink still arms the guard — with
# exists() a dangling link would read as absent, the hook would go inert,
# and the write that recreates the marker could follow the link to create
# an author file outside the proposal directory
if not os.path.lexists(marker):
    # inert without the marker — except for the one write the protocol
    # makes while unarmed, the marker bootstrap itself: that write must
    # resolve to the marker path, or a default directory that is already
    # a symlink routes the marker creation into an author directory. The
    # check covers both spellings — the marker path itself, and a write
    # addressed straight at the redirect target it resolves to — and runs
    # against EVERY candidate root, since with no marker anywhere the
    # selected project is the environment root while the bootstrap may
    # target the worktree the payload cwd names
    for c in candidates:
        cm = os.path.join(c, "facts-and-figures-out", ".active")
        cm_real = os.path.realpath(cm)
        if (lexical == cm or resolved == cm_real) and cm_real != cm:
            deny(
                "facts-and-figures write boundary: the marker path {m} does not "
                "resolve to itself — facts-and-figures-out is a symlink, so creating "
                "the run marker there would land outside the proposal directory. "
                "Replace facts-and-figures-out with a real directory first.".format(m=cm)
            )
    sys.exit(0)

try:
    # the marker content is trusted only from a plain, singly linked
    # regular file at the marker path itself (lstat, not stat): a marker
    # symlinked or hard-linked to another file carries planted content
    # that would re-aim the proposal root at an author subtree, and a
    # FIFO would block the read, hanging every guarded write
    marker_st = os.lstat(marker)
    if not stat.S_ISREG(marker_st.st_mode) or marker_st.st_nlink > 1:
        raise OSError("marker is not a plain regular file")
    with open(marker) as f:
        named = f.readline().strip()
except Exception:
    named = ""
# a marker line carrying an embedded NUL or absurd length is planted
# garbage: fall back to the default proposal directory instead of
# crashing on path resolution — Claude Code treats a hook error as
# non-blocking and would let the intercepted write through
if "\x00" in named or len(named) > 4096:
    named = ""
out_dir = named or os.environ.get("FACTS_AND_FIGURES_OUT", "") or "facts-and-figures-out"
proposal_lexical = os.path.normpath(os.path.join(project, out_dir))
proposal = os.path.realpath(proposal_lexical)


def under(path, root):
    return path == root or path.startswith(root + os.sep)


# a hard link shares its inode: a proposal file linked to the manuscript
# keeps its realpath under the proposal while a write through it would
# truncate the manuscript — the inode route the symlink checks cannot see
def multi_linked(path):
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and st.st_nlink > 1


# a directory is a safe allowance only if it neither equals nor contains
# the project, where a path like ".." would whitelist the whole tree
def safe_root(cand):
    return cand != project and not under(project, cand)


# the proposal allowance must also resolve to its own lexical path: a
# proposal root that is itself a symlink (facts-and-figures-out -> data)
# would launder every generated file into the author directory it points
# at, with safe_root none the wiser
proposal_safe = safe_root(proposal) and proposal == proposal_lexical

if lexical == marker or resolved == marker:
    # the marker is read-only while a run is armed: it is created before
    # the first command, carrying any custom proposal directory as its
    # single line (the unarmed branch above validates that write), and it
    # is removed with the run at teardown. A guarded tool rewriting it
    # mid-run would re-aim the write boundary itself — name data as the
    # proposal directory, then edit the dataset through the very tools
    # this hook guards. Judged on the resolved path too: an alias symlink
    # planted in the proposal directory must not reach the marker past
    # the lexical check
    deny(
        "facts-and-figures write boundary: the run marker {m} is read-only while "
        "a run is active. It is created before the first command and removed at "
        "teardown; a different proposal directory is named at creation, not by "
        "rewriting the marker mid-run.".format(m=marker)
    )

# the one allowance: a write that RESOLVES inside a safe proposal
# directory. Judging the resolved path defeats symlinks in either
# direction (a repo path leading out, a proposal path leading back in),
# and there is no scratch exemption — the protocol authors new files only
# in the proposal directory, and a disjoint /tmp root would have
# whitelisted an author input that happens to live there
if proposal_safe and under(resolved, proposal) and not multi_linked(resolved):
    sys.exit(0)

deny(
    "facts-and-figures write boundary: a run is active (marker {m}) and {t} is outside "
    "the proposal directory {p}. The skill never edits the manuscript, data, figures, or "
    "analysis code; write generated work under the proposal directory instead. If no run "
    "is actually in progress, remove the marker file to disarm this guard.".format(
        m=marker, t=resolved, p=proposal)
)
'
