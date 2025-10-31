"""Parser for Duke Energy billing emails."""
from __future__ import annotations

from datetime import datetime
from html import unescape
import quopri
import re
from typing import Any

from ..const import (
    ATTR_ACCOUNT_NUMBER,
    ATTR_BILLING_DATE,
    ATTR_BILLING_DATE_ISO,
    DEFAULT_SNIPPET_LENGTH,
    EMAIL_ATTR_BODY,
    EMAIL_ATTR_DATE,
    EMAIL_ATTR_FROM,
    EMAIL_ATTR_ADDRESS,
    EMAIL_ATTR_SUBJECT,
)

ACCOUNT_RE = re.compile(r"Account\s+Number:\s*([0-9\-]+)", re.IGNORECASE)
BILLING_DATE_RE = re.compile(r"Billing\s+Date:\s*([A-Za-z0-9.,\-/ ]+)", re.IGNORECASE)
DUE_DATE_RE = re.compile(r"Due\s+Date:\s*([A-Za-z0-9.,\-/ ]+)", re.IGNORECASE)
AMOUNT_DUE_RE = re.compile(r"Amount\s+Due:\s*\$?([0-9,]+(?:\.[0-9]{2})?)", re.IGNORECASE)
MONTH_NAME_PATTERN = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
DATE_FINDER_RE = re.compile(
    rf"({MONTH_NAME_PATTERN}\.?\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}})",
    re.IGNORECASE,
)


def parse_duke_energy(email: dict[str, Any]) -> dict[str, Any] | None:
    """Extract Duke Energy billing details from an email."""
    subject = (email.get(EMAIL_ATTR_SUBJECT) or "").strip()
    body = email.get(EMAIL_ATTR_BODY) or ""

    normalized = _normalize(body)
    combined = f"{subject} {normalized}".lower()

    if "duke energy" not in combined:
        return None

    account_number = _search_group(ACCOUNT_RE, normalized)
    amount_display, amount_value = _parse_amount(_search_group(AMOUNT_DUE_RE, normalized))
    billing_display = _extract_first_date(_search_group(BILLING_DATE_RE, normalized))
    billing_iso = _parse_date_iso(billing_display)
    due_display = _extract_first_date(_search_group(DUE_DATE_RE, normalized))
    due_iso = _parse_date_iso(due_display)

    if not any((account_number, amount_display, due_display, billing_display)):
        return None

    status = _derive_status(due_iso)

    snippet_source = normalized[:DEFAULT_SNIPPET_LENGTH]

    bill = {
        "id": email.get("message_id") or email.get("uid"),
        "provider": "Duke Energy",
        "subject": subject,
        "received": email.get(EMAIL_ATTR_DATE),
        "amount_due": amount_display,
        "amount_due_value": amount_value,
        "due_date": due_display,
        "due_date_iso": due_iso,
        "status": status,
        "snippet": snippet_source,
        "from_address": email.get(EMAIL_ATTR_ADDRESS),
        ATTR_ACCOUNT_NUMBER: account_number,
        ATTR_BILLING_DATE: billing_display,
        ATTR_BILLING_DATE_ISO: billing_iso,
    }

    from_display = email.get(EMAIL_ATTR_FROM)
    if from_display:
        bill[EMAIL_ATTR_FROM] = from_display

    return bill


def _normalize(value: str) -> str:
    """Clean the HTML body down to a searchable text block."""
    if not value:
        return ""

    text = value
    try:
        decoded = quopri.decodestring(text)
        if isinstance(decoded, bytes):
            text = decoded.decode("utf-8", "ignore")
        else:
            text = decoded
    except Exception:
        if not isinstance(text, str):
            text = text.decode("utf-8", "ignore")

    text = unescape(text)
    text = re.sub(r"</?(tr|p|div|li|table|tbody|thead|section|article)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(td|th)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _search_group(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if match:
        value = match.group(1).strip()
        return value or None
    return None


def _parse_amount(value: str | None) -> tuple[str | None, float | None]:
    if not value:
        return None, None

    normalized = value.replace(",", "")
    try:
        amount = float(normalized)
    except ValueError:
        amount = None

    display = value
    if not display.startswith("$"):
        display = f"${display}"

    return display, amount


def _parse_date_iso(value: str | None) -> str | None:
    if not value:
        return None

    cleaned = (
        value.replace("\n", " ")
        .replace("\r", " ")
        .replace("\xa0", " ")
        .replace(".", "")
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    for fmt in (
        "%B %d, %Y",
        "%b %d, %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
    ):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _extract_first_date(value: str | None) -> str | None:
    if not value:
        return None

    match = DATE_FINDER_RE.search(value)
    if match:
        return match.group(1).strip()

    cleaned = value.strip()
    return cleaned or None


def _derive_status(due_iso: str | None) -> str:
    if not due_iso:
        return "due"

    try:
        due_date = datetime.fromisoformat(due_iso).date()
    except ValueError:
        return "due"

    today = datetime.utcnow().date()
    if due_date < today:
        return "overdue"
    return "due"
