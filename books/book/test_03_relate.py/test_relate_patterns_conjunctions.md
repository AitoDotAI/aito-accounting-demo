# Conjunction rule discovery: $patterns (CUST-0000)


  gl_code = 1600:
    vendor="Bronex Software Oy" AND amount_band="large"  (~144/145 est, 99%)  lift=23.5
    vendor="TMT-Software Technologies Oy" AND category="software"  (~195/204 est, 96%)  lift=22.8
    vendor="K. Itäluoma Oy" AND category="maintenance"  (~322/353 est, 91%)  lift=21.9

  approver = Markku Heikkinen:
    vendor="Avarn Security Oy" AND amount_band="large"  (~909/909 est, 100%)  lift=3.1
    vendor="Kuljetusliike Rosenberg-Boman Oy" AND category="logistics"  (~824/993 est, 83%)  lift=2.6
    vendor="Kardex Finland Oy" AND amount_band="medium"  (~10/1790 est, 1%)  lift=0.0
    vendor="EEE Energy Ecology Engineering Oy" AND category="supplies"  (~10/3359 est, 0%)  lift=0.0

Counts above are $patterns' smoothed estimates; the service uses
exact _search counts for the displayed support.
