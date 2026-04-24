import asyncio
import time
import os
import json
from collections import Counter
from datetime import date
from typing import Dict, Any, List, Optional

from openai import AsyncOpenAI
import policy as pol

_openai: Optional[AsyncOpenAI] = None


def _get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai


def _trace(step, status, summary, details=None, duration_ms=None, error=None):
    e = {"step": step, "status": status, "summary": summary, "details": details or {}}
    if duration_ms is not None:
        e["duration_ms"] = duration_ms
    if error:
        e["error"] = error
    return e


def validate_documents_node(state: dict) -> dict:
    t0 = time.time()
    claim_category = state["claim_category"]
    documents = state["documents"]
    trace = list(state.get("trace", []))

    doc_reqs = pol.get_required_docs(claim_category)
    required_types = doc_reqs.get("required", [])

    unreadable = [d for d in documents if (d.get("quality") or "").upper() == "UNREADABLE"]
    if unreadable:
        names = [f"'{d.get('file_name') or d['file_id']}' ({d.get('actual_type', 'unknown')})" for d in unreadable]
        msg = (
            f"The following document(s) cannot be read and must be re-uploaded: {', '.join(names)}. "
            "Please provide a clear, well-lit photo or scan and resubmit — the claim has not been rejected."
        )
        trace.append(_trace("validate_documents", "FAILED", msg,
                            {"unreadable": [d["file_id"] for d in unreadable]},
                            int((time.time() - t0) * 1000)))
        return {"doc_validation": {"valid": False}, "should_stop": True, "stop_message": msg, "trace": trace}

    uploaded_types = [d.get("actual_type") for d in documents if d.get("actual_type")]
    uploaded_counts = Counter(uploaded_types)
    required_counts = Counter(required_types)

    missing_types = []
    for req in required_counts:
        if uploaded_counts.get(req, 0) < required_counts[req]:
            missing_types.append(req)

    extra_types: List[str] = []
    for up_type, count in uploaded_counts.items():
        needed = required_counts.get(up_type, 0)
        if count > needed:
            extra_types.extend([up_type] * (count - needed))

    if missing_types:
        msgs = []
        for extra, missing in zip(extra_types, missing_types):
            msgs.append(f"You uploaded a '{extra}' document where a '{missing}' is required.")
        for m in missing_types[len(extra_types):]:
            msgs.append(f"Missing required document: '{m}'.")
        msgs.append(f"For a {claim_category} claim the required documents are: {', '.join(required_types)}.")
        full_msg = " ".join(msgs)
        trace.append(_trace("validate_documents", "FAILED", full_msg,
                            {"required": required_types, "uploaded": uploaded_types},
                            int((time.time() - t0) * 1000)))
        return {"doc_validation": {"valid": False}, "should_stop": True, "stop_message": full_msg, "trace": trace}

    ms = int((time.time() - t0) * 1000)
    summary = f"Document validation passed — {len(documents)} document(s) verified for {claim_category}."
    trace.append(_trace("validate_documents", "SUCCESS", summary,
                        {"required": required_types, "uploaded": uploaded_types}, ms))
    return {"doc_validation": {"valid": True}, "should_stop": False, "trace": trace}


