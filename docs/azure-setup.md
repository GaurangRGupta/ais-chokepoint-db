# Azure setup for the AIS chokepoint database

You create these resources yourself, using the Azure portal and/or Azure CLI, so you learn both. This file is the runbook. Do not paste passwords, API keys, or connection strings into Git, chat, or the report.

The project uses one Azure for Students subscription as the data plane. Do not create matching resources on Amazon Web Services (AWS). Keep the AWS credits as a spare.

You do not need to finish this before the day-1 Automatic Identification System (AIS) spike. The spike is a local Python script. You can do Session A now (login, credit, region, resource group, storage). Do Session B (database and virtual machine) when you are ready. The database and virtual machine start the always-on bill. A day or two of learning cost is small. Leaving a General Purpose database running for weeks is not.

## What you will create

One resource group in one region, containing:

| Resource | Purpose | Target size |
| --- | --- | --- |
| Resource group | Folder for everything | `rg-ais-chokepoint` |
| Storage account + blob container | Raw AIS landing zone and demo-day replay | Standard, locally redundant, Hot, container `ais-raw` |
| Azure Database for PostgreSQL Flexible Server | System of record | Burstable `Standard_B1ms`, 32 GB, PostgreSQL 16, high availability off |
| Linux virtual machine | Always-on ingest worker | Burstable 1 vCPU class, Ubuntu 22.04, SSH key only |
| Budget / credit watch | Stop a surprise burn | Sponsorships portal plus a budget if the portal allows it |

Also: PostGIS allowed and created, SSL required, firewall limited to your laptop IP and the virtual machine IP.

## Names to pick once and reuse

Copy these into a notepad that is not in the Git repo. Storage account names must be globally unique, 3 to 24 characters, lowercase letters and digits only. PostgreSQL server names must be globally unique too.

```text
Resource group:     rg-ais-chokepoint
Region:             eastus          (change if the student policy blocks it)
Storage account:    aiscpland<yourinitials><3digits>     example: aiscplandgg017
Blob container:     ais-raw
PostgreSQL server:  aiscpdb<yourinitials><3digits>       example: aiscpdbgg017
PostgreSQL admin:   chokepointadmin
PostgreSQL database: chokepoint
Virtual machine:    vm-ais-ingest
VM admin user:      azureuser
```

The PostgreSQL admin name must not be `admin`, `administrator`, `root`, `guest`, `public`, or start with `azure_`. `chokepointadmin` is safe.

Generate a long password (16+ characters, upper, lower, digit, symbol). Store it in a password manager. You will type it into the portal or into a CLI prompt. Never put it in a script that you commit.

## Hard rules (read before you click)

1. Keep the Azure for Students spending limit on. If credit runs out, Azure stops the subscription. That is better than a bill. Do not upgrade to pay as you go for this course project.
2. One region. One availability zone. High availability off.
3. Burstable compute only. If the portal offers General Purpose `D2ds` or similar, you picked the wrong tier. Go back.
4. Storage 32 GB. Do not pick 128 GB "because it is the default".
5. Do not open the PostgreSQL firewall to `0.0.0.0/0` or "allow public access from any Azure service" unless a later step fails without it. Start with your IP only.
6. Do not enable geo-redundant backup.
7. Do not create a Windows virtual machine. Linux only.
8. Do not create a second Flexible Server "to try something". Restore drills later use a temporary server that you delete the same day.

## Session A. Login, credit, region, group, storage

Do this first. It costs almost nothing.

### A1. See which account you are using

Portal:

1. Open https://portal.azure.com/ and sign in with the school account that owns Azure for Students.
2. Top right, confirm the directory and the subscription name. It should say Azure for Students, not a pay-as-you-go subscription.

CLI, in PowerShell:

```powershell
az version
az login
az account show --output table
az account list --output table
```

`az login` opens a browser. If you have more than one subscription, set the student one:

```powershell
az account set --subscription "Azure for Students"
az account show --query "{name:name, id:id, offer:offerId, state:state}" --output table
```

Azure for Students often has offer ID `MS-AZR-0170P`. If `az account show` lists a different subscription as default, stop and switch.

### A2. Remaining credit

The Azure portal often shows `$0.00` on a student subscription because the offer applies a 100 percent discount. That number is not your remaining credit.

Authoritative balance:

1. Open https://www.microsoftazuresponsorships.com/Balance
2. Sign in with the same school account.
3. Write down remaining credit and the expiry date.

Also open Education Hub in the Azure portal (search for **Education**) and note monthly usage.

