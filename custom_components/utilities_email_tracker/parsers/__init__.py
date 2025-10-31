"""Email parsing helpers for Utilities Email Tracker."""
from __future__ import annotations

import logging
from typing import Any

from .duke_energy import parse_duke_energy
from .psnc_energy import parse_psnc_energy

_LOGGER = logging.getLogger(__name__)

PARSERS = [
    ("duke_energy", parse_duke_energy),
    ("psnc_energy", parse_psnc_energy),
]


def extract_bills(emails: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run available parsers over the provided emails."""
    bills: list[dict[str, Any]] = []

    for email in emails:
        for parser_name, parser in PARSERS:
            try:
                parsed = parser(email)
            except Exception as err:  # pragma: no cover - defensive
                _LOGGER.debug("Parser %s failed: %s", parser_name, err)
                continue

            if not parsed:
                continue

            # Each parser can return a single bill or list of bills
            if isinstance(parsed, dict):
                parsed = [parsed]

            if not isinstance(parsed, list):
                _LOGGER.debug(
                    "Parser %s returned unsupported payload for message %s",
                    parser_name,
                    email.get("message_id"),
                )
                continue

            bills.extend(parsed)

    return bills
