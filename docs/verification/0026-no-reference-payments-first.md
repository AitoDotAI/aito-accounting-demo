# Verification — ADR 0026, payments that quote no reference come first

**Date:** 2026-09-28 · **Branch:** `feat/no-reference-payments-first` ·
**Data:** v2 environment `v2-demo`

**Method.** The pass was run by hand, not as a separate adversary instance
(`./do verify` does not exist yet). The frontend came from this branch's
`next dev`. `/api/matching/pairs` was computed live by this branch's
`match_all`, and every other `/api/*` call went to production. The page was
driven in Chrome at a width of 946 px.

## Verdict

All acceptance criteria hold. The pass found one defect: a match by
reference hid a short or over payment. It is fixed on this branch. One
limitation remains and is noted below.

## Acceptance criteria

| Criterion | Result |
|---|---|
| First six rows quote no reference, each with an Aito confidence and a why panel | ✅ CUST-0000: `DB-FIN KARDEX FINLAND OY`, `K.H.N.-MARKETING / 07.05.24`, … all `matched_by: aito`, 0.71–0.99 |
| First auto-expanded why panel is an unreferenced payment | ✅ row 1 (Kardex, no reference); factors are amount, `DB-FIN`, `KARDEX`, `vendor_name` |
| Quoted reference → *Matched by reference*, 100%, no explanation | ✅ rows 7–8 show a grey `ref` badge and no why panel; unit test asserts no `_predict` is sent |
| Reference matching no open invoice goes to Aito | ✅ unit test `test_returns_none_when_no_open_invoice_is_quoted` plus the fall-through in `match_reference_first` |
| Metrics count reference and Aito matches separately | ✅ cards: Matched by Aito 6 · Avg Aito confidence 0.85 · Matched by reference 2 · Unmatched 0 |
| `./do eval-matching` splits referenced / unreferenced | ✅ v2-demo, 25 payments, 55-invoice ledger: quoted 12/12, **no reference 13/13**, all 25/25 |
| `./do aito-check` asserts ≥ 6 Aito matches | ✅ `6 matched by Aito, 2 by reference / 8 pairs` |

## Scenarios tried to break it

- **Other tenants.** `match_all` was run live for CUST-0000, 0001, 0002,
  0003 and 0007. Each gave 6 Aito matches, 2 reference matches and 0
  unmatched, in 3–7 s.
- **Tenants with few payments.** Every sixth tenant was checked, 43 in
  all. Each has at least 6 unreferenced and 2 referenced payments within
  the 40-payment window, so none gets a short page.
- **Each bank's reference format.** Handelsbanken `Saaja VIITE n`, Nordea
  `Viite: n`, Aktia `ref=VIITE n`, Danske without the label, and an `RF`
  reference split across spaces all count as quoted (unit tests).
- **Digits inside a date.** Reference `2402` inside `24022026` is not a
  quote (unit test).
- **Two open invoices quoted by one line.** This raises an error naming
  both invoices rather than picking one (unit test).
- **Stale precompute.** A payload built before this change has no
  `matched_by`, and `./do verify-demo` now fails on it with "stale
  precompute? run ./do precompute-v2".

## Failure found and fixed

**A reference match hid a short or over payment.** About half of the
referenced payments differ from their invoice by €0.50–1.00: 575 in the
43-tenant sample. The lookup matched them at 100% with nothing to show
that the amounts disagree. CUST-0000's Kardex row was paid €1 854,80
against an invoice of €1 853,80. The row now says **overpaid €1,00**
(or underpaid), and this was added to the ADR's acceptance criteria.

## Known limitation, not fixed

- At a width of about 950 px, with the navigation and the Aito panel
  both open, the top bar is cramped on every page, not only this one.
  This change shortened the matching subtitle to
  `8 payments · open ledger of 30` so that it no longer runs under the
  bar.