Check this page once a week for the rest of the semester.

### A3. Allowed regions (student accounts are restricted)

Portal:

1. Search for **Policy**.
2. Open **Assignments**.
3. Look for **Allowed resource deployment regions** (wording varies).
4. Open it and write down the allowed region list.

CLI:

```powershell
az policy assignment list --query "[].{name:displayName, id:id}" --output table
```

If you see an allowed-regions assignment, open it in the portal and read the region list. Typical student sets include a handful of regions. They are not the same for every student.

Try regions in this order, but only if they appear in your allowed list:

1. `eastus`
2. `eastus2`
3. `westus2`
4. `westeurope`

Do not pick Southeast Asia unless every cheaper allowed region fails. The ships are in Singapore. The database does not need to be.

### A4. Confirm the cheap PostgreSQL size exists in that region

```powershell
az postgres flexible-server list-skus --location eastus --output table
```

You want a row like `Standard_B1ms` with tier `Burstable`. If `eastus` errors, repeat with `eastus2`, then `westus2`, then `westeurope`.

If Burstable `B1ms` is missing, try the next region. Do not "just pick D2ds_v5".

### A5. Create the resource group

Portal:

1. Search **Resource groups** > **Create**.
2. Subscription: Azure for Students.
3. Name: `rg-ais-chokepoint`.
4. Region: the region you confirmed in A3/A4.
5. Tags (optional): `project=adbms`, `course=adbms`.
6. Review + create > Create.

CLI:

```powershell
az group create --name rg-ais-chokepoint --location eastus --tags project=adbms course=adbms
```

Change `--location` if you are not using East US.

### A6. Budget alert

Azure for Students sometimes supports Cost Management budgets, and sometimes the subscription is greyed out because it is a sponsorship offer. Try it. If it fails, rely on the Sponsorships portal and a calendar reminder.

Portal:

1. Open the resource group `rg-ais-chokepoint`.
2. Left menu: **Budgets** (under Cost Management). If the blade says Cost Management is not supported, skip to A6b.
3. Add a budget.
4. Scope: this resource group.
5. Name: `ais-chokepoint-50`.
6. Reset period: Monthly, or Billing month if that is the only option.
7. Amount: `50` (US dollars). This is an alert, not a hard stop. The hard stop is the student spending limit at $100.
8. Alert conditions: 50 percent and 80 percent and 100 percent. Email: your school address.
9. Create.
10. Repeat with name `ais-chokepoint-80` and amount `80` if you prefer two named budgets. One budget with three thresholds is enough.

CLI (this may fail on student offers; that is OK):

```powershell
az consumption budget create `
  --budget-name ais-chokepoint-50 `
  --category cost `
  --amount 50 `
  --time-grain monthly `
  --start-date 2026-10-01 `
  --end-date 2027-06-01 `
  --resource-group rg-ais-chokepoint
```

Use the first day of the current month as `--start-date`.

A6b. If budgets are blocked:

- Pin https://www.microsoftazuresponsorships.com/Balance
- Set a weekly reminder titled "AIS Azure credit check"

### A7. Storage account (landing zone)

Portal:

1. In `rg-ais-chokepoint`, **Create** > search **Storage account**.
2. Name: your unique `aiscpland...` name.
3. Region: same as the resource group.
4. Performance: Standard.
5. Redundancy: Locally-redundant storage (LRS). Not GRS. Not ZRS.
6. Next: Networking. Public network access: Enable from all networks for now (the ingest virtual machine and your laptop both need it). You can tighten this later.
7. Next: Encryption. Leave Microsoft-managed keys.
8. Next: Data protection. You can leave versioning off.
9. Review + create. On the summary, confirm redundancy is LRS and the region is correct. Create.

Then create the container:

1. Open the storage account > **Containers** > **+ Container**.
2. Name: `ais-raw`.
3. Anonymous access level: Private (no anonymous access).
4. Create.

CLI:

```powershell
az storage account create `
  --name aiscplandgg017 `
  --resource-group rg-ais-chokepoint `
  --location eastus `
  --sku Standard_LRS `
  --kind StorageV2 `
  --access-tier Hot `
  --min-tls-version TLS1_2 `
  --allow-blob-public-access false `
  --https-only true

az storage container create `
  --name ais-raw `
  --account-name aiscplandgg017 `
  --auth-mode login
