"""The labeled evaluation set: 20 fake receipts, each testing something specific.

Every sample is defined once, in code: the same values produce both the receipt image and
its expected extraction, so labels can't drift from what's printed. All vendors, card
numbers, and addresses are made up.

    python -m evaluation.samples   # (re)writes evaluation/samples/ and labels.json

The generated files are committed, so the evaluation doesn't depend on local fonts.
"""

import json
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

SAMPLES_DIR = Path(__file__).parent / "samples"
LABELS_FILE = SAMPLES_DIR / "labels.json"

# --- Money helpers ---


def d(value: str) -> Decimal:
    return Decimal(value)


def cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt(value: Decimal) -> str:
    return f"{value:.2f}"


# --- Expected results ---


@dataclass
class Item:
    description: str
    amount: str
    quantity: str | None = None
    unit_price: str | None = None


@dataclass
class Expected:
    """What a perfect extraction returns: the values as printed (see EXTRACTION_PROMPT)."""

    vendor: str | None
    purchase_date: str | None
    currency: str | None
    line_items: list[Item]
    subtotal: str | None
    tax: str | None
    tip: str | None
    total: str | None
    payment_method: str | None

    def to_json(self) -> dict[str, Any]:
        return {**self.__dict__, "line_items": [item.__dict__ for item in self.line_items]}


@dataclass
class Sample:
    id: str
    tests: str  # what this sample checks, in plain words
    expected: Expected
    # True if the checks in app/validation.py should flag it (e.g. a misprinted total).
    expect_flagged: bool
    render: Callable[[], tuple[bytes, str]]  # -> (file bytes, mime type)
    extension: str = "jpg"


# --- Fonts (macOS first, then Linux; the committed files were made on macOS) ---

FONTS = {
    "mono": ["/System/Library/Fonts/Menlo.ttc", "DejaVuSansMono.ttf"],
    "sans": ["/System/Library/Fonts/Helvetica.ttc", "DejaVuSans.ttf"],
    "sans_bold": ["/System/Library/Fonts/HelveticaNeue.ttc", "DejaVuSans-Bold.ttf"],
    "hand": ["/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf", "DejaVuSans.ttf"],
}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONTS[kind]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


# --- Thermal-printer receipts ---

WIDTH = 40  # characters per line


@dataclass
class Thermal:
    """A receipt laid out in monospace lines, like a till printer."""

    lines: list[tuple[str, str]] = field(default_factory=list)  # (style, text)

    def center(self, text: str) -> "Thermal":
        self.lines.append(("mono", text.center(WIDTH)))
        return self

    def text(self, text: str) -> "Thermal":
        self.lines.append(("mono", text))
        return self

    def row(self, left: str, right: str) -> "Thermal":
        self.lines.append(
            ("mono", left[: WIDTH - len(right) - 1].ljust(WIDTH - len(right)) + right)
        )
        return self

    def rule(self) -> "Thermal":
        return self.text("-" * WIDTH)

    def blank(self) -> "Thermal":
        return self.text("")

    def handwritten(self, label: str, value: str) -> "Thermal":
        """A printed label with a value written in by hand (e.g. the tip line)."""
        self.lines.append(("hand", f"{label}\t{value}"))
        return self

    def image(self, ink: tuple[int, int, int] = (25, 25, 25)) -> Image.Image:
        mono = font("mono", 22)
        hand = font("hand", 30)
        char_w = mono.getlength("M")
        line_h = 30
        margin = 28
        width = int(char_w * WIDTH + 2 * margin)
        height = line_h * len(self.lines) + 2 * margin
        paper = Image.new("RGB", (width, height), (250, 249, 244))
        draw = ImageDraw.Draw(paper)
        for i, (style, text) in enumerate(self.lines):
            y = margin + i * line_h
            if style == "hand":
                label, value = text.split("\t")
                draw.text((margin, y), label, font=mono, fill=ink)
                draw.text((margin + char_w * 24, y - 8), value, font=hand, fill=(20, 40, 120))
            else:
                draw.text((margin, y), text, font=mono, fill=ink)
        return paper


