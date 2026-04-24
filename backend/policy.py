import json
import os
import re
from datetime import date, timedelta
from typing import Optional, List, Dict, Any, Tuple

_policy: Dict[str, Any] = {}


def load_policy(path: str = None) -> Dict[str, Any]:
    global _policy
    if not _policy:
        p = path or os.path.join(os.path.dirname(__file__), "policy_terms.json")
        with open(p) as f:
            _policy = json.load(f)
    return _policy


def get_member(member_id: str) -> Optional[Dict]:
    policy = load_policy()
    for m in policy["members"]:
        if m["member_id"] == member_id:
            return m
    return None


def get_required_docs(claim_category: str) -> Dict[str, List[str]]:
    policy = load_policy()
    return policy["document_requirements"].get(claim_category, {"required": [], "optional": []})


def check_waiting_period(member: Dict, treatment_date: date, diagnosis: str) -> Tuple[bool, str]:
    policy = load_policy()
    wp = policy["waiting_periods"]

    join_date = date.fromisoformat(member["join_date"])
    days_since_join = (treatment_date - join_date).days

    initial_days = wp["initial_waiting_period_days"]
    if days_since_join < initial_days:
        eligible_date = join_date + timedelta(days=initial_days)
        return True, (
            f"Initial waiting period of {initial_days} days not completed. "
            f"Eligible from {eligible_date.isoformat()}."
        )

    # Word-boundary matching prevents "hernia" matching "herniation" etc.
    diagnosis_lower = (diagnosis or "").lower()
    specific = wp.get("specific_conditions", {})
    condition_map = {
        "diabetes": specific.get("diabetes", 0),
        "hypertension": specific.get("hypertension", 0),
        "thyroid": specific.get("thyroid_disorders", 0),
        "joint replacement": specific.get("joint_replacement", 0),
        "maternity": specific.get("maternity", 0),
        "mental health": specific.get("mental_health", 0),
        "obesity": specific.get("obesity_treatment", 0),
        "hernia": specific.get("hernia", 0),
        "cataract": specific.get("cataract", 0),
    }
    for keyword, wait_days in condition_map.items():
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if wait_days > 0 and re.search(pattern, diagnosis_lower):
            if days_since_join < wait_days:
                eligible_date = join_date + timedelta(days=wait_days)
                return True, (
                    f"Waiting period of {wait_days} days applies for {keyword}. "
                    f"Member joined on {join_date.isoformat()}. "
                    f"Eligible from {eligible_date.isoformat()}."
                )
    return False, ""


def check_exclusions(
    claim_category: str, diagnosis: str, procedures: List[str]
) -> Tuple[bool, List[str], List[str]]:
    policy = load_policy()
    excl = policy["exclusions"]
    diagnosis_lower = (diagnosis or "").lower()

    # Global exclusions match diagnosis only — not procedure names — to avoid
    # false positives (e.g. "treatment" in "Substance abuse treatment" matching any claim).
    global_exclusions = [e.lower() for e in excl.get("conditions", [])]
    for exc in global_exclusions:
        exc_keywords = [w for w in exc.replace("(", "").replace(")", "").split() if len(w) > 5]
        if exc_keywords and any(kw in diagnosis_lower for kw in exc_keywords):
            return True, [], [f"Treatment falls under excluded condition: '{exc}'"]

    procedures_lower = [p.lower() for p in (procedures or [])]
    excluded_items = []
    exclusion_reasons = []

    if claim_category == "DENTAL":
        category_data = policy["opd_categories"].get("dental", {})
        excluded_procs = [p.lower() for p in category_data.get("excluded_procedures", [])]
        for proc in procedures_lower:
            for ep in excluded_procs:
                if ep in proc or proc in ep:
                    excluded_items.append(proc)
                    exclusion_reasons.append(f"{proc} is a cosmetic/excluded dental procedure")
                    break

    if claim_category == "VISION":
        vision_excl = [e.lower() for e in excl.get("vision_exclusions", [])]
        for proc in procedures_lower:
            for ep in vision_excl:
                if ep in proc:
                    excluded_items.append(proc)
                    exclusion_reasons.append(f"{proc} is excluded under vision coverage")
                    break

    return False, excluded_items, exclusion_reasons


