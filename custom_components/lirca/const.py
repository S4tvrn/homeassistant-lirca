"""Costanti per l'integrazione LIRCA."""
from datetime import timedelta

DOMAIN = "lirca"

BASE_URL = "https://utenti.lirca.it"

DEFAULT_SCAN_INTERVAL = timedelta(hours=6)

HEADERS_COMMON = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.6 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "it-IT,it;q=0.9",
}
