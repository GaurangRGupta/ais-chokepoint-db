"""Live AIS ingest: WebSocket to Blob landing zone and PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections import deque
from datetime import datetime, timezone

import orjson
import websockets
from azure.storage.blob import BlobServiceClient, ContentSettings
from websockets.exceptions import ConnectionClosed

from adbms_project.ingest.boxes import (
    AIS_MESSAGE_TYPES,
    AISSTREAM_URL,
    BOX_LABELS,
    OPENWATERS_URL,
)
from adbms_project.ingest.envelope import compression_flag, message_type, parse_frame
from adbms_project.ingest.landing import LandingZone
from adbms_project.ingest.load import Loader
from adbms_project.ingest.validate import (
    PositionRecord,
    QuarantineRecord,
    StaticRecord,
    classify_frame,
)
from adbms_project.settings import Settings

_SILENCE_S = 300.0
_FLUSH_S = 30.0
_HEARTBEAT_S = 60.0
_PROGRESS_S = 30.0


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(
        description="Ingest live AIS into Azure Blob and PostgreSQL."
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Seconds to run, then exit. Default is until Ctrl+C.",
    )
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
        help="auto tries AISStream, then Open Waters after 5 minutes of silence.",
    )
    args = parser.parse_args()
    try:
        asyncio.run(
            run_ingest(duration_s=args.duration, box_name=args.box, source=args.source)
        )
    except KeyboardInterrupt:
        print("ingest stopped")


async def run_ingest(*, duration_s: float | None, box_name: str, source: str) -> None:
    settings = Settings()
    dsn = settings.require_database_url()
    settings.require_blob_auth()
    if source == "aiscast":
        settings.require_openwaters_key()
    else:
        settings.require_aisstream_key()

    put = make_blob_put(settings)
    landing = LandingZone(put)
    try:
        loader = Loader(dsn)
    except Exception:
        raise SystemExit(
            "PostgreSQL connect failed. Check DATABASE_URL, sslmode=require, "
            "and that your laptop IP is on the Flexible Server firewall."
        ) from None
    try:
        loader.ensure_schema()
        loader.ensure_hot_partitions()
    except SystemExit:
        loader.close()
        raise
    except Exception:
        loader.close()
        raise SystemExit(
            "PostgreSQL schema check failed. Confirm PostGIS and sql/schema/001_core.sql "
            "on database chokepoint."
        ) from None

    box = BOX_LABELS[box_name]
    started = datetime.now(timezone.utc)
    deadline = time.monotonic() + duration_s if duration_s is not None else None
    dur_label = f"{duration_s:.0f}s" if duration_s is not None else "until Ctrl+C"
    print(f"ingest start {started.isoformat()} box={box_name} duration={dur_label} source={source}")
    print("db ok; blob container ok; keys not printed")

    runtime = Runtime(loader=loader, landing=landing, source_name="")
    try:
        if source == "aiscast":
            await listen(
                url=OPENWATERS_URL,
                api_key=settings.require_openwaters_key(),
                source_name="aiscast",
                box=box,
                deadline=deadline,
                silence_abort_s=None,
                runtime=runtime,
            )
        else:
            await listen(
                url=AISSTREAM_URL,
                api_key=settings.require_aisstream_key(),
                source_name="aisstream",
                box=box,
                deadline=deadline,
                silence_abort_s=_SILENCE_S if source == "auto" else None,
                runtime=runtime,
            )
            if (
                source == "auto"
                and runtime.ais_n == 0
                and not _expired(deadline)
            ):
                print("AISStream silent. Switching to Open Waters.")
                await listen(
                    url=OPENWATERS_URL,
                    api_key=settings.require_openwaters_key(),
                    source_name="aiscast",
                    box=box,
                    deadline=deadline,
                    silence_abort_s=None,
                    runtime=runtime,
                )
    finally:
        runtime.shutdown()
        print(
            f"ingest done pos={runtime.pos_n} static={runtime.static_n} "
            f"quarantine={runtime.q_n} blob_flush={landing.flushes}"
        )


async def listen(
    *,
    url: str,
    api_key: str,
    source_name: str,
    box: list[list[list[float]]],
    deadline: float | None,
    silence_abort_s: float | None,
    runtime: Runtime,
) -> None:
    runtime.source_name = source_name
    subscribe = {
        "APIKey": api_key,
        "BoundingBoxes": box,
        "FilterMessageTypes": list(AIS_MESSAGE_TYPES),
    }
    failures = 0
    session_t0 = time.monotonic()
    while not _expired(deadline):
        if (
            silence_abort_s is not None
            and runtime.ais_n == 0
            and (time.monotonic() - session_t0) >= silence_abort_s
        ):
            print(f"no AIS frames after {silence_abort_s:.0f}s, leaving {source_name}")
            return
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
                runtime.connected = True
                failures = 0
                while not _expired(deadline):
                    if (
                        silence_abort_s is not None
                        and runtime.ais_n == 0
                        and (time.monotonic() - session_t0) >= silence_abort_s
                    ):
                        print(f"no AIS frames after {silence_abort_s:.0f}s, leaving {source_name}")
                        return
                    runtime.tick()
                    timeout = _recv_timeout(deadline)
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    except TimeoutError:
                        continue
                    runtime.handle_frame(raw)
        except ConnectionClosed as exc:
            runtime.connected = False
            print(f"{source_name} closed code={exc.code}")
        except OSError:
            runtime.connected = False
            print(f"{source_name} network error: OSError")
        except Exception as exc:  # noqa: BLE001 - ingest must keep trying
            runtime.connected = False
            print(f"{source_name} error: {type(exc).__name__}")
        if _expired(deadline):
            return
        failures += 1
        delay = min(30.0, 2.0 ** min(failures, 5))
        print(f"reconnect in {delay:.0f}s")
        await _sleep_until(delay, deadline)


class Runtime:
    def __init__(self, *, loader: Loader, landing: LandingZone, source_name: str) -> None:
        self.loader = loader
        self.landing = landing
        self.source_name = source_name
        self.connected = False
        self.pos_n = 0
        self.static_n = 0
        self.q_n = 0
        self.frames_n = 0
        self.window = MinuteWindow()
        now = time.monotonic()
        self._last_flush = now
        self._last_heartbeat = now
        self._last_progress = now
        self._t0 = now

    @property
    def ais_n(self) -> int:
        return self.pos_n + self.static_n

    def handle_frame(self, raw: str | bytes) -> None:
        received = datetime.now(timezone.utc)
        raw_b = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        self.frames_n += 1
        try:
            self.landing.append(received, raw_b)
        except Exception as exc:  # noqa: BLE001
            print(f"landing error: {type(exc).__name__}")
        try:
            envelope = parse_frame(raw_b)
        except (ValueError, TypeError):
            self._quarantine_parse(len(raw_b))
            return
        kind = message_type(envelope)
        if kind == "SubscriptionConfirmation":
            print(f"SubscriptionConfirmation compression={compression_flag(envelope)}")
        classified = classify_frame(envelope, raw_b, self.source_name, received)
        if classified is None:
            return
        try:
            self._store(classified, received)
        except Exception as exc:  # noqa: BLE001
            print(f"db error: {type(exc).__name__}")

    def tick(self) -> None:
        now = time.monotonic()
        if now - self._last_flush >= _FLUSH_S:
            self._flush_landing()
            self._last_flush = now
        if now - self._last_heartbeat >= _HEARTBEAT_S:
            self._heartbeat()
            self._last_heartbeat = now
        if now - self._last_progress >= _PROGRESS_S:
            elapsed = now - self._t0
            print(
                f"{elapsed:6.0f}s {self.source_name} frames={self.frames_n} "
                f"pos={self.pos_n} static={self.static_n} q={self.q_n} "
                f"blob_flush={self.landing.flushes}"
            )
            self._last_progress = now

    def shutdown(self) -> None:
        self.connected = False
        self._flush_landing()
        try:
            self._heartbeat()
        except Exception as exc:  # noqa: BLE001
            print(f"heartbeat error: {type(exc).__name__}")
        self.loader.close()

    def _store(self, classified: object, received: datetime) -> None:
        if isinstance(classified, PositionRecord):
            self.loader.insert_position(classified)
            self.pos_n += 1
            self.window.add(classified.mmsi, (received - classified.valid_time).total_seconds())
            return
        if isinstance(classified, StaticRecord):
            self.loader.insert_static(classified)
            self.static_n += 1
            self.window.add(classified.mmsi, (received - classified.valid_time).total_seconds())
            return
        if isinstance(classified, QuarantineRecord):
            self.loader.insert_quarantine(classified)
            self.q_n += 1

    def _quarantine_parse(self, byte_length: int) -> None:
        rec = QuarantineRecord(
            "parse_error",
            self.source_name,
            {"_parse_error": True, "byte_length": byte_length},
        )
        try:
            self.loader.insert_quarantine(rec)
            self.q_n += 1
        except Exception as exc:  # noqa: BLE001
            print(f"db error: {type(exc).__name__}")

    def _flush_landing(self) -> None:
        try:
            self.landing.flush()
        except Exception as exc:  # noqa: BLE001
            print(f"landing error: {type(exc).__name__}")

    def _heartbeat(self) -> None:
        msg_n, mmsi_n, p50, p95 = self.window.snapshot()
        try:
            self.loader.heartbeat(
                source=self.source_name or "none",
                connected=self.connected,
                msg_last_minute=msg_n,
                distinct_mmsi_last_minute=mmsi_n,
                lag_p50_s=p50,
                lag_p95_s=p95,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"heartbeat error: {type(exc).__name__}")


class MinuteWindow:
    def __init__(self) -> None:
        self._events: deque[tuple[float, int, float | None]] = deque()

    def add(self, mmsi: int, lag_s: float | None) -> None:
        self._events.append((time.monotonic(), mmsi, lag_s))
        self._trim()

    def snapshot(self) -> tuple[int, int, float | None, float | None]:
        self._trim()
        msg_n = len(self._events)
        mmsi_n = len({item[1] for item in self._events})
        lags = [item[2] for item in self._events if item[2] is not None]
        return msg_n, mmsi_n, _percentile(lags, 50), _percentile(lags, 95)

    def _trim(self) -> None:
        cutoff = time.monotonic() - 60.0
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()


def make_blob_put(settings: Settings):
    if settings.azure_storage_connection_string:
        service = BlobServiceClient.from_connection_string(
            settings.azure_storage_connection_string
        )
    else:
        account_url = f"https://{settings.azure_storage_account}.blob.core.windows.net"
        service = BlobServiceClient(
            account_url=account_url, credential=settings.azure_storage_key
        )
    container = settings.azure_blob_container or "ais-raw"
    try:
        client = service.get_container_client(container)
        if not client.exists():
            raise SystemExit(
                f"Blob container {container} does not exist. Create it under the storage account."
            )
    except SystemExit:
        raise
    except Exception:
        raise SystemExit(
            "Blob check failed. Check AZURE_STORAGE_CONNECTION_STRING or "
            "AZURE_STORAGE_ACCOUNT plus AZURE_STORAGE_KEY, and container ais-raw."
        ) from None
    content = ContentSettings(content_type="application/gzip")

    def put(name: str, data: bytes) -> None:
        blob = service.get_blob_client(container=container, blob=name)
        blob.upload_blob(data, overwrite=True, content_settings=content)

    return put


def _expired(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


async def _sleep_until(delay: float, deadline: float | None) -> None:
    if deadline is None:
        await asyncio.sleep(delay)
        return
    await asyncio.sleep(max(0.0, min(delay, deadline - time.monotonic())))


def _recv_timeout(deadline: float | None) -> float:
    if deadline is None:
        return 5.0
    return max(0.05, min(5.0, deadline - time.monotonic()))


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((p / 100.0) * (len(ordered) - 1)))
    index = min(max(index, 0), len(ordered) - 1)
    return ordered[index]
