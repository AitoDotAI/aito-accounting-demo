# CLAUDE.md — OSS Reference Project

## What this project is

This is a public, open-source reference project demonstrating Aito.ai's
predictive database capabilities in a real-world vertical. It serves three
purposes simultaneously:

1. **Working demo** — a functional application with a compelling demo path
2. **Reference implementation** — production-quality code that CTOs and
   developers evaluate when considering Aito
3. **Learning resource** — readable code, clear ADRs, and well-named tests
   that teach how to use Aito

The code IS the sales collateral. An outside developer reading this repo
should think: "these people know what they're doing, and Aito is
straightforward to integrate." Every file, test, and commit message
contributes to or detracts from that impression.

---

## Prime directives

These never relax.

1. **Diagnose before you fix.** If you don't understand why something is
   broken, stop and say so. Don't stack workarounds.

2. **Never silently filter, coerce, or discard unexpected data.** Assert
   and fail loudly. Silent handling hides bugs and teaches wrong patterns
   to developers reading this code.

3. **Aito queries are not in your training data.** Never invent query
   shapes, endpoints, or field semantics. Consult `docs/aito-cheatsheet.md`
   and the linked Aito documentation. When unsure: write the query, run it
   against test data, inspect the response structure, and confirm it
   matches expectations before building on it.

4. **Write for the reader, not the machine.** Every file will be read by a
   developer evaluating whether to adopt Aito. Name things clearly. Keep
   files focused. Let structure tell the story.

---

## Project structure

```
├── CLAUDE.md                  # You are here
├── README.md                  # Three-audience README (see below)
├── docs/
│   ├── adr/                   # Architecture Decision Records
│   │   └── 0000-template.md   # ADR template
│   ├── aito-cheatsheet.md     # Aito query patterns, gotchas, examples
│   ├── demo-script.md         # The canonical demo walkthrough
│   ├── notes/                 # Durable self-notes (gotchas, invariants)
│   ├── sessions/              # Session logs
│   └── verification/          # Adversary verification reports
├── src/                       # Application source
├── tests/                     # Test suite (doubles as usage examples)
├── do                         # Task runner (see below)
└── ...
```

---

## Feature workflow

Each feature is a branch → PR → merge to main.

### 1. ADR — `docs/adr/NNNN-title.md`

Write the ADR before any code. ADRs in this project are externally
legible — an outside developer should understand the decision and its
rationale without project-internal context.

Every ADR contains:
- **Context**: What problem or capability this addresses
- **Decision**: What we're building and how
- **Aito usage**: Which query types, which data, expected behavior
- **Acceptance criteria**: User-visible, testable, written as "A user
  can..." or "When X happens, Y is shown"
- **Demo impact**: How this affects `docs/demo-script.md`
- **Out of scope**: What this deliberately does not do

### 2. Tests

Tests are required, not optional. In an OSS reference project, tests
serve double duty:

- **Correctness gate**: the obvious purpose
- **Usage documentation**: a well-structured test file is the most
  concrete tutorial for how to use Aito in this context

Write tests that an outside developer can read as examples. Use clear
names: `test_predict_returns_top_account_for_known_invoice_pattern`,
not `test_predict_1`. Arrange/act/assert structure. Comments where the
"why" isn't obvious.

Required test coverage:
- All Aito query logic (predict, recommend, similarity, etc.)
- Data transforms between app domain and Aito schema
- Critical UI paths via Playwright (see adversary verification below)

Not required:
- Pure boilerplate/glue (routing setup, config loading)
- Aspirational edge cases that aren't in the demo path

### 3. Implementation

Write the minimum clean code to make the tests pass. "Clean" here means
readable and well-structured, not minimal-LOC. Specifically:

- **One responsibility per file.** A file that does two things should be
  two files. Target ~200 lines max; split at ~300.
- **Name for the reader.** `aito_query_builder.py` not `utils.py`.
  `PredictionResult` not `Result`. Function names state what they do.
- **Comments explain WHY, not WHAT.** Exception: Aito-specific patterns
  where the what is unfamiliar to the reader. For those, a brief
  `# Aito's _predict endpoint expects the target field as the key...`
  style comment helps.
- **No dead code, no commented-out blocks, no TODOs without issue links.**
  Every line in the repo should look intentional.

### 4. Verification

Run `./do verify <feature>`. This invokes the adversary agent — a
separate CC instance with Playwright whose job is to **find failures**,
not confirm success. See the adversary section below.

Review the verification report before merging.

### 5. Documentation pass

