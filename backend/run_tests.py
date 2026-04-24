"""Quick smoke test for all 12 test cases."""
import asyncio
from graph import run_claim_pipeline

BASE = {
    "member": None, "doc_validation": None, "extracted_docs": None,
    "cross_validation": None, "policy_check": None, "fraud_check": None,
    "decision": None, "approved_amount": None, "confidence_score": None,
    "rejection_reasons": None, "decision_notes": None, "line_item_decisions": None,
    "should_stop": False, "stop_message": None, "component_failures": [], "trace": [],
    "hospital_name": None, "ytd_claims_amount": 0, "claims_history": [],
    "simulate_component_failure": False, "policy_id": "PLUM_GHI_2024",
}


def doc(fid, atype, content=None, patient=None, quality="GOOD"):
    return {"file_id": fid, "file_name": fid + ".jpg", "actual_type": atype,
            "quality": quality, "patient_name_on_doc": patient,
            "content": content, "image_base64": None}


CASES = [
    ("TC001", {**BASE, "claim_id": "TC001", "member_id": "EMP001",
               "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
               "claimed_amount": 1500,
               "documents": [doc("F001", "PRESCRIPTION"), doc("F002", "PRESCRIPTION")]}),

    ("TC002", {**BASE, "claim_id": "TC002", "member_id": "EMP004",
               "claim_category": "PHARMACY", "treatment_date": "2024-10-25",
               "claimed_amount": 800,
               "documents": [doc("F003", "PRESCRIPTION", {"doctor": "Dr X"}),
                              doc("F004", "PHARMACY_BILL", None, None, "UNREADABLE")]}),

    ("TC003", {**BASE, "claim_id": "TC003", "member_id": "EMP001",
               "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
               "claimed_amount": 1500,
               "documents": [doc("F005", "PRESCRIPTION", None, "Rajesh Kumar"),
                              doc("F006", "HOSPITAL_BILL", None, "Arjun Mehta")]}),

    ("TC004", {**BASE, "claim_id": "TC004", "member_id": "EMP001",
               "claim_category": "CONSULTATION", "treatment_date": "2024-11-01",
               "claimed_amount": 1500,
               "documents": [
                   doc("F007", "PRESCRIPTION", {"patient_name": "Rajesh Kumar", "diagnosis": "Viral Fever"}),
                   doc("F008", "HOSPITAL_BILL", {"patient_name": "Rajesh Kumar", "total": 1500})]}),

    ("TC005", {**BASE, "claim_id": "TC005", "member_id": "EMP005",
               "claim_category": "CONSULTATION", "treatment_date": "2024-10-15",
               "claimed_amount": 3000,
               "documents": [
                   doc("F009", "PRESCRIPTION", {"patient_name": "Vikram Joshi",
                                                 "diagnosis": "Type 2 Diabetes Mellitus"}),
                   doc("F010", "HOSPITAL_BILL", {"patient_name": "Vikram Joshi", "total": 3000})]}),

    ("TC006", {**BASE, "claim_id": "TC006", "member_id": "EMP002",
               "claim_category": "DENTAL", "treatment_date": "2024-10-15",
               "claimed_amount": 12000,
               "documents": [
                   doc("F011", "HOSPITAL_BILL", {
                       "patient_name": "Priya Singh",
                       "line_items": [{"description": "Root Canal Treatment", "amount": 8000},
                                      {"description": "Teeth Whitening", "amount": 4000}],
                       "total": 12000})]}),

    ("TC007", {**BASE, "claim_id": "TC007", "member_id": "EMP007",
               "claim_category": "DIAGNOSTIC", "treatment_date": "2024-11-02",
               "claimed_amount": 15000,
               "documents": [
                   doc("F012", "PRESCRIPTION", {"diagnosis": "Lumbar Disc Herniation",
                                                 "tests_ordered": ["MRI Lumbar Spine"]}),
                   doc("F013", "LAB_REPORT", {"test_name": "MRI Lumbar Spine"}),
                   doc("F014", "HOSPITAL_BILL", {"total": 15000})]}),

    ("TC008", {**BASE, "claim_id": "TC008", "member_id": "EMP003",
               "claim_category": "CONSULTATION", "treatment_date": "2024-10-20",
               "claimed_amount": 7500,
               "documents": [
                   doc("F015", "PRESCRIPTION", {"diagnosis": "Gastroenteritis"}),
                   doc("F016", "HOSPITAL_BILL", {"total": 7500})]}),

    ("TC009", {**BASE, "claim_id": "TC009", "member_id": "EMP008",
               "claim_category": "CONSULTATION", "treatment_date": "2024-10-30",
               "claimed_amount": 4800,
               "claims_history": [
                   {"claim_id": "CLM_0081", "date": "2024-10-30", "amount": 1200},
                   {"claim_id": "CLM_0082", "date": "2024-10-30", "amount": 1800},
                   {"claim_id": "CLM_0083", "date": "2024-10-30", "amount": 2100},
               ],
               "documents": [
                   doc("F017", "PRESCRIPTION", {"diagnosis": "Migraine"}),
                   doc("F018", "HOSPITAL_BILL", {"total": 4800})]}),

    ("TC010", {**BASE, "claim_id": "TC010", "member_id": "EMP010",
               "claim_category": "CONSULTATION", "treatment_date": "2024-11-03",
               "claimed_amount": 4500, "hospital_name": "Apollo Hospitals",
               "documents": [
                   doc("F019", "PRESCRIPTION", {"patient_name": "Deepak Shah",
                                                 "diagnosis": "Acute Bronchitis"}),
                   doc("F020", "HOSPITAL_BILL", {"hospital_name": "Apollo Hospitals",
                                                  "patient_name": "Deepak Shah", "total": 4500})]}),

    ("TC011", {**BASE, "claim_id": "TC011", "member_id": "EMP006",
               "claim_category": "ALTERNATIVE_MEDICINE", "treatment_date": "2024-10-28",
               "claimed_amount": 4000, "simulate_component_failure": True,
               "documents": [
                   doc("F021", "PRESCRIPTION", {"diagnosis": "Chronic Joint Pain",
                                                 "treatment": "Panchakarma Therapy"}),
                   doc("F022", "HOSPITAL_BILL", {"total": 4000,
                                                  "line_items": [
                                                      {"description": "Panchakarma Therapy", "amount": 3000},
                                                      {"description": "Consultation", "amount": 1000}]})]}),

    ("TC012", {**BASE, "claim_id": "TC012", "member_id": "EMP009",
               "claim_category": "CONSULTATION", "treatment_date": "2024-10-18",
               "claimed_amount": 8000,
               "documents": [
                   doc("F023", "PRESCRIPTION", {"diagnosis": "Morbid Obesity - BMI 37",
                                                 "treatment": "Bariatric Consultation and Customised Diet Plan"}),
                   doc("F024", "HOSPITAL_BILL", {
                       "line_items": [{"description": "Bariatric Consultation", "amount": 3000},
                                      {"description": "Personalised Diet and Nutrition Program", "amount": 5000}],
                       "total": 8000})]}),
]

