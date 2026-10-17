-- Diagnostic catalogue for database chokepoint.
-- Read-only SELECT statements. Run in pgAdmin Query Tool (F5).
-- One result grid per statement. Work through D1 to D32 in order.
-- How to read each grid: docs/dba-manual.md section 12.
-- Do not paste passwords, connection strings, or API keys into kept output.

-- D1. Session: database name, clock, time zone, server version, PostGIS.
SELECT
    current_database() AS database_name,
    current_user AS session_user_name,
    inet_server_addr() AS server_addr,
    inet_server_port() AS server_port,
    current_setting('TimeZone') AS time_zone,
    clock_timestamp() AS db_now,
    version() AS postgres_version,
    PostGIS_Version() AS postgis_version,
    PostGIS_GEOS_Version() AS geos_version,
    PostGIS_PROJ_Version() AS proj_version;

-- D2. Databases on this Flexible Server that this login can see.
SELECT datname, pg_catalog.pg_get_userbyid(datdba) AS owner,
       pg_catalog.pg_encoding_to_char(encoding) AS encoding,
       datcollate
FROM pg_database
WHERE datistemplate = false
ORDER BY datname;

-- D3. Application schemas.
SELECT nspname AS schema_name, pg_catalog.pg_get_userbyid(nspowner) AS owner
FROM pg_namespace
WHERE nspname IN ('ais', 'ops', 'public', 'tiger', 'topology')
ORDER BY 1;

-- D4. Tables and views in ais and ops (includes daily partitions).
SELECT table_schema, table_type, table_name
FROM information_schema.tables
WHERE table_schema IN ('ais', 'ops')
ORDER BY table_schema, table_type, table_name;

-- D5. Column inventory: attributes per designed table.
SELECT table_schema, table_name, ordinal_position, column_name, data_type,
       is_nullable, column_default
FROM information_schema.columns
WHERE table_schema IN ('ais', 'ops')
  AND table_name NOT LIKE 'vessel_position\_20%' ESCAPE '\'
ORDER BY table_schema, table_name, ordinal_position;

-- D6. Column counts on the nine designed tables (parent, not partition children).
SELECT table_schema, table_name, count(*) AS n_columns
FROM information_schema.columns
WHERE table_schema IN ('ais', 'ops')
  AND table_name NOT LIKE 'vessel_position\_20%' ESCAPE '\'
GROUP BY table_schema, table_name
ORDER BY table_schema, table_name;

-- D7. Daily partitions of ais.vessel_position.
SELECT
    inhrelid::regclass AS partition_name,
    pg_get_expr(c.relpartbound, c.oid) AS bounds
FROM pg_inherits i
JOIN pg_class c ON c.oid = i.inhrelid
WHERE i.inhparent = 'ais.vessel_position'::regclass
ORDER BY 1;

-- D8. Indexes used by the application schemas.
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname IN ('ais', 'ops')
ORDER BY 1, 2, 3;

-- D9. Table sizes including indexes (parent plus each partition).
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relkind,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
    pg_size_pretty(pg_relation_size(c.oid)) AS heap_size,
    pg_stat_get_live_tuples(c.oid) AS live_tuples_est
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('ais', 'ops')
  AND c.relkind IN ('r', 'p')
ORDER BY pg_total_relation_size(c.oid) DESC;

-- D10. Exact row counts (can take a moment as data grows).
SELECT 'ais.vessel_position' AS table_name, count(*) AS n FROM ais.vessel_position
UNION ALL SELECT 'ais.vessel_position_current', count(*) FROM ais.vessel_position_current
UNION ALL SELECT 'ais.vessel_static_current', count(*) FROM ais.vessel_static_current
UNION ALL SELECT 'ais.vessel_static_history', count(*) FROM ais.vessel_static_history
UNION ALL SELECT 'ais.quarantine', count(*) FROM ais.quarantine
UNION ALL SELECT 'ops.geofence', count(*) FROM ops.geofence
UNION ALL SELECT 'ops.transit_event', count(*) FROM ops.transit_event
UNION ALL SELECT 'ops.dwell_event', count(*) FROM ops.dwell_event
UNION ALL SELECT 'ops.ingest_heartbeat', count(*) FROM ops.ingest_heartbeat
ORDER BY 1;

