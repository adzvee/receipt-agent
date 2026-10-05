# Receipt Agent

An AI agent that turns receipts into bookkeeping. Upload a photo, PDF, or screenshot of a
receipt (or forward a receipt email) and the app extracts the details, categorizes the
expense, flags duplicates and unusual charges, and answers questions like
*"How much did I spend on food in September?"*

> 🚧 Work in progress — built in stages. See [Roadmap](#roadmap).

## Problem

_TODO (stage 10)._

## Architecture

_TODO (stage 10): diagram._

## Tech stack

- **Backend:** Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic
- **AI:** Gemini API (behind a provider-agnostic wrapper)
- **Frontend:** React + TypeScript (Vite)
- **Infra:** Docker, docker-compose, GitHub Actions, Terraform (AWS), S3, Postmark

## Running locally

Requirements: Python 3.11+, Docker.

```bash
# 1. Configure environment
cp .env.example .env

# 2. Start Postgres (exposed on localhost:5433)
docker compose up -d db

# 3. Install the backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 4. Apply database migrations
alembic upgrade head

# 5. Run the API (docs at http://localhost:8000/docs)
uvicorn app.main:app --reload
```

### Tests

```bash
cd backend
pytest
```

Tests mock the LLM, so no API key is needed. They do need the Postgres container running.

## Project structure

```
receipt-agent/
├── backend/
│   ├── app/            # FastAPI application
│   │   ├── main.py     # App + routes
│   │   ├── config.py   # Settings from environment variables
│   │   └── db.py       # SQLAlchemy engine/session/base
│   ├── alembic/        # Database migrations
│   └── tests/          # pytest suite
├── .github/workflows/  # CI
├── docker-compose.yml  # Local Postgres
└── .env.example        # Template for local secrets/config
```

## Evaluation

_TODO (stage 8)._

## Demo

_TODO: link._

## Roadmap

- [x] 1. Project setup
- [ ] 2. Upload + extraction (images, PDFs) with validation
- [ ] 3. Categorization, duplicate detection, anomaly flags
- [ ] 4. Q&A agent with read-only database tools
- [ ] 5. Email forwarding (Postmark inbound webhook)
- [ ] 6. Frontend: upload, list, flags, dashboard, chat
- [ ] 7. User accounts + demo account
- [ ] 8. Extraction evaluation script
- [ ] 9. Deployment (Docker, Terraform, CD)
- [ ] 10. Final README
