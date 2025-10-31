"""Data update coordinator for Utilities Email Tracker."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any

from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError
from mailparser import parse_from_bytes

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from email.utils import parseaddr

from .const import (
    ATTR_BILLS,
    ATTR_COUNT,
    ATTR_LAST_UPDATE,
    ATTR_SUMMARY,
    CONF_DAYS_OLD,
    CONF_EMAIL,
    CONF_EMAIL_FOLDER,
    CONF_IMAP_PORT,
    CONF_IMAP_SERVER,
    CONF_MAX_MESSAGES,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USE_SSL,
    DEFAULT_DAYS_OLD,
    DEFAULT_FOLDER,
    DEFAULT_IMAP_PORT,
    DEFAULT_IMAP_SERVER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_MAX_MESSAGES,
    DEFAULT_USE_SSL,
    DOMAIN,
    EMAIL_ATTR_ADDRESS,
    EMAIL_ATTR_BODY,
    EMAIL_ATTR_DATE,
    EMAIL_ATTR_FROM,
    EMAIL_ATTR_SUBJECT,
    IMAP_TIMEOUT,
)
from .parsers import extract_bills

_LOGGER = logging.getLogger(__name__)


class UtilitiesEmailTrackerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator responsible for polling email inbox for utility bills."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict[str, Any],
        options: dict[str, Any],
    ) -> None:
        self.hass = hass
        self.config = config
        self.options = options
        self.entry_id = entry_id

        scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        update_interval = timedelta(minutes=scan_interval)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{config.get(CONF_EMAIL)}",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest bills from the mailbox."""
        try:
            emails = await self.hass.async_add_executor_job(self._fetch_emails)
            bills = extract_bills(emails)
            limited_bills = self._limit_bills(bills)
            summary = self._build_summary(limited_bills)

            return {
                ATTR_BILLS: limited_bills,
                ATTR_SUMMARY: summary,
                ATTR_COUNT: len(limited_bills),
                ATTR_LAST_UPDATE: datetime.utcnow().isoformat(),
            }
        except Exception as err:  # pragma: no cover - defensive
            raise UpdateFailed(f"Unable to refresh utility bills: {err}") from err

    def _fetch_emails(self) -> list[dict[str, Any]]:
        """Fetch raw email payloads from the IMAP server."""
        server_host = self.config.get(CONF_IMAP_SERVER, DEFAULT_IMAP_SERVER)
        server_port = self.config.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT)
        use_ssl = self.config.get(CONF_USE_SSL, DEFAULT_USE_SSL)
        username = self.config[CONF_EMAIL]
        password = self.config[CONF_PASSWORD]
        folder = self.options.get(CONF_EMAIL_FOLDER, DEFAULT_FOLDER)
        days_old = self.options.get(CONF_DAYS_OLD, DEFAULT_DAYS_OLD)

        search_date = date.today() - timedelta(days=days_old)
        search_flag = ["SINCE", search_date]

        _LOGGER.debug(
            "Connecting to IMAP %s:%s (SSL=%s) for %s",
            server_host,
            server_port,
            use_ssl,
            username,
        )

        server = IMAPClient(
            server_host,
            port=server_port,
            use_uid=True,
            ssl=use_ssl,
            timeout=IMAP_TIMEOUT,
        )

        try:
            server.login(username, password)
            server.select_folder(folder, readonly=True)
            message_ids = server.search(search_flag)

            _LOGGER.debug(
                "Found %s messages in %s since %s",
                len(message_ids),
                folder,
                search_date,
            )

            emails: list[dict[str, Any]] = []
            if not message_ids:
                return emails

            response = server.fetch(message_ids, ["RFC822"])
            for uid, data in response.items():
                raw = data.get(b"RFC822")
                if raw is None:
                    continue

                try:
                    mail = parse_from_bytes(raw)
                except Exception as err:  # pragma: no cover - defensive
                    _LOGGER.debug("Failed to parse message %s: %s", uid, err)
                    continue

                from_display, from_address = _parse_from(mail.from_)

                body = mail.body or ""
                if hasattr(mail, "text_html") and mail.text_html:
                    body = "\n".join(mail.text_html)
                elif hasattr(mail, "text_plain") and mail.text_plain and not body:
                    body = "\n".join(mail.text_plain)

                emails.append(
                    {
                        "uid": uid,
                        "message_id": getattr(mail, "message_id", None),
                        EMAIL_ATTR_FROM: from_display,
                        EMAIL_ATTR_ADDRESS: from_address,
                        EMAIL_ATTR_SUBJECT: mail.subject,
                        EMAIL_ATTR_BODY: body,
                        EMAIL_ATTR_DATE: _format_date(mail.date),
                    }
                )

            return emails
        except IMAPClientError as err:
            raise UpdateFailed(f"IMAP error: {err}") from err
        finally:
            try:
                server.logout()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

    def _limit_bills(self, bills: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Limit the number of tracked bills to configured maximum."""
        if not bills:
            return []

        # Deduplicate by message id / uid
        seen = set()
        unique_bills: list[dict[str, Any]] = []
        for bill in bills:
            identifier = bill.get("id")
            if identifier and identifier in seen:
                continue
            if identifier:
                seen.add(identifier)
            unique_bills.append(bill)

        unique_bills.sort(
            key=lambda item: item.get("received") or "",
            reverse=True,
        )

        max_messages = self.options.get(CONF_MAX_MESSAGES, DEFAULT_MAX_MESSAGES)
        if len(unique_bills) <= max_messages:
            return unique_bills
        return unique_bills[:max_messages]

    def _build_summary(self, bills: list[dict[str, Any]]) -> dict[str, Any]:
        """Construct summary metrics for exposed attributes."""
        by_provider: dict[str, int] = {}
        total_amount = 0.0
        next_due: str | None = None
        overdue = 0

        for bill in bills:
            provider = bill.get("provider", "Unknown")
            by_provider[provider] = by_provider.get(provider, 0) + 1

            amount_value = bill.get("amount_due_value")
            if isinstance(amount_value, (int, float)):
                total_amount += float(amount_value)

            due_iso = bill.get("due_date_iso")
            if due_iso:
                next_due = _min_iso_date(next_due, due_iso)

            if bill.get("status") == "overdue":
                overdue += 1

        summary: dict[str, Any] = {
            "by_provider": by_provider,
            "total_amount_due": round(total_amount, 2) if total_amount else 0.0,
            "next_due_date": next_due,
            "overdue_count": overdue,
        }
        return summary


def _parse_from(from_list: Any) -> tuple[str | None, str | None]:
    """Extract a usable display name and address from mailparser output."""
    if not from_list:
        return None, None

    item = from_list[0]
    if isinstance(item, (list, tuple)) and len(item) == 2:
        display, address = item
    else:
        display, address = parseaddr(str(item))

    display = (display or "").strip() or None
    address = (address or "").strip() or None
    return display, address


def _format_date(raw_date: Any) -> str | None:
    """Convert parsed email date to ISO string."""
    if raw_date is None:
        return None

    if isinstance(raw_date, datetime):
        return raw_date.isoformat()

    try:
        parsed = datetime.fromisoformat(str(raw_date))
        return parsed.isoformat()
    except (TypeError, ValueError):
        return str(raw_date)


def _min_iso_date(existing: str | None, candidate: str) -> str:
    """Return the earliest ISO date between existing and candidate."""
    if not existing:
        return candidate

    try:
        existing_date = datetime.fromisoformat(existing).date()
        candidate_date = datetime.fromisoformat(candidate).date()
    except ValueError:
        return existing

    return candidate if candidate_date < existing_date else existing
