"""Demo accounts: "Try demo" creates a private account filled with two months of fake receipts.

Every visitor gets their own account, so they can upload, recategorize, and dismiss flags
without affecting anyone else. Accounts expire after DEMO_TTL_HOURS and are deleted.

All vendors, items, and amounts are invented. Each receipt goes through the real validation,
duplicate, and anomaly checks, so the demo's flags come from the actual code.
"""

import hashlib
import random
import secrets
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.anomalies import find_anomaly_flags
from app.auth import new_inbound_token
from app.config import get_settings
from app.duplicates import find_duplicate_flags
from app.extraction import ExtractedLineItem, ExtractedReceipt
from app.models import Category, CategorySource, Receipt, User
from app.receipt_service import apply_extraction
from app.storage import FileStorage
from app.vendors import normalize_vendor

DEMO_DAYS = 60
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Vendor:
    name: str
    category: Category
    reason: str
    items: list[tuple[str, float, float]]  # (description, lowest price, highest price)
    item_count: tuple[int, int] = (1, 1)
    tax_rate: Decimal = Decimal("0")
    tip_rate: Decimal | None = None


VENDORS = {
    v.name: v
    for v in [
        Vendor(
            "Corner Cafe",
            Category.DINING,
            "Coffee and pastries from a café.",
            [
                ("Latte", 4.25, 5.25),
                ("Cappuccino", 4.0, 5.0),
                ("Croissant", 3.25, 4.0),
                ("Bagel", 3.0, 4.5),
                ("Iced tea", 3.0, 3.75),
            ],
            (1, 3),
            Decimal("0.08"),
        ),
        Vendor(
            "Noodle House",
            Category.DINING,
            "A restaurant meal.",
            # Each visit is one or two main dishes (eating alone or with a friend).
            [("Pad thai", 13.0, 16.0), ("Ramen", 14.0, 17.0), ("Green curry", 13.0, 16.0)],
            (1, 2),
            Decimal("0.08"),
            Decimal("0.18"),
        ),
        Vendor(
            "Lakeside Grill",
            Category.DINING,
            "A sit-down restaurant meal.",
            [
                ("Grilled salmon", 24.0, 29.0),
                ("Steak frites", 28.0, 34.0),
                ("Caesar salad", 11.0, 14.0),
                ("Lemonade", 4.0, 5.0),
            ],
            (2, 3),
            Decimal("0.08"),
            Decimal("0.18"),
        ),
        Vendor(
            "Fresh Mart",
            Category.GROCERIES,
            "Groceries from a supermarket.",
            [
                ("Milk", 3.5, 4.5),
                ("Bread", 3.0, 5.0),
                ("Eggs (dozen)", 3.5, 5.0),
                ("Chicken breast", 9.0, 14.0),
                ("Rice", 4.0, 8.0),
                ("Vegetables", 6.0, 15.0),
                ("Fruit", 5.0, 12.0),
                ("Coffee beans", 11.0, 15.0),
                ("Pasta", 1.5, 3.0),
                ("Yogurt", 4.0, 6.0),
            ],
            (4, 8),
        ),
        Vendor(
            "Green Basket Co-op",
            Category.GROCERIES,
            "Groceries from a food co-op.",
            [
                ("Organic spinach", 3.5, 5.0),
                ("Tofu", 2.5, 4.0),
                ("Oat milk", 4.0, 5.5),
                ("Lentils", 2.0, 3.5),
                ("Apples", 4.0, 7.0),
            ],
            (3, 5),
        ),
        Vendor(
            "QuickRide",
            Category.TRANSPORTATION,
            "A rideshare trip.",
            [("Ride", 9.0, 24.0)],
            tip_rate=Decimal("0.15"),
        ),
        Vendor(
            "City Transit",
            Category.TRANSPORTATION,
            "A public transit pass.",
            [("Monthly student pass", 25.0, 25.0)],
        ),
        Vendor(
            "Streamly",
            Category.SUBSCRIPTIONS,
            "A streaming subscription.",
            [("Monthly plan", 15.99, 15.99)],
        ),
        Vendor(
            "CloudBox Storage",
            Category.SUBSCRIPTIONS,
            "A cloud storage subscription.",
            [("200 GB plan", 2.99, 2.99)],
        ),
        Vendor(
            "Brightline Electric",
            Category.UTILITIES,
            "An electricity bill.",
            [("Electricity", 58.0, 84.0)],
        ),
        Vendor(
            "FiberNet", Category.UTILITIES, "An internet bill.", [("Home internet", 55.0, 55.0)]
        ),
        Vendor(
            "Pine Pharmacy",
            Category.HEALTH,
            "Pharmacy items.",
            [("Allergy tablets", 8.0, 14.0), ("Vitamins", 9.0, 16.0), ("Bandages", 4.0, 6.0)],
            (1, 2),
            Decimal("0.08"),
        ),
        Vendor(
            "Bookhaven",
            Category.EDUCATION,
            "A textbook purchase.",
            [("Statistics textbook", 64.0, 89.0), ("Notebooks (3-pack)", 7.0, 9.0)],
            (1, 2),
            Decimal("0.08"),
        ),
        Vendor(
            "HomeGoods Depot",
            Category.SHOPPING,
            "Household goods.",
            [("Desk lamp", 18.0, 32.0), ("Storage bins", 12.0, 20.0), ("Towels", 15.0, 25.0)],
            (1, 2),
            Decimal("0.08"),
        ),
        Vendor(
            "Starlight Cinema",
            Category.ENTERTAINMENT,
            "Movie tickets.",
            [("Movie ticket", 12.0, 15.0), ("Popcorn", 6.0, 8.0)],
            (1, 3),
            Decimal("0.08"),
        ),
    ]
}

