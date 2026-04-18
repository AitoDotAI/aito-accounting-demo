# 0010. README, demo script, and polish

**Date:** 2026-04-18
**Status:** accepted

## Context

All major demo features are implemented. The project needs a README
that serves the three audiences defined in CLAUDE.md, an updated demo
script reflecting live views, and a final consistency pass.

## Decision

1. **README** following the three-audience structure: what this is,
   quick start, how it works, project structure, ADRs, learn more
2. **Demo script** updated with all 6 live views and key narratives
3. **Consistency pass** — verify all commands work, test suite passes

## Acceptance criteria

- README quick start works from clone to running demo
- Demo script covers all live views with operator callouts
- `./do test` passes
- `./do dev` + HTML demo shows live data

## Demo impact

This is the final documentation pass. After this, the repo is
ready for external evaluation.

## Out of scope

- Screenshots/GIFs (need manual capture)
- CI/CD pipeline
- Deployment documentation
