"""Constants for Utilities Email Tracker integration."""

# Domain
DOMAIN = "utilities_email_tracker"

# Configuration keys
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_IMAP_SERVER = "imap_server"
CONF_IMAP_PORT = "imap_port"
CONF_EMAIL_FOLDER = "folder"
CONF_USE_SSL = "use_ssl"
CONF_DAYS_OLD = "days_old"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_MAX_MESSAGES = "max_messages"

# Defaults
DEFAULT_IMAP_SERVER = "imap.gmail.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_USE_SSL = True
DEFAULT_FOLDER = "INBOX"
DEFAULT_DAYS_OLD = 30
DEFAULT_SCAN_INTERVAL = 30  # minutes
DEFAULT_MAX_MESSAGES = 100

# Email attributes
EMAIL_ATTR_FROM = "from"
EMAIL_ATTR_ADDRESS = "from_address"
EMAIL_ATTR_SUBJECT = "subject"
EMAIL_ATTR_BODY = "body"
EMAIL_ATTR_DATE = "date"

# Sensor attributes
ATTR_BILLS = "bills"
ATTR_SUMMARY = "summary"
ATTR_COUNT = "count"
ATTR_LAST_UPDATE = "last_update"
ATTR_ACCOUNT_NUMBER = "account_number"
ATTR_BILLING_DATE = "billing_date"
ATTR_BILLING_DATE_ISO = "billing_date_iso"

# Misc
IMAP_TIMEOUT = 10
DEFAULT_SNIPPET_LENGTH = 240
