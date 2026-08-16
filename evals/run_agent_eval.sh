#!/usr/bin/env bash
# Agent-in-the-loop eval for the facts-and-figures skill.
#
# Prepares two scratch workspaces from the toy-paper fixture — one intact,
# one with the dataset removed (the gate case) — installs the skill and the
# write-boundary hook into each, runs Claude Code headless when the `claude`
# CLI is available, and grades the resulting reports with grade_report.py.
# Without the CLI it prepares the workspaces and prints the commands to run.
#
# The workspaces receive the fixture and the skill's runtime files ONLY —
# never this evals/ directory, which contains the answer key.
#
# Usage: evals/run_agent_eval.sh [workdir]

set -euo pipefail

EVALS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$EVALS_DIR")"
WORK="${1:-$(mktemp -d /tmp/fnf-eval.XXXXXX)}"
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
            "command": "$CLAUDE_PROJECT_DIR/.claude/skills/facts-and-figures/hooks/write-boundary.sh"
          }
        ]
      }
    ]
  }
}
JSON
}

prepare verify
prepare gated
rm "$WORK/gated/data/workers.csv"

echo "workspaces prepared under $WORK"

# Headless runs cannot answer permission prompts, so Bash is pre-approved:
# the workspace is scratch, the fixture synthetic, and the write-boundary
# hook still guards file edits. acceptEdits covers the run marker.
CLAUDE_ARGS=(--permission-mode acceptEdits --allowedTools Bash)

if command -v claude >/dev/null 2>&1; then
    rc=0

    # reports are saved OUTSIDE the workspaces: a pre-created report file
    # inside one is an artifact the agent under eval will notice and mention
    echo "== running verification case =="
    (cd "$WORK/verify" && claude -p "$PROMPT" "${CLAUDE_ARGS[@]}") | tee "$WORK/verify-report.md"
    python3 "$EVALS_DIR/grade_report.py" "$WORK/verify-report.md" "$EVALS_DIR/expected.json" || rc=1

    echo "== running gate case =="
    (cd "$WORK/gated" && claude -p "$PROMPT" "${CLAUDE_ARGS[@]}") | tee "$WORK/gated-report.md"
    python3 "$EVALS_DIR/grade_report.py" --gate "$WORK/gated-report.md" "$EVALS_DIR/expected.json" || rc=1

    exit "$rc"
else
    cat <<EOF
claude CLI not found; run each case yourself, saving the agent's report:

  cd $WORK/verify && claude -p "$PROMPT" ${CLAUDE_ARGS[*]} > $WORK/verify-report.md
  python3 $EVALS_DIR/grade_report.py $WORK/verify-report.md

  cd $WORK/gated && claude -p "$PROMPT" ${CLAUDE_ARGS[*]} > $WORK/gated-report.md
  python3 $EVALS_DIR/grade_report.py --gate $WORK/gated-report.md
EOF
fi
