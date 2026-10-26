# Receipt pipeline: extraction, checks, and analysis

## How extraction works

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

## Categorization, duplicates, and anomalies

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

The LLM sits behind a small `LLMClient` interface (`app/llm/`), so Gemini can be swapped
for another provider by adding one class.
