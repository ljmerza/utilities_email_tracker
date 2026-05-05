# Utilities Email Tracker

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/ljmerza/utilities_email_tracker/actions/workflows/validate.yml/badge.svg)](https://github.com/ljmerza/utilities_email_tracker/actions/workflows/validate.yml)
[![Release](https://github.com/ljmerza/utilities_email_tracker/actions/workflows/release.yml/badge.svg)](https://github.com/ljmerza/utilities_email_tracker/actions/workflows/release.yml)
[![GitHub release](https://img.shields.io/github/v/release/ljmerza/utilities_email_tracker)](https://github.com/ljmerza/utilities_email_tracker/releases)

A Home Assistant custom integration that polls an IMAP mailbox for utility-bill
emails, parses them with provider-specific extractors, and exposes the results
as a sensor with detailed attributes.

## Features

- IMAP polling over SSL with configurable server, port, folder, and scan interval
- Pluggable per-provider parsers — current bundled parsers:
  - Duke Energy
  - PSNC Energy (Piedmont Natural Gas)
  - City of Raleigh Water
  - Truist Mortgage
- Single sensor per account whose state is the count of bills found in the
  configured lookback window
- Attributes expose individual bills, totals/summary, and last-update timestamp
- Fully UI-configured via Home Assistant config flow

## Installation

### HACS (recommended once published)

1. Open HACS in Home Assistant.
2. Search for **Utilities Email Tracker** under Integrations and install.
3. Restart Home Assistant.

### HACS as a custom repository (until merged into the default list)

1. In HACS, open the menu and choose **Custom repositories**.
2. Add `https://github.com/ljmerza/utilities_email_tracker` with category
   **Integration**.
3. Install **Utilities Email Tracker** from the integrations list and restart
   Home Assistant.

### Manual

Copy `custom_components/utilities_email_tracker/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

After installation, add the integration via **Settings → Devices & Services →
Add Integration → Utilities Email Tracker**.

| Field            | Default          | Notes                                                              |
|------------------|------------------|--------------------------------------------------------------------|
| Email            | —                | Mailbox address used for IMAP login.                               |
| Password         | —                | App password recommended (e.g. Gmail app password).                |
| IMAP server      | `imap.gmail.com` | Hostname of the IMAP server.                                       |
| IMAP port        | `993`            | TLS/SSL port.                                                      |
| Use SSL          | `true`           | Disable only for non-SSL servers.                                  |
| Folder           | `INBOX`          | Mailbox/folder to scan.                                            |
| Days old         | `30`             | Lookback window for messages.                                      |
| Scan interval    | `30` minutes     | How often the coordinator polls.                                   |
| Max messages     | `100`            | Upper bound per poll to avoid expensive scans.                     |

> **Gmail tip:** create an [app password](https://support.google.com/accounts/answer/185833)
> rather than using your account password, and confirm IMAP is enabled in
> Gmail settings.

## Sensor

The integration creates one sensor per configured account:

- **State:** number of bills detected in the lookback window
- **Attributes:**
  - `bills` — list of parsed bill objects (provider, amount, due date, account
    number, billing date, source email metadata)
  - `summary` — aggregate totals and per-provider rollups
  - `count` — same as the state
  - `last_update` — ISO timestamp of the last successful poll

## Adding a new provider parser

Parsers live in `custom_components/utilities_email_tracker/parsers/`. Each
parser is a pure function that takes a single email dict and returns either:

- a `dict` describing one bill,
- a `list[dict]` of bills, or
- `None` if the email isn't relevant.

To add a parser:

1. Create `parsers/<provider>.py` exporting a `parse_<provider>(email)` function.
2. Register it in `parsers/__init__.py` by appending a `(name, callable)` tuple
   to the `PARSERS` list.
3. Restart Home Assistant.

Parsers should match on sender + subject before doing expensive body parsing,
and should fail closed (return `None`) on anything unexpected — `extract_bills`
already swallows parser exceptions.

## Troubleshooting

- **No bills appear:** raise `Days old` and confirm the matching emails are in
  the configured `Folder`.
- **Auth errors:** verify IMAP is enabled and you're using an app password
  where required (Gmail, Outlook with 2FA, etc.).
- **Debug logs:** add the following to `configuration.yaml` and restart:
  ```yaml
  logger:
    default: warning
    logs:
      custom_components.utilities_email_tracker: debug
  ```

## Contributing

Issues and pull requests welcome at
<https://github.com/ljmerza/utilities_email_tracker>. New parsers and bug
reports for existing ones are particularly appreciated — include a redacted
sample of the email subject/body so the regex can be exercised.

## License

[MIT](LICENSE)
