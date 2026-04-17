# 0001. Project foundation — scaffold, tooling, and initial demo

**Date:** 2026-04-17
**Status:** accepted

## Context

This is a new OSS reference project demonstrating Aito.ai's predictive
database in an accounting/financial automation context. We have a
polished HTML mockup (`ledger-pro-demo.html`) but no project
infrastructure: no git repo, no task runner, no documentation beyond
the task description.

Before building features, we need the foundation that makes everything
else possible: version control, a repeatable task runner, and enough
documentation that an outside developer can open the repo and understand
what they're looking at.

## Decision

Set up the minimal project scaffold:

1. **Git repository** with `.gitignore` and conventional `main` branch
2. **`.env.example`** documenting required Aito environment variables
3. **`./do` task runner** with `help` and `demo` commands (demo opens
   the HTML mockup in a browser)
4. **Documentation stubs** — README, demo script, aito cheatsheet — so
   the structure exists for future features to fill in
5. **This ADR** as the first architectural record

The HTML mockup serves as the demo until we wire features to a live
Aito instance. `./do demo` opens it directly — no build step.

## Aito usage

None in this ADR. This is pure project infrastructure.

## Acceptance criteria

- A developer can clone the repo, run `./do help`, and see available commands
- `./do demo` opens the HTML mockup in a browser
- `.env.example` documents the required Aito variables
- `.gitignore` excludes `.venv/`, `node_modules/`, `.env`, and IDE files
- `docs/` structure exists: `adr/`, `notes/`, `sessions/`, `verification/`

## Demo impact

Establishes `./do demo` as the canonical way to run the demo. Future
features update the demo; this ADR creates the entry point.

## Out of scope

- Application source code (no `src/` yet)
- Tests (nothing to test yet)
- Live Aito integration
- CI/CD pipeline
