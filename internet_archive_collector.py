#!/usr/bin/env python3
"""Discover Internet Archive public-domain candidates and download only manually approved items.

Search results are leads, not proof of copyright status. Downloads require an explicit
allowlist entry with independent verification evidence and a manually checked audio language.
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import quote, urlparse

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent
ALLOWLIST = ROOT / "config" / "internet_archive_public_domain.json"
METADATA_FILE = ROOT / "metadata.json"
VIDEO_DIR = ROOT / "input" / "videos"
THUMB_DIR = ROOT / "input" / "thumbnails"
CANDIDATE_REPORT = ROOT / "output" / "internet_archive_candidates.json"
ADVANCED_SEARCH = "https://archive.org/advancedsearch.php"
METADATA_API = "https://archive.org/metadata/{identifier}"
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"
THUMB_URL = "https://archive.org/services/img/{identifier}"
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm"}
DEFAULT_MAX_MB = 1500
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "MovieAutoPublisher/InternetArchiveCollector/1.0"})


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def valid_identifier(value):
    value = str(value or "").strip()
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{5,80}", value))


def public_domain_signal(metadata):
    """Require an IA public-domain license URL or an explicit public-domain rights statement."""
    license_url = str(metadata.get("licenseurl") or "").strip().lower()
    rights = str(metadata.get("rights") or "").strip().lower()
    recognized_license = (
        "creativecommons.org/publicdomain/mark/1.0" in license_url
        or "creativecommons.org/publicdomain/zero/1.0" in license_url
    )
    rights_statement = "public domain" in rights or "public-domain" in rights
    return recognized_license or rights_statement


def verification_is_independent(url):
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme in {"http", "https"}
        and bool(host)
        and host != "archive.org"
        and not host.endswith(".archive.org")
    )


def discover_candidates():
    """Write a review-only report. Nothing found here is automatically downloaded."""
    query = "mediatype:movies AND licenseurl:http*publicdomain*"
    report = {
        "created_at": utc_now(),
        "query": query,
        "warning": (
            "Candidates only. Internet Archive metadata and uploader claims are not independent "
            "proof. Verify the exact edition, soundtrack, public-domain status in India, and reuse "
            "rights before adding an item to the approved allowlist."
        ),
        "items": [],
    }
    try:
        response = SESSION.get(
            ADVANCED_SEARCH,
            params=[
                ("q", query),
                ("fl[]", "identifier"),
                ("fl[]", "title"),
                ("fl[]", "licenseurl"),
                ("fl[]", "rights"),
                ("fl[]", "date"),
                ("rows", "50"),
                ("page", "1"),
                ("output", "json"),
            ],
            timeout=(15, 45),
        )
        response.raise_for_status()
        payload = response.json()
        docs = payload.get("response", {}).get("docs", [])
        for doc in docs:
            identifier = str(doc.get("identifier") or "").strip()
            if not valid_identifier(identifier):
                continue
            report["items"].append({
                "identifier": identifier,
                "title": str(doc.get("title") or identifier),
                "archive_url": f"https://archive.org/details/{identifier}",
                "licenseurl": str(doc.get("licenseurl") or ""),
                "rights": str(doc.get("rights") or ""),
                "date": str(doc.get("date") or doc.get("year") or ""),
                "review_required": True,
                "approved_for_download": False,
            })
    except Exception as exc:
        report["error"] = f"Candidate discovery failed: {type(exc).__name__}: {exc}"
        print(report["error"], file=sys.stderr)
    write_json(CANDIDATE_REPORT, report)
    print(f"Review-only candidate report: {CANDIDATE_REPORT.relative_to(ROOT)} "
          f"({len(report['items'])} candidate(s))")
    return report


def fetch_item_metadata(identifier):
    response = SESSION.get(METADATA_API.format(identifier=quote(identifier, safe="")), timeout=(15, 45))
    response.raise_for_status()
    data = response.json()
    metadata = data.get("metadata") or {}
    if str(metadata.get("mediatype") or "").lower() != "movies":
        raise ValueError(f"{identifier}: Internet Archive mediatype is not movies")
    if not public_domain_signal(metadata):
        raise ValueError(
            f"{identifier}: Internet Archive metadata does not contain a recognized public-domain "
            "license URL or explicit public-domain rights statement"
        )
    return data, metadata


def choose_video_file(files, max_bytes):
    candidates = []
    for item in files or []:
        name = str(item.get("name") or "")
        if not name or Path(name).name != name or "/" in name or "\\" in name:
            continue
        if Path(name).suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if str(item.get("private") or "").lower() in {"true", "1", "yes"}:
            continue
        try:
            size = int(item.get("size") or 0)
        except (TypeError, ValueError):
            continue
        if size <= 0 or size > max_bytes:
            continue
        candidates.append((size, name, item))
    if not candidates:
        raise ValueError("No public, supported video file found within the configured size limit")
    candidates.sort(key=lambda row: row[0], reverse=True)
    return candidates[0][2]


def file_matches(path, item):
    try:
        if not path.is_file():
            return False
        expected_size = int(item.get("size") or 0)
        if expected_size and path.stat().st_size != expected_size:
            return False
        expected_md5 = str(item.get("md5") or "").strip().lower()
        if expected_md5:
            digest = hashlib.md5()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest().lower() != expected_md5:
                return False
        return True
    except (OSError, TypeError, ValueError):
        return False


def download_video(identifier, item, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if file_matches(target, item):
        print(f"REUSE verified local file: {target.relative_to(ROOT)}")
        return
    url = DOWNLOAD_URL.format(
        identifier=quote(identifier, safe=""),
        filename=quote(str(item["name"]), safe=""),
    )
    temp = target.with_suffix(target.suffix + ".part")
    digest = hashlib.md5()
    written = 0
    try:
        with SESSION.get(url, stream=True, timeout=(20, 90)) as response:
            response.raise_for_status()
            with temp.open("wb") as stream:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    written += len(chunk)
                    stream.write(chunk)
                    digest.update(chunk)
        expected_size = int(item.get("size") or 0)
        if expected_size and written != expected_size:
            raise ValueError(f"Downloaded size mismatch: expected {expected_size}, got {written}")
        expected_md5 = str(item.get("md5") or "").strip().lower()
        if expected_md5 and digest.hexdigest().lower() != expected_md5:
            raise ValueError("Downloaded file MD5 does not match Internet Archive metadata")
        temp.replace(target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def download_thumbnail(identifier, target):
    response = SESSION.get(THUMB_URL.format(identifier=quote(identifier, safe="")), timeout=(15, 45))
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content))
    image.load()
    if image.width < 64 or image.height < 64:
        raise ValueError("Internet Archive thumbnail is unexpectedly small")
    target.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(target, format="JPEG", quality=92, optimize=True)


def validate_approval(entry):
    identifier = str(entry.get("identifier") or "").strip()
    if not valid_identifier(identifier):
        raise ValueError("identifier is missing or invalid")
    if entry.get("verified_public_domain") is not True:
        raise ValueError(f"{identifier}: verified_public_domain must be true after manual review")
    if not verification_is_independent(entry.get("verification_url")):
        raise ValueError(f"{identifier}: verification_url must point to independent evidence outside archive.org")
    if len(str(entry.get("verification_note") or "").strip()) < 20:
        raise ValueError(f"{identifier}: add a meaningful verification_note (include India rights review)")
    language = str(entry.get("audio_language") or "").strip().lower()
    if language not in {"hi", "en"} or entry.get("audio_language_verified") is not True:
        raise ValueError(f"{identifier}: manually verify the actual audio track and set audio_language to hi/en")
    return identifier, language


def build_metadata_entry(entry, archive_metadata, video_path, thumb_path):
    identifier = str(entry["identifier"]).strip()
    title = str(archive_metadata.get("title") or identifier).strip()
    license_url = str(archive_metadata.get("licenseurl") or "").strip()
    rights = str(archive_metadata.get("rights") or "").strip()
    proof_url = str(entry["verification_url"]).strip()
    proof_note = str(entry["verification_note"]).strip()
    ia_url = f"https://archive.org/details/{identifier}"
    license_note = (
        f"Internet Archive item {ia_url}; IA licenseurl={license_url or 'not supplied'}; "
        f"IA rights={rights or 'not supplied'}; independently verified public-domain evidence: "
        f"{proof_url}; review note: {proof_note}"
    )
    return {
        "id": f"ia-{identifier}",
        "topic_id": f"ia-{identifier}",
        "source": video_path.relative_to(ROOT).as_posix(),
        "thumbnail": thumb_path.relative_to(ROOT).as_posix(),
        "type": "movie",
        "title": title,
        "licensed": True,
        "license": license_note,
        "source_url": ia_url,
        "rights_verification_url": proof_url,
        "rights_verification_note": proof_note,
        "adult": False,
        "edit_style": "clean",
        "description": (
            f"{title}. Source: {ia_url}. Public-domain verification evidence: {proof_url}. "
            f"{proof_note}"
        ),
        "tags": ["public-domain", "internet-archive", "classic-film", "VYROX-2008"],
        "privacy_status": "private",
        "audio_language": str(entry["audio_language"]).strip().lower(),
        "audio_language_verified": True,
        "category": "movie",
        "music_mood": "cinematic",
    }


def download_approved():
    config = read_json(ALLOWLIST, {"items": []})
    entries = config.get("items", []) if isinstance(config, dict) else []
    if not entries:
        print(
            "No approved Internet Archive items configured. No media downloaded; "
            "daily publisher credentials and upload settings were not changed."
        )
        return 0

    try:
        max_mb = max(100, int(os.getenv("IA_MAX_FILE_MB", str(DEFAULT_MAX_MB))))
    except ValueError:
        max_mb = DEFAULT_MAX_MB
    max_bytes = max_mb * 1024 * 1024
    metadata_doc = read_json(METADATA_FILE, {"items": []})
    existing = metadata_doc.get("items", []) if isinstance(metadata_doc, dict) else []
    by_id = {str(row.get("id")): row for row in existing if isinstance(row, dict) and row.get("id")}
    succeeded = 0
    errors = []
    try:
        max_items = max(1, min(5, int(os.getenv("IA_MAX_ITEMS_PER_RUN", "1"))))
    except ValueError:
        max_items = 1
    # Keep downloads small: select one allowlisted film per day by default and rotate through
    # the list using India-local date. Set IA_MAX_ITEMS_PER_RUN only when disk/network allow.
    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    start_index = today_ist.toordinal() % len(entries)
    selected_entries = [
        entries[(start_index + offset) % len(entries)]
        for offset in range(min(max_items, len(entries)))
    ]
    print(f"Selected {len(selected_entries)} approved film(s) for {today_ist.isoformat()} (Asia/Kolkata).")

    for entry in selected_entries:
        if not isinstance(entry, dict):
            errors.append("allowlist entry must be a JSON object")
            continue
        try:
            identifier, language = validate_approval(entry)
            data, archive_metadata = fetch_item_metadata(identifier)
            chosen = choose_video_file(data.get("files", []), max_bytes)
            extension = Path(str(chosen["name"])).suffix.lower()
            video_path = VIDEO_DIR / f"ia-{identifier}{extension}"
            thumb_path = THUMB_DIR / f"ia-{identifier}.jpg"
            download_video(identifier, chosen, video_path)
            try:
                download_thumbnail(identifier, thumb_path)
            except Exception:
                video_path.unlink(missing_ok=True)
                raise
            approved = dict(entry)
            approved["audio_language"] = language
            row = build_metadata_entry(approved, archive_metadata, video_path, thumb_path)
            by_id[row["id"]] = row
            succeeded += 1
            print(f"APPROVED SOURCE READY: {row['title']} ({video_path.relative_to(ROOT)})")
        except Exception as exc:
            message = f"{entry.get('identifier', 'unknown')}: {type(exc).__name__}: {exc}"
            errors.append(message)
            print("ERROR:", message, file=sys.stderr)

    if succeeded:
        metadata_doc = dict(metadata_doc) if isinstance(metadata_doc, dict) else {}
        metadata_doc["items"] = list(by_id.values())
        write_json(METADATA_FILE, metadata_doc)
        print(f"Updated metadata.json with {succeeded} approved Internet Archive source(s).")

    if errors:
        print("Collector stopped safely; one or more approved entries failed validation.", file=sys.stderr)
        for error in errors:
            print(" - " + error, file=sys.stderr)
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true", help="write review-only public-domain candidates")
    parser.add_argument("--download-approved", action="store_true", help="download only manually approved allowlist items")
    args = parser.parse_args()
    if not args.discover and not args.download_approved:
        parser.error("choose --discover and/or --download-approved")
    if args.discover:
        discover_candidates()
    if args.download_approved:
        return download_approved()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
