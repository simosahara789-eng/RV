"""Sold listing extraction via public Reverb page + API fallback."""

from __future__ import annotations

import importlib.util
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

from parser import extract_item_id, parse_price_value
from utils import retry_with_backoff

if importlib.util.find_spec("bs4") is not None:
    from bs4 import BeautifulSoup  # type: ignore
else:
    BeautifulSoup = None

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


def _fetch_html(url: str, timeout: int = 30) -> requests.Response:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/json"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", "2"))
        raise requests.HTTPError(f"429 Too Many Requests. Retry-After={retry_after}")
    if resp.status_code == 403:
        raise requests.HTTPError("403 Forbidden from sold page")
    resp.raise_for_status()
    return resp


def _extract_json_ld_from_soup(soup: Any) -> dict[str, Any]:
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


def _extract_json_ld_from_html(html: str) -> dict[str, Any]:
    for raw in re.findall(r"<script[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>", html, flags=re.DOTALL):
        try:
            payload = json.loads(raw.strip())
        except Exception:
            continue
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get("@type") in {"Product", "Offer"}:
                    return item
        if isinstance(payload, dict) and payload.get("@type") in {"Product", "Offer"}:
            return payload
    return {}


def _extract_meta(html: str, prop: str) -> str:
    m = re.search(rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']', html)
    return m.group(1).strip() if m else ""


def _hydrate_from_api(result: ExtractedListing, listing: dict[str, Any]) -> None:
    result.title = listing.get("title", result.title)
    result.description = listing.get("description", result.description)

    price_obj = listing.get("price", {}) if isinstance(listing.get("price"), dict) else {}
    amount = parse_price_value(price_obj.get("amount") or price_obj.get("display") or listing.get("sold_price"))
    if amount is not None:
        result.price_amount = str(amount)
    result.price_currency = price_obj.get("currency", result.price_currency)

    make = listing.get("make", {})
    result.brand = make.get("name", "") if isinstance(make, dict) else str(make or "")

    model = listing.get("model", {})
    result.model = model.get("name", "") if isinstance(model, dict) else str(model or "")

    condition = listing.get("condition", {})
    if isinstance(condition, dict):
        result.condition = condition.get("display_name", result.condition)

    category = listing.get("category", {})
    if isinstance(category, dict):
        result.category = category.get("full_name", result.category)
        result.category_uuid = category.get("uuid", "")

    photos = listing.get("photos", [])
    if isinstance(photos, list):
        photo_urls: list[str] = []
        for p in photos:
            if isinstance(p, dict):
                if p.get("_links", {}).get("full", {}).get("href"):
                    photo_urls.append(p["_links"]["full"]["href"])
                elif p.get("image_url"):
                    photo_urls.append(p["image_url"])
        if photo_urls:
            result.images = photo_urls

    for key in ("finish", "year", "handedness", "country_of_origin"):
        if listing.get(key):
            result.specs[key] = listing.get(key)


def extract_listing_data(url: str, api_client: Optional[Any] = None) -> ExtractedListing:
    """Extract listing data from HTML. On 403/blocking, fallback to Reverb API listing lookup."""
    result = ExtractedListing(source_url=url)
    item_id = extract_item_id(url)
    result.specs["item_id"] = item_id or ""

    html_error: Optional[str] = None
    try:
        resp = retry_with_backoff(_fetch_html, url, retry_on=(Exception,), max_attempts=3)
        html = resp.text

        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            title = soup.select_one("meta[property='og:title']")
            if title and title.get("content"):
                result.title = title["content"]

            description = soup.select_one("meta[property='og:description']")
            if description and description.get("content"):
                result.description = description["content"]

            image_tags = soup.select("meta[property='og:image']")
            result.images = [tag.get("content") for tag in image_tags if tag.get("content")]
            json_ld = _extract_json_ld_from_soup(soup)
        else:
            result.title = _extract_meta(html, "og:title")
            result.description = _extract_meta(html, "og:description")
            img = _extract_meta(html, "og:image")
            if img:
                result.images = [img]
            json_ld = _extract_json_ld_from_html(html)
            result.warnings.append("BeautifulSoup not installed; using lightweight HTML parser.")

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
                if offers.get("itemCondition"):
                    result.condition = str(offers.get("itemCondition")).split("/")[-1]

            category = json_ld.get("category")
            if category:
                result.category = category
    except Exception as exc:
        html_error = str(exc)

    if (not result.price_amount or not result.title) and api_client and item_id:
        ok, listing, err = api_client.get_listing_details(item_id)
        if ok:
            _hydrate_from_api(result, listing)
            result.warnings.append("HTML extraction blocked/incomplete; used Reverb API fallback.")
        else:
            result.warnings.append(f"API fallback failed: {err}")

    if html_error:
        result.warnings.append(f"HTML extraction issue: {html_error}")
    if not result.price_amount:
        result.warnings.append("Sold price not confidently extracted.")
    if not result.images:
        result.warnings.append("No images discovered.")
    if not result.brand:
        result.warnings.append("Brand not found; may need manual draft edits.")

    return result
