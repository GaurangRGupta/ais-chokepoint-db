"""Parse AISStream / Open Waters envelopes. Never log raw JSON that might hold a key."""

from __future__ import annotations

from typing import Any

import orjson


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


def extract_mmsi(envelope: dict[str, Any]) -> int | None:
    meta = envelope.get("MetaData") or {}
    if isinstance(meta, dict):
        for key in ("MMSI", "mmsi", "UserID"):
            parsed = _as_mmsi(meta.get(key))
            if parsed is not None:
                return parsed
    message = envelope.get("Message")
    if isinstance(message, dict):
        for inner in message.values():
            if isinstance(inner, dict):
                parsed = _as_mmsi(inner.get("UserID") or inner.get("MMSI"))
                if parsed is not None:
                    return parsed
    return None


def extract_lat_lon(envelope: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = lon = None
    meta = envelope.get("MetaData") or {}
    if isinstance(meta, dict):
        lat = _as_float(meta.get("Latitude", meta.get("latitude")))
        lon = _as_float(meta.get("Longitude", meta.get("longitude")))
    message = envelope.get("Message")
    if isinstance(message, dict):
        for inner in message.values():
            if not isinstance(inner, dict):
                continue
            if lat is None:
                lat = _as_float(inner.get("Latitude", inner.get("latitude")))
            if lon is None:
                lon = _as_float(inner.get("Longitude", inner.get("longitude")))
    return lat, lon


def compression_flag(envelope: dict[str, Any]) -> bool | None:
    message = envelope.get("Message")
    if not isinstance(message, dict):
        return None
    inner = message.get("SubscriptionConfirmation") or message
    if isinstance(inner, dict) and "CompressionEnabled" in inner:
        return bool(inner["CompressionEnabled"])
    return None


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
