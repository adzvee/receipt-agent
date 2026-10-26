# WildReceipt extraction accuracy: gemini-3.8-flash

472 real receipts from the WildReceipt test split, run on 2026-10-26.
Each field is scored only on receipts where WildReceipt labels it.

| Field | Accuracy | Correct | Labeled in |
| --- | ---: | ---: | ---: |
| store name | 96% | 455/472 | 472 |
| date | 97% | 341/351 | 351 |
| total | 97% | 410/422 | 422 |
| subtotal | 94% | 322/342 | 342 |
| tax | 90% | 286/318 | 318 |
| tip | 76% | 16/21 | 21 |

- Store names: 312/472 (66%) match the label exactly (ignoring case, spaces, punctuation); the rest of the correct ones are close matches (a typo, a branch number, or just one of the label's boxes).
- Ambiguous dates (like 05/02/18): 85 scored using the country shown by the receipt's address, phone, or currency (57 month-first, 28 day-first); **39 left out** of the date score because the receipt has no clear country clue.
- Tokens (471 receipts with recorded usage): 608,619 input, 533,727 output (of which 423,656 thinking), 1,142,346 total.

Labeled fields not scored:

- date: ambiguous, no country clue: 36
- date: label has no full date: 8
- date: ambiguous, could be Canadian: 2
- subtotal: label has no amount: 1
- date: ambiguous, clues disagree: 1

## Most common errors

| Field | Error | Count |
| --- | --- | ---: |
| tax | missing | 25 |
| store name | different name | 13 |
| subtotal | missing | 11 |
| total | different amount | 8 |
| date | different date | 5 |
| store name | missing | 4 |
| tax | different amount | 4 |
| subtotal | different amount | 4 |
| tip | missing | 4 |
| subtotal | one digit misread | 3 |
| total | one digit misread | 2 |
| subtotal | gave the total instead | 2 |
| date | day and month swapped | 2 |
| date | missing | 2 |
| total | missing | 2 |
| tax | one digit misread | 2 |
| tax | decimal point misplaced | 1 |
| date | wrong year | 1 |
| tip | different amount | 1 |

## Failure examples

- `27f879c6141f` tax, missing: label `1.30 0.38`, model `None`
- `d9544f86929a` tax, missing: label `2.48 2.48`, model `None`
- `b56293eb3656` store name, different name: label `1E.MillsCircle`, model `COACH`
- `2134` store name, different name: label `PMfarlia`, model `Pizza Hut Restaurants Sdn Bhd`
- `565131355216` subtotal, missing: label `1.48`, model `None`
- `fda09a8db93c` subtotal, missing: label `18.90`, model `None`
- `3755a671aa0c` total, different amount: label `11.98`, model `12.00`
- `4227` total, different amount: label `11.98`, model `12.00`
- `fda09a8db93c` date, different date: label `07-12-2017`, model `2017-07-13`
- `0c0b19ea80a9` date, different date: label `18/09/2018`, model `2016-09-16`
- `32b598f05010` store name, missing: label `DresserWayne`, model `None`
- `881976df4715` store name, missing: label `PROFORMA`, model `None`
- `89ac29dbd20a` tax, different amount: label `-50.00`, model `0.00`
- `4f92cc1cb44e` tax, different amount: label `1.07VAT20%`, model `1.07`
- `8503b34e776a` subtotal, different amount: label `49.25`, model `44.77`
- `7dbaadf00dc8` subtotal, different amount: label `$88.95`, model `97.62`
- `1d9b1fc7e0af` tip, missing: label `$61.89 $64.58 $67.28 $8.07 $13.46 $10.76`, model `None`
- `db26cc8b43a2` tip, missing: label `$5.57 $6.19 $4.64`, model `None`
- `828ed85f4e77` subtotal, one digit misread: label `11.98`, model `11.99`
- `dcff7be58f5c` subtotal, one digit misread: label `$97.30`, model `87.30`
- `3455` total, one digit misread: label `$61.56 $61.56`, model `61.76`
- `1265ac53a8ad` total, one digit misread: label `$61.56`, model `61.76`
- `4f92cc1cb44e` subtotal, gave the total instead: label `GBP5.33`, model `6.40`
- `375ac92e91a4` subtotal, gave the total instead: label `528.80`, model `661.00`
- `abe4a99fc868` date, day and month swapped: label `06/08/2017`, model `2017-06-08`
- `46d65aed5ae6` date, day and month swapped: label `06/02/2015 06/02/2015`, model `2015-02-06`
- `a91821e592a9` date, missing: label `NOV/25/2016 DIC/21/2016`, model `None`
- `2b99c1df5dd5` date, missing: label `01/17/17`, model `None`
- `a91821e592a9` total, missing: label `$1,400.00 $1,400.00`, model `None`
- `4f449bf99b3d` total, missing: label `5.74`, model `None`
- `e000cbc415cb` tax, one digit misread: label `12.05`, model `12.06`
- `3c610b660ee3` tax, one digit misread: label `4.53`, model `1.53`
- `c78135ef3a18` tax, decimal point misplaced: label `8.59-A`, model `8.59`
- `2134` date, wrong year: label `07-27-2005`, model `2009-07-27`
- `f7a60a9b2fc2` tip, different amount: label `$14:20`, model `16.70`
