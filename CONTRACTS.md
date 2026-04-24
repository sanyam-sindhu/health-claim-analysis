# Component Contracts

Each node in the LangGraph pipeline is a pure function on `ClaimState`. These contracts are precise enough to reimplement any node without reading its code.

---

## 1. `validate_documents_node`

**Reads from state:** `claim_category`, `documents[]`

**Writes to state:**
```
doc_validation: { valid: bool }
should_stop:    bool
stop_message:   str | None   — populated when should_stop=True
trace:          trace + new entry
```

**Logic:**
1. Load `document_requirements[claim_category].required` from policy.
2. If any document has `quality == "UNREADABLE"` → `should_stop=True`, message names the file and asks for re-upload.
3. Count uploaded doc types vs. required doc types. If a required type is missing:
   - If an extra doc was uploaded in its place → "You uploaded a '{extra}' where a '{required}' is required."
   - Otherwise → "Missing required document: '{required}'."
4. Append the full required list to the message for context.

**Errors it can raise:** None — all failures are surfaced via `stop_message`.

---

## 2. `extract_documents_node`

**Reads from state:** `documents[]`, `simulate_component_failure`

**Writes to state:**
```
extracted_docs:     List[{ file_id, type, data: dict }]
component_failures: list + failures from this node
trace:              trace + new entry
```

**Logic:**
1. If `simulate_component_failure=True` → append `FAILED` trace entry, add `"extract_documents"` to `component_failures`, return `extracted_docs=[]`.
2. For each document:
   - If `patient_name_on_doc` is set → seed `data["patient_name"]` with it.
   - If `content` is present → merge with seed data; no API call.
   - If `image_base64` is present → call GPT-4o vision (`gpt-4o`, `response_format=json_object`). On error: log to `component_failures`, return empty `data`.
   - Otherwise → return seed data only.

**GPT-4o extraction fields:** `patient_name`, `doctor_name`, `doctor_registration`, `hospital_name`, `date`, `diagnosis`, `medicines[]`, `tests_ordered[]`, `treatment`, `line_items[{description, amount}]`, `total_amount`.

**Errors it can raise:** Catches `openai.APIError` per document; does not raise.

---

## 3. `cross_validate_node`

**Reads from state:** `extracted_docs[]`

**Writes to state:**
```
cross_validation: { valid: bool, skipped?: bool }
should_stop:      bool
stop_message:     str | None
trace:            trace + new entry
```

**Logic:**
1. If `extracted_docs` is empty → `skipped=True`, `valid=True` (nothing to compare).
2. For each extracted doc, read `data.patient_name` (case-insensitive).
3. If unique names > 1 → `should_stop=True`. Message lists `"'{name}' on document {file_id}"` for each doc.

**Errors it can raise:** None.

---

## 4. `check_policy_node`

**Reads from state:** `member_id`, `claim_category`, `claimed_amount`, `hospital_name`, `treatment_date`, `extracted_docs[]`, `ytd_claims_amount`

**Writes to state:**
```
member:              dict | None
policy_check: {
  passed:            bool,
  checks:            List[{ check, passed, detail }],
  issues:            List[str],
  rejection_reasons: List[str],   — subset of enum below
  net_claimable:     float
}
line_item_decisions: List[{ description, amount, approved, reason }] | None
trace:               trace + new entry
```

**Check order and rejection reason enum:**
| Order | Check | Reason |
|-------|-------|--------|
| 1 | Global policy exclusions (diagnosis keyword match, word-boundary) | `EXCLUDED_CONDITION` |
| 2 | Specific condition waiting period (only if not excluded) | `WAITING_PERIOD` |
| 3 | Pre-authorization required (DIAGNOSTIC + high-value tests) | `PRE_AUTH_MISSING` |
| 4 | Per-claim / sub-limit (skipped if pre-auth missing or excluded) | `PER_CLAIM_EXCEEDED` |
| 5 | Annual OPD limit (50,000 INR, uses ytd_claims_amount) | `ANNUAL_LIMIT_EXHAUSTED` |

**Dental partial logic:** when `claim_category=DENTAL` and excluded items found, each line item is evaluated individually. `line_item_decisions` is populated; `net_claimable` = sum of approved items only.

**Errors it can raise:** None — member-not-found adds `MEMBER_NOT_FOUND` to reasons.

---

## 5. `check_fraud_node`

**Reads from state:** `claimed_amount`, `claims_history[]`, `treatment_date`

