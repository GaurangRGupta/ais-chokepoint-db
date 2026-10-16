"""Hourly gzip JSONL landing zone. Path: raw/ais/yyyy/mm/dd/hh.jsonl.gz"""

from __future__ import annotations

import gzip
import io
from collections.abc import Callable
from datetime import datetime, timezone

BlobPut = Callable[[str, bytes], None]


def blob_name(when: datetime) -> str:
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    else:
        when = when.astimezone(timezone.utc)
    return f"raw/ais/{when:%Y}/{when:%m}/{when:%d}/{when:%H}.jsonl.gz"


def gzip_jsonl(parts: list[bytes]) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for part in parts:
            gz.write(part)
    return buf.getvalue()


class LandingZone:
    """Buffer original frames and overwrite the current UTC-hour blob on flush."""

    def __init__(self, put: BlobPut) -> None:
        self._put = put
        self._name: str | None = None
        self._parts: list[bytes] = []
        self._dirty = False
        self.flushes = 0

    def append(self, when: datetime, raw: bytes) -> None:
        line = raw.rstrip(b"\r\n") + b"\n"
        name = blob_name(when)
        if self._name is not None and name != self._name:
            self.flush()
            self._parts = []
        self._name = name
        self._parts.append(line)
        self._dirty = True

    def flush(self) -> None:
        if not self._dirty or self._name is None:
            return
        payload = gzip_jsonl(self._parts)
        self._put(self._name, payload)
        self._dirty = False
        self.flushes += 1
