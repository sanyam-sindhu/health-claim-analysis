import json
import os
from typing import Optional, List, Dict, Any

import psycopg
from psycopg_pool import AsyncConnectionPool


class Database:
    def __init__(self):
        self.pool: Optional[AsyncConnectionPool] = None

    async def connect(self):
        self.pool = AsyncConnectionPool(
            conninfo=os.getenv("DATABASE_URL"),
            min_size=2, max_size=10, open=False,
        )
        await self.pool.open()

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def create_tables(self):
        async with self.pool.connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS claims (
                    claim_id        VARCHAR(50) PRIMARY KEY,
                    member_id       VARCHAR(20) NOT NULL,
                    policy_id       VARCHAR(50) NOT NULL,
                    claim_category  VARCHAR(50) NOT NULL,
                    treatment_date  DATE NOT NULL,
                    claimed_amount  NUMERIC(12,2) NOT NULL,
                    hospital_name   VARCHAR(200),
                    status          VARCHAR(20) NOT NULL DEFAULT 'PROCESSING',
                    decision        VARCHAR(20),
                    approved_amount NUMERIC(12,2),
                    confidence_score NUMERIC(5,4),
                    rejection_reasons JSONB,
                    decision_notes  TEXT,
                    line_item_decisions JSONB,
                    component_failures  JSONB,
                    stop_message    TEXT,
                    created_at      TIMESTAMP DEFAULT NOW(),
                    updated_at      TIMESTAMP DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS claim_documents (
                    id              SERIAL PRIMARY KEY,
                    claim_id        VARCHAR(50) REFERENCES claims(claim_id),
                    file_id         VARCHAR(50),
                    file_name       VARCHAR(200),
                    actual_type     VARCHAR(50),
                    quality         VARCHAR(20),
                    patient_name_on_doc VARCHAR(200),
                    created_at      TIMESTAMP DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS claim_trace (
                    id              SERIAL PRIMARY KEY,
                    claim_id        VARCHAR(50) REFERENCES claims(claim_id),
                    step_order      INTEGER NOT NULL,
                    step_name       VARCHAR(100) NOT NULL,
                    status          VARCHAR(20) NOT NULL,
                    summary         TEXT,
                    details         JSONB,
                    duration_ms     INTEGER,
                    error           TEXT,
                    created_at      TIMESTAMP DEFAULT NOW()
                )
            """)

    async def create_claim(self, claim_id: str, submission) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO claims (claim_id, member_id, policy_id, claim_category,
                    treatment_date, claimed_amount, hospital_name, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'PROCESSING')
                """,
                (claim_id, submission.member_id, submission.policy_id,
                 submission.claim_category, submission.treatment_date,
                 submission.claimed_amount, submission.hospital_name),
            )
            for doc in submission.documents:
                await conn.execute(
                    """
                    INSERT INTO claim_documents
                        (claim_id, file_id, file_name, actual_type, quality, patient_name_on_doc)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    """,
                    (claim_id, doc.file_id, doc.file_name, doc.actual_type,
                     doc.quality, doc.patient_name_on_doc),
                )

    async def save_result(self, claim_id: str, result: dict) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                UPDATE claims SET
                    status = %s, decision = %s, approved_amount = %s, confidence_score = %s,
                    rejection_reasons = %s, decision_notes = %s, line_item_decisions = %s,
                    component_failures = %s, stop_message = %s, updated_at = NOW()
                WHERE claim_id = %s
                """,
                (
                    "COMPLETED",
                    result.get("decision"),
                    result.get("approved_amount"),
                    result.get("confidence_score"),
                    json.dumps(result.get("rejection_reasons")) if result.get("rejection_reasons") else None,
                    result.get("decision_notes"),
                    json.dumps(result.get("line_item_decisions")) if result.get("line_item_decisions") else None,
                    json.dumps(result.get("component_failures", [])),
                    result.get("stop_message"),
                    claim_id,
                ),
            )
            trace = result.get("trace") or []
            for i, step in enumerate(trace):
                await conn.execute(
                    """
                    INSERT INTO claim_trace
                        (claim_id, step_order, step_name, status, summary, details, duration_ms, error)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        claim_id, i, step.get("step"), step.get("status"),
                        step.get("summary"),
                        json.dumps(step.get("details") or {}),
                        step.get("duration_ms"),
                        step.get("error"),
                    ),
                )

    async def save_error(self, claim_id: str, error: str) -> None:
        async with self.pool.connection() as conn:
            await conn.execute(
                "UPDATE claims SET status='ERROR', decision_notes=%s, updated_at=NOW() WHERE claim_id=%s",
                (error, claim_id),
            )

    async def list_claims(self) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                await cur.execute(
                    """
                    SELECT claim_id, member_id, claim_category, treatment_date,
                           claimed_amount, status, decision, approved_amount,
                           confidence_score, created_at
                    FROM claims ORDER BY created_at DESC
                    """
                )
                return await cur.fetchall()

    async def get_claim(self, claim_id: str) -> Optional[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                await cur.execute("SELECT * FROM claims WHERE claim_id=%s", (claim_id,))
                row = await cur.fetchone()
                if not row:
                    return None
                data = dict(row)
                for field in ("rejection_reasons", "line_item_decisions", "component_failures"):
                    if isinstance(data.get(field), str):
                        data[field] = json.loads(data[field])
                return data

    async def get_trace(self, claim_id: str) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM claim_trace WHERE claim_id=%s ORDER BY step_order",
                    (claim_id,),
                )
                rows = await cur.fetchall()
                result = []
                for r in rows:
                    d = dict(r)
                    if isinstance(d.get("details"), str):
                        d["details"] = json.loads(d["details"])
                    result.append(d)
                return result

    async def get_documents(self, claim_id: str) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM claim_documents WHERE claim_id=%s",
                    (claim_id,),
                )
                return await cur.fetchall()