EXPECTED = {
    "TC001": ("STOP", None),   "TC002": ("STOP", None),    "TC003": ("STOP", None),
    "TC004": ("APPROVED", 1350), "TC005": ("REJECTED", None), "TC006": ("PARTIAL", 8000),
    "TC007": ("REJECTED", None), "TC008": ("REJECTED", None), "TC009": ("MANUAL_REVIEW", None),
    "TC010": ("APPROVED", 3240), "TC011": ("APPROVED", None), "TC012": ("REJECTED", None),
}


async def main():
    passed = 0
    for tc_id, state in CASES:
        r = await run_claim_pipeline(state)
        exp_dec, exp_amt = EXPECTED[tc_id]
        actual_dec = "STOP" if r.get("should_stop") else r.get("decision")
        amt = r.get("approved_amount")
        amt_ok = exp_amt is None or (amt is not None and abs(float(amt) - exp_amt) < 1)
        ok = actual_dec == exp_dec and amt_ok
        if ok:
            passed += 1
        mark = "PASS" if ok else "FAIL"
        amt_str = f"  approved=INR{amt:,.0f}" if amt is not None else ""
        conf_str = f"  conf={r.get('confidence_score')}" if r.get("confidence_score") else ""
        stop_str = f"  stop={r.get('stop_message', '')[:60]}" if r.get("should_stop") else ""
        reasons = r.get("rejection_reasons") or []
        print(f"[{mark}] {tc_id}: {actual_dec}{amt_str}{conf_str}{stop_str}  reasons={reasons}")

    print(f"\n{passed}/12 test cases passed")


if __name__ == "__main__":
    asyncio.run(main())
