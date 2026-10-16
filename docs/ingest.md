# First laptop ingest

The schema is loaded. Next you put the database URL and the storage key into `.env`, then run a three-minute ingest from this laptop. The worker writes raw Automatic Identification System (AIS) frames to blob container `ais-raw` and inserts validated rows into PostgreSQL.

Do not put passwords, keys, or connection strings into Git, chat, or the report. Do not create the ingest virtual machine yet.

## 1. Open `.env`

In `adbms_project`, copy `.env.example` to `.env` if you do not already have `.env`. You already have `AISSTREAM_API_KEY` from the spike. Leave that line as it is.

You still need:

- `DATABASE_URL`
- `AZURE_STORAGE_CONNECTION_STRING` (or `AZURE_STORAGE_ACCOUNT` plus `AZURE_STORAGE_KEY`)
- `AZURE_BLOB_CONTAINER=ais-raw`

## 2. Build DATABASE_URL

1. Open Notepad (not a file in the Git repo).
2. Your PostgreSQL admin login is `chokepointadmin`.
3. The host is `aiscpdbgg013.postgres.database.azure.com`.
4. The database is `chokepoint`.
5. URL-encode the admin password in PowerShell. Type your real password only in this window:

```powershell
[uri]::EscapeDataString('PASTE_PASSWORD_HERE')
```

6. Copy the encoded output. A character like `@` becomes `%40`, `/` becomes `%2F`, `#` becomes `%23`.
7. In `.env` set:

```text
DATABASE_URL=postgresql://chokepointadmin:ENCODED_PASSWORD@aiscpdbgg013.postgres.database.azure.com:5432/chokepoint?sslmode=require
```

Replace `ENCODED_PASSWORD` with the encoded output. Keep `sslmode=require`. Do not paste the raw password into the URL if it contains `@`, `#`, `/`, `%`, `:`, `?`, or `&`.

## 3. Copy the storage connection string

Portal:

1. Open https://portal.azure.com/
2. Open resource group `rg-ais-chokepoint`.
3. Click the storage account (the name starts with `aiscpland`).
4. Left menu: **Security + networking** > **Access keys**.
5. Click **Show** next to key1.
6. Copy **Connection string** for key1.
7. In `.env` set:

```text
AZURE_STORAGE_ACCOUNT=yourstorageaccountname
AZURE_BLOB_CONTAINER=ais-raw
AZURE_STORAGE_CONNECTION_STRING=paste-the-connection-string
```

`AZURE_STORAGE_ACCOUNT` is only the account name, with no `.blob.core.windows.net`.

If you prefer the account key instead of the connection string, paste key1 into `AZURE_STORAGE_KEY` and leave `AZURE_STORAGE_CONNECTION_STRING` empty. One of the two methods is enough.

## 4. Confirm your laptop IP is still allowed

PostgreSQL Flexible Server firewall rules are tied to your current public IP. If your IP changed since pgAdmin last connected, add it again.

Portal: server `aiscpdbgg013` > **Networking** > **Add current client IP address** > Save.

CLI:

```powershell
az postgres flexible-server firewall-rule create `
  --resource-group rg-ais-chokepoint `
  --name aiscpdbgg013 `
  --rule-name laptop `
  --start-ip-address YOUR_PUBLIC_IP `
  --end-ip-address YOUR_PUBLIC_IP
```

You can read the current public IP from https://ifconfig.me/ip

## 5. Run three minutes

```powershell
cd C:\Users\gaura\Documents\grok_build_trial\adbms_project
uv sync --group dev
uv run adbms-ingest --duration 180
```

You should see:

- `ingest start` with the Singapore box
- `db ok; blob container ok; keys not printed`
- `connecting aisstream (key not printed)`
- `SubscriptionConfirmation`
- a progress line about every 30 seconds with `pos=`, `static=`, `q=`
- `ingest done` after about 180 seconds

Do not paste the terminal output into Git if you think a secret leaked. The worker is written so it does not print keys, passwords, or connection strings.

Stop early with Ctrl+C. It flushes the current blob and writes a heartbeat before it exits.

## 6. Check PostgreSQL in pgAdmin

Connect to database `chokepoint`. Query Tool, then F5:

```sql
SELECT count(*) AS positions FROM ais.vessel_position;
SELECT count(*) AS current_ships FROM ais.vessel_position_current;
SELECT count(*) AS static_rows FROM ais.vessel_static_current;
SELECT reason, count(*) FROM ais.quarantine GROUP BY reason ORDER BY 2 DESC;
SELECT ts, source, connected, msg_last_minute, distinct_mmsi_last_minute, lag_p50_s, lag_p95_s
FROM ops.ingest_heartbeat
ORDER BY ts DESC
LIMIT 10;
```

You want positions greater than zero, current ships greater than zero, and at least one heartbeat row. Quarantine can be zero. A few quarantine rows with reasons like `bad_coordinates` are normal.

A current-position sample:

```sql
SELECT mmsi, sog_kn, valid_time, ingest_time, source,
       ST_Y(geom::geometry) AS lat,
       ST_X(geom::geometry) AS lon
FROM ais.vessel_position_current
ORDER BY valid_time DESC
LIMIT 20;
```

`valid_time` is when the fact was true in the world. `ingest_time` is when this database learned it. Ingest lag in seconds is `extract(epoch from ingest_time - valid_time)`.

## 7. Check the blob

Portal:

1. Storage account > **Storage browser** > **Blob containers** > `ais-raw`.
2. Open `raw` > `ais` > year > month > day.
3. You should see an object named like `08.jsonl.gz` (the UTC hour while you ran).

CLI (do not print the key):

```powershell
az storage blob list `
  --account-name YOUR_STORAGE_ACCOUNT `
  --container-name ais-raw `
  --prefix raw/ais/ `
  --auth-mode login `
  --output table
```

## If it fails

| What you see | What to do |
| --- | --- |
| `DATABASE_URL is empty` | Save `.env` in `adbms_project/.env`, not in the parent folder. |
| `Blob auth is empty` | Set `AZURE_STORAGE_CONNECTION_STRING` or account plus key. |
| `PostgreSQL connect failed` | Add the current laptop IP on the Flexible Server firewall. Confirm `sslmode=require`. Confirm the password is URL-encoded. |
| `Blob check failed` | Recopy the connection string. Confirm container `ais-raw` exists inside the storage account. |
| `Table ais.vessel_position is missing` | Run `sql/schema/001_core.sql` on database `chokepoint`, not on `postgres`. |
| `connecting` then silence for minutes | Wait. The spike took a few seconds for the first AIS frame. If it stays at zero for five minutes, the worker tries Open Waters. |
| pgAdmin timeout | Your public IP changed. Add it again. |

## After the three-minute run works

You can run without `--duration` and leave the terminal open while you work:

```powershell
uv run adbms-ingest
```

That is still this laptop. History only grows while the process is running.

Next: [docs/geofences.md](geofences.md) (load polygons, run the query pack). The always-on Linux virtual machine comes after those queries.

Do not commit `.env`.
