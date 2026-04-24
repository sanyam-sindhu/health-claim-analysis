# Health Insurance Claims Processing System

AI-powered claims pipeline using LangGraph, FastAPI, GPT-4o, and PostgreSQL.

## Stack

- **Backend** — FastAPI + LangGraph (6-node pipeline) + psycopg3 + PostgreSQL via PgBouncer
- **Extraction** — GPT-4o vision for real documents; structured content for tests
- **Frontend** — React + Vite
- **Observability** — Full trace per claim stored in DB; LangSmith integration

## Quick Start

```bash
# 1. Start PostgreSQL + PgBouncer
docker compose up -d

# 2. Backend
cd backend
pip install -r requirements.txt
cp .env.example .env   # add your OPENAI_API_KEY
uvicorn main:app --reload --port 8000

# 3. Frontend
cd frontend
npm install
npm run dev            # http://localhost:5173

# 4. Run all 12 test cases
cd backend
python run_tests.py
```

## Deliverables

| File | Description |
|------|-------------|
| `ARCHITECTURE.md` | System design, decisions, 10x scaling plan |
| `CONTRACTS.md` | Input/output contracts for all 6 pipeline nodes |
| `EVAL_REPORT.md` | 12/12 test cases passing with full traces |
| `SETUP.md` | Detailed setup instructions |
