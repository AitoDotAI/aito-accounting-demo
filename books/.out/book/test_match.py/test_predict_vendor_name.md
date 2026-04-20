# _predict vendor_name from bank description

The vendor_name Text field enables Aito to tokenize and match
bank descriptions like 'KESKO OYJ HELSINKI' to vendor 'Kesko Oyj'.
This is more reliable than _match for vendor resolution.

  TELIA FINLAND OY          → Telia Finland        p=0.4593  [ok]
  KESKO OYJ HELSINKI        → Kesko Oyj            p=0.1985  [ok]
  SOK CORPORATION           → SOK Corporation      p=0.0998  [ok]
  FAZER GROUP OY            → Fazer Bakeries       p=0.1965  [ok]
  VERKKOKAUPPA.COM          → Verkkokauppa.com     p=0.2000  [ok]
  KONE                      → Kone Oyj             p=0.1423  [ok]
  ISS PALVELUT              → ISS Palvelut         p=0.1990  [ok]
  UNKNOWN TRANSFER          → Verkkokauppa.com     p=0.0108  [low-p]

Accuracy: 7/7 vendors matched correctly.

_predict on the Text vendor_name field uses token analysis to
match partial and case-insensitive descriptions reliably.
