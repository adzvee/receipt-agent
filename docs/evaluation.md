# Evaluation

How accurate is extraction? `backend/evaluation/` measures it on 20 labeled, fake
receipts, each built to test one thing that goes wrong in practice:

| Kind | Samples |
| --- | --- |
| Photo quality | clean baseline, 14° rotation, blurry and low-res, faded thermal ink, shadow across half the receipt |
| Formats | scanned PDF invoice, ride-app screenshot, 16-item receipt |
| Reading what's there | handwritten tip and total, discounts as negative items, quantity × price and per-pound lines, cash tendered and change (not the total) |
| Dates and money | US `04/10` vs French `03/04` date order, `Sat, Sep 5 2026`, EUR/GBP with VAT included, `$` + `CAD`, no currency printed (must be null, not "USD") |
| Should be flagged | a misprinted total (must be copied as printed, not fixed) and a receipt with no date |

Each sample is defined once in `evaluation/samples.py`: the same values draw the image and
write its label, so they can't disagree. A test feeds every label back through scoring as a
"perfect model" and requires 100%, which also proves the labels' arithmetic adds up and
that exactly the two broken receipts trip the app's validation.

```bash
cd backend
python -m evaluation.run              # the model in GEMINI_MODEL; ~20 requests
python -m evaluation.run --no-calls   # re-score saved answers, no requests
```

Scoring is per field, judged like a person would: amounts must match to the cent; vendor
names match loosely (`FRESH MART #112` = `Fresh Mart`); payment matches on card brand and
last 4 digits; line items must all be found (same amount, similar name) with no extras;
and a value that isn't printed must come back as null. A `flag_decision` row checks that
the app's validation flags exactly the receipts it should. Raw model answers are saved in
`evaluation/results/<model>/raw/`, so a run stopped by rate limits resumes where it left
off, and the report is written to `evaluation/results/<model>/report.md`.

## On real receipts: WildReceipt

The fake set tests specific hard cases; [WildReceipt](https://arxiv.org/abs/2103.14470)
(hosted by MMOCR) checks real-world photos. Its test split has 472 receipts, each labeled
per text box (`Store_name_value`, `Date_value`, `Total_value`, ...). `evaluation/wildreceipt.py`
joins each field's boxes in reading order into one expected value and normalizes it:

- **Names** are compared ignoring case, spaces, and punctuation (the labels drop spaces:
  `KOREANRESTAURANT`). A close spelling or one of several labeled boxes (logo and printed
  name) counts, and the report shows how many matched exactly.
- **Dates** are parsed from many formats (`Aug15.2017`, `Jun17'13`, `0ct25'14` with OCR's
  zero for O). An ambiguous one like `05/02/18` is read in the order used by the
  receipt's country, worked out from clear clues in its labeled text: a US state and ZIP
  or a North American phone number (month first); a UK postcode, Australian state,
  international phone code, or £/€/₹/RM/VAT (day first). Canada uses both orders, so a
  Canadian clue settles nothing. With no clear clue (36 of the 124 ambiguous dates in the
  test split) or conflicting clues, the date is left out of the score and counted in the
  report, as are the 8 labels with no year, a French month, or just a time.
- **Amounts** become numbers (`Eur154,40` = 154.40, `.26` = 0.26); a total labeled twice
  collapses to one, and several tax lines may also be answered as their sum.

Fields are scored only where WildReceipt labels them, and mistakes are sorted into types
(missing, gave the subtotal instead, decimal point misplaced, one digit misread, day and
month swapped, wrong year, ...). A label-perfect answer scores 100% on all 1,926 scored
fields, which checks the scoring itself. Address is labeled too but isn't scored: the
extraction schema has no address field.

```bash
python -m evaluation.wildreceipt --download   # once, ~185 MB, into a gitignored folder
python -m evaluation.wildreceipt              # a fixed sample of 100 test receipts
python -m evaluation.wildreceipt --all        # all 472 (the 100 are its first 100)
```

It calls the extraction function directly (not the upload endpoint, so the app's daily
limits don't apply), saves each answer as it arrives, and resumes where it stopped when the
free tier's daily quota runs out. Images and raw answers (real receipts can show card
digits) stay in the gitignored `evaluation/datasets/`; only the report and failure examples
are committed, under `evaluation/results/wildreceipt/`.

**Results: gemini-3.8-flash on all 472 WildReceipt test receipts** (October 2026,
[full report](../backend/evaluation/results/wildreceipt/gemini-3.8-flash/report-all.md)):

| Field | Accuracy | Correct / labeled |
| --- | ---: | ---: |
| Store name (exact, ignoring case/spaces/punctuation) | 66% | 312 / 472 |
| Store name (exact or close) | 96% | 455 / 472 |
| Date | 97% | 341 / 351 |
| Total | 97% | 410 / 422 |
| Subtotal | 94% | 322 / 342 |
| Tax | 90% | 286 / 318 |
| Tip | 76% | 16 / 21 |

- The most common mistake is **leaving tax empty** (25 receipts), often where the
  receipt lists several tax lines; then store names that differ from the label (13,
  some of them label errors, such as an address labeled as the store name) and a
  missing subtotal (11). Misread digits and swapped day/month are rare (2–3 each).
- 85 ambiguous dates were scored in their country's order (57 month-first, 28
  day-first); 39 were left out for lack of a clear country clue, and 8 labels have no
  full date.
- No request failed. The run used 1.14M tokens (609k input, 534k output, of which 424k
  were the model's thinking): about $2.46 at the October 2026 list price ($0.75 / $3.75
  per million input / output tokens), or roughly half a cent per receipt.
- Reading the first 100 results turned up three scoring bugs, all cases where the model
  was right: refunds printed `101.97-`, `170.000` meaning 170,000, and a short store
  name inside the full one (`ROSS` in `ROSS DRESS FOR LESS`). The parser handles them
  now, with tests.

## Results on the fake set

**Results on the fake set (gemini-3.5-flash), partial:** the free tier's 20 requests/day
ran out after 12 of the 20 receipts, which scored 100% on every field (50/50 line items).
The other 8 (including the hardest cases) weren't run: the WildReceipt evaluation above
measures real-world accuracy instead, so the free quota goes there. [Latest report](../backend/evaluation/results/gemini-3.5-flash/report.md).
