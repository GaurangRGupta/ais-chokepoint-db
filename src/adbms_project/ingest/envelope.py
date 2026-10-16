"""Parse AISStream / Open Waters envelopes. Never log raw JSON that might hold a key."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import orjson

# AISStream MetaData.time_utc is often Go's time.String(), not ISO-8601.
_FRAC_RE = re.compile(r"\.(\d+)")
_OFFSET_SPACE_RE = re.compile(r"\s+([+-])(\d{2}):?(\d{2})$")
_OFFSET_NOSPACE_RE = re.compile(r"([+-])(\d{2})(\d{2})$")


def parse_frame(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    payload = orjson.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("frame is not a JSON object")
    return payload


def message_type(envelope: dict[str, Any]) -> str:
    value = envelope.get("MessageType")
    return str(value) if value is not None else ""


def extract_inner(envelope: dict[str, Any]) -> dict[str, Any]:
    message = envelope.get("Message")
    if not isinstance(message, dict):
        return {}
    kind = message_type(envelope)
    if kind and isinstance(message.get(kind), dict):
        return message[kind]
    if len(message) == 1:
        only = next(iter(message.values()))
        if isinstance(only, dict):
            return only
    return {}


def extract_mmsi(envelope: dict[str, Any]) -> int | None:
    meta = envelope.get("MetaData") or {}
    if isinstance(meta, dict):
        for key in ("MMSI", "mmsi", "UserID"):
            parsed = _as_mmsi(meta.get(key))
            if parsed is not None:
                return parsed
    inner = extract_inner(envelope)
    parsed = _as_mmsi(inner.get("UserID") or inner.get("MMSI"))
    if parsed is not None:
        return parsed
    message = envelope.get("Message")
    if isinstance(message, dict):
        for nested in message.values():
            if isinstance(nested, dict):
                parsed = _as_mmsi(nested.get("UserID") or nested.get("MMSI"))
                if parsed is not None:
                    return parsed
    return None


def extract_lat_lon(envelope: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = lon = None
    meta = envelope.get("MetaData") or {}
    if isinstance(meta, dict):
        lat = _as_float(meta.get("Latitude", meta.get("latitude")))
        lon = _as_float(meta.get("Longitude", meta.get("longitude")))
    inner = extract_inner(envelope)
    if lat is None:
        lat = _as_float(inner.get("Latitude", inner.get("latitude")))
    if lon is None:
        lon = _as_float(inner.get("Longitude", inner.get("longitude")))
    return lat, lon


def extract_valid_time(envelope: dict[str, Any]) -> datetime | None:
    meta = envelope.get("MetaData") or {}
    if not isinstance(meta, dict):
        return None
    for key in ("time_utc", "TimeUTC", "time", "Time"):
        parsed = parse_ais_time(meta.get(key))
        if parsed is not None:
            return parsed
    return None


def extract_motion(
    envelope: dict[str, Any],
) -> tuple[float | None, float | None, int | None, int | None]:
    """Return raw SOG, COG, true heading, navigational status, including AIS sentinels."""
    inner = extract_inner(envelope)
    sog = _as_float(inner.get("Sog", inner.get("sog")))
    cog = _as_float(inner.get("Cog", inner.get("cog")))
    heading = _as_int(inner.get("TrueHeading", inner.get("true_heading")))
    nav = _as_int(inner.get("NavigationalStatus", inner.get("navigational_status")))
    return sog, cog, heading, nav


def compression_flag(envelope: dict[str, Any]) -> bool | None:
    message = envelope.get("Message")
    if not isinstance(message, dict):
        return None
    inner = message.get("SubscriptionConfirmation") or message
    if isinstance(inner, dict) and "CompressionEnabled" in inner:
        return bool(inner["CompressionEnabled"])
    return None


def parse_ais_time(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if text.endswith(" UTC"):
        text = text[:-4].rstrip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    text = _OFFSET_SPACE_RE.sub(r"\1\2:\3", text)
    text = _OFFSET_NOSPACE_RE.sub(r"\1\2:\3", text)

    def _trim_frac(match: re.Match[str]) -> str:
        return "." + match.group(1)[:6].ljust(6, "0")

    text = _FRAC_RE.sub(_trim_frac, text, count=1)
    if "T" not in text[:20]:
        text = text.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_mmsi(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _as_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _as_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
