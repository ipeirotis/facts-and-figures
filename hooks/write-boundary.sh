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
# the hook guards it. The marker is the ONLY channel for a custom
# directory: an environment-variable fallback would bypass the
# fresh-directory validation the bootstrap applies to marker content. A
# proposal directory that equals or contains the project is rejected — it
# would whitelist the author's tree — as is one reached through a symlink.
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

# a candidate may be a subdirectory rather than a root: the payload cwd
# follows the session into any directory it changes into, and judging
# the marker against <root>/analysis/facts-and-figures-out would read an
# armed tree as unarmed. EVERY ancestor holding a marker or a .git
# entry (a linked worktree carries .git as a file) is a candidate root:
# keeping only the nearest .git misses the worktree above a nested
# repository during bootstrap, and electing a single marker — nearest
# or outermost — is gameable from whichever side was not elected, so
# all of them are collected and the ambiguity resolves fail-closed in
# the selection and safe_root rules below
def roots_above(p):
    out = []
    cur = p
    while True:
        if (os.path.lexists(os.path.join(cur, "facts-and-figures-out", ".active"))
                or os.path.lexists(os.path.join(cur, ".git"))):
            out.append(cur)
        nxt = os.path.dirname(cur)
        if nxt == cur:
            return out
        cur = nxt


# prefer the root whose marker exists: in a linked worktree the
# CLAUDE_PROJECT_DIR environment variable stays at the original checkout
# while the session works in — and creates its marker in — the worktree
# the payload cwd names; judging only the original root would leave the
# worktree manuscript unguarded. Each path is kept alongside its
# ascended roots rather than replaced by them: a project that is not a
# git repository must not lose its own candidacy to a .git-bearing
# ancestor
candidates = []
for c in (os.environ.get("CLAUDE_PROJECT_DIR") or "", payload.get("cwd") or ""):
    if not c:
        continue
    c = os.path.realpath(c)
    for cand in [c] + roots_above(c):
        if cand not in candidates:
            candidates.append(cand)
if not candidates:
    c = os.path.realpath(os.getcwd())
    for cand in [c] + roots_above(c):
        if cand not in candidates:
            candidates.append(cand)
# with runs armed concurrently in separate checkouts (the documented
# parallel mode), the payload cwd names which run this write belongs
# to: always picking the first marked candidate would judge a worktree
# write by the original checkout, denying the run its own proposal
# directory while allowing it writes into the proposal directory of
# the other run. Prefer the marked root containing the cwd, then the
# first marked root, then the first candidate
cwd_real = os.path.realpath(payload.get("cwd") or os.getcwd())
marked = [c for c in candidates
          if os.path.lexists(os.path.join(c, "facts-and-figures-out", ".active"))]
# among marked roots containing the cwd, the SHALLOWEST wins for the
# same reason the ascent prefers the outermost marker: the nested one
# may be stale or planted, and choosing it would judge the write by a
# marker the outer run does not own
containing = [c for c in marked
              if cwd_real == c or cwd_real.startswith(c + os.sep)]
if containing:
    project = min(containing, key=len)
elif marked:
    project = marked[0]
else:
    project = candidates[0]
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
    # the bootstrap write may name a custom proposal directory as its
    # first line. A name pointing at an EXISTING, NON-EMPTY directory
    # would hand pre-existing author content (data/, analysis/) to the
    # write allowance, so it is refused at creation: the proposal
    # directory starts fresh
    for c in candidates:
        cm = os.path.join(c, "facts-and-figures-out", ".active")
        if lexical != cm or os.path.realpath(cm) != cm:
            continue
        lines = str(tool_input.get("content") or "").splitlines()
        line = lines[0].strip() if lines else ""
        if not line or "\x00" in line or len(line) > 4096:
            continue
        named_dir = os.path.realpath(os.path.normpath(os.path.join(c, line)))
        try:
            occupied = os.path.isdir(named_dir) and bool(os.listdir(named_dir))
        except OSError:
            # an unlistable directory (execute-only modes) may still
            # hold writable files the allowance would cover — an
            # inspection failure counts as occupied, not empty
            occupied = True
        if occupied:
            deny(
                "facts-and-figures write boundary: this marker names {d} as the "
                "proposal directory, but that directory already exists and is not "
                "empty. The proposal directory holds only generated work and starts "
                "fresh: name a new or empty directory (or use the default), never an "
                "existing data, code, or figure directory.".format(d=named_dir)
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
# the marker content is the single channel for a custom directory — an
# environment fallback was dropped because it reached this assignment
# without the fresh-directory validation the bootstrap applies to
# marker content, so FACTS_AND_FIGURES_OUT=data would have handed the
# dataset to the allowance on an empty marker
out_dir = named or "facts-and-figures-out"
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


# a directory is a safe allowance only if it neither equals nor
# contains ANY candidate root, not just the selected project: a planted
# ancestor marker naming the checkout directory as its proposal line
# would otherwise whitelist the entire checkout — the checkout is a
# candidate, but it is not the selected project once the ancestor
# marker wins the selection
def safe_root(cand):
    return all(cand != r and not under(r, cand) for r in candidates)


# the proposal allowance must also resolve to its own lexical path: a
# proposal root that is itself a symlink (facts-and-figures-out -> data)
# would launder every generated file into the author directory it points
# at, with safe_root none the wiser. And it must be a directory or not
# yet exist — a marker naming an existing author FILE would otherwise
# hand that very file to the allowance
proposal_safe = (safe_root(proposal) and proposal == proposal_lexical
                 and (not os.path.exists(proposal) or os.path.isdir(proposal)))

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
