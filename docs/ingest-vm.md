# Always-on ingest virtual machine

Laptop ingest works. This session puts the same worker on an Ubuntu virtual machine so history keeps growing when the laptop sleeps.

You create the Azure virtual machine yourself (portal or Azure CLI). This file is the click-by-click runbook. Do not paste passwords, API keys, or connection strings into Git, chat, or the report.

PostgreSQL is already running: Flexible Server `aiscpdbgg013` in **Central India**, database `chokepoint`. Create the virtual machine in that same region.

Stop laptop `adbms-ingest` after the virtual machine worker is healthy. Two workers can both write (duplicates are ignored), but they fight over the hourly blob object and they confuse heartbeat evidence.

## What you will have at the end

- Ubuntu 22.04 virtual machine `vm-ais-ingest` in `rg-ais-chokepoint`
- SSH from your laptop only (port 22)
- PostgreSQL firewall rule for the virtual machine public IP
- Worker running as systemd unit `ais-ingest`, restarting on failure
- Heartbeat rows in `ops.ingest_heartbeat` while you are away

## Names (already chosen)

```text
Resource group:      rg-ais-chokepoint
Region:              centralindia
PostgreSQL server:   aiscpdbgg013
PostgreSQL database: chokepoint
PostgreSQL admin:    chokepointadmin
Virtual machine:     vm-ais-ingest
VM admin user:       azureuser
Blob container:      ais-raw
```

The storage account name starts with `aiscpland`. Read it from the portal. Do not put the account key in this file.

## Hard rules

1. Linux only. Ubuntu Server 22.04 LTS. Not Windows.
2. Burstable size. Prefer `Standard_B1s`. If that size is blocked, `Standard_B2ats_v2` or `Standard_B2ts_v2`. Do not pick a D-series General Purpose size.
3. Same region as PostgreSQL: Central India (`centralindia`).
4. SSH key login. Do not enable password login.
5. Inbound ports: SSH (22) only. Not HTTP. Not PostgreSQL. PostgreSQL stays on the Flexible Server, not on this virtual machine.
6. Do not open SSH to `0.0.0.0/0` after you have your laptop IP. Tighten it in step 2.
7. Do not open the PostgreSQL firewall to the whole internet. Add the virtual machine public IP as one extra rule.
8. Keep the Azure for Students spending limit on. Do not upgrade to pay as you go.
9. Do not stop the virtual machine on a schedule. Overnight holes in history are the problem this machine exists to solve.
10. Secrets live in `/etc/ais-chokepoint.env` on the virtual machine, mode 640. Never in Git.

---

## 1. Create the virtual machine

### 1a. Portal (recommended the first time)

1. Open https://portal.azure.com/ and sign in with the school account that owns Azure for Students.
2. Resource group `rg-ais-chokepoint` > **Create** > **Virtual machine**.
3. Resource group: `rg-ais-chokepoint`.
4. Name: `vm-ais-ingest`.
5. Region: **Central India**. It must match PostgreSQL. If the portal lists `(Asia Pacific) Central India`, that is the one.
6. Availability options: No infrastructure redundancy required.
7. Security type: Standard is fine. Trusted Launch is OK if it is the default.
8. Image: **Ubuntu Server 22.04 LTS - x64 Gen2**.
9. Size: **See all sizes**. Search `B1s`. Pick **Standard_B1s** (1 vCPU, 1 GiB) if it exists. If the list is empty or the create button fails, try **Standard_B2ats_v2** (2 vCPU, 1 GiB), then **Standard_B2ts_v2**. Confirm RAM is 1 or 2 GiB. Write the size you actually got in your notepad.
10. Administrator account: **SSH public key**. Username: `azureuser`.
    - Let Azure generate a new key pair, or paste a public key you already have.
    - If Azure generates it, download the `.pem` immediately. You cannot download it again. Move it to `$HOME\.ssh\vm-ais-ingest_key.pem` (outside the Git repo).
11. Public inbound ports: **Allow selected ports** > **SSH (22)** only.
12. Disks: OS disk **Standard SSD**, locally redundant. No extra data disk. 32 GiB if the portal lets you. 64 GiB is acceptable. Do not pick 128 GiB Premium unless the image forces it.
13. Networking: a new virtual network in this resource group is fine. Public IP: Standard. NIC network security group: SSH only.
14. Management: enable **System assigned managed identity**.
15. Tags: `project=adbms`.
16. Review + create. Confirm Linux, the size, and Central India. Create.
17. Wait until the Overview blade says Running. Copy the **Public IP address** into your notepad.