def check_pre_auth(claim_category: str, tests: List[str], amount: float) -> Tuple[bool, str]:
    policy = load_policy()
    if claim_category != "DIAGNOSTIC":
        return False, ""

    high_value = policy["opd_categories"]["diagnostic"].get("high_value_tests_requiring_pre_auth", [])
    pre_auth_threshold = policy["opd_categories"]["diagnostic"].get("pre_auth_threshold", 10000)

    tests_upper = [t.upper() for t in (tests or [])]
    for hv in high_value:
        for t in tests_upper:
            if hv.upper() in t or t in hv.upper():
                if amount > pre_auth_threshold:
                    return True, (
                        f"{hv} requires pre-authorization when claim amount exceeds "
                        f"INR {pre_auth_threshold:,.0f}. Please obtain pre-auth and resubmit."
                    )
    return False, ""


def get_effective_claim_limit(claim_category: str) -> float:
    policy = load_policy()
    per_claim_limit = policy["coverage"]["per_claim_limit"]
    cat_key = claim_category.lower().replace("_medicine", "").replace("alternative", "alternative_medicine")
    cat_data = policy["opd_categories"].get(cat_key, {})
    sub_limit = cat_data.get("sub_limit", per_claim_limit)
    # sub_limit overrides per_claim_limit when larger (e.g. dental=10000 > global 5000)
    return max(per_claim_limit, sub_limit)


def calculate_approved_amount(
    claim_category: str, amount: float, hospital_name: Optional[str]
) -> Dict[str, Any]:
    policy = load_policy()
    cat_key = claim_category.lower().replace(" ", "_")
    cat_data = policy["opd_categories"].get(cat_key, {})

    network_hospitals = [h.lower() for h in policy.get("network_hospitals", [])]
    is_network = hospital_name and hospital_name.lower() in network_hospitals

    network_discount = cat_data.get("network_discount_percent", 0) / 100.0 if is_network else 0.0
    after_discount = amount * (1 - network_discount)
    copay = cat_data.get("copay_percent", 0) / 100.0
    after_copay = after_discount * (1 - copay)

    return {
        "original_amount": amount,
        "network_discount_pct": network_discount * 100,
        "after_discount": after_discount,
        "copay_pct": copay * 100,
        "approved_amount": round(after_copay, 2),
        "is_network_hospital": is_network,
    }


def check_submission_deadline(treatment_date: date, submission_date: date = None) -> Tuple[bool, str]:
    policy = load_policy()
    deadline_days = policy["submission_rules"]["deadline_days_from_treatment"]
    today = submission_date or date.today()
    days_since = (today - treatment_date).days
    if days_since > deadline_days:
        return True, f"Claim submitted {days_since} days after treatment. Deadline is {deadline_days} days."
    return False, ""


def is_network_hospital(hospital_name: Optional[str]) -> bool:
    if not hospital_name:
        return False
    policy = load_policy()
    networks = [h.lower() for h in policy.get("network_hospitals", [])]
    return hospital_name.lower() in networks


def check_annual_opd_limit(ytd_amount: float, new_amount: float) -> Tuple[bool, float, str]:
    policy = load_policy()
    annual_limit = policy["coverage"]["annual_opd_limit"]
    remaining = max(0.0, annual_limit - ytd_amount)
    if ytd_amount >= annual_limit:
        return True, 0.0, (
            f"Annual OPD limit of INR {annual_limit:,.0f} already exhausted "
            f"(YTD: INR {ytd_amount:,.0f})."
        )
    if ytd_amount + new_amount > annual_limit:
        return False, remaining, (
            f"Claim partially payable: only INR {remaining:,.0f} remains of the "
            f"INR {annual_limit:,.0f} annual OPD limit (YTD used: INR {ytd_amount:,.0f})."
        )
    return False, new_amount, ""
