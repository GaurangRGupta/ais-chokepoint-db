# Day-1 AIS feed spike

Started (UTC): 2026-10-16T18:56:21.690038+00:00
Ended (UTC): 2026-10-16T19:06:22.333393+00:00
Requested duration: 600 seconds
Used Open Waters fallback: no

No API keys, tokens, or connection strings are in this file.

## Decision

**go_singapore**

Subscription confirmed, at least 30 distinct MMSI, and mean rate under 40 messages per second. Stay on Singapore and start schema.

## Source `aisstream`

- WebSocket host: `wss://stream.aisstream.io/v0/stream`
- Box: `singapore`
- Listen seconds: 600.6
- SubscriptionConfirmation: yes
- CompressionEnabled: True
- AIS application frames: 159
- Distinct MMSI: 98
- Mean AIS messages per second: 0.265
- First AIS frame after seconds: 4.25
- Latitude range: 1.14273 to 1.29236
- Longitude range: 103.71486 to 103.97441
- Close code: None
- Close reason (no secrets): (none)
- Error type: (none)
- Counts by MessageType: PositionReport=136, ShipStaticData=21, StandardClassBPositionReport=1, StaticDataReport=1, SubscriptionConfirmation=1

## Pass rules used

- Pass Singapore: SubscriptionConfirmation, at least 30 distinct MMSI in 10 minutes, mean AIS rate under 40 messages per second.
- Shrink: mean rate over 40 messages per second.
- Switch to Gibraltar: fewer than 15 distinct MMSI after about 9 minutes.
- Fallback: zero AIS application frames on AISStream for 5 minutes.
- Abort this source family: both AISStream and Open Waters empty.

## Sources

- AISStream documentation: https://aisstream.io/documentation/
- Open Waters aiscast: https://openwaters.io/api/ais/
