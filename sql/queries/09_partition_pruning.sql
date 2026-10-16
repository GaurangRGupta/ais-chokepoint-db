-- Q9. Partition pruning evidence.
-- Run the EXPLAIN first. The plan should name only today's UTC partition
-- (ais.vessel_position_YYYYMMDD), not every daily child.

EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*)
FROM ais.vessel_position
WHERE valid_time >= date_trunc('day', clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
  AND valid_time <  date_trunc('day', clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
                    + interval '1 day';

SELECT count(*) AS positions_today
FROM ais.vessel_position
WHERE valid_time >= date_trunc('day', clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
  AND valid_time <  date_trunc('day', clock_timestamp() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
                    + interval '1 day';

SELECT inhrelid::regclass AS partition
FROM pg_inherits
WHERE inhparent = 'ais.vessel_position'::regclass
ORDER BY 1;
