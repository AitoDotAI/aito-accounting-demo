"""Every cache key is built by src/cache_keys.py, wherever it is read or written.

The prefix convention (`v2:`) is the whole problem: `/api/cache/status` once
spelled page keys by hand without it and reported a fully warm cache as cold,
and `src/badges.py` and `src/rule_governance.py` later spelled their own. A
regex over source text cannot hold that line (concatenation, `%`, `.format`,
single-quoted or uppercase f-strings, implicit concatenation and any variable
name for the prefix all slip past it), so this reads the syntax tree:

  - the first argument of every `cache.get/set/delete/compute_lock` call must
    come from `page_cache_key`, `derived_key` or `scoped_key` (directly, through
    a variable assigned from one, or as `f"{builder(...)}:..."`), or be a
    function parameter (the caller is then checked where it builds the key);
  - no module but `src/cache_keys.py` may read the prefix itself.

Known limit: a key built from a parameter is trusted at the parameter, not at
the caller that passes it; and strings handed to anything other than the
`cache` module are not looked at.
"""

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"

BUILDERS = {"page_cache_key", "derived_key", "scoped_key"}
CACHE_CALLS = {"get", "set", "delete", "compute_lock"}
PREFIX_NAMES = {"_V2", "V2_PREFIX", "v2_prefix"}
# cache.py is the cache itself; cache_keys.py is the one place allowed to spell.
SKIP = {"cache.py", "cache_keys.py"}


def _walk_own(scope: ast.AST):
    """Nodes of `scope` without descending into functions nested in it."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(node))


def _assignments(scope: ast.AST) -> dict[str, list[ast.expr]]:
    found: dict[str, list[ast.expr]] = {}
    for node in _walk_own(scope):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.setdefault(target.id, []).append(node.value)
    return found


def _derived(expr: ast.expr, assigns: dict, params: set[str], top: bool = True) -> bool:
    if isinstance(expr, ast.Constant):
        return isinstance(expr.value, str) and ":" not in expr.value
    if isinstance(expr, ast.Call):
        func = expr.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        return name in BUILDERS
    if isinstance(expr, ast.JoinedStr):
        first = expr.values[0] if expr.values else None
        return (isinstance(first, ast.FormattedValue)
                and _derived(first.value, assigns, params, top=False))
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
        return _derived(expr.left, assigns, params, top=False)
    if isinstance(expr, ast.Name):
        # A parameter is trusted only as the whole key; spliced into an
        # f-string it is just a name being formatted (f"{kind}:{cid}").
        if expr.id in params:
            return top
        values = assigns.get(expr.id)
        return bool(values) and all(_derived(v, assigns, params) for v in values)
    return False


def _is_cache_call(node: ast.Call) -> bool:
    func = node.func
    return (isinstance(func, ast.Attribute) and func.attr in CACHE_CALLS
            and isinstance(func.value, ast.Name) and func.value.id == "cache")


def hand_spelled_keys(root: pathlib.Path) -> list[str]:
    problems = []
    for path in sorted(root.rglob("*.py")):
        if path.name in SKIP:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        module_assigns = _assignments(tree)
        scopes = [(tree, module_assigns, set())]
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args
                params = {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]}
                scopes.append((node, {**module_assigns, **_assignments(node)}, params))
        for scope, assigns, params in scopes:
            for node in _walk_own(scope):
                if isinstance(node, ast.Call) and _is_cache_call(node) and node.args:
                    if not _derived(node.args[0], assigns, params):
                        problems.append(f"{path.name}:{node.lineno}: cache.{node.func.attr}"
                                        f"({ast.unparse(node.args[0])}) is not built by cache_keys")
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in PREFIX_NAMES \
                    and isinstance(node.ctx, ast.Load):
                problems.append(f"{path.name}:{node.lineno}: reads the key prefix {node.id}")
    return problems


def _plant(tmp_path, body: str) -> list[str]:
    (tmp_path / "other.py").write_text("from src import cache\n" + body)
    return hand_spelled_keys(tmp_path)


def test_every_hand_spelling_shape_is_found(tmp_path):
    shapes = {
        "f-string": 'def f(kind, cid):\n    cache.get(f"{kind}:{prefix}{cid}")\n',
        "named page": 'def f(cid):\n    cache.set(f"matching:{V}{cid}", 1)\n',
        "concatenation": 'def f(cid):\n    cache.get("matching:v2:" + cid)\n',
        "percent": 'def f(cid):\n    cache.get("matching:%s" % cid)\n',
        "format": 'def f(cid):\n    cache.delete("matching:{}".format(cid))\n',
        "single-quoted f-string": "def f(cid):\n    cache.get(f'matching:{cid}')\n",
        "uppercase F-string": 'def f(cid):\n    cache.get(F"matching:{cid}")\n',
        "implicit concatenation": 'def f(cid):\n    cache.get("matching:" f"{cid}")\n',
        "via a variable": 'def f(cid):\n    key = f"matching:{cid}"\n    cache.get(key)\n',
        "lock": 'def f(cid):\n    with cache.compute_lock(f"matching:{cid}"):\n        pass\n',
    }
    for name, body in shapes.items():
        assert _plant(tmp_path, body), f"{name}: a hand-spelled key went unseen"


def test_reading_the_prefix_outside_cache_keys_is_found(tmp_path):
    for name in ("_V2", "V2_PREFIX", "v2_prefix"):
        assert _plant(tmp_path, f"def f(cid):\n    return {name}\n"), name


def test_keys_built_by_cache_keys_are_accepted(tmp_path):
    body = (
        "from src.cache_keys import page_cache_key, derived_key, scoped_key\n"
        "def f(cid, txn, key):\n"
        "    cache.get(page_cache_key('matching', cid))\n"
        "    k = derived_key('eval', cid, 5)\n"
        "    cache.set(k, 1)\n"
        "    cache.delete(f\"{page_cache_key('matching_why', cid)}:{txn}\")\n"
        "    cache.get(scoped_key('formfill', 'x') + ':more')\n"
        "    cache.get(key)\n"
        "    cache.get('health')\n"
    )
    assert _plant(tmp_path, body) == []


def test_no_module_under_src_spells_a_cache_key_by_hand():
    problems = hand_spelled_keys(SRC)
    assert problems == [], "hand-spelled cache keys remain:\n" + "\n".join(problems)
