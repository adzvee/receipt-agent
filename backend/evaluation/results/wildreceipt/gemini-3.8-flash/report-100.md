# WildReceipt extraction accuracy: gemini-3.8-flash

100 real receipts from the WildReceipt test split, run on 2026-10-26.
Each field is scored only on receipts where WildReceipt labels it.

| Field | Accuracy | Correct | Labeled in |
| --- | ---: | ---: | ---: |
| store name | 95% | 95/100 | 100 |
| date | 96% | 68/71 | 71 |
| total | 98% | 88/90 | 90 |
| subtotal | 94% | 67/71 | 71 |
| tax | 91% | 61/67 | 67 |
| tip | 100% | 3/3 | 3 |

- Store names: 66/100 (66%) match the label exactly (ignoring case, spaces, punctuation); the rest of the correct ones are close matches (a typo, a branch number, or just one of the label's boxes).
- Ambiguous dates (like 05/02/18): 19 scored using the country shown by the receipt's address, phone, or currency (11 month-first, 8 day-first); **13 left out** of the date score because the receipt has no clear country clue.
- Tokens (99 receipts with recorded usage): 127,662 input, 106,373 output (of which 82,806 thinking), 234,035 total.

Labeled fields not scored:

- date: ambiguous, no country clue: 13
- date: label has no full date: 3

## Most common errors

| Field | Error | Count |
| --- | --- | ---: |
| tax | missing | 4 |
| store name | different name | 3 |
| total | different amount | 2 |
| subtotal | one digit misread | 2 |
| subtotal | missing | 2 |
| date | different date | 2 |
| store name | missing | 2 |
| tax | decimal point misplaced | 1 |
| date | wrong year | 1 |
| tax | different amount | 1 |

## Failure examples

- `27f879c6141f` tax, missing: label `1.30 0.38`, model `None`
- `d9544f86929a` tax, missing: label `2.48 2.48`, model `None`
- `b56293eb3656` store name, different name: label `1E.MillsCircle`, model `COACH`
- `2134` store name, different name: label `PMfarlia`, model `Pizza Hut Restaurants Sdn Bhd`
- `3755a671aa0c` total, different amount: label `11.98`, model `12.00`
- `4227` total, different amount: label `11.98`, model `12.00`
- `828ed85f4e77` subtotal, one digit misread: label `11.98`, model `11.99`
- `dcff7be58f5c` subtotal, one digit misread: label `$97.30`, model `87.30`
- `565131355216` subtotal, missing: label `1.48`, model `None`
- `fda09a8db93c` subtotal, missing: label `18.90`, model `None`
- `fda09a8db93c` date, different date: label `07-12-2017`, model `2017-07-13`
- `0c0b19ea80a9` date, different date: label `18/09/2018`, model `2016-09-16`
- `32b598f05010` store name, missing: label `DresserWayne`, model `None`
- `881976df4715` store name, missing: label `PROFORMA`, model `None`
- `c78135ef3a18` tax, decimal point misplaced: label `8.59-A`, model `8.59`
- `2134` date, wrong year: label `07-27-2005`, model `2009-07-27`
- `89ac29dbd20a` tax, different amount: label `-50.00`, model `0.00`
