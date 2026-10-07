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
# candidates feed marker selection and bootstrap validation; roots
# additionally constrain the proposal allowance below. The environment
# project dir and every marker or .git ancestor are roots; the RAW
# payload cwd is a candidate but NOT a root — a session that has
# entered the proposal directory must not have that directory rejected
# as a proposal for containing the cwd
candidates = []
roots = []
env_c = os.environ.get("CLAUDE_PROJECT_DIR") or ""
cwd_c = payload.get("cwd") or ""
if not env_c and not cwd_c:
    cwd_c = os.getcwd()
for raw, is_root in ((env_c, True), (cwd_c, False)):
    if not raw:
        continue
    c = os.path.realpath(raw)
    above = roots_above(c)
    for cand in [c] + above:
        if cand not in candidates:
            candidates.append(cand)
    for r in ([c] if is_root else []) + above:
        if r not in roots:
            roots.append(r)
if not roots:
    roots = candidates[:1]
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


def under(path, root):
    return path == root or path.startswith(root + os.sep)


# the one write the protocol makes before arming: the marker bootstrap.
# That write must resolve to the canonical marker path — a default
# directory that is already a symlink routes the creation into an author
# directory and is denied — and a custom directory named as the content
# line must start fresh: pointing it at an EXISTING, NON-EMPTY directory
# would hand pre-existing author content (data/, analysis/) to the write
# allowance. Validated by either spelling, since an alias symlink to the
# REAL marker directory resolves to the canonical marker too. Returns
# True when this write IS a valid bootstrap for one of cands
def bootstrap_checks(cands):
    hit = False
    for c in cands:
        cm = os.path.join(c, "facts-and-figures-out", ".active")
        cm_real = os.path.realpath(cm)
        if (lexical == cm or resolved == cm_real) and cm_real != cm:
            deny(
                "facts-and-figures write boundary: the marker path {m} does not "
                "resolve to itself — facts-and-figures-out is a symlink, so creating "
                "the run marker there would land outside the proposal directory. "
                "Replace facts-and-figures-out with a real directory first.".format(m=cm)
            )
        if cm_real != cm or (lexical != cm and resolved != cm):
            continue
        hit = True
        lines = str(tool_input.get("content") or "").splitlines()
        line = lines[0].strip() if lines else ""
        if not line or "\x00" in line or len(line) > 4096:
            continue
        # ~ expands as it does for write targets: an author naming
        # ~/fnf-out means the home directory, not a literal ~ under the
        # project — unexpanded, the freshness check would inspect the
        # wrong directory and every real write would be denied
        named_lex = os.path.normpath(os.path.join(c, os.path.expanduser(line)))
        named_dir = os.path.realpath(named_lex)
        # a custom path reached through a symlink is refused at arming,
        # exactly as the armed guard would refuse its writes — allowing
        # the bootstrap would leave the run stuck behind a marker the
        # hook itself approved
        if named_dir != named_lex:
            deny(
                "facts-and-figures write boundary: this marker names {l} as the "
                "proposal directory, but that path resolves to {d} through a "
                "symlink. Name the real directory instead.".format(
                    l=named_lex, d=named_dir)
            )
        if os.path.exists(named_dir) and not os.path.isdir(named_dir):
            deny(
                "facts-and-figures write boundary: this marker names {d} as the "
                "proposal directory, but that path is an existing file, not a "
                "directory. Arming it would leave the run stuck behind a guard "
                "that can allow nothing: name a new or empty directory "
                "instead.".format(d=named_dir)
            )
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
    return hit


# lexists: a marker that is a broken symlink still arms the guard — with
# exists() a dangling link would read as absent, the hook would go inert,
# and the write that recreates the marker could follow the link to create
# an author file outside the proposal directory
if not os.path.lexists(marker):
    # inert without the marker — except for the bootstrap, validated
    # against EVERY candidate root, since with no marker anywhere the
    # selected project is the environment root while the bootstrap may
    # target the worktree the payload cwd names
    bootstrap_checks(candidates)
    sys.exit(0)

# the documented parallel mode runs one checkout per run: with an armed
# original checkout and a stale CLAUDE_PROJECT_DIR, the second checkout
# must still be able to create its OWN marker. A write targeting the
# canonical marker path of an unmarked candidate root that is DISJOINT
# from every marked root is that bootstrap — validated by the same
# rules — not an outside write of the armed run. Disjointness keeps the
# armed tree closed: a nested or enclosing directory of a marked root
# never qualifies
cross = [c for c in candidates
         if not os.path.lexists(os.path.join(c, "facts-and-figures-out", ".active"))
         and all(not under(c, m) and not under(m, c) for m in marked)]
if bootstrap_checks(cross):
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
# the same ~ expansion the bootstrap applies — the armed path must guard
# the directory the author actually named
proposal_lexical = os.path.normpath(os.path.join(project, os.path.expanduser(out_dir)))
proposal = os.path.realpath(proposal_lexical)


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
# contains ANY root, not just the selected project: a planted ancestor
# marker naming the checkout directory as its proposal line would
# otherwise whitelist the entire checkout — the checkout is a root,
# but it is not the selected project once the ancestor marker wins the
# selection. Judged against roots, not raw candidates, so a cwd inside
# the active proposal directory does not reject that very proposal
def safe_root(cand):
    return all(cand != r and not under(r, cand) for r in roots)


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

# a custom-named proposal directory holding anything OLDER than the marker
# is stale or planted: the bootstrap only ever blesses a fresh directory,
# and a run creates its marker before every file it writes there, so
# pre-existing content behind the name means a plain regular marker —
# the one planted form the link checks above cannot see — was aimed at
# author files (content line "data" re-aiming the allowance at the
# dataset). Compared by inode change time, which userland cannot
# backdate; an unlistable directory counts as stale, matching the
# bootstrap; the default directory is exempt because its kept companion
# from an earlier run legitimately predates a new marker
default_proposal = os.path.realpath(os.path.join(project, "facts-and-figures-out"))
if named and proposal != default_proposal and os.path.isdir(proposal):
    stale = False
    try:
        for e in os.listdir(proposal):
            if os.lstat(os.path.join(proposal, e)).st_ctime_ns < marker_st.st_ctime_ns:
                stale = True
                break
    except OSError:
        stale = True
    if stale:
        deny(
            "facts-and-figures write boundary: the run marker names {d} as the "
            "proposal directory, but that directory holds content older than the "
            "marker itself. A proposal directory starts fresh and fills only after "
            "its marker exists, so this marker is stale or planted; remove {m} and "
            "start the run again.".format(d=proposal, m=marker)
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
