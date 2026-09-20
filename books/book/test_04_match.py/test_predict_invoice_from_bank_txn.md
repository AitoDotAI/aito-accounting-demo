# Payment matching: _predict invoice_id

Bank transaction -> invoice via schema link traversal.

The candidate domain is the OPEN LEDGER, not every invoice the
tenant has. Ranking all ~2000 makes the true invoice compete with
rows that were never outstanding, and it loses whenever the payment
quotes no reference number. Both shapes are shown below.


## Unscoped — ranks every invoice the tenant has

  KARDEX FINLAND  Saaja  VI €  1,854.80  ->  Kardex Finland Oy    p=0.0708
  OY BOTNIA-FOTO AB VANTAA  €  1,756.00  ->  Oy Botnia-Foto Ab    p=0.0005
  AVARN SECURITY OY  Saaja  €  7,113.00  ->  Oy Finnish Medical F p=0.0000
  SECURITY VENTURE OY VIITE €  6,470.50  ->  Security Venture Oy  p=0.0000
  AVARN SECURITY 15072025 V € 12,859.50  ->  Avarn Security Oy    p=0.0001


## Scoped to the open ledger

  KARDEX FINLAND  Saaja  VI €  1,854.80  ->  Kardex Finland Oy    p=0.9437 [ok]
  OY BOTNIA-FOTO AB VANTAA  €  1,756.00  ->  Oy Botnia-Foto Ab    p=0.3544 [ok]
  AVARN SECURITY OY  Saaja  €  7,113.00  ->  Avarn Security Oy    p=0.4608 [ok]
  SECURITY VENTURE OY VIITE €  6,470.50  ->  Security Venture Oy  p=0.1042 [ok]
  AVARN SECURITY 15072025 V € 12,859.50  ->  Inside Restaurant Se p=0.1141

Scoping raises $p by orders of magnitude, because the probability
is now spread over the invoices that could actually be settled.
