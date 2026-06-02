"""Constants for the Aqualia integration."""

from datetime import timedelta

DOMAIN = "aqualia"

CONF_NIF = "nif"
CONF_CAC_CODE = "cac_code"
CONF_CONTRACT_CODE = "contract_code"
CONF_INSTALLATION_CODE = "installation_code"
CONF_CONTRACT_NUMBER = "contract_number"
CONF_POLL_INTERVAL_MINUTES = "poll_interval_minutes"
CONF_DAYS_BACK = "days_back"

DEFAULT_POLL_INTERVAL_MINUTES = 60
DEFAULT_DAYS_BACK = 60
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=DEFAULT_POLL_INTERVAL_MINUTES)

MIN_POLL_INTERVAL_MINUTES = 5
MAX_POLL_INTERVAL_MINUTES = 1440
MIN_DAYS_BACK = 7
MAX_DAYS_BACK = 365

PLATFORMS = ["sensor"]
