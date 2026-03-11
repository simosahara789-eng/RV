"""Utility helpers for validation, sanitization, retry, and reporting."""

from __future__ import annotations

import io
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional
from urllib.parse import urlparse

import pandas as pd

LOGGER_NAME = "reverb_bulk_draft"


def setup_logging() -> logging.Logger:
    """Configure app-wide logging once and return logger."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def sanitize_text(
    value: str,
    remove_special: bool = False,
    trim_length: Optional[int] = None,
) -> str:
    """Sanitize text optionally removing unusual chars and trimming length."""
    if not value:
        return ""

    text = value.strip()
    if remove_special:
        # Keep printable text and standard punctuation; remove most emoji/symbol blocks.
        text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
        text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\u024F]", "", text)

    text = re.sub(r"\s+", " ", text).strip()
    if trim_length and trim_length > 0:
        text = text[:trim_length].strip()
    return text


def parse_bulk_urls(text: str) -> list[str]:
    """Parse URL textarea content and preserve order while de-duplicating."""
    seen: set[str] = set()
    valid_urls: list[str] = []
    for raw in text.splitlines():
        url = raw.strip()
        if not url:
            continue
        normalized = normalize_reverb_url(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            valid_urls.append(normalized)
    return valid_urls


def normalize_reverb_url(url: str) -> Optional[str]:
    """Validate and normalize Reverb item URL."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    if parsed.scheme not in {"http", "https"}:
        return None
    if "reverb.com" not in parsed.netloc.lower():
        return None
    if not parsed.path.startswith("/item/"):
        return None

    return f"https://reverb.com{parsed.path}".rstrip("/")


def retry_with_backoff(
    fn: Callable,
    *args,
    max_attempts: int = 4,
    initial_delay: float = 1.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
    **kwargs,
):
    """Retry wrapper with exponential backoff for temporary failures."""
    last_exc = None
    delay = initial_delay
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except retry_on as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt == max_attempts:
                break
            time.sleep(delay)
            delay *= 2
    if last_exc:
        raise last_exc
    raise RuntimeError("Retry failed without exception")


@dataclass
class ResultRow:
    """Single processed record for report output."""

    source_url: str
    status: str
    title: str = ""
    sold_price: str = ""
    discounted_price: str = ""
    action: str = ""
    error: str = ""
    warnings: str = ""


def results_to_dataframe(rows: Iterable[ResultRow]) -> pd.DataFrame:
    """Convert result rows to dataframe suitable for UI and CSV."""
    return pd.DataFrame([r.__dict__ for r in rows])


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Encode dataframe as UTF-8 CSV bytes for download."""
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")
