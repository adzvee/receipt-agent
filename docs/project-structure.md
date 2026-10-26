# Project structure

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
│   ├── evaluation/     # Labeled fake receipts + extraction accuracy script
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
