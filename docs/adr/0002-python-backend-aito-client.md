# 0002. Python backend with Aito client library

**Date:** 2026-04-17
**Status:** accepted

## Context

The HTML mockup shows static data. To demonstrate Aito's predictive
database capabilities with real predictions, we need a backend that
talks to Aito and serves results to the frontend.

Python is a natural fit: the target audience (accounting SaaS
developers, data teams evaluating Aito) is comfortable with Python,
and the Nix shell already provisions Python 3.12.

## Decision

Build a thin FastAPI application with:

1. **Aito client** (`src/aito_client.py`) — a focused HTTP wrapper for
   Aito's REST API. Handles authentication, request/response, and
   error reporting. Not a generic SDK — only the operations this demo
   needs: `_predict`, `_relate`, `_search`, and schema inspection.

2. **Config** (`src/config.py`) — loads `AITO_API_URL` and
   `AITO_API_KEY` from environment / `.env` file. Fails loudly if
   missing.

3. **FastAPI app** (`src/app.py`) — mounts the API. Initial endpoints:
   `GET /api/health` (returns Aito connectivity status) and
   `GET /api/schema` (returns current Aito table schema).

4. **`./do dev`** — starts the backend with uvicorn on port 8000.

The client is intentionally thin. Outside developers reading this code
should see direct Aito HTTP calls with clear request/response shapes,
not abstraction layers that hide what's happening.

## Aito usage

- `GET /api/v1/schema` — verify connectivity and inspect tables
- No `_predict` or `_relate` calls yet (no data loaded)

## Acceptance criteria

- `./do dev` starts the FastAPI app on port 8000
- `GET /api/health` returns `{"status": "ok", "aito_connected": true}`
  when Aito is reachable, or `aito_connected: false` with details
- `GET /api/schema` proxies the Aito schema response
- `src/aito_client.py` has tests covering success and error paths
- Config fails with a clear error if `AITO_API_URL` or `AITO_API_KEY`
  is missing
- All source files under 200 lines

## Demo impact

No visible change to the HTML demo yet. Backend runs alongside the
mockup. `./do dev` added to the task runner.

## Out of scope

- Frontend changes or API calls from the HTML
- Sample data loading (PR 2)
- Prediction endpoints (PR 3)
- Authentication/CORS (not needed for a local demo)
