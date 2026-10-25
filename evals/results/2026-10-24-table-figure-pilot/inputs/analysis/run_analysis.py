"""Canonical deterministic analysis for a fictional table/figure paper."""

import argparse
import csv
from decimal import Decimal
from html import escape
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def analyze():
    groups = {}
    with (ROOT / "data/scores.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            groups.setdefault(row["group"], []).append(Decimal(row["score"]))
    return {key: sum(values) / len(values) for key, values in sorted(groups.items())}


def figure(means):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="480" height="320" viewBox="0 0 480 320">',
             '<rect width="480" height="320" fill="white"/>',
             '<g font-family="sans-serif" font-size="14" fill="#17212b">',
             '<text x="240" y="22" text-anchor="middle">Mean quality score</text>',
             '<path d="M60 40 V240 H440" fill="none" stroke="#17212b"/>']
    for tick in range(0, 101, 20):
        y = 240 - 2 * tick
        parts.append(f'<text x="48" y="{y + 5}" text-anchor="end">{tick}</text>')
    for i, (group, value) in enumerate(means.items()):
        x = 120 + i * 180
        height = value * 2
        key = escape(group, quote=True)
        parts.append(f'<rect data-group="{key}" x="{x}" y="{240 - height}" '
                     f'width="70" height="{height}" fill="#366b9b"/>')
        parts.append(f'<text data-value-for="{key}" x="{x + 35}" y="{230 - height}" '
                     f'text-anchor="middle">{value:.1f}</text>')
        parts.append(f'<text x="{x + 35}" y="265" text-anchor="middle">{key}</text>')
    parts.append('<text x="240" y="300" text-anchor="middle">Group</text></g></svg>')
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    # Refuse an existing directory so a rerun cannot silently replace artifacts.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    means = analyze()
    (args.output_dir / "results.json").write_text(
        json.dumps({"mean_quality": {key: float(v) for key, v in means.items()}}, indent=2) + "\n",
        encoding="utf-8")
    with (args.output_dir / "table.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["group", "mean"])
        writer.writerows((key, f"{value:.1f}") for key, value in means.items())
    (args.output_dir / "quality.svg").write_text(figure(means), encoding="utf-8")


if __name__ == "__main__":
    main()
