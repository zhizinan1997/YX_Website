"""Admin login geo-access settings and country catalog helpers."""

from __future__ import annotations

ADMIN_LOGIN_GEO_ALLOWED = "allow"
ADMIN_LOGIN_GEO_DENIED = "deny"
ADMIN_LOGIN_GEO_INHERIT = "inherit"

ADMIN_GEO_CONTINENTS = (
    {"key": "asia", "label": "亚洲"},
    {"key": "europe", "label": "欧洲"},
    {"key": "africa", "label": "非洲"},
    {"key": "north-america", "label": "北美洲"},
    {"key": "south-america", "label": "南美洲"},
    {"key": "oceania", "label": "大洋洲"},
    {"key": "antarctica", "label": "南极洲"},
)

ADMIN_GEO_COUNTRIES_BY_CONTINENT = {
    "asia": [
        "AE", "AF", "AM", "AZ", "BD", "BH", "BN", "BT", "CN", "GE",
        "HK", "ID", "IL", "IN", "IQ", "IR", "JO", "JP", "KG", "KH",
        "KP", "KR", "KW", "KZ", "LA", "LB", "LK", "MM", "MN", "MO",
        "MV", "MY", "NP", "OM", "PH", "PK", "PS", "QA", "SA", "SG",
        "SY", "TH", "TJ", "TL", "TM", "TR", "TW", "UZ", "VN", "YE",
    ],
    "europe": [
        "AD", "AL", "AT", "AX", "BA", "BE", "BG", "BY", "CH", "CY",
        "CZ", "DE", "DK", "EE", "ES", "FI", "FO", "FR", "GB", "GG",
        "GI", "GR", "HR", "HU", "IE", "IM", "IS", "IT", "JE", "LI",
        "LT", "LU", "LV", "MC", "MD", "ME", "MK", "MT", "NL", "NO",
        "PL", "PT", "RO", "RS", "RU", "SE", "SI", "SJ", "SK", "SM",
        "UA", "VA", "XK",
    ],
    "africa": [
        "AO", "BF", "BI", "BJ", "BW", "CD", "CF", "CG", "CI", "CM",
        "CV", "DJ", "DZ", "EG", "EH", "ER", "ET", "GA", "GH", "GM",
        "GN", "GQ", "GW", "IO", "KE", "KM", "LR", "LS", "LY", "MA",
        "MG", "ML", "MR", "MU", "MW", "MZ", "NA", "NE", "NG", "RE",
        "RW", "SC", "SD", "SH", "SL", "SN", "SO", "SS", "ST", "SZ",
        "TD", "TG", "TN", "TZ", "UG", "YT", "ZA", "ZM", "ZW",
    ],
    "north-america": [
        "AG", "AI", "AW", "BB", "BL", "BM", "BQ", "BS", "BZ", "CA",
        "CR", "CU", "CW", "DM", "DO", "GD", "GL", "GP", "GT", "HN",
        "HT", "JM", "KN", "KY", "LC", "MF", "MQ", "MS", "MX", "NI",
        "PA", "PM", "PR", "SV", "SX", "TC", "TT", "UM", "US", "VC",
        "VG", "VI",
    ],
    "south-america": [
        "AR", "BO", "BR", "CL", "CO", "EC", "FK", "GF", "GY", "PE",
        "PY", "SR", "UY", "VE",
    ],
    "oceania": [
        "AS", "AU", "CC", "CK", "CX", "FJ", "FM", "GU", "KI", "MH",
        "MP", "NC", "NF", "NR", "NU", "NZ", "PF", "PG", "PN", "PW",
        "SB", "TK", "TO", "TV", "VU", "WF", "WS",
    ],
    "antarctica": ["AQ", "BV", "GS", "HM", "TF"],
}

ADMIN_GEO_COUNTRY_TO_CONTINENT = {}
for _continent in ADMIN_GEO_CONTINENTS:
    _continent_key = _continent["key"]
    for _country_code in ADMIN_GEO_COUNTRIES_BY_CONTINENT.get(_continent_key, []):
        ADMIN_GEO_COUNTRY_TO_CONTINENT[_country_code] = _continent_key

DEFAULT_ADMIN_LOGIN_GEO_SETTINGS = {
    "enabled": True,
    "continents": {
        continent["key"]: (
            ADMIN_LOGIN_GEO_ALLOWED if continent["key"] == "asia" else ADMIN_LOGIN_GEO_DENIED
        )
        for continent in ADMIN_GEO_CONTINENTS
    },
    "countries": {
        "CN": ADMIN_LOGIN_GEO_ALLOWED,
        "HK": ADMIN_LOGIN_GEO_ALLOWED,
        "MO": ADMIN_LOGIN_GEO_ALLOWED,
        "TW": ADMIN_LOGIN_GEO_ALLOWED,
    },
}


