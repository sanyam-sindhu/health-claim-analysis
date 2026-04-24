import uuid
import os
import base64
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from typing import List, Optional

load_dotenv()

if os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGSMITH_TRACING"] = os.getenv("LANGSMITH_TRACING", "true")
    os.environ["LANGSMITH_ENDPOINT"] = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    os.environ["LANGSMITH_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "health_claims")

from db import Database
from models import ClaimSubmission
from graph import run_claim_pipeline

db = Database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    await db.create_tables()
    yield
    await db.disconnect()


app = FastAPI(title="Claims Processor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/claims")
async def submit_claim(submission: ClaimSubmission):
    claim_id = f"CLM_{uuid.uuid4().hex[:8].upper()}"
    await db.create_claim(claim_id, submission)

    initial_state = {
        "claim_id": claim_id,
        "member_id": submission.member_id,
        "policy_id": submission.policy_id,
        "claim_category": submission.claim_category,
        "treatment_date": submission.treatment_date.isoformat(),
        "claimed_amount": submission.claimed_amount,
        "hospital_name": submission.hospital_name,
        "ytd_claims_amount": submission.ytd_claims_amount or 0.0,
        "claims_history": [dict(c) for c in (submission.claims_history or [])],
        "documents": [d.model_dump() for d in submission.documents],
        "simulate_component_failure": submission.simulate_component_failure or False,
        "member": None,
        "doc_validation": None,
        "extracted_docs": None,
        "cross_validation": None,
        "policy_check": None,
        "fraud_check": None,
        "decision": None,
        "approved_amount": None,
        "confidence_score": None,
        "rejection_reasons": None,
        "decision_notes": None,
        "line_item_decisions": None,
        "should_stop": False,
        "stop_message": None,
        "component_failures": [],
        "trace": [],
    }

    try:
        result = await run_claim_pipeline(initial_state)
        await db.save_result(claim_id, dict(result))
        return {
            "claim_id": claim_id,
            "decision": result.get("decision"),
            "approved_amount": result.get("approved_amount"),
            "confidence_score": result.get("confidence_score"),
            "rejection_reasons": result.get("rejection_reasons"),
            "decision_notes": result.get("decision_notes"),
            "line_item_decisions": result.get("line_item_decisions"),
            "component_failures": result.get("component_failures", []),
            "stop_message": result.get("stop_message"),
            "trace": result.get("trace", []),
        }
    except Exception as e:
        await db.save_error(claim_id, str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/claims/upload")
async def submit_claim_with_files(
    member_id: str = Form(...),
    policy_id: str = Form(...),
    claim_category: str = Form(...),
    treatment_date: str = Form(...),
    claimed_amount: float = Form(...),
    hospital_name: Optional[str] = Form(None),
    ytd_claims_amount: float = Form(0.0),
    files: List[UploadFile] = File(...),
):
    from models import ClaimSubmission, DocumentInput
    documents = []
    for f in files:
        raw = await f.read()
        b64 = base64.b64encode(raw).decode()
        documents.append({
            "file_id": uuid.uuid4().hex[:8].upper(),
            "file_name": f.filename,
            "actual_type": None,
            "quality": "GOOD",
            "patient_name_on_doc": None,
            "content": None,
            "image_base64": b64,
        })

    submission = ClaimSubmission(
        member_id=member_id,
        policy_id=policy_id,
        claim_category=claim_category,
        treatment_date=treatment_date,
        claimed_amount=claimed_amount,
        hospital_name=hospital_name,
        ytd_claims_amount=ytd_claims_amount,
        documents=[DocumentInput(**d) for d in documents],
    )
    return await submit_claim(submission)


@app.get("/api/claims")
async def list_claims():
    rows = await db.list_claims()
    for r in rows:
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat()
    return rows


@app.get("/api/claims/{claim_id}")
async def get_claim(claim_id: str):
    claim = await db.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    trace = await db.get_trace(claim_id)
    documents = await db.get_documents(claim_id)
    for r in [claim] + trace + documents:
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat()
    return {**claim, "trace": trace, "documents": documents}
