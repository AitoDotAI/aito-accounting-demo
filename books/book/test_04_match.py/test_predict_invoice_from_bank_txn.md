# Payment matching: _predict invoice_id

Bank transaction -> invoice via schema link traversal.

  KARDEX FINLAND  Saaja  VI €  1,854.80  ->  Kardex Finland Oy    p=0.0703
  OY BOTNIA-FOTO AB VANTAA  €  1,756.00  ->  Oy Botnia-Foto Ab    p=0.0001
  AVARN SECURITY OY  Saaja  €  7,113.00  ->  Avarn Security Oy    p=0.0000
  SECURITY VENTURE OY VIITE €  6,470.50  ->  Security Venture Oy  p=0.0001
  AVARN SECURITY 15072025 V € 12,859.50  ->  Avarn Security Oy    p=0.0000

Matches scoped to CUST-0000 via customer_id in where clause.
