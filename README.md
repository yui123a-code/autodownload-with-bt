# qBittorrent RSS Auto Download

This local tool searches configured RSS feeds, filters items by title keywords and exclude words, then asks for confirmation before adding selected links to qBittorrent.

Use it only with feeds and content you are authorized to download.

## GUI

Run the packaged Windows executable:

```text
dist\AutoDownloadWithBT.exe
```

Start the desktop client:

```powershell
python .\qb_rss_gui.py
```

The GUI can:

- Add, remove, enable, and disable RSS sources.
- Set the qBittorrent URL, username, category, and download root.
- Remember the qBittorrent password in Windows Credential Manager and auto-check login on startup.
- Search current RSS feeds plus the local archive.
- Preview title-derived save paths before download.
- Add selected items to qBittorrent only after confirmation.
- Run a manual RSS archive.

## Build The EXE

Build the Windows executable with PyInstaller:

```powershell
.\build_exe.ps1
```

The output is:

```text
dist\AutoDownloadWithBT.exe
```

The executable stores `config.toml`, `archive.db`, and `state.json` beside the `.exe`, not inside the temporary PyInstaller extraction folder.

## Setup

qBittorrent must have Web UI enabled at:

```text
http://127.0.0.1:8080
```

Set the qBittorrent password in the current PowerShell session:

```powershell
$env:QBIT_PASSWORD = "your-qbittorrent-password"
```

The local config file is `config.toml`. A publish-safe example is [config.example.toml](config.example.toml).

```toml
[qbittorrent]
url = "http://127.0.0.1:8080"
username = "yui"
password_env = "QBIT_PASSWORD"
save_path = "E:\\media"
category = ""
organize_by_title = true
folder_name_max_length = 120
remember_password = true
```

The qBittorrent password is not written to `config.toml`. When `Remember password and auto-login` is enabled in the GUI, the password is saved under the current Windows user in Credential Manager.

## Search By Title

Check qBittorrent login:

```powershell
python .\qb_rss_autodl.py check-qbit
```

Dry run first:

```powershell
python .\qb_rss_autodl.py search "title" --dry-run
```

Search and confirm before adding to qBittorrent:

```powershell
python .\qb_rss_autodl.py search "title"
```

Add required and excluded keywords:

```powershell
python .\qb_rss_autodl.py search "title" --include "1080p" --exclude "720p" --exclude "CAM"
```

The default search limit is 20 candidates. Use `--limit 40` if you want more for one run.

By default, search reads both the current RSS feeds and the local archive database. To search only the live RSS feeds:

```powershell
python .\qb_rss_autodl.py search "title" --no-archive
```

When matches are found, the script prints candidates and asks:

```text
Download selection: enter 'y' for all, numbers like '1,3', or press Enter to cancel.
```

Pressing Enter cancels without adding anything.

## Rules

Edit `config.toml` to add more RSS feeds:

```toml
[[sources]]
name = "another-feed"
url = "https://example.com/rss.xml"
enabled = true
```

Add automatic matching rules:

```toml
[[rules]]
name = "my-rule"
enabled = true
keywords = ["title", "1080p"]
exclude = ["720p", "CAM", "TC", "sample"]
limit = 20
```

Run enabled rules:

```powershell
python .\qb_rss_autodl.py scan-rules --dry-run
python .\qb_rss_autodl.py scan-rules
```

Even `scan-rules` asks before adding downloads.

## Local RSS Archive

Archive the current RSS items without adding anything to qBittorrent:

```powershell
python .\qb_rss_autodl.py archive
```

Show archive status:

```powershell
python .\qb_rss_autodl.py archive-stats
```

The archive database is `archive.db`. RSS item URLs are unique in the database, so repeated archive runs do not create duplicate rows. Repeated URLs only update `last_seen_at`.

To install a Windows scheduled task that archives RSS feeds every day at 12:00:

```powershell
.\install_daily_archive_task.ps1
```

The scheduled task runs [run_archive.ps1](run_archive.ps1), writes logs to `archive.log`, and does not require the qBittorrent password.

The task is configured to:

- Run daily at 12:00.
- Run once when the current Windows user logs in.
- Run as soon as possible if the 12:00 schedule was missed because the PC was off.
- Retry up to three times at 15-minute intervals if archiving fails.

## Folder Organization

When `organize_by_title = true`, each selected item is added with a title-derived subfolder under `E:\media`.

For example:

```text
E:\media\Mairimashita! Iruma-kun 4th Season
```

The parser removes leading release-group brackets, trailing episode numbers, and common quality/codec suffixes. Dry runs show the planned `savepath` before anything is added.

## Notes

- Downloaded URLs are recorded in `state.json` to avoid repeated additions.
- Use `--ignore-state` if you intentionally want to show already recorded items.
- Do not expose qBittorrent Web UI to the public internet.
