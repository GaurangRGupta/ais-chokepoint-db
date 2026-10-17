# Geofences and first queries

Laptop ingest works. Next you load four operational polygons and run the query pack in pgAdmin.

These polygons are student sketches for the course, not navigational charts. Lane vertices follow published WGS 84 traffic-separation coordinates in Maritime and Port Authority of Singapore, Singapore Port Information 2026, Annex 5 to 7 (IMO traffic separation scheme). Western Anchorage is a box around the published AWW representative point. The port-limit polygon is a simplified southern-waters sketch.

Do not insert fake ships.

## 1. Keep ingest running

In a PowerShell window you can leave open:

```powershell
cd C:\Users\gaura\Documents\grok_build_trial\adbms_project
uv run adbms-ingest
```

No `--duration`. Leave it until you close the laptop. Ctrl+C flushes the blob. If you must close the machine soon, a 20 to 30 minute run is still enough for Q1, Q2, Q8, Q9, and Q10.

Always-on ingest on Ubuntu: [ingest-vm.md](ingest-vm.md). Keep Q1 and Q9 screenshots for the report while the worker is live.

## 2. Load the geofences

1. pgAdmin, database `chokepoint`, Query Tool.
2. Open `adbms_project/sql/schema/002_geofences.sql`.
3. F5.

You should see four rows with `is_valid` true:

```text
singapore_port_limit_sketch  port_limit
western_anchorage            anchorage
tss_eastbound                lane_east
tss_westbound                lane_west
```

If `is_valid` is false, stop and send the output. Do not run queries on invalid polygons.

Confirm:

```sql
SELECT name, kind FROM ops.geofence ORDER BY kind, name;
```

## 3. Run queries that work on a short capture

Still in Query Tool, open and F5, one file at a time:

1. `sql/queries/01_in_lane_now.sql`
2. `sql/queries/02_nearest_neighbour.sql`
3. `sql/queries/08_ingest_lag.sql`
4. `sql/queries/09_partition_pruning.sql`
5. `sql/queries/10_data_quality.sql`

Q1 can be empty if every current ship sits outside the lane sketches. Q2 should still return five rows if `vessel_position_current` is not empty.

For Q9, the EXPLAIN plan should mention `vessel_position_YYYYMMDD` for today UTC, not a sequential scan of every partition.

Optional map screenshot: on Q1, use the pgAdmin Geometry Viewer on the `geom` column.

## 4. After 20 or more minutes of ingest

```powershell
cd C:\Users\gaura\Documents\grok_build_trial\adbms_project
uv run adbms-events
```

You should see `events done transits=... dwells=...` with no keys printed. Dwells need 15 minutes inside the anchorage box at under 0.5 knots, so `dwells=0` on a short run is normal.

Then run:

- `sql/queries/03_transits_24h.sql`
- `sql/queries/04_dwellers_now.sql`
- `sql/queries/05_trajectory.sql`
- `sql/queries/06_timeslice.sql`
- `sql/queries/11_static_history.sql`
- `sql/queries/12_as_of_ingest.sql`

Q7 (`07_stale_sla.sql`) is the lost-contact query. It fills after you stop ingest and wait 15 minutes.

## If a query is empty

| Query | Usual reason |
| --- | --- |
| Q1 | Ships in the box are not inside the TSS sketches. Q2 still proves spatial search. |
| Q3 | `adbms-events` not run yet, or ingest shorter than a real lane crossing. |
| Q4 | No ship sat in the Western Anchorage box at under 0.5 knots for 15 minutes. |
| Q7 | Ingest is still live and positions are fresh. |
| Q11 | No vessel has reported two different static identities yet. |

Paste back Q1 row count, Q9 EXPLAIN (the partition name line is enough), and the `adbms-events` summary line. Those have no secrets.
