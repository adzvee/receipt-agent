# API

Everything except the auth routes, the webhook, and the health checks requires being logged
in, and only ever sees the logged-in user's data.

| Method | Path | What it does |
|---|---|---|
| `POST` | `/auth/register` | Create an account (`{"email", "password"}`, 8+ characters) and log in. |
| `POST` | `/auth/login` | Log in. Sets an HttpOnly session cookie. |
| `POST` | `/auth/logout` | Log out. |
| `GET` | `/auth/me` | The logged-in user, their email forwarding address, and what's left of today's limits. |
| `DELETE` | `/auth/me` | Delete the account, all its receipts, and their files (`{"password"}`; none for demos). |
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