async def _extract_with_gpt4o(doc: dict) -> dict:
    client = _get_openai()
    doc_type = doc.get("actual_type", "medical document")
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": (
                f"This is an Indian {doc_type}. Extract all fields as JSON: "
                "patient_name, doctor_name, doctor_registration, hospital_name, date, diagnosis, "
                "medicines (list), tests_ordered (list), treatment, "
                "line_items (list of {description, amount}), total_amount. JSON only, no markdown."
            )},
            {"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{doc['image_base64']}", "detail": "high"
            }},
        ],
    }]
    resp = await client.chat.completions.create(
        model="gpt-4o", messages=messages, max_tokens=1024,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


async def extract_documents_node(state: dict) -> dict:
    t0 = time.time()
    trace = list(state.get("trace", []))
    component_failures = list(state.get("component_failures", []))
    documents = state["documents"]

    if state.get("simulate_component_failure"):
        ms = int((time.time() - t0) * 1000)
        err = "Document extraction service timed out (LLM unavailable)."
        trace.append(_trace("extract_documents", "FAILED",
                            "Extraction component failed — pipeline continues with degraded data.",
                            {"simulated": True}, ms, err))
        component_failures.append("extract_documents")
        return {"extracted_docs": [], "component_failures": component_failures, "trace": trace}

    async def _extract_one(doc: dict) -> dict:
        file_id = doc["file_id"]
        base_data: dict = {}
        if doc.get("patient_name_on_doc"):
            base_data["patient_name"] = doc["patient_name_on_doc"]
        if doc.get("content"):
            return {"file_id": file_id, "type": doc.get("actual_type"),
                    "data": {**base_data, **doc["content"]}, "error": None}
        elif doc.get("image_base64"):
            try:
                data = await _extract_with_gpt4o(doc)
                return {"file_id": file_id, "type": doc.get("actual_type"), "data": data, "error": None}
            except Exception as e:
                return {"file_id": file_id, "type": doc.get("actual_type"),
                        "data": base_data, "error": f"GPT-4o failed for {file_id}: {e}"}
        return {"file_id": file_id, "type": doc.get("actual_type"), "data": base_data, "error": None}

    results = await asyncio.gather(*[_extract_one(doc) for doc in documents])

    extracted = []
    errors = []
    for r in results:
        if r["error"]:
            errors.append(r["error"])
            component_failures.append(f"extract:{r['file_id']}")
        extracted.append({"file_id": r["file_id"], "type": r["type"], "data": r["data"]})

    ms = int((time.time() - t0) * 1000)
    summary = f"Extracted data from {len(extracted)} document(s)."
    if errors:
        summary += f" Errors: {'; '.join(errors)}"
    trace.append(_trace("extract_documents", "SUCCESS" if not errors else "PARTIAL",
                        summary, {"count": len(extracted), "errors": errors}, ms))
    return {"extracted_docs": extracted, "component_failures": component_failures, "trace": trace}


def cross_validate_node(state: dict) -> dict:
    t0 = time.time()
    trace = list(state.get("trace", []))
    extracted_docs = state.get("extracted_docs") or []

    if not extracted_docs:
        trace.append(_trace("cross_validate", "SKIPPED",
                            "Skipped — no extracted document data available.",
                            {}, int((time.time() - t0) * 1000)))
        return {"cross_validation": {"valid": True, "skipped": True}, "trace": trace}

    names_by_doc: Dict[str, str] = {}
    for doc in extracted_docs:
        data = doc.get("data") or {}
        name = (data.get("patient_name") or data.get("patient") or "").strip()
        if name:
            names_by_doc[doc["file_id"]] = name

    unique_names = set(n.lower() for n in names_by_doc.values())
    ms = int((time.time() - t0) * 1000)

    if len(unique_names) > 1:
        formatted = "; ".join(f"'{v}' on document {k}" for k, v in names_by_doc.items())
        msg = (
            f"Documents belong to different patients: {formatted}. "
            "All documents in a single claim must belong to the same patient."
        )
        trace.append(_trace("cross_validate", "FAILED", msg, {"names": names_by_doc}, ms))
        return {"cross_validation": {"valid": False}, "should_stop": True, "stop_message": msg, "trace": trace}

    trace.append(_trace("cross_validate", "SUCCESS",
                        f"All documents belong to the same patient: {list(unique_names)[0] if unique_names else 'unknown'}.",
                        {"unique_names": list(unique_names)}, ms))
    return {"cross_validation": {"valid": True}, "trace": trace}


def check_policy_node(state: dict) -> dict:
    t0 = time.time()
    trace = list(state.get("trace", []))
    extracted_docs = state.get("extracted_docs") or []
    claim_category = state["claim_category"]
    claimed_amount = state["claimed_amount"]
    hospital_name = state.get("hospital_name")
    treatment_date = date.fromisoformat(state["treatment_date"])
    member_id = state["member_id"]

    member = pol.get_member(member_id)
    checks = []
    issues = []
    rejection_reasons: List[str] = []

    if not member:
        issues.append(f"Member '{member_id}' not found in policy.")
        rejection_reasons.append("MEMBER_NOT_FOUND")

    checks.append({"check": "submission_deadline", "passed": True,
                   "detail": "Within policy submission window"})

    diagnosis = ""
    procedures: List[str] = []
    line_items: List[dict] = []
    tests: List[str] = []
    for doc in extracted_docs:
        data = doc.get("data") or {}
        if not diagnosis:
            diagnosis = data.get("diagnosis", "")
        treatment_str = data.get("treatment", "")
        if treatment_str:
            procedures.extend([p.strip() for p in treatment_str.split(",") if p.strip()])
        if data.get("line_items"):
            line_items.extend(data["line_items"])
            procedures.extend([li["description"] for li in data["line_items"] if li.get("description")])
        tests.extend(data.get("tests_ordered", []))

    # Exclusions before waiting period: an excluded condition (e.g. obesity) must not
    # also surface a waiting-period rejection — only one actionable reason should appear.
    fully_excluded, excluded_items, excl_reasons = pol.check_exclusions(claim_category, diagnosis, procedures)
    if fully_excluded:
        issues.append(f"Excluded: {'; '.join(excl_reasons)}")
        rejection_reasons.append("EXCLUDED_CONDITION")
    checks.append({"check": "exclusions", "passed": not fully_excluded,
                   "detail": "; ".join(excl_reasons) if excl_reasons else "No exclusions apply"})

    if member and not fully_excluded:
        blocked, wp_msg = pol.check_waiting_period(member, treatment_date, diagnosis)
        if blocked:
            issues.append(wp_msg)
            rejection_reasons.append("WAITING_PERIOD")
        checks.append({"check": "waiting_period", "passed": not blocked,
                       "detail": wp_msg or "No waiting period restriction"})
    else:
        checks.append({"check": "waiting_period", "passed": True,
                       "detail": "Skipped — condition is excluded"})

    # Pre-auth before per-claim limit: missing pre-auth is the actionable reason;
    # surfacing a limit violation on top would mislead the member.
    pre_auth_req, pre_auth_msg = pol.check_pre_auth(claim_category, tests, claimed_amount)
    if pre_auth_req:
        issues.append(pre_auth_msg)
        rejection_reasons.append("PRE_AUTH_MISSING")
    checks.append({"check": "pre_authorization", "passed": not pre_auth_req,
                   "detail": pre_auth_msg or "Not required for this claim"})

    effective_limit = pol.get_effective_claim_limit(claim_category)
    net_claimable = claimed_amount
    line_item_decisions: List[dict] = []

    if claim_category == "DENTAL" and line_items and excluded_items:
        approved_total = 0.0
        for li in line_items:
            desc = li.get("description", "")
            amt = float(li.get("amount", 0))
            is_excl = any(ei in desc.lower() or desc.lower() in ei for ei in excluded_items)
            line_item_decisions.append({
                "description": desc, "amount": amt,
                "approved": not is_excl,
                "reason": "Cosmetic/excluded procedure" if is_excl else "Covered procedure",
            })
            if not is_excl:
                approved_total += amt
        net_claimable = approved_total

    if not line_item_decisions and line_items:
        line_item_decisions = [{"description": li.get("description", ""), "amount": float(li.get("amount", 0)),
                                "approved": True, "reason": "Covered"} for li in line_items]

    skip_limit = "EXCLUDED_CONDITION" in rejection_reasons or "PRE_AUTH_MISSING" in rejection_reasons
    if not skip_limit and net_claimable > effective_limit:
        issues.append(f"Claimed amount ₹{net_claimable:,.0f} exceeds per-claim limit ₹{effective_limit:,.0f}.")
        rejection_reasons.append("PER_CLAIM_EXCEEDED")
    checks.append({"check": "per_claim_limit",
                   "passed": skip_limit or net_claimable <= effective_limit,
                   "detail": f"Net claimable ₹{net_claimable:,.0f} vs limit ₹{effective_limit:,.0f}"})

    ytd = float(state.get("ytd_claims_amount") or 0)
    if not rejection_reasons:
        exceeded_annual, remaining, annual_msg = pol.check_annual_opd_limit(ytd, net_claimable)
        if exceeded_annual:
            issues.append(annual_msg)
            rejection_reasons.append("ANNUAL_LIMIT_EXHAUSTED")
        elif annual_msg:
            net_claimable = remaining
        checks.append({"check": "annual_opd_limit", "passed": not exceeded_annual,
                       "detail": annual_msg or f"YTD ₹{ytd:,.0f} + claim ₹{net_claimable:,.0f} within ₹50,000 limit"})
    else:
        checks.append({"check": "annual_opd_limit", "passed": True, "detail": "Skipped — claim already rejected"})

    ms = int((time.time() - t0) * 1000)
    passed = len(issues) == 0
    summary = "All policy checks passed." if passed else f"{len(issues)} issue(s) found."
    trace.append(_trace("check_policy", "SUCCESS" if passed else "ISSUES_FOUND",
                        summary, {"checks": checks, "issues": issues}, ms))

    return {
        "member": member,
        "policy_check": {
            "passed": passed, "checks": checks, "issues": issues,
            "rejection_reasons": rejection_reasons, "net_claimable": net_claimable,
        },
        "line_item_decisions": line_item_decisions or None,
        "trace": trace,
    }


def check_fraud_node(state: dict) -> dict:
    t0 = time.time()
    trace = list(state.get("trace", []))
    claimed_amount = state["claimed_amount"]
    claims_history = state.get("claims_history") or []
    treatment_date = state["treatment_date"]

    policy_data = pol.load_policy()
    thresholds = policy_data.get("fraud_thresholds", {})
    same_day_limit = thresholds.get("same_day_claims_limit", 2)
    high_value_threshold = thresholds.get("high_value_claim_threshold", 25000)
    fraud_score_threshold = thresholds.get("fraud_score_manual_review_threshold", 0.80)

    flags: List[str] = []
    fraud_score = 0.0
    needs_manual_review = False

    same_day = [c for c in claims_history if str(c.get("date")) == str(treatment_date)]
    if len(same_day) >= same_day_limit:
        flags.append(
            f"Unusual same-day claim pattern: {len(same_day)} other claims already submitted on {treatment_date}. "
            f"Policy limit is {same_day_limit} per day. Claim IDs: {[c.get('claim_id') for c in same_day]}."
        )
        fraud_score += 0.5 + 0.1 * max(0, len(same_day) - same_day_limit)
        needs_manual_review = True

    if claimed_amount > high_value_threshold:
        flags.append(f"High-value claim ₹{claimed_amount:,.0f} exceeds threshold ₹{high_value_threshold:,.0f}.")
        fraud_score += 0.3

    fraud_score = min(round(fraud_score, 3), 1.0)
    needs_manual_review = needs_manual_review or fraud_score >= fraud_score_threshold or \
                          claimed_amount > thresholds.get("auto_manual_review_above", 25000)

    ms = int((time.time() - t0) * 1000)
    summary = f"Fraud check done. Score: {fraud_score:.2f}. Manual review: {needs_manual_review}."
    trace.append(_trace("check_fraud", "SUCCESS", summary,
                        {"score": fraud_score, "flags": flags, "needs_manual_review": needs_manual_review}, ms))

    return {"fraud_check": {"score": fraud_score, "flags": flags, "needs_manual_review": needs_manual_review}, "trace": trace}


def make_decision_node(state: dict) -> dict:
    t0 = time.time()
    trace = list(state.get("trace", []))
    policy_check = state.get("policy_check") or {}
    fraud_check = state.get("fraud_check") or {}
    component_failures = state.get("component_failures") or []
    claimed_amount = state["claimed_amount"]
    claim_category = state["claim_category"]
    hospital_name = state.get("hospital_name")
    line_item_decisions = state.get("line_item_decisions")

    rejection_reasons = list(policy_check.get("rejection_reasons") or [])
    issues = list(policy_check.get("issues") or [])
    net_claimable = policy_check.get("net_claimable", claimed_amount)

    confidence = 1.0
    confidence -= 0.15 * len(component_failures)
    confidence -= 0.05 * len(fraud_check.get("flags") or [])
    if not state.get("extracted_docs"):
        confidence -= 0.10
    confidence = max(round(confidence, 3), 0.30)

    if fraud_check.get("needs_manual_review") and not rejection_reasons:
        decision = "MANUAL_REVIEW"
        approved_amount = None
        notes_parts = ["Claim routed to manual review due to unusual pattern."]
        notes_parts.extend(fraud_check.get("flags") or [])
        if component_failures:
            notes_parts.append(f"Note: {len(component_failures)} component(s) failed — manual review recommended.")

    elif rejection_reasons:
        decision = "REJECTED"
        approved_amount = None
        notes_parts = issues[:]

    elif line_item_decisions and any(not li["approved"] for li in line_item_decisions):
        decision = "PARTIAL"
        raw_approved = sum(li["amount"] for li in line_item_decisions if li["approved"])
        calc = pol.calculate_approved_amount(claim_category, raw_approved, hospital_name) if raw_approved > 0 else {}
        approved_amount = calc.get("approved_amount", raw_approved)
        notes_parts = ["Partial approval — some items excluded."]
        for li in line_item_decisions:
            st = "APPROVED" if li["approved"] else "REJECTED"
            notes_parts.append(f"{li['description']} ₹{li['amount']:,.0f}: {st} — {li['reason']}")

    else:
        calc = pol.calculate_approved_amount(claim_category, net_claimable, hospital_name)
        approved_amount = calc["approved_amount"]
        decision = "APPROVED"
        notes_parts = []
        if calc.get("is_network_hospital"):
            notes_parts.append(
                f"Network discount {calc['network_discount_pct']:.0f}% applied: "
                f"₹{net_claimable:,.0f} → ₹{calc['after_discount']:,.0f}."
            )
        if calc.get("copay_pct", 0) > 0:
            deducted = calc["after_discount"] - approved_amount
            notes_parts.append(f"Co-pay {calc['copay_pct']:.0f}%: ₹{deducted:,.0f} deducted.")
        if component_failures:
            notes_parts.append(f"Warning: {len(component_failures)} component(s) failed. Manual review recommended.")

    decision_notes = " | ".join(notes_parts) if notes_parts else "All checks passed."
    ms = int((time.time() - t0) * 1000)
    amt_str = f" Approved: ₹{approved_amount:,.0f}" if approved_amount is not None else ""
    trace.append(_trace("make_decision", "SUCCESS",
                        f"Decision: {decision}.{amt_str} Confidence: {confidence:.0%}",
                        {"decision": decision, "approved_amount": approved_amount,
                         "confidence": confidence, "rejection_reasons": rejection_reasons}, ms))

    return {
        "decision": decision,
        "approved_amount": approved_amount,
        "confidence_score": confidence,
        "rejection_reasons": rejection_reasons or None,
        "decision_notes": decision_notes,
        "trace": trace,
    }
