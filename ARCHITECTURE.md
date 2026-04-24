# Architecture Document

## System Overview

A multi-agent LangGraph pipeline that processes health insurance claims from document submission through policy adjudication to a final decision. Every step is recorded in PostgreSQL so any decision can be fully reconstructed after the fact.

---

## Component Map

```
Browser (React)
    │
    ▼ POST /api/claims  (JSON)
    │ POST /api/claims/upload  (multipart files)
    │
FastAPI (main.py)
    │
    ▼  builds initial ClaimState, calls run_claim_pipeline()
    │
LangGraph StateGraph  ──────────────────────────────────────────────
    │
    ├─► [1] validate_documents_node
    │       Checks document types match claim category.
    │       Checks for unreadable (UNREADABLE quality) files.
    │       → should_stop=True for wrong/missing/unreadable docs (TC001–TC002)
    │
    ├─► [2] extract_documents_node
    │       If content provided → use directly (test/structured mode)
    │       If image_base64 provided → GPT-4o vision API
    │       If simulate_component_failure → marks FAILED, continues (TC011)
    │
    ├─► [3] cross_validate_node
    │       Extracts patient_name from each document.
    │       Stops if names differ across documents (TC003).
    │
    ├─► [4] check_policy_node
    │       Runs checks in priority order:
    │         1. Exclusions (categorical: never covered)
    │         2. Waiting period (only if not excluded)
    │         3. Pre-authorization (before per-claim limit)
    │         4. Per-claim limit (skipped if pre-auth missing)
    │         5. Annual OPD limit (ytd_claims_amount + new claim)
    │
    ├─► [5] check_fraud_node
    │       Same-day claim count vs. policy limit → MANUAL_REVIEW
    │       High-value claim threshold check
    │       Fraud score calculation
    │
    └─► [6] make_decision_node
            Aggregates all check outputs.
            Calculates: network discount → copay → approved amount.
            Assigns confidence (degrades with component failures / fraud flags).
            Produces: APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW
    │
    ▼
PostgreSQL
    ├── claims          (one row per claim + final result)
    ├── claim_documents (one row per uploaded file)
    └── claim_trace     (one row per pipeline node execution)
```

---

## Key Design Decisions

### Multi-agent via LangGraph
Each node has a single responsibility, a defined input (ClaimState keys it reads), and a defined output (keys it writes back). Nodes can be tested independently. Conditional edges allow early termination without exceptions — the graph just routes to `END` when `should_stop=True`.

**Why LangGraph over a plain function chain:** explicit state machine, built-in async, easy to add/remove/reorder nodes, and the graph structure itself serves as documentation.

### Check ordering in the policy node
Exclusions → Waiting period → Pre-auth → Per-claim limit. This order matters:
- An excluded treatment should never also show a waiting-period message (confusing and irrelevant).
- A missing pre-auth is the primary actionable rejection for high-value tests; surfacing a per-claim limit violation on top would mislead the member.

### Word-boundary waiting-period matching
`re.search(r'\bhernia\b', diagnosis)` instead of `"hernia" in diagnosis` prevents "herniation" from triggering the hernia waiting period. Same pattern for all specific conditions.

### GPT-4o vision for extraction
Documents are images of handwritten prescriptions, rubber-stamped bills, phone photos. A structured regex/OCR pipeline cannot handle this variety reliably. GPT-4o returns JSON directly via `response_format={"type": "json_object"}`. For test cases that supply structured `content`, the GPT-4o call is skipped entirely — making tests fast and free.

### Policy loaded from JSON, not hardcoded
`policy.py` reads `policy_terms.json` once and caches it. All limits, co-pays, waiting periods, exclusions, network hospitals, and member rosters come from this file. Changing the policy requires only changing the JSON.

### Graceful degradation (TC011)
When a node fails (simulated or real), it:
1. Appends a `FAILED` trace entry with the error.
2. Adds itself to `component_failures`.
3. Returns empty data for its output keys (pipeline continues).
The `make_decision_node` reads `component_failures` and reduces `confidence_score` by 0.15 per failure, and adds a manual-review warning.

---

## What I Considered and Rejected

| Option | Why Rejected |
|--------|-------------|
| Sync FastAPI endpoints | Async is needed for concurrent GPT-4o calls during extraction |
| SQLite | Rejected per requirements; also poor for concurrent writes |
| LLM for policy adjudication | Non-deterministic; policy rules are precise enough for deterministic code |
| Per-request DB writes from graph nodes | Simpler to write once at the end; trace is in-memory during graph execution |
| Separate microservices per agent | Over-engineered for this scale; LangGraph nodes give the same separation with less infra |

---

## Limitations and 10× Scaling

### Current Limitations
- Document extraction is synchronous per document (GPT-4o calls are awaited sequentially).
- No auth or tenant isolation — all members share one DB.
- No retry logic for GPT-4o timeouts beyond the graceful-degradation path.
- Policy version is not stored with the claim — future policy changes would reinterpret historical claims differently.

### At 10× Load (~750,000 claims/year)
- **Extraction parallelism**: `asyncio.gather()` to call GPT-4o for multiple documents concurrently.
- **Queue-based processing**: decouple claim submission (fast HTTP response) from pipeline execution (background worker via Celery/RQ). Return `claim_id` immediately, poll or webhook for result.
- **Read replicas**: route `GET /api/claims` to a read replica.
- **Policy versioning**: add a `policy_version` column to `claims` so historical adjudications remain reproducible.
- **LangGraph Cloud / LangSmith**: for tracing, replay, and debugging at scale.
