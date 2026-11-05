"""Farmer source backed by a CSV or Excel sheet kept outside git (real farmer data never goes in the repo).

Columns follow the client's "Prototype Farmer Data Requirements" sheet: Farmer ID, Farmer Name, Mobile Number,
Village, District, State, Preferred Calling Language, Call Consent. Optional: Active, Latitude, Longitude.
Header case, spaces and underscores do not matter. Errors name the row and farmer ID, never the phone number.
"""
from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

from ..contracts import FarmerContext, Language

_ALIASES = {
    "farmer_id": ("farmerid", "id"),
    "name": ("farmername", "name"),
    "phone": ("mobilenumber", "mobile", "phone", "phonenumber"),
    "village": ("village",),
    "district": ("district",),
    "state": ("state",),
    "language": ("preferredcallinglanguage", "language"),
    "consent": ("callconsent", "consent"),
    "active": ("active",),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lon", "lng"),
}
_REQUIRED = ("farmer_id", "name", "phone", "language", "consent")
_LANG = {"hindi": Language.HI, "hi": Language.HI, "hiin": Language.HI, "हिंदी": Language.HI, "हिन्दी": Language.HI,
         "english": Language.EN, "en": Language.EN, "enin": Language.EN,
         "kannada": Language.KN, "kn": Language.KN, "knin": Language.KN, "ಕನ್ನಡ": Language.KN,
         "telugu": Language.TE, "te": Language.TE, "tein": Language.TE, "తెలుగు": Language.TE}
_YES = {"yes", "y", "true", "1", "agreed", "consented", "given"}
_NO = {"no", "n", "false", "0", "inactive"}


def _key(header: object) -> str:
    return re.sub(r"[\s_\-]+", "", str(header or "")).lower()


def _text(v: object) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)                       # Excel stores mobile numbers as numbers
    return "" if v is None else str(v).strip()


def _read_rows(path: Path) -> list[list[object]]:
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl  # only needed for Excel files
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
        finally:
            wb.close()
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [list(r) for r in csv.reader(fh)]


def load_farmers(path: str | Path, geocoder=None, matches: dict[str, str] | None = None) -> list[FarmerContext]:
    """geocoder(village, district, state) -> Place | None fills coordinates the sheet leaves empty.
    matches, if given, receives farmer_id -> matched place description for a human to check."""
    path = Path(path)
    places: dict[tuple[str, str, str], object] = {}

    def locate(village: str, district: str, state: str):
        key = (village.lower(), district.lower(), state.lower())
        if key not in places:
            try:
                places[key] = geocoder(village, district, state)
            except Exception:  # lookup down: no coordinates, so no weather and no call for these farmers
                places[key] = None
        return places[key]

    rows = _read_rows(path)
    if not rows:
        raise ValueError(f"{path.name}: sheet is empty")
    headers = [_key(h) for h in rows[0]]
    col = {field: next((headers.index(a) for a in aliases if a in headers), None) for field, aliases in _ALIASES.items()}
    missing = [f for f in _REQUIRED if col[f] is None]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    if col["village"] is None and col["district"] is None:
        raise ValueError(f"{path.name}: needs a Village or District column")

    farmers: dict[str, FarmerContext] = {}
    for n, row in enumerate(rows[1:], start=2):
        get = lambda f: _text(row[col[f]]) if col[f] is not None and col[f] < len(row) else ""  # noqa: E731
        if not any(_text(c) for c in row):
            continue
        fid = get("farmer_id")
        if not fid:
            raise ValueError(f"{path.name} row {n}: Farmer ID is empty")
        if fid in farmers:
            raise ValueError(f"{path.name} row {n}: Farmer ID {fid} appears twice")
        lang = _LANG.get(_key(get("language")))
        if lang is None:
            raise ValueError(f"{path.name} row {n} (farmer {fid}): language {get('language')!r} not supported; "
                             "use Hindi, Kannada, Telugu or English")
        try:
            lat, lon = float(get("latitude") or 0), float(get("longitude") or 0)
        except ValueError:
            raise ValueError(f"{path.name} row {n} (farmer {fid}): latitude/longitude is not a number") from None
        if matches is not None and (lat or lon):
            matches[fid] = f"{lat}, {lon} (from sheet)"
        elif geocoder is not None:
            place = locate(get("village"), get("district"), get("state"))
            if place is not None:
                lat, lon = place.latitude, place.longitude
            if matches is not None:
                matches[fid] = place.matched if place else "no confident match"
        farmers[fid] = FarmerContext(
            farmer_id=fid, display_name=get("name"), language=lang,
            place_name=get("village") or get("district"), latitude=lat, longitude=lon,
            consent=get("consent").lower() in _YES,                 # anything unclear counts as no consent
            active=get("active").lower() not in _NO,                # blank or missing column counts as active
            phone=re.sub(r"[\s\-()]", "", get("phone")),
        )
    return list(farmers.values())


class SheetFarmerSource:
    def __init__(self, path: str | Path, geocoder=None):
        self.matches: dict[str, str] = {}
        self._by_id = {f.farmer_id: f for f in load_farmers(path, geocoder, self.matches)}

    def list_callable_ids(self, call_date: date) -> list[str]:
        return list(self._by_id)

    def get_context(self, farmer_id: str) -> FarmerContext | None:
        return self._by_id.get(farmer_id)
