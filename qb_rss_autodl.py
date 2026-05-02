from __future__ import annotations

import argparse
import getpass
import html
import http.cookiejar
import json
import os
import re
import sqlite3
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = APP_DIR / "config.toml"
DEFAULT_STATE = APP_DIR / "state.json"
DEFAULT_ARCHIVE = APP_DIR / "archive.db"
USER_AGENT = "qb-rss-autodl/0.1"
DEFAULT_LIMIT = 20


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    enabled: bool = True


@dataclass(frozen=True)
class Rule:
    name: str
    keywords: tuple[str, ...]
    exclude: tuple[str, ...]
    enabled: bool = True
    limit: int = DEFAULT_LIMIT


@dataclass(frozen=True)
class Candidate:
    source: str
    title: str
    url: str
    published: str = ""


@dataclass(frozen=True)
class ArchiveResult:
    total: int
    inserted: int
    updated: int


def load_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def read_sources(config: dict[str, Any]) -> list[Source]:
    sources: list[Source] = []
    for item in config.get("sources", []):
        sources.append(
            Source(
                name=str(item["name"]),
                url=str(item["url"]),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return sources


def read_rules(config: dict[str, Any]) -> list[Rule]:
    rules: list[Rule] = []
    for item in config.get("rules", []):
        keywords = tuple(str(value) for value in item.get("keywords", []))
        exclude = tuple(str(value) for value in item.get("exclude", []))
        rules.append(
            Rule(
                name=str(item["name"]),
                keywords=keywords,
                exclude=exclude,
                enabled=bool(item.get("enabled", True)),
                limit=int(item.get("limit", DEFAULT_LIMIT)),
            )
        )
    return rules


def normalize(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip().casefold()


def title_matches(title: str, keywords: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    normalized = normalize(title)
    return all(normalize(word) in normalized for word in keywords) and not any(
        normalize(word) in normalized for word in exclude
    )


def sanitize_folder_name(value: str, max_length: int = 120) -> str:
    value = html.unescape(value)
    value = re.sub(r'[<>:"/\\|?*\x00-\x1F]', " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        return "Unsorted"
    return value[:max_length].rstrip(" .")


def derive_media_folder(title: str, max_length: int = 120) -> str:
    value = html.unescape(title)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^(?:\[[^\]]+\]\s*)+", "", value).strip()

    if " / " in value:
        value = value.rsplit(" / ", 1)[-1].strip()

    while re.search(r"\s*(?:\([^)]*\)|\[[^\]]*\])\s*$", value):
        value = re.sub(r"\s*(?:\([^)]*\)|\[[^\]]*\])\s*$", "", value).strip()

    value = re.sub(r"\s+-\s+\d{1,4}(?:-\d{1,4})?(?:v\d+)?\s*$", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(r"\s+\d{1,4}(?:-\d{1,4})?(?:v\d+)?\s*$", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(r"\s+S\d{1,2}E\d{1,3}\b.*$", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(
        r"\s+(?:2160p|1080p|720p|480p|HEVC|AVC|AAC|FLAC|WEB-DL|BluRay|MKV|MP4)\b.*$",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()

    return sanitize_folder_name(value, max_length=max_length)


def planned_save_path(qbit_config: dict[str, Any], candidate: Candidate) -> str:
    base_path = Path(str(qbit_config.get("save_path", "")))
    if not bool(qbit_config.get("organize_by_title", True)):
        return str(base_path)
    max_length = int(qbit_config.get("folder_name_max_length", 120))
    return str(base_path / derive_media_folder(candidate.title, max_length=max_length))


def archive_db_path(config: dict[str, Any]) -> Path:
    archive_config = config.get("archive", {})
    raw_path = str(archive_config.get("database", DEFAULT_ARCHIVE))
    path = Path(raw_path)
    if not path.is_absolute():
        path = APP_DIR / path
    return path


def published_timestamp(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(parsedate_to_datetime(value).timestamp())
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def open_archive_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rss_items (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            published TEXT NOT NULL DEFAULT '',
            published_at INTEGER,
            first_seen_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL
        )
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(rss_items)").fetchall()}
    if "published_at" not in columns:
        connection.execute("ALTER TABLE rss_items ADD COLUMN published_at INTEGER")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_rss_items_title ON rss_items(title)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_rss_items_source ON rss_items(source)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_rss_items_published_at ON rss_items(published_at)")
    return connection


def archive_candidates(db_path: Path, candidates: list[Candidate]) -> ArchiveResult:
    now = int(time.time())
    inserted = 0
    updated = 0
    connection = open_archive_db(db_path)
    try:
        for item in candidates:
            item_published_at = published_timestamp(item.published)
            existing = connection.execute(
                "SELECT id FROM rss_items WHERE url = ?",
                (item.url,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO rss_items (source, title, url, published, published_at, first_seen_at, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (item.source, item.title, item.url, item.published, item_published_at, now, now),
                )
                inserted += 1
            else:
                connection.execute(
                    """
                    UPDATE rss_items
                    SET source = ?, title = ?, published = ?, published_at = ?, last_seen_at = ?
                    WHERE url = ?
                    """,
                    (item.source, item.title, item.published, item_published_at, now, item.url),
                )
                updated += 1
        connection.commit()
    finally:
        connection.close()
    return ArchiveResult(total=len(candidates), inserted=inserted, updated=updated)


def read_archive_candidates(db_path: Path) -> list[Candidate]:
    if not db_path.exists():
        return []
    connection = open_archive_db(db_path)
    try:
        rows = connection.execute(
            """
            SELECT source, title, url, published
            FROM rss_items
            ORDER BY COALESCE(published_at, last_seen_at) DESC, id DESC
            """
        ).fetchall()
    finally:
        connection.close()
    return [Candidate(source=str(row[0]), title=str(row[1]), url=str(row[2]), published=str(row[3])) for row in rows]


def merge_candidates(primary: list[Candidate], secondary: list[Candidate]) -> list[Candidate]:
    merged: list[Candidate] = []
    seen: set[str] = set()
    for item in primary + secondary:
        if item.url in seen:
            continue
        seen.add(item.url)
        merged.append(item)
    return merged


def is_download_url(value: str, mime_type: str = "") -> bool:
    if "bittorrent" in mime_type.casefold():
        return True
    lower = value.casefold()
    if lower.startswith("magnet:?"):
        return True
    parsed = urllib.parse.urlparse(value)
    path = parsed.path.casefold()
    query = urllib.parse.parse_qs(parsed.query.casefold())
    return parsed.scheme in {"http", "https"} and (
        path.endswith(".torrent")
        or ".torrent" in path
        or "download" in path
        or query.get("r") == ["down"]
    )


def fetch_text(url: str, timeout: int = 60) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
    return data.decode(encoding, errors="replace")


def text_or_empty(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def find_child(element: ET.Element, local_name: str) -> ET.Element | None:
    for child in element:
        if child.tag.rsplit("}", 1)[-1] == local_name:
            return child
    return None


def parse_feed(source: Source, xml_text: str) -> list[Candidate]:
    root = ET.fromstring(xml_text)
    candidates: list[Candidate] = []

    items = list(root.findall(".//item"))
    if not items:
        items = [entry for entry in root.iter() if entry.tag.rsplit("}", 1)[-1] == "entry"]

    for item in items:
        title = html.unescape(text_or_empty(find_child(item, "title")))
        published = text_or_empty(find_child(item, "pubDate")) or text_or_empty(find_child(item, "updated"))
        urls: list[str] = []

        enclosure = find_child(item, "enclosure")
        if enclosure is not None and enclosure.get("url"):
            enclosure_url = enclosure.get("url", "").strip()
            if is_download_url(enclosure_url, enclosure.get("type", "")):
                candidates.append(Candidate(source=source.name, title=title, url=enclosure_url, published=published))
                continue

        for child_name in ("link", "guid"):
            child = find_child(item, child_name)
            if child is None:
                continue
            href = child.get("href") or child.text or ""
            href = href.strip()
            if href:
                urls.append(href)

        for url in urls:
            if is_download_url(url):
                candidates.append(Candidate(source=source.name, title=title, url=url, published=published))
                break

    return candidates


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"downloads": []}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_state(path: Path, state: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def seen_urls(state: dict[str, Any]) -> set[str]:
    return {str(item.get("url")) for item in state.get("downloads", [])}


def record_downloads(path: Path, state: dict[str, Any], selected: list[Candidate]) -> None:
    downloads = state.setdefault("downloads", [])
    now = int(time.time())
    for item in selected:
        downloads.append(
            {
                "title": item.title,
                "url": item.url,
                "source": item.source,
                "added_at": now,
            }
        )
    save_state(path, state)


class QBittorrentClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))

    def post(self, path: str, data: dict[str, str]) -> str:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=encoded,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
                "Referer": self.base_url,
            },
        )
        with self.opener.open(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")

    def login(self) -> None:
        result = self.post(
            "/api/v2/auth/login",
            {"username": self.username, "password": self.password},
        )
        if result.strip() != "Ok.":
            raise RuntimeError("qBittorrent login failed")

    def add_urls(self, urls: list[str], save_path: str, category: str = "") -> None:
        data = {"urls": "\n".join(urls), "savepath": save_path}
        if category:
            data["category"] = category
        result = self.post("/api/v2/torrents/add", data)
        if result.strip() not in {"Ok.", ""}:
            raise RuntimeError(f"qBittorrent add failed: {result.strip()}")


def get_password(qbit_config: dict[str, Any]) -> str:
    env_name = str(qbit_config.get("password_env", "QBIT_PASSWORD"))
    password = os.environ.get(env_name)
    if password:
        return password
    return getpass.getpass(f"qBittorrent password ({env_name}): ")


def collect_candidates(sources: list[Source], state: dict[str, Any], ignore_state: bool) -> list[Candidate]:
    already_seen = seen_urls(state)
    results: list[Candidate] = []
    for source in sources:
        if not source.enabled:
            continue
        xml_text = fetch_text(source.url)
        for item in parse_feed(source, xml_text):
            if ignore_state or item.url not in already_seen:
                results.append(item)
    return results


def collect_search_candidates(
    config: dict[str, Any],
    sources: list[Source],
    state: dict[str, Any],
    ignore_state: bool,
    no_archive: bool,
) -> list[Candidate]:
    live_error: Exception | None = None
    try:
        current = collect_candidates(sources, state, ignore_state)
    except urllib.error.URLError as exc:
        current = []
        live_error = exc
    if no_archive or not bool(config.get("archive", {}).get("include_in_search", True)):
        if live_error is not None:
            raise live_error
        return current
    archived = read_archive_candidates(archive_db_path(config))
    if live_error is not None and archived:
        print(f"Warning: live RSS fetch failed, using archive only: {live_error}", file=sys.stderr)
    elif live_error is not None:
        raise live_error
    already_seen = seen_urls(state)
    if not ignore_state:
        archived = [item for item in archived if item.url not in already_seen]
    return merge_candidates(current, archived)


def print_candidates(candidates: list[Candidate], qbit_config: dict[str, Any] | None = None) -> None:
    for index, item in enumerate(candidates, start=1):
        print(f"{index}. [{item.source}] {item.title}")
        if item.published:
            print(f"   published: {item.published}")
        if qbit_config is not None:
            print(f"   savepath: {planned_save_path(qbit_config, item)}")
        print(f"   url: {item.url}")


def ask_selection(candidates: list[Candidate]) -> list[Candidate]:
    if not candidates:
        return []
    print()
    print("Download selection: enter 'y' for all, numbers like '1,3', or press Enter to cancel.")
    answer = input("> ").strip().casefold()
    if not answer:
        return []
    if answer in {"y", "yes"}:
        return candidates

    selected: list[Candidate] = []
    for part in re.split(r"[,\uFF0C\s]+", answer):
        if not part:
            continue
        if not part.isdigit():
            raise ValueError(f"Invalid selection: {part}")
        index = int(part)
        if index < 1 or index > len(candidates):
            raise ValueError(f"Selection out of range: {index}")
        selected.append(candidates[index - 1])
    return selected


def add_after_confirmation(
    config: dict[str, Any],
    state_path: Path,
    state: dict[str, Any],
    candidates: list[Candidate],
    dry_run: bool,
) -> int:
    if not candidates:
        print("No matching downloadable RSS items found.")
        return 1

    qbit = config["qbittorrent"]
    print_candidates(candidates, qbit)
    if dry_run:
        print("Dry run only. Nothing was added to qBittorrent.")
        return 0

    selected = ask_selection(candidates)
    if not selected:
        print("Cancelled. Nothing was added to qBittorrent.")
        return 1

    client = QBittorrentClient(
        base_url=str(qbit["url"]),
        username=str(qbit["username"]),
        password=get_password(qbit),
    )
    client.login()
    for item in selected:
        save_path = planned_save_path(qbit, item)
        if save_path:
            Path(save_path).mkdir(parents=True, exist_ok=True)
        client.add_urls([item.url], save_path=save_path, category=str(qbit.get("category", "")))
    record_downloads(state_path, state, selected)
    print(f"Added {len(selected)} item(s) to qBittorrent.")
    return 0


def command_search(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    sources = read_sources(config)
    state = load_state(args.state)
    candidates = collect_search_candidates(config, sources, state, args.ignore_state, args.no_archive)
    keywords = tuple(args.include or ()) + (args.query,)
    exclude = tuple(args.exclude or ())
    matches = [item for item in candidates if title_matches(item.title, keywords, exclude)]
    return add_after_confirmation(config, args.state, state, matches[: args.limit], args.dry_run)


def command_scan_rules(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    sources = read_sources(config)
    rules = [rule for rule in read_rules(config) if rule.enabled]
    state = load_state(args.state)
    all_candidates = collect_search_candidates(config, sources, state, args.ignore_state, args.no_archive)
    selected_matches: list[Candidate] = []
    seen: set[str] = set()

    for rule in rules:
        matches = [
            item
            for item in all_candidates
            if item.url not in seen and title_matches(item.title, rule.keywords, rule.exclude)
        ][: rule.limit]
        for item in matches:
            seen.add(item.url)
        if matches:
            print(f"Rule '{rule.name}' matched {len(matches)} item(s).")
            selected_matches.extend(matches)

    return add_after_confirmation(config, args.state, state, selected_matches, args.dry_run)


def command_archive(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    sources = read_sources(config)
    state = {"downloads": []}
    candidates = collect_candidates(sources, state, ignore_state=True)
    result = archive_candidates(archive_db_path(config), candidates)
    print(
        f"Archived {result.total} RSS item(s): "
        f"{result.inserted} new, {result.updated} duplicate/update."
    )
    return 0


def command_archive_stats(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    db_path = archive_db_path(config)
    if not db_path.exists():
        print(f"Archive database not found: {db_path}")
        return 1
    connection = open_archive_db(db_path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM rss_items").fetchone()[0]
        oldest = connection.execute(
            """
            SELECT published, title FROM rss_items
            WHERE published_at IS NOT NULL
            ORDER BY published_at ASC
            LIMIT 1
            """
        ).fetchone()
        newest = connection.execute(
            """
            SELECT published, title FROM rss_items
            WHERE published_at IS NOT NULL
            ORDER BY published_at DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()
    print(f"Archive database: {db_path}")
    print(f"Archived item count: {count}")
    if oldest:
        print(f"Oldest published: {oldest[0]} {oldest[1]}")
    if newest:
        print(f"Newest published: {newest[0]} {newest[1]}")
    return 0


def command_list_sources(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    sources = read_sources(config)
    for source in sources:
        status = "enabled" if source.enabled else "disabled"
        print(f"{source.name}: {status} {source.url}")
    return 0


def command_check_qbit(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    qbit = config["qbittorrent"]
    client = QBittorrentClient(
        base_url=str(qbit["url"]),
        username=str(qbit["username"]),
        password=get_password(qbit),
    )
    client.login()
    print("qBittorrent login OK.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find RSS torrent links and add them to qBittorrent after confirmation.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)

    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="Search configured RSS feeds by title text.")
    search.add_argument("query", help="Title or phrase to match.")
    search.add_argument("--include", action="append", help="Additional required keyword. Can be repeated.")
    search.add_argument("--exclude", action="append", help="Keyword to exclude. Can be repeated.")
    search.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    search.add_argument("--dry-run", action="store_true", help="Show matches without adding them.")
    search.add_argument("--ignore-state", action="store_true", help="Include items already recorded in state.json.")
    search.add_argument("--no-archive", action="store_true", help="Search current RSS only, ignoring archive.db.")
    search.set_defaults(func=command_search)

    scan_rules = subparsers.add_parser("scan-rules", help="Run enabled rules from config.toml.")
    scan_rules.add_argument("--dry-run", action="store_true", help="Show matches without adding them.")
    scan_rules.add_argument("--ignore-state", action="store_true", help="Include items already recorded in state.json.")
    scan_rules.add_argument("--no-archive", action="store_true", help="Search current RSS only, ignoring archive.db.")
    scan_rules.set_defaults(func=command_scan_rules)

    archive = subparsers.add_parser("archive", help="Fetch enabled RSS sources and save unique items to archive.db.")
    archive.set_defaults(func=command_archive)

    archive_stats = subparsers.add_parser("archive-stats", help="Show archive database counts and date range.")
    archive_stats.set_defaults(func=command_archive_stats)

    list_sources = subparsers.add_parser("sources", help="List configured RSS sources.")
    list_sources.set_defaults(func=command_list_sources)

    check_qbit = subparsers.add_parser("check-qbit", help="Check qBittorrent Web API login.")
    check_qbit.set_defaults(func=command_check_qbit)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (urllib.error.URLError, ET.ParseError, KeyError, RuntimeError, ValueError, sqlite3.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
