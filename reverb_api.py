"""Reverb API client wrappers with retry and safe fallbacks."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests

from utils import retry_with_backoff

API_BASE = "https://api.reverb.com/api"

CONDITION_FALLBACK = {
    "mint": "ac5b9c1e-dc78-466d-b0b3-7cf712967a48",
    "excellent": "df268ad1-c462-4ba6-b6db-e007e23922ea",
    "very good": "ae4d9114-1bd7-4ec5-a4ba-6653af5ac84d",
    "good": "f7a3f48c-972a-44c6-b01a-0cd27488d3f6",
    "fair": "98777886-76d0-44c8-865e-bb40e669e934",
    "poor": "6a9dfcad-600b-46c8-9e08-ce6e5057921e",
    "brand new": "7c3f45de-2ae0-4c81-8400-fdb6b1d74890",
}


class ReverbAPIClient:
    """Thin API client focused on auth checks and draft listing creation."""

    def __init__(self, api_key: str, logger: Optional[logging.Logger] = None):
        self.api_key = api_key
        self.logger = logger or logging.getLogger(__name__)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept-Version": "3.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        url = f"{API_BASE}{endpoint}"
        kwargs.setdefault("headers", self.headers)
        kwargs.setdefault("timeout", 45)
        resp = requests.request(method, url, **kwargs)

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "2"))
            time.sleep(max(retry_after, 1))
            raise requests.HTTPError("Rate limited by Reverb API")

        return resp

    def test_api_key(self) -> tuple[bool, str]:
        """Validate key with a lightweight authenticated endpoint."""
        try:
            resp = retry_with_backoff(
                self._request,
                "GET",
                "/shop",
                retry_on=(requests.HTTPError, requests.ConnectionError, requests.Timeout),
                max_attempts=4,
            )
        except Exception as exc:
            return False, f"Connection error: {exc}"

        if resp.status_code == 200:
            shop = resp.json().get("name", "shop")
            return True, f"API key valid. Connected to: {shop}"
        if resp.status_code in {401, 403}:
            return False, "Unauthorized. Check API key permissions."
        return False, f"API test failed ({resp.status_code}): {resp.text[:300]}"

    def get_listing_details(self, item_id: str) -> tuple[bool, dict[str, Any], str]:
        """Fetch listing details for an item id. Useful fallback when HTML scraping is blocked."""
        try:
            resp = retry_with_backoff(
                self._request,
                "GET",
                f"/listings/{item_id}",
                retry_on=(requests.HTTPError, requests.ConnectionError, requests.Timeout),
                max_attempts=3,
            )
        except Exception as exc:
            return False, {}, f"Listing lookup failed: {exc}"

        if resp.status_code == 200:
            return True, resp.json(), ""
        return False, {}, f"Listing lookup failed ({resp.status_code}): {resp.text[:300]}"

    def _extract_listing_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(payload.get("listings"), list):
            return payload["listings"]
        embedded = payload.get("_embedded", {})
        if isinstance(embedded, dict) and isinstance(embedded.get("listings"), list):
            return embedded["listings"]
        if isinstance(payload.get("data"), list):
            return payload["data"]
        return []

    def get_my_drafts(self, per_page: int = 50) -> tuple[bool, list[dict[str, Any]], str]:
        """Best-effort fetch for account draft listings."""
        endpoints = [
            f"/my/listings?state=draft&per_page={per_page}",
            f"/my/listings?status=draft&per_page={per_page}",
            f"/listings/my?state=draft&per_page={per_page}",
        ]
        last_error = ""
        for endpoint in endpoints:
            resp = self._request("GET", endpoint)
            if resp.status_code == 200:
                rows = self._extract_listing_rows(resp.json())
                return True, rows, ""
            last_error = f"{endpoint} -> {resp.status_code}: {resp.text[:180]}"
        return False, [], f"Unable to fetch drafts. {last_error}"

    def publish_draft(self, listing_id: str) -> tuple[bool, str]:
        """Best-effort publish call for an existing draft listing."""
        endpoints = [
            f"/listings/{listing_id}/publish",
            f"/my/listings/{listing_id}/publish",
        ]
        last_error = ""
        for endpoint in endpoints:
            resp = self._request("POST", endpoint)
            if resp.status_code in {200, 201}:
                return True, f"Draft {listing_id} published."
            last_error = f"{endpoint} -> {resp.status_code}: {resp.text[:200]}"
        return False, f"Publish failed for draft {listing_id}. {last_error}"

    def create_draft(self, payload: dict[str, Any]) -> tuple[bool, dict[str, Any], str]:
        """Create draft listing. If image urls fail, retry without photos."""
        resp = self._request("POST", "/listings", json=payload)
        if resp.status_code in {200, 201}:
            return True, resp.json(), ""

        if payload.get("photos"):
            stripped = {k: v for k, v in payload.items() if k != "photos"}
            resp2 = self._request("POST", "/listings", json=stripped)
            if resp2.status_code in {200, 201}:
                msg = "Draft created without photos (photo upload endpoint/format constraints)."
                return True, resp2.json(), msg

        return False, {}, f"{resp.status_code}: {resp.text[:500]}"


def condition_to_uuid(condition_text: str) -> str:
    """Map condition text to known Reverb UUID with safe default."""
    if not condition_text:
        return CONDITION_FALLBACK["excellent"]
    normalized = condition_text.lower().replace("condition", "").strip()
    return CONDITION_FALLBACK.get(normalized, CONDITION_FALLBACK["excellent"])
