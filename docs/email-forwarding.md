# Forwarding receipts by email

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