def photo(
    paper: Image.Image,
    *,
    seed: int,
    angle: float = 2.0,
    blur: float = 0.6,
    scale: float = 1.0,
    shadow: float = 0.0,
    noise: int = 6,
) -> Image.Image:
    """Make a clean receipt look photographed: on a table, tilted, softened, unevenly lit."""
    rng = random.Random(seed)
    pad = 80
    table = Image.new("RGB", (paper.width + 2 * pad, paper.height + 2 * pad), (118, 96, 74))
    table.paste(paper, (pad, pad))
    image = table.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=(118, 96, 74))
    if shadow:
        # Darken one side, like a phone or hand casting a shadow.
        gradient = Image.linear_gradient("L").rotate(90).resize(image.size)
        dark = ImageEnhance.Brightness(image).enhance(1 - shadow)
        image = Image.composite(image, dark, gradient)
    if scale != 1.0:
        image = image.resize((int(image.width * scale), int(image.height * scale)))
    image = image.filter(ImageFilter.GaussianBlur(blur))
    if noise:
        pixels = image.load()
        for _ in range(image.width * image.height // 12):
            x, y = rng.randrange(image.width), rng.randrange(image.height)
            r, g, b = pixels[x, y]
            n = rng.randint(-noise, noise)
            pixels[x, y] = (r + n, g + n, b + n)
    return image


def jpeg(image: Image.Image, quality: int = 85) -> tuple[bytes, str]:
    out = BytesIO()
    image.save(out, "JPEG", quality=quality)
    return out.getvalue(), "image/jpeg"


def png(image: Image.Image) -> tuple[bytes, str]:
    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue(), "image/png"


def money_rows(receipt: Thermal, items: list[Item], symbol: str = "") -> None:
    for item in items:
        if item.quantity and item.unit_price:
            receipt.text(item.description)
            receipt.row(f"  {item.quantity} @ {item.unit_price}", f"{symbol}{item.amount}")
        else:
            receipt.row(item.description, f"{symbol}{item.amount}")


def items_total(items: list[Item]) -> Decimal:
    return sum((d(item.amount) for item in items), Decimal("0"))


# --- The samples ---


def expected(
    vendor: str | None,
    date: str | None,
    currency: str | None,
    items: list[Item],
    *,
    total: Decimal | str | None,
    subtotal: Decimal | str | None = None,
    tax: Decimal | str | None = None,
    tip: Decimal | str | None = None,
    payment: str | None = None,
) -> Expected:
    def as_text(value: Decimal | str | None) -> str | None:
        return fmt(value) if isinstance(value, Decimal) else value

    return Expected(
        vendor=vendor,
        purchase_date=date,
        currency=currency,
        line_items=items,
        subtotal=as_text(subtotal),
        tax=as_text(tax),
        tip=as_text(tip),
        total=as_text(total),
        payment_method=payment,
    )


def grocery_clean() -> Sample:
    items = [
        Item("Bananas", "1.29"),
        Item("Whole milk 1 gal", "4.19"),
        Item("Sourdough bread", "5.49"),
        Item("Eggs dozen", "3.99"),
        Item("Spinach", "2.99"),
        Item("Dish soap", "3.79"),
    ]
    subtotal = items_total(items)
    tax = cents(d("3.79") * d("0.0725"))  # only the soap is taxable
    total = subtotal + tax
    r = Thermal().center("FRESH MART #112").center("88 Orchard Ave, Springfield")
    r.center("(555) 010-2231").blank().text("09/12/2026  14:32      Reg 3").rule()
    money_rows(r, items)
    r.rule().row("SUBTOTAL", fmt(subtotal)).row("TAX 7.25%", fmt(tax))
    r.row("TOTAL", f"${fmt(total)}").blank().row("VISA ************4242", fmt(total))
    r.blank().center("THANK YOU FOR SHOPPING!")
    return Sample(
        "grocery_clean",
        "A clean, upright grocery receipt: the baseline.",
        expected(
            "Fresh Mart",
            "2026-09-12",
            "USD",
            items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            payment="Visa ending 4242",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=1, angle=0.8)),
    )


