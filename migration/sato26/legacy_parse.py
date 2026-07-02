"""Parse legacy SATO26 line notes into destinations and map item codes."""

from __future__ import annotations

import re

ITEM_PACKAGE_TYPE = {
    "10001": "HOTEL",
    "10002": "VISA",
    "10003": "TRANSFER",
    "10004": "TICKET",
    "10005": "FULL_PACKAGE",
    "10007": "INSURANCE",
    "10011": "TRANSFER",
    "10015": "FULL_PACKAGE",
}

ITEM_LABELS = {
    "10001": "Hotel",
    "10002": "Visa",
    "10003": "Transport",
    "10004": "Ticket",
    "10005": "Package",
    "10007": "Insurance",
    "10011": "Transfer",
    "10015": "Package / Activities",
}

PLACE_TOKENS: dict[str, str] = {
    "FRANCE": "France",
    "GERMANY": "Germany",
    "GEORGIA": "Georgia",
    "LONDON": "London",
    "DUBAI": "Dubai",
    "DXB": "Dubai",
    "CAIRO": "Cairo",
    "ITALY": "Italy",
    "SPAIN": "Spain",
    "TURKEY": "Turkey",
    "ISTANBUL": "Istanbul",
    "SAW": "Istanbul",
    "TAKSIM": "Istanbul",
    "GREECE": "Greece",
    "CYPRUS": "Cyprus",
    "LEBANON": "Lebanon",
    "BEIRUT": "Beirut",
    "JORDAN": "Jordan",
    "QATAR": "Qatar",
    "DOHA": "Doha",
    "KUWAIT": "Kuwait",
    "BAHRAIN": "Bahrain",
    "OMAN": "Oman",
    "MUSCAT": "Muscat",
    "MALAYSIA": "Malaysia",
    "THAILAND": "Thailand",
    "INDIA": "India",
    "CHINA": "China",
    "JAPAN": "Japan",
    "USA": "United States",
    "CANADA": "Canada",
    "UK": "United Kingdom",
    "ENGLAND": "England",
    "SWITZERLAND": "Switzerland",
    "NETHERLANDS": "Netherlands",
    "BELGIUM": "Belgium",
    "AUSTRIA": "Austria",
    "PORTUGAL": "Portugal",
    "MOROCCO": "Morocco",
    "TUNISIA": "Tunisia",
    "EGYPT": "Egypt",
    "SAUDI": "Saudi Arabia",
    "RIYADH": "Riyadh",
    "JEDDAH": "Jeddah",
    "ABU DHABI": "Abu Dhabi",
    "SHARJAH": "Sharjah",
    "ARMENIA": "Armenia",
    "AZERBAIJAN": "Azerbaijan",
    "SCHENGEN": "Schengen",
}

PNR_RE = re.compile(r"^[A-Z0-9]{6}$")
SKIP_PARTS = frozenset(
    {
        "REISSUE",
        "REFUND",
        "VISA",
        "PACKAGE",
        "PACKAGES",
        "TOUR",
        "TRANSFER",
        "SIM CARD",
        "SIM",
        "FROM HIS SIDE",
        "NO PNRS",
        "FUUL PACKAGE",
        "FULL PACKAGE",
        "MELISSA",
        "DAD",
        "TAHRIR",
        "MICHALINE",
        "ESIM",
        "COMM",
        "SIM",
        "PNR",
        "REBOOK",
    }
)


def package_type_for_item(item_code: str) -> str:
    return ITEM_PACKAGE_TYPE.get(str(item_code or "").strip(), "TICKET")


def _title_place(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return raw
    if raw.isupper() and len(raw) <= 4:
        return raw
    return raw.title()


def _match_place_token(text: str) -> str | None:
    upper = text.upper()
    for token in sorted(PLACE_TOKENS, key=len, reverse=True):
        if token in upper:
            return PLACE_TOKENS[token]
    return None


def _is_skip_part(part: str) -> bool:
    cleaned = part.strip().upper()
    if not cleaned or len(cleaned) < 2:
        return True
    if cleaned in SKIP_PARTS:
        return True
    if PNR_RE.match(cleaned.replace(" ", "")):
        return True
    if re.match(r"^SIA-\d", cleaned):
        return True
    if re.match(r"^TBX-", cleaned):
        return True
    if re.match(r"^\d+$", cleaned):
        return True
    if re.match(r"^\(\d", cleaned):
        return True
    if re.search(r"\$\s*\d", cleaned):
        return True
    if re.search(r"\d+\s*PAX", cleaned):
        return True
    return False


def _destination_from_part(part: str) -> str | None:
    part = part.strip()
    if _is_skip_part(part):
        place = _match_place_token(part)
        return place
    place = _match_place_token(part)
    if place:
        return place
    words = [w for w in re.split(r"[\s/]+", part) if w]
    for w in words:
        place = _match_place_token(w)
        if place:
            return place
    return None


def _is_visa_label_part(part: str) -> bool:
    """Skip 'schengen visa' style segments; keep 'FRANCE' after the slash."""
    upper = part.upper()
    if "VISA" not in upper and "SCHENGEN" not in upper:
        return False
    return _match_place_token(part) in (None, "Schengen")


def parse_destination_from_note(note: str | None, item_code: str | None = None) -> str | None:
    note = (note or "").strip()
    if not note:
        return None

    parts = [p for p in re.split(r"[/\\|]", note) if p.strip()]
    # Destination often appears after the slash (e.g. "schengen visa/ FRANCE")
    for part in reversed(parts):
        if _is_visa_label_part(part):
            continue
        dest = _destination_from_part(part)
        if dest:
            return dest
    for part in parts:
        dest = _destination_from_part(part)
        if dest:
            return dest

    place = _match_place_token(note)
    if place:
        return place

    if ":" in note:
        head = note.split(":", 1)[0]
        dest = _match_place_token(head)
        if dest:
            return dest

    if "HOTEL" in note.upper():
        dest = _match_place_token(note)
        if dest:
            return dest

    if "SAW" in note.upper() and "TAKSIM" in note.upper():
        return "Istanbul"

    return None


def fallback_destination(item_code: str | None, note: str | None = None) -> str:
    code = str(item_code or "").strip()
    parsed = parse_destination_from_note(note, code)
    if parsed:
        return parsed
    defaults = {
        "10004": "Air travel",
        "10002": "Visa services",
        "10001": "Hotel",
        "10011": "Transfer",
        "10003": "Transfer",
        "10015": "Package",
        "10007": "Insurance",
        "10005": "Package",
    }
    return defaults.get(code, ITEM_LABELS.get(code, "Travel"))


def pick_main_destination(line_destinations: list[str | None]) -> str | None:
    generics = {
        "Air travel",
        "Visa services",
        "Hotel",
        "Transfer",
        "Package",
        "Insurance",
        "Travel",
        "Ticket",
        "Package / Activities",
    }
    for d in line_destinations:
        if d and d not in generics:
            return d
    for d in line_destinations:
        if d:
            return d
    return None
