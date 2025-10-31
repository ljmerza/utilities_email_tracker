"""Parser for City of Raleigh water billing emails."""
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

ACCOUNT_RE = re.compile(r"Account:\s*([0-9\-]+)", re.IGNORECASE)
AMOUNT_DUE_RE = re.compile(r"Amount\s+Due:\s*\$?([0-9,]+(?:\.[0-9]{2})?)", re.IGNORECASE)
DUE_DATE_RE = re.compile(r"Due\s+Date:\s*([A-Za-z0-9.,\-/ ]+)", re.IGNORECASE)
CUSTOMER_RE = re.compile(r"Customer\s+Name:\s*([A-Za-z ,.'-]+)", re.IGNORECASE)
SERVICE_ADDRESS_RE = re.compile(
    r"Service\s+Address:\s*([A-Za-z0-9.,#' \-]+)",
    re.IGNORECASE,
)
FORWARDED_SENDER_RE = re.compile(
    r"From:\s*(?:<)?([^\s>]+@raleighnc\.gov)(?:>)?",
    re.IGNORECASE,
)


def parse_raleigh_water(email: dict[str, Any]) -> dict[str, Any] | None:
    """Extract Raleigh Water billing details from a forwarded email."""
    subject = (email.get(EMAIL_ATTR_SUBJECT) or "").strip()
    body = email.get(EMAIL_ATTR_BODY) or ""

    normalized = _normalize(body)
    combined = f"{subject} {normalized}".lower()

    if "raleigh" not in combined or "utility bill" not in combined:
        return None

    account_number = _search_group(ACCOUNT_RE, normalized)
    amount_display, amount_value = _parse_amount(_search_group(AMOUNT_DUE_RE, normalized))
    due_display = _extract_first_date(_search_group(DUE_DATE_RE, normalized))
    due_iso = _parse_date_iso(due_display)
    customer_name = _search_group(CUSTOMER_RE, normalized)
    service_address = _search_group(SERVICE_ADDRESS_RE, normalized)

    if not any((account_number, amount_display, due_display)):
        return None

    status = _derive_status(due_iso)
    forwarded_address = _extract_forwarded_sender(normalized)

    bill: dict[str, Any] = {
        "id": email.get("message_id") or email.get("uid"),
        "provider": "City of Raleigh Water",
        "subject": subject,
        "received": email.get(EMAIL_ATTR_DATE),
        "amount_due": amount_display,
        "amount_due_value": amount_value,
        "due_date": due_display,
        "due_date_iso": due_iso,
        "status": status,
        "snippet": normalized[:DEFAULT_SNIPPET_LENGTH],
        ATTR_ACCOUNT_NUMBER: account_number,
        ATTR_BILLING_DATE: None,
        ATTR_BILLING_DATE_ISO: None,
    }

    if customer_name:
        bill["customer_name"] = customer_name
    if service_address:
        bill["service_address"] = service_address

    from_address = forwarded_address or email.get(EMAIL_ATTR_ADDRESS)
    from_display = email.get(EMAIL_ATTR_FROM)

    if forwarded_address:
        from_display = "Raleigh Water"

    if from_display:
        bill[EMAIL_ATTR_FROM] = from_display
    if from_address:
        bill[EMAIL_ATTR_ADDRESS] = from_address

    return bill


def _normalize(value: str) -> str:
    """Clean the HTML body into a searchable text block."""
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

    date_match = re.search(
        r"(?:\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
        r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
        r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+\d{4})"
        r"|(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        value,
        re.IGNORECASE,
    )
    if date_match:
        return date_match.group(0).strip()
    return value.strip() or None


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


def _extract_forwarded_sender(text: str) -> str | None:
    match = FORWARDED_SENDER_RE.search(text)
    if match:
        return match.group(1).strip()
    return None
