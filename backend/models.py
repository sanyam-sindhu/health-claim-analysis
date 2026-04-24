from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import date


class DocumentInput(BaseModel):
    file_id: str
    file_name: Optional[str] = None
    actual_type: Optional[str] = None        # PRESCRIPTION, HOSPITAL_BILL, etc.
    quality: Optional[str] = "GOOD"          # GOOD, POOR, UNREADABLE
    patient_name_on_doc: Optional[str] = None
    content: Optional[Dict[str, Any]] = None  # pre-structured content (test mode)
    image_base64: Optional[str] = None        # raw image for GPT-4o vision


class ClaimSubmission(BaseModel):
    member_id: str
    policy_id: str
    claim_category: str   # CONSULTATION | DIAGNOSTIC | PHARMACY | DENTAL | VISION | ALTERNATIVE_MEDICINE
    treatment_date: date
    claimed_amount: float
    hospital_name: Optional[str] = None
    ytd_claims_amount: Optional[float] = 0.0
    claims_history: Optional[List[Dict[str, Any]]] = []
    documents: List[DocumentInput]
    simulate_component_failure: Optional[bool] = False


class TraceStep(BaseModel):
    step: str
    status: str          # SUCCESS | FAILED | SKIPPED
    summary: str
    details: Dict[str, Any] = {}
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class ClaimResult(BaseModel):
    claim_id: str
    status: str
    decision: Optional[str] = None
    approved_amount: Optional[float] = None
    confidence_score: Optional[float] = None
    rejection_reasons: Optional[List[str]] = None
    decision_notes: Optional[str] = None
    line_item_decisions: Optional[List[Dict[str, Any]]] = None
    component_failures: List[str] = []
    stop_message: Optional[str] = None
    trace: List[Dict[str, Any]] = []
