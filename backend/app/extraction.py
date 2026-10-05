"""Turning a receipt file into structured data with a vision LLM."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from pydantic import BaseModel, Field

from app.llm import Attachment, LLMClient

# What we ask the model to return. Money is a float here because LLM structured-output
# schemas don't support decimals; it's converted to Decimal with `money()` right after.


class ExtractedLineItem(BaseModel):
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    amount: float = Field(description="Line total as printed. Discounts are negative.")


class ExtractedReceipt(BaseModel):
    vendor: str | None = Field(description="Store or business name.")
    purchase_date: str | None = Field(description="Date of purchase as YYYY-MM-DD.")
    currency: str | None = Field(
        description="ISO 4217 code, e.g. USD, EUR, GBP. Null unless a symbol or code is printed."
    )
    line_items: list[ExtractedLineItem]
    subtotal: float | None
    tax: float | None
    tip: float | None
    total: float | None
    payment_method: str | None = Field(
        description="e.g. 'Cash', 'Visa ending 1234'. Never the full card number."
    )


EXTRACTION_PROMPT = """\
You are extracting data from a receipt for bookkeeping.

Rules:
- Copy every number exactly as printed. Do NOT calculate, correct, or fill in values that
  aren't on the receipt; use null instead. A separate step checks the arithmetic.
- Amounts are plain numbers without currency symbols.
- Set currency only if a currency symbol or code is printed. Treat "$" as USD unless the
  receipt shows another dollar currency (e.g. CAD, AUD). If nothing is printed, use null.
- Record discounts and coupons as line items with negative amounts.
- `amount` is the total for the line (quantity x unit price), as printed.
- If tax is already included in item prices (e.g. "VAT included"), still report the tax
  amount shown.
- For payment_method, include at most the card brand and last 4 digits.
- If the image is not a receipt, return nulls and an empty line_items list.
"""


def extract_receipt(llm: LLMClient, data: bytes, mime_type: str) -> ExtractedReceipt:
    return llm.generate_structured(
        prompt=EXTRACTION_PROMPT,
        response_model=ExtractedReceipt,
        attachments=[Attachment(data=data, mime_type=mime_type)],
    )


def money(value: float | None) -> Decimal | None:
    """An LLM float as a Decimal with 2 places, matching the database's money columns."""
    return _to_decimal(value, places=Decimal("0.01"))


def quantity(value: float | None) -> Decimal | None:
    """An LLM float as a Decimal with 3 places (e.g. 1.250 kg), matching the database column."""
    return _to_decimal(value, places=Decimal("0.001"))


def _to_decimal(value: float | None, places: Decimal) -> Decimal | None:
    # Going through str() avoids float artifacts: Decimal(0.1) is 0.1000000000000000055...
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(places, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
