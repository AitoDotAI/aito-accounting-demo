"""PUBLIC_DEMO: the deployment anyone on the internet can use.

Every visitor of the public demo writes to and reads from the same Aito
instance, so in this mode nothing a visitor types is stored: a Form Fill
submit logs its outcome without the values, a help impression logs the
article and page without the search, and a Form Fill prediction (whose
cache key is the typed input) is not cached. Set PUBLIC_DEMO=1 (or true,
yes) in the deployment's environment; it is off by default, as in the
ERP and e-commerce demos.
"""

import os

ENABLED = os.environ.get("PUBLIC_DEMO", "").strip().lower() in ("1", "true", "yes")
