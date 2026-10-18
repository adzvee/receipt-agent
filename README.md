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

## API

Everything except the auth routes, the webhook, and the health checks requires being logged
in, and only ever sees the logged-in user's data.

| Method | Path | What it does |
|---|---|---|
| `POST` | `/auth/register` | Create an account (`{"email", "password"}`, 8+ characters) and log in. |
| `POST` | `/auth/login` | Log in. Sets an HttpOnly session cookie. |
| `POST` | `/auth/logout` | Log out. |
| `GET` | `/auth/me` | The logged-in user (and their email forwarding address). |
| `POST` | `/auth/demo` | Create a private demo account with sample data, and log into it. |
| `POST` | `/receipts` | Upload a receipt (JPEG, PNG, WebP, or PDF, max 10 MB). Extracts, validates, and saves it. |
| `GET` | `/receipts` | List receipts, newest first. `?needs_review=true` for flagged ones only; `?limit=N` for the first N. |
| `GET` | `/receipts/categories` | The list of spending categories. |
| `GET` | `/receipts/{id}` | One receipt with its line items, category, and flags. |
| `PATCH` | `/receipts/{id}` | Correct the category, e.g. `{"category": "groceries"}`. |
| `POST` | `/receipts/{id}/flags/{flag_id}/dismiss` | Mark a flag as reviewed. |
| `GET` | `/receipts/{id}/file` | The original uploaded file. |
| `GET` | `/receipts/{id}/thumbnail` | A small JPEG preview of a photo receipt (404 for PDFs and emails). |
| `GET` | `/stats/spending` | Totals for the dashboard, e.g. `?group_by=category&start_date=2026-09-01`. |
| `POST` | `/webhooks/postmark/inbound` | Receives forwarded emails from Postmark (HTTP Basic Auth). |
| `POST` | `/chat` | Ask a question, e.g. `{"question": "How much did I spend on food in September?"}`. Returns the answer and which tools were used. |

Try it with curl (or use the app, or the interactive docs at `/docs`):

```bash
curl -c cookies.txt -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "a long password"}' localhost:8000/auth/register
curl -b cookies.txt -F "file=@my-receipt.jpg" localhost:8000/receipts
```

### How extraction works

1. **Check the file.** The real type is detected from the file's first bytes (not its name).
2. **Store the file** under a random key, so the original is always available for review.
3. **Extract.** The file goes to a vision LLM with a JSON schema; the model must return
   vendor, date, line items, subtotal, tax, tip, total, and payment method in that shape.
   The prompt tells it to copy numbers as printed and never "fix" the math.
4. **Validate.** Plain Python checks that line items add up to the subtotal and that
   subtotal + tax + tip equals the total (allowing tax-inclusive receipts and 2¢ of
   rounding), and that vendor, date, and total are present and the date isn't in the future.
5. **Save.** Any failed check becomes a flag. If the LLM call itself fails (after retrying
   temporary errors), the receipt is saved with `status: failed` so nothing is lost.

### Categorization, duplicates, and anomalies

After extraction, each receipt is analyzed:

- **Category.** One of a fixed list (groceries, dining, transportation, ...), so reports stay
  consistent. If an earlier receipt from the same vendor already has a category, it's reused
  (a category you set yourself always wins) and no LLM call is needed. Otherwise the LLM
  picks one from the extracted text, with a one-sentence reason. Vendor names are
  normalized first, so `STARBUCKS #1234` and `Starbucks` count as the same vendor.
- **Duplicates.** Flagged if the exact same file was uploaded before, or if another receipt
  has the same vendor, date, and total (e.g. a photo and the emailed PDF of one purchase).
- **Unusual charges.** Flagged if the total is over 2x the *high end* (90th percentile) of
  your past purchases in that category (once there are 10+ to compare with), over 2.5x your
  *median* at that vendor (5+), or the tip is over 30% of the subtotal. A flagged charge must
  also be at least $25 above the usual amount, so a $12 café order isn't "3x a coffee".
  Categories use the high end because they mix very different purchases (a $4 coffee and a
  $45 dinner are both dining); a vendor's receipts are similar, so the median works there.
  Only receipts in the same currency are compared.

Every problem, from a math mismatch to a likely duplicate, is a **flag** with a plain-English
message. A receipt `needs_review` while it has any flag that hasn't been dismissed.

### The Q&A agent

`POST /chat` answers plain-English questions by running a small agent loop
(`app/agent/agent.py`):

1. The question (plus earlier turns, for follow-ups) goes to the LLM along with
   descriptions of four tools: `spending_summary`, `list_receipts`, `get_receipt`, and
   `search_line_items`.
2. The LLM either answers, or asks for one or more tools with specific arguments.
3. Our code validates the arguments, runs the tool, and sends the result back. Repeat,
   up to 6 steps. On the last step the model isn't allowed to call tools and is told to
   answer from what it has found.

