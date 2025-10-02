from __future__ import annotations

import random
import string
from dataclasses import dataclass
from typing import Dict, List, Tuple


def _rand_id(prefix: str, n: int = 6) -> str:
    return f"{prefix}_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


# Geo/IP hints (very rough, just for synthetic data)
COUNTRY_INFO: Dict[str, Dict] = {
    "US": {"currency": "USD", "cities": [(37.7749, -122.4194), (40.7128, -74.0060), (34.0522, -118.2437)]},
    "GB": {"currency": "GBP", "cities": [(51.5074, -0.1278), (53.4808, -2.2426)]},
    "DE": {"currency": "EUR", "cities": [(52.5200, 13.4050), (48.1351, 11.5820)]},
    "IN": {"currency": "INR", "cities": [(28.6139, 77.2090), (19.0760, 72.8777)]},
    "CA": {"currency": "CAD", "cities": [(43.6532, -79.3832), (45.5019, -73.5674)]},
    "AU": {"currency": "AUD", "cities": [(-33.8688, 151.2093), (-37.8136, 144.9631)]},
}


def sample_ip(country: str) -> str:
    # Simulate country blocks by hardcoding first octets per country
    first_octet = {
        "US": 23,
        "GB": 51,
        "DE": 88,
        "IN": 49,
        "CA": 24,
        "AU": 101,
    }.get(country, 45)
    return f"{first_octet}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def sample_geo(country: str) -> Tuple[str, float, float]:
    data = COUNTRY_INFO.get(country) or COUNTRY_INFO["US"]
    lat, lon = random.choice(data["cities"])  # seed city
    # small jitter
    lat += random.uniform(-0.2, 0.2)
    lon += random.uniform(-0.2, 0.2)
    return country, lat, lon


@dataclass
class Merchant:
    merchant_id: str
    name: str
    mcc: int


MERCHANTS: List[Merchant] = [
    Merchant("m_acme", "ACME-MARKET", 5411),  # Grocery stores
    Merchant("m_travel", "GLOBAL-TRAVEL", 4511),  # Airlines/Air Carriers
    Merchant("m_fast", "FAST-FOOD", 5814),  # Fast Food Restaurants
    Merchant("m_stream", "STREAMFLIX", 4899),  # Cable, Satellite, Pay Television
    Merchant("m_mega", "MEGASTORE", 5311),  # Department Stores
]


@dataclass
class Persona:
    user_id: str
    type: str  # normal | traveler | fraudster
    home_country: str
    home_currency: str
    devices: List[str]


def sample_personas(n_normal: int = 80, n_travelers: int = 15, n_fraudsters: int = 5) -> List[Persona]:
    personas: List[Persona] = []
    countries = list(COUNTRY_INFO.keys())

    for _ in range(n_normal):
        c = random.choice(countries)
        personas.append(
            Persona(
                user_id=_rand_id("user"),
                type="normal",
                home_country=c,
                home_currency=COUNTRY_INFO[c]["currency"],
                devices=[_rand_id("dev")],
            )
        )

    for _ in range(n_travelers):
        c = random.choice(countries)
        personas.append(
            Persona(
                user_id=_rand_id("user"),
                type="traveler",
                home_country=c,
                home_currency=COUNTRY_INFO[c]["currency"],
                devices=[_rand_id("dev"), _rand_id("dev")],
            )
        )

    for _ in range(n_fraudsters):
        c = random.choice(countries)
        personas.append(
            Persona(
                user_id=_rand_id("user"),
                type="fraudster",
                home_country=c,
                home_currency=COUNTRY_INFO[c]["currency"],
                devices=[_rand_id("dev"), _rand_id("dev"), _rand_id("dev")],
            )
        )

    return personas

