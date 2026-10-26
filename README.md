# Receipt Agent

An AI agent that turns receipts into bookkeeping. Upload a photo, PDF, or screenshot of a
receipt (or forward a receipt email) and the app extracts the details, categorizes the
expense, flags duplicates and unusual charges, and answers questions like
*"How much did I spend on food in September?"*

## Problem

Receipts arrive as paper slips, PDFs, screenshots, and emails, each with its own layout,
and turning them into usable bookkeeping means typing the vendor, date, items, and totals
by hand: slow, and easy to get wrong. Plain OCR doesn't solve it: it returns text, not a
total, and can't tell a subtotal from a tip or notice a receipt entered twice. Receipt
Agent uses a vision LLM to turn any receipt into structured data, then checks it with
ordinary code (do the numbers add up? is this a duplicate? an unusual charge?) rather than
trusting the model, and lets you ask about your spending in plain English, through
read-only tools so the model never writes to (or queries) the database directly.

## Key features

- **Any receipt in:** upload photos, screenshots, or PDFs (or take a photo on a phone), or
  forward receipt emails to a personal address.
- **Extraction you can check:** a vision LLM reads vendor, date, line items, subtotal,
  tax, tip, total, and payment method; plain code checks the arithmetic and flags what
  doesn't add up. The original file is always kept.
- **Analysis:** automatic categories (reusing the category of earlier receipts from the
  same vendor), duplicate detection, and flags for unusual charges and tips.
- **Ask in plain English:** "How much did I spend on food last month?" is answered from
  your data through read-only tools; the LLM never writes SQL.
- **Dashboard:** spending by category and over time, receipts that need review, and chat.
- **Accounts and privacy:** per-user data isolation, a "Try the demo" account, account
  deletion, full card numbers masked before saving, and daily usage limits.

## Results on real receipts

Extraction measured on all 472 receipts in the
[WildReceipt](https://arxiv.org/abs/2103.14470) test split, with gemini-3.8-flash
(October 2026). Each field is scored only where the dataset labels it.

| Field | Accuracy | Correct / labeled |
| --- | ---: | ---: |
| Store name (exact, ignoring case/spaces/punctuation) | 66% | 312 / 472 |
| Store name (exact or close) | 96% | 455 / 472 |
| Date | 97% | 341 / 351 |
| Total | 97% | 410 / 422 |
| Subtotal | 94% | 322 / 342 |
| Tax | 90% | 286 / 318 |
| Tip | 76% | 16 / 21 |

The most common mistake is leaving tax empty (25 receipts), often where the receipt lists
several tax lines. No request failed, and the run cost about $2.46 at list price.
Method, error types, and the fake-receipt test set: [docs/evaluation.md](docs/evaluation.md).

## How it works

**Extraction and checks.** An uploaded or forwarded receipt is stored, then sent to a
vision LLM with a JSON schema and a prompt telling it to copy numbers as printed. Plain
Python then checks that the line items add up to the subtotal and that subtotal + tax +
tip equals the total, and that the vendor, date, and total are present. Every problem
becomes a flag to review instead of being silently fixed. Categorization, duplicate
checks, and unusual-charge rules run next.
Details: [docs/receipt-pipeline.md](docs/receipt-pipeline.md).

**The Q&A agent.** A question goes to the LLM along with four read-only tools (spending
summary, list receipts, get one receipt, search line items). The model picks tools and
fills in typed arguments; our code validates and runs them as fixed, parameterized
queries, inside a read-only database transaction, and sends results back, for up to 6
steps. The LLM never writes SQL. Details: [docs/qa-agent.md](docs/qa-agent.md).

**The evaluation.** `backend/evaluation/` runs the real extraction function on labeled
receipts and scores each field: 20 fake receipts built to test specific hard cases, and
the 472 real receipts in WildReceipt. Answers are saved as they arrive, so a run stopped
by a rate limit resumes where it left off. Details:
[docs/evaluation.md](docs/evaluation.md).

## Tech stack

- **Backend:** Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic
- **AI:** Gemini API (behind a provider-agnostic wrapper)
- **Frontend:** React + TypeScript (Vite)
- **Infra:** Docker, docker-compose, GitHub Actions, Terraform (AWS), S3, Postmark

## Running locally

Requirements: Python 3.11+, Node 26+, Docker.

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

# 6. In a second terminal, run the frontend (http://localhost:5173)
cd frontend
npm install
npm run dev
```

The Vite dev server forwards `/api/*` to the API on port 8000, so the browser only ever
talks to one origin.

### Tests

```bash
cd backend && pytest          # API, agent, pipeline (mocked LLM)
cd frontend && npm test       # components and helpers (mocked API)
```

Tests mock the LLM, so no API key is needed. They need the Postgres container running, and
use a separate `receipts_test` database (created automatically) so your own receipts never
affect results. Each test also runs inside a transaction that is rolled back afterwards.

## More documentation

- [API reference](docs/api.md): every route, with curl examples
- [Receipt pipeline](docs/receipt-pipeline.md): extraction, validation, categories,
  duplicates, unusual charges
- [Q&A agent](docs/qa-agent.md): the agent loop, tools, and guard rails
- [Accounts and security](docs/security.md): sessions, data isolation, the demo, account
  deletion, card-number masking, limits
- [Frontend](docs/frontend.md): pages, charts, and accessibility
- [Email forwarding](docs/email-forwarding.md): the Postmark webhook and how to try it
- [Evaluation](docs/evaluation.md): test sets, scoring rules, and full results
- [Project structure](docs/project-structure.md)
