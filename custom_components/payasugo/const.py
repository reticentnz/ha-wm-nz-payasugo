"""Constants for the Waste Management New Zealand PayAsUGO integration."""

from datetime import timedelta

DOMAIN = "payasugo"
PLATFORMS = ["sensor", "switch"]

CONF_ADDRESS = "address"

DEFAULT_SCAN_INTERVAL = timedelta(hours=24)
RETRY_INTERVALS = (
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(minutes=30),
    timedelta(hours=1),
)
BASE_URL = "https://payasugo.wastemanagement.co.nz"