### 1b. Azure CLI (same result)

PowerShell. `--generate-ssh-keys` reuses `~\.ssh\id_rsa` if it exists, otherwise it creates one.

```powershell
az account show --output table
az vm create `
  --resource-group rg-ais-chokepoint `
  --name vm-ais-ingest `
  --location centralindia `
  --image Ubuntu2204 `
  --size Standard_B1s `
  --admin-username azureuser `
  --generate-ssh-keys `
  --public-ip-sku Standard `
  --nsg-rule SSH `
  --assign-identity `
  --os-disk-size-gb 32 `
  --storage-sku StandardSSD_LRS
```

If the size is rejected:

```powershell
az vm create `
  --resource-group rg-ais-chokepoint `
  --name vm-ais-ingest `
  --location centralindia `
  --image Ubuntu2204 `
  --size Standard_B2ats_v2 `
  --admin-username azureuser `
  --generate-ssh-keys `
  --public-ip-sku Standard `
  --nsg-rule SSH `
  --assign-identity `
  --os-disk-size-gb 32 `
  --storage-sku StandardSSD_LRS
```

The command prints a public IP. Save it.

If create fails with a vCPU quota error, check:

```powershell
az vm list-usage --location centralindia --output table
```

PostgreSQL Flexible Server vCPUs are a different quota from virtual machine vCPUs. One B1ms database plus one B1s virtual machine is the intended pair.

---

## 2. Restrict SSH to your laptop IP

The default SSH rule is often the whole internet. Tighten it.

```powershell
$myip = (Invoke-RestMethod -Uri "https://api.ipify.org")
Write-Host "laptop public IP: $myip"
az network nsg list --resource-group rg-ais-chokepoint --output table
```

The network security group name is often `vm-ais-ingestNSG`. List rules, then update the SSH one:

```powershell
az network nsg rule list --resource-group rg-ais-chokepoint --nsg-name vm-ais-ingestNSG --output table
az network nsg rule update `
  --resource-group rg-ais-chokepoint `
  --nsg-name vm-ais-ingestNSG `
  --name default-allow-ssh `
  --source-address-prefixes "$myip/32"
```

If the rule name is different, use the name from the list (the one with destination port 22).

Portal path: virtual machine `vm-ais-ingest` > **Networking** > inbound rule for port 22 > Source: My IP address.

Home IPs change. If SSH suddenly times out the next day, add the new IP the same way. Do not "fix" it by opening `0.0.0.0/0`.

---

## 3. SSH in and check outbound HTTPS

If Azure saved the key as `vm-ais-ingest_key.pem` in Downloads, move it and lock permissions:

```powershell
New-Item -ItemType Directory -Force -Path $HOME\.ssh | Out-Null
Move-Item -Force $HOME\Downloads\vm-ais-ingest_key.pem $HOME\.ssh\vm-ais-ingest_key.pem
icacls $HOME\.ssh\vm-ais-ingest_key.pem /inheritance:r
icacls $HOME\.ssh\vm-ais-ingest_key.pem /grant:r "$($env:USERNAME):(R)"
```

SSH (replace `VM_PUBLIC_IP`):

```powershell
ssh -i $HOME\.ssh\vm-ais-ingest_key.pem azureuser@VM_PUBLIC_IP
```

If you used `--generate-ssh-keys` and the key is `id_rsa`:

```powershell
ssh azureuser@VM_PUBLIC_IP
```

On the virtual machine you should see an Ubuntu prompt. Check outbound HTTPS (AISStream, Open Waters, and Blob all use TLS):

```bash
curl -I https://stream.aisstream.io
curl -I https://ais.openwaters.io
curl -I https://aka.ms
```

You want a response, even an HTTP error. A hang means outbound 443 is blocked, which would kill ingest.

Leave this SSH session open. You will use it in later steps.

---

## 4. Let the virtual machine talk to PostgreSQL

From PowerShell on the laptop (not inside SSH):

```powershell
az vm list-ip-addresses --resource-group rg-ais-chokepoint --name vm-ais-ingest --output table
```

Add that **public** IP to the Flexible Server firewall. Do not use the private 10.x address unless you later build a private network.