```

If `--auth-mode login` fails, sign in to the data plane first:

```powershell
az login
az storage container create --name ais-raw --account-name aiscplandgg017 --auth-mode login
```

Or use the account key (do not commit the key):

```powershell
$stkey = az storage account keys list --account-name aiscplandgg017 --resource-group rg-ais-chokepoint --query "[0].value" --output tsv
az storage container create --name ais-raw --account-name aiscplandgg017 --account-key $stkey
```

### A8. Session A checks

```powershell
az group show --name rg-ais-chokepoint --output table
az storage account show --name aiscplandgg017 --resource-group rg-ais-chokepoint --query "{name:name, location:location, sku:sku.name, https:enableHttpsTrafficOnly}" --output table
az storage container list --account-name aiscplandgg017 --auth-mode login --output table
```

You should have a resource group, a storage account on LRS, and container `ais-raw`. Remaining credit should barely have moved.

---

## Session B. PostgreSQL Flexible Server

This is the resource that costs about $12 per month in East US if it is not covered by free hours. Create it when you are ready to keep it on.

### B1. Create the server (portal, recommended the first time)

1. In `rg-ais-chokepoint`, **Create** > search **Azure Database for PostgreSQL**. Choose **Flexible server** (not Single server, not Cosmos DB).
2. Subscription and resource group: the student subscription and `rg-ais-chokepoint`.
3. Server name: your unique `aiscpdb...` name. The portal will add `.postgres.database.azure.com`.
4. Region: same as the resource group. If Create is disabled or the SKU list is empty, the region is blocked. Cancel and use the next allowed region. Moving a server later is painful, so get the region right.
5. PostgreSQL version: **16**. If 16 is missing, 17 is acceptable. Prefer 16 if both exist.
6. Workload type: **Development**. This is what exposes Burstable sizes.
7. **Configure server** (Compute + storage):
   - Compute tier: **Burstable**.
   - Compute size: **Standard_B1ms** (1 vCore, 2 GiB). If the portal only shows B2s or D-series, you are on the wrong tier or a blocked SKU. Do not accept General Purpose.
   - Storage: **32 GiB**. Storage can grow later. It cannot shrink.
   - Storage autogrow: **Enable**.
   - High availability: **Disabled**. Burstable often cannot enable it anyway. Do not switch to General Purpose just to turn HA on.
   - Backup retention: **7 days**.
   - Backup redundancy: **Locally redundant**.
8. Authentication: **PostgreSQL authentication only** for now.
   - Admin username: `chokepointadmin`
   - Password: the long password from your notepad.
9. Networking:
   - Connectivity method: **Public access (allowed IP addresses)**.
   - Do **not** tick "Allow public access from any Azure service within Azure to this server" unless a later connection from the virtual machine fails.
   - Add current client IP address: **Yes**. That is your laptop, for pgAdmin.
   - Firewall rule name example: `laptop-gaurang`.
10. Security / encryption: service-managed keys. Defaults are fine.
11. Tags: `project=adbms`.
12. Review + create.

On the review screen, read these four lines out loud before you click Create:

- SKU is `Standard_B1ms` / Burstable
- Storage is 32 GiB
- High availability is Disabled
- Region is the one you chose

Create. Provisioning takes 5 to 10 minutes. Wait until the server shows **Ready**.

### B2. Create the server (CLI)

Replace names, location, and password. `--public-access` here is your current public IP, not `0.0.0.0`.

Find your public IP:

```powershell
(Invoke-RestMethod -Uri "https://api.ipify.org")
```

Then:

```powershell
az postgres flexible-server create `
  --resource-group rg-ais-chokepoint `
  --name aiscpdbgg017 `
  --location eastus `
  --admin-user chokepointadmin `
  --admin-password "PASTE_PASSWORD_HERE" `
  --sku-name Standard_B1ms `
  --tier Burstable `
  --storage-size 32 `
  --version 16 `
  --high-availability Disabled `
  --backup-retention 7 `
  --public-access "YOUR.PUBLIC.IP.HERE" `
  --yes
```

If the command errors on `--storage-size 32`, the region may require a higher minimum. Try `64` only if 32 is rejected, and write that down for the report.

Create the application database:

```powershell
az postgres flexible-server db create `
  --resource-group rg-ais-chokepoint `
  --server-name aiscpdbgg017 `
  --database-name chokepoint
