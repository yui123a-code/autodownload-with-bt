# qBittorrent RSS Auto Download

This local tool searches configured RSS feeds, filters items by title keywords and exclude words, then asks for confirmation before adding selected links to qBittorrent.

Use it only with feeds and content you are authorized to download.

## Requirements

- Windows 10 or newer.
- qBittorrent installed on the same PC.
- qBittorrent Web UI enabled and reachable, usually at `http://127.0.0.1:8080`.
- RSS feeds that provide torrent or magnet links.

## GUI

Run the packaged Windows executable:

```text
dist\AutoDownloadWithBT.exe
```

For end users, download the Windows installer from GitHub Releases and run:

```text
AutoDownloadWithBT-Setup.exe
```

Start the desktop client:

```powershell
python .\qb_rss_gui.py
```

The GUI can:

- Show a first-run setup wizard for qBittorrent URL, username, password, download root, and RSS sources.
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

## Build The Installer

Build the Windows installer with Inno Setup:

```powershell
.\build_installer.ps1
```

The output is:

```text
release\AutoDownloadWithBT-Setup.exe
```

Upload that installer to GitHub Releases for users who do not want to install Python.

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

---

# 中文说明

这是一个本地 qBittorrent RSS 下载辅助工具。它会读取你配置的 RSS 源，根据标题关键词和排除词搜索资源，在你确认之后才把选中的 torrent 或 magnet 链接添加到 qBittorrent。

请只下载你有权下载和保存的内容。

## 使用条件

- Windows 10 或更新版本。
- 电脑上已经下载安装 qBittorrent。
- qBittorrent 已启用 Web UI，并且本机可以访问，常见地址是 `http://127.0.0.1:8080`。
- 你有可用的 RSS 订阅源，且 RSS 条目里包含 `.torrent` 或 magnet 下载链接。

## 普通用户安装

到 GitHub Releases 下载 Windows 安装包：

```text
AutoDownloadWithBT-Setup.exe
```

安装后启动桌面客户端。首次启动时会出现配置向导，需要填写：

- qBittorrent 地址，例如 `http://127.0.0.1:8080`
- qBittorrent 用户名
- qBittorrent 密码
- 下载根目录，例如 `E:\media`
- RSS 源，一行一个 RSS URL

密码不会写入 `config.toml`。如果启用记住密码，密码会保存在当前 Windows 用户的凭据管理器里。

## GUI 功能

- 首次启动配置向导。
- 添加、删除、启用、禁用 RSS 源。
- 设置 qBittorrent 地址、用户名、分类和下载根目录。
- 记住 qBittorrent 密码，并在启动后自动检查登录。
- 搜索当前 RSS 和本地归档数据库。
- 下载前预览按片名整理后的保存目录。
- 只有手动确认后才会把选中资源添加到 qBittorrent。
- 手动执行 RSS 归档。

## 搜索和下载

在 `Search and Download` 区域输入片名或关键词，然后点击 `Search`。

搜索结果出现后，选中你想下载的条目，再点击 `Add Selected`。程序会再次询问确认，确认后才会添加到 qBittorrent。

`Must include` 是必须包含的关键词，`Exclude` 是排除词。多个词可以用逗号或分号分隔。

## 文件夹整理

当 `Organize by title` 开启时，程序会在下载根目录下按片名自动创建子文件夹。

例如下载根目录是：

```text
E:\media
```

某个条目的标题会被解析成：

```text
E:\media\Mairimashita! Iruma-kun 4th Season
```

程序会尽量去掉字幕组前缀、集数、清晰度、编码等常见后缀。

## 本地 RSS 归档

程序可以把每天获取到的 RSS 条目保存到本地 `archive.db`，以后即使 RSS 源只显示最近内容，也能搜索已经归档过的旧条目。

同一个 RSS 条目 URL 不会重复保存。重复归档只会更新最后看到时间。

如果要安装每天 12:00 自动归档的 Windows 计划任务，可以运行：

```powershell
.\install_daily_archive_task.ps1
```

该任务会：

- 每天 12:00 运行。
- 当前 Windows 用户登录时运行一次。
- 如果电脑 12:00 没开机，会在之后尽快补跑。
- 归档失败时最多重试三次，每次间隔 15 分钟。

## 开发者构建

构建单文件 exe：

```powershell
.\build_exe.ps1
```

构建安装包：

```powershell
.\build_installer.ps1
```

安装包输出位置：

```text
release\AutoDownloadWithBT-Setup.exe
```

## 注意事项

- 不要把 qBittorrent Web UI 暴露到公网。
- 不要把自己的 `config.toml`、`archive.db`、`state.json` 上传到 GitHub。
- `state.json` 用来记录已经添加过的下载，避免重复添加。
