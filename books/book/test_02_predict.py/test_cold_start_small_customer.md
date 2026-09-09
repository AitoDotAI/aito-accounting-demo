# Cold start: small customer prediction

Small customers have fewer invoices. How confident is Aito?

  CUST-0063 (250 invoices): vendor=Oy Aahan Thai Ltd         -> GL 5400   p=0.9836
  CUST-0064 (250 invoices): vendor=Pangea Telecommunications -> GL 6200   p=0.9836
  CUST-0065 (250 invoices): vendor=HS Cleaning Oy            -> GL 5100   p=0.9238

Confidence decreases with fewer invoices — honest uncertainty.
