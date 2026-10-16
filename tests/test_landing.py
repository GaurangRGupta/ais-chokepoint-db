import gzip
from datetime import datetime, timezone

from adbms_project.ingest.landing import LandingZone, blob_name


def test_blob_name_utc_hour() -> None:
    when = datetime(2026, 10, 17, 8, 15, tzinfo=timezone.utc)
    assert blob_name(when) == "raw/ais/2026/10/17/08.jsonl.gz"


def test_flush_gzip_roundtrip() -> None:
    store: dict[str, bytes] = {}
    zone = LandingZone(store.__setitem__)
    when = datetime(2026, 10, 17, 8, 1, tzinfo=timezone.utc)
    zone.append(when, b'{"MessageType":"PositionReport"}')
    zone.append(when, b'{"MessageType":"ShipStaticData"}')
    zone.flush()
    name = "raw/ais/2026/10/17/08.jsonl.gz"
    assert name in store
    text = gzip.decompress(store[name]).decode("utf-8")
    assert text.splitlines() == [
        '{"MessageType":"PositionReport"}',
        '{"MessageType":"ShipStaticData"}',
    ]


def test_hour_change_writes_previous_blob() -> None:
    store: dict[str, bytes] = {}
    zone = LandingZone(store.__setitem__)
    zone.append(datetime(2026, 10, 17, 8, 59, tzinfo=timezone.utc), b'{"h":8}')
    zone.append(datetime(2026, 10, 17, 9, 1, tzinfo=timezone.utc), b'{"h":9}')
    zone.flush()
    assert "raw/ais/2026/10/17/08.jsonl.gz" in store
    assert "raw/ais/2026/10/17/09.jsonl.gz" in store
    assert gzip.decompress(store["raw/ais/2026/10/17/08.jsonl.gz"]) == b'{"h":8}\n'
    assert gzip.decompress(store["raw/ais/2026/10/17/09.jsonl.gz"]) == b'{"h":9}\n'
