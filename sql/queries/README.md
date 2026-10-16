# Query evidence pack

Run these in pgAdmin Query Tool on database `chokepoint`. Load `sql/schema/002_geofences.sql` first. For Q3 and Q4, also run `uv run adbms-events`.

Keep ingest running in another terminal while you query, so current positions stay fresh.

| File | Question |
| --- | --- |
| `01_in_lane_now.sql` | Who is in a TSS lane right now? |
| `02_nearest_neighbour.sql` | Five ships nearest to 1.20 N, 103.85 E |
| `03_transits_24h.sql` | Who transited, and in which direction? |
| `04_dwellers_now.sql` | Who is sitting in Western Anchorage? |
| `05_trajectory.sql` | Path of the busiest MMSI in the last 6 hours |
| `06_timeslice.sql` | Traffic picture at T (valid time) |
| `07_stale_sla.sql` | No fresh position for 15 minutes |
| `08_ingest_lag.sql` | How late ingest is versus AIS event time |
| `09_partition_pruning.sql` | EXPLAIN should touch one daily partition |
| `10_data_quality.sql` | Quarantine counts by reason |
| `11_static_history.sql` | Identity versions with valid_range |
| `12_as_of_ingest.sql` | World slice versus what we knew at T |

For EXPLAIN evidence, copy the `EXPLAIN (ANALYZE, BUFFERS)` block from the file, run it, and save the text (no secrets) into `reports/query_evidence.md` later.

Q1 or Q5 `geom` / `traj` columns can be opened with the pgAdmin Geometry Viewer for a map screenshot.
