# Strategy 4: Hybrid — _predict vendor + amount ranking

Step 1: _predict vendor_name from description (text analysis)
Step 2: Find invoices matching that vendor
Step 3: Rank by amount proximity

This is the current production approach.

  TELIA FINLAND OY          → Telia Finland        INV-2838     p=0.4593  ok
  KESKO OYJ HELSINKI        → Kesko Oyj            INV-2835     p=0.1985  ok
  SOK CORPORATION           → SOK Corporation      INV-2839     p=0.0998  ok
  FAZER GROUP OY            → Fazer Bakeries       INV-2840     p=0.1965  ok
  UNKNOWN TRANSFER          → no match

Hybrid gives best results: text analysis for vendor,
amount proximity for specific invoice selection.
