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
# 1. Configure environment, then add your Gemini API key to .env
#    (get one at https://aistudio.google.com/apikey)
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

Tests mock the LLM, so no API key is needed. They do need the Postgres container running;
each test runs inside a transaction that is rolled back, so your local data is untouched.

## API

| Method | Path | What it does |
|---|---|---|
| `POST` | `/receipts` | Upload a receipt (JPEG, PNG, WebP, or PDF, max 10 MB). Extracts, validates, and saves it. |
| `GET` | `/receipts` | List receipts, newest first. |
| `GET` | `/receipts/{id}` | One receipt with its line items and any validation issues. |
| `GET` | `/receipts/{id}/file` | The original uploaded file. |

Try it: `curl -F "file=@my-receipt.jpg" localhost:8000/receipts`, or use the interactive docs
at `/docs`.

### How extraction works

1. **Check the file.** The real type is detected from the file's first bytes (not its name).
2. **Store the file** under a random key, so the original is always available for review.
3. **Extract.** The file goes to a vision LLM with a JSON schema; the model must return
   vendor, date, line items, subtotal, tax, tip, total, and payment method in that shape.
   The prompt tells it to copy numbers as printed and never "fix" the math.
4. **Validate.** Plain Python checks that line items add up to the subtotal and that
   subtotal + tax + tip equals the total (allowing tax-inclusive receipts and 2¢ of
   rounding), and that vendor, date, and total are present and the date isn't in the future.
5. **Save.** Any failed check is recorded and the receipt is flagged `needs_review`. If the
   LLM call itself fails, the receipt is saved with `status: failed` so nothing is lost.

The LLM sits behind a small `LLMClient` interface (`app/llm/`), so Gemini can be swapped
for another provider by adding one class.

## Project structure

```
receipt-agent/
├── backend/
│   ├── app/            # FastAPI application
│   │   ├── main.py            # App entry point
│   │   ├── config.py          # Settings from environment variables
│   │   ├── db.py              # SQLAlchemy engine/session/base
│   │   ├── models.py          # Database tables
│   │   ├── schemas.py         # API response shapes
│   │   ├── routers/           # HTTP routes
│   │   ├── receipt_service.py # Upload pipeline: store → extract → validate → save
│   │   ├── extraction.py      # LLM schema + prompt
│   │   ├── validation.py      # Arithmetic and sanity checks
│   │   ├── file_types.py      # Detect file type from content
│   │   ├── storage.py         # File storage (local disk; S3 later)
│   │   └── llm/               # Provider-agnostic LLM wrapper + Gemini implementation
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
- [x] 2. Upload + extraction (images, PDFs) with validation
- [ ] 3. Categorization, duplicate detection, anomaly flags
- [ ] 4. Q&A agent with read-only database tools
- [ ] 5. Email forwarding (Postmark inbound webhook)
- [ ] 6. Frontend: upload, list, flags, dashboard, chat
- [ ] 7. User accounts + demo account
- [ ] 8. Extraction evaluation script
- [ ] 9. Deployment (Docker, Terraform, CD)
- [ ] 10. Final README
