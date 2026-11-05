# Payment matching: _predict invoice_id

Bank transaction -> invoice via schema link traversal.

The candidate domain is the OPEN LEDGER, not every invoice the
tenant has. Ranking all ~2000 makes the true invoice compete with
rows that were never outstanding, and it loses whenever the payment
quotes no reference number. Both shapes are shown below.


## Unscoped — ranks every invoice the tenant has

  KARDEX FINLAND  Saaja  VI €  1,854.80  ->  Kardex Finland Oy    p=0.0787
  OY BOTNIA-FOTO AB VANTAA  €  1,756.00  ->  Oy Botnia-Foto Ab    p=0.0005
  AVARN SECURITY OY  Saaja  €  7,113.00  ->  Avarn Security Oy    p=0.0093
  SECURITY VENTURE OY VIITE €  6,470.50  ->  Security Venture Oy  p=0.0499
  AVARN SECURITY 15072025 V € 12,859.50  ->  Avarn Security Oy    p=0.0089


## Scoped to the open ledger

  KARDEX FINLAND  Saaja  VI €  1,854.80  ->  Kardex Finland Oy    p=0.9849 [ok]
  OY BOTNIA-FOTO AB VANTAA  €  1,756.00  ->  Oy Botnia-Foto Ab    p=0.9203 [ok]
  AVARN SECURITY OY  Saaja  €  7,113.00  ->  Avarn Security Oy    p=0.9744 [ok]
  SECURITY VENTURE OY VIITE €  6,470.50  ->  Security Venture Oy  p=0.9866 [ok]
  AVARN SECURITY 15072025 V € 12,859.50  ->  Avarn Security Oy    p=0.8587 [ok]

Scoping raises $p by orders of magnitude, because the probability
is now spread over the invoices that could actually be settled.
