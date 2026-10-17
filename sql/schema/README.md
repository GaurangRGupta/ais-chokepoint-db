# Schema

1. In pgAdmin, click database `chokepoint`.
2. Tools > Query Tool.
3. Open `001_core.sql`, paste it, press F5.
4. Confirm with:

```sql
SELECT nspname FROM pg_namespace WHERE nspname IN ('ais', 'ops');
SELECT tablename FROM pg_tables WHERE schemaname IN ('ais', 'ops') ORDER BY 1;
SELECT inhrelid::regclass AS partition
FROM pg_inherits
WHERE inhparent = 'ais.vessel_position'::regclass
ORDER BY 1;
```

Do not insert fake ships by hand.

After `001_core.sql`, follow [docs/ingest.md](../../docs/ingest.md) for laptop ingest.

After ingest writes rows, load `002_geofences.sql` and follow [docs/geofences.md](../../docs/geofences.md).

The database administrator manual ([docs/dba-manual.md](../../docs/dba-manual.md)) lists every designed table, every attribute, and the diagnostic catalogue in `sql/diagnostics/`.
