"""Pure deterministic normalizers for extracted OCR field values."""

from __future__ import annotations

from datetime import date
import json
import re
from typing import Mapping, Optional, Sequence


def normalize_business_registration_number(value: str) -> Optional[str]:
    """Remove permitted separators and require exactly ten digits."""

    normalized = re.sub(r"[-\s]", "", value)
    if re.fullmatch(r"\d{10}", normalized) is None:
        return None
    return normalized


def normalize_corporate_registration_number(value: str) -> Optional[str]:
    """Apply only explicit separator removal to a corporate registration number."""

    normalized = re.sub(r"[-\s]", "", value)
    if re.fullmatch(r"\d+", normalized) is None:
        return None
    return normalized


def normalize_corporation_name(value: str) -> Optional[str]:
    """Canonicalize safe whitespace and the explicitly allowed company marker."""

    normalized = normalize_text(value)
    if normalized is None:
        return None
    return normalized.replace("㈜", "주식회사").replace(" ", "")


def normalize_text(value: str) -> Optional[str]:
    """Collapse whitespace without applying semantic similarity or inference."""

    normalized = " ".join(value.split())
    return normalized or None


def normalize_date(value: str) -> Optional[str]:
    """Accept only a valid ISO ``YYYY-MM-DD`` calendar date."""

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def normalize_amount(value: str) -> Optional[str]:
    """Canonicalize a whole-won amount such as ``500000000원``."""

    match = re.fullmatch(r"\s*(0|[1-9]\d*)\s*원\s*", value)
    if match is None:
        return None
    return match.group(1)


def normalize_ownership_ratio(value: str) -> Optional[str]:
    """Canonicalize an integer ownership percentage in the inclusive 0–100 range."""

    match = re.fullmatch(r"\s*(\d{1,3})\s*%\s*", value)
    if match is None:
        return None
    percentage = int(match.group(1))
    if not 0 <= percentage <= 100:
        return None
    return str(percentage)


def canonicalize_shareholders(
    shareholders: Sequence[Mapping[str, str]],
) -> str:
    """Serialize normalized shareholder records into a stable comparison value."""

    return json.dumps(
        list(shareholders),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
