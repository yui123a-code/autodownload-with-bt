# AutoDownloadWithBT

<p align="right">
  <a href="./README.md">English</a> |
  <strong>简体中文</strong>
</p>

AutoDownloadWithBT 是一个 Windows 桌面工具，用来搜索 RSS torrent 订阅源，并在你确认后把选中的结果添加到 qBittorrent。

它适合本地使用：你配置 RSS 源，按片名或关键词搜索，预览保存目录，然后把选中的 `.torrent` 或 magnet 链接发送到 qBittorrent。

请只下载你有权下载和保存的内容。

## 使用条件

- Windows 10 或更新版本。
- 电脑上已经下载安装 qBittorrent。
- qBittorrent 已启用 Web UI，并且本机可以访问，常见地址是 `http://127.0.0.1:8080`。
- 你有可用的 RSS 订阅源，且 RSS 条目里包含 `.torrent` 或 magnet 下载链接。

## 下载

到 GitHub Releases 下载 Windows 安装包：

```text
AutoDownloadWithBT-Setup.exe
```

最新发布页面：

```text
https://github.com/yui123a-code/autodownload-with-bt/releases
```

安装后，可以从开始菜单或桌面快捷方式启动 `AutoDownloadWithBT`。

## 首次启动

首次启动会打开配置向导。需要填写：

- qBittorrent Web UI 地址，例如 `http://127.0.0.1:8080`
- qBittorrent 用户名
- qBittorrent 密码
- 下载根目录，例如 `E:\media`
- RSS 源，一行一个 URL

密码不会写入 `config.toml`。如果启用记住密码，密码会保存在当前 Windows 用户的凭据管理器里。

## 功能

- 首次启动配置向导。
- 添加、删除、启用、禁用 RSS 源。
- 搜索当前 RSS 和本地归档数据库。
- 用必须包含的关键词和排除词过滤结果。
- 下载前预览按片名整理后的保存目录。
- 只有手动确认后才会把选中资源添加到 qBittorrent。
- 把 qBittorrent 密码保存到 Windows 凭据管理器。
- 将 RSS 条目归档到本地数据库，让旧条目也可以继续搜索。
- 在下载根目录下按片名自动创建子文件夹。

## 搜索和下载

在 `Search and Download` 区域输入片名或关键词，然后点击 `Search`。

搜索结果出现后，选中你想下载的条目，再点击 `Add Selected`。程序会再次询问确认，确认后才会添加到 qBittorrent。

`Must include` 是必须包含的关键词，`Exclude` 是排除词。多个词可以用逗号或分号分隔。

## 文件夹整理

当 `Organize by title` 开启时，程序会在下载根目录下按片名自动创建子文件夹。

示例：

```text
E:\media\Mairimashita! Iruma-kun 4th Season
```

程序会尽量去掉字幕组前缀、集数、清晰度、编码等常见后缀。

## 本地 RSS 归档

程序可以把 RSS 条目保存到本地 `archive.db` 数据库。即使远程 RSS 源只保留最近内容，你也可以搜索已经归档过的旧条目。

同一个 RSS 条目 URL 不会重复保存。重复归档只会更新最后看到时间。

安装每天自动归档的 Windows 计划任务：

```powershell
.\install_daily_archive_task.ps1
```

该任务会：

- 每天 12:00 运行。
- 当前 Windows 用户登录时运行一次。
- 如果电脑 12:00 没开机，会在之后尽快补跑。
- 归档失败时最多重试三次，每次间隔 15 分钟。

## 开发者使用

从源码启动 GUI：

```powershell
python .\qb_rss_gui.py
```

构建单文件 exe：

```powershell
.\build_exe.ps1
```

构建 Windows 安装包：

```powershell
.\build_installer.ps1
```

安装包输出位置：

```text
release\AutoDownloadWithBT-Setup.exe
```

## 命令行

检查 qBittorrent 登录：

```powershell
python .\qb_rss_autodl.py check-qbit
```

只搜索，不添加下载：

```powershell
python .\qb_rss_autodl.py search "title" --dry-run
```

搜索并在确认后添加到 qBittorrent：

```powershell
python .\qb_rss_autodl.py search "title"
```

添加必须包含的关键词和排除词：

```powershell
python .\qb_rss_autodl.py search "title" --include "1080p" --exclude "720p" --exclude "CAM"
```

默认搜索结果数量是 20。单次搜索想显示更多，可以使用 `--limit 40`。

## 配置

本地配置文件是 `config.toml`。可以参考安全发布用的示例文件：[config.example.toml](config.example.toml)。

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

## 注意事项

- 不要把 qBittorrent Web UI 暴露到公网。
- 不要把自己的 `config.toml`、`archive.db`、`state.json` 上传到 GitHub。
- `state.json` 用来记录已经添加过的下载，避免重复添加。
