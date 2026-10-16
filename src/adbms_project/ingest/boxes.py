"""Geographic boxes. AISStream corners are [latitude, longitude] pairs."""

from __future__ import annotations

# Singapore Strait start box (plan). Southwest then northeast.
SINGAPORE: list[list[list[float]]] = [[[1.10, 103.40], [1.48, 104.15]]]

# Backup chokepoint if Singapore is too quiet after shrinks.
GIBRALTAR: list[list[list[float]]] = [[[35.85, -5.60], [36.15, -5.20]]]

AIS_MESSAGE_TYPES: tuple[str, ...] = (
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
    "ShipStaticData",
    "StaticDataReport",
)

AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"
OPENWATERS_URL = "wss://ais.openwaters.io/v0/stream"

BOX_LABELS = {
    "singapore": SINGAPORE,
    "gibraltar": GIBRALTAR,
}
