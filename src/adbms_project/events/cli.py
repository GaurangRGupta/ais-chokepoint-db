"""Rebuild transit and dwell events from recent AIS positions."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from adbms_project.events.detect import Dwell, Sample, Transit, detect_dwells, detect_transits
from adbms_project.settings import Settings


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass
    parser = argparse.ArgumentParser(
        description="Refresh ops.transit_event and ops.dwell_event from vessel_position."
    )
    parser.add_argument(
        "--lookback-hours",
        type=float,
        default=48.0,
        help="Rebuild events whose start falls in this many past hours (default 48).",
    )
    args = parser.parse_args()
    dsn = Settings().require_database_url()
    lookback = timedelta(hours=args.lookback_hours)
    try:
        conn = psycopg.connect(
            dsn,
            autocommit=False,
            connect_timeout=15,
            application_name="adbms-events",
            row_factory=dict_row,
        )
    except Exception:
        raise SystemExit(
            "PostgreSQL connect failed. Check DATABASE_URL and the Flexible Server firewall."
        ) from None
    try:
        n_tr, n_dw = refresh(conn, lookback)
        conn.commit()
    except SystemExit:
        conn.close()
        raise
    except Exception:
        conn.rollback()
        conn.close()
        raise SystemExit(
            "Event refresh failed. Load sql/schema/002_geofences.sql and confirm ais.vessel_position has rows."
        ) from None
    conn.close()
    print(f"events done transits={n_tr} dwells={n_dw} lookback_h={args.lookback_hours:g}")


def refresh(conn: psycopg.Connection, lookback: timedelta) -> tuple[int, int]:
    ids = _geofence_ids(conn)
    samples = _load_samples(conn, lookback)
    now = datetime.now(timezone.utc)
    transits = detect_transits(samples, now=now)
    dwells = detect_dwells(samples, now=now)
    cutoff = now - lookback
    conn.execute("DELETE FROM ops.transit_event WHERE enter_time >= %s", [cutoff])
    conn.execute("DELETE FROM ops.dwell_event WHERE start_time >= %s", [cutoff])
    for item in transits:
        gid = ids["east"] if item.direction == "east" else ids["west"]
        _insert_transit(conn, item, gid)
    for item in dwells:
        _insert_dwell(conn, item, ids["anchorage"])
    return len(transits), len(dwells)


def _geofence_ids(conn: psycopg.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT geofence_id, kind FROM ops.geofence WHERE kind IN ('lane_east', 'lane_west', 'anchorage')"
    ).fetchall()
    by_kind = {row["kind"]: int(row["geofence_id"]) for row in rows}
    missing = [kind for kind in ("lane_east", "lane_west", "anchorage") if kind not in by_kind]
    if missing:
        raise SystemExit(
            "Missing geofences "
            + ", ".join(missing)
            + ". Run sql/schema/002_geofences.sql on database chokepoint."
        )
    return {
        "east": by_kind["lane_east"],
        "west": by_kind["lane_west"],
        "anchorage": by_kind["anchorage"],
    }


def _load_samples(conn: psycopg.Connection, lookback: timedelta) -> list[Sample]:
    rows = conn.execute(
        """
        SELECT
            p.mmsi,
            p.valid_time,
            p.ingest_time,
            p.sog_kn,
            ST_X(p.geom::geometry) AS lon,
            ST_Y(p.geom::geometry) AS lat,
            ST_Covers(e.geom, p.geom) AS in_east,
            ST_Covers(w.geom, p.geom) AS in_west,
            ST_Covers(a.geom, p.geom) AS in_anchorage
        FROM ais.vessel_position p
        JOIN ops.geofence e ON e.kind = 'lane_east'
        JOIN ops.geofence w ON w.kind = 'lane_west'
        JOIN ops.geofence a ON a.kind = 'anchorage'
        WHERE p.valid_time >= now() - %s
        ORDER BY p.mmsi, p.valid_time
        """,
        [lookback],
    ).fetchall()
    samples: list[Sample] = []
    for row in rows:
        samples.append(
            Sample(
                mmsi=int(row["mmsi"]),
                valid_time=row["valid_time"],
                in_east=bool(row["in_east"]),
                in_west=bool(row["in_west"]),
                in_anchorage=bool(row["in_anchorage"]),
                sog_kn=row["sog_kn"],
                lon=float(row["lon"]),
                lat=float(row["lat"]),
                ingest_time=row["ingest_time"],
            )
        )
    return samples


def _insert_transit(conn: psycopg.Connection, item: Transit, geofence_id: int) -> None:
    conn.execute(
        """
        INSERT INTO ops.transit_event (
            mmsi, geofence_id, direction,
            enter_time, leave_time, enter_geom, leave_geom, enter_ingest, leave_ingest
        ) VALUES (
            %s, %s, %s, %s, %s,
            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
            %s, %s
        )
        """,
        [
            item.mmsi,
            geofence_id,
            item.direction,
            item.enter_time,
            item.leave_time,
            item.enter_lon,
            item.enter_lat,
            item.leave_lon,
            item.leave_lat,
            item.enter_ingest,
            item.leave_ingest,
        ],
    )


def _insert_dwell(conn: psycopg.Connection, item: Dwell, geofence_id: int) -> None:
    conn.execute(
        """
        INSERT INTO ops.dwell_event (
            mmsi, geofence_id, start_time, end_time, min_sog, median_sog
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [item.mmsi, geofence_id, item.start_time, item.end_time, item.min_sog, item.median_sog],
    )
