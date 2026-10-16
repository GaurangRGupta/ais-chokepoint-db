from datetime import datetime, timedelta, timezone

from adbms_project.events.detect import Sample, detect_dwells, detect_transits

T0 = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def _s(
    minutes: float,
    *,
    mmsi: int = 563000000,
    in_east: bool = False,
    in_west: bool = False,
    in_anchorage: bool = False,
    sog: float | None = 10.0,
) -> Sample:
    return Sample(
        mmsi=mmsi,
        valid_time=T0 + timedelta(minutes=minutes),
        in_east=in_east,
        in_west=in_west,
        in_anchorage=in_anchorage,
        sog_kn=sog,
        lon=103.85,
        lat=1.20,
    )


def test_two_in_two_out_makes_westbound_transit() -> None:
    samples = [
        _s(0, in_west=False),
        _s(1, in_west=True),
        _s(2, in_west=True),
        _s(8, in_west=True),
        _s(9, in_west=False),
        _s(10, in_west=False),
    ]
    found = detect_transits(samples)
    assert len(found) == 1
    assert found[0].direction == "west"
    assert found[0].enter_time == T0 + timedelta(minutes=1)
    assert found[0].leave_time == T0 + timedelta(minutes=9)


def test_single_inside_point_is_flicker() -> None:
    samples = [_s(0), _s(1, in_east=True), _s(2)]
    assert detect_transits(samples) == []


def test_short_transit_under_two_minutes_dropped() -> None:
    samples = [
        _s(0, in_east=True),
        _s(0.5, in_east=True),
        _s(1, in_east=False),
        _s(1.5, in_east=False),
    ]
    assert detect_transits(samples) == []


def test_open_transit_kept_if_already_two_minutes() -> None:
    samples = [_s(0, in_west=True), _s(1, in_west=True), _s(20, in_west=True)]
    found = detect_transits(samples, now=T0 + timedelta(minutes=21))
    assert len(found) == 1
    assert found[0].leave_time is None
    assert found[0].direction == "west"


def test_overlap_east_and_west_counts_as_outside() -> None:
    samples = [
        _s(0, in_east=True),
        _s(1, in_east=True),
        _s(2, in_east=True, in_west=True),
        _s(3, in_east=True, in_west=True),
    ]
    found = detect_transits(samples)
    assert len(found) == 1
    assert found[0].leave_time == T0 + timedelta(minutes=2)


def test_dwell_starts_after_fifteen_slow_minutes() -> None:
    samples = [_s(i, in_anchorage=True, sog=0.2) for i in range(0, 20)]
    found = detect_dwells(samples, now=T0 + timedelta(minutes=20))
    assert len(found) == 1
    assert found[0].end_time is None
    assert found[0].min_sog == 0.2


def test_dwell_ends_when_speed_rises() -> None:
    samples = [_s(i, in_anchorage=True, sog=0.2) for i in range(0, 16)]
    samples.append(_s(17, in_anchorage=True, sog=3.0))
    found = detect_dwells(samples)
    assert len(found) == 1
    assert found[0].end_time == T0 + timedelta(minutes=17)


def test_moving_in_anchorage_is_not_a_dwell() -> None:
    samples = [_s(i, in_anchorage=True, sog=4.0) for i in range(0, 20)]
    assert detect_dwells(samples) == []
