"""Parsing helpers for sold listing URLs and payload preparation."""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional
from urllib.parse import urlparse


def extract_item_id(url: str) -> Optional[str]:
    """Extract numeric item id from /item/<id>-slug path."""
    path = urlparse(url).path
    match = re.match(r"/item/(\d+)", path)
    return match.group(1) if match else None


def parse_price_value(raw: Any) -> Optional[Decimal]:
    """Parse price from API/scraped formats into Decimal."""
    if raw is None:
        return None

    if isinstance(raw, dict):
        for key in ("amount", "display", "value"):
            if key in raw:
                raw = raw[key]
                break

    if isinstance(raw, (int, float, Decimal)):
        return Decimal(str(raw))

    if not isinstance(raw, str):
        return None

    cleaned = re.sub(r"[^0-9.]", "", raw)
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def apply_discount(price: Decimal, discount_percent: float) -> Decimal:
    """Apply discount percentage and round to cents."""
    factor = Decimal("1") - (Decimal(str(discount_percent)) / Decimal("100"))
    discounted = (price * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if discounted < Decimal("0.01"):
        return Decimal("0.01")
    return discounted


def flatten_specs(specs: dict[str, Any]) -> str:
    """Represent specs as text warnings/reporting detail."""
    if not specs:
        return ""
    return "; ".join(f"{k}: {v}" for k, v in specs.items() if v)
