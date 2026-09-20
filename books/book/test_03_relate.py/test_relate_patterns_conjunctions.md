# Conjunction rule discovery: $patterns (CUST-0000)


  gl_code = 1600:
    category="software" AND vendor="TMT-Software Technologies Oy" AND amount_band="large"  lift=29.6
    category="maintenance" AND amount_band="large" AND vendor="WSP Suunnittelukortes Oy"  lift=29.4
    category="software" AND amount_band="large" AND vendor="Roima Intelligence Oy"  lift=29.4

  approver = CUST-0000-EMP-0006:
    amount_band="large" AND vendor="EEE Energy Ecology Engineering Oy"  lift=2.2
    amount_band="medium" AND vendor="Kardex Finland Oy"  lift=0.0
    amount_band="large" AND vendor="Dottoressa Oy"  lift=2.2
    amount_band="medium" AND category="insurance" AND vendor="Talotilit Oy"  lift=0.0

Counts above are $patterns' smoothed estimates; the service uses
exact _search counts for the displayed support.