def _parse_bool(value, default=False):
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_continent_policy(value) -> str:
    text = str(value or "").strip().lower()
    if text == ADMIN_LOGIN_GEO_ALLOWED:
        return ADMIN_LOGIN_GEO_ALLOWED
    return ADMIN_LOGIN_GEO_DENIED


def _normalize_country_policy(value) -> str:
    text = str(value or "").strip().lower()
    if text in {
        ADMIN_LOGIN_GEO_ALLOWED,
        ADMIN_LOGIN_GEO_DENIED,
        ADMIN_LOGIN_GEO_INHERIT,
    }:
        return text
    return ADMIN_LOGIN_GEO_INHERIT


def normalize_admin_login_geo_settings(config) -> dict:
    safe = config if isinstance(config, dict) else {}
    normalized = {
        "enabled": _parse_bool(
            safe.get("admin_login_geo_enabled", DEFAULT_ADMIN_LOGIN_GEO_SETTINGS["enabled"]),
            DEFAULT_ADMIN_LOGIN_GEO_SETTINGS["enabled"],
        ),
        "continents": dict(DEFAULT_ADMIN_LOGIN_GEO_SETTINGS["continents"]),
        "countries": dict(DEFAULT_ADMIN_LOGIN_GEO_SETTINGS["countries"]),
    }

    raw_continents = safe.get("admin_login_geo_continents", {})
    if isinstance(raw_continents, dict):
        for continent in ADMIN_GEO_CONTINENTS:
            key = continent["key"]
            if key in raw_continents:
                normalized["continents"][key] = _normalize_continent_policy(raw_continents.get(key))

    raw_countries = safe.get("admin_login_geo_countries")
    if isinstance(raw_countries, dict):
        normalized["countries"] = {}
        for raw_code, raw_policy in raw_countries.items():
            code = str(raw_code or "").strip().upper()
            if code not in ADMIN_GEO_COUNTRY_TO_CONTINENT:
                continue
            policy = _normalize_country_policy(raw_policy)
            if policy != ADMIN_LOGIN_GEO_INHERIT:
                normalized["countries"][code] = policy

    return normalized


def build_admin_login_geo_catalog_payload() -> dict:
    return {
        "continents": [
            {
                "key": continent["key"],
                "label": continent["label"],
                "countries": list(ADMIN_GEO_COUNTRIES_BY_CONTINENT.get(continent["key"], [])),
            }
            for continent in ADMIN_GEO_CONTINENTS
        ]
    }


def build_admin_login_geo_settings_payload(config) -> dict:
    normalized = normalize_admin_login_geo_settings(config)
    return {
        "enabled": bool(normalized["enabled"]),
        "continents": dict(normalized["continents"]),
        "countries": dict(normalized["countries"]),
    }


def extract_admin_login_geo_updates(payload) -> dict:
    safe = payload if isinstance(payload, dict) else {}
    current = normalize_admin_login_geo_settings({})

    normalized = {
        "enabled": _parse_bool(safe.get("enabled", current["enabled"]), current["enabled"]),
        "continents": dict(current["continents"]),
        "countries": {},
    }

    raw_continents = safe.get("continents", {})
    if isinstance(raw_continents, dict):
        for continent in ADMIN_GEO_CONTINENTS:
            key = continent["key"]
            normalized["continents"][key] = _normalize_continent_policy(raw_continents.get(key))

    raw_countries = safe.get("countries", {})
    if isinstance(raw_countries, dict):
        for raw_code, raw_policy in raw_countries.items():
            code = str(raw_code or "").strip().upper()
            if code not in ADMIN_GEO_COUNTRY_TO_CONTINENT:
                continue
            policy = _normalize_country_policy(raw_policy)
            if policy != ADMIN_LOGIN_GEO_INHERIT:
                normalized["countries"][code] = policy

    return {
        "admin_login_geo_enabled": bool(normalized["enabled"]),
        "admin_login_geo_continents": dict(normalized["continents"]),
        "admin_login_geo_countries": dict(normalized["countries"]),
    }


def get_country_continent_key(country_code: str) -> str:
    return ADMIN_GEO_COUNTRY_TO_CONTINENT.get(str(country_code or "").strip().upper(), "")


def is_country_code_allowed(country_code: str, settings: dict) -> bool:
    normalized = settings if isinstance(settings, dict) else normalize_admin_login_geo_settings({})
    if not normalized.get("enabled", True):
        return True

    code = str(country_code or "").strip().upper()
    if not code:
        return False

    country_policy = str((normalized.get("countries") or {}).get(code) or "").strip().lower()
    if country_policy == ADMIN_LOGIN_GEO_ALLOWED:
        return True
    if country_policy == ADMIN_LOGIN_GEO_DENIED:
        return False

    continent_key = get_country_continent_key(code)
    continent_policy = str((normalized.get("continents") or {}).get(continent_key) or "").strip().lower()
    return continent_policy == ADMIN_LOGIN_GEO_ALLOWED
