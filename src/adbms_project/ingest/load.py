"""Insert validated AIS rows into PostgreSQL. Do not log the connection string."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import psycopg
from psycopg.errors import CheckViolation, ExclusionViolation, OperationalError
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from adbms_project.ingest.validate import (
    IDENTITY_FIELDS,
    PositionRecord,
    QuarantineRecord,
    StaticRecord,
    merge_static,
    static_identity_tuple,
)

_POSITION_SQL = """
INSERT INTO ais.vessel_position (
    mmsi, geom, sog_kn, cog_deg, heading_deg, nav_status,
    msg_type, valid_time, source, payload_sha256
) VALUES (
    %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
    %s, %s, %s, %s, %s, %s, %s, %s
)
ON CONFLICT (mmsi, valid_time, payload_sha256) DO NOTHING
"""

_CURRENT_SQL = """
INSERT INTO ais.vessel_position_current (
    mmsi, geom, sog_kn, cog_deg, heading_deg, nav_status,
    msg_type, valid_time, ingest_time, source
) VALUES (
    %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
    %s, %s, %s, %s, %s, %s, clock_timestamp(), %s
)
ON CONFLICT (mmsi) DO UPDATE SET
    geom = EXCLUDED.geom,
    sog_kn = EXCLUDED.sog_kn,
    cog_deg = EXCLUDED.cog_deg,
    heading_deg = EXCLUDED.heading_deg,
    nav_status = EXCLUDED.nav_status,
    msg_type = EXCLUDED.msg_type,
    valid_time = EXCLUDED.valid_time,
    ingest_time = EXCLUDED.ingest_time,
    source = EXCLUDED.source