Portal: Flexible Server `aiscpdbgg013` > **Networking** > Add a firewall rule. Name: `vm-ais-ingest`. Start and end IP: the virtual machine public IP.

CLI:

```powershell
az postgres flexible-server firewall-rule create `
  --resource-group rg-ais-chokepoint `
  --name aiscpdbgg013 `
  --rule-name vm-ais-ingest `
  --start-ip-address VM_PUBLIC_IP `
  --end-ip-address VM_PUBLIC_IP
```

Keep the existing laptop firewall rule. pgAdmin still needs it.

From the virtual machine (SSH session):

```bash
sudo apt-get update
sudo apt-get install -y postgresql-client
psql "host=aiscpdbgg013.postgres.database.azure.com port=5432 dbname=chokepoint user=chokepointadmin sslmode=require"
```

It will prompt for the admin password. Type it. Then:

```sql
SELECT current_database(), PostGIS_Version();
\q
```

Expect database `chokepoint` and PostGIS 3.6. If this times out, the firewall rule is missing or you added the private IP. If SSL fails, you omitted `sslmode=require`.

---

## 5. Copy the project onto the virtual machine

GitHub `origin/main` is behind the laptop. Copy from this machine, not `git clone`, until you choose to push.

On the virtual machine (SSH):

```bash
sudo mkdir -p /opt/ais-chokepoint
sudo chown azureuser:azureuser /opt/ais-chokepoint
```

On the laptop, in PowerShell. This sends the committed tree only (no `.venv`, no `.env`):

```powershell
cd C:\Users\gaura\Documents\grok_build_trial\adbms_project
git archive --format=tar HEAD | ssh -i $HOME\.ssh\vm-ais-ingest_key.pem azureuser@VM_PUBLIC_IP "tar -x -C /opt/ais-chokepoint"
```

If the pipe is awkward, pack then copy:

```powershell
cd C:\Users\gaura\Documents\grok_build_trial\adbms_project
git archive --format=tar --output $HOME\ais-chokepoint.tar HEAD
scp -i $HOME\.ssh\vm-ais-ingest_key.pem $HOME\ais-chokepoint.tar azureuser@VM_PUBLIC_IP:~/
```

Then on the virtual machine:

```bash
tar -x -f ~/ais-chokepoint.tar -C /opt/ais-chokepoint
rm ~/ais-chokepoint.tar
ls /opt/ais-chokepoint/docs/ingest-vm.md
```

Delete `ais-chokepoint.tar` from the laptop afterwards.

---

## 6. Install secrets on the virtual machine

The worker reads the same environment variables as the laptop. Copy `.env` to a root-owned file. Do not put that file in Git. Do not paste its contents into chat.

On the laptop:

```powershell
scp -i $HOME\.ssh\vm-ais-ingest_key.pem `
  C:\Users\gaura\Documents\grok_build_trial\adbms_project\.env `
  azureuser@VM_PUBLIC_IP:/tmp/ais-chokepoint.env
```

On the virtual machine:

```bash
sudo mv /tmp/ais-chokepoint.env /etc/ais-chokepoint.env
sudo chown root:azureuser /etc/ais-chokepoint.env
sudo chmod 640 /etc/ais-chokepoint.env
sudo ls -l /etc/ais-chokepoint.env
```

Expect `-rw-r----- 1 root azureuser`. Confirm names only (no values) with:

```bash
sudo grep -E '^[A-Z_]+=' /etc/ais-chokepoint.env | sed 's/=.*/=***hidden***/'
```

Needed names: `AISSTREAM_API_KEY`, `DATABASE_URL`, blob auth (`AZURE_STORAGE_CONNECTION_STRING` or account plus key), `AZURE_BLOB_CONTAINER=ais-raw`. `OPENWATERS_API_KEY` if you use auto fallback. If a name is missing, `sudo nano /etc/ais-chokepoint.env`. Do not `cat` the file into a screenshot.

---

## 7. Install Python 3.12, uv, and the worker

Still on the virtual machine:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
cd /opt/ais-chokepoint
uv python install 3.12
uv sync
/opt/ais-chokepoint/.venv/bin/adbms-ingest --help
```

Expect the ingest help text. If `uv` is "command not found" after the installer, log out of SSH and back in, or run `source "$HOME/.local/bin/env"` again.