def cafe_us_date() -> Sample:
    items = [Item("Oat latte", "5.25"), Item("Almond croissant", "4.50")]
    subtotal = items_total(items)
    tax = cents(subtotal * d("0.08875"))
    total = subtotal + tax
    r = Thermal().center("CORNER CAFE").center("12 Elm St").blank()
    r.text("04/10/2026 08:12   Order #5521").rule()  # US style: April 10
    money_rows(r, items, "$")
    r.rule().row("Subtotal", f"${fmt(subtotal)}").row("Sales Tax", f"${fmt(tax)}")
    r.row("Total", f"${fmt(total)}").row("Mastercard xxxx-xxxx-xxxx-8810", f"${fmt(total)}")
    return Sample(
        "cafe_us_date",
        "US date format 04/10/2026 means April 10, not October 4.",
        expected(
            "Corner Cafe",
            "2026-04-10",
            "USD",
            items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            payment="Mastercard ending 8810",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=2, angle=-1.5)),
    )


def restaurant_handwritten_tip() -> Sample:
    items = [
        Item("Grilled salmon", "26.00"),
        Item("Ribeye", "34.00"),
        Item("House salad", "9.50"),
        Item("Iced tea", "3.50", "2", "1.75"),
    ]
    subtotal = items_total(items)
    tax = cents(subtotal * d("0.08"))
    amount = subtotal + tax
    tip = d("14.00")
    total = amount + tip
    r = Thermal().center("LAKESIDE GRILL").center("400 Shore Rd").blank()
    r.text("Server: Dana     Table 12").text("Sep 19, 2026  7:48 PM").rule()
    money_rows(r, items)
    r.rule().row("Subtotal", fmt(subtotal)).row("Tax", fmt(tax)).row("Amount", f"${fmt(amount)}")
    r.blank().handwritten("Tip:", fmt(tip)).blank().handwritten("Total:", fmt(total))
    r.blank().text("AMEX ***********1007").blank().text("X_______________________")
    return Sample(
        "restaurant_handwritten_tip",
        "Tip and final total are handwritten; the printed 'Amount' is not the total.",
        expected(
            "Lakeside Grill",
            "2026-09-19",
            "USD",
            items,
            subtotal=subtotal,
            tax=tax,
            tip=tip,
            total=total,
            payment="Amex ending 1007",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=3, angle=1.2)),
    )


def eu_vat_included() -> Sample:
    items = [Item("Croque monsieur", "12.50"), Item("Salade verte", "6.50"), Item("Café", "2.80")]
    total = items_total(items)
    tax = cents(total - total / d("1.10"))  # 10% VAT already in the prices
    r = Thermal().center("BISTRO LUMIERE").center("21 rue des Lilas, 75011 Paris")
    r.blank().text("03/04/2026  12:41      Table 4").rule()  # French style: 3 April
    money_rows(r, items)
    r.rule().row("TOTAL TTC", f"{fmt(total)} EUR").row("dont TVA 10%", fmt(tax))
    r.blank().row("CB VISA **** 3391", f"{fmt(total)} EUR").blank().center("MERCI !")
    return Sample(
        "eu_vat_included",
        "French receipt: VAT already included in prices, and 03/04 means 3 April.",
        expected(
            "Bistro Lumiere",
            "2026-04-03",
            "EUR",
            items,
            tax=tax,
            total=total,
            payment="Visa ending 3391",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=4, angle=-0.7)),
    )


