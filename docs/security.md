# Accounts, security, and the demo

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
- **Deleting an account** (Account page, `DELETE /auth/me`) needs the password, then
  removes the user, every receipt with its line items and flags, forwarded emails, usage
  counts (all via `ON DELETE CASCADE`), and the uploaded files.
- **Full card numbers are never stored.** The extraction prompt asks for brand and last 4
  only, but that's a request, not a guarantee, so `app/redaction.py` masks any 13-19 digit
  number that passes the card checksum (Luhn) to `•••• 4242` in every extracted text
  field, the raw model answer, and forwarded email text, before anything is saved.
- **Limits.** Every account gets 5 receipts (uploaded or forwarded) and 10 chat questions
  per UTC day, counted with one atomic Postgres upsert so parallel requests can't slip
  past. Login is limited to 10 attempts a minute per IP and 20 an hour per email;
  sign-ups and demos to 5 an hour per IP; and at most 100 demo accounts exist at once.
  The per-IP counters live in memory, which suits a single server.
- **It's a portfolio project:** the sign-up page and dashboard ask people not to upload
  real or sensitive receipts.