-- D11. Distinct ships and time span of stored positions.
SELECT
    count(*) AS position_rows,
    count(DISTINCT mmsi) AS distinct_mmsi,
    min(valid_time) AS min_valid_time,
    max(valid_time) AS max_valid_time,
    min(ingest_time) AS min_ingest_time,
    max(ingest_time) AS max_ingest_time,
    clock_timestamp() AS db_now,
    extract(epoch from max(valid_time) - min(valid_time)) AS capture_span_s
FROM ais.vessel_position;

-- D12. Mean stored-position rate over the captured span (rows per second and per minute).
SELECT
    count(*) AS position_rows,
    extract(epoch from max(valid_time) - min(valid_time)) AS span_s,
    round((count(*) / greatest(extract(epoch from max(valid_time) - min(valid_time)), 1))::numeric, 4)
        AS rows_per_s,
    round((count(*) / greatest(extract(epoch from max(valid_time) - min(valid_time)), 1) * 60)::numeric, 2)
        AS rows_per_min
FROM ais.vessel_position;

-- D13. Position counts by UTC day (should match partition names).
SELECT
    (valid_time AT TIME ZONE 'UTC')::date AS utc_day,
    count(*) AS n,
    count(DISTINCT mmsi) AS distinct_mmsi
FROM ais.vessel_position
GROUP BY 1
ORDER BY 1;

-- D14. Message types stored in history.
SELECT msg_type, count(*) AS n
FROM ais.vessel_position
GROUP BY msg_type
ORDER BY n DESC;

-- D15. Ingest lag: ingest_time minus valid_time, in seconds.
SELECT
    count(*) AS n,
    round(percentile_cont(0.50) WITHIN GROUP (
        ORDER BY extract(epoch from ingest_time - valid_time)
    )::numeric, 2) AS lag_p50_s,
    round(percentile_cont(0.95) WITHIN GROUP (
        ORDER BY extract(epoch from ingest_time - valid_time)
    )::numeric, 2) AS lag_p95_s,
    round(percentile_cont(0.99) WITHIN GROUP (
        ORDER BY extract(epoch from ingest_time - valid_time)
    )::numeric, 2) AS lag_p99_s,
    round(avg(extract(epoch from ingest_time - valid_time))::numeric, 2) AS lag_avg_s
FROM ais.vessel_position;

-- D16. Current-picture freshness versus the database clock.
SELECT
    count(*) AS current_ships,
    count(*) FILTER (
        WHERE clock_timestamp() - valid_time <= interval '15 minutes'
    ) AS fresh_within_15_min,
    count(*) FILTER (
        WHERE clock_timestamp() - valid_time > interval '15 minutes'
    ) AS stale_over_15_min,
    min(valid_time) AS oldest_current_valid,
    max(valid_time) AS newest_current_valid
FROM ais.vessel_position_current;

-- D17. Heartbeat: is ingest running, and what did the last minutes look like.
SELECT ts, source, connected, msg_last_minute, distinct_mmsi_last_minute, lag_p50_s, lag_p95_s
FROM ops.ingest_heartbeat
ORDER BY ts DESC
LIMIT 15;

-- D18. Data quality: quarantine reasons.
SELECT reason, count(*) AS n, min(received_at) AS first_seen, max(received_at) AS last_seen
FROM ais.quarantine
GROUP BY reason
ORDER BY n DESC;

-- D19. Geofence inventory and validity.
SELECT
    geofence_id, name, kind, drawn_by,
    ST_IsValid(geom::geometry) AS is_valid,
    round(ST_Area(geom)::numeric, 0) AS area_m2
FROM ops.geofence
ORDER BY kind, name;

-- D20. Open transits and dwells (empty until uv run adbms-events).
SELECT 'open_transits' AS kind, count(*) AS n
FROM ops.transit_event WHERE leave_time IS NULL
UNION ALL
SELECT 'completed_transits', count(*) FROM ops.transit_event WHERE leave_time IS NOT NULL
UNION ALL
SELECT 'open_dwells', count(*) FROM ops.dwell_event WHERE end_time IS NULL
UNION ALL
SELECT 'completed_dwells', count(*) FROM ops.dwell_event WHERE end_time IS NOT NULL;