def uk_pharmacy_gbp() -> Sample:
    items = [Item("Ibuprofen 200mg x16", "2.49"), Item("Sun cream SPF50", "8.99")]
    total = items_total(items)
    tax = cents(total - total / d("1.20"))
    r = Thermal().center("GREENWAY PHARMACY").center("5 Mill Lane, London N1").blank()
    r.text("14/09/2026 16:05").rule()
    money_rows(r, items, "£")
    r.rule().row("TOTAL", f"£{fmt(total)}").row("VAT @ 20% incl.", f"£{fmt(tax)}")
    r.row("Contactless DEBIT ****6620", f"£{fmt(total)}")
    return Sample(
        "uk_pharmacy_gbp",
        "Pound sterling, UK date order, VAT included.",
        expected(
            "Greenway Pharmacy",
            "2026-09-14",
            "GBP",
            items,
            tax=tax,
            total=total,
            payment="Debit ending 6620",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=5, angle=2.5)),
    )


def discounts() -> Sample:
    items = [
        Item("Bath towel set", "24.99"),
        Item("Storage bins 3pk", "18.49"),
        Item("COUPON 20% TOWELS", "-5.00"),
        Item("Desk lamp", "29.99"),
        Item("MEMBER SAVINGS", "-2.50"),
    ]
    subtotal = items_total(items)
    tax = cents(subtotal * d("0.065"))
    total = subtotal + tax
    r = Thermal().center("HOMEGOODS DEPOT").center("Store 0412").blank()
    r.text("10/02/2026 11:20").rule()
    money_rows(r, items)
    r.rule().row("SUBTOTAL", fmt(subtotal)).row("TAX", fmt(tax)).row("TOTAL USD", fmt(total))
    r.row("DISCOVER ...9014", fmt(total)).blank().center("YOU SAVED $7.50 TODAY")
    return Sample(
        "discounts",
        "Coupon and member savings must be negative line items.",
        expected(
            "HomeGoods Depot",
            "2026-10-02",
            "USD",
            items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            payment="Discover ending 9014",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=6, angle=-2.0)),
    )


def quantities_and_weights() -> Sample:
    items = [
        Item("Honeycrisp apples", "4.99", "1.25", "3.99"),
        Item("Peaches", "2.98", "2", "1.49"),
        Item("Sweet corn", "3.00", "6", "0.50"),
        Item("Raw honey 12oz", "9.00"),
    ]
    total = items_total(items)
    r = Thermal().center("HILLTOP FARM STAND").center("Route 9").blank()
    r.text("Sat 08/29/2026").rule()
    for item in items:
        if item.description.startswith("Honeycrisp"):
            r.text(item.description).row("  1.25 lb @ $3.99/lb", item.amount)
        elif item.quantity:
            r.text(item.description).row(f"  {item.quantity} @ ${item.unit_price}", item.amount)
        else:
            r.row(item.description, item.amount)
    r.rule().row("TOTAL", f"${fmt(total)}").row("CASH", "20.00").row("CHANGE", "0.03")
    return Sample(
        "quantities_and_weights",
        "Quantity x unit price lines, including a weight in pounds.",
        expected(
            "Hilltop Farm Stand",
            "2026-08-29",
            "USD",
            items,
            total=total,
            payment="Cash",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=7, angle=1.0)),
    )


def rotated_photo() -> Sample:
    items = [Item("Allergy relief 30ct", "12.99"), Item("Cough drops", "3.49")]
    subtotal = items_total(items)
    tax = cents(subtotal * d("0.06"))
    total = subtotal + tax
    r = Thermal().center("PINE PHARMACY").center("70 Birch Blvd").blank()
    r.text("10/09/2026 18:03").rule()
    money_rows(r, items)
    r.rule().row("SUBTOTAL", fmt(subtotal)).row("TAX", fmt(tax)).row("TOTAL", f"${fmt(total)}")
    r.row("VISA DEBIT ****5108", fmt(total))
    return Sample(
        "rotated_photo",
        "Photo taken at a 14 degree angle.",
        expected(
            "Pine Pharmacy",
            "2026-10-09",
            "USD",
            items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            payment="Visa ending 5108",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=8, angle=14)),
    )


