"""Parser for Truist mortgage payment emails."""
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
    EMAIL_ATTR_ADDRESS,
    EMAIL_ATTR_BODY,
    EMAIL_ATTR_DATE,
    EMAIL_ATTR_FROM,
    EMAIL_ATTR_SUBJECT,
)

PAYMENT_INFO_RE = re.compile(
    r"payment\s+of\s*\$?([0-9,]+(?:\.[0-9]{2})?)\s+on\s+([A-Za-z0-9.,/\- ]+?)(?:\.|\s+your\s+next|\s|$)",
    re.IGNORECASE,
)
PAYMENT_AMOUNT_RE = re.compile(
    r"payment\s+of\s*\$?([0-9,]+(?:\.[0-9]{2})?)",
    re.IGNORECASE,
)
TOTAL_PAID_RE = re.compile(
    r"Total\s+paid\s*\$?\s*([0-9,]+(?:\.[0-9]{2})?)",
    re.IGNORECASE,
)
NEXT_DUE_RE = re.compile(
    r"next\s+payment\s+(?:will\s+be\s+)?due\s+on\s*([A-Za-z0-9.,/\- ]+)",
    re.IGNORECASE,
)
LOAN_NUMBER_RE = re.compile(r"Loan\s+number:\s*([A-Za-z0-9]+)", re.IGNORECASE)
DATE_FINDER_RE = re.compile(
    r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    re.IGNORECASE,
)


def parse_truist_mortgage(email: dict[str, Any]) -> dict[str, Any] | None:
    """Extract mortgage payment details from Truist emails."""
    subject = (email.get(EMAIL_ATTR_SUBJECT) or "").strip()
    body = email.get(EMAIL_ATTR_BODY) or ""

    normalized = _normalize(body)
    combined = f"{subject} {normalized}".lower()

    if "truist" not in combined or "mortgage" not in combined:
        return None

    payment_match = PAYMENT_INFO_RE.search(normalized)
    payment_amount_raw = payment_match.group(1) if payment_match else None
    payment_date_raw = payment_match.group(2) if payment_match else None

    if not payment_amount_raw:
        payment_amount_raw = _search_group(PAYMENT_AMOUNT_RE, normalized)

    if not payment_date_raw and payment_match is not None:
        payment_date_raw = payment_match.group(2)

    if not payment_amount_raw:
        payment_amount_raw = _search_group(TOTAL_PAID_RE, normalized)

    next_due_raw = _search_group(NEXT_DUE_RE, normalized)
    loan_number = _search_group(LOAN_NUMBER_RE, normalized)

    payment_date_display = _extract_first_date(payment_date_raw)
    payment_date_iso = _parse_date_iso(payment_date_display)

    next_due_display = _extract_first_date(next_due_raw)
    next_due_iso = _parse_date_iso(next_due_display)

    amount_display, amount_value = _parse_amount(payment_amount_raw)

    if not any((amount_display, next_due_display, payment_date_display, loan_number)):
        return None

    status = _derive_status(next_due_iso, payment_date_iso)

    bill: dict[str, Any] = {
        "id": email.get("message_id") or email.get("uid"),
        "provider": "Truist Mortgage",
        "subject": subject,
        "received": email.get(EMAIL_ATTR_DATE),
        "amount_due": amount_display,
        "amount_due_value": amount_value,
        "due_date": next_due_display,
        "due_date_iso": next_due_iso,
        "status": status,
        "snippet": normalized[:DEFAULT_SNIPPET_LENGTH],
        "from_address": email.get(EMAIL_ATTR_ADDRESS),
        ATTR_ACCOUNT_NUMBER: loan_number,
        ATTR_BILLING_DATE: payment_date_display,
        ATTR_BILLING_DATE_ISO: payment_date_iso,
    }

    if payment_date_display:
        bill["payment_date"] = payment_date_display
        bill["payment_date_iso"] = payment_date_iso

    from_display = email.get(EMAIL_ATTR_FROM)
    if from_display:
        bill[EMAIL_ATTR_FROM] = from_display

    return bill


def _normalize(value: str) -> str:
    """Clean HTML into a searchable text block."""
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
    text = re.sub(
        r"</?(tr|p|div|li|table|tbody|thead|section|article)[^>]*>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
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


def _extract_first_date(value: str | None) -> str | None:
    if not value:
        return None

    match = DATE_FINDER_RE.search(value)
    if match:
        return match.group(1).strip()

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


def _derive_status(due_iso: str | None, payment_iso: str | None) -> str:
    if payment_iso:
        return "paid"

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
