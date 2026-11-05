"""Report test bodies that may not be able to fail.

    uv run python -I scripts/find_unfalsifiable_tests.py tests

Flags a test when it contains no assert, no `pytest.raises`/`warns`, no
`self.assertX` and no `fail()`, or when every assert it has is on a
literal (`assert True` can never go red).

**A lead generator, not a gate.** A body whose whole point is "this call
does not raise" legitimately has no assert and still fails when the call
starts raising -- two of the three hits in the first sweep
(2026-10-31) were exactly that, and sound. The only way to tell is to
break the code under test and watch the test go red. So: run this, then
mutation-check each hit by hand.

Companion to scripts/prove_book_assertions.py, which does the same job
for the book suite, where `assertln` made it mechanical.
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(sys.argv[1])

RAISING = {"raises", "warns", "fail", "xfail", "exit", "approx"}


def is_literal(node):
    try:
        ast.literal_eval(node)
        return True
    except (ValueError, TypeError, SyntaxError, MemoryError):
        return False


class Body(ast.NodeVisitor):
    def __init__(self):
        self.asserts = []        # assert statements
        self.literal_only = True
        self.guards = 0          # pytest.raises / self.assertX / fail()

    def visit_Assert(self, node):
        self.asserts.append(node)
        if not is_literal(node.test):
            self.literal_only = False

    def visit_Call(self, node):
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if name in RAISING or name.startswith("assert"):
            self.guards += 1
        self.generic_visit(node)

    def visit_With(self, node):
        for item in node.items:
            c = item.context_expr
            if isinstance(c, ast.Call):
                f = c.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if name in RAISING:
                    self.guards += 1
        self.generic_visit(node)


for path in sorted(ROOT.rglob("test_*.py")):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test"):
            continue
        body = Body()
        for stmt in node.body:
            body.visit(stmt)
        if not body.asserts and not body.guards:
            verdict = "NO ASSERTION AT ALL"
        elif body.asserts and body.literal_only and not body.guards:
            verdict = "ASSERTS ONLY LITERALS"
        else:
            continue
        print(f"{path}:{node.lineno}  {node.name}  -- {verdict}")
