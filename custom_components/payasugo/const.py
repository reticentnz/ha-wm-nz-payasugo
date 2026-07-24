"""Constants for the Waste Management New Zealand PayAsUGO integration."""

from datetime import timedelta

DOMAIN = "payasugo"
PLATFORMS = ["sensor", "switch"]

CONF_ADDRESS = "address"

DEFAULT_SCAN_INTERVAL = timedelta(hours=6)
BASE_URL = "https://payasugo.wastemanagement.co.nz"
