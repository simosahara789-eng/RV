"""Sold listing extraction via public Reverb page and APIs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import requests
try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - fallback when dependency missing in constrained env
    BeautifulSoup = None

from parser import extract_item_id, parse_price_value
from utils import retry_with_backoff

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class ExtractedListing:
    source_url: str
    title: str = ""
    description: str = ""
    price_amount: str = ""
    price_currency: str = "USD"
    brand: str = ""
    model: str = ""
    finish: str = ""
    year: str = ""
    condition: str = "Excellent"
    category: str = ""
    category_uuid: str = ""
    images: list[str] = field(default_factory=list)
    specs: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _fetch(url: str, timeout: int = 30) -> requests.Response:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/json"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    # lightweight rate-limit handling
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", "2"))
        raise requests.HTTPError(f"429 Too Many Requests. Retry-After={retry_after}")
    resp.raise_for_status()
    return resp


def _extract_json_ld(soup) -> dict[str, Any]:
    for script in soup.select("script[type='application/ld+json']"):
        try:
            payload = json.loads(script.text.strip())
        except Exception:
            continue
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get("@type") in {"Product", "Offer"}:
                    return item
        if isinstance(payload, dict) and payload.get("@type") in {"Product", "Offer"}:
            return payload
    return {}


def extract_listing_data(url: str) -> ExtractedListing:
    """Extract listing data from page HTML with best-effort parsing."""
    result = ExtractedListing(source_url=url)

    resp = retry_with_backoff(_fetch, url, retry_on=(Exception,), max_attempts=3)
    html = resp.text
    if BeautifulSoup:
        soup = BeautifulSoup(html, "html.parser")

        title = soup.select_one("meta[property='og:title']")
        if title and title.get("content"):
            result.title = title["content"]

        description = soup.select_one("meta[property='og:description']")
        if description and description.get("content"):
            result.description = description["content"]

        image_tags = soup.select("meta[property='og:image']")
        result.images = [tag.get("content") for tag in image_tags if tag.get("content")]

        json_ld = _extract_json_ld(soup)
    else:
        # Fallback lightweight extraction when BeautifulSoup is unavailable.
        def _meta(prop: str) -> str:
            import re
            m = re.search(rf'<meta[^>]+property=["\']{prop}["\'][^>]+content=["\']([^"\']+)["\']', html)
            return m.group(1) if m else ""

        result.title = _meta("og:title")
        result.description = _meta("og:description")
        first_image = _meta("og:image")
        if first_image:
            result.images = [first_image]
        json_ld = {}
    if json_ld:
        result.title = json_ld.get("name", result.title)
        result.description = json_ld.get("description", result.description)
        brand = json_ld.get("brand")
        if isinstance(brand, dict):
            result.brand = brand.get("name", "")
        elif isinstance(brand, str):
            result.brand = brand

        offers = json_ld.get("offers") if isinstance(json_ld.get("offers"), dict) else json_ld
        if offers:
            amount = parse_price_value(offers.get("price"))
            if amount is not None:
                result.price_amount = str(amount)
            result.price_currency = offers.get("priceCurrency", result.price_currency)
            result.condition = offers.get("itemCondition", result.condition).split("/")[-1] if offers.get("itemCondition") else result.condition

        category = json_ld.get("category")
        if category:
            result.category = category

    # Extract common details in page feature list.
    if BeautifulSoup:
        for row in soup.select("li, div"):
            text = row.get_text(" ", strip=True)
            if text.lower().startswith("model:") and not result.model:
                result.model = text.split(":", 1)[-1].strip()
            elif text.lower().startswith("finish:") and not result.finish:
                result.finish = text.split(":", 1)[-1].strip()
            elif text.lower().startswith("year:") and not result.year:
                result.year = text.split(":", 1)[-1].strip()

    # Fallback item id for later API enrichment.
    item_id = extract_item_id(url)
    result.specs["item_id"] = item_id or ""

    if not result.price_amount:
        result.warnings.append("Sold price not confidently extracted from page metadata.")
    if not result.images:
        result.warnings.append("No images discovered in page metadata.")
    if not result.brand:
        result.warnings.append("Brand not found; may need manual edit in draft.")

    return result
