# Schema writes to the production demo database are refused

`src/schema_write_guard.py` runs inside both Aito clients. A schema `PUT` or
`DELETE` aimed at `shared.aito.ai/db/aito-accounting-demo` (v1, or v2 `master`)
raises `ProdSchemaWriteRefused` before a request is sent. Why: on 2026-09-20 a
loader run aimed at localhost wrote a v1 schema to prod.

- Not guarded: reads, data inserts, v2 branch environments, any other host.
- Not guarded on purpose: the app's own `cache_entries`, `cache_versions` and
  `precompute_entries`, which it creates at every startup.
- Deliberate override: `AITO_ALLOW_PROD_SCHEMA_WRITE=1` **and**
  `AITO_PROD_SCHEMA_CONFIRM=aito-accounting-demo`.
- Limit: it matches host + database path (port, case, `//`, trailing `/api/v1|v2` all match). A prod database reached through another hostname
  or proxy is not recognised.