Install the systemd unit:

```bash
sudo cp /opt/ais-chokepoint/deploy/ais-ingest.service /etc/systemd/system/ais-ingest.service
sudo systemctl daemon-reload
sudo systemctl enable ais-ingest
sudo systemctl start ais-ingest
sudo systemctl status ais-ingest --no-pager
```

`status` should say `active (running)`. Then:

```bash
journalctl -u ais-ingest -n 40 --no-pager
```

Expect a line like `ingest start ... box=singapore` and `db ok; blob container ok; keys not printed`. You should see `SubscriptionConfirmation` within a few seconds.

If it exited:

- `PostgreSQL connect failed`: firewall rule or `DATABASE_URL`.
- `Blob check failed`: storage connection string or container name.
- `AISSTREAM_API_KEY is empty`: `/etc/ais-chokepoint.env` not loaded. Check `systemctl show ais-ingest -p EnvironmentFiles`.
- Permission denied on `.venv`: `sudo chown -R azureuser:azureuser /opt/ais-chokepoint`.

---

## 8. Confirm from pgAdmin on the laptop

Connect to `chokepoint` as usual (laptop IP still on the PostgreSQL firewall). Run:

```sql
SELECT ts, source, connected, msg_last_minute, distinct_mmsi_last_minute, lag_p50_s
FROM ops.ingest_heartbeat
ORDER BY ts DESC
LIMIT 10;
```

Expect a new row about every 60 seconds, `connected = true`, and `application_name` `adbms-ingest` in:

```sql
SELECT pid, usename, application_name, client_addr, state
FROM pg_stat_activity
WHERE datname = 'chokepoint'
ORDER BY query_start NULLS LAST;
```

`client_addr` should be the virtual machine public IP, not your laptop.

Optional: D10 and D16 from `sql/diagnostics/catalog.sql`. After a few minutes, `fresh_within_15_min` should be greater than zero.

---

## 9. Stop laptop ingest

On the laptop, in the PowerShell window that was running `uv run adbms-ingest`, press Ctrl+C. Leave the virtual machine worker running.

Do not run `adbms-ingest` on the laptop again unless you have stopped systemd (`sudo systemctl stop ais-ingest`). One writer at a time.

---

## 10. Day-to-day operations

| Action | Command (on the virtual machine) |
| --- | --- |
| Live log | `journalctl -u ais-ingest -f` |
| Restart after a code copy | `sudo systemctl restart ais-ingest` |
| Stop | `sudo systemctl stop ais-ingest` |
| Start | `sudo systemctl start ais-ingest` |
| Enabled on boot | `systemctl is-enabled ais-ingest` |

After you copy a newer tree with `git archive` again:

```bash
cd /opt/ais-chokepoint
source "$HOME/.local/bin/env"
uv sync
sudo systemctl restart ais-ingest
```

Transit and dwell refresh still runs on a laptop when you want Q3 and Q4:

```powershell
cd C:\Users\gaura\Documents\grok_build_trial\adbms_project
uv run adbms-events
```

You can add a systemd timer for that later. It is not required to keep positions flowing.

---

## 11. What you should not do

- Do not create a second virtual machine to try a size. Delete a failed one the same day, including its disk, NIC, and public IP.
- Do not install Docker, Kubernetes, or nginx. systemd is the process manager.
- Do not open port 5432 on the virtual machine. PostgreSQL is the Flexible Server.
- Do not commit `/etc/ais-chokepoint.env` or copy it into the repo.
- Do not deallocate the virtual machine overnight. Deallocate stops ingest.

Delete a failed virtual machine (laptop PowerShell), only if you intend to recreate it:

```powershell
az vm delete --resource-group rg-ais-chokepoint --name vm-ais-ingest --yes
```

Then check the resource group for leftover disks, NICs, and public IPs and delete those too.

---

## 12. Record facts (no secrets)

Keep this in a notepad, not in Git:

```text
VM size actually provisioned:
VM public IP:
SSH key path:
PostgreSQL firewall rule vm-ais-ingest: yes/no
NSG SSH source: laptop /32
systemctl status ais-ingest: active / failed
First heartbeat timestamp (UTC):
```

Screenshot for the report (redact keys): virtual machine Overview (size and region), PostgreSQL firewall list, `systemctl status ais-ingest` in the SSH window.
