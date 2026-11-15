"""Builds the written message (email) that follows a call. Pure: farmer name, place, weather and situation in, text out.

Decided 5 Nov 2026 (docs/DECISIONS.md): a fixed template with the four weather facts and no free text from the call. Sent
after a successful call, and after the last failed attempt or an unanswered or missed callback. WhatsApp and SMS could not
be used, so email carries it (15 Nov 2026); the template is English for every farmer. Farmers are our customers, so the
wording is polite, professional and short. The subject and the lead-in line change with the situation, see KINDS. Each message has a plain-text version and an HTML version with the Agrythm logo (sent as the inline image LOGO_CID).
"""
from __future__ import annotations

from html import escape

KIND_WEATHER = "weather"                      # the call went through: the weather facts
KIND_MISSED = "missed"                        # every attempt of the day went unanswered: we tried, plus the weather
KIND_CALLBACK_WEATHER = "callback_weather"    # the call the farmer asked for went through: the weather facts
KIND_CALLBACK_MISSED = "callback_missed"      # we called at the time the farmer asked for, nobody answered, no more chances

KINDS = (KIND_WEATHER, KIND_MISSED, KIND_CALLBACK_WEATHER, KIND_CALLBACK_MISSED)

LOGO_CID = "agrythm-logo"                     # <img src="cid:agrythm-logo"> in the HTML; the sender attaches the picture

_SUBJECT = {
    KIND_WEATHER: "Weather update for {place}",
    KIND_MISSED: "Weather update for {place} (we tried to call you)",
    KIND_CALLBACK_WEATHER: "Weather update for {place}",
    KIND_CALLBACK_MISSED: "Weather update for {place} (missed call at {time})",
}

# one short lead-in per situation, straight to the point
_LEAD = {
    KIND_WEATHER: "Thank you for speaking with us today. Here is today's weather update for {place}:",
    KIND_MISSED: "We tried to call you today but unfortunately could not reach you. Here is today's weather update for {place}:",
    KIND_CALLBACK_WEATHER: "Thank you for speaking with us at {time}. Here is today's weather update for {place}:",
    KIND_CALLBACK_MISSED: "We tried to call you back at {time}, as you requested, but unfortunately could not reach you. "
                          "Here is today's weather update for {place}:",
}

_SIGNOFF = ("Regards,", "Team Agrythm")
_FOOTER = "This is an automated message from Agrythm."

_FACTS = (("Temperature", "{tmin} to {tmax} degrees Celsius"), ("Wind speed", "up to {wind} km/h"),
          ("Chance of rain", "{rain} percent"), ("Humidity", "{humidity} percent"))

# the logo is teal and green: the page uses the same two colours
_TEAL, _GREEN, _INK, _MUTED, _BG = "#0f8f8a", "#1c6b4a", "#1f2937", "#6b7280", "#f3f7f6"


def _num(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f.is_integer() else f"{f:.1f}"


def _fields(name: str, place: str, weather: dict, callback_time: str) -> dict:
    return dict(name=name, place=place, time=callback_time, tmin=_num(weather.get("temp_min")),
                tmax=_num(weather.get("temp_max")), wind=_num(weather.get("wind")), rain=_num(weather.get("rain")),
                humidity=_num(weather.get("humidity")))


def build_email(name: str, place: str, weather: dict, kind: str, callback_time: str = "") -> tuple[str, str, str]:
    """(subject, plain text, html). weather: temp_min, temp_max, wind, rain, humidity as saved with the call result.
    callback_time: the time the farmer asked to be called, in 24-hour form such as 14:15 (callback kinds only).
    Only the four weather facts: no advice and nothing the farmer said on the call."""
    if kind not in KINDS:
        raise ValueError(f"unknown message kind {kind!r}")
    f = _fields(name, place, weather, callback_time)
    greeting = f"Dear {name},"
    lead = _LEAD[kind].format(**f)
    facts = [(label, value.format(**f)) for label, value in _FACTS]
    subject = _SUBJECT[kind].format(**f)

    text = "\n".join([greeting, "", lead, *(f"- {label}: {value}" for label, value in facts), "", *_SIGNOFF, "", _FOOTER])

    e = escape
    rows = "".join(
        f'<tr><td style="padding:10px 16px;font-size:14px;color:{_MUTED};border-top:1px solid #e3ece9">{e(label)}</td>'
        f'<td style="padding:10px 16px;font-size:15px;font-weight:600;color:{_INK};border-top:1px solid #e3ece9" align="right">{e(value)}</td></tr>'
        for label, value in facts)
    html = (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        f'<body style="margin:0;padding:0;background:{_BG};font-family:Segoe UI,Helvetica,Arial,sans-serif">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG}"><tr><td align="center" style="padding:24px 12px">'
        '<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e3ece9">'
        f'<tr><td style="padding:22px 28px;border-bottom:4px solid {_TEAL}"><table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        f'<td><img src="cid:{LOGO_CID}" width="56" height="56" alt="Agrythm" style="display:block;border:0"></td>'
        f'<td style="padding-left:14px;font-size:22px;font-weight:700;color:{_GREEN};letter-spacing:.3px">Agrythm</td></tr></table></td></tr>'
        '<tr><td style="padding:28px">'
        f'<p style="margin:0 0 14px;font-size:16px;font-weight:600;color:{_INK}">{e(greeting)}</p>'
        f'<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:{_INK}">{e(lead)}</p>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px;background:{_BG};border-radius:10px;border:1px solid #e3ece9">{rows}</table>'
        f'<p style="margin:0;font-size:15px;line-height:1.5;color:{_INK}">{e(_SIGNOFF[0])}<br><strong style="color:{_GREEN}">{e(_SIGNOFF[1])}</strong></p>'
        '</td></tr>'
        f'<tr><td style="padding:14px 28px;background:{_BG};font-size:12px;color:{_MUTED};text-align:center">{e(_FOOTER)}</td></tr>'
        '</table></td></tr></table></body></html>')
    return subject, text, html


def has_full_weather(weather: dict) -> bool:
    return all(weather.get(k) not in (None, "") for k in ("temp_min", "temp_max", "wind", "rain", "humidity"))
