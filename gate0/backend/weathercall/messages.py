"""Builds the written message (email) that follows a call. Pure: farmer name, place, weather and situation in, text out.

Decided 5 Nov 2026 (docs/DECISIONS.md): a fixed template with the four weather facts and no free text from the call. Sent
after a successful call, and after the last failed attempt or an unanswered or missed callback. WhatsApp and SMS could not
be used, so email carries it (15 Nov 2026); the template is English for every farmer (team, 15 Nov). The subject and the
opening lines change with the situation, see KINDS.
"""
from __future__ import annotations

KIND_WEATHER = "weather"                      # the call went through: the weather facts
KIND_MISSED = "missed"                        # every attempt of the day went unanswered: we tried, plus the weather
KIND_CALLBACK_WEATHER = "callback_weather"    # the call the farmer asked for went through: the weather facts
KIND_CALLBACK_MISSED = "callback_missed"      # we called at the time the farmer asked for, nobody answered, no more chances

KINDS = (KIND_WEATHER, KIND_MISSED, KIND_CALLBACK_WEATHER, KIND_CALLBACK_MISSED)

_SUBJECT = {
    KIND_WEATHER: "Today's weather for {place}",
    KIND_MISSED: "We could not reach you today: weather for {place}",
    KIND_CALLBACK_WEATHER: "Your requested call back: weather for {place}",
    KIND_CALLBACK_MISSED: "We called you back at {time} but could not reach you: weather for {place}",
}

_OPENING = {
    KIND_WEATHER: [],
    KIND_MISSED: ["We tried to call you from Agrythm today but could not reach you."],
    KIND_CALLBACK_WEATHER: ["Thank you for taking our call back at the time you asked for."],
    KIND_CALLBACK_MISSED: ["You asked us to call you back at {time}. We called you at that time but could not reach you.",
                           "We will not call again today, so here is today's weather in writing."],
}


def _num(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f.is_integer() else f"{f:.1f}"


def build_email(name: str, place: str, weather: dict, kind: str, callback_time: str = "") -> tuple[str, str]:
    """(subject, body). weather: temp_min, temp_max, wind, rain, humidity as saved with the call result.
    callback_time: the time the farmer asked to be called, in 24-hour form such as 14:15 (callback kinds only).
    Only the four weather facts: no advice and nothing the farmer said on the call."""
    if kind not in KINDS:
        raise ValueError(f"unknown message kind {kind!r}")
    f = dict(name=name, place=place, time=callback_time)
    lines = [f"Hello {name},", ""]
    for text in _OPENING[kind]:
        lines.append(text.format(**f))
    if _OPENING[kind]:
        lines.append("")
    lines += [f"Here is today's weather for {place}:",
              f"- Temperature: {_num(weather.get('temp_min'))} to {_num(weather.get('temp_max'))} degrees Celsius",
              f"- Wind speed: up to {_num(weather.get('wind'))} km/h",
              f"- Chance of rain: {_num(weather.get('rain'))} percent",
              f"- Humidity: {_num(weather.get('humidity'))} percent",
              "",
              "This is an automated message from Agrythm. If you do not want these messages, please tell your Agrythm contact person."]
    return _SUBJECT[kind].format(**f), "\n".join(lines)


def has_full_weather(weather: dict) -> bool:
    return all(weather.get(k) not in (None, "") for k in ("temp_min", "temp_max", "wind", "rain", "humidity"))
