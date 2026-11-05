"""A page's cache key is spelled in one place, wherever it is read or written.

`page_cache_key` exists because `/api/cache/status` once spelled these keys
by hand without the v2 prefix and reported a fully warm cache as cold. The
guard that came with it read only `src/app.py`, so the same drift could
(and in `src/badges.py` did) live in any other module. This scans every
module under `src/`.
"""

import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"

# The one allowed spelling carries this marker on its line.
THE_BUILDER = "# the one spelling of a page cache key"

STRAY_KEY = [
    # A named page: f"matching:{_V2}{customer_id}"
    re.compile(r'f"(?:invoices|quality|matching|rules|anomalies):\{[^"]*\}"'),
    # A dynamic name and a v2 prefix variable: f"{cache_prefix}:{v2_prefix}{customer_id}"
    re.compile(r'f"\{\w+\}:\{\w*[vV]2\w*\}\{\w+\}"'),
]


def hand_spelled_keys(root: pathlib.Path) -> list[str]:
    found = []
    for path in sorted(root.rglob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if THE_BUILDER in line:
                continue
            if any(pattern.search(line) for pattern in STRAY_KEY):
                found.append(f"{path.name}:{number}: {line.strip()}")
    return found


def test_a_key_hand_spelled_in_a_second_module_is_found(tmp_path):
    (tmp_path / "app.py").write_text('key = f"matching:{_V2}{customer_id}"  # fine? no\n')
    (tmp_path / "other.py").write_text('key = f"{prefix}:{v2_prefix}{customer_id}"\n')

    found = hand_spelled_keys(tmp_path)

    assert any(entry.startswith("app.py") for entry in found)
    assert any(entry.startswith("other.py") for entry in found), \
        "a hand-spelled key outside app.py went unseen"


def test_the_builders_own_line_is_the_only_exception(tmp_path):
    (tmp_path / "app.py").write_text(
        f'    return f"{{name}}:{{_V2}}{{customer_id}}"  {THE_BUILDER}\n')
    assert hand_spelled_keys(tmp_path) == []


def test_no_module_under_src_spells_a_page_cache_key_by_hand():
    stray = hand_spelled_keys(SRC)
    assert stray == [], "hand-spelled page cache keys remain:\n" + "\n".join(stray)
