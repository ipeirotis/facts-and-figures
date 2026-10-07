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

# hash every workspace file outside the proposal directory and .claude, so
# a run that writes into the author's tree (results/, edited data) or
# leaves its marker armed fails the eval behaviorally, not just on paper
snapshot() {
    (cd "$1" && find . \( -path ./.claude -o -path ./facts-and-figures-out \) -prune \
        -o -type f -print0 | sort -z | xargs -0 sha256sum)
}

workspace_clean() {
    local ws="$1" pre_file="$2" label="$3" bad=0
    if [ -e "$ws/facts-and-figures-out/.active" ]; then
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
# hook still guards file edits. acceptEdits covers the run marker.
CLAUDE_ARGS=(--permission-mode acceptEdits --allowedTools Bash)

if command -v claude >/dev/null 2>&1; then
    echo "== running verification case =="
    (cd "$WORK/verify" && claude -p "$PROMPT" "${CLAUDE_ARGS[@]}") | tee "$WORK/verify-report.md"
    echo "== running gate case =="
    (cd "$WORK/gated" && claude -p "$PROMPT" "${CLAUDE_ARGS[@]}") | tee "$WORK/gated-report.md"
    grade_all
    exit "$?"
else
    cat <<EOF
claude CLI not found; run each case yourself, saving the agent's report,
then apply the full grading and workspace-integrity suite:

  cd $WORK/verify && claude -p "$PROMPT" ${CLAUDE_ARGS[*]} > $WORK/verify-report.md
  cd $WORK/gated && claude -p "$PROMPT" ${CLAUDE_ARGS[*]} > $WORK/gated-report.md
  $EVALS_DIR/run_agent_eval.sh --grade-only $WORK
EOF
fi
