import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import library_worker


class LibraryWorkerTests(unittest.TestCase):
    def test_build_filename_uses_author_title_year_and_isbn(self):
        name = library_worker.build_filename(
            title="A Study in Scarlet",
            author="Arthur Conan Doyle",
            year="1887",
            isbn="9780140439083",
        )

        self.assertEqual(
            name,
            "Doyle, Arthur Conan - A Study in Scarlet (1887) [9780140439083].epub",
        )

    def test_build_filename_removes_windows_reserved_characters(self):
        name = library_worker.build_filename(
            title='Notes: "Private" / Draft?',
            author="Ada Lovelace",
        )

        self.assertEqual(name, "Lovelace, Ada - Notes Private Draft.epub")

    def test_load_requests_reads_expected_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "requests.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["request_id", "title", "author", "isbn", "notes"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "request_id": "REQ-2026-0001",
                        "title": "Pride and Prejudice",
                        "author": "Jane Austen",
                        "isbn": "",
                        "notes": "Standard Ebooks if available",
                    }
                )

            requests = library_worker.load_requests(csv_path)

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["request_id"], "REQ-2026-0001")
        self.assertEqual(requests[0]["title"], "Pride and Prejudice")

    def test_load_requests_reads_google_forms_column_names_without_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "responses.csv"
            csv_path.write_text(
                "Timestamp,Title,Author,ISBN,Notes\n"
                "2026-06-10 12:00:00,Emma,Jane Austen,,No email needed\n",
                encoding="utf-8",
            )

            requests = library_worker.load_requests(csv_path)

        self.assertEqual(requests[0]["title"], "Emma")
        self.assertEqual(requests[0]["email"], "")
        self.assertEqual(requests[0]["notes"], "No email needed")

    def test_find_local_epub_matches_title_and_author_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            epub = source / "A Study in Scarlet - Arthur Conan Doyle.epub"
            epub.write_bytes(b"placeholder epub bytes")

            match = library_worker.find_local_epub(
                {"title": "A Study in Scarlet", "author": "Arthur Conan Doyle"},
                [source],
            )

        self.assertEqual(match, epub)

    def test_direct_url_must_be_epub_and_on_allowlist(self):
        self.assertTrue(
            library_worker.is_allowed_epub_url(
                "https://standardebooks.org/ebooks/jane-austen/emma/downloads/jane-austen_emma.epub",
                ["standardebooks.org"],
            )
        )
        self.assertFalse(
            library_worker.is_allowed_epub_url(
                "https://example.com/book.pdf",
                ["example.com"],
            )
        )
        self.assertFalse(
            library_worker.is_allowed_epub_url(
                "https://unapproved.example/book.epub",
                ["standardebooks.org"],
            )
        )

    def test_load_requests_from_backend_json(self):
        payload = {
            "ok": True,
            "requests": [
                {
                    "request_id": "REQ-2026-0100",
                    "title": "Moby Dick",
                    "author": "Herman Melville",
                    "isbn": "",
                    "notes": "Classic",
                    "source_url": "",
                }
            ],
        }

        requests = library_worker.parse_backend_requests(payload)

        self.assertEqual(requests[0]["request_id"], "REQ-2026-0100")
        self.assertEqual(requests[0]["title"], "Moby Dick")
        self.assertEqual(requests[0]["email"], "")

    def test_select_gutendex_candidate_prefers_epub_with_matching_author(self):
        payload = {
            "results": [
                {
                    "title": "Moby Dick; Or, The Whale",
                    "authors": [{"name": "Melville, Herman"}],
                    "formats": {
                        "text/html": "https://example.com/moby.html",
                        "application/epub+zip": "https://www.gutenberg.org/ebooks/2701.epub3.images",
                    },
                }
            ]
        }

        match = library_worker.select_gutendex_candidate(
            {"title": "Moby Dick", "author": "Herman Melville"},
            payload,
        )

        self.assertIsNotNone(match)
        self.assertEqual(match.label, "Project Gutenberg")
        self.assertEqual(match.url, "https://www.gutenberg.org/ebooks/2701.epub3.images")

    def test_build_destination_uses_configured_drive_folder(self):
        config = {
            "drive_remote": "gdrive",
            "drive_folder": "Family EPUB Library/Incoming",
        }

        self.assertEqual(
            library_worker.build_drive_destination(config),
            "gdrive:Family EPUB Library/Incoming",
        )

    def test_source_error_does_not_stop_worker(self):
        original = library_worker.find_gutendex_match
        try:
            library_worker.find_gutendex_match = lambda request, base_url, timeout_seconds=8: (_ for _ in ()).throw(TimeoutError("slow"))
            match = library_worker.find_configured_match(
                {"title": "Slow Book", "author": "Someone", "source_url": ""},
                {
                    "local_sources": [],
                    "direct_url_allowed_domains": [],
                    "gutendex_enabled": True,
                    "gutendex_base_url": "https://example.com/books",
                },
            )
        finally:
            library_worker.find_gutendex_match = original

        self.assertIsNone(match)

    def test_run_dry_run_generates_status_and_latest_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            epub = source / "Pride and Prejudice - Jane Austen.epub"
            epub.write_bytes(b"placeholder epub bytes")

            requests_path = root / "requests.csv"
            requests_path.write_text(
                "request_id,title,author,isbn,notes\n"
                "REQ-2026-0001,Pride and Prejudice,Jane Austen,,\n",
                encoding="utf-8",
            )

            latest_path = root / "latest-books.json"
            status_path = root / "request-status.json"
            config = {
                "requests_csv": str(requests_path),
                "staging_dir": str(root / "staging"),
                "latest_json": str(latest_path),
                "status_json": str(status_path),
                "local_sources": [str(source)],
                "drive_remote": "gdrive:Family Library",
                "rclone_path": "rclone",
            }

            summary = library_worker.run_worker(config, dry_run=True)

            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            statuses = json.loads(status_path.read_text(encoding="utf-8"))

        self.assertEqual(summary["uploaded"], 0)
        self.assertEqual(summary["matched"], 1)
        self.assertEqual(latest[0]["title"], "Pride and Prejudice")
        self.assertEqual(statuses[0]["status"], "found")
        self.assertEqual(statuses[0]["request_id"], "REQ-2026-0001")


if __name__ == "__main__":
    unittest.main()
