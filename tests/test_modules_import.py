"""Every source module imports.

The unit tests exercise functions, not modules, so a module none of them
imports can be syntactically broken and the suite still passes -- which
is how a stray brace in the schema file reached a live run.
"""

import importlib
import pkgutil

import src


def test_every_src_module_imports():
    broken = []
    for mod in pkgutil.iter_modules(src.__path__):
        if mod.name == "app":
            continue  # constructs live clients at import time -- see ADR 0022
        try:
            importlib.import_module(f"src.{mod.name}")
        except SyntaxError as exc:
            broken.append(f"{mod.name}: {exc}")
    assert not broken, broken