def blurry_low_res() -> Sample:
    items = [Item("Wood screws 100pk", "7.49"), Item("Paint roller", "8.99"), Item("Tape", "4.29")]
    subtotal = items_total(items)
    tax = cents(subtotal * d("0.07"))
    total = subtotal + tax
    r = Thermal().center("CITY HARDWARE").center("1 Main St").blank()
    r.text("09/27/2026 10:15").rule()
    money_rows(r, items)
    r.rule().row("SUBTOTAL", fmt(subtotal)).row("TAX", fmt(tax)).row("TOTAL", f"${fmt(total)}")
    r.row("VISA ****7731", fmt(total))
    return Sample(
        "blurry_low_res",
        "Small, out-of-focus photo.",
        expected(
            "City Hardware",
            "2026-09-27",
            "USD",
            items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            payment="Visa ending 7731",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=9, scale=0.55, blur=1.3), quality=70),
    )


def faded_thermal() -> Sample:
    items = [Item("Unleaded", "36.36", "10.512", "3.459")]
    total = items_total(items)
    r = Thermal().center("QUICKSTOP FUEL").center("Pump 6").blank()
    r.text("DATE 10/11/2026  TIME 07:55").rule()
    r.text("Unleaded").row("  10.512 GAL @ $3.459", "36.36")
    r.rule().row("TOTAL SALE", f"${fmt(total)}").row("VISA ****2208", fmt(total))
    return Sample(
        "faded_thermal",
        "Faded thermal paper with low-contrast gray print.",
        expected(
            "QuickStop Fuel",
            "2026-10-11",
            "USD",
            items,
            total=total,
            payment="Visa ending 2208",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(ink=(165, 162, 155)), seed=10, angle=-1.0)),
    )


def shadowed_photo() -> Sample:
    items = [Item("Spicy beef noodles", "15.50"), Item("Pork dumplings", "8.00")]
    subtotal = items_total(items)
    tax = cents(subtotal * d("0.0875"))
    total = subtotal + tax
    r = Thermal().center("NOODLE HOUSE").center("9 Canal St").blank()
    r.text("09/03/2026 13:10   Takeout").rule()
    money_rows(r, items)
    r.rule().row("Subtotal", fmt(subtotal)).row("Tax", fmt(tax)).row("Total", f"${fmt(total)}")
    r.row("VISA ****4242", fmt(total))
    return Sample(
        "shadowed_photo",
        "Uneven lighting: one side of the photo is in shadow.",
        expected(
            "Noodle House",
            "2026-09-03",
            "USD",
            items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            payment="Visa ending 4242",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=11, angle=3, shadow=0.6)),
    )


def long_receipt() -> Sample:
    names = [
        ("Apples 3lb bag", "4.99"),
        ("Carrots", "1.49"),
        ("Chicken thighs", "8.72"),
        ("Brown rice", "3.29"),
        ("Black beans", "1.19"),
        ("Black beans", "1.19"),
        ("Greek yogurt", "5.49"),
        ("Cheddar block", "4.79"),
        ("Tortillas", "3.49"),
        ("Salsa", "3.99"),
        ("Coffee beans", "11.99"),
        ("Paper towels", "8.99"),
        ("Olive oil", "9.49"),
        ("Lemons", "2.00"),
        ("Pasta", "1.79"),
        ("Tomato sauce", "2.49"),
    ]
    items = [Item(name, amount) for name, amount in names]
    subtotal = items_total(items)
    tax = cents(d("8.99") * d("0.07"))  # paper towels only
    total = subtotal + tax
    r = Thermal().center("FRESH MART #112").center("88 Orchard Ave, Springfield").blank()
    r.text("10/16/2026  17:46      Reg 1").rule()
    money_rows(r, items)
    r.rule().row(f"SUBTOTAL ({len(items)} items)", fmt(subtotal)).row("TAX", fmt(tax))
    r.row("TOTAL", f"${fmt(total)}").row("VISA ************4242", fmt(total))
    return Sample(
        "long_receipt",
        "16 line items, including the same item twice.",
        expected(
            "Fresh Mart",
            "2026-10-16",
            "USD",
            items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            payment="Visa ending 4242",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=12, angle=-0.5)),
    )


