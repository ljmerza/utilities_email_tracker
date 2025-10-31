"""Generic parser for utility bill style emails."""
from __future__ import annotations

from datetime import datetime
import re
from email.utils import parseaddr
from typing import Any

from ..const import (
    DEFAULT_SNIPPET_LENGTH,
    EMAIL_ATTR_BODY,
    EMAIL_ATTR_DATE,
    EMAIL_ATTR_FROM,
    EMAIL_ATTR_ADDRESS,
    EMAIL_ATTR_SUBJECT,
)

DATE_WORD_REGEX = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Oct|Nov|Dec)\s+\d{1,2}(?:,\s*\d{2,4})?",
    re.IGNORECASE,
)
DATE_NUMERIC_REGEX = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")

AMOUNT_HINT_REGEX = re.compile(
    r"(amount(?:\s+due|\s+owed|\s+payable)?|total(?:\s+due)?|balance(?:\s+due)?|payment)"
    r"[^\n\r]{0,32}\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|[0-9]+(?:\.[0-9]{2})?)",
    re.IGNORECASE,
)
AMOUNT_LOOSE_REGEX = re.compile(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|[0-9]+(?:\.[0-9]{2})?)")

STATUS_HINTS = {
    "past due": "overdue",
    "overdue": "overdue",
    "late fee": "overdue",
    "paid": "paid",
    "payment received": "paid",
}

UTILITY_KEYWORDS = (
    "bill",
    "statement",
    "payment",
    "due",
    "utility",
    "electric",
    "gas",
    "water",
    "sewer",
    "trash",
    "invoice",
)


def parse_generic_email(email: dict[str, Any]) -> dict[str, Any] | None:
    """Attempt to extract bill information from a utility style email."""
    subject = (email.get(EMAIL_ATTR_SUBJECT) or "").strip()
    body = (email.get(EMAIL_ATTR_BODY) or "").strip()
    combined_raw = f"{subject}\n{body}"
    combined_text = combined_raw.lower()

    if not subject and not body:
        return None

    if not any(keyword in combined_text for keyword in UTILITY_KEYWORDS):
        # Avoid flagging unrelated emails
        return None

    provider = _derive_provider(email)
    amount_display, amount_value = _extract_amount(body)
    due_date_display, due_date_iso = _extract_due_date(combined_raw)
    status = _determine_status(combined_text, due_date_iso)

    snippet = body[:DEFAULT_SNIPPET_LENGTH].replace("\r", " ")

    bill = {
        "id": email.get("message_id") or email.get("uid"),
        "provider": provider,
        "subject": subject,
        "received": email.get(EMAIL_ATTR_DATE),
        "amount_due": amount_display,
        "amount_due_value": amount_value,
        "due_date": due_date_display,
        "due_date_iso": due_date_iso,
        "status": status,
        "snippet": snippet,
        "from_address": email.get(EMAIL_ATTR_ADDRESS),
    }

    return bill


def _derive_provider(email: dict[str, Any]) -> str:
    """Choose the most useful provider label from email metadata."""
    from_display = str(email.get(EMAIL_ATTR_FROM) or "").strip()
    from_address = str(email.get(EMAIL_ATTR_ADDRESS) or "").strip()

    if not from_display and from_address:
        parsed = parseaddr(from_address)
        if parsed[0]:
            from_display = parsed[0]
        else:
            from_address = parsed[1]

    if not from_address and from_display:
        parsed = parseaddr(from_display)
        if parsed[1]:
            from_address = parsed[1]
        if parsed[0]:
            from_display = parsed[0]

    if from_display:
        return from_display

    if from_address:
        domain = from_address.split("@")[-1]
        provider = domain.split(".")[0]
        return provider.replace("-", " ").replace("_", " ").title()

    return "Unknown"


def _extract_amount(body: str) -> tuple[str | None, float | None]:
    """Extract the billed amount if present."""
    match = AMOUNT_HINT_REGEX.search(body)
    if not match:
        match = AMOUNT_LOOSE_REGEX.search(body)

    if not match:
        return None, None

    amount_str = match.group(2) if len(match.groups()) >= 2 else match.group(1)
    if amount_str is None:
        return None, None

    normalized = amount_str.replace(",", "").strip()
    try:
        value = float(normalized)
    except ValueError:
        value = None

    # Ensure we include a currency symbol for display
    display = amount_str.strip()
    if not display.startswith("$"):
        display = f"${display}"

    return display, value


def _extract_due_date(text: str) -> tuple[str | None, str | None]:
    """Find a due date string and convert to ISO date if possible."""
    match = DATE_WORD_REGEX.search(text)
    if not match:
        match = DATE_NUMERIC_REGEX.search(text)

    if not match:
        return None, None

    date_str = match.group(0)
    iso_date = _parse_date_iso(date_str)
    return date_str, iso_date


def _parse_date_iso(date_str: str) -> str | None:
    """Parse several common date formats to ISO (YYYY-MM-DD)."""
    cleaned = date_str.replace("\n", " ").replace("\r", " ").replace("  ", " ").strip()
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
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.date().isoformat()
        except ValueError:
            continue
    return None


def _determine_status(text: str, due_date_iso: str | None) -> str:
    """Infer bill status from textual hints and due date."""
    for phrase, status in STATUS_HINTS.items():
        if phrase in text:
            return status

    if due_date_iso:
        try:
            due_date = datetime.fromisoformat(due_date_iso)
            if due_date.date() < datetime.now().date():
                return "overdue"
        except ValueError:
            pass

    return "due"
