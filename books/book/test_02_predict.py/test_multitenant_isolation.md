# Multi-tenant isolation

Same vendor should predict different GL codes per customer,
because each customer has their own routing patterns.


## Vendor: Kardex Finland Oy

  CUST-0000 (16000 invoices): GL 4400   p=0.9753
  CUST-0003 ( 4000 invoices): GL 4400   p=0.9214
  CUST-0010 ( 2000 invoices): GL 4400   p=0.9836
  CUST-0100 (  250 invoices): GL 4400   p=0.9675

Different GL codes per customer = multi-tenancy working.
