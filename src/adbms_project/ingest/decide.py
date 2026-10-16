"""Day-1 spike pass / shrink / switch / fallback rules. No secrets."""

from __future__ import annotations

from dataclasses import dataclass, field


AIS_TYPES = frozenset(
    {
        "PositionReport",
        "StandardClassBPositionReport",
        "ExtendedClassBPositionReport",
        "ShipStaticData",
        "StaticDataReport",
    }
)


@dataclass
class SpikeStats:
    source: str
    url: str
    box_name: str
    duration_s: float = 0.0
    confirmation: bool = False
    compression_enabled: bool | None = None
    close_code: int | None = None
    close_reason: str = ""
    error: str = ""
    messages_by_type: dict[str, int] = field(default_factory=dict)
    distinct_mmsi: set[int] = field(default_factory=set)
    lat_min: float | None = None
    lat_max: float | None = None
    lon_min: float | None = None
    lon_max: float | None = None
    first_ais_after_s: float | None = None

    @property
    def ais_messages(self) -> int:
        return sum(n for t, n in self.messages_by_type.items() if t in AIS_TYPES)

    @property
    def mean_msg_per_s(self) -> float:
        if self.duration_s <= 0:
            return 0.0
        return self.ais_messages / self.duration_s

    def note_type(self, message_type: str) -> None:
        self.messages_by_type[message_type] = self.messages_by_type.get(message_type, 0) + 1

    def note_coords(self, lat: float | None, lon: float | None) -> None:
        if lat is None or lon is None:
            return
        self.lat_min = lat if self.lat_min is None else min(self.lat_min, lat)
        self.lat_max = lat if self.lat_max is None else max(self.lat_max, lat)
        self.lon_min = lon if self.lon_min is None else min(self.lon_min, lon)
        self.lon_max = lon if self.lon_max is None else max(self.lon_max, lon)


def decide(stats: SpikeStats, *, used_fallback: bool) -> tuple[str, str]:
    """Return (decision, reason) for the spike report."""
    if stats.ais_messages == 0:
        if used_fallback:
            return (
                "abort_source_family",
                "AISStream and Open Waters both delivered zero AIS application frames. Do not scrape apps. Do not buy a commercial API.",
            )
        return (
            "fallback",
            "Primary feed sent no AIS application frames. Retry Open Waters with the same box.",
        )
    if stats.mean_msg_per_s > 40:
        return (
            "shrink",
            "Mean rate over 40 messages per second. Shrink the box 0.10 degree of longitude east-west and rerun.",
        )
    if stats.duration_s >= 540 and len(stats.distinct_mmsi) < 15:
        return (
            "switch_gibraltar",
            "Fewer than 15 distinct MMSI in about 9+ minutes. Switch the primary box to Gibraltar.",
        )
    if stats.confirmation and len(stats.distinct_mmsi) >= 30 and stats.mean_msg_per_s < 40:
        return (
            "go_singapore",
            "Subscription confirmed, at least 30 distinct MMSI, and mean rate under 40 messages per second. Stay on Singapore and start schema.",
        )
    if len(stats.distinct_mmsi) >= 15:
        return (
            "go_singapore_weak",
            "Useful traffic but under 30 distinct MMSI in this window. Stay on Singapore, rerun 15 minutes, and start schema if the second run holds.",
        )
    return (
        "rerun",
        "Some AIS arrived but counts are too low to lock Singapore. Rerun 15 minutes before switching boxes.",
    )
