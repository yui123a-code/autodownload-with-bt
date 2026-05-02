# AutoDownloadWithBT

<p align="right">
  <strong>English</strong> |
  <a href="./README.zh-CN.md">简体中文</a>
</p>

AutoDownloadWithBT is a Windows desktop tool for searching RSS torrent feeds and adding selected results to qBittorrent only after confirmation.

It is designed for local use: you configure RSS sources, search by title keywords, preview the target save folder, then send selected torrent or magnet links to qBittorrent.

Use it only with feeds and content you are authorized to download.

## Requirements

- Windows 10 or newer.
- qBittorrent installed on the same PC.
- qBittorrent Web UI enabled and reachable, usually at `http://127.0.0.1:8080`.
- RSS feeds that provide `.torrent` or magnet links.

## Download

Download the Windows installer from GitHub Releases:

```text
AutoDownloadWithBT-Setup.exe
```

Latest release:

```text
https://github.com/yui123a-code/autodownload-with-bt/releases
```

After installation, start `AutoDownloadWithBT` from the Start Menu or desktop shortcut.

## First Run

The first launch opens a setup wizard. Fill in:

- qBittorrent Web UI address, for example `http://127.0.0.1:8080`
- qBittorrent username
- qBittorrent password
- Download root, for example `E:\media`
- RSS sources, one URL per line

The password is not written to `config.toml`. When password remembering is enabled, it is stored under the current Windows user in Windows Credential Manager.

## Features

- First-run setup wizard.
- Add, remove, enable, and disable RSS sources.
- Search current RSS feeds plus the local archive database.
- Filter results with required keywords and exclude words.
- Preview title-derived save folders before download.
- Add selected items to qBittorrent only after confirmation.
- Store the qBittorrent password in Windows Credential Manager.
- Archive RSS items locally so older entries remain searchable.
- Organize downloads into title-derived folders under the configured download root.

## Search And Download

Open the `Search and Download` area, enter a title or keyword, then click `Search`.

Select one or more results and click `Add Selected`. The app asks for confirmation before adding anything to qBittorrent.

`Must include` contains additional required keywords. `Exclude` contains words that should reject a result. Multiple words can be separated with commas or semicolons.

## Folder Organization

When `Organize by title` is enabled, each selected item is added with a title-derived subfolder under the configured download root.

Example:

```text
E:\media\Mairimashita! Iruma-kun 4th Season
```

The parser removes common release-group prefixes, trailing episode numbers, quality tags, codec tags, and similar metadata where possible.

## Local RSS Archive

The app can save RSS entries into a local `archive.db` database. This helps you search entries that were seen before even if the remote RSS feed only keeps recent items.

RSS item URLs are unique in the database, so repeated archive runs do not create duplicate rows. Existing rows only update their last-seen time.

To install the daily archive task:

```powershell
.\install_daily_archive_task.ps1
```

The scheduled task:

- Runs daily at 12:00.
- Runs once when the current Windows user logs in.
- Runs as soon as possible if the 12:00 schedule was missed because the PC was off.
- Retries up to three times at 15-minute intervals if archiving fails.

## Developer Usage

Run the GUI from source:

```powershell
python .\qb_rss_gui.py
```

Build the standalone executable:

```powershell
.\build_exe.ps1
```

Build the Windows installer:

```powershell
.\build_installer.ps1
```

Installer output:

```text
release\AutoDownloadWithBT-Setup.exe
```

## CLI

Check qBittorrent login:

```powershell
python .\qb_rss_autodl.py check-qbit
```

Search without adding anything:

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

The default search limit is 20 candidates. Use `--limit 40` to show more for one run.

## Configuration

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

[archive]
database = "archive.db"
include_in_search = true
daily_time = "12:00"
```

## Notes

- Do not expose qBittorrent Web UI to the public internet.
- Do not commit your own `config.toml`, `archive.db`, or `state.json`.
- Downloaded URLs are recorded in `state.json` to avoid repeated additions.
