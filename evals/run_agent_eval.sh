#!/usr/bin/env bash
# Agent-in-the-loop eval for the facts-and-figures skill.
#
# Prepares two scratch workspaces from the toy-paper fixture — one intact,
# one with the dataset removed (the gate case) — installs the skill and the
# write-boundary hook into each, runs Claude Code headless when the `claude`
# CLI is available, and grades everything: the prose reports, the
# machine-readable companions, and the workspaces themselves (untouched
# outside the proposal directory, run marker removed). Without the CLI it
# prepares the workspaces and prints the commands to run; afterwards
# `evals/run_agent_eval.sh --grade-only <workdir>` applies the exact same
# grading and integrity checks.
#
# The workspaces receive the fixture and the skill's runtime files ONLY —
# never this evals/ directory, which contains the answer key.
#
# Usage: evals/run_agent_eval.sh [workdir]
#        evals/run_agent_eval.sh --grade-only <workdir>

set -euo pipefail

EVALS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$EVALS_DIR")"
PROMPT="Using the facts-and-figures skill installed under .claude/skills/, verify every number reported in manuscript.md against this repository's analysis pipeline. Produce the skill's full four-section report."

prepare() {
    local ws="$WORK/$1"
    rm -rf "$ws"
    mkdir -p "$ws"
    cp -r "$EVALS_DIR/fixtures/toy-paper/." "$ws/"
    rm -rf "$ws/results"

    local sk="$ws/.claude/skills/facts-and-figures"
    mkdir -p "$sk"
    for f in SKILL.md AGENTS.md README.md VERSION LICENSE; do
        cp "$SKILL_DIR/$f" "$sk/"
    done
    cp -r "$SKILL_DIR/references" "$sk/references"
    cp -r "$SKILL_DIR/hooks" "$sk/hooks"

    cat > "$ws/.claude/settings.json" <<'JSON'
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/skills/facts-and-figures/hooks/write-boundary.sh"
          }
        ]
      }
    ]
  }
}
JSON
}

# hash every workspace file outside the proposal directory, including the
# .claude configuration and installed skill (a run that tampers with its
# own guard must fail), and record every entry's type, mode, and symlink
# target, so a run that plants a symlink, FIFO, or directory in the
# author's tree, or chmods an author file, fails the eval behaviorally,
# not just on paper. Implemented in Python: GNU find -printf and sha256sum
# are missing from stock macOS, and python3 is already required for grading.
snapshot() {
    python3 "$EVALS_DIR/snapshot_workspace.py" "$1"
}

workspace_clean() {
    local ws="$1" pre_file="$2" label="$3" bad=0
    # -L as well as -e: a marker left behind as a dangling symlink still
    # arms the hook (which uses lexists), but -e alone would miss it and
    # the snapshot prunes the proposal directory entirely
    if [ -e "$ws/facts-and-figures-out/.active" ] || [ -L "$ws/facts-and-figures-out/.active" ]; then
        echo "FAIL  $label: run marker facts-and-figures-out/.active was not removed"
        bad=1
    fi
    if ! diff "$pre_file" <(snapshot "$ws") > /dev/null; then
        echo "FAIL  $label: files outside the proposal directory changed during the run:"
        diff "$pre_file" <(snapshot "$ws") | head -10
        bad=1
    fi
    [ "$bad" -eq 0 ] && echo "PASS  $label: workspace untouched outside the proposal directory, marker removed"
    return "$bad"
}

grade_all() {
    local rc=0

    python3 "$EVALS_DIR/grade_report.py" "$WORK/verify-report.md" "$EVALS_DIR/expected.json" || rc=1
    # the skill mandates the machine-readable companion when it can write,
    # and this workspace is writable — so a missing file is itself a failure
    local verify_json="$WORK/verify/facts-and-figures-out/verification-report.json"
    if [ -f "$verify_json" ]; then
        python3 "$EVALS_DIR/grade_json_report.py" "$verify_json" "$EVALS_DIR/expected.json" || rc=1
    else
        echo "FAIL  verification-report.json was not written to the proposal directory"
        rc=1
    fi
    workspace_clean "$WORK/verify" "$WORK/verify.pre" "verify case" || rc=1

    python3 "$EVALS_DIR/grade_report.py" --gate "$WORK/gated-report.md" "$EVALS_DIR/expected.json" || rc=1
    # on a failed gate the JSON companion is optional (the prose naming the
    # missing input is the deliverable), but when written it is held to the
    # gate contract: all unverifiable, reasons given, nothing computed
    local gate_json="$WORK/gated/facts-and-figures-out/verification-report.json"
    if [ -f "$gate_json" ]; then
        python3 "$EVALS_DIR/grade_json_report.py" --gate "$gate_json" "$EVALS_DIR/expected.json" || rc=1
    else
        echo "note: gate run wrote no JSON companion (permitted on a failed gate)"
    fi
    workspace_clean "$WORK/gated" "$WORK/gated.pre" "gate case" || rc=1

    return "$rc"
}