An empty result says so explicitly ("this account has no receipts yet, this is a complete
answer"). Without that, the model treated `[]` as a possible mistake and kept re-checking
with broader filters until it ran out of steps. Now "How much did I spend on food last
month?" on an empty account is one tool call and "$0, no receipts in that period".

**The LLM never writes SQL.** It can only choose a predefined tool and fill in typed
arguments (dates, categories from a fixed list, a vendor name), which are validated before
anything runs. Each tool is a fixed, parameterized SQLAlchemy `SELECT`
(`app/agent/tools.py`). As a second line of defense, the chat request runs in a Postgres
`READ ONLY` transaction with a 5-second statement timeout, so even a buggy tool couldn't
modify data.

Other guard rails: invalid tool calls are returned to the model as errors so it can
correct itself; spending totals skip unreadable receipts and open duplicates; different
currencies are never added together; and receipt text in tool results is treated as data,
not instructions.

### Accounts and the demo

- **Passwords** are hashed with Argon2; only the hash is stored. Login errors are identical
  (and take the same time) whether or not the email exists.
- **Sessions** are JWTs signed with `JWT_SECRET` (required, 32+ characters, outside
  development) and kept in an **HttpOnly, SameSite=Lax cookie**: page JavaScript can't read
  it, so a script-injection bug couldn't steal it, and other sites can't make requests with
  it. API clients can send the same token as a `Bearer` header.
- **Every query is scoped to the logged-in user**: receipt routes, dashboard stats, all
  four agent tools, and the analysis steps (vendor history, duplicate checks, and anomaly
  history never look at other people's receipts). Someone else's receipt returns the same
  404 as a missing one, so ids can't be probed. Tests cover each route and tool.
- **Email forwarding** is routed by a private token in the address
  (`inbox+TOKEN@inbound.postmarkapp.com`); mail for unknown tokens is ignored before any
  LLM call.
- **"Try the demo"** creates a fresh private account per visitor with ~two months of
  invented receipts, so visitors can upload and edit without affecting each other. Every
  demo receipt goes through the real validation, duplicate, and anomaly checks (four are
  built to trip one each). Demo accounts are deleted after 24 hours and are capped at 25
  AI-backed requests, so a public demo can't exhaust the LLM quota.

### The frontend

React + TypeScript (Vite), with React Router for pages, TanStack Query for fetching and
caching API data, and Recharts for charts.

- **Dashboard:** monthly spending for the last year, a period filter (this month, last
  month, last 90 days, ...) that scopes the total and the category breakdown below it,
  receipts needing review, and the chat box. The dashboard's totals come from the same
  `spending_summary` function the agent uses, so the two always agree. A new account sees
  a single welcome state instead: an Upload receipt button and its forwarding address.
- **Receipts:** drag-and-drop upload (several files at once, or "Take photo" on phones),
  the user's email forwarding address, and the list with photo thumbnails, filterable to
  receipts that need review.
- **Receipt detail:** the original file next to the extracted fields and line items,
  flags with a Dismiss button, and a category picker.

Each category has one color and icon, used in both the category chart and the receipts
list; every color is checked for at least 3:1 contrast in light and dark mode, and the
category name is always shown too, so color is never the only cue. Charts label values
directly or in a subtitle (never clipped), show a tooltip on hover, and have a "Show as
table" view so no number is only available by hovering. The chat renders
the model's bold text and bullet lists as React elements, never as raw HTML.

### Forwarding receipts by email

[Postmark](https://postmarkapp.com/developer/webhooks/inbound-webhook) receives emails sent
to an inbound address and POSTs each one to `/webhooks/postmark/inbound` as JSON.

1. **Authenticate.** Postmark doesn't sign webhooks, so the webhook URL carries a username
   and password (`https://USER:PASS@host/webhooks/postmark/inbound`), compared in constant
   time. The endpoint is disabled until both are set in `.env`.
2. **Skip re-deliveries.** Postmark retries until it gets a 200, so each email's
   `MessageID` is stored and a repeat is answered without reprocessing.
3. **Is it a receipt?** One LLM call sees the sender, subject, body, and attachment names,
   and decides whether it's a receipt and whether the receipt is in an attachment or the
   body (common for ride, delivery, and online-order emails). Promotions, newsletters, and
   shipping updates are recorded and ignored.
4. **Process.** Each usable attachment (PDF/image, not an inline logo) goes through the same
   pipeline as an upload. A receipt in the body is converted from HTML to plain text and
   stored as `.txt` — never as HTML, which could run scripts when viewed.
5. **Fail safely.** If the "is it a receipt?" call fails, nothing is saved and the endpoint
   returns 503, so Postmark retries later.

Try it locally with the fake sample email. Set `POSTMARK_INBOUND_USERNAME` and
`POSTMARK_INBOUND_PASSWORD` in `.env`, restart the API, and use the same values here:

```bash
curl -u "YOUR_USERNAME:YOUR_PASSWORD" \
  -H "Content-Type: application/json" \
  --data @backend/samples/postmark_receipt_email.json \
  localhost:8000/webhooks/postmark/inbound
```

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
│   │   ├── categorization.py  # Vendor history, else LLM picks a category
│   │   ├── duplicates.py      # Same file / same purchase detection
│   │   ├── anomalies.py       # Unusual-charge rules
│   │   ├── vendors.py         # Vendor name normalization and matching
│   │   ├── agent/             # Q&A agent loop + read-only database tools
│   │   ├── auth.py            # Password hashing, JWT sessions, current user
│   │   ├── demo.py            # "Try demo" accounts and their fake receipts
│   │   ├── email/             # Forwarded emails: receipt check, HTML→text
│   │   ├── file_types.py      # Detect file type from content
│   │   ├── storage.py         # File storage (local disk; S3 later)
│   │   └── llm/               # Provider-agnostic LLM wrapper + Gemini implementation
│   ├── alembic/        # Database migrations
│   ├── samples/        # Fake example payloads
│   └── tests/          # pytest suite
├── frontend/
│   └── src/
│       ├── api.ts      # Typed API client
│       ├── format.ts   # Money/date formatting, period math
│       ├── pages/      # Dashboard, Receipts, Receipt detail
│       └── components/ # Charts, upload, chat, table, flags
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
- [x] 3. Categorization, duplicate detection, anomaly flags
- [x] 4. Q&A agent with read-only database tools
- [x] 5. Email forwarding (Postmark inbound webhook)
- [x] 6. Frontend: upload, list, flags, dashboard, chat
- [x] 7. User accounts + demo account
- [ ] 8. Extraction evaluation script
- [ ] 9. Deployment (Docker, Terraform, CD)
- [ ] 10. Final README
