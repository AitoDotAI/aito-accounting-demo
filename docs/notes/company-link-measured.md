# Company link in the invoice queries: held-out accuracy (ADR 0031 step A)

> Synthetic fixtures. Pre-registered in `docs/notes/company-link-preregistration.md`; `scripts/measure_company_link.py` against Aito 2.11.6, 2026-10-18 12:13 Helsinki.

| target | test invoices | without link | with link | only without right | only with right | exact McNemar p |
|---|---|---|---|---|---|---|
| gl_code | 1700 | 93.2% | 92.6% | 22 | 12 | 0.121 |
| approver | 1700 | 79.2% | 73.9% | 145 | 56 | 2.77e-10 |
