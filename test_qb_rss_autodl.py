import unittest
from pathlib import Path

from qb_rss_autodl import (
    Source,
    archive_candidates,
    derive_media_folder,
    parse_feed,
    planned_save_path,
    read_archive_candidates,
    title_matches,
)
from qb_rss_gui import config_to_toml, credential_target


SAMPLE_RSS = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Example Show S01E01 1080p</title>
      <link>https://example.com/download/example-show-s01e01.torrent</link>
      <pubDate>Sat, 02 May 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Example Show S01E02 720p</title>
      <enclosure url="magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" />
    </item>
    <item>
      <title>Example Show S01E03 1080p</title>
      <enclosure url="https://example.com/?r=down&amp;hash=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" type="application/x-bittorrent" />
    </item>
    <item>
      <title>Plain Web Page</title>
      <link>https://example.com/page/123</link>
    </item>
  </channel>
</rss>
"""


class RssAutodlTests(unittest.TestCase):
    def test_parse_feed_keeps_downloadable_links(self):
        source = Source(name="sample", url="https://example.com/rss.xml")
        candidates = parse_feed(source, SAMPLE_RSS)

        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].title, "Example Show S01E01 1080p")
        self.assertTrue(candidates[0].url.endswith(".torrent"))
        self.assertTrue(candidates[1].url.startswith("magnet:?"))
        self.assertIn("r=down", candidates[2].url)

    def test_title_matches_keywords_and_excludes(self):
        self.assertTrue(title_matches("Example Show S01E01 1080p", ("example show", "1080p"), ("720p",)))
        self.assertFalse(title_matches("Example Show S01E01 720p", ("example show",), ("720p",)))
        self.assertFalse(title_matches("Other Show S01E01 1080p", ("example show",), ()))

    def test_derive_media_folder_from_kisssub_style_title(self):
        title = "[Group] Native Title / Mairimashita! Iruma-kun 4th Season - 05 (B-Global 1920x1080 HEVC AAC MKV)"
        self.assertEqual(derive_media_folder(title), "Mairimashita! Iruma-kun 4th Season")

    def test_derive_media_folder_from_episode_style_title(self):
        self.assertEqual(derive_media_folder("Example Show S01E01 1080p"), "Example Show")

    def test_derive_media_folder_removes_square_bracket_metadata(self):
        title = "[SFSub] Native / Otonari no Tenshi-sama 2nd Season - 05 [WebRip][1080P][AVC][AAC][MP4]"
        self.assertEqual(derive_media_folder(title), "Otonari no Tenshi-sama 2nd Season")

    def test_derive_media_folder_removes_bracket_episode_metadata(self):
        title = "[Team] Native / Niwatori Fighter [05][WebRip][1080p]"
        self.assertEqual(derive_media_folder(title), "Niwatori Fighter")

    def test_derive_media_folder_removes_batch_range(self):
        title = "[Team] Native / Kikaijikake no Marie - 01-12 [WebRip 1080p HEVC-10bit AAC]"
        self.assertEqual(derive_media_folder(title), "Kikaijikake no Marie")

    def test_planned_save_path_uses_title_folder(self):
        qbit_config = {"save_path": "E:\\media", "organize_by_title": True}
        candidate = parse_feed(Source(name="sample", url="https://example.com/rss.xml"), SAMPLE_RSS)[0]
        self.assertEqual(planned_save_path(qbit_config, candidate), "E:\\media\\Example Show")

    def test_archive_candidates_deduplicates_by_url(self):
        candidates = parse_feed(Source(name="sample", url="https://example.com/rss.xml"), SAMPLE_RSS)
        db_path = Path(__file__).resolve().parent / "test_archive.db"
        for suffix in ("", "-shm", "-wal"):
            target = Path(str(db_path) + suffix)
            if target.exists():
                target.unlink()
        try:
            first = archive_candidates(db_path, candidates)
            second = archive_candidates(db_path, candidates)
            archived = read_archive_candidates(db_path)
        finally:
            for suffix in ("", "-shm", "-wal"):
                target = Path(str(db_path) + suffix)
                if target.exists():
                    target.unlink()

        self.assertEqual(first.total, 3)
        self.assertEqual(first.inserted, 3)
        self.assertEqual(first.updated, 0)
        self.assertEqual(second.total, 3)
        self.assertEqual(second.inserted, 0)
        self.assertEqual(second.updated, 3)
        self.assertEqual(len(archived), 3)

    def test_gui_config_writer_outputs_sources_and_path(self):
        text = config_to_toml(
            {
                "qbittorrent": {
                    "url": "http://127.0.0.1:8080",
                    "username": "admin",
                    "password_env": "QBIT_PASSWORD",
                    "save_path": "E:\\media",
                    "category": "",
                    "organize_by_title": True,
                    "folder_name_max_length": 120,
                },
                "archive": {"database": "archive.db", "include_in_search": True, "daily_time": "12:00"},
                "sources": [{"name": "sample", "url": "https://example.com/rss.xml", "enabled": True}],
                "rules": [],
            }
        )
        self.assertIn('save_path = "E:\\\\media"', text)
        self.assertIn("remember_password = true", text)
        self.assertIn("[[sources]]", text)
        self.assertIn('url = "https://example.com/rss.xml"', text)

    def test_credential_target_includes_url_and_user(self):
        target = credential_target("http://127.0.0.1:8080/", "yui")
        self.assertEqual(target, "AutoDownloadWithBT/qBittorrent/http://127.0.0.1:8080/yui")


if __name__ == "__main__":
    unittest.main()