PAYMENT_METHODS = ["Visa ending 4242", "Mastercard ending 5454", "Cash", "Debit ending 1881"]


@dataclass
class PlannedReceipt:
    day: date
    vendor: Vendor
    # Tweaks that make a receipt trip one of the checks, to show each kind of flag.
    total_offset: Decimal = Decimal("0")  # printed total is off -> "total_mismatch"
    tip_rate: Decimal | None = None  # overrides the vendor's usual tip
    items: list[tuple[str, float, float]] | None = None  # replaces the vendor's usual items
    copy_of: "PlannedReceipt | None" = None  # same purchase uploaded twice
    extracted: ExtractedReceipt | None = field(default=None, repr=False)


def plan_receipts(today: date, rng: random.Random) -> list[PlannedReceipt]:
    """When each fake purchase happens over the last DEMO_DAYS days."""
    start = today - timedelta(days=DEMO_DAYS)
    plan: list[PlannedReceipt] = []

    def every(vendor: str, min_gap: int, max_gap: int) -> None:
        day = start + timedelta(days=rng.randint(0, min_gap))
        while day <= today:
            plan.append(PlannedReceipt(day, VENDORS[vendor]))
            day += timedelta(days=rng.randint(min_gap, max_gap))

    every("Corner Cafe", 2, 4)
    every("Fresh Mart", 6, 8)
    every("Green Basket Co-op", 12, 16)
    every("Noodle House", 8, 12)
    every("QuickRide", 6, 10)

    def monthly(vendor: str, day_of_month: int) -> None:
        month = date(start.year, start.month, 1)
        while month <= today:
            day = month.replace(day=day_of_month)
            if start <= day <= today:
                plan.append(PlannedReceipt(day, VENDORS[vendor]))
            month = (month + timedelta(days=32)).replace(day=1)

    monthly("City Transit", 1)
    monthly("Brightline Electric", 5)
    monthly("FiberNet", 8)
    monthly("Streamly", 12)
    monthly("CloudBox Storage", 20)

    for vendor, days_ago in [
        ("Pine Pharmacy", 41),
        ("Pine Pharmacy", 9),
        ("Bookhaven", 52),
        ("HomeGoods Depot", 33),
        ("HomeGoods Depot", 12),
        ("Starlight Cinema", 26),
        ("Starlight Cinema", 4),
    ]:
        plan.append(PlannedReceipt(today - timedelta(days=days_ago), VENDORS[vendor]))

    # One of each kind of flag, late enough that there's history to compare against.
    plan.append(
        PlannedReceipt(
            today - timedelta(days=20), VENDORS["Noodle House"], total_offset=Decimal("2.00")
        )
    )
    plan.append(
        PlannedReceipt(
            today - timedelta(days=6),
            VENDORS["Lakeside Grill"],
            items=[("Group dinner for 6", 210.0, 240.0)],
        )
    )
    plan.append(
        PlannedReceipt(today - timedelta(days=3), VENDORS["QuickRide"], tip_rate=Decimal("0.45"))
    )
    grocery_runs = [p for p in plan if p.vendor.name == "Fresh Mart" and p.day < today]
    original = grocery_runs[-1]
    plan.append(PlannedReceipt(original.day, original.vendor, copy_of=original))

    return sorted(plan, key=lambda p: p.day)