WHERE ais.vessel_position_current.valid_time <= EXCLUDED.valid_time
"""

_STATIC_INSERT_SQL = """
INSERT INTO ais.vessel_static_current (
    mmsi, name, ship_type, callsign, imo,
    dim_bow_m, dim_stern_m, dim_port_m, dim_starboard_m,
    destination, eta, valid_time, source
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_STATIC_UPDATE_SQL = """
UPDATE ais.vessel_static_current SET
    name = %s, ship_type = %s, callsign = %s, imo = %s,
    dim_bow_m = %s, dim_stern_m = %s, dim_port_m = %s, dim_starboard_m = %s,
    destination = %s, eta = %s, valid_time = %s, ingest_time = clock_timestamp(),
    source = %s
WHERE mmsi = %s
"""

_HISTORY_INSERT_SQL = """
INSERT INTO ais.vessel_static_history (
    mmsi, name, ship_type, callsign, imo,
    dim_bow_m, dim_stern_m, dim_port_m, dim_starboard_m,
    destination, eta, valid_range, source
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    tstzrange(%s, NULL, '[)'), %s
)
"""

_HISTORY_CLOSE_SQL = """
UPDATE ais.vessel_static_history
SET valid_range = tstzrange(lower(valid_range), %s, '[)')
WHERE mmsi = %s AND upper_inf(valid_range)
"""


class Loader:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = self._connect()

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(
            self._dsn,
            autocommit=True,
            connect_timeout=15,
            application_name="adbms-ingest",
            row_factory=dict_row,
        )

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def ping(self) -> None:
        self._conn.execute("SELECT 1")

    def reconnect(self) -> None:
        self.close()
        self._conn = self._connect()

    def ensure_schema(self) -> None:
        row = self._conn.execute(
            "SELECT to_regclass('ais.vessel_position') AS rel"
        ).fetchone()
        if row is None or row["rel"] is None:
            raise SystemExit(
                "Table ais.vessel_position is missing. Run sql/schema/001_core.sql "
                "in pgAdmin on database chokepoint."
            )
        self._conn.execute("SELECT PostGIS_Version() AS v")

    def ensure_hot_partitions(self) -> None:
        self._conn.execute(
            """
            SELECT ais.ensure_position_partitions(
                (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date - 1,
                (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date + 8
            )
            """
        )

    def ensure_day(self, day: date) -> None:
        self._conn.execute(
            "SELECT ais.ensure_position_partitions(%s, %s)",
            [day, day + timedelta(days=1)],
        )

    def insert_position(self, rec: PositionRecord) -> None:
        try:
            self._write_position(rec)
        except CheckViolation:
            self.ensure_day(rec.valid_time.date())
            try:
                self._write_position(rec)
            except Exception:
                self.insert_quarantine(
                    QuarantineRecord("no_partition", rec.source, rec.envelope)
                )
        except OperationalError:
            self.reconnect()
            self._write_position(rec)

    def insert_static(self, rec: StaticRecord) -> None:
        try:
            self._write_static(rec)
        except ExclusionViolation:
            self.insert_quarantine(
                QuarantineRecord("static_history_overlap", rec.source, rec.envelope)
            )
        except OperationalError:
            self.reconnect()
            self._write_static(rec)

    def insert_quarantine(self, rec: QuarantineRecord) -> None:
        self._conn.execute(
            "INSERT INTO ais.quarantine (reason, source, raw) VALUES (%s, %s, %s)",
            [rec.reason, rec.source, Jsonb(rec.envelope)],
        )

    def heartbeat(
        self,
        *,
        source: str,
        connected: bool,
        msg_last_minute: int,
        distinct_mmsi_last_minute: int,
        lag_p50_s: float | None,
        lag_p95_s: float | None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO ops.ingest_heartbeat (
                source, connected, msg_last_minute, distinct_mmsi_last_minute,
                lag_p50_s, lag_p95_s
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                source,
                connected,
                msg_last_minute,
                distinct_mmsi_last_minute,
                lag_p50_s,
                lag_p95_s,
            ],
        )

    def _write_position(self, rec: PositionRecord) -> None:
        # ST_MakePoint takes (longitude, latitude).
        args = [
            rec.mmsi,
            rec.lon,
            rec.lat,
            rec.sog_kn,
            rec.cog_deg,
            rec.heading_deg,
            rec.nav_status,
            rec.msg_type,
            rec.valid_time,
            rec.source,
            rec.payload_sha256,
        ]
        current_args = [
            rec.mmsi,
            rec.lon,
            rec.lat,
            rec.sog_kn,
            rec.cog_deg,
            rec.heading_deg,
            rec.nav_status,
            rec.msg_type,
            rec.valid_time,
            rec.source,
        ]
        with self._conn.transaction():
            self._conn.execute(_POSITION_SQL, args)
            self._conn.execute(_CURRENT_SQL, current_args)

    def _write_static(self, rec: StaticRecord) -> None:
        with self._conn.transaction():
            row = self._conn.execute(
                """
                SELECT mmsi, name, ship_type, callsign, imo,
                       dim_bow_m, dim_stern_m, dim_port_m, dim_starboard_m,
                       destination, eta, valid_time
                FROM ais.vessel_static_current
                WHERE mmsi = %s
                """,
                [rec.mmsi],
            ).fetchone()
            if row is None:
                self._insert_static_current(rec)
                self._insert_static_history(rec)
                return
            existing_time = row["valid_time"]
            if rec.valid_time < existing_time:
                return
            merged = merge_static(row, rec)
            same_identity = static_identity_tuple(merged) == static_identity_tuple(
                {name: row.get(name) for name in IDENTITY_FIELDS}
            )
            if same_identity:
                if rec.valid_time > existing_time:
                    self._conn.execute(
                        """
                        UPDATE ais.vessel_static_current
                        SET valid_time = %s, ingest_time = clock_timestamp(), source = %s
                        WHERE mmsi = %s
                        """,
                        [rec.valid_time, rec.source, rec.mmsi],
                    )
                return
            if rec.valid_time == existing_time:
                self.insert_quarantine(
                    QuarantineRecord("static_same_time_change", rec.source, rec.envelope)
                )
                return
            self._conn.execute(_HISTORY_CLOSE_SQL, [rec.valid_time, rec.mmsi])
            self._insert_static_history(merged)
            self._update_static_current(merged)

    def _insert_static_current(self, rec: StaticRecord) -> None:
        self._conn.execute(_STATIC_INSERT_SQL, _static_current_values(rec))

    def _update_static_current(self, rec: StaticRecord) -> None:
        values = _static_identity_values(rec)
        self._conn.execute(
            _STATIC_UPDATE_SQL,
            [*values, rec.valid_time, rec.source, rec.mmsi],
        )

    def _insert_static_history(self, rec: StaticRecord) -> None:
        values = _static_identity_values(rec)
        self._conn.execute(
            _HISTORY_INSERT_SQL,
            [rec.mmsi, *values, rec.valid_time, rec.source],
        )


def _static_identity_values(rec: StaticRecord) -> list[Any]:
    return [getattr(rec, name) for name in IDENTITY_FIELDS]


def _static_current_values(rec: StaticRecord) -> list[Any]:
    return [rec.mmsi, *_static_identity_values(rec), rec.valid_time, rec.source]
