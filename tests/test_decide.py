from adbms_project.ingest.decide import SpikeStats, decide
from adbms_project.ingest.envelope import extract_lat_lon, extract_mmsi, parse_frame


def _stats(**kwargs: object) -> SpikeStats:
    stats = SpikeStats(source="aisstream", url="wss://example", box_name="singapore")
    for key, value in kwargs.items():
        setattr(stats, key, value)
    return stats


def test_go_singapore() -> None:
    stats = _stats(duration_s=600, confirmation=True, distinct_mmsi=set(range(30)))
    stats.messages_by_type["PositionReport"] = 1200
    decision, _ = decide(stats, used_fallback=False)
    assert decision == "go_singapore"


def test_shrink_on_hot_stream() -> None:
    stats = _stats(duration_s=600, confirmation=True, distinct_mmsi=set(range(50)))
    stats.messages_by_type["PositionReport"] = 30_000
    decision, _ = decide(stats, used_fallback=False)
    assert decision == "shrink"


def test_fallback_when_primary_empty() -> None:
    stats = _stats(duration_s=300, confirmation=True)
    decision, _ = decide(stats, used_fallback=False)
    assert decision == "fallback"


def test_abort_when_both_empty() -> None:
    stats = _stats(duration_s=300, confirmation=True)
    decision, _ = decide(stats, used_fallback=True)
    assert decision == "abort_source_family"


def test_parse_position_envelope() -> None:
    raw = b"""{
      "MessageType": "PositionReport",
      "MetaData": {"MMSI": 563000000, "Latitude": 1.26, "Longitude": 103.85},
      "Message": {"PositionReport": {"UserID": 563000000, "Latitude": 1.26, "Longitude": 103.85}}
    }"""
    envelope = parse_frame(raw)
    assert extract_mmsi(envelope) == 563000000
    assert extract_lat_lon(envelope) == (1.26, 103.85)