```

### B3. Confirm SSL and compute

Portal: open the server > **Overview**. Note the fully qualified domain name, for example `aiscpdbgg017.postgres.database.azure.com`. Open **Compute + storage** and screenshot Burstable B1ms / 32 GiB for the DBA folder later (no password in the shot).

CLI:

```powershell
az postgres flexible-server show `
  --resource-group rg-ais-chokepoint `
  --name aiscpdbgg017 `
  --query "{name:name, fqdn:fullyQualifiedDomainName, sku:sku.name, tier:sku.tier, version:version, ha:highAvailability.mode, storage:storage.storageSizeGb, state:state}" `
  --output table
```

### B4. Allow PostGIS, then create it

Azure requires two steps. Allow-list the extension on the server, then `CREATE EXTENSION` inside the database.

Portal:

1. Open the Flexible Server > **Server parameters** (sometimes labelled **Parameters**).
2. Search `azure.extensions`.
3. Tick **POSTGIS**. Also tick **BTREE_GIST** if it appears (needed for range exclusion later).
4. Save. Wait for the parameter deployment to finish.
5. You do not need to put PostGIS in `shared_preload_libraries` for basic geography types.

CLI:

```powershell
az postgres flexible-server parameter set `
  --resource-group rg-ais-chokepoint `
  --server-name aiscpdbgg017 `
  --name azure.extensions `
  --value "POSTGIS,BTREE_GIST"
```

Then connect with SSL and create the extension. On Windows, `psql` is available if you installed PostgreSQL client tools. Azure Cloud Shell also has `psql`.

```powershell
psql "host=aiscpdbgg017.postgres.database.azure.com port=5432 dbname=chokepoint user=chokepointadmin sslmode=require"
```

Inside `psql`:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;
SELECT PostGIS_Version();
```

You should see a PostGIS version string, commonly 3.x. Type `\q` to quit.

If `psql` is missing, install the PostgreSQL 16 client, or use Azure Cloud Shell, or use pgAdmin (next step).

### B5. Connect from pgAdmin on your laptop

1. Install pgAdmin 4 if you do not have it.
2. Register > Server.
3. General name: `ais-chokepoint`.
4. Connection:
   - Host: `aiscpdbgg017.postgres.database.azure.com`
   - Port: `5432`
   - Maintenance database: `chokepoint`
   - Username: `chokepointadmin`
   - Password: saved password
5. SSL: SSL mode **Require**.
6. Save.

If it times out, your home IP changed. Add the new IP:

Portal: Flexible Server > **Networking** > Add current client IP.

CLI:

```powershell
$myip = (Invoke-RestMethod -Uri "https://api.ipify.org")
az postgres flexible-server firewall-rule create `
  --resource-group rg-ais-chokepoint `
  --name aiscpdbgg017 `
  --rule-name laptop-gaurang `
  --start-ip-address $myip `
  --end-ip-address $myip
```

Home internet IPs change. When pgAdmin suddenly fails, it is usually this. Add a new rule or update the existing one. Do not "fix" it by opening `0.0.0.0`.

---

## Session C. Linux virtual machine (ingest host)

The worker must stay on. This virtual machine is that host. Create it in the **same region** as PostgreSQL (this project: Central India). After the machine exists, software install is [ingest-vm.md](ingest-vm.md).

### C1. Pick a size

Preferred: `Standard_B1s` (1 vCore, 1 GiB), about $8 per month in East US.

B-series version 1 is being retired in some regions and Azure for Students often refuses it. If `Standard_B1s` is unavailable, use one of these, still burstable, still small:

- `Standard_B2ats_v2` (AMD, 2 vCPU, 1 GiB) often listed as free-eligible for students
- `Standard_B2ts_v2`
- `Standard_B1ms` (1 vCPU, 2 GiB) if the others fail

Check:

```powershell
az vm list-skus --location eastus --size Standard_B --output table
```

Look at the `Name` column. If `Standard_B1s` is not there, pick `Standard_B2ats_v2`.

Do not pick `Standard_D2s_v3` or anything with 8 GiB unless B-series is completely blocked. Write the chosen size down.

OS disk: Standard SSD, 32 GiB if the portal lets you pick 32. 64 GiB is acceptable. Do not pick 128 GiB Premium unless the image forces it. A larger disk costs more every month.

### C2. Create the virtual machine (portal)

1. In `rg-ais-chokepoint`, **Create** > **Virtual machine**.
2. Resource group: `rg-ais-chokepoint`.
3. Name: `vm-ais-ingest`.
4. Region: same as PostgreSQL.
5. Availability options: No infrastructure redundancy required.
6. Security type: Standard is fine. Trusted Launch is OK if it is the default.
7. Image: **Ubuntu Server 22.04 LTS - x64 Gen2**.
8. Size: **See all sizes** > search `B1s` or `B2ats`. Pick the size from C1. Confirm vCPUs is 1 or 2 and RAM is 1 or 2 GiB.
9. Administrator account: **SSH public key**. Username: `azureuser`. Let Azure generate a new key pair, or paste your existing public key. If Azure generates it, download the private key `.pem` and store it outside the repo, for example in your user `.ssh` folder. You cannot download it again.
10. Public inbound ports: **Allow selected ports** > **SSH (22)** only. Not HTTP. Not PostgreSQL.
11. Disks: OS disk Standard SSD (locally redundant). No extra data disk.
12. Networking: new virtual network is fine. Public IP: Standard. NIC network security group: Basic, SSH only.
13. Management: enable **System assigned managed identity**. You will use this later so the virtual machine can write blobs without a storage key in a file.
14. Review + create. Confirm the size and that the OS is Linux. Create.
15. If Azure generated the key, download it immediately.

### C3. Create the virtual machine (CLI)

PowerShell on Windows. `--generate-ssh-keys` reuses `~\.ssh\id_rsa` if it exists, otherwise it creates one.

```powershell
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

