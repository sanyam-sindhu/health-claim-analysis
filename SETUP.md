# Setup & Run

## Prerequisites
- Python 3.11+
- Node.js 18+
- Docker (for PostgreSQL)
- OpenAI API key

## 1. Start PostgreSQL
```bash
docker compose up -d
```

## 2. Backend
```bash
cd backend
pip install -r requirements.txt
# Edit .env — set your OPENAI_API_KEY
uvicorn main:app --reload --port 8000
```

## 3. Frontend
```bash
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

## Run the 12 test cases (no DB needed)
```bash
cd backend
python run_tests.py
```

## Architecture

```
React UI
  → POST /api/claims
      → FastAPI
          → LangGraph pipeline (6 nodes):
              1. validate_documents   — checks doc types & readability
              2. extract_documents    — GPT-4o vision OR structured content
              3. cross_validate       — patient name consistency
              4. check_policy         — waiting periods, exclusions, limits, pre-auth
              5. check_fraud          — same-day patterns, high-value signals
              6. make_decision        — financial calc, confidence score
          → PostgreSQL (claims + trace)
```

### Document extraction
- If `content` is provided in the document JSON → used directly (test mode)
- If `image_base64` is provided → GPT-4o vision API is called
- Both paths produce the same structured data for downstream nodes

### Key design decisions
- Each node is independently testable and returns its own trace entry
- `should_stop=True` exits the graph early (TC001–TC003) with a specific user message
- `simulate_component_failure=True` causes extraction to fail gracefully (TC011)
- Per-claim limits: category sub_limit overrides global limit when sub_limit is higher (dental=10k > default=5k)
- Global exclusions match against diagnosis only; dental/vision exclusions match procedure names
