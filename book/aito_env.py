"""Which Aito the book tests talk to.

Mirrors the switch in `src/app.py` so the tests exercise whatever the
application would: `AITO_V2_ENV` unset means v1 against master, a name
means v2 against that environment branch, and `master` means v2 against
master with no `/env/` segment.

The recorded HTTP snapshots are keyed by request hash, so v1 and v2
entries coexist in the same file. The `.md` baselines cannot — one
expected output per test — so a baseline describes whichever backend it
was accepted against. `./do book` picks that backend; see the runbook.
"""

import os

from src.aito_client import AitoClient
from src.aito_v2_client import AitoV2Client, resolve_env
from src.config import load_config


def get_client():
    """The client for the configured Aito generation."""
    config = load_config()
    use_v2, env = resolve_env(os.environ.get("AITO_V2_ENV"))
    if use_v2:
        return AitoV2Client(config.aito_api_url, config.aito_api_key, env=env)
    return AitoClient(config)