If the size is rejected, retry with `--size Standard_B2ats_v2`.

The command prints a public IP. Save it.

### C4. Restrict SSH to your IP

The default SSH rule is often `0.0.0.0/0`. Tighten it.

Portal: virtual machine > **Networking** > inbound rule for port 22 > Source: My IP address.

CLI (network security group name is often `vm-ais-ingestNSG`):

```powershell
$myip = (Invoke-RestMethod -Uri "https://api.ipify.org")
az network nsg rule update `
  --resource-group rg-ais-chokepoint `
  --nsg-name vm-ais-ingestNSG `
  --name default-allow-ssh `
  --source-address-prefixes "$myip/32"
```

If the rule name is different:

```powershell
az network nsg list --resource-group rg-ais-chokepoint --output table
az network nsg rule list --resource-group rg-ais-chokepoint --nsg-name vm-ais-ingestNSG --output table
```

### C5. SSH in and sanity-check

From PowerShell, using the downloaded key:

```powershell
ssh -i $HOME\.ssh\id_rsa azureuser@VM_PUBLIC_IP
```

If Azure saved the key as a `.pem` in Downloads:

```powershell
ssh -i $HOME\Downloads\vm-ais-ingest_key.pem azureuser@VM_PUBLIC_IP
```

On Windows, if SSH refuses the key permissions, move the key into `$HOME\.ssh\` and, if needed, run:

```powershell
icacls $HOME\.ssh\vm-ais-ingest_key.pem /inheritance:r
icacls $HOME\.ssh\vm-ais-ingest_key.pem /grant:r "$($env:USERNAME):(R)"
```

On the virtual machine you should see an Ubuntu prompt. Check outbound HTTPS (AISStream and Blob both use TLS):

```bash
curl -I https://stream.aisstream.io
curl -I https://ais.openwaters.io
```

You want a response, even an HTTP error. A hang means outbound 443 is blocked, which would kill ingest.

Install nothing heavy yet. Later we will put `uv` and the worker here. For now, confirm you can log in.

### C6. Let the virtual machine talk to PostgreSQL

Get the virtual machine public IP (Overview blade, or):

```powershell
az vm list-ip-addresses --resource-group rg-ais-chokepoint --name vm-ais-ingest --output table
```

Add it to the PostgreSQL firewall:

Portal: Flexible Server > **Networking** > Add a firewall rule. Name: `vm-ais-ingest`. Start and end IP: the virtual machine public IP.

CLI:

```powershell
az postgres flexible-server firewall-rule create `
  --resource-group rg-ais-chokepoint `
  --name aiscpdbgg017 `
  --rule-name vm-ais-ingest `
  --start-ip-address VM_PUBLIC_IP `
  --end-ip-address VM_PUBLIC_IP
```

From the virtual machine, test (install the client first):

```bash
sudo apt-get update
sudo apt-get install -y postgresql-client
psql "host=aiscpdbgg017.postgres.database.azure.com port=5432 dbname=chokepoint user=chokepointadmin sslmode=require"
```

It will prompt for the password. `SELECT PostGIS_Version();` should work. If this times out, the firewall rule is wrong or you added the private IP by mistake. Use the public IP unless you later build a private network.

### C7. Let the virtual machine write blobs (managed identity)

This avoids storing the storage account key on disk.

Portal:

