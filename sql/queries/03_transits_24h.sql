-- Q3. Completed and open transits whose enter_time is in the last 24 hours.
-- Run uv run adbms-events first. Empty is expected before that, or on a very short capture.
-- Shape: mmsi, direction, enter_time, leave_time, duration_min.

SELECT
    t.mmsi,
    s.name,
    t.direction,
    g.name AS lane,
    t.enter_time,
    t.leave_time,
    round(extract(epoch from coalesce(t.leave_time, clock_timestamp()) - t.enter_time)::numeric / 60, 1)
        AS duration_min
FROM ops.transit_event t
JOIN ops.geofence g ON g.geofence_id = t.geofence_id
LEFT JOIN ais.vessel_static_current s ON s.mmsi = t.mmsi
WHERE t.enter_time >= clock_timestamp() - interval '24 hours'
ORDER BY t.enter_time DESC;
