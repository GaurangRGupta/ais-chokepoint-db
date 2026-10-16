"""Turn an AIS envelope into a position, static identity, quarantine, or skip."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from adbms_project.ingest.envelope import (
    _as_int,
    extract_inner,
    extract_lat_lon,
    extract_mmsi,
    extract_motion,
    extract_valid_time,
    message_type,
)

POSITION_TYPES = frozenset(
    {
        "PositionReport",
        "StandardClassBPositionReport",
        "ExtendedClassBPositionReport",
    }
)
STATIC_TYPES = frozenset({"ShipStaticData", "StaticDataReport"})
SKIP_TYPES = frozenset({"SubscriptionConfirmation"})

# AIS sentinels and DBA quality rules.
MAX_SOG_KN = 80.0
SOG_UNAVAILABLE = 102.2
FUTURE_SKEW = timedelta(seconds=120)
TOO_OLD = timedelta(days=30)

IDENTITY_FIELDS = (
    "name",
    "ship_type",
    "callsign",
    "imo",
    "dim_bow_m",
    "dim_stern_m",
    "dim_port_m",
    "dim_starboard_m",
    "destination",
    "eta",
)


@dataclass(frozen=True)
class PositionRecord:
    mmsi: int
    lat: float
    lon: float
    sog_kn: float | None
    cog_deg: float | None
    heading_deg: int | None
    nav_status: int | None
    msg_type: str
    valid_time: datetime
    source: str
    payload_sha256: str
    envelope: dict[str, Any]


@dataclass(frozen=True)
class StaticRecord:
    mmsi: int
    name: str | None
    ship_type: int | None
    callsign: str | None
    imo: int | None
    dim_bow_m: int | None
    dim_stern_m: int | None
    dim_port_m: int | None
    dim_starboard_m: int | None
    destination: str | None
    eta: str | None
    valid_time: datetime
    source: str
    payload_sha256: str
    envelope: dict[str, Any]


@dataclass(frozen=True)
class QuarantineRecord:
    reason: str
    source: str
    envelope: dict[str, Any]


Classified = PositionRecord | StaticRecord | QuarantineRecord | None


def payload_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def classify_frame(
    envelope: dict[str, Any],
    raw: bytes,
    source: str,
    now: datetime,
) -> Classified:
    kind = message_type(envelope)
    if kind in SKIP_TYPES:
        return None
    if not kind:
        return QuarantineRecord("unknown_message_type", source, envelope)
    digest = payload_sha256(raw)
    if kind in POSITION_TYPES:
        return _classify_position(envelope, kind, source, digest, now)
    if kind in STATIC_TYPES:
        return _classify_static(envelope, source, digest, now)
    return None


def static_identity_tuple(record: StaticRecord | dict[str, Any]) -> tuple[object, ...]:
    if isinstance(record, StaticRecord):
        return tuple(getattr(record, name) for name in IDENTITY_FIELDS)
    return tuple(record.get(name) for name in IDENTITY_FIELDS)


def merge_static(existing: dict[str, Any], incoming: StaticRecord) -> StaticRecord:
    """Partial StaticDataReport updates keep previous non-null identity fields."""
    values = {
        name: _coalesce(getattr(incoming, name), existing.get(name)) for name in IDENTITY_FIELDS
    }
    return StaticRecord(
        mmsi=incoming.mmsi,
        valid_time=incoming.valid_time,
        source=incoming.source,
        payload_sha256=incoming.payload_sha256,
        envelope=incoming.envelope,
        **values,
    )


def _classify_position(
    envelope: dict[str, Any],
    kind: str,
    source: str,
    digest: str,
    now: datetime,
) -> PositionRecord | QuarantineRecord:
    mmsi = extract_mmsi(envelope)
    if mmsi is None:
        return QuarantineRecord("missing_mmsi", source, envelope)
    lat, lon = extract_lat_lon(envelope)
    if lat is None or lon is None:
        return QuarantineRecord("missing_coordinates", source, envelope)
    if lat == 0.0 and lon == 0.0:
        return QuarantineRecord("bad_coordinates", source, envelope)
    if lat < -90.0 or lat > 90.0 or lon < -180.0 or lon > 180.0:
        return QuarantineRecord("bad_coordinates", source, envelope)
    if abs(lat - 91.0) < 1e-6 or abs(lon - 181.0) < 1e-6:
        return QuarantineRecord("bad_coordinates", source, envelope)
    valid_time = extract_valid_time(envelope)
    if valid_time is None:
        return QuarantineRecord("missing_valid_time", source, envelope)
    if valid_time > now + FUTURE_SKEW:
        return QuarantineRecord("future_valid_time", source, envelope)
    if valid_time < now - TOO_OLD:
        return QuarantineRecord("valid_time_too_old", source, envelope)
    sog, cog, heading, nav = extract_motion(envelope)
    sog = _clean_sog(sog)
    if sog is not None and (sog < 0.0 or sog > MAX_SOG_KN):
        return QuarantineRecord("impossible_speed", source, envelope)
    return PositionRecord(
        mmsi=mmsi,
        lat=lat,
        lon=lon,
        sog_kn=sog,
        cog_deg=_clean_cog(cog),
        heading_deg=_clean_heading(heading),
        nav_status=nav,
        msg_type=kind,
        valid_time=valid_time,
        source=source,
        payload_sha256=digest,
        envelope=envelope,
    )


def _classify_static(
    envelope: dict[str, Any],
    source: str,
    digest: str,
    now: datetime,
) -> StaticRecord | QuarantineRecord:
    mmsi = extract_mmsi(envelope)
    if mmsi is None:
        return QuarantineRecord("missing_mmsi", source, envelope)
    valid_time = extract_valid_time(envelope)
    if valid_time is None:
        return QuarantineRecord("missing_valid_time", source, envelope)
    if valid_time > now + FUTURE_SKEW:
        return QuarantineRecord("future_valid_time", source, envelope)
    if valid_time < now - TOO_OLD:
        return QuarantineRecord("valid_time_too_old", source, envelope)
    fields = extract_static_fields(envelope)
    return StaticRecord(
        mmsi=mmsi,
        valid_time=valid_time,
        source=source,
        payload_sha256=digest,
        envelope=envelope,
        **fields,
    )


def extract_static_fields(envelope: dict[str, Any]) -> dict[str, Any]:
    inner = extract_inner(envelope)
    kind = message_type(envelope)
    fields: dict[str, Any] = {name: None for name in IDENTITY_FIELDS}
    if kind == "ShipStaticData":
        fields["name"] = _clean_text(inner.get("Name"))
        fields["ship_type"] = _zero_none(_as_int(inner.get("Type")))
        fields["callsign"] = _clean_text(inner.get("CallSign"))
        fields["imo"] = _zero_none(_as_int(inner.get("ImoNumber")))
        _apply_dimension(fields, inner.get("Dimension"))
        fields["destination"] = _clean_text(inner.get("Destination"))
        fields["eta"] = format_eta(inner.get("Eta"))
        return fields
    if kind == "StaticDataReport":
        report_a = inner.get("ReportA") if isinstance(inner.get("ReportA"), dict) else {}
        report_b = inner.get("ReportB") if isinstance(inner.get("ReportB"), dict) else {}
        part = inner.get("PartNumber")
        if part == 0 or (report_a and part != 1):
            fields["name"] = _clean_text(report_a.get("Name"))
        if part == 1 or (report_b and part != 0):
            fields["ship_type"] = _zero_none(
                _as_int(report_b.get("ShipType", report_b.get("Type")))
            )
            fields["callsign"] = _clean_text(report_b.get("CallSign"))
            _apply_dimension(fields, report_b.get("Dimension"))
        return fields
    return fields


def format_eta(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    month = _as_int(value.get("Month"))
    day = _as_int(value.get("Day"))
    hour = _as_int(value.get("Hour"))
    minute = _as_int(value.get("Minute"))
    if month is None or day is None or hour is None or minute is None:
        return None
    if month <= 0 or day <= 0 or month > 12 or day > 31:
        return None
    if hour >= 24 or minute >= 60 or hour < 0 or minute < 0:
        return None
    return f"{month:02d}-{day:02d} {hour:02d}:{minute:02d}"


def _apply_dimension(fields: dict[str, Any], dimension: object) -> None:
    if not isinstance(dimension, dict):
        return
    fields["dim_bow_m"] = _as_int(dimension.get("A"))
    fields["dim_stern_m"] = _as_int(dimension.get("B"))
    fields["dim_port_m"] = _as_int(dimension.get("C"))
    fields["dim_starboard_m"] = _as_int(dimension.get("D"))


def _clean_sog(sog: float | None) -> float | None:
    if sog is None:
        return None
    if sog >= SOG_UNAVAILABLE:
        return None
    return sog


def _clean_cog(cog: float | None) -> float | None:
    if cog is None:
        return None
    if cog < 0.0 or cog >= 359.95:
        return None
    return cog


def _clean_heading(heading: int | None) -> int | None:
    if heading is None:
        return None
    if heading < 0 or heading > 359:
        return None
    return heading


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or set(text) <= {"@"}:
        return None
    return text.rstrip("@").strip() or None


def _zero_none(value: int | None) -> int | None:
    if value is None or value == 0:
        return None
    return value


def _coalesce(incoming: object, existing: object) -> object:
    return incoming if incoming is not None else existing