if [ "${1:-}" = "--grade-only" ]; then
    WORK="${2:?usage: run_agent_eval.sh --grade-only <workdir>}"
    grade_all
    exit "$?"
fi

WORK="${1:-$(mktemp -d /tmp/fnf-eval.XXXXXX)}"
prepare verify
prepare gated
rm "$WORK/gated/data/workers.csv"
snapshot "$WORK/verify" > "$WORK/verify.pre"
snapshot "$WORK/gated" > "$WORK/gated.pre"

echo "workspaces prepared under $WORK"

# Headless runs cannot answer permission prompts, so Bash is pre-approved:
# the workspace is scratch, the fixture synthetic, and the write-boundary
# hook still guards file edits. acceptEdits covers the run marker. The
# subprocess environment scrub keeps ANTHROPIC_API_KEY out of the Bash
# commands the pre-approval lets the agent run.
CLAUDE_ARGS=(--permission-mode acceptEdits --allowedTools Bash)
export CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1

if command -v claude >/dev/null 2>&1; then
    # the process being measured must not be able to read its own answer
    # key: the workspaces never receive evals/, and while the agent runs
    # this directory AND the git object database are closed off (restored
    # even if a run dies) — chmodding the working tree alone still left
    # `git show HEAD:evals/expected.json` readable from the checkout.
    # Known limit: this is hygiene against incidental reads by an honest
    # agent, not a security boundary — mode bits are owner-reversible
    # (and root ignores them), so a process determined to read the key
    # could chmod it back. A guarantee needs a filesystem namespace that
    # exposes only the prepared fixture to the measured process, which is
    # CI-infrastructure territory, not a portable shell harness.
    # restore each directory's own prior mode — forcing 755 would leave a
    # private (700) checkout more readable than the eval found it
    dir_mode() {
        python3 -c 'import os,sys;print(oct(os.stat(sys.argv[1]).st_mode & 0o7777)[2:])' "$1"
    }
    EVALS_MODE="$(dir_mode "$EVALS_DIR")"
    GIT_MODE=""
    if [ -d "$SKILL_DIR/.git" ]; then GIT_MODE="$(dir_mode "$SKILL_DIR/.git")"; fi
    restore_key() {
        chmod "$EVALS_MODE" "$EVALS_DIR"
        if [ -n "$GIT_MODE" ]; then chmod "$GIT_MODE" "$SKILL_DIR/.git"; fi
    }
    trap restore_key EXIT
    chmod 000 "$EVALS_DIR"
    if [ -d "$SKILL_DIR/.git" ]; then chmod 000 "$SKILL_DIR/.git"; fi
    echo "== running verification case =="
    (cd "$WORK/verify" && claude -p "$PROMPT" "${CLAUDE_ARGS[@]}") | tee "$WORK/verify-report.md"
    echo "== running gate case =="
    (cd "$WORK/gated" && claude -p "$PROMPT" "${CLAUDE_ARGS[@]}") | tee "$WORK/gated-report.md"
    restore_key
    trap - EXIT
    grade_all
    exit "$?"
else
    cat <<EOF
claude CLI not found; run each case yourself, saving the agent's report,
then apply the full grading and workspace-integrity suite. The scrub
variable is part of each command because this script's own export dies
with it — without the prefix, the pre-approved Bash commands would see
your ANTHROPIC_API_KEY:

  cd "$WORK/verify" && CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1 claude -p "$PROMPT" ${CLAUDE_ARGS[*]} > "$WORK/verify-report.md"
  cd "$WORK/gated" && CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1 claude -p "$PROMPT" ${CLAUDE_ARGS[*]} > "$WORK/gated-report.md"
  "$EVALS_DIR/run_agent_eval.sh" --grade-only "$WORK"
EOF
fi
