"""Day-1 AIS feed spike. Laptop only. Writes reports/day1_spike.md with no secrets."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import orjson
import websockets
from websockets.exceptions import ConnectionClosed

from adbms_project.ingest.boxes import (
    AIS_MESSAGE_TYPES,
    AISSTREAM_URL,
    BOX_LABELS,
    OPENWATERS_URL,
)
from adbms_project.ingest.decide import AIS_TYPES, SpikeStats, decide
from adbms_project.ingest.envelope import (
    compression_flag,
    extract_lat_lon,
    extract_mmsi,
    message_type,
    parse_frame,
)
from adbms_project.settings import Settings

_ROOT = Path(__file__).resolve().parents[3]
_REPORT = _ROOT / "reports" / "day1_spike.md"
_SILENCE_S = 300.0


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(description="10-minute AIS feed spike for Singapore Strait.")
    parser.add_argument("--duration", type=float, default=600.0, help="Seconds to listen (default 600).")
    parser.add_argument(
        "--box",
        choices=sorted(BOX_LABELS),
        default="singapore",
        help="Bounding box name.",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "aisstream", "aiscast"),
        default="auto",
        help="auto tries AISStream then Open Waters after 5 minutes of silence.",
    )
    args = parser.parse_args()
    asyncio.run(run_spike(duration_s=args.duration, box_name=args.box, source=args.source))


async def run_spike(*, duration_s: float, box_name: str, source: str) -> None:
    settings = Settings()
    box = BOX_LABELS[box_name]
    started = datetime.now(timezone.utc)
    print(
    print(f"spike start {started.isoformat()} box={box_name} duration={duration_s:.0f}s source={source}")

    if source == "aiscast":
        stats = await listen(
            url=OPENWATERS_URL,
            api_key=settings.require_openwaters_key(),
            source_name="aiscast",
            box_name=box_name,
            box=box,
            duration_s=duration_s,
            silence_abort_s=None,
        )
        used_fallback = True
        extra: list[SpikeStats] = []
    else:
        stats = await listen(
            url=AISSTREAM_URL,
            api_key=settings.require_aisstream_key(),
            source_name="aisstream",
            box_name=box_name,
            box=box,
            duration_s=duration_s,
            silence_abort_s=_SILENCE_S if source == "auto" else None,
        )
        extra = []
        used_fallback = False
        if source == "auto" and stats.ais_messages == 0:
            remaining = max(duration_s - stats.duration_s, 300.0)
            print(f"AISStream silent. Switching to Open Waters for {remaining:.0f}s.")
            fallback = await listen(
                url=OPENWATERS_URL,
                api_key=settings.require_openwaters_key(),
                source_name="aiscast",
                box_name=box_name,
                box=box,
                duration_s=remaining,
                silence_abort_s=None,
            )
            extra = [stats]
            stats = fallback
            used_fallback = True

    decision, reason = decide(stats, used_fallback=used_fallback)
    path = write_report(
        primary=stats,
        extra=extra,
        decision=decision,
        reason=reason,
        started=started,
        requested_s=duration_s,
        used_fallback=used_fallback,
    )
    print(f"decision={decision}")
    print(f"report={path}")


async def listen(
    *,
    url: str,
    api_key: str,
    source_name: str,
    box_name: str,
    box: list[list[list[float]]],
    duration_s: float,
    silence_abort_s: float | None,
) -> SpikeStats:
    stats = SpikeStats(source=source_name, url=url, box_name=box_name)
    subscribe = {
        "APIKey": api_key,
        "BoundingBoxes": box,
        "FilterMessageTypes": list(AIS_MESSAGE_TYPES),
    }
    t0 = time.monotonic()
    deadline = t0 + duration_s
    last_progress = t0
    print(f"connecting {source_name} (key not printed)")
    try:
        async with websockets.connect(
            url,
            compression="deflate",
            max_size=2**22,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=15,
        ) as ws:
            await ws.send(orjson.dumps(subscribe))
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if (
                    silence_abort_s is not None
                    and stats.ais_messages == 0
                    and (time.monotonic() - t0) >= silence_abort_s
                ):
                    print(f"no AIS frames after {silence_abort_s:.0f}s, leaving {source_name}")
                    break
                timeout = min(5.0, remaining)
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except TimeoutError:
                    continue
                try:
                    envelope = parse_frame(raw)
                except (orjson.JSONDecodeError, ValueError, TypeError):
                    stats.note_type("_parse_error")
                    continue
                kind = message_type(envelope) or "_unknown"
                stats.note_type(kind)
                elapsed = time.monotonic() - t0
                if kind == "SubscriptionConfirmation":
                    stats.confirmation = True
                    stats.compression_enabled = compression_flag(envelope)
                    print(f"SubscriptionConfirmation compression={stats.compression_enabled}")
                    continue
                if kind in AIS_TYPES:
                    if stats.first_ais_after_s is None:
                        stats.first_ais_after_s = elapsed
                    mmsi = extract_mmsi(envelope)
                    if mmsi is not None:
                        stats.distinct_mmsi.add(mmsi)
                    lat, lon = extract_lat_lon(envelope)
                    stats.note_coords(lat, lon)
                now = time.monotonic()
                if now - last_progress >= 30:
                    last_progress = now
                    print(
                        f"{elapsed:6.0f}s {source_name} ais={stats.ais_messages} "
                        f"mmsi={len(stats.distinct_mmsi)} rate={stats.ais_messages / max(elapsed, 1):.2f}/s"
                    )
    except ConnectionClosed as exc:
        stats.close_code = exc.code
        stats.close_reason = str(exc.reason or "")
        print(f"{source_name} closed code={exc.code}")
    except OSError as exc:
        stats.error = type(exc).__name__
        print(f"{source_name} network error: {type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001 - spike must always write a report
        stats.error = type(exc).__name__
        print(f"{source_name} error: {type(exc).__name__}")
    stats.duration_s = time.monotonic() - t0
    print(
        f"{source_name} done {stats.duration_s:.1f}s ais={stats.ais_messages} "
        f"distinct_mmsi={len(stats.distinct_mmsi)}"
    )
    return stats


def write_report(
    *,
    primary: SpikeStats,
    extra: list[SpikeStats],
    decision: str,
    reason: str,
    started: datetime,
    requested_s: float,
    used_fallback: bool,
) -> Path:
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    ended = datetime.now(timezone.utc)
    sections = [
        "# Day-1 AIS feed spike",
        "",
        f"Started (UTC): {started.isoformat()}",
        f"Ended (UTC): {ended.isoformat()}",
        f"Requested duration: {requested_s:.0f} seconds",
        f"Used Open Waters fallback: {'yes' if used_fallback else 'no'}",
        "",
        "No API keys, tokens, or connection strings are in this file.",
        "",
        "## Decision",
        "",
        f"**{decision}**",
        "",
        reason,
        "",
    ]
    for stats in [*extra, primary]:
        sections.extend(_stats_markdown(stats))
    sections.extend(
        [
            "## Pass rules used",
            "",
            "- Pass Singapore: SubscriptionConfirmation, at least 30 distinct MMSI in 10 minutes, mean AIS rate under 40 messages per second.",
            "- Shrink: mean rate over 40 messages per second.",
            "- Switch to Gibraltar: fewer than 15 distinct MMSI after about 9 minutes.",
            "- Fallback: zero AIS application frames on AISStream for 5 minutes.",
            "- Abort this source family: both AISStream and Open Waters empty.",
            "",
            "## Sources",
            "",
            "- AISStream documentation: https://aisstream.io/documentation/",
            "- Open Waters aiscast: https://openwaters.io/api/ais/",
            "",
        ]
    )
    _REPORT.write_text("\n".join(sections), encoding="utf-8")
    return _REPORT


def _stats_markdown(stats: SpikeStats) -> list[str]:
    types = ", ".join(f"{k}={v}" for k, v in sorted(stats.messages_by_type.items())) or "(none)"
    lat = _range(stats.lat_min, stats.lat_max)
    lon = _range(stats.lon_min, stats.lon_max)
    return [
        f"## Source `{stats.source}`",
        "",
        f"- WebSocket host: `{stats.url}`",
        f"- Box: `{stats.box_name}`",
        f"- Listen seconds: {stats.duration_s:.1f}",
        f"- SubscriptionConfirmation: {'yes' if stats.confirmation else 'no'}",
        f"- CompressionEnabled: {stats.compression_enabled}",
        f"- AIS application frames: {stats.ais_messages}",
        f"- Distinct MMSI: {len(stats.distinct_mmsi)}",
        f"- Mean AIS messages per second: {stats.mean_msg_per_s:.3f}",
        f"- First AIS frame after seconds: {stats.first_ais_after_s}",
        f"- Latitude range: {lat}",
        f"- Longitude range: {lon}",
        f"- Close code: {stats.close_code}",
        f"- Close reason (no secrets): {stats.close_reason or '(none)'}",
        f"- Error type: {stats.error or '(none)'}",
        f"- Counts by MessageType: {types}",
        "",
    ]


def _range(lo: float | None, hi: float | None) -> str:
    if lo is None or hi is None:
        return "(none)"
    return f"{lo:.5f} to {hi:.5f}"
