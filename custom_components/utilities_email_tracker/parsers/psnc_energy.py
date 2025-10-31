"""Parser for PSNC Energy / Dominion Energy gas billing emails."""
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

ACCOUNT_RE = re.compile(r"Account\s+Ending\s+In:\s*([A-Za-z0-9*]+)", re.IGNORECASE)
AMOUNT_DRAFT_RE = re.compile(
    r"Amount\s+to\s+Be\s+Drafted:\s*\$?([0-9,]+(?:\.[0-9]{2})?)",
    re.IGNORECASE,
)
BANK_DRAFT_DATE_RE = re.compile(
    r"Date\s+of\s+Bank\s+Draft:\s*([A-Za-z0-9.,\-/ ]+)",
    re.IGNORECASE,
)
SERVICE_ADDRESS_RE = re.compile(
    r"Service\s+Address:\s*([A-Za-z0-9.,#*\- ]+)", re.IGNORECASE
)

IDENTIFIERS = (
    "psnc energy",
    "messages.psncenergy.com",
    "dominion energy",
    "enbridge gas",
    "dominionenergync.com",
)


def parse_psnc_energy(email: dict[str, Any]) -> dict[str, Any] | None:
    """Parse PSNC Energy billing notification."""
    subject = (email.get(EMAIL_ATTR_SUBJECT) or "").strip()
    body = email.get(EMAIL_ATTR_BODY) or ""

    normalized = _normalize(body)
    combined = f"{subject} {normalized}".lower()

    if not any(identifier in combined for identifier in IDENTIFIERS):
        return None

    account_raw = _search_group(ACCOUNT_RE, normalized)
    account_number = _normalize_account(account_raw)

    amount_display, amount_value = _parse_amount(
        _search_group(AMOUNT_DRAFT_RE, normalized)
    )

    draft_display = _search_group(BANK_DRAFT_DATE_RE, normalized)
    draft_display = _extract_first_date(draft_display)
    draft_iso = _parse_date_iso(draft_display)

    service_address = _search_group(SERVICE_ADDRESS_RE, normalized)

    if not any((account_number, amount_display, draft_display)):
        return None

    status = _derive_status(draft_iso)

    bill = {
        "id": email.get("message_id") or email.get("uid"),
        "provider": "PSNC Energy",
        "subject": subject,
        "received": email.get(EMAIL_ATTR_DATE),
        "amount_due": amount_display,
        "amount_due_value": amount_value,
        "due_date": draft_display,
        "due_date_iso": draft_iso,
        "status": status,
        "snippet": normalized[:DEFAULT_SNIPPET_LENGTH],
        "from_address": email.get(EMAIL_ATTR_ADDRESS),
        ATTR_ACCOUNT_NUMBER: account_number,
    }

    if service_address:
        bill["service_address"] = service_address

    # Some sensors expect billing keys even if missing
    bill.setdefault(ATTR_BILLING_DATE, None)
    bill.setdefault(ATTR_BILLING_DATE_ISO, None)

    from_display = email.get(EMAIL_ATTR_FROM)
    if from_display:
        bill[EMAIL_ATTR_FROM] = from_display

    return bill


def _normalize(value: str) -> str:
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
    text = text.replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
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


def _extract_first_date(value: str | None) -> str | None:
    if not value:
        return None

    date_match = re.search(
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
        r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        value,
        flags=re.IGNORECASE,
    )
    if date_match:
        return date_match.group(1).strip()

    cleaned = value.strip()
    return cleaned or None


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


def _normalize_account(value: str | None) -> str | None:
    if not value:
        return None

    cleaned = value.replace(" ", "")
    cleaned = re.sub(r"[^0-9*]", "", cleaned)
    return cleaned or None
