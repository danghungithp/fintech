---
kind: external_dependency
name: Vercel Serverless Deployment Target
slug: vercel
category: external_dependency
category_hints:
    - framework_behavior
    - client_constraint
scope:
    - '**'
---

### Vercel
- Role: production serverless host for the Flask app; `vercel.json` declares `api/index.py` as a Python 3.12 function with `maxDuration=60s` and rewrites all routes through it.
- Constraint: filesystem is read-only except `/tmp`; `config.py` detects via `VERCEL` env var and switches `DATA_DIR` to `/tmp/finviet-pro`. Persistent storage requires setting `FINTECH_DATA_DIR` to an external volume (VPS/Render/Railway).
- Verify exact runtime limits and include rules against official Vercel docs.