def build_extraction(planned: PlannedReceipt, rng: random.Random) -> ExtractedReceipt:
    """What extraction would have returned for this fake receipt."""
    if planned.copy_of is not None:
        return planned.copy_of.extracted  # identical content, uploaded a second time

    vendor = planned.vendor
    count = min(rng.randint(*vendor.item_count), len(vendor.items))
    choices = planned.items or rng.sample(vendor.items, count)
    items = []
    for description, low, high in choices:
        price = Decimal(str(rng.uniform(low, high))).quantize(CENT)
        items.append(
            ExtractedLineItem(
                description=description, quantity=1, unit_price=float(price), amount=float(price)
            )
        )
    subtotal = sum((Decimal(str(i.amount)) for i in items), Decimal("0"))
    tax = (subtotal * vendor.tax_rate).quantize(CENT)
    tip_rate = planned.tip_rate if planned.tip_rate is not None else vendor.tip_rate
    tip = (subtotal * tip_rate).quantize(CENT) if tip_rate else None
    total = subtotal + tax + (tip or 0) + planned.total_offset
    return ExtractedReceipt(
        vendor=vendor.name,
        purchase_date=planned.day.isoformat(),
        currency="USD",
        line_items=items,
        subtotal=float(subtotal),
        tax=float(tax) if vendor.tax_rate else None,
        tip=float(tip) if tip is not None else None,
        total=float(total),
        payment_method=rng.choice(PAYMENT_METHODS),
    )


def render_receipt_text(extracted: ExtractedReceipt) -> str:
    """A plain-text version of the receipt, shown as the "original file" in the app."""
    lines = [extracted.vendor or "", f"Date: {extracted.purchase_date}", ""]
    lines += [f"{item.description:<28}{item.amount:>8.2f}" for item in extracted.line_items]
    lines.append("")
    for label, value in [
        ("Subtotal", extracted.subtotal),
        ("Tax", extracted.tax),
        ("Tip", extracted.tip),
        ("TOTAL", extracted.total),
    ]:
        if value is not None:
            lines.append(f"{label:<28}{value:>8.2f}")
    lines += ["", f"Paid with {extracted.payment_method}", "(Demo receipt: all details are fake)"]
    return "\n".join(lines) + "\n"


def seed_demo_receipts(db: Session, storage: FileStorage, user: User, today: date) -> int:
    # Seeded by date, so every demo account made on the same day looks the same.
    rng = random.Random(f"demo-{today}")
    plan = plan_receipts(today, rng)
    for planned in plan:
        extracted = build_extraction(planned, rng)
        planned.extracted = extracted
        text = render_receipt_text(extracted).encode()
        # The duplicate is a separate copy (e.g. a photo and the emailed version of one
        # purchase), so it has its own file and is caught by the "same purchase" check.
        if planned.copy_of is not None:
            text += b"(copy)\n"

        receipt = Receipt(
            user_id=user.id,
            original_filename=f"{normalize_vendor(planned.vendor.name)} {planned.day}.txt",
            content_type="text/plain",
            file_key=f"receipts/demo/{uuid4().hex}.txt",
            file_sha256=hashlib.sha256(text).hexdigest(),
        )
        storage.save(receipt.file_key, text, "text/plain")
        apply_extraction(receipt, extracted, today=today)  # adds any validation flags
        receipt.category = planned.vendor.category
        receipt.category_source = CategorySource.LLM
        receipt.category_reason = planned.vendor.reason
        db.add(receipt)
        db.flush()
        receipt.flags.extend(find_duplicate_flags(db, receipt))
        receipt.flags.extend(find_anomaly_flags(db, receipt))
    return len(plan)


def delete_expired_demo_accounts(db: Session, storage: FileStorage, now: datetime) -> int:
    cutoff = now - timedelta(hours=get_settings().demo_ttl_hours)
    expired = db.scalars(select(User).where(User.is_demo, User.created_at < cutoff)).all()
    for user in expired:
        for file_key in db.scalars(select(Receipt.file_key).where(Receipt.user_id == user.id)):
            storage.delete(file_key)
        db.delete(user)  # receipts, flags, and line items are deleted with it
    return len(expired)


def create_demo_account(db: Session, storage: FileStorage, today: date | None = None) -> User:
    delete_expired_demo_accounts(db, storage, datetime.now(UTC))
    user = User(
        # ".invalid" is reserved and can never be a real address.
        email=f"demo-{secrets.token_hex(6)}@demo.invalid",
        password_hash="!",  # matches no password; demo accounts are entered via "Try demo"
        inbound_token=new_inbound_token(),
        is_demo=True,
    )
    db.add(user)
    db.flush()
    seed_demo_receipts(db, storage, user, today or date.today())
    db.commit()
    return user