-- D21. Extensions required by this project.
SELECT extname, extversion
FROM pg_extension
WHERE extname IN ('postgis', 'btree_gist', 'plpgsql')
ORDER BY 1;

-- D22. Active connections (no passwords). Useful if ingest or pgAdmin appears stuck.
SELECT pid, usename, application_name, client_addr, state,
       date_trunc('second', clock_timestamp() - query_start) AS running_for,
       left(query, 80) AS query_preview
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;

-- D23. Constraints on application tables.
SELECT n.nspname AS schema_name, c.relname AS table_name, con.conname,
       con.contype, pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('ais', 'ops')
ORDER BY 1, 2, 3;

-- D24. Functions in ais and ops.
SELECT n.nspname AS schema_name, p.proname AS function_name,
       pg_get_function_identity_arguments(p.oid) AS args
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname IN ('ais', 'ops')
ORDER BY 1, 2;

-- D25. Table comments loaded from 001_core.sql.
SELECT n.nspname AS schema_name, c.relname AS table_name,
       obj_description(c.oid, 'pg_class') AS table_comment
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('ais', 'ops')
  AND c.relkind IN ('r', 'p')
  AND c.relname NOT LIKE 'vessel_position_20%'
ORDER BY 1, 2;

-- D26. Position MMSI with and without static identity.
SELECT
    count(DISTINCT p.mmsi) AS position_mmsi,
    count(DISTINCT s.mmsi) AS static_mmsi,
    count(DISTINCT p.mmsi) FILTER (WHERE s.mmsi IS NOT NULL) AS both,
    count(DISTINCT p.mmsi) FILTER (WHERE s.mmsi IS NULL) AS position_without_static
FROM ais.vessel_position p
LEFT JOIN ais.vessel_static_current s ON s.mmsi = p.mmsi;

-- D27. Busiest MMSI in stored history.
SELECT p.mmsi, s.name, count(*) AS n_points,
       min(p.valid_time) AS t_from, max(p.valid_time) AS t_to
FROM ais.vessel_position p
LEFT JOIN ais.vessel_static_current s ON s.mmsi = p.mmsi
GROUP BY p.mmsi, s.name
ORDER BY n_points DESC
LIMIT 15;

-- D28. Geographic extent of stored points (must sit inside the Singapore box).
SELECT
    round(ST_YMin(ext)::numeric, 5) AS min_lat,
    round(ST_YMax(ext)::numeric, 5) AS max_lat,
    round(ST_XMin(ext)::numeric, 5) AS min_lon,
    round(ST_XMax(ext)::numeric, 5) AS max_lon
FROM (
    SELECT ST_Extent(geom::geometry) AS ext
    FROM ais.vessel_position
) e;

-- D29. Navigational status histogram.
SELECT nav_status, count(*) AS n
FROM ais.vessel_position
GROUP BY nav_status
ORDER BY n DESC;

-- D30. Login roles visible to this session.
SELECT rolname, rolcanlogin, rolcreatedb, rolcreaterole, rolsuper
FROM pg_roles
WHERE rolcanlogin
ORDER BY 1;

-- D31. Table-level grants on ais and ops.
SELECT grantee, table_schema, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema IN ('ais', 'ops')
ORDER BY 1, 2, 3, 4;

-- D32. Every UTC day that has rows must have a matching daily partition.
WITH days AS (
    SELECT DISTINCT (valid_time AT TIME ZONE 'UTC')::date AS utc_day
    FROM ais.vessel_position
),
parts AS (
    SELECT regexp_replace(c.relname, '^vessel_position_', '') AS ymd
    FROM pg_inherits i
    JOIN pg_class c ON c.oid = i.inhrelid
    WHERE i.inhparent = 'ais.vessel_position'::regclass
)
SELECT d.utc_day,
       EXISTS (
           SELECT 1 FROM parts p
           WHERE p.ymd = to_char(d.utc_day, 'YYYYMMDD')
       ) AS partition_exists
FROM days d
ORDER BY 1;
