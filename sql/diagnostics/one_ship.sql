-- Inspect one MMSI: current picture, history track, static identity, events.
-- Replace every 563009190 below with the MMSI you want (find names in catalog D27).
-- Example from the first capture: 563009190 NOBLE JEWEL TG45.
-- Run in pgAdmin Query Tool on database chokepoint.
-- See docs/dba-manual.md section 13.

-- Current position joined to current static identity.
SELECT
    c.mmsi,
    s.name,
    s.callsign,
    s.imo,
    s.ship_type,
    s.destination,
    c.sog_kn,
    c.cog_deg,
    c.heading_deg,
    c.nav_status,
    c.msg_type,
    c.valid_time,
    c.ingest_time,
    c.source,
    ST_Y(c.geom::geometry) AS lat,
    ST_X(c.geom::geometry) AS lon,
    c.geom
FROM ais.vessel_position_current c
LEFT JOIN ais.vessel_static_current s ON s.mmsi = c.mmsi
WHERE c.mmsi = 563009190;

-- Append-only history for that MMSI, oldest first.
SELECT
    p.pos_id,
    p.valid_time,
    p.ingest_time,
    p.sog_kn,
    p.cog_deg,
    p.heading_deg,
    p.nav_status,
    p.msg_type,
    p.source,
    ST_Y(p.geom::geometry) AS lat,
    ST_X(p.geom::geometry) AS lon,
    p.geom
FROM ais.vessel_position p
WHERE p.mmsi = 563009190
ORDER BY p.valid_time;

-- Trajectory as a single line (needs at least two points).
SELECT
    p.mmsi,
    count(*) AS n_points,
    min(p.valid_time) AS t_from,
    max(p.valid_time) AS t_to,
    ST_MakeLine(p.geom::geometry ORDER BY p.valid_time)::geography AS traj
FROM ais.vessel_position p
WHERE p.mmsi = 563009190
GROUP BY p.mmsi
HAVING count(*) >= 2;

-- Static identity versions (tstzrange). Empty if this MMSI never sent static data.
SELECT
    h.mmsi,
    h.name,
    h.imo,
    h.ship_type,
    h.callsign,
    h.destination,
    h.valid_range,
    h.ingest_time,
    h.source
FROM ais.vessel_static_history h
WHERE h.mmsi = 563009190
ORDER BY lower(h.valid_range);

-- Derived events for this MMSI (empty until uv run adbms-events).
SELECT 'transit' AS event_kind, tr.transit_id AS event_id, g.name AS geofence,
       tr.direction, tr.enter_time AS t_from, tr.leave_time AS t_to
FROM ops.transit_event tr
JOIN ops.geofence g ON g.geofence_id = tr.geofence_id
WHERE tr.mmsi = 563009190
UNION ALL
SELECT 'dwell', d.dwell_id, g.name, NULL, d.start_time, d.end_time
FROM ops.dwell_event d
JOIN ops.geofence g ON g.geofence_id = d.geofence_id
WHERE d.mmsi = 563009190
ORDER BY 5;
