"""Refuse a book baseline in which two entities share one measurement.

Accepting a baseline is not a neutral act. booktest records whatever the
system did, defect included: a dropped condition returns 200 with
perfectly clean-looking numbers, and once accepted, the wrong number
reads as the expected answer. It happened twice in this repo (removed in
8324912), and both baselines carried the same tell:

    K.H.N.-Marketing Oy    -> GL 4400  7383/16000  lift=2.3
    Bronex Software Oy     -> GL 4400  7383/16000  lift=2.3

Different vendors cannot have the same support out of the same
denominator. 7383 of 16000 was the tenant-wide count of GL 4400 -- the
vendor clause was not in the condition at all. The other baseline showed
one lift, 21.94, for two different tenants.

So: when one measurement (a support pair `N/M`, or a `lift=`) appears
against two different entities in the same baseline, refuse. An entity is
the row's own label when the row has one ("Bronex Software Oy ->"), and
otherwise the nearest enclosing label or heading, so measurements
repeated *within* one entity -- several conjunctions predicting the same
value, say -- are not collisions.

Usage:
    python scripts/baseline_collisions.py books/.out/book
    python scripts/baseline_collisions.py books/book/*/*.md
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# A support pair: 7383/16000. Denominators under ten are skipped -- small
# counts coincide honestly, and dates (2024/09/01) are not measurements.
SUPPORT = re.compile(r"(?<![\d.])(\d+)\s*/\s*(\d+)(?![\d.])")
LIFT = re.compile(r"lift\s*=\s*(\d+(?:\.\d+)?)")
MIN_DENOMINATOR = 10

HEADING = re.compile(r"^#+\s+(.*\S)\s*$")
# "Bronex Software Oy    -> GL 6100 ..." — the row names its own subject.
ROW_LABEL = re.compile(r"^\s*(\S.*?)\s*->")
# "approver = CUST-0000-EMP-0006:" — a label for the rows indented under it.
BLOCK_LABEL = re.compile(r"^(\s*)(\S.*\S):\s*$")


@dataclass
class Collision:
    measurement: str
    entities: list[str]
    lines: list[int]

    def describe(self) -> str:
        where = ", ".join(f"line {n}" for n in self.lines)
        subjects = " / ".join(self.entities)
        return (f"{self.measurement} appears for {len(self.entities)} different "
                f"entities ({subjects}) at {where}")


def _measurements(line: str) -> list[str]:
    found = []
    for numerator, denominator in SUPPORT.findall(line):
        if int(denominator) >= MIN_DENOMINATOR:
            found.append(f"{numerator}/{denominator}")
    for value in LIFT.findall(line):
        # A zero lift is "no association", which many rows share honestly.
        if float(value) != 0.0:
            found.append(f"lift={value}")
    return found


def collisions(text: str) -> list[Collision]:
    """Measurements that appear against more than one entity."""
    heading = "<document>"
    block: tuple[int, str] | None = None   # (indent, label)
    seen: dict[str, dict[str, int]] = {}   # measurement -> entity -> first line

    for number, line in enumerate(text.splitlines(), start=1):
        matched_heading = HEADING.match(line)
        if matched_heading:
            heading, block = matched_heading.group(1), None
            continue
        matched_block = BLOCK_LABEL.match(line)
        if matched_block and not _measurements(line):
            block = (len(matched_block.group(1)), matched_block.group(2))
            continue
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip())
        if block and indent <= block[0]:
            block = None

        matched_row = ROW_LABEL.match(line)
        if matched_row:
            entity = matched_row.group(1)
        elif block:
            entity = block[1]
        else:
            entity = heading

        for measurement in _measurements(line):
            seen.setdefault(measurement, {}).setdefault(entity, number)

    return [
        Collision(measurement=measurement,
                  entities=list(entities),
                  lines=sorted(entities.values()))
        for measurement, entities in seen.items()
        if len(entities) > 1
    ]


def baselines(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        files.extend(sorted(path.rglob("*.md")) if path.is_dir() else [path])
    return [f for f in files if f.is_file()]


def main(argv: list[str]) -> int:
    targets = baselines(argv or ["books/.out/book"])
    if not targets:
        print("no baselines to check (nothing under books/.out — run ./do book first)")
        return 0

    offenders = [(path, found) for path in targets
                 if (found := collisions(path.read_text()))]
    if not offenders:
        print(f"{len(targets)} baseline(s) checked, no shared measurements")
        return 0

    print(f"{len(offenders)} of {len(targets)} baseline(s) record one measurement "
          f"for several entities:\n")
    for path, found in offenders:
        print(f"  {path}")
        for collision in found:
            print(f"      {collision.describe()}")
    print("\nThat is what a dropped condition looks like: the query answered a")
    print("question about the whole population, not about each subject.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