**Writes to state:**
```
fraud_check: {
  score:               float  [0.0–1.0],
  flags:               List[str],
  needs_manual_review: bool
}
trace: trace + new entry
```

**Scoring:**
- Same-day claim count ≥ `same_day_claims_limit` (2): `score += 0.5 + 0.1×(count − limit)`, `needs_manual_review = True` unconditionally.
- `claimed_amount > high_value_claim_threshold` (25,000): `score += 0.3`.
- `score >= fraud_score_manual_review_threshold` (0.80) or `claimed_amount > auto_manual_review_above` (25,000): `needs_manual_review = True`.

**Errors it can raise:** None.

---

## 6. `make_decision_node`

**Reads from state:** `policy_check`, `fraud_check`, `component_failures`, `claimed_amount`, `claim_category`, `hospital_name`, `line_item_decisions`

**Writes to state:**
```
decision:          "APPROVED" | "PARTIAL" | "REJECTED" | "MANUAL_REVIEW"
approved_amount:   float | None
confidence_score:  float  [0.30–1.0]
rejection_reasons: List[str] | None
decision_notes:    str
trace:             trace + new entry
```

**Decision priority:**
1. `fraud_check.needs_manual_review AND no rejection_reasons` → `MANUAL_REVIEW`
2. `rejection_reasons` non-empty → `REJECTED`, `approved_amount=None`
3. `line_item_decisions` has any `approved=False` → `PARTIAL`
4. Otherwise → `APPROVED`

**Financial calculation (APPROVED / PARTIAL):**
```
after_discount = amount × (1 − network_discount_pct/100)   # 0 if not network hospital
approved       = after_discount × (1 − copay_pct/100)
```
Network discount is applied **before** copay (TC010 verification).

**Confidence degradation:**
```
confidence = 1.0
           − 0.15 × len(component_failures)
           − 0.05 × len(fraud_check.flags)
           − 0.10  if extracted_docs is empty
```
Floor: 0.30.

**Errors it can raise:** None.

---

## Database Schema

### `claims`
| Column | Type | Notes |
|--------|------|-------|
| `claim_id` | VARCHAR(50) PK | `CLM_<8-hex>` |
| `member_id` | VARCHAR(20) | |
| `policy_id` | VARCHAR(50) | |
| `claim_category` | VARCHAR(50) | |
| `treatment_date` | DATE | |
| `claimed_amount` | NUMERIC(12,2) | |
| `hospital_name` | VARCHAR(200) | nullable |
| `status` | VARCHAR(20) | PROCESSING / COMPLETED / ERROR |
| `decision` | VARCHAR(20) | APPROVED / PARTIAL / REJECTED / MANUAL_REVIEW |
| `approved_amount` | NUMERIC(12,2) | nullable |
| `confidence_score` | NUMERIC(5,4) | nullable |
| `rejection_reasons` | JSONB | nullable |
| `decision_notes` | TEXT | nullable |
| `line_item_decisions` | JSONB | nullable |
| `component_failures` | JSONB | nullable |
| `stop_message` | TEXT | nullable — set when pipeline stops early |

### `claim_trace`
| Column | Type | Notes |
|--------|------|-------|
| `claim_id` | VARCHAR(50) FK | |
| `step_order` | INTEGER | 0-indexed execution order |
| `step_name` | VARCHAR(100) | e.g. `validate_documents` |
| `status` | VARCHAR(20) | SUCCESS / FAILED / PARTIAL / SKIPPED / ISSUES_FOUND |
| `summary` | TEXT | human-readable one-liner |
| `details` | JSONB | full structured output of the node |
| `duration_ms` | INTEGER | wall-clock time for the node |
| `error` | TEXT | nullable |

### `claim_documents`
| Column | Type | Notes |
|--------|------|-------|
| `claim_id` | VARCHAR(50) FK | |
| `file_id` | VARCHAR(50) | |
| `file_name` | VARCHAR(200) | |
| `actual_type` | VARCHAR(50) | PRESCRIPTION / HOSPITAL_BILL / etc. |
| `quality` | VARCHAR(20) | GOOD / POOR / UNREADABLE |
| `patient_name_on_doc` | VARCHAR(200) | nullable |

---

## REST API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/claims` | Submit claim as JSON (test/structured mode) |
| POST | `/api/claims/upload` | Submit claim with multipart file uploads (GPT-4o extraction) |
| GET | `/api/claims` | List all claims (summary) |
| GET | `/api/claims/{claim_id}` | Full claim with trace and documents |
