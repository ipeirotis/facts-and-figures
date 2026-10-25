"""Offline self-check of table/figure test materials, not an agent grader."""

import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


EVALS = Path(__file__).resolve().parent
KEY = json.loads((EVALS / "table-figure-expected.json").read_text())
FIXTURE = EVALS / KEY["fixture"]


def snapshot():
    return {str(p.relative_to(FIXTURE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in FIXTURE.rglob("*") if p.is_file()}


def graph_values(path):
    root = ET.parse(path).getroot()
    marks, labels = {}, {}
    for node in root.iter():
        if "data-group" in node.attrib:
            value = float(node.attrib["height"]) / 2
            if float(node.attrib["y"]) != 240 - 2 * value:
                raise ValueError("bar geometry disagrees with zero baseline")
            marks[node.attrib["data-group"]] = value
        if "data-value-for" in node.attrib:
            labels[node.attrib["data-value-for"]] = float(node.text)
    return marks, labels


class FixtureTests(unittest.TestCase):
    def test_mark_geometry_and_printed_labels_are_independent(self):
        original = (FIXTURE / "figures/quality.svg").read_text()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "variant.svg"
            # Correct label alone does not repair the wrong bar.
            p.write_text(original.replace('>65.0</text>', '>60.0</text>'))
            marks, labels = graph_values(p)
            self.assertEqual(marks["B"], 65)
            self.assertEqual(labels["B"], 60)
            # Correct geometry alone does not repair the wrong label.
            p.write_text(original.replace('y="110" width="70" height="130"',
                                          'y="120" width="70" height="120"'))
            marks, labels = graph_values(p)
            self.assertEqual(marks["B"], 60)
            self.assertEqual(labels["B"], 65)

    def test_pipeline_outputs_and_preserves_submitted_files(self):
        before = snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "recomputed"
            command = [sys.executable, str(FIXTURE / "analysis/run_analysis.py"),
                       "--output-dir", str(output)]
            proc = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            results = json.loads((output / "results.json").read_text())
            self.assertEqual(results["mean_quality"], KEY["mean_quality"])
            with (output / "table.csv").open(newline="") as stream:
                cells = {r["group"]: float(r["mean"]) for r in csv.DictReader(stream)}
            self.assertEqual(cells, KEY["mean_quality"])
            marks, labels = graph_values(output / "quality.svg")
            self.assertEqual(marks, KEY["mean_quality"])
            self.assertEqual(labels, KEY["mean_quality"])
            # Re-running must fail rather than overwrite an existing output directory.
            again = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
        self.assertEqual(before, snapshot())

    def test_planted_table_and_graph_discrepancies_match_key(self):
        text = (FIXTURE / "manuscript.md").read_text()
        cells = {group: float(value) for group, value in
                 re.findall(r"\| ([AB]) \| ([\d.]+) \|", text)}
        marks, labels = graph_values(FIXTURE / "figures/quality.svg")
        for target in KEY["targets"]:
            with self.subTest(location=target["location"]):
                loc = target["location"]
                group = "A" if re.search(r"\bA\b", loc) else "B"
                actual = cells[group] if loc.startswith("Table") else (
                    marks[group] if loc.endswith("bar") else labels[group])
                self.assertEqual(actual, target["reported"])
                self.assertEqual(KEY["mean_quality"][group], target["computed"])
                verdict = "match" if actual == target["computed"] else "mismatch"
                self.assertEqual(verdict, target["expected"])


if __name__ == "__main__":
    unittest.main()
