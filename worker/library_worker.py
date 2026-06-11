"""Family EPUB portal worker.

This worker is intentionally small: it reads a CSV queue, checks configured
lawful/authorized local EPUB folders, stages renamed files, and writes static
JSON data for the GitHub Pages portal.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


RESERVED_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*]')
WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class SourceMatch:
    label: str
    path: Path | None = None
    url: str = ""


def clean_text(value: str | None) -> str:
    """Return text that is safe for filenames and stable display."""
    if not value:
        return ""
    without_reserved = RESERVED_WINDOWS_CHARS.sub(" ", value)
    return WHITESPACE.sub(" ", without_reserved).strip()


def normalize(value: str | None) -> str:
    """Normalize text for simple title/author matching."""
    cleaned = clean_text(value).lower()
    return re.sub(r"[^a-z0-9]+", " ", cleaned).strip()


def format_author_for_filename(author: str) -> str:
    cleaned = clean_text(author)
    if not cleaned:
        return "Unknown Author"
    if "," in cleaned:
        return cleaned
    parts = cleaned.split()
    if len(parts) == 1:
        return parts[0]
    return f"{parts[-1]}, {' '.join(parts[:-1])}"


def build_filename(
    title: str,
    author: str,
    year: str | None = None,
    isbn: str | None = None,
) -> str:
    base = f"{format_author_for_filename(author)} - {clean_text(title)}"
    if year:
        base += f" ({clean_text(str(year))})"
    if isbn:
        base += f" [{clean_text(str(isbn))}]"
    return f"{base}.epub"


def open_csv_source(csv_path: str | Path):
    source = str(csv_path)
    if source.startswith(("https://", "http://")):
        with urlopen(source, timeout=30) as response:
            return io.StringIO(response.read().decode("utf-8-sig"))
    return Path(csv_path).open("r", newline="", encoding="utf-8-sig")


def first_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return value.strip()
    return ""


def load_requests(csv_path: str | Path) -> list[dict[str, str]]:
    with open_csv_source(csv_path) as handle:
        reader = csv.DictReader(handle)
        requests: list[dict[str, str]] = []
        for index, row in enumerate(reader, start=1):
            title = first_value(row, "title", "Title", "Book Title")
            author = first_value(row, "author", "Author", "Book Author")
            if not title:
                continue
            request_id = (
                row.get("request_id")
                or row.get("Request ID")
                or row.get("id")
                or f"REQ-{date.today().year}-{index:04d}"
            )
            requests.append(
                {
                    "request_id": request_id.strip(),
                    "title": title,
                    "author": author,
                    "isbn": first_value(row, "isbn", "ISBN"),
                    "email": first_value(row, "email", "Email", "Email Address"),
                    "notes": first_value(row, "notes", "Notes"),
                    "year": first_value(row, "year", "Year"),
                    "source_url": first_value(row, "source_url", "Source URL", "EPUB URL"),
                }
            )
    return requests


def normalize_request(item: dict[str, Any], index: int = 1) -> dict[str, str]:
    request_id = str(
        item.get("request_id")
        or item.get("Request ID")
        or item.get("id")
        or f"REQ-{date.today().year}-{index:04d}"
    )
    return {
        "request_id": request_id.strip(),
        "title": str(item.get("title") or item.get("Title") or "").strip(),
        "author": str(item.get("author") or item.get("Author") or "").strip(),
        "isbn": str(item.get("isbn") or item.get("ISBN") or "").strip(),
        "email": str(item.get("email") or item.get("Email") or item.get("Email Address") or "").strip(),
        "notes": str(item.get("notes") or item.get("Notes") or "").strip(),
        "year": str(item.get("year") or item.get("Year") or "").strip(),
        "source_url": str(item.get("source_url") or item.get("Source URL") or item.get("EPUB URL") or "").strip(),
    }


def parse_backend_requests(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows = payload.get("requests", [])
    return [
        request
        for index, item in enumerate(rows, start=1)
        if (request := normalize_request(item, index)).get("title")
    ]


def load_requests_from_backend(endpoint: str, secret: str = "") -> list[dict[str, str]]:
    params = {"action": "requests"}
    if secret:
        params["secret"] = secret
    separator = "&" if "?" in endpoint else "?"
    url = f"{endpoint}{separator}{urlencode(params)}"
    with urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_backend_requests(payload)


def find_local_epub(request: dict[str, str], source_dirs: list[str | Path]) -> Path | None:
    title = normalize(request.get("title"))
    author = normalize(request.get("author"))
    author_last = author.split()[-1] if author else ""

    for source_dir in source_dirs:
        root = Path(source_dir)
        if not root.exists():
            continue
        for candidate in sorted(root.rglob("*.epub")):
            stem = normalize(candidate.stem)
            title_matches = title and title in stem
            author_matches = not author_last or author_last in stem
            if title_matches and author_matches:
                return candidate
    return None


def find_local_match(request: dict[str, str], source_dirs: list[str | Path]) -> SourceMatch | None:
    path = find_local_epub(request, source_dirs)
    if path:
        return SourceMatch(label="Local folder", path=path)
    return None


def is_allowed_epub_url(url: str, allowed_domains: list[str]) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path.lower()
    if parsed.scheme != "https" or not path.endswith(".epub"):
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)


def find_direct_url_match(request: dict[str, str], allowed_domains: list[str]) -> SourceMatch | None:
    url = request.get("source_url", "")
    if is_allowed_epub_url(url, allowed_domains):
        host = urlparse(url).hostname or "Direct URL"
        return SourceMatch(label=host, url=url)
    return None


def select_gutendex_candidate(request: dict[str, str], payload: dict[str, Any]) -> SourceMatch | None:
    title = normalize(request.get("title"))
    author = normalize(request.get("author"))
    author_last = author.split()[-1] if author else ""

    for result in payload.get("results", []):
        result_title = normalize(str(result.get("title", "")))
        author_names = " ".join(author.get("name", "") for author in result.get("authors", []))
        result_author = normalize(author_names)
        title_matches = title and title in result_title
        author_matches = not author_last or author_last in result_author
        if not title_matches or not author_matches:
            continue
        formats = result.get("formats", {})
        for mime, url in formats.items():
            if "epub" in mime.lower() and isinstance(url, str) and url.startswith("https://"):
                return SourceMatch(label="Project Gutenberg", url=url)
    return None


def find_gutendex_match(
    request: dict[str, str],
    base_url: str,
    timeout_seconds: int = 8,
) -> SourceMatch | None:
    query = " ".join(part for part in [request.get("title", ""), request.get("author", "")] if part)
    url = f"{base_url}?{urlencode({'search': query, 'languages': 'en'})}"
    http_request = Request(url, headers={"User-Agent": "FamilyEpubPortal/1.0"})
    with urlopen(http_request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return select_gutendex_candidate(request, payload)


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def build_drive_destination(config: dict[str, Any]) -> str:
    remote = str(config.get("drive_remote", "")).rstrip(":")
    folder = str(config.get("drive_folder", "")).strip().strip("/")
    if not remote:
        return ""
    return f"{remote}:{folder}" if folder else f"{remote}:"


def upload_file(staged_path: Path, drive_destination: str, rclone_path: str) -> None:
    if drive_destination:
        subprocess.run([rclone_path, "copy", str(staged_path), drive_destination], check=True)


def stage_source_file(
    source: Path,
    staged_path: Path,
) -> None:
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, staged_path)


def download_epub_url(url: str, staged_path: Path) -> None:
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "FamilyEpubPortal/1.0"})
    with urlopen(request, timeout=60) as response:
        staged_path.write_bytes(response.read())


def find_configured_match(request: dict[str, str], config: dict[str, Any]) -> SourceMatch | None:
    local = find_local_match(request, config.get("local_sources", []))
    if local:
        return local

    direct = find_direct_url_match(request, config.get("direct_url_allowed_domains", []))
    if direct:
        return direct

    if config.get("gutendex_enabled"):
        try:
            return find_gutendex_match(
                request,
                config.get("gutendex_base_url", "https://gutendex.com/books"),
                int(config.get("source_timeout_seconds", 8)),
            )
        except Exception as error:
            print(
                f"Source warning: Gutendex lookup failed for {request.get('request_id', '')}: {error}",
                file=sys.stderr,
            )
            return None

    return None


def load_configured_requests(config: dict[str, Any]) -> list[dict[str, str]]:
    if config.get("requests_backend_url"):
        return load_requests_from_backend(
            endpoint=config["requests_backend_url"],
            secret=config.get("requests_backend_secret", ""),
        )
    return load_requests(config["requests_csv"])


def run_worker(config: dict[str, Any], dry_run: bool = False) -> dict[str, int]:
    requests = load_configured_requests(config)
    staging_dir = Path(config.get("staging_dir", "staging"))
    drive_destination = build_drive_destination(config)
    today = date.today().isoformat()

    latest_books: list[dict[str, str]] = []
    statuses: list[dict[str, str]] = []
    matched = 0
    uploaded = 0

    for request in requests:
        match = find_configured_match(request, config)
        if not match:
            statuses.append(
                {
                    "request_id": request["request_id"],
                    "title": request["title"],
                    "author": request["author"],
                    "status": "not_found",
                    "last_checked": today,
                    "notes": "No matching authorized EPUB source found.",
                }
            )
            continue

        matched += 1
        filename = build_filename(
            title=request["title"],
            author=request["author"],
            year=request.get("year"),
            isbn=request.get("isbn"),
        )
        staged_path = staging_dir / filename

        if not dry_run:
            if match.path:
                stage_source_file(source=match.path, staged_path=staged_path)
            else:
                download_epub_url(match.url, staged_path)
            upload_file(
                staged_path=staged_path,
                drive_destination=drive_destination,
                rclone_path=config.get("rclone_path", "rclone"),
            )
            uploaded += 1

        status = "found" if dry_run else "uploaded"
        latest_books.append(
            {
                "title": request["title"],
                "author": request["author"],
                "added": today,
                "source": match.label,
                "filename": filename,
            }
        )
        statuses.append(
            {
                "request_id": request["request_id"],
                "title": request["title"],
                "author": request["author"],
                "status": status,
                "last_checked": today,
                "notes": "Matched authorized EPUB source.",
            }
        )

    write_json(config["latest_json"], latest_books)
    write_json(config["status_json"], statuses)
    return {"requests": len(requests), "matched": matched, "uploaded": uploaded}


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)

    worker = raw.get("worker", {})
    site = raw.get("site", {})
    google_drive = raw.get("google_drive", {})
    sources = raw.get("sources", {})
    backend = raw.get("request_backend", {})

    return {
        "requests_csv": worker.get("requests_csv", "requests.example.csv"),
        "requests_backend_url": backend.get("url", ""),
        "requests_backend_secret": backend.get("secret", ""),
        "staging_dir": worker.get("staging_dir", "staging"),
        "latest_json": site.get("latest_json", "../site/data/latest-books.json"),
        "status_json": site.get("status_json", "../site/data/request-status.json"),
        "local_sources": sources.get("local_folders", []),
        "direct_url_allowed_domains": sources.get("direct_url_allowed_domains", []),
        "gutendex_enabled": sources.get("gutendex_enabled", True),
        "gutendex_base_url": sources.get("gutendex_base_url", "https://gutendex.com/books"),
        "source_timeout_seconds": sources.get("timeout_seconds", 8),
        "drive_remote": google_drive.get("rclone_remote", "gdrive"),
        "drive_folder": google_drive.get("folder", ""),
        "rclone_path": google_drive.get("rclone_path", "rclone"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Family EPUB Portal worker.")
    parser.add_argument("--config", default="config.example.toml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    config = load_config(config_path)

    # Resolve relative paths from the config file location.
    base = config_path.resolve().parent
    for key in ("requests_csv", "staging_dir", "latest_json", "status_json"):
        path = Path(config[key])
        if key == "requests_csv" and str(config[key]).startswith(("https://", "http://")):
            continue
        if not path.is_absolute():
            config[key] = str(base / path)
    config["local_sources"] = [
        str(base / path) if not Path(path).is_absolute() else str(path)
        for path in config["local_sources"]
    ]

    summary = run_worker(config, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
