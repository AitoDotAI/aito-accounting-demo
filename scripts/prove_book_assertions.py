"""Prove that every assertion in book/ is able to fail.

A book assertion that cannot fail is worse than no assertion: it prints
"ok" and a reader takes the invariant as checked. This repo had 21 of
them at once, because `TestCaseRun.assertln(cond, error_message)` takes
the condition FIRST and every call passed the message first, so `cond`
was a non-empty string. Two of the 21 asserted that no other customer's
help articles leak through.

Argument order is only the symptom. The property worth holding is that
each assertion is wired to something the test observes, so this proves it
the way a mutation tester would: break the assertion, and require the run
to notice.

For each `t.assertln(cond, message)` call:

- a real condition is negated in place -- `not (cond)` -- and the test is
  re-run; the message must reach the output.
- `assertln(False, ...)` is a "fails if this branch is reached" guard, so
  negating the condition proves nothing. The enclosing `if` is negated
  instead, which forces the branch; the message must then reach the
  output.
- `assertln(True, ...)` cannot fail whatever the data does. There is no
  mutation that redeems it, so it is reported as a defect: say it with
  `t.tln(...)` instead, which a baseline compares.

Tests are re-run from recorded snapshots, so this needs no network and
costs about a second per assertion.

Usage:
    ./do prove-assertions                 # every assertion in book/
    ./do prove-assertions --only help     # just the tests matching "help"
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BOOK = REPO / "book"
# The same backend ./do book records and replays against.
BOOK_ENV = {"AITO_V2_ENV": os.environ.get("AITO_V2_ENV", "v2-demo")}


@dataclass
class Call:
    """One `t.assertln(...)` call site."""

    path: Path
    open_paren: int
    close_paren: int
    condition: str
    message: str
    line: int
    test: str

    @property
    def where(self) -> str:
        return f"{self.path.name}:{self.line}"


def close_paren_of(src: str, open_idx: int) -> int:
    """Index of the ")" matching the "(" at open_idx, strings respected."""
    depth = 0
    i = open_idx
    quote = None
    while i < len(src):
        ch = src[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError(f"unbalanced parentheses at offset {open_idx}")


def split_arguments(src: str) -> tuple[str, str]:
    """Split "cond, message" at the top-level comma."""
    depth = 0
    i = 0
    quote = None
    while i < len(src):
        ch = src[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            return src[:i].strip(), src[i + 1:].strip()
        i += 1
    return src.strip(), ""


def enclosing_test(src: str, idx: int) -> str | None:
    name = None
    for match in re.finditer(r"^def (test_\w+)\(", src, re.M):
        if match.start() < idx:
            name = match.group(1)
        else:
            break
    return name


def message_probe(message: str) -> str | None:
    """The longest literal run of the message, as it will be printed.

    An f-string whose first character is an interpolation has no literal
    prefix, so take the longest static fragment instead -- otherwise the
    proof cannot see its own evidence.
    """
    match = re.match(r"f?\"((?:[^\"\\]|\\.)*)\"", message)
    if not match:
        return None
    fragments = re.split(r"\{[^}]*\}", match.group(1))
    best = max((f.strip() for f in fragments), key=len, default="")
    return best if len(best) >= 4 else None


def call_sites(path: Path) -> list[Call]:
    src = path.read_text()
    sites: list[Call] = []
    pos = 0
    while True:
        match = re.compile(r"t\.assertln\(").search(src, pos)
        if not match:
            return sites
        open_paren = match.end() - 1
        close = close_paren_of(src, open_paren)
        condition, message = split_arguments(src[open_paren + 1:close])
        sites.append(Call(
            path=path,
            open_paren=open_paren,
            close_paren=close,
            condition=condition,
            message=message,
            line=src[:open_paren].count("\n") + 1,
            test=enclosing_test(src, open_paren) or "<module>",
        ))
        pos = close


def negate_condition(src: str, call: Call) -> str:
    head = src[:call.open_paren + 1]
    tail = src[call.close_paren:]
    args = f"not ({call.condition})" + (f", {call.message}" if call.message else "")
    return head + args + tail


def negate_enclosing_if(src: str, call: Call) -> str | None:
    """Force a guard's branch by negating the `if` that guards it."""
    assertion_line = src[:call.open_paren].count("\n")
    lines = src.split("\n")
    indent = len(lines[assertion_line]) - len(lines[assertion_line].lstrip())
    for i in range(assertion_line - 1, -1, -1):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        line_indent = len(lines[i]) - len(lines[i].lstrip())
        if line_indent >= indent:
            continue
        match = re.match(r"if (.+):$", stripped)
        if not match:
            return None
        lines[i] = " " * line_indent + f"if not ({match.group(1)}):"
        return "\n".join(lines)
    return None


def run_test(path: Path, test: str) -> str:
    result = subprocess.run(
        ["uv", "run", "booktest", "-v", f"book/{path.name}::{test}"],
        cwd=REPO, env={**os.environ, **BOOK_ENV},
        capture_output=True, text=True, timeout=600,
    )
    return result.stdout + result.stderr


def prove(call: Call) -> tuple[str, str]:
    """Return (verdict, detail) for one assertion."""
    probe = message_probe(call.message)
    if call.condition == "True":
        return "CANNOT FAIL", "the condition is the literal True; use t.tln(...) to state the outcome"
    if not probe:
        return "UNPROVEN", "no literal fragment in the message to look for"

    src = call.path.read_text()
    if call.condition == "False":
        mutated = negate_enclosing_if(src, call)
        how = "its branch forced"
        if mutated is None:
            return "UNPROVEN", "guard with no single-line enclosing `if` to force"
    else:
        mutated = negate_condition(src, call)
        how = "negated"

    try:
        call.path.write_text(mutated)
        output = run_test(call.path, call.test)
    finally:
        call.path.write_text(src)

    if probe in output:
        return "CAN FAIL", how
    return "UNPROVEN", f"{how}, but {probe!r} never reached the output"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", metavar="SUBSTRING",
                        help="only prove assertions in tests whose name or file matches")
    args = parser.parse_args()

    calls = [c for path in sorted(BOOK.glob("test_*.py")) for c in call_sites(path)]
    if args.only:
        calls = [c for c in calls if args.only in c.test or args.only in c.path.name]
    if not calls:
        print("no assertions matched", file=sys.stderr)
        return 1

    print(f"Proving {len(calls)} book assertion(s) can fail — "
          f"env {BOOK_ENV['AITO_V2_ENV']}, replayed from snapshots\n")
    failures = []
    for call in calls:
        verdict, detail = prove(call)
        mark = "ok  " if verdict == "CAN FAIL" else "FAIL"
        print(f"  {mark}  {call.where:34} {verdict:12} {call.condition[:40]:40} {detail}")
        if verdict != "CAN FAIL":
            failures.append((call, verdict, detail))

    print()
    if failures:
        print(f"{len(failures)} of {len(calls)} assertion(s) could not be shown to fail:")
        for call, verdict, detail in failures:
            print(f"  {call.where}  {call.test}  {verdict}: {detail}")
        return 1
    print(f"All {len(calls)} assertions fail when broken.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
