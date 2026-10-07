#!/usr/bin/env python3
"""Portable workspace inventory for the agent eval.

Prints a deterministic snapshot of everything outside the proposal
directory: a sha256 line for every regular file (the .claude configuration
and installed skill included — a run that tampers with its own guard must
fail), and an inventory line for every entry recording its type, permission
bits, path, and symlink target — so a run that modifies an author file,
chmods one, or plants a symlink, FIFO, or directory in the author's tree
fails the eval behaviorally, not just on paper.

Implemented in Python because the eval must run where GNU tools are not
installed: `find -printf` and `sha256sum` are GNU extensions missing from
stock macOS, and the harness already requires python3 for grading.

Usage: python3 evals/snapshot_workspace.py WORKSPACE_DIR
"""

import hashlib
import os
import stat
import sys

PRUNE = "facts-and-figures-out"

TYPE_CHARS = (
    (stat.S_ISREG, "f"), (stat.S_ISDIR, "d"), (stat.S_ISLNK, "l"),
    (stat.S_ISFIFO, "p"), (stat.S_ISSOCK, "s"), (stat.S_ISBLK, "b"),
    (stat.S_ISCHR, "c"),
)


def type_char(mode):
    for test, char in TYPE_CHARS:
        if test(mode):
            return char
    return "?"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = sys.argv[1]

    def fail(err):
        # an unreadable directory would silently hide modifications
        raise err

    hashes, inventory = [], []
    for dirpath, dirnames, filenames in os.walk(root, onerror=fail):
        if dirpath == root:
            # prune only a REAL proposal directory at the top level: a
            # symlink, file, or FIFO carrying the proposal name is not the
            # proposal directory and stays in the inventory — pruning it
            # would hide a run that replaced the root with a symlink and
            # routed generated work outside it
            dirnames[:] = [d for d in dirnames
                           if d != PRUNE or os.path.islink(os.path.join(dirpath, d))]
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        entries = [dirpath] if rel_dir == "." else []
        entries += [os.path.join(dirpath, n) for n in dirnames + sorted(filenames)]
        for full in entries:
            rel = os.path.relpath(full, root)
            rel = "." if rel == "." else "./" + rel
            st = os.lstat(full)
            kind = type_char(st.st_mode)
            target = os.readlink(full) if kind == "l" else ""
            inventory.append(f"{kind} {oct(stat.S_IMODE(st.st_mode))[2:]} {rel} -> {target}")
            if kind == "f":
                hashes.append((rel, f"{sha256(full)}  {rel}"))

    # the hash block sorts by path (as the earlier find|sort|sha256sum
    # pipeline did), keeping snapshots comparable across implementations
    for _, line in sorted(hashes):
        print(line)
    for line in sorted(inventory):
        print(line)


if __name__ == "__main__":
    main()
