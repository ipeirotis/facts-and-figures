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
    # a hard timeout so a hook regression that blocks (a FIFO marker made
    # open() wait for a writer) fails the suite loudly instead of hanging it
    return subprocess.run(["bash", str(HOOK)], input=data, env=env,
                          capture_output=True, text=True, timeout=15)


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
        # the decision reason says WHICH rule fired — without it a
        # wrong deny is indistinguishable from the expected one
        if proc.stdout.strip():
            print(f"      hook output: {proc.stdout.strip()[:300]}")
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
        check("marker: mid-run marker rewrite denied",
              write_payload(proj, proj / "facts-and-figures-out" / ".active"), proj,
              want_deny=True)
        # nor through a symlink alias in the proposal directory, which
        # skips the lexical marker check but resolves to the marker itself
        (proj / "facts-and-figures-out" / "alias").symlink_to(
            proj / "facts-and-figures-out" / ".active")
        check("marker: rewrite through a proposal-dir alias denied",
              write_payload(proj, proj / "facts-and-figures-out" / "alias"), proj,
              want_deny=True)
        (proj / "facts-and-figures-out" / "alias").unlink()
        # no scratch allowance: the protocol authors new files only in the
        # proposal directory, and an author input living under /tmp would
        # otherwise be writable through guarded tools
        check("marker: scratch write under /tmp denied",
              write_payload(proj, "/tmp/fnf-scratch.txt"), proj, want_deny=True)
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

        # the environment variable is no longer a channel for the
        # proposal directory — it bypassed the fresh-directory
        # validation the bootstrap applies to marker content
        marker = proj / "facts-and-figures-out" / ".active"
        check("env naming ..: ignored, manuscript write still denied",
              write_payload(proj, proj / "manuscript.md"), proj, want_deny=True,
              extra_env={"FACTS_AND_FIGURES_OUT": ".."})
        (proj / "data").mkdir(exist_ok=True)
        (proj / "data" / "workers.csv").write_text("id\n1\n")
        check("env naming the data directory: ignored, data write denied",
              write_payload(proj, proj / "data" / "x.csv"), proj, want_deny=True,
              extra_env={"FACTS_AND_FIGURES_OUT": "data"})
        check("env naming the data directory: default proposal still allowed",
              write_payload(proj, proj / "facts-and-figures-out" / "s.py"), proj,
              want_deny=False, extra_env={"FACTS_AND_FIGURES_OUT": "data"})
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
        # the armed marker is read-only to guarded tools: a rewrite would
        # re-aim the boundary at any directory the writer names
        check("marker naming custom-out: mid-run marker rewrite denied",
              write_payload(proj, marker), proj, want_deny=True)
        marker.write_text("")

        # the proposal root itself must not be a symlink into the author
        # tree: a redirected root would launder every generated file into
        # the directory it points at
        sproj = Path(home_base) / "paper2"
        (sproj / "data").mkdir(parents=True)
        (sproj / "data" / ".active").touch()
        (sproj / "facts-and-figures-out").symlink_to(sproj / "data")
        check("symlinked proposal root: write under it denied",
              write_payload(sproj, sproj / "facts-and-figures-out" / "s.py"), sproj,
              want_deny=True)
        check("symlinked proposal root: marker-path write exemption refused",
              write_payload(sproj, sproj / "facts-and-figures-out" / ".active"), sproj,
              want_deny=True)

        # the marker bootstrap is the one write the protocol makes while
        # the guard is unarmed: through an already-symlinked default
        # directory it must be denied, through a real directory it is the
        # ordinary lifecycle write
        nproj = Path(home_base) / "paper4"
        nproj.mkdir()
        (nproj / "data").mkdir()
        (nproj / "facts-and-figures-out").symlink_to(nproj / "data")
        check("no marker, symlinked root: marker bootstrap write denied",
              write_payload(nproj, nproj / "facts-and-figures-out" / ".active"), nproj,
              want_deny=True)
        check("no marker, symlinked root: bootstrap via the resolved path denied",
              write_payload(nproj, nproj / "data" / ".active"), nproj, want_deny=True)
        check("no marker, symlinked root: unrelated write still allowed",
              write_payload(nproj, nproj / "notes.md"), nproj, want_deny=False)
        rproj = Path(home_base) / "paper5"
        (rproj / "facts-and-figures-out").mkdir(parents=True)
        check("no marker, real root: marker bootstrap write allowed",
              write_payload(rproj, rproj / "facts-and-figures-out" / ".active"), rproj,
              want_deny=False)

        # a broken marker symlink must still arm the guard: with exists()
        # it would read as absent and the write recreating the marker could
        # follow the link to create an author file
        bproj = Path(home_base) / "paper3"
        (bproj / "facts-and-figures-out").mkdir(parents=True)
        (bproj / "facts-and-figures-out" / ".active").symlink_to(bproj / "planted.md")
        check("broken marker symlink: guard armed, outside write denied",
              write_payload(bproj, bproj / "notes.md"), bproj, want_deny=True)
        check("broken marker symlink: write to the marker path denied",
              write_payload(bproj, bproj / "facts-and-figures-out" / ".active"), bproj,
              want_deny=True)
        check("broken marker symlink: proposal-directory write still allowed",
              write_payload(bproj, bproj / "facts-and-figures-out" / "s.py"), bproj,
              want_deny=False)

        # a hard link in the proposal directory shares the author file's
        # inode: realpath stays under the proposal, so only the link count
        # betrays it
        os.link(proj / "manuscript.md", proj / "facts-and-figures-out" / "vr.json")
        check("hard-linked proposal file: write denied",
              write_payload(proj, proj / "facts-and-figures-out" / "vr.json"), proj,
              want_deny=True)
        (proj / "facts-and-figures-out" / "vr.json").unlink()

        # nor may the marker itself be a hard link to an author file
        marker.unlink()
        os.link(proj / "manuscript.md", marker)
        check("hard-linked marker: write to the marker path denied",
              write_payload(proj, marker), proj, want_deny=True)
        marker.unlink()
        marker.touch()

        # a marker that is a symlink or hard link to a file naming an
        # author subtree must not have its content trusted as the
        # proposal root
        mproj = Path(home_base) / "paper7"
        (mproj / "facts-and-figures-out").mkdir(parents=True)
        (mproj / "data").mkdir()
        (mproj / "data" / "workers.csv").write_text("x\n")
        (mproj / "redirect.txt").write_text("data\n")
        (mproj / "facts-and-figures-out" / ".active").symlink_to(mproj / "redirect.txt")
        check("symlinked marker naming data: data write still denied",
              write_payload(mproj, mproj / "data" / "workers.csv"), mproj, want_deny=True)
        (mproj / "facts-and-figures-out" / ".active").unlink()
        os.link(mproj / "redirect.txt", mproj / "facts-and-figures-out" / ".active")
        check("hard-linked marker naming data: data write still denied",
              write_payload(mproj, mproj / "data" / "workers.csv"), mproj, want_deny=True)

        # a FIFO planted at the marker path arms the guard but must not be
        # opened: reading it would block until a writer appears, hanging
        # every guarded write
        fproj = Path(home_base) / "paper6"
        (fproj / "facts-and-figures-out").mkdir(parents=True)
        os.mkfifo(fproj / "facts-and-figures-out" / ".active")
        check("FIFO marker: guard armed, outside write denied without hanging",
              write_payload(fproj, fproj / "notes.md"), fproj, want_deny=True)
        check("FIFO marker: proposal-directory write still allowed",
              write_payload(fproj, fproj / "facts-and-figures-out" / "s.py"), fproj,
              want_deny=False)

        # a proposal root must be a directory: a marker naming an existing
        # author file would otherwise hand that very file to the allowance
        marker.write_text("manuscript.md\n")
        check("marker naming an author file: write to that file denied",
              write_payload(proj, proj / "manuscript.md"), proj, want_deny=True)
        marker.write_text("")

        # a marker whose line carries an embedded NUL is planted garbage:
        # the hook must fall back to the default proposal directory, not
        # crash into a non-blocking hook error that lets the write through
        marker.write_text("data\x00evil\n")
        check("marker with NUL content: manuscript write still denied",
              write_payload(proj, proj / "manuscript.md"), proj, want_deny=True)
        check("marker with NUL content: default proposal write allowed",
              write_payload(proj, proj / "facts-and-figures-out" / "s.py"), proj,
              want_deny=False)
        marker.write_text("")

        # the session may work in a linked worktree while the
        # CLAUDE_PROJECT_DIR environment variable stays at the original
        # checkout: the marker in the worktree (the payload cwd) must
        # still arm the guard there
        oproj = Path(home_base) / "orig"
        (oproj / "facts-and-figures-out").mkdir(parents=True)
        wproj = Path(home_base) / "wt"
        (wproj / "facts-and-figures-out").mkdir(parents=True)
        (wproj / "facts-and-figures-out" / ".active").touch()
        check("worktree cwd with marker: outside write denied despite stale env root",
              write_payload(wproj, wproj / "manuscript.md"), oproj, want_deny=True)
        check("worktree cwd with marker: proposal write allowed",
              write_payload(wproj, wproj / "facts-and-figures-out" / "s.py"), oproj,
              want_deny=False)

        # the bootstrap validation must run against every candidate root:
        # with no marker anywhere the selected project is the environment
        # root, while the bootstrap may target a worktree whose default
        # directory is already a symlink
        o2 = Path(home_base) / "orig2"
        (o2 / "facts-and-figures-out").mkdir(parents=True)
        w2 = Path(home_base) / "wt2"
        w2.mkdir()
        (w2 / "data").mkdir()
        (w2 / "facts-and-figures-out").symlink_to(w2 / "data")
        check("worktree bootstrap, symlinked root: marker write denied",
              write_payload(w2, w2 / "facts-and-figures-out" / ".active"), o2,
              want_deny=True)
        check("worktree bootstrap, symlinked root: resolved-path write denied",
              write_payload(w2, w2 / "data" / ".active"), o2, want_deny=True)
        check("worktree bootstrap, symlinked root: unrelated write allowed",
              write_payload(w2, w2 / "notes.md"), o2, want_deny=False)

        # the payload cwd follows the session into subdirectories (cd
        # analysis): the guard must ascend to the worktree root instead
        # of reading <wt>/analysis as an unarmed project
        (wproj / "analysis").mkdir()
        check("nested worktree cwd: outside write denied",
              write_payload(wproj / "analysis", wproj / "manuscript.md"), oproj,
              want_deny=True)
        check("nested worktree cwd: proposal write allowed",
              write_payload(wproj / "analysis",
                            wproj / "facts-and-figures-out" / "s.py"), oproj,
              want_deny=False)
        # the unarmed bootstrap validation must also reach the root the
        # nested cwd ascends to — identified by the .git file a linked
        # worktree carries, since no marker exists yet
        (w2 / "analysis").mkdir()
        (w2 / ".git").write_text("gitdir: elsewhere\n")
        check("nested worktree bootstrap, symlinked root: marker write denied",
              write_payload(w2 / "analysis",
                            w2 / "facts-and-figures-out" / ".active"), o2,
              want_deny=True)

        # a nested git repository (vendored code, a submodule) inside an
        # armed project must not cut the marker ascent short: the armed
        # marker above outranks the nearer .git
        (wproj / "vendor" / "lib").mkdir(parents=True)
        (wproj / "vendor" / "lib" / ".git").mkdir()
        (wproj / "manuscript.md").write_text("# Title\n")
        check("cwd in nested git repo of armed worktree: outside write denied",
              write_payload(wproj / "vendor" / "lib", wproj / "manuscript.md"),
              oproj, want_deny=True)
        check("cwd in nested git repo of armed worktree: proposal write allowed",
              write_payload(wproj / "vendor" / "lib",
                            wproj / "facts-and-figures-out" / "s.py"), oproj,
              want_deny=False)

        # runs armed concurrently in an original checkout and a linked
        # worktree: the payload cwd names which run a write belongs to,
        # and neither run may write into the proposal directory of the
        # other
        o3 = Path(home_base) / "orig3"
        (o3 / "facts-and-figures-out").mkdir(parents=True)
        (o3 / "facts-and-figures-out" / ".active").touch()
        w3 = Path(home_base) / "wt3"
        (w3 / "facts-and-figures-out").mkdir(parents=True)
        (w3 / "facts-and-figures-out" / ".active").touch()
        (w3 / "manuscript.md").write_text("# Title\n")
        check("concurrent runs: worktree writes its own proposal",
              write_payload(w3, w3 / "facts-and-figures-out" / "r.json"), o3,
              want_deny=False)
        check("concurrent runs: worktree write into the other proposal denied",
              write_payload(w3, o3 / "facts-and-figures-out" / "r.json"), o3,
              want_deny=True)
        check("concurrent runs: worktree manuscript still denied",
              write_payload(w3, w3 / "manuscript.md"), o3, want_deny=True)
        check("concurrent runs: original checkout writes its own proposal",
              write_payload(o3, o3 / "facts-and-figures-out" / "r.json"), o3,
              want_deny=False)

        # a stale or planted marker in a subdirectory must not shadow
        # the real marker at the root: its content naming ../data would
        # re-aim the proposal allowance at the author data directory
        (wproj / "analysis" / "facts-and-figures-out").mkdir()
        (wproj / "analysis" / "facts-and-figures-out" / ".active").write_text("../data\n")
        (wproj / "data").mkdir()
        check("nested marker shadowing: write into author data denied",
              write_payload(wproj / "analysis", wproj / "data" / "x.csv"), oproj,
              want_deny=True)
        check("nested marker shadowing: root proposal write still allowed",
              write_payload(wproj / "analysis",
                            wproj / "facts-and-figures-out" / "s2.py"), oproj,
              want_deny=False)

        # the inverse nesting: a planted ANCESTOR marker naming the
        # checkout as its proposal would whitelist the whole checkout —
        # the checkout is a candidate root, so safe_root rejects it and
        # the ambiguity fails closed
        anc = Path(home_base) / "anc"
        (anc / "facts-and-figures-out").mkdir(parents=True)
        (anc / "facts-and-figures-out" / ".active").write_text("paper2\n")
        p2 = anc / "paper2"
        (p2 / "facts-and-figures-out").mkdir(parents=True)
        (p2 / "facts-and-figures-out" / ".active").touch()
        (p2 / "manuscript.md").write_text("# Title\n")
        check("ancestor marker naming the checkout: manuscript write denied",
              write_payload(p2, p2 / "manuscript.md"), p2, want_deny=True)
        check("ancestor marker naming the checkout: checkout-wide writes denied",
              write_payload(p2, p2 / "notes.md"), p2, want_deny=True)

        # bootstrap from a nested git repository: the worktree root above
        # it must stay a candidate, or its symlinked default directory
        # escapes the bootstrap validation
        w4 = Path(home_base) / "wt4"
        (w4 / "vendor" / "lib").mkdir(parents=True)
        (w4 / "vendor" / "lib" / ".git").mkdir()
        (w4 / ".git").write_text("gitdir: elsewhere\n")
        (w4 / "data").mkdir()
        (w4 / "facts-and-figures-out").symlink_to(w4 / "data")
        check("nested-repo bootstrap, symlinked worktree root: marker write denied",
              write_payload(w4 / "vendor" / "lib",
                            w4 / "facts-and-figures-out" / ".active"), o2,
              want_deny=True)
        check("nested-repo bootstrap, symlinked worktree root: resolved spelling denied",
              write_payload(w4 / "vendor" / "lib", w4 / "data" / ".active"), o2,
              want_deny=True)

        # a bootstrap marker naming an existing, non-empty directory
        # would hand pre-existing author content to the allowance
        p8 = Path(home_base) / "paper8"
        (p8 / "data").mkdir(parents=True)
        (p8 / "data" / "workers.csv").write_text("id\n1\n")
        (p8 / "empty-out").mkdir()
        check("bootstrap marker naming the data directory: denied",
              write_payload(p8, p8 / "facts-and-figures-out" / ".active",
                            content="data\n"), p8, want_deny=True)
        check("bootstrap marker naming a fresh directory: allowed",
              write_payload(p8, p8 / "facts-and-figures-out" / ".active",
                            content="fresh-out\n"), p8, want_deny=False)
        check("bootstrap marker naming an empty directory: allowed",
              write_payload(p8, p8 / "facts-and-figures-out" / ".active",
                            content="empty-out\n"), p8, want_deny=False)

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
