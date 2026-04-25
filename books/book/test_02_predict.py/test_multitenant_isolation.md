# Multi-tenant isolation

Same vendor should predict different GL codes per customer,
because each customer has their own routing patterns.


## Vendor: Security Venture Oy

  CUST-0000 ( 2000 invoices): GL 5100   p=0.7095
  CUST-0003 (  500 invoices): GL 5100   p=0.5856
  CUST-0010 (  250 invoices): GL 5100   p=0.7656
  CUST-0100 (   32 invoices): GL 4100   p=0.3370

Different GL codes per customer = multi-tenancy working.
