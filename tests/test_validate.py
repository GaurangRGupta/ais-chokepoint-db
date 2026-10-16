from datetime import datetime, timezone

import orjson

from adbms_project.ingest.envelope import extract_valid_time, parse_ais_time
from adbms_project.ingest.validate import (
    PositionRecord,
    QuarantineRecord,
    StaticRecord,
    classify_frame,
    extract_static_fields,
    merge_static,
)

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def _raw(envelope: dict) -> bytes:
    return orjson.dumps(envelope)


def _position(**meta_extra: object) -> dict:
    meta = {
        "MMSI": 563000000,
        "latitude": 1.26,
        "longitude": 103.85,
        "time_utc": "2026-10-17 12:00:00.000000000 +0000 UTC",
    }
    meta.update(meta_extra)
    return {
        "MessageType": "PositionReport",
        "MetaData": meta,
        "Message": {
            "PositionReport": {
                "UserID": 563000000,
                "Latitude": meta["latitude"],
                "Longitude": meta["longitude"],
                "Sog": 12.4,
                "Cog": 86.7,
                "TrueHeading": 87,
                "NavigationalStatus": 0,
            }
        },
    }


def test_parse_go_time_utc() -> None:
    parsed = parse_ais_time("2026-07-12 12:00:00.000000000 +0000 UTC")
    assert parsed == datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)


def test_parse_iso_z() -> None:
    parsed = parse_ais_time("2026-07-13T10:00:00Z")
    assert parsed == datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)


def test_extract_valid_time_from_metadata() -> None:
    envelope = _position()
    assert extract_valid_time(envelope) == NOW


def test_good_position() -> None:
    envelope = _position()
    result = classify_frame(envelope, _raw(envelope), "aisstream", NOW)
    assert isinstance(result, PositionRecord)
    assert result.mmsi == 563000000
    assert result.lat == 1.26
    assert result.lon == 103.85
    assert result.sog_kn == 12.4
    assert result.heading_deg == 87
    assert result.msg_type == "PositionReport"


def test_skip_subscription_confirmation() -> None:
    envelope = {
        "MessageType": "SubscriptionConfirmation",
        "Message": {"SubscriptionConfirmation": {"CompressionEnabled": True}},
    }
    assert classify_frame(envelope, _raw(envelope), "aisstream", NOW) is None


def test_quarantine_bad_latitude() -> None:
    envelope = _position(latitude=91.0)
    result = classify_frame(envelope, _raw(envelope), "aisstream", NOW)
    assert isinstance(result, QuarantineRecord)
    assert result.reason == "bad_coordinates"


def test_quarantine_null_island() -> None:
    envelope = _position(latitude=0.0, longitude=0.0)
    result = classify_frame(envelope, _raw(envelope), "aisstream", NOW)
    assert isinstance(result, QuarantineRecord)
    assert result.reason == "bad_coordinates"


def test_unavailable_sog_is_null_not_quarantine() -> None:
    envelope = _position()
    envelope["Message"]["PositionReport"]["Sog"] = 102.3
    result = classify_frame(envelope, _raw(envelope), "aisstream", NOW)
    assert isinstance(result, PositionRecord)
    assert result.sog_kn is None


def test_impossible_speed_quarantine() -> None:
    envelope = _position()
    envelope["Message"]["PositionReport"]["Sog"] = 90.0
    result = classify_frame(envelope, _raw(envelope), "aisstream", NOW)
    assert isinstance(result, QuarantineRecord)
    assert result.reason == "impossible_speed"


def test_heading_511_is_null() -> None:
    envelope = _position()
    envelope["Message"]["PositionReport"]["TrueHeading"] = 511
    result = classify_frame(envelope, _raw(envelope), "aisstream", NOW)
    assert isinstance(result, PositionRecord)
    assert result.heading_deg is None


def test_future_valid_time_quarantine() -> None:
    envelope = _position(time_utc="2026-10-17 12:10:00.000000000 +0000 UTC")
    result = classify_frame(envelope, _raw(envelope), "aisstream", NOW)
    assert isinstance(result, QuarantineRecord)
    assert result.reason == "future_valid_time"


def test_ship_static_data() -> None:
    envelope = {
        "MessageType": "ShipStaticData",
        "MetaData": {
            "MMSI": 563000000,
            "time_utc": "2026-10-17 12:00:00.000000000 +0000 UTC",
        },
        "Message": {
            "ShipStaticData": {
                "UserID": 563000000,
                "ImoNumber": 1234567,
                "CallSign": "TESTCS",
                "Name": "TEST SHIP",
                "Type": 70,
                "Dimension": {"A": 50, "B": 20, "C": 5, "D": 6},
                "Destination": "SINGAPORE",
                "Eta": {"Month": 10, "Day": 18, "Hour": 8, "Minute": 0},
            }
        },
    }
    result = classify_frame(envelope, _raw(envelope), "aisstream", NOW)
    assert isinstance(result, StaticRecord)
    assert result.name == "TEST SHIP"
    assert result.ship_type == 70
    assert result.imo == 1234567
    assert result.dim_bow_m == 50
    assert result.eta == "10-18 08:00"


def test_static_data_report_part_a() -> None:
    envelope = {
        "MessageType": "StaticDataReport",
        "MetaData": {
            "MMSI": 563000000,
            "time_utc": "2026-10-17 12:00:00.000000000 +0000 UTC",
        },
        "Message": {
            "StaticDataReport": {
                "UserID": 563000000,
                "PartNumber": 0,
                "ReportA": {"UserID": 563000000, "Valid": True, "Name": "PART A NAME"},
            }
        },
    }
    fields = extract_static_fields(envelope)
    assert fields["name"] == "PART A NAME"
    assert fields["ship_type"] is None


def test_merge_static_keeps_previous_fields() -> None:
    incoming_env = {
        "MessageType": "StaticDataReport",
        "MetaData": {
            "MMSI": 563000000,
            "time_utc": "2026-10-17 12:00:00.000000000 +0000 UTC",
        },
        "Message": {"StaticDataReport": {"PartNumber": 0, "ReportA": {"Name": "NEW"}}},
    }
    incoming = classify_frame(incoming_env, _raw(incoming_env), "aisstream", NOW)
    assert isinstance(incoming, StaticRecord)
    merged = merge_static(
        {
            "name": "OLD",
            "ship_type": 70,
            "callsign": "AB",
            "imo": 1,
            "dim_bow_m": 10,
            "dim_stern_m": 10,
            "dim_port_m": 2,
            "dim_starboard_m": 2,
            "destination": "PORT",
            "eta": "10-18 08:00",
        },
        incoming,
    )
    assert merged.name == "NEW"
    assert merged.ship_type == 70
    assert merged.callsign == "AB"
