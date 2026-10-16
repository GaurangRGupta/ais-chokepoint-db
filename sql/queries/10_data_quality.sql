-- Q10. Data-quality quarantine counts.
-- Shape: reason, n, latest. A few bad_coordinates rows from live AIS are normal.

SELECT reason, count(*) AS n, max(received_at) AS latest
FROM ais.quarantine
GROUP BY reason
ORDER BY n DESC;

SELECT id, received_at, reason, source
FROM ais.quarantine
ORDER BY received_at DESC
LIMIT 20;
