"""Unit tests for policy.py — run with: python -m pytest test_policy.py -v"""
import pytest
from datetime import date
import policy


# ── Member lookup ─────────────────────────────────────────────────────────────

def test_get_member_exists():
    m = policy.get_member("EMP001")
    assert m is not None
    assert m["name"] == "Rajesh Kumar"


def test_get_member_not_found():
    assert policy.get_member("INVALID") is None


def test_get_member_dependent():
    m = policy.get_member("DEP001")
    assert m is not None
    assert m["relationship"] == "SPOUSE"


# ── Waiting periods ───────────────────────────────────────────────────────────

def test_initial_waiting_period_blocks():
    member = {"join_date": "2024-04-01"}
    blocked, msg = policy.check_waiting_period(member, date(2024, 4, 15), "Fever")
    assert blocked is True
    assert "30" in msg
    assert "2024-05-01" in msg


def test_initial_waiting_period_passes_after_30_days():
    member = {"join_date": "2024-04-01"}
    blocked, _ = policy.check_waiting_period(member, date(2024, 11, 1), "Fever")
    assert blocked is False


def test_diabetes_waiting_period():
    member = {"join_date": "2024-09-01"}
    blocked, msg = policy.check_waiting_period(member, date(2024, 10, 15), "Type 2 Diabetes Mellitus")
    assert blocked is True
    assert "90" in msg
    assert "2024-11-30" in msg


def test_herniation_does_not_trigger_hernia_waiting_period():
    """'hernia' must not match 'herniation' — word-boundary guard."""
    member = {"join_date": "2024-04-01"}
    blocked, _ = policy.check_waiting_period(member, date(2024, 11, 2), "Suspected Lumbar Disc Herniation")
    assert blocked is False


def test_obesity_waiting_period():
    member = {"join_date": "2024-04-01"}
    blocked, msg = policy.check_waiting_period(member, date(2024, 10, 18), "Morbid Obesity - BMI 37")
    assert blocked is True
    assert "obesity" in msg.lower()


# ── Exclusions ────────────────────────────────────────────────────────────────

def test_global_exclusion_obesity():
    fully, _, reasons = policy.check_exclusions("CONSULTATION", "Morbid Obesity - BMI 37", [])
    assert fully is True
    assert any("obesity" in r.lower() for r in reasons)


def test_global_exclusion_bariatric():
    fully, _, _ = policy.check_exclusions("CONSULTATION", "Bariatric Surgery consultation", [])
    assert fully is True


def test_dental_whitening_excluded():
    fully, items, _ = policy.check_exclusions("DENTAL", "", ["Root Canal Treatment", "Teeth Whitening"])
    assert fully is False
    assert any("teeth whitening" in i for i in items)


def test_dental_root_canal_covered():
    fully, items, _ = policy.check_exclusions("DENTAL", "", ["Root Canal Treatment"])
    assert fully is False
    assert len(items) == 0


def test_no_exclusion_viral_fever():
    fully, items, _ = policy.check_exclusions("CONSULTATION", "Viral Fever", [])
    assert fully is False
    assert len(items) == 0


# ── Claim limits ──────────────────────────────────────────────────────────────

def test_consultation_per_claim_limit():
    assert policy.get_effective_claim_limit("CONSULTATION") == 5000.0


def test_dental_uses_sub_limit():
    assert policy.get_effective_claim_limit("DENTAL") == 10000.0


def test_diagnostic_uses_sub_limit():
    assert policy.get_effective_claim_limit("DIAGNOSTIC") == 10000.0


# ── Financial calculation ─────────────────────────────────────────────────────

def test_consultation_copay_10_pct():
    result = policy.calculate_approved_amount("CONSULTATION", 1500, None)
    assert result["approved_amount"] == 1350.0
    assert result["copay_pct"] == 10.0
    assert not result["is_network_hospital"]


def test_network_discount_before_copay():
    """TC010: Apollo network → 20% discount then 10% copay → 3240."""
    result = policy.calculate_approved_amount("CONSULTATION", 4500, "Apollo Hospitals")
    assert result["is_network_hospital"] is True
    assert result["after_discount"] == pytest.approx(3600.0)
    assert result["approved_amount"] == pytest.approx(3240.0)


def test_dental_no_copay():
    result = policy.calculate_approved_amount("DENTAL", 8000, None)
    assert result["approved_amount"] == 8000.0
    assert result["copay_pct"] == 0.0


def test_non_network_hospital_no_discount():
    result = policy.calculate_approved_amount("CONSULTATION", 1000, "Random Clinic")
    assert result["network_discount_pct"] == 0.0
    assert result["approved_amount"] == pytest.approx(900.0)


# ── Pre-authorization ─────────────────────────────────────────────────────────

def test_mri_above_threshold_requires_pre_auth():
    required, msg = policy.check_pre_auth("DIAGNOSTIC", ["MRI Lumbar Spine"], 15000)
    assert required is True
    assert "pre-authorization" in msg.lower()
    assert "resubmit" in msg.lower()


def test_mri_below_threshold_no_pre_auth():
    required, _ = policy.check_pre_auth("DIAGNOSTIC", ["MRI Lumbar Spine"], 8000)
    assert required is False


def test_ct_above_threshold_requires_pre_auth():
    required, _ = policy.check_pre_auth("DIAGNOSTIC", ["CT Scan Brain"], 12000)
    assert required is True


def test_non_diagnostic_no_pre_auth():
    required, _ = policy.check_pre_auth("CONSULTATION", ["MRI"], 20000)
    assert required is False


# ── Annual OPD limit ──────────────────────────────────────────────────────────

def test_annual_limit_not_exceeded():
    exceeded, remaining, msg = policy.check_annual_opd_limit(5000, 1350)
    assert exceeded is False
    assert remaining == 1350
    assert msg == ""


def test_annual_limit_partial():
    exceeded, remaining, msg = policy.check_annual_opd_limit(49000, 2000)
    assert exceeded is False
    assert remaining == 1000
    assert "partially payable" in msg.lower()


def test_annual_limit_exhausted():
    exceeded, remaining, msg = policy.check_annual_opd_limit(50000, 500)
    assert exceeded is True
    assert remaining == 0
    assert "exhausted" in msg.lower()


# ── Required documents ────────────────────────────────────────────────────────

def test_consultation_requires_prescription_and_bill():
    reqs = policy.get_required_docs("CONSULTATION")
    assert "PRESCRIPTION" in reqs["required"]
    assert "HOSPITAL_BILL" in reqs["required"]


def test_pharmacy_requires_prescription_and_pharmacy_bill():
    reqs = policy.get_required_docs("PHARMACY")
    assert "PRESCRIPTION" in reqs["required"]
    assert "PHARMACY_BILL" in reqs["required"]


def test_diagnostic_requires_three_docs():
    reqs = policy.get_required_docs("DIAGNOSTIC")
    assert set(reqs["required"]) == {"PRESCRIPTION", "LAB_REPORT", "HOSPITAL_BILL"}