def written_month_date() -> Sample:
    items = [Item("Adult ticket", "28.00", "2", "14.00"), Item("Large popcorn", "8.50")]
    subtotal = items_total(items)
    tax = cents(subtotal * d("0.05"))
    total = subtotal + tax
    r = Thermal().center("STARLIGHT CINEMA").center("Screen 4 - 7:30 PM").blank()
    r.text("Sat, Sep 5 2026").rule()
    money_rows(r, items, "$")
    r.rule().row("Subtotal", fmt(subtotal)).row("Tax", fmt(tax)).row("Total", f"${fmt(total)}")
    r.row("Apple Pay (Visa ****0044)", fmt(total))
    return Sample(
        "written_month_date",
        "Date written as 'Sat, Sep 5 2026'; payment via a wallet.",
        expected(
            "Starlight Cinema",
            "2026-09-05",
            "USD",
            items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            payment="Visa ending 0044",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=13, angle=1.8)),
    )


def no_currency_symbol() -> Sample:
    items = [Item("Rye loaf", "6.00"), Item("Cinnamon roll", "3.75"), Item("Baguette", "3.25")]
    total = items_total(items)
    r = Thermal().center("VILLAGE BAKERY").blank().text("10/14/2026").rule()
    money_rows(r, items)
    r.rule().row("TOTAL", fmt(total)).row("CASH", fmt(total))
    return Sample(
        "no_currency_symbol",
        "No currency symbol or code anywhere, so currency must be null, not guessed.",
        expected("Village Bakery", "2026-10-14", None, items, total=total, payment="Cash"),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=14, angle=-1.2)),
    )


def misprinted_total() -> Sample:
    items = [Item("Pad thai", "14.50"), Item("Spring rolls", "6.95"), Item("Thai iced tea", "4.75")]
    subtotal = items_total(items)
    tax = cents(subtotal * d("0.08"))
    printed_total = d("31.37")  # should be 28.30: digits swapped at the till
    r = Thermal().center("SIAM KITCHEN").center("33 Market St").blank()
    r.text("10/07/2026 19:22").rule()
    money_rows(r, items)
    r.rule().row("SUBTOTAL", fmt(subtotal)).row("TAX", fmt(tax))
    r.row("TOTAL", f"${fmt(printed_total)}").row("VISA ****4242", fmt(printed_total))
    return Sample(
        "misprinted_total",
        "The printed total is wrong. It must be copied as printed (not fixed) and get flagged.",
        expected(
            "Siam Kitchen",
            "2026-10-07",
            "USD",
            items,
            subtotal=subtotal,
            tax=tax,
            total=printed_total,
            payment="Visa ending 4242",
        ),
        expect_flagged=True,
        render=lambda: jpeg(photo(r.image(), seed=15, angle=0.6)),
    )


def cash_with_change() -> Sample:
    items = [Item("Carnitas taco", "9.00", "3", "3.00"), Item("Horchata", "4.75")]
    total = items_total(items)
    r = Thermal().center("EL CAMINO TACOS").center("Food truck #7").blank()
    r.text("09/22/2026 12:30").rule()
    money_rows(r, items)
    r.rule().row("TOTAL", f"${fmt(total)}").row("CASH TENDERED", "20.00").row("CHANGE", "6.25")
    return Sample(
        "cash_with_change",
        "Cash payment: the $20.00 tendered and the change are not the total.",
        expected("El Camino Tacos", "2026-09-22", "USD", items, total=total, payment="Cash"),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=16, angle=-2.2)),
    )


