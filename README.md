# Family EPUB Portal

A free, low-traffic family book request system:

- GitHub Pages hosts the public site.
- A Google Apps Script web app receives no-login book requests and stores them in your private Google Sheet.
- A Windows scheduled Python worker searches configured authorized EPUB sources, renames files, uploads to your private Google Drive folder with rclone, and republishes public status JSON.

The system is configurable, but it intentionally does not include piracy-site adapters.

## Live Site

Current public site:

```text
https://claudegptimini.github.io/family-epub-portal/
```

## What You Still Need To Authorize

Private Google resources require your approval. No one else needs to log in.

You will do these once:

1. Create a private Google Sheet for requests.
2. Deploy `apps-script/Code.gs` as a Google Apps Script web app.
3. Configure rclone on the Windows worker so it can upload to your private Google Drive folder.
4. Paste the Apps Script web app URL into `site/config.js` and `worker/config.example.toml`.
5. Paste the Google Drive folder name/path into `worker/config.example.toml`.

## Folder Layout

```text
family-epub-portal/
  apps-script/
    Code.gs
  site/
    config.js
    index.html
    request.html
    request.js
    styles.css
    app.js
    data/
      latest-books.json
      request-status.json
  worker/
    library_worker.py
    config.example.toml
    publish-site.ps1
    setup-drive.ps1
    requests.example.csv
    tests/
      test_library_worker.py
```

## Request Backend Setup

1. Create a private Google Sheet named something like `Family EPUB Requests`.
2. Copy the spreadsheet ID from the URL:

```text
https://docs.google.com/spreadsheets/d/SPREADSHEET_ID_HERE/edit
```

3. Open Apps Script and create a new project:

```text
https://script.google.com/
```

4. Paste in `apps-script/Code.gs`.
5. Set these values at the top:

```javascript
SPREADSHEET_ID: "PASTE_PRIVATE_SHEET_ID_HERE",
WORKER_SECRET: "CHANGE_ME_TO_A_LONG_RANDOM_SECRET",
```

6. Deploy as a web app:

```text
Execute as: Me
Who has access: Anyone
```

7. Copy the web app URL.
8. Paste it into `site/config.js`:

```javascript
window.PORTAL_CONFIG = {
  requestEndpoint: "https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec",
  requestFormUrl: "request.html",
};
```

Submitters do not need Google accounts. The web app runs as you and writes into your private Sheet.

## Private Google Drive Upload Setup

Install rclone:

```powershell
winget install Rclone.Rclone
```

Or run the included helper:

```powershell
cd worker
.\setup-drive.ps1 -RemoteName gdrive -Folder "Family EPUB Library"
```

If rclone is not installed, the helper attempts to install it with winget. If the `gdrive` remote is not configured, it opens `rclone config`; create a remote named `gdrive`, choose Google Drive, and approve access in your browser.

Create the destination folder in Google Drive, for example:

```text
Family EPUB Library
```

Then configure `worker/config.example.toml`:

```toml
[google_drive]
rclone_remote = "gdrive"
folder = "Family EPUB Library"
rclone_path = "rclone"
```

If the folder is nested, use a path:

```toml
folder = "Books/Family EPUB Library"
```

## Source Configuration

Edit `worker/config.example.toml`.

Local authorized folders:

```toml
[sources]
local_folders = [
  "authorized-epubs",
  "D:\\Books\\Purchased EPUBs"
]
```

Direct EPUB URLs from approved domains:

```toml
direct_url_allowed_domains = [
  "standardebooks.org",
  "gutenberg.org",
  "www.gutenberg.org",
  "your-domain.example"
]
```

Project Gutenberg search through Gutendex:

```toml
gutendex_enabled = true
gutendex_base_url = "https://gutendex.com/books"
```

The search order is:

1. Local folders
2. Request-provided direct EPUB URL from an allowed domain
3. Project Gutenberg via Gutendex

## Worker Setup

From the project root:

```powershell
cd worker
python -m unittest discover tests
python library_worker.py --config config.example.toml --dry-run
```

Dry-run searches sources and updates local JSON, but does not download or upload files.

Real run:

```powershell
python library_worker.py --config config.example.toml
```

Publish updated status JSON to GitHub Pages:

```powershell
.\publish-site.ps1
```

## Scheduling On Windows

Create a scheduled task that runs nightly:

```powershell
$project = "C:\Path\To\family-epub-portal\worker"
$python = "python"
$action = New-ScheduledTaskAction -Execute $python -Argument "library_worker.py --config config.example.toml" -WorkingDirectory $project
$trigger = New-ScheduledTaskTrigger -Daily -At 2:00am
Register-ScheduledTask -TaskName "Family EPUB Portal Worker" -Action $action -Trigger $trigger -Description "Updates family EPUB portal data and Drive uploads."
```

You can add a second scheduled action after the worker run to publish the status JSON:

```powershell
powershell.exe -ExecutionPolicy Bypass -File publish-site.ps1
```

## Naming Convention

Files are renamed as:

```text
Last, First - Title (Year) [ISBN].epub
```

Year and ISBN are omitted when blank.
