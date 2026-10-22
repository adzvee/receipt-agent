# Extraction accuracy: gemini-3.5-flash

12 fake receipts from `evaluation/samples/`, run on 2026-10-22.

| Field | Accuracy | Correct |
| --- | ---: | ---: |
| vendor | 100% | 12/12 |
| purchase_date | 100% | 12/12 |
| currency | 100% | 12/12 |
| subtotal | 100% | 12/12 |
| tax | 100% | 12/12 |
| tip | 100% | 12/12 |
| total | 100% | 12/12 |
| payment_method | 100% | 12/12 |
| line_items | 100% | 12/12 |
| flag_decision | 100% | 12/12 |

- Receipts with every field right: **12/12** (100%)
- Line items found: 50/50 (100%); of the items returned, 50/50 were real (100%)

## Not scored

- `shadowed_photo`: no saved answer (run without --no-calls)
- `no_currency_symbol`: no saved answer (run without --no-calls)
- `misprinted_total`: no saved answer (run without --no-calls)
- `cash_with_change`: no saved answer (run without --no-calls)
- `canadian_dollars`: no saved answer (run without --no-calls)
- `no_date`: no saved answer (run without --no-calls)
- `utility_bill_pdf`: no saved answer (run without --no-calls)
- `ride_app_screenshot`: no saved answer (run without --no-calls)

## Mistakes

None.