def canadian_dollars() -> Sample:
    items = [Item("Maple syrup 500ml", "14.99"), Item("Smoked salmon", "12.49")]
    subtotal = items_total(items)
    tax = cents(subtotal * d("0.13"))
    total = subtotal + tax
    r = Thermal().center("MAPLE MARKET").center("210 Queen St W, Toronto ON").blank()
    r.text("2026-10-05 15:40").rule()
    money_rows(r, items)
    r.rule().row("SUBTOTAL", fmt(subtotal)).row("HST 13%", fmt(tax))
    r.row("TOTAL CAD", f"${fmt(total)}").row("INTERAC DEBIT ****3350", fmt(total))
    return Sample(
        "canadian_dollars",
        "'$' with 'CAD' printed means Canadian dollars, not USD.",
        expected(
            "Maple Market",
            "2026-10-05",
            "CAD",
            items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            payment="Interac ending 3350",
        ),
        expect_flagged=False,
        render=lambda: jpeg(photo(r.image(), seed=17, angle=1.4)),
    )


def no_date() -> Sample:
    items = [Item("Jar of jam", "8.00"), Item("Goat cheese", "7.00")]
    total = items_total(items)
    r = Thermal().center("ROSE HILL FARM").center("Farmers market stall").rule()
    money_rows(r, items, "$")
    r.rule().row("TOTAL", f"${fmt(total)}").row("Paid", "CASH")
    return Sample(
        "no_date",
        "No date printed: the date must be null (and the receipt flagged), not invented.",
        expected("Rose Hill Farm", None, "USD", items, total=total, payment="Cash"),
        expect_flagged=True,
        render=lambda: jpeg(photo(r.image(), seed=18, angle=-0.9)),
    )


# --- Non-thermal formats ---


def utility_bill_pdf() -> Sample:
    items = [Item("Electricity usage 412 kWh", "52.31"), Item("Delivery charge", "8.40")]
    subtotal = items_total(items)
    tax = d("3.65")
    total = subtotal + tax

    def render() -> tuple[bytes, str]:
        page = Image.new("RGB", (1275, 1650), "white")  # US letter at 150 dpi
        draw = ImageDraw.Draw(page)
        title, body, bold = font("sans_bold", 44), font("sans", 26), font("sans_bold", 28)
        draw.text((100, 100), "Brightline Electric", font=title, fill=(10, 60, 120))
        draw.text((100, 165), "PO Box 4410, Springfield", font=body, fill="black")
        draw.text((800, 110), "INVOICE", font=title, fill="black")
        draw.text((800, 175), "Invoice date: September 30, 2026", font=body, fill="black")
        draw.text((800, 210), "Account: 0091-2231", font=body, fill="black")
        draw.text((100, 330), "Billing period: Aug 28 - Sep 27, 2026", font=body, fill="black")
        draw.line((100, 400, 1175, 400), fill="black", width=2)
        draw.text((100, 420), "Description", font=bold, fill="black")
        draw.text((1000, 420), "Amount", font=bold, fill="black")
        y = 480
        rows = [(i.description, i.amount) for i in items]
        rows += [("Subtotal", fmt(subtotal)), ("State utility tax", fmt(tax))]
        for label, amount in rows:
            draw.text((100, y), label, font=body, fill="black")
            draw.text((1000, y), f"${amount}", font=body, fill="black")
            y += 50
        draw.line((100, y + 10, 1175, y + 10), fill="black", width=2)
        draw.text((100, y + 30), "Amount due", font=bold, fill="black")
        draw.text((1000, y + 30), f"${fmt(total)}", font=bold, fill="black")
        draw.text(
            (100, y + 120), "Paid by Autopay - Mastercard ending 5521", font=body, fill="black"
        )
        out = BytesIO()
        page.save(out, "PDF", resolution=150)
        return out.getvalue(), "application/pdf"

    return Sample(
        "utility_bill_pdf",
        "A scanned-style PDF invoice with a different layout from a till receipt.",
        expected(
            "Brightline Electric",
            "2026-09-30",
            "USD",
            items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            payment="Mastercard ending 5521",
        ),
        expect_flagged=False,
        render=render,
        extension="pdf",
    )


