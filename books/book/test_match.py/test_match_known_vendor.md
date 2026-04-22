# _match: KESKO OYJ HELSINKI → invoices

Aito's _match traverses bank_transactions.invoice_id → invoices
and returns full invoice rows ranked by association strength.


## Top matches

  INV-2628     vendor=Kesko Oyj            amount=   1599.57  p=0.1895
  INV-2744     vendor=Kesko Oyj            amount=   5186.26  p=0.1895
  INV-2717     vendor=Kesko Oyj            amount=   2952.50  p=0.0948
  INV-2748     vendor=Kesko Oyj            amount=   4290.07  p=0.0948
  INV-2769     vendor=Kesko Oyj            amount=   6962.36  p=0.0948

ok

Note: $p=0.1895 is low in absolute terms because
probability is spread across 230 invoices.
