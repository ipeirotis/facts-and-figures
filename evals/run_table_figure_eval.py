#!/usr/bin/env python3
"""Run the table/figure pilot with a locally authenticated Claude Code CLI.

Creates a fresh workspace and a ZIP in Downloads by default. The answer key
is not copied. This collects evidence for grading; it does not grade semantic
correctness. Use --prepare-only to inspect the setup without calling Claude.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import zipfile


REPO = Path(__file__).resolve().parents[1]
TOOLS = "Read,Glob,Grep,Bash,Write,Edit"
PROMPT = (
    "Read .claude/skills/facts-and-figures/SKILL.md and follow that skill. "
    "Verify Table 1 and Figure 1 in manuscript.md against this repository's "
    "existing analysis pipeline. Check numeric labels and actual bar heights "
    "separately, plus group labels, axes, units and caption. Do not edit the "
    "submitted artifacts. Produce the skill's four-section report and numerical "
    "JSON companion. Work only on this supplied paper. Do not access other "
    "directories, search for an answer key or use external services."
)


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def prepare(run):
    workspace = run / "workspace"
    shutil.copytree(REPO / "evals/fixtures/table-figure-paper", workspace)
    skill = workspace / ".claude/skills/facts-and-figures"
    skill.mkdir(parents=True)
    for name in ["SKILL.md", "VERSION", "LICENSE"]:
        shutil.copy2(REPO / name, skill / name)
    for name in ["references", "hooks"]:
        shutil.copytree(REPO / name, skill / name)
    # No repo README, development instructions, eval scripts, key or git objects.
    save(workspace / ".claude/settings.json", {"hooks": {"PreToolUse": [{
        "matcher": "Write|Edit|MultiEdit|NotebookEdit", "hooks": [{
            "type": "command",
            "command": '"$CLAUDE_PROJECT_DIR"/.claude/skills/facts-and-figures/hooks/write-boundary.sh'
        }]
    }]}})
    (run / "prompt.txt").write_text(PROMPT + "\n", encoding="utf-8")
    return workspace


def inventory(workspace):
    proc = subprocess.run([sys.executable, "-B", str(REPO / "evals/snapshot_workspace.py"),
                           str(workspace)], capture_output=True, text=True, check=True)
    return proc.stdout


def result_from_trace(path):
    result, init = None, None
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "system" and event.get("subtype") == "init":
                init = event
            if event.get("type") == "result":
                result = event
    return result, init


def bundle(run):
    target = run.with_suffix(".zip")
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run.rglob("*")):
            if path.is_symlink():
                continue
            if path.is_file():
                archive.write(path, str(Path(run.name) / path.relative_to(run)))
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="new directory; must not already exist")
    parser.add_argument("--model", default="sonnet", help="Claude model alias/id (default: sonnet)")
    parser.add_argument("--claude", default="claude", help="Claude Code executable")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = (args.output_dir or Path.home() / "Downloads" /
           f"facts-and-figures-run-{stamp}-{uuid.uuid4().hex[:6]}").resolve()
    if run.exists() or run.with_suffix(".zip").exists():
        parser.error("output directory/ZIP already exists; choose a fresh path")
    if run == REPO or REPO in run.parents:
        parser.error("output must be outside the skill checkout")
    run.mkdir(parents=True)
    workspace = prepare(run)
    before = inventory(workspace)
    (run / "workspace-before.txt").write_text(before, encoding="utf-8")
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                            capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                           capture_output=True, text=True)
    metadata = {"status": "prepared", "grading": "pending review",
                "started_utc": datetime.now(timezone.utc).isoformat(),
                "skill_commit": commit.stdout.strip(),
                "checkout_dirty": bool(dirty.stdout.strip()),
                "requested_model": args.model,
                "input_sha256": {str(p.relative_to(workspace)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in workspace.rglob("*") if p.is_file()},
                "isolation": "Fresh workspace and key excluded; not an OS sandbox. Bash can access this user's files.",
                "cost_note": "Any Claude-reported USD value is an estimate, not the subscription charge."}
    save(run / "run-metadata.json", metadata)
    if args.prepare_only:
        print(f"Prepared only; Claude was NOT run. Workspace: {workspace}")
        print(f"ZIP: {bundle(run)}")
        return 0
    executable = shutil.which(args.claude)
    exit_code = 2
    start = time.monotonic()
    try:
        if not executable:
            raise RuntimeError("Claude Code not found. Install it/sign in locally, then rerun in a fresh directory.")
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, check=True)
        metadata["claude_version"] = version.stdout.strip()
        # Keep OAuth/keychain login. Do not use --bare, which skips subscription auth.
        # Do not forward a shell API key: this pilot uses the user's existing login.
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OLDPWD", None)
        env["PWD"] = str(workspace)
        env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] = "1"
        command = [executable, "-p", PROMPT, "--model", args.model,
                   "--output-format", "stream-json", "--verbose",
                   "--max-turns", "40", "--tools", TOOLS,
                   "--permission-mode", "acceptEdits", "--allowedTools", "Bash",
                   "--setting-sources", "project", "--strict-mcp-config",
                   "--mcp-config", '{"mcpServers":{}}']
        metadata["command"] = command
        print(f"Running Claude in: {workspace}", flush=True)
        print("This may take several minutes. Logs and results are being saved.", flush=True)
        with (run / "claude-events.jsonl").open("w", encoding="utf-8") as stdout, \
                (run / "claude-stderr.txt").open("w", encoding="utf-8") as stderr:
            proc = subprocess.run(command, cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                                  stdout=stdout, stderr=stderr, timeout=1200)
        exit_code = proc.returncode
        result, init = result_from_trace(run / "claude-events.jsonl")
        metadata.update(status="completed" if exit_code == 0 and result and not result.get("is_error") else "failed",
                        claude_exit_code=exit_code, initialization=init)
        if result:
            save(run / "claude-result.json", result)
            (run / "report.md").write_text(str(result.get("result", "")), encoding="utf-8")
            metadata["usage"] = result.get("usage")
            metadata["model_usage"] = result.get("modelUsage")
            metadata["claude_duration_ms"] = result.get("duration_ms")
            metadata["estimated_cost_usd"] = result.get("total_cost_usd")
        else:
            metadata["error"] = "No final result event; inspect event log and stderr."
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        metadata.update(status="failed", error=str(error))
    finally:
        metadata["elapsed_seconds"] = round(time.monotonic() - start, 3)
        try:
            after = inventory(workspace)
            (run / "workspace-after.txt").write_text(after, encoding="utf-8")
            metadata["originals_and_skill_unchanged"] = before == after
        except (OSError, subprocess.SubprocessError) as error:
            metadata["inventory_error"] = str(error)
        marker = workspace / "facts-and-figures-out/.active"
        metadata["marker_removed"] = not os.path.lexists(marker)
        metadata["numeric_report_present"] = (workspace / "facts-and-figures-out/verification-report.json").is_file()
        save(run / "run-metadata.json", metadata)
        print(f"Status: {metadata['status']} (semantic grading pending review)")
        print(f"ZIP TO UPLOAD: {bundle(run)}")
    return 0 if metadata["status"] == "completed" else (exit_code or 1)


if __name__ == "__main__":
    sys.exit(main())