def ride_app_screenshot() -> Sample:
    items = [Item("Trip fare", "18.40"), Item("Booking fee", "2.50")]
    subtotal = items_total(items)
    tip = d("4.00")
    total = subtotal + tip

    def render() -> tuple[bytes, str]:
        screen = Image.new("RGB", (750, 1334), (246, 246, 248))  # a phone screenshot
        draw = ImageDraw.Draw(screen)
        big, body, small = font("sans_bold", 46), font("sans", 32), font("sans", 26)
        draw.rectangle((0, 0, 750, 130), fill=(20, 20, 24))
        draw.text((40, 45), "QuickRide", font=big, fill="white")
        draw.text((40, 180), "Thanks for riding, Sam", font=body, fill="black")
        draw.text((40, 230), "Oct 3, 2026 · 9:41 PM", font=small, fill=(90, 90, 96))
        draw.text((40, 320), "Total", font=big, fill="black")
        draw.text((520, 320), f"${fmt(total)}", font=big, fill="black")
        y = 430
        for label, amount in [(i.description, i.amount) for i in items] + [("Tip", fmt(tip))]:
            draw.text((40, y), label, font=body, fill=(50, 50, 56))
            draw.text((560, y), f"${amount}", font=body, fill=(50, 50, 56))
            y += 60
        draw.line((40, y + 10, 710, y + 10), fill=(210, 210, 214), width=2)
        draw.text((40, y + 40), "Payment", font=body, fill="black")
        draw.text((40, y + 90), "Visa •••• 1881", font=small, fill=(90, 90, 96))
        draw.text((40, y + 180), "Pickup: 14 Station Rd", font=small, fill=(90, 90, 96))
        draw.text((40, y + 220), "Drop-off: 300 Lake Ave", font=small, fill=(90, 90, 96))
        return png(screen)

    return Sample(
        "ride_app_screenshot",
        "An app screenshot with the total at the top and a tip but no tax.",
        expected(
            "QuickRide",
            "2026-10-03",
            "USD",
            items,
            tip=tip,
            total=total,
            payment="Visa ending 1881",
        ),
        expect_flagged=False,
        render=render,
        extension="png",
    )


SAMPLES: list[Callable[[], Sample]] = [
    grocery_clean,
    cafe_us_date,
    restaurant_handwritten_tip,
    eu_vat_included,
    uk_pharmacy_gbp,
    discounts,
    quantities_and_weights,
    rotated_photo,
    blurry_low_res,
    faded_thermal,
    shadowed_photo,
    long_receipt,
    written_month_date,
    no_currency_symbol,
    misprinted_total,
    cash_with_change,
    canadian_dollars,
    no_date,
    utility_bill_pdf,
    ride_app_screenshot,
]


def write_samples(directory: Path = SAMPLES_DIR) -> list[dict[str, Any]]:
    directory.mkdir(parents=True, exist_ok=True)
    labels = []
    for make in SAMPLES:
        sample = make()
        data, mime_type = sample.render()
        filename = f"{sample.id}.{sample.extension}"
        (directory / filename).write_bytes(data)
        labels.append(
            {
                "id": sample.id,
                "file": filename,
                "mime_type": mime_type,
                "tests": sample.tests,
                "expect_flagged": sample.expect_flagged,
                "expected": sample.expected.to_json(),
            }
        )
    (directory / "labels.json").write_text(json.dumps(labels, indent=2, ensure_ascii=False) + "\n")
    return labels


if __name__ == "__main__":
    labels = write_samples()
    print(f"Wrote {len(labels)} samples to {SAMPLES_DIR}")