1. Storage account > **Access Control (IAM)** > **Add role assignment**.
2. Role: **Storage Blob Data Contributor**.
3. Members: Managed identity > virtual machine `vm-ais-ingest`.
4. Review + assign.

CLI:

```powershell
$vmId = az vm show --resource-group rg-ais-chokepoint --name vm-ais-ingest --query identity.principalId --output tsv
$storageId = az storage account show --name aiscplandgg017 --resource-group rg-ais-chokepoint --query id --output tsv
az role assignment create `
  --assignee-object-id $vmId `
  --assignee-principal-type ServicePrincipal `
  --role "Storage Blob Data Contributor" `
  --scope $storageId
```

Role assignments can take a few minutes. Later the worker will use DefaultAzureCredential. For a first blob test from the virtual machine you can still use an account key kept in an environment file that is not in Git.

---

## Session D. Record facts for the team (no secrets)

Create a file on your machine, not in Git, or put a redacted copy in `reports/dba/` later:

```text
Subscription: Azure for Students
Region:
Resource group: rg-ais-chokepoint
Storage account:
Container: ais-raw
PostgreSQL FQDN: something.postgres.database.azure.com
PostgreSQL version:
SKU:
PostGIS version:
VM name: vm-ais-ingest
VM size:
VM public IP:
Laptop firewall rule: yes/no
VM firewall rule: yes/no
Sponsorships remaining credit after setup:
```

Screenshot (redact passwords):

- Flexible Server compute + storage blade
- Networking firewall rules (IPs are OK)
- Sponsorships balance
- Virtual machine size

---

## If something fails

### Region or policy error

The student **Allowed resource deployment regions** policy is the usual cause. Switch to a region on that list. Recreate the resource group in the new region. Resources cannot sit in a group whose location disagrees with what you want in a clean way; keep one group, one region.

### PostgreSQL SKU not available

`az postgres flexible-server list-skus --location <region>`. If `Standard_B1ms` is absent, change region. If only General Purpose exists, still change region. Do not upgrade the tier to "make Create work".

### Virtual machine size not available

Try `Standard_B2ats_v2`, then `Standard_B2ts_v2`, then `Standard_B1ms`. Check **Usage + quotas** on the subscription if every size fails. Student quotas can be 2 vCPUs in a region. One B1ms database plus one B1s virtual machine fits. A D2s virtual machine may not.

### pgAdmin timeout

Your public IP changed. Add it again. Confirm `sslmode=require`. Confirm the server state is Ready, not Stopped. Flexible Server can be stopped from the portal; do not stop it if ingest is supposed to run.

### `CREATE EXTENSION postgis` fails

The allow-list step was skipped or did not finish. Re-save `azure.extensions` with `POSTGIS`. Connect to database `chokepoint`, not `postgres`.

### Credit looks like zero in the Azure portal

Ignore portal Cost analysis if it shows $0. Use https://www.microsoftazuresponsorships.com/Balance

### You created the wrong SKU

Delete it the same day. Open the resource > Delete. Then recreate. Do not leave a D-series server running "until next week".

Delete a Flexible Server:

```powershell
az postgres flexible-server delete --resource-group rg-ais-chokepoint --name aiscpdbgg017 --yes
```

Delete a virtual machine and its disks / NIC / public IP is messier in the portal: delete the VM and tick the associated NICs, public IP, and OS disk if the portal offers that. Check the resource group afterwards and delete leftover disks so they do not keep billing.

---

## What you should not set up yet

- Extra Azure Database for PostgreSQL servers
- Azure Kubernetes Service, Container Apps, Functions, or App Service (the virtual machine is the ingest host)
- Virtual network private endpoints (stretch extra, not required)
- Key Vault (nice later; environment variables on the virtual machine are enough for the first worker)
- Microsoft Entra-only PostgreSQL login (password auth is enough for the viva)
- Stopping the virtual machine or the database on a schedule (history needs always-on ingest)

---

## After the resources exist

Tell the rest of the team:

1. Region and SKUs that actually provisioned (especially if you had to leave `eastus` or `Standard_B1s`).
2. PostgreSQL fully qualified domain name.
3. That PostGIS `SELECT PostGIS_Version();` works from your laptop and from the virtual machine.
4. Remaining student credit.

Do not send the admin password or storage keys in chat. Share them in person or a password manager.

After the virtual machine exists, install the worker with [ingest-vm.md](ingest-vm.md) and `deploy/ais-ingest.service`. Roles `ingest_writer` / `analyst_ro` remain a later DBA drill.
