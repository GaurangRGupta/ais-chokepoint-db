"""Transit and dwell detection from ordered position samples. No database I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

MIN_TRANSIT = timedelta(minutes=2)
MIN_DWELL = timedelta(minutes=15)
DWELL_START_SOG_KN = 0.5
DWELL_END_SOG_KN = 1.0


@dataclass(frozen=True)
class Sample:
    mmsi: int
    valid_time: datetime
    in_east: bool
    in_west: bool
    in_anchorage: bool
    sog_kn: float | None
    lon: float
    lat: float
    ingest_time: datetime | None = None


@dataclass(frozen=True)
class Transit:
    mmsi: int
    direction: str
    enter_time: datetime
    leave_time: datetime | None
    enter_lon: float
    enter_lat: float
    leave_lon: float | None
    leave_lat: float | None
    enter_ingest: datetime | None
    leave_ingest: datetime | None


@dataclass(frozen=True)
class Dwell:
    mmsi: int
    start_time: datetime
    end_time: datetime | None
    min_sog: float | None
    median_sog: float | None


def lane_of(sample: Sample) -> str | None:
    if sample.in_east and sample.in_west:
        return None
    if sample.in_east:
        return "east"
    if sample.in_west:
        return "west"
    return None


def detect_transits(samples: list[Sample], *, now: datetime | None = None) -> list[Transit]:
    """Two consecutive points in a lane opens a transit. Two consecutive outside closes it."""
    by_mmsi: dict[int, list[Sample]] = {}
    for sample in samples:
        by_mmsi.setdefault(sample.mmsi, []).append(sample)
    found: list[Transit] = []
    for mmsi, series in by_mmsi.items():
        ordered = sorted(series, key=lambda item: item.valid_time)
        found.extend(_transits_for_mmsi(mmsi, ordered, now=now))
    return found


def detect_dwells(samples: list[Sample], *, now: datetime | None = None) -> list[Dwell]:
    """Inside anchorage and SOG under 0.5 kn for 15 minutes. End at 1.0 kn or leave."""
    by_mmsi: dict[int, list[Sample]] = {}
    for sample in samples:
        by_mmsi.setdefault(sample.mmsi, []).append(sample)
    found: list[Dwell] = []
    for mmsi, series in by_mmsi.items():
        ordered = sorted(series, key=lambda item: item.valid_time)
        found.extend(_dwells_for_mmsi(mmsi, ordered, now=now))
    return found


def _transits_for_mmsi(
    mmsi: int, series: list[Sample], *, now: datetime | None
) -> list[Transit]:
    out: list[Transit] = []
    consec_in = 0
    consec_out = 0
    pending: Sample | None = None
    pending_lane: str | None = None
    first_out: Sample | None = None
    open_tr: Transit | None = None

    def close_with(leave: Sample) -> None:
        nonlocal open_tr
        if open_tr is None:
            return
        duration = leave.valid_time - open_tr.enter_time
        if duration >= MIN_TRANSIT:
            out.append(
                Transit(
                    mmsi=open_tr.mmsi,
                    direction=open_tr.direction,
                    enter_time=open_tr.enter_time,
                    leave_time=leave.valid_time,
                    enter_lon=open_tr.enter_lon,
                    enter_lat=open_tr.enter_lat,
                    leave_lon=leave.lon,
                    leave_lat=leave.lat,
                    enter_ingest=open_tr.enter_ingest,
                    leave_ingest=leave.ingest_time,
                )
            )
        open_tr = None

    for sample in series:
        lane = lane_of(sample)
        if open_tr is not None and lane is not None and lane != open_tr.direction:
            lane = None
        if lane is not None:
            consec_in += 1
            consec_out = 0
            first_out = None
            if consec_in == 1:
                pending = sample
                pending_lane = lane
            if consec_in >= 2 and open_tr is None and pending is not None and pending_lane:
                open_tr = Transit(
                    mmsi=mmsi,
                    direction=pending_lane,
                    enter_time=pending.valid_time,
                    leave_time=None,
                    enter_lon=pending.lon,
                    enter_lat=pending.lat,
                    leave_lon=None,
                    leave_lat=None,
                    enter_ingest=pending.ingest_time,
                    leave_ingest=None,
                )
        else:
            consec_out += 1
            consec_in = 0
            pending = None
            pending_lane = None
            if consec_out == 1:
                first_out = sample
            if consec_out >= 2 and open_tr is not None and first_out is not None:
                close_with(first_out)

    if open_tr is not None:
        end = now or series[-1].valid_time
        if end - open_tr.enter_time >= MIN_TRANSIT:
            out.append(open_tr)
    return out


def _dwells_for_mmsi(mmsi: int, series: list[Sample], *, now: datetime | None) -> list[Dwell]:
    out: list[Dwell] = []
    candidate_start: Sample | None = None
    sogs: list[float] = []
    open_dw: tuple[datetime, list[float]] | None = None

    def is_slow(sample: Sample) -> bool:
        return sample.in_anchorage and sample.sog_kn is not None and sample.sog_kn < DWELL_START_SOG_KN

    def is_end(sample: Sample) -> bool:
        if not sample.in_anchorage:
            return True
        return sample.sog_kn is not None and sample.sog_kn >= DWELL_END_SOG_KN

    def emit_open(start: datetime, values: list[float], end: datetime | None) -> None:
        if not values:
            return
        ordered = sorted(values)
        median = ordered[len(ordered) // 2]
        out.append(
            Dwell(
                mmsi=mmsi,
                start_time=start,
                end_time=end,
                min_sog=min(values),
                median_sog=median,
            )
        )

    for sample in series:
        if open_dw is None:
            if is_slow(sample):
                if candidate_start is None:
                    candidate_start = sample
                    sogs = [sample.sog_kn] if sample.sog_kn is not None else []
                elif sample.sog_kn is not None:
                    sogs.append(sample.sog_kn)
                if candidate_start and sample.valid_time - candidate_start.valid_time >= MIN_DWELL:
                    open_dw = (candidate_start.valid_time, list(sogs))
                    candidate_start = None
            else:
                candidate_start = None
                sogs = []
            continue
        start, values = open_dw
        if sample.sog_kn is not None and sample.in_anchorage:
            values.append(sample.sog_kn)
            open_dw = (start, values)
        if is_end(sample):
            emit_open(start, values, sample.valid_time)
            open_dw = None
            candidate_start = None
            sogs = []

    if open_dw is not None:
        start, values = open_dw
        end_clock = now or series[-1].valid_time
        if end_clock - start >= MIN_DWELL:
            emit_open(start, values, None)
    return out