Before merging, check:
- README still accurate? Quick-start still works?
- `docs/demo-script.md` updated if demo path changed?
- `docs/aito-cheatsheet.md` updated if new Aito patterns used?
- ADR marked as accepted?

### 6. Merge to main

Squash merge. Write a commit message an outside reader would understand.
Main must be demo-runnable at all times — `./do demo` works on main,
always.

---

## Adversary verification

`./do verify <feature>` runs a separate agent with Playwright tasked
with **breaking** the feature, not confirming it.

The adversary gets:
- The ADR acceptance criteria
- The running app
- Playwright + screenshot/DOM-snapshot helpers

It produces `docs/verification/<feature>.md`:
- Steps attempted (including edge cases and invalid inputs)
- Screenshots at key states
- Network calls observed — especially Aito requests and responses
- Failure paths found, OR explicit: "No failures found after trying:
  [list of scenarios attempted]"

Merge is blocked until the verification report exists. The adversary is
not authoritative — Antti is — but the report makes async review
possible.

### Aito query sanity

`./do aito-check` runs all Aito queries against the PoC dataset and
asserts:
- Response structure matches expected shape
- Probabilities in [0, 1]
- Recommendations non-empty for known-good inputs
- Predictions contain expected fields
- No silent null / empty-list returns where data should exist

When you add a new Aito query pattern, add its sanity assertion in the
same PR.

---

## The `./do` script

All common workflows live in `./do`. Run `./do help` for the full list.

Core commands:
- `./do dev` — start the app in development mode
- `./do test` — run the test suite
- `./do verify <feature>` — adversary Playwright verification
- `./do verify-demo` — end-to-end demo path check
- `./do aito-check` — Aito query sanity checks
- `./do check` — all of the above (the pre-merge gate)
- `./do demo` — run the demo from a clean state
- `./do fmt` — format code

If you run the same multi-step command twice, add it to `./do` in the
same PR.

---

## README structure

The README serves three audiences. Maintain this structure:

1. **What this is** (2-3 sentences) — what the app does, that it
   demonstrates Aito.ai, link to Aito docs
2. **See it in action** — screenshot or GIF of the demo path
3. **Quick start** — clone, configure, run. Under 5 steps. Must work.
4. **How it works** — architecture overview: app ↔ Aito data flow,
   which Aito features are used and why
5. **Project structure** — directory guide for code readers
6. **ADRs** — link to `docs/adr/` with one-line summaries
7. **Learn more** — links to Aito docs, blog posts, related projects

---

## Autonomy rules

### Do autonomously
- Feature implementation following the workflow above
- `./do` script additions
- Documentation updates
- File organization and naming improvements (as their own PR)
- Writing self-notes in `docs/notes/`
- Picking the next feature from the plan when the current one is merged

### Propose before implementing
Write a short proposal in the ADR or as a comment, and wait:
- Any Aito query pattern not already in `docs/aito-cheatsheet.md`
- Changes to the demo path
- Adding dependencies
- Anything where you're not confident the Aito usage is correct

### Stop and escalate
- Two failed attempts at the same bug — describe what you tried
- Aito returns unexpected data and you're unsure if it's a query error
  or a data issue
- The adversary verification found a failure you can't reproduce or fix
- You're about to add a workaround or try/except that hides an error

---

## Session log

End of each session: append to `docs/sessions/YYYY-MM-DD.md`.

- What shipped (PR numbers)
- What's blocked or stuck
- Aito quirks discovered
- Anything surprising

Two sentences per item. This is for the next session's context.

---

## Code style and conventions

- Consistent with the language ecosystem's conventions (PEP 8 / ESLint
  defaults / etc.)
- Imports organized: stdlib → third-party → local
- No abbreviations in public names except universally understood ones
  (id, url, http)
- Error messages include enough context to diagnose without a debugger:
  `f"Prediction failed for invoice {invoice_id}: Aito returned {status}"`
  not `"Prediction failed"`
- Aito client calls wrapped in a thin service layer — never raw HTTP
  calls scattered through business logic

---

## What this project does NOT want

- **Speculative abstraction.** No interfaces, factories, or indirection
  until the second concrete use. This is a reference project — readers
  should see the direct path, not layers of architecture.
- **Framework maximalism.** Use the simplest tool that works. The reader
  should be learning about Aito, not about your framework choices.
- **Clever code.** If a reviewer has to think twice to understand a line,
  rewrite it to be obvious. Boring, clear code is the goal.
- **Coverage theater.** Don't write tests for boilerplate. Write tests
  that show how Aito works and catch real regressions.
