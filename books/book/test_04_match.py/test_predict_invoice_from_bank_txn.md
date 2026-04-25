# Payment matching: _predict invoice_id

Bank transaction -> invoice via schema link traversal.

  SECURITY VENTURE OY       €    914.00  ->  Security Venture Oy  p=0.3686
  KIINTEISTÖ OY TÖRMÄNIITYN € 31,535.00  ->  Kiinteistö Oy Törmän p=0.3686
  AB TRANSPORT HELGE KULL O € 24,899.50  ->  Ab Transport Helge K p=0.6293
  EEE ENERGY ECOLOGY ENGINE €  4,389.50  ->  EEE Energy Ecology E p=0.1136
  SECURITY VENTURE OY       €    846.00  ->  Security Venture Oy  p=0.3686

Matches scoped to CUST-0000 via customer_id in where clause.
