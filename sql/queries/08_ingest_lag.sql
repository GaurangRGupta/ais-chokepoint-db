-- Q8. How late the database is relative to AIS event time, last hour.
-- lag_s = ingest_time - valid_time. Shape: n, p50, p95, p99 seconds.

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
    )::numeric, 2) AS lag_p99_s
FROM ais.vessel_position
WHERE ingest_time >= clock_timestamp() - interval '1 hour';

SELECT ts, source, connected, msg_last_minute, distinct_mmsi_last_minute, lag_p50_s, lag_p95_s
FROM ops.ingest_heartbeat
ORDER BY ts DESC
LIMIT 8;
