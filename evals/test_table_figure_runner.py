"""Runner plumbing tests with a stub CLI. These do not run Claude."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).with_name("run_table_figure_eval.py")
spec = importlib.util.spec_from_file_location("pilot_runner", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fnf-runner-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def run_script(self, *extra):
        target = self.root / "run"
        proc = subprocess.run([sys.executable, "-B", str(SCRIPT),
                               "--output-dir", str(target), *map(str, extra)],
                              capture_output=True, text=True)
        return proc, target

    def test_prepare_only_excludes_answer_key_and_development_files(self):
        proc, target = self.run_script("--prepare-only")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        workspace = target / "workspace"
        self.assertTrue((workspace / "manuscript.md").is_file())
        self.assertTrue((workspace / ".claude/skills/facts-and-figures/SKILL.md").is_file())
        names = [str(p.relative_to(workspace)) for p in workspace.rglob("*")]
        self.assertFalse(any("expected" in p or p.startswith("evals") for p in names))
        self.assertFalse((workspace / "AGENTS.md").exists())
        meta = json.loads((target / "run-metadata.json").read_text())
        self.assertEqual(meta["status"], "prepared")
        self.assertTrue(target.with_suffix(".zip").is_file())

    def test_missing_claude_saves_failed_attempt_without_claiming_results(self):
        proc, target = self.run_script("--claude", str(self.root / "absent-cli"))
        self.assertEqual(proc.returncode, 2)
        meta = json.loads((target / "run-metadata.json").read_text())
        self.assertEqual(meta["status"], "failed")
        self.assertTrue(meta["originals_and_skill_unchanged"])
        self.assertTrue(meta["marker_removed"])
        self.assertFalse(meta["numeric_report_present"])
        self.assertFalse((target / "report.md").exists())
        self.assertTrue(target.with_suffix(".zip").is_file())

    def test_refuses_existing_output_without_deleting_files(self):
        proc, target = self.run_script("--prepare-only")
        self.assertEqual(proc.returncode, 0)
        sentinel = target / "keep.txt"
        sentinel.write_text("keep")
        proc, _ = self.run_script("--prepare-only")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(sentinel.read_text(), "keep")

    @unittest.skipIf(os.name == "nt", "stub executable uses a POSIX shebang")
    def test_stub_cli_captures_trace_usage_and_report(self):
        cli = self.root / "stub-claude"
        cli.write_text(f"#!{sys.executable}\n" + '''import sys, json, os
if '--version' in sys.argv:
    print('test-stub; not Claude')
    sys.exit(0)
assert 'ANTHROPIC_API_KEY' not in os.environ
print(json.dumps({'type':'system','subtype':'init','model':'test-stub'}))
print(json.dumps({'type':'result','is_error':False,'result':'Stub report; not a model result',
 'usage':{'input_tokens':5,'output_tokens':7},'duration_ms':100,'modelUsage':{'test-stub':{}}}))
''', encoding="utf-8")
        cli.chmod(0o700)
        proc, target = self.run_script("--claude", cli)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        meta = json.loads((target / "run-metadata.json").read_text())
        self.assertEqual(meta["status"], "completed")
        self.assertEqual(meta["usage"]["output_tokens"], 7)
        self.assertEqual(meta["initialization"]["model"], "test-stub")
        self.assertEqual(meta["grading"], "pending review")
        self.assertTrue(meta["originals_and_skill_unchanged"])
        self.assertEqual((target / "report.md").read_text(), "Stub report; not a model result")
        with zipfile.ZipFile(target.with_suffix(".zip")) as archive:
            names = archive.namelist()
            self.assertTrue(any(p.endswith("claude-events.jsonl") for p in names))
            self.assertTrue(any(p.endswith("run-metadata.json") for p in names))

    def test_trace_parser_uses_final_result_not_assistant_intermediates(self):
        path = self.root / "events.jsonl"
        path.write_text('\n'.join(["not JSON", '[]',
            json.dumps({"type": "assistant", "result": "ignore"}),
            json.dumps({"type": "result", "result": "first"}),
            json.dumps({"type": "result", "result": "last"})]))
        result, init = runner.result_from_trace(path)
        self.assertEqual(result["result"], "last")
        self.assertIsNone(init)


if __name__ == "__main__":
    unittest.main()
