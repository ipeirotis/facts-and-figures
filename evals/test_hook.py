#!/usr/bin/env python3
"""Self-test for hooks/write-boundary.sh. No LLM.

Exercises the guard's allow and deny paths, including the two regressions
found in PR review: a project checkout living under /tmp must still be
protected (the scratch-root allowance must not whitelist an ancestor of
the project), and a very large Write payload must still reach the parser
(stdin, not an environment variable, so no E2BIG fail-open).

Usage: python3 evals/test_hook.py
Exit code 0 iff every case behaves as expected.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "write-boundary.sh"

failures = 0


def run_hook(payload, project):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))
    env.pop("FACTS_AND_FIGURES_OUT", None)
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(["bash", str(HOOK)], input=data, env=env,
                          capture_output=True, text=True)


def check(label, payload, project, want_deny):
    global failures
    proc = run_hook(payload, project)
    denied = '"deny"' in proc.stdout
    ok = proc.returncode == 0 and denied == want_deny
    print(f"{'PASS' if ok else 'FAIL'}  {label}"
          + ("" if ok else f"  (exit {proc.returncode}, denied={denied}, want deny={want_deny})"))
    if not ok:
        failures += 1


def write_payload(project, path, content="x"):
    return {"tool_name": "Write", "cwd": str(project),
            "tool_input": {"file_path": str(path), "content": content}}


def main():
    home_base = tempfile.mkdtemp(prefix="fnf-hook-test.", dir=os.path.expanduser("~"))
    tmp_base = tempfile.mkdtemp(prefix="fnf-hook-test.")
    try:
        # project outside /tmp — the ordinary case
        proj = Path(home_base) / "paper"
        (proj / "facts-and-figures-out").mkdir(parents=True)

        check("no marker: outside write allowed",
              write_payload(proj, proj / "manuscript.md"), proj, want_deny=False)

        (proj / "facts-and-figures-out" / ".active").touch()

        check("marker: outside write denied",
              write_payload(proj, proj / "manuscript.md"), proj, want_deny=True)
        check("marker: proposal-directory write allowed",
              write_payload(proj, proj / "facts-and-figures-out" / "s.py"), proj, want_deny=False)
        check("marker: scratch write under /tmp allowed",
              write_payload(proj, "/tmp/fnf-scratch.txt"), proj, want_deny=False)
        check("marker: Bash payload ignored",
              {"tool_name": "Bash", "cwd": str(proj), "tool_input": {"command": "ls"}},
              proj, want_deny=False)
        check("garbage stdin fails open",
              "not json", proj, want_deny=False)
        check("marker: 300 KiB write outside still denied (stdin, no E2BIG)",
              write_payload(proj, proj / "manuscript.md", content="A" * 300_000),
              proj, want_deny=True)

        # project checkout itself under /tmp — the ancestor-root regression
        tproj = Path(tmp_base) / "paper"
        (tproj / "facts-and-figures-out").mkdir(parents=True)
        (tproj / "facts-and-figures-out" / ".active").touch()

        check("project under /tmp: outside write still denied",
              write_payload(tproj, tproj / "manuscript.md"), tproj, want_deny=True)
        check("project under /tmp: proposal-directory write allowed",
              write_payload(tproj, tproj / "facts-and-figures-out" / "s.py"), tproj, want_deny=False)
    finally:
        shutil.rmtree(home_base, ignore_errors=True)
        shutil.rmtree(tmp_base, ignore_errors=True)

    print()
    if failures:
        print(f"{failures} hook self-test(s) FAILED")
        sys.exit(1)
    print("all hook self-tests passed")


if __name__ == "__main__":
    main()
