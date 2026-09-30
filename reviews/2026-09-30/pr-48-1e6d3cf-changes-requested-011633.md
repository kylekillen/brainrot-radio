### 2026-09-30 01:16 — PR #48 review: changes requested

Reviewed head: `1e6d3cfab7e6df08837710286dac950f128729c5`.

Decision: changes requested.

- Correctness: fails. `free_lane_diag.py:77-78` classifies an endpoint as local by substring. A billable remote endpoint such as `https://localhost.billing-provider.example/v1` is classified `free`, so the burn-degraded gate allows its dispatch. This defeats the cost ceiling. Parse the URL and accept only exact loopback/local hostnames (and add a regression test).
- Coherence: otherwise consistent with the shared route classification and the existing fallback flow.
- Smallness: scoped to reporting plus the requested billing guard.
- Hosted CI: green on the reviewed head (`pytest`, two completed successful runs). Local targeted gate tests: 37 passed. A local full-suite attempt could not collect unrelated modules under the available Python 3.9 environment because `feedgen` is unavailable and another module uses Python 3.10 union syntax; hosted CI remains the authoritative gate.
