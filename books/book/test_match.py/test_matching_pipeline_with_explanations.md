# Full matching pipeline with explanations

The pipeline: _predict vendor_name → find matching invoices
→ rank by amount proximity → build explanation.


## TELIA FINLAND OY → Telia Finland

  status=matched  confidence=0.64
  description        "telia" (lift 15.75x)
  description        "finland" (lift 15.75x)
  description        "oy" (lift 0.89x)
  invoice_id         "INV-2696" (prior 0.0061)
  amount             exact match (890.5)


## KESKO OYJ HELSINKI → Kesko Oyj

  status=matched  confidence=0.62
  description        "kesko" (lift 17.89x)
  description        "oyj" (lift 17.89x)
  invoice_id         "INV-2717" (prior 0.0043)
  amount             exact match (4220.0)


## SOK CORPORATION → SOK Corporation

  status=matched  confidence=0.62
  description        "corporation" (lift 62.96x)
  description        "sok" (lift 62.96x)
  invoice_id         "INV-2819" (prior 0.0043)
  amount             within 0.5% (diff 2.00)

Explanation shows: description tokens (lift from Aito $why),
vendor_name prior, and amount proximity.
