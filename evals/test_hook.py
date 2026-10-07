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


def run_hook(payload, project, extra_env=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))
    env.pop("FACTS_AND_FIGURES_OUT", None)
    env.update(extra_env or {})
    data = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(["bash", str(HOOK)], input=data, env=env,
                          capture_output=True, text=True)


def check(label, payload, project, want_deny, extra_env=None):
    global failures
    proc = run_hook(payload, project, extra_env)
    # a denial is only the exact decision shape Claude Code acts on, not
    # any output that happens to contain the word "deny"
    denied = False
    if proc.stdout.strip():
        try:
            out = json.loads(proc.stdout)
            hso = out.get("hookSpecificOutput", {})
            denied = (hso.get("hookEventName") == "PreToolUse"
                      and hso.get("permissionDecision") == "deny")
        except ValueError:
            denied = False
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
        (proj / "manuscript.md").write_text("# Title\n")

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

        # a symlink inside the repository must not route author-path writes
        # into the scratch exemption
        scratch_dir = Path(tempfile.mkdtemp(prefix="fnf-symlink-target."))
        (proj / "data2").symlink_to(scratch_dir)
        check("marker: write through an in-repo symlink into /tmp denied",
              write_payload(proj, proj / "data2" / "workers.csv"), proj, want_deny=True)
        shutil.rmtree(scratch_dir, ignore_errors=True)

        # nor must a symlink planted inside the proposal directory escape
        # the boundary from within
        (proj / "facts-and-figures-out" / "escape").symlink_to(proj / "manuscript.md")
        check("marker: write through a proposal-dir symlink to the manuscript denied",
              write_payload(proj, proj / "facts-and-figures-out" / "escape"), proj,
              want_deny=True)
        (proj / "facts-and-figures-out" / "escape").unlink()

        # the marker exemption must not apply when the marker itself is a
        # symlink to an author file
        marker_path = proj / "facts-and-figures-out" / ".active"
        marker_path.unlink()
        marker_path.symlink_to(proj / "manuscript.md")
        check("symlinked marker: write to the marker path denied",
              write_payload(proj, marker_path), proj, want_deny=True)
        marker_path.unlink()
        marker_path.touch()

        # a proposal override that contains the project must not whitelist it
        marker = proj / "facts-and-figures-out" / ".active"
        check("FACTS_AND_FIGURES_OUT=..: manuscript write still denied",
              write_payload(proj, proj / "manuscript.md"), proj, want_deny=True,
              extra_env={"FACTS_AND_FIGURES_OUT": ".."})
        marker.write_text("..\n")
        check("marker naming ..: manuscript write still denied",
              write_payload(proj, proj / "manuscript.md"), proj, want_deny=True)

        # an author-named proposal directory carried in the marker content
        (proj / "custom-out").mkdir(exist_ok=True)
        marker.write_text("custom-out\n")
        check("marker naming custom-out: custom proposal write allowed",
              write_payload(proj, proj / "custom-out" / "s.py"), proj, want_deny=False)
        check("marker naming custom-out: manuscript write denied",
              write_payload(proj, proj / "manuscript.md"), proj, want_deny=True)
        check("marker naming custom-out: default-directory write denied",
              write_payload(proj, proj / "facts-and-figures-out" / "r.json"), proj, want_deny=True)
        check("marker naming custom-out: the marker file itself stays writable",
              write_payload(proj, marker), proj, want_deny=False)
        marker.write_text("")

        # a scratch root inside the project must not whitelist author files
        (proj / "data").mkdir(exist_ok=True)
        check("TMPDIR inside project: data write still denied",
              write_payload(proj, proj / "data" / "workers.csv"), proj, want_deny=True,
              extra_env={"TMPDIR": str(proj / "data")})

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